"""HM-14 test harness: a switched-on profile's gateway driven end to end, with a child a test steers.

The runtime is HM-08's (tests/multi_profile_runtime.py: run_product with the product switched on, the token dispatcher,
every profile's gate and app; the outside replaced). Here:

- GatewayChild is one profile's child behind the MockTransport (test_profile_runtime.ProfileChild's sessions and
  bearer rule) that a test can make hold its tools/calls or notifications, answer a tools/call as an event stream,
  break the connection before any header (an httpx error class) or after the first bytes of a JSON or SSE answer, and
  report the moment the connection breaks (on_break: the Supervisor sees the exit then, or later, or never);
- Exchange drives one request into an ASGI app by hand, as a server presents it: its body, then nothing until the
  client leaves (http.disconnect); a test can keep the server from taking the response's headers (a client that does
  not read: backpressure);
- quota() makes a profile's quota small or slow for a test (profiles.ProfileQuota is read when a profile is added);
- supervisor(runtime, profile) is the profile's Supervisor (NoProcessSupervisor: status and starts as the real one
  reports them), so a test can stop or replace the child generation a request went to.

No token or secret is written here: every token is made when a test runs (create_profile, secrets.token_urlsafe).
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json

import httpx

from multi_profile_runtime import create_profile, ids, stored
from mcp_admin_core import profiles
from mcp_admin_core.products import PROBES
from test_profile_runtime import ProfileChild
from test_single_profile_golden import ACCEPT, configure, initialize_message, probe_name

PRODUCT = 'odoo'
B, C = ids(2)
LABELS = {B: 'Beta Ops', C: 'Gamma Ops'}
TOOL, ARGUMENTS = PROBES[PRODUCT]
FAILURES = (httpx.ReadError, httpx.RemoteProtocolError, httpx.WriteError)


def bearer(token):
    return {**ACCEPT, 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}


def call(ident):
    return {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call', 'params': {'name': TOOL, 'arguments': ARGUMENTS}}


def ping(ident):
    """A bounded child reply: it occupies an ordinary slot without a large-reply ticket."""
    return {'jsonrpc': '2.0', 'id': ident, 'method': 'ping'}


INITIALIZED = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}


def setup(tmp_path, extras=(B,)):
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    for number, profile_id in enumerate(extras):
        create_profile(data, PRODUCT, profile_id, label=LABELS[profile_id], port=18000 + number)
    return data


def quota(monkeypatch, profile='extra', **changes):
    """The default ('default') or every additional profile's quota changed for this test (read when added)."""
    name = 'DEFAULT_PROFILE_QUOTA' if profile == 'default' else 'EXTRA_PROFILE_QUOTA'
    monkeypatch.setattr(profiles, name, replace(getattr(profiles, name), **changes))


def watch(log_scan, data, *extras):
    for directory in [data, *(profiles.Layout(data).profile(p) for p in extras)]:
        value = stored(directory)
        log_scan.watch(*(v for v in (value['token'], value['child_token']) if v))
    log_scan.watch(*(LABELS[p] for p in extras), kind='name')


def supervisor(runtime, profile_id):
    return runtime.manager.get(profile_id).runtime.supervisor


async def until(condition, seconds=10):
    async with asyncio.timeout(seconds):
        while not condition():
            await asyncio.sleep(.005)


async def session_of(client, token, url='/mcp'):
    """A session token's Bearer initialize opens (url: /mcp of the client's base, or a full URL)."""
    response = await client.post(url, headers=bearer(token), json=initialize_message())
    assert response.status_code == 200, response.status_code
    return response.headers['mcp-session-id']


class Broken(httpx.AsyncByteStream):
    """An answer's body that sends chunks, then breaks as a connection the peer closed (on_break runs right then)."""

    def __init__(self, chunks, on_break=None, error=httpx.RemoteProtocolError):
        self.chunks, self.on_break, self.error = chunks, on_break, error

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk
        await asyncio.sleep(.01)  # what came is relayed first
        if self.on_break is not None:
            self.on_break()
        raise self.error('peer closed connection without sending complete message body')

    async def aclose(self):
        pass


class GatewayChild(ProfileChild):
    """A ProfileChild a test steers (see the module docstring). Only requests in a session it opened for a client are
    steered: the readiness check's (clientInfo local-readiness) and the readiness probe always get today's answers."""

    def __init__(self, *args):
        super().__init__(*args)
        self.free = asyncio.Event()
        self.hold_calls = self.hold_initialized = self.streaming = False
        self.waiting = 0
        self.hold_ping = False
        self.fail = None          # an httpx error class: a tools/call breaks before any header
        self.broken = None        # 'json' or 'sse': a tools/call's answer breaks after its first bytes
        self.on_break = None
        self.on_initialize = None  # called once an initialize is in (before its answer)
        self.initialize_answer = None  # initialize_answer(message): the answer to a client's initialize instead
        self.reply = None         # reply(message): the answer to a client's tools/call instead (e.g. a 3xx)
        self.seen = []            # (HTTP method, JSON-RPC method, id) of every client request it got
        self.checks = set()       # sessions of the readiness check

    def authorized(self, request):
        token = json.loads(self.state.read_text())['child_token']
        return request.headers.get_list('authorization') == ['Bearer ' + token] and request.url.path == '/mcp'

    async def hold(self):
        self.waiting += 1
        try:
            await self.free.wait()
        finally:
            self.waiting -= 1

    async def __call__(self, request):
        if not self.authorized(request):
            return await super().__call__(request)
        message = json.loads(request.content) if request.content else {}
        method, session = message.get('method'), request.headers.get('mcp-session-id')
        if method == 'initialize':
            if message['params']['clientInfo']['name'] == 'local-readiness':
                response = await super().__call__(request)
                self.checks.add(response.headers.get('mcp-session-id'))
                return response
            self.seen.append((request.method, method, message.get('id')))
            if self.on_initialize is not None:
                self.on_initialize()
            if self.initialize_answer is not None:
                self.requests.append(request)
                return self.initialize_answer(message)
            return await super().__call__(request)
        if session in self.checks or session not in self.sessions:
            return await super().__call__(request)
        self.seen.append((request.method, method, message.get('id')))
        if request.method == 'GET':
            self.requests.append(request)
            free = self.free

            async def events():
                yield b': open\n\n'
                await free.wait()
            if self.broken == 'sse' or self.fail is not None:
                if self.fail is not None:
                    if self.on_break is not None:
                        self.on_break()
                    raise self.fail('the child connection broke', request=request)
                return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                                      stream=Broken([b': open\n\n'], self.on_break))
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=events())
        if method == 'notifications/initialized' and self.hold_initialized:
            self.requests.append(request)
            await self.hold()
            return httpx.Response(202)
        if method == 'ping' and self.hold_ping:
            await self.hold()
            return await super().__call__(request)
        if method == 'tools/call' and message['params']['name'] != probe_name(self.product):
            ident = message['id']
            if self.reply is not None:
                self.requests.append(request)
                return self.reply(message)
            if self.fail is not None:
                self.requests.append(request)
                if self.on_break is not None:
                    self.on_break()
                raise self.fail('the child connection broke', request=request)
            if self.broken == 'json':
                self.requests.append(request)
                return httpx.Response(200, headers={'content-type': 'application/json'}, stream=Broken(
                    [b'{"jsonrpc":"2.0","id":' + json.dumps(ident).encode() + b',"result":{"too'], self.on_break))
            if self.broken == 'sse':
                self.requests.append(request)
                return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                                      stream=Broken([b': working\n\n'], self.on_break))
            if self.streaming:
                self.requests.append(request)
                free = self.free

                async def reply():
                    yield b': working\n\n'
                    await free.wait()
                    yield b'data: ' + json.dumps({'jsonrpc': '2.0', 'id': ident, 'result': {
                        'content': [{'type': 'text', 'text': 'streamed'}], 'isError': False}}).encode() + b'\n\n'
                return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=reply())
            if self.hold_calls:
                await self.hold()
        return await super().__call__(request)

    def client_calls(self):
        """The ids of the client tools/calls this child got."""
        return [ident for method, rpc, ident in self.seen if rpc == 'tools/call']

    def client_pings(self):
        """The ids of bounded control requests the child got."""
        return [ident for method, rpc, ident in self.seen if rpc == 'ping']


class Exchange:
    """One request into an ASGI app driven by hand (see the module docstring). hold_start: the server does not take
    the response's first headers until let_through() (a cancelled send took nothing, as uvicorn's send waiting to
    write; headers sent after a cancelled first attempt go out); hold_all: it never takes any header. sent: every
    message the server took."""

    def __init__(self, app, method, path, headers=(), body=b'', *, hold_start=False, hold_all=False):
        self.app, self.method, self.path, self.headers, self.body = app, method, path, list(headers), body
        self.hold_start, self.hold_all = hold_start, hold_all
        self.sent, self.attempts = [], []
        self.gone, self.blocked, self.unblocked = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self.body_read = False
        self.task = None

    def scope(self):
        return {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': self.method,
                'scheme': 'http', 'path': self.path, 'raw_path': self.path.encode(), 'query_string': b'',
                'root_path': '', 'server': ('mcp', 80), 'client': ('127.0.0.1', 1),
                'headers': [(k.lower().encode(), v.encode()) for k, v in self.headers]}

    async def receive(self):
        if not self.body_read:
            self.body_read = True
            return {'type': 'http.request', 'body': self.body, 'more_body': False}
        await self.gone.wait()
        return {'type': 'http.disconnect'}

    async def send(self, message):
        if message['type'] == 'http.response.start':
            self.attempts.append(message['status'])
            # hold_start: the first headers wait (a later answer, the gateway's own refusal, goes out); hold_all: all do
            if self.hold_all or self.hold_start and len(self.attempts) == 1 and not self.unblocked.is_set():
                self.blocked.set()
                await (asyncio.Event().wait() if self.hold_all else self.unblocked.wait())
        self.sent.append(message)

    def start(self):
        self.task = asyncio.create_task(self.app(self.scope(), self.receive, self.send))
        return self

    def leave(self):
        self.gone.set()

    def let_through(self):
        self.unblocked.set()

    @property
    def status(self):
        starts = [m['status'] for m in self.sent if m['type'] == 'http.response.start']
        return starts[0] if starts else None

    @property
    def response_headers(self):
        starts = [m for m in self.sent if m['type'] == 'http.response.start']
        return sorted((k.decode(), v.decode()) for k, v in starts[0]['headers']) if starts else None

    @property
    def content(self):
        return b''.join(m.get('body', b'') for m in self.sent if m['type'] == 'http.response.body')

    @property
    def ended(self):
        """The last body message went out (more_body false): a complete answer."""
        return any(m['type'] == 'http.response.body' and not m.get('more_body', False) for m in self.sent)


def json_body(token, message, session=None):
    """(headers, body) of a Bearer POST of message (in session when given)."""
    headers = [(k, v) for k, v in bearer(token).items()]
    if session is not None:
        headers.append(('mcp-session-id', session))
    return headers, json.dumps(message).encode()


def sse_messages(body):
    out = []
    for event in body.replace(b'\r\n', b'\n').split(b'\n\n'):
        data = b'\n'.join(line[5:].lstrip() for line in event.split(b'\n') if line.startswith(b'data:'))
        if data:
            out.append(json.loads(data))
    return out
