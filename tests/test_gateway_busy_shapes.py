"""HM-14: the busy answers of a switched-on profile's forwarding slots, against the PaaS table (multi-profile plan 12.3
HM-14, 5.2; contract 2.4, 4.2; FM-50, FM-51; PaaS docs/mcp-gateway-limits.md "超過上限時用戶端拿到什麼", 69ac425 and its
later fixes to cf3d0d5; its tests packages/mcp-admin-core/tests/test_gateway_queue.py and test_gateway_pool.py).

| Situation (switched on) | HTTP | Body |
|---|---|---|
| the lane's queue is full, the request has an id | 200, Retry-After 5 | -32003 under its id, the queue's text; at once |
| the lane's queue is full, no id (GET, DELETE, a notification) | 503, Retry-After 5 | -32003 id null |
| waited for a slot in vain, an id | 200, Retry-After 5 | -32003 under its id: MCP Python SDK 1.x ends the session on any other status |
| waited in vain, no id | 503, Retry-After 5 | -32003 id null |
| a GET past the profile's stream cap | 429, Retry-After 30 | -32003 id null (HM-08: tests/test_profile_quotas.py) |

Every text is fixed and names the lane's own number of slots (ordinary or reserved for notifications; PaaS review N8),
and each situation writes one WARNING per profile a minute (PaaS 82c6929: its full text is pinned). A busy answer ends
nothing but that request: the session goes on. HA waits 1 s (PaaS 10; plan 8.8 #15) and answers no legacy SSE (plan 8.8
#6). Switched off (the repository), every answer stays today's: 503 {"error":"request denied"} after 1 s, no queue cap,
no reserve (tests/test_profile_quotas.py pins its bytes; here, that nothing of HM-14 applies).
"""
import asyncio
import json

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import Children, multi_profile_runtime
from mcp_admin_core import gateway, profile_router, profiles
from switched_gateway import (B, INITIALIZED, PRODUCT, GatewayChild, bearer, call, quota, session_of, setup, until,
                              watch)
from test_single_profile_golden import answer, configure, initialize_message, settle

pytestmark = pytest.mark.usefixtures('log_scan')
ORDINARY, RESERVED = 'ordinary', 'reserved'  # gateway.ORDINARY_LANE, RESERVED_LANE


def busy(response, *, status, ident, text):
    assert response.status_code == status, (response.status_code, response.content[:200])
    assert response.headers['retry-after'] == '5' and response.headers['cache-control'] == 'no-store'
    assert response.headers['content-type'] == 'application/json'
    assert response.json() == {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32003, 'message': text}}


def runtime_with_child(tmp_path, monkeypatch, **changes):
    quota(monkeypatch, **changes)
    data = setup(tmp_path)
    children = Children()
    children.add(3000, GatewayChild('default', PRODUCT, data))
    child = children.add(18000, GatewayChild('p' + B[:4], PRODUCT, profiles.Layout(data).profile(B)))
    return data, children, child


async def test_a_busy_lane_answers_as_the_paas_table_and_the_session_goes_on(tmp_path, log_scan, monkeypatch):
    """B's 2 slots held (queue 1). A write waits 0.6 s and gets 200 + -32003 under its id; a DELETE and a GET 503, id
    null, both Retry-After 5. With one request queued, the next write and the next GET are refused at once with the
    queue's text. The child gets none of them. Once the slots come free, the same session answers (a busy answer ends
    no session: PaaS test_busy_answer_keeps_streamable_sessions_and_legacy_sse_status, its legacy SSE half aside)."""
    data, children, child = runtime_with_child(tmp_path, monkeypatch, forward_slots=2, queue=1,
                                               forward_wait_seconds=.6)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        wait_text, queue_text = profile_router.forward_text(2, .6), profile_router.queue_text(1, 2)
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            child.hold_calls = True
            held = [asyncio.create_task(client.post('/mcp', headers=headers, json=call(60 + n))) for n in range(2)]
            await until(lambda: child.waiting == 2)
            loop = asyncio.get_running_loop()
            started = loop.time()
            busy(await client.post('/mcp', headers=headers, json=call(7)), status=200, ident=7, text=wait_text)
            assert .55 <= loop.time() - started < 3
            busy(await client.delete('/mcp', headers=headers), status=503, ident=None, text=wait_text)
            busy(await client.get('/mcp', headers=headers), status=503, ident=None, text=wait_text)
            queued = asyncio.create_task(client.post('/mcp', headers=headers, json=call(8)))
            lanes = runtime.manager.get(B).runtime.mcp_app.state.lanes
            await until(lambda: lanes[ORDINARY].waiting == 1)
            started = loop.time()
            busy(await client.post('/mcp', headers=headers, json=call(9)), status=200, ident=9, text=queue_text)
            busy(await client.get('/mcp', headers=headers), status=503, ident=None, text=queue_text)
            assert loop.time() - started < .5, 'over the queue cap is refused at once (a wait is 0.6 s)'
            busy(await queued, status=200, ident=8, text=wait_text)
            assert child.client_calls() == [60, 61] or sorted(child.client_calls()) == [60, 61]
            child.free.set()
            assert all(response.status_code == 200 for response in await asyncio.gather(*held))
            child.hold_calls = False
            after = await client.post('/mcp', headers=headers, json=call(10))
            assert after.status_code == 200 and after.json()['result']['content'][0]['text'] == child.text
        assert sorted(child.client_calls()) == [10, 60, 61]


@pytest.mark.parametrize('lane', [ORDINARY, RESERVED])
async def test_busy_texts_and_warnings_name_the_limit_of_their_own_lane(log_scan, lane):
    """PaaS review N8 (its cases 21 and 22) and 82c6929 (the WARNING's full text): the wait and queue texts and the
    WARNING name the lane's own number of slots, here 9 ordinary and 3 reserved on purpose; the reserved lane's WARNING
    names no setting to change (there is none) but says the MCP server may be stuck."""
    quota_ = profiles.ProfileQuota(32, 64 * 1024 * 1024, 9, .05, 8, 2, 3, 32 * 1024 * 1024, 24)
    gate = profile_router.ProfileGate(B, quota_, profile_router.RefusalAllowance(), profile_router.Reports())
    waited = gate.slot_busy.answer(call(7), 'wait', lane)
    full = gate.slot_busy.answer(call(8), 'queue', lane)
    texts = [json.loads(response.body)['error']['message'] for response in (waited, full)]
    lines = [record.getMessage() for record in log_scan.records if record.name == 'mcp_admin_core.profile_router']
    if lane == RESERVED:
        assert texts[0] == profile_router.forward_text(3, .05, reserved=True)
        assert 'All 3 connections reserved for notifications of this MCP URL to its MCP server are in use' in texts[0]
        assert '保留給通知、送往 MCP 子程式的 3 條連線都在使用中' in texts[0] and '9' not in texts[0]
        assert texts[1] == profile_router.queue_text(2, 3, reserved=True)
        assert ('2 requests of this MCP URL are already waiting for one of its 3 connections reserved for '
                'notifications') in texts[1] and '9' not in texts[1]
        assert '已經有 2 個請求在排隊等 3 條保留給通知、送往 MCP 子程式的連線' in texts[1]
        assert lines == [
            f'MCP gateway [profile={B[:8]}]: all 3 forwarding slots reserved for notifications stayed in use for '
            '0.05 s; notifications were answered busy (-32003) and not sent (its MCP server may be stuck)',
            f'MCP gateway [profile={B[:8]}]: 2 requests were waiting for one of its 3 forwarding slots reserved for '
            'notifications, its limit; new ones were answered busy (-32003) without waiting']
    else:
        assert texts[0] == profile_router.forward_text(9, .05)
        assert 'All 9 connections of this MCP URL to its MCP server are in use' in texts[0]
        assert 'reserved' not in texts[0] and '保留' not in texts[0] and '3' not in texts[0].replace('0.05', '')
        assert texts[1] == profile_router.queue_text(2, 9)
        assert '2 requests of this MCP URL are already waiting for one of its 9 connections to its MCP server' in texts[1]
        assert '已經有 2 個請求在排隊等 9 條送往 MCP 子程式的連線' in texts[1] and '保留' not in texts[1]
        assert lines == [
            f'MCP gateway [profile={B[:8]}]: all 9 forwarding slots stayed in use for 0.05 s; requests were answered '
            'busy (-32003) and not sent',
            f'MCP gateway [profile={B[:8]}]: 2 requests were waiting for one of its 9 forwarding slots, its limit; new '
            'ones were answered busy (-32003) without waiting']
    for response, ident in ((waited, 7), (full, 8)):
        assert response.status_code == 200 and response.headers['retry-after'] == '5'
        assert json.loads(response.body)['id'] == ident
    note = gate.slot_busy.answer(None, 'wait', lane)  # a notification, a GET or a DELETE: no id
    assert note.status_code == 503 and json.loads(note.body)['id'] is None
    assert len([r for r in log_scan.records if r.name == 'mcp_admin_core.profile_router']) == 2  # one a minute


@pytest.mark.parametrize('queue', [1, 0])
async def test_an_initialize_waiting_for_a_slot_gets_the_normal_busy_answer(tmp_path, log_scan, monkeypatch, queue):
    """PaaS case 17: an initialize that finds B's slots busy waits like any request (queue 0: refused at once) and
    gets 200 + -32003 under its id + Retry-After 5 and B's WARNING, never a not-ready 503; the child gets no
    initialize. (HA answers an initialize itself only while no child runs, before any slot: plan 8.8 #68.)"""
    data, children, child = runtime_with_child(tmp_path, monkeypatch, forward_slots=1, queue=queue,
                                               forward_wait_seconds=.3)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            child.hold_calls = True
            held = asyncio.create_task(client.post('/mcp', headers=headers, json=call(50)))
            await until(lambda: child.waiting == 1)
            seen = len(child.seen)
            response = await client.post('/mcp', headers=bearer(token), json=initialize_message())
            text = profile_router.forward_text(1, .3) if queue else profile_router.queue_text(0, 1)
            busy(response, status=200, ident=1, text=text)
            assert 'mcp-session-id' not in response.headers
            assert child.seen[seen:] == [], 'no slot: the initialize is not sent'
            child.free.set()
            assert (await held).status_code == 200
        lines = [r.getMessage() for r in log_scan.records if r.name == 'mcp_admin_core.profile_router']
        assert len(lines) == 1 and 'profile=' + B[:8] in lines[0]


async def test_switched_off_nothing_of_the_lanes_applies(tmp_path, log_scan):
    """The repository (switched off): one set of 32 slots, no queue cap, no reserve, no disconnect watch. With the 32
    held, notifications/initialized waits for them like any request and gets today's 503 {"error":"request denied"}
    after the 1 s wait (byte for byte, as tests/test_profile_quotas.py pins it for a tools/call)."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    children = Children()
    child = children.add(3000, GatewayChild('default', PRODUCT, data))
    async with multi_profile_runtime(PRODUCT, data, switch=False, children=children) as runtime:
        await settle(runtime, 'configured')
        token = runtime.token('default')
        log_scan.watch(token)
        assert runtime.manager is None and runtime.mcp_app.state.lanes is None
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            child.hold_calls = True
            held = [asyncio.create_task(client.post('/mcp', headers=headers, json=call(n))) for n in range(32)]
            await until(lambda: child.waiting == 32)
            loop = asyncio.get_running_loop()
            started = loop.time()
            note = await client.post('/mcp', headers=headers, json=INITIALIZED)
            assert .9 <= loop.time() - started < 5
            assert answer(note) == (503, [('content-length', '26'), ('content-type', 'application/json')],
                                    b'{"error":"request denied"}')
            child.free.set()
            await asyncio.gather(*held)
