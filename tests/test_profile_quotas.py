"""HM-08: every profile's own admission, byte budget, forwarding slots, GET streams and child client, the default
profile's included (multi-profile plan 5.2; contract 2.4, 4.2, 5; invariant I8; DQ-07 (a); C1-M5, C3-MF-2, C3-SF-1;
FM-49, 50, 149, 150).

Once a product is switched on, the dispatcher admits a request of a profile before its body is read (64 for the
default profile, 32 for each additional one), charges what is read of it to the profile's byte budget (64 MiB each:
max(the declared Content-Length, at most MAX_REQUEST, and the bytes read so far)) until the profile's app starts its
answer, and caps the profile's open GET streams (24, 8). Each profile's app has its own forwarding slots (32, 16; one
second's wait) and its own child client (40, 24 connections). No pool is shared: one profile's requests never take
another profile's slots or bytes.

The busy answers follow the PaaS table (docs/mcp-gateway-limits.md "超過上限時用戶端拿到什麼", woow-mcp-server 69ac425,
unchanged at cf3d0d5) with HA's one deviation (plan 8.8 #16): a request refused before its body is read is read with the
add-on's small refusal allowance (8 at once, 512 KiB in all, at most 64 KiB and 2 s each) only to find its JSON-RPC id;
with an id: 200, Retry-After 5 and a -32003 error under that id; without one, larger, unreadable in time or not JSON:
503, Retry-After 5, id null. A forwarding slot that stays busy for a second: the same shapes (#148). A full GET stream
cap: 429, Retry-After 30. Each comes with one WARNING per profile and situation a minute (id's first 8 characters,
suppressed=N), never a token, URL or label.

The quotas of the mechanism tests are made small (monkeypatched ProfileQuota) where the real 64 MiB would only cost
time; the default profile's attack (C1-M5) and the real-socket starvation cases (G2 S5, S6) use the real values.
"""
import asyncio
from dataclasses import replace
import json

import httpx
import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import (Children, RealChild, create_profile, ids, multi_profile_runtime, stored)
from mcp_admin_core import gateway, profiles
from mcp_admin_core.products import PROBES
from test_profile_runtime import ProfileChild
from test_single_profile_golden import (ACCEPT, GENUINE_CLIENT, answer, configure, initialize_message, probe_name,
                                        settle)

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
    64 KiB is read with the refusal allowance and gets 200 + -32003 under its id + Retry-After 5 (PaaS row "排隊已達上限
    /等名額逾時，請求有 JSON-RPC id"); a notification, a GET and a POST over 64 KiB get 503 + -32003 id null + Retry-After
    5 (the last one is HA's deviation, plan 8.8 #16: PaaS reads every body first). The default profile and C are
    unaffected; B's own answers resume when its requests end."""
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
            held = [asyncio.create_task(client.post('/mcp', headers={**bearer(runtime.token(B)),
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
            busy(await client.post('/mcp', headers=in_session,
                                   json={'jsonrpc': '2.0', 'method': 'notifications/initialized'}),
                 status=503, retry_after=5, ident=None, text=text)
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
            await drain(held)
            await until(lambda: gate.active == 0 and gate.body_bytes == 0)
            response = await client.post('/mcp', headers=in_session, json=call(45))
            assert response.status_code == 200 and 'result' in response.json()
        lines = [line for line in warnings_of(log_scan) if 'profile=' + B[:8] in line]
        assert len(lines) == 1 and str(limit) in lines[0], lines  # one line a minute for this profile and situation


async def test_the_byte_budget_answers_as_the_paas_table(tmp_path, log_scan, monkeypatch):
    """The byte budget (here 1 MiB, monkeypatched; 64 MiB in the add-on): a declared Content-Length over what is left
    refuses the request before its body is read (at most 64 KiB with an id: 200 + -32003 under its id; otherwise 503,
    id null); a body without Content-Length that grows past the budget is cut off at once: 503 + -32003 id null +
    Retry-After 5, nothing of it forwarded, its bytes given back (contract 2.4 row 3)."""
    monkeypatch.setattr(profiles, 'EXTRA_PROFILE_QUOTA', replace(profiles.EXTRA_PROFILE_QUOTA, body_bytes=MiB))
    data = setup(tmp_path)
    children = holding_children(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        gate = runtime.gate(B)
        assert gate.quota.body_bytes == MiB
        text = router().bytes_text(MiB)
        opened = asyncio.Event()
        async with runtime.mcp() as client:
            session = await session_of(client, runtime.token(B))
            headers = {**bearer(runtime.token(B)), 'Mcp-Session-Id': session, 'Content-Type': 'application/json'}
            # One request declares the whole budget and sends a little of it.
            held = asyncio.create_task(client.post('/mcp', headers={**headers, 'Content-Length': str(MiB)},
                                                   content=slow_body(b'{', opened)))
            await until(lambda: gate.body_bytes == MiB)
            busy(await client.post('/mcp', headers=headers, content=json.dumps(call(51)).encode()),
                 status=200, retry_after=5, ident=51, text=text)
            busy(await client.post('/mcp', headers=headers,
                                   content=json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'})),
                 status=503, retry_after=5, ident=None, text=text)
            # A body without Content-Length: refused once it would pass the budget.
            since = len(children.by_port[18000].requests)
            busy(await client.post('/mcp', headers=headers, content=slow_body(b'{"jsonrpc":', asyncio.Event())),
                 status=503, retry_after=5, ident=None, text=text)
            assert len(children.by_port[18000].requests) == since
            opened.set()
            await drain([held])
            await until(lambda: gate.body_bytes == 0 and gate.active == 0)

            # One request alone past the budget: 512 KiB chunks, the third is not read.
            async def growing():
                for _ in range(3):
                    yield b' ' * (512 * 1024)
            busy(await client.post('/mcp', headers=headers, content=growing()), status=503, retry_after=5,
                 ident=None, text=text)
            await until(lambda: gate.body_bytes == 0 and gate.active == 0)
            response = await client.post('/mcp', headers=headers, content=json.dumps(call(52)).encode())
            assert response.status_code == 200 and 'result' in response.json()
            # The default profile's budget is its own.
            token = runtime.token('default')
            response = await client.post('/mcp', headers={**bearer(token), 'Mcp-Session-Id': await session_of(
                client, token)}, json=call(53))
            assert response.status_code == 200


async def test_a_busy_forwarding_slot_answers_as_the_paas_table(tmp_path, log_scan):
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
async def test_the_stream_cap_answers_429_at_once_and_posts_still_work(tmp_path, log_scan, profile_id):
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


# ---- the refusal allowance ----

async def test_the_refusal_allowance_reads_little_and_few(monkeypatch):
    """The add-on's refusal allowance (contract 2.4: 8 at once, 512 KiB in all, at most 64 KiB and 2 s each) finds the
    JSON-RPC id of a refused request: a single request object of a JSON body with a string or integer id; nothing for a
    notification, a batch, a boolean or float id, a body that is not JSON or not application/json, a lone surrogate, a
    body over 64 KiB (declared or read), one that does not end in time, a client that leaves; and nothing read at all
    while 8 refusals are being read or their bytes would pass 512 KiB."""
    module = router()
    allowance = module.RefusalAllowance()
    assert (module.REFUSAL_SLOTS, module.REFUSAL_BYTES, module.REFUSAL_BODY_LIMIT, module.REFUSAL_READ_SECONDS) == \
        (8, 512 * 1024, 64 * 1024, 2)

    def scope(body=None, content_type='application/json', length=True):
        headers = [(b'content-type', content_type.encode())] if content_type else []
        if length and body is not None:
            headers.append((b'content-length', str(len(body)).encode()))
        return {'type': 'http', 'method': 'POST', 'headers': headers}

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

    async def read(body, **kwargs):
        length = len(body) if kwargs.pop('declared', True) else None
        return await allowance.read_message(scope(body, **kwargs), receiving(body), length)

    for value, expected in (({'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call'}, 7),
                            ({'jsonrpc': '2.0', 'id': 'x', 'method': 'ping'}, 'x'),
                            ({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, None),
                            ([{'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}], None),
                            ({'jsonrpc': '2.0', 'id': True, 'method': 'ping'}, None),
                            ({'jsonrpc': '2.0', 'id': 1.0, 'method': 'ping'}, None),
                            ({'jsonrpc': '2.0', 'id': 1, 'result': {}}, None),
                            ({'id': 1, 'method': 'ping'}, None)):
        assert gateway.request_id(await read(json.dumps(value).encode())) == expected, value
    assert await read(b'{"jsonrpc":"2.0","id":1,"method":"ping"') is None
    assert await read(b'{"jsonrpc":"2.0","id":"\\ud800","method":"ping"}') is None
    assert await read(b'{"jsonrpc":"2.0","id":1,"method":"ping"}', content_type='text/plain') is None
    assert await read(b'{"jsonrpc":"2.0","id":1,"method":"ping","pad":"' + b'x' * 65536 + b'"}',
                      declared=False) is None
    assert allowance.active == 0 and allowance.reserved == 0
    # Too slow: nothing after 2 s (shortened here).
    monkeypatch.setattr(module, 'REFUSAL_READ_SECONDS', .05)
    assert await allowance.read_message(scope(b'{}'), receiving(b'{', stall=True), 2) is None
    assert allowance.active == 0 and allowance.reserved == 0
    monkeypatch.setattr(module, 'REFUSAL_READ_SECONDS', 2)
    # 8 at once, then nothing is read; the bytes: 512 KiB in all (an unknown length reserves 64 KiB).
    stalled = [asyncio.create_task(allowance.read_message(scope(None, length=False), receiving(b'{', stall=True),
                                                          None)) for _ in range(8)]
    await until(lambda: allowance.active == 8)
    assert allowance.reserved == 8 * 64 * 1024
    untouched = []

    async def never():
        untouched.append(1)
        return {'type': 'http.request', 'body': b'{}', 'more_body': False}
    assert await allowance.read_message(scope(b'{}'), never, 2) is None and untouched == []
    for task in stalled:
        task.cancel()
    await asyncio.gather(*stalled, return_exceptions=True)
    assert allowance.active == 0 and allowance.reserved == 0
    # The bytes (512 KiB in all) bite on their own once more than 8 could be read at once.
    wider = module.RefusalAllowance(slots=9)
    full = [asyncio.create_task(wider.read_message(scope(None, length=False), receiving(b'{', stall=True), None))
            for _ in range(8)]
    await until(lambda: wider.active == 8 and wider.reserved == 512 * 1024)
    assert await wider.read_message(scope(b'{}'), never, 2) is None and untouched == []
    for task in full:
        task.cancel()
    await asyncio.gather(*full, return_exceptions=True)
    assert wider.active == 0 and wider.reserved == 0
    # Larger than 64 KiB declared: nothing read.
    assert await allowance.read_message(scope(b'x' * 65537), never, 65537) is None and untouched == []


# ---- the default profile as the attacker (C1-M5, I8) and the starvation cases (G2 S5, S6) ----

async def test_the_default_profiles_token_holder_cannot_exhaust_memory(tmp_path, log_scan):
    """The default profile's token holder sends 64 slow 16 MiB bodies at once (C1-M5): the default profile's byte
    budget (64 MiB, as every profile's) admits four, which may read their 16 MiB each; the other 60 are refused before a
    byte is read (503, Retry-After 5: over 64 KiB, so no id is looked for). What the gateway holds for the default
    profile never passes 64 MiB, and an idle additional profile is answered at once all along (I8)."""
    data = setup(tmp_path, extras=(B,))
    children = holding_children(data, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        gate = runtime.gate('default')
        assert gate.quota.body_bytes == 64 * MiB and gate.quota.admission == 64
        opened = asyncio.Event()
        peak = [0]
        token = runtime.token('default')
        async with runtime.mcp() as client:
            session = await session_of(client, token)
            headers = {**bearer(token), 'Mcp-Session-Id': session, 'Content-Type': 'application/json',
                       'Content-Length': str(16 * MiB)}

            def sixteen():
                async def chunks():
                    for _ in range(15):
                        yield b' ' * MiB
                        peak[0] = max(peak[0], gate.body_bytes)
                    await opened.wait()
                    yield b' ' * (MiB - 1) + b'{'
                return chunks()
            attack = [asyncio.create_task(client.post('/mcp', headers=headers, content=sixteen())) for _ in range(64)]
            refused = []
            async with asyncio.timeout(30):
                while len(refused) < 60:
                    await asyncio.sleep(.01)
                    refused = [task for task in attack if task.done()]
            for task in refused:
                busy(task.result(), status=503, retry_after=5, ident=None)
            assert gate.body_bytes == 64 * MiB and gate.active == 4 + 0
            b_token = runtime.token(B)
            loop = asyncio.get_running_loop()
            started = loop.time()
            response = await client.post('/mcp', headers={**bearer(b_token), 'Mcp-Session-Id': await session_of(
                client, b_token)}, json=call(100))
            assert response.status_code == 200 and 'result' in response.json() and loop.time() - started < 2
            opened.set()
            await drain(attack)
            await until(lambda: gate.body_bytes == 0 and gate.active == 0)
        assert peak[0] <= 64 * MiB


async def test_a_saturated_profile_does_not_starve_an_idle_one_on_real_sockets(tmp_path, log_scan):
    """G2's S5 and S6 on the real listener (uvicorn, h11) with real loopback children and every profile's own real
    httpx client: the default profile holds its 32 forwarding slots and B its 16 (S5: one shared pool of 40 left C
    waiting 3 s for a 502) and then the default profile fills its admission with 64 slow bodies (S6: 63 of the 64
    listener places left C a 503): C is answered at once, and the default profile's next request gets its own busy
    answer."""
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
                assert response.status_code == 200 and loop.time() - started < 1, 'S6: the idle profile waited'
                for child in real.values():
                    child.release()
                assert all(response.status_code == 200 for response in await drain(held))
                assert real['default'].peak <= profiles.DEFAULT_PROFILE_QUOTA.forward_slots
                assert real[B].peak <= profiles.EXTRA_PROFILE_QUOTA.forward_slots
                for writer in sockets:  # the slow bodies' clients leave: their requests end, and so does the admission
                    writer.close()
                await until(lambda: gate.active == 0 and gate.body_bytes == 0, 15)
    finally:
        for writer in sockets:
            writer.close()
        for child in real.values():
            await child.stop()


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


async def test_admission_bytes_and_streams_are_given_back_however_a_request_ends(tmp_path, log_scan):
    """Every way a request ends gives back what it held (PaaS test_slots_are_returned_on_transport_errors_and_
    cancellation, test_already_read_response_returns_its_slot_at_once): an answer, an answer of the gateway's own
    (502 when the child cannot be reached), a refusal of the app (400, 403, 405, 415), a client that is cancelled
    while its body is read or while its call waits, a stream that ends."""
    data = setup(tmp_path, extras=(B,))
    children = holding_children(data, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        gate = runtime.gate(B)
        token = runtime.token(B)

        def clear():
            return gate.active == 0 and gate.body_bytes == 0 and gate.streams == 0
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
                                                      content=slow_body(b'{"a":', opened)))
            await until(lambda: gate.active == 1 and gate.body_bytes > 0)
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
            # A tools/call answered as an event stream: its bytes are given back once the answer starts (the body is no
            # longer held: PaaS test_already_read_response_returns_its_slot_at_once), its admission when it ends.
            child.streaming = True
            body = json.dumps(call(5)).encode()
            answered = asyncio.create_task(client.post('/mcp', headers={**headers, 'Content-Type': 'application/json'},
                                                       content=body))
            await until(lambda: gate.active == 2 and gate.body_bytes == 0 and child.requests
                        and child.requests[-1].method == 'POST')
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
    denied"} (the gateway's own answer for ClientDisconnect); and no admission or byte budget applies (no dispatcher)."""
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
