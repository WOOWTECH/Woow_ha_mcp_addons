"""The pinned wheel text and the child overlay's all-on listing match their actual Odoo write gates.

The pinned HA wheel retains the earlier direct-write text patch. The source-guarded child overlay applies the PaaS
#89 gate decisions and their descriptions before launch; its all-on listing is also the offline snapshot. The four
saved child switches are exercised separately against a synthetic XML-RPC backend.
"""
import asyncio
from contextlib import closing
import json
from pathlib import Path
import subprocess

import httpx
import pytest

from mcp_admin_core.products import ProductStore, child_spec
from mcp_admin_core.odoo_write_gates import METHOD_TEXT_ALL_ON
from mcp_admin_core.tool_snapshot import LISTED
from owned_runtime import Endpoint
from test_expansion_runtime import fake_api
from test_real_products import connection, rpc

ROOT = Path(__file__).resolve().parents[1]
DIRECT_METHOD = METHOD_TEXT_ALL_ON  # The child overlay's all-on text, also used by the offline snapshot.
PATCHED_METHOD = ("Odoo model method to call; create, write and unlink run directly in this deployment "
                  "(ODOO_MCP_ALLOW_DIRECT_WRITES is set), without the preview_write -> validate_write -> "
                  "execute_approved_write flow; the Odoo user's own access rights still apply.")
DIRECT_CHATTER = ("Post a chatter message on a mail.thread record. Direct mode is on in this deployment "
                  "(MCP_CHATTER_DIRECT): the first call posts the message at once; there is no preview and no "
                  "approval token.")
UPSTREAM_METHOD = "Odoo model method to call; direct create, write, and unlink are blocked."
UPSTREAM_CHATTER = ("Post a chatter message on a mail.thread record. Default mode requires an approval token returned "
                    "from a preview call; set MCP_CHATTER_DIRECT=1 to bypass and post immediately.")


def texts(tools):
    by_name = {tool['name']: tool for tool in tools}
    return (by_name['execute_method']['inputSchema']['properties']['method']['description'],
            by_name['chatter_post']['description'])


def test_the_child_runs_with_both_switches_on(tmp_path):
    with closing(ProductStore(tmp_path / 'state', 'odoo')) as store:
        store.update(connection=connection('odoo', 'http://127.0.0.1:9999'))
        spec = child_spec(store.load(), store.directory)
    assert spec.env['ODOO_MCP_ALLOW_DIRECT_WRITES'] == '1' and spec.env['MCP_CHATTER_DIRECT'] == '1'


def test_the_listing_the_gateway_ships_states_the_direct_mode():
    # tool_snapshot.py is what the gateway lists when no child answers; tests/test_tool_snapshot.py keeps it equal to the
    # real child's listing and to what the gateway relays from it.
    method, chatter = texts(LISTED['odoo'])
    assert (method, chatter) == (DIRECT_METHOD, DIRECT_CHATTER)
    for text in (method, chatter):
        assert 'blocked' not in text and 'requires an approval token' not in text


@pytest.mark.parametrize('switches', ['on', 'off'])
def test_the_patched_text_follows_the_switches_the_code_reads(switches):
    env = {'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'}
    if switches == 'on':
        env.update(ODOO_MCP_ALLOW_DIRECT_WRITES='1', MCP_CHATTER_DIRECT='1')
    code = ('import json\nfrom odoo_mcp.server import mcp\nfrom odoo_mcp.write_policy import chatter_direct_enabled\n'
            't = mcp._tool_manager\n'
            "print(json.dumps([t.get_tool('execute_method').parameters['properties']['method']['description'],"
            " t.get_tool('chatter_post').description, chatter_direct_enabled()]))\n")
    done = subprocess.run([str(ROOT / 'apps/odoo/.venv/bin/python'), '-c', code], env=env, capture_output=True,
                          text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    method, chatter, direct_chatter = json.loads(done.stdout.splitlines()[-1])
    expected = (PATCHED_METHOD, DIRECT_CHATTER, True) if switches == 'on' else (UPSTREAM_METHOD, UPSTREAM_CHATTER, False)
    assert (method, chatter, direct_chatter) == expected


async def test_the_real_child_lists_the_direct_mode_text(tmp_path):
    with fake_api() as (url, _events, mutations, _failures), closing(ProductStore(tmp_path / 'state', 'odoo')) as store:
        store.update(connection=connection('odoo', url))
        endpoint = Endpoint('odoo')
        process = endpoint.supervisor(child_spec(store.load(), store.directory))
        try:
            await process.start()
            async with endpoint.client() as child:
                headers = {'Authorization': 'Bearer ' + store.load().child_token,
                           'Accept': 'application/json, text/event-stream'}
                init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                    'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'texts', 'version': '0'}}}
                async with asyncio.timeout(25):
                    while True:
                        try:
                            result = await rpc(child, endpoint.url, headers, init)
                            break
                        except (ValueError, httpx.HTTPError):
                            await asyncio.sleep(.1)
                headers['MCP-Protocol-Version'] = result['protocolVersion']
                await rpc(child, endpoint.url, headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                listed = await rpc(child, endpoint.url, headers, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
                await child.delete(endpoint.url, headers=headers)
        finally:
            await process.stop()
            endpoint.close()
    assert texts(listed['tools']) == (DIRECT_METHOD, DIRECT_CHATTER)
    assert mutations == []  # listing writes nothing
