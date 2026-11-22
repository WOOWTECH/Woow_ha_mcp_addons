"""Global Odoo reply tickets across slow ASGI sends and cancellation."""

import asyncio
import json

import httpx
import pytest

from multi_profile_runtime import Children, multi_profile_runtime
from mcp_admin_core import gateway, profile_router, profiles, reply_memory, request_budget
from test_profile_runtime import ProfileChild
from test_single_profile_golden import ACCEPT, configure, initialize_message
from switched_gateway import B, PRODUCT, Exchange, GatewayChild, bearer, call, ping, setup, session_of, until, watch
from log_scan import log_scan  # noqa: F401 (fixture)

pytestmark = pytest.mark.asyncio


@pytest.mark.usefixtures('log_scan')
@pytest.mark.parametrize('profile_id,cap', [('default', 3), (B, 1)])
async def test_real_gateway_stream_cap_is_ticket_backed_429(tmp_path, log_scan, profile_id, cap):
    data = setup(tmp_path)
    children = Children()
    children.add(3000, GatewayChild('default', PRODUCT, data))
    children.add(18000, GatewayChild('p' + B[:4], PRODUCT, profiles.Layout(data).profile(B)))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        async with runtime.mcp() as client:
            token = runtime.token(profile_id)
            session = await session_of(client, token)
            headers = {**bearer(token), 'Mcp-Session-Id': session}
            streams = [Exchange(runtime.mcp_app, 'GET', '/mcp', list(headers.items())).start()
                       for _ in range(cap)]
            await until(lambda: all(b': open' in stream.content for stream in streams))
            assert runtime.manager.reply_memory.by_profile[profile_id] == cap
            denied = await client.get('/mcp', headers=headers)
            assert denied.status_code == 429 and denied.headers['retry-after'] == '30'
            assert denied.json() == {'jsonrpc': '2.0', 'id': None, 'error': {
                'code': -32003, 'message': profile_router.streams_text(cap, ticketed=True)}}
            # Bounded controls remain available even when all stream tickets are held.
            control = await client.post('/mcp', headers=headers, json=ping(20))
            assert control.status_code == 200 and control.json()['result'] == {}
            children.by_port[3000 if profile_id == 'default' else 18000].free.set()
            await asyncio.wait_for(asyncio.gather(*(stream.task for stream in streams)), 5)
        assert runtime.manager.reply_memory.held == 0


@pytest.mark.usefixtures('log_scan')
@pytest.mark.parametrize('ending', ['reply', 'cancel'])
async def test_second_real_child_call_gets_ticket_busy_then_runs_after_first_ends(tmp_path, log_scan, ending):
    """The one-ticket extra cap refuses a write before child dispatch, then releases on send or cancellation."""
    data = setup(tmp_path)
    children = Children()
    children.add(3000, GatewayChild('default', PRODUCT, data))
    child = children.add(18000, GatewayChild('p' + B[:4], PRODUCT, profiles.Layout(data).profile(B)))
    child.hold_calls = True
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        async with runtime.mcp() as client:
            token = runtime.token(B)
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            first = asyncio.create_task(client.post('/mcp', headers=headers, json=call(101)))
            await until(lambda: child.waiting == 1)
            assert runtime.manager.reply_memory.held == reply_memory.TICKET_BYTES
            refused = await client.post('/mcp', headers=headers, json=call(102))
            assert refused.status_code == 200 and refused.headers['retry-after'] == '5'
            assert refused.json() == {'jsonrpc': '2.0', 'id': 102, 'error': {
                'code': -32003, 'message': profile_router.global_reply_text()}}
            assert child.client_calls() == [101], 'the busy write was dispatched to the child'
            if ending == 'reply':
                child.free.set()
                answer = await asyncio.wait_for(first, 5)
                assert answer.status_code == 200 and 'result' in answer.json()
            else:
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first
                await until(lambda: child.waiting == 0)
                child.free.set()
            await until(lambda: runtime.manager.reply_memory.held == 0)
            retried = await client.post('/mcp', headers=headers, json=call(103))
            assert retried.status_code == 200 and 'result' in retried.json()
            assert child.client_calls() == [101, 103]
        assert runtime.manager.reply_memory.held == 0


def gate(profile_id, shared):
    budget = request_budget.RequestBudget(request_budget.BudgetLimits(total=32 * 1024 * 1024,
                                                                     per_profile=16 * 1024 * 1024))
    quota = profiles.DEFAULT_PROFILE_QUOTA if profile_id == 'default' else profiles.EXTRA_PROFILE_QUOTA
    return profile_router.ProfileGate(profile_id, quota, budget, profile_router.Reports(), shared)


def scope():
    return {'type': 'http', 'method': 'POST', 'headers': [], 'path': '/mcp'}


async def receive():
    return {'type': 'http.request', 'body': b'', 'more_body': False}


async def test_slow_readers_hold_tickets_and_pending_bytes_then_release():
    shared = reply_memory.ReplyMemory()
    default = gate('default', shared)
    extra = gate('0123456789abcdef01234567', shared)
    release = asyncio.Event()
    started = asyncio.Event()
    seen = []

    async def app(request_scope, recv, send):
        answer = request_scope['state'][gateway.REPLY_RESERVE](
            {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call'})
        if answer is not None:
            await answer(request_scope, recv, send)
            return
        request_scope['state'][gateway.PENDING_CHARGE](1000)
        await send({'type': 'http.response.start', 'status': 200,
                    'headers': [(b'content-length', b'1000')]})
        await send({'type': 'http.response.body', 'body': b'x' * 1000})

    async def send(message):
        seen.append(message)
        if message['type'] == 'http.response.body' and message.get('body') == b'x' * 1000:
            started.set()
            await release.wait()

    tasks = [asyncio.create_task(default.serve(app, scope(), receive, send)) for _ in range(3)]
    tasks.append(asyncio.create_task(extra.serve(app, scope(), receive, send)))
    await asyncio.wait_for(started.wait(), 2)
    await asyncio.sleep(0)
    assert shared.held == 4 * reply_memory.TICKET_BYTES
    assert default.reply_bytes == 3000 and extra.reply_bytes == 1000
    # Nominal default slots remain 32; all 29 further offers are safely busy
    # while the first three default-profile replies hold their tickets.
    assert default.quota.forward_slots == 32 and extra.quota.forward_slots == 16
    async def offer_while_held():
        events = []

        async def capture(message):
            events.append(message)

        await default.serve(app, scope(), receive, capture)
        return events

    busy_offers = await asyncio.gather(*(offer_while_held() for _ in range(29)))
    for events in busy_offers:
        assert len(events) == 2
        start, body = events
        assert start['type'] == 'http.response.start' and start['status'] == 200
        headers = [(k.lower(), v) for k, v in start['headers']]
        assert (b'retry-after', b'5') in headers
        assert (b'cache-control', b'no-store') in headers
        assert body['type'] == 'http.response.body'
        refused = json.loads(body['body'])
        assert refused['id'] == 7 and refused['error']['code'] == -32003
    assert shared.held == 4 * reply_memory.TICKET_BYTES
    tasks[0].cancel()  # token-revocation / disconnected-client cancellation path
    with pytest.raises(asyncio.CancelledError):
        await tasks[0]
    assert shared.held == 3 * reply_memory.TICKET_BYTES
    assert default.reply_bytes == 2000
    release.set()
    await asyncio.gather(*tasks[1:])
    assert shared.held == 0 and shared.by_profile == {}
    assert default.reply_bytes == extra.reply_bytes == 0


async def test_extra_profile_cannot_take_anothers_reserved_ticket():
    shared = reply_memory.ReplyMemory()
    names = ['default'] * 3 + [f'{i:024x}' for i in range(5)]
    for name in names:
        assert shared.take(name)
    assert shared.held == reply_memory.TOTAL_BYTES
    assert not shared.take('default') and not shared.take(f'{9:024x}')
    for name in names:
        shared.give(name)
    assert shared.held == 0


async def test_ticket_caps_a_streamed_reply_and_releases_on_error():
    shared = reply_memory.ReplyMemory()
    shared.TICKET_BYTES = 1024  # scale the byte cap without allocating a 64 MiB test body
    owner = gate('default', shared)

    async def app(request_scope, recv, send):
        assert request_scope['state'][gateway.REPLY_RESERVE](None) is None  # GET's ticket
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'x' * 1025})

    sent = []
    async def send(message):
        sent.append(message)
    with pytest.raises(gateway.BadRequest):
        await owner.serve(app, {**scope(), 'method': 'GET'}, receive, send)
    assert shared.held == 0 and owner.reply_bytes == 0
    assert not any(item['type'] == 'http.response.body' for item in sent)


async def test_no_large_child_reply_route_can_bypass_the_pre_forward_ticket():
    request = {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}
    for method in ('tools/call', 'tools/list', 'resources/read', 'prompts/get'):
        assert gateway.reply_may_hold_large_child_output('POST', {**request, 'method': method})
    for method in ('initialize', 'ping'):
        assert not gateway.reply_may_hold_large_child_output('POST', {**request, 'method': method})
    assert gateway.reply_may_hold_large_child_output('GET', None)  # SSE
    assert not gateway.reply_may_hold_large_child_output('POST',
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    assert not gateway.reply_may_hold_large_child_output('DELETE', None)
    # The local /health route has neither an MCP body nor this forwarding path.


async def test_switched_on_odoo_sse_ping_is_bounded_and_sanitized(tmp_path):
    class PingChild(ProfileChild):
        ping_body = None
        ping_status = 200

        async def __call__(self, request):
            response = await super().__call__(request)  # bearer, session, and child request recording
            message = json.loads(request.content) if request.content else {}
            if message.get('method') == 'ping' and response.status_code == 200 and self.ping_body is not None:
                return httpx.Response(self.ping_status, headers={'content-type': 'text/event-stream'},
                                      content=self.ping_body)
            return response

    def event(value):
        return b'data: ' + json.dumps(value, separators=(',', ':')).encode() + b'\n\n'

    data = tmp_path / 'data'
    configure(data, 'odoo')
    children = Children()
    child = children.add(3000, PingChild('default', 'odoo', data))
    async with multi_profile_runtime('odoo', data, children=children) as runtime:
        assert runtime.manager.reply_memory is not None
        token = runtime.token('default')
        async with runtime.mcp() as client:
            headers = {**ACCEPT, 'Authorization': 'Bearer ' + token}
            opened = await client.post('/mcp', headers=headers, json=initialize_message())
            assert opened.status_code == 200
            headers['Mcp-Session-Id'] = opened.headers['mcp-session-id']
            ping = {'jsonrpc': '2.0', 'id': 7, 'method': 'ping'}

            # A child can send other events first; none of them or its own
            # top-level fields may reach this unticketed control reply.
            child.ping_body = (event({'jsonrpc': '2.0', 'method': 'notifications/progress',
                                      'params': {'progress': 'child-only'}})
                               + event({'jsonrpc': '2.0', 'id': 7, 'result': {'child-only': True}}))
            response = await client.post('/mcp', headers=headers, json=ping)
            assert response.status_code == 200 and response.headers['content-type'] == 'text/event-stream'
            assert response.content == event({'jsonrpc': '2.0', 'id': 7, 'result': {}})
            assert runtime.manager.reply_memory.held == 0

            child.ping_body = b'data: ' + b'x' * gateway.UNTICKETED_CONTROL_RESPONSE + b'\n\n'
            oversized = await client.post('/mcp', headers=headers, json=ping)
            assert oversized.status_code == 502 and b'x' * 100 not in oversized.content

            child.ping_body = event({'jsonrpc': '2.0', 'id': 8, 'result': {}})
            wrong_id = await client.post('/mcp', headers=headers, json=ping)
            assert wrong_id.status_code == 502

            child.ping_body = event({'jsonrpc': '2.0', 'id': 7,
                                     'error': {'code': -32000, 'message': token}})
            masked = await client.post('/mcp', headers=headers, json=ping)
            assert masked.status_code == 200 and token.encode() not in masked.content
            assert b'[REDACTED]' in masked.content

            # An SSE-framed child error on HTTP 500 must keep the existing
            # status mapping; a matching JSON-RPC ID cannot turn it into 200.
            child.ping_status = 500
            child.ping_body = event({'jsonrpc': '2.0', 'id': 7,
                                     'error': {'code': -32000, 'message': 'child-only-500'}})
            failed = await client.post('/mcp', headers=headers, json=ping)
            assert failed.status_code == 500
            assert failed.headers['content-type'] == 'application/json'
            assert failed.json() == {'jsonrpc': '2.0', 'id': 7,
                                     'error': {'code': -32000, 'message': 'Internal Server Error'}}
            assert b'child-only-500' not in failed.content
            child.ping_status = 200

            # A UTF-8 child error can expand when the gateway JSON-escapes it.
            # The unticketed bound applies to the serialized response too.
            child.ping_body = (b'data: ' + json.dumps({'jsonrpc': '2.0', 'id': 7,
                                'error': {'code': -32000, 'message': '中' * 11_000}},
                                ensure_ascii=False).encode() + b'\n\n')
            expanded = await client.post('/mcp', headers=headers, json=ping)
            assert expanded.status_code == 502

            before = len(child.requests)
            denied = await client.post('/mcp', headers={**headers, 'Authorization': 'Bearer wrong'}, json=ping)
            assert denied.status_code == 401 and len(child.requests) == before
            assert runtime.manager.reply_memory.held == 0
