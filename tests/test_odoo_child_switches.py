"""Four child switches: PaaS #89 decisions, exact state, management, offline listing (synthetic only)."""
from contextlib import closing
from itertools import product
import json
from types import SimpleNamespace

import httpx
import pytest

from mcp_admin_core import odoo_write_gates as gates
from mcp_admin_core.config import ConfigError
from mcp_admin_core.configuration import ConfigurationState
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.migration import owner_record, plan_migration, plan_owner_restore
from mcp_admin_core.odoo_switch_listing import for_state
from mcp_admin_core.policy import authorize, ToolCallRefused
from mcp_admin_core.products import ProductStore, TOOLS, child_spec
from mcp_admin_core.surface import listing
from test_expansion_policy import call
from test_real_products import connection


ALL_ON = dict(enable_writes=True, allow_direct_writes=True, allow_unknown_methods=True, chatter_direct=True)


@pytest.mark.parametrize('values', [dict(zip(ALL_ON, bits)) for bits in product((False, True), repeat=4)])
def test_all_sixteen_gate_combinations_match_explicit_precedence(values):
    switches = gates.Switches(values['enable_writes'], values['allow_direct_writes'],
                              values['allow_unknown_methods'], values['chatter_direct'])
    def refused(model, method, safety='unknown', allowlisted=False):
        return gates.execute_method_refusal(model, method, {'safety': safety}, lambda: allowlisted, switches)

    # Reviewed reads remain readable even when every child write switch is off.
    assert refused('res.partner', 'search_read', 'read_only') is None
    assert (refused('res.partner', 'create', 'destructive') is None) is (switches.enable and switches.direct)
    assert (refused('res.partner', 'action_confirm') is None) is (switches.enable and switches.direct and switches.unknown)
    assert (refused('res.partner', 'get_portal_url', 'read_only') is None) is (switches.enable and switches.direct and switches.unknown)
    assert (refused('res.partner', 'action_confirm', allowlisted=True) is None) is switches.enable
    assert (refused('res.partner', 'message_post', allowlisted=True) is None) is (switches.enable and switches.chatter)
    assert (refused('mail.message', 'create', 'destructive') is None) is (switches.enable and switches.direct and switches.chatter)
    assert (gates.chatter_post_refusal(switches) is None) is switches.enable
    assert gates.unknown_methods_run(switches) is (switches.enable and switches.direct and switches.unknown)


def test_old_schema_four_remains_exact_and_outer_revocations_stay_revoked(tmp_path):
    with closing(ProductStore(tmp_path / 'state', 'odoo')) as store:
        store.update(connection=connection('odoo', 'http://127.0.0.1:9999'),
                     writes_enabled=False, enabled_write_tools=[], disabled=['chatter_post'],
                     denied_operations={'execute_method': ['old_operation']})
        old = json.loads(store.path.read_text())
        assert 'odoo_write_switches' not in old
        assert store.load().effective_odoo_write_switches.model_dump() == ALL_ON
        configuration = ConfigurationState(store)
        before = configuration.launch_revision(store.load())
        store.update(odoo_write_switches={**ALL_ON, 'allow_direct_writes': False})
        after = configuration.launch_revision(store.load())
        assert before != after
        assert store.load().enabled_write_tools == [] and not store.load().writes_enabled
        assert store.load().disabled == ['chatter_post']
        assert store.load().denied_operations == {'execute_method': ['old_operation']}
        with pytest.raises(ToolCallRefused):
            authorize(call('execute_method', {'model': 'res.partner', 'method': 'write',
                                              'args': [[1], {'name': 'fake'}]}), TOOLS['odoo'], store.load())
        spec = child_spec(store.load(), store.directory)
        assert spec.env['ODOO_MCP_ALLOW_DIRECT_WRITES'] == '0'
        assert spec.env['ODOO_MCP_ENABLE_WRITES'] == '1'
        assert spec.argv[1].endswith('/apps/odoo/start_switches.py')
    with closing(ProductStore(tmp_path / 'state', 'odoo')) as reopened:
        assert reopened.load().odoo_write_switches.allow_direct_writes is False
        assert reopened.load().enabled_write_tools == []


def test_exact_key_validation_and_legacy_migration(tmp_path):
    with closing(ProductStore(tmp_path / 'state', 'odoo')) as store:
        old = json.loads(store.path.read_text())
        for bad in ({'enable_writes': False}, {**ALL_ON, 'extra': True}, {**ALL_ON, 'enable_writes': 1}):
            with pytest.raises(ConfigError):
                store.update(odoo_write_switches=bad)
        assert json.loads(store.path.read_text()) == old
        with pytest.raises(ValueError):
            store._decode({**old, 'odoo_write_switches': None})
        legacy = {**old, 'schema_version': 3, 'enabled_write_tools': []}
        migrated = plan_migration(legacy, 'odoo', policy='all_on')
        assert migrated.state.odoo_write_switches is None
        assert migrated.state.effective_odoo_write_switches.model_dump() == ALL_ON
        with pytest.raises(Exception):
            plan_migration({**legacy, 'odoo_write_switches': ALL_ON}, 'odoo', policy='all_on')
        saved = {**old, 'odoo_write_switches': {**ALL_ON, 'chatter_direct': False}}
        assert plan_migration(saved, 'odoo', policy='all_on').state.odoo_write_switches.chatter_direct is False
        restored = plan_owner_restore(saved, 'odoo', owner_record(legacy, 'odoo'))
        assert restored.state.odoo_write_switches.chatter_direct is False
        with pytest.raises(Exception):
            plan_migration({**saved, 'odoo_write_switches': None}, 'odoo', policy='all_on')
    with closing(ProductStore(tmp_path / 'other', 'hermes')) as other:
        with pytest.raises(ConfigError):
            other.update(odoo_write_switches=ALL_ON)


def test_offline_listing_matches_saved_switches(tmp_path):
    with closing(ProductStore(tmp_path / 'state', 'odoo')) as store:
        baseline = listing('odoo')
        assert for_state(baseline, store.load()) is not baseline
        store.update(odoo_write_switches=dict(enable_writes=False, allow_direct_writes=True,
                                              allow_unknown_methods=True, chatter_direct=True))
        indexed = {item['name']: item for item in for_state(baseline, store.load())}
        assert 'writes are disabled' in indexed['execute_method']['inputSchema']['properties']['method']['description']
        assert 'refuses every call' in indexed['chatter_post']['description']
        assert 'valid=true' not in indexed['validate_write']['description']


async def test_admin_route_requires_role_csrf_revision_and_restarts_only_odoo(tmp_path):
    restarts = []
    role = {'allowed': True}
    async def verify(_): return role['allowed']
    async def restart(state): restarts.append(state.odoo_write_switches)
    with closing(ProductStore(tmp_path / 'state', 'odoo')) as store:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as child:
            admin, _ = make_apps(store, TOOLS['odoo'], child, verify_admin=verify, backend_changed=restart,
                                 listing=listing('odoo'))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://admin') as client:
                identity = {'x-remote-user-id': 'fake-admin'}
                boot = await client.get('/api/bootstrap', headers=identity)
                assert boot.json()['odoo_write_switches'] == ALL_ON
                assert boot.json()['odoo_write_switches_source'] == 'legacy_all_on'
                payload = {'odoo_write_switches': {**ALL_ON, 'chatter_direct': False}}
                assert (await client.put('/api/odoo/write-switches', headers=identity, json=payload)).status_code == 403
                headers = {**identity, 'x-csrf-token': boot.json()['csrf']}
                assert (await client.put('/api/odoo/write-switches', headers=headers, json=payload)).status_code == 428
                conditional = {**headers, 'if-match': boot.headers['etag']}
                role['allowed'] = False
                assert (await client.put('/api/odoo/write-switches', headers=conditional, json=payload)).status_code == 403
                role['allowed'] = True
                for invalid in ({'odoo_write_switches': {'chatter_direct': False}},
                                {'odoo_write_switches': {**ALL_ON, 'chatter_direct': 0}},
                                {'odoo_write_switches': ALL_ON, 'writes_enabled': True}):
                    assert (await client.put('/api/odoo/write-switches', headers=conditional, json=invalid)).status_code == 400
                assert restarts == [] and store.load().odoo_write_switches is None
                saved = await client.put('/api/odoo/write-switches', headers=conditional, json=payload)
                assert saved.status_code == 200 and saved.json()['saved'] is True
                assert len(restarts) == 1 and restarts[0].chatter_direct is False
                assert store.load().odoo_write_switches.chatter_direct is False
                assert (await client.put('/api/odoo/write-switches', headers=conditional, json=payload)).status_code == 409
                assert len(restarts) == 1
                changed = await client.get('/api/bootstrap', headers=identity)
                assert changed.json()['odoo_write_switches_source'] == 'saved'
                assert changed.json()['odoo_write_switches']['chatter_direct'] is False
    with closing(ProductStore(tmp_path / 'other', 'hermes')) as other:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as child:
            admin, _ = make_apps(other, TOOLS['hermes'], child, verify_admin=verify, backend_changed=restart)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://admin') as client:
                boot = await client.get('/api/bootstrap', headers=identity)
                assert 'odoo_write_switches' not in boot.json()
                headers = {**identity, 'x-csrf-token': boot.json()['csrf'], 'if-match': boot.headers['etag']}
                assert (await client.put('/api/odoo/write-switches', headers=headers, json=payload)).status_code == 400


async def test_saved_switches_report_failed_child_apply_without_rollback_or_secret_leak(tmp_path):
    with closing(ProductStore(tmp_path / 'state', 'odoo')) as store:
        store.update(connection=connection('odoo', 'http://127.0.0.1:9999'))
        process = SimpleNamespace(starts=1, status='running')
        health = SimpleNamespace(settled=(1, True, 'reachable', None))
        tracker = ConfigurationState(store, process, health)
        async def verify(_): return True
        async def restart(state):
            tracker.begin(state)
            process.status = 'failed'
            tracker.failed('child_start_failed')
            raise RuntimeError('PRIVATE_FAKE_CREDENTIAL')
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as child:
            admin, _ = make_apps(store, TOOLS['odoo'], child, configuration=tracker,
                                 verify_admin=verify, backend_changed=restart)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)),
                                         base_url='http://admin') as client:
                identity = {'x-remote-user-id': 'fake-admin'}
                boot = await client.get('/api/bootstrap', headers=identity)
                values = {**ALL_ON, 'enable_writes': False}
                headers = {**identity, 'x-csrf-token': boot.json()['csrf'], 'if-match': boot.headers['etag']}
                response = await client.put('/api/odoo/write-switches', headers=headers,
                                            json={'odoo_write_switches': values})
                assert response.status_code == 503
                assert response.json()['saved'] is True
                assert response.json()['detail']['code'] == 'config_apply_failed'
                assert response.json()['configuration']['apply_state'] == 'failed'
                assert 'PRIVATE_FAKE_CREDENTIAL' not in response.text
                fresh = await client.get('/api/bootstrap', headers=identity)
                assert fresh.json()['odoo_write_switches'] == values
                assert fresh.json()['configuration']['apply_state'] == 'failed'
