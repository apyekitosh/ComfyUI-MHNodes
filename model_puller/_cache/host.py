"""Durable preparation on the execution host, before GPU queue admission.

Requests are immutable and keyed by caller-owned attempt IDs. Restart never
replays a request with uncertain status. Persistent file holds survive threads,
HTTP clients and host processes; only known cancellation or queue handoff frees
them. There is no model runtime or web framework dependency here.
"""
from hashlib import sha256
import json
from pathlib import Path
import threading
import time

from .core import CacheError, Busy, Cancelled, atomic, file_lock, canonical, fingerprint


class TransferHost:
    def __init__(self, bridge, *, terminal=lambda prompt_id:False, invalidate=lambda:None, collect=None):
        self.bridge, self.cache = bridge, bridge.cache
        self.terminal, self.invalidate = terminal, invalidate
        self.collect=collect
        self.directory = self.cache.state / 'preparations'

    def _paths(self, owner):
        if not isinstance(owner, str) or not owner or len(owner) > 200:
            raise CacheError('Invalid preparation owner')
        key = sha256(owner.encode()).hexdigest()
        return self.directory / (key + '.json'), self.directory / (key + '.lock'), self.directory / (key + '.process')

    def _read(self, owner):
        path, _, _ = self._paths(owner)
        row = json.loads(path.read_text(encoding='utf-8'))
        if row['owner'] != owner:
            raise CacheError('Preparation identity mismatch')
        return row

    def _update(self, owner, **changes):
        path, lock, _ = self._paths(owner)
        with file_lock(lock):
            row = self._read(owner); row.update(changes); atomic(path, row)
            return row

    def status(self, owner):
        _, lock, processing = self._paths(owner)
        with file_lock(lock):
            row = self._read(owner)
            if row['status'] in ('preparing', 'cancelling'):
                try:
                    with file_lock(processing, 0):
                        row['status'] = 'interrupted'
                        row['error'] = 'Preparation interrupted; reconcile this attempt before retrying'
                        atomic(self._paths(owner)[0], row)
                except Busy:
                    pass
            return row

    def start(self, owner, prompt_id, prompt):
        request_digest = sha256(json.dumps({'prompt_id':str(prompt_id), 'prompt':prompt}, sort_keys=True,
                                        allow_nan=False).encode()).hexdigest()
        path, lock, processing = self._paths(owner)
        with file_lock(lock):
            if path.exists():
                row = self._read(owner)
                if row['fingerprint'] != request_digest:
                    raise CacheError('Preparation owner already has different frozen parameters')
                if row.get('version') != 2 and row['status'] not in ('cancelled','failed','handed_off'):
                    raise CacheError('Old preparation requires explicit reconciliation')
                return row  # No replay, even after cancellation/failure/restart.
            bridge = self.bridge.frozen()
            models, unknown = bridge.dependencies(prompt)
            if unknown:
                raise CacheError('Unmapped model dependencies: ' + ', '.join(unknown))
            physical = bridge.physical(models)
            guard = file_lock(processing, 0); guard.__enter__()
            try:
                self.cache.hold('prepare:' + owner, paths=[p for _,_,p in physical])
                row = {'version':2, 'owner':owner, 'prompt_id':str(prompt_id), 'fingerprint':request_digest,
                       'models':[{'category':c, 'name':n, 'path':canonical(p),
                                  'fingerprint':fingerprint(p) if p.is_file() else None}
                                 for c,n,p in physical], 'status':'preparing',
                       'copied':0, 'total':0, 'cancel_requested':False, 'error':None}
                atomic(path, row)
                thread = threading.Thread(target=self._run, args=(owner,physical,guard,bridge), daemon=True,
                                          name='model-prepare-' + str(prompt_id))
                thread.start()
            except BaseException:
                guard.__exit__(None,None,None)
                raise
        return row

    def _run(self, owner, models, guard, bridge):
        cache = bridge.cache
        try:
            total = sum(cache.master(c,n).stat().st_size for c,n,p in models if not p.is_file())
            self._update(owner,total=total)
            completed = 0
            for category,name,path in models:
                key = canonical(path)
                missing = not path.is_file()
                accepted = next(row for row in self._read(owner)['models']
                                if row['category']==category and row['name']==name)
                if accepted['fingerprint'] is not None and (missing or fingerprint(path) != accepted['fingerprint']):
                    raise CacheError('Installed model changed after preparation was accepted')

                def cancel_copy():
                    if not self._read(owner)['cancel_requested']:
                        return False
                    # Another app/Comfy consumer still needs this physical file.
                    holds = self.cache.snapshot()['holds']
                    for other,hold in holds.items():
                        if other == 'prepare:' + owner or key not in hold['keys']:
                            continue
                        if other.startswith('prepare:'):
                            try:
                                if self._read(other.removeprefix('prepare:'))['cancel_requested']:
                                    continue
                            except (OSError, ValueError, KeyError):
                                pass  # Uncertain consumers still protect the transfer.
                        return False
                    return True

                if missing:
                    last_report = [0.0]
                    def progress(done,size):
                        now=time.monotonic()
                        if done==size or now-last_report[0]>=.2:
                            self._update(owner,copied=completed+done,current={'category':category,'name':name})
                            last_report[0]=now
                    cache.at(category,name,path).ensure(category,name,
                                      cancelled=cancel_copy,
                                      progress=progress)
                if missing:
                    completed += path.stat().st_size
                cache.touch_path(path)
                if self._read(owner)['cancel_requested']:
                    raise Cancelled('Preparation cancelled')
            self.invalidate()
            receipts = []
            rows = []
            for c,n,path in models:
                actual = bridge.installed(c,n)
                if actual is None or canonical(actual) != canonical(path):
                    raise CacheError('Prepared model is not the file Comfy resolves')
                entry = cache.owned(path) or {}
                receipts.append({'category':c,'name':n,'sha256':entry.get('sha256')})
                rows.append({'category':c,'name':n,'path':canonical(path),'fingerprint':fingerprint(path)})
            self._update(owner,status='ready',copied=completed,receipts=receipts,models=rows)
        except Cancelled:
            self._update(owner,status='cancelled')
            self.cache.release('prepare:' + owner)
        except Exception as exc:
            # No inference was submitted; completed cache files remain reusable.
            self._update(owner,status='failed',error=str(exc))
            self.cache.release('prepare:' + owner)
        finally:
            guard.__exit__(None,None,None)

    def cancel(self, owner):
        path, lock, _ = self._paths(owner)
        with file_lock(lock):
            row = self._read(owner)
            if row['status'] in ('ready', 'interrupted'):
                row.update(cancel_requested=True,status='cancelled')
                atomic(path,row); self.cache.release('prepare:' + owner)
            elif row['status'] in ('preparing','cancelling'):
                row.update(cancel_requested=True,status='cancelling'); atomic(path,row)
            return row

    def handoff(self, owner):
        row = self.status(owner)
        if row['status'] == 'handed_off':
            return row
        prompt_id = row['prompt_id']
        queued = self.bridge.prefix + prompt_id in self.cache.snapshot()['holds']
        if row['status'] != 'ready' or not (queued or self.terminal(prompt_id)):
            raise CacheError('No positive Comfy queue/completion receipt for model handoff')
        # Persist proof before releasing; a crash can only over-retain the hold.
        row = self._update(owner,status='handed_off')
        self.cache.release('prepare:' + owner)
        return row

    def reconcile(self):
        """Only positive terminal receipts can release abandoned ready/handed-off holds."""
        if not self.directory.exists():return
        for path in self.directory.glob('*.json'):
            row = json.loads(path.read_text(encoding='utf-8'))
            if row['status'] == 'handed_off':
                self.cache.release('prepare:' + row['owner'])
            elif row['status'] == 'ready' and self.terminal(row['prompt_id']):
                self.handoff(row['owner'])

    def startup(self):
        self.reconcile()
        result=self.collect() if self.collect else {'blocked':True}
        if result.get('deleted'):self.invalidate()
        return result
