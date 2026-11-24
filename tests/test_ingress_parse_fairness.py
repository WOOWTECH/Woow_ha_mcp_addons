"""The object-heavy ingress parser must leave other profiles able to run."""
import asyncio
import json
import threading

import pytest
from starlette.requests import Request

from mcp_admin_core import gateway


def request_for(raw):
    async def receive():
        return {'type': 'http.request', 'body': raw, 'more_body': False}

    return Request({'type': 'http', 'method': 'POST', 'headers':
                    [(b'content-type', b'application/json'),
                     (b'content-length', str(len(raw)).encode())]}, receive)


async def test_slow_profile_parser_does_not_hold_another_profiles_loop(monkeypatch):
    heavy = b'{"id":1,"a":[]}'
    small = b'{"id":2}'
    entered, release = threading.Event(), threading.Event()
    original = gateway._parse_json_body

    def slow_parse(raw, guard, escaped_only=False):
        if raw == heavy:
            entered.set()
            assert release.wait(3)
        return original(raw, guard, escaped_only)

    monkeypatch.setattr(gateway, '_parse_json_body', slow_parse)
    a_slot, b_slot = asyncio.Semaphore(1), asyncio.Semaphore(1)
    a = asyncio.create_task(gateway.json_body(request_for(heavy), gateway.STRUCTURE_LIMITS, a_slot))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        # If the first parser executes on the loop, this timer cannot fire.
        b = await asyncio.wait_for(gateway.json_body(request_for(small), gateway.STRUCTURE_LIMITS, b_slot), 1)
        assert b == json.loads(small)
        assert not a.done()
    finally:
        release.set()
        assert await asyncio.wait_for(a, 2) == json.loads(heavy)


async def test_cancelled_parse_keeps_profile_slot_until_worker_exits(monkeypatch):
    raw = b'{"id":1}'
    entered, release = threading.Event(), threading.Event()
    calls = []
    original = gateway._parse_json_body

    def slow_parse(body, guard, escaped_only=False):
        calls.append(1)
        entered.set()
        assert release.wait(3)
        return original(body, guard, escaped_only)

    monkeypatch.setattr(gateway, '_parse_json_body', slow_parse)
    slot = asyncio.Semaphore(1)
    first = asyncio.create_task(gateway.json_body(request_for(raw), gateway.STRUCTURE_LIMITS, slot))
    assert await asyncio.to_thread(entered.wait, 2)
    first.cancel()
    second = asyncio.create_task(gateway.json_body(request_for(raw), gateway.STRUCTURE_LIMITS, slot))
    await asyncio.sleep(.05)
    assert calls == [1]  # cancelled work has not spawned another parser
    release.set()
    try:
        await first
    except asyncio.CancelledError:
        pass
    assert (await asyncio.wait_for(second, 2)) == json.loads(raw)
    assert calls == [1, 1]


@pytest.mark.parametrize('raw', [b'{"id":"\\ud800"}', b'{"id":1,"id":2}', b'{"id":NaN}'])
async def test_offloaded_parser_keeps_strict_json_rejections(raw):
    with pytest.raises(gateway.BadRequest) as error:
        await gateway.json_body(request_for(raw), gateway.STRUCTURE_LIMITS, asyncio.Semaphore(1))
    assert error.value.status == 400


async def test_offloaded_parser_accepts_valid_unicode_without_escape():
    raw = '{"id":"你好😀"}'.encode()
    assert await gateway.json_body(request_for(raw), gateway.STRUCTURE_LIMITS,
                                   asyncio.Semaphore(1)) == json.loads(raw)
