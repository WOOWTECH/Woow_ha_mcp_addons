"""HM-08: every profile's own admission, byte budget, forwarding slots, GET streams and child client, the default
profile's included (multi-profile plan 5.2; contract 2.4, 4.2, 5; invariant I8; DQ-07 (a); C1-M5, C3-MF-2, C3-SF-1;
FM-49, 50, 149, 150). HM-31 merged the byte budget with the PaaS #155 one (contract 2.4, 5; woow-mcp-server d7f5849).

Once a product is switched on, the dispatcher admits a request of a profile before its body is read (64 for the
default profile, 32 for each additional one) and caps the profile's open GET streams (24, 8). Each profile's app has its
own forwarding slots (32, 16; one second's wait) and its own child client (40, 24 connections), and charges the
profile's share of the add-on's one request body budget (HM-31: min(the profile's quota, 64 MiB, half the add-on's
budget, at least 16 MiB)) with a large request's body (over 64 KiB: the larger of what was read and what is forwarded,
re-serialized with ASCII escapes) until the request ends (HM-08 review MF-1, S-1: an event stream's headers come before
the tool runs, and the gateway's forwarded copy of the body stays referenced until the stream ends). One profile's
requests never take another profile's slots or share; the add-on's budget is the one pool they share (PaaS).

The busy answers follow the PaaS table (docs/mcp-gateway-limits.md "超過上限時用戶端拿到什麼" and the budget's,
woow-mcp-server d7f5849) with HA's one deviation (plan 8.8 #16): beyond the profile's admission, a POST of at most 64 KiB
is read (HM-31, MF-2 (b)): one that carries no request goes on (the reserve), any other gets 200, Retry-After 5 and a
-32003 error under its id; a larger one, a GET or a DELETE gets 503, Retry-After 5, id null, unread. A large body the
budget cannot hold is refused before it is read and drained, its id from its head and tail (200 + -32003 under it, else
503). A forwarding slot that stays busy for a second: the same shapes (#148). A full GET stream cap: 429, Retry-After
30. Each comes with one WARNING per profile and situation a minute (id's first 8 characters, suppressed=N), never a
token, URL or label.

The budgets of the mechanism tests are made small (a monkeypatched ProfileQuota caps a profile's share; a monkeypatched
BudgetLimits.derive the add-on's budget) where the real 64 MiB would only cost time.
"""
import asyncio
from dataclasses import replace
import gc
import json
import secrets

import httpx
import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import (Children, RealChild, create_profile, ids, multi_profile_runtime, stored)
from mcp_admin_core import gateway, profiles, reply_memory
from mcp_admin_core.products import PROBES
from test_profile_runtime import ProfileChild
from test_single_profile_golden import (ACCEPT, BEARER_REQUIRED, GENUINE_CLIENT, NOT_FOUND, answer, configure,
                                        initialize_message, probe_name, settle)

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'odoo'
B, C = ids(2)
LABELS = {B: 'Beta Ops', C: 'Gamma Ops'}
MiB = 1024 * 1024
TOOL, ARGUMENTS = PROBES[PRODUCT]


def router():
    import mcp_admin_core.profile_router as module  # imported when a test runs (the red half of red-green)
    return module


def bearer(token):
    return {**ACCEPT, 'Authorization': 'Bearer ' + token}


def call(ident):
    return {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call', 'params': {'name': TOOL, 'arguments': ARGUMENTS}}


def charged(runtime, profile_id):
    """What the profile's requests hold of the add-on's request body budget now (HM-31: the gate holds no bytes)."""
    return runtime.manager.budget.used(profile_id)


def request_budget():
    import mcp_admin_core.request_budget as module  # imported when a test runs (the red half of red-green)
    return module


def add_on_budget(monkeypatch, total_mib, per_mib):
    """The add-on's request body budget a ProfileManager derives from now on (HM-31)."""
    def derive(cls, product=None, *, switched_on=False):
        return cls(total=int(total_mib * MiB), per_profile=int(per_mib * MiB))
    monkeypatch.setattr(request_budget().BudgetLimits, 'derive', classmethod(derive))


def isolate_reply_memory_from_other_quota_tests(monkeypatch):
    """Exercise the named admission/slot/stream rule without the separate HM-19c gate."""
    monkeypatch.setattr(reply_memory, 'DEFAULT_TICKETS', 64)
    monkeypatch.setattr(reply_memory, 'EXTRA_TICKETS', 32)
    monkeypatch.setattr(reply_memory, 'TOTAL_BYTES', 64 * 64 * MiB)


def budget_text(scope, limit):
    module = request_budget()
    return module.budget_text(module.BudgetExceeded(scope, limit))


def warnings_of(log_scan):
    return [record.getMessage() for record in log_scan.records
            if record.name == 'mcp_admin_core.profile_router' and record.levelname == 'WARNING']


def busy(response, *, status, retry_after, ident, text=None):
    """The response is the gateway's busy answer: that status, Retry-After, no-store and one -32003 error (under ident,
    or id null), its text fixed (no token, URL or label)."""
    assert response.status_code == status, (response.status_code, response.content[:200])
    assert response.headers['retry-after'] == str(retry_after) and response.headers['cache-control'] == 'no-store'
    assert response.headers['content-type'] == 'application/json'
    body = response.json()
    assert set(body) == {'jsonrpc', 'id', 'error'} and body['jsonrpc'] == '2.0' and body['id'] == ident
    assert set(body['error']) == {'code', 'message'} and body['error']['code'] == -32003
    assert isinstance(body['error']['message'], str) and body['error']['message']
    if text is not None:
        assert body['error']['message'] == text
    return body


class HoldingChild(ProfileChild):
    """A ProfileChild whose tools/calls (the readiness probe aside) all wait, while holding_all, until free is set, and
    whose GET in a session it opened is an event stream that stays open until then; failing: its tools/calls break
    the connection."""

    def __init__(self, *args):
        super().__init__(*args)
        self.holding_all = False
        self.failing = False
        self.streaming = False  # a tools/call is answered as an event stream that stays open until free
        self.free = asyncio.Event()
        self.waiting = 0

    async def __call__(self, request):
        message = json.loads(request.content) if request.content else {}
        if self.failing and message.get('method') == 'tools/call':
            raise httpx.ReadError('the child connection broke', request=request)
        if (self.streaming and message.get('method') == 'tools/call'
                and message['params']['name'] != probe_name(self.product)):
            self.requests.append(request)
            free, ident = self.free, message['id']

            async def reply():
                yield b': working\n\n'
                await free.wait()
                yield b'data: ' + json.dumps({'jsonrpc': '2.0', 'id': ident, 'result': {
                    'content': [{'type': 'text', 'text': 'streamed'}], 'isError': False}}).encode() + b'\n\n'
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=reply())
        session = request.headers.get('mcp-session-id')
        if request.method == 'GET' and session in self.sessions:
            self.requests.append(request)
            free = self.free

            async def events():
                yield b': open\n\n'
                await free.wait()
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=events())
        if (self.holding_all and message.get('method') == 'tools/call'
                and message['params']['name'] != probe_name(self.product)):
            self.waiting += 1
            try:
                await self.free.wait()
            finally:
                self.waiting -= 1
        return await super().__call__(request)


def holding_children(data, extras=(B, C)):
    children = Children()
    children.add(3000, HoldingChild('default', PRODUCT, data))
    for number, profile_id in enumerate(extras):
        children.add(18000 + number, HoldingChild('p' + profile_id[:4], PRODUCT,
                                                  profiles.Layout(data).profile(profile_id)))
    return children


class OversizePingChild(HoldingChild):
    async def __call__(self, request):
        message = json.loads(request.content) if request.content else {}
        if message.get('method') == 'ping':
            self.requests.append(request)
            return httpx.Response(200, json={'jsonrpc': '2.0', 'id': message['id'],
                                             'result': {'text': 'x' * (65 * 1024)}})
        return await super().__call__(request)


def setup(tmp_path, extras=(B, C)):
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    for number, profile_id in enumerate(extras):
        create_profile(data, PRODUCT, profile_id, label=LABELS[profile_id], port=18000 + number)
    return data


def watch(log_scan, data):
    for directory in [data, *(profiles.Layout(data).profile(p) for p in (B, C))]:
        if (directory / 'state.json').exists():
            value = stored(directory)
            log_scan.watch(*(v for v in (value['token'], value['child_token']) if v))
    log_scan.watch(*LABELS.values(), kind='name')


async def session_of(client, token):
    response = await client.post('/mcp', headers=bearer(token), json=initialize_message())
    assert response.status_code == 200
    return response.headers['mcp-session-id']


async def until(condition, seconds=5):
    async with asyncio.timeout(seconds):
        while not condition():
            await asyncio.sleep(.005)


def mock_child_ready(runtime, profile_id):
    """The mock transport has a child, while NoProcessSupervisor has no real process or spec."""
    health = runtime.manager.get(profile_id).runtime.health
    health.process.status = 'running'
    health.process.ready = True
    health.settled = (health.process.starts, True, 'reachable', None)


async def test_full_reply_reservation_keeps_other_profile_controls_available(tmp_path, log_scan):
    """Full A/other tickets cannot hide B's control probes or admit a large listing."""
    data = setup(tmp_path)
    children = holding_children(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        mock_child_ready(runtime, B)
        memory = runtime.manager.reply_memory
        holders = ['default'] * 3 + [B, C] + [f'{i:024x}' for i in range(3)]
        for name in holders:
            assert memory.take(name)
        try:
            async with runtime.mcp() as client:
                token = runtime.token(B)
                initialized = await asyncio.wait_for(
                    client.post('/mcp', headers=bearer(token), json=initialize_message()), 2)
                assert initialized.status_code == 200
                assert not initialized.headers['mcp-session-id'].startswith('woow-local-')
                headers = {**bearer(token), 'Mcp-Session-Id': initialized.headers['mcp-session-id']}
                ping = await asyncio.wait_for(client.post('/mcp', headers=headers,
                    json={'jsonrpc': '2.0', 'id': 9, 'method': 'ping'}), 2)
                assert ping.status_code == 200 and ping.json()['result'] == {}
                listed = await client.post('/mcp', headers=headers,
                    json={'jsonrpc': '2.0', 'id': 10, 'method': 'tools/list'})
                busy(listed, status=200, retry_after=5, ident=10)
                streamed = await client.get('/mcp', headers=headers)
                busy(streamed, status=503, retry_after=5, ident=None)
        finally:
            for name in holders:
                memory.give(name)
        assert memory.held == 0


async def test_unticketed_ping_child_body_is_hard_capped(tmp_path, log_scan):
    data = setup(tmp_path, extras=(B,))
    children = holding_children(data, extras=(B,))
    children.add(18000, OversizePingChild('pbeta', PRODUCT, profiles.Layout(data).profile(B)))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        mock_child_ready(runtime, B)
        async with runtime.mcp() as client:
            token = runtime.token(B)
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            answer = await client.post('/mcp', headers=headers,
                                       json={'jsonrpc': '2.0', 'id': 11, 'method': 'ping'})
            assert answer.status_code == 502
            assert runtime.manager.reply_memory.held == 0


def slow_body(first, opened, rest=b'', length=None):
    """A request body that sends first, then waits until opened before sending rest (and ending)."""
    async def chunks():
        yield first
        await opened.wait()
        if rest:
            yield rest
    return chunks()


async def drain(tasks):
    results = await asyncio.gather(*tasks, return_exceptions=True)
    unexpected = [result for result in results if isinstance(result, BaseException)
                  and not isinstance(result, (httpx.HTTPError, asyncio.CancelledError))]
    assert not unexpected, unexpected
    return results


# ---- the busy answers against the PaaS table ----

async def test_admission_full_answers_as_the_paas_table(tmp_path, log_scan, monkeypatch):
    """Admission full (all 32 of B's requests in flight, here held reading their bodies): a POST with an id of at most
    64 KiB is read and gets 200 + -32003 under its id + Retry-After 5 (PaaS row "排隊已達上限/等名額逾時，請求有
    JSON-RPC id"); notifications/initialized is read and goes on beyond the admission (HM-31, MF-2 (b): 202 from the
    child through the reserve); a GET and a POST over 64 KiB get 503 + -32003 id null + Retry-After 5, unread (the last
    one is HA's deviation, plan 8.8 #16: PaaS reads every body first). The default profile and C are unaffected; B's
    own answers resume when its requests end."""
    data = setup(tmp_path)
    children = holding_children(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        gate = runtime.gate(B)
        limit = gate.quota.admission
        assert limit == profiles.EXTRA_PROFILE_QUOTA.admission == 32
        text = router().admission_text(limit)
        opened = asyncio.Event()
        async with runtime.mcp() as client:
            session = await session_of(client, runtime.token(B))
            held_reads = [asyncio.create_task(client.post('/mcp', headers={**bearer(runtime.token(B)),
                                                                           'Content-Type': 'application/json'},
                                                          content=slow_body(b'{"jsonrpc":"2.0",', opened,
                                                                            b'"id":1,"method":"ping"}')))
                          for _ in range(limit)]
            await until(lambda: gate.active == limit)
            in_session = {**bearer(runtime.token(B)), 'Mcp-Session-Id': session}
            busy(await client.post('/mcp', headers=in_session, json=call(41)), status=200, retry_after=5, ident=41,
                 text=text)
            busy(await client.post(f'/private_{runtime.token(B)}/mcp', headers={**ACCEPT, 'Mcp-Session-Id': session},
                                   json=call('forty-two')), status=200, retry_after=5, ident='forty-two')
            note = await client.post('/mcp', headers=in_session,
                                     json={'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            assert note.status_code == 202 and gate.beyond == 0  # HM-31: read and served beyond the admission
            busy(await client.get('/mcp', headers=in_session), status=503, retry_after=5, ident=None)
            large = {**call(43), 'params': {'name': TOOL, 'arguments': {**ARGUMENTS, 'pad': 'x' * (65 * 1024)}}}
            busy(await client.post('/mcp', headers=in_session, json=large), status=503, retry_after=5, ident=None)
            for other in ('default', C):  # not this profile's budget
                token = runtime.token(other)
                response = await client.post('/mcp', headers={**bearer(token),
                                                              'Mcp-Session-Id': await session_of(client, token)},
                                             json=call(44))
                assert response.status_code == 200 and 'result' in response.json()
            assert gate.active == limit
            opened.set()
            await drain(held_reads)
            await until(lambda: gate.active == 0 and charged(runtime, B) == 0)
            response = await client.post('/mcp', headers=in_session, json=call(45))
            assert response.status_code == 200 and 'result' in response.json()
        lines = [line for line in warnings_of(log_scan) if 'profile=' + B[:8] in line]
        assert len(lines) == 1 and str(limit) in lines[0], lines  # one line a minute for this profile and situation


async def test_the_byte_budget_answers_as_the_paas_table(tmp_path, log_scan, monkeypatch):
    """B's share of the add-on's budget (here 1 MiB: its quota caps it; 64 MiB in the add-on), the PaaS budget rows
    (d7f5849, HM-31): a large declared body that does not fit what is left is refused before it is read, drained, its id
    from its head: 200 + -32003 under its id (503, id null, without one); a large body without Content-Length that grows
    past the share is cut off at once (503 + -32003 id null + Retry-After 5), nothing of it forwarded; a small request
    (64 KiB at most) is never charged nor refused. Every byte goes back; the default profile's share is its own."""
    monkeypatch.setattr(profiles, 'EXTRA_PROFILE_QUOTA', replace(profiles.EXTRA_PROFILE_QUOTA, body_bytes=MiB))
    data = setup(tmp_path)
    children = holding_children(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        gate = runtime.gate(B)
        assert gate.quota.body_bytes == MiB and gate.budget_share.limit == MiB
        text = budget_text('profile', MiB)
        opened = asyncio.Event()
        async with runtime.mcp() as client:
            session = await session_of(client, runtime.token(B))
            headers = {**bearer(runtime.token(B)), 'Mcp-Session-Id': session, 'Content-Type': 'application/json'}
            # One request declares the whole share and sends a little of it.
            reading = asyncio.create_task(client.post('/mcp', headers={**headers, 'Content-Length': str(MiB)},
                                                      content=slow_body(b'{', opened)))
            await until(lambda: charged(runtime, B) == MiB)
            large = json.dumps({**call(51), 'params': {'name': TOOL, 'arguments': {
                **ARGUMENTS, 'pad': 'x' * (100 * 1024)}}}).encode()
            busy(await client.post('/mcp', headers=headers, content=large), status=200, retry_after=5, ident=51,
                 text=text)
            note = json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized',
                               'params': {'pad': 'x' * (100 * 1024)}}).encode()
            busy(await client.post('/mcp', headers=headers, content=note), status=503, retry_after=5, ident=None,
                 text=text)
            small = await client.post('/mcp', headers=headers, content=json.dumps(call(52)).encode())
            assert small.status_code == 200 and 'result' in small.json()  # never charged nor refused
            since = len(children.by_port[18000].requests)

            async def growing():  # a body without Content-Length: refused once it would pass the share
                for _ in range(3):
                    yield b' ' * (512 * 1024)
            busy(await client.post('/mcp', headers=headers, content=growing()), status=503, retry_after=5,
                 ident=None, text=text)
            assert len(children.by_port[18000].requests) == since
            opened.set()
            await drain([reading])
            await until(lambda: charged(runtime, B) == 0 and gate.active == 0)
            busy(await client.post('/mcp', headers=headers, content=growing()), status=503, retry_after=5,
                 ident=None, text=text)  # alone past its share
            await until(lambda: charged(runtime, B) == 0 and gate.active == 0)
            # The default profile's share is its own.
            token = runtime.token('default')
            response = await client.post('/mcp', headers={**bearer(token), 'Mcp-Session-Id': await session_of(
                client, token), 'Content-Type': 'application/json'}, content=large)
            assert response.status_code == 200 and 'result' in response.json()
        lines = [line for line in warnings_of(log_scan) if 'profile=' + B[:8] in line and 'byte budget' in line]
        assert len(lines) == 1, lines  # one line a minute for this profile and situation


async def test_a_busy_forwarding_slot_answers_as_the_paas_table(tmp_path, log_scan, monkeypatch):
    isolate_reply_memory_from_other_quota_tests(monkeypatch)
    """B's 16 forwarding slots held by tools/calls its child has not answered: the next one waits one second, then gets
    200 + -32003 under its id + Retry-After 5 (PaaS row "等名額逾時，請求有 JSON-RPC id"; #148 shape) and a DELETE 503 id
    null; the child never gets them. The default profile's 32 slots are its own: its calls are answered meanwhile (the
    HM-05 review S-2(b) case: slots are per profile)."""
    data = setup(tmp_path)
    children = holding_children(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        child = children.by_port[18000]
        slots = profiles.EXTRA_PROFILE_QUOTA.forward_slots
        assert slots == 16 and profiles.DEFAULT_PROFILE_QUOTA.forward_slots == 32
        text = router().forward_text(slots, profiles.EXTRA_PROFILE_QUOTA.forward_wait_seconds)
        async with runtime.mcp() as client:
            session = await session_of(client, runtime.token(B))
            headers = {**bearer(runtime.token(B)), 'Mcp-Session-Id': session}
            child.holding_all = True
            held = [asyncio.create_task(client.post('/mcp', headers=headers, json=call(60 + n))) for n in range(slots)]
            await until(lambda: child.waiting == slots)
            loop = asyncio.get_running_loop()
            started = loop.time()
            busy(await client.post('/mcp', headers=headers, json=call(81)), status=200, retry_after=5, ident=81,
                 text=text)
            assert .9 <= loop.time() - started < 5
            busy(await client.delete('/mcp', headers=headers), status=503, retry_after=5, ident=None, text=text)
            assert child.waiting == slots
            token = runtime.token('default')
            default_headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            answered = await asyncio.gather(*(client.post('/mcp', headers=default_headers, json=call(90 + n))
                                              for n in range(20)))
            assert all(response.status_code == 200 and 'result' in response.json() for response in answered)
            child.free.set()
            assert all(response.status_code == 200 for response in await drain(held))
        assert [line for line in warnings_of(log_scan) if 'profile=' + B[:8] in line and str(slots) in line]


@pytest.mark.parametrize('profile_id', ['default', B])
async def test_the_stream_cap_answers_429_at_once_and_posts_still_work(tmp_path, log_scan, monkeypatch, profile_id):
    isolate_reply_memory_from_other_quota_tests(monkeypatch)
    """A profile's open GET streams reach its cap (the default profile 24, an additional one 8; PaaS 32 < 64): the
    next GET gets 429 + -32003 id null + Retry-After 30 at once (no wait), while its POSTs are still answered (PaaS
    test_stream_limit_refuses_immediately_and_posts_still_work)."""
    data = setup(tmp_path, extras=(B,))
    children = holding_children(data, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        quota = profiles.DEFAULT_PROFILE_QUOTA if profile_id == 'default' else profiles.EXTRA_PROFILE_QUOTA
        cap = quota.get_streams
        assert cap == (24 if profile_id == 'default' else 8)
        gate = runtime.gate(profile_id)
        child = children.by_port[3000 if profile_id == 'default' else 18000]
        async with runtime.mcp() as client:
            token = runtime.token(profile_id)
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            streams = [asyncio.create_task(client.get('/mcp', headers=headers)) for _ in range(cap)]
            await until(lambda: gate.streams == cap and len([r for r in child.requests if r.method == 'GET']) == cap)
            loop = asyncio.get_running_loop()
            started = loop.time()
            busy(await client.get('/mcp', headers=headers), status=429, retry_after=30, ident=None,
                 text=router().streams_text(cap))
            assert loop.time() - started < .5
            response = await client.post('/mcp', headers=headers, json=call(70))
            assert response.status_code == 200 and 'result' in response.json()
            child.free.set()
            assert all(response.status_code == 200 for response in await drain(streams))
            await until(lambda: gate.streams == 0 and gate.active == 0)


# ---- beyond the admission: a small body read once (HM-31, MF-2 (b); HM-08's refusal allowance is gone) ----

async def test_beyond_the_admission_a_small_body_is_read_once_and_handed_on(monkeypatch):
    """What the gate reads of a POST beyond its profile's admission (contract 2.4): at most 64 KiB within 2 s, and no
    bound on how many at once (PaaS: small requests' reads are not counted; the 8081 listener's bound holds them). Its
    value as the gateway would read it: a JSON-RPC request with a string or integer id gets its busy answer under it;
    a notification or a response is handed on with the body replayed once, then the server's own receive. Nothing for
    a body over 64 KiB, one that does not end in time, a client that leaves, one that is not UTF-8, not strict JSON or
    has a lone surrogate."""
    module = router()
    assert (module.REFUSAL_BODY_LIMIT, module.REFUSAL_READ_SECONDS) == (64 * 1024, 2)
    assert not hasattr(module, 'RefusalAllowance')  # HM-31: no shared allowance any more

    def receiving(*chunks, stall=False):
        queue = list(chunks)

        async def receive():
            if queue:
                chunk = queue.pop(0)
                return {'type': 'http.request', 'body': chunk, 'more_body': bool(queue) or stall}
            if stall:
                await asyncio.sleep(3600)
            return {'type': 'http.disconnect'}
        return receive

    for value, expected in (({'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call'}, 7),
                            ({'jsonrpc': '2.0', 'id': 'x', 'method': 'ping'}, 'x'),
                            ({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, None),
                            ([{'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}], None),
                            ({'jsonrpc': '2.0', 'id': True, 'method': 'ping'}, None),
                            ({'jsonrpc': '2.0', 'id': 1.0, 'method': 'ping'}, None),
                            ({'jsonrpc': '2.0', 'id': 1, 'result': {}}, None)):
        body = await module.read_small(receiving(json.dumps(value).encode()))
        assert gateway.request_id(module.small_message(body)) == expected, value
    assert gateway.carries_no_request('POST', module.small_message(json.dumps(
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'}).encode()))
    for body in (b'{"jsonrpc":"2.0","id":1,"method":"ping"', b'{"jsonrpc":"2.0","id":"\\ud800","method":"ping"}',
                 '{"jsonrpc":"2.0","id":1,"method":"ping"}'.encode('utf-16'), b'{"a":1,"a":2}'):
        assert module.small_message(body) is None, body
    pieces = [b'{"jsonrpc":"2.0",', b'"id":9,', b'"method":"ping"}']
    assert await module.read_small(receiving(*pieces)) == b''.join(pieces)
    assert await module.read_small(receiving(b'x' * 40_000, b'x' * 30_000)) is None  # over 64 KiB once read
    assert await module.read_small(receiving(b'{')) == b'{'  # a short body that ends: parsing decides
    monkeypatch.setattr(module, 'REFUSAL_READ_SECONDS', .05)
    assert await module.read_small(receiving(b'{', stall=True)) is None  # too slow
    monkeypatch.setattr(module, 'REFUSAL_READ_SECONDS', 2)

    async def left():
        return {'type': 'http.disconnect'}
    assert await module.read_small(left) is None  # the client left
    # many at once: none waits for another (no shared allowance)
    reads = [asyncio.create_task(module.read_small(receiving(b'{"jsonrpc":"2.0","id":1,"method":"ping"}')))
             for _ in range(64)]
    assert all(body is not None for body in await asyncio.gather(*reads))
    replay = module.replayed(b'{}', left)
    assert await replay() == {'type': 'http.request', 'body': b'{}', 'more_body': False}
    assert await replay() == {'type': 'http.disconnect'}


# ---- the default profile as the attacker (C1-M5, I8) and the starvation cases (G2 S5, S6) ----

async def test_the_default_profiles_token_holder_cannot_exhaust_memory(tmp_path, log_scan, monkeypatch):
    """The default profile's token holder sends 12 slow 16 MiB bodies at once (C1-M5): its share of the add-on's budget
    (64 MiB, its quota's, as every profile's; HM-31) holds four, charged before a byte is read, which may read their
    16 MiB each; the other 8 do not fit and are drained, nothing of them kept but their head and tail (PaaS: the client
    that sends its whole body first gets an answer, not a reset), then answered 503 + Retry-After 5 (no id in their
    head). What the gateway holds for the default profile never passes 64 MiB, and an idle additional profile is
    answered at once all along (I8)."""
    add_on_budget(monkeypatch, 1024, 512)
    data = setup(tmp_path, extras=(B,))
    children = holding_children(data, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        gate = runtime.gate('default')
        assert gate.quota.body_bytes == 64 * MiB and gate.budget_share.limit == 64 * MiB and gate.quota.admission == 64
        opened = asyncio.Event()
        token = runtime.token('default')
        async with runtime.mcp(timeout=60) as client:
            session = await session_of(client, token)
            headers = {**bearer(token), 'Mcp-Session-Id': session, 'Content-Type': 'application/json',
                       'Content-Length': str(16 * MiB)}
            chunk = b' ' * MiB

            def sixteen():
                async def chunks():
                    for _ in range(15):
                        yield chunk
                    await opened.wait()
                    yield b' ' * (MiB - 1) + b'{'
                return chunks()
            attack = [asyncio.create_task(client.post('/mcp', headers=headers, content=sixteen())) for _ in range(12)]
            await until(lambda: charged(runtime, 'default') == 64 * MiB and gate.active == 12, 30)
            b_token = runtime.token(B)
            loop = asyncio.get_running_loop()
            started = loop.time()
            response = await client.post('/mcp', headers={**bearer(b_token), 'Mcp-Session-Id': await session_of(
                client, b_token)}, json=call(100))
            assert response.status_code == 200 and 'result' in response.json() and loop.time() - started < 2
            assert charged(runtime, 'default') == 64 * MiB
            opened.set()
            results = await drain(attack)
            refused = [r for r in results if r.status_code == 503]
            assert len(refused) == 8 and len([r for r in results if r.status_code == 400]) == 4  # '{': not JSON
            for result in refused:
                busy(result, status=503, retry_after=5, ident=None, text=budget_text('profile', 64 * MiB))
            await until(lambda: charged(runtime, 'default') == 0 and gate.active == 0)
        assert runtime.manager.budget.peak <= 64 * MiB


async def test_a_saturated_profile_does_not_starve_an_idle_one_on_real_sockets(tmp_path, log_scan, monkeypatch):
    isolate_reply_memory_from_other_quota_tests(monkeypatch)
    """G2's S5 and S6 on the real listener (uvicorn, h11) with real loopback children and every profile's own real
    httpx client: the default profile holds its 32 forwarding slots and B its 16 (S5: one shared pool of 40 left C
    waiting 3 s for a 502) and then the default profile fills its admission with 64 slow bodies (S6: 63 of the 64
    listener places left C a 503): C gets its result at once (not a busy answer: one with an id is 200 too), and the
    default profile's next request gets its own busy answer. This proves the isolation per request: the listener's
    connections (64 + 32 x the product's limit, idle keep-alive ones and those of clients without a token included) are
    one bound of the whole add-on, and a full listener answers uvicorn's plain-text 503 to anyone (HM-08 review S-5;
    known since G2 S7, out of the plan's scope)."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    layout = profiles.Layout(data)
    real = {'default': RealChild(data, PRODUCT)}
    for profile_id in (B, C):  # each child's ephemeral port is the one its profile's index entry names
        real[profile_id] = RealChild(layout.profile(profile_id), PRODUCT)
        create_profile(data, PRODUCT, profile_id, label=LABELS[profile_id], port=real[profile_id].port)
    for child in real.values():
        await child.start()
    sockets = []
    try:
        async with multi_profile_runtime(PRODUCT, data, sockets=True, real_children=True,
                                         default_port=real['default'].port) as runtime:
            await settle(runtime, 'configured')
            watch(log_scan, data)
            url = f'http://127.0.0.1:{runtime.mcp_port}'
            async with GENUINE_CLIENT(base_url=url, timeout=30,
                                      limits=httpx.Limits(max_connections=300, max_keepalive_connections=0)) as client:
                sessions = {}
                for profile_id in ('default', B, C):
                    sessions[profile_id] = await session_of(client, runtime.token(profile_id))

                def headers(profile_id):
                    return {**bearer(runtime.token(profile_id)), 'Mcp-Session-Id': sessions[profile_id]}
                for child in real.values():
                    child.hold()
                held = [asyncio.create_task(client.post('/mcp', headers=headers('default'), json=call(n)))
                        for n in range(32)]
                held += [asyncio.create_task(client.post('/mcp', headers=headers(B), json=call(n))) for n in range(16)]
                await until(lambda: real['default'].in_flight == 32 and real[B].in_flight == 16, 15)
                real[C].release()
                loop = asyncio.get_running_loop()
                started = loop.time()
                response = await client.post('/mcp', headers=headers(C), json=call(200))
                assert response.status_code == 200 and response.json()['result'], response.content[:200]
                assert loop.time() - started < 1, 'S5: the idle profile waited'
                # S6: 64 slow bodies of the default profile fill its admission; C is still answered.
                gate = runtime.gate('default')
                for _ in range(64 - 32):
                    reader, writer = await asyncio.open_connection('127.0.0.1', runtime.mcp_port)
                    writer.write(('POST /mcp HTTP/1.1\r\nHost: 127.0.0.1\r\nAccept: ' + ACCEPT['Accept']
                                  + '\r\nAuthorization: Bearer ' + runtime.token('default')
                                  + '\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{').encode())
                    await writer.drain()
                    sockets.append(writer)
                await until(lambda: gate.active == 64, 15)
                busy(await client.post('/mcp', headers=headers('default'), json=call(201)), status=200,
                     retry_after=5, ident=201)
                started = loop.time()
                response = await client.post('/mcp', headers=headers(C), json=call(202))
                # A busy answer with an id is 200 too: C must get its result, not -32003 (HM-08 review MF-2).
                assert response.status_code == 200 and 'result' in response.json(), 'S6: the idle profile was refused'
                assert loop.time() - started < 1, 'S6: the idle profile waited'
                for child in real.values():
                    child.release()
                assert all(response.status_code == 200 for response in await drain(held))
                assert real['default'].peak <= profiles.DEFAULT_PROFILE_QUOTA.forward_slots
                assert real[B].peak <= profiles.EXTRA_PROFILE_QUOTA.forward_slots
                for writer in sockets:  # the slow bodies' clients leave: their requests end, and so does the admission
                    writer.close()
                await until(lambda: gate.active == 0 and charged(runtime, 'default') == 0, 15)
    finally:
        for writer in sockets:
            writer.close()
        for child in real.values():
            await child.stop()


# ---- what the gateway holds while an answer streams (HM-08 review MF-1, S-1) ----

class StreamingChild(ProfileChild):
    """A ProfileChild that answers a large POST (over 64 KiB: the tests' long tools/list cursors) as an mcp 2.3.0 child
    answers a request by default (is_json_response_enabled=False; FastMCP 4.1.3's json_response=False): the event
    stream's headers at once, the reply only once free is set. It keeps nothing of those requests but their sizes (the
    test double must hold no reference to them)."""

    def __init__(self, *args):
        super().__init__(*args)
        self.free = asyncio.Event()
        self.sizes = []

    async def __call__(self, request):
        if request.method != 'POST' or len(request.content) <= 64 * 1024:
            return await super().__call__(request)
        token = json.loads(self.state.read_text())['child_token']
        assert request.headers.get_list('authorization') == ['Bearer ' + token]
        ident, free = json.loads(request.content)['id'], self.free
        self.sizes.append(len(request.content))

        async def reply():
            yield b': working\n\n'
            await free.wait()
            yield b'data: ' + json.dumps({'jsonrpc': '2.0', 'id': ident, 'result': {'tools': []}}).encode() + b'\n\n'
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=reply())


def forwarded_bodies(port):
    """The bodies over 64 KiB the gateway built for the child on port that are still referenced (an httpx.Request keeps
    its content, and the child's response keeps its request): (how many, their bytes). The test client's own requests
    (to http://mcp) are not counted."""
    gc.collect()
    sizes = [len(item._content) for item in gc.get_objects()
             if isinstance(item, httpx.Request) and item.url.host == '127.0.0.1' and item.url.port == port
             and len(getattr(item, '_content', None) or b'') > 64 * 1024]
    return len(sizes), sum(sizes)


@pytest.mark.parametrize('text,streams', [('x', 4), ('中', 2), ('\U0001F600', 1)], ids=['ascii', 'cjk', 'emoji'])
async def test_an_event_stream_keeps_its_bytes_charged_until_it_ends(tmp_path, log_scan, monkeypatch, text, streams):
    isolate_reply_memory_from_other_quota_tests(monkeypatch)
    """A child answers a request with an event stream whose headers come before its tool runs, and the gateway's
    forwarded copy of the body stays referenced until the stream ends (HM-08 review MF-1: E1 found 192 MiB held for an
    additional profile and 480 MiB for the default one while the dispatcher counted 0). So a request stays charged until
    it ends, and it is charged the larger of what was read and what is forwarded: the gateway re-serializes the body
    with ASCII escapes, a CJK character (3 UTF-8 bytes) as 6 bytes, an emoji (4) as 12 (review S-1).

    B's share is 4 MiB here (its quota caps it; 64 MiB in the add-on). Its token holder sends 1 MiB requests one after
    another, each once the previous one's stream has started: whatever the text, the forwarded bodies the gateway still
    holds never pass the share, and the charge always covers them. ASCII: 4 streams, the fifth is refused before a byte
    is read and drained, its id from its head (HM-31, PaaS: 200 + -32003 under its id). CJK, forwarded as 2 MiB: 2
    streams. Emoji, forwarded as 3 MiB: 1 stream; the next one fits as read but not as forwarded, so it is refused once
    read: 200 + -32003 under its id, never sent to the child. When the streams end, every byte is given back and no
    forwarded body is left."""
    budget = 4 * MiB
    monkeypatch.setattr(profiles, 'EXTRA_PROFILE_QUOTA', replace(profiles.EXTRA_PROFILE_QUOTA, body_bytes=budget))
    data = setup(tmp_path, extras=(B,))
    children = Children()
    children.add(3000, StreamingChild('default', PRODUCT, data))
    child = children.add(18000, StreamingChild('pbeta', PRODUCT, profiles.Layout(data).profile(B)))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        gate = runtime.gate(B)
        assert gate.quota.body_bytes == budget
        token = runtime.token(B)
        text_bytes = len(text.encode())
        async with runtime.mcp(timeout=60) as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token),
                       'Content-Type': 'application/json'}

            def body(ident):  # about 1 MiB as received (UTF-8)
                cursor = text * ((MiB - 100) // text_bytes)
                return json.dumps({'jsonrpc': '2.0', 'id': ident, 'method': 'tools/list', 'params': {'cursor': cursor}},
                                  ensure_ascii=False).encode()
            tasks, answers = [], {}
            for ident in range(1, 9):
                task = asyncio.create_task(client.post('/mcp', headers=headers, content=body(ident)))
                tasks.append(task)
                before = len(child.sizes)
                await until(lambda: len(child.sizes) == before + 1 or task.done(), 30)
                if task.done():
                    answers[ident] = task.result()
                count, held_bytes = forwarded_bodies(18000)
                assert held_bytes <= charged(runtime, B) <= budget, (ident, held_bytes, charged(runtime, B))
            assert len(child.sizes) == streams and sorted(answers) == list(range(streams + 1, 9))
            count, held_bytes = forwarded_bodies(18000)
            assert count == streams and held_bytes == sum(child.sizes)  # every open stream still holds its body
            factor = {1: 1, 3: 2, 4: 3}[text_bytes]  # forwarded size / received size
            assert all(factor * (MiB - 200) < size <= factor * MiB for size in child.sizes), child.sizes
            for ident, response in answers.items():
                busy(response, status=200, retry_after=5, ident=ident, text=budget_text('profile', budget))
            child.free.set()
            for task in tasks[:streams]:
                response = await task
                assert response.status_code == 200 and 'result' in response.text
            await until(lambda: gate.active == 0 and charged(runtime, B) == 0)
        del tasks, answers, task
        assert forwarded_bodies(18000) == (0, 0)
        assert len(child.sizes) == streams  # a refused body never reached the child


async def test_a_wrong_token_takes_no_admission_and_gets_todays_answer(tmp_path, log_scan):
    """A token no profile holds (no match) takes no admission and reads no body: its request goes to the default
    profile's app untouched, so even while all 64 of the default profile's admission places are taken its answer is
    today's 404 (secret path) or 401 (Bearer), byte for byte, never a busy answer (contract 2.3; HM-08 review S-3,
    mutation R01)."""
    data = setup(tmp_path, extras=(B,))
    children = holding_children(data, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        gate = runtime.gate('default')
        limit = gate.quota.admission
        assert limit == profiles.DEFAULT_PROFILE_QUOTA.admission == 64
        token = runtime.token('default')
        unknown = secrets.token_urlsafe(32)  # held by nobody (made at run time)
        log_scan.watch(unknown)
        opened = asyncio.Event()
        async with runtime.mcp() as client:
            held_reads = [asyncio.create_task(client.post(
                '/mcp', headers={**bearer(token), 'Content-Type': 'application/json'},
                content=slow_body(b'{"jsonrpc":"2.0",', opened, b'"id":1,"method":"ping"}'))) for _ in range(limit)]
            await until(lambda: gate.active == limit)
            for path, headers in (('/mcp', bearer(unknown)), (f'/private_{unknown}/mcp', dict(ACCEPT))):
                response = await client.post(path, headers=headers, json=initialize_message())
                assert answer(response) == (NOT_FOUND if path.startswith('/private_') else BEARER_REQUIRED)
            assert gate.active == limit
            opened.set()
            await drain(held_reads)
            await until(lambda: gate.active == 0 and charged(runtime, 'default') == 0)
        assert not [line for line in warnings_of(log_scan) if 'profile=default' in line]  # nothing was refused


# ---- what each profile gets, what is given back ----

async def test_every_profile_has_its_own_child_client(tmp_path, log_scan):
    """The manager gives every profile its own child client, made as run_product made the one before (no proxy or
    .netrc from the environment, no redirect followed, 10 s per request, 3 s to connect; test_profile_runtime checks the
    options it passes) with its quota's connections: 40 for the default profile, 24 for each additional one (PaaS
    test_gateway_client_uses_bounded_pool_wait; HA has no shared pool, so PaaS
    test_shared_pool_has_room_for_every_profiles_slots_and_reserve has nothing to size here)."""
    data = setup(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=holding_children(data)) as runtime:
        watch(log_scan, data)
        entries = {entry.profile_id: entry for entry in runtime.manager.profiles()}
        assert list(entries) == ['default', B, C]
        assert entries['default'].runtime.child_connections == profiles.DEFAULT_PROFILE_QUOTA.child_connections == 40
        assert all(entries[p].runtime.child_connections == profiles.EXTRA_PROFILE_QUOTA.child_connections == 24
                   for p in (B, C))
        clients = [entry.runtime.child for entry in entries.values()]
        assert len({id(client) for client in clients}) == 3
        for client in clients:
            assert (client.trust_env, client.follow_redirects) == (False, False)
            assert client.timeout == httpx.Timeout(10, connect=3)
        assert [entry.gate.quota for entry in entries.values()] == [profiles.DEFAULT_PROFILE_QUOTA,
                                                                    profiles.EXTRA_PROFILE_QUOTA,
                                                                    profiles.EXTRA_PROFILE_QUOTA]


async def test_admission_bytes_and_streams_are_given_back_however_a_request_ends(tmp_path, log_scan, monkeypatch):
    isolate_reply_memory_from_other_quota_tests(monkeypatch)
    """Every way a request ends gives back what it held (PaaS test_slots_are_returned_on_transport_errors_and_
    cancellation): an answer, an answer of the gateway's own (502 when the child cannot be reached), a refusal of the
    app (400, 403, 405, 415), a client that is cancelled while its body is read or while its call waits, a stream that
    ends. A request's bytes are given back when it ends, not when its answer starts (HM-08 review MF-1: PaaS
    test_already_read_response_returns_its_slot_at_once is about connection slots). HM-31: only a large body (over 64
    KiB) is charged, so the bodies that must show their charge here are larger than that."""
    data = setup(tmp_path, extras=(B,))
    children = holding_children(data, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        gate = runtime.gate(B)
        token = runtime.token(B)

        def clear():
            return gate.active == 0 and charged(runtime, B) == 0 and gate.streams == 0
        async with runtime.mcp() as client:
            session = await session_of(client, token)
            headers = {**bearer(token), 'Mcp-Session-Id': session}
            assert (await client.post('/mcp', headers=headers, json=call(1))).status_code == 200
            assert clear()
            for request in (client.post('/mcp', headers=headers, content=b'{', ),
                            client.put('/mcp', headers=headers),
                            client.post('/mcp', headers={**headers, 'Content-Type': 'text/plain'}, content=b'{}'),
                            client.post('/mcp?x=1', headers=headers, json=call(2)),
                            client.get('/mcp', headers=bearer(token))):
                response = await request
                assert response.status_code in (400, 403, 405, 415), response.status_code
                assert clear()
            opened = asyncio.Event()
            reading = asyncio.create_task(client.post('/mcp', headers={**headers, 'Content-Type': 'application/json'},
                                                      content=slow_body(b'{"a":"' + b'x' * (100 * 1024), opened)))
            await until(lambda: gate.active == 1 and charged(runtime, B) > 0)
            reading.cancel()
            await asyncio.gather(reading, return_exceptions=True)
            await until(clear)
            child = children.by_port[18000]
            child.holding_all = True
            waiting = asyncio.create_task(client.post('/mcp', headers=headers, json=call(3)))
            await until(lambda: child.waiting == 1)
            waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)
            await until(clear)
            child.holding_all = False
            stream = asyncio.create_task(client.get('/mcp', headers=headers))
            await until(lambda: gate.streams == 1)
            # A tools/call answered as an event stream: its bytes stay charged, as its admission, until the stream ends
            # (HM-08 review MF-1: the answer's headers come before the tool runs, and the gateway's forwarded copy of the
            # body stays referenced until the end), the larger of what was read and what was forwarded.
            child.streaming = True
            body = json.dumps({**call(5), 'params': {'name': TOOL, 'arguments': {
                **ARGUMENTS, 'pad': 'x' * (100 * 1024)}}}).encode()
            answered = asyncio.create_task(client.post('/mcp', headers={**headers, 'Content-Type': 'application/json'},
                                                       content=body))
            await until(lambda: gate.active == 2 and child.requests and child.requests[-1].method == 'POST')
            await asyncio.sleep(.05)  # the stream has started: nothing is given back before it ends
            assert charged(runtime, B) == max(len(body), len(child.requests[-1].content)) > 64 * 1024
            assert gate.streams == 1
            child.free.set()
            assert (await stream).status_code == 200
            assert (await answered).status_code == 200
            await until(clear)
            child.streaming = False
            child.failing = True  # the connection to B's child breaks: the gateway's own 502
            assert (await client.post('/mcp', headers=headers, json=call(4))).status_code == 502
            assert clear()


async def test_busy_warnings_are_one_line_per_profile_and_situation_a_minute(tmp_path, log_scan):
    """One WARNING per profile and situation a minute (the PaaS gateway_pool report): the profile by its id's first 8
    characters or default, the limit, then suppressed=N for the ones not written; never a token, a URL or a label."""
    module = router()
    reports = module.Reports()
    clock = [0.0]
    reports.clock = lambda: clock[0]
    for _ in range(3):
        reports.warn(B, 'admission', 'MCP gateway [profile=%s]: test line' % profiles.log_id(B))
    reports.warn('default', 'admission', 'MCP gateway [profile=default]: test line')
    reports.warn(B, 'streams', 'MCP gateway [profile=%s]: other line' % profiles.log_id(B))
    clock[0] += 59.9
    reports.warn(B, 'admission', 'MCP gateway [profile=%s]: test line' % profiles.log_id(B))
    clock[0] += .2
    reports.warn(B, 'admission', 'MCP gateway [profile=%s]: test line' % profiles.log_id(B))
    lines = warnings_of(log_scan)
    assert lines == ['MCP gateway [profile=aaaaaaaa]: test line', 'MCP gateway [profile=default]: test line',
                     'MCP gateway [profile=aaaaaaaa]: other line',
                     'MCP gateway [profile=aaaaaaaa]: test line suppressed=3']
    for number in range(200):  # the remembered situations stay bounded
        reports.warn('%024x' % number, 'admission', 'line')
    assert len(reports.state) <= module.MAX_REPORT_KEYS + 1


# ---- switched off: today's answers ----

async def test_switched_off_a_busy_slot_and_a_client_leaving_answer_as_before(tmp_path, log_scan):
    """With the product switched off (the repository), the answers HM-08 changes only once a product is switched on stay
    those of bb48449, byte for byte (HM-01 provenance note 4.2; contract 4.2): a forwarding slot busy for a second
    answers 503 {"error":"request denied"}; a client that leaves while its body is read, 403 {"error":"request
    denied"} (the gateway's own answer for ClientDisconnect); and no admission applies (no dispatcher). HM-31: the
    request body budget applies switched off too (not gated, contract 1.2); a client leaving is no budget refusal."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    children = Children()
    child = children.add(3000, HoldingChild('default', PRODUCT, data))
    denied = {403: (403, [('content-length', '26'), ('content-type', 'application/json')],
                    b'{"error":"request denied"}'),
              503: (503, [('content-length', '26'), ('content-type', 'application/json')],
                    b'{"error":"request denied"}')}
    async with multi_profile_runtime(PRODUCT, data, switch=False, children=children) as runtime:
        await settle(runtime, 'configured')
        token = stored(data)['token']
        log_scan.watch(token, stored(data)['child_token'])
        assert runtime.manager is None
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            child.holding_all = True
            held = [asyncio.create_task(client.post('/mcp', headers=headers, json=call(n))) for n in range(32)]
            await until(lambda: child.waiting == 32)
            assert answer(await client.post('/mcp', headers=headers, json=call(99))) == denied[503]
            child.free.set()
            await drain(held)
        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': 'POST',
                 'scheme': 'http', 'path': '/mcp', 'raw_path': b'/mcp', 'query_string': b'', 'root_path': '',
                 'server': ('mcp', 80), 'client': ('127.0.0.1', 1),
                 'headers': [(b'authorization', ('Bearer ' + token).encode()), (b'content-type', b'application/json'),
                             (b'accept', ACCEPT['Accept'].encode())]}
        messages = iter([{'type': 'http.request', 'body': b'{"jsonrpc":', 'more_body': True},
                         {'type': 'http.disconnect'}])
        sent = []

        async def receive():
            return next(messages)

        async def send(message):
            sent.append(message)
        await runtime.mcp_app(scope, receive, send)
        start, body = sent[0], b''.join(message.get('body', b'') for message in sent[1:])
        assert (start['status'], sorted((k.decode(), v.decode()) for k, v in start['headers']), body) == denied[403]
