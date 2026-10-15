"""0.2.1: n8n's MCP access token.

n8n-mcp needs N8N_MCP_ACCESS_TOKEN (the instance-level MCP key, separate from the API key) for native version
history, data table column actions, n8n_test_workflow prepare/pinned/direct, n8n_explore_node_resources and
n8n_manage_agents; 0.2.0 never passed it, so those answered NOT_CONFIGURED.
"""
from contextlib import closing
import json
from pathlib import Path
import subprocess

import httpx
import pytest

from mcp_admin_core import redact
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductState, ProductStore
from n8n_adapter import TOOLS, child_spec

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = {'x-remote-user-id': 'a' * 32}


def test_only_n8n_holds_a_printable_token():
    state = ProductState(product='n8n', token='a' * 43, child_token='b' * 43, mcp_access_token='mcp-token-0815')
    assert state.mcp_access_token == 'mcp-token-0815' and 'mcp-token-0815' not in repr(state)
    with pytest.raises(ValueError):
        ProductState(product='emqx', token='a' * 43, child_token='b' * 43, mcp_access_token='mcp-token-0815')
    for bad in ('', 'x\ny', 'é' * 3, 'x' * 8193):
        with pytest.raises(ValueError):
            ProductState(product='n8n', token='a' * 43, child_token='b' * 43, mcp_access_token=bad)


@pytest.mark.parametrize('product', ['n8n', 'emqx'])
def test_a_0_2_0_state_gets_the_field_without_other_changes(tmp_path, product):
    with closing(ProductStore(tmp_path, product)) as store:
        store.update(disabled=[next(iter(store.load().enabled_write_tools)).split(':')[0]], enabled_write_tools=[])
        old = store.load().model_dump()
    old.pop('mcp_access_token')  # as 0.2.0 wrote schema 4
    store.path.write_text(json.dumps(old))
    with closing(ProductStore(tmp_path, product)) as store:
        state = store.load()
        assert state.mcp_access_token is None
        assert {k: v for k, v in state.model_dump().items() if k != 'mcp_access_token'} == old  # nothing else changes
        assert json.loads(store.path.read_text())['mcp_access_token'] is None  # written once


def test_child_gets_the_token_and_the_permissive_webhook_mode(tmp_path):
    state = ProductState(product='n8n', token='a' * 43, child_token='b' * 43, backend_url='http://172.30.33.10:5678',
                         backend_key='api-key-0815', mcp_access_token='mcp-token-0815')
    env = child_spec(state, tmp_path).env
    assert env['N8N_MCP_ACCESS_TOKEN'] == 'mcp-token-0815' and env['N8N_API_KEY'] == 'api-key-0815'
    without = state.model_copy(update={'mcp_access_token': None})
    env = child_spec(without, tmp_path).env
    assert 'N8N_MCP_ACCESS_TOKEN' not in env
    unconfigured = state.model_copy(update={'backend_url': None, 'backend_key': None})
    assert 'N8N_MCP_ACCESS_TOKEN' not in child_spec(unconfigured, tmp_path).env
    assert 'mcp-token-0815' in redact.secret_values(state)  # never relayed in a reply


async def test_admin_api_saves_reports_and_clears_the_token(tmp_path):
    async def role(_): return True
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        async with httpx.AsyncClient(trust_env=False) as child:
            admin, _ = make_apps(store, TOOLS, child, verify_admin=role)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)),
                                         base_url='http://local') as client:
                async def put(value):
                    csrf = (await client.get('/api/bootstrap', headers=IDENTITY)).json()['csrf']
                    return await client.put('/api/backend', headers={**IDENTITY, 'x-csrf-token': csrf}, json=value)

                assert (await client.get('/api/bootstrap', headers=IDENTITY)).json()['mcp_access_token_set'] is False
                response = await put({'url': 'http://172.30.33.10:5678', 'key': 'api-key-0815', 'mcp_access_token': 'mcp-token-0815'})
                assert response.status_code == 200, response.text
                bootstrap = (await client.get('/api/bootstrap', headers=IDENTITY))
                assert bootstrap.json()['mcp_access_token_set'] is True and 'mcp-token-0815' not in bootstrap.text
                assert store.load().mcp_access_token == 'mcp-token-0815'
                for bad in ({'url': 'http://n8n.test', 'key': 'k', 'mcp_access_token': 'x\ny'},
                            {'url': 'http://n8n.test', 'key': 'k', 'other': 'x'}):
                    assert (await put(bad)).status_code == 400
                assert store.load().mcp_access_token == 'mcp-token-0815'
                assert (await put({'url': 'http://172.30.33.10:5678', 'key': 'api-key-0815'})).status_code == 200
                assert store.load().mcp_access_token is None  # the whole set is replaced
                await put({'url': 'http://172.30.33.10:5678', 'key': 'api-key-0815', 'mcp_access_token': 'mcp-token-0815'})
                assert (await put({'url': None, 'key': None})).status_code == 200
                assert store.load().mcp_access_token is None and store.load().backend_url is None
