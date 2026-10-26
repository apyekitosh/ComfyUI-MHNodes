"""Compatibility seam for MHNodes' existing pull/keep/registry UI.

Install only during explicit coordinated startup, before its original setup. The
old in-memory registry, copy loop and purger must never run alongside this seam.
"""
from datetime import datetime, timezone
from pathlib import Path

from .core import CacheError, Cancelled, canonical


def split(key):
    category, name = key.replace('\\', '/').split('/', 1)
    return category, name


def iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat()


class RegistryView:
    def __init__(self, cache):self.cache = cache
    @staticmethod
    def row(entry):
        return {'pulled':iso(entry['downloaded']),'last_used':iso(entry['last_used']),
                'kept':entry['kept'],'path':entry['path'],'size':entry['size'],'mtime':entry['mtime_ns']/1e9}
    def all(self):
        return {f"{entry['category']}/{entry['name']}": self.row(entry)
            for entry in self.cache.snapshot()['entries'].values()}
    def get(self, key):
        entry=self.cache.snapshot()['entries'].get(self.cache.key(*split(key)))
        return self.row(entry) if entry else None
    def touch(self, key):self.cache.touch(*split(key))
    def set_kept(self, key, kept):
        if self.get(key) is None:return False
        self.cache.keep(*split(key), kept);return True
    def record_pull(self, key, path):
        entry = self.get(key)
        if not entry or canonical(path) != canonical(entry['path']):
            raise CacheError('Pull did not complete through the shared cache engine')
    def forget(self, key):self.cache.forget_missing(*split(key))
    def flush(self):pass  # Every mutation is already durable under a process lock.
    def start_autoflush(self):pass


def install_legacy(registry, transfer, purge, bridge, *, integration_ready, config=None, invalidate=lambda:None):
    """Injected MHNodes modules; no installed files or modules imported here."""
    if getattr(registry, '_registry', None) is not None:
        raise CacheError('Restart required: legacy registry already initialized')
    view = RegistryView(bridge.cache)

    def copy(source, destination, on_progress=None, cancel=None):
        try:
            source = Path(source).resolve()
            choices=[]
            for candidate,root in bridge.cache.destinations.items():
                target=Path(destination).resolve()
                if target.is_relative_to(root):
                    name=target.relative_to(root).as_posix()
                    if canonical(source)==canonical(bridge.cache.master(candidate,name)):
                        choices.append((candidate,name))
            if not choices:
                raise CacheError('Comfy destination differs from the shared cache configuration')
            category,name=choices[0]
            path = bridge.cache.ensure(category, name, progress=on_progress,
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
