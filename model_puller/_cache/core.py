"""No model runtime, app imports, background daemon or implicit live configuration.

All participants sharing destination roots must share this state directory. OS locks
are released on process death; persistent holds deliberately are not. Unknown work
requires explicit reconciliation, never a guessed expiry.
"""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import time
from uuid import uuid4

MODEL_SUFFIXES = {'.safetensors', '.ckpt', '.pt', '.pth', '.gguf', '.sft', '.bin', '.onnx', '.engine', '.pkl'}


class CacheError(RuntimeError):
    pass


class Busy(CacheError):
    pass


class Cancelled(CacheError):
    pass


def canonical(path):
    return os.path.normcase(str(Path(path).resolve()))


def contained(root, relative):
    name = str(relative).replace('\\', '/')
    parts = PurePosixPath(name)
    if not name or parts.is_absolute() or any(p in ('..', '.') or ':' in p for p in parts.parts):
        raise CacheError('Model path must be relative to its configured category')
    root = Path(root).resolve()
    target = (root / name).resolve()
    if target == root or not target.is_relative_to(root):
        raise CacheError('Model path escapes its configured category')
    return target


@contextmanager
def file_lock(path, timeout=30, cancelled=None):
    """Lock the same byte/inode across processes; never delete a lock file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b'0'); handle.flush()
        start = time.monotonic()
        while True:
            if cancelled and cancelled():raise Cancelled('Model transfer cancelled')
            try:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError):
                if time.monotonic() - start >= timeout:
                    raise Busy('Model cache is in use')
                time.sleep(.02)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def atomic(path, value):
    temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        with temp.open('x', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def fingerprint(path):
    stat = path.stat()
    return {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'device': stat.st_dev, 'inode': stat.st_ino}


class Cache:
    def __init__(self, state, source, destinations, *, clock=time.time,
                 before_transfer=None, reserve_bytes=512 * 1024**2, source_categories=None,
                 registered_roots=None):
        self.state = Path(state).resolve()
        self.source = Path(source).resolve()
        self.destinations = {str(k): Path(v).resolve() for k, v in destinations.items()}
        self.registered_roots = {k: tuple(Path(p).resolve() for p in paths)
                                 for k, paths in (registered_roots or
                                     {k: [v] for k, v in destinations.items()}).items()}
        if any(root not in self.registered_roots.get(k, ()) for k, root in self.destinations.items()):
            raise CacheError('Download target is not a registered search root')
        self.source_categories={k:(source_categories or {}).get(k,k) for k in self.destinations}
        if set(source_categories or {})-set(self.destinations):raise CacheError('Source mapping has an unconfigured category')
        for relative in self.source_categories.values():contained(self.source,relative)
        self.clock, self.before_transfer, self.reserve_bytes = clock, before_transfer, reserve_bytes
        if not self.destinations:
            raise CacheError('At least one model destination is required')
        for root in self.destinations.values():
            if root == self.source or root.is_relative_to(self.source) or self.source.is_relative_to(root):
                raise CacheError('Master library and caches must not overlap')
        if self.state == self.source or self.state.is_relative_to(self.source):
            raise CacheError('Cache state must not be stored in the master library')
        if any(self.state == root or self.state.is_relative_to(root) or root.is_relative_to(self.state)
               for root in self.destinations.values()):
            raise CacheError('Cache metadata and model destinations must be separate')

    def _claim_roots(self, roots=None):
        """Refuse two registries managing the same physical destination root."""
        for root in sorted(set(roots if roots is not None else self.destinations.values())):
            root.mkdir(parents=True, exist_ok=True)
            with file_lock(root / '.model-cache-root.lock'):
                marker = root / '.model-cache-authority.json'
                expected = {'version': 1, 'state': canonical(self.state)}
                if marker.exists():
                    try:
                        if json.loads(marker.read_text(encoding='utf-8')) != expected:
                            raise CacheError('Destination belongs to another cache authority')
                    except (ValueError, TypeError) as exc:
                        raise CacheError('Invalid cache authority marker') from exc
                else:
                    atomic(marker, expected)

    def target(self, category, relative):
        if category not in self.destinations:
            raise CacheError('Unconfigured model category')
        return contained(self.destinations[category], relative)

    def master(self, category, relative):
        # Category itself is validated, not accepted as an arbitrary relative root.
        if category not in self.destinations or '/' in category or '\\' in category or ':' in category:
            raise CacheError('Unconfigured model category')
        return contained(contained(self.source, self.source_categories[category]), relative)

    def key(self, category, relative):
        return canonical(self.target(category, relative))

    def with_destinations(self, destinations, *, registered_roots=None):
        """Independent location snapshot; never mutate an in-flight cache view."""
        return Cache(self.state, self.source, destinations, clock=self.clock,
                     before_transfer=self.before_transfer, reserve_bytes=self.reserve_bytes,
                     source_categories=self.source_categories,
                     registered_roots=registered_roots or self.registered_roots)

    def at(self, category, name, path):
        """Constrain a logical operation to one registered physical filename."""
        matches = [root for root in self.registered_roots.get(category, ())
                   if canonical(contained(root, name)) == canonical(path)]
        if len(matches) != 1:
            raise CacheError('Model location is not a unique registered root')
        return self.with_destinations({**self.destinations, category: matches[0]})

    def _model_lock(self, key, timeout=30, cancelled=None):
        return file_lock(self.state / 'locks' / (sha256(key.encode()).hexdigest() + '.lock'), timeout, cancelled)

    @contextmanager
    def _transaction(self):
        self.state.mkdir(parents=True, exist_ok=True)
        with file_lock(self.state / 'registry.lock'):
            path = self.state / 'registry.json'
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding='utf-8'))
                    if data['version'] != 2 or not all(isinstance(data[k], dict) for k in ('entries', 'holds', 'reservations', 'roots')):
                        raise ValueError('Unsupported registry')
                except (ValueError, KeyError, TypeError) as exc:
                    raise CacheError('Cache registry is invalid; no files changed') from exc
                if data.get('fenced') or data.get('source') != canonical(self.source):
                    raise CacheError('Cache roots differ from the recorded authority')
                recorded_mapping = data.get('source_categories', {})
                if any(recorded_mapping.get(k) != v for k,v in self.source_categories.items()):
                    raise CacheError('Cache source category mapping changed')
            else:
                # Losing a registry must never cause existing files to be adopted.
                data = {'version': 2, 'entries': {}, 'holds': {}, 'reservations': {}, 'roots': {},
                        'source': canonical(self.source), 'source_categories':self.source_categories,
                        }
            original = json.dumps(data, sort_keys=True)
            for category, paths in self.registered_roots.items():
                known = data['roots'].setdefault(category, [])
                for root in paths:
                    if canonical(root) not in known:
                        known.append(canonical(root))
            yield data
            if json.dumps(data, sort_keys=True) != original or not path.exists():
                atomic(path, data)

    def snapshot(self):
        with self._transaction() as data:
            return json.loads(json.dumps(data))

    def hold(self, owner, models=(), *, unknown=False, paths=None):
        """Durable hold before queue admission; owners reconcile, not wall-clock TTLs."""
        if not isinstance(owner, str) or not owner:
            raise CacheError('A durable attempt owner is required')
        keys = sorted({canonical(p) for p in paths} if paths is not None else
                      {self.key(category, relative) for category, relative in models})
        with self._transaction() as data:
            current = data['holds'].get(owner)
            if current and (current['keys'] != keys or current['unknown'] != bool(unknown)):
                raise CacheError('Attempt already holds different models')
            data['holds'][owner] = {'keys': keys, 'unknown': bool(unknown)}

    def release(self, owner):
        with self._transaction() as data:
            data['holds'].pop(owner, None)

    def touch(self, category, relative):
        self.touch_path(self.target(category, relative))

    def owned(self, path, *, data=None):
        entry = (data if data is not None else self.snapshot())['entries'].get(canonical(path))
        if not entry:
            return None
        try:
            if fingerprint(Path(path)) == {k: entry[k] for k in ('size', 'mtime_ns', 'device', 'inode')}:
                return entry
        except OSError:
            pass
        return None

    def touch_path(self, path):
        key = canonical(path)
        with self._transaction() as data:
            if entry := self.owned(path, data=data):
                entry['last_used'] = max(entry.get('last_used', 0), self.clock())

    def keep(self, category, relative, kept=True):
        with self._transaction() as data:
            entry = data['entries'].get(self.key(category, relative))
            if not entry:
                raise CacheError('Only registered managed files have retention settings')
            entry['kept'] = bool(kept)

    def remove_managed(self, category, relative):
        """Existing Comfy manual-remove action, through the same ownership lock.

        No caller can use this to adopt/delete an unrelated installed model.
        """
        path = self.target(category, relative); key = canonical(path)
        self._claim_roots([self.destinations[category]])
        with self._model_lock(key, 0), self._transaction() as data:
            entry = data['entries'].get(key)
            if not entry:
                raise CacheError('File is not owned by this model cache')
            if key in data['reservations'] or any(h['unknown'] or key in h['keys'] for h in data['holds'].values()):
                raise Busy('Model is required by queued, active or unresolved work')
            if path.exists():
                if canonical(path) != key or fingerprint(path) != {k: entry[k] for k in ('size', 'mtime_ns', 'device', 'inode')}:
                    raise CacheError('Managed model was replaced; retained')
                path.unlink()
            del data['entries'][key]

    def forget_missing(self, category, relative):
        key = self.key(category, relative)
        with self._model_lock(key, 0), self._transaction() as data:
            if self.target(category, relative).exists():
                raise CacheError('Cannot forget ownership of an existing model')
            data['entries'].pop(key, None)

    def status(self, category, relative):
        path = self.target(category, relative); key = canonical(path)
        data = self.snapshot()
        if key in data['reservations']:
            return 'downloading'
        if path.is_file():
            return 'ready'
        return 'needs_download' if self.master(category, relative).is_file() else 'unavailable'

    def catalogue(self, categories=None):
        """Metadata only. Never hashes or opens weights while browsing."""
        if not self.source.is_dir():
            raise CacheError('Master library is unavailable')
        records = []
        data = self.snapshot()  # One metadata snapshot, not one registry parse per model.
        for category in categories or self.destinations:
            root = contained(self.source, self.source_categories[category])
            if not root.is_dir():
                continue
            for path in sorted(root.rglob('*')):
                if path.is_file() and path.suffix.lower() in MODEL_SUFFIXES:
                    relative = path.relative_to(root).as_posix()
                    master = self.master(category, relative)
                    target = self.target(category, relative)
                    availability = ('downloading' if canonical(target) in data['reservations']
                                    else 'ready' if target.is_file() else 'needs_download')
                    records.append({'category': category, 'name': relative,
                                    'size': master.stat().st_size,
                                    'availability': availability})
        return records

    def ensure(self, category, relative, *, progress=None, cancelled=None, timeout=600):
        target = self.target(category, relative); key = canonical(target)
        self._claim_roots([self.destinations[category]])
        with self._model_lock(key, timeout, cancelled):
            with self._transaction() as data:
                previous = data['reservations'].get(key)
            if previous:
                # This process owns the OS lock, so an old writer is no longer alive.
                # Recover only its exact partial, never sweep arbitrary .part files.
                partial = Path(previous['partial'])
                if partial.parent != target.parent or not partial.name.startswith('.' + target.name + '.'):
                    raise CacheError('Invalid transfer recovery record')
                if target.exists() and previous.get('verified'):
                    if fingerprint(target) == previous['published_fingerprint']:
                        with self._transaction() as data:
                            recovered = previous['entry']
                            current = data['entries'].get(key, recovered)
                            recovered['kept'] = current['kept']
                            recovered['last_used'] = max(current['last_used'], recovered['last_used'])
                            data['entries'][key] = recovered
                            data['reservations'].pop(key, None)
                        partial.unlink(missing_ok=True)
                        return target
                    raise CacheError('Published transfer changed; retain for reconciliation')
                partial.unlink(missing_ok=True)
                with self._transaction() as data:
                    data['reservations'].pop(key, None)
            if target.is_file():
                return target  # Manual files are usable, never adopted or overwritten.
            source = self.master(category, relative)
            if not source.is_file():
                raise CacheError('Model is absent from the master library')
            # One copy per authority: avoid overcommitting free space across files.
            with file_lock(self.state / 'transfer.lock', timeout, cancelled):
                if self.before_transfer is None:
                    raise CacheError('Host resource permission callback is required for transfers')
                self.before_transfer()
                source_stamp = fingerprint(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                if shutil.disk_usage(target.parent).free < source_stamp['size'] + self.reserve_bytes:
                    raise CacheError('Insufficient model-cache disk space')
                partial = target.with_name('.' + target.name + '.' + uuid4().hex + '.part')
                with self._transaction() as data:
                    data['reservations'][key] = {'partial': str(partial), 'verified': False}
                published = False
                try:
                    digest = sha256(); copied = 0
                    with source.open('rb') as src, partial.open('xb') as dst:
                        while block := src.read(4 * 1024**2):
                            if cancelled and cancelled():
                                raise Cancelled('Model transfer cancelled')
                            dst.write(block); digest.update(block); copied += len(block)
                            if progress:
                                progress(copied, source_stamp['size'])
                        dst.flush(); os.fsync(dst.fileno())
                    if cancelled and cancelled():
                        raise Cancelled('Model transfer cancelled')
                    if copied != source_stamp['size'] or fingerprint(source) != source_stamp:
                        raise CacheError('Master model changed during transfer')
                    old_entry = self.snapshot()['entries'].get(key, {})
                    entry = {'path': str(target), 'category': category, 'name': relative,
                             'downloaded': self.clock(), 'last_used': max(self.clock(), old_entry.get('last_used', 0)),
                             'kept': bool(old_entry.get('kept', False)),
                             'sha256': digest.hexdigest(), **fingerprint(partial)}
                    # Record a recoverable publication intent first. Rename is no-clobber
                    # on Windows; hard-link publication gives the same guarantee on POSIX.
                    with self._transaction() as data:
                        data['reservations'][key].update(verified=True, entry=entry,
                                                        published_fingerprint=fingerprint(partial))
                    with self._transaction() as data:
                        current = data['entries'].get(key, entry)
                        entry['kept'] = current['kept']
                        entry['last_used'] = max(current['last_used'], entry['last_used'])
                        if os.name == 'nt':
                            partial.rename(target)
                        else:
                            os.link(partial, target); partial.unlink()
                        published = True
                        data['entries'][key] = entry
                        data['reservations'].pop(key, None)
                    return target
                finally:
                    if not published:
                        partial.unlink(missing_ok=True)
                        with self._transaction() as data:
                            data['reservations'].pop(key, None)

    def collect(self, *, dry_run=True, integration_ready=False):
        """Explicit startup call. Unknown/unfinished consumers suppress collection."""
        result = {'deleted': [], 'eligible': [], 'skipped': [], 'blocked': False}
        if not integration_ready:
            result['blocked'] = True
            return result
        snapshot=self.snapshot()
        for key in snapshot['entries']:
            try:
                recorded = snapshot['entries'][key]
                path = Path(recorded['path'])
                roots = [Path(p) for p in snapshot['roots'].get(recorded['category'], [])
                         if canonical(contained(Path(p), recorded['name'])) == key]
                # Never recreate an offline root or claim an unverified old drive.
                if len(roots) != 1 or roots[0] not in self.registered_roots.get(recorded['category'], ()):
                    result['skipped'].append(key); continue
                marker = roots[0] / '.model-cache-authority.json'
                if not roots[0].is_dir() or not marker.is_file() or json.loads(marker.read_text(encoding='utf-8')) != {'version':1,'state':canonical(self.state)}:
                    result['skipped'].append(key); continue
                with self._model_lock(key, 0), self._transaction() as data:
                    if any(hold['unknown'] for hold in data['holds'].values()):
                        result['blocked'] = True
                        return result
                    entry = data['entries'].get(key)
                    if not entry or entry.get('kept') or key in data['reservations']:
                        continue
                    if any(key in hold['keys'] for hold in data['holds'].values()):
                        result['skipped'].append(key); continue
                    if self.clock() < max(entry['downloaded'], entry['last_used']) + 7 * 86400:
                        continue
                    path = contained(roots[0], entry['name'])
                    if canonical(path) != key or str(path) != entry['path']:
                        raise CacheError('Recorded model destination changed')
                    if not path.exists():
                        if not dry_run:
                            del data['entries'][key]
                        continue
                    if fingerprint(path) != {k: entry[k] for k in ('size', 'mtime_ns', 'device', 'inode')}:
                        result['skipped'].append(key); continue
                    result['eligible'].append(key)
                    if not dry_run:
                        path.unlink()
                        del data['entries'][key]
                        result['deleted'].append(key)
            except (Busy, OSError, ValueError):
                result['skipped'].append(key)
        return result
