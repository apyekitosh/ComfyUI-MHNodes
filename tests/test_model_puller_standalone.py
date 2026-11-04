"""Exercise staged MHNodes with tiny files and no Comfy/GPU/model dependency."""
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType,SimpleNamespace

import pytest

STAGE=Path(__file__).parents[1]/'model_puller'


@pytest.fixture
def puller(tmp_path,monkeypatch):
    name='standalone_puller_fixture'
    spec=importlib.util.spec_from_file_location(name,STAGE/'__init__.py',submodule_search_locations=[str(STAGE)])
    package=importlib.util.module_from_spec(spec);monkeypatch.setitem(sys.modules,name,package);spec.loader.exec_module(package)
    modules={part:importlib.import_module(name+'.'+part) for part in ('config','folders','registry','purge','tracking','coordinated','transfer')}
    settings={'Enabled':True,'TrackUsage':False,'ServerPath':str(tmp_path/'source'),'LocalPath':str(tmp_path/'models'),'PurgeDays':7}
    settings_dir=tmp_path/'settings';settings_dir.mkdir()
    for folder in ('source/vae','models/vae'):(tmp_path/folder).mkdir(parents=True)
    monkeypatch.setattr(modules['config'],'data_dir',lambda:str(settings_dir))
    monkeypatch.setattr(modules['config'],'load',lambda:dict(settings))
    monkeypatch.setattr(modules['folders'],'roots_for',lambda category:[str(tmp_path/'models'/category)])
    monkeypatch.setattr(modules['folders'],'all_roots',lambda:{'vae':[str(tmp_path/'models/vae')]})
    reg=modules['registry'].Registry(str(settings_dir/'model_registry.json'))
    monkeypatch.setattr(modules['registry'],'instance',lambda:reg)
    class HTTPError(Exception):
        def __init__(self,*,reason):super().__init__(reason)
    web=SimpleNamespace(json_response=lambda body:body,HTTPBadRequest=HTTPError,HTTPNotFound=HTTPError,HTTPInternalServerError=HTTPError)
    monkeypatch.setitem(sys.modules,'aiohttp',SimpleNamespace(web=web))
    class Routes:
        def __init__(self):self.handlers={}
        def route(self,method,path):
            def decorate(fn):self.handlers[(method,path)]=fn;return fn
            return decorate
        def get(self,path):return self.route('GET',path)
        def post(self,path):return self.route('POST',path)
    routes=Routes();events=[]
    monkeypatch.setitem(sys.modules,'server',SimpleNamespace(PromptServer=SimpleNamespace(instance=SimpleNamespace(routes=routes,send_sync=lambda *a:events.append(a)))))
    purge_calls=[]
    monkeypatch.setattr(modules['purge'],'run',lambda **kw:purge_calls.append(kw) or kw)
    api=importlib.import_module(name+'.api')
    monkeypatch.setattr(api,'_pool',SimpleNamespace(submit=lambda fn,*args:fn(*args)))
    yield SimpleNamespace(package=package,modules=modules,routes=routes,reg=reg,settings_dir=settings_dir,root=tmp_path,api=api,purge_calls=purge_calls,events=events)
    # Imported child modules also carry fixture references; unload between cases.
    for key in list(sys.modules):
        if key.startswith(name+'.'):sys.modules.pop(key,None)


def request(body=None):
    async def read():return body or {}
    return SimpleNamespace(json=read)


@pytest.mark.parametrize('retired',[False,True])
def test_standalone_start_pull_keep_and_delete_without_shared_cache(puller,retired):
    p=puller
    if retired:
        (p.settings_dir/'coordinated-cache.json').write_text(json.dumps({'enabled':True,'retired':True,'state':'unused-fenced-state'}))
    p.package.setup()
    assert ('POST','/mhnodes/model_puller/pull') in p.routes.handlers
    assert bool(p.purge_calls) is not retired
    source=p.root/'source/vae/tiny.pt';source.write_bytes(b'tiny standalone regression')
    result=asyncio.run(p.routes.handlers['GET','/mhnodes/model_puller/targets'](request()))
    assert result['targets']['vae']['destination']==str(p.root/'models/vae')
    result=asyncio.run(p.routes.handlers['POST','/mhnodes/model_puller/pull'](request({'items':[{'path':'vae/tiny.pt'}]})))
    assert result['queued']==['vae/tiny.pt']
    destination=p.root/'models/vae/tiny.pt'
    assert destination.read_bytes()==source.read_bytes()
    assert p.reg.get('vae/tiny.pt')['path']==str(destination)
    assert any(event[0].endswith('.done') for event in p.events)
    asyncio.run(p.routes.handlers['POST','/mhnodes/model_puller/keep'](request({'key':'vae/tiny.pt','kept':True})))
    assert p.reg.get('vae/tiny.pt')['kept']
    asyncio.run(p.routes.handlers['POST','/mhnodes/model_puller/delete'](request({'key':'vae/tiny.pt'})))
    assert not destination.exists() and source.exists() and p.reg.get('vae/tiny.pt') is None
    result=asyncio.run(p.routes.handlers['POST','/mhnodes/model_puller/purge'](request()))
    assert result['dry_run'] is retired


def test_standalone_removal_refuses_manual_and_replaced_files(puller):
    p=puller;p.package.setup()
    manual=p.root/'models/vae/manual.pt';manual.write_bytes(b'manual')
    with pytest.raises(OSError):p.modules['coordinated'].remove_model('vae/manual.pt')
    p.reg.record_pull('vae/manual.pt',str(manual));manual.write_bytes(b'replaced with different content')
    with pytest.raises(OSError):p.modules['coordinated'].remove_model('vae/manual.pt')
    assert manual.read_bytes()==b'replaced with different content'


def test_disabled_coordinated_configuration_does_not_disable_puller(puller):
    p=puller;(p.settings_dir/'coordinated-cache.json').write_text('{"enabled":false}')
    p.package.setup()
    assert ('POST','/mhnodes/model_puller/pull') in p.routes.handlers
    assert p.modules['coordinated']._bridge is None
