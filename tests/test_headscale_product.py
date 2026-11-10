"""Headscale's HA product boundary: typed connection, exact grants, and child isolation."""
from contextlib import closing
from pathlib import Path

import pytest

from mcp_admin_core import products
from mcp_admin_core.backend_edit import changes, view
from mcp_admin_core.policy import ToolCallRefused, authorize
from mcp_admin_core.products import (HeadscaleConnection, ProductStore, TOOLS,
                                     check_saved_destinations, child_spec,
                                     fresh_write_grants, health_probe, probe_success)
from mcp_admin_core.config import ConfigError
from mcp_admin_core.owner_defaults import apply_legacy_upgrade


def test_headscale_connection_is_one_exact_origin():
    assert HeadscaleConnection(url='https://hs.example.test/api/v1', api_key='DUMMY').url == 'https://hs.example.test'
    for bad in ('https://hs.example.test/proxy', 'https://hs.example.test/api/v1/user',
                'https://hs.example.test@other.example', 'https://hs.example.test?token=x'):
        with pytest.raises(ValueError):
            HeadscaleConnection(url=bad, api_key='DUMMY')
    with pytest.raises(ValueError):
        HeadscaleConnection(url='https://hs.example.test', api_key='bad key')


def test_headscale_grants_and_policy_are_exact(tmp_path):
    with closing(ProductStore(tmp_path, 'headscale')) as store:
        state = store.load()
        assert state.connection is None
        assert set(state.enabled_write_tools) == set(fresh_write_grants('headscale'))
        assert set(TOOLS['headscale']) == {
            'headscale_users', 'headscale_nodes', 'headscale_register', 'headscale_preauth_keys',
            'headscale_auth', 'headscale_api_keys', 'headscale_policy', 'headscale_routes_replace',
            'headscale_health', 'headscale_debug_node', 'headscale_backfill_ips'}
        store.update(connection={'url': 'https://hs.example.test', 'api_key': 'DUMMY'})
        state = store.load()
        assert view(state)['secret_set'] == {'api_key': True}
        assert view(state)['values'] == {'url': 'https://hs.example.test'}
        assert changes(state, {'changes': {'api_key': 'REPLACEMENT'}}) == {
            'connection': {'url': 'https://hs.example.test', 'api_key': 'REPLACEMENT'}}
        check_saved_destinations(state)
        with pytest.raises(ValueError):
            check_saved_destinations(state.model_copy(update={
                'connection': HeadscaleConnection(url='http://100.101.102.103', api_key='DUMMY')}))
        store.update(enabled_write_tools=[g for g in state.enabled_write_tools
                                          if g != 'headscale_policy:apply' and g != 'headscale_routes_replace'])
        state = store.load()
        for name, args in (
            ('headscale_policy', {'operation': 'apply', 'policy': '{}', 'expected_digest': 'a'*64}),
            ('headscale_routes_replace', {'node_id': '1', 'routes': []}),
            ('headscale_nodes', {'operation': 'not_native'}),
        ):
            message = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                       'params': {'name': name, 'arguments': args}}
            with pytest.raises(ToolCallRefused):
                authorize(message, TOOLS['headscale'], state)


def test_headscale_health_requires_real_database_response():
    assert health_probe('headscale') == ('headscale_health', {})
    assert probe_success('headscale', {'databaseConnectivity': True})
    for result in ({'databaseConnectivity': 1}, {'databaseConnectivity': False},
                   {'databaseConnectivity': True, 'error': 'failed'}, {}, []):
        assert not probe_success('headscale', result)


def test_headscale_child_only_gets_scoped_credentials_and_state_path(tmp_path, monkeypatch):
    root = tmp_path / 'checkout'
    binary = root / 'apps/headscale/.venv/bin/python'
    binary.parent.mkdir(parents=True)
    binary.touch()
    monkeypatch.setattr(products, 'ROOT', root)
    with closing(ProductStore(tmp_path / 'data', 'headscale')) as store:
        store.update(connection={'url': 'https://hs.example.test', 'api_key': 'DUMMY'})
        spec = child_spec(store.load(), store.directory)
        assert spec.argv == (str(binary), str(root / 'apps/headscale/launch.py'), '--host', '127.0.0.1',
                             '--port', '3000')
        assert spec.env['HEADSCALE_MCP_BASE_URL'] == 'https://hs.example.test'
        assert spec.env['HEADSCALE_MCP_API_KEY'] == 'DUMMY'
        assert spec.env['HEADSCALE_MCP_STATE_PATH'] == str(store.path)
        assert 'SUPERVISOR_TOKEN' not in spec.env
        assert spec.cwd == store.directory / 'child'


def test_headscale_accepts_current_state_but_refuses_fabricated_legacy_state(tmp_path):
    with closing(ProductStore(tmp_path, 'headscale')) as store:
        current = store.path.read_text()
    assert apply_legacy_upgrade(tmp_path, 'headscale') is None
    import json
    legacy = json.loads(current)
    legacy['schema_version'] = 3
    (tmp_path / 'state.json').write_text(json.dumps(legacy))
    with pytest.raises(ConfigError):
        apply_legacy_upgrade(tmp_path, 'headscale')
    assert json.loads((tmp_path / 'state.json').read_text()) == legacy
