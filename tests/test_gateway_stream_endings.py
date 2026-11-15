"""HM-14: how a switched-on profile's answers end when the child's connection breaks or the token changes mid-answer
(multi-profile plan 12.3 HM-14; contract 2.5, 4.2; FM-34, FM-44; the PaaS #148 gateway, woow-mcp-server 69ac425:
proxy.py, mcp_access.py, initialize_fence.py; its tests packages/mcp-admin-core/tests/test_proxy_interrupted_cause.py
and test_initialize_fence_backpressure.py).

The child's connection breaks while it handles a request (a read, write or protocol error once it was reached):

| When | Switched on (HM-14) | Switched off (today, pinned here byte for byte) |
|---|---|---|
| before the answer's headers | 502 + the gateway's own -32004 (under the request's id when it has one) | 502 {"error":"request denied"} |
| on an event stream | one -32004 event under the POST's id, then the stream ends | the stream ends quietly |

Its text says whether the child generation the request went to has stopped (exited, stopped or replaced; looked at for
up to 0.25 s, since the broken connection may come a moment before the Supervisor sees the exit) or still runs, and
both say the operation may or may not have completed. The profile's WARNING names the HTTP method and the error's class,
with no traceback, path, token or body. A connection that could not be made, a slow child and a child's wrong answer
(3xx, 401, 403, a malformed or oversize reply, an unreviewed protocol version) keep their 502 {"error":"request denied"}.

The token is rotated or revoked once the answer began to go out (gateway.Ending, access.LeasedResponse):

| How far the answer got | Switched on | Switched off (today) |
|---|---|---|
| its headers were not taken (a client not reading) | the clean refusal: Bearer 401 {"error":"request denied"}, secret path 404 | ClientDisconnect to the server (a traceback, 500) |
| an event stream started | one -32005 event under the POST's id (none for a GET), then the end | ClientDisconnect (a traceback) |
| a buffered answer's headers went out | nothing more can be sent (its Content-Length is fixed): the gateway returns, the server closes the connection | ClientDisconnect (a traceback) |

Nothing is raised to the server; a client that reads nothing gets nothing after ENDING_SECONDS (PaaS: 2 s).
tests/test_active_token_leases.py keeps pinning the switched-off rows.
"""
import asyncio
import json
import logging
import secrets
import socket
import struct

import httpx
import pytest
from starlette.responses import Response

from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import Children, RealChild, create_profile, multi_profile_runtime
from mcp_admin_core import access, gateway, profiles
from mcp_admin_core.access import AccessChanged
from switched_gateway import (B, FAILURES, LABELS, PRODUCT, Broken, Exchange, GatewayChild, bearer, call, json_body,
                              session_of, setup, sse_messages, supervisor, until, watch)
from test_single_profile_golden import (ACCEPT, NOT_FOUND, answer, configure, initialize_message, settle)

pytestmark = pytest.mark.usefixtures('log_scan')
# read when the module loads (None without HM-14: each test then fails on its own, the red half)
STOPPED = getattr(gateway, 'CHILD_STOPPED_TEXT', None)
CONNECTION = getattr(gateway, 'CHILD_CONNECTION_TEXT', None)
DENIED_502 = (502, [('content-length', '26'), ('content-type', 'application/json')], b'{"error":"request denied"}')
DENIED_401 = (401, [('content-length', '26'), ('content-type', 'application/json')], b'{"error":"request denied"}')


def interrupted(response, ident, text):
    assert response.status_code == 502 and response.headers['cache-control'] == 'no-store'
    assert response.headers['content-type'] == 'application/json' and 'retry-after' not in response.headers
    assert response.json() == {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32004, 'message': text}}


def child_runtime(tmp_path, **kwargs):
    data = setup(tmp_path)
    children = Children()
    children.add(3000, GatewayChild('default', PRODUCT, data))
    child = children.add(18000, GatewayChild('p' + B[:4], PRODUCT, profiles.Layout(data).profile(B)))
    return data, children, child


def warnings_of(log_scan):
    return [record for record in log_scan.records
            if record.name == 'mcp_admin_core.profile_router' and record.levelno == logging.WARNING]


def rotate(runtime, profile_id, action='rotate'):
    """The panel's token rotate or revoke as admin_action commits it: the store, then TokenAccess.committed()."""
    profile = runtime.manager.get(profile_id).runtime
    new = secrets.token_urlsafe(32) if action == 'rotate' else None
    profile.store.change_token(new, action=action)
    profile.token_access.committed()
    return new


# ---- -32004 before the headers (PaaS test_proxy_interrupted_cause.py cases 1-4, 7) ----

@pytest.mark.parametrize('error', FAILURES, ids=lambda error: error.__name__)
async def test_a_connection_broken_with_the_child_still_running_says_so(tmp_path, log_scan, error):
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            child.fail = error
            loop = asyncio.get_running_loop()
            started = loop.time()
            interrupted(await client.post('/mcp', headers=headers, json=call(7)), 7, CONNECTION)
            assert loop.time() - started < 3  # the look for an exit is short (0.25 s)
            assert 'still running' in CONNECTION and '子程式仍在執行' in CONNECTION
            assert 'may or may not have completed' in CONNECTION and '可能已完成也可能沒有' in CONNECTION
            assert supervisor(runtime, B).status == 'running'


@pytest.mark.parametrize('how', ['exited', 'generation replaced'])
async def test_a_child_that_stopped_during_the_request_is_reported_stopped(tmp_path, log_scan, monkeypatch, how):
    monkeypatch.setattr(gateway, 'CHILD_EXIT_GRACE_SECONDS', 3.0)  # a wait would show (a stop already seen needs none)
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token, child_supervisor = runtime.token(B), supervisor(runtime, B)

        def stop():
            if how == 'exited':
                child_supervisor.status = 'backoff'
            else:  # restarted: a new process, a new generation
                child_supervisor.starts += 1
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            child.fail, child.on_break = httpx.ReadError, stop
            loop = asyncio.get_running_loop()
            started = loop.time()
            interrupted(await client.post('/mcp', headers=headers, json=call(7)), 7, STOPPED)
            assert loop.time() - started < 1.5, 'a stop already seen needs no wait'
            assert 'restarts automatically' in STOPPED and '會自動重新啟動' in STOPPED
            assert 'may or may not have completed' in STOPPED


async def test_the_supervisor_noticing_the_exit_a_moment_later_still_reports_stopped(tmp_path, log_scan,
                                                                                    monkeypatch):
    """The connection breaks first and the Supervisor sees the exit 50 ms later (the reaping and the pipes' end come
    after): the gateway looks for it (its grace made 3 s here, for a slow runner) and reports the stop."""
    monkeypatch.setattr(gateway, 'CHILD_EXIT_GRACE_SECONDS', 3.0)
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token, child_supervisor = runtime.token(B), supervisor(runtime, B)

        def later():
            asyncio.get_running_loop().call_later(.05, setattr, child_supervisor, 'status', 'backoff')
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            child.fail, child.on_break = httpx.ReadError, later
            interrupted(await client.post('/mcp', headers=headers, json=call(7)), 7, STOPPED)


async def test_a_get_stream_and_a_buffered_answer_follow_the_same_rule(tmp_path, log_scan):
    """A GET whose connection breaks before its headers: 502, -32004 id null (it answers no request). A JSON answer
    that breaks after its first bytes (PaaS: the buffered tools/list): 502, -32004 under the request's id, the text
    by the cause. (A batch, PaaS's other case, never reaches an HA child: policy.authorize refuses it, 403.)"""
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token, child_supervisor = runtime.token(B), supervisor(runtime, B)
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            child.fail = httpx.ReadError
            interrupted(await client.get('/mcp', headers=headers), None, CONNECTION)
            child.fail, child.broken = None, 'json'
            interrupted(await client.post('/mcp', headers=headers, json=call(3)), 3, CONNECTION)
            child.on_break = lambda: setattr(child_supervisor, 'status', 'backoff')
            interrupted(await client.post('/mcp', headers=headers, json=call(4)), 4, STOPPED)
            batch = await client.post('/mcp', headers=headers, json=[call(5), call(6)])
            assert answer(batch)[0] == 403


@pytest.mark.parametrize('stopped', [False, True], ids=['still running', 'stopped'])
async def test_an_initialize_answer_broken_mid_body_gets_minus_32004_and_no_session(tmp_path, log_scan, stopped):
    """Contract 2.5 (HM-14 review S-2: R05, R06): the child's initialize answer breaks after its first bytes: 502 + the
    gateway's -32004 under the initialize's id, its text by the cause, and no session id. The session the child opened
    for it gets the gateway's one DELETE only while the child still runs; a stopped child took it with it (a DELETE
    would reach the next generation). The DELETE is done before the answer goes out (UpstreamOwner.close)."""
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token, child_supervisor = runtime.token(B), supervisor(runtime, B)

        def on_break():
            if stopped:
                child_supervisor.status = 'backoff'
        child.initialize_answer = lambda message: httpx.Response(
            200, headers={'content-type': 'application/json', 'mcp-session-id': 'broken-session-1'},
            stream=Broken([b'{"jsonrpc":"2.0","id":1,"res'], on_break))
        async with runtime.mcp() as client:
            response = await client.post('/mcp', headers=bearer(token), json=initialize_message())
        interrupted(response, 1, STOPPED if stopped else CONNECTION)
        assert 'mcp-session-id' not in response.headers
        deletes = [request for request in child.requests
                   if request.method == 'DELETE' and request.headers.get('mcp-session-id') == 'broken-session-1']
        assert len(deletes) == (0 if stopped else 1)
        lines = [record.getMessage() for record in warnings_of(log_scan)]
        assert len(lines) == 1 and 'a POST request' in lines[0] and 'answered -32004' in lines[0], lines


# ---- -32004 on an event stream (PaaS cases 5, 6) ----

@pytest.mark.parametrize('stopped', [False, True], ids=['still running', 'stopped'])
async def test_an_event_stream_broken_mid_reply_gets_one_minus_32004_event_and_ends(tmp_path, log_scan, stopped):
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token, child_supervisor = runtime.token(B), supervisor(runtime, B)
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            child.broken = 'sse'
            if stopped:
                child.on_break = lambda: setattr(child_supervisor, 'status', 'backoff')
            response = await client.post('/mcp', headers=headers, json=call(7))  # read to its end: no error
            assert response.status_code == 200 and response.headers['content-type'] == 'text/event-stream'
            assert response.content.startswith(b': working\n\n')
            events = sse_messages(response.content)
            assert events == [{'jsonrpc': '2.0', 'id': 7, 'error': {'code': -32004,
                                                                     'message': STOPPED if stopped else CONNECTION}}]
            assert response.content.endswith(gateway.gateway_event(7, -32004, STOPPED if stopped else CONNECTION))
            child.on_break = None
            child_supervisor.status = 'running'  # (restarted) so that the GET below reaches it
            stream = await client.get('/mcp', headers=headers)  # a GET stream answers no request: it just ends
            assert stream.status_code == 200 and sse_messages(stream.content) == []


async def test_the_log_line_names_the_cause_without_a_traceback_or_token(tmp_path, log_scan):
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            child.fail = httpx.ReadError
            for ident in (7, 8):  # one line a minute per profile and cause
                await client.post('/mcp', headers=headers, json=call(ident))
        lines = warnings_of(log_scan)
        assert [record.getMessage() for record in lines] == [
            f'MCP gateway [profile={B[:8]}]: the connection to its MCP server broke while it handled a POST request '
            '(ReadError); the MCP server is still running; answered -32004']
        assert lines[0].exc_info is None and lines[0].stack_info is None
        assert not [r for r in log_scan.records if r.levelno >= logging.ERROR or r.exc_info]


class ResettingChild:
    """A real loopback child of just enough HTTP/1.1 (PaaS case 9's real child, without a process): only its
    profile's child bearer is served; an initialize opens a session; a tools/call has its connection reset (SO_LINGER
    0: an RST, as when the process dies) the moment on_break runs."""

    def __init__(self, directory):
        self.directory = directory
        self.on_break = None
        self.server = None

    async def start(self):
        self.server = await asyncio.start_server(self.handle, '127.0.0.1', 0)
        self.port = self.server.sockets[0].getsockname()[1]
        assert self.port != 3000 and self.port not in range(18000, 18100)

    async def handle(self, reader, writer):
        try:
            while True:
                head = (await reader.readuntil(b'\r\n\r\n')).decode('latin-1').split('\r\n')
                fields = dict(line.split(': ', 1) for line in head[1:] if ': ' in line)
                fields = {key.lower(): value for key, value in fields.items()}
                body = await reader.readexactly(int(fields.get('content-length', '0')))
                token = json.loads((self.directory / 'state.json').read_text())['child_token']
                message = json.loads(body) if body else {}
                if fields.get('authorization') != 'Bearer ' + token:
                    writer.write(b'HTTP/1.1 401 Unauthorized\r\ncontent-length: 0\r\n\r\n')
                elif message.get('method') == 'initialize':
                    payload = json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {
                        'protocolVersion': message['params']['protocolVersion'], 'capabilities': {'tools': {}},
                        'serverInfo': {'name': 'resetting-child', 'version': '0'}}}).encode()
                    writer.write(b'HTTP/1.1 200 OK\r\ncontent-type: application/json\r\nmcp-session-id: reset-1\r\n'
                                 b'content-length: %d\r\n\r\n' % len(payload) + payload)
                elif 'id' not in message:
                    writer.write(b'HTTP/1.1 202 Accepted\r\ncontent-length: 0\r\n\r\n')
                else:
                    if self.on_break is not None:
                        self.on_break()
                    writer.get_extra_info('socket').setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                                                               struct.pack('ii', 1, 0))
                    writer.transport.abort()
                    return
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()


async def test_a_real_connection_reset_mid_request_is_reported(tmp_path, log_scan):
    """The real httpx transport (not a MockTransport raising the error itself) on a real connection the child resets
    while it handles the call, the Supervisor seeing the exit at that moment: 502 + -32004 under the call's id with the
    stopped text. (A real process killed mid-request is exercised in the HAOS acceptance; the Supervisor here is the
    tests' NoProcessSupervisor.)"""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    layout = profiles.Layout(data)
    default_child = RealChild(data, PRODUCT)
    resetting = ResettingChild(layout.profile(B))
    await resetting.start()
    create_profile(data, PRODUCT, B, label=LABELS[B], port=resetting.port)
    await default_child.start()
    try:
        async with multi_profile_runtime(PRODUCT, data, real_children=True, default_port=default_child.port) as runtime:
            watch(log_scan, data, B)
            token, child_supervisor = runtime.token(B), supervisor(runtime, B)
            resetting.on_break = lambda: setattr(child_supervisor, 'status', 'backoff')
            async with runtime.mcp() as client:
                headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
                interrupted(await client.post('/mcp', headers=headers, json=call(7)), 7, STOPPED)
            lines = [record.getMessage() for record in warnings_of(log_scan)]
            assert len(lines) == 1 and 'the MCP server stopped' in lines[0], lines
            assert any(name in lines[0] for name in ('ReadError', 'RemoteProtocolError')), lines
    finally:
        await default_child.stop()
        await resetting.stop()


# ---- -32005 and the clean refusal (PaaS test_initialize_fence_backpressure.py, mcp_access) ----

async def test_a_token_rotated_mid_stream_ends_it_with_one_minus_32005_event(tmp_path, log_scan):
    """B's tools/call answered as an event stream that has started (': working' delivered): the token is rotated. The
    child's reply never goes out; the stream gets one -32005 event under the call's id and ends normally (its last
    message has more_body false); nothing is raised. A GET stream rotated the same way just ends."""
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            session = await session_of(client, token)
        child.streaming = True
        exchange = Exchange(runtime.mcp_app, 'POST', '/mcp', *json_body(token, call(7), session)).start()
        await until(lambda: b': working' in exchange.content)
        log_scan.watch(rotate(runtime, B))
        await asyncio.wait_for(exchange.task, 5)
        assert exchange.task.exception() is None and exchange.status == 200 and exchange.ended
        assert exchange.content == b': working\n\n' + gateway.gateway_event(7, -32005, gateway.ACCESS_CHANGED_TEXT)
        assert 'rotated or revoked' in gateway.ACCESS_CHANGED_TEXT and '輪替或撤銷' in gateway.ACCESS_CHANGED_TEXT
        child.free.set()
        token = runtime.token(B)
        async with runtime.mcp() as client:
            session = await session_of(client, token)
        stream_headers = [(k, v) for k, v in bearer(token).items()] + [('mcp-session-id', session)]
        stream = Exchange(runtime.mcp_app, 'GET', '/mcp', stream_headers).start()
        child.free = asyncio.Event()
        await until(lambda: b': open' in stream.content)
        rotate(runtime, B, 'revoke')
        await asyncio.wait_for(stream.task, 5)
        assert stream.task.exception() is None and stream.ended and stream.content == b': open\n\n'


async def test_a_reply_delivered_before_the_token_changed_gets_no_minus_32005(tmp_path, log_scan):
    """The stream's reply went out, then the token changed before the stream's last message: the client already has
    its answer, so no -32005 follows it; the stream just ends (nothing raised)."""
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            session = await session_of(client, token)
        child.streaming = True
        child.free.set()  # the child answers at once
        rotated = []

        class Rotating(Exchange):
            async def send(self, message):
                await super().send(message)
                if message['type'] == 'http.response.body' and b'"result"' in message.get('body', b''):
                    rotated.append(rotate(runtime, B))  # the reply was taken, then the token changed
        exchange = Rotating(runtime.mcp_app, 'POST', '/mcp', *json_body(token, call(7), session)).start()
        await asyncio.wait_for(exchange.task, 5)
        log_scan.watch(*rotated)
        assert rotated and exchange.task.exception() is None and exchange.ended
        assert [message['id'] for message in sse_messages(exchange.content)] == [7]
        assert sse_messages(exchange.content)[0]['result']['content'][0]['text'] == 'streamed'


async def test_the_minus_32004_event_is_the_answer_and_no_minus_32005_follows_it(tmp_path, log_scan):
    """HM-14 review S-1 (plan 8.8 #95): the gateway's own -32004 event answers the POST as a reply does. The child's
    stream broke, the server took the -32004 event, then the token changed before the stream's last message: no
    -32005 follows under the same id (JSON-RPC: one answer per request) and the stream ends normally, nothing raised.
    (PaaS adds the -32005 there: its _Interruption knows only the child's replies.)"""
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            session = await session_of(client, token)
        child.broken = 'sse'
        rotated = []

        class Rotating(Exchange):
            async def send(self, message):
                await super().send(message)
                if message['type'] == 'http.response.body' and b'-32004' in message.get('body', b''):
                    rotated.append(rotate(runtime, B))  # the server took the -32004 event, then the token changed
        exchange = Rotating(runtime.mcp_app, 'POST', '/mcp', *json_body(token, call(7), session)).start()
        await asyncio.wait_for(exchange.task, 10)
        log_scan.watch(*rotated)
        assert rotated and exchange.task.exception() is None and exchange.ended
        assert [(event['id'], event['error']['code']) for event in sse_messages(exchange.content)] == [(7, -32004)]


async def test_a_reply_the_server_had_not_taken_when_the_token_changed_gets_minus_32005(tmp_path, log_scan):
    """HM-14 review S-2 (R22): the reply's event waits for the server (its client does not read) when the token
    changes; the cancelled send took nothing, so the reply was not delivered: the stream gets one -32005 under its id
    and none of the child's reply, then ends normally."""
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            session = await session_of(client, token)
        child.streaming = True
        child.free.set()  # the child answers at once
        held = asyncio.Event()

        class Stuck(Exchange):
            async def send(self, message):
                if (message['type'] == 'http.response.body' and b'"result"' in message.get('body', b'')
                        and not held.is_set()):
                    held.set()
                    await asyncio.Event().wait()  # the server never takes the reply (a cancelled send took nothing)
                await super().send(message)
        exchange = Stuck(runtime.mcp_app, 'POST', '/mcp', *json_body(token, call(7), session)).start()
        await asyncio.wait_for(held.wait(), 5)
        log_scan.watch(rotate(runtime, B))
        await asyncio.wait_for(exchange.task, 5)
        assert exchange.task.exception() is None and exchange.ended and b'"result"' not in exchange.content
        assert [(event['id'], event['error']['code']) for event in sse_messages(exchange.content)] == [(7, -32005)]


async def test_a_token_changed_as_the_last_message_is_taken_adds_nothing_after_it(tmp_path, log_scan):
    """HM-14 review S-2 (R12): the token changes in the very instant the server takes the stream's last message: the
    answer is complete, so the gateway sends nothing after it (one last message; uvicorn raises on a message after a
    complete response, with a traceback)."""
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            session = await session_of(client, token)
        child.streaming = True
        child.free.set()
        rotated = []

        class Rotating(Exchange):
            async def send(self, message):
                await super().send(message)
                if (message['type'] == 'http.response.body' and not message.get('more_body', False)
                        and not rotated):
                    rotated.append(rotate(runtime, B))  # the last message was taken, then the token changed
        exchange = Rotating(runtime.mcp_app, 'POST', '/mcp', *json_body(token, call(7), session)).start()
        await asyncio.wait_for(exchange.task, 5)
        log_scan.watch(*rotated)
        assert rotated and exchange.task.exception() is None
        lasts = [m for m in exchange.sent if m['type'] == 'http.response.body' and not m.get('more_body', False)]
        assert len(lasts) == 1, exchange.sent
        assert [message['id'] for message in sse_messages(exchange.content)] == [7]


@pytest.mark.parametrize('path', ['bearer', 'secret'])
async def test_a_token_changed_while_the_headers_wait_gets_the_clean_refusal_and_no_exception(tmp_path, log_scan,
                                                                                             path):
    """The answer's headers are not taken (the client does not read) when the token is rotated: the gateway sends the
    refusal a changed token gets before an answer starts, byte for byte (Bearer 401 {"error":"request denied"}, secret
    path 404 Not Found), and none of the child's bytes; nothing is raised. Afterwards the old token stays refused (PaaS
    test_old_token_stays_rejected_after_the_fence_answered)."""
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        target = '/mcp' if path == 'bearer' else f'/private_{token}/mcp'
        async with runtime.mcp() as client:
            session = await session_of(client, token)
        request_headers, body = json_body(token, call(7), session)
        if path == 'secret':
            request_headers = [(k, v) for k, v in request_headers if k != 'Authorization']
        exchange = Exchange(runtime.mcp_app, 'POST', target, request_headers, body, hold_start=True).start()
        await asyncio.wait_for(exchange.blocked.wait(), 5)
        log_scan.watch(rotate(runtime, B))
        await asyncio.wait_for(exchange.task, 5)
        assert exchange.task.exception() is None and exchange.attempts == [200, 401 if path == 'bearer' else 404]
        expected = DENIED_401 if path == 'bearer' else NOT_FOUND
        assert (exchange.status, exchange.response_headers, exchange.content) == expected
        assert b'profile tool result' not in exchange.content
        # the same bytes as the refusal raised before any answer starts (the token changes while the child works)
        child.hold_calls = True
        new = runtime.token(B)
        async with runtime.mcp() as client:
            session = await session_of(client, new)
            if path == 'bearer':
                pending = asyncio.create_task(client.post('/mcp', headers={**bearer(new), 'Mcp-Session-Id': session},
                                                          json=call(8)))
            else:
                pending = asyncio.create_task(client.post(f'/private_{new}/mcp', json=call(8), headers={
                    **ACCEPT, 'Content-Type': 'application/json', 'Mcp-Session-Id': session}))
            await until(lambda: child.waiting == 1)
            log_scan.watch(rotate(runtime, B))
            raised = await pending
            assert answer(raised) == expected
            old = await client.post(target if path == 'bearer' else f'/private_{token}/mcp', json=call(9),
                                    headers={**bearer(token), 'Mcp-Session-Id': session})
            assert answer(old)[0] == (401 if path == 'bearer' else 404)
        child.free.set()


async def test_a_token_changed_as_the_headers_are_taken_ends_without_an_exception(tmp_path, log_scan):
    """A buffered answer (JSON, its Content-Length set: HM-01's golden bytes) whose headers were taken in the very
    instant the token changed: its body is not sent (it would be the child's bytes after the change) and cannot be
    replaced; the gateway returns without raising and the server closes the connection (PaaS sends -32005 there: its
    answers carry no Content-Length; plan 8.8, contract 2.5)."""
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            session = await session_of(client, token)
        rotated = []

        class Rotating(Exchange):
            async def send(self, message):
                await super().send(message)
                if message['type'] == 'http.response.start':
                    rotated.append(rotate(runtime, B))  # the headers were taken, then the token changed
        exchange = Rotating(runtime.mcp_app, 'POST', '/mcp', *json_body(token, call(7), session)).start()
        await asyncio.wait_for(exchange.task, 5)
        log_scan.watch(*rotated)
        assert exchange.task.exception() is None and exchange.status == 200
        assert not exchange.ended and exchange.content == b''


async def test_a_client_that_reads_nothing_does_not_hold_the_ending(tmp_path, log_scan, monkeypatch):
    """No header is ever taken (the client reads nothing): the gateway's 401 cannot go out either; after ENDING_SECONDS
    (0.2 s here) it gives up and returns, raising nothing (the server then logs one line and answers 500 to a client
    that reads again; PaaS's known trade-off)."""
    monkeypatch.setattr(gateway, 'ENDING_SECONDS', .2)
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            session = await session_of(client, token)
        exchange = Exchange(runtime.mcp_app, 'POST', '/mcp', *json_body(token, call(7), session), hold_all=True).start()
        await asyncio.wait_for(exchange.blocked.wait(), 5)
        log_scan.watch(rotate(runtime, B))
        await asyncio.wait_for(exchange.task, 5)
        assert exchange.task.exception() is None and exchange.attempts == [200, 401] and exchange.sent == []


class Lease:
    """A token lease for LeasedResponse alone: changed() makes check() and run() raise AccessChanged."""

    def __init__(self):
        self.changed = False

    def check(self):
        if self.changed:
            raise AccessChanged()

    async def run(self, operation):
        self.check()
        result = await operation()
        self.check()
        return result


@pytest.mark.parametrize('error', [ValueError('boom'), KeyError('k'), asyncio.CancelledError()],
                         ids=['ValueError', 'KeyError', 'CancelledError'])
async def test_only_a_changed_token_is_ended_never_another_error(error):
    """PaaS N6: the ending handles a changed token only. Any other error of the answer (a cancellation too) goes on as
    before, the ending is never called; a token changed before the answer started keeps today's refusal (raised,
    error_handler answers it)."""
    called = []

    async def ending(*args):
        called.append(args)

    class Failing(Response):
        async def __call__(self, scope, receive, send):
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            raise error

    class Refused(Exception):
        pass

    async def send(message):
        pass
    leased = access.LeasedResponse(Failing(), Lease(), Refused, ending)
    with pytest.raises(type(error)):
        await leased({'type': 'http'}, None, send)
    assert called == []
    lease = Lease()
    lease.changed = True
    refusal = access.LeasedResponse(Response(b'x'), lease, Refused, ending)
    with pytest.raises(Refused):
        await refusal({'type': 'http'}, None, send)
    assert called == []


# ---- switched off: today's bytes (contract 4.2, handed to HM-14 by HM-01's provenance note 4.2) ----

def wrong(kind):
    """A child's wrong answer to a tools/call: today's 502 {"error":"request denied"}, switched on or off."""
    if kind == 'redirect':
        return lambda message: httpx.Response(307, headers={'location': 'http://127.0.0.1:1/elsewhere'})
    if kind == 'refused':
        return lambda message: httpx.Response(403)
    if kind == 'unauthorized':
        return lambda message: httpx.Response(401)
    if kind == 'malformed':
        return lambda message: httpx.Response(200, headers={'content-type': 'application/json'}, content=b'{"jsonrpc"')
    if kind == 'another id':
        return lambda message: httpx.Response(200, json={'jsonrpc': '2.0', 'id': message['id'] + 1, 'result': {}})
    if kind == 'oversize':
        return lambda message: httpx.Response(200, headers={'content-type': 'application/json'},
                                              content=b'{"jsonrpc":"2.0","id":%d,"result":{"x":"' % message['id']
                                              + b'x' * gateway.MAX_RESPONSE + b'"}}')
    raise AssertionError(kind)


@pytest.mark.parametrize('switch', [False, True], ids=['switched off', 'switched on'])
async def test_a_childs_wrong_answer_keeps_todays_502(tmp_path, log_scan, switch):
    """3xx, 401/403, a malformed, mismatched or oversize reply, an unreviewed protocol version: 502 {"error":"request
    denied"}, byte for byte, whether or not the product is switched on (-32004 is for a broken connection only)."""
    data, children, child = child_runtime(tmp_path)
    profile = B if switch else 'default'
    if not switch:
        child = children.by_port[3000]
    async with multi_profile_runtime(PRODUCT, data, children=children, switch=switch) as runtime:
        await settle(runtime, 'configured')
        token = runtime.token(profile)
        log_scan.watch(token)
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            for kind in ('redirect', 'refused', 'unauthorized', 'malformed', 'another id', 'oversize'):
                child.reply = wrong(kind)
                assert answer(await client.post('/mcp', headers=headers, json=call(7))) == DENIED_502, kind
            child.reply = None
            child.fail = httpx.ReadTimeout  # a slow child is no broken connection
            assert answer(await client.post('/mcp', headers=headers, json=call(8))) == DENIED_502
            child.fail = None
            child.initialize_answer = lambda message: httpx.Response(200, json={
                'jsonrpc': '2.0', 'id': message['id'], 'result': {'protocolVersion': '2024-06-25', 'capabilities': {},
                                                                  'serverInfo': {'name': 'x', 'version': '0'}}})
            assert answer(await client.post('/mcp', headers=bearer(token), json=initialize_message())) == DENIED_502


async def test_switched_off_a_broken_connection_keeps_todays_answers(tmp_path, log_scan):
    """The repository: a connection broken before the headers is 502 {"error":"request denied"} (byte for byte) and
    a stream broken mid-reply ends quietly, without any event; no -32004 and no WARNING."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    children = Children()
    child = children.add(3000, GatewayChild('default', PRODUCT, data))
    async with multi_profile_runtime(PRODUCT, data, switch=False, children=children) as runtime:
        await settle(runtime, 'configured')
        token = runtime.token('default')
        log_scan.watch(token)
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            for error in FAILURES:
                child.fail = error
                assert answer(await client.post('/mcp', headers=headers, json=call(7))) == DENIED_502, error
            child.fail, child.broken = None, 'json'
            assert answer(await client.post('/mcp', headers=headers, json=call(8))) == DENIED_502
            child.broken = 'sse'
            response = await client.post('/mcp', headers=headers, json=call(9))
            assert response.status_code == 200 and response.content == b': working\n\n'
        assert warnings_of(log_scan) == []
