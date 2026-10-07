"""Private native probes survive public disable; real children and policy API.

Only owned loopback backends and dummy credentials. No background monitor races:
explicit HealthMonitor.check() calls own every health read in the counters.
"""
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import threading

import httpx
import pytest

from mcp_admin_core.gateway import make_apps
from mcp_admin_core.health import HealthMonitor
from owned_runtime import Endpoint
from mcp_admin_core.native_inventory import NAMES
from mcp_admin_core.policy import enabled
from mcp_admin_core.products import PROBES, ProductStore, TOOLS, child_spec
from test_expansion_policy import call
from test_expansion_runtime import WRITES, payload
from test_real_products import connection, rpc


@contextmanager
def native_backend(product):
    events, mutations = [], []
    offline = threading.Event()
    read_path = '/api/v5/nodes' if product == 'emqx' else '/v1/models'
    write_route = ('DELETE', '/api/v5/clients/device') if product == 'emqx' else ('POST', '/team/new')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def handle_api(self):
            event = (self.command, self.path)
            events.append(event)
            auth = 'Basic RFVNTVk6RFVNTVk=' if product == 'emqx' else 'Bearer DUMMY'
            if self.headers.get('Authorization') != auth:
                self.send_error(401); return
            if offline.is_set():
                self.send_error(503); return
            if event == ('GET', read_path):
                value = ([{'node': 'fake@local', 'version': '5.fake'}] if product == 'emqx'
                         else {'data': [{'id': 'fake-model'}]})
            elif event == write_route:
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                mutations.append(event)
                value = {'team_id': 'one', 'team_alias': 'Owned', 'status': 'success'}
            else:
                self.send_error(404); return
            data = json.dumps(value).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = do_DELETE = handle_api

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', events, mutations, offline, read_path
    finally:
        server.shutdown(); server.server_close(); thread.join()


@pytest.mark.parametrize('product', ['emqx', 'litellm'])
@pytest.mark.parametrize('grant_writer', [False, True], ids=['default', 'write-grant'])
@pytest.mark.parametrize('disable_all', [False, True], ids=['probe-disabled', 'all-disabled'])
async def test_policy_disable_keeps_private_probe_and_public_denial(tmp_path, product, grant_writer, disable_all):
    with native_backend(product) as (url, events, mutations, offline, read_path):
        store = ProductStore(tmp_path, product)
        writer, writer_args = WRITES[product][0]
        grants = [writer] if grant_writer else []
        store.update(connection=connection(product, url), enabled_write_tools=grants)
        endpoint = Endpoint(product)
        manager = endpoint.supervisor(child_spec(store.load(), store.directory))
        committed, finish_restart = asyncio.Event(), asyncio.Event()
        pending = None
        child_requests = []

        async def record(request):
            child_requests.append(request)

        async def restart(state):
            committed.set()
            await finish_restart.wait()
            await manager.stop()
            manager.spec = endpoint.prepare(child_spec(state, store.directory))
            await manager.start()

        async def role(_): return True  # Test-only role injection, not production HA approval.

        try:
            await manager.start()
            async with endpoint.client() as child:
                child.event_hooks['request'].append(record)
                health = HealthMonitor(store, manager, child, child_url=endpoint.url)

                async def transport_ready():
                    async with asyncio.timeout(20):
                        while True:
                            await health.check()
                            if manager.ready:
                                return
                            await asyncio.sleep(.1)

                await transport_ready()
                assert health.backend == 'reachable' and events == [('GET', read_path)]
                admin, app = make_apps(store, TOOLS[product], child, verify_admin=role,
                                       backend_changed=restart, health=health.snapshot, child_url=endpoint.url)
                async with (httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as client,
                            httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://admin') as a):
                    async def initialize():
                        headers = {'Authorization': 'Bearer '+store.load().token,
                                   'Accept': 'application/json, text/event-stream'}
                        result = await rpc(client, '/mcp', headers, {
                            'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                                'protocolVersion': '2025-03-26', 'capabilities': {},
                                'clientInfo': {'name': 'private-probe-test', 'version': '0'}}})
                        headers['MCP-Protocol-Version'] = result['protocolVersion']
                        await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                        return headers

                    headers = await initialize()
                    probe, args = PROBES[product]
                    payload(await rpc(client, '/mcp', headers, call(probe, args)))
                    assert events[-1] == ('GET', read_path)
                    if grant_writer:
                        payload(await rpc(client, '/mcp', headers, call(writer, writer_args)))
                        assert len(mutations) == 1
                    identity = {'x-remote-user-id': 'a'*32}
                    bootstrap = (await a.get('/api/bootstrap', headers=identity)).json()
                    identity['x-csrf-token'] = bootstrap['csrf']
                    old_pid = manager.process.pid
                    disabled = list(TOOLS[product]) if disable_all else [probe]
                    pending = asyncio.create_task(a.put('/api/policy', headers=identity, json={
                        'writes_enabled': False, 'disabled': disabled, 'enabled_write_tools': grants}))
                    await asyncio.wait_for(committed.wait(), 3)
                    assert store.load().disabled == disabled and not pending.done()
                    assert manager.process.pid == old_pid

                    async def denied(names):
                        before = (len(child_requests), len(events), len(mutations))
                        for name in names:
                            arguments = dict(WRITES[product]).get(name, {})
                            response = await client.post('/mcp', headers=headers, json=call(name, arguments))
                            assert response.status_code == 403, (name, response.text)
                        assert (len(child_requests), len(events), len(mutations)) == before

                    # Same still-live session is denied before the owned restart.
                    public_names = {n for n in TOOLS[product] if enabled(n, TOOLS[product], store.load())}
                    await denied(set(NAMES[product]) - public_names)
                    listed = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
                    assert {t['name'] for t in listed['tools']} == public_names
                    finish_restart.set()
                    assert (await pending).status_code == 200
                    await transport_ready()
                    assert manager.process.pid != old_pid and not Path(f'/proc/{old_pid}').exists()
                    before = len(events)
                    await health.check()
                    assert events[before:] == [('GET', read_path)], 'disabled probe must make an actual backend read'
                    assert health.backend == 'reachable' and manager.ready
                    assert (await client.get('/health/ready')).status_code == 200
                    await denied(set(NAMES[product]) - public_names)  # pre-restart session also denied
                    headers = await initialize()
                    listed = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'})
                    assert {t['name'] for t in listed['tools']} == public_names
                    raw = await rpc(child, endpoint.url, headers,
                                    {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/list'})
                    assert {t['name'] for t in raw['tools']} == public_names | {probe}
                    if disable_all:
                        assert not public_names
                    await denied(set(NAMES[product]) - public_names)
                    # Native registration itself denies every other blocked tool.
                    before = len(events)
                    for name in set(NAMES[product]) - public_names - {probe}:
                        result = await rpc(child, endpoint.url, headers,
                                           call(name, dict(WRITES[product]).get(name, {})))
                        assert result.get('isError'), name
                    assert len(events) == before
                    if grant_writer and not disable_all:
                        payload(await rpc(client, '/mcp', headers, call(writer, writer_args)))
                        assert len(mutations) == 2
                    else:
                        assert len(mutations) == int(grant_writer)
                    prefix = 'EMQX_MCP_' if product == 'emqx' else 'LITELLM_MCP_'
                    assert manager.spec.env[prefix+'READONLY'] == ('false' if grant_writer and not disable_all else 'true')
                    pid, starts = manager.process.pid, manager.starts
                    offline.set()
                    for _ in range(3):
                        before = len(events)
                        await health.check()
                        assert events[before:] == [('GET', read_path)]
                        assert health.backend == 'unreachable' and manager.ready
                        assert (await client.get('/health/ready')).status_code == 503
                        assert manager.process.pid == pid and manager.starts == starts == 2
                        await denied(set(NAMES[product]) - public_names)
                    offline.clear()
                    before = len(events)
                    await health.check()
                    assert events[before:] == [('GET', read_path)]
                    assert health.backend == 'reachable' and (await client.get('/health/ready')).status_code == 200
                    assert manager.process.pid == pid and manager.starts == starts
        finally:
            finish_restart.set()
            if pending is not None:
                await asyncio.gather(pending, return_exceptions=True)
            await manager.stop()
            endpoint.close()
            store.close()


@contextmanager
def nextcloud_backend():
    """Owned in-memory Nextcloud (tests/nextcloud_fixtures.py); every request is recorded."""
    import nextcloud_fixtures
    fake = nextcloud_fixtures.NextcloudFake()
    events = []
    offline = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def handle_api(self):
            events.append((self.command, self.path))
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if offline.is_set():
                self.send_error(503); return
            nextcloud_fixtures.respond(self, *fake.handle(self.command, self.path, self.headers, body))

        do_GET = do_PUT = do_DELETE = do_PROPFIND = do_REPORT = handle_api

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', events, fake.mutations, offline
    finally:
        server.shutdown(); server.server_close(); thread.join()


@pytest.mark.parametrize('grant_writer', [False, True], ids=['default', 'write-grant'])
@pytest.mark.parametrize('disable_all', [False, True], ids=['reads-disabled', 'all-disabled'])
async def test_nextcloud_private_probe_survives_public_disable(tmp_path, grant_writer, disable_all):
    """0.1.7: HealthMonitor calls the child's private woow_backend_probe (one OCS GET, never listed or authorized
    publicly); disabling every public tool restarts the child without them and the probe still reads the backend."""
    from mcp_admin_core.products import ODOO_HEALTH_PROBE, health_probe
    import nextcloud_fixtures
    product = 'nextcloud'
    assert health_probe(product) == (ODOO_HEALTH_PROBE, {}) and ODOO_HEALTH_PROBE not in TOOLS[product]
    probe_event = ('GET', nextcloud_fixtures.OCS_PATH)
    with nextcloud_backend() as (url, events, mutations, offline):
        store = ProductStore(tmp_path, product)
        writer, writer_args = WRITES[product][0]
        grants = [writer] if grant_writer else []
        store.update(connection=connection(product, url), enabled_write_tools=grants)
        endpoint = Endpoint(product)
        manager = endpoint.supervisor(child_spec(store.load(), store.directory))
        committed, finish_restart = asyncio.Event(), asyncio.Event()
        pending = None

        async def restart(state):
            committed.set()
            await finish_restart.wait()
            await manager.stop()
            manager.spec = endpoint.prepare(child_spec(state, store.directory))
            await manager.start()

        async def role(_): return True  # Test-only role injection, not production HA approval.

        try:
            await manager.start()
            async with endpoint.client() as child:
                health = HealthMonitor(store, manager, child, child_url=endpoint.url)

                async def transport_ready():
                    async with asyncio.timeout(20):
                        while True:
                            await health.check()
                            if manager.ready:
                                return
                            await asyncio.sleep(.1)

                await transport_ready()
                assert health.backend == 'reachable' and events == [probe_event]
                admin, app = make_apps(store, TOOLS[product], child, verify_admin=role,
                                       backend_changed=restart, health=health.snapshot, child_url=endpoint.url)
                async with (httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as client,
                            httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://admin') as a):
                    async def initialize():
                        headers = {'Authorization': 'Bearer '+store.load().token,
                                   'Accept': 'application/json, text/event-stream'}
                        result = await rpc(client, '/mcp', headers, {
                            'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                                'protocolVersion': '2025-03-26', 'capabilities': {},
                                'clientInfo': {'name': 'private-probe-test', 'version': '0'}}})
                        headers['MCP-Protocol-Version'] = result['protocolVersion']
                        await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                        return headers

                    headers = await initialize()
                    # The private probe is never public: not listed, and refused before dispatch.
                    listed = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
                    assert ODOO_HEALTH_PROBE not in {t['name'] for t in listed['tools']}
                    before = len(events)
                    response = await client.post('/mcp', headers=headers, json=call(ODOO_HEALTH_PROBE, {}))
                    assert response.status_code == 403 and len(events) == before
                    read, read_args = PROBES[product]
                    payload(await rpc(client, '/mcp', headers, call(read, read_args)))
                    if grant_writer:
                        payload(await rpc(client, '/mcp', headers, call(writer, writer_args)))
                        assert len(mutations) == 1
                    identity = {'x-remote-user-id': 'a'*32}
                    bootstrap = (await a.get('/api/bootstrap', headers=identity)).json()
                    assert ODOO_HEALTH_PROBE not in bootstrap['tools']
                    identity['x-csrf-token'] = bootstrap['csrf']
                    old_pid = manager.process.pid
                    disabled = list(TOOLS[product]) if disable_all else [n for n, t in TOOLS[product].items() if not t.write]
                    pending = asyncio.create_task(a.put('/api/policy', headers=identity, json={
                        'writes_enabled': False, 'disabled': disabled, 'enabled_write_tools': grants}))
                    await asyncio.wait_for(committed.wait(), 3)
                    assert not pending.done() and manager.process.pid == old_pid
                    public_names = {n for n in TOOLS[product] if enabled(n, TOOLS[product], store.load())}
                    assert public_names == ({writer} if grant_writer and not disable_all else set())
                    finish_restart.set()
                    assert (await pending).status_code == 200
                    await transport_ready()
                    assert manager.process.pid != old_pid and not Path(f'/proc/{old_pid}').exists()
                    env = manager.spec.env
                    assert env['NEXTCLOUD_MCP_READONLY'] == ('false' if public_names else 'true')
                    assert env['NEXTCLOUD_MCP_ALLOW_DELETE'] == 'false'
                    assert set(env['NEXTCLOUD_MCP_DISABLED_TOOLS'].split(',')) == set(NAMES[product]) - public_names
                    before = len(events)
                    await health.check()
                    assert events[before:] == [probe_event], 'the private probe must make an actual backend read'
                    assert health.backend == 'reachable' and manager.ready
                    headers = await initialize()
                    raw = await rpc(child, endpoint.url, headers, {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/list'})
                    assert {t['name'] for t in raw['tools']} == public_names | {ODOO_HEALTH_PROBE}
                    listed = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'})
                    assert {t['name'] for t in listed['tools']} == public_names
                    # Native registration itself refuses every tool that is not public (the child never has it).
                    before = len(events)
                    for name in set(NAMES[product]) - public_names:
                        result = await rpc(child, endpoint.url, headers, call(name, dict(WRITES[product]).get(name, {})))
                        assert result.get('isError'), name
                    assert len(events) == before
                    pid, starts = manager.process.pid, manager.starts
                    offline.set()
                    for _ in range(2):
                        before = len(events)
                        await health.check()
                        assert events[before:] == [probe_event]
                        assert health.backend == 'unreachable' and manager.ready
                        assert (await client.get('/health/ready')).status_code == 503
                        assert manager.process.pid == pid and manager.starts == starts == 2
                    offline.clear()
                    await health.check()
                    assert health.backend == 'reachable' and (await client.get('/health/ready')).status_code == 200
        finally:
            finish_restart.set()
            if pending is not None:
                await asyncio.gather(pending, return_exceptions=True)
            await manager.stop()
            endpoint.close()
            store.close()
