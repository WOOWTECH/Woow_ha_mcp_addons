"""HM-31: the JSON structure guard of every product (multi-profile plan 12.3 HM-31; contract 1.2, 2.4; the PaaS #155
guard, woow-mcp-server d7f5849 request_limits.structure_violation and not_utf8, its tests
test_gateway_request_structure.py and test_gateway_budget_round3.py (their structure and encoding cases); the
case-by-case map is in docs/provenance/ha-multiprofile-HM-31-20261116.md).

A byte budget counts bytes, but a parsed body costs by its structure: 16 MiB of [[],[],...] or [{},{},...] parse into
about 390 MiB (24 times; HM-08's measurement of strict_json: {} 24.1, [] 21.5, floats 6.5, small integers 4.2), one
string of the same size into 1 time. So before a POST body is parsed, every product (switched on or off: not gated)
scans its structural characters only, building nothing: more than 64 levels of nesting or more than 200,000 elements
(commas and containers; inside strings they do not count) is refused, and so is a body that is not UTF-8 (json.loads
would read UTF-16 or UTF-32, the scan would not: PaaS round 3 P1-A). The refusal is the PaaS one: 200 + -32602 under the
request's id when its head or tail shows it, else 413, the message without content. n8n's own limits run the same guard
first (McpRequestLimits.parse_and_check). Not JSON stays what it was (400: HA's parser refuses it; PaaS forwards it).

The 16 MiB bodies are made one at a time, when a test runs (no module-level corpus held across tests).
"""
import asyncio
import base64
import json
import time
import tracemalloc

import httpx
import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import gateway, request_limits
from mcp_admin_core.products import ProductStore, TOOLS
from test_single_profile_golden import configure

pytestmark = pytest.mark.usefixtures('log_scan')
MiB = 1024 * 1024
N = 16 * MiB
ACCEPT = 'application/json, text/event-stream'
# The guard's limits (PaaS d7f5849 DEFAULT_MAX_DEPTH, DEFAULT_MAX_TOTAL_ELEMENTS): test_the_default_limits_are_the_paas_ones.
DEFAULT_MAX_DEPTH = 64
DEFAULT_MAX_TOTAL_ELEMENTS = 200_000


def structure_violation(body, *, max_depth, max_elements):
    return request_limits.structure_violation(body, max_depth=max_depth, max_elements=max_elements)  # (red: missing)


def violation(body: bytes):
    return structure_violation(body, max_depth=DEFAULT_MAX_DEPTH, max_elements=DEFAULT_MAX_TOTAL_ELEMENTS)


def test_the_default_limits_are_the_paas_ones():
    assert (request_limits.DEFAULT_MAX_DEPTH, request_limits.DEFAULT_MAX_TOTAL_ELEMENTS) == (64, 200_000)


def envelope(arguments_json: bytes, rpc_id: int = 7) -> bytes:
    return (b'{"jsonrpc":"2.0","id":%d,"method":"tools/call","params":{"name":"execute_method","arguments":' % rpc_id
            + arguments_json + b'}}')


HEAD = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"execute_method","arguments":{"p":'
# The PaaS review's corpora (amp.py; round 3) and HM-08's: what a 16 MiB body of each is made of.
SHAPES = {'pad': None, 'lists': b'[],', 'dicts': b'{},', 'kv': b'{"a":1},', 'floats': b'1.5,', 'small-ints': b'1,',
          'strings': b'"ab",'}


def worst(kind: str, size: int = N) -> bytes:
    """A body of about size bytes: one string (pad) or an array of the shape (made when the test runs)."""
    if kind == 'pad':
        return HEAD + b'"' + b'x' * (size - 1024) + b'"}}}'
    unit = SHAPES[kind]
    return HEAD + b'[' + unit * ((size - 1024) // len(unit)) + b'0]}}}'


# ---- the scan (PaaS test_gateway_request_structure.py, units) ----

@pytest.mark.parametrize('kind', ['lists', 'dicts', 'kv', 'floats', 'small-ints', 'strings'])
def test_pathological_16_mib_bodies_are_refused(kind):
    """The amplification corpora with structure ({}, [], {"a":1}, floats, small integers, short strings): refused."""
    reason = violation(worst(kind))
    assert reason is not None and 'elements' in reason


def test_one_big_string_has_no_structure_to_refuse():
    assert violation(worst('pad')) is None


@pytest.mark.parametrize('text', ['你', '\U0001F600', 'é'], ids=['cjk', 'emoji', 'latin'])
def test_large_strings_of_chinese_and_emoji_pass_quickly(text):
    """The corpora without structure: 16 MiB of Chinese or emoji in one string is no element at all, valid UTF-8, and
    checked in linear time without decoding the whole body (PaaS round 3)."""
    body = envelope(json.dumps({'text': text * (N // 4)}, ensure_ascii=False).encode('utf-8'))
    started = time.process_time()
    assert violation(body) is None
    assert time.process_time() - started < .5


def test_a_legitimate_nextcloud_upload_of_13_3_mib_passes():
    content = base64.b64encode(b'\x00\xffbinary' * (10 * MiB // 8)).decode()
    assert len(content) > 13 * MiB
    assert violation(envelope(json.dumps({'path': '/a/b.bin', 'content': content}).encode())) is None


def test_a_legitimate_odoo_batch_create_of_thousands_of_records_passes():
    record = {f'x_field_{i}': f'value {i}' for i in range(28)}
    record['tag_ids'] = [[6, 0, [1, 2, 3]]]
    record['line_ids'] = [[0, 0, {'name': 'line', 'qty': 2.5}]]
    body = envelope(json.dumps({'model': 'res.partner', 'method': 'create', 'args': [[record] * 3000]}).encode())
    assert len(body) > MiB
    assert violation(body) is None


def test_a_legitimate_large_n8n_workflow_passes():
    node = {'id': 'n1', 'name': 'HTTP', 'type': 'n8n-nodes-base.httpRequest', 'position': [0, 0],
            'parameters': {'url': 'https://example.invalid', 'options': {'headers': [{'name': 'a', 'value': 'b'}] * 5}}}
    workflow = {'name': 'big', 'nodes': [node] * 1500,
                'connections': {f'n{i}': {'main': [[{'node': 'x', 'index': 0}]]} for i in range(1500)}}
    assert violation(envelope(json.dumps({'workflow': workflow}).encode())) is None


def test_a_batch_of_thousands_of_small_requests_passes_the_scan():
    batch = [{'jsonrpc': '2.0', 'id': i, 'method': 'tools/call', 'params': {'name': 't', 'arguments': {'a': [1, 2, 3]}}}
             for i in range(5000)]
    assert violation(json.dumps(batch).encode()) is None


def test_brackets_and_commas_inside_strings_do_not_count():
    noisy = b'{"text":"' + b'{[,],} ' * (N // 7) + b'","q":"\\"[[[["}'
    assert violation(noisy) is None


def test_the_depth_boundary():
    def nested(levels):
        return b'[' * levels + b']' * levels
    assert violation(nested(DEFAULT_MAX_DEPTH)) is None
    assert 'nesting' in violation(nested(DEFAULT_MAX_DEPTH + 1))
    assert violation(b'{"a":"' + b'[' * 500 + b'\\"' + b'[' * 500 + b'"}') is None


def test_the_element_boundary_counts_commas_and_containers():
    limit = 1000
    at_limit = b'[' + b','.join([b'0'] * limit) + b']'
    over = b'[' + b','.join([b'0'] * (limit + 1)) + b']'
    assert structure_violation(at_limit, max_depth=64, max_elements=limit) is None
    assert 'elements' in structure_violation(over, max_depth=64, max_elements=limit)


def test_the_scan_costs_what_the_limit_allows_not_what_the_body_holds():
    unterminated = b'"' + b'[,]' * 100_000 + b'"' + b'"' + b'x' * N
    for body in (worst('lists'), worst('kv'), worst('strings'), unterminated):
        started = time.perf_counter()
        violation(body)
        assert time.perf_counter() - started < 2.0


def test_an_n8n_limits_refusal_carries_no_content():
    limits = request_limits.McpRequestLimits(max_bytes=N, max_argument_elements=10)
    with pytest.raises(request_limits.RequestLimitError) as caught:
        limits.check_structure(b'{"secret-value":' + b'[' * 100 + b']' * 100 + b'}')
    assert 'secret-value' not in caught.value.payload['error']['message']
    assert caught.value.status == 413 and caught.value.payload['error']['code'] == -32602
    assert caught.value.kind == 'structure' and caught.value.log_reason == 'more than 64 levels of nesting'


# ---- encodings (PaaS test_gateway_budget_round3.py P1-A) ----

ENCODINGS = ['utf-16', 'utf-16-le', 'utf-16-be', 'utf-32', 'utf-32-le', 'utf-32-be']
TEXTS = {'simple': '{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
         'review-F1': '["∀",' + ','.join(['[]'] * 5000) + ']',
         'cjk': '{"name":"你好，世界"}'}


@pytest.mark.parametrize('encoding', ENCODINGS)
@pytest.mark.parametrize('name', sorted(TEXTS))
def test_utf16_and_utf32_bodies_are_refused(encoding, name):
    body = TEXTS[name].encode(encoding)
    reason = violation(body)
    assert reason is not None and 'UTF-8' in reason
    assert json.loads(body) is not None  # why: json.loads reads it, the scan could not


@pytest.mark.parametrize('bom', [b'\xff\xfe', b'\xfe\xff', b'\x00\x00\xfe\xff', b'\xff\xfe\x00\x00'])
def test_bom_prefixed_bodies_are_refused(bom):
    assert 'UTF-8' in violation(bom + b'[\x00]\x00')
    assert 'UTF-8' in violation(bom)


def test_a_nul_in_the_first_four_bytes_is_refused_as_json_detect_encoding_reads_it():
    assert 'UTF-8' in violation(b'[\x00\x00\x00')
    assert 'UTF-8' in violation(b'\x00[')


def test_bytes_that_are_not_valid_utf8_are_refused():
    assert 'UTF-8' in violation('{"a":"é"}'.encode('latin-1'))
    assert 'UTF-8' in violation(b'{"a":"\xff"}')
    assert 'UTF-8' in violation(b'{"a":"\xed\xa0\x80"}')  # an encoded surrogate is not UTF-8
    assert 'UTF-8' in violation('{"a":"你好"}'.encode()[:-3])  # a truncated character


LEGIT_UTF8 = ['{"name":"你好😀"}',
              '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"t","arguments":{"text":"こんにちは、世界！🎉🚀"}}}',
              '{"mixed":"abc 你好 こんにちは 😀 𝒳 é ñ ∀ \\u4f60 \\ud83d\\ude00"}',
              '["∀","中文",[1,2,{"k":"😀"}]]',
              '﻿{"bom":"utf-8 with BOM 你好"}',
              '{"emoji_only":"😀😀😀😀"}']


@pytest.mark.parametrize('text', LEGIT_UTF8)
def test_valid_utf8_with_chinese_and_emoji_passes(text):
    body = text.encode('utf-8')
    assert violation(body) is None
    json.loads(body)


def test_empty_and_plain_ascii_bodies_are_unchanged():
    assert violation(b'') is None
    assert violation(b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}') is None
    assert violation(b'not json at all') is None


def test_a_multibyte_character_split_by_a_check_block_is_not_misjudged():
    from mcp_admin_core import request_limits

    chunk = request_limits._UTF8_CHUNK
    for offset in range(5):
        body = b'{"a":"' + b'x' * (chunk - 6 - offset) + '你😀你'.encode() * 3 + b'"}'
        assert violation(body) is None


def test_an_encoding_refusal_says_so_and_a_structure_refusal_says_that():
    """The message names the encoding, not the structure (PaaS sandbox finding 3); the kind tells the WARNING."""
    limits = request_limits.McpRequestLimits(max_bytes=N, max_argument_elements=10)
    with pytest.raises(request_limits.RequestLimitError) as encoding:
        limits.parse_and_check('{"jsonrpc":"2.0","id":5,"method":"tools/call","secret-marker":1}'.encode('utf-16-le'))
    message = encoding.value.payload['error']['message']
    assert 'structure is too complex' not in message and 'not UTF-8' in message and 'secret-marker' not in message
    assert encoding.value.kind == 'encoding' and encoding.value.payload['error']['code'] == -32602
    with pytest.raises(request_limits.RequestLimitError) as structure:
        limits.parse_and_check(envelope(b'[' * (DEFAULT_MAX_DEPTH + 5) + b']' * (DEFAULT_MAX_DEPTH + 5)))
    assert 'structure is too complex' in structure.value.payload['error']['message']
    assert structure.value.kind == 'structure'
    assert structure.value.status == 200 and structure.value.payload['id'] == 7  # its id is in its head


# ---- closing brackets (PaaS round 3 P1-B) and the boundaries (P2-E) ----

def closers(total, closer):
    head = b'"' + b',' * 300_000 + b'"'  # commas inside a string defeat the fast path
    return head + closer * ((total - len(head)) // len(closer))


@pytest.mark.parametrize('closer', [b']', b'}]', b'}', b']}'])
def test_a_closing_bracket_flood_does_not_stall_the_scan(closer):
    body = closers(N, closer)
    started = time.process_time()
    assert violation(body) is None  # not JSON: no verdict (the parser refuses it), but fast
    assert time.process_time() - started < .3


def test_the_scan_time_does_not_grow_with_the_body():
    small, large = closers(N // 2, b']'), closers(N, b']')
    started = time.process_time()
    violation(small)
    small_time = time.process_time() - started
    started = time.process_time()
    violation(large)
    assert time.process_time() - started < 2 * small_time + .1


def test_closers_after_balanced_structure_are_bounded_too():
    body = b'[' + b'","' + b',' * 300_000 + b']' + b']' * (N - 300_100)
    started = time.process_time()
    violation(body)
    assert time.process_time() - started < .3


def test_valid_nesting_never_passes_the_work_bound():
    assert violation(b'[' * 64 + b']' * 64) is None
    assert violation(b'[' + b','.join([b'[]'] * 90_000) + b']') is None
    assert 'elements' in violation(b'[' + b','.join([b'[]'] * 120_000) + b']')


def test_a_plain_ascii_big_string_is_still_accepted():
    assert violation(envelope(b'{"text":"' + b'x' * (N - 4096) + b'"}')) is None


def test_an_escaped_quote_does_not_end_the_string():
    assert structure_violation(b'["a\\"' + b',' * 50 + b'"]', max_depth=64, max_elements=10) is None


def test_an_escaped_backslash_before_a_quote_does_end_the_string():
    assert 'elements' in structure_violation(b'["a\\\\"' + b',' * 50 + b']', max_depth=64, max_elements=10)


def test_backslash_pairs_and_quotes_in_the_slow_path():
    ends = b'["' + b'x\\\\' + b'"' + b',' * 40 + b']'
    continues = b'["' + b'x\\\\\\' + b'"' + b',' * 40 + b'"]'
    assert 'elements' in structure_violation(ends, max_depth=64, max_elements=30)
    assert structure_violation(continues, max_depth=64, max_elements=30) is None


def test_the_element_boundary_is_exactly_the_limit_on_the_fast_path():
    limit = DEFAULT_MAX_TOTAL_ELEMENTS
    assert violation(b'[' + b','.join([b'0'] * limit) + b']') is None
    assert 'elements' in violation(b'[' + b','.join([b'0'] * (limit + 1)) + b']')


def test_the_element_boundary_is_exactly_the_limit_on_the_slow_path():
    limit = DEFAULT_MAX_TOTAL_ELEMENTS
    noise = b'"' + b',' * 5000 + b'"'

    def make(elements):
        return b'[' + noise + b',0' * (elements - 1) + b']'
    assert violation(make(limit)) is None
    assert 'elements' in violation(make(limit + 1))


# ---- the corpora under the guard: what parsing still costs (HM-08's measurement, HM-19c measures on the hardware) ----

PARSE_UNITS = {'dicts': b'{},', 'lists': b'[],', 'kv': b'{"a":1},', 'floats': b'1.5,', 'small-ints': b'1,'}


@pytest.mark.parametrize('kind', sorted(PARSE_UNITS))
def test_what_the_guard_lets_through_parses_within_a_bounded_cost(kind):
    """The most structure the guard lets through (just under 200,000 elements of the shape, the rest one string, 4 MiB
    in all) parses with the gateway's own parser (config.strict_json) into a bounded amount of memory, whatever the
    shape: the element limit, not the body size, bounds it (HM-08 measured 16 MiB of {} at 24 times: about 390 MiB;
    under the guard the worst shape, 100,000 objects of one key, peaks at about 26 MiB here). The factors (EPYC 7713:
    up to 19.5 times at 1 MiB, 6.4 at 4 MiB, 3.1 at 16 MiB) are in the provenance note for HM-19c."""
    from mcp_admin_core.config import strict_json

    unit = PARSE_UNITS[kind]
    per_item = unit.count(b',') + unit.count(b'[') + unit.count(b'{')  # {}, is a container and a comma: 2 elements
    count = (DEFAULT_MAX_TOTAL_ELEMENTS - 20) // per_item
    structure = b'[' + unit * (count - 1) + b'0]'
    size = 4 * MiB
    body = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"s":' + structure + b',"pad":"' + \
        b'x' * (size - len(structure) - 200) + b'"}}'
    assert violation(body) is None
    tracemalloc.start()
    try:
        value = strict_json(body)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    del value
    assert peak < 64 * MiB, (kind, peak / MiB)


# ---- HTTP: every product's gateway (switched off) refuses before forwarding ----

class Child:
    """A child that answers every request (and records it)."""

    def __init__(self):
        self.seen = []

    def __call__(self, request):
        self.seen.append(request)
        message = json.loads(request.content) if request.content else {}
        if 'id' not in message:
            return httpx.Response(202)
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': message['id'], 'result': {'content': []}})


@pytest.fixture
def odoo_store(tmp_path):
    configure(tmp_path / 'odoo', 'odoo')
    store = ProductStore(tmp_path / 'odoo', 'odoo')
    yield store
    store.close()


async def post(store, child, body, *, product='odoo', session='hm31-session'):
    headers = {'Authorization': 'Bearer ' + store.load().token, 'Accept': ACCEPT, 'Content-Type': 'application/json',
               'Mcp-Session-Id': session}
    async with httpx.AsyncClient(transport=httpx.MockTransport(child)) as to_child:
        _, app = gateway.make_apps(store, TOOLS[product], to_child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://mcp') as client:
            return await asyncio.wait_for(client.post('/mcp', headers=headers, content=body), 30)


def refusal(response, status, ident, *, encoding=False):
    assert response.status_code == status, response.content[:200]
    assert response.headers['cache-control'] == 'no-store'
    payload = response.json()
    assert set(payload) == {'jsonrpc', 'id', 'error'} and payload['id'] == ident
    assert payload['error']['code'] == -32602
    assert ('not UTF-8' if encoding else 'structure is too complex') in payload['error']['message']
    return payload


def test_every_product_but_n8n_gets_the_default_structure_limits():
    assert (gateway.STRUCTURE_LIMITS.max_depth, gateway.STRUCTURE_LIMITS.max_total_elements) == (64, 200_000)
    assert gateway.STRUCTURE_LIMITS.max_bytes == gateway.MAX_REQUEST == 16 * MiB
    assert (gateway.N8N_REQUEST_LIMITS.max_depth, gateway.N8N_REQUEST_LIMITS.max_total_elements) == (64, 200_000)


@pytest.mark.parametrize('kind', ['lists', 'kv'])
async def test_a_pathological_body_is_refused_before_anything_is_forwarded(odoo_store, kind):
    """Its id is in its head: 200 + -32602 under it (an MCP SDK client then fails this call only); never forwarded."""
    child = Child()
    refusal(await post(odoo_store, child, worst(kind)), 200, 1)
    assert child.seen == []


async def test_a_too_deep_body_is_refused_and_the_message_has_no_content(odoo_store):
    child = Child()
    body = envelope(b'{"secret-marker":' + b'[' * (DEFAULT_MAX_DEPTH + 1) + b']' * (DEFAULT_MAX_DEPTH + 1) + b'}')
    payload = refusal(await post(odoo_store, child, body), 200, 7)
    assert 'levels of nesting' in payload['error']['message'] and 'secret-marker' not in json.dumps(payload)
    assert child.seen == []


async def test_a_body_without_a_recoverable_id_is_refused_with_413(odoo_store):
    child = Child()
    body = b'[' + b','.join([b'{"jsonrpc":"2.0","method":"notifications/x"}'] * (DEFAULT_MAX_TOTAL_ELEMENTS + 1)) + b']'
    refusal(await post(odoo_store, child, body), 413, None)
    assert child.seen == []


async def test_utf16_bodies_are_refused_and_never_parsed(odoo_store, monkeypatch):
    """A UTF-16 or UTF-32 body (that json.loads would read) is refused before the gateway's parser runs: 413 (its id
    cannot be read from its UTF-16 head), the encoding's message; never forwarded."""
    from mcp_admin_core import config

    def boom(raw):
        raise AssertionError('strict_json must not run for a body that is not UTF-8')
    monkeypatch.setattr(gateway, 'strict_json', boom)
    child = Child()
    for encoding in ENCODINGS:
        body = ('{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"a":["∀",' + ','.join(['[]'] * 100)
                + ']}}').encode(encoding)
        refusal(await post(odoo_store, child, body), 413, None, encoding=True)
    assert child.seen == [] and config.strict_json is not boom


async def test_legitimate_large_calls_still_forward(odoo_store):
    """A 10 MiB file as base64 (13.3 MiB, no element) and an Odoo batch create of 3,000 records of 30 fields (about
    93,000 elements): both reach the child; valid UTF-8 with Chinese and emoji too (PaaS round 3)."""
    child = Child()
    upload = base64.b64encode(b'\x01' * (10 * MiB)).decode()
    record = {f'f{i}': i for i in range(30)}
    bodies = (envelope(json.dumps({'path': '/x', 'content': upload}).encode()),
              envelope(json.dumps({'model': 'res.partner', 'method': 'create', 'args': [[record] * 3000]}).encode()),
              envelope(json.dumps({'text': '你好😀こんにちは'}, ensure_ascii=False).encode()))
    for body in bodies:
        response = await post(odoo_store, child, body)
        assert response.status_code == 200 and 'error' not in response.json(), response.content[:200]
    assert len(child.seen) == 3
    assert json.loads(child.seen[2].content)['params']['arguments'] == {'text': '你好😀こんにちは'}


async def test_not_json_and_bodiless_requests_answer_as_before(odoo_store):
    """Not JSON: today's 400 (HA's parser refuses it before any slot; PaaS forwards it). A GET has no body to guard."""
    child = Child()
    response = await post(odoo_store, child, b'this is not json {[[[')
    assert (response.status_code, response.json()) == (400, {'error': 'request denied'})
    assert child.seen == []


@pytest.mark.parametrize('route', ['bearer', 'private'])
async def test_n8n_runs_the_guard_first_and_answers_its_refusals_as_paas_does(tmp_path, route):
    """n8n's own limits (4 MiB, 10,000 argument elements, depth 64) run the structure guard first (PaaS round 3 F7):
    a body too deep is now 200 + -32602 under its id when its head shows it (before: 413, id null, "MCP JSON exceeds 64
    levels of nesting"); one that is not UTF-8 gets the encoding's refusal (before: 400 -32700)."""
    from n8n_adapter import TOOLS as N8N_TOOLS

    store = ProductStore(tmp_path / 'n8n', 'n8n')
    try:
        token = store.load().token
        child = Child()
        path, auth = (('/mcp', {'Authorization': 'Bearer ' + token}) if route == 'bearer'
                      else ('/private_' + token + '/mcp', {}))
        headers = {**auth, 'Accept': ACCEPT, 'Content-Type': 'application/json', 'Mcp-Session-Id': 'hm31-session'}
        deep = {}
        nested = deep
        for _ in range(65):
            nested['next'] = {}
            nested = nested['next']
        bodies = {'deep': json.dumps({'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
                                      'params': {'name': 'search_nodes', 'arguments': deep}}).encode(),
                  'utf16': json.dumps({'jsonrpc': '2.0', 'id': 8, 'method': 'tools/call',
                                       'params': {'name': 'search_nodes', 'arguments': {}}}).encode('utf-16')}
        async with httpx.AsyncClient(transport=httpx.MockTransport(child)) as to_child:
            _, app = gateway.make_apps(store, N8N_TOOLS, to_child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://mcp') as client:
                deep_answer = await client.post(path, headers=headers, content=bodies['deep'])
                utf16_answer = await client.post(path, headers=headers, content=bodies['utf16'])
        payload = refusal(deep_answer, 200, 7)
        assert 'more than 64 levels of nesting' in payload['error']['message']
        refusal(utf16_answer, 413, None, encoding=True)
        assert child.seen == []
    finally:
        store.close()


async def test_structure_refusals_log_one_throttled_warning_per_profile_and_kind(odoo_store, log_scan, monkeypatch):
    """PaaS round 3 P2-D: a structure refusal and an encoding refusal each write one WARNING a minute for the profile
    (the kind, the HTTP status and a short reason), the next one with suppressed=N; never content or a token."""
    from mcp_admin_core import request_budget

    child = Child()
    token = odoo_store.load().token
    log_scan.watch(token, odoo_store.load().child_token)
    clock = [5000.0]
    made = []
    real = request_budget.own_share

    def own_share(product=None):
        share = real(product)
        share.reports.clock = lambda: clock[0]
        made.append(share)
        return share
    monkeypatch.setattr(request_budget, 'own_share', own_share)
    bad = envelope(b'[' * (DEFAULT_MAX_DEPTH + 1) + b'"secret-marker"' + b']' * (DEFAULT_MAX_DEPTH + 1))
    utf16 = '{"jsonrpc":"2.0","id":7,"secret-marker":1}'.encode('utf-16-le')
    headers = {'Authorization': 'Bearer ' + token, 'Accept': ACCEPT, 'Content-Type': 'application/json',
               'Mcp-Session-Id': 'hm31-session'}

    def lines():
        return [record.getMessage() for record in log_scan.records
                if record.name == 'mcp_admin_core.request_budget' and 'refused a request body' in record.getMessage()]
    async with httpx.AsyncClient(transport=httpx.MockTransport(child)) as to_child:
        _, app = gateway.make_apps(odoo_store, TOOLS['odoo'], to_child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://mcp') as client:
            for _ in range(4):
                assert (await client.post('/mcp', headers=headers, content=bad)).status_code == 200
            assert len(lines()) == 1 and 'suppressed' not in lines()[0]
            assert lines()[0] == ('MCP gateway [profile=default]: refused a request body (structure, HTTP 200): more '
                                  'than 64 levels of nesting')
            await client.post('/mcp', headers=headers, content=utf16)  # its own kind, its own line
            assert len(lines()) == 2 and '(encoding, HTTP 413)' in lines()[1]
            clock[0] += request_budget.REPORT_SECONDS + 1
            await client.post('/mcp', headers=headers, content=bad)
            assert len(lines()) == 3 and lines()[2].endswith('suppressed=3')
    assert len(made) == 1
    assert not any('secret-marker' in text or token in text for _, _, _, text in log_scan.seen)
    assert child.seen == []
