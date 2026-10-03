"""Fallback and process-owned DNS regressions; owned loopback/synthetic DNS only."""
import asyncio
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import socket
import subprocess
import threading
import time
import xmlrpc.client

import httpcore
import httpx
import pytest

from mcp_admin_core.gateway import make_apps
from mcp_admin_core.health import HealthMonitor
from mcp_admin_core.lifecycle import ChildSpec, Supervisor
from mcp_admin_core.products import PROBES, ProductState, ProductStore, TOOLS, child_spec
from test_backend_policy_python import policy
from test_real_products import rpc
from test_six_hardening import Quiet, call, runtime, serve


@pytest.mark.parametrize('kind', ['sync', 'async', 'xmlrpc'])
@pytest.mark.parametrize('answers', ['localhost', 'same-family', 'dual-stack'])
async def test_fallback_after_refused_address(monkeypatch, kind, answers):
    hosts = []
    class Backend(Quiet):
        def do_GET(self):
            hosts.append(self.headers['Host'])
            self.reply({'status': 'ok'})
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            hosts.append(self.headers['Host'])
            self.reply(xmlrpc.client.dumps((7,), methodresponse=True).encode())
    with serve(Backend) as literal:
        port = int(literal.rsplit(':', 1)[1])
        host = 'localhost' if answers == 'localhost' else 'configured.invalid'
        lookups = []
        original = socket.getaddrinfo
        def resolve(name, p, *a, **kw):
            lookups.append(name)
            if answers == 'localhost':
                result = original(name, p, *a, **kw)
                assert result[0][4][0] == '::1', result
                return result
            first = (socket.AF_INET6, ('::1', p, 0, 0)) if answers == 'dual-stack' else (socket.AF_INET, ('127.0.0.2', p))
            return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', addr)
                    for family, addr in (first, (socket.AF_INET, ('127.0.0.1', p)))]
        base = f'http://{host}:{port}'
        if answers == 'localhost':
            if kind == 'sync':
                with httpx.Client(trust_env=False, timeout=1) as client:
                    assert client.get(base).status_code == 200
            elif kind == 'async':
                async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
                    assert (await client.get(base)).status_code == 200
            else:
                with xmlrpc.client.ServerProxy(base) as client:
                    assert client.probe() == 7
            hosts.clear()
        monkeypatch.setattr(socket, 'getaddrinfo', resolve)
        if kind == 'sync':
            with policy.sync_client(base_url=base, timeout=1) as client:
                assert client.get('/').status_code == 200
        elif kind == 'async':
            async with policy.async_client(base_url=base, timeout=1) as client:
                assert (await client.get('/')).status_code == 200
        else:
            assert policy.XMLTransport(base, timeout=1).request(f'{host}:{port}', '/RPC2', b'<methodCall/>') == (7,)
        assert lookups == [host]
        assert hosts == [f'{host}:{port}']


@pytest.mark.parametrize('kind', ['sync', 'async', 'xmlrpc'])
async def test_fallback_to_live_ipv6(monkeypatch, kind):
    class IPv6Server(ThreadingHTTPServer):
        address_family = socket.AF_INET6
    class Backend(Quiet):
        def do_GET(self): self.reply({})
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            self.reply(xmlrpc.client.dumps((7,), methodresponse=True).encode())
    server = IPv6Server(('::1', 0), Backend)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    lookups = []
    def resolve(host, port, *a, **kw):
        lookups.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('127.0.0.1', port)),
                (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('::1', port, 0, 0))]
    monkeypatch.setattr(socket, 'getaddrinfo', resolve)
    base = f'http://configured.invalid:{server.server_port}'
    try:
        if kind == 'sync':
            with policy.sync_client(base_url=base, timeout=1) as client:
                assert client.get('/').status_code == 200
        elif kind == 'async':
            async with policy.async_client(base_url=base, timeout=1) as client:
                assert (await client.get('/')).status_code == 200
        else:
            assert policy.XMLTransport(base, timeout=1).request(f'configured.invalid:{server.server_port}', '/', b'<methodCall/>') == (7,)
        assert lookups == ['configured.invalid']
    finally:
        server.shutdown(); server.server_close(); thread.join()


@pytest.mark.parametrize('kind', ['sync', 'async', 'xmlrpc'])
async def test_dns_and_all_connect_attempts_share_deadline(monkeypatch, kind):
    calls, budgets, closed = [], [], []
    def resolve(host, port, *a, **kw):
        calls.append(host)
        time.sleep(.06)
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (ip, port))
                for ip in ('127.0.0.2', '127.0.0.3', '127.0.0.1')]
    monkeypatch.setattr(socket, 'getaddrinfo', resolve)
    class StallSocket:
        def __init__(self, *args): self.timeout = None
        def settimeout(self, value): self.timeout = value
        def setsockopt(self, *args): pass
        def connect(self, address):
            budgets.append(self.timeout)
            time.sleep(self.timeout)
            raise TimeoutError('synthetic blackhole')
        def close(self): closed.append(self)
    async def stall(self, host, port, timeout=None, *args):
        budgets.append(timeout)
        await asyncio.sleep(timeout)
        raise httpcore.ConnectTimeout('synthetic blackhole')
    destination = policy.Destination('http://configured.invalid')
    if kind == 'async':
        monkeypatch.setattr(policy.AnyIOBackend, 'connect_tcp', stall)
    else:
        monkeypatch.setattr(socket, 'socket', StallSocket)
    started = time.monotonic()
    with pytest.raises((httpcore.ConnectTimeout, ValueError), match='BACKEND_TIMEOUT|synthetic blackhole'):
        if kind == 'async':
            await policy.PinnedAsyncBackend(destination).connect_tcp(destination.host, 80, timeout=.24)
        elif kind == 'sync':
            policy.PinnedSyncBackend(destination).connect_tcp(destination.host, 80, timeout=.24)
        else:
            policy.XMLTransport('http://configured.invalid', timeout=.24).request('configured.invalid', '/', b'<methodCall/>')
    assert .20 <= time.monotonic() - started < .4
    assert calls == ['configured.invalid']
    assert len(budgets) == 3 and sum(budgets) <= .19, budgets
    if kind != 'async': assert len(closed) == 3


@pytest.mark.parametrize('product', ['opendesign', 'hermes'])
async def test_real_localhost_health_and_readiness(tmp_path, product):
    class Backend(Quiet):
        def do_GET(self): self.reply({'status': 'ok'})
    with serve(Backend) as url:
        async with runtime(tmp_path, product, url.replace('127.0.0.1', 'localhost')) as (client, headers, store, manager, child):
            name, args = PROBES[product]
            result = await rpc(client, '/mcp', headers, call(name, args))
            assert not result.get('isError'), result
            monitor = HealthMonitor(store, manager, child)
            await monitor.check()
            assert monitor.backend == 'reachable'
            _, app = make_apps(store, TOOLS[product], child, health=monitor.snapshot)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as health:
                assert (await health.get('/health/ready')).status_code == 200
            assert manager.ready and manager.starts == 1


# This wrapper changes ONLY DNS before the actual pinned Hermes launcher runs.
DNS_WRAPPER = r'''
import socket, runpy, sys
port = int(sys.argv[1]); launch = sys.argv[2]; original = socket.getaddrinfo
def blocked(host, p, *a, **kw):
    if host not in ('configured.invalid', b'configured.invalid'):
        return original(host, p, *a, **kw)
    with socket.socket() as s:
        s.settimeout(20); s.connect(('127.0.0.1', port))
        s.sendall(b'GET /dns HTTP/1.0\r\nHost: owned\r\n\r\n')
        while s.recv(4096): pass
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('127.0.0.1', p))]
socket.getaddrinfo = blocked
runpy.run_path(launch, run_name='__main__')
'''


async def test_gateway_cancellation_waves_bound_dns_and_reap(tmp_path):
    active = peak = entered = 0
    release = threading.Event()
    lock = threading.Lock()
    class Backend(Quiet):
        def do_GET(self):
            nonlocal active, peak, entered
            if self.path == '/dns':
                with lock:
                    active += 1; entered += 1; peak = max(peak, active)
                release.wait(15)
                with lock: active -= 1
            self.reply({'capabilities': ['owned-test']})
    with socket.socket() as check:
        check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        check.bind(('127.0.0.1', 3000))
    with serve(Backend) as url:
        store = ProductStore(tmp_path / 'state', 'hermes')
        store.update(connection={'gateway_url': url.replace('127.0.0.1', 'configured.invalid'), 'gateway_api_key': 'DUMMY'})
        spec = child_spec(store.load(), store.directory)
        wrapped = ChildSpec((spec.argv[0], '-c', DNS_WRAPPER, url.rsplit(':', 1)[1], spec.argv[1]), spec.env, spec.cwd)
        manager = Supervisor(wrapped)
        await manager.start()
        tasks = []
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=20) as child:
                _, app = make_apps(store, TOOLS['hermes'], child)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary', timeout=20) as client:
                    headers = {'Authorization': 'Bearer ' + store.load().token, 'Accept': 'application/json, text/event-stream'}
                    init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'dns-test', 'version': '0'}}}
                    for _ in range(100):
                        try:
                            await rpc(client, '/mcp', headers, init); break
                        except (httpx.HTTPError, ValueError): await asyncio.sleep(.1)
                    else: raise AssertionError('child not ready')
                    await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                    snapshots, completions = [], []
                    for wave in range(3):
                        tasks = [asyncio.create_task(client.post('/mcp', headers=headers, json=call('hermes_inspect', {'target': 'capabilities'}, id=100+wave*24+i))) for i in range(24)]
                        # Wait for admission/explicit rejection, not the stalled resolver.
                        for _ in range(150):
                            if sum(t.done() for t in tasks) >= 20: break
                            await asyncio.sleep(.02)
                        with lock: snapshot = active, peak, entered
                        print('DNS wave', wave + 1, snapshot)
                        snapshots.append(snapshot)
                        completions.append([t.result() for t in tasks if t.done()])
                        started = time.monotonic()
                        assert await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 50, 'method': 'ping'}) == {}
                        assert time.monotonic() - started < .75
                        for task in tasks: task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
                    assert snapshots == [(4, 4, 4)] * 3, snapshots
                    assert all(len(completed) >= 20 for completed in completions)
                    assert all('BACKEND_BUSY' in r.text for completed in completions for r in completed)
                    release.set()
                    for _ in range(100):
                        result = await rpc(client, '/mcp', headers, call('hermes_inspect', {'target': 'capabilities'}))
                        if 'owned-test' in json.dumps(result): break
                        await asyncio.sleep(.02)
                    else: raise AssertionError('DNS capacity not reusable')
                    with lock: assert active == 0 and peak == 4 and entered > 4
                    # Block again; supervisor must reap the process with live resolvers.
                    release.clear()
                    tasks = [asyncio.create_task(client.post('/mcp', headers=headers, json=call('hermes_inspect', {'target': 'capabilities'}, id=500+i))) for i in range(4)]
                    for _ in range(100):
                        with lock: n = active
                        if n == 4: break
                        await asyncio.sleep(.02)
                    assert n == 4
                    pid = manager.process.pid
                    started = time.monotonic()
                    await manager.stop()
                    assert time.monotonic() - started < 5
                    assert not Path(f'/proc/{pid}').exists()
        finally:
            release.set()
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await manager.stop()
            store.close()


def test_actual_hermes_clients_share_execution_owned_resolvers(tmp_path):
    state = ProductState(product='hermes', token='a'*43, child_token='b'*43,
                         connection={'gateway_url': 'http://configured.invalid', 'gateway_api_key': 'DUMMY'})
    spec = child_spec(state, tmp_path)
    program = r'''
import asyncio, socket, threading, time
from backend_policy import sync_client, async_client, XMLTransport, RESOLVER_CAPACITY
from hermes_mcp_server.server import _gateway_client, _dashboard_login, _dashboard_client
active = peak = entered = 0
lock = threading.Lock(); release = threading.Event()
def resolve(*args, **kwargs):
    global active, peak, entered
    with lock:
        active += 1; entered += 1; peak = max(active, peak)
    release.wait(8)
    with lock: active -= 1
    raise socket.gaierror(socket.EAI_AGAIN, 'synthetic DNS failure')
socket.getaddrinfo = resolve
base = 'http://configured.invalid'
def sync_read():
    with sync_client(base_url=base, timeout=.15) as c: c.get('/')
async def invoke(kind):
    try:
        if kind == 'login': await _dashboard_login(base, 'tester', 'DUMMY')
        elif kind == 'sync': await asyncio.to_thread(sync_read)
        elif kind == 'xmlrpc': XMLTransport(base, timeout=.15).request('configured.invalid', '/', b'<methodCall/>')
        else:
            c = _gateway_client(base, 'DUMMY') if kind == 'gateway' else _dashboard_client(base, 'DUMMY') if kind == 'cookie' else async_client(base_url=base, timeout=.05)
            async with c: await c.get('/')
    except Exception as exc: return str(exc)
async def main():
    tasks = [asyncio.create_task(invoke(k)) for k in ('gateway', 'login', 'cookie', 'sync')]
    try:
        for _ in range(100):
            with lock: n = active
            if n == 4: break
            await asyncio.sleep(.01)
        assert n == RESOLVER_CAPACITY == 4
        for task in tasks: task.cancel()
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), .5)
        for _ in range(3):
            for kind in ('gateway', 'login', 'cookie', 'sync', 'xmlrpc'):
                assert await invoke(kind) == 'BACKEND_BUSY', kind
        with lock: assert (active, peak, entered) == (4, 4, 4)
        assert len([t for t in threading.enumerate() if t.name.startswith('backend-dns')]) == 4
        release.set()
        for _ in range(100):
            result = await invoke('gateway')
            if result == 'BACKEND_UNAVAILABLE': break
            assert result == 'BACKEND_BUSY', result
            await asyncio.sleep(.01)
        else: raise AssertionError('resolver capacity leaked')
        # A DNS deadline must stop waiting, but not free the still-running slot.
        release.clear()
        tasks = [asyncio.create_task(invoke('timeout')) for _ in range(4)]
        assert await asyncio.wait_for(asyncio.gather(*tasks), .5) == ['BACKEND_TIMEOUT'] * 4
        with lock: assert active == 4 and peak == 4
        assert await invoke('cookie') == 'BACKEND_BUSY'
        release.set()
    finally:
        release.set()
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
asyncio.run(main())
'''
    result = subprocess.run([spec.argv[0], '-c', program], env=spec.env, cwd=spec.cwd,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
