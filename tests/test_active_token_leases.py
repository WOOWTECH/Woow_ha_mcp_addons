"""Real owned sockets for open streams; deterministic I/O/send races as ASGI tests.

Admin requests use the normal verified-role API with a synthetic Ingress peer.
No HA, third-party backend, production port, or child restart is used.
"""
import asyncio
from contextlib import asynccontextmanager, contextmanager
import json

import httpx
import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from batch2_owned_port import reserve_port
from mcp_admin_core.config import Store
from mcp_admin_core.gateway import make_apps
from n8n_adapter import TOOLS
from test_management_capabilities import IDENTITY

INIT = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
    'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'owned-test', 'version': '0'}}}
PING = {'jsonrpc': '2.0', 'id': 2, 'method': 'ping'}


@asynccontextmanager
async def listen(app):
    class Server(uvicorn.Server):
        @contextmanager
        def capture_signals(self):
            yield

    sock = reserve_port()
    port = sock.getsockname()[1]
    ready = asyncio.Event()

    class ReadyServer(Server):
        async def startup(self, sockets=None):
            await super().startup(sockets)
            ready.set()

    server = ReadyServer(uvicorn.Config(app, access_log=False, log_level='critical', lifespan='off',
                                       proxy_headers=False, timeout_graceful_shutdown=1))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        await asyncio.wait_for(ready.wait(), 2)
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, 3)
        finally:
            sock.close()


@asynccontextmanager
async def fixture(tmp_path, transport=None, child_url='http://mock-child/mcp'):
    store = Store(tmp_path / 'state')
    restarts = []
    async def verify(_): return True
    async def restart(state): restarts.append(state)
    async with httpx.AsyncClient(transport=transport, trust_env=False) as child:
        admin, mcp = make_apps(store, TOOLS, child, child_url=child_url, verify_admin=verify,
                              backend_changed=restart, restart_child=restart)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=admin, client=('172.30.32.2', 1)),
                                     base_url='http://admin') as management:
            boot = (await management.get('/api/bootstrap', headers=IDENTITY)).json()
            try:
                yield store, mcp, management, {**IDENTITY, 'x-csrf-token': boot['csrf']}, restarts
            finally:
                store.close()


@pytest.mark.parametrize('operation', ['revoke', 'rotate'])
@pytest.mark.parametrize('method', ['GET', 'POST'])
async def test_real_socket_two_established_streams_close_and_reissue_works(tmp_path, operation, method):
    closed = [asyncio.Event(), asyncio.Event()]
    streams = []
    sessions = []

    async def upstream(request):
        message = await request.json() if request.method == 'POST' else None
        if message and message.get('method') == 'initialize':
            session = 'owned-session-' + str(len(sessions))
            sessions.append(session)
            return JSONResponse({'jsonrpc': '2.0', 'id': 1, 'result': {
                'protocolVersion': '2025-03-26', 'serverInfo': {'name': 'owned', 'version': '0'}, 'capabilities': {}}},
                headers={'mcp-session-id': session})
        if request.method == 'DELETE':
            return JSONResponse({})
        index = len(streams)
        streams.append(request.headers['mcp-session-id'])
        async def frames():
            try:
                yield b': opened\n\n'
                await asyncio.Event().wait()
            finally:
                closed[index].set()
        return StreamingResponse(frames(), media_type='text/event-stream')

    async with listen(Starlette(routes=[Route('/mcp', upstream, methods=['GET', 'POST', 'DELETE'])])) as child_url:
        async with fixture(tmp_path, child_url=child_url + '/mcp') as (store, app, admin, headers, restarts):
            old = store.load().token
            async with listen(app) as public_url, httpx.AsyncClient(base_url=public_url, trust_env=False) as a, \
                    httpx.AsyncClient(base_url=public_url, trust_env=False) as b:
                paths = ['/mcp', '/private_' + old + '/mcp']
                auth = [{'authorization': 'Bearer ' + old}, {}]
                responses, readers = [], []
                try:
                    for client, path, authentication in zip((a, b), paths, auth):
                        initialized = await client.post(path, headers=authentication, json=INIT)
                        assert initialized.status_code == 200
                        request = client.build_request(method, path,
                            headers={**authentication, 'mcp-session-id': initialized.headers['mcp-session-id']},
                            **({'json': PING} if method == 'POST' else {}))
                        response = await client.send(request, stream=True)
                        assert response.status_code == 200
                        responses.append(response)
                        reader = response.aiter_raw()
                        assert await asyncio.wait_for(anext(reader), 2) == b': opened\n\n'
                        readers.append(reader)
                    mutation = await admin.post('/api/token/' + operation, headers=headers)
                    assert mutation.status_code == (204 if operation == 'revoke' else 200)
                    for reader in readers:
                        with pytest.raises((httpx.RemoteProtocolError, StopAsyncIteration)):
                            await asyncio.wait_for(anext(reader), 2)
                    await asyncio.wait_for(asyncio.gather(*(event.wait() for event in closed)), 2)
                    assert (await a.post(paths[0], headers=auth[0], json=INIT)).status_code == 401
                    assert (await b.post(paths[1], json=INIT)).status_code == 404
                    if operation == 'revoke':
                        assert store.load().token is None
                        mutation = await admin.post('/api/token/rotate', headers=headers)
                    new = mutation.json()['token']
                    assert new != old
                    ok = await a.post('/mcp', headers={'authorization': 'Bearer ' + new}, json=INIT)
                    assert ok.status_code == 200
                    assert restarts == []
                finally:
                    for response in responses:
                        await response.aclose()


async def asgi_get(app, token, send):
    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}
    await app({'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'}, 'http_version': '1.1',
               'method': 'GET', 'path': '/mcp', 'raw_path': b'/mcp', 'query_string': b'', 'scheme': 'http',
               'server': ('localhost', 8081), 'client': ('127.0.0.1', 1),
               'headers': [(b'authorization', ('Bearer ' + token).encode()), (b'mcp-session-id', b'owned')]},
              receive, send)


@pytest.mark.parametrize('phase', ['headers', 'send', 'coalesced'])
async def test_revocation_joins_blocked_io_and_drops_unemitted_frames(tmp_path, phase):
    reached, closed, send_cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    delivered = []
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b': first\n\n: second\n\n'
            await asyncio.Event().wait()
        async def aclose(self): closed.set()
    async def upstream(request):
        if phase == 'headers':
            reached.set()
            try: await asyncio.Event().wait()
            finally: closed.set()
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=Stream())

    async with fixture(tmp_path, httpx.MockTransport(upstream)) as (store, app, admin, headers, restarts):
        async def send(message):
            if message['type'] == 'http.response.body' and message.get('body'):
                if phase == 'send':
                    reached.set()
                    try: await asyncio.Event().wait()
                    finally: send_cancelled.set()
                elif phase == 'coalesced':
                    delivered.append(message['body'])
                    reached.set()
                    assert (await admin.post('/api/token/revoke', headers=headers)).status_code == 204
                    return
            delivered.append(message.get('body', b''))
        task = asyncio.create_task(asgi_get(app, store.load().token, send))
        try:
            await asyncio.wait_for(reached.wait(), 2)
            if phase != 'coalesced':
                assert (await admin.post('/api/token/revoke', headers=headers)).status_code == 204
            if phase == 'headers':
                await asyncio.wait_for(task, 2)
            else:
                with pytest.raises(ClientDisconnect): await asyncio.wait_for(task, 2)
            assert closed.is_set() and restarts == []
            assert b': second' not in b''.join(delivered)
            if phase == 'send': assert send_cancelled.is_set() and b': first' not in b''.join(delivered)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
