"""HM-01: the owned test doubles take the child's production port as a parameter and carry the child bearer.

- owned_network refuses 3000 (the default profile's child) and 18000-18099 (the extra profiles' children in the
  multi-profile plan) before any socket operation, in this process, in spawned Python and in Node.
- owned_runtime.private_spec / Endpoint and owned_child replace a given production port (default 3000) with the
  private one; nothing else in the production spec changes.
- Endpoint.client() sends the child bearer on every request that names no Authorization itself: the supervised
  spec's own (n8n AUTH_TOKEN; WOOW_MCP_CHILD_TOKEN for the Python children from HM-06), else one synthetic value per
  endpoint. The real children of bb48449 are run with it below: the Python ones ignore the extra header today, n8n
  requires exactly this value.
"""
import asyncio
from contextlib import closing, nullcontext
from dataclasses import replace
import re
import subprocess
import sys
import time
import types

import httpx
import pytest

from batch2_owned_port import OwnershipError, reserve_port
from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core.health import protocol_reply
from mcp_admin_core.lifecycle import ChildSpec
from mcp_admin_core.products import ProductStore, child_spec
from n8n_adapter import child_spec as n8n_spec
import owned_network
import owned_runtime
from test_real_products import backend, connection

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan

PRODUCTS = ('odoo', 'n8n', 'hermes', 'opendesign', 'emqx', 'litellm', 'nextcloud', 'headscale')
ACCEPT = {'Accept': 'application/json, text/event-stream'}
INIT = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
    'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'owned-bearer', 'version': '0'}}}
TOKEN = re.compile(r'[A-Za-z0-9_-]{43}')


@pytest.mark.parametrize('port, forbidden', [
    (3000, True), ('3000', True), (b'3000', True), (bytearray(b'18001'), True), (18000, True), ('18050', True),
    (18099, True), (' 18099', True), ('+18000', True), (b' +3000', True), ('018042', True),
    (2999, False), (3001, False), (17999, False), (18100, False), (0, False), (None, False), ('http', False),
    (True, False), (3000.0, False), ('18000.0', False), ('0x4650', False), ('-18000', False)])
def test_forbidden_ports(port, forbidden):
    """As getaddrinfo reads a port (strtoul: blanks, one '+', leading zeros); a float or hex text is no port there."""
    assert owned_network.forbidden_port(port) is forbidden


@pytest.mark.parametrize('address', [('127.0.0.1', 18000), ('::1', 18099, 0, 0), ('::ffff:127.0.0.1', '18042'),
                                     ('localhost', 3000)])
def test_python_sentinel_refuses_before_the_operation(address):
    calls = []
    for event in ('socket.bind', 'socket.connect'):
        with pytest.raises(OwnershipError):
            owned_network.audit(event, (object(), address))
            calls.append(event)
    with pytest.raises(OwnershipError):
        owned_network.audit('socket.getaddrinfo', (address[0], address[1], 0, 0, 0, 0))
        calls.append('getaddrinfo')
    assert calls == []
    owned_network.audit('socket.connect', (object(), ('127.0.0.1', 18100)))
    owned_network.audit('socket.connect', (object(), ('127.0.0.1', 17999)))


def test_spawned_python_sentinel_refuses_profile_child_ports():
    code = '''import sys
calls = []
for port in (18000, 18099, '18042'):
    try:
        sys.audit('socket.connect', object(), ('localhost', port))
        calls.append(port)
    except RuntimeError:
        pass
sys.audit('socket.connect', object(), ('localhost', 18100))
assert not calls, calls
print('guarded')
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=5,
                            env={'PATH': '/usr/bin:/bin'})
    assert result.returncode == 0 and result.stdout.strip() == 'guarded', result.stderr


def test_node_guard_refuses_profile_child_ports():
    preload = owned_network.HERE / 'owned_network.cjs'
    code = r'''
const assert = require('node:assert/strict'), net = require('node:net');
let calls = 0;
net.Socket.prototype.connect = function () { calls++; };
net.Server.prototype.listen = function () { calls++; };
delete require.cache[require.resolve(process.argv[1])];
require(process.argv[1]);
// Node reads a port with unary + (validatePort): ' 18000.0 ' and '0x4650' are port 18000 there.
for (const args of [[18000, '127.0.0.1'], [{port: 18099, host: '::1'}], ['18042', 'localhost'], [3000],
                    [' 18000.0 ', '127.0.0.1'], [{port: '0x4650'}], [[{port: 18001}, null]]]) {
  assert.throws(() => new net.Socket().connect(...args), /production port/);
  assert.throws(() => net.createServer().listen(...args), /production port/);
}
assert.equal(calls, 0);
new net.Socket().connect(18100, '127.0.0.1');
net.createServer().listen(17999, '127.0.0.1');
net.createServer().listen('/nonexistent/owned-network.sock');  // a Unix socket path has no port
new net.Socket().connect({path: '/nonexistent/owned-network.sock'});
assert.equal(calls, 4);
'''
    result = subprocess.run(['node', '-e', code, str(preload)], capture_output=True, text=True, timeout=5,
                            env={'PATH': '/usr/bin:/bin'})
    assert result.returncode == 0, result.stderr


def production_spec(product, directory):
    """The actual production ChildSpec of a configured product (n8n: its own adapter, which needs no backend)."""
    store = ProductStore(directory, product)
    try:
        if product == 'n8n':
            return n8n_spec(store.load(), store.directory)
        store.update(connection=connection(product, 'http://127.0.0.1:43210'))
        return child_spec(store.load(), store.directory)
    finally:
        store.close()


def moved(spec, product, port):
    """The same spec on another production port, as an extra profile's child (HM-04) will be launched."""
    if product == 'n8n':
        return replace(spec, env={**spec.env, 'PORT': str(port)})
    if '--port' in spec.argv:
        argv = list(spec.argv)
        argv[argv.index('--port') + 1] = str(port)
        return replace(spec, argv=tuple(argv))
    return spec  # Hermes and OpenDesign: the port is the launcher's run() argument (owned_child)


@pytest.mark.parametrize('product', PRODUCTS)
def test_private_spec_replaces_the_given_production_port_only(tmp_path, product):
    spec = production_spec(product, tmp_path / 'state')
    with closing(reserve_port()) as reservation:
        port = reservation.getsockname()[1]
    default = owned_runtime.private_spec(spec, product, port)
    explicit = owned_runtime.private_spec(spec, product, port, production_port=3000)
    assert default == explicit
    other = moved(spec, product, 18005)
    result = owned_runtime.private_spec(other, product, port, production_port=18005)
    assert result.cwd == other.cwd
    if product in ('hermes', 'opendesign'):
        assert default.argv == (spec.argv[0], str(owned_runtime.HERE / 'owned_child.py'), product, str(port),
                                *spec.argv[1:])
        assert result.argv == (other.argv[0], str(owned_runtime.HERE / 'owned_child.py'), product, str(port),
                               '--production-port=18005', *other.argv[1:])
        assert result.env == other.env
    else:
        assert result == moved(other, product, port) and default == moved(spec, product, port)
        with pytest.raises(AssertionError):
            owned_runtime.private_spec(other, product, port)  # the spec is not on the port the test expects
    for private in (3000, 18000, 18099):
        with pytest.raises(AssertionError):
            owned_runtime.private_spec(spec, product, private)
    with pytest.raises(AssertionError):
        owned_runtime.private_spec(spec, product, port, production_port=8081)  # not a child production port


def test_endpoint_refuses_production_ports():
    for port in (3000, 18000, 18099):
        with pytest.raises(OwnershipError):
            owned_runtime.Endpoint(port=port)
    for production in (8081, 17999, 18100, 18005.0, '18005', True):  # only 3000 and 18000-18099, as int
        with pytest.raises(OwnershipError):
            owned_runtime.Endpoint(production_port=production)
    endpoint = owned_runtime.Endpoint(production_port=18005)
    try:
        assert endpoint.production_port == 18005 and not owned_network.forbidden_port(endpoint.port)
    finally:
        endpoint.close()


class FakeServer:
    """mcp.server.mcpserver.MCPServer for owned_child in this process: records the run() it finally gets."""
    runs = []

    def run(self, **kwargs):
        self.runs.append(kwargs)


def run_owned_child(monkeypatch, argv):
    import owned_child
    package = types.ModuleType('mcp.server.mcpserver')
    package.MCPServer = type('MCPServer', (FakeServer,), {})
    monkeypatch.setitem(sys.modules, 'mcp', types.ModuleType('mcp'))
    monkeypatch.setitem(sys.modules, 'mcp.server', types.ModuleType('mcp.server'))
    monkeypatch.setitem(sys.modules, 'mcp.server.mcpserver', package)
    monkeypatch.setattr(sys, 'argv', ['owned_child.py', *argv])
    FakeServer.runs = []
    owned_child.main()
    return FakeServer.runs


def launcher(port):
    return ("from mcp.server.mcpserver import MCPServer\n"
            f"MCPServer().run(transport='streamable-http', host='127.0.0.1', port={port}, "
            "streamable_http_path='/mcp')\n")


def test_owned_child_moves_the_launchers_production_port(monkeypatch):
    run = {'transport': 'streamable-http', 'host': '127.0.0.1', 'streamable_http_path': '/mcp'}
    assert run_owned_child(monkeypatch, ['hermes', '43210', '-c', launcher(3000), 'x']) == [{**run, 'port': 43210}]
    assert run_owned_child(monkeypatch, ['opendesign', '43211', '--production-port=18005', '-c', launcher(18005),
                                         'x']) == [{**run, 'port': 43211}]
    for argv in (['hermes', '43210', '-c', launcher(18005), 'x'],                    # not the expected port
                 ['hermes', '43210', '--production-port=18005', '-c', launcher(3000), 'x'],
                 ['hermes', '18001', '-c', launcher(3000), 'x'],                     # a production port as private
                 ['hermes', '43210', '--production-port=8081', '-c', launcher(8081), 'x']):  # not a child port
        with pytest.raises(AssertionError):
            run_owned_child(monkeypatch, argv)


async def sent_authorization(endpoint, client, **kwargs):
    """The Authorization values a request of this client carries when it is sent: the client's request hooks after
    the ownership guard (which needs a live child) run on it, as httpx runs them just before sending."""
    hooks = client.event_hooks['request']
    assert hooks[0] == endpoint.guard  # the guard still runs first
    request = client.build_request('POST', endpoint.url, **kwargs)
    for hook in hooks[1:]:
        await hook(request)
    return request.headers.get_list('authorization')


async def test_endpoint_client_sends_the_child_bearer_by_default(tmp_path):
    n8n = production_spec('n8n', tmp_path / 'n8n')
    hm06 = ChildSpec(('python3', '-c', 'pass'), {'PATH': '/usr/bin:/bin', 'WOOW_MCP_CHILD_TOKEN': 'C' * 43}, tmp_path)
    current = production_spec('odoo', tmp_path / 'odoo')
    endpoints = [owned_runtime.Endpoint('n8n'), owned_runtime.Endpoint('odoo'), owned_runtime.Endpoint('odoo'),
                 owned_runtime.Endpoint('odoo'), owned_runtime.Endpoint(port=43210)]
    try:
        endpoints[0].supervisor(n8n)
        endpoints[1].supervisor(hm06, prepared=True)
        endpoints[2].supervisor(current)
        endpoints[3].supervisor(current)
        assert endpoints[0].bearer() == n8n.env['AUTH_TOKEN']
        assert endpoints[1].bearer() == 'C' * 43
        synthetic = endpoints[2].bearer()
        assert TOKEN.fullmatch(synthetic) and endpoints[2].bearer() == synthetic != endpoints[3].bearer()
        assert TOKEN.fullmatch(endpoints[4].bearer())  # no supervisor (owned_uid_probe's Endpoint(port=...))
        for endpoint in endpoints:
            async with endpoint.client() as client:
                assert await sent_authorization(endpoint, client) == ['Bearer ' + endpoint.bearer()]
                # Every add-on request names its own credential: that one is sent, never both.
                assert await sent_authorization(endpoint, client, headers={'Authorization': 'Bearer ' + 'T' * 43}) == [
                    'Bearer ' + 'T' * 43]
            async with endpoint.client(bearer=False) as client:
                assert await sent_authorization(endpoint, client) == []
            async with endpoint.client(bearer='T' * 43) as client:
                assert await sent_authorization(endpoint, client) == ['Bearer ' + 'T' * 43]
            async with endpoint.client(headers={'authorization': 'Bearer x'}) as client:
                assert await sent_authorization(endpoint, client) == ['Bearer x']
        # Read at each send: a restart with a new spec (HM-06's rotated child token) is followed.
        async with endpoints[1].client() as client:
            endpoints[1].manager.spec = replace(hm06, env={**hm06.env, 'WOOW_MCP_CHILD_TOKEN': 'T' * 43})
            assert await sent_authorization(endpoints[1], client) == ['Bearer ' + 'T' * 43]
        with pytest.raises(TypeError):
            endpoints[2].client(bearer=1)
    finally:
        for endpoint in endpoints:
            endpoint.close()


async def direct_session(client, url):
    """initialize, notifications/initialized, tools/list and DELETE straight to the child (retried while it starts)."""
    started = time.monotonic()
    while True:
        try:
            async with client.stream('POST', url, headers=ACCEPT, json=INIT) as response:
                session = response.headers.get('mcp-session-id')
                result = await protocol_reply(response, 1)
            break
        except (httpx.HTTPError, ValueError, OwnershipError):
            if time.monotonic() - started > 40:
                raise
            await asyncio.sleep(.25)
    headers = {**ACCEPT, 'MCP-Protocol-Version': result['protocolVersion'],
               **({'Mcp-Session-Id': session} if session else {})}
    notified = await client.post(url, headers=headers, json={'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    assert notified.status_code in (200, 202, 204)
    listing = {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}
    async with client.stream('POST', url, headers=headers, json=listing) as response:
        listed = await protocol_reply(response, 2)
    assert listed['tools']
    deleted = await client.delete(url, headers=headers)
    assert deleted.status_code in (200, 202, 204, 405)
    return result


@pytest.mark.parametrize('product', PRODUCTS)
async def test_real_children_accept_the_default_bearer(tmp_path, log_scan, product):
    """bb48449's real children with the shared client's default bearer: every direct request carries it and the child
    answers; n8n (which checks its AUTH_TOKEN) refuses the same client without it."""
    with (nullcontext((None, None, None)) if product == 'n8n' else backend(product)) as (url, _calls, _offline):
        store = ProductStore(tmp_path / 'state', product)
        try:
            if product != 'n8n':
                store.update(connection=connection(product, url))
            state = store.load()
            spec = (n8n_spec if product == 'n8n' else child_spec)(state, store.directory)
        finally:
            store.close()
        log_scan.watch_state(state)
        endpoint = owned_runtime.Endpoint(product)
        manager = endpoint.supervisor(spec)
        sent = []

        async def record(request):
            sent.append(request.headers.get_list('authorization'))

        try:
            await manager.start()
            log_scan.watch(endpoint.bearer())
            async with endpoint.client(timeout=15) as client:
                client.event_hooks['request'].append(record)
                await direct_session(client, endpoint.url)
            assert sent and all(value == ['Bearer ' + endpoint.bearer()] for value in sent)
            if product == 'n8n':
                assert endpoint.bearer() == state.child_token
                async with endpoint.client(bearer=False, timeout=15) as client:
                    refused = await client.post(endpoint.url, headers=ACCEPT, json=INIT)
                    assert refused.status_code == 401
        finally:
            await manager.stop()
            endpoint.close()
