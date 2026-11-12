"""0.1.8 (0.1.6 RC GATEWAY-3): the Python children end sessions a client leaves idle.

Real children (each in its pinned venv, started from products.child_spec on a private port, fake backends): a session
nobody uses is gone after the limit (the child answers 404, so MCP clients initialize again) while a session in use
stays. Unit checks run session_idle inside both pinned SDK flavours (0.4.0: mcp 2.3.0 MCPServer; FastMCP 4.1.3); since
0.3.4 the SDK has its own 30-minute default, which MCPServer (FastMCP in mcp 1.30.0) passes explicitly, and the add-on's
limit still replaces it; its 4 MiB request body limit becomes the gateway's 16 MiB (a real child takes a body just under
it).
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

import pytest

from mcp_admin_core import gateway
from mcp_admin_core.health import protocol_reply
from mcp_admin_core.products import PRODUCTS, ProductStore, child_spec

from owned_runtime import Endpoint
from test_real_products import backend, connection

ROOT = Path(__file__).resolve().parents[1]
CHILDREN = [p for p in PRODUCTS if p != 'odoo-manage']  # retired: no image since 0.1.5
BODY = 16 * 1024 * 1024  # 0.3.4: the request body every Python child accepts (the gateway's MAX_REQUEST)
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
# 0.3.4 (mcp 1.30.0): the request body limit (SDK default 4 MiB) becomes the gateway's MAX_REQUEST unless set otherwise.
out['body'] = Manager(app=object()).max_request_body_size
out['body_explicit'] = Manager(app=object(), max_request_body_size=1024).max_request_body_size
out['body_stateless'] = Manager(app=object(), stateless=True).max_request_body_size
if sys.argv[1] == 'fastmcp':
    from fastmcp.server.http import FastMCPStreamableHTTPSessionManager
    manager = FastMCPStreamableHTTPSessionManager(app=object())
else:
    # 0.4.0 (mcp 2.3.0): mcp 1.x's FastMCP is MCPServer; it passes the SDK defaults to the manager explicitly.
    from mcp.server.mcpserver import MCPServer
    server = MCPServer('t')
    server.streamable_http_app()
    manager = server.session_manager
out['fastmcp'] = manager.session_idle_timeout
out['fastmcp_body'] = manager.max_request_body_size
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
    # 0.3.4 (mcp 1.30.0): a stateless manager keeps the SDK's own default (1800 s, unused without sessions; 1.28.1 had
    # None) whatever the limit is, and the SDK's FastMCP, which passes that default explicitly, still gets the limit.
    body = {'body': BODY, 'body_explicit': 1024, 'body_stateless': BODY, 'fastmcp_body': BODY}
    assert unit(venv, flavour) == {'limit': 1800.0, 'again': 1800.0, 'default': 1800.0, 'explicit': 5,
                                   'stateless': 1800, 'positional': 1800.0, 'fastmcp': 1800.0, **body}
    assert unit(venv, flavour, '7') == {'limit': 7.0, 'again': 7.0, 'default': 7.0, 'explicit': 5,
                                        'stateless': 1800, 'positional': 7.0, 'fastmcp': 7.0, **body}


def test_the_childs_body_limit_is_the_gateways():
    # 0.3.4: mcp 1.30.0 refuses a body over its max_request_body_size (4 MiB by default) with 413; the gateway admits up
    # to MAX_REQUEST (0.2.0: 16 MiB, Nextcloud uploads up to 10 MiB as base64); session_idle gives the children that.
    spec = importlib.util.spec_from_file_location('session_idle_module', ROOT / 'apps/runtime/session_idle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.BODY_BYTES == BODY == gateway.MAX_REQUEST


@pytest.mark.parametrize('value', ['0', '-1', 'abc', '100000', 'nan'])
def test_an_invalid_limit_refuses_to_start(value):
    assert 'refused' in unit('hermes', 'sdk', value)


BOOTSTRAP = ROOT / 'tests/owned_bootstrap'  # the test network sentinel every test subprocess loads as sitecustomize
SDK_WITHOUT_IDLE = """import runpy
runpy.run_path(%r)  # keep the sentinel: this file shadows its sitecustomize
import mcp.server.streamable_http_manager as m
original = m.StreamableHTTPSessionManager.__init__
def __init__(self, app, event_store=None, json_response=False, stateless=False, security_settings=None, retry_interval=None):
    original(self, app, event_store, json_response, stateless, security_settings, retry_interval)
m.StreamableHTTPSessionManager.__init__ = __init__
""" % str(BOOTSTRAP / 'sitecustomize.py')


def child(product, tmp_path):
    with backend(product) as (url, _calls, _offline):
        store = ProductStore(tmp_path / ('state-' + product), product)
        store.update(connection=connection(product, url))
        spec = child_spec(store.load(), store.directory)
        store.close()
    return spec


def start(spec, **env):
    """Run a child as the add-on starts it, expecting it to refuse before it serves (bounded: a child that does start
    is killed by the timeout and fails the test)."""
    return subprocess.run(list(spec.argv), env={**spec.env, **env}, cwd=spec.cwd, capture_output=True, text=True,
                          timeout=60)


@pytest.mark.parametrize('product', ['hermes', 'emqx'])  # one launch.py child, one run_child child
def test_a_child_whose_sdk_has_no_idle_parameter_refuses_to_start(tmp_path, product):
    # 0.1.8 review F-5b: session_idle.install() fails closed when the pinned SDK lacks session_idle_timeout.
    shim = tmp_path / 'shim'
    shim.mkdir()
    (shim / 'sitecustomize.py').write_text(SDK_WITHOUT_IDLE)  # imported at startup: the SDK as an older version
    spec = child(product, tmp_path)
    # First on the path, before the sentinel's directory (which the test harness then leaves in place).
    done = start(spec, PYTHONPATH=f'{shim}:{BOOTSTRAP}:{spec.env["PYTHONPATH"]}')
    assert done.returncode != 0 and 'pinned MCP SDK without session_idle_timeout' in done.stderr, done.stderr[-2000:]
    assert 'Uvicorn running' not in done.stderr + done.stdout


@pytest.mark.parametrize('value', ['0', 'abc'])
def test_a_child_with_an_invalid_limit_refuses_to_start(tmp_path, value):
    spec = child('emqx', tmp_path)
    done = start(spec, WOOW_MCP_SESSION_IDLE_SECONDS=value)
    assert done.returncode != 0 and 'ValueError' in done.stderr, done.stderr[-2000:]
    assert 'Uvicorn running' not in done.stderr + done.stdout


@pytest.mark.parametrize('argv', [[], ['os'], ['marker_module'], ['emqx_mcp_server']])
def test_run_child_refuses_any_other_module(tmp_path, argv):
    # 0.1.8 review F-5b: only the three vendored FastMCP modules; anything else exits before it is imported.
    (tmp_path / 'marker_module.py').write_text(
        'import pathlib\npathlib.Path(%r).write_text("imported")\n' % str(tmp_path / 'imported'))
    env = {'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1',
           'PYTHONPATH': f'{tmp_path}:{ROOT / "apps/emqx/vendor"}:{ROOT / "apps/runtime"}'}
    done = subprocess.run([str(ROOT / 'apps/emqx/.venv/bin/python'), '-m', 'run_child', *argv], env=env, cwd=tmp_path,
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 1 and 'run_child: unknown child module' in done.stderr, (done.returncode, done.stderr)
    assert not (tmp_path / 'imported').exists()


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
    idle = 4.0  # the measured value (review F-5c): a slow ping must not let the used session expire
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
                # 0.3.4: a body just under the gateway's MAX_REQUEST still reaches the child (mcp 1.30.0 alone: 413).
                padding = 'A' * (BODY - 4096)
                big = {'jsonrpc': '2.0', 'id': 4, 'method': 'ping', 'params': {'_meta': {'padding': padding}}}
                assert len(json.dumps(big)) < BODY
                assert (await post(client, endpoint.url, used, big))[0] == 200
        finally:
            await manager.stop()
            endpoint.close()
