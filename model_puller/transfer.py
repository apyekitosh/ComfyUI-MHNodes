"""Copying models from the server.

Copies run in a worker thread and report progress over the websocket. Three things matter here
beyond moving bytes: an interrupted copy must never leave a file that looks complete, the
destination must stay inside the configured roots, and there has to be room before starting.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time

log = logging.getLogger("MHNodes.ModelPuller")

#: Large enough that syscall overhead is irrelevant over SMB, small enough for smooth progress.
CHUNK = 8 * 1024 * 1024

#: Don't fill the disk completely.
HEADROOM = 512 * 1024 * 1024


class TransferError(Exception):
    pass


def contained_in(root: str, candidate: str) -> bool:
    """True when candidate resolves to somewhere inside root."""
    try:
        root_abs = os.path.realpath(root)
        candidate_abs = os.path.realpath(candidate)
    except OSError:
        return False
    return os.path.normcase(candidate_abs).startswith(os.path.normcase(os.path.join(root_abs, "")))


def safe_join(root: str, relative: str) -> str:
    """Join under root, rejecting anything that escapes it."""
    relative = relative.replace("\\", "/").lstrip("/")
    if not relative:
        raise TransferError("empty path")
    target = os.path.normpath(os.path.join(root, relative))
    if not contained_in(root, target) and os.path.normcase(os.path.realpath(target)) != \
            os.path.normcase(os.path.realpath(root)):
        raise TransferError(f"path escapes its root: {relative!r}")
    return target


def copy_with_progress(source: str, destination: str, on_progress=None,
                       cancel: threading.Event | None = None) -> int:
    """Copy source to destination, writing to a .part file and renaming only on success.

    Returns the number of bytes written. Raises TransferError on any failure, leaving no
    partial file behind.
    """
    if not os.path.isfile(source):
        raise TransferError(f"source does not exist: {source}")

    total = os.path.getsize(source)
    os.makedirs(os.path.dirname(destination), exist_ok=True)

    try:
        free = shutil.disk_usage(os.path.dirname(destination)).free
    except OSError:
        free = None
    if free is not None and free < total + HEADROOM:
        raise TransferError(
            f"not enough space: needs {total / 2**30:.1f} GB, {free / 2**30:.1f} GB free"
        )

    partial = destination + ".part"
    copied = 0
    last_report = 0.0

    try:
        with open(source, "rb") as src, open(partial, "wb") as dst:
            while True:
                if cancel is not None and cancel.is_set():
                    raise TransferError("cancelled")
                block = src.read(CHUNK)
                if not block:
                    break
                dst.write(block)
                copied += len(block)

                now = time.monotonic()
                if on_progress and (now - last_report > 0.25 or copied == total):
                    on_progress(copied, total)
                    last_report = now

        if copied != total:
            raise TransferError(f"short read: {copied} of {total} bytes")

        # Only now does a file appear at the real name, so a crash can never leave a
        # truncated model that looks loadable.
        os.replace(partial, destination)
    except TransferError:
        _discard(partial)
        raise
    except Exception as exc:
        _discard(partial)
        raise TransferError(str(exc)) from exc

    if on_progress:
        on_progress(total, total)
    return total


def _discard(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as exc:
        log.warning("could not remove partial file %s: %s", path, exc)
