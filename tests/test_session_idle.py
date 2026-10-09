"""0.1.8 (0.1.6 RC GATEWAY-3): the Python children end sessions a client leaves idle.

Real children (each in its pinned venv, started from products.child_spec on a private port, fake backends): a session
nobody uses is gone after the limit (the child answers 404, so MCP clients initialize again) while a session in use
stays. Unit checks run session_idle inside both pinned SDK flavours (mcp 1.28.1 FastMCP; FastMCP 3.4.5).
"""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import time

import pytest

from mcp_admin_core.health import protocol_reply
from mcp_admin_core.products import PRODUCTS, ProductStore, child_spec

from owned_runtime import Endpoint
from test_real_products import backend, connection

ROOT = Path(__file__).resolve().parents[1]
CHILDREN = [p for p in PRODUCTS if p != 'odoo-manage']  # retired: no image since 0.1.5
INIT = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
        'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'idle-test', 'version': '0'}}}

UNIT = r'''
import json, os, sys
import session_idle
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager as Manager
out = {}
try:
    out['limit'] = session_idle.install()
except ValueError as exc:
    print(json.dumps({'refused': str(exc)})); sys.exit(0)
out['again'] = session_idle.install()
out['default'] = Manager(app=object()).session_idle_timeout
out['explicit'] = Manager(app=object(), session_idle_timeout=5).session_idle_timeout
out['stateless'] = Manager(app=object(), stateless=True).session_idle_timeout
out['positional'] = Manager(object(), None, False, False).session_idle_timeout
if sys.argv[1] == 'fastmcp':
    from fastmcp.server.http import FastMCPStreamableHTTPSessionManager
    out['fastmcp'] = FastMCPStreamableHTTPSessionManager(app=object()).session_idle_timeout
else:
    from mcp.server.fastmcp import FastMCP
    server = FastMCP('t')
    server.streamable_http_app()
    out['fastmcp'] = server.session_manager.session_idle_timeout
print(json.dumps(out))
'''


def unit(venv, flavour, idle=None):
    env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'apps/runtime'), 'PYTHONDONTWRITEBYTECODE': '1'}
    if idle is not None:
        env['WOOW_MCP_SESSION_IDLE_SECONDS'] = idle
    done = subprocess.run([str(ROOT / 'apps' / venv / '.venv/bin/python'), '-c', UNIT, flavour], env=env,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.splitlines()[-1])


@pytest.mark.parametrize('venv,flavour', [('hermes', 'sdk'), ('emqx', 'fastmcp')])
def test_every_stateful_manager_gets_the_limit(venv, flavour):
    assert unit(venv, flavour) == {'limit': 1800.0, 'again': 1800.0, 'default': 1800.0, 'explicit': 5,
                                   'stateless': None, 'positional': 1800.0, 'fastmcp': 1800.0}
    assert unit(venv, flavour, '7')['fastmcp'] == 7.0


@pytest.mark.parametrize('value', ['0', '-1', 'abc', '100000', 'nan'])
def test_an_invalid_limit_refuses_to_start(value):
    assert 'refused' in unit('hermes', 'sdk', value)


def test_every_python_child_installs_it():
    for product in ('odoo', 'hermes', 'opendesign'):
        assert 'session_idle.install()' in (ROOT / 'apps' / product / 'launch.py').read_text()
    store_root = ROOT / 'packages/mcp-admin-core/mcp_admin_core/products.py'
    assert "'-m', 'run_child', module" in store_root.read_text()


async def post(client, url, headers, message):
    async with client.stream('POST', url, headers=headers, json=message) as response:
        if 'id' not in message or response.status_code != 200:
            await response.aread()
            return response.status_code, None, response.headers.get('mcp-session-id')
        return 200, await protocol_reply(response, message['id']), response.headers.get('mcp-session-id')


async def open_session(client, url):
    headers = {'Accept': 'application/json, text/event-stream'}
    status, result, session = await post(client, url, headers, INIT)
    assert status == 200 and session
    headers.update({'Mcp-Session-Id': session, 'MCP-Protocol-Version': result['protocolVersion']})
    await post(client, url, headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    status, listed, _ = await post(client, url, headers, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
    assert status == 200 and listed['tools']
    return headers


async def ping(client, url, headers):
    return (await post(client, url, headers, {'jsonrpc': '2.0', 'id': 3, 'method': 'ping'}))[0]


@pytest.mark.parametrize('product', CHILDREN)
async def test_real_child_ends_an_idle_session_and_keeps_an_active_one(tmp_path, product):
    idle = 2.0
    with backend(product) as (url, _calls, _offline):
        store = ProductStore(tmp_path / 'state', product)
        store.update(connection=connection(product, url))
        spec = child_spec(store.load(), store.directory)
        store.close()
        spec.env['WOOW_MCP_SESSION_IDLE_SECONDS'] = str(idle)  # the limit itself is 1800 s (unit test above)
        endpoint = Endpoint(product)
        manager = endpoint.supervisor(spec)
        try:
            await manager.start()
            async with endpoint.client(timeout=15) as client:
                started = time.monotonic()
                while True:
                    try:
                        left = await open_session(client, endpoint.url)
                        break
                    except Exception:
                        if time.monotonic() - started > 40:
                            raise
                        await asyncio.sleep(0.25)
                used = await open_session(client, endpoint.url)
                deadline = time.monotonic() + 2 * idle + 1
                while time.monotonic() < deadline:
                    assert await ping(client, endpoint.url, used) == 200
                    await asyncio.sleep(idle / 4)
                assert await ping(client, endpoint.url, left) == 404
                assert await ping(client, endpoint.url, used) == 200
        finally:
            await manager.stop()
            endpoint.close()
