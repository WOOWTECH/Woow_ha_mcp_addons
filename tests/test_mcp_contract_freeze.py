"""HM-01 contract freeze: the MCP endpoint's error contract and the 31 URL variants, as bb48449 answers them.

tests/contract/profiles_v1_cases.json is the first batch of the multi-profile contract cases (column "ha"): what the
default profile's MCP listener answers today, read from gateway.py (serve, leased_serve, secret_valid, token_valid,
the routes) and confirmed here. Every case is sent as a raw HTTP/1.1 request target to the production runtime of each
product (tests/test_single_profile_golden.py: production_runtime) on its real uvicorn listener (h11, as in the image:
uvicorn decodes %XX once, removes no dot segment and passes '#' through), with a configured backend and a ready
child. The case also fixes whether the child was reached. HM-08 adds the extra profiles' columns; for the default
profile every expectation here must keep holding.

The 31 URL variants, the unknown tokens and the header switches are the PaaS real-machine lists (T-05, Odoo profile
isolation run of 2026-11-13, receipt s04-token-routing.json and its harness s04_routing.py: the same names, targets and
placeholders); "paas_observed" records what PaaS answered there, for comparison only, and where HA answers otherwise
the case names the row of the deliberate differences (multi-profile plan 8.8) or a note. The two cross cases of
invariant I1 (plan 8.2) are cross-bearer-b and switch-authorization.
"""
import asyncio
import json
from pathlib import Path
import re
import secrets

import h11
import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from test_single_profile_golden import (PRODUCTS, configure, initialize_body, initialize_message,
                                        production_runtime, settle, stored)

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan
CASES = Path(__file__).with_name('contract') / 'profiles_v1_cases.json'
BODIES = {
    'initialize': json.dumps(initialize_message()).encode(),
    'tools_list': json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}).encode(),
    'initialized': json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}).encode(),
    'discover': json.dumps({'jsonrpc': '2.0', 'id': 9, 'method': 'server/discover'}).encode(),
    'malformed': b'{',
    'none': b'',
}


def contract():
    return json.loads(CASES.read_text())


def placeholders(token, other):
    if token.upper() == token:
        raise AssertionError('the default token has no lower-case letter')  # 43 random URL-safe characters
    # As the PaaS T-05 harness built them (s04_routing.py: AU, AP1, APA, AT); P24 has an extra profile id's form.
    return {'A': token, 'B': other, 'AU': token.upper(), 'AP1': '%%%02X' % ord(token[0]) + token[1:],
            'APA': ''.join('%%%02X' % ord(char) for char in token), 'AT': token[:-1],
            'R43': secrets.token_urlsafe(32), 'R64': secrets.token_hex(32), 'R257': 'a' * 257,
            'P24': secrets.token_hex(12)}


def fill(text, values):
    for name in sorted(values, key=len, reverse=True):
        text = text.replace('{' + name + '}', values[name])
    assert '{' not in text, text
    return text


async def raw_http(port, method, target, headers, body):
    """One request with this exact target (no client normalization) on its own connection: (status, headers, body)."""
    reader, writer = await asyncio.open_connection('127.0.0.1', port)
    try:
        connection = h11.Connection(h11.CLIENT)
        head = [('Host', '127.0.0.1'), *headers, ('Content-Length', str(len(body))), ('Connection', 'close')]
        data = connection.send(h11.Request(method=method, target=target.encode('ascii'), headers=head))
        if body:
            data += connection.send(h11.Data(data=body))
        data += connection.send(h11.EndOfMessage())
        writer.write(data)
        await writer.drain()
        response, chunks = None, []
        async with asyncio.timeout(10):
            while True:
                event = connection.next_event()
                if event is h11.NEED_DATA:
                    connection.receive_data(await reader.read(65536))
                elif isinstance(event, h11.Response):
                    response = event
                elif isinstance(event, h11.Data):
                    chunks.append(bytes(event.data))
                elif isinstance(event, (h11.EndOfMessage, h11.ConnectionClosed)):
                    break
        return (response.status_code, [(name.decode('latin-1').lower(), value.decode('latin-1'))
                                       for name, value in response.headers], b''.join(chunks))
    finally:
        writer.close()
        await writer.wait_closed()


def request_of(case, values):
    headers = [('Accept', 'application/json, text/event-stream')]
    if case['body'] != 'none':
        headers.append(('Content-Type', 'application/json'))
    for name, value in case.get('headers', []):
        headers = [pair for pair in headers if pair[0].lower() != name.lower() or name.lower() == 'authorization']
        headers.append((name, fill(value, values)))
    return case['method'], fill(case['target'], values), headers, BODIES[case['body']]


def expectation(case, product):
    return {**case['ha'], **case.get('ha_products', {}).get(product, {})}


def mismatch(document, case, product, status, headers, body, reached):
    """What differs from the case's ha expectation for this product (empty when it holds)."""
    expected = expectation(case, product)
    response = document['responses'][expected['response']]
    found = []
    if status != response['status']:
        found.append(f'status {status} != {response["status"]}')
    names = {}
    for name, value in headers:
        names.setdefault(name, []).append(value)
    for name, value in response.get('headers', {}).items():
        if names.get(name) != [value]:
            found.append(f'header {name} {names.get(name)} != [{value!r}]')
    for name in response.get('absent', []):
        if name in names:
            found.append(f'header {name} present')
    wanted = initialize_body(product) if response['body'] == '<initialize>' else response['body'].encode()
    if body != wanted:
        found.append(f'body {body[:80]!r} != {wanted[:80]!r}')
    if reached != expected['child']:
        found.append(f'child reached {reached} != {expected["child"]}')
    return found


def test_cases_file_is_well_formed():
    document = contract()
    assert set(document) == {'schema', 'contract', 'batch', 'baseline', 'conditions', 'columns', 'placeholders',
                             'bodies', 'responses', 'cases'}
    assert document['schema'] == 1 and document['contract'] == 'profiles_v1' and document['baseline'] == 'bb48449'
    assert set(document['bodies']) == set(BODIES)
    assert set(document['placeholders']) == set(placeholders('aA' * 21 + 'a', 'b' * 43))
    ids = [case['id'] for case in document['cases']]
    assert len(ids) == len(set(ids))
    variants = [case for case in document['cases'] if case['group'] == 'url_variant']
    assert len(variants) == 31 and len({case['paas_name'] for case in variants}) == 31
    names = [case['paas_name'] for case in document['cases'] if 'paas_name' in case]
    assert len(names) == len(set(names))
    for case in document['cases']:
        assert set(case) <= {'id', 'group', 'paas_name', 'paas_observed', 'method', 'target', 'headers', 'body',
                             'note', 'deviation', 'ha', 'ha_products'}, case['id']
        assert case['body'] in BODIES and case['method'] in ('GET', 'POST', 'PUT', 'DELETE'), case['id']
        for value in (case['ha'], *case.get('ha_products', {}).values()):
            assert set(value) <= {'response', 'child', 'profile'}, case['id']
            assert value['response'] in document['responses'], case['id']
            assert value['profile'] == ('default' if value['child'] else None), case['id']
        assert set(case.get('ha_products', {})) <= set(PRODUCTS), case['id']
        assert ('paas_name' in case) == ('paas_observed' in case), case['id']
        assert 'deviation' not in case or re.fullmatch(r'§8\.8 #[1-9][0-9]?', case['deviation']), case['id']
        # Where HA answers otherwise than PaaS did, the case says why: a row of the deliberate differences or a note.
        if 'paas_observed' in case and document['responses'][case['ha']['response']]['status'] != case['paas_observed']:
            assert 'deviation' in case or 'note' in case, case['id']
    for response in document['responses'].values():
        assert set(response) <= {'status', 'headers', 'absent', 'body', 'meaning'}


@pytest.mark.parametrize('product', PRODUCTS)
async def test_mcp_contract_freeze(tmp_path, log_scan, product):
    document = contract()
    data = tmp_path / 'data'
    configure(data, product)
    other = secrets.token_urlsafe(32)
    log_scan.watch(other)
    async with production_runtime(product, data, sockets=True) as runtime:
        await settle(runtime, 'configured')
        token = stored(data)['token']
        values = placeholders(token, other)
        # The tokens and every token-shaped value a request carries (the percent-encoded and upper-case forms of A too;
        # AP1 and AT are pieces of A, which any 16-character piece of A already finds).
        log_scan.watch(token, stored(data)['child_token'], *(values[name] for name in ('AU', 'APA', 'R43', 'R64')))
        failures = []
        for case in document['cases']:
            method, target, headers, body = request_of(case, values)
            since = len(runtime.child.requests)
            status, answer, content = await raw_http(runtime.mcp_port, method, target, headers, body)
            reached = bool(runtime.child.forwarded(since))
            found = mismatch(document, case, product, status, answer, content, reached)
            if found:
                failures.append(f'{case["id"]} ({case.get("paas_name") or case["group"]}): ' + '; '.join(found))
    detail = '\n'.join(failure.replace(token, '<A>').replace(other, '<B>') for failure in failures)
    assert not failures, f'{product}: {len(failures)} case(s) differ from the frozen contract:\n{detail}'
