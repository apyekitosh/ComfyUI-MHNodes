"""Record of models pulled from the server.

The registry is the only authority for deletion: the purge removes exactly what is listed here
and nothing else, so a model installed by hand can never be collected. Losing the registry
strands pulled files on disk forever, which is the failure we want over the alternative.

Entry shape, keyed by "<folder_type>/<relative path>":

    {
        "pulled":    ISO timestamp of the copy,
        "last_used": ISO timestamp a workflow last referenced it,
        "kept":      True to exempt it from the purge,
        "path":      absolute path written,
        "size":      byte size at pull time,
        "mtime":     modification time at pull time,
    }

`size` and `mtime` are the tamper check: if either differs at purge time the file on disk is no
longer the one we wrote, so it is somebody else's and gets left alone.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

from . import config

log = logging.getLogger("MHNodes.ModelPuller")

FLUSH_INTERVAL = 5.0  # seconds; writes are ~2ms but there is no reason to do them inline


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return None


def key_for(folder_type: str, relative_path: str) -> str:
    return f"{folder_type}/{relative_path}".replace("\\", "/")


class Registry:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(config.data_dir(), "model_registry.json")
        self._lock = threading.RLock()
        self._entries: dict[str, dict] = {}
        self._dirty = False
        self._stop = threading.Event()
        self._load()

    # -- persistence ------------------------------------------------------------------

    def _load(self) -> None:
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                self._entries = loaded
        except Exception as exc:
            # A corrupt registry must not take the install down, and must not be overwritten
            # blindly either -- keep a copy so the entries can be recovered by hand.
            log.error("registry unreadable (%s); starting empty", exc)
            try:
                os.replace(self.path, self.path + ".corrupt")
            except OSError:
                pass

    def flush(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            snapshot = dict(self._entries)
            self._dirty = False

        temp = self.path + ".tmp"
        try:
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump(snapshot, handle, indent=2, sort_keys=True)
            os.replace(temp, self.path)
        except Exception as exc:
            log.error("could not write registry: %s", exc)
            with self._lock:
                self._dirty = True

    def start_autoflush(self) -> None:
        def loop():
            while not self._stop.wait(FLUSH_INTERVAL):
                self.flush()

        threading.Thread(target=loop, name="MHNodes-registry-flush", daemon=True).start()
        atexit.register(self.flush)

    # -- queries ----------------------------------------------------------------------

    def all(self) -> dict[str, dict]:
        with self._lock:
            return {k: dict(v) for k, v in self._entries.items()}

    def get(self, key: str) -> dict | None:
        with self._lock:
            entry = self._entries.get(key)
            return dict(entry) if entry else None

    # -- mutations --------------------------------------------------------------------

    def record_pull(self, key: str, path: str) -> None:
        stamp = now()
        try:
            stat = os.stat(path)
            size, mtime = stat.st_size, stat.st_mtime
        except OSError:
            size, mtime = None, None

        with self._lock:
            existing = self._entries.get(key, {})
            self._entries[key] = {
                "pulled": stamp,
                "last_used": existing.get("last_used") or stamp,
                "kept": bool(existing.get("kept", False)),
                "path": path,
                "size": size,
                "mtime": mtime,
            }
            self._dirty = True

    def touch(self, key: str) -> None:
        """Mark a model as used now. No-op for anything we did not pull."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return
            entry["last_used"] = now()
            self._dirty = True

    def set_kept(self, key: str, kept: bool) -> bool:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            entry["kept"] = bool(kept)
            self._dirty = True
        return True

    def forget(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)
            self._dirty = True


_registry: Registry | None = None


def instance() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
        _registry.start_autoflush()
    return _registry
