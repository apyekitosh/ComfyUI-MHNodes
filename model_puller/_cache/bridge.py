"""Thin Comfy integration logic, with queue and loader APIs injected by its host.

No Comfy imports: the same implementation is tested and distributed with the cache
core. The installed MHNodes adapter supplies its existing widget/category map and
real resolved paths instead of making the app infer Comfy filesystem locations.
"""
from pathlib import Path
from contextvars import ContextVar

from .core import CacheError, canonical, MODEL_SUFFIXES


class ComfyBridge:
    def __init__(self, cache, bindings, *, identity, resolve=None, opaque_nodes=(), locations=None):
        self.cache = cache
        self.bindings = dict(bindings)
        self.prefix = f'comfy:{identity}:'
        self.resolve = resolve
        self.opaque_nodes=set(opaque_nodes)
        self.locations = locations
        self.execution_owner = ContextVar('model_cache_execution_owner', default=None)
        if not identity:
            raise CacheError('Comfy installation identity is required')

    def frozen(self):
        if self.locations is None:
            return self
        cache = self.locations()
        return ComfyBridge(cache, self.bindings, identity=self.prefix[6:-1],
                           resolve=self.resolve, opaque_nodes=self.opaque_nodes)

    def physical(self, models):
        return [(c, n, self.installed(c, n) or self.cache.target(c, n)) for c, n in models]

    def installed(self, category, name):
        path = self.resolve(category,name) if self.resolve else self.cache.target(category,name)
        return Path(path) if path and Path(path).is_file() else None

    def dependencies(self, prompt):
        models, unknown = set(), []
        for node_id, node in prompt.items():
            if not isinstance(node, dict):
                continue
            if node.get('class_type') in self.opaque_nodes:
                unknown.append(str(node_id)+':'+node['class_type'])
            for field, value in node.get('inputs', {}).items():
                category = self.bindings.get((node.get('class_type'), field))
                if category and isinstance(value, str):
                    # Includes directory-based models if their loader declares them.
                    if category not in self.cache.destinations:
                        unknown.append(f'{node_id}.{field}')
                    else:
                        self.cache.target(category, value)  # Validate before any hold/copy.
                        models.add((category, value.replace('\\', '/')))
                elif isinstance(value, str) and Path(value).suffix.lower() in MODEL_SUFFIXES:
                    unknown.append(f'{node_id}.{field}')
        return sorted(models), unknown

    def submitted(self, prompt_id, prompt):
        if self.locations is not None:
            return self.frozen().submitted(prompt_id, prompt)
        models, unknown = self.dependencies(prompt)
        physical = self.physical(models)
        # A ready preparation binds this prompt to actual physical files. Search
        # order or file replacement after preparation must fail before enqueue.
        directory = self.cache.state / 'preparations'
        for path in directory.glob('*.json'):
            import json
            row = json.loads(path.read_text(encoding='utf-8'))
            if row.get('prompt_id') == str(prompt_id) and row.get('status') == 'ready':
                if row.get('version') != 2:
                    raise CacheError('Old preparation requires explicit reconciliation')
                expected = {(r['category'], r['name']): r for r in row['models']}
                if set(expected) != {(c,n) for c,n,_ in physical}:
                    raise CacheError('Prepared model dependencies changed')
                from .core import fingerprint
                for c,n,p in physical:
                    prior = expected[c,n]
                    if canonical(p) != prior['path'] or not p.is_file() or fingerprint(p) != prior['fingerprint']:
                        raise CacheError('Prepared model location or identity changed')
        self.cache.hold(self.prefix + str(prompt_id), unknown=bool(unknown), paths=[p for _,_,p in physical])
        for _,_,path in physical:
            self.cache.touch_path(path)
        return {'models': models, 'unknown': unknown}

    def finished(self, prompt_id):
        self.cache.release(self.prefix + str(prompt_id))

    def reconcile(self, queued_and_running, terminal_ids):
        """Never release an absent job without a positive terminal receipt."""
        for prompt_id, prompt in queued_and_running.items():
            self.submitted(prompt_id, prompt)
        active = {str(value) for value in queued_and_running}
        for prompt_id in terminal_ids:
            if str(prompt_id) not in active:
                self.finished(prompt_id)

    def resolved(self, category, relative, resolved_path):
        # Comfy can choose another search root. Never touch/delete a different file
        # merely because the dropdown's relative filename happens to match.
        if category in self.cache.destinations:
            self.cache.touch_path(resolved_path)

    def stage(self, prompt, *, progress=None, cancelled=None):
        models, unknown = self.dependencies(prompt)
        if unknown:
            raise CacheError('Model dependencies are not mapped: ' + ', '.join(unknown))
        for category, name in models:
            if self.installed(category,name):continue
            self.cache.ensure(category, name,
                              progress=(lambda done, total, c=category, n=name:
                                        progress(c, n, done, total)) if progress else None,
                              cancelled=cancelled)
        return models

    def inventory(self):
        if self.locations is not None:
            return self.frozen().inventory()
        models = self.cache.catalogue()
        for row in models:
            if self.installed(row['category'],row['name']):row['availability']='ready'
        return {'version': 1, 'capabilities': ['physical-locations-v2'], 'models': models,
                'bindings': [{'node': node, 'input': field, 'category': category}
                             for (node, field), category in sorted(self.bindings.items())],
                'retention_days': 7}

    def migration_preview(self, legacy):
        """Read-only preview. No ownership is granted by matching a filename."""
        rows = []
        for key, entry in legacy.items():
            try:
                category, name = key.replace('\\', '/').split('/', 1)
                target = self.cache.target(category, name)
                matches = canonical(entry['path']) == canonical(target)
                stat = target.stat()
                matches = matches and entry.get('size') == stat.st_size and isinstance(entry.get('mtime'), (int, float))
                matches = matches and abs(entry['mtime'] - stat.st_mtime) <= 1
                rows.append({'category': category, 'name': name,
                             'disposition': 'review_owned' if matches else 'retain_unverified',
                             'kept': bool(entry.get('kept')), 'last_used': entry.get('last_used'),
                             'pulled': entry.get('pulled')})
            except (ValueError, KeyError, OSError, CacheError, TypeError):
                rows.append({'legacy_key': key, 'disposition': 'retain_unverified'})
        return rows
