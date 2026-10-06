"""Working out which model folder a node's widget draws from.

A loader's combo is populated by ``folder_paths.get_filename_list(folder)``, but the folder name
itself never reaches the client -- only the resulting list of filenames. So the mapping is
recovered by comparing each combo's options against each folder's listing. Measured on a heavily
modded install this resolves ~94% of model combos, including custom packs, with no cooperation
from the node author.

Exact set equality is too strict: several nodes decorate the list (VAELoader appends taesd
entries, easy fullLoader prepends "None"), so the match is scored by coverage instead.
"""

from __future__ import annotations

import logging
import os
import threading

log = logging.getLogger("MHNodes.ModelPuller")

MODEL_EXTENSIONS = (
    ".safetensors", ".ckpt", ".pt", ".pth", ".gguf", ".sft",
    ".bin", ".onnx", ".engine", ".pkl",
)

#: Entries in folder_names_and_paths that hold no model weights. "configs" is full of .yaml and
#: "custom_nodes" can contain stray .pt/.bin files from a pack, either of which would otherwise
#: look like a model folder and produce bogus matches.
NON_MODEL_FOLDERS = frozenset({"configs", "custom_nodes"})

MIN_COVERAGE = 0.5

_lock = threading.Lock()
_cache: dict[tuple[str, str], str] | None = None


def looks_like_model(value) -> bool:
    return isinstance(value, str) and value.lower().endswith(MODEL_EXTENSIONS)


def _folder_listings() -> dict[str, set]:
    """Model folders that currently hold model files.

    folder_names_and_paths also carries non-model entries such as "configs" and "custom_nodes";
    requiring at least one model-looking file keeps those from producing spurious matches.
    """
    import folder_paths

    listings = {}
    for name in folder_paths.folder_names_and_paths:
        if name in NON_MODEL_FOLDERS:
            continue
        try:
            files = folder_paths.get_filename_list(name)
        except Exception:
            continue
        if files and any(looks_like_model(f) for f in files):
            listings[name] = set(files)
    return listings


def _resolve(options, listings: dict[str, set]) -> str | None:
    """Folder whose listing best covers this combo's real file entries."""
    files = {o for o in options if looks_like_model(o)}
    if not files:
        return None

    best_score, winners = 0.0, []
    for name, listing in listings.items():
        score = len(files & listing) / len(files)
        if score > best_score:
            best_score, winners = score, [name]
        elif score == best_score and score > 0:
            winners.append(name)

    if best_score < MIN_COVERAGE or not winners:
        return None

    if len(winners) > 1:
        # Folders that are merely aliases of each other (llm/LLM, depth_anything_3 vs
        # depthanything3) resolve to the same directories, so either answer is correct.
        import folder_paths

        resolved = set()
        for name in winners:
            try:
                paths = folder_paths.get_folder_paths(name)
            except Exception:
                # Unknown to this install; treat the tie as unresolvable rather than guessing.
                log.debug("ambiguous model folder for combo: %s", winners)
                return None
            resolved.add(tuple(sorted(os.path.normcase(os.path.abspath(p)) for p in paths)))
        if len(resolved) > 1:
            log.debug("ambiguous model folder for combo: %s", winners)
            return None

    return sorted(winners)[0]


def build_map(force: bool = False) -> dict[tuple[str, str], str]:
    """Map of (node_type, input_name) -> folder name, built once and cached."""
    global _cache
    with _lock:
        if _cache is not None and not force:
            return _cache

        mapping: dict[tuple[str, str], str] = {}
        ready = False
        try:
            import nodes

            listings = _folder_listings()
            # Model paths are configured after this pack is imported, so an early call sees
            # empty folders and would resolve nothing useful. Treat that as "not ready" rather
            # than caching a map built from nothing.
            ready = bool(listings)
            for node_type, node_class in nodes.NODE_CLASS_MAPPINGS.items():
                try:
                    spec = node_class.INPUT_TYPES()
                except Exception:
                    continue
                for section in ("required", "optional"):
                    for input_name, definition in (spec.get(section) or {}).items():
                        if not (isinstance(definition, (list, tuple)) and definition):
                            continue
                        options = definition[0]
                        if not isinstance(options, (list, tuple)) or not options:
                            continue
                        if not any(looks_like_model(o) for o in options):
                            continue
                        folder = _resolve(options, listings)
                        if folder:
                            mapping[(node_type, input_name)] = folder
        except Exception as exc:
            log.warning("could not build the model folder map: %s", exc)

        # Custom node packs load in an arbitrary order, so an early call can also see a
        # half-built NODE_CLASS_MAPPINGS. Caching either kind of partial result would poison the
        # map for the whole session, so only a map built from real folders is kept.
        if ready and mapping:
            _cache = mapping
            log.info("model folder map: %d loader inputs resolved", len(mapping))
        else:
            log.debug("model folders not ready yet (%d resolved); will rebuild", len(mapping))
        return mapping


def invalidate() -> None:
    global _cache
    with _lock:
        _cache = None


def roots_for(folder_type: str) -> list[str]:
    """Registered directories ComfyUI searches for this model type, as absolute paths."""
    try:
        import folder_paths

        return [os.path.abspath(p) for p in folder_paths.get_folder_paths(folder_type)]
    except Exception:
        return []


def all_roots() -> dict[str, list[str]]:
    """Every model type mapped to the directories ComfyUI searches for it."""
    try:
        import folder_paths

        names = [n for n in folder_paths.folder_names_and_paths if n not in NON_MODEL_FOLDERS]
    except Exception:
        return {}
    return {name: roots_for(name) for name in sorted(names)}


def _in_source_dir(path: str) -> bool:
    """True for paths inside the directory ComfyUI's own code lives in.

    On the Desktop build that is the Electron app bundle, which an update replaces wholesale --
    a bad place to park a 20 GB model. This deliberately keys on the *source* location rather
    than folder_paths.base_path: Desktop launches with --base-directory pointing at the user's
    data root (C:\\ComfyUI), so base_path is where the real models live, not the install.
    """
    try:
        import folder_paths

        source = os.path.dirname(os.path.realpath(folder_paths.__file__))
    except Exception:
        return False
    source = os.path.normcase(source)
    return os.path.normcase(os.path.realpath(path)).startswith(source + os.sep)


def destination_root(folder_type: str, preferred: str = "") -> str | None:
    """Where a pulled model of this type should land.

    Always one of the directories ComfyUI already searches, so a pulled model is findable by
    construction -- there is no way to write it somewhere invisible.

    When a type has several registered folders the choice is, in order: an explicit preference,
    then whichever folder already holds the most models of that type -- that is where this
    install actually keeps them, and it is the signal that works everywhere. Only when that
    cannot separate them (typically all empty) does it fall back to avoiding ComfyUI's own
    source directory.
    """
    candidates = roots_for(folder_type)
    if not candidates:
        return None

    def prefer_named(options: list[str]) -> list[str]:
        """Narrow to the folder actually named after this type, when one is present.

        Several types register legacy aliases -- diffusion_models also searches unet,
        text_encoders also searches clip, controlnet also searches t2i_adapter -- and those can
        come first in the candidate list. Landing a pull in one works, but it is not where
        anybody would look for it.
        """
        named = [o for o in options
                 if os.path.basename(o.rstrip(os.sep)).lower() == folder_type.lower()]
        return named or options

    if preferred:
        prefix = os.path.normcase(os.path.abspath(preferred))
        under = [c for c in candidates if os.path.normcase(c).startswith(prefix)]
        if under:
            return prefer_named(under)[0]
        # Nothing registered for this type under the preferred root, so fall through rather
        # than writing somewhere ComfyUI does not search for it.

    if len(candidates) == 1:
        return candidates[0]

    def populated(path: str) -> int:
        count = 0
        for _, _, files in os.walk(path):
            count += sum(1 for f in files if looks_like_model(f))
            if count > 500:  # enough to rank it; no need to walk a huge tree fully
                break
        return count

    # Several registered names can point at one directory through a junction or symlink, so
    # compare resolved paths rather than the names when counting them as distinct.
    counts = {c: populated(c) for c in candidates}
    best = max(counts.values())
    leaders = [c for c in candidates if counts[c] == best]

    if len(leaders) > 1:
        # Nothing separates them by content. Avoid the app bundle first...
        outside = [c for c in leaders if not _in_source_dir(c)]
        if outside:
            leaders = outside
        elif best == 0:
            log.warning(
                "every registered folder for '%s' is inside the ComfyUI install, which a "
                "Desktop update replaces. Consider adding one outside it.", folder_type
            )

    # ...then prefer the folder actually named after this type.
    return prefer_named(leaders)[0]


def find_local(folder_type: str, relative_path: str) -> str | None:
    """Absolute path if this model already exists in any registered folder for its type."""
    try:
        import folder_paths

        return folder_paths.get_full_path(folder_type, relative_path)
    except Exception:
        return None
