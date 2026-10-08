"""Shared storage for latents saved alongside a visual preview.

Both files live in ``input/latents`` under the same stem -- ``take_00001_.latent`` next to
``take_00001_.webp``. Keeping them in *input* rather than *output* is deliberate: ComfyUI's own
SaveLatent writes to output while LoadLatent reads from input, so files have to be moved by hand.
Here the loader sees what the saver wrote, immediately.

The pairing is what makes the loader free of custom frontend code. Its combo lists the previews,
which the frontend already knows how to render, and the latent is found from the stem.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("MHNodes.LatentStore")

SUBFOLDER = "latents"
PREVIEW_EXT = ".webp"
LATENT_EXT = ".latent"


def root() -> str:
    """Directory holding the pairs, created on demand."""
    import folder_paths

    path = os.path.join(folder_paths.get_input_directory(), SUBFOLDER)
    os.makedirs(path, exist_ok=True)
    return path


def list_previews() -> list[str]:
    """Previews that have a latent beside them, as paths relative to the input directory.

    Walks subfolders, which core's own loaders do not -- their flat os.listdir is why a pasted
    image never shows up in LoadImage's dropdown even though the value works.
    """
    base = root()
    found = []
    for folder, _, files in os.walk(base):
        for name in files:
            if not name.lower().endswith(PREVIEW_EXT):
                continue
            if not os.path.isfile(os.path.join(folder, _latent_name(name))):
                continue
            relative = os.path.relpath(os.path.join(folder, name), os.path.dirname(base))
            found.append(relative.replace("\\", "/"))
    return sorted(found)


def _latent_name(preview_name: str) -> str:
    return os.path.splitext(preview_name)[0] + LATENT_EXT


def latent_for(preview_value: str) -> str | None:
    """Absolute path of the latent paired with a combo value, or None if it is missing."""
    import folder_paths

    try:
        preview_path = folder_paths.get_annotated_filepath(preview_value)
    except Exception:
        return None

    candidate = os.path.join(os.path.dirname(preview_path), _latent_name(os.path.basename(preview_path)))
    return candidate if os.path.isfile(candidate) else None


def _within_root(path: str) -> bool:
    base = os.path.realpath(root())
    target = os.path.realpath(path)
    return os.path.normcase(target).startswith(os.path.normcase(base + os.sep))


def discard(preview_value: str) -> dict:
    """Delete a preview and its latent together. Only ever touches files under the store."""
    import folder_paths

    removed, missing = [], []
    try:
        preview_path = folder_paths.get_annotated_filepath(preview_value)
    except Exception as exc:
        raise ValueError(f"bad path: {exc}") from exc

    latent_path = os.path.join(
        os.path.dirname(preview_path), _latent_name(os.path.basename(preview_path))
    )

    for path in (preview_path, latent_path):
        if not _within_root(path):
            raise ValueError("refusing to delete outside the latent store")
        if not os.path.isfile(path):
            missing.append(os.path.basename(path))
            continue
        try:
            os.remove(path)
            removed.append(os.path.basename(path))
        except OSError as exc:
            raise ValueError(f"could not delete {os.path.basename(path)}: {exc}") from exc

    log.info("discarded %s", ", ".join(removed) or "nothing")
    return {"removed": removed, "missing": missing}


def setup() -> None:
    """Register the discard route. Deletion is deliberately not a node: it must never be
    something a workflow does by being run."""
    try:
        from aiohttp import web
        from server import PromptServer

        routes = PromptServer.instance.routes

        @routes.post("/mhnodes/latent_store/discard")
        async def _discard(request):
            body = await request.json()
            value = (body or {}).get("path")
            if not value:
                raise web.HTTPBadRequest(reason="Missing path")
            try:
                return web.json_response(discard(value))
            except ValueError as exc:
                raise web.HTTPBadRequest(reason=str(exc))

        @routes.get("/mhnodes/latent_store/list")
        async def _list(request):
            return web.json_response({"previews": list_previews()})

        log.info("latent store routes registered")
    except Exception as exc:
        log.error("could not register latent store routes: %s", exc)
