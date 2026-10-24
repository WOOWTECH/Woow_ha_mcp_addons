"""0.4.0 (MCP SDK 2.3.0): a failed tool's text reaches the client as in mcp 1.x, in the SDK MCPServer children.

mcp 2.1 and later answer any exception but ToolError/ResourceError with only 'Error executing tool <name>'; the
children rely on the text (backend_policy's error codes, Hermes's input guards, BACKEND_BUSY, Odoo's readiness probe,
odoo-mcp's own errors). apps/runtime/tool_error_text.keep_error_text restores it. The unit checks run inside a pinned
SDK 2 child venv; the real children answer exactly what 0.3.4 (mcp 1.30.0) answered, measured 2026-10-25 against a
closed backend port with the 0.3.4 tree.
"""
import asyncio
from contextlib import closing
import json
from pathlib import Path
import subprocess

import httpx
import pytest

from mcp_admin_core.products import ProductStore, child_spec
from owned_runtime import Endpoint
from test_real_products import connection, free_port, rpc

ROOT = Path(__file__).resolve().parents[1]

UNIT = r'''
import asyncio, json, sys, tempfile
from pathlib import Path
import httpx
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.shared.exceptions import MCPError
import tool_error_text

def build():
    mcp = MCPServer('error-text')
    @mcp.tool()
    def sync_fail(x: int) -> str:
        raise ValueError(f'BACKEND_UNAVAILABLE: sync {x}')
    @mcp.tool()
    async def async_fail() -> str:
        raise httpx.ConnectError('BACKEND_UNAVAILABLE: async')
    @mcp.tool()
    def tool_error() -> str:
        raise ToolError('already a ToolError')
    @mcp.tool()
    def protocol_error() -> str:
        raise MCPError(-32602, 'a protocol error')
    @mcp.tool()
    async def cancelled() -> str:
        raise asyncio.CancelledError()
    @mcp.tool()
    def fine(x: int) -> int:
        return x + 1
    return mcp

async def answers(mcp):
    out = {}
    async with Client(mcp, mode='legacy') as client:
        for name, args in (('sync_fail', {'x': 1}), ('async_fail', {}), ('tool_error', {}), ('fine', {'x': 1}),
                           ('sync_fail', {'x': 'not a number'}), ('protocol_error', {})):
            key = name if name != 'sync_fail' or args['x'] == 1 else 'invalid_arguments'
            try:
                result = await client.call_tool(name, args)
                out[key] = {'is_error': result.is_error, 'text': [c.text for c in result.content if c.type == 'text']}
            except MCPError as exc:
                out[key] = {'mcp_error': exc.error.code, 'message': exc.error.message}
    try:
        await mcp.call_tool('cancelled', {})
    except asyncio.CancelledError:
        out['cancelled'] = 'CancelledError'
    except BaseException as exc:
        out['cancelled'] = type(exc).__name__
    return out

masked = build()
plain = asyncio.run(answers(masked))
kept = build()
schemas = {t.name: (t.parameters, t.is_async) for t in kept._tool_manager.list_tools()}
wrapped = tool_error_text.keep_error_text(kept)
again = tool_error_text.keep_error_text(kept)
after = {t.name: (t.parameters, t.is_async) for t in kept._tool_manager.list_tools()}
restored = asyncio.run(answers(kept))
from mcp.server.mcpserver.tools import base
copy = Path(tempfile.mkdtemp()) / 'base.py'
copy.write_bytes(Path(base.__file__).read_bytes() + b'\n')
base.__file__ = str(copy)
try:
    tool_error_text.keep_error_text(build())
    guard = 'accepted'
except RuntimeError as exc:
    guard = str(exc)
print(json.dumps({'plain': plain, 'restored': restored, 'wrapped': wrapped, 'again': again,
                  'unchanged': schemas == after, 'guard': guard}))
'''


def unit():
    env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'apps/runtime'), 'PYTHONDONTWRITEBYTECODE': '1'}
    done = subprocess.run([str(ROOT / 'apps/hermes/.venv/bin/python'), '-c', UNIT], env=env, capture_output=True,
                          text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.splitlines()[-1])


def test_keep_error_text_restores_the_1x_text_and_nothing_else():
    out = unit()
    # The premise: without it, the SDK 2 MCPServer hides every non-ToolError exception's text.
    assert out['plain']['sync_fail'] == {'is_error': True, 'text': ['Error executing tool sync_fail']}
    assert out['plain']['async_fail'] == {'is_error': True, 'text': ['Error executing tool async_fail']}
    restored = out['restored']
    assert restored['sync_fail'] == {'is_error': True, 'text': ['Error executing tool sync_fail: BACKEND_UNAVAILABLE: sync 1']}
    assert restored['async_fail'] == {'is_error': True, 'text': ['Error executing tool async_fail: BACKEND_UNAVAILABLE: async']}
    # A ToolError, an argument error, a protocol error, success and cancellation are what they were.
    for name in ('tool_error', 'invalid_arguments', 'protocol_error', 'fine', 'cancelled'):
        assert restored[name] == out['plain'][name], name
    assert restored['tool_error'] == {'is_error': True, 'text': ['Error executing tool tool_error: already a ToolError']}
    assert restored['fine'] == {'is_error': False, 'text': ['2']}
    assert restored['protocol_error'] == {'mcp_error': -32602, 'message': 'a protocol error'}
    assert restored['invalid_arguments']['text'][0].startswith('Error executing tool sync_fail: 1 validation error')
    assert restored['cancelled'] == 'CancelledError'
    assert out['wrapped'] == sorted(['async_fail', 'cancelled', 'fine', 'protocol_error', 'sync_fail', 'tool_error'])
    assert out['again'] == [] and out['unchanged'] is True  # idempotent; schemas and sync/async kept
    assert out['guard'] == 'SDK tool error handling requires source review'  # a changed tools/base.py fails closed


def test_the_mcpserver_children_apply_it():
    assert 'keep_error_text(mcp)' in (ROOT / 'apps/hermes/vendor/hermes_mcp_server/server.py').read_text()
    for product in ('odoo', 'opendesign'):
        launcher = (ROOT / 'apps' / product / 'launch.py').read_text()
        # After BoundedTools, so its BACKEND_BUSY keeps its text too.
        assert launcher.index('BoundedTools(mcp, capacity=') < launcher.index('keep_error_text(mcp)'), product


ACCEPT = {'Accept': 'application/json, text/event-stream'}
INIT = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
    'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'error-text', 'version': '0'}}}
# The texts 0.3.4 (mcp 1.30.0) answered with the same calls; the private probes are called as HealthMonitor does.
EXPECTED = {
    'hermes': [('hermes_chat', {'message': 'hi'}, 'Error executing tool hermes_chat: BACKEND_UNAVAILABLE: All connection attempts failed')],
    'opendesign': [('health', {}, 'Error executing tool health: BACKEND_UNAVAILABLE: BACKEND_CONNECT_FAILED'),
                   ('get_project', {'project_id': '12345678-1234-1234-1234-123456789abc'},
                    'Error executing tool get_project: BACKEND_UNAVAILABLE: BACKEND_CONNECT_FAILED')],
    'odoo': [('woow_backend_probe', {}, 'Error executing tool woow_backend_probe: BACKEND_UNAVAILABLE'),
             ('search_records', {'model': 'res.partner', 'limit': 'abc'},
              'Error executing tool search_records: 1 validation error for search_recordsArguments\nlimit\n  Input should '
              'be a valid integer, unable to parse string as an integer')],
}


@pytest.mark.parametrize('product', list(EXPECTED))
async def test_real_children_answer_the_1x_text(tmp_path, product):
    url = f'http://127.0.0.1:{free_port()}'  # nothing listens: every backend call fails to connect
    with closing(ProductStore(tmp_path / 'state', product)) as store:
        store.update(connection=connection(product, url))
        endpoint = Endpoint(product)
        process = endpoint.supervisor(child_spec(store.load(), store.directory))
        try:
            await process.start()
            async with endpoint.client() as child:
                headers = {'Authorization': 'Bearer ' + store.load().child_token, **ACCEPT}
                async with asyncio.timeout(25):
                    while True:
                        try:
                            init = await rpc(child, endpoint.url, headers, INIT)
                            break
                        except (ValueError, httpx.HTTPError):
                            await asyncio.sleep(.1)
                headers['MCP-Protocol-Version'] = init['protocolVersion']
                await rpc(child, endpoint.url, headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                for index, (name, arguments, expected) in enumerate(EXPECTED[product]):
                    result = await rpc(child, endpoint.url, headers, {'jsonrpc': '2.0', 'id': 10 + index,
                                                                      'method': 'tools/call',
                                                                      'params': {'name': name, 'arguments': arguments}})
                    [text] = [item['text'] for item in result['content'] if item['type'] == 'text']
                    assert result['isError'] is True and text.startswith(expected), (name, text)
                    assert text == expected or name == 'search_records', (name, text)
                await child.delete(endpoint.url, headers=headers)
        finally:
            await process.stop()
            endpoint.close()
