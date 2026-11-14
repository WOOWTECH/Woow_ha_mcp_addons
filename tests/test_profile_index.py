"""HM-07: the profile index (profiles.json), labels, ids, ports, capacity and the index verdicts (not wired yet).

Multi-profile plan §4.2, §5.2, §5.4; docs/multi-profile/contract.md §3.6, §5, §8 (HM-00). The PaaS index rules
(woow-mcp-server packages/mcp-admin-core/mcp_admin_core/profiles.py @69ac425, _index_entries / _port_collisions /
ProfileCapacity) are written next to every case as the expected value; where HA differs the case names the reason
(contract §9 = plan §8.8 row). The PaaS column is documentation: this repository does not run PaaS code.
"""
import json
import os
import stat
import time
import unicodedata

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import profiles
from mcp_admin_core.profiles import (
    INDEX_ABSENT, INDEX_CORRUPT, INDEX_MODIFIED, INDEX_OK, IndexCorrupt, IndexEntry, LabelError,
)

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan

A, B, C, D, E, F = ('a' * 24, 'b' * 24, 'c' * 24, 'd' * 24, 'e' * 24, 'f' * 24)
EXAMPLE = '0123456789abcdef01234567'  # contract §8's example id


def raw(index, version=1, **top):
    return json.dumps({'version': version, 'profile_index': index, **top}, ensure_ascii=False).encode()


def entry(label, port):
    return {'label': label, 'port': port}


# (case, index bytes, PaaS outcome, HA outcome). 'ok' / 'corrupt' (the whole index is unusable: plan §4.2 "整份壞").
PARITY = [
    ('contract-example', raw({EXAMPLE: entry('會計', 18000)}), 'ok', 'ok'),
    ('empty', raw({}), 'ok', 'ok'),
    ('five', raw({k: entry(k[:1].upper() + ' prod', 18000 + i) for i, k in enumerate((A, B, C, D, E))}), 'ok', 'ok'),
    ('six', raw({k: entry('P' + str(i), 18000 + i) for i, k in enumerate((A, B, C, D, E, F))}), 'corrupt', 'corrupt'),
    ('not-an-object', raw([[A, entry('x', 18000)]]), 'corrupt', 'corrupt'),
    ('id-uppercase', raw({A.upper(): entry('x', 18000)}), 'corrupt', 'corrupt'),
    ('id-23-hex', raw({A[:23]: entry('x', 18000)}), 'corrupt', 'corrupt'),
    ('id-25-hex', raw({A + 'a': entry('x', 18000)}), 'corrupt', 'corrupt'),
    ('id-non-hex', raw({'g' * 24: entry('x', 18000)}), 'corrupt', 'corrupt'),
    ('id-default', raw({'default': entry('x', 18000)}), 'corrupt', 'corrupt'),
    ('entry-extra-key', raw({A: {'label': 'x', 'port': 18000, 'token': 'T' * 43}}), 'corrupt', 'corrupt'),
    ('entry-missing-port', raw({A: {'label': 'x'}}), 'corrupt', 'corrupt'),
    ('entry-not-object', raw({A: ['x', 18000]}), 'corrupt', 'corrupt'),
    ('label-empty', raw({A: entry('', 18000)}), 'corrupt', 'corrupt'),
    ('label-blank', raw({A: entry('   ', 18000)}), 'corrupt', 'corrupt'),
    ('label-81', raw({A: entry('x' * 81, 18000)}), 'corrupt', 'corrupt'),
    ('label-80', raw({A: entry('x' * 80, 18000)}), 'ok', 'ok'),
    ('label-not-string', raw({A: entry(7, 18000)}), 'corrupt', 'corrupt'),
    ('label-reserved-default', raw({A: entry('Default', 18000)}), 'corrupt', 'corrupt'),
    ('label-duplicate-case', raw({A: entry('Sales', 18000), B: entry('sALES', 18001)}), 'corrupt', 'corrupt'),
    ('port-bool', raw({A: entry('x', True)}), 'corrupt', 'corrupt'),
    ('port-string', raw({A: entry('x', '18000')}), 'corrupt', 'corrupt'),
    ('port-float', raw({A: entry('x', 18000.0)}), 'corrupt', 'corrupt'),
    ('port-1023', raw({A: entry('x', 1023)}), 'corrupt', 'corrupt'),
    ('port-65536', raw({A: entry('x', 65536)}), 'corrupt', 'corrupt'),
    ('port-1024', raw({A: entry('x', 1024)}), 'ok', 'ok'),
    ('port-65535', raw({A: entry('x', 65535)}), 'ok', 'ok'),
    # Not structural (PaaS test_profile_robustness.py:191, :316): only the profiles involved stop (port_conflicts).
    ('port-duplicate', raw({A: entry('x', 18000), B: entry('y', 18000)}), 'ok', 'ok'),
    ('port-default-child', raw({A: entry('x', 3000)}), 'ok', 'ok'),
    # The add-on's own listeners, 8081 (MCP) and 8099 (panel), likewise: PaaS _index_entries takes any port of
    # 1024-65535 and refuses a listener port only at spawn (process.py _port_refusal); design A-port and FM-40 list
    # 3000, 8081 and 8099 together as "not structural". HM-07 review MF-1; the provenance note, section 3.
    ('port-mcp-listener', raw({A: entry('x', 8081)}), 'ok', 'ok'),
    ('port-admin-listener', raw({A: entry('x', 8099)}), 'ok', 'ok'),
    # Contract §9 #35 (DQ-40 ④): label characters and NFKC + casefold uniqueness; '預設帳號' reserved.
    ('label-zero-width', raw({A: entry('Sa\u200bles', 18000)}), 'ok', 'corrupt'),
    ('label-bidi-override', raw({A: entry('\u202eselaS', 18000)}), 'ok', 'corrupt'),
    ('label-control', raw({A: entry('a\tb', 18000)}), 'ok', 'corrupt'),
    ('label-line-separator', raw({A: entry('a\u2028b', 18000)}), 'ok', 'corrupt'),
    ('label-private-use', raw({A: entry('a\ue000', 18000)}), 'ok', 'corrupt'),
    ('label-lone-surrogate', b'{"version":1,"profile_index":{"' + A.encode() + b'":{"label":"a\\ud800","port":18000}}}',
     'ok', 'corrupt'),
    ('label-nfkc-duplicate', raw({A: entry('ＡＢＣ', 18000), B: entry('abc', 18001)}), 'ok', 'corrupt'),
    ('label-reserved-chinese', raw({A: entry('預設帳號', 18000)}), 'ok', 'corrupt'),
    ('label-reserved-fullwidth', raw({A: entry('ｄｅｆａｕｌｔ', 18000)}), 'ok', 'corrupt'),
    # A stored label is already normalized (the create and rename paths store the stripped text).
    ('label-outer-space', raw({A: entry(' Sales ', 18000)}), 'ok', 'corrupt'),
    ('label-outer-ideographic-space', raw({A: entry('\u3000會計\u3000', 18000)}), 'ok', 'corrupt'),
    ('label-outer-nbsp', raw({A: entry('\u00a0Sales', 18000)}), 'ok', 'corrupt'),
    # HA's own file (contract §9 #44): exact top-level keys and version, strict JSON (duplicate keys refused).
    ('duplicate-id-key', b'{"version":1,"profile_index":{"' + A.encode() + b'":{"label":"x","port":18000},"'
     + A.encode() + b'":{"label":"y","port":18001}}}', 'ok', 'corrupt'),
    ('top-extra-key', raw({}, extra=1), 'n/a', 'corrupt'),
    ('top-missing-version', json.dumps({'profile_index': {}}).encode(), 'n/a', 'corrupt'),
    ('version-2', raw({}, version=2), 'n/a', 'corrupt'),
    ('version-bool', raw({}, version=True), 'n/a', 'corrupt'),
    ('not-utf8', b'{"version":1,"profile_index":{"' + A.encode() + b'":{"label":"\xff","port":18000}}}', 'n/a', 'corrupt'),
    ('utf8-bom', b'\xef\xbb\xbf' + raw({}), 'n/a', 'corrupt'),
    ('not-json', b'{"version":1,', 'n/a', 'corrupt'),
    ('nonfinite', b'{"version":1,"profile_index":{},"x":NaN}', 'n/a', 'corrupt'),
    ('deep', b'[' * 10000 + b']' * 10000, 'n/a', 'corrupt'),
]


@pytest.mark.parametrize('case, data, paas, ha', PARITY, ids=[c[0] for c in PARITY])
def test_index_rules_against_the_paas_rules(case, data, paas, ha):
    assert paas in ('ok', 'corrupt', 'n/a')
    if ha == 'ok':
        entries = profiles.parse_index(data)
        assert all(isinstance(e, IndexEntry) for e in entries)
        assert profiles.encode_index(entries) == data or json.loads(profiles.encode_index(entries)) == json.loads(data)
    else:
        with pytest.raises(IndexCorrupt):
            profiles.parse_index(data)


def test_order_is_the_creation_order_and_survives_a_round_trip():
    index = {C: entry('三', 18002), A: entry('一', 18000), B: entry('二', 18001)}
    entries = profiles.parse_index(raw(index))
    assert [e.id for e in entries] == [C, A, B]
    assert [(e.label, e.port) for e in entries] == [('三', 18002), ('一', 18000), ('二', 18001)]
    data = profiles.encode_index(entries)
    assert profiles.parse_index(data) == entries
    assert list(json.loads(data)['profile_index']) == [C, A, B]
    assert json.loads(data) == {'version': 1, 'profile_index': index}
    assert '一' in data.decode('utf-8')  # stored as UTF-8 text, not \u escapes


def test_encode_refuses_what_parse_would_refuse():
    for entries in ([IndexEntry(A, 'x', 1023)], [IndexEntry(A, 'x', True)],
                    [IndexEntry(A, 'x', 18000), IndexEntry(B, 'X', 18001)],
                    [IndexEntry('A' * 24, 'x', 18000)], [IndexEntry(A, ' x', 18000)],
                    [IndexEntry(k, k, 18000 + i) for i, k in enumerate((A, B, C, D, E, F))]):
        with pytest.raises(IndexCorrupt):
            profiles.encode_index(entries)


def test_duplicate_port_and_default_port_are_not_structural_and_name_only_the_profiles_involved():
    # PaaS test_profile_robustness.py:191 / :252 / :316: the runtime index relaxes only port uniqueness (and the
    # default profile's port); every structural rule still applies. HA has no strict "restore" variant: the HA restore
    # guard never reads the index (plan §8.4: "不看索引").
    entries = profiles.parse_index(raw({A: entry('a1', 18000), B: entry('b1', 18000), C: entry('c1', 3000),
                                        D: entry('d1', 18003)}))
    assert profiles.port_conflicts(entries) == {18000: (A, B), 3000: (C,)}
    assert profiles.port_conflicts(profiles.parse_index(raw({A: entry('a1', 18000), B: entry('b1', 18001)}))) == {}
    with pytest.raises(IndexCorrupt):
        profiles.parse_index(raw({A: entry('a1', 18000), B: entry('b1', 18000), C: entry('A1', 18002)}))


def test_a_listener_port_stops_only_the_profile_holding_it(tmp_path):
    # HM-07 review MF-1: an index port that is one of the add-on's own listeners (8081 MCP, 8099 panel) keeps the index
    # usable, so 8081 goes on serving the default profile and every other profile; only the profiles on such a port are
    # not started (disabled_reason port_conflict), like a duplicate or the default child's port. PaaS takes the port in
    # its index and refuses the spawn (process.py _port_refusal: "the admin listener uses this port").
    data = raw({A: entry('a1', 18000), B: entry('b1', 8081), C: entry('c1', 8099), D: entry('d1', 18003),
                E: entry('e1', 8081)})
    entries = profiles.parse_index(data)
    assert [e.port for e in entries] == [18000, 8081, 8099, 18003, 8081]
    assert profiles.port_conflicts(entries) == {8081: (B, E), 8099: (C,)}
    assert profiles.disabled_reasons(entries, profiles.capacity('odoo')) == {
        B: {'disabled_reason': 'port_conflict'}, C: {'disabled_reason': 'port_conflict'},
        E: {'disabled_reason': 'port_conflict'}}
    path = tmp_path / 'profiles.json'
    path.write_bytes(data)
    path.chmod(0o600)
    view = profiles.read_index(path)
    assert view.state == INDEX_OK and view.entries == entries
    assert view.serves_mcp and not view.offers_quarantine


def test_ids():
    assert profiles.is_profile_id(EXAMPLE) and profiles.is_profile_id(A)
    for value in ('default', A.upper(), A[:23], A + 'a', A + '\n', ' ' + A[1:], '٠' * 24, None, 7, b'a' * 24):
        assert not profiles.is_profile_id(value)
    made = {profiles.new_profile_id() for _ in range(32)}
    assert len(made) == 32 and all(profiles.is_profile_id(value) for value in made)
    taken = set(made)
    assert profiles.new_profile_id(taken) not in taken
    assert profiles.log_id(EXAMPLE) == '01234567' and profiles.log_id('default') == 'default'
    with pytest.raises(ValueError):
        profiles.log_id('Accounting')  # never a label or any other text


@pytest.mark.parametrize('value, stored', [
    ('會計', '會計'), ('  Sales team  ', 'Sales team'), ('x' * 80, 'x' * 80), (' ' + 'x' * 80 + ' ', 'x' * 80),
    ('Ünïcödé', 'Ünïcödé'), ('a\u00a0b', 'a\u00a0b'), ('e\u0301', 'e\u0301'), ('中文 + emoji 🙂', '中文 + emoji 🙂'),
    # Outer whitespace of any kind goes, not only ASCII (HM-07 review S-12): ideographic space, NBSP, em space.
    ('\u3000會計\u3000', '會計'), ('\u00a0Sales\u00a0', 'Sales'), ('\u2003a\u3000b\u2009', 'a\u3000b'),
])
def test_label_accepted_and_stored_stripped(value, stored):
    assert profiles.normalize_label(value) == stored


@pytest.mark.parametrize('value', [
    '', '   ', 'x' * 81, 'a\tb', 'a\x00b', 'a\x7fb', 'a\x85b', 'Sa\u200bles', '\u200d', '\u202eabc', 'a\u2066b',
    'a\u2028b', 'a\u2029b', 'a\ue000', 'a\U000f0000', 'a\ud800', 'a\U000e0001', 'a\u0378', '\ufeffabc', None, 7,
])
def test_label_refused(value):
    with pytest.raises(LabelError):
        profiles.normalize_label(value)
    assert LabelError.code == 'profile_label_invalid'


def test_label_refused_categories_are_the_contract_ones():
    # contract §3.6: Cc, Cf (bidi, zero-width), Zl, Zp, Cs, Co and unassigned (Cn) -- and nothing else.
    assert profiles.REFUSED_LABEL_CATEGORIES == frozenset({'Cc', 'Cf', 'Zl', 'Zp', 'Cs', 'Co', 'Cn'})
    for code in range(0x110000):
        char = chr(code)
        category = unicodedata.category(char)
        if char.isspace() or category in profiles.REFUSED_LABEL_CATEGORIES:
            continue
        assert profiles.normalize_label('a' + char + 'b') == 'a' + char + 'b'


def test_label_uniqueness_is_nfkc_and_casefold_and_keeps_the_reserved_names():
    assert profiles.RESERVED_LABELS == ('default', '預設帳號')
    assert profiles.label_key('ＤｅｆＡｕｌｔ') == profiles.label_key('default')
    assert profiles.label_key('Straße') == profiles.label_key('STRASSE')
    assert profiles.label_key('ﬁle') == profiles.label_key('FILE')
    for label in ('Default', 'DEFAULT', 'ｄｅｆａｕｌｔ', '預設帳號'):
        assert profiles.label_taken(label, [])
    assert profiles.label_taken('sales', ['Accounting', 'SALES'])
    assert profiles.label_taken('ＳＡＬＥＳ', ['sales'])
    assert not profiles.label_taken('Sales 2', ['Sales'])
    assert not profiles.label_taken('預設', [])
    for text in ('ＡＢＣ', 'Straße', 'ﬁ', 'ǅ', 'İ', 'ς', '㍿'):
        key = profiles.label_key(text)
        assert profiles.label_key(key) == key  # stable: comparing keys of keys changes nothing


def test_port_allocation_is_the_first_free_port_of_18000_to_18099():
    assert (profiles.FIRST_PROFILE_PORT, profiles.LAST_PROFILE_PORT) == (18000, 18099)
    assert profiles.RESERVED_PORTS == frozenset({3000, 8081, 8099})
    assert profiles.allocate_port() == 18000
    assert profiles.allocate_port([18000, 18001, 18003]) == 18002
    assert profiles.allocate_port(range(18000, 18099)) == 18099
    assert profiles.allocate_port(range(18000, 18100)) is None
    assert profiles.allocate_port([3000, 8081, 8099, 17999, 18100]) == 18000
    # Reserved ports can never come out, whatever the constants become.
    for port in range(profiles.FIRST_PROFILE_PORT, profiles.LAST_PROFILE_PORT + 1):
        assert port not in profiles.RESERVED_PORTS and profiles.MIN_PORT <= port <= profiles.MAX_PORT


def test_capacity_constants_are_the_contract_values():
    # contract §5 (DQ-07 + DQ-29 (a)); provisional until HM-19c measures on the target hardware.
    assert profiles.MAX_EXTRA_PROFILES == 5 and profiles.PROFILE_MEMORY_RESERVE_MIB == 256
    assert profiles.EXTRA_PROFILE_LIMITS == {'odoo': 5, 'n8n': 2, 'hermes': 3, 'emqx': 3, 'litellm': 3,
                                             'nextcloud': 3, 'headscale': 3, 'opendesign': 0, 'odoo-manage': 0}
    assert profiles.CHILD_MEMORY_MIB == {'odoo': 100, 'n8n': 300, 'hermes': 160, 'emqx': 160, 'litellm': 160,
                                         'nextcloud': 160, 'headscale': 160, 'opendesign': None, 'odoo-manage': None}
    assert {p: profiles.mcp_listener_limit(p) for p in profiles.EXTRA_PROFILE_LIMITS} == {
        'odoo': 224, 'n8n': 128, 'hermes': 160, 'emqx': 160, 'litellm': 160, 'nextcloud': 160, 'headscale': 160,
        'opendesign': 64, 'odoo-manage': 64}
    mib = 1024 * 1024
    assert profiles.DEFAULT_PROFILE_QUOTA == profiles.ProfileQuota(
        admission=64, body_bytes=64 * mib, forward_slots=32, forward_wait_seconds=1.0, get_streams=24, queue=32,
        reserved_notifications=4, pending_reply_bytes=32 * mib, child_connections=40)
    assert profiles.EXTRA_PROFILE_QUOTA == profiles.ProfileQuota(
        admission=32, body_bytes=64 * mib, forward_slots=16, forward_wait_seconds=1.0, get_streams=8, queue=16,
        reserved_notifications=4, pending_reply_bytes=32 * mib, child_connections=24)


def test_opendesign_and_odoo_manage_cannot_have_additional_profiles():
    # DQ-28 (2026-11-14): not opened; creating one answers 409 profile_product_unsupported (HM-10).
    supported = {p for p in profiles.EXTRA_PROFILE_LIMITS if profiles.supports_profiles(p)}
    assert supported == {'odoo', 'n8n', 'hermes', 'emqx', 'litellm', 'nextcloud', 'headscale'}
    for product in ('opendesign', 'odoo-manage'):
        assert profiles.capacity(product).limit == 0
        assert profiles.capacity(product, memory_limit_mib=8192).limit == 0
        assert profiles.capacity(product).disabled_reason(0) == 'profile_limit'
    with pytest.raises(ValueError):
        profiles.capacity('bogus')


def test_product_limit_disables_only_the_later_profiles_in_index_order():
    # PaaS test_profiles.py:307: the index stays valid; positions past the product limit are not started.
    entries = profiles.parse_index(raw({k: entry('n' + str(i), 18000 + i) for i, k in enumerate((A, B, C, D, E))}))
    n8n = profiles.capacity('n8n')
    assert n8n.limit == 2 and n8n.memory_extra_limit is None
    assert profiles.disabled_reasons(entries, n8n) == {C: {'disabled_reason': 'profile_limit'},
                                                       D: {'disabled_reason': 'profile_limit'},
                                                       E: {'disabled_reason': 'profile_limit'}}
    assert profiles.disabled_reasons(entries, profiles.capacity('odoo')) == {}
    assert profiles.disabled_reasons(entries[:3], profiles.capacity('hermes')) == {}


def test_memory_formula_is_the_paas_one():
    # PaaS profiles.py:170-174, :309-314: extra = min(limit, max(1, (memory - 256) // child) - 1).
    odoo = profiles.capacity('odoo', memory_limit_mib=600)  # (600 - 256) // 100 = 3 children -> 2 extra
    assert (odoo.policy_limit, odoo.memory_extra_limit, odoo.limit) == (5, 2, 2)
    assert odoo.required_memory_mib(3) == 256 + 4 * 100
    assert odoo.disabled_reason(1) is None and odoo.disabled_reason(2) == 'memory_capacity'
    assert profiles.capacity('odoo', memory_limit_mib=100).memory_extra_limit == 0  # max(1, ...) - 1
    assert profiles.capacity('n8n', memory_limit_mib=8192).limit == 2
    assert profiles.capacity('odoo').required_memory_mib(1) == 456
    entries = profiles.parse_index(raw({A: entry('a1', 18000), B: entry('b1', 18000), C: entry('c1', 18002),
                                        D: entry('d1', 18003)}))
    # PaaS order: product limit, then memory, then the port (setdefault: a profile keeps its first reason).
    # The third additional profile needs the default plus three children: 256 + 4 x 100 MiB.
    assert profiles.disabled_reasons(entries, odoo) == {
        A: {'disabled_reason': 'port_conflict'}, B: {'disabled_reason': 'port_conflict'},
        C: {'disabled_reason': 'memory_capacity', 'required_memory_mib': 656},
        D: {'disabled_reason': 'memory_capacity', 'required_memory_mib': 756}}


def test_a_profile_keeps_its_first_disabled_reason():
    # Contract §3.6, PaaS _start_blocks: the product limit first, then memory, then a port conflict (HM-07 review S-04).
    # A profile past the limit that also holds a conflicting port says profile_limit; one past the memory budget says
    # memory_capacity; the other holder of the port still says port_conflict.
    n8n = profiles.capacity('n8n')  # two additional profiles
    entries = profiles.parse_index(raw({A: entry('a1', 18000), B: entry('b1', 18001), C: entry('c1', 18000),
                                        D: entry('d1', 8081)}))
    assert profiles.port_conflicts(entries) == {18000: (A, C), 8081: (D,)}
    assert profiles.disabled_reasons(entries, n8n) == {A: {'disabled_reason': 'port_conflict'},
                                                       C: {'disabled_reason': 'profile_limit'},
                                                       D: {'disabled_reason': 'profile_limit'}}
    odoo = profiles.capacity('odoo', memory_limit_mib=456)  # (456 - 256) // 100 = 2 children: one additional
    assert odoo.memory_extra_limit == 1
    entries = profiles.parse_index(raw({A: entry('a1', 18000), B: entry('b1', 18000), C: entry('c1', 3000)}))
    assert profiles.disabled_reasons(entries, odoo) == {
        A: {'disabled_reason': 'port_conflict'},
        B: {'disabled_reason': 'memory_capacity', 'required_memory_mib': 556},
        C: {'disabled_reason': 'memory_capacity', 'required_memory_mib': 656}}


# ---------------------------------------------------------------------------------------------------------------
# The file: read, write, signature, verdicts (DQ-12)
# ---------------------------------------------------------------------------------------------------------------

def next_tick(directory):
    """Wait until the file-time clock moves on: Linux stamps ctime and mtime with a coarse clock (one tick, a few
    ms), so a change made within the tick of the previous one can carry the same ctime."""
    probe = directory / '.tick'
    probe.write_bytes(b'')
    first = os.lstat(probe).st_ctime_ns
    while os.lstat(probe).st_ctime_ns == first:
        time.sleep(0.002)
        os.chmod(probe, 0o600)
    probe.unlink()


def written(tmp_path, entries=None):
    path = tmp_path / 'profiles.json'
    view = profiles.write_index(path, entries or [IndexEntry(A, '會計', 18000)], expected=profiles.read_index(path))
    return path, view


def test_write_then_read(tmp_path, log_scan):
    log_scan.watch('Sales', '會計部門', kind='name')  # I7: a label never shows in a log record
    path, view = written(tmp_path, [IndexEntry(A, '會計', 18000), IndexEntry(B, 'Sales', 18001),
                                    IndexEntry(C, '會計部門', 18002)])
    assert view.state == INDEX_OK and [e.id for e in view.entries] == [A, B, C]
    info = os.lstat(path)
    assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
    assert info.st_uid == os.geteuid()
    assert view.signature == profiles.signature_of(path)
    assert profiles.read_index(path) == view
    assert sorted(p.name for p in tmp_path.iterdir()) == ['profiles.json']  # no temporary file left
    assert json.loads(path.read_bytes()) == {'version': 1, 'profile_index': {
        A: entry('會計', 18000), B: entry('Sales', 18001), C: entry('會計部門', 18002)}}


def test_write_sets_0600_whatever_the_umask(tmp_path):
    previous = os.umask(0o277)
    try:
        path, view = written(tmp_path)
    finally:
        os.umask(previous)
    assert stat.S_IMODE(os.lstat(path).st_mode) == 0o600 and profiles.read_index(path) == view


def test_write_is_atomic_and_durable(tmp_path, monkeypatch):
    path, before = written(tmp_path)
    old = path.read_bytes()
    calls = []
    real_fsync = os.fsync
    monkeypatch.setattr(profiles.os, 'fsync', lambda fd: (calls.append(stat.S_IFMT(os.fstat(fd).st_mode)),
                                                          real_fsync(fd))[1])
    after = profiles.write_index(path, [IndexEntry(A, '會計', 18000), IndexEntry(B, 'B', 18001)], expected=before)
    assert calls == [stat.S_IFREG, stat.S_IFDIR]  # the file before the rename, the directory after it
    assert after.signature != before.signature and after.signature.st_ino != before.signature.st_ino
    monkeypatch.undo()
    for step in ('open', 'write', 'fsync', 'replace'):
        with monkeypatch.context() as patch:
            def fail(*args, **kwargs):
                raise OSError('injected LOCAL storage fault')
            if step == 'open':
                patch.setattr(profiles.os, 'open', fail)
            elif step == 'write':
                patch.setattr(profiles.os, 'write', fail)
            elif step == 'fsync':
                patch.setattr(profiles.os, 'fsync', fail)
            else:
                patch.setattr(profiles.os, 'replace', fail)
            with pytest.raises(profiles.ProfileDataError):
                profiles.write_index(path, [IndexEntry(C, 'C', 18002)], expected=after)
        assert profiles.read_index(path) == after  # the previous index is untouched
        assert sorted(p.name for p in tmp_path.iterdir()) == ['profiles.json'], step
    path.write_bytes(old)


def test_read_absent_index(tmp_path):
    view = profiles.read_index(tmp_path / 'profiles.json')
    assert (view.state, view.entries, view.signature) == (INDEX_ABSENT, (), None)
    assert view.serves_mcp and not view.offers_quarantine
    assert list(tmp_path.iterdir()) == []  # reading never creates anything
    assert profiles.read_index(tmp_path / 'missing' / 'profiles.json').state == INDEX_ABSENT


def corrupt_files(tmp_path):
    """Every unusable file shape; each is the only profiles.json of its own directory."""
    cases = {}

    def place(name, setup):
        directory = tmp_path / name
        directory.mkdir()
        setup(directory / 'profiles.json')
        cases[name] = directory / 'profiles.json'

    good = profiles.encode_index([IndexEntry(A, 'x', 18000)])
    place('symlink', lambda p: (p.with_name('target').write_bytes(good), p.with_name('target').chmod(0o600),
                                p.symlink_to('target')))
    place('dangling-symlink', lambda p: p.symlink_to('nowhere'))
    place('hard-link', lambda p: (p.write_bytes(good), p.chmod(0o600), os.link(p, p.with_name('second'))))
    place('mode-0644', lambda p: (p.write_bytes(good), p.chmod(0o644)))
    place('mode-0400', lambda p: (p.write_bytes(good), p.chmod(0o400)))
    place('too-large', lambda p: (p.write_bytes(good[:-1] + b' ' * 70000 + b'}'), p.chmod(0o600)))
    place('directory', lambda p: p.mkdir(mode=0o700))
    place('fifo', lambda p: os.mkfifo(p, 0o600))
    place('structure', lambda p: (p.write_bytes(raw({A: entry('x', 1023)})), p.chmod(0o600)))
    place('empty-file', lambda p: (p.write_bytes(b''), p.chmod(0o600)))
    return cases


def test_read_refuses_every_unusable_file_without_changing_it(tmp_path):
    for name, path in corrupt_files(tmp_path).items():
        before = os.lstat(path)
        next_tick(tmp_path)  # a chmod by the read would show in the ctime
        view = profiles.read_index(path)
        assert (view.state, view.entries) == (INDEX_CORRUPT, ()), name
        assert not view.serves_mcp and view.offers_quarantine, name
        after = os.lstat(path)
        assert (after.st_mode, after.st_ino, after.st_mtime_ns, after.st_ctime_ns) == (
            before.st_mode, before.st_ino, before.st_mtime_ns, before.st_ctime_ns), name  # never fchmod'ed


def test_read_refuses_an_index_another_uid_owns(tmp_path, monkeypatch):
    path, view = written(tmp_path)
    assert profiles.read_index(path) == view
    with monkeypatch.context() as patch:
        patch.setattr(profiles.os, 'geteuid', lambda: os.lstat(path).st_uid + 1)
        assert profiles.read_index(path).state == INDEX_CORRUPT


def test_signature_has_ctime_and_link_count(tmp_path):
    # Plan §4.2 (C1-S8): st_dev, st_ino, st_mtime_ns, st_ctime_ns, st_size, st_nlink. The same uid can put back the
    # bytes and the mtime (os.utime) but not the ctime. Not a security boundary: it catches mistakes.
    assert [f.name for f in profiles.IndexSignature.__dataclass_fields__.values()] == [
        'st_dev', 'st_ino', 'st_mtime_ns', 'st_ctime_ns', 'st_size', 'st_nlink']
    path, view = written(tmp_path)
    base = view.signature
    info = os.lstat(path)
    assert base == profiles.IndexSignature(info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns,
                                           info.st_size, info.st_nlink)
    assert profiles.recheck_index(path, view) is view

    def changed():
        current = profiles.recheck_index(path, view)
        assert current.state == INDEX_MODIFIED and current.entries == () and not current.serves_mcp
        assert current.offers_quarantine
        return current.signature

    data = path.read_bytes()
    next_tick(tmp_path)
    with open(path, 'r+b') as stream:  # same bytes, same inode, mtime put back: only the ctime tells
        stream.write(data)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
    assert os.lstat(path).st_mtime_ns == base.st_mtime_ns and path.read_bytes() == data
    assert changed().st_ctime_ns != base.st_ctime_ns
    path, view = written(tmp_path)
    next_tick(tmp_path)
    os.link(path, tmp_path / 'second-link')  # nlink 2
    assert changed().st_nlink == 2
    (tmp_path / 'second-link').unlink()
    assert profiles.recheck_index(path, view).state == INDEX_MODIFIED  # the unlink changed the ctime too
    path, view = written(tmp_path)
    next_tick(tmp_path)
    os.chmod(path, 0o600)  # a no-op chmod still changes the ctime
    changed()
    path, view = written(tmp_path)
    path.unlink()  # disappeared
    assert changed() is None
    absent = profiles.read_index(path)
    assert profiles.recheck_index(path, absent) is absent
    path.write_bytes(profiles.encode_index([IndexEntry(A, 'x', 18000)]))  # appeared from nowhere
    path.chmod(0o600)
    appeared = profiles.recheck_index(path, absent)
    assert appeared.state == INDEX_MODIFIED and appeared.signature is not None


def test_a_recheck_that_cannot_stat_the_index_fails_closed(tmp_path, monkeypatch):
    # HM-07 review S-05: any error of the per-request lstat but "no such file" (EACCES, EIO, ...) answers MODIFIED,
    # never the view it was given: 8081 answers 503 and the panel offers the quarantine.
    path, view = written(tmp_path)
    absent = profiles.read_index(tmp_path / 'none.json')

    def denied(*args, **kwargs):
        raise PermissionError('injected')

    with monkeypatch.context() as patch:
        patch.setattr(profiles.os, 'lstat', denied)
        results = [(before, profiles.recheck_index(path, before)) for before in (view, absent)]
    for before, after in results:
        assert after is not before and after.state == INDEX_MODIFIED and after.entries == ()
        assert not after.serves_mcp and after.offers_quarantine
    assert profiles.recheck_index(path, view) is view  # the file itself never changed


def open_descriptors():
    return sorted(os.listdir('/proc/self/fd'))


def test_read_closes_its_descriptor_whatever_the_file(tmp_path):
    # HM-07 review S-12: no descriptor stays open on any path of read_index (HM-08 reads at every start and after the
    # quarantine; a leak per read would add up).
    path, view = written(tmp_path)
    (tmp_path / 'shapes').mkdir()
    cases = [path, tmp_path / 'missing.json', *corrupt_files(tmp_path / 'shapes').values()]
    bad = tmp_path / 'bad.json'
    bad.write_bytes(b'{')
    bad.chmod(0o600)
    cases.append(bad)
    before = open_descriptors()
    states = [profiles.read_index(case).state for case in cases]
    assert open_descriptors() == before
    assert states[:2] == [INDEX_OK, INDEX_ABSENT] and set(states[2:]) == {INDEX_CORRUPT}


def test_a_modified_index_stays_modified_until_a_restart_reads_it_again(tmp_path):
    # Contract §2.3: changed behind the add-on's back -> 503 "直到重啟". The caller keeps the view a recheck returns;
    # once MODIFIED it stays MODIFIED whatever the file does next: put back, removed again, rewritten.
    path, view = written(tmp_path)
    data = path.read_bytes()
    absent = profiles.read_index(tmp_path / 'other.json')
    (tmp_path / 'other.json').write_bytes(data)  # an index appears where there was none
    (tmp_path / 'other.json').chmod(0o600)
    appeared = profiles.recheck_index(tmp_path / 'other.json', absent)
    assert appeared.state == INDEX_MODIFIED
    (tmp_path / 'other.json').unlink()  # and disappears again: still MODIFIED, the signature matches "absent" again
    assert profiles.recheck_index(tmp_path / 'other.json', appeared) is appeared
    next_tick(tmp_path)
    path.unlink()
    modified = profiles.recheck_index(path, view)
    assert modified.state == INDEX_MODIFIED and not modified.serves_mcp and modified.offers_quarantine
    for change in (lambda: (path.write_bytes(data), path.chmod(0o600)), lambda: path.unlink(),
                   lambda: (path.write_bytes(profiles.encode_index([IndexEntry(B, 'y', 18001)])), path.chmod(0o600))):
        next_tick(tmp_path)
        change()
        assert profiles.recheck_index(path, modified) is modified
    assert profiles.read_index(path).state == INDEX_OK  # a restart reads the file as it is now


def test_a_rewrite_by_this_process_is_the_new_baseline(tmp_path):
    path, view = written(tmp_path)
    renamed = profiles.write_index(path, [IndexEntry(A, 'Renamed', 18000)], expected=view)
    assert profiles.recheck_index(path, view).state == INDEX_MODIFIED  # the old baseline no longer matches
    assert profiles.recheck_index(path, renamed) is renamed
    assert profiles.read_index(path) == renamed


def test_a_write_replaces_only_the_index_this_process_vouches_for(tmp_path):
    # HM-07 review S-07: the write compares before it replaces. Only the view this process read or wrote last, ABSENT
    # or OK and still matching the file, may be replaced; any other index stays as it is (ProfileDataError), so a
    # write never washes away DQ-12's "503 until a restart" (only the index quarantine, HM-10, ends it).
    path, first = written(tmp_path)
    current = profiles.write_index(path, [IndexEntry(A, '會計', 18000), IndexEntry(B, 'B', 18001)], expected=first)
    data = path.read_bytes()

    def refused(target, expected):
        before = sorted(p.name for p in tmp_path.iterdir()), target.read_bytes(), os.lstat(target).st_ino
        with pytest.raises(profiles.ProfileDataError):
            profiles.write_index(target, [IndexEntry(C, 'C', 18002)], expected=expected)
        assert (sorted(p.name for p in tmp_path.iterdir()), target.read_bytes(), os.lstat(target).st_ino) == before

    refused(path, first)  # an older baseline of this process
    refused(path, profiles.IndexView(INDEX_CORRUPT, (), current.signature))
    refused(path, profiles.IndexView(INDEX_MODIFIED, (), current.signature))
    assert profiles.write_index(path, [IndexEntry(A, 'x', 18000)], expected=current).state == INDEX_OK
    current = profiles.read_index(path)
    next_tick(tmp_path)
    path.write_bytes(data)  # changed behind the add-on's back: kept as it is, for the quarantine
    refused(path, current)
    assert path.read_bytes() == data
    other = tmp_path / 'other.json'
    absent = profiles.read_index(other)
    other.write_bytes(data)  # appeared where there was none
    other.chmod(0o600)
    refused(other, absent)
    corrupt = tmp_path / 'corrupt.json'
    corrupt.write_bytes(b'{')
    corrupt.chmod(0o600)
    refused(corrupt, profiles.read_index(corrupt))  # read at startup as CORRUPT: never written over


def test_verdicts_for_the_mcp_listener_and_the_panel():
    # DQ-12 (2026-11-14, as recommended): index corrupt or changed behind the add-on's back -> 8081 answers 503 for
    # every token, the default profile's included; the panel still opens and offers "quarantine the profile index";
    # no manual repair on HA. HM-07 only decides; HM-08 (8081) and HM-10 (panel) wire it.
    for state, serves, quarantine in ((INDEX_ABSENT, True, False), (INDEX_OK, True, False),
                                      (INDEX_CORRUPT, False, True), (INDEX_MODIFIED, False, True)):
        view = profiles.IndexView(state, (), None)
        assert (view.serves_mcp, view.offers_quarantine) == (serves, quarantine)
    with pytest.raises(ValueError):
        profiles.IndexView('broken', (), None)
    with pytest.raises(ValueError):
        profiles.IndexView(INDEX_CORRUPT, (IndexEntry(A, 'x', 18000),), None)  # entries only when usable
