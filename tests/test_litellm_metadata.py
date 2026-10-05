"""Pure ASGI/MockTransport tests; no listener, real backend or child server."""
import json
import os
from pathlib import Path
import subprocess

import httpx
import pytest
from mcp_admin_core.products import TOOLS, ProductState, ProductStore
from mcp_admin_core.policy import authorize, Denied, filter_list
from mcp_admin_core.gateway import make_apps

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    'litellm_model_info': {'litellm_model_id': 'model-1'},
    'litellm_model_group_info': {'model_group': 'openai/gpt-4.1'},
    'litellm_team_info': {'team_id': 'team-1'},
    'litellm_list_users': {},
    'litellm_user_info': {'user_id': 'user-1'},
}
GOOD = list(CASES.items()) + [
    ('litellm_model_info', {'litellm_model_id': 'x'*128}),
    ('litellm_model_group_info', {'model_group': 'x'*256}),
    ('litellm_list_users', {'page': 10000, 'page_size': 100, 'role': 'proxy_admin_viewer',
                            'user_ids': ['u']*20, 'team': 't'*128,
                            'user_email': None, 'sort_by': None, 'sort_order': None}),
]
BAD = [(name, {**args, 'config': {}}) for name, args in CASES.items()] + [
    ('litellm_model_info', {}), ('litellm_model_info', {'litellm_model_id': None}),
    ('litellm_model_info', {'litellm_model_id': 'x'*129}),
    ('litellm_model_group_info', {}), ('litellm_model_group_info', {'model_group': 'x\n'}),
    ('litellm_team_info', {'team_id': ''}), ('litellm_user_info', {'user_id': 'a,b'}),
    ('litellm_team_info', {'team_id': 'x\n'}), ('litellm_user_info', {'user_id': 'x\n'}),
    ('litellm_list_users', {'user_ids': ['x\n']}),
    *[('litellm_list_users', value) for value in [
        {'page': True}, {'page': '1'}, {'page': 0}, {'page': 10001},
        {'page_size': 0}, {'page_size': 101}, {'user_ids': []}, {'user_ids': ['u']*21},
        {'user_email': 'private@example.test'}, {'sort_by': 'spend'},
        {'sort_order': 'desc'}, {'role': 'invented'}, {'team': 'x'*129},
    ]],
]

def call(name, args):
    return {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': args.copy()}}

def state():
    return ProductState(product='litellm', token='a'*43, child_token='b'*43,
                        connection={'url': 'http://backend.test', 'master_key': 'DUMMY'})

@pytest.mark.parametrize('name,args', GOOD)
def test_read_policy_and_public_schema(name, args):
    tool = TOOLS['litellm'][name]
    assert not tool.write and not tool.grants(name)
    message = call(name, args)
    authorize(message, TOOLS['litellm'], state())
    normalized = json.loads(json.dumps(message))
    authorize(message, TOOLS['litellm'], state())
    assert message == normalized
    listing = {'result': {'tools': [{'name': name, 'inputSchema': {}}]}}
    assert filter_list(listing, TOOLS['litellm'], state())['result']['tools'][0]['inputSchema'] == tool.arguments.model_json_schema()

@pytest.mark.parametrize('name,args', CASES.items())
def test_unconfigured_read_denied(name, args):
    unconfigured = ProductState(product='litellm', token='a'*43, child_token='b'*43)
    with pytest.raises(Denied):
        authorize(call(name, args), TOOLS['litellm'], unconfigured)


@pytest.mark.parametrize('name,args', BAD)
def test_invalid_policy(name, args):
    with pytest.raises(Denied):
        authorize(call(name, args), TOOLS['litellm'], state())

async def test_disabled_invalid_and_unsupported_zero_dispatch(tmp_path):
    calls = []
    def dispatch(request):
        calls.append(request)
        return httpx.Response(200, json={})
    store = ProductStore(tmp_path, 'litellm')
    try:
        store.update(connection=state().connection.model_dump(), writes_enabled=True)
        async with httpx.AsyncClient(transport=httpx.MockTransport(dispatch)) as child:
            _, app = make_apps(store, TOOLS['litellm'], child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://mcp.test') as client:
                headers = {'Authorization': 'Bearer '+store.load().token}
                for name, args in BAD:
                    assert (await client.post('/mcp', headers=headers, json=call(name, args))).status_code == 403
                for name in ('litellm_health', 'litellm_chat_completion', 'litellm_key_info', 'litellm_list_keys', 'litellm_create_user', 'litellm_spend_logs'):
                    assert (await client.post('/mcp', headers=headers, json=call(name, {}))).status_code == 403
                for name, args in CASES.items():
                    store.update(disabled=[name])
                    assert (await client.post('/mcp', headers=headers, json=call(name, args))).status_code == 403
        assert calls == []
    finally:
        store.close()


def test_actual_vendor_handlers_and_json_schema_in_isolated_child_environment():
    # Interpreter only, not an MCP child/server. Parent pytest owns shared lock.
    schemas = {name: TOOLS['litellm'][name].arguments.model_json_schema() for name in CASES}
    cases = [(name, args, True) for name, args in GOOD] + [(n,a,False) for n,a in BAD]
    result = subprocess.run([str(ROOT/'apps/litellm/.venv/bin/python'), str(ROOT/'tests/litellm_metadata_unit.py')],
        input=json.dumps({'schemas': schemas, 'cases': cases}), capture_output=True, text=True, timeout=45,
        env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1',
             'PYTHONPATH': os.pathsep.join([str(ROOT/'apps/litellm/vendor'), str(ROOT/'apps/runtime')]),
             'FASTMCP_CHECK_FOR_UPDATES': 'off', 'FASTMCP_SHOW_SERVER_BANNER': 'false'})
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stderr)
