"""Recording when a model was last used.

ComfyUI exposes no execution hook, so both of these are patches. Each is wrapped defensively:
if a future ComfyUI changes something underneath, tracking degrades to not recording rather than
breaking model loading. A stale purge is an annoyance; a broken get_full_path is a dead install.

Two hooks, because neither alone is correct:

* ``folder_paths.get_full_path`` sees every model a loader actually resolves, with the folder
  name and filename already separated. But ComfyUI caches node outputs, so re-running a workflow
  does not re-execute the loader -- a model used daily could look untouched for a week.
* Walking the prompt on submission catches those cached runs. Measured at ~30 microseconds for a
  67-node workflow, so it costs nothing at queue time.
"""

from __future__ import annotations

import logging

from . import folders, registry

log = logging.getLogger("MHNodes.ModelPuller")

_patched = False


def note_use(folder_type: str, relative_path: str) -> None:
    if not folder_type or not isinstance(relative_path, str):
        return
    try:
        registry.instance().touch(registry.key_for(folder_type, relative_path))
    except Exception:
        pass  # tracking must never be able to break a load


def _patch_get_full_path() -> None:
    import folder_paths

    original = folder_paths.get_full_path
    if getattr(original, "_mhnodes_wrapped", False):
        return

    def wrapper(folder_name, filename, *args, **kwargs):
        result = original(folder_name, filename, *args, **kwargs)
        if result is not None:
            note_use(folder_name, filename)
        return result

    wrapper._mhnodes_wrapped = True
    wrapper.__wrapped__ = original
    folder_paths.get_full_path = wrapper
    log.info("usage tracking: get_full_path hooked")


def walk_prompt(prompt: dict) -> int:
    """Mark every model a submitted prompt references. Returns how many were matched."""
    mapping = folders.build_map()
    if not mapping:
        return 0

    seen = 0
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        node_type = node.get("class_type")
        inputs = node.get("inputs")
        if not node_type or not isinstance(inputs, dict):
            continue
        for input_name, value in inputs.items():
            if not folders.looks_like_model(value):
                continue
            folder_type = mapping.get((node_type, input_name))
            if folder_type:
                note_use(folder_type, value)
                seen += 1
    return seen


def _patch_prompt_route() -> None:
    from server import PromptServer

    instance = getattr(PromptServer, "instance", None)
    app = getattr(instance, "app", None)
    if app is None:
        log.debug("usage tracking: server not ready, prompt hook skipped")
        return

    if getattr(app, "_mhnodes_prompt_tracked", False):
        return

    @_middleware
    async def tracker(request, handler):
        if request.method == "POST" and request.path.rstrip("/").endswith("/prompt"):
            try:
                # aiohttp caches the body, so reading it here does not consume it for
                # ComfyUI's own handler further down the chain.
                payload = await request.json()
                prompt = payload.get("prompt")
                if isinstance(prompt, dict):
                    walk_prompt(prompt)
            except Exception:
                pass
        return await handler(request)

    app.middlewares.append(tracker)
    app._mhnodes_prompt_tracked = True
    log.info("usage tracking: prompt submissions hooked")


def _middleware(func):
    from aiohttp import web

    return web.middleware(func)


def install() -> None:
    """Apply both hooks. Any failure disables that hook and leaves ComfyUI untouched."""
    global _patched
    if _patched:
        return
    _patched = True

    for name, patch in (("get_full_path", _patch_get_full_path),
                        ("prompt route", _patch_prompt_route)):
        try:
            patch()
        except Exception as exc:
            log.warning("usage tracking disabled for %s: %s", name, exc)
