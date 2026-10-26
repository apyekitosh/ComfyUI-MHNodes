"""Explicit legacy ownership import; preview first, never automatic at startup."""
from datetime import datetime,timezone
from hashlib import sha256
import json

from .core import CacheError,atomic,fingerprint


def digest(legacy):return sha256(json.dumps(legacy,sort_keys=True,allow_nan=False).encode()).hexdigest()


def import_legacy(bridge,legacy,*,expected_digest,quiesced=False):
    if not quiesced:raise CacheError('Stop the legacy writer before importing ownership')
    if digest(legacy)!=expected_digest:raise CacheError('Legacy registry differs from the reviewed snapshot')
    cache=bridge.cache;report={'imported':[],'retained':[],'already_imported':False}
    with cache._transaction() as data:
        if expected_digest in data.get('legacy_imports',[]):
            report['already_imported']=True;return report
    backup=cache.state/'legacy-imports'/f'{expected_digest}.json';backup.parent.mkdir(exist_ok=True)
    if backup.exists():
        if digest(json.loads(backup.read_text(encoding='utf-8')))!=expected_digest:raise CacheError('Legacy snapshot backup differs')
    else:atomic(backup,legacy)
    for row in bridge.migration_preview(legacy):
        if row['disposition']!='review_owned':report['retained'].append(row);continue
        category,name=row['category'],row['name'];key=cache.key(category,name);path=cache.target(category,name)
        cache._claim_roots([cache.destinations[category]])
        with cache._model_lock(key),cache._transaction() as data:
            original=next(value for old_key,value in legacy.items() if old_key.replace('\\','/')==category+'/'+name)
            stat=path.stat()
            if original['size']!=stat.st_size or abs(original['mtime']-stat.st_mtime)>1:
                report['retained'].append(row);continue
            def stamp(value):
                parsed=datetime.fromisoformat(value)
                if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=timezone.utc)
                return parsed.timestamp()
            try:downloaded=stamp(row['pulled']);used=stamp(row['last_used'] or row['pulled']);kept=row['kept']
            except (TypeError,ValueError,OSError,OverflowError):downloaded=used=cache.clock();kept=True
            entry=data['entries'].get(key,{'path':str(path),'category':category,'name':name,'sha256':None,**fingerprint(path),
                                           'downloaded':downloaded,'last_used':used,'kept':kept})
            if entry['size']!=stat.st_size or entry['mtime_ns']!=stat.st_mtime_ns:
                report['retained'].append(row);continue
            entry['last_used']=max(entry['last_used'],used)
            entry['kept']=bool(entry['kept'] or kept)
            data['entries'][key]=entry;report['imported'].append(category+'/'+name)
    with cache._transaction() as data:
        data.setdefault('legacy_imports',[]).append(expected_digest)
    return report
