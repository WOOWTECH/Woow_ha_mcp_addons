"""0.5.1 (F1): a GET event stream holds no reply ticket and is bounded by its own bytes instead.

HM-19b (2026-11-23) found that every GET stream of a switched-on Odoo held one 64 MiB reply ticket for its whole life,
so an additional profile (one ticket) whose MCP SDK client opened its resident GET could not call a tool any more
(200 + -32003 "reply memory reservation is full"), and five SDK clients of the default profile (three tickets) left no
ticket for a tools/call. The ticket now bounds only a POST that may carry a large reply."""

import asyncio
import json

import pytest

from multi_profile_runtime import Children, multi_profile_runtime
from mcp_admin_core import gateway, profile_router, profiles, reply_memory, request_budget
from switched_gateway import B, PRODUCT, Exchange, GatewayChild, bearer, call, ping, setup, session_of, until, watch
from log_scan import log_scan  # noqa: F401 (fixture)

pytestmark = pytest.mark.asyncio

LIST = {'jsonrpc': '2.0', 'id': 31, 'method': 'tools/list'}
NOTIFICATION = b'{"jsonrpc":"2.0","method":"notifications/tools/list_changed"}'


def runtime_parts(tmp_path):
    data = setup(tmp_path)
    children = Children()
    children.add(3000, GatewayChild('default', PRODUCT, data))
    children.add(18000, GatewayChild('p' + B[:4], PRODUCT, profiles.Layout(data).profile(B)))
    return data, children


def open_streams(runtime, token, session, count):
    headers = [*bearer(token).items(), ('mcp-session-id', session)]
    return [Exchange(runtime.mcp_app, 'GET', '/mcp', headers).start() for _ in range(count)]


def answered(response):
    assert response.status_code == 200, response.text
    body = response.json()
    assert 'result' in body, body
    return body


@pytest.mark.usefixtures('log_scan')
async def test_an_extra_profiles_resident_get_leaves_its_own_and_other_sessions_calls_working(tmp_path, log_scan):
    """The HM-19b F1 shape: one resident GET of an additional profile, then tools/list and tools/call from the same
    session and from a second session of the same profile all succeed (the ticket was taken by the GET before)."""
    data, children = runtime_parts(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        async with runtime.mcp() as client:
            token = runtime.token(B)
            first = await session_of(client, token)
            second = await session_of(client, token)
            streams = open_streams(runtime, token, first, 1)
            await until(lambda: all(b': open' in stream.content for stream in streams))
            memory = runtime.manager.reply_memory
            assert memory.held == 0 and memory.by_profile == {}
            for session in (first, second):
                headers = {**bearer(token), 'Mcp-Session-Id': session}
                answered(await client.post('/mcp', headers=headers, json=LIST))
                for ident in (40, 41):
                    answered(await client.post('/mcp', headers=headers, json=call(ident)))
            assert memory.held == 0 and not any(stream.ended for stream in streams)
            children.by_port[18000].free.set()
            await asyncio.wait_for(asyncio.gather(*(stream.task for stream in streams)), 5)


@pytest.mark.usefixtures('log_scan')
async def test_five_get_streams_of_the_default_profile_leave_five_concurrent_calls_working(tmp_path, log_scan):
    data, children = runtime_parts(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        async with runtime.mcp() as client:
            token = runtime.token('default')
            sessions = [await session_of(client, token) for _ in range(5)]
            streams = [open_streams(runtime, token, session, 1)[0] for session in sessions]
            await until(lambda: all(b': open' in stream.content for stream in streams))
            assert runtime.manager.reply_memory.held == 0
            # 5 GETs held 5 tickets' worth of the default profile's 3 in 0.5.0: every call was busy. Now each succeeds,
            # one after the other, and the three tickets still let three overlapping calls through.
            for n, session in enumerate(sessions):
                answered(await client.post('/mcp', headers={**bearer(token), 'Mcp-Session-Id': session}, json=call(50 + n)))
            answers = await asyncio.gather(*(client.post('/mcp', headers={**bearer(token), 'Mcp-Session-Id': session},
                                                         json=call(60 + n)) for n, session in enumerate(sessions[:3])))
            for response in answers:
                answered(response)
            assert runtime.manager.reply_memory.held == 0
            children.by_port[3000].free.set()
            await asyncio.wait_for(asyncio.gather(*(stream.task for stream in streams)), 5)


@pytest.mark.usefixtures('log_scan')
async def test_tickets_still_limit_only_overlapping_large_reply_posts(tmp_path, log_scan):
    """An additional profile (one ticket): a second tools/call while the first holds the ticket is still 200 + -32003
    + Retry-After 5 (before it reaches the child), even with a GET stream open, which holds none."""
    data, children = runtime_parts(tmp_path)
    child = children.by_port[18000]
    child.hold_calls = True
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        async with runtime.mcp() as client:
            token = runtime.token(B)
            session = await session_of(client, token)
            headers = {**bearer(token), 'Mcp-Session-Id': session}
            streams = open_streams(runtime, token, session, 1)
            await until(lambda: all(b': open' in stream.content for stream in streams))
            first = asyncio.create_task(client.post('/mcp', headers=headers, json=call(61)))
            await until(lambda: child.waiting == 1)
            assert runtime.manager.reply_memory.held == reply_memory.TICKET_BYTES  # the POST's, not the stream's
            refused = await client.post('/mcp', headers=headers, json=call(62))
            assert refused.status_code == 200 and refused.headers['retry-after'] == '5'
            assert refused.json() == {'jsonrpc': '2.0', 'id': 62, 'error': {
                'code': -32003, 'message': profile_router.global_reply_text()}}
            assert child.client_calls() == [61]
            child.free.set()
            answered(await asyncio.wait_for(first, 5))
            await asyncio.wait_for(asyncio.gather(*(stream.task for stream in streams)), 5)
            assert runtime.manager.reply_memory.held == 0


@pytest.mark.usefixtures('log_scan')
@pytest.mark.parametrize('what', ['event', 'unread'])
async def test_a_get_stream_over_its_byte_bound_ends_cleanly(tmp_path, log_scan, monkeypatch, what):
    """A child event larger than STREAM_EVENT_BYTES, or relayed bytes the server has not taken beyond STREAM_BYTES,
    end that stream: its response is complete (a last empty body), nothing is raised to the server, the profile's
    stream count and tickets are back to zero, one WARNING without a token, and the other requests go on."""
    if what == 'event':
        monkeypatch.setattr(reply_memory, 'STREAM_EVENT_BYTES', 512)
        padding = b'data: {"jsonrpc":"2.0","method":"notifications/tools/list_changed","params":{"x":"' + b'a' * 1024 + b'"}}\n\n'
        events = (padding,)
    else:
        monkeypatch.setattr(reply_memory, 'STREAM_BYTES', 256)
        # each event is ~200 bytes: the one handed over and the one before it (not yet known taken) exceed 256
        events = (b': ' + b'k' * 150 + b'\ndata: ' + NOTIFICATION + b'\n\n',) * 4
    data, children = runtime_parts(tmp_path)
    children.by_port[18000].get_events = events
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        async with runtime.mcp() as client:
            token = runtime.token(B)
            session = await session_of(client, token)
            headers = {**bearer(token), 'Mcp-Session-Id': session}
            stream = open_streams(runtime, token, session, 1)[0]
            await asyncio.wait_for(stream.task, 5)  # returned normally: no exception reached the server
            assert stream.ended and stream.status == 200
            await until(lambda: runtime.gate(B).streams == 0 and runtime.gate(B).active == 0)
            assert runtime.manager.reply_memory.held == 0 and runtime.gate(B).reply_bytes == 0
            warnings = [r.getMessage() for r in log_scan.records
                        if r.name == 'mcp_admin_core.profile_router' and r.levelno >= 30 and 'event stream' in r.getMessage()]
            assert len(warnings) == 1 and 'reconnects' in warnings[0], warnings
            assert ('had not taken' in warnings[0]) == (what == 'unread'), warnings
            assert ('in a child event' in warnings[0]) == (what == 'event'), warnings
            answered(await client.post('/mcp', headers=headers, json=call(70)))


async def test_the_stream_bound_is_part_of_the_worst_case_memory_plan():
    """ODOO_STREAM_RESERVE_MIB covers every stream the profiles can have open (default 24 + 5 additional x 8 = 64),
    each at STREAM_BYTES, and the plan's two formulas both count it."""
    streams = profiles.DEFAULT_PROFILE_QUOTA.get_streams + profiles.EXTRA_PROFILE_LIMITS['odoo'] * profiles.EXTRA_PROFILE_QUOTA.get_streams
    assert streams == request_budget.ODOO_MAX_STREAMS == 64
    assert request_budget.ODOO_STREAM_RESERVE_MIB * 1024 * 1024 >= streams * reply_memory.STREAM_BYTES
    assert reply_memory.STREAM_BYTES == 16 * reply_memory.STREAM_EVENT_BYTES
    ticket_mib = reply_memory.TOTAL_BYTES // (1024 * 1024)
    assert ticket_mib == request_budget.ODOO_REPLY_RESERVE_MIB
    needed = request_budget.odoo_switched_memory_fits
    base = (request_budget.HOST_RESERVE_MIB + request_budget.GATEWAY_BASELINE_MIB + 6 * 100 + request_budget.SAFETY_MARGIN_MIB
            + ticket_mib + request_budget.ODOO_REPLY_WORK_MIB + request_budget.ODOO_ADMISSION_AMPLIFICATION * 16)
    assert not needed(base + request_budget.ODOO_STREAM_RESERVE_MIB - 1, 6, 'cgroup')
    assert needed(base + request_budget.ODOO_STREAM_RESERVE_MIB, 6, 'cgroup')


@pytest.mark.usefixtures('log_scan')
async def test_a_worst_case_event_stays_inside_the_stream_bound(tmp_path, log_scan):
    """Review MF-1: the biggest event a stream accepts (STREAM_EVENT_BYTES of emoji, which the gateway re-escapes
    about 3x) is not cut (the gateway relays the bare notification, its params are not forwarded) and the gateway's peak extra
    memory while it handles it stays inside STREAM_BYTES."""
    import tracemalloc
    emoji = '\U0001F600'
    head = b'data: {"jsonrpc":"2.0","method":"notifications/tools/list_changed","params":{"x":"'
    tail = b'"}}\n\n'
    text = emoji.encode() * ((reply_memory.STREAM_EVENT_BYTES - len(head) - len(tail)) // 4)
    event = head + text + tail
    assert reply_memory.STREAM_EVENT_BYTES - 8 <= len(event) <= reply_memory.STREAM_EVENT_BYTES
    data, children = runtime_parts(tmp_path)
    children.by_port[18000].get_events = (event,)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        async with runtime.mcp() as client:
            token = runtime.token(B)
            session = await session_of(client, token)
            tracemalloc.start()
            try:
                tracemalloc.reset_peak()
                before = tracemalloc.get_traced_memory()[0]
                stream = open_streams(runtime, token, session, 1)[0]
                await until(lambda: b'list_changed' in stream.content or stream.ended)
                peak = tracemalloc.get_traced_memory()[1] - before
            finally:
                tracemalloc.stop()
            assert not stream.ended, 'the largest allowed event must not end the stream'
            assert peak <= reply_memory.STREAM_BYTES, (peak, reply_memory.STREAM_BYTES)
            assert runtime.gate(B).streams == 1
            children.by_port[18000].free.set()
            await asyncio.wait_for(stream.task, 5)
            warnings = [r.getMessage() for r in log_scan.records if 'event stream' in r.getMessage()]
            assert warnings == [], warnings


@pytest.mark.usefixtures('log_scan')
async def test_a_stream_ended_over_its_bound_can_reconnect_and_its_counts_are_zero(tmp_path, log_scan, monkeypatch):
    """Review MF-3: after an over-limit end the same session opens a new GET (a client reconnect): it takes a stream
    slot and no ticket, the earlier stream's slot and bytes are back to zero, and a still-oversized event ends the new
    stream the same clean way without a reconnect storm (one WARNING a minute per profile and cause)."""
    monkeypatch.setattr(reply_memory, 'STREAM_EVENT_BYTES', 512)
    big = b'data: {"jsonrpc":"2.0","method":"notifications/tools/list_changed","params":{"x":"' + b'a' * 1024 + b'"}}\n\n'
    data, children = runtime_parts(tmp_path)
    children.by_port[18000].get_events = (big,)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        async with runtime.mcp() as client:
            token = runtime.token(B)
            session = await session_of(client, token)
            for _ in range(3):
                stream = open_streams(runtime, token, session, 1)[0]
                await asyncio.wait_for(stream.task, 5)
                assert stream.ended and stream.status == 200
                await until(lambda: runtime.gate(B).streams == 0 and runtime.gate(B).active == 0)
                assert runtime.manager.reply_memory.held == 0 and runtime.gate(B).reply_bytes == 0
            warnings = [r.getMessage() for r in log_scan.records
                        if r.name == 'mcp_admin_core.profile_router' and r.levelno >= 30 and 'event stream' in r.getMessage()]
            assert len(warnings) == 1, warnings  # throttled: three cuts, one line
            # and with the bound back to normal the same session streams and calls again
            monkeypatch.undo()
            children.by_port[18000].get_events = (b': ' + b'k' * 20 + b'\ndata: ' + NOTIFICATION + b'\n\n',)
            stream = open_streams(runtime, token, session, 1)[0]
            await until(lambda: b'list_changed' in stream.content)
            assert not stream.ended and runtime.gate(B).streams == 1
            answered(await client.post('/mcp', headers={**bearer(token), 'Mcp-Session-Id': session}, json=call(80)))
            children.by_port[18000].free.set()
            await asyncio.wait_for(stream.task, 5)
