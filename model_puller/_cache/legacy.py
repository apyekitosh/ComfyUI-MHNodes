"""Compatibility seam for MHNodes' existing pull/keep/registry UI.

Install only during explicit coordinated startup, before its original setup. The
old in-memory registry, copy loop and purger must never run alongside this seam.
"""
from datetime import datetime, timezone
from pathlib import Path
from hashlib import sha256

from .core import CacheError, Cancelled, canonical


def split(key):
    category, name = key.replace('\\', '/').split('/', 1)
    return category, name


def iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat()


class RegistryView:
    def __init__(self, cache, resolve=None):self.cache, self.resolve = cache, resolve
    @staticmethod
    def physical_key(key):return 'physical:' + sha256(key.encode()).hexdigest()
    def entry(self, key):
        entries = self.cache.snapshot()['entries']
        if key.startswith('physical:'):
            return next((e for p,e in entries.items() if self.physical_key(p) == key), None)
        category, name = split(key)
        path = self.resolve(category,name) if self.resolve else self.cache.target(category,name)
        return entries.get(canonical(path)) if path else None
    def location(self, key):
        entry = self.entry(key)
        if entry is None:raise CacheError('Managed physical file is not registered')
        return self.cache.at(entry['category'],entry['name'],entry['path']), entry
    @staticmethod
    def row(entry):
        return {'pulled':iso(entry['downloaded']),'last_used':iso(entry['last_used']),
                'kept':entry['kept'],'path':entry['path'],'size':entry['size'],'mtime':entry['mtime_ns']/1e9}
    def all(self):
        entries = self.cache.snapshot()['entries']
        groups = {}
        for physical,entry in entries.items():
            logical = f"{entry['category']}/{entry['name']}"
            groups.setdefault(logical, []).append((physical,entry))
        return {self.physical_key(physical): self.row(entry)
                for logical,rows in groups.items() for physical,entry in rows}
    def get(self, key):
        entry=self.entry(key)
        return self.row(entry) if entry else None
    def touch(self, key):
        if entry := self.entry(key):self.cache.touch_path(entry['path'])
    def set_kept(self, key, kept):
        entry = self.entry(key)
        if entry is None:return False
        # Keeping an offline/unregistered historical file is metadata-only.
        with self.cache._transaction() as data:
            current = data['entries'].get(canonical(entry['path']))
            if current is None:return False
            current['kept'] = bool(kept)
        return True
    def record_pull(self, key, path):
        entry = self.cache.owned(path)
        if not entry or (entry['category'],entry['name']) != split(key):
            raise CacheError('Pull did not complete through the shared cache engine')
    def forget(self, key):
        # Delete's follow-up forget may occur after the engine already removed it.
        if self.entry(key):
            cache, entry = self.location(key)
            cache.forget_missing(entry['category'],entry['name'])
    def flush(self):pass  # Every mutation is already durable under a process lock.
    def start_autoflush(self):pass


def install_legacy(registry, transfer, purge, bridge, *, integration_ready, config=None, invalidate=lambda:None):
    """Injected MHNodes modules; no installed files or modules imported here."""
    if getattr(registry, '_registry', None) is not None:
        raise CacheError('Restart required: legacy registry already initialized')
    view = RegistryView(bridge.cache, bridge.installed)

    def copy(source, destination, on_progress=None, cancel=None):
        try:
            source = Path(source).resolve()
            choices=[]
            for candidate,roots in bridge.cache.registered_roots.items():
                for root in roots:
                    target=Path(destination).resolve()
                    if target.is_relative_to(root):
                        name=target.relative_to(root).as_posix()
                        if canonical(source)==canonical(bridge.cache.master(candidate,name)):
                            choices.append((candidate,name))
            if not choices:
                raise CacheError('Comfy destination differs from the shared cache configuration')
            category,name=choices[0]
            path = bridge.cache.at(category,name,destination).ensure(category, name, progress=on_progress,
                                      cancelled=cancel.is_set if cancel else None)
            return path.stat().st_size
        except Cancelled as exc:
            raise transfer.TransferError('cancelled') from exc
        except (ValueError, CacheError) as exc:
            raise transfer.TransferError(str(exc)) from exc

    if config is not None:
        original_config=config.load
        config.load=lambda:{**original_config(),'PurgeDays':7,'TrackUsage':True}
    registry.instance = lambda:view
    transfer.copy_with_progress = copy
    def collect(dry_run=False):
        result=bridge.cache.collect(dry_run=dry_run,integration_ready=integration_ready())
        if result['deleted']:invalidate()
        return result
    purge.run = collect
    purge.sweep_partials = lambda dry_run=False:[]  # Exact durable reservations replace age guessing.
    return view
