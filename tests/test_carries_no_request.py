"""HM-14: which POST may use a switched-on profile's reserved slots (multi-profile plan 12.3 HM-14; contract 2.4, 5;
C3-SF-2; FM-51).

gateway.carries_no_request is the PaaS rule (woow-mcp-server 69ac425 proxy._carries_no_request, proxy.py:336; its tests
packages/mcp-admin-core/tests/test_proxy_carries_no_request.py, review N5): only a POST whose JSON value is an object or
a non-empty array of objects, none of them a request (a string method with an id other than null), each a notification
(a string method) or a response to the server (an id and a result or an error, no method), takes one of the 4 slots kept
for such POSTs; anything else, an unreadable body included, takes an ordinary slot. Classifying a request as a
notification would let it bypass the ordinary slots' limit and queue, so the rule is conservative.

The bodies are the PaaS cases, synthetic. HA reads a body with its own strict rules first (gateway.json_body:
config.strict_json refuses a duplicate key and NaN, a lone surrogate is refused; 400 before any slot), so here a body
is classified as the gateway would see it: parsed with those rules, None when they refuse it. HA's policy then lets only
single messages through (policy.authorize): a batch, a response to the server and a call without an id get 403 before
any slot, and every notification but notifications/initialized is answered 202 by the gateway itself, never forwarded.
The last tests show that end to end: the reserve carries notifications/initialized, and nothing else gets near it.
"""
import asyncio
import json

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import Children, multi_profile_runtime
from mcp_admin_core import gateway, profile_router, profiles
from mcp_admin_core.config import strict_json
from switched_gateway import (B, INITIALIZED, PRODUCT, GatewayChild, bearer, call, quota, session_of, setup, until,
                              watch)

pytestmark = pytest.mark.usefixtures('log_scan')


def _json(value) -> bytes:
    return json.dumps(value).encode()


_CALL = '"method":"tools/call","params":{"name":"x","arguments":{}}'
_NOTIFICATION = {"jsonrpc": "2.0", "method": "notifications/initialized"}
_REQUEST = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "x", "arguments": {}}}
_RESPONSE = {"jsonrpc": "2.0", "id": "server-req-1", "result": {"roots": []}}


def parsed(body: bytes):
    """The body as gateway.json_body reads it (strict JSON, no lone surrogate), or None where it is refused (400)."""
    try:
        value = strict_json(body)
        json.dumps(value, ensure_ascii=False).encode('utf-8')
        return value
    except (ValueError, RecursionError):
        return None


def classify(method: str, body: bytes) -> bool:
    """As the gateway does: only a POST's body is read (a GET or DELETE has none), then carries_no_request."""
    return gateway.carries_no_request(method, parsed(body) if method == 'POST' else None)


# The PaaS cases that must take an ordinary slot (False), each a body that could carry a request or cannot be read.
MUST_USE_THE_ORDINARY_LANE = {
    "request": _json(_REQUEST),
    "request id 0": f'{{"jsonrpc":"2.0","id":0,{_CALL}}}'.encode(),
    "request id empty string": f'{{"jsonrpc":"2.0","id":"",{_CALL}}}'.encode(),
    "request id false": f'{{"jsonrpc":"2.0","id":false,{_CALL}}}'.encode(),
    "request id float": f'{{"jsonrpc":"2.0","id":1.5,{_CALL}}}'.encode(),
    "request id NaN": f'{{"jsonrpc":"2.0","id":NaN,{_CALL}}}'.encode(),
    "request id object": f'{{"jsonrpc":"2.0","id":{{"a":1}},{_CALL}}}'.encode(),
    "request id list": f'{{"jsonrpc":"2.0","id":[1],{_CALL}}}'.encode(),
    "request that also carries a result": f'{{"jsonrpc":"2.0","id":1,"result":{{}},{_CALL}}}'.encode(),
    "batch of a notification and a request": _json([_NOTIFICATION, _REQUEST]),
    "batch of a response and a request": _json([_RESPONSE, {"jsonrpc": "2.0", "id": 2, "method": "ping"}]),
    "batch of a request only": _json([_REQUEST]),
    "duplicate id, the last one is a real id": f'{{"jsonrpc":"2.0","id":null,"id":8,{_CALL}}}'.encode(),
    "duplicate method, a request id with a notification method last":
        b'{"jsonrpc":"2.0","id":1,"method":"tools/call","method":"notifications/initialized"}',
    "duplicate method, a request id with a notification method first":
        b'{"jsonrpc":"2.0","id":1,"method":"notifications/initialized","method":"tools/call"}',
    "request with a UTF-8 BOM": b"\xef\xbb\xbf" + _json(_REQUEST),
    "request in UTF-16": _json(_REQUEST).decode().encode("utf-16"),
    "request in UTF-16 without a BOM": _json(_REQUEST).decode().encode("utf-16-le"),
    "request in UTF-32": _json(_REQUEST).decode().encode("utf-32"),
    "request with an escaped key name for id": b'{"jsonrpc":"2.0","\\u0069d":1,"method":"tools/call"}',
    "request with an escaped key name for method": b'{"jsonrpc":"2.0","id":1,"\\u006dethod":"tools/call"}',
    "method is a number": b'{"jsonrpc":"2.0","method":5}',
    "method is null": b'{"jsonrpc":"2.0","method":null}',
    "method is a list": b'{"jsonrpc":"2.0","method":["notifications/initialized"]}',
    "method is a number with an id": b'{"jsonrpc":"2.0","id":1,"method":5}',
    "no method, no id, no result": b'{"jsonrpc":"2.0"}',
    "an id alone": b'{"jsonrpc":"2.0","id":1}',
    "empty object": b"{}",
    "response without an id": b'{"jsonrpc":"2.0","result":{}}',
    "empty batch": b"[]",
    "batch of numbers": b"[1,2]",
    "batch with a notification and a number": _json([_NOTIFICATION, 5]),
    "nested batch": _json([[_REQUEST]]),
    "batch with an unreadable member": _json([_NOTIFICATION, {}]),
    "empty body": b"",
    "not json": b"hello",
    "truncated json": b'{"jsonrpc":"2.0","method":"notifications/init',
    "trailing garbage": _json(_NOTIFICATION) + b" garbage",
    "json string": b'"notifications/initialized"',
    "json number": b"1",
    "json null": b"null",
    "json true": b"true",
}

# The PaaS cases that take the reserved slots (True): the boundary's decisions.
USES_THE_RESERVED_LANE = {
    "notification": _json(_NOTIFICATION),
    "notification with params": b'{"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":1000}}',
    "batch of notifications": _json([_NOTIFICATION, {"jsonrpc": "2.0", "method": "notifications/cancelled"}]),
    "response with a result": _json(_RESPONSE),
    "response with an error": b'{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"x"}}',
    "batch of a notification and a response": _json([_NOTIFICATION, _RESPONSE]),
    # A JSON-RPC notification has no id: an id null (or none) tools/call is no request (PaaS review N5).
    "tools/call with id null": f'{{"jsonrpc":"2.0","id":null,{_CALL}}}'.encode(),
    "tools/call without an id": f'{{"jsonrpc":"2.0",{_CALL}}}'.encode(),
}
# PaaS: True (its parser keeps the last of duplicate keys). HA's strict JSON refuses a duplicate key (400 before any
# slot), so it takes no slot at all: stricter, never a reserved one.
REFUSED_BEFORE_ANY_SLOT = {
    "duplicate id, the last one is null": f'{{"jsonrpc":"2.0","id":7,"id":null,{_CALL}}}'.encode(),
}


@pytest.mark.parametrize("body", MUST_USE_THE_ORDINARY_LANE.values(), ids=MUST_USE_THE_ORDINARY_LANE.keys())
def test_anything_that_could_be_a_request_or_cannot_be_read_uses_the_ordinary_lane(body):
    assert classify("POST", body) is False


@pytest.mark.parametrize("body", USES_THE_RESERVED_LANE.values(), ids=USES_THE_RESERVED_LANE.keys())
def test_only_notifications_and_responses_use_the_reserved_lane(body):
    assert classify("POST", body) is True


@pytest.mark.parametrize("body", REFUSED_BEFORE_ANY_SLOT.values(), ids=REFUSED_BEFORE_ANY_SLOT.keys())
def test_a_duplicate_key_is_refused_before_any_slot(body):
    """The PaaS reserve takes it; HA's strict JSON refuses it (gateway.json_body answers 400), so it never gets a
    slot of either lane."""
    assert parsed(body) is None and classify("POST", body) is False


@pytest.mark.parametrize("method", ["GET", "DELETE", "PUT", "OPTIONS", "get"])
def test_only_post_can_use_the_reserved_lane(method):
    """A GET is a stream (it holds its slot for hours), a DELETE ends a session: neither is a notification, whatever
    its content looks like."""
    assert gateway.carries_no_request("POST", _NOTIFICATION) is True  # the same content as a POST: reserved
    assert gateway.carries_no_request(method, _NOTIFICATION) is False
    assert gateway.carries_no_request(method, [_NOTIFICATION]) is False
    assert gateway.carries_no_request(method, None) is False
    assert classify(method, _json(_NOTIFICATION)) is False


def test_nothing_parsed_means_the_ordinary_lane():
    assert gateway.carries_no_request("POST", None) is False
    assert gateway.carries_no_request("POST", []) is False
    assert gateway.carries_no_request("POST", {}) is False


# ---- end to end: what reaches the reserve (PaaS test_gateway_queue.py cases 6, 7 and 14) ----

async def test_the_reserve_carries_notifications_initialized_while_every_ordinary_slot_is_busy(
        tmp_path, log_scan, monkeypatch):
    """B's 2 ordinary slots held by tools/calls its child has not answered. A request waits its 0.6 s and gets 200 +
    -32003 under its id; notifications/initialized takes one of the reserved slots and reaches the child at once (202;
    MCP Python SDK 1.x ends the session on a 5xx to a notification, the TS SDK's connect fails, SDK 2.x drops it); other
    notifications are answered 202 by the gateway itself and never forwarded (HA forwards none of them: plan 8.8 #6's
    note); a response to the server, a batch, an empty object and an id-less call are refused 403 before any slot (HA
    never relays a server-to-client request, policy.authorize). A GET stream is no notification: it waits for an
    ordinary slot and gets 503 + -32003 id null (PaaS case 7). The reserve is a lane of its own: notifications/initialized
    held by the child fill its 4 slots, the next one waits and gets 503 + -32003 id null with the reserve's own text,
    while ordinary requests still get their own answers (PaaS case 14)."""
    quota(monkeypatch, forward_slots=2, forward_wait_seconds=.6)
    data = setup(tmp_path)
    children = Children()
    children.add(3000, GatewayChild('default', PRODUCT, data))
    child = children.add(18000, GatewayChild('p' + B[:4], PRODUCT, profiles.Layout(data).profile(B)))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            session = await session_of(client, token)
            headers = {**bearer(token), 'Mcp-Session-Id': session}
            child.hold_calls = True
            held = [asyncio.create_task(client.post('/mcp', headers=headers, json=call(60 + n))) for n in range(2)]
            await until(lambda: child.waiting == 2)
            ordinary = await client.post('/mcp', headers=headers, json=call(9))
            assert ordinary.status_code == 200 and ordinary.json()['error']['code'] == -32003
            assert ordinary.json()['error']['message'] == profile_router.forward_text(2, .6)
            before = len(child.seen)
            loop = asyncio.get_running_loop()
            started = loop.time()
            initialized = await client.post('/mcp', headers=headers, json=INITIALIZED)
            assert loop.time() - started < .5, 'a notification never waits for an ordinary slot (a wait is 0.6 s)'
            assert initialized.status_code == 202 and initialized.content == b''
            assert child.seen[before:] == [('POST', 'notifications/initialized', None)]
            assert child.waiting == 2  # the ordinary slots were still held: it went through the reserve
            for message in ({'jsonrpc': '2.0', 'method': 'notifications/cancelled', 'params': {'requestId': 60}},
                            {'jsonrpc': '2.0', 'method': 'notifications/progress', 'params': {'progressToken': 't'}},
                            {'jsonrpc': '2.0', 'method': 'notifications/roots/list_changed'}):
                answer = await client.post('/mcp', headers=headers, json=message)
                assert answer.status_code == 202 and answer.content == b''
            for message in ({'jsonrpc': '2.0', 'id': 'server-req-1', 'result': {'roots': []}},
                            [INITIALIZED, {'jsonrpc': '2.0', 'method': 'notifications/cancelled'}], {},
                            {'jsonrpc': '2.0', 'id': None, 'method': 'tools/call', 'params': {'name': 'x'}},
                            {'jsonrpc': '2.0', 'method': 'tools/call', 'params': {'name': 'x'}}):
                answer = await client.post('/mcp', headers=headers, json=message)
                assert answer.status_code == 403 and answer.json() == {'error': 'request denied'}
            assert child.seen[before + 1:] == [], 'nothing but notifications/initialized reached the child'
            stream = await client.get('/mcp', headers=headers)
            assert stream.status_code == 503 and stream.headers['retry-after'] == '5'
            assert stream.json()['id'] is None and stream.json()['error']['code'] == -32003
            # the reserve's own lane: 4 held notifications fill it, the 5th waits and is refused with its own text
            child.hold_initialized = True
            notes = [asyncio.create_task(client.post('/mcp', headers=headers, json=INITIALIZED)) for _ in range(4)]
            await until(lambda: child.waiting == 6)
            fifth = await client.post('/mcp', headers=headers, json=INITIALIZED)
            assert fifth.status_code == 503 and fifth.headers['retry-after'] == '5'
            assert fifth.json() == {'jsonrpc': '2.0', 'id': None, 'error': {
                'code': -32003, 'message': profile_router.forward_text(4, .6, reserved=True)}}
            assert (await client.post('/mcp', headers=headers, json=call(10))).json()['error']['code'] == -32003
            child.free.set()
            assert [n.status_code for n in await asyncio.gather(*notes)] == [202] * 4
            assert [h.status_code for h in await asyncio.gather(*held)] == [200, 200]
        lines = [r.getMessage() for r in log_scan.records if r.name == 'mcp_admin_core.profile_router']
        assert any('profile=' + B[:8] in line and '4 forwarding slots reserved for notifications' in line
                   for line in lines), lines


@pytest.mark.parametrize('queued', [15, 16], ids=['queue 15 of 16', 'queue full'])
async def test_the_reserve_is_reached_only_while_the_profiles_admission_has_room(tmp_path, log_scan, monkeypatch,
                                                                                queued):
    """Contract 2.4, plan 8.8 #95 (HM-14 review MF-2; a known limitation, pinned as it is until HM-31 changes it).
    An additional profile's real numbers (admission 32 = its 16 ordinary slots + their queue of 16; reserve 4; only the
    wait made 30 s so that the queued requests stay queued). Its 16 slots held and 15 requests queued, the admission
    has room (31 of 32): notifications/initialized is read and reaches the child through the reserve (202). With 16
    queued the admission is full first: the notification is refused before its body is read (503, -32003 id null, the
    admission's text) and never gets near the reserve (PaaS reads the body first and has no admission: its reserve
    still carries it). Settled on 2026-11-16 (MF-2 (b), the main conversation): DQ-07's numbers stay, and HM-31
    (aligned with PaaS #155) makes the dispatcher read a small request (64 KiB at most) when the admission is full and
    let a notification or a response through to the reserve, as PaaS does; HM-31 changes this test then."""
    quota(monkeypatch, 'extra', forward_wait_seconds=30)
    data = setup(tmp_path)
    children = Children()
    children.add(3000, GatewayChild('default', PRODUCT, data))
    child = children.add(18000, GatewayChild('p' + B[:4], PRODUCT, profiles.Layout(data).profile(B)))
    numbers = profiles.EXTRA_PROFILE_QUOTA
    assert (numbers.admission, numbers.forward_slots, numbers.queue, numbers.reserved_notifications) == (32, 16, 16, 4)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp(timeout=60) as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            child.hold_calls = True
            held = [asyncio.create_task(client.post('/mcp', headers=headers, json=call(100 + n)))
                    for n in range(numbers.forward_slots)]
            await until(lambda: child.waiting == numbers.forward_slots)
            ordinary = runtime.manager.get(B).runtime.mcp_app.state.lanes['ordinary']
            waiting = [asyncio.create_task(client.post('/mcp', headers=headers, json=call(200 + n)))
                       for n in range(queued)]
            await until(lambda: ordinary.waiting == queued)
            assert runtime.gate(B).active == numbers.forward_slots + queued
            before = len(child.seen)
            note = await client.post('/mcp', headers=headers, json=INITIALIZED)
            if queued < numbers.queue:
                assert note.status_code == 202 and note.content == b''
                assert child.seen[before:] == [('POST', 'notifications/initialized', None)]
                assert child.waiting == numbers.forward_slots  # the ordinary slots stayed held: it took the reserve
            else:
                assert note.status_code == 503 and note.headers['retry-after'] == '5'
                assert note.json() == {'jsonrpc': '2.0', 'id': None, 'error': {
                    'code': -32003, 'message': profile_router.admission_text(numbers.admission)}}
                assert child.seen[before:] == [], 'refused before its body was read: the child never got it'
            child.free.set()
            assert [response.status_code for response in await asyncio.gather(*held, *waiting)] == \
                [200] * (numbers.forward_slots + queued)


async def test_without_a_reserve_a_notification_takes_an_ordinary_slot(tmp_path, log_scan, monkeypatch):
    """reserved_notifications 0 (the mechanism; HA's quota is 4): notifications/initialized then waits for an ordinary
    slot like any request and, none coming free, gets 503 + -32003 id null (PaaS: notification_reserve 0 is the
    ordinary lane)."""
    quota(monkeypatch, forward_slots=1, forward_wait_seconds=.2, reserved_notifications=0)
    data = setup(tmp_path)
    children = Children()
    children.add(3000, GatewayChild('default', PRODUCT, data))
    child = children.add(18000, GatewayChild('p' + B[:4], PRODUCT, profiles.Layout(data).profile(B)))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            child.hold_calls = True
            held = asyncio.create_task(client.post('/mcp', headers=headers, json=call(1)))
            await until(lambda: child.waiting == 1)
            note = await client.post('/mcp', headers=headers, json=INITIALIZED)
            assert note.status_code == 503 and note.json()['id'] is None and note.json()['error']['code'] == -32003
            child.free.set()
            assert (await held).status_code == 200
