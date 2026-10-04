"""Private B1 port ownership: no HTTP may reach an unproved listener."""
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading

import httpx
import pytest

from batch2_owned_port import (
    OwnershipError, private_spec, reserve_port, request_guard, wait_owned_listener,
)
from mcp_admin_core.lifecycle import ChildSpec, Supervisor
from mcp_admin_core.products import ProductStore, child_spec
from n8n_adapter import child_spec as n8n_spec
from test_real_products import connection


def dummy_spec(*args):
    return ChildSpec((sys.executable, *args), {'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'}, Path.cwd())


@pytest.mark.parametrize('product', ['odoo', 'odoo-manage', 'n8n'])
def test_private_port_changes_only_fixed_production_port(tmp_path, product):
    with closing(ProductStore(tmp_path, product)) as store, reserve_port() as reservation:
        port = reservation.getsockname()[1]
        if product == 'n8n':
            store.update(backend_url='http://127.0.0.1:12345', backend_key='DUMMY')
            original = n8n_spec(store.load(), store.directory)
        else:
            store.update(connection=connection(product, 'http://127.0.0.1:12345'))
            original = child_spec(store.load(), store.directory)
        changed = private_spec(original, product, port)
        assert original.cwd == changed.cwd
        if product == 'n8n':
            assert original.argv == changed.argv
            assert original.env['PORT'] == '3000'
            assert changed.env == {**original.env, 'PORT': str(port)}
        else:
            assert original.env == changed.env
            index = original.argv.index('--port') + 1
            assert original.argv[index] == '3000'
            assert changed.argv == (*original.argv[:index], str(port), *original.argv[index+1:])
        # Reservation remains exclusive until explicitly handed to the child.
        import socket
        with socket.socket() as contender, pytest.raises(OSError):
            contender.bind(('127.0.0.1', port))


async def test_owned_listener_allows_http_then_rejects_after_exit():
    with reserve_port() as reservation:
        port = reservation.getsockname()[1]
        supervisor = Supervisor(dummy_spec('-m', 'http.server', str(port), '--bind', '127.0.0.1'), retries=0)
        try:
            reservation.close()
            await supervisor.start()
            proof = await wait_owned_listener(supervisor, port)
            assert proof[0] == supervisor.process.pid
            sent = []
            async def dispatched(request): sent.append(request.method)
            async with httpx.AsyncClient(trust_env=False, event_hooks={
                    'request': [request_guard(supervisor, port, proof), dispatched]}) as client:
                assert (await client.get(f'http://127.0.0.1:{port}/mcp')).status_code == 404
                assert sent == ['GET']
                # Exercise destination rejection without connecting to that URL.
                with pytest.raises(OwnershipError, match='unexpected child destination'):
                    await request_guard(supervisor, port, proof)(httpx.Request('GET', 'http://127.0.0.1:3000/mcp'))
                await supervisor.stop()
                with pytest.raises(OwnershipError):
                    await client.get(f'http://127.0.0.1:{port}/mcp')
                assert sent == ['GET']
        finally:
            await supervisor.stop()


@pytest.mark.parametrize('mode', ['occupied-live-child', 'occupied-bind-exit', 'early-exit'])
async def test_unproved_listener_fails_without_any_foreign_http(mode):
    # This dummy is OUR listener, never the unknown production-port service.
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200); self.end_headers()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    assert port != 3000
    args = ('-c', 'import time; time.sleep(30)')
    if mode == 'occupied-bind-exit':
        args = ('-m', 'http.server', str(port), '--bind', '127.0.0.1')
    elif mode == 'early-exit':
        args = ('-c', 'raise SystemExit(7)')
    supervisor = Supervisor(dummy_spec(*args), retries=0)
    try:
        await supervisor.start()
        if mode != 'occupied-live-child':
            # Ensure the exited-child path is tested, not just its occupied port.
            import asyncio
            await asyncio.wait_for(asyncio.shield(supervisor.task), timeout=5)
        with pytest.raises(OwnershipError, match='not owned|exited|stopped'):
            await wait_owned_listener(supervisor, port, timeout=2)
            async with httpx.AsyncClient(trust_env=False) as client:
                await client.get(f'http://127.0.0.1:{port}/mcp')
        sent = []
        async def dispatched(request): sent.append(request.method)
        async with httpx.AsyncClient(trust_env=False, event_hooks={
                'request': [request_guard(supervisor, port, (-1, 'unproved')), dispatched]}) as client:
            with pytest.raises(OwnershipError):
                await client.get(f'http://127.0.0.1:{port}/mcp')
        assert requests == [] and sent == []
    finally:
        await supervisor.stop()
        server.shutdown(); server.server_close(); thread.join()
