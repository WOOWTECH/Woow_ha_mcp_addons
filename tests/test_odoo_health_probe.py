"""Odoo readiness probe: its own owned thread, authentication only, never public.

0.1.2 HA regression: right after an Odoo restart, the backend probe (list_models) held the child's single tool
worker while Odoo was slow and twelve user reads got BACKEND_BUSY; an account without ir.model access also read
as unreachable. Genuine pinned Odoo child, owned fake XMLRPC backend, real HealthMonitor and gateway.
"""
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import xmlrpc.client

import httpx

from owned_runtime import Endpoint
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.health import HealthMonitor
from mcp_admin_core.products import ProductStore, TOOLS, child_spec, health_probe
from test_b2_odoo_runtime import initialize
from test_expansion_policy import call
from test_expansion_runtime import payload
from test_real_products import connection, rpc

FIELDS = {'name': 'char', 'active': 'boolean'}
REPORT = call('data_quality_report', {'model': 'res.partner'})


@contextmanager
def fake_odoo():
    """Like the HA test account: authenticates, reads res.partner, has no ir.model access."""
    calls, failures = [], []
    state = {'hold': None, 'deny': False, 'started': threading.Event(), 'release': threading.Event()}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def do_POST(self):
            try:
                params, method = xmlrpc.client.loads(self.rfile.read(int(self.headers['Content-Length'])))
                with lock:  # hold only the first matching request after arming (slow Odoo)
                    held = state['hold'] == method
                    if held:
                        state['hold'] = None
                if held:
                    state['started'].set()
                    assert state['release'].wait(20)
                if method == 'authenticate':
                    calls.append(method)
                    value = False if state['deny'] else 7
                else:
                    assert method == 'execute_kw', method
                    model, op, args = params[3:6]
                    calls.append(f'{model}.{op}')
                    if model == 'ir.model':
                        raise xmlrpc.client.Fault(4, 'AccessError')
                    if op == 'fields_get':
                        value = {n: {'type': FIELDS[n], 'required': n == 'name', 'store': True} for n in args[0]}
                    else:
                        assert op == 'search_count', op
                        value = 3
                data = xmlrpc.client.dumps((value,), methodresponse=True, allow_none=True).encode()
            except xmlrpc.client.Fault as exc:
                data = xmlrpc.client.dumps(exc).encode()
            except Exception as exc:
                failures.append(repr(exc))
                data = xmlrpc.client.dumps(xmlrpc.client.Fault(1, 'fake assertion')).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/xml')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except BrokenPipeError:
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', calls, failures, state
    finally:
        state['release'].set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


async def test_odoo_probe_never_takes_the_tool_worker(tmp_path):
    with fake_odoo() as (url, calls, failures, state):
        def hold(method):
            state['started'].clear()
            state['release'].clear()
            state['hold'] = method

        async def held():
            assert await asyncio.to_thread(state['started'].wait, 10)

        store = ProductStore(tmp_path / 'state', 'odoo')
        store.update(connection=connection('odoo', url))
        endpoint = Endpoint('odoo')
        process = endpoint.supervisor(child_spec(store.load(), store.directory))
        try:
            await process.start()
            async with endpoint.client() as child:
                health = HealthMonitor(store, process, child, child_url=endpoint.url)
                _, app = make_apps(store, TOOLS['odoo'], child, child_url=endpoint.url)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as client:
                    headers = {'Authorization': 'Bearer ' + store.load().token,
                               'Accept': 'application/json, text/event-stream'}
                    await initialize(client, headers)

                    # Reachable without ir.model access: one authenticate, nothing else.
                    before = len(calls)
                    await health.check()
                    assert health.backend == 'reachable' and calls[before:] == ['authenticate'], calls[before:]

                    # Private: never listed or dispatched through the gateway.
                    name, arguments = health_probe('odoo')
                    assert name not in TOOLS['odoo']
                    listed = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
                    assert name not in {t['name'] for t in listed['tools']}
                    before = len(calls)
                    assert (await client.post('/mcp', headers=headers, json=call(name, arguments))).status_code == 403
                    assert len(calls) == before
                    assert payload(await rpc(client, '/mcp', headers, REPORT))['summary']['total_issues'] == 3

                    # A probe held by a slow Odoo leaves the tool worker to users (0.1.2: BACKEND_BUSY).
                    hold('authenticate')
                    probe = asyncio.create_task(health.check())
                    try:
                        await held()
                        assert payload(await rpc(client, '/mcp', headers, REPORT))['summary']['total_issues'] == 3
                    finally:
                        state['release'].set()
                    await probe
                    assert health.backend == 'reachable'

                    # A user call held by a slow Odoo does not starve the probe either.
                    hold('execute_kw')
                    pending = asyncio.create_task(rpc(client, '/mcp', headers, REPORT))
                    try:
                        await held()
                        await health.check()
                        assert health.backend == 'reachable'
                    finally:
                        state['release'].set()
                    assert payload(await pending)['summary']['total_issues'] == 3

                    # A probe still running owns its thread: the next one is refused (no queue), users are not.
                    hold('authenticate')
                    stuck = asyncio.create_task(health.check())
                    try:
                        await held()
                        stuck.cancel()
                        await asyncio.gather(stuck, return_exceptions=True)
                        await health.check()
                        assert health.backend == 'unreachable'
                        assert payload(await rpc(client, '/mcp', headers, REPORT))['summary']['total_issues'] == 3
                    finally:
                        state['release'].set()
                    async with asyncio.timeout(10):
                        while True:
                            await health.check()
                            if health.backend == 'reachable':
                                break
                            await asyncio.sleep(.1)

                    # Rejected credentials (Odoo answers False) are not reachable.
                    state['deny'] = True
                    await health.check()
                    assert health.backend == 'unreachable'
                    state['deny'] = False
                    await health.check()
                    assert health.backend == 'reachable'
                    assert not failures, failures
        finally:
            await process.stop()
            store.close()
