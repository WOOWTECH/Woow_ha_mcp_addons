"""Global Odoo reply tickets across slow ASGI sends and cancellation."""

import asyncio
import json

import pytest

from mcp_admin_core import gateway, profile_router, profiles, reply_memory, request_budget

pytestmark = pytest.mark.asyncio


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
    # Nominal default slots remain 32; the memory gate refuses its fourth call.
    assert default.quota.forward_slots == 32 and extra.quota.forward_slots == 16
    await default.serve(app, scope(), receive, send)
    assert seen[-1]['type'] == 'http.response.body'
    refused = json.loads(seen[-1]['body'])
    assert refused['id'] == 7 and refused['error']['code'] == -32003
    assert any(item['type'] == 'http.response.start' and item['status'] == 200 and
               (b'retry-after', b'5') in [(k.lower(), v) for k, v in item['headers']]
               for item in seen)
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
