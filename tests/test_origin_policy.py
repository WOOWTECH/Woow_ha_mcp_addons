"""HM-27: the secret path's add-on-wide Origin allowlist, report-only by default (multi-profile plan 8.7, 12.3 HM-27, 3.3,
7.2 point 10; DQ-11 (a), the user's decision of 2026-11-14; contract 2.6, 3.1, 3.5, 4.1 and section 9 #9, #10, #42 and
HM-27's rows; FM-73, FM-74, FM-123; acceptance T-24).

Once a product is switched on (features.enabled; run_product's ProfileManager), every profile's secret path
(/private_<token>/mcp) checks the Origin of a request whose token it accepted, against one list for the whole add-on
(mcp_admin_core.origin_policy; /data/mcp/origin-policy.json, never the default profile's state):

- report-only (the default; no file: https://claude.ai only): a request whose Origin the list does not hold (not listed,
  malformed, null, more than one) is answered exactly as without the check, byte for byte, and writes one
  decision=would_deny line naming the profile (its id's first 8 characters), at most one per profile and origin a
  minute and 20 a minute per profile, never its path, token, query, another header or its body;
- enforce: only such a request is refused (403 {"error":"request denied"}, the gateway's fixed answer), with one
  decision=deny line; no Origin, or exactly one the list holds, is served as before;
- never a CORS header (FM-74); the Bearer path refuses any Origin as before (DQ-11's second question waits for S14);
  Headscale keeps its own rule (only https://claude.ai) and has no policy; a wrong token never reaches the check;
- the panel reads and saves it through the shared management pipeline (GET and PUT {base}/api/origin-policy: the role
  checks, If-Match, Idempotency-Key, the receipts beside the file);
- a file that cannot be used: every secret-path request whose token is checked is 503 {"error":"state unavailable"},
  until the panel saves a new one over it (the PaaS runtime behaviour for a bad value);
- after a restore (HM-13b's boot guard; this slice merged after HM-13b and HM-13c): the policy is the backup's, as it
  came back (saved, absent or unusable), and every save made before the restore answers 410 operation_restored (the
  guard archives the receipts beside the policy as the index's).

Switched off nothing of it exists: the file is never read or written, the route is an unknown operation (404), any
Origin on the secret path is served as today and no line is written (HM-01's golden regression and both contract
freezes keep proving the bytes).

The PaaS tests (woow-mcp-server 69ac425: packages/mcp-admin-core/tests/test_origin_*.py) are mapped case by case in
docs/provenance/ha-multiprofile-HM-27-20261117.md; the log-rendering cases here are theirs, on HA's line.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
from pathlib import Path
import random
import re
import secrets
import shutil
import stat
import threading
import time

import httpx
import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from switch_modes import switched_off  # noqa: F401  (fixture: HM-23, the switch a test pins)
from mcp_admin_core import operations, profiles
from multi_profile_runtime import Children, SWITCHABLE, create_profile, ids, multi_profile_runtime, stored
from restore_guard_disk import newest_ctime
from test_restore_detection import after_tick, supervisor_restore
from test_single_profile_golden import (ACCEPT, ADMIN, BEARER_REQUIRED, GENUINE_CLIENT, NOT_FOUND, PRODUCTS, answer,
                                        configure, initialize_body, initialize_message, json_answer,
                                        production_runtime, settle)

pytestmark = pytest.mark.usefixtures('log_scan')
LOGGER = 'mcp_admin_core.origin_policy'
B, = ids(1)
POLICY = 'origin-policy.json'
RECEIPTS = '.origin-policy.json.operations.json'
DENIED_403 = (403, [('content-length', '26'), ('content-type', 'application/json')], b'{"error":"request denied"}')
UNAVAILABLE = (503, [('content-length', '29'), ('content-type', 'application/json')], b'{"error":"state unavailable"}')
# The products of run_product that may be switched on and use the service-level list (Headscale keeps its own rule).
LISTED = tuple(product for product in SWITCHABLE if product != 'headscale')
ORIGIN_CASES = {
    'none': [],
    'allowed': [('Origin', 'https://claude.ai')],
    'allowed-otherwise-spelled': [('Origin', 'HTTPS://Claude.AI:443')],
    'not-allowed': [('Origin', 'https://evil.example')],
    'null': [('Origin', 'null')],
    'duplicate': [('Origin', 'https://evil.example'), ('Origin', 'https://claude.ai')],
    'allowed-twice': [('Origin', 'https://claude.ai'), ('Origin', 'https://claude.ai')],
    'malformed': [('Origin', 'https://claude.ai/')],
    'empty': [('Origin', '')],
}
# case -> (reason, the origin as the line shows it): the cases the default list does not hold.
NOT_PERMITTED = {
    'not-allowed': ('not_allowed', 'https://evil.example'),
    'null': ('null', 'null'),
    'duplicate': ('duplicate', 'https://evil.example,https://claude.ai'),
    'allowed-twice': ('duplicate', 'https://claude.ai,https://claude.ai'),
    'malformed': ('malformed', 'https://claude.ai(has=path)'),
    'empty': ('malformed', 'non-url(len=0,classes=none)'),
}


def module():
    import mcp_admin_core.origin_policy as found  # imported when a test runs (the red half of red-green)
    return found


def would_deny(profile, reason, shown):
    return (f'MCP gateway [profile={profile}]: an Origin the secret path does not allow (report-only: served as '
            f'usual) decision=would_deny mode=report-only reason={reason} origin="{shown}"')


def deny(profile, reason, shown):
    return (f'MCP gateway [profile={profile}]: an Origin the secret path does not allow (enforce: refused, 403) '
            f'decision=deny mode=enforce reason={reason} origin="{shown}"')


def lines(caplog):
    return [record.getMessage() for record in caplog.records if record.name == LOGGER]


def decision_lines(caplog):
    return [line for line in lines(caplog) if ' decision=' in line]


def operation_key():
    """An Idempotency-Key as the panel makes one (a second ago, 16 random bytes; never committed)."""
    return f'{int(time.time() * 1000) - 1000}.{secrets.token_hex(16)}'


def headers_of(case, extra=()):
    return httpx.Headers([*ACCEPT.items(), *ORIGIN_CASES[case], *extra])


def normalized(response):
    """answer(), with a child session id replaced (every initialize opens a new one)."""
    status, pairs, body = answer(response)
    return status, [(name, 'SESSION' if name == 'mcp-session-id' else value) for name, value in pairs], body


async def policy_get(runtime):
    async with runtime.admin() as admin:
        return await admin.get('/api/origin-policy', headers=ADMIN)


async def policy_put(runtime, body, *, if_match='current', key='new', csrf=True, profile='default'):
    """PUT {base}/api/origin-policy as the panel sends it (its CSRF value from a fresh bootstrap, If-Match of what it
    read, a new Idempotency-Key). Returns (response, the key)."""
    async with runtime.admin(profile) as admin:
        headers = dict(ADMIN)
        if csrf:
            headers['X-CSRF-Token'] = (await admin.get('/api/bootstrap', headers=ADMIN)).json()['csrf']
        if if_match == 'current':
            headers['If-Match'] = (await admin.get('/api/origin-policy', headers=ADMIN)).headers['etag']
        elif if_match is not None:
            headers['If-Match'] = if_match
        if key == 'new':
            key = operation_key()
        if key is not None:
            headers['Idempotency-Key'] = key
        return await admin.put('/api/origin-policy', headers=headers, json=body), key


async def save(runtime, mode, allowed):
    response, _ = await policy_put(runtime, {'mode': mode, 'allowed_origins': list(allowed)})
    assert response.status_code == 200, response.content
    return response


def watch_tokens(log_scan, data):
    for path in [Path(data) / 'state.json', *sorted((Path(data) / 'profiles').glob('*/state.json'))]:
        value = json.loads(path.read_text())
        log_scan.watch(*(item for item in (value['token'], value['child_token']) if item))


def write_policy(data, raw, mode=0o600):
    path = Path(data) / POLICY
    path.write_bytes(raw)
    path.chmod(mode)
    return path


def setup(tmp_path, product='odoo', extra=False):
    data = tmp_path / 'data'
    configure(data, product)
    if extra:
        create_profile(data, product, B, label='Beta Ops', port=18000)
    return data


def children_of(data, product):
    children = Children()
    children.profile_child(3000, 'default', product, data)
    children.profile_child(18000, 'pbbbb', product, Path(data) / 'profiles' / B)
    return children


def entries(data):
    return sorted(str(path.relative_to(data)) for path in Path(data).rglob('*'))


@pytest.fixture(autouse=True)
def no_test_bind(monkeypatch):
    from mcp_admin_core import profiles
    monkeypatch.setattr(profiles, 'port_occupied', lambda port: None)  # tests/owned_network.py: 18000-18099
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: None)
    monkeypatch.setattr(profiles, 'available_memory_mib', lambda: 4096)


# ---- the origin rule and the log's rendering (the PaaS cases, on HA's line) ----

@pytest.mark.parametrize('value, expected', [
    ('https://claude.ai', ('https', 'claude.ai', 443)),
    ('HTTPS://CLAUDE.AI', ('https', 'claude.ai', 443)),
    ('https://claude.ai:443', ('https', 'claude.ai', 443)),
    ('http://localhost:6274', ('http', 'localhost', 6274)),
    ('http://app.example:80', ('http', 'app.example', 80)),
    ('https://[::1]:8443', ('https', '::1', 8443)),
    ('https://[2001:DB8::1]', ('https', '2001:db8::1', 443)),
])
def test_an_origin_is_normalized_as_paas_does(value, expected):
    assert module().normalize_origin(value) == expected


@pytest.mark.parametrize('value', [
    '', 'null', '*', 'claude.ai', 'ftp://claude.ai', 'https://claude.ai/', 'https://claude.ai.', 'https://user@claude.ai',
    'https://claude.ai?x=1', 'https://claude.ai#x', 'https://claude.ai:0', 'https://claude.ai:65536', 'https://ex ample',
    'https://bad_host.example', 'https://[zz::1]', 'https://' + 'a' * 64 + '.example',
    # origin-2 (PaaS test_normalize_origin_rejects_non_ascii_instead_of_case_folding): no Unicode case folding
    'https://K.example', 'https://claude.aiK', 'https://ınfo.example', 'https://ſhop.example',
    'https://claude.ai:٣٤٥',
])
def test_anything_else_is_no_origin(value):
    with pytest.raises(ValueError):
        module().normalize_origin(value)


def test_an_ipv6_origin_has_one_normal_form_whatever_the_python(tmp_path):
    """HM-27 review S-9: ipaddress's str() writes an IPv4-mapped address as a dotted quad in newer releases
    (::ffff:127.0.0.1 on 3.12.14 and 3.13.2 here; ::ffff:7f00:1 on 3.12.3), so its normal form would follow the
    image's Python, and a saved policy holding one would turn unusable (503) when the Python changes. The add-on writes
    RFC 5952's hex form, as the WHATWG URL serializer that a browser's Origin comes from: the same as str() for every
    other address, on every version."""
    found = module()
    for value in ('http://[::ffff:127.0.0.1]', 'HTTP://[::FFFF:7F00:1]:80', 'http://[0:0:0:0:0:ffff:7f00:1]'):
        assert found.canonical(value) == 'http://[::ffff:7f00:1]', value
    for value, expected in (
            ('1:0:0:2:0:0:0:3', '1:0:0:2::3'), ('1:0:0:2:0:0:3:4', '1::2:0:0:3:4'), ('0:0:0:0:0:0:0:0', '::'),
            ('0:0:0:0:0:0:0:1', '::1'), ('1:0:0:0:0:0:0:0', '1::'), ('1:2:3:4:5:6:7:0', '1:2:3:4:5:6:7:0'),
            ('::ffff:1.2.3.4', '::ffff:102:304'), ('::ffff:0:1.2.3.4', '::ffff:0:102:304'),
            ('64:ff9b::1.2.3.4', '64:ff9b::102:304'), ('::127.0.0.1', '::7f00:1')):
        assert found.canonical(f'https://[{value}]') == f'https://[{expected}]', value
    rng = random.Random(27)  # every other address: what str() writes, which no Python version changed
    for _ in range(3000):
        pieces = [0 if rng.random() < .5 else rng.getrandbits(16) for _ in range(8)]
        address = ipaddress.IPv6Address(sum(piece << 16 * (7 - index) for index, piece in enumerate(pieces)))
        if address.ipv4_mapped is None:
            assert found.canonical(f'https://[{address.exploded}]') == f'https://[{address}]', address.exploded
    policy = found.requested({'mode': 'enforce', 'allowed_origins': ['http://[::ffff:127.0.0.1]']})
    assert policy.allowed == ('http://[::ffff:7f00:1]',)
    assert policy.permits(['http://[::ffff:127.0.0.1]']) and policy.permits(['http://[::ffff:7f00:1]'])
    path = tmp_path / POLICY
    assert policy_state(path, policy.document()) == 'saved'
    assert policy_state(path, b'{"version":1,"mode":"enforce","allowed_origins":["http://[::ffff:127.0.0.1]"]}') == 'unusable'


@pytest.mark.parametrize('origins, reason, shown', [
    (['https://claude.ai/'], 'malformed', 'https://claude.ai(has=path)'),
    (['null'], 'null', 'null'),
    ([''], 'malformed', 'non-url(len=0,classes=none)'),
    (['https://evil.example', 'https://claude.ai'], 'duplicate', 'https://evil.example,https://claude.ai'),
    (['HTTPS://Evil.EXAMPLE:443'], 'not_allowed', 'https://evil.example'),
    (['http://evil.example:8080'], 'not_allowed', 'http://evil.example:8080'),
    (['http://[::1]:8443'], 'not_allowed', 'http://[::1]:8443'),
    (['https://user@claude.ai'], 'malformed', 'https://claude.ai(has=userinfo)'),
])
def test_reason_codes_and_rendered_origins(origins, reason, shown):
    """PaaS test_reason_codes_and_normalized_origins."""
    assert module().classify_denial(origins) == (reason, shown)


def test_the_sanitizer_escapes_everything_outside_printable_ascii():
    """PaaS test_sanitizer_escapes_everything_outside_printable_ascii."""
    sanitize = module().sanitize_origin_text
    assert sanitize('https://ok.example') == 'https://ok.example'
    assert sanitize('a b\t"c"\\\r\n\x7féK\U0001f600') == (
        'a\\x20b\\x09\\x22c\\x22\\x5c\\x0d\\x0a\\x7f\\xe9\\u212a\\U0001f600')
    long = sanitize('\x01' * 1000)
    assert len(long) <= 120 and long.endswith('...') and '\\x01' in long
    assert len(sanitize('x' * 120)) == 120 and not sanitize('x' * 120).endswith('...')
    assert sanitize('x' * 121) == 'x' * 117 + '...'


def test_duplicates_show_at_most_four_values_each_escaped_once():
    """PaaS test_duplicate_shows_at_most_four_values, test_duplicate_values_are_escaped_exactly_once,
    test_duplicate_header_values_also_summarise_non_url_shapes, test_duplicate_header_renders_each_url_shaped_value_without_secrets."""
    classify = module().classify_denial
    reason, shown = classify([f'https://d{i}.example' for i in range(9)])
    assert reason == 'duplicate' and shown.count(',') == 4 and shown.endswith(',...') and len(shown) <= 120
    assert classify(['https://a.example\r\n', 'HTTPS://B.Example']) == (
        'duplicate', 'non-url(len=19,classes=alpha+control+punct,scheme=https),https://b.example')
    assert classify(['https://a.example/x\\y', 'HTTPS://B.Example']) == (
        'duplicate', 'https://a.example(has=path),https://b.example')
    token = 'T' * 43
    reason, shown = classify(['Bearer ' + token, 'https://evil.example'])
    assert reason == 'duplicate' and token not in shown and 'https://evil.example' in shown
    assert classify(['https://us:SECRET123@evil.example/x?k=SECRET123', 'https://claude.ai']) == (
        'duplicate', 'https://evil.example(has=userinfo+path+query),https://claude.ai')


S = 'SECRET123'


@pytest.mark.parametrize('raw, expected', [
    (f'https://us:{S}@evil.example', 'https://evil.example(has=userinfo)'),
    (f'https://{S}@evil.example:8443', 'https://evil.example:8443(has=userinfo)'),
    (f'https://evil.example/x?api_key={S}', 'https://evil.example(has=path+query)'),
    (f'https://evil.example?api_key={S}', 'https://evil.example(has=query)'),
    (f'https://evil.example#access_token={S}', 'https://evil.example(has=fragment)'),
    (f'https://evil.example/p?k={S}#frag{S}', 'https://evil.example(has=path+query+fragment)'),
    (f'https://u:{S}@evil.example:444/p?k={S}#f', 'https://evil.example:444(has=userinfo+path+query+fragment)'),
    (f'HTTP://Us:{S}@EVIL.Example:80/', 'http://evil.example(has=userinfo+path)'),
    (f'https://[::1]:8443/x?k={S}', 'https://[::1]:8443(has=path+query)'),
    (f'https://{S}@[2001:DB8::1]/', 'https://[2001:db8::1](has=userinfo+path)'),
    (f'https://evil.example\\@x.example/?k={S}', 'https://evil.example(has=path+query)'),
    (f'https://evil.example/private_{S}', 'https://evil.example(has=path)'),
    ('https://evil.example/', 'https://evil.example(has=path)'),
])
def test_a_url_shaped_malformed_origin_shows_only_its_origin_and_which_parts_it_had(raw, expected):
    """PaaS test_url_shaped_malformed_origin_logs_only_normalised_origin_and_flags (and the cases of
    test_url_shaped_malformed_values_log_only_scheme_host_port_and_flags)."""
    reason, shown = module().classify_denial([raw])
    assert reason == 'malformed' and shown == expected and S not in shown


@pytest.mark.parametrize('raw', [
    f'https://us:{S}@', f'https://us:{S}@/path', f'https://@evil.example:99999/x?k={S}',
    f'https://bad_host.example/x?k={S}', f'https://evil.example:/x?k={S}', f'https://[zz::1]/x?k={S}',
    f'https://exémple.example/x?k={S}', f'https://us:{S}@evil.example\r\nWARNING forged',
    f'https://evil.example/x?k={S}\x00', f'https://evil.example/x?k={S}\x1b[31m', f'https://evil.example/x?k={S} tail',
])
def test_any_other_malformed_origin_shows_a_summary_only(raw):
    """PaaS test_url_shaped_origin_without_a_parsable_host_falls_back_to_the_non_url_summary and
    test_url_shaped_origin_with_control_characters_gets_the_non_url_summary."""
    reason, shown = module().classify_denial([raw])
    assert reason == 'malformed' and shown.startswith('non-url(len=') and S not in shown and 'forged' not in shown
    assert re.fullmatch(r'[ -~]*', shown) and not re.search(r'[\r\n"\\\s]', shown)


@pytest.mark.parametrize('raw', ['private_' + 'T' * 43, 'Bearer ' + 'T' * 43, 'bearer   ' + 'T' * 43, 'T' * 43,
                                 'x' * 10_000, 'https://evil.example\r\nWARNING forged ' + 'T' * 43,
                                 'あ' * 50 + 'T' * 43])
def test_a_non_url_value_never_shows_verbatim(raw):
    """PaaS test_malformed_non_url_values_never_appear_verbatim_in_the_log, test_malformed_summary_shows_length_and_
    character_classes, test_malformed_summary_keeps_a_recognisable_scheme_prefix_only."""
    reason, shown = module().classify_denial([raw])
    assert reason == 'malformed' and 'T' * 16 not in shown and 'Bearer' not in shown and 'private_' not in shown
    assert re.fullmatch(r'[ -~]*', shown) and len(shown) <= 120 and f'len={len(raw)}' in shown
    assert 'alert' not in module().classify_denial(['javascript:alert(1)'])[1]
    shown = module().classify_denial(['ftp://evil.example'])[1]
    assert shown.startswith('ftp://') or 'scheme=ftp' in shown


def test_an_overlong_host_is_cut_and_shows_nothing_of_it():
    """PaaS test_url_shaped_origin_with_overlong_host_is_truncated_and_leaks_nothing."""
    classify = module().classify_denial
    reason, shown = classify([f"https://{'a' * 63}.{'b' * 63}.{'c' * 63}.{'d' * 60}/x?k={S}"])
    assert reason == 'malformed' and len(shown) <= 120 and shown.endswith('...') and S not in shown
    assert classify([f"https://{'a' * 5000}.example/x?k={S}"])[1].startswith('non-url(len=')
    assert classify([f"https://evil.example/{'x' * 100_000}?k={S}"])[1] == 'https://evil.example(has=path+query)'


# ---- the lines' rate: per profile (PaaS: per service) ----

def test_one_line_per_origin_then_twenty_a_minute_per_profile_then_one_summary(caplog):
    """PaaS test_one_line_per_origin_per_interval_global_cap_then_one_summary, per profile: one line per (decision,
    reason, origin) a minute, at most 20 lines a minute per profile, the lines held back written as one line when the
    next one is."""
    now = [1000.0]
    denials = module().Denials(clock=lambda: now[0])
    for _ in range(50):
        denials.record('default', 'report-only', ['https://repeat.example'])
    assert decision_lines(caplog) == [would_deny('default', 'not_allowed', 'https://repeat.example')]
    for i in range(30):
        denials.record('default', 'report-only', [f'https://distinct{i}.example'])
    assert len(decision_lines(caplog)) == 20
    now[0] += 59.9
    denials.record('default', 'report-only', ['https://repeat.example'])
    assert len(lines(caplog)) == 20
    now[0] += 0.2  # a new window: first the count of the lines held back, then this one
    denials.record('default', 'report-only', ['https://repeat.example'])
    assert lines(caplog)[20:] == [
        'MCP gateway [profile=default]: Origin lines held back suppressed=61 (one line per origin every 60 s, at most '
        '20 lines every 60 s per profile)', would_deny('default', 'not_allowed', 'https://repeat.example')]
    now[0] += 61
    denials.record('default', 'enforce', ['https://repeat.example'])
    assert lines(caplog)[22:] == [deny('default', 'not_allowed', 'https://repeat.example')]  # no summary: none held


def test_a_profiles_flood_never_holds_back_another_profiles_lines(caplog):
    """HA's per-profile rate (the PaaS one is the service's: a flood of one profile there hides the others' lines; R04
    S-10, its HANDOFF :241 info)."""
    now = [5.0]
    denials = module().Denials(clock=lambda: now[0])
    for i in range(200):
        denials.record(B, 'report-only', [f'https://flood{i}.example'])
    denials.record('default', 'report-only', ['https://claude.example'])
    assert decision_lines(caplog)[-1] == would_deny('default', 'not_allowed', 'https://claude.example')
    assert sum(f'[profile={B[:8]}]' in line for line in lines(caplog)) == 20


def test_the_state_stays_bounded_under_a_flood_of_distinct_origins(caplog):
    """PaaS test_state_is_bounded_under_a_flood_of_distinct_origins: per profile, and for the number of profiles."""
    found = module()
    now = [0.0]
    denials = found.Denials(clock=lambda: now[0])
    windows = 0
    for i in range(20_000):
        if i % 1000 == 0:
            now[0] += 61
            windows += 1
        denials.record('default', 'report-only', [f'https://flood-{i}.example'])
        assert denials.size('default') <= 2 * found.LOG_MAX_PER_WINDOW
    assert len(lines(caplog)) <= windows * (found.LOG_MAX_PER_WINDOW + 1)
    for i in range(found.LOG_MAX_PROFILES * 3):
        denials.record(f'{i:024x}', 'report-only', ['https://one.example'])
    assert denials.profiles_held() <= found.LOG_MAX_PROFILES


async def test_the_summary_is_written_when_the_window_ends_without_another_line(caplog):
    """PaaS test_summary_is_flushed_when_the_window_ends_without_new_rejections: a timer on the running loop, at most
    one a window, never twice."""
    denials = module().Denials(interval=0.05, window=0.05)
    denials.record(B, 'report-only', ['https://burst.example'])
    for _ in range(5):
        denials.record(B, 'report-only', ['https://burst.example'])
    assert len(lines(caplog)) == 1
    await asyncio.sleep(0.3)
    assert len(lines(caplog)) == 2 and lines(caplog)[1].startswith(
        f'MCP gateway [profile={B[:8]}]: Origin lines held back suppressed=5 (')
    denials.record(B, 'report-only', ['https://burst.example'])
    assert not any('suppressed=' in line for line in lines(caplog)[2:])


# ---- the request rules (the panel's PUT; 422 origin_policy_invalid) ----

@pytest.mark.parametrize('body', [
    {'mode': 'Enforce', 'allowed_origins': []}, {'mode': ' enforce', 'allowed_origins': []},
    {'mode': 'enforce ', 'allowed_origins': []}, {'mode': 'report_only', 'allowed_origins': []},
    {'mode': 'block', 'allowed_origins': []}, {'mode': '', 'allowed_origins': []},
    {'mode': 'report-only', 'allowed_origins': ['*']}, {'mode': 'report-only', 'allowed_origins': ['null']},
    {'mode': 'report-only', 'allowed_origins': ['https://service.example/path']},
    {'mode': 'report-only', 'allowed_origins': ['https://service.example/']},
    {'mode': 'report-only', 'allowed_origins': ['https://service.example.']},
    {'mode': 'report-only', 'allowed_origins': ['https://user@service.example']},
    {'mode': 'report-only', 'allowed_origins': ['']}, {'mode': 'report-only', 'allowed_origins': [' https://a.example']},
    {'mode': 'report-only', 'allowed_origins': ['https://claude.ai', 'HTTPS://CLAUDE.AI:443']},
    {'mode': 'report-only', 'allowed_origins': [f'https://o{i}.example' for i in range(17)]},
])
def test_what_a_policy_may_not_be(body):
    """PaaS test_misconfigured_allowlist_fails_closed_even_without_origin, test_non_headscale_rejects_trailing_dot_
    allowlist, test_invalid_mode_fails_startup_validation_without_echoing_the_value: the panel's PUT refuses these
    (the file is never written with them)."""
    found = module()
    assert found.request_shape(body)
    with pytest.raises(found.BadRequest) as refused:
        found.requested(body)
    assert (refused.value.status, refused.value.detail) == (422, {'code': 'origin_policy_invalid'})


def test_what_a_policy_may_be():
    found = module()
    policy = found.requested({'mode': 'enforce', 'allowed_origins': [
        'https://claude.ai', 'http://localhost:6274', 'https://[::1]:8443', 'HTTPS://App.Example:443']})
    assert (policy.mode, policy.allowed) == ('enforce', (
        'https://claude.ai', 'http://localhost:6274', 'https://[::1]:8443', 'https://app.example'))
    assert found.requested({'mode': 'report-only', 'allowed_origins': []}).allowed == ()
    assert found.requested({'mode': 'report-only', 'allowed_origins': [f'https://o{i}.example'
                                                                       for i in range(16)]}).mode == 'report-only'
    for wrong in ({'mode': 'enforce'}, {'mode': 'enforce', 'allowed_origins': [], 'extra': 1}, [],
                  {'mode': 1, 'allowed_origins': []}, {'mode': 'enforce', 'allowed_origins': 'https://claude.ai'},
                  {'mode': 'enforce', 'allowed_origins': [1]}, {'label': 'x'}):
        assert not found.request_shape(wrong)  # step 5: a fixed 400, before the role check


# ---- report-only: no answer changes ----

def requests_of(path, session):
    """The requests the matrix sends with each Origin case (one session open): every method the secret path serves
    (POST, GET and DELETE: HM-27 review S-1) and two it refuses before the check (PUT, OPTIONS: 405)."""
    in_session = [('Mcp-Session-Id', session)]
    return (
        ('initialize', 'POST', path, (), initialize_message(5)),
        ('tools/list', 'POST', path, in_session, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}),
        ('ping', 'POST', path, in_session, {'jsonrpc': '2.0', 'id': 4, 'method': 'ping'}),
        ('initialized', 'POST', path, in_session, {'jsonrpc': '2.0', 'method': 'notifications/initialized'}),
        ('discover', 'POST', path, (), {'jsonrpc': '2.0', 'id': 9, 'method': 'server/discover'}),
        ('get without session', 'GET', path, (), None),
        ('query', 'POST', path + '?x=1', in_session, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}),
        ('put', 'PUT', path, (), None),
        ('options', 'OPTIONS', path, (), None),
        ('delete', 'DELETE', path, in_session, None),
    )


async def matrix(runtime, client, path, session, cases):
    seen = {}
    for case in cases:
        for name, method, target, extra, body in requests_of(path, session):
            response = await client.request(method, target, headers=headers_of(case, extra),
                                            **({} if body is None else {'json': body}))
            seen[case, name] = normalized(response)
    return seen


@pytest.mark.parametrize('product', LISTED)
async def test_report_only_answers_every_request_as_without_the_check(tmp_path, log_scan, caplog, product):
    """T-24, DQ-11 (a): the default policy (no file: report-only, https://claude.ai). Every Origin case gets exactly the
    answer of the same request without an Origin (status, every header, body; PaaS test_mode_origin_method_matrix,
    test_allowed_and_absent_origins_are_identical_in_both_modes_at_the_middleware), no CORS header, the child gets the
    same requests (never an Origin), and each case the list does not hold writes one would_deny line naming the
    profile."""
    data = setup(tmp_path, product)
    async with multi_profile_runtime(product, data) as runtime:
        await settle(runtime, 'configured')
        watch_tokens(log_scan, data)
        path = f'/private_{runtime.token("default")}/mcp'
        async with runtime.mcp() as client:
            opened = await client.post(path, headers=ACCEPT, json=initialize_message())
            session = opened.headers['mcp-session-id']
            since = len(runtime.children.by_port[3000].requests)
            seen = await matrix(runtime, client, path, session, ORIGIN_CASES)
            forwarded = runtime.children.by_port[3000].forwarded(since)
        for (case, name), got in seen.items():
            assert got == seen['none', name], (case, name)
            assert not [header for header, _ in got[1] if header.startswith('access-control-')]
        per_case = len(forwarded) // len(ORIGIN_CASES)
        assert forwarded == forwarded[:per_case] * len(ORIGIN_CASES)  # the child got every case's requests alike
        assert seen['none', 'tools/list'][0] == 200 and seen['none', 'put'][0] == 405 and seen['none', 'query'][0] == 400
        assert seen['none', 'delete'][0] == 200
        assert decision_lines(caplog) == [would_deny('default', *NOT_PERMITTED[case]) for case in ORIGIN_CASES
                                          if case in NOT_PERMITTED]
        assert not (data / POLICY).exists() and not (data / RECEIPTS).exists()


async def test_the_default_policy_is_report_only_and_claude_ai(tmp_path, log_scan):
    data = setup(tmp_path)
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        response = await policy_get(runtime)
        assert response.status_code == 200 and re.fullmatch(r'"o1-[0-9a-f]{64}"', response.headers['etag'])
        assert response.json() == {'mode': 'report-only', 'allowed_origins': ['https://claude.ai'],
                                   'origin_policy_state': 'default'}
        assert response.headers['cache-control'] == 'no-store'
    assert not (data / POLICY).exists()


# ---- enforce: only what the list does not hold ----

@pytest.mark.parametrize('product', LISTED)
async def test_enforce_refuses_only_what_the_list_does_not_hold(tmp_path, log_scan, caplog, product):
    """T-24: switched to enforce in the panel, a request whose Origin the list does not hold is 403 {"error":"request
    denied"} (the Bearer path's and Headscale's fixed answer; PaaS 403 ORIGIN_DENIED), never reaches the child and
    writes one deny line; no Origin or exactly one listed is served as before, byte for byte. The method rule still
    comes first (405), the query rule after (400); a DELETE is refused as a GET or a POST (HM-27 review S-1)."""
    data = setup(tmp_path, product)
    async with multi_profile_runtime(product, data) as runtime:
        await settle(runtime, 'configured')
        watch_tokens(log_scan, data)
        path = f'/private_{runtime.token("default")}/mcp'
        async with runtime.mcp() as client:
            opened = await client.post(path, headers=ACCEPT, json=initialize_message())
            session = opened.headers['mcp-session-id']
            before = await matrix(runtime, client, path, session, ['none'])
            await save(runtime, 'enforce', ['https://claude.ai'])
            child = runtime.children.by_port[3000]
            reached = {}
            seen = {}
            for case in ORIGIN_CASES:
                since = len(child.requests)
                seen.update(await matrix(runtime, client, path, session, [case]))
                reached[case] = child.forwarded(since)
        for (case, name), got in seen.items():
            if case in NOT_PERMITTED and name not in ('put', 'options'):
                assert got == DENIED_403, (case, name)
            else:
                assert got == before['none', name], (case, name)
        assert all(reached[case] == [] for case in NOT_PERMITTED)
        assert reached['allowed'] == reached['allowed-otherwise-spelled'] == reached['none'] != []
        assert decision_lines(caplog) == [deny('default', *NOT_PERMITTED[case]) for case in ORIGIN_CASES
                                          if case in NOT_PERMITTED]


@pytest.mark.parametrize('headers', [
    [('Origin', '')], [('Origin', 'null')], [('Origin', 'not-an-origin')], [('Origin', 'https://service.example/')],
    [('Origin', 'https://user@service.example')], [('Origin', 'https://service.example:65536')],
    [('Origin', 'https://service.example.evil')], [('Origin', 'https://service.example'), ('Origin', 'https://service.example')],
    [('Origin', 'https://evil.example'), ('Host', 'evil.example'), ('X-Forwarded-Host', 'evil.example'),
     ('X-Forwarded-Proto', 'https'), ('Forwarded', 'host=evil.example;proto=https')],
    [('Origin', 'https://K.example')],
])
async def test_enforce_refuses_bad_origins_whatever_the_host_or_proxy_headers(tmp_path, log_scan, headers):
    """PaaS test_rejects_bad_origins_even_if_host_or_proxy_headers_are_spoofed, test_kelvin_sign_does_not_match_an_
    ascii_allowlist, test_untrusted_origin_with_valid_token_cannot_initialize."""
    data = setup(tmp_path)
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        await save(runtime, 'enforce', ['https://service.example', 'https://k.example'])
        path = f'/private_{runtime.token("default")}/mcp'
        async with runtime.mcp() as client:
            raw = httpx.Headers([*((name.encode(), value.encode()) for name, value in ACCEPT.items()),
                                 *((name.encode(), value.encode('utf-8')) for name, value in headers)])
            assert answer(await client.post(path, headers=raw, json=initialize_message())) == DENIED_403
            served = await client.post(path, headers={**ACCEPT, 'Origin': 'https://service.example'},
                                       json=initialize_message())
            assert served.status_code == 200 and 'access-control-allow-origin' not in served.headers


async def test_every_profile_takes_the_one_policy_and_its_lines_name_the_profile(tmp_path, log_scan, caplog):
    """FM-73 (service level, every profile), PaaS test_origin_boundary_with_real_product_and_two_profiles: the default
    profile and B, each through its own token; the lines name each profile by its id's first 8 characters; a save
    from B's panel view changes the add-on's one policy (the route never reads X-MCP-Profile)."""
    data = setup(tmp_path, extra=True)
    async with multi_profile_runtime('odoo', data, children=children_of(data, 'odoo')) as runtime:
        await settle(runtime, 'configured')
        watch_tokens(log_scan, data)
        log_scan.watch('Beta Ops', kind='name')
        async with runtime.mcp() as client:
            for profile in ('default', B):
                path = f'/private_{runtime.token(profile)}/mcp'
                response = await client.post(path, headers={**ACCEPT, 'Origin': 'https://evil.example'},
                                             json=initialize_message())
                assert response.status_code == 200 and response.json()['result']['serverInfo']
            response, _ = await policy_put(runtime, {'mode': 'enforce', 'allowed_origins': ['https://claude.ai']},
                                           profile=B)
            assert response.status_code == 200 and 'profile' not in response.json()
            for profile in ('default', B):
                path = f'/private_{runtime.token(profile)}/mcp'
                assert answer(await client.post(path, headers={**ACCEPT, 'Origin': 'https://evil.example'},
                                                json=initialize_message())) == DENIED_403
                assert (await client.post(path, headers={**ACCEPT, 'Origin': 'https://claude.ai'},
                                          json=initialize_message())).status_code == 200
        assert decision_lines(caplog) == [
            would_deny('default', 'not_allowed', 'https://evil.example'),
            would_deny(B[:8], 'not_allowed', 'https://evil.example'),
            deny('default', 'not_allowed', 'https://evil.example'), deny(B[:8], 'not_allowed', 'https://evil.example')]


# ---- what the check never touches ----

async def test_the_bearer_path_still_refuses_any_origin_and_writes_no_line(tmp_path, log_scan, caplog):
    """DQ-11: the Bearer path is not the policy's (contract 2.1, section 9 #10; the second question waits for S14):
    an Origin there is 403 in both modes, an allowed one too, with no line; a wrong token still 401 first."""
    data = setup(tmp_path)
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        bearer = {'Authorization': f'Bearer {runtime.token("default")}'}
        async with runtime.mcp() as client:
            for mode in ('report-only', 'enforce'):
                if mode == 'enforce':
                    await save(runtime, 'enforce', ['https://claude.ai'])
                for origin in ('https://claude.ai', 'https://evil.example', 'null'):
                    assert answer(await client.post('/mcp', headers={**ACCEPT, **bearer, 'Origin': origin},
                                                    json=initialize_message())) == DENIED_403
                assert answer(await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer ' + 'R' * 43,
                                                                 'Origin': 'https://claude.ai'},
                                                json=initialize_message())) == BEARER_REQUIRED
                assert (await client.post('/mcp', headers={**ACCEPT, **bearer}, json=initialize_message())).status_code == 200
        assert decision_lines(caplog) == []


async def test_a_wrong_token_never_learns_the_policy(tmp_path, log_scan, caplog):
    """The check comes after the token (FM-73's HA column: an unauthenticated client cannot write a line, PaaS K-09;
    PaaS test_trusted_origin_still_requires_token_and_exposes_session_header): a wrong or revoked secret is today's
    404 with any Origin, in both modes, and writes nothing."""
    data = setup(tmp_path)
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        async with runtime.mcp() as client:
            for mode in ('report-only', 'enforce'):
                if mode == 'enforce':
                    await save(runtime, 'enforce', [])
                for case in ORIGIN_CASES:
                    response = await client.post('/private_' + 'R' * 43 + '/mcp', headers=headers_of(case),
                                                 json=initialize_message())
                    assert answer(response) == NOT_FOUND, (mode, case)
        assert decision_lines(caplog) == []


async def test_no_cors_header_in_either_mode(tmp_path, log_scan):
    """FM-74: no CORS, ever (PaaS report-only reflects any origin with credentials, its pre-#136 CORS; HA had none and
    adding it would widen access). A preflight is today's 405 after the token check (PaaS test_preflight_is_limited_to_
    explicitly_trusted_origins, test_root_path_preflight_and_native_clients_use_same_policy: HA serves no preflight);
    an allowed origin gets no Access-Control-* or Vary header either (PaaS test_vary_lists_origin_at_most_once...)."""
    data = setup(tmp_path)
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        path = f'/private_{runtime.token("default")}/mcp'
        preflight = {'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'content-type'}
        async with runtime.mcp() as client:
            for mode in ('report-only', 'enforce'):
                if mode == 'enforce':
                    await save(runtime, 'enforce', ['https://claude.ai'])
                for origin in ('https://claude.ai', 'https://evil.example'):
                    options = await client.options(path, headers={**preflight, 'Origin': origin})
                    assert answer(options) == (405, [('allow', 'GET, POST, DELETE'), ('content-length', '0')], b'')
                    response = await client.post(path, headers={**ACCEPT, 'Origin': origin}, json=initialize_message())
                    assert not [name for name in response.headers if name.lower().startswith('access-control-')
                                or name.lower() == 'vary']


async def test_readiness_and_the_management_api_ignore_the_policy(tmp_path, log_scan, caplog):
    """PaaS test_non_mcp_routes_ignore_the_mode, test_allowed_absent_and_non_mcp_origins_produce_no_line: only the
    secret path; 8099 keeps its own cross-site rules."""
    data = setup(tmp_path)
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        await save(runtime, 'enforce', [])
        async with runtime.mcp() as client:
            assert answer(await client.get('/health/ready', headers={'Origin': 'https://evil.example'})) == (
                200, [('content-length', '14'), ('content-type', 'application/json')], b'{"ready":true}')
        async with runtime.admin() as admin:
            assert (await admin.get('/api/bootstrap', headers={**ADMIN, 'Origin': 'https://evil.example'})).status_code == 200
        assert decision_lines(caplog) == []


async def test_a_line_that_cannot_be_written_never_changes_the_answer(tmp_path, log_scan, caplog, monkeypatch):
    """PaaS test_logging_failure_never_blocks_a_report_only_request, test_logging_failure_never_changes_the_response."""
    data = setup(tmp_path)
    found = module()

    def broken(*args, **kwargs):
        raise RuntimeError('synthetic logging failure with https://evil.example')
    monkeypatch.setattr(found, 'classify_denial', broken)
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        path = f'/private_{runtime.token("default")}/mcp'
        async with runtime.mcp() as client:
            served = await client.post(path, headers={**ACCEPT, 'Origin': 'https://evil.example'}, json=initialize_message())
            assert served.status_code == 200
            await save(runtime, 'enforce', [])
            assert answer(await client.post(path, headers={**ACCEPT, 'Origin': 'https://evil.example'},
                                            json=initialize_message())) == DENIED_403
    assert lines(caplog) == []


def raw_scope(path, origins):
    return {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': 'POST', 'scheme': 'http',
            'path': path, 'raw_path': path.encode(), 'query_string': b'', 'root_path': '', 'client': ('127.0.0.1', 1),
            'server': ('mcp', 80), 'headers': [(b'host', b'mcp'), (b'content-type', b'application/json'),
                                               (b'accept', b'application/json, text/event-stream'),
                                               *((b'origin', value) for value in origins)]}


async def raw_post(app, path, origins):
    """One ASGI request with raw Origin bytes (an HTTP client refuses CR, LF and the like): (status, body)."""
    sent, body = [], json.dumps(initialize_message()).encode()

    async def receive():
        nonlocal body
        if body is None:
            await asyncio.Event().wait()
        part, body = body, None
        return {'type': 'http.request', 'body': part, 'more_body': False}

    async def emit(message):
        sent.append(message)
    await app(raw_scope(path, origins), receive, emit)
    start = next(message for message in sent if message['type'] == 'http.response.start')
    return start['status'], b''.join(message.get('body', b'') for message in sent if message['type'] == 'http.response.body')


@pytest.mark.parametrize('raw', [
    b'https://evil.example\r\nWARNING forged line reason=not_allowed', b'\x1b[31mhttps://evil.example\x1b[0m',
    b'https://evil.example" origin="https://claude.ai', b'https://evil.example\\x0a', b'https://\xff\xfeevil.example',
    b'https://evil.example/private_' + b'Q' * 43 + b'?token=query-token-value', b'https://' + b'a' * 10_000,
    b'\x00' * 300, b'Bearer ' + b'Q' * 43,
])
async def test_a_hostile_origin_value_cannot_inject_or_leak_into_the_line(tmp_path, log_scan, caplog, raw):
    """PaaS test_malicious_origin_values_are_escaped_truncated_and_cannot_inject, test_end_to_end_log_line_has_no_raw_
    malformed_text, test_url_credentials_in_a_malformed_origin_are_masked_without_the_global_record_factory: through
    the real dispatcher, both modes; one line each, one physical line, its fields intact, the origin shown in printable
    ASCII within 120 characters, nothing of a token, a path or a query."""
    data = setup(tmp_path)
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        watch_tokens(log_scan, data)
        path = f'/private_{runtime.token("default")}/mcp'
        assert (await raw_post(runtime.mcp_app, path, [raw]))[0] == 200
        await save(runtime, 'enforce', ['https://claude.ai'])
        assert await raw_post(runtime.mcp_app, path, [raw]) == (403, b'{"error":"request denied"}')
    found = decision_lines(caplog)
    assert len(found) == 2
    for line, mode, decision, effect in zip(found, ('report-only', 'enforce'), ('would_deny', 'deny'),
                                            ('report-only: served as usual', 'enforce: refused, 403')):
        assert not re.search(r'[\x00-\x1f\x7f-\x9f]', line), line
        match = re.fullmatch(rf'MCP gateway \[profile=default\]: an Origin the secret path does not allow \({re.escape(effect)}\) '
                             rf'decision={decision} mode={mode} reason=(\w+) origin="([^"]*)"', line)
        assert match, line
        assert len(match.group(2)) <= 120 and all('!' <= char <= '~' for char in match.group(2))
        assert 'Q' * 16 not in line and 'query-token-value' not in line and 'private_' not in line and 'forged' not in line


# ---- the policy file ----

async def test_the_policy_is_saved_beside_the_index_never_in_the_default_state(tmp_path, log_scan):
    """Plan 12.3 HM-27: the service-level file in /data/mcp (0600, exactly this JSON), its receipts beside it; the
    default profile's state.json not touched; nothing written before the first save (plan 7.2 point 8: switched on,
    only the two sentinel files are new)."""
    data = setup(tmp_path)
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        state = (data / 'state.json').read_bytes()
        before = entries(data)
        assert POLICY not in before and RECEIPTS not in before
        response = await save(runtime, 'enforce', ['HTTPS://Claude.AI:443', 'http://localhost:6274'])
        assert response.json()['allowed_origins'] == ['https://claude.ai', 'http://localhost:6274']
        assert (data / 'state.json').read_bytes() == state
        assert sorted(set(entries(data)) - set(before)) == [RECEIPTS, POLICY]
        info = (data / POLICY).lstat()
        assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
        assert (data / POLICY).read_bytes() == (b'{"version":1,"mode":"enforce","allowed_origins":'
                                                b'["https://claude.ai","http://localhost:6274"]}')
        assert stat.S_IMODE((data / RECEIPTS).lstat().st_mode) == 0o600
    async with multi_profile_runtime('odoo', data) as runtime:  # read again at the next start
        await settle(runtime, 'configured')
        assert (await policy_get(runtime)).json() == {
            'mode': 'enforce', 'allowed_origins': ['https://claude.ai', 'http://localhost:6274'],
            'origin_policy_state': 'saved'}


@pytest.mark.parametrize('name, raw, mode', [
    ('not JSON', b'{', 0o600),
    ('a mode in another case', b'{"version":1,"mode":"Enforce","allowed_origins":[]}', 0o600),
    ('an unknown key', b'{"version":1,"mode":"enforce","allowed_origins":[],"extra":1}', 0o600),
    ('a newer version', b'{"version":2,"mode":"enforce","allowed_origins":[]}', 0o600),
    ('an origin not in its normal form', b'{"version":1,"mode":"enforce","allowed_origins":["HTTPS://CLAUDE.AI"]}', 0o600),
    ('a wildcard', b'{"version":1,"mode":"report-only","allowed_origins":["*"]}', 0o600),
    ('another mode bit set', b'{"version":1,"mode":"report-only","allowed_origins":[]}', 0o644),
    # HM-27 review S-2: the file's own rules, each with the request's rule as well
    ('a repeated origin', b'{"version":1,"mode":"report-only","allowed_origins":["https://claude.ai","https://claude.ai"]}',
     0o600),
    ('a list in the list', b'{"version":1,"mode":"report-only","allowed_origins":[[]]}', 0o600),
    ('an object in the list', b'{"version":1,"mode":"report-only","allowed_origins":[{}]}', 0o600),
    ('17 origins', ('{"version":1,"mode":"report-only","allowed_origins":['
                    + ','.join(f'"https://o{i}.example"' for i in range(17)) + ']}').encode(), 0o600),
    ('16 KiB and one byte', b'{"version":1,"mode":"report-only","allowed_origins":[]}'.ljust(16385), 0o600),
])
async def test_an_unusable_policy_file_refuses_the_secret_path_until_the_panel_saves_one(tmp_path, log_scan, caplog,
                                                                                         name, raw, mode):
    """PaaS test_invalid_mode_at_runtime_fails_closed_like_an_invalid_allowlist, test_misconfigured_allowlist_fails_
    closed_even_without_origin (a bad value at runtime: the MCP path 503, with or without an Origin; at startup PaaS
    refuses to start, which on HA would leave nobody a way to repair it): every secret-path request whose token is
    checked is 503 {"error":"state unavailable"}; a wrong token is still 404, the Bearer path and readiness as before;
    one WARNING, without the file's content; the panel shows it unusable and a save with its ETag replaces it."""
    data = setup(tmp_path)
    write_policy(data, raw, mode)
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        path = f'/private_{runtime.token("default")}/mcp'
        bearer = {**ACCEPT, 'Authorization': f'Bearer {runtime.token("default")}'}
        async with runtime.mcp() as client:
            for case in ('none', 'allowed', 'not-allowed'):
                assert answer(await client.post(path, headers=headers_of(case), json=initialize_message())) == UNAVAILABLE
            assert answer(await client.post('/private_' + 'R' * 43 + '/mcp', headers=ACCEPT,
                                            json=initialize_message())) == NOT_FOUND
            assert (await client.post('/mcp', headers=bearer, json=initialize_message())).status_code == 200
            assert (await client.get('/health/ready')).status_code == 200
            read = await policy_get(runtime)
            assert read.status_code == 200 and read.json() == {'mode': None, 'allowed_origins': None,
                                                               'origin_policy_state': 'unusable'}
            stale, _ = await policy_put(runtime, {'mode': 'report-only', 'allowed_origins': []},
                                        if_match='"o1-' + '0' * 64 + '"')
            assert stale.status_code == 409 and stale.headers['etag'] == read.headers['etag']
            assert (data / POLICY).read_bytes() == raw
            repaired = await save(runtime, 'report-only', ['https://claude.ai'])
            assert repaired.json()['origin_policy_state'] == 'saved'
            assert (await client.post(path, headers=headers_of('not-allowed'), json=initialize_message())).status_code == 200
    warnings = [line for line in lines(caplog) if 'cannot be used' in line]
    assert warnings == ["multi-profile: the secret path's Origin policy (origin-policy.json) cannot be used; MCP "
                        "requests on secret paths are refused (503) until it is saved again in the panel"]
    assert not any(part in line for line in lines(caplog) for part in ('Enforce', 'extra', '"version"'))


async def test_a_policy_file_changed_behind_the_add_ons_back_is_read_again(tmp_path, log_scan, caplog):
    """Read at every secret-path request whose file changed (its lstat signature, as every state of HA: plan 8.8 #46):
    a valid replacement applies at once, an unusable one refuses (503) until it is valid again; a link is never
    followed."""
    data = setup(tmp_path)
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        path = f'/private_{runtime.token("default")}/mcp'
        async with runtime.mcp() as client:
            async def evil():
                return await client.post(path, headers={**ACCEPT, 'Origin': 'https://evil.example'},
                                         json=initialize_message())
            assert (await evil()).status_code == 200
            write_policy(data, b'{"version":1,"mode":"enforce","allowed_origins":["https://claude.ai"]}')
            assert answer(await evil()) == DENIED_403
            write_policy(data, b'not json')
            assert answer(await evil()) == UNAVAILABLE
            (data / POLICY).unlink()
            target = data / 'elsewhere.json'
            target.write_bytes(b'{"version":1,"mode":"report-only","allowed_origins":["https://evil.example"]}')
            target.chmod(0o600)
            (data / POLICY).symlink_to(target)
            assert answer(await evil()) == UNAVAILABLE
            (data / POLICY).unlink()
            assert (await evil()).status_code == 200  # no file: the default again
    assert len([line for line in lines(caplog) if 'cannot be used' in line]) == 2


def policy_state(path, raw):
    """The state PolicyFile reads of path written with raw (0600, this uid)."""
    if path.exists():
        path.unlink()
    path.write_bytes(raw)
    path.chmod(0o600)
    return module().PolicyFile(path).read().state


def test_the_policy_files_bounds_are_its_own(tmp_path):
    """HM-27 review S-2: 16 KiB (a valid policy padded with spaces) and 16 origins are used; one byte or one origin more
    is unusable (contract 2.6, section 9 #128: the numbers are pinned here, not read from the module)."""
    path = tmp_path / POLICY
    document = b'{"version":1,"mode":"report-only","allowed_origins":[]}'
    assert policy_state(path, document.ljust(16384)) == 'saved'
    assert policy_state(path, document.ljust(16385)) == 'unusable'
    origins = [f'https://o{i}.example' for i in range(17)]

    def listing(count):
        return json.dumps({'version': 1, 'mode': 'enforce', 'allowed_origins': origins[:count]},
                          separators=(',', ':')).encode()
    assert policy_state(path, listing(16)) == 'saved'
    assert policy_state(path, listing(17)) == 'unusable'


async def test_a_second_hard_link_is_unusable_and_a_save_replaces_only_this_name(tmp_path, log_scan):
    """PolicyFile._load (HM-27 review S-2): a policy file with a second hard link (valid, 0600, this uid) is unusable,
    the secret path 503; a panel save replaces this name only (rename), the other name keeps its bytes."""
    data = setup(tmp_path)
    other = data / 'elsewhere.json'
    raw = b'{"version":1,"mode":"report-only","allowed_origins":["https://claude.ai"]}'
    other.write_bytes(raw)
    other.chmod(0o600)
    os.link(other, data / POLICY)
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        path = f'/private_{runtime.token("default")}/mcp'
        async with runtime.mcp() as client:
            assert answer(await client.post(path, headers=headers_of('allowed'), json=initialize_message())) == UNAVAILABLE
            assert (await policy_get(runtime)).json()['origin_policy_state'] == 'unusable'
            await save(runtime, 'enforce', ['https://claude.ai'])
            assert (await client.post(path, headers=headers_of('allowed'), json=initialize_message())).status_code == 200
    info = (data / POLICY).lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_ino != other.lstat().st_ino
    assert other.read_bytes() == raw and other.lstat().st_nlink == 1


def test_a_fifo_is_unusable_and_never_waited_for(tmp_path):
    """PolicyFile._load (HM-27 review S-2): a FIFO in the file's place is unusable at once (O_NONBLOCK: reading it
    never waits for a writer, which would hold the event loop). Read in a thread here: if it waits, a writer is opened
    so that the thread ends, and the test fails instead of hanging."""
    found = module()
    path = tmp_path / POLICY
    os.mkfifo(path, 0o600)
    states = []
    reader = threading.Thread(target=lambda: states.append(found.PolicyFile(path).read().state), daemon=True)
    reader.start()
    reader.join(5)
    if reader.is_alive():
        os.close(os.open(path, os.O_WRONLY | os.O_NONBLOCK))
        reader.join(5)
        pytest.fail('the policy file was read waiting for a writer (a FIFO)')
    assert states == ['unusable']


def test_a_policy_file_another_uid_owns_is_unusable(tmp_path, monkeypatch):
    """PolicyFile._load (HM-27 review S-2): the file must be this uid's. The add-on's uid is made another one here
    (os.geteuid, as the module calls it), so that this runs unprivileged and in the CI alike: the same file, 0600 and
    valid, is used as its own and unusable as another uid's."""
    found = module()
    path = tmp_path / POLICY
    assert policy_state(path, b'{"version":1,"mode":"report-only","allowed_origins":[]}') == 'saved'
    owner = path.lstat().st_uid
    monkeypatch.setattr(found.os, 'geteuid', lambda: owner + 1)
    assert found.PolicyFile(path).read().state == 'unusable'


async def test_a_directory_in_the_policy_files_place_cannot_be_saved_over(tmp_path, log_scan):
    """Threat model section 3 (HM-27 review S-2): a directory where the file belongs is unusable (the secret path 503,
    with or without an Origin) and a panel save cannot replace it (rename onto a directory): 409
    operation_outcome_unknown, the same key again the same 409, no temporary file left; only a backup restore repairs
    it, and the Bearer path is served as before meanwhile."""
    data = setup(tmp_path)
    (data / POLICY).mkdir(mode=0o700)
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        path = f'/private_{runtime.token("default")}/mcp'
        bearer = {**ACCEPT, 'Authorization': f'Bearer {runtime.token("default")}'}
        async with runtime.mcp() as client:
            for case in ('none', 'allowed'):
                assert answer(await client.post(path, headers=headers_of(case), json=initialize_message())) == UNAVAILABLE
            assert (await policy_get(runtime)).json()['origin_policy_state'] == 'unusable'
            body = {'mode': 'report-only', 'allowed_origins': []}
            response, key = await policy_put(runtime, body)
            assert (response.status_code, response.json()['detail']['code']) == (409, 'operation_outcome_unknown')
            again, _ = await policy_put(runtime, body, key=key)
            assert (again.status_code, again.json()['detail']['code']) == (409, 'operation_outcome_unknown')
            assert (data / POLICY).is_dir() and [name for name in os.listdir(data) if 'origin-policy.json-' in name] == []
            assert answer(await client.post(path, headers=ACCEPT, json=initialize_message())) == UNAVAILABLE
            assert (await client.post('/mcp', headers=bearer, json=initialize_message())).status_code == 200


# ---- the panel's route: the shared pipeline, If-Match, Idempotency-Key, receipts ----

def test_the_route_is_a_global_path_of_the_shared_pipelines_table():
    """Contract 3.1, 3.2: GET and PUT {base}/api/origin-policy are global paths (X-MCP-Profile never read) of the 8099
    dispatcher's table, so tests/test_admin_pipeline_matrix.py refuses every caller who is not an administrator there
    with the same bytes as anywhere else, and their handlers are ProfileAdmin's (the second role check, the locks)."""
    from mcp_admin_core import profile_admin, profile_router
    route, segments = profile_router.global_route('origin-policy')  # HM-13c: (route, {placeholder: segment})
    assert route is not None and segments == {} and profile_router.is_global('origin-policy')
    assert {method: takes_json for method, (_, takes_json) in route.methods.items()} == {'GET': False, 'PUT': True}
    for handler, _ in route.methods.values():
        assert callable(getattr(profile_admin.ProfileAdmin, handler))
    assert route.allows() == ('GET', 'PUT')
    assert not profile_router.is_global('origin-policy/x') and profile_router.global_route('origin-policy/x') == (None, {})


async def test_the_route_reads_and_saves_through_the_shared_pipeline(tmp_path, log_scan):
    """Plan 12.3 HM-27 (If-Match, receipts; the shared pipeline), contract 3.1, 3.5, 4.1: the order of HM-10's
    creation (If-Match present, Idempotency-Key, a replay before the ETag, the ETag, the request's rules, the receipt,
    the file); every answer without a token, an echo or server text."""
    data = setup(tmp_path)
    body = {'mode': 'enforce', 'allowed_origins': ['https://claude.ai', 'https://app.example']}
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        current = (await policy_get(runtime)).headers['etag']
        response, _ = await policy_put(runtime, body, csrf=False)
        assert answer(response)[0] == 403 and response.content == b'{"error":"request denied"}'
        response, _ = await policy_put(runtime, body, if_match=None)
        assert (response.status_code, response.json()) == (428, {'error': 'request denied',
                                                                 'detail': {'code': 'config_revision_required'}})
        response, _ = await policy_put(runtime, body, key=None)
        assert (response.status_code, response.json()) == (428, {'error': 'request denied',
                                                                 'detail': {'code': 'operation_id_required'}})
        for stale in ('"o1-' + '0' * 64 + '"', '"p1-' + '0' * 64 + '"', 'o1-' + '0' * 64):
            response, _ = await policy_put(runtime, body, if_match=stale)
            assert (response.status_code, response.json(), response.headers['etag']) == (
                409, {'detail': {'code': 'config_conflict'}}, current)
        async with runtime.admin() as admin:
            csrf = (await admin.get('/api/bootstrap', headers=ADMIN)).json()['csrf']
            for wrong in ({'mode': 'enforce'}, {'label': 'x'}, {'mode': 'enforce', 'allowed_origins': 'x'}):
                refused = await admin.put('/api/origin-policy', json=wrong, headers={
                    **ADMIN, 'X-CSRF-Token': csrf, 'If-Match': current, 'Idempotency-Key': operation_key()})
                assert (refused.status_code, refused.content) == (400, b'{"error":"request denied"}')
            refused = await admin.put('/api/origin-policy', content=json.dumps(body), headers={
                **ADMIN, 'X-CSRF-Token': csrf, 'If-Match': current, 'Idempotency-Key': operation_key(),
                'Content-Type': 'text/plain'})
            assert refused.status_code == 415
        response, _ = await policy_put(runtime, {'mode': 'enforce', 'allowed_origins': ['*']})
        assert (response.status_code, response.json()) == (422, {'error': 'request denied',
                                                                 'detail': {'code': 'origin_policy_invalid'}})
        assert not (data / POLICY).exists()
        saved, key = await policy_put(runtime, body)
        assert saved.status_code == 200 and saved.headers['etag'] != current
        assert saved.json() == {'mode': 'enforce', 'allowed_origins': ['https://claude.ai', 'https://app.example'],
                                'origin_policy_state': 'saved',
                                'operation': {'id': key, 'kind': 'origin.policy', 'state': 'completed', 'replayed': False}}
        assert (await policy_get(runtime)).headers['etag'] == saved.headers['etag']
        replay, _ = await policy_put(runtime, body, if_match=current, key=key)  # a stale If-Match: the replay first
        assert replay.status_code == 200 and replay.json()['operation'] == {
            'id': key, 'kind': 'origin.policy', 'state': 'completed', 'replayed': True}
        assert replay.headers['etag'] == saved.headers['etag']
        other, _ = await policy_put(runtime, {'mode': 'report-only', 'allowed_origins': []}, key=key)
        assert (other.status_code, other.json()) == (409, {'error': 'request denied',
                                                           'detail': {'code': 'operation_id_conflict'}})
        for response in (saved, replay, other):
            assert 'profile' not in response.text and runtime.token('default') not in response.text


async def test_a_save_answers_in_the_pipelines_order(tmp_path, log_scan):
    """Contract 3.5, 4.1 (HM-27 review S-3): the If-Match is looked at before the Idempotency-Key, the ETag before the
    request's rules. A malformed If-Match without a key is 409 config_conflict (not 428 operation_id_required); a request
    the rules refuse with a stale If-Match is 409 config_conflict (not 422 origin_policy_invalid). Nothing is written."""
    data = setup(tmp_path)
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        current = (await policy_get(runtime)).headers['etag']
        malformed, _ = await policy_put(runtime, {'mode': 'enforce', 'allowed_origins': []}, if_match='o1-' + '0' * 64,
                                        key=None)
        stale, _ = await policy_put(runtime, {'mode': 'enforce', 'allowed_origins': ['*']},
                                    if_match='"o1-' + '0' * 64 + '"')
        for response in (malformed, stale):
            assert (response.status_code, response.json(), response.headers['etag']) == (
                409, {'detail': {'code': 'config_conflict'}}, current)
        assert not (data / POLICY).exists() and not (data / RECEIPTS).exists()


async def test_the_etag_names_the_policy_not_the_file(tmp_path, log_scan):
    """The ETag "o1-<64 hex>" is an HMAC with a key of this process of the policy (HM-10's index ETag rule): saving the
    same policy again keeps it (the default included), another policy changes it, a restart changes every ETag."""
    data = setup(tmp_path)
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        default = (await policy_get(runtime)).headers['etag']
        assert (await save(runtime, 'report-only', ['https://claude.ai'])).headers['etag'] == default
        other = (await save(runtime, 'enforce', ['https://claude.ai'])).headers['etag']
        assert other != default
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        assert (await policy_get(runtime)).headers['etag'] not in (default, other)


async def test_a_save_that_cannot_be_written_leaves_its_receipt_unknown(tmp_path, log_scan, monkeypatch):
    """HM-10's rule for a failure after the receipt began: 409 operation_outcome_unknown, the same key again is the
    same 409, never a second write; the policy in force is what is on disk."""
    data = setup(tmp_path)
    found = module()
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        real = os.replace

        def refuse(source, target, *args, **kwargs):
            if Path(target).name == POLICY:
                raise OSError('synthetic: the policy file cannot be replaced')
            return real(source, target, *args, **kwargs)
        monkeypatch.setattr(found.os, 'replace', refuse)
        body = {'mode': 'enforce', 'allowed_origins': []}
        response, key = await policy_put(runtime, body)
        assert (response.status_code, response.json()['detail']['code']) == (409, 'operation_outcome_unknown')
        again, _ = await policy_put(runtime, body, key=key)
        assert (again.status_code, again.json()['detail']['code']) == (409, 'operation_outcome_unknown')
        monkeypatch.setattr(found.os, 'replace', real)
        assert not (data / POLICY).exists() and [name for name in os.listdir(data) if 'origin-policy.json-' in name] == []
        assert (await policy_get(runtime)).json()['origin_policy_state'] == 'default'


async def test_a_save_never_replaces_a_file_changed_after_it_was_read(tmp_path, log_scan, monkeypatch):
    """PolicyFile.write replaces the file only while it is still the one the save read (its lstat signature): a file
    another writer put there in between (the same uid, DQ-37) is kept and is the policy in force; the save is HM-10's
    409 operation_outcome_unknown (the same key again the same 409, never a write), and a save of what the panel
    reads again replaces it."""
    data = setup(tmp_path)
    found = module()
    outside = b'{"version":1,"mode":"enforce","allowed_origins":["https://outside.example"]}'
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        real = found.PolicyFile.write

        def meanwhile(self, policy, *, expected):
            write_policy(data, outside)  # another writer, after the save read the file and before it writes it
            return real(self, policy, expected=expected)
        monkeypatch.setattr(found.PolicyFile, 'write', meanwhile)
        body = {'mode': 'report-only', 'allowed_origins': []}
        response, key = await policy_put(runtime, body)
        assert (response.status_code, response.json()['detail']['code']) == (409, 'operation_outcome_unknown')
        monkeypatch.setattr(found.PolicyFile, 'write', real)
        again, _ = await policy_put(runtime, body, key=key)
        assert (again.status_code, again.json()['detail']['code']) == (409, 'operation_outcome_unknown')
        assert (data / POLICY).read_bytes() == outside
        assert [name for name in os.listdir(data) if 'origin-policy.json-' in name] == []
        assert (await policy_get(runtime)).json() == {
            'mode': 'enforce', 'allowed_origins': ['https://outside.example'], 'origin_policy_state': 'saved'}
        await save(runtime, 'report-only', [])
        assert (data / POLICY).read_bytes() == b'{"version":1,"mode":"report-only","allowed_origins":[]}'


# ---- after a restore (HM-13b's boot guard; this slice merged after HM-13b and HM-13c) ----

def test_the_layout_names_the_policy_and_its_receipts():
    """Contract 2.6, 8: the policy and its receipts in /data/mcp under the layout's names (profiles.py: written there
    and nowhere else, so that the boot guard, restore_lock, handles the receipts by the same name the policy writes
    them under)."""
    from mcp_admin_core import origin_policy
    root = Path('/data/mcp')
    assert profiles.ORIGIN_POLICY_NAME == origin_policy.POLICY_NAME == POLICY
    assert profiles.ORIGIN_POLICY_OPERATIONS_NAME == operations.journal_path(root / POLICY).name == RECEIPTS
    assert profiles.Layout(root).origin_policy == root / POLICY
    policy = origin_policy.OriginPolicy(root)  # nothing is read before it is asked
    assert (policy.file.path, policy.journal.path) == (root / POLICY, root / RECEIPTS)


def restore_into(data, backup):
    """Supervisor's restore of backup into data and the entrypoint's marker (as tests/restore_guard_disk.py's
    Disk.restore: every entry a new file, a ctime of now)."""
    after_tick(Path(data).parent, max(newest_ctime(data), newest_ctime(backup)))
    supervisor_restore(backup, data)
    os.close(os.open(Path(data) / profiles.RESTORE_MARKER_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600))


SAVED_BEFORE = {'mode': 'enforce', 'allowed_origins': ['https://claude.ai']}  # before the backup
SAVED_AFTER = {'mode': 'report-only', 'allowed_origins': []}  # after it: lost with the restore
RESTORED_410 = (410, {'error': 'request denied', 'detail': {'code': 'operation_restored'}})


@pytest.mark.parametrize('policy', ['saved', 'absent', 'unusable', 'a directory'])
async def test_after_a_restore_the_backups_policy_applies_and_no_earlier_save_is_taken_again(tmp_path, log_scan,
                                                                                           policy):
    """With HM-13b's boot guard (contract 1.3, 2.6, 3.5; I9): a restore brings the policy back as the backup had it and
    the next start serves exactly that (the guard never reads or changes it): saved (its mode and list in force on the
    secret path), absent (the default: report-only and https://claude.ai), unusable (every secret-path request 503
    until the panel saves one; a directory there cannot be replaced: 409 operation_outcome_unknown, and only another
    backup repairs it). Every save made before the restore, the one after the backup that the restore lost included,
    answers 410 operation_restored when the panel sends it again, whatever its If-Match (the guard archived the
    receipts beside the policy and gave it a new journal, also where the backup had none); a new save is a new
    operation."""
    data = setup(tmp_path)
    watch_tokens(log_scan, data)
    before = None
    async with multi_profile_runtime('odoo', data) as runtime:  # the first switched-on start: the sentinel
        await settle(runtime, 'configured')
        if policy != 'absent':
            response, before = await policy_put(runtime, SAVED_BEFORE)
            assert response.status_code == 200
    backup = tmp_path / 'backup'
    shutil.copytree(data, backup, symlinks=True)  # an HA backup of /data/mcp
    if policy == 'unusable':
        write_policy(backup, b'{"version":1,"mode":"Enforce","allowed_origins":[]}')
    elif policy == 'a directory':
        (backup / POLICY).unlink()
        (backup / POLICY).mkdir()
    async with multi_profile_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        response, lost = await policy_put(runtime, SAVED_AFTER)
        assert response.status_code == 200
    restore_into(data, backup)
    async with multi_profile_runtime('odoo', data) as runtime:  # run_product runs the guard before anything serves
        await settle(runtime, 'configured')
        assert profiles.RESTORE_MARKER_NAME not in os.listdir(data)
        assert (data / (RECEIPTS + operations.RESTORED_SUFFIX)).exists() is (before is not None)
        read = await policy_get(runtime)
        path = f'/private_{runtime.token("default")}/mcp'
        async with runtime.mcp() as client:
            async def sent(case):
                return await client.post(path, headers=headers_of(case), json=initialize_message())
            if policy == 'saved':
                assert read.json() == {**SAVED_BEFORE, 'origin_policy_state': 'saved'}
                assert answer(await sent('not-allowed')) == DENIED_403
                assert (await sent('allowed')).status_code == 200
            elif policy == 'absent':
                assert read.json() == {'mode': 'report-only', 'allowed_origins': ['https://claude.ai'],
                                       'origin_policy_state': 'default'}
                assert (await sent('not-allowed')).status_code == 200
            else:
                assert read.json() == {'mode': None, 'allowed_origins': None, 'origin_policy_state': 'unusable'}
                for case in ('none', 'allowed', 'not-allowed'):
                    assert answer(await sent(case)) == UNAVAILABLE
        for body, key in ((SAVED_BEFORE, before), (SAVED_AFTER, lost)):
            if key is not None:
                for if_match in ('"o1-' + '0' * 64 + '"', 'current'):
                    again, _ = await policy_put(runtime, body, if_match=if_match, key=key)
                    assert (again.status_code, again.json()) == RESTORED_410
        # A new save's key is made now, after the restore (the panel's bootstrap after the start); operation_key()
        # goes a second back, which may be before the guard's cutoff a moment ago.
        key = f'{int(time.time() * 1000)}.{secrets.token_hex(16)}'
        assert int(key.split('.')[0]) > json.loads((data / RECEIPTS).read_text())['restored_before_ms']
        if policy == 'a directory':
            refused, _ = await policy_put(runtime, SAVED_AFTER, key=key)
            assert (refused.status_code, refused.json()['detail']['code']) == (409, 'operation_outcome_unknown')
            assert (data / POLICY).is_dir()
        else:
            saved, _ = await policy_put(runtime, {'mode': 'report-only', 'allowed_origins': ['https://claude.ai']},
                                        key=key)
            assert saved.status_code == 200 and saved.json()['operation'] == {
                'id': key, 'kind': 'origin.policy', 'state': 'completed', 'replayed': False}
            assert (await policy_get(runtime)).json()['origin_policy_state'] == 'saved'
            async with runtime.mcp() as client:
                assert (await client.post(path, headers=headers_of('not-allowed'),
                                          json=initialize_message())).status_code == 200


# ---- Headscale and the switch ----

async def test_headscale_keeps_only_claude_ai_and_has_no_policy(tmp_path, log_scan, caplog, monkeypatch):
    """Plan 8.7, section 9 #9 (the user's HA Headscale decision, R01 H-08): switched on, Headscale's secret path still
    takes no Origin but https://claude.ai (403 for any other, its rule of today, with no line); no policy is made, its
    file is never read (one on disk that would refuse claude.ai changes nothing) and the route is an unknown operation
    (404, no body)."""
    data = setup(tmp_path, 'headscale')
    write_policy(data, b'{"version":1,"mode":"enforce","allowed_origins":[]}')
    found = module()

    def never(*args, **kwargs):
        raise AssertionError('the Origin policy is not Headscale\'s')
    monkeypatch.setattr(found.PolicyFile, '__init__', never)
    async with multi_profile_runtime('headscale', data) as runtime:
        await settle(runtime, 'configured')
        path = f'/private_{runtime.token("default")}/mcp'
        async with runtime.mcp() as client:
            assert (await client.post(path, headers={**ACCEPT, 'Origin': 'https://claude.ai'},
                                      json=initialize_message())).status_code == 200
            for case in ('not-allowed', 'null', 'duplicate', 'allowed-otherwise-spelled'):
                assert answer(await client.post(path, headers=headers_of(case), json=initialize_message())) == DENIED_403
        async with runtime.admin() as admin:
            unknown = answer(await admin.get('/api/no-such-operation', headers=ADMIN))
        assert unknown[0] == 404 and answer(await policy_get(runtime)) == unknown
        response, _ = await policy_put(runtime, {'mode': 'report-only', 'allowed_origins': []},
                                       if_match='"o1-' + '0' * 64 + '"')
        assert answer(response) == unknown
    assert decision_lines(caplog) == []
    assert (data / POLICY).read_bytes() == b'{"version":1,"mode":"enforce","allowed_origins":[]}'


@pytest.mark.parametrize('product', PRODUCTS)
async def test_switched_off_the_policy_does_not_exist(tmp_path, log_scan, caplog, monkeypatch, product,
                                                     switched_off):
    """Plan 3.3, 12.3 HM-27 (switched by features.enabled): a product not switched on never reads or writes the file
    (one on disk that would refuse every Origin, left by a release that had the product switched on, changes nothing),
    has no route (an unknown operation: today's empty 404 after the role check, and today's 400 for a body sent to
    it), serves any Origin on the secret path as today (Headscale: its own rule) and writes no line."""
    data = tmp_path / 'data'
    configure(data, product)
    write_policy(data, b'{"version":1,"mode":"enforce","allowed_origins":[]}')
    found = module()

    def never(*args, **kwargs):
        raise AssertionError('a switched-off product reads no Origin policy')
    monkeypatch.setattr(found.PolicyFile, '__init__', never)
    monkeypatch.setattr(found.OriginPolicy, '__init__', never)
    async with production_runtime(product, data) as runtime:
        await settle(runtime, 'configured')
        before = entries(data)
        path = f'/private_{stored(data)["token"]}/mcp'
        async with runtime.mcp() as client:
            response = await client.post(path, headers={**ACCEPT, 'Origin': 'https://evil.example'},
                                         json=initialize_message())
            assert response.status_code == (403 if product == 'headscale' else 200)
            response = await client.post(path, headers={**ACCEPT, 'Origin': 'https://claude.ai'},
                                         json=initialize_message())
            assert response.status_code == 200
        async with runtime.admin() as admin:
            unknown = answer(await admin.get('/api/no-such-operation', headers=ADMIN))
            assert unknown[0] == 404 and unknown[2] == b''
            assert answer(await admin.get('/api/origin-policy', headers=ADMIN)) == unknown
            csrf = (await admin.get('/api/bootstrap', headers=ADMIN)).json()['csrf']
            write = {**ADMIN, 'X-CSRF-Token': csrf}
            assert answer(await admin.put('/api/origin-policy', headers=write)) == answer(
                await admin.put('/api/no-such-operation', headers=write))
            sent = await admin.put('/api/origin-policy', headers={**write, 'Content-Type': 'application/json'},
                                   content=b'{"mode":"report-only","allowed_origins":[]}')
            assert (sent.status_code, sent.content) == (400, b'{"error":"request denied"}')
        assert entries(data) == before
    assert lines(caplog) == []
    assert (data / POLICY).read_bytes() == b'{"version":1,"mode":"enforce","allowed_origins":[]}'
