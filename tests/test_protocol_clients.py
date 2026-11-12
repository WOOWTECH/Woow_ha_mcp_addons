"""0.4.0 (MCP SDK 2.3.0 children, issue #21): clients stay in the 2025 handshake era through the gateway, and the
clients in use before still connect, list and call end to end.

Real gateway on an owned port, real children with fake backends: Odoo (SDK MCPServer, odoo-mcp 1.3.0) and EMQX
(FastMCP 4.1.3). Clients: raw JSON-RPC at each reviewed revision; the Python MCP SDK 1.30 client (the archived Odoo
Manage venv's pinned SDK); the MCP TypeScript SDK 1.32 client (n8n-mcp's pinned override, the library of n8n-style
clients); the Python MCP SDK 2.3 client, whose default mode sends server/discover (2026-07-28) first and falls back to
initialize when the gateway answers it with JSON-RPC -32601 (0.1.13, before any session, slot or child).

An SDK 2 child sends any request whose MCP-Protocol-Version header is not a handshake revision to its 2026-07-28
handling, which refuses an initialize (mcp 1.x ignored the header there): the gateway no longer forwards the header
with an initialize, so a client that keeps its server/discover header still connects; a 2026-07-28 request inside a
session fails as such a header did with mcp 1.x.
"""
import asyncio
from contextlib import asynccontextmanager, closing
import json
import os
from pathlib import Path
import subprocess

import httpx
import pytest

from mcp_admin_core.gateway import PROTOCOL_VERSIONS, make_apps
from mcp_admin_core.products import PROBES, ProductStore, TOOLS, child_spec, probe_success
from owned_runtime import Endpoint
from test_active_token_leases import listen
from test_real_products import backend, connection, rpc

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ('odoo', 'emqx')
ACCEPT = {'Accept': 'application/json, text/event-stream'}
MODERN = '2026-07-28'


def initialize(version):
    return {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
        'protocolVersion': version, 'capabilities': {}, 'clientInfo': {'name': 'protocol-clients', 'version': '0'}}}


@asynccontextmanager
async def served(tmp_path, product):
    """The real child behind the real gateway, served on an owned port: (gateway URL, add-on token, child)."""
    with backend(product) as (url, _calls, _offline), closing(ProductStore(tmp_path / 'state', product)) as store:
        store.update(connection=connection(product, url))
        endpoint = Endpoint(product)
        manager = endpoint.supervisor(child_spec(store.load(), store.directory))
        try:
            await manager.start()
            async with endpoint.client(timeout=15) as child:
                _, app = make_apps(store, TOOLS[product], child, child_url=endpoint.url)
                async with listen(app) as base:
                    token = store.load().token
                    async with httpx.AsyncClient(timeout=15) as client:
                        headers = {'Authorization': 'Bearer ' + token, **ACCEPT}
                        for _ in range(100):  # until the child answers through the gateway
                            try:
                                await rpc(client, base + '/mcp', dict(headers), initialize('2025-11-25'))
                                break
                            except (httpx.HTTPError, ValueError):
                                await asyncio.sleep(.1)
                        else:
                            raise AssertionError('child not ready')
                    yield base + '/mcp', token, (endpoint, store.load().child_token)
        finally:
            await manager.stop()
            endpoint.close()


def succeeded(product, texts):
    [text] = texts
    return probe_success(product, json.loads(text))


@pytest.mark.parametrize('product', PRODUCTS)
async def test_raw_json_rpc_at_every_reviewed_revision(tmp_path, product):
    name, arguments = PROBES[product]
    async with served(tmp_path, product) as (url, token, _):
        async with httpx.AsyncClient(timeout=15) as client:
            for version in sorted(PROTOCOL_VERSIONS):
                headers = {'Authorization': 'Bearer ' + token, **ACCEPT}
                result = await rpc(client, url, headers, initialize(version))
                assert result['protocolVersion'] == version and headers.get('Mcp-Session-Id')
                headers['MCP-Protocol-Version'] = version
                await rpc(client, url, headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                listed = await rpc(client, url, headers, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
                assert name in {tool['name'] for tool in listed['tools']}
                called = await rpc(client, url, headers, {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                                                          'params': {'name': name, 'arguments': arguments}})
                assert called.get('isError') is not True
                assert succeeded(product, [c['text'] for c in called['content'] if c['type'] == 'text']), called
                assert (await client.delete(url, headers=headers)).status_code in (200, 204)


@pytest.mark.parametrize('product', PRODUCTS)
async def test_server_discover_gets_a_clean_error_and_the_2026_era_never_reaches_a_child(tmp_path, product):
    discover = {'jsonrpc': '2.0', 'id': 0, 'method': 'server/discover', 'params': {'_meta': {
        'io.modelcontextprotocol/clientCapabilities': {}, 'io.modelcontextprotocol/protocolVersion': MODERN,
        'io.modelcontextprotocol/clientInfo': {'name': 'probe', 'version': '0'}}}}
    async with served(tmp_path, product) as (url, token, (endpoint, child_token)):
        async with httpx.AsyncClient(timeout=15) as client:
            auth = {'Authorization': 'Bearer ' + token, **ACCEPT}
            for headers in ({**auth, 'MCP-Protocol-Version': MODERN, 'Mcp-Method': 'server/discover'}, auth):
                answer = await client.post(url, headers=headers, json=discover)
                assert answer.status_code == 200 and 'mcp-session-id' not in answer.headers
                assert answer.json() == {'jsonrpc': '2.0', 'id': 0, 'error': {'code': -32601, 'message': 'Method not found'}}
            # The premise: an SDK 2 child itself refuses an initialize that carries a 2026-07-28 header (HTTP 400).
            async with endpoint.client() as direct:
                refused = await direct.post(endpoint.url, json=initialize('2025-11-25'), headers={
                    'Authorization': 'Bearer ' + child_token, **ACCEPT, 'MCP-Protocol-Version': MODERN})
                assert refused.status_code == 400 and 'mcp-session-id' not in refused.headers
            # Through the gateway the header never reaches the child with an initialize: the handshake works.
            headers = {**auth, 'MCP-Protocol-Version': MODERN}
            result = await rpc(client, url, headers, initialize('2025-11-25'))
            assert result['protocolVersion'] == '2025-11-25' and headers.get('Mcp-Session-Id')
            # A 2026-07-28 request inside that session fails, as an unsupported header did with mcp 1.x (400).
            answer = await client.post(url, headers=headers, json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
            assert answer.status_code == 400 and 'tools' not in answer.text
            headers['MCP-Protocol-Version'] = '2025-11-25'
            listed = await rpc(client, url, headers, {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'})
            assert listed['tools']


PYTHON_1 = r'''
import asyncio, json, os
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
async def main():
    headers = {'Authorization': 'Bearer ' + os.environ['WOOW_TOKEN']}
    async with streamablehttp_client(os.environ['WOOW_URL'], headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            listed = await session.list_tools()
            result = await session.call_tool(os.environ['WOOW_TOOL'], json.loads(os.environ['WOOW_ARGS']))
    print(json.dumps({'protocol': init.protocolVersion, 'tools': [t.name for t in listed.tools], 'is_error': result.isError,
                      'text': [c.text for c in result.content if c.type == 'text']}))
asyncio.run(main())
'''

PYTHON_2 = r'''
import asyncio, json, os
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
async def main():
    async with httpx2.AsyncClient(headers={'Authorization': 'Bearer ' + os.environ['WOOW_TOKEN']}) as http:
        async with Client(streamable_http_client(os.environ['WOOW_URL'], http_client=http)) as client:  # mode='auto'
            listed = await client.list_tools()
            result = await client.call_tool(os.environ['WOOW_TOOL'], json.loads(os.environ['WOOW_ARGS']))
            out = {'protocol': client.protocol_version, 'discovered': client.session.discover_result is not None,
                   'tools': [t.name for t in listed.tools], 'is_error': result.is_error,
                   'text': [c.text for c in result.content if c.type == 'text']}
    print(json.dumps(out))
asyncio.run(main())
'''

TYPESCRIPT = r'''
const sdk = process.env.WOOW_SDK;
const { Client } = require(sdk + '/dist/cjs/client/index.js');
const { StreamableHTTPClientTransport } = require(sdk + '/dist/cjs/client/streamableHttp.js');
(async () => {
  const transport = new StreamableHTTPClientTransport(new URL(process.env.WOOW_URL),
    { requestInit: { headers: { Authorization: 'Bearer ' + process.env.WOOW_TOKEN } } });
  const client = new Client({ name: 'protocol-clients-ts', version: '0' });
  await client.connect(transport);
  const listed = await client.listTools();
  const result = await client.callTool({ name: process.env.WOOW_TOOL, arguments: JSON.parse(process.env.WOOW_ARGS) });
  const out = { protocol: transport.protocolVersion, tools: listed.tools.map(t => t.name), is_error: Boolean(result.isError),
                text: result.content.filter(c => c.type === 'text').map(c => c.text) };
  await transport.terminateSession();
  await client.close();
  console.log(JSON.stringify(out));
})().catch(error => { console.error(error); process.exit(1); });
'''

CLIENTS = {
    'python-mcp-1.30': (lambda: [str(ROOT / 'apps/odoo-manage/.venv/bin/python'), '-c', PYTHON_1], '1.30.0'),
    'python-mcp-2.3': (lambda: [str(ROOT / 'apps/hermes/.venv/bin/python'), '-c', PYTHON_2], '2.3.0'),
    'typescript-sdk-1.32': (lambda: ['node', '-e', TYPESCRIPT], '1.32.2'),
}
SDK = ROOT / 'apps/n8n/node_modules/@modelcontextprotocol/sdk'


def installed(client):
    if client == 'typescript-sdk-1.32':
        return json.loads((SDK / 'package.json').read_text())['version']
    venv = 'odoo-manage' if client == 'python-mcp-1.30' else 'hermes'
    [info] = (ROOT / 'apps' / venv / '.venv/lib/python3.13/site-packages').glob('mcp-*.dist-info')
    return info.name[len('mcp-'):-len('.dist-info')]


@pytest.mark.parametrize('client', list(CLIENTS))
@pytest.mark.parametrize('product', PRODUCTS)
async def test_sdk_clients_connect_list_and_call_through_the_gateway(tmp_path, product, client):
    argv, version = CLIENTS[client]
    assert installed(client) == version  # the client library this test is about
    name, arguments = PROBES[product]
    async with served(tmp_path, product) as (url, token, _):
        env = {'PATH': os.environ['PATH'], 'HOME': str(tmp_path), 'PYTHONDONTWRITEBYTECODE': '1', 'WOOW_URL': url,
               'WOOW_TOKEN': token, 'WOOW_TOOL': name, 'WOOW_ARGS': json.dumps(arguments), 'WOOW_SDK': str(SDK)}
        done = await asyncio.to_thread(subprocess.run, argv(), env=env, cwd=tmp_path, capture_output=True, text=True,
                                       timeout=90)
    assert done.returncode == 0, done.stderr[-3000:]
    out = json.loads(done.stdout.splitlines()[-1])
    assert out['protocol'] == '2025-11-25'  # every client lands on the newest handshake revision
    assert out.get('discovered', False) is False  # the 2.3 client fell back from server/discover to initialize
    assert name in out['tools'] and len(out['tools']) == len(TOOLS[product])
    assert out['is_error'] is False and succeeded(product, out['text']), out
