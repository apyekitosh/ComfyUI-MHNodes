"""Deleting models nobody has used lately.

Runs once at startup, which is when nothing is loaded and nobody has a session open. Only files
the registry recorded are ever considered, and each is checked against the size and mtime we
wrote before being removed -- if either differs, somebody replaced that file by hand and it is
no longer ours to delete.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone

from . import config, registry

log = logging.getLogger("MHNodes.ModelPuller")


def _unchanged(entry: dict, path: str) -> bool:
    try:
        stat = os.stat(path)
    except OSError:
        return False

    size, mtime = entry.get("size"), entry.get("mtime")
    if size is not None and stat.st_size != size:
        return False
    # Filesystems round mtime differently across copies; a second of slack avoids false alarms.
    if mtime is not None and abs(stat.st_mtime - mtime) > 1.0:
        return False
    return True


def expired(entry: dict, days: int, reference: datetime | None = None) -> bool:
    if entry.get("kept"):
        return False
    stamp = registry.parse(entry.get("last_used")) or registry.parse(entry.get("pulled"))
    if stamp is None:
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (reference or datetime.now(timezone.utc)) - stamp > timedelta(days=days)


#: Only a leftover from our own copy loop looks like this: a model filename plus ".part".
MODEL_SUFFIXES = (
    ".safetensors", ".ckpt", ".pt", ".pth", ".gguf", ".sft",
    ".bin", ".onnx", ".engine", ".pkl",
)

#: Don't touch something a copy might still be writing, in case a second instance is running.
MIN_PART_AGE = 300  # seconds


def sweep_partials(dry_run: bool = False) -> list[str]:
    """Delete .part files left behind when ComfyUI died mid-copy.

    Cancelling cleans up after itself, but a hard crash or a killed process skips the handler
    that would have, leaving a partial file that can be tens of gigabytes. Startup is the safe
    moment to collect them: nothing of ours is copying yet.
    """
    from . import folders

    # One root can be registered under several names, or reached through a junction, so walk
    # each physical directory once.
    roots, seen = [], set()
    for folder_type in folders.all_roots():
        destination = folders.destination_root(folder_type)
        if not destination:
            continue
        key = os.path.normcase(os.path.realpath(destination))
        if key not in seen:
            seen.add(key)
            roots.append(destination)

    now = time.time()
    removed = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for folder, _, files in os.walk(root):
            for name in files:
                if not name.endswith(".part"):
                    continue
                if not name[:-5].lower().endswith(MODEL_SUFFIXES):
                    continue
                path = os.path.join(folder, name)
                try:
                    if now - os.path.getmtime(path) < MIN_PART_AGE:
                        continue
                    size = os.path.getsize(path)
                except OSError:
                    continue
                if dry_run:
                    removed.append(path)
                    continue
                try:
                    os.remove(path)
                    removed.append(path)
                    log.info("removed stale partial %s (%.1f GB)", path, size / 2**30)
                except OSError as exc:
                    log.warning("could not remove partial %s: %s", path, exc)
    return removed


def run(dry_run: bool = False) -> dict:
    """Delete expired pulls. Returns a summary of what happened."""
    settings = config.load()
    result = {"deleted": [], "kept": 0, "skipped": [], "missing": [],
              "partials": [], "dry_run": dry_run}

    # Stale partials are swept even when cleanup is off: they are never wanted, and they are
    # ours by construction rather than a model somebody chose to keep.
    try:
        result["partials"] = sweep_partials(dry_run)
    except Exception as exc:
        log.warning("could not sweep partial files: %s", exc)

    if not settings.get("Enabled", True):
        log.info("purge skipped: model puller disabled")
        return result

    try:
        days = max(1, int(settings.get("PurgeDays", 7)))
    except (TypeError, ValueError):
        days = 7

    reg = registry.instance()
    for key, entry in reg.all().items():
        if entry.get("kept"):
            result["kept"] += 1
            continue
        if not expired(entry, days):
            continue

        path = entry.get("path")
        if not path or not os.path.exists(path):
            # Already gone by other means; drop the stale row.
            result["missing"].append(key)
            if not dry_run:
                reg.forget(key)
            continue

        if not _unchanged(entry, path):
            log.warning("skipping %s: file changed since it was pulled", key)
            result["skipped"].append(key)
            continue

        if dry_run:
            result["deleted"].append(key)
            continue

        try:
            os.remove(path)
            reg.forget(key)
            result["deleted"].append(key)
            log.info("purged %s (unused for over %d days)", key, days)
        except OSError as exc:
            log.error("could not delete %s: %s", path, exc)
            result["skipped"].append(key)

    if not dry_run:
        reg.flush()

    if result["deleted"] or result["skipped"] or result["partials"]:
        log.info(
            "purge: %d deleted, %d kept, %d skipped, %d stale partials",
            len(result["deleted"]), result["kept"], len(result["skipped"]),
            len(result["partials"]),
        )
    return result
