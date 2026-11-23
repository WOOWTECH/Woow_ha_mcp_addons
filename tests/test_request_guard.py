"""HM-19c request guard (request_guard.py; contract 2.4, 5, 6): what a large request may cost before it is parsed.

Unit (the scan equals the structure guard's, the model bounds what json.loads builds), adversarial (just under and over
the threshold, every shape, CJK and emoji), the gateway (busy shape, refusal shape, one place, switched off unchanged),
CPU-time assertions (never wall time: the runner's load decides it).
"""
import asyncio
import gc
import json
import random
import threading
import time
import tracemalloc

import pytest
from starlette.requests import Request

from mcp_admin_core import gateway, request_guard as guard, request_limits
from mcp_admin_core.config import strict_json

KIB = 1024
MAX_DEPTH, MAX_ELEMENTS = request_limits.DEFAULT_MAX_DEPTH, request_limits.DEFAULT_MAX_TOTAL_ELEMENTS


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def call(arguments, ident=100):
    return dump({'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
                 'params': {'name': 'search_records', 'arguments': arguments}})


def request_for(raw):
    async def receive():
        return {'type': 'http.request', 'body': raw, 'more_body': False}

    return Request({'type': 'http', 'method': 'POST', 'headers': [(b'content-type', b'application/json'),
                                                                  (b'content-length', str(len(raw)).encode())]}, receive)


def padded_objects(count, pad=0):
    """count {"a":1} objects plus an ASCII pad string: the kit's objects shape (kit-next guard_shapes.objects_body)."""
    return call({'limit': 1, 'pad': 'a' * pad, 'padding': [{'a': 1}] * count})


def density_floor_pad(count):
    """The smallest pad (bytes) at which count {"a":1} objects are accepted by the estimate."""
    low, high = 0, 8 * 1024 * 1024
    while low < high:
        middle = (low + high) // 2
        if guard.too_costly(guard.scan(padded_objects(count, middle))) is None:
            high = middle
        else:
            low = middle + 1
    return low


# ---------------------------------------------------------------- the scan equals the structure guard's ----------

def random_body(rng, size):
    alphabet = [b'{', b'}', b'[', b']', b',', b':', b'"', b'\\', b'a', b'1', b' ', b'\\"', b'\\\\', b'"a"', b'{"a":1}',
                '中'.encode(), '😀'.encode(), b'true', b'null', b'-5', b'1.5']
    return b''.join(rng.choice(alphabet) for _ in range(size))


@pytest.mark.parametrize('chunk', [1, 2, 3, 7, 64, 4096])
def test_scan_structure_equals_the_one_call_scan_on_random_bodies(monkeypatch, chunk):
    monkeypatch.setattr(guard, 'SCAN_CHUNK', chunk)
    rng = random.Random(chunk)
    for _ in range(300):
        raw = random_body(rng, rng.randint(0, 120))
        outside = request_limits._COMPLETE_STRING.sub(b'', raw).split(b'"', 1)[0]
        expected = outside.translate(request_limits._STRUCTURE_BYTES).replace(b'\x00', b'')
        assert guard.scan(raw).structural == expected, raw


@pytest.mark.parametrize('depth,elements', [(3, 10), (4, 40), (64, 200000)])
def test_structure_reason_equals_structure_violation(monkeypatch, depth, elements):
    monkeypatch.setattr(guard, 'SCAN_CHUNK', 5)
    rng = random.Random(depth)
    for _ in range(400):
        raw = random_body(rng, rng.randint(0, 150))
        if request_limits.not_utf8(raw):
            continue
        assert guard.structure_reason(guard.scan(raw), max_depth=depth, max_elements=elements) == \
            request_limits.structure_violation(raw, max_depth=depth, max_elements=elements), raw


def test_a_string_and_an_escape_cut_by_a_piece_boundary(monkeypatch):
    # a quote escaped by the backslash at the end of a piece, an escaped backslash before the quote, a string that ends
    # exactly at a boundary: counts stay exact whatever the piece size
    raw = b'{"k":"a\\"b\\\\","m":["x\\\\\\"y",{"q":1}],"z":"{[,"}'
    expected = guard.scan(raw)
    for size in range(1, len(raw) + 2):
        guard.SCAN_CHUNK = size
        try:
            got = guard.scan(raw)
        finally:
            guard.SCAN_CHUNK = 32 * KIB
        assert (got.objects, got.arrays, got.commas, got.members, got.strings, got.structural) == \
            (expected.objects, expected.arrays, expected.commas, expected.members, expected.strings, expected.structural)
    assert (expected.objects, expected.arrays, expected.members, expected.strings) == (2, 1, 4, 7)


def test_counts_of_a_known_body():
    found = guard.scan(call({'a': [1, 2, 'xy', True, None, {'b': 2.5}], 'c': {}}))
    assert (found.objects, found.arrays, found.members) == (5, 1, 9)
    assert found.literals == 2 and found.uncached_numbers == 2  # 2.5 and the id 100 (a bound: 100 is a cached int)


# ---------------------------------------------------------------- the model bounds what is built ------------------

def graph_bytes(raw):
    gc.collect()
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    value = strict_json(raw)
    after = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    del value
    return after - before


def shapes():
    rng = random.Random(3)
    records = [{('field_%d' % k): ('v%d' % (i * k)) if k % 3 else i * k for k in range(30)} for i in range(400)]
    yield 'odoo_batch', call({'model': 'res.partner', 'method': 'create', 'args': [records]})
    yield 'objects', padded_objects(10000)
    yield 'empty_objects', call({'p': [{}] * 8000})
    yield 'empty_arrays', call({'p': [[]] * 8000})
    yield 'small_ints', call({'p': [1] * 20000})
    yield 'big_ints', call({'p': list(range(10000, 20000))})
    yield 'floats', call({'p': [1.5 + i for i in range(10000)]})
    yield 'short_strings', call({'p': ['ab'] * 10000})
    yield 'literals', call({'p': [True, False, None] * 8000})
    yield 'wide_dict', call({'p': {'k%d' % i: 'v%d' % i for i in range(8000)}})
    yield 'nested', call({'p': [{'a': {'b': {'c': [1, 2, {'d': 'xx'}]}}}] * 1500})
    for name, unit in (('ascii', 'a'), ('cjk', '中'), ('emoji', '😀'), ('mixed', 'a中😀')):
        yield name + '_string', call({'p': unit * 40000})
    for number in range(12):
        def value(depth):
            kind = rng.random()
            if depth <= 0 or kind < .4:
                return rng.choice([rng.randint(0, 5), rng.randint(257, 10 ** 9), rng.random() * 9, True, None,
                                   ''.join(rng.choice('ab中😀') for _ in range(rng.choice([0, 1, 5, 40])))])
            if kind < .7:
                return [value(depth - 1) for _ in range(rng.randint(0, 5))]
            return {rng.choice(['a', 'b', 'k%d' % rng.randint(0, 999)]): value(depth - 1) for _ in range(rng.randint(0, 5))}
        yield 'random%d' % number, call({'p': [value(3) for _ in range(400)]})


@pytest.mark.parametrize('name,raw', list(shapes()), ids=lambda value: value if isinstance(value, str) else '')
def test_model_bounds_the_measured_shapes(name, raw):
    """The graph the model says is never below what strict_json builds (tracemalloc), and the whole parse is never more
    than 3 times the model (a model that is far above would refuse good traffic)."""
    found = guard.scan(raw)
    built = graph_bytes(raw)
    assert guard.graph_bytes(found) >= built * 0.97, name  # 3%: strings only are exact to the byte
    if built > 4 * len(raw):
        assert guard.graph_bytes(found) <= 4.5 * built, name


def test_light_bodies_cannot_exceed_the_gate_whatever_they_hold():
    # the worst body that is 'light' (few container openers and commas over its raw bytes): empty objects at the light
    # limit, padded to the smallest large size; its estimated amplification stays under the gate
    for unit in (b'{}', b'[]', b'{"a":""}', b'[1]'):
        count = guard.LIGHT_ELEMENTS // 2 - 5
        pad = 'a' * (guard.LARGE_REQUEST_BYTES + 1 - len(call({'p': []})) - len(unit) * count)
        raw = call({'pad': pad, 'p': 0}).replace(b'"p":0', b'"p":[' + b','.join([unit] * count) + b']')
        assert len(raw) > guard.LARGE_REQUEST_BYTES and guard.light(raw)
        assert guard.amplification(guard.scan(raw)) <= guard.MAX_AMPLIFICATION, unit


# ---------------------------------------------------------------- adversarial: thresholds and shapes ---------------

def test_the_kit_objects_shape_is_refused_by_memory():
    raw = padded_objects(99990)  # 800 KB: 99,990 {"a":1}: the HM-19c failing request
    assert len(raw) > 700 * KIB
    assert guard.too_costly(guard.scan(raw)) == guard.TOO_MUCH_MEMORY
    assert guard.amplification(guard.scan(raw)) > 2 * guard.MAX_AMPLIFICATION


def test_just_under_and_just_over_the_density_floor():
    count = 99990
    pad = density_floor_pad(count)
    assert pad > 0
    under, over = padded_objects(count, pad), padded_objects(count, pad - 1)
    assert guard.too_costly(guard.scan(under)) is None
    assert guard.amplification(guard.scan(under)) <= guard.MAX_AMPLIFICATION
    assert guard.too_costly(guard.scan(over)) == guard.TOO_MUCH_MEMORY
    assert len(under) == len(over) + 1
    # and what the model lets in really is under the gate: gateway graph x (1 + child) + the copies of the body
    real = graph_bytes(under) * (1 + guard.CHILD_GRAPH_FACTOR) / len(under) + guard.BODY_COPIES
    assert real < guard.MAX_AMPLIFICATION


@pytest.mark.parametrize('unit', ['a', '中', '😀', 'a中😀'])
def test_long_strings_of_every_alphabet_are_not_heavy_and_are_accepted_at_the_byte_cap(unit):
    raw = call({'padding': (unit * (16 * 1024 * 1024))[:3_000_000]})
    assert not guard.classify(raw)
    assert guard.amplification(guard.scan(raw)) < 11  # at most 4 bytes a character in memory, the child's, the copies
    assert guard.too_costly(guard.scan(raw)) is None


def test_a_long_string_full_of_structure_characters_is_heavy_to_count_but_cheap_to_parse():
    raw = call({'padding': '{a,b},[c] ' * 90000})  # 900 KB of text: tens of thousands of commas and braces in a string
    assert guard.classify(raw)
    found = guard.scan(raw)
    assert (found.objects, found.arrays, found.commas, found.members) == (3, 0, 4, 7)  # the envelope only
    assert guard.too_costly(found) is None


def test_an_odoo_batch_of_thousands_of_records_is_accepted():
    records = [{('field_%d' % k): ('v%d' % (i * k)) if k % 3 else i * k for k in range(30)} for i in range(3000)]
    raw = call({'model': 'res.partner', 'method': 'create', 'args': [records]})
    found = guard.scan(raw)
    assert found.elements > 90000 and guard.too_costly(found) is None
    assert guard.amplification(found) < 18


@pytest.mark.parametrize('name,body', [
    ('empty_objects', call({'p': [{}] * 30000})),
    ('empty_arrays', call({'p': [[]] * 30000})),
    ('nested_objects', call({'p': [{'a': {'b': {'c': [1, 2, {'d': 'xx'}]}}}] * 5000})),
    ('short_strings', call({'p': ['ab'] * 40000})),
    ('tiny_records', call({'p': [{'id': 1, 'n': 'a'}] * 8000})),
])
def test_dense_shapes_are_refused_by_memory(name, body):
    assert len(body) > guard.LARGE_REQUEST_BYTES
    assert guard.too_costly(guard.scan(body)) == guard.TOO_MUCH_MEMORY, name


def test_one_huge_object_is_refused_for_the_stretch_nothing_can_cut():
    # one object of 12,000 members: the parser calls back only when the object is complete, one C call for all of it
    raw = call({'p': {'k%d' % i: 'v' for i in range(20000)}})
    found = guard.scan(raw)
    assert found.stall > guard.MAX_STALL_REFERENCE_SECONDS or guard.amplification(found) > guard.MAX_AMPLIFICATION
    assert guard.too_costly(found) is not None


def test_a_flat_array_of_short_strings_just_under_the_stall_limit():
    per = guard.SECONDS_PER_STRING
    under = int(guard.MAX_STALL_REFERENCE_SECONDS / per) - 2000  # strings in one array, no object between them
    raw = call({'p': ['abcdefghijklmnopqrstuvwxyz0123456789' * 3] * under})
    found = guard.scan(raw)
    assert found.stall <= guard.MAX_STALL_REFERENCE_SECONDS
    over = call({'p': ['abcdefghijklmnopqrstuvwxyz0123456789' * 3] * (under + 6000)})
    assert guard.scan(over).stall > guard.MAX_STALL_REFERENCE_SECONDS
    assert guard.too_costly(guard.scan(over)) is not None


# ---------------------------------------------------------------- the gateway ------------------------------------------

async def parse(raw, **options):
    return await gateway.json_body(request_for(raw), gateway.STRUCTURE_LIMITS, asyncio.Semaphore(1), **options)


async def test_a_heavy_body_is_refused_before_it_is_parsed(monkeypatch):
    called = []
    monkeypatch.setattr(guard, 'strict_json', lambda *a, **k: called.append(1))
    with pytest.raises(request_limits.RequestLimitError) as refused:
        await parse(padded_objects(99990))
    error = refused.value
    assert called == [] and error.status == 200 and error.payload['id'] == 100 and error.payload['error']['code'] == -32602
    assert error.kind == 'cost'
    text = error.payload['error']['message']
    assert 'too much' in text and '{"a"' not in text and 'padding' not in text  # the reason, never the content


async def test_a_refused_body_without_a_recognized_id_is_413():
    raw = padded_objects(99990).replace(b'"id":100', b'"id":true')
    with pytest.raises(request_limits.RequestLimitError) as refused:
        await parse(raw)
    assert refused.value.status == 413 and refused.value.payload['id'] is None


async def test_a_second_heavy_body_is_busy_not_queued():
    place = guard.ParsePlace(1)
    raw = padded_objects(5000, 200_000)  # heavy (many elements) and accepted
    assert guard.classify(raw) and guard.too_costly(guard.scan(raw)) is None
    entered, release = threading.Event(), threading.Event()
    original = guard.parse_large

    def slow(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    guard_parse = guard.parse_large
    guard.parse_large = slow
    try:
        first = asyncio.create_task(parse(raw, place=place))
        assert await asyncio.to_thread(entered.wait, 3)
        started = time.monotonic()
        with pytest.raises(guard.ParseBusy) as busy:
            await parse(raw, place=place)  # another profile's slot, the same add-on: answered at once
        assert time.monotonic() - started < 0.5 and busy.value.ident == 100
        assert place.free == 0
    finally:
        release.set()
        guard.parse_large = guard_parse
    assert (await asyncio.wait_for(first, 5))['id'] == 100
    assert place.free == 1  # given back when the parse ended
    assert (await parse(raw, place=place))['id'] == 100


async def test_the_place_is_given_back_however_the_request_ends():
    place = guard.ParsePlace(1)
    for raw in (padded_objects(99990), padded_objects(3000, 120000).replace(b'"id":100', b'"id":100,"id":1'),
                padded_objects(3000, 120000)[:-3]):
        with pytest.raises((request_limits.RequestLimitError, gateway.BadRequest)):
            await parse(raw, place=place)
        assert place.free == 1


async def test_a_cancelled_heavy_parse_gives_the_place_back_after_the_thread_ends():
    place = guard.ParsePlace(1)
    raw = padded_objects(5000, 200_000)
    entered, release = threading.Event(), threading.Event()
    original = guard.parse_large

    def slow(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    guard.parse_large = slow
    try:
        task = asyncio.create_task(parse(raw, place=place))
        assert await asyncio.to_thread(entered.wait, 3)
        task.cancel()
        await asyncio.sleep(.05)
        assert place.free == 0  # the thread still runs: the place is still taken
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        guard.parse_large = original
        release.set()
    assert place.free == 1


async def test_small_and_light_bodies_do_not_use_the_place():
    place = guard.ParsePlace(0)  # no place at all: anything that needed one would be busy
    assert (await parse(call({'limit': 1}), place=place))['id'] == 100
    light = call({'padding': 'a' * 800_000})
    assert not guard.classify(light)
    assert (await parse(light, place=place))['params']['arguments']['padding'] == 'a' * 800_000
    cjk = call({'padding': '中😀' * 200_000})
    assert (await parse(cjk, place=place))['params']['arguments']['padding'] == '中😀' * 200_000


async def test_a_body_of_exactly_the_large_size_is_small_and_one_byte_more_is_large():
    base = call({'padding': ''})
    at = call({'padding': 'a' * (guard.LARGE_REQUEST_BYTES - len(base))})
    assert len(at) == guard.LARGE_REQUEST_BYTES  # not large (the limit is exclusive): parsed as before
    assert (await parse(at, place=guard.ParsePlace(0)))['id'] == 100
    more = at + b' '
    assert len(more) > guard.LARGE_REQUEST_BYTES and (await parse(more, place=guard.ParsePlace(0)))['id'] == 100


async def test_switched_off_nothing_changes():
    """No parse slot (a switched-off product): the body goes through _parse_json_body exactly as before, whatever its
    shape: the kit's objects body is parsed (and then answered by the structure guard's own limits only)."""
    raw = padded_objects(99990)
    value = await gateway.json_body(request_for(raw), gateway.STRUCTURE_LIMITS)
    assert value['params']['arguments']['padding'][0] == {'a': 1} and len(value['params']['arguments']['padding']) == 99990
    # strict_json refusals and the structure guard are the same as before
    with pytest.raises(gateway.BadRequest):
        await gateway.json_body(request_for(b'{"id":1,"id":2}'), gateway.STRUCTURE_LIMITS)


@pytest.mark.parametrize('raw', [b'{"id":"\\ud800","pad":"' + b'a' * 70000 + b'"}',
                                 b'{"id":1,"id":2,"pad":"' + b'a' * 70000 + b'"}',
                                 b'{"id":NaN,"pad":"' + b'a' * 70000 + b'"}',
                                 b'{"id":1e999,"pad":"' + b'a' * 70000 + b'"}'])
async def test_large_bodies_keep_strict_json_rejections(raw):
    with pytest.raises(gateway.BadRequest) as error:
        await parse(raw)
    assert error.value.status == 400


async def test_large_heavy_bodies_keep_strict_json_rejections():
    pad = padded_objects(3000, 120000)
    for broken in (pad.replace(b'"limit":1', b'"limit":1,"limit":2'), pad.replace(b'"limit":1', b'"limit":NaN'),
                   pad.replace(b'"limit":1', b'"limit":"\\ud800"')):
        assert guard.classify(broken)
        with pytest.raises(gateway.BadRequest) as error:
            await parse(broken)
        assert error.value.status == 400


async def test_large_bodies_keep_the_utf8_and_structure_refusals():
    deep = call({'p': '[' * 70 + ']' * 70 + 'a' * 70000}).replace(b'"p":"', b'"p":' + b'[' * 70 + b']' * 70 + b',"q":"')
    for raw in (b'{"id":1,"pad":"' + b'a' * 70000 + b'\xff"}', deep,
                b'{"id":1,"x":[' + b'0,' * (MAX_ELEMENTS + 5) + b'0]}'):
        with pytest.raises(request_limits.RequestLimitError):
            await parse(raw)


async def test_lone_surrogate_check_walks_a_heavy_value():
    raw = padded_objects(3000, 120000).replace(b'"limit":1', b'"limit":{"k":["x","\\ud800"]}')
    assert guard.classify(raw)
    with pytest.raises(gateway.BadRequest):
        await parse(raw)
    ok = padded_objects(3000, 120000).replace(b'"limit":1', b'"limit":{"k":["x","\\ud83d\\ude00"]}')
    assert (await parse(ok))['params']['arguments']['limit'] == {'k': ['x', '😀']}


@pytest.mark.parametrize('value', [
    {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call', 'params': {'name': 'x', 'arguments': {'p': '中😀a\u2028' * 30000}}},
    {'a': [{'k': 1.5, 'u': None, 'v': True, 's': '\\"\n\t\x01é'}] * 5000, '中': {'😀': ['\ud7ff', '\U0010ffff']}},
    {'p': 'x' * 3_000_000}, {'p': [[]] * 20000}, {'p': {('k%d' % i): i for i in range(20000)}}])
def test_the_forwarded_bytes_are_json_dumps_byte_for_byte(value):
    loop = asyncio.new_event_loop()
    try:
        breath = guard.Breath(loop, threading.get_ident())
        assert guard.encode_forward(value, breath) == json.dumps(value, separators=(',', ':')).encode()
    finally:
        loop.close()
    assert reply_breath_is_off()


def reply_breath_is_off():
    from mcp_admin_core import reply_worker
    return getattr(reply_worker._breath, 'since', None) is None


# ---------------------------------------------------------------- CPU, not wall time -----------------------------------

def cpu(function, *args):
    start = time.thread_time()
    function(*args)
    return time.thread_time() - start


def test_the_refusal_costs_a_fraction_of_the_parse_in_cpu_time():
    raw = padded_objects(99990)
    parse_cost = min(cpu(strict_json, raw) for _ in range(3))
    refuse_cost = min(cpu(lambda: guard.too_costly(guard.scan(raw))) for _ in range(3))
    assert refuse_cost < parse_cost * 1.5  # the scan is linear and builds nothing; it is not the parse again
    # and the heavy body never reaches strict_json: the gateway test above


def test_a_piece_is_a_short_c_call_and_the_scan_breathes_between_pieces():
    raw = padded_objects(99990)
    calls = []
    guard.scan(raw, lambda: calls.append(1))
    assert len(calls) == -(-len(raw) // guard.SCAN_CHUNK)
    # the dearest single piece of the densest body, in CPU time, against the whole-body call it replaces
    piece = raw[len(raw) // 3: len(raw) // 3 + guard.SCAN_CHUNK]
    one_piece = min(cpu(lambda: guard._STRING.subn(b'', piece)) for _ in range(5))
    whole = min(cpu(lambda: guard._STRING.subn(b'', raw)) for _ in range(3))
    assert one_piece < whole / 10


@pytest.mark.parametrize('name,raw', [item for item in shapes() if item[0] in (
    'odoo_batch', 'objects', 'small_ints', 'big_ints', 'floats', 'short_strings', 'literals', 'wide_dict', 'nested',
    'ascii_string', 'cjk_string')], ids=lambda value: value if isinstance(value, str) else '')
def test_parse_time_model_is_an_upper_envelope_of_the_cpu_time(name, raw):
    """The whole-parse model (parse_seconds) is not below what strict_json costs in CPU time (30% for the runner's
    noise: the best of five runs against the model), and not more than 6 times above it."""
    found = guard.scan(raw)
    measured = min(cpu(strict_json, raw) for _ in range(5))
    assert guard.parse_seconds(found) >= measured * 0.7, name
    assert guard.parse_seconds(found) <= measured * 6 + 0.002, name


def test_the_scan_is_linear():
    small, large = padded_objects(20000), padded_objects(80000)
    a = min(cpu(guard.scan, small) for _ in range(3))
    b = min(cpu(guard.scan, large) for _ in range(3))
    assert b < a * 4 * 1.8  # four times the body, not much more than four times the time


# ---------------------------------------------------------------- the whole gateway (switched on, a child behind it) ---

from log_scan import log_scan  # noqa: E402,F401  (fixture)
from multi_profile_runtime import Children, multi_profile_runtime  # noqa: E402
from mcp_admin_core import profiles  # noqa: E402
from switched_gateway import B, PRODUCT, GatewayChild, bearer, session_of, setup, watch  # noqa: E402


def posted(ident, **arguments):
    return call(arguments, ident)


def passed_the_guard(answer):
    """The answer is the child's or the gateway's own about the call (a result, or an error that is not the guard's
    refusal -32602 or the busy -32003): the request got past the parse."""
    return answer.get('error', {}).get('code') not in (-32602, -32003)


async def two_profiles(tmp_path):
    data = setup(tmp_path)
    children = Children()
    default = children.add(3000, GatewayChild('default', PRODUCT, data))
    extra = children.add(18000, GatewayChild('p' + B[:4], PRODUCT, profiles.Layout(data).profile(B)))
    return data, children, default, extra


async def test_gateway_refuses_a_heavy_body_in_the_structure_shape_and_the_child_never_sees_it(tmp_path, log_scan):
    data, children, default, extra = await two_profiles(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            before = len(extra.seen)
            response = await client.post('/mcp', headers=headers, content=padded_objects(99990, 0))
            assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
            body = response.json()
            assert body['id'] == 100 and body['error']['code'] == -32602 and 'too much' in body['error']['message']
            assert len(extra.seen) == before  # nothing reached the child
            # the session goes on: a normal call answers
            ok = await client.post('/mcp', headers=headers, content=call({'limit': 1}, 101))
            assert ok.status_code == 200 and ok.json()['id'] == 101 and passed_the_guard(ok.json())


async def test_gateway_answers_the_exact_busy_shape_to_a_second_large_parse_and_serves_it_after(tmp_path, log_scan):
    data, children, default, extra = await two_profiles(tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = guard.parse_large

    def slow(*args):
        entered.set()
        assert release.wait(10)
        return original(*args)

    heavy_ok = padded_objects(5000, 200_000)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token_a, token_b = runtime.token('default'), runtime.token(B)
        guard.parse_large = slow
        try:
            async with runtime.mcp() as client:
                headers_a = {**bearer(token_a), 'Mcp-Session-Id': await session_of(client, token_a)}
                headers_b = {**bearer(token_b), 'Mcp-Session-Id': await session_of(client, token_b)}
                first = asyncio.create_task(client.post('/mcp', headers=headers_a, content=heavy_ok))
                assert await asyncio.to_thread(entered.wait, 5)
                started = time.monotonic()
                busy = await client.post('/mcp', headers=headers_b, content=padded_objects(5000, 200_000).replace(
                    b'"id":100', b'"id":777'))
                assert time.monotonic() - started < 2  # at once, never queued behind the first
                assert busy.status_code == 200 and busy.headers['retry-after'] == '5'
                assert busy.headers['cache-control'] == 'no-store'
                assert busy.json()['id'] == 777 and busy.json()['error']['code'] == -32003
                assert 'parsing another large request' in busy.json()['error']['message']
                # a normal small request of the same profile is served meanwhile
                small = await client.post('/mcp', headers=headers_b, content=call({'limit': 1}, 5))
                assert small.status_code == 200 and small.json()['id'] == 5
                release.set()
                served = await first
                assert served.status_code == 200 and served.json()['id'] == 100 and passed_the_guard(served.json())
                again = await client.post('/mcp', headers=headers_b, content=heavy_ok.replace(b'"id":100', b'"id":778'))
                assert again.status_code == 200 and again.json()['id'] == 778 and passed_the_guard(again.json())
        finally:
            guard.parse_large = original
            release.set()
