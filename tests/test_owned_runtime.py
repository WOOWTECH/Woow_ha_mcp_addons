"""Isolation regressions: forbidden destinations use spies, never real port 3000."""
import asyncio
from dataclasses import replace
from pathlib import Path
import socket
import sys

import httpx
import pytest

from batch2_owned_port import OwnershipError, reserve_port
from mcp_admin_core.lifecycle import ChildSpec
from owned_runtime import Endpoint, private_spec
from owned_network import check_address


@pytest.mark.parametrize('address', [('127.0.0.1', 3000), ('::1', 3000, 0, 0),
                                     ('::ffff:127.0.0.1', 3000), ('localhost', 3000)])
def test_forbidden_before_downstream_spy(address):
    calls = []
    def operation(address):
        check_address(address)
        calls.append(address)
    with pytest.raises(OwnershipError):
        operation(address)
    assert calls == []


def dummy(port):
    return ChildSpec((sys.executable, '-c',
        'import socket,time; s=socket.socket(); s.bind(("127.0.0.1",'+str(port)+')); s.listen(); time.sleep(30)'),
        {'PATH': '/usr/bin:/bin'}, Path('/tmp'))


async def test_generation_invalidated_before_stop_and_refreshed():
    endpoint = Endpoint()
    manager = endpoint.supervisor(dummy(endpoint.port), prepared=True)
    try:
        await manager.start()
        first = endpoint.proof
        request = httpx.Request('DELETE', endpoint.url)
        await endpoint.guard(request)
        await manager.stop()
        with pytest.raises(OwnershipError):
            await endpoint.guard(request)
        await manager.start()
        assert endpoint.proof != first and endpoint.generation == 2
        await endpoint.guard(request)
        for url in ('http://127.0.0.1:3000/mcp', endpoint.url + '/other'):
            with pytest.raises(OwnershipError):
                await endpoint.guard(httpx.Request('POST', url))
    finally:
        await manager.stop()
        endpoint.close()


async def test_health_invalidation_denies_transport_without_stopping_monitor(tmp_path):
    from mcp_admin_core.config import Store
    from mcp_admin_core.health import HealthMonitor
    endpoint = Endpoint()
    manager = endpoint.supervisor(dummy(endpoint.port), prepared=True)
    store = Store(tmp_path)
    dispatched = []
    def initialize(request):
        dispatched.append(request.method)
        # The real callback invalidates proof before awaiting child shutdown.
        # Force that exact interleaving after health initialize, before its
        # notification and finally DELETE; neither may reach the transport.
        endpoint.invalidate()
        return httpx.Response(200, headers={'mcp-session-id':'owned-session'}, json={
            'jsonrpc':'2.0', 'id':1, 'result':{'serverInfo':{}, 'protocolVersion':'2025-03-26'}})
    try:
        await manager.start()
        first = endpoint.proof
        async with httpx.AsyncClient(transport=httpx.MockTransport(initialize)) as client:
            endpoint.attach(client)
            async with asyncio.timeout(5):
                await HealthMonitor(store, manager, client, child_url=endpoint.url).check()
        assert dispatched == ['POST']
        assert not manager.ready
        await manager.restart(dummy(endpoint.port))
        assert endpoint.proof != first and endpoint.generation == 2
        await endpoint.guard(httpx.Request('DELETE', endpoint.url))
    finally:
        await manager.stop()
        endpoint.close()
        store.close()


async def test_unconfigured_is_zero_probe():
    endpoint = Endpoint()
    manager = endpoint.supervisor(None, prepared=True)
    try:
        await manager.start()
        assert manager.status == 'unconfigured' and endpoint.proof is None
        with pytest.raises(OwnershipError):
            await endpoint.guard(httpx.Request('POST', endpoint.url))
    finally:
        await manager.stop()
        endpoint.close()


async def test_owned_decoy_receives_no_http():
    calls = []
    async def decoy(reader, writer):
        calls.append(await reader.read(1024))
        writer.close()
    server = await asyncio.start_server(decoy, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    endpoint = Endpoint(port=port)
    manager = endpoint.supervisor(ChildSpec((sys.executable, '-c', 'import time; time.sleep(30)'),
                                          {'PATH': '/usr/bin:/bin'}, Path('/tmp')), prepared=True)
    try:
        with pytest.raises(OwnershipError, match='not owned'):
            await manager.start()
        assert calls == []
    finally:
        await manager.stop()
        endpoint.close()
        server.close()
        await server.wait_closed()


@pytest.mark.parametrize('product', ['odoo', 'odoo-manage', 'emqx', 'litellm', 'hermes', 'opendesign', 'n8n'])
def test_exact_spec_shape(product):
    from mcp_admin_core.products import ProductStore, child_spec
    from test_real_products import connection
    from n8n_adapter import child_spec as n8n_spec
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        store = ProductStore(Path(directory), product)
        try:
            if product == 'n8n':
                store.update(backend_url='http://127.0.0.1:43210', backend_key='DUMMY')
            else:
                store.update(connection=connection(product, 'http://127.0.0.1:43210'))
            original = (n8n_spec if product == 'n8n' else child_spec)(store.load(), store.directory)
            with reserve_port() as reservation:
                port = reservation.getsockname()[1]
                result = private_spec(original, product, port)
            assert result.cwd == original.cwd
            if product != 'n8n':
                assert result.env == original.env
            if product in ('odoo', 'odoo-manage', 'emqx', 'litellm'):
                index = original.argv.index('--port') + 1
                assert original.argv[index] == '3000'
                assert result.argv[:index] == original.argv[:index]
                assert result.argv[index] == str(port)
                assert result.argv[index+1:] == original.argv[index+1:]
            elif product == 'n8n':
                assert original.env['PORT'] == '3000'
                assert result == replace(original, env={**original.env, 'PORT': str(port)})
            else:
                assert result.argv[-len(original.argv[1:]):] == original.argv[1:]
                assert result.argv[0] == original.argv[0]
        finally:
            store.close()


async def test_omitted_gateway_and_monitor_urls_fail_before_dispatch(tmp_path):
    from mcp_admin_core.config import Store
    from mcp_admin_core.gateway import make_apps
    from mcp_admin_core.health import HealthMonitor
    from n8n_adapter import TOOLS
    endpoint = Endpoint()
    manager = endpoint.supervisor(dummy(endpoint.port), prepared=True)
    calls = []
    store = Store(tmp_path)
    def downstream(request):
        calls.append(request)
        raise AssertionError('must not dispatch')
    try:
        await manager.start()
        async with httpx.AsyncClient(transport=httpx.MockTransport(downstream)) as child:
            endpoint.attach(child)
            rejected = []
            hooks = child.event_hooks['request']
            guard = hooks[hooks.index(endpoint.guard)]

            async def recording_guard(request):
                try:
                    await guard(request)
                except OwnershipError as exc:
                    rejected.append(str(exc))
                    raise
            hooks[hooks.index(endpoint.guard)] = recording_guard
            # Deliberately OMIT both existing URL seams. These default Requests
            # stay in memory; the endpoint guard rejects before the mock spy.
            # Since 0.1.2 the monitor contains every error a child path raises (a misbehaving child must not
            # stop the add-on), so the rejection is observed at the guard and readiness stays false.
            monitor = HealthMonitor(store, manager, child)
            await monitor.check()
            assert rejected and 'destination' in rejected[0]
            assert manager.ready is False and monitor.snapshot()['backend'] in ('unconfigured', 'unreachable')
            _, app = make_apps(store, TOOLS, child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                with pytest.raises(OwnershipError, match='destination'):
                    await client.post('/mcp', headers={'Authorization':'Bearer '+store.load().token},
                                      json={'jsonrpc':'2.0','id':1,'method':'ping'})
            assert calls == []
    finally:
        await manager.stop()
        endpoint.close()
        store.close()


async def test_inaccessible_own_fd_fails_before_http(monkeypatch):
    endpoint = Endpoint()
    manager = endpoint.supervisor(dummy(endpoint.port), prepared=True)
    try:
        await manager.start()
        original = Path.iterdir
        with monkeypatch.context() as patch:
            def inaccessible(path):
                if str(path) == f'/proc/{manager.process.pid}/fd':
                    raise PermissionError('synthetic own fd denial')
                return original(path)
            patch.setattr(Path, 'iterdir', inaccessible)
            with pytest.raises(OwnershipError, match='cannot prove'):
                await endpoint.guard(httpx.Request('POST', endpoint.url))
    finally:
        await manager.stop()
        endpoint.close()


def test_python_audit_spy_is_pre_operation():
    from owned_network import audit
    calls = []
    for operation in ('socket.bind', 'socket.connect'):
        with pytest.raises(OwnershipError):
            audit(operation, (object(), ('::ffff:127.0.0.1', 3000)))
            calls.append(operation)
    assert calls == []
    audit('socket.connect', (object(), ('127.0.0.1', 43210)))


def test_node_guard_spies_zero_original_operations():
    import subprocess
    preload = Path(__file__).with_name('owned_network.cjs')
    code = r'''
const assert=require('node:assert/strict'), net=require('node:net');
let calls=0;
net.Socket.prototype.connect=function(){calls++;};
net.Server.prototype.listen=function(){calls++;};
delete require.cache[require.resolve(process.argv[1])];
require(process.argv[1]);
for(const args of [[3000,'127.0.0.1'],[{port:3000,host:'::1'}],['3000','localhost'],[{port:3000,host:'::ffff:127.0.0.1'}]]) {
  assert.throws(()=>new net.Socket().connect(...args),/production port/);
  assert.throws(()=>net.createServer().listen(...args),/production port/);
}
assert.equal(calls,0);
new net.Socket().connect(43210,'127.0.0.1');
net.createServer().listen(43210,'127.0.0.1');
assert.equal(calls,2);
'''
    result = subprocess.run(['node', '-e', code, str(preload)], capture_output=True, text=True, timeout=5,
                            env={'PATH':'/usr/bin:/bin'})
    assert result.returncode == 0, result.stderr


def test_spawned_python_sentinel_is_installed_before_target():
    import subprocess
    # Explicit audit event + spy, not a real socket operation against 3000.
    code = '''import sys
calls=[]
try:
    sys.audit('socket.connect', object(), ('localhost',3000))
    calls.append('underlying operation')
except RuntimeError: pass
assert not calls
print('guarded before target')
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=5,
                            env={'PATH':'/usr/bin:/bin'})
    assert result.returncode == 0 and result.stdout.strip() == 'guarded before target', result.stderr
