"""Explicit private v1 upgrade/merge. Preview takes snapshots, never model bytes.

The executor is an operator primitive, not a startup hook or HTTP route. All
writers must be quiesced; journals fence old v1 engines before root handover.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path

from .core import CacheError, atomic, canonical, contained, file_lock, fingerprint
from .migration import digest


def preview(snapshots, authority):
    """snapshots maps original state directory to an unmodified v1 JSON object."""
    merged = {'version':2, 'entries':{}, 'holds':{}, 'reservations':{}, 'roots':{}}
    originals = {canonical(state):deepcopy(data) for state,data in snapshots.items()}
    if len(originals) != len(snapshots) or canonical(authority) not in originals:
        raise CacheError('Migration requires distinct original authorities including its destination')
    for state, data in originals.items():
        if data.get('version') != 1 or data.get('holds') != {} or data.get('reservations') != {}:
            raise CacheError('Only idle version1 authorities can be reviewed')
        if not isinstance(data.get('entries'), dict) or not isinstance(data.get('destinations'), dict):
            raise CacheError('Invalid version1 registry')
        source = data['source']
        mapping = data.get('source_categories', {c:c for c in data['destinations']})
        if 'source' in merged and (merged['source'] != source or merged['source_categories'] != mapping):
            # Categories may differ between installs, but overlapping mappings
            # must agree. Historical category metadata remains available.
            if merged['source'] != source or any(c in merged['source_categories'] and merged['source_categories'][c] != v for c,v in mapping.items()):
                raise CacheError('Master library/category mappings conflict')
            merged['source_categories'].update(mapping)
        else:
            merged['source'], merged['source_categories'] = source, deepcopy(mapping)
        for category, root in data['destinations'].items():
            roots = merged['roots'].setdefault(category, [])
            if canonical(root) not in roots:roots.append(canonical(root))
        for key, entry in data['entries'].items():
            category, name = entry['category'], entry['name']
            if canonical(contained(Path(data['destinations'][category]), name)) != key or canonical(entry['path']) != key:
                raise CacheError('Owned entry is not contained in its recorded root')
            if key in merged['entries']:
                prior = merged['entries'][key]
                identity = ('category','name','path','size','mtime_ns','device','inode','sha256')
                if any(prior.get(k) != entry.get(k) for k in identity):
                    raise CacheError('Conflicting physical ownership records')
                prior['last_used'] = max(prior['last_used'], entry['last_used'])
                prior['kept'] = bool(prior['kept'] or entry['kept'])
                prior['downloaded'] = min(prior['downloaded'], entry['downloaded'])
            else:
                merged['entries'][key] = deepcopy(entry)
        for item in data.get('legacy_imports', []):
            if item not in merged.setdefault('legacy_imports', []):merged['legacy_imports'].append(item)
    proposal = {'authority':canonical(authority), 'originals':originals, 'registry':merged}
    proposal['id'] = digest(proposal)
    merged['migration_id'] = proposal['id']
    return proposal


def execute(proposal, *, expected_id, quiesced=False, checkpoint=lambda phase:None):
    """Explicit, restartable handover; tests inject failures at durable phases.

    No implicit rollback. A completed target may have newer use records; resume
    recognizes its migration ID and never overwrites those records.
    """
    clean = preview(proposal['originals'], proposal['authority'])
    if clean != proposal or expected_id != proposal['id']:
        raise CacheError('Migration differs from the reviewed proposal')
    if not quiesced:raise CacheError('All writers must be stopped before migration')
    target = Path(proposal['authority'])
    journal = target / 'root-migrations' / (expected_id + '.json')
    known_roots = sorted({p for paths in proposal['registry']['roots'].values() for p in paths})
    owned_roots = {canonical(Path(entry['path']).parents[len(Path(entry['name']).parts)-1])
                   for entry in proposal['registry']['entries'].values()}
    # Empty/unclaimed roots remain recorded, without creating folders/markers.
    # An owned or previously claimed root must be reachable for handover.
    roots = [p for p in known_roots if p in owned_roots or
             (Path(p)/'.model-cache-authority.json').is_file()]
    fence = {'version':0, 'fenced':True, 'authority':str(target), 'migration_id':expected_id}
    with ExitStack() as locks:
        for state in sorted(proposal['originals']):
            locks.enter_context(file_lock(Path(state) / 'registry.lock'))
        for root in roots:
            if not Path(root).is_dir():raise CacheError('A historical root is offline; retain and review later')
            locks.enter_context(file_lock(Path(root) / '.model-cache-root.lock'))
        current = json.loads((target / 'registry.json').read_text(encoding='utf-8'))
        if journal.is_file() and json.loads(journal.read_text(encoding='utf-8')).get('proposal') != proposal:
            raise CacheError('Migration journal conflicts')
        if current.get('migration_id') == expected_id and current.get('version') == 2:
            if not journal.is_file():raise CacheError('Migration journal is missing')
            atomic(journal, {'phase':'committed', 'proposal':proposal})
            return 'already_committed'
        for state, original in proposal['originals'].items():
            active = json.loads((Path(state) / 'registry.json').read_text(encoding='utf-8'))
            if active != original and active != fence:
                raise CacheError('Registry changed since review')
            for path in (Path(state) / 'preparations').glob('*.json'):
                if json.loads(path.read_text(encoding='utf-8')).get('status') not in ('failed','cancelled','handed_off'):
                    raise CacheError('Unresolved preparation requires reconciliation')
        for key, entry in proposal['registry']['entries'].items():
            if fingerprint(Path(entry['path'])) != {k:entry[k] for k in ('size','mtime_ns','device','inode')}:
                raise CacheError('Owned model identity changed since review')
        expected_marker = {'version':1, 'state':canonical(target)}
        for root in roots:
            marker = Path(root) / '.model-cache-authority.json'
            if marker.is_file():
                value = json.loads(marker.read_text(encoding='utf-8'))
                if value.get('version') != 1 or value.get('state') not in proposal['originals']:
                    raise CacheError('Root authority changed since review')
        journal.parent.mkdir(parents=True, exist_ok=True)
        if journal.exists():
            if json.loads(journal.read_text(encoding='utf-8'))['proposal'] != proposal:
                raise CacheError('Migration journal conflicts')
        else:atomic(journal, {'phase':'prepared','proposal':proposal})
        checkpoint('prepared')
        for state in proposal['originals']:
            atomic(Path(state) / 'registry.json', fence)
        atomic(journal, {'phase':'fenced','proposal':proposal}); checkpoint('fenced')
        for root in roots:atomic(Path(root) / '.model-cache-authority.json', expected_marker)
        atomic(journal, {'phase':'roots','proposal':proposal}); checkpoint('roots')
        atomic(target / 'registry.json', proposal['registry']); checkpoint('published')
        atomic(journal, {'phase':'committed','proposal':proposal})
    return 'committed'
