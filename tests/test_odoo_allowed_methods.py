"""Exact method management with synthetic state and no backend I/O."""
from contextlib import closing
import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from mcp_admin_core.config import ConfigError
from mcp_admin_core.configuration import ConfigurationState
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.migration import MigrationError, owner_record, plan_migration, plan_owner_restore
from mcp_admin_core.odoo_methods import MAX_METHODS, MAX_ENTRY_LENGTH, validate_methods
from mcp_admin_core.products import ProductStore, TOOLS, child_spec
from n8n_adapter import TOOLS as N8N_TOOLS
from owned_runtime import forbidden_transport
from test_real_products import connection


METHODS = ['sale.order.action_confirm', 'res.partner.get_portal_url']
ROUTE = '/api/odoo/allowed-methods'
INVALID = [None, '', 'res.partner.action_confirm', {}, (), True, [1], [None], [{}], [[]],
           ['res.partner.action_confirm'] * 2, ['res.partner.*'], ['*.action_confirm'],
           ['res.partner._private'], ['res.partner.__class__'],
           ['action_confirm'], ['res..partner.action_confirm'], ['.res.partner.action_confirm'],
           ['res.partner.action_confirm.'], ['res.partner.1method'], ['1model.action_confirm'],
           ['res-partner.action_confirm'], ['res.partner.action-confirm'], ['res.partner.方法'],
           [' res.partner.action_confirm'], ['res.partner.action_confirm '],
           ['res.partner.action_confirm\n'], ['res.partner.action_confirm,res.partner.write'],
           ['res.partner.action_confirm\x00'], ['x.' + 'a' * MAX_ENTRY_LENGTH],
           [f'res.partner.action_{i}' for i in range(MAX_METHODS + 1)],
           [f'res.partner.{"a" * 240}{i}' for i in range(70)]]


@pytest.mark.parametrize('value', INVALID)
def test_invalid_values_are_inert_for_state_and_migration(tmp_path, value):
    with closing(ProductStore(tmp_path, 'odoo')) as store:
        original = store.path.read_bytes()
        with pytest.raises(ConfigError):
            store.update(odoo_allowed_methods=value)
        assert store.path.read_bytes() == original
        with pytest.raises(MigrationError):
            plan_migration({**json.loads(original), 'odoo_allowed_methods': value}, 'odoo', policy='all_on')


def test_exact_names_boundaries_and_order():
    values = ['res.partner', 'x_studio_model.action_review2', 'sale.order.ActionConfirm', 'sale.order.actionConfirm']
    assert validate_methods(values) == values
    assert validate_methods([]) == []
    assert len(validate_methods([f'res.partner.action_{i}' for i in range(MAX_METHODS)])) == MAX_METHODS
    assert validate_methods(['x.' + 'a' * (MAX_ENTRY_LENGTH - 2)])


def test_absent_state_is_not_rewritten_and_persisted_list_controls_fixed_child(tmp_path, monkeypatch):
    monkeypatch.setenv('ODOO_MCP_ALLOWED_SIDE_EFFECT_METHODS', 'ambient.model.method')
    with closing(ProductStore(tmp_path, 'odoo')) as store:
        store.update(connection=connection('odoo', 'http://127.0.0.1:9999'),
                     writes_enabled=False, enabled_write_tools=[], disabled=['chatter_post'],
                     denied_operations={'execute_method': ['old_operation']})
        original = store.path.read_bytes()
        assert 'odoo_allowed_methods' not in json.loads(original)
        configuration = ConfigurationState(store)
        before = configuration.launch_revision(store.load())
        assert child_spec(store.load(), store.directory).env['ODOO_MCP_ALLOWED_SIDE_EFFECT_METHODS'] == ''
    with closing(ProductStore(tmp_path, 'odoo')) as store:
        assert store.path.read_bytes() == original and store.load().odoo_allowed_methods is None
        state = store.update(odoo_allowed_methods=METHODS)
        assert configuration.launch_revision(state) != before
        assert not state.writes_enabled and state.enabled_write_tools == []
        assert state.disabled == ['chatter_post']
        assert state.denied_operations == {'execute_method': ['old_operation']}
        spec = child_spec(state, store.directory)
        assert spec.env['ODOO_MCP_ALLOWED_SIDE_EFFECT_METHODS'] == ','.join(METHODS)
        assert spec.argv[1].endswith('/apps/odoo/start_switches.py')
        assert 'ODOO_MCP_POLICY_FILE' not in spec.env
    with closing(ProductStore(tmp_path, 'odoo')) as store:
        assert store.load().odoo_allowed_methods == METHODS
        store.update(odoo_allowed_methods=[])
        assert json.loads(store.path.read_bytes())['odoo_allowed_methods'] == []
        assert configuration.launch_revision(store.load()) == before


def test_optional_field_migration_and_owner_restore(tmp_path):
    with closing(ProductStore(tmp_path, 'odoo')) as store:
        old = json.loads(store.path.read_bytes())
        legacy = {**old, 'schema_version': 3, 'enabled_write_tools': []}
        assert plan_migration(legacy, 'odoo', policy='all_on').state.odoo_allowed_methods is None
        for version in (2, 3):
            source = {**legacy, 'schema_version': version, 'odoo_allowed_methods': METHODS}
            if version == 2:
                del source['enabled_write_tools']
            with pytest.raises(MigrationError):
                plan_migration(source, 'odoo', policy='all_on')
            with pytest.raises(ValueError):
                store._decode(source)
        saved = {**old, 'odoo_allowed_methods': METHODS}
        for policy in ('all_on', 'preserve'):
            assert plan_migration(saved, 'odoo', policy=policy).state.odoo_allowed_methods == METHODS
        restored = plan_owner_restore(saved, 'odoo', owner_record(legacy, 'odoo'))
        assert restored.state.odoo_allowed_methods == METHODS


@pytest.mark.parametrize('product', ['n8n', 'odoo-manage', 'hermes', 'opendesign', 'emqx', 'litellm', 'nextcloud'])
async def test_wrong_products_never_accept_or_expose_field(tmp_path, product):
    async def verify(_): return True
    with closing(ProductStore(tmp_path, product)) as store:
        for value in ([], METHODS):
            with pytest.raises(ConfigError):
                store.update(odoo_allowed_methods=value)
            with pytest.raises(MigrationError):
                plan_migration({**store.load().model_dump(), 'odoo_allowed_methods': value}, product, policy='all_on')
        async with httpx.AsyncClient(transport=forbidden_transport()) as child:
            admin, _ = make_apps(store, N8N_TOOLS if product == 'n8n' else TOOLS[product], child, verify_admin=verify)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://admin') as client:
                identity = {'x-remote-user-id': 'fake-admin'}
                boot = await client.get('/api/bootstrap', headers=identity)
                assert 'odoo_allowed_methods' not in boot.json()
                assert 'odoo_allowed_methods_source' not in boot.json()
                headers = {**identity, 'x-csrf-token': boot.json()['csrf'], 'if-match': boot.headers['etag']}
                assert (await client.put(ROUTE, headers=headers, json={'odoo_allowed_methods': []})).status_code == 400


async def test_admin_validation_csrf_fresh_role_revision_and_clear(tmp_path):
    restarts, roles = [], []
    allowed = True
    async def verify(user):
        roles.append(user)
        return allowed
    async def restart(state): restarts.append(state.odoo_allowed_methods)
    with closing(ProductStore(tmp_path, 'odoo')) as store:
        store.update(connection=connection('odoo', 'http://127.0.0.1:9999'))
        original = store.path.read_bytes()
        async with httpx.AsyncClient(transport=forbidden_transport()) as child:
            admin, _ = make_apps(store, TOOLS['odoo'], child, verify_admin=verify, backend_changed=restart)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://admin') as client:
                identity = {'x-remote-user-id': 'fake-admin'}
                boot = await client.get('/api/bootstrap', headers=identity)
                assert boot.json()['odoo_allowed_methods'] == []
                assert boot.json()['odoo_allowed_methods_source'] == 'legacy_empty'
                assert store.load().connection.password not in boot.text
                assert store.load().child_token not in boot.text and store.load().token not in boot.text
                payload = {'odoo_allowed_methods': METHODS}
                assert (await client.put(ROUTE, headers=identity, json=payload)).status_code == 403
                headers = {**identity, 'x-csrf-token': boot.json()['csrf']}
                assert (await client.put(ROUTE, headers=headers, json=payload)).status_code == 428
                headers['if-match'] = boot.headers['etag']
                count = len(roles)
                allowed = False
                assert (await client.put(ROUTE, headers=headers, json=payload)).status_code == 403
                assert len(roles) > count
                allowed = True
                for invalid in (None, [], {}, {'odoo_allowed_methods': None}, {'odoo_allowed_methods': METHODS, 'writes_enabled': True},
                                *({'odoo_allowed_methods': value} for value in INVALID if not isinstance(value, tuple))):
                    assert (await client.put(ROUTE, headers={**headers, 'content-type': 'application/json'},
                                             content=json.dumps(invalid))).status_code == 400
                assert store.path.read_bytes() == original and not restarts
                result = await client.put(ROUTE, headers=headers, json=payload)
                assert result.status_code == 200 and result.json()['saved'] is True
                assert restarts == [METHODS] and store.load().odoo_allowed_methods == METHODS
                saved = store.path.read_bytes()
                stale = await client.put(ROUTE, headers=headers, json={'odoo_allowed_methods': []})
                assert stale.status_code == 409 and stale.json()['detail']['code'] == 'config_conflict'
                assert store.path.read_bytes() == saved and restarts == [METHODS]
                changed = await client.get('/api/bootstrap', headers=identity)
                assert changed.json()['odoo_allowed_methods'] == METHODS
                assert changed.json()['odoo_allowed_methods_source'] == 'saved'
                assert changed.headers['etag'] == result.headers['etag']
                headers['if-match'] = result.headers['etag']
                cleared = await client.put(ROUTE, headers=headers, json={'odoo_allowed_methods': []})
                assert cleared.status_code == 200 and restarts == [METHODS, []]
                assert store.load().odoo_allowed_methods == []
                assert (await client.get('/api/bootstrap', headers=identity)).json()['odoo_allowed_methods_source'] == 'saved'


async def test_failed_apply_retains_saved_list_and_reports_sanitized_lifecycle(tmp_path):
    with closing(ProductStore(tmp_path, 'odoo')) as store:
        store.update(connection=connection('odoo', 'http://127.0.0.1:9999'))
        process = SimpleNamespace(starts=1, status='running')
        tracker = ConfigurationState(store, process, SimpleNamespace(settled=(1, True, 'reachable', None)))
        async def verify(_): return True
        async def restart(state):
            tracker.begin(state)
            process.status = 'failed'
            tracker.failed()
            raise RuntimeError('PRIVATE_FAKE_CREDENTIAL')
        async with httpx.AsyncClient(transport=forbidden_transport()) as child:
            admin, _ = make_apps(store, TOOLS['odoo'], child, verify_admin=verify, backend_changed=restart, configuration=tracker)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://admin') as client:
                identity = {'x-remote-user-id': 'fake-admin'}
                boot = await client.get('/api/bootstrap', headers=identity)
                headers = {**identity, 'x-csrf-token': boot.json()['csrf'], 'if-match': boot.headers['etag']}
                response = await client.put(ROUTE, headers=headers, json={'odoo_allowed_methods': METHODS})
                assert response.status_code == 503 and response.json()['saved'] is True
                assert response.json()['detail']['code'] == 'config_apply_failed'
                assert response.json()['configuration']['apply_state'] == 'failed'
                assert response.json()['configuration']['saved_revision'] != boot.json()['configuration']['saved_revision']
                assert 'PRIVATE_FAKE_CREDENTIAL' not in response.text
                fresh = await client.get('/api/bootstrap', headers=identity)
                assert fresh.json()['odoo_allowed_methods'] == METHODS
                assert fresh.json()['configuration']['apply_state'] == 'failed'


async def test_committed_apply_keeps_lock_on_cancellation_and_rechecks_queued_role(tmp_path):
    entered, finish = asyncio.Event(), asyncio.Event()
    allowed, roles, applied = True, [], []
    async def verify(user):
        roles.append(user)
        return allowed
    async def restart(state):
        entered.set()
        await finish.wait()
        applied.append(state.odoo_allowed_methods)
    with closing(ProductStore(tmp_path, 'odoo')) as store:
        async with httpx.AsyncClient(transport=forbidden_transport()) as child:
            admin, _ = make_apps(store, TOOLS['odoo'], child, verify_admin=verify, backend_changed=restart)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://admin') as client:
                identity = {'x-remote-user-id': 'fake-admin'}
                boot = await client.get('/api/bootstrap', headers=identity)
                headers = {**identity, 'x-csrf-token': boot.json()['csrf'], 'if-match': boot.headers['etag']}
                request = asyncio.create_task(client.put(ROUTE, headers=headers, json={'odoo_allowed_methods': METHODS}))
                queued = None
                try:
                    await asyncio.wait_for(entered.wait(), 2)
                    assert store.load().odoo_allowed_methods == METHODS
                    committed = store.path.read_bytes()
                    request.cancel()
                    allowed = False
                    count = len(roles)
                    queued = asyncio.create_task(client.put(ROUTE, headers=headers, json={'odoo_allowed_methods': []}))
                    await asyncio.sleep(.02)
                    assert not request.done() and not queued.done() and len(roles) == count
                    finish.set()
                    with pytest.raises(asyncio.CancelledError):
                        await asyncio.wait_for(request, 2)
                    assert (await asyncio.wait_for(queued, 2)).status_code == 403
                    assert applied == [METHODS] and len(roles) == count + 1
                    assert store.path.read_bytes() == committed
                finally:
                    finish.set()
                    await asyncio.gather(*(task for task in (request, queued) if task), return_exceptions=True)
