"""HM-19c: a large MCP request is read by its envelope, not parsed (request_envelope.py; gateway.enveloped_json_body).

The scan's answers equal what json.loads and structure_violation say about the same bytes (fuzzed with tiny chunk sizes so
every chunk-boundary case happens), and a switched-on gateway hands the child the large body's bytes as they came."""
import asyncio
import json
import random
import time

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
import reply_load as RL
from multi_profile_runtime import multi_profile_runtime
from mcp_admin_core import gateway, request_envelope as E, request_limits
from test_profile_runtime import ProfileChild

LIMITS = E.EnvelopeLimits()
KiB = 1024


def scan(raw, keys_for=lambda name: (), limits=LIMITS):
    return E.scan_sync(raw, limits, keys_for)


def message(arguments, *, params_extra=None, order=0, pretty=False, ident=5, name='t'):
    params = {'name': name, 'arguments': arguments, **(params_extra or {})}
    items = list(params.items())
    if order:
        items.reverse()
    return json.dumps({'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call', 'params': dict(items)},
                      ensure_ascii=bool(order & 1), indent=2 if pretty else None,
                      separators=None if pretty else (',', ':')).encode()


@pytest.fixture
def tiny_chunks(monkeypatch):
    monkeypatch.setattr(E, 'CHUNK', 64)
    monkeypatch.setattr(E, 'FIRST_STEP', 8)
    monkeypatch.setattr(E, 'EXACT_SLICE', 16)


def value(rng, depth=0):
    kind = rng.random()
    if depth > 4 or kind < .3:
        return rng.choice([1, 'a"b\\', '中😀\n', None, True, 1.5, 'x' * rng.randint(0, 3000)])
    if kind < .65:
        return [value(rng, depth + 1) for _ in range(rng.randint(0, 8))]
    return {rng.choice(['a', 'b\\"', 'k%d' % rng.randint(0, 99)]): value(rng, depth + 1) for _ in range(rng.randint(0, 6))}


def test_the_scan_equals_json_loads_and_the_structure_guard_on_random_bodies(tiny_chunks):
    rng = random.Random(7)
    for _ in range(600):
        meta = rng.choice([None, {'traceparent': '00-ab'}])
        raw = message({'x': value(rng), 'y': value(rng)}, params_extra=None if meta is None else {'_meta': meta},
                      order=rng.randint(0, 3), pretty=rng.random() < .3)
        found = scan(raw)
        expected = json.loads(raw)
        expected['params'].pop('_meta', None)
        assert json.loads(found.forward) == expected
        assert found.message['params']['name'] == 't' and found.message['id'] == 5
        assert found.meta_removed == (meta is not None)
        # elements: exactly the structure guard's count
        assert request_limits.structure_violation(raw, max_depth=64, max_elements=found.elements) is None
        assert request_limits.structure_violation(raw, max_depth=64, max_elements=found.elements - 1) is not None


def test_a_body_without_meta_is_forwarded_as_the_same_bytes():
    raw = message({'a': [1, 2, {'b': 'c'}]})
    assert scan(raw).forward is raw


@pytest.mark.parametrize('meta_position', ['first', 'middle', 'last', 'only'])
def test_meta_is_cut_out_of_the_bytes_whatever_its_place(meta_position):
    meta = b'"_meta":{"traceparent":"00-ab","progressToken":3}'
    parts = {'first': [meta, b'"name":"t"', b'"arguments":{"q":[1]}'],
             'middle': [b'"name":"t"', meta, b'"arguments":{"q":[1]}'],
             'last': [b'"name":"t"', b'"arguments":{"q":[1]}', meta],
             'only': [meta]}[meta_position]
    raw = b'{"jsonrpc":"2.0","id":9,"method":"tools/call","params":{' + b' , '.join(parts) + b'}}'
    found = scan(raw)
    expected = json.loads(raw)
    del expected['params']['_meta']
    assert json.loads(found.forward) == expected
    assert b'_meta' not in found.forward


@pytest.mark.parametrize('meta, how', [(b'[1]', 'not an object'), (b'"x"', 'not an object'),
                                       (b'{"a":"' + b'x' * 9000 + b'"}', 'over 8192 bytes')])
def test_an_invalid_or_oversized_meta_is_denied(meta, how):
    raw = b'{"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"name":"t","_meta":' + meta + b'}}'
    with pytest.raises(E.EnvelopeDenied):
        scan(raw)


@pytest.mark.parametrize('raw', [
    b'{"jsonrpc":"2.0","id":1,"id":2,"method":"tools/call","params":{"name":"t"}}',
    b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"a","name":"b"}}',
    b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"t"},"params":{"name":"u"}}',
    b'{"jsonrpc":"2.0","id":NaN,"method":"tools/call","params":{"name":"t"}}',
    b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"t"}} x',
    b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"t","arguments":{"a":"\x01"}}}',
    b'{"jsonrpc":"2.0","id":"\\ud800","method":"tools/call","params":{"name":"t"}}',
    b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"t","arguments":{"a":"\\ud83d"}}}',
    b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"t","arguments":{"a":"\\ude00\\ud83d"}}}',
    b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"t","arguments":{"a":"unterminated}}}',
    b'',
    b'[1]',
])
def test_what_the_envelope_reads_is_strict(raw):
    with pytest.raises(ValueError):  # EnvelopeInvalid
        scan(raw)


def test_malformed_content_that_still_balances_is_the_childs_to_refuse():
    for inner in (b'{"a":1 "b":2}', b'{"a":01,}', b'{"a":[1,,]}'):
        raw = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"t","arguments":' + inner + b'}}'
        assert scan(raw).message['id'] == 1  # the gateway does not validate what it does not read


def test_a_duplicate_key_inside_skipped_content_is_the_childs_to_judge():
    raw = message({'a': 1}).replace(b'{"a":1}', b'{"a":1,"a":2,"n":Infinity}')
    assert scan(raw).message['params']['name'] == 't'  # documented change: only the envelope's own keys are checked


def test_valid_surrogate_pairs_pass_in_any_chunk_position(tiny_chunks):
    for pad in range(0, 100):
        text = 'x' * pad + '😀' + 'y' * 5
        raw = message({'t': text}, order=1)  # ensure_ascii: the pair is written as two escapes
        assert b'\\ud83d\\ude00' in raw
        assert scan(raw).message['params']['name'] == 't'


@pytest.mark.parametrize('pad', range(0, 90, 3))
def test_a_lone_surrogate_is_found_in_any_chunk_position(tiny_chunks, pad):
    raw = (b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"t","arguments":{"a":"' + b'x' * pad
           + b'\\ud83d\\ud83d\\ude00"}}}')
    with pytest.raises(ValueError):
        scan(raw)


def test_an_escaped_backslash_before_u_is_not_an_escape(tiny_chunks):
    raw = message({'a': 'x\\ud800'})  # the text backslash-u-d-8-0-0
    assert scan(raw).message['id'] == 5


def test_depth_and_element_limits_are_the_guards(tiny_chunks):
    deep = message(json.loads('[' * 60 + ']' * 60))  # 3 levels of envelope + 60 = 63... plus the list itself
    assert scan(deep)
    too_deep = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"t","arguments":' + b'[' * 70 + b']' * 70 + b'}}'
    with pytest.raises(E.EnvelopeRefused) as refused:
        scan(too_deep)
    assert refused.value.reason == 'more than 64 levels of nesting'
    flat = message({'p': [{}] * 100_000})
    with pytest.raises(E.EnvelopeRefused) as refused:
        scan(flat, limits=E.EnvelopeLimits(max_elements=100_000))
    assert refused.value.reason == 'more than 100000 JSON elements'


@pytest.mark.parametrize('opening, closing', [(b'[', b']'), (b'{"a":', b'}')])
def test_nesting_depth_boundary_is_exact(opening, closing):
    head = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"t","arguments":'
    for levels in (61, 62):  # envelope (1) + params (2) + arguments level: 3 + levels - 1
        raw = head + opening * levels + b'1' + closing * levels + b'}}'
        old = request_limits.structure_violation(raw, max_depth=64, max_elements=10**6)
        try:
            scan(raw)
            new = None
        except E.EnvelopeRefused as refused:
            new = refused.reason
        assert (old is None) == (new is None), (levels, old, new)


def test_container_density_limit_refuses_the_dense_shape_and_only_it():
    dense = message({'padding': [{'a': 1}] * 99_990})
    scan(dense)  # no density limit by default
    limits = E.EnvelopeLimits(max_containers_per_kib=64)
    with pytest.raises(E.EnvelopeRefused) as refused:
        scan(dense, limits=limits)
    assert 'containers per KiB' in refused.value.reason
    scan(message({'records': [{'name': 'a record with a name of a realistic length', 'x': i} for i in range(2000)]}), limits=limits)


def test_utf8_check_matches_not_utf8():
    for raw in (b'{"a":"\xff"}', '{"a":"中"}'.encode('utf-16'), b'{"a":"\xe4\xb8"}'):
        with pytest.raises(E.EnvelopeRefused) as refused:
            scan(raw)
        assert request_limits.not_utf8(raw) and refused.value.reason == request_limits.NOT_UTF8_REASON
    raw = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                      'params': {'name': 't', 'arguments': {'a': '中😀' * 30_000}}}, ensure_ascii=False).encode()
    assert not request_limits.not_utf8(raw) and scan(raw).message['id'] == 1


def test_selector_keys_are_read_wherever_the_arguments_sit():
    keys = lambda name: ('action',) if name == 'sel' else ()  # noqa: E731
    for order in (0, 1):
        raw = message({'pad': [1] * 1000, 'action': 'delete', 'deep': {'action': 'ignored'}}, order=order, name='sel')
        found = scan(raw, keys)
        assert found.message['params']['arguments'] == {'action': 'delete'}
    plain = scan(message({'action': 'delete'}, name='other'), keys)
    assert isinstance(plain.message['params']['arguments'], dict) and 'action' not in plain.message['params']['arguments']
    dup = message({'action': 'x'}, name='sel').replace(b'"action":"x"', b'"action":"read","action":"delete"')
    with pytest.raises(ValueError):
        scan(dup, keys)
    big = message({'action': 'q' * 9000}, name='sel')
    stand_in = scan(big, keys).message['params']['arguments']['action']
    assert not isinstance(stand_in, str)  # policy refuses a selector that is not a known string
    not_object = scan(message([1, 2, 3], name='sel'), keys)
    assert not isinstance(not_object.message['params']['arguments'], dict)


def test_a_tool_that_reads_its_whole_arguments_takes_the_full_parse():
    with pytest.raises(E.NeedsFullParse):
        scan(message({'a': 1}, order=1, name='whole'), lambda name: None)
    with pytest.raises(E.NeedsFullParse):
        scan(message({'a': 1}, name='whole'), lambda name: None)


def test_every_step_is_short_and_the_scan_costs_what_the_limit_allows():
    shapes = {
        'objects': message({'limit': 1, 'padding': [{'a': 1}] * 99_990}),
        'ascii': message({'padding': 'a' * (4 << 20)}),
        'cjk': json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                           'params': {'name': 't', 'arguments': {'p': '中' * 1_000_000}}}, ensure_ascii=False).encode(),
        'escapes': message({'p': '😀' * 400_000}, order=1),
    }
    for kind, raw in shapes.items():
        steps = E.scan_steps(raw, LIMITS, lambda name: ())
        worst = 0.0
        while True:
            started = time.perf_counter()
            try:
                next(steps)
            except StopIteration:
                worst = max(worst, time.perf_counter() - started)
                break
            worst = max(worst, time.perf_counter() - started)
        assert worst < .05, (kind, worst)  # one step: tens of times under the 50 ms bound even on a loaded runner


# ---- the gateway ------------------------------------------------------------------------------------------------

def big_call(ident, *, meta=None, name='search_records', pad=200_000, arguments=None):
    params = {'name': name, 'arguments': arguments if arguments is not None else {'limit': 1, 'padding': 'p' * pad}}
    if meta is not None:
        params['_meta'] = meta
    return json.dumps({'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call', 'params': params},
                      separators=(',', ':')).encode()


async def ready(client, headers):
    for _ in range(100):
        reply = await client.post('/mcp', headers=headers, json=RL.call(1, {'limit': 1}))
        if 'result' in reply.json():
            return
        await asyncio.sleep(.1)
    raise AssertionError('the add-on never became ready')


async def started(tmp_path, log_scan):
    data, children = RL.setup(tmp_path, {}, ProfileChild)
    own = children.add(3000, ProfileChild('default', 'odoo', data))
    return data, children, own


async def test_a_switched_on_gateway_forwards_a_large_call_as_it_came_and_cuts_out_meta(tmp_path, log_scan):
    data, children, child = await started(tmp_path, log_scan)
    async with multi_profile_runtime('odoo', data, children=children) as runtime:
        token = runtime.token('default')
        async with runtime.mcp(timeout=60) as client:
            session = await RL.session_of(client, token)
            headers = {**RL.bearer(token), 'Mcp-Session-Id': session, 'Content-Type': 'application/json'}
            await ready(client, headers)
            plain = big_call(11)
            reply = await client.post('/mcp', headers=headers, content=plain)
            assert reply.status_code == 200 and 'result' in reply.json(), reply.text[:300]
            assert child.requests[-1].content == plain  # not one byte changed, not re-serialized
            with_meta = big_call(12, meta={'traceparent': '00-abc', 'progressToken': 'p'})
            reply = await client.post('/mcp', headers=headers, content=with_meta)
            assert reply.status_code == 200 and reply.json()['id'] == 12
            forwarded = json.loads(child.requests[-1].content)
            assert '_meta' not in forwarded['params'] and forwarded['params']['name'] == 'search_records'
            assert child.requests[-1].content == big_call(12)


async def test_a_large_body_that_is_not_a_tools_call_is_refused_before_the_child(tmp_path, log_scan):
    data, children, child = await started(tmp_path, log_scan)
    async with multi_profile_runtime('odoo', data, children=children) as runtime:
        token = runtime.token('default')
        async with runtime.mcp(timeout=60) as client:
            session = await RL.session_of(client, token)
            headers = {**RL.bearer(token), 'Mcp-Session-Id': session, 'Content-Type': 'application/json'}
            await ready(client, headers)
            seen = len(child.requests)
            body = json.dumps({'jsonrpc': '2.0', 'id': 21, 'method': 'tools/list', 'params': {'cursor': 'c' * 200_000}},
                              separators=(',', ':')).encode()
            reply = await client.post('/mcp', headers=headers, content=body)
            assert reply.status_code == 200 and reply.json()['id'] == 21 and reply.json()['error']['code'] == -32602
            assert len(child.requests) == seen


async def test_strict_refusals_of_a_large_body_keep_their_codes(tmp_path, log_scan):
    data, children, child = await started(tmp_path, log_scan)
    async with multi_profile_runtime('odoo', data, children=children) as runtime:
        token = runtime.token('default')
        async with runtime.mcp(timeout=60) as client:
            session = await RL.session_of(client, token)
            headers = {**RL.bearer(token), 'Mcp-Session-Id': session, 'Content-Type': 'application/json'}
            await ready(client, headers)
            seen = len(child.requests)
            dup = big_call(31).replace(b'"id":31', b'"id":31,"id":32')
            assert (await client.post('/mcp', headers=headers, content=dup)).status_code == 400
            lone = big_call(33).replace(b'"limit":1', b'"limit":1,"s":"\\ud800"')
            assert (await client.post('/mcp', headers=headers, content=lone)).status_code == 400
            bad_meta = big_call(34, meta=[1])
            assert (await client.post('/mcp', headers=headers, content=bad_meta)).status_code == 403
            deep = big_call(35, arguments={'p': json.loads('[' * 70 + ']' * 70), 'pad': 'x' * 100_000})
            reply = await client.post('/mcp', headers=headers, content=deep)
            assert reply.status_code == 200 and reply.json()['error']['code'] == -32602
            unknown = big_call(36, name='no_such_tool')
            reply = await client.post('/mcp', headers=headers, content=unknown)
            assert reply.status_code in (200, 403) and len(child.requests) == seen


async def test_a_small_call_is_still_parsed_and_serialized_as_before(tmp_path, log_scan):
    data, children, child = await started(tmp_path, log_scan)
    async with multi_profile_runtime('odoo', data, children=children) as runtime:
        token = runtime.token('default')
        async with runtime.mcp(timeout=60) as client:
            session = await RL.session_of(client, token)
            headers = {**RL.bearer(token), 'Mcp-Session-Id': session, 'Content-Type': 'application/json'}
            await ready(client, headers)
            small = big_call(41, pad=100, meta={'t': 1}).replace(b'"limit":1', b'"limit":1,"s":"\xe4\xb8\xad"')
            reply = await client.post('/mcp', headers=headers, content=small)
            assert reply.status_code == 200
            sent = child.requests[-1].content
            assert sent == json.dumps(json.loads(sent), separators=(',', ':')).encode() and b'_meta' not in sent
            assert b'\\u4e2d' in sent  # as before: ASCII-escaped by the gateway's own serialization


async def test_the_event_loop_keeps_running_while_a_dense_body_is_scanned(tmp_path, log_scan):
    data, children, child = await started(tmp_path, log_scan)
    async with multi_profile_runtime('odoo', data, children=children) as runtime:
        token = runtime.token('default')
        async with runtime.mcp(timeout=120) as client:
            session = await RL.session_of(client, token)
            headers = {**RL.bearer(token), 'Mcp-Session-Id': session, 'Content-Type': 'application/json'}
            await ready(client, headers)
            dense = big_call(51, arguments={'limit': 1, 'padding': [{'a': 1}] * 99_990})
            lag = RL.LoopLag(.005).start()
            replies = await asyncio.gather(*[client.post('/mcp', headers=headers, content=dense.replace(b'"id":51', b'"id":%d' % (51 + i)))
                                             for i in range(8)])
            await lag.stop()
            assert all(r.status_code == 200 for r in replies)
            assert lag.worst < .15, lag.worst  # the ASGI rig shares the loop with the 8 clients; the bench measures the real figure
