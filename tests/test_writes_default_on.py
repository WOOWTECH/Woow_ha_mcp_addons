"""Owner decision 2026-10-15: a NEW installation starts with every reviewed write enabled.

Only a state created on first boot gets the default; an existing state (and what an administrator saved in it) is
never rewritten, a write turned off stays off across restarts, and an upgrade from an older state keeps its grants.
"""
from contextlib import closing
import json
from pathlib import Path
import subprocess

import httpx
import pytest

from mcp_admin_core.config import Store
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.policy import Denied, ToolCallRefused, authorize, enabled
from mcp_admin_core.products import PRODUCTS, ProductStore, TOOLS, fresh_write_grants, write_grants
from n8n_adapter import TOOLS as N8N_TOOLS
from test_expansion_policy import call

ROOT = Path(__file__).resolve().parents[1]
ALL = (*PRODUCTS, 'n8n')
# One representative write call per product (exact grant shown); Odoo Manage keeps writes off (module mode only).
WRITE_CALLS = {
    'odoo': ('chatter_post', {'model': 'res.partner', 'record_id': 1, 'body': 'x'}),
    'hermes': ('hermes_skill', {'action': 'disable', 'name': 'example'}),
    'opendesign': ('delete_project', {'project_id': '12345678-1234-1234-1234-123456789abc'}),
    'emqx': ('emqx_kick_client', {'clientid': 'device'}),
    'litellm': ('litellm_delete_model', {'model_id': 'one'}),
    'nextcloud': ('delete_file_checked', {'path': 'a.txt', 'expected_etag': '"e"'}),
    'n8n': ('n8n_manage_folders', {'action': 'create', 'projectId': 'project', 'name': 'New'}),
}


def tools_of(product):
    return N8N_TOOLS if product == 'n8n' else TOOLS[product]


def grants_of(product):
    return {g for name, tool in tools_of(product).items() for g in tool.grants(name)}


def test_reviewed_grant_sets_match_the_tools():
    for product in ALL:
        assert write_grants(product) == grants_of(product), product
    # Hermes tool:action and n8n_manage_folders operation grants are part of the default.
    assert {'hermes_skill:enable', 'hermes_skill:disable', 'hermes_gateway:restart', 'hermes_session:delete',
            'hermes_tools:enable', 'hermes_tools:disable', 'hermes_cron:delete', 'hermes_cron:pause'} <= write_grants('hermes')
    assert {'n8n_manage_folders:create', 'n8n_manage_folders:rename', 'n8n_delete_workflow'} <= write_grants('n8n')


@pytest.mark.parametrize('product', ALL)
def test_new_state_enables_every_write(tmp_path, product):
    with closing(ProductStore(tmp_path, product)) as store:
        state = store.load()
        assert state.writes_enabled is True
        if product == 'odoo-manage':
            # Its writers require an existing MCP module connection (mode 'module'); a new state has none.
            assert state.enabled_write_tools == [] and fresh_write_grants(product) == []
            return
        assert state.enabled_write_tools == sorted(grants_of(product)) == fresh_write_grants(product)
        tools = tools_of(product)
        assert all(enabled(name, tools, state) for name in tools)
        stored = json.loads(store.path.read_text())
        assert stored['writes_enabled'] is True and stored['enabled_write_tools'] == state.enabled_write_tools


@pytest.mark.parametrize('product', sorted(WRITE_CALLS))
def test_new_state_authorizes_a_write_and_a_revoked_grant_stays_revoked(tmp_path, product):
    name, arguments = WRITE_CALLS[product]
    tools = tools_of(product)
    tool = tools[name]
    grant = name if tool.write else f'{name}:{arguments[tool.selector]}'
    store = ProductStore(tmp_path, product)
    try:
        if product == 'n8n':
            store.update(backend_url='http://127.0.0.1:9', backend_key='DUMMY')
        assert authorize(call(name, arguments), tools, store.load()) == 'tools/call'
        # What the panel saves when the administrator unticks one write (the UI always sends writes_enabled false).
        remaining = [g for g in store.load().enabled_write_tools if g != grant]
        store.update(writes_enabled=False, enabled_write_tools=remaining)
    finally:
        store.close()
    store = ProductStore(tmp_path, product)  # restart: the existing state is loaded, never re-seeded
    try:
        state = store.load()
        assert state.writes_enabled is False and state.enabled_write_tools == remaining
        with pytest.raises(ToolCallRefused):
            authorize(call(name, arguments), tools, state)
    finally:
        store.close()


@pytest.mark.parametrize('product', ALL)
def test_existing_read_only_state_is_not_rewritten(tmp_path, product):
    with closing(ProductStore(tmp_path, product)) as store:
        store.update(writes_enabled=False, enabled_write_tools=[])
        before = store.path.read_bytes()
    for _ in range(2):  # two restarts
        with closing(ProductStore(tmp_path, product)) as store:
            assert store.path.read_bytes() == before
            state = store.load()
            assert state.writes_enabled is False and state.enabled_write_tools == []
            tools = tools_of(product)
            assert not any(enabled(name, tools, state) for name, tool in tools.items() if tool.write)


def test_state_written_by_an_older_version_keeps_its_grants(tmp_path):
    # A v3 state as 0.1.14 created it (writes off, one grant the administrator chose) is loaded unchanged.
    with closing(ProductStore(tmp_path, 'emqx')) as store:
        old = {**store.load().model_dump(), 'writes_enabled': False, 'enabled_write_tools': ['emqx_kick_client']}
    store.path.write_text(json.dumps(old))
    raw = store.path.read_bytes()
    with closing(ProductStore(tmp_path, 'emqx')) as store:
        assert store.path.read_bytes() == raw
        assert store.load().enabled_write_tools == ['emqx_kick_client'] and store.load().writes_enabled is False


@pytest.mark.parametrize('product', ['hermes', 'n8n'])
def test_migrated_legacy_state_does_not_gain_writes(tmp_path, product):
    # v2 (and n8n v1) states predate exact grants: the upgrade keeps them without any (existing installations).
    with closing(ProductStore(tmp_path, product)) as store:
        old = store.load().model_dump()
    old.pop('enabled_write_tools')
    old.update(schema_version=2, writes_enabled=False)
    if product == 'n8n':
        old = {k: v for k, v in old.items() if k not in ('product', 'connection')}
        old['schema_version'] = 1
    store.path.write_text(json.dumps(old))
    with closing(ProductStore(tmp_path, product)) as store:
        state = store.load()
        assert state.schema_version == 3 and state.enabled_write_tools == [] and state.writes_enabled is False


def test_plain_v1_store_is_unchanged(tmp_path):
    # Production always runs ProductStore; a plain v1 Store (migration source, test fixture) keeps writes off.
    with closing(Store(tmp_path)) as store:
        assert store.load().writes_enabled is False


@pytest.mark.parametrize('product,grant', [('n8n', 'n8n_delete_workflow'), ('hermes', 'hermes_cron:delete'),
                                          ('opendesign', 'delete_project')])
async def test_panel_shows_all_writes_on_and_unticking_one_survives_restart(tmp_path, product, grant):
    """The unmodified production UI serializers on a new state: every write is ticked; saving with one unticked
    stores exactly the rest, clears the legacy switch (so a legacy writer really is off) and survives a restart."""
    async def role(_): return True
    tools = tools_of(product)
    with closing(ProductStore(tmp_path, product)) as store:
        async with httpx.AsyncClient(trust_env=False) as child:
            admin, _ = make_apps(store, tools, child, verify_admin=role)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)),
                                         base_url='http://local') as client:
                identity = {'x-remote-user-id': 'a' * 32}
                bootstrap = (await client.get('/api/bootstrap', headers=identity)).json()
                assert bootstrap['writes_enabled'] is True
                assert sorted(bootstrap['enabled_write_tools']) == sorted(grants_of(product))
                probe = subprocess.run(['node', '--input-type=module', '-e', '''
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {granularPolicy, toolRows, effectiveGrant, policyPayload} from './packages/mcp-admin-ui/src/contracts.js';
const [b, off] = JSON.parse(fs.readFileSync(0, 'utf8'));
assert.equal(granularPolicy(b), true);
const ticked = [];
for (const row of toolRows(b)) {
  const operations = row.operations.length ? row.operations : row.write ? [null] : [];
  for (const operation of operations) {
    assert.equal(effectiveGrant(b, row, operation), true, row.name);  // every write is shown as allowed
    if ((operation === null ? row.name : `${row.name}:${operation}`) !== off) ticked.push({tool: row.name, operation});
  }
}
console.log(JSON.stringify(policyPayload(b, [], ticked)));
'''], cwd=ROOT, input=json.dumps([bootstrap, grant]), text=True, capture_output=True, timeout=10,
                    env={'PATH': '/usr/local/bin:/usr/bin:/bin'})
                assert probe.returncode == 0, probe.stderr
                payload = json.loads(probe.stdout)
                assert payload['writes_enabled'] is False and grant not in payload['enabled_write_tools']
                response = await client.put('/api/policy', headers={**identity, 'x-csrf-token': bootstrap['csrf']},
                                            json=payload)
                assert response.status_code == 200, response.text
        expected = sorted(grants_of(product) - {grant})
        assert sorted(store.load().enabled_write_tools) == expected
    with closing(ProductStore(tmp_path, product)) as store:
        state = store.load()
        assert state.writes_enabled is False and sorted(state.enabled_write_tools) == expected
        name = grant.split(':')[0]
        arguments = {'n8n_delete_workflow': {'id': 'one'}, 'hermes_cron': {'action': 'delete', 'job_id': 'example'},
                     'delete_project': {'project_id': '12345678-1234-1234-1234-123456789abc'}}[name]
        if product == 'n8n':
            store.update(backend_url='http://127.0.0.1:9', backend_key='DUMMY')
        with pytest.raises(Denied):
            authorize(call(name, arguments), tools, store.load())
