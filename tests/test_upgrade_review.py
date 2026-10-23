"""Real pre-start review apps and durable migration; synthetic state, no backend."""
import asyncio
from contextlib import closing
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from mcp_admin_core import upgrade, ui, run_product
from mcp_admin_core.config import ConfigError
from mcp_admin_core.migration import MigrationError, _existing_writer, apply_migration, source_digest
from mcp_admin_core.products import ProductStore
from test_migration_preview import fixture, install_fixture

IDENTITY = {'x-remote-user-id': 'a' * 32, 'x-ingress-path': '/api/hassio_ingress/REVIEW'}
BASE = IDENTITY['x-ingress-path']

async def allow(_):
    return True

@pytest.mark.parametrize('version,product', [(1,'n8n'),(2,'hermes'),(3,'hermes')])
@pytest.mark.parametrize('policy', ['all_on','preserve'])
async def test_authenticated_review_precedes_migration_and_normal_store(tmp_path, monkeypatch, version, product, policy):
    state = install_fixture(tmp_path/'state', fixture(version, product))
    old = state.read_bytes()
    assert upgrade.needs_review(state.parent, product)
    dist = tmp_path/'dist'; (dist/'assets').mkdir(parents=True)
    (dist/'index.html').write_text('<script src="__MCP_UI_BASE__/assets/app.js"></script>')
    (dist/'assets/upgrade.js').write_text('/* upgrade */')
    monkeypatch.setattr(ui, 'UI_ROOT', dist)
    with _existing_writer(state.parent) as writer:
        review = upgrade.UpgradeReview(writer, product)
        admin, public = upgrade.make_upgrade_apps(review, verify_admin=allow)
        with pytest.raises(ConfigError):
            ProductStore(state.parent, product)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2',1)), base_url='http://local', headers=IDENTITY) as c:
            page = await c.get(BASE+'/'); assert page.status_code==200 and '/assets/upgrade.js' in page.text
            b = (await c.get(BASE+'/api/bootstrap')).json()
            assert b['stage']=='upgrade_review' and b['default_policy']=='all_on'
            assert b['plans'][policy]['source_schema']==version
            assert state.read_bytes()==old
            for secret in ('token','child_token','backend_key','connection'):
                assert secret not in b
            for key in ('token', 'child_token', 'backend_key'):
                secret = json.loads(old).get(key)
                if secret is not None:
                    assert secret not in json.dumps(b)
            assert (await c.post(BASE+'/api/upgrade/apply',json={})).status_code==403
            response = await c.post(BASE+'/api/upgrade/apply',headers={'x-csrf-token':b['csrf']},json={'policy':policy,'expected_sha256':b['plans'][policy]['source_sha256']})
            assert response.status_code==202 and response.json()['stage']=='starting'
            assert review.completed.is_set()
            assert (await c.post(BASE+'/api/upgrade/apply',headers={'x-csrf-token':b['csrf']},json={'policy':policy,'expected_sha256':b['plans'][policy]['source_sha256']})).status_code==409
        async with httpx.AsyncClient(transport=httpx.ASGITransport(public),base_url='http://local') as c:
            assert (await c.post('/mcp',json={'method':'tools/call'})).status_code==503
    with closing(ProductStore(state.parent,product)) as loaded:
        final = loaded.load()
        assert final.schema_version==4 and final.token==json.loads(old)['token']
        assert final.disabled==b['plans'][policy]['after']['disabled']
    assert not upgrade.needs_review(state.parent, product)
    recovery = state.parent/'migration-policy-recovery.json'
    assert recovery.stat().st_mode & 0o777 == 0o600

async def test_stale_preview_role_revocation_and_unknown_fields_never_write(tmp_path):
    state=install_fixture(tmp_path/'state',fixture(3,'hermes')); allowed=True
    async def role(_): return allowed
    with _existing_writer(state.parent) as writer:
        review=upgrade.UpgradeReview(writer,'hermes');admin,_=upgrade.make_upgrade_apps(review,verify_admin=role)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(admin,client=('172.30.32.2',1)),base_url='http://local',headers=IDENTITY) as c:
            b=(await c.get('/api/bootstrap')).json();h={'x-csrf-token':b['csrf']};payload={'policy':'all_on','expected_sha256':b['plans']['all_on']['source_sha256']}
            old=json.loads(state.read_text());old['token']=None;state.write_text(json.dumps(old));unchanged=state.read_bytes()
            assert (await c.post('/api/upgrade/apply',headers=h,json=payload)).status_code==409
            assert state.read_bytes()==unchanged and not review.completed.is_set()
            assert not (state.parent/'migration-policy-recovery.json').exists()
            payload['expected_sha256']=source_digest(old)
            for malformed in [{**payload,'token':'injected'}, {**payload,'policy':'automatic'}, {**payload,'expected_sha256':None}]:
                assert (await c.post('/api/upgrade/apply',headers=h,json=malformed)).status_code==400
            allowed=False
            assert (await c.post('/api/upgrade/apply',headers=h,json=payload)).status_code==403
            assert (await c.get('/api/bootstrap')).status_code==403
            assert state.read_bytes()==unchanged
            allowed=True
            assert (await c.post('/api/upgrade/apply',headers={**h,'sec-fetch-site':'cross-site'},json=payload)).status_code==403
            assert (await c.post('/api/upgrade/apply',headers=h,content=b'x'*4097)).status_code==413
        for peer in [('127.0.0.1',1),('172.30.32.3',1)]:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin,client=peer),base_url='http://local',headers=IDENTITY) as c:
                assert (await c.get('/api/bootstrap')).status_code==403
        with pytest.raises(MigrationError):
            apply_migration(state.parent,'hermes',policy='all_on',expected_sha256=source_digest(old))
        assert state.read_bytes()==unchanged

async def test_review_save_failure_stays_pending_and_preserves_source(tmp_path,monkeypatch):
    state=install_fixture(tmp_path/'state',fixture(3,'hermes'));original=state.read_bytes()
    with _existing_writer(state.parent) as writer:
        review=upgrade.UpgradeReview(writer,'hermes');digest=review.plans()['all_on']['source_sha256']
        def fail(_):raise ConfigError('fixed fixture write failure')
        monkeypatch.setattr(writer,'_write',fail)
        with pytest.raises(MigrationError):review.apply({'policy':'all_on','expected_sha256':digest})
        assert not review.completed.is_set() and state.read_bytes()==original

async def test_fresh_and_current_state_skip_gate(tmp_path):
    args=SimpleNamespace(data=tmp_path/'new')
    assert await upgrade.run_upgrade_review(args,'hermes') is True
    assert not args.data.exists()
    with closing(ProductStore(args.data,'hermes')) as store:original=store.path.read_bytes()
    assert await upgrade.run_upgrade_review(args,'hermes') is True
    assert (args.data/'state.json').read_bytes()==original

@pytest.mark.parametrize('kind',['product','n8n'])
async def test_runtime_calls_gate_before_store_and_honors_shutdown(tmp_path,monkeypatch,kind):
    if kind=='product': module=run_product
    else:
        spec=importlib.util.spec_from_file_location('upgrade_n8n_runtime',Path(__file__).resolve().parents[1]/'apps/n8n/run.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    seen=[]
    async def gate(args,product):seen.append(product);return False
    def forbidden(*a,**k):raise AssertionError('Store constructed before confirmation')
    monkeypatch.setattr(upgrade,'run_upgrade_review',gate);monkeypatch.setattr(module,'ProductStore',forbidden)
    await module.run(SimpleNamespace(data=tmp_path/'state',product='hermes'))
    assert seen==['hermes' if kind=='product' else 'n8n']

async def test_disconnect_while_role_pending_has_no_effect_and_joins_role(tmp_path):
    state=install_fixture(tmp_path/'state',fixture(3,'hermes'));old=state.read_bytes();entered=asyncio.Event();closed=asyncio.Event()
    async def role(_):
        entered.set()
        try:await asyncio.Event().wait()
        finally:closed.set()
    with _existing_writer(state.parent) as writer:
        admin,_=upgrade.make_upgrade_apps(upgrade.UpgradeReview(writer,'hermes'),verify_admin=role)
        queue=asyncio.Queue();await queue.put({'type':'http.request','body':b'','more_body':False})
        scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'GET','scheme':'http','path':'/api/bootstrap','raw_path':b'/api/bootstrap','query_string':b'','headers':[(k.encode(),v.encode()) for k,v in IDENTITY.items()],'client':('172.30.32.2',1),'server':('local',80)}
        replies=[]
        async def send(value):replies.append(value)
        task=asyncio.create_task(admin(scope,queue.get,send));await asyncio.wait_for(entered.wait(),1)
        await queue.put({'type':'http.disconnect'});await asyncio.wait_for(task,1)
        assert closed.is_set() and state.read_bytes()==old
        assert replies[0]['status']==403

@pytest.mark.parametrize('confirm',[False,True])
async def test_pending_runtime_owns_lock_then_releases_after_both_listeners_stop(tmp_path,monkeypatch,confirm):
    state=install_fixture(tmp_path/'state',fixture(3,'hermes'));old=state.read_bytes();listeners=[];signals={}
    class Listener:
        def __init__(self,config):
            self.app=config.app;self.closed=False;self.ready=asyncio.Event();self.exit=asyncio.Event();listeners.append(self)
        @property
        def should_exit(self):return self.exit.is_set()
        @should_exit.setter
        def should_exit(self,value):
            if value:self.exit.set()
        async def serve(self):
            self.ready.set()
            try:await self.exit.wait()
            finally:self.closed=True
    monkeypatch.setattr(upgrade,'_Listener',Listener)
    monkeypatch.setattr(upgrade,'make_ha_admin_verifier',lambda:allow)
    loop=asyncio.get_running_loop()
    monkeypatch.setattr(loop,'add_signal_handler',lambda sig,cb:signals.__setitem__(sig,cb))
    monkeypatch.setattr(loop,'remove_signal_handler',lambda sig:signals.pop(sig,None))
    args=SimpleNamespace(data=state.parent,host='127.0.0.1',admin_port=18099,mcp_port=18081)
    task=asyncio.create_task(upgrade.run_upgrade_review(args,'hermes'))
    for _ in range(100):
        if len(listeners)==2 and all(x.ready.is_set() for x in listeners):break
        await asyncio.sleep(.001)
    assert len(listeners)==2 and state.read_bytes()==old
    with pytest.raises(ConfigError):ProductStore(state.parent,'hermes')
    if confirm:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(listeners[0].app,client=('172.30.32.2',1)),base_url='http://local',headers=IDENTITY) as c:
            b=(await c.get('/api/bootstrap')).json()
            response=await c.post('/api/upgrade/apply',headers={'x-csrf-token':b['csrf']},json={'policy':'all_on','expected_sha256':b['plans']['all_on']['source_sha256']})
            assert response.status_code==202
    else:signals[upgrade.signal.SIGTERM]()
    assert await asyncio.wait_for(task,2) is confirm
    assert all(x.closed for x in listeners) and not signals
    if confirm:
        with closing(ProductStore(state.parent,'hermes')) as store:assert store.load().schema_version==4
    else:
        assert state.read_bytes()==old
        with _existing_writer(state.parent):pass
