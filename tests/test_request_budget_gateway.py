"""HM-31: the request body budget end to end, switched off (one profile, the add-on's own budget) and switched on (every
profile's share of one budget) (multi-profile plan 12.3 HM-31; contract 1.2, 2.4, 5; the PaaS #155 gateway,
woow-mcp-server d7f5849 proxy.py, its tests test_gateway_request_budget.py section 4, test_gateway_budget_round2.py and
test_gateway_budget_round3.py (their HTTP cases); the case-by-case map is in
docs/provenance/ha-multiprofile-HM-31-20261116.md).

Not gated (the user's decision of 2026-11-16, contract 1.2): a switched-off product's gateway reads every MCP request
under the budget too. A large body (declared over 64 KiB, or without Content-Length) is charged once the token is
checked: a declared length that does not fit is refused before a byte is read (the body drained, only its head and
tail kept: 200 + -32003 under its id, else 503; Retry-After 5); one without a length is cut off once it does not fit
(its id from its head); one that sends nothing for the idle limit gets 408 + -32003 + Retry-After 5 + Connection: close;
the whole read keeps HA's 60 s (today's 408). The body as forwarded (re-serialized) is charged too. A small request
(64 KiB at most) is never charged nor refused. Whatever a request holds goes back when it ends, however it ends.

Budgets are made small for the test (BudgetLimits.derive replaced: the code that derives them is the unit's,
tests/test_request_budget.py). Bodies are made once per test and shared, never one 16 MiB object per request.
"""
import asyncio
from contextlib import asynccontextmanager
import json
import tracemalloc

import httpx
import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import Children, multi_profile_runtime
from mcp_admin_core import gateway, profiles
from mcp_admin_core.products import ProductStore, TOOLS
from switched_gateway import B, PRODUCT, GatewayChild, bearer, call, session_of, setup, until, watch
import test_single_profile_golden as golden
from test_single_profile_golden import configure, production_runtime, stored

pytestmark = pytest.mark.usefixtures('log_scan')
MiB = 1024 * 1024
ACCEPT = 'application/json, text/event-stream'
SESSION = 'hm31-session'


def rb():
    import mcp_admin_core.request_budget as module  # imported when a test runs (the red half of red-green)
    return module


def limits(monkeypatch, total_mib, per_mib, idle=30.0):
    """Every budget made from now on (make_apps' own, a ProfileManager's) has these limits."""
    made = []

    def derive(cls, product=None, *, switched_on=False):
        made.append((product, switched_on))
        return cls(total=int(total_mib * MiB), per_profile=int(per_mib * MiB), idle_seconds=idle)
    monkeypatch.setattr(rb().BudgetLimits, 'derive', classmethod(derive))
    return made


def held_call(ident, size=0, *, hold=True, text='x'):
    """A tools/call the test child holds until released (hold), its arguments padded to about size bytes."""
    arguments = {'hold': hold}
    if size:
        arguments['padding'] = text * (size // len(text.encode()))
    return {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
            'params': {'name': 'execute_method', 'arguments': arguments}}


def encoded(message, ensure_ascii=True):
    return json.dumps(message, separators=(',', ':'), ensure_ascii=ensure_ascii).encode()


class Child:
    """The child behind a switched-off gateway (MockTransport): holds a tools/call whose arguments say hold until
    release is set; answers a tools/call as an event stream that stays open until release when streaming; records the
    id and size of what it got."""

    def __init__(self):
        self.release = asyncio.Event()
        self.held = 0
        self.got = []  # (id, size)
        self.streaming = False

    async def __call__(self, request):
        message = json.loads(request.content) if request.content else {}
        self.got.append((message.get('id'), len(request.content)))
        arguments = (message.get('params') or {}).get('arguments') or {}
        if message.get('method') == 'tools/call' and self.streaming:
            release, ident = self.release, message['id']

            async def events():
                yield b': working\n\n'
                await release.wait()
                yield b'data: ' + encoded({'jsonrpc': '2.0', 'id': ident, 'result': {'content': []}}) + b'\n\n'
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=events())
        if message.get('method') == 'tools/call' and arguments.get('hold'):
            self.held += 1
            try:
                await self.release.wait()
            finally:
                self.held -= 1
        if 'id' not in message:
            return httpx.Response(202)
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': message['id'], 'result': {'content': []}})

    def ids(self):
        return [ident for ident, _ in self.got]


class Single:
    """A switched-off product's MCP app (make_apps without a body_budget: the add-on's own budget) and a client."""

    def __init__(self, app, client, store):
        self.app, self.client, self.store = app, client, store

    @property
    def budget(self):
        return self.app.state.body_budget.budget

    def headers(self, **extra):
        return {'Authorization': 'Bearer ' + self.store.load().token, 'Accept': ACCEPT,
                'Content-Type': 'application/json', 'Mcp-Session-Id': SESSION, **extra}

    def post(self, content, **extra):
        return self.client.post('/mcp', headers=self.headers(**extra), content=content)


@asynccontextmanager
async def single(tmp_path, child, product='odoo'):
    configure(tmp_path / product, product)
    store = ProductStore(tmp_path / product, product)
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(child)) as to_child:
            _, app = gateway.make_apps(store, TOOLS[product], to_child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://mcp',
                                         timeout=60) as client:
                yield Single(app, client, store)
    finally:
        store.close()


async def hold(gw, child, ident, size):
    """A request of size bytes that the child holds; returns once the child has it (its bytes charged)."""
    before = child.held
    task = asyncio.create_task(gw.post(encoded(held_call(ident, size))))
    await until(lambda: child.held == before + 1 or task.done(), 30)
    assert not task.done(), task.result().content[:200]
    return task


def busy(response, ident, *, status=None, scope=None):
    """The gateway's busy answer of the budget: 200 + -32003 under ident (503, id null, without one), Retry-After 5."""
    expected = status if status is not None else (503 if ident is None else 200)
    assert response.status_code == expected, (response.status_code, response.content[:300])
    assert response.headers['retry-after'] == '5' and response.headers['cache-control'] == 'no-store'
    body = response.json()
    assert body['id'] == ident and body['error']['code'] == -32003
    if scope is not None:
        assert body['error']['message'] == rb().budget_text(rb().BudgetExceeded(*scope))
    return body


def budget_warnings(log_scan, logger='mcp_admin_core.request_budget'):
    return [record.getMessage() for record in log_scan.records if record.name == logger
            and record.levelname == 'WARNING' and 'byte budget' in record.getMessage()]


# ---- switched off: the add-on's own budget ----

async def test_an_over_budget_request_is_refused_with_the_busy_reply_and_never_forwarded(tmp_path, log_scan,
                                                                                           monkeypatch):
    """PaaS T8's core: a large request the child holds has taken the budget; the next large one is refused at once by
    its declared length, its body drained, its id found in its head: 200 + -32003 + Retry-After 5, never forwarded.
    Small requests and notifications go on (the reserve's purpose); one WARNING, no content or token in it."""
    limits(monkeypatch, 16, 16)
    child = Child()
    async with single(tmp_path, child) as gw:
        log_scan.watch(gw.store.load().token, gw.store.load().child_token)
        first = await hold(gw, child, 1, 10 * MiB)
        assert 10 * MiB <= gw.budget.used() < 10 * MiB + 4096
        second = encoded(held_call(2, 10 * MiB))
        busy(await gw.post(second), 2, scope=('profile', 16 * MiB))
        assert 2 not in child.ids()
        ok = await gw.post(encoded({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                                    'params': {'name': 'execute_method', 'arguments': {}}}))
        assert ok.status_code == 200 and 'result' in ok.json()
        note = await gw.post(encoded({'jsonrpc': '2.0', 'method': 'notifications/initialized'}))
        assert note.status_code == 202
        child.release.set()
        assert (await first).status_code == 200
        assert gw.budget.used() == 0
    lines = budget_warnings(log_scan)
    assert lines == ['MCP gateway [profile=default]: its requests in progress held 16 MiB of request bodies, its share '
                     'of the byte budget; new large requests were answered busy (-32003) and not sent']


async def test_the_refusal_formats_for_a_get_a_batch_and_a_chunked_body(tmp_path, monkeypatch):
    """No id to answer under: a batch (HA's gateway never answers one), a GET (it carries no body; one declaring a
    large one is drained and refused), a chunked body cut off before its id: 503 + -32003 id null + Retry-After 5."""
    limits(monkeypatch, 16, 16)
    child = Child()
    async with single(tmp_path, child) as gw:
        first = await hold(gw, child, 1, 10 * MiB)
        batch = encoded([held_call(10, 5 * MiB), held_call(11, 5 * MiB)])
        busy(await gw.post(batch), None)
        get = await gw.client.request('GET', '/mcp', headers=gw.headers(), content=b' ' * (8 * MiB))
        busy(get, None)

        async def chunks():
            for _ in range(8):
                yield b'x' * MiB
        busy(await gw.post(chunks()), None)
        assert child.ids() == [1]
        child.release.set()
        await first
        assert gw.budget.used() == 0


async def test_a_chunked_request_within_the_budget_is_forwarded_and_given_back(tmp_path, monkeypatch):
    limits(monkeypatch, 16, 16)
    child = Child()
    async with single(tmp_path, child) as gw:
        body = encoded(held_call(5, 3 * MiB, hold=False))

        async def chunks():
            for start in range(0, len(body), MiB):
                yield body[start:start + MiB]
        response = await gw.post(chunks())
        assert response.status_code == 200 and 'result' in response.json()
        assert gw.budget.used() == 0 and gw.budget.peak >= 3 * MiB


async def test_a_chunked_request_refused_mid_stream_still_gets_its_id_back(tmp_path, monkeypatch):
    """PaaS N5: a body without Content-Length passes the budget while it is read: its id is in its head, so 200 +
    -32003 under it (not 503 id null); nothing reaches the child."""
    limits(monkeypatch, 16, 16)
    child = Child()
    async with single(tmp_path, child) as gw:
        first = await hold(gw, child, 1, 10 * MiB)

        async def chunks():
            yield b'{"jsonrpc":"2.0","id":77,"method":"tools/call","params":{"padding":"' + b'x' * (MiB - 80)
            for _ in range(8):
                yield b'x' * MiB
        busy(await gw.post(chunks()), 77)
        assert 77 not in child.ids()
        child.release.set()
        await first
        assert gw.budget.used() == 0


async def test_a_legitimate_13_mib_upload_passes_with_the_default_budget(tmp_path, monkeypatch):
    """The derived default (here a 1 GiB ceiling, cgroup or MemAvailable less the reserve): every share holds one
    request of the single-request ceiling, so a Nextcloud-size upload (10 MiB as base64) passes."""
    for source, ceiling in (('cgroup', 1024), ('meminfo', 1024)):
        monkeypatch.setattr(rb(), 'memory_ceiling', lambda: (ceiling, source))
        child = Child()
        async with single(tmp_path / source, child) as gw:
            assert gw.budget.limits.source == source and gw.app.state.body_budget.limit >= 16 * MiB
            response = await gw.post(encoded(held_call(9, int(13.3 * MiB), hold=False)))
            assert response.status_code == 200 and 'result' in response.json(), response.content[:200]
            assert gw.budget.used() == 0


async def test_a_flood_of_large_requests_never_holds_more_than_the_budget(tmp_path, monkeypatch):
    """20 requests of 4 MiB at once (one body, shared): what the gateway holds never passes 16 MiB; some reach the
    child, the others are answered busy under their id; all of it goes back."""
    limits(monkeypatch, 16, 16)
    child = Child()
    async with single(tmp_path, child) as gw:
        body = encoded(held_call(100, 4 * MiB))
        tasks = [asyncio.create_task(gw.post(body)) for _ in range(20)]
        await until(lambda: child.held >= 3, 30)
        await asyncio.sleep(.3)
        child.release.set()
        results = await asyncio.gather(*tasks)
        admitted = [r for r in results if 'result' in r.json()]
        refused = [r for r in results if r.json().get('error', {}).get('code') == -32003]
        assert len(admitted) + len(refused) == 20 and refused and len(admitted) >= 3
        assert gw.budget.peak <= 16 * MiB
        assert gw.budget.used() == 0


async def test_the_budget_is_given_back_however_a_request_ends(tmp_path, monkeypatch):
    """PaaS test_budget_returns_after_abandoned_queue_client_disconnect_and_refusals, its transport case and
    test_proxy_wrapper_returns_the_budget_when_the_request_raises: a client cancelled while its body is read or while
    its call waits, a busy forwarding slot (503: switched off), the child's connection failing (502), an event stream
    that ends (its bytes stay charged until then: HM-08 review MF-1), an exception in the gateway: every byte goes
    back."""
    limits(monkeypatch, 64, 64)
    child = Child()
    async with single(tmp_path, child) as gw:
        opened = asyncio.Event()

        async def stalled():
            yield b'{"jsonrpc":"2.0","id":1,' + b' ' * MiB
            await opened.wait()
        reading = asyncio.create_task(gw.post(stalled()))
        await until(lambda: gw.budget.used() >= MiB)
        reading.cancel()
        await asyncio.gather(reading, return_exceptions=True)
        await until(lambda: gw.budget.used() == 0)
        waiting = await hold(gw, child, 2, 2 * MiB)
        waiting.cancel()
        await asyncio.gather(waiting, return_exceptions=True)
        await until(lambda: gw.budget.used() == 0 and child.held == 0)
        child.streaming = True
        stream = asyncio.create_task(gw.post(encoded(held_call(3, MiB, hold=False))))
        await until(lambda: 3 in child.ids())
        await asyncio.sleep(.05)
        assert gw.budget.used() >= MiB  # the stream is open: its bytes stay charged
        child.release.set()
        assert (await stream).status_code == 200
        assert gw.budget.used() == 0

    class Broken:
        async def __call__(self, request):
            raise httpx.ReadError('the child connection broke', request=request)
    async with single(tmp_path / 'broken', Broken()) as gw:
        assert (await gw.post(encoded(held_call(4, MiB)))).status_code == 502
        assert gw.budget.used() == 0
        real = gateway.authorize
        try:
            def boom(*args):
                raise RuntimeError('boom')
            gateway.authorize = boom
            with pytest.raises(RuntimeError):
                await gw.post(encoded(held_call(5, MiB)))
        finally:
            gateway.authorize = real
        assert gw.budget.used() == 0


async def test_the_forwarded_size_is_charged_and_a_body_that_does_not_fit_as_forwarded_is_not_sent(tmp_path,
                                                                                                    monkeypatch):
    """HA's own rule (HM-08 review S-1; contract 9): the gateway re-serializes a body with ASCII escapes, an emoji as 12
    bytes; 6 MiB of emoji read is 18 MiB forwarded, more than the 16 MiB share: refused once read, 200 + -32003 under
    its id, and the child never gets it. 4 MiB of emoji (12 MiB forwarded) fits and is charged as forwarded."""
    limits(monkeypatch, 16, 16)
    child = Child()
    async with single(tmp_path, child) as gw:
        large = encoded(held_call(6, 6 * MiB, hold=False, text='\U0001F600'), ensure_ascii=False)
        assert len(large) < 6.1 * MiB
        busy(await gw.post(large), 6, scope=('profile', 16 * MiB))
        assert 6 not in child.ids()
        smaller = encoded(held_call(7, 4 * MiB, text='\U0001F600'), ensure_ascii=False)
        task = asyncio.create_task(gw.post(smaller))
        await until(lambda: child.held == 1)
        assert 3 * len(smaller) - 1024 < gw.budget.used() <= 3 * len(smaller)
        child.release.set()
        assert (await task).status_code == 200 and gw.budget.used() == 0


# ---- the idle body and the whole read (PaaS round 2 P2-D, round 3 F5) ----

async def test_an_idle_upload_is_dropped_with_408_and_its_bytes_given_back(tmp_path, monkeypatch):
    """A large request that declares 15 MiB, sends a little, then nothing: after the idle limit (0.3 s here, 30 s in
    the add-on) 408 + -32003 id null + Retry-After 5 + Connection: close, and its 15 MiB go back at once; a large
    request after it passes."""
    limits(monkeypatch, 16, 16, idle=.3)
    child = Child()
    async with single(tmp_path, child) as gw:
        stop = asyncio.Event()

        async def stall():
            yield b'{"jsonrpc":"2.0","id":1,'
            await stop.wait()
        task = asyncio.create_task(gw.post(stall(), **{'Content-Length': str(15 * MiB)}))
        await until(lambda: gw.budget.used() == 15 * MiB)
        response = await asyncio.wait_for(task, 5)
        assert response.status_code == 408
        assert response.headers['retry-after'] == '5' and response.headers['connection'] == 'close'
        assert response.json() == {'jsonrpc': '2.0', 'id': None, 'error': {
            'code': -32003, 'message': rb().idle_text(.3)}}
        assert gw.budget.used() == 0
        ok = await gw.post(encoded(held_call(2, 5 * MiB, hold=False)))
        assert ok.status_code == 200 and 'result' in ok.json()
        assert child.ids() == [2]


async def test_a_slow_but_steady_upload_is_not_cut_off(tmp_path, monkeypatch):
    limits(monkeypatch, 32, 32, idle=1)
    child = Child()
    async with single(tmp_path, child) as gw:
        body = encoded(held_call(3, 2 * MiB, hold=False))
        step = len(body) // 4 + 1

        async def slow():
            for start in range(0, len(body), step):  # 4 parts, 0.4 s apart: never idle 1 s, longer than it in all
                yield body[start:start + step]
                await asyncio.sleep(.4)
        response = await gw.post(slow())
        assert response.status_code == 200 and 'result' in response.json()
        assert gw.budget.used() == 0


async def test_small_requests_are_neither_charged_nor_cut_off_when_idle(tmp_path, monkeypatch):
    """A body that declares at most 64 KiB is not watched: sent after a pause longer than the idle limit, it is
    answered (HA's whole-read limit of 60 s still applies to it, as before)."""
    limits(monkeypatch, 16, 16, idle=.2)
    child = Child()
    async with single(tmp_path, child) as gw:
        body = encoded({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call',
                        'params': {'name': 'execute_method', 'arguments': {}}})

        async def late():
            await asyncio.sleep(.5)
            yield body
        response = await gw.post(late(), **{'Content-Length': str(len(body))})
        assert response.status_code == 200 and 'result' in response.json()
        assert gw.budget.peak == 0


async def test_a_trickling_upload_ends_at_the_whole_read_limit_as_before(tmp_path, monkeypatch):
    """PaaS F5 (a byte every 29 s never trips the idle limit) is HA's existing whole-read limit (BODY_SECONDS, 60 s for
    every request; PaaS 300 s for large ones): here 1 s, a byte every 0.1 s with a 2 s idle limit (never reached):
    today's 408 {"error":"request denied"}, the bytes given back."""
    limits(monkeypatch, 16, 16, idle=2)
    monkeypatch.setattr(gateway, 'BODY_SECONDS', 1)
    child = Child()
    async with single(tmp_path, child) as gw:
        async def trickle():
            yield b'{"jsonrpc":"2.0","id":1,'
            for _ in range(100):
                await asyncio.sleep(.1)
                yield b' '
        task = asyncio.create_task(gw.post(trickle(), **{'Content-Length': str(15 * MiB)}))
        await until(lambda: gw.budget.used() == 15 * MiB)
        response = await asyncio.wait_for(task, 10)
        assert (response.status_code, response.json()) == (408, {'error': 'request denied'})
        assert gw.budget.used() == 0 and child.ids() == []


async def test_a_client_leaving_while_its_refused_body_is_drained_is_no_error(tmp_path, monkeypatch, log_scan):
    """PaaS N2: a refused body's client leaves while it is drained: the gateway answers nothing anyone receives (499,
    as for a client gone while it waited) and raises nothing."""
    limits(monkeypatch, 16, 16)
    child = Child()
    async with single(tmp_path, child) as gw:
        first = await hold(gw, child, 1, 10 * MiB)
        token = gw.store.load().token
        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': 'POST', 'scheme': 'http',
                 'path': '/mcp', 'raw_path': b'/mcp', 'query_string': b'', 'root_path': '', 'server': ('mcp', 80),
                 'client': ('127.0.0.1', 1),
                 'headers': [(b'authorization', ('Bearer ' + token).encode()), (b'content-type', b'application/json'),
                             (b'accept', ACCEPT.encode()), (b'mcp-session-id', SESSION.encode()),
                             (b'content-length', str(10 * MiB).encode())]}
        messages = iter([{'type': 'http.request', 'body': b'{"jsonrpc":"2.0","id":9,' + b' ' * MiB, 'more_body': True},
                         {'type': 'http.disconnect'}])
        sent = []

        async def receive():
            return next(messages)

        async def send(message):
            sent.append(message)
        await gw.app(scope, receive, send)
        assert [m['status'] for m in sent if m['type'] == 'http.response.start'] == [gateway.CLIENT_CLOSED]
        assert 9 not in child.ids() and gw.budget.used() >= 10 * MiB
        child.release.set()
        await first
        assert gw.budget.used() == 0
    assert not [record for record in log_scan.records if record.levelname == 'ERROR']


async def test_the_budget_is_made_with_the_apps(tmp_path, monkeypatch):
    """PaaS round 2 P2-C (the budget made at startup, not at the first request): make_apps derives a switched-off
    add-on's budget when it is called (one account of the product); a switched-on ProfileManager derives one budget for
    the add-on when it is made (every profile the product may run). No environment variable is read (contract 9)."""
    from mcp_admin_core import profile_runtime

    made = limits(monkeypatch, 16, 16)
    configure(tmp_path / 'odoo', 'odoo')
    store = ProductStore(tmp_path / 'odoo', 'odoo')
    try:
        async with httpx.AsyncClient() as to_child:
            _, app = gateway.make_apps(store, TOOLS['odoo'], to_child)
        assert made == [('odoo', False)] and app.state.body_budget.budget.used() == 0
        manager = profile_runtime.ProfileManager(store, 'odoo', TOOLS['odoo'], lambda *a, **k: None)
        assert made[-1] == ('odoo', True) and manager.budget.limits.total == 16 * MiB
    finally:
        store.close()



@pytest.mark.parametrize('product', golden.PRODUCTS)
async def test_every_products_runtime_reads_under_the_budget_and_the_guard(tmp_path, log_scan, monkeypatch, product):
    """Not gated (contract 1.2; PaaS #155's apps/<product>/tests/test_request_structure_guard.py): every product's
    production runtime (run_product; apps/n8n/run.py for n8n), switched off, serves its MCP listener with the add-on's
    own budget (one account of the product's child estimate; here a 2 GiB cgroup ceiling, the default profile's share
    capped at 64 MiB) and the structure guard: a body nested 70 deep is refused 200 + -32602 under its id, a UTF-16 one
    413, and the child gets neither."""
    monkeypatch.setattr(rb(), 'memory_ceiling', lambda: (2048, 'cgroup'))
    data = tmp_path / 'data'
    configure(data, product)
    async with production_runtime(product, data) as runtime:
        token = stored(data)['token']
        log_scan.watch(token, stored(data)['child_token'])
        share = runtime.mcp_app.state.body_budget
        _, child_mib = rb().runtime_inputs(product, switched_on=False)
        assert share.profile_id == 'default'
        assert share.budget.limits.total == rb().default_total_bytes(2048, accounts=1, child_memory_mib=child_mib)
        assert share.limit == min(64 * MiB, rb().default_per_profile_bytes(share.budget.limits.total))
        deep = {}
        nested = deep
        for _ in range(70):
            nested['hm31-deep'] = {}
            nested = nested['hm31-deep']
        message = {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call', 'params': {'name': 'x', 'arguments': deep}}
        headers = {'Authorization': 'Bearer ' + token, 'Accept': ACCEPT, 'Content-Type': 'application/json'}
        async with runtime.mcp() as client:
            refused = await client.post('/mcp', headers=headers, content=encoded(message))
            assert refused.status_code == 200 and refused.json()['id'] == 7, refused.content[:200]
            assert refused.json()['error']['code'] == -32602 and 'levels of nesting' in refused.text
            utf16 = await client.post('/mcp', headers=headers,
                                      content=json.dumps({**message, 'params': {}}).encode('utf-16'))
            assert utf16.status_code == 413 and 'not UTF-8' in utf16.json()['error']['message']
        assert not any(b'hm31-deep' in (request.content or b'') for request in runtime.child.requests)


# ---- the declared length, the single-request ceiling and a refused body's drain (HM-31 review MF-1, MF-3, S-2) ----

def raw_scope(token, extra, method='POST', session=SESSION):
    """An MCP request's ASGI scope as uvicorn hands it (header names in lower case), the test's framing headers last.
    h11 0.16.0 (the add-on's HTTP parser: no httptools in its environment) frames a request that has both
    Content-Length and Transfer-Encoding: chunked by its chunks and hands content-length on as sent (review MF-1)."""
    headers = [(b'host', b'mcp'), (b'authorization', b'Bearer ' + token.encode()), (b'accept', ACCEPT.encode()),
               (b'content-type', b'application/json'), (b'mcp-session-id', session.encode()), *extra]
    return {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': method, 'scheme': 'http',
            'path': '/mcp', 'raw_path': b'/mcp', 'query_string': b'', 'root_path': '', 'headers': headers,
            'client': ('127.0.0.1', 1), 'server': ('mcp', 80)}


async def drive(app, scope, pieces, *, observe=None, stall_after=None, gap=0.0):
    """Hand pieces to app as uvicorn does (observe() after each one); after stall_after pieces, or the last, nothing
    more until the answer is sent, then the client leaves. (status, body, the number of pieces handed)."""
    sent, handed = [], [0]
    done = asyncio.Event()

    async def receive():
        if handed[0] < len(pieces) and (stall_after is None or handed[0] < stall_after):
            if gap:
                await asyncio.sleep(gap)
            piece = pieces[handed[0]]
            handed[0] += 1
            if observe is not None:
                observe()
            return {'type': 'http.request', 'body': piece, 'more_body': handed[0] < len(pieces)}
        await done.wait()
        return {'type': 'http.disconnect'}

    async def send(message):
        sent.append(message)
        if message['type'] == 'http.response.body' and not message.get('more_body'):
            done.set()
    await app(scope, receive, send)
    start = next(message for message in sent if message['type'] == 'http.response.start')
    return (start['status'], b''.join(message.get('body', b'') for message in sent
                                      if message['type'] == 'http.response.body'), handed[0])


def pieces_of(body, size=256 * 1024):
    return [body[start:start + size] for start in range(0, len(body), size)]


@pytest.mark.parametrize('stated', [b'10', b'70000'], ids=['small', 'large'])
async def test_a_declared_length_beside_a_chunked_framing_is_not_the_body_s(tmp_path, monkeypatch, stated):
    """Review MF-1 (RFC 9112 6.3: Transfer-Encoding frames the body, Content-Length is then ignored): a body that states
    10 (or 70,000) bytes and sends 10 MiB chunked is charged as it arrives, as one without Content-Length is, so it is
    cut off once it does not fit (200 + -32003 under the id its head shows; never forwarded). Before the fix the
    stated 10 bytes left it unwatched and uncharged, the stated 70,000 charged only them: either way the whole body
    was read outside the budget."""
    limits(monkeypatch, 16, 16)
    child = Child()
    async with single(tmp_path, child) as gw:
        first = await hold(gw, child, 1, 10 * MiB)
        pieces = pieces_of(encoded(held_call(2, 10 * MiB)))
        seen = []
        status, answer, handed = await drive(gw.app, raw_scope(gw.store.load().token, [
            (b'content-length', stated), (b'transfer-encoding', b'chunked')]), pieces,
            observe=lambda: seen.append(gw.budget.used()))
        assert status == 200 and json.loads(answer)['id'] == 2 and json.loads(answer)['error']['code'] == -32003
        assert handed < len(pieces), f'the whole body ({len(pieces)} pieces) was read outside the budget'
        assert max(seen) > 10 * MiB and 2 not in child.ids()
        child.release.set()
        await first
        assert gw.budget.used() == 0


async def test_a_declared_length_beside_a_chunked_framing_does_not_escape_the_idle_limit(tmp_path, monkeypatch):
    """Review MF-1: a body that states 10 bytes, sends a large first chunk and then nothing is watched for idleness as
    any large body is: the idle 408 (-32003, Connection: close) after the limit (0.3 s here), its bytes given back."""
    limits(monkeypatch, 16, 16, idle=.3)
    child = Child()
    async with single(tmp_path, child) as gw:
        pieces = pieces_of(encoded(held_call(3, 2 * MiB, hold=False)), MiB)
        started = asyncio.get_running_loop().time()
        status, answer, handed = await asyncio.wait_for(drive(gw.app, raw_scope(gw.store.load().token, [
            (b'content-length', b'10'), (b'transfer-encoding', b'chunked')]), pieces, stall_after=1), 10)
        assert (status, handed) == (408, 1)
        assert json.loads(answer) == {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32003,
                                                                              'message': rb().idle_text(.3)}}
        assert asyncio.get_running_loop().time() - started < 5
        assert gw.budget.used() == 0 and child.ids() == []


async def test_the_production_listener_charges_and_watches_a_chunked_body_that_states_a_small_length(
        tmp_path, log_scan, monkeypatch):
    """Review MF-1 over a real socket: the add-on's own uvicorn 0.38.0 and h11 0.16.0 (run_product's listener). A POST
    that states Content-Length: 10 and sends its body chunked is charged as its chunks arrive (here 1 MiB) and, once it
    stalls, gets the idle 408 (0.3 s here) with Connection: close, not the whole-read limit's (5 s here); the child
    gets nothing and every byte goes back."""
    limits(monkeypatch, 16, 16, idle=.3)
    monkeypatch.setattr(gateway, 'BODY_SECONDS', 5)
    data = tmp_path / 'data'
    configure(data, 'odoo')
    async with production_runtime('odoo', data, sockets=True) as runtime:
        token = stored(data)['token']
        log_scan.watch(token, stored(data)['child_token'])
        budget = runtime.mcp_app.state.body_budget.budget
        chunk = (b'{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"x","arguments":{"hm31-cl-te":"'
                 + b'x' * MiB)
        reader, writer = await asyncio.open_connection('127.0.0.1', runtime.mcp_port)
        try:
            writer.write(b'POST /mcp HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer ' + token.encode()
                         + b'\r\nAccept: ' + ACCEPT.encode() + b'\r\nContent-Type: application/json\r\n'
                         + b'Content-Length: 10\r\nTransfer-Encoding: chunked\r\n\r\n'
                         + b'%x\r\n' % len(chunk) + chunk + b'\r\n')
            await writer.drain()
            await until(lambda: budget.used() >= MiB, 5)  # charged as it arrives
            started = asyncio.get_running_loop().time()
            async with asyncio.timeout(10):
                answer = await reader.read()  # the server closes the connection once it answered
            elapsed = asyncio.get_running_loop().time() - started
        finally:
            writer.close()
            await asyncio.gather(writer.wait_closed(), return_exceptions=True)
        head, _, payload = answer.partition(b'\r\n\r\n')
        assert head.startswith(b'HTTP/1.1 408 ') and b'\r\nconnection: close' in head.lower(), head
        assert json.loads(payload) == {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32003,
                                                                               'message': rb().idle_text(.3)}}
        assert elapsed < 3
        await until(lambda: budget.used() == 0, 5)  # the request's task gives its bytes back once its answer is out
        assert not any(b'hm31-cl-te' in (request.content or b'') for request in runtime.child.requests)


async def test_a_body_declared_over_the_single_request_ceiling_gets_todays_413_before_a_byte_is_read(
        tmp_path, monkeypatch, log_scan):
    """Review MF-3: a body that states more than 16 MiB can never be served. Today's 413 {"error":"request denied"}
    before a byte of it is read, with part of the budget held or none: never charged, never the budget's retryable
    200 + -32003 (PaaS: not charged, 413; n8n's read_body refuses it before reading too). A body framed chunked is
    judged by what arrives whatever its Content-Length says (RFC 9112 6.3): a small one stating 17 MiB is answered as
    before."""
    limits(monkeypatch, 16, 16)
    child = Child()
    async with single(tmp_path, child) as gw:
        handed = []

        async def seventeen():
            handed.append(0)
            yield b'{"jsonrpc":"2.0","id":38,"method":"tools/call","params":{"pad":"'
            for _ in range(17):
                handed.append(0)
                yield b'x' * MiB
        stated = {'Content-Length': str(17 * MiB + 100)}
        response = await gw.post(seventeen(), **stated)
        assert (response.status_code, response.json()) == (413, {'error': 'request denied'}), response.content[:200]
        first = await hold(gw, child, 1, 10 * MiB)
        response = await gw.post(seventeen(), **stated)
        assert (response.status_code, response.json()) == (413, {'error': 'request denied'}), response.content[:200]
        assert handed == [] and 38 not in child.ids()
        small = encoded(held_call(39, hold=False))
        status, answer, _ = await drive(gw.app, raw_scope(gw.store.load().token, [
            (b'content-length', str(17 * MiB).encode()), (b'transfer-encoding', b'chunked')]), [small])
        assert status == 200 and json.loads(answer) == {'jsonrpc': '2.0', 'id': 39, 'result': {'content': []}}
        child.release.set()
        await first
        assert gw.budget.used() == 0
    assert [record.getMessage() for record in log_scan.records if record.name == 'mcp_admin_core.request_budget'
            and 'too-large' in record.getMessage()] == [
        f'MCP gateway [profile=default]: refused a request body (too-large, HTTP 413): body exceeds {16 * MiB} bytes']


async def test_a_refused_bodys_drain_stops_at_the_idle_limit(tmp_path, monkeypatch):
    """Review S-2: a declared body refused before it is read, whose client then stops sending, is answered after the
    idle limit (0.3 s here), not held open until the whole-read limit."""
    limits(monkeypatch, 16, 16, idle=.3)
    child = Child()
    async with single(tmp_path, child) as gw:
        first = await hold(gw, child, 1, 10 * MiB)
        pieces = [b'{"jsonrpc":"2.0","id":31,"method":"tools/call","params":{"x":"', b'x' * MiB, b'x' * MiB]
        started = asyncio.get_running_loop().time()
        status, answer, handed = await asyncio.wait_for(drive(gw.app, raw_scope(gw.store.load().token, [
            (b'content-length', str(10 * MiB).encode())]), pieces, stall_after=2), 10)
        assert handed == 2 and asyncio.get_running_loop().time() - started < 5
        assert status == 200 and json.loads(answer)['id'] == 31 and json.loads(answer)['error']['code'] == -32003
        child.release.set()
        await first


async def test_a_refused_bodys_drain_stops_at_the_whole_read_limit(tmp_path, monkeypatch):
    """Review S-2: a refused body that trickles (never idle long enough) is answered at the whole-read limit (1 s
    here), not when its client is done."""
    limits(monkeypatch, 16, 16, idle=2)
    monkeypatch.setattr(gateway, 'BODY_SECONDS', 1)
    child = Child()
    async with single(tmp_path, child) as gw:
        first = await hold(gw, child, 1, 10 * MiB)
        pieces = [b'{"jsonrpc":"2.0","id":32,"method":"tools/call","params":{"x":"'] + [b'x'] * 200
        started = asyncio.get_running_loop().time()
        status, answer, handed = await asyncio.wait_for(drive(gw.app, raw_scope(gw.store.load().token, [
            (b'content-length', str(10 * MiB).encode())]), pieces, gap=.05), 10)
        assert status == 200 and json.loads(answer)['id'] == 32
        assert asyncio.get_running_loop().time() - started < 4 and handed < len(pieces)
        child.release.set()
        await first


async def test_a_refused_bodys_drain_keeps_only_its_head_and_tail(tmp_path, monkeypatch):
    """Review S-2: draining a refused 10 MiB body holds its two 4 KiB windows, not the body (the Python heap grows by
    less than 2 MiB while it is drained and answered)."""
    limits(monkeypatch, 16, 16)
    child = Child()
    async with single(tmp_path, child) as gw:
        first = await hold(gw, child, 1, 10 * MiB)
        chunk = b'x' * (256 * 1024)
        pieces = [b'{"jsonrpc":"2.0","id":33,"method":"tools/call","params":{"x":"'] + [chunk] * 39 + [b'"}}']
        scope = raw_scope(gw.store.load().token, [(b'content-length', str(sum(map(len, pieces))).encode())])
        tracemalloc.start()
        try:
            base = tracemalloc.get_traced_memory()[0]
            status, answer, handed = await drive(gw.app, scope, pieces)
            peak = tracemalloc.get_traced_memory()[1] - base
        finally:
            tracemalloc.stop()
        assert status == 200 and json.loads(answer)['id'] == 33 and handed == len(pieces)
        assert peak < 2 * MiB, peak
        child.release.set()
        await first


async def test_an_sdk_ordered_refused_body_gets_its_id_from_its_tail(tmp_path, monkeypatch):
    """Review S-2: the MCP SDK writes {"method":...,"params":...,"jsonrpc":"2.0","id":N}; a declared body refused before
    it is read is drained and its id found in its tail: 200 + -32003 under it (PaaS _refuse_over_budget), not 503."""
    limits(monkeypatch, 16, 16)
    child = Child()
    async with single(tmp_path, child) as gw:
        first = await hold(gw, child, 1, 10 * MiB)
        body = json.dumps({'method': 'tools/call', 'params': {'name': 'execute_method',
                                                              'arguments': {'padding': 'x' * (10 * MiB)}},
                           'jsonrpc': '2.0', 'id': 34}, separators=(',', ':')).encode()
        busy(await gw.post(body), 34, scope=('profile', 16 * MiB))
        assert 34 not in child.ids()
        child.release.set()
        await first

# ---- switched on: every profile's share of one budget ----

def extra_child(data, profile_id=B, port=18000):
    return GatewayChild('p' + profile_id[:4], PRODUCT, profiles.Layout(data).profile(profile_id))


@asynccontextmanager
async def switched(tmp_path, monkeypatch, log_scan, total_mib, per_mib):
    limits(monkeypatch, total_mib, per_mib)
    data = setup(tmp_path)
    children = Children()
    children.add(3000, GatewayChild('default', PRODUCT, data))
    children.add(18000, extra_child(data))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        yield runtime, children


def padded(ident, size):
    return encoded({'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
                    'params': {'name': call(0)['params']['name'], 'arguments': {**call(0)['params']['arguments'],
                                                                               'padding': 'x' * size}}})


async def test_one_profile_filling_its_share_does_not_affect_another(tmp_path, monkeypatch, log_scan):
    """The add-on's budget 32 MiB, each share 16: the default profile holds 10 MiB, its next 10 MiB is refused (its
    share, -32003 under its id); B's 10 MiB passes meanwhile (PaaS test_one_profile_filling_its_share...)."""
    async with switched(tmp_path, monkeypatch, log_scan, 32, 16) as (runtime, children):
        budget = runtime.manager.budget
        default, child_b = children.by_port[3000], children.by_port[18000]
        async with runtime.mcp(timeout=60) as client:
            headers = {token: {**bearer(runtime.token(token)), 'Mcp-Session-Id': await session_of(
                client, runtime.token(token))} for token in ('default', B)}
            default.hold_calls = child_b.hold_calls = True
            first = asyncio.create_task(client.post('/mcp', headers=headers['default'], content=padded(1, 10 * MiB)))
            await until(lambda: default.waiting == 1, 30)
            busy(await client.post('/mcp', headers=headers['default'], content=padded(2, 10 * MiB)), 2,
                 scope=('profile', 16 * MiB))
            other = asyncio.create_task(client.post('/mcp', headers=headers[B], content=padded(3, 10 * MiB)))
            await until(lambda: child_b.waiting == 1, 30)
            assert 10 * MiB <= budget.used('default') < 11 * MiB and 10 * MiB <= budget.used(B) < 11 * MiB
            default.free.set()
            child_b.free.set()
            assert [r.status_code for r in await asyncio.gather(first, other)] == [200, 200]
            assert budget.used() == 0
        lines = budget_warnings(log_scan, 'mcp_admin_core.profile_router')
        assert lines and all(line.startswith('MCP gateway [profile=default]:') for line in lines)


async def test_the_add_ons_budget_is_shared_by_every_profile(tmp_path, monkeypatch, log_scan):
    """The add-on's budget 16 MiB: the default profile holds 10 MiB, so B's 10 MiB is refused though B holds nothing
    (the add-on's limit, -32003 under its id: PaaS test_global_budget_is_shared_by_all_profiles)."""
    async with switched(tmp_path, monkeypatch, log_scan, 16, 16) as (runtime, children):
        default = children.by_port[3000]
        async with runtime.mcp(timeout=60) as client:
            headers = {token: {**bearer(runtime.token(token)), 'Mcp-Session-Id': await session_of(
                client, runtime.token(token))} for token in ('default', B)}
            default.hold_calls = True
            first = asyncio.create_task(client.post('/mcp', headers=headers['default'], content=padded(1, 10 * MiB)))
            await until(lambda: default.waiting == 1, 30)
            busy(await client.post('/mcp', headers=headers[B], content=padded(2, 10 * MiB)), 2,
                 scope=('global', 16 * MiB))
            assert runtime.manager.budget.used(B) == 0
            default.free.set()
            assert (await first).status_code == 200
            assert runtime.manager.budget.used() == 0
        lines = budget_warnings(log_scan, 'mcp_admin_core.profile_router')
        assert any(line.startswith('MCP gateway [profile=' + B[:8] + ']:') and "the add-on's byte budget" in line
                   for line in lines)


async def test_a_switched_on_profile_shares_one_budget_derived_once(tmp_path, monkeypatch, log_scan):
    """Every profile's app charges its share of the manager's one budget (ProfileGate.budget_share), capped at the
    profile's quota (64 MiB, DQ-07) and at half the add-on's budget."""
    async with switched(tmp_path, monkeypatch, log_scan, 200, 100) as (runtime, _):
        budget = runtime.manager.budget
        for profile_id in ('default', B):
            share = runtime.gate(profile_id).budget_share
            assert share.budget is budget and share.limit == 64 * MiB
            assert runtime.manager.get(profile_id).runtime.mcp_app.state.body_budget is share


async def test_a_switched_on_profiles_chunked_body_that_states_a_small_length_is_charged_as_it_arrives(
        tmp_path, monkeypatch, log_scan):
    """Review MF-1, switched on (HM-08's dispatcher counted the bytes it read: no regression): the default profile's
    share is 16 MiB and 10 MiB of it is held; its tools/call that states Content-Length: 10 and sends 10 MiB chunked is
    cut off once it does not fit (200 + -32003 under its id), not read whole and refused only once forwarded."""
    async with switched(tmp_path, monkeypatch, log_scan, 32, 16) as (runtime, children):
        default = children.by_port[3000]
        budget = runtime.manager.budget
        async with runtime.mcp(timeout=60) as client:
            token = runtime.token('default')
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            default.hold_calls = True
            first = asyncio.create_task(client.post('/mcp', headers=headers, content=padded(1, 10 * MiB)))
            await until(lambda: default.waiting == 1, 30)
            pieces = pieces_of(padded(2, 10 * MiB))
            scope = raw_scope(token, [(b'content-length', b'10'), (b'transfer-encoding', b'chunked')],
                              session=headers['Mcp-Session-Id'])
            seen = []
            status, answer, handed = await drive(runtime.mcp_app, scope, pieces,
                                                 observe=lambda: seen.append(budget.used('default')))
            assert status == 200 and json.loads(answer)['id'] == 2 and json.loads(answer)['error']['code'] == -32003
            assert handed < len(pieces), f'the whole body ({len(pieces)} pieces) was read outside the budget'
            assert max(seen) > 10 * MiB and ('POST', 'tools/call', 2) not in default.seen
            default.free.set()
            assert (await first).status_code == 200
            assert budget.used() == 0
