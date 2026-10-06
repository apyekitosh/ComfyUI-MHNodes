"""HTTP routes backing the model browser.

Every path that arrives from the client is confined to the configured roots before it is used,
and the only files that can be removed are ones the registry already recorded.
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from aiohttp import web

from . import config, folders, purge, registry, transfer

log = logging.getLogger("MHNodes.ModelPuller")

PREFIX = "/mhnodes/model_puller"

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="MHNodes-pull")
_active: dict[str, threading.Event] = {}


def _notify(event: str, payload: dict) -> None:
    try:
        from server import PromptServer

        PromptServer.instance.send_sync(f"mhnodes.model_puller.{event}", payload)
    except Exception:
        pass


def _server_root() -> str:
    root = (config.load().get("ServerPath") or "").strip()
    if not root:
        raise web.HTTPBadRequest(reason="Server path is not set in Settings > MHNodes")
    if not os.path.isdir(root):
        raise web.HTTPBadRequest(reason=f"Server path does not exist: {root}")
    return root


def _local_root() -> str:
    root = (config.load().get("LocalPath") or "").strip()
    if not root:
        raise web.HTTPBadRequest(reason="Local path is not set in Settings > MHNodes")
    return root


def _days_left(entry: dict) -> int | None:
    if entry.get("kept"):
        return None
    try:
        days = max(1, int(config.load().get("PurgeDays", 7)))
    except (TypeError, ValueError):
        days = 7
    stamp = registry.parse(entry.get("last_used")) or registry.parse(entry.get("pulled"))
    if stamp is None:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    remaining = (stamp + timedelta(days=days)) - datetime.now(timezone.utc)
    return max(0, int(remaining.total_seconds() // 86400))


def _state_for(folder_type: str, relative: str) -> dict:
    """Whether this model is absent, managed by us, or permanent."""
    key = registry.key_for(folder_type, relative)
    entry = registry.instance().get(key)
    local = folders.find_local(folder_type, relative.replace("/", os.sep))

    if local is None:
        return {"state": "absent", "key": key}
    if entry is None:
        return {"state": "permanent", "key": key, "path": local}
    if entry.get("kept"):
        return {"state": "kept", "key": key, "path": local}
    return {
        "state": "managed",
        "key": key,
        "path": local,
        "days_left": _days_left(entry),
        "last_used": entry.get("last_used"),
    }


def register(routes) -> None:
    @routes.get(f"{PREFIX}/config")
    async def get_config(request):
        settings = config.load()
        return web.json_response({
            "server_path": settings.get("ServerPath", ""),
            "local_path": settings.get("LocalPath", ""),
            "purge_days": settings.get("PurgeDays", 7),
            "enabled": settings.get("Enabled", True),
            "server_ok": bool(settings.get("ServerPath")) and os.path.isdir(settings.get("ServerPath") or ""),
            "local_ok": bool(settings.get("LocalPath")) and os.path.isdir(settings.get("LocalPath") or ""),
        })

    @routes.get(f"{PREFIX}/browse")
    async def browse(request):
        """One directory level of the server tree, with the local state of each file."""
        root = _server_root()
        relative = request.query.get("path", "")

        try:
            target = transfer.safe_join(root, relative) if relative else root
        except transfer.TransferError as exc:
            raise web.HTTPBadRequest(reason=str(exc))

        if not os.path.isdir(target):
            raise web.HTTPNotFound(reason="Not a directory")

        # The first path segment is the model type, mirroring the models/ layout.
        parts = [p for p in relative.replace("\\", "/").split("/") if p]
        folder_type = parts[0] if parts else None

        directories, files = [], []
        try:
            for name in sorted(os.listdir(target), key=str.lower):
                full = os.path.join(target, name)
                child_rel = "/".join(parts + [name])
                if os.path.isdir(full):
                    directories.append({"name": name, "path": child_rel})
                elif folders.looks_like_model(name) and folder_type:
                    inner = "/".join(parts[1:] + [name])
                    info = _state_for(folder_type, inner)
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        size = 0
                    files.append({
                        "name": name, "path": child_rel, "size": size,
                        "folder_type": folder_type, "relative": inner, **info,
                    })
        except OSError as exc:
            raise web.HTTPInternalServerError(reason=str(exc))

        return web.json_response({
            "path": relative, "folder_type": folder_type,
            "directories": directories, "files": files,
        })

    @routes.post(f"{PREFIX}/pull")
    async def pull(request):
        """Queue one or more models for copying. Returns immediately; progress is pushed."""
        body = await request.json()
        items = body.get("items") or []
        if not isinstance(items, list) or not items:
            raise web.HTTPBadRequest(reason="No models selected")

        server_root, local_root = _server_root(), _local_root()
        queued = []

        for item in items:
            relative = (item or {}).get("path", "")
            try:
                source = transfer.safe_join(server_root, relative)
                destination = transfer.safe_join(local_root, relative)
            except transfer.TransferError as exc:
                raise web.HTTPBadRequest(reason=str(exc))

            if not os.path.isfile(source):
                raise web.HTTPBadRequest(reason=f"Not a file on the server: {relative}")

            parts = [p for p in relative.replace("\\", "/").split("/") if p]
            if len(parts) < 2:
                raise web.HTTPBadRequest(reason=f"Expected <model type>/<file>: {relative}")
            key = registry.key_for(parts[0], "/".join(parts[1:]))

            if key in _active:
                continue
            cancel = threading.Event()
            _active[key] = cancel
            _pool.submit(_run_pull, key, relative, source, destination, cancel)
            queued.append(key)

        return web.json_response({"queued": queued})

    @routes.post(f"{PREFIX}/keep")
    async def keep(request):
        body = await request.json()
        key, kept = body.get("key"), bool(body.get("kept", True))
        if not key:
            raise web.HTTPBadRequest(reason="Missing key")
        if not registry.instance().set_kept(key, kept):
            raise web.HTTPNotFound(reason="Not a model this tool pulled")
        registry.instance().flush()
        return web.json_response({"key": key, "kept": kept})

    @routes.get(f"{PREFIX}/registry")
    async def get_registry(request):
        entries = []
        for key, entry in sorted(registry.instance().all().items()):
            entries.append({
                "key": key, "kept": bool(entry.get("kept")),
                "pulled": entry.get("pulled"), "last_used": entry.get("last_used"),
                "size": entry.get("size"), "path": entry.get("path"),
                "days_left": _days_left(entry),
                "present": bool(entry.get("path") and os.path.exists(entry["path"])),
            })
        return web.json_response({"entries": entries})

    @routes.post(f"{PREFIX}/purge")
    async def run_purge(request):
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        return web.json_response(purge.run(dry_run=bool(body.get("dry_run"))))


def _run_pull(key: str, relative: str, source: str, destination: str,
              cancel: threading.Event) -> None:
    try:
        total = os.path.getsize(source)
        _notify("start", {"key": key, "path": relative, "total": total})

        def progress(copied, total_bytes):
            _notify("progress", {"key": key, "copied": copied, "total": total_bytes})

        transfer.copy_with_progress(source, destination, progress, cancel)
        registry.instance().record_pull(key, destination)
        registry.instance().flush()
        folders.invalidate()
        _notify("done", {"key": key, "path": relative, "destination": destination})
        log.info("pulled %s -> %s", key, destination)
    except Exception as exc:
        log.error("pull failed for %s: %s", key, exc)
        _notify("error", {"key": key, "path": relative, "error": str(exc)})
    finally:
        _active.pop(key, None)
