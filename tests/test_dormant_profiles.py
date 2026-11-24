"""HM-13b: dormant profiles (multi-profile plan 3.3, 8.4 休眠處理, 10.3; contract 1.2, 1.3, 9 #24; FM-119; I13).

A product that is not switched on but has profile data on disk (a version that switched the product off again, or a
restored backup of such a time) serves the default profile only. At every start, before anything is served, the boot
guard (restore_lock.guard) revokes the token of every additional profile and orphan that is not revoked yet, with a
new child token; one that cannot be opened is quarantined; the default profile is left as it is unless a restore is
seen at the same start (DQ-03 (b): then profile data revokes it too). The bootstrap shows the number as
dormant_profiles; nothing else of the profile management exists while the product is switched off.

The disk is tests/restore_guard_disk.py; every test runs under the HM-01 log scan.
"""
import json

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from switch_modes import switched_off  # noqa: F401  (fixture: HM-19a, the switch a test pins)
from mcp_admin_core import profiles, restore_detect as rd, restore_lock
from mcp_admin_core.config import ConfigError
from multi_profile_runtime import Children, multi_profile_runtime
from restore_guard_disk import DEFAULT, Disk, StopAt, break_state, lying_revocation, tree
from test_profile_routing import paths
from test_restore_detection import Crash
from test_single_profile_golden import (ACCEPT, ADMIN, BEARER_REQUIRED, BOOTSTRAP_COMMON, BOOTSTRAP_EXTRA, NOT_FOUND,
                                        MockChild, answer, configure, initialize_message, production_runtime, settle)

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'odoo'
A, B, C = 'a' * 24, 'b' * 24, 'c' * 24
MARKER = profiles.RESTORE_MARKER_NAME
LOGGER = 'mcp_admin_core.restore_lock'


def guard_lines(log_scan):
    return [record.getMessage() for record in log_scan.records if record.name == LOGGER]


def dormant_disk(tmp_path, log_scan, *, configured_default=False):
    """The default profile, A and B (indexed) and C (an orphan), made while the product was switched on (a start made
    the sentinel), now on a version that has it switched off."""
    if configured_default:
        configure(tmp_path / 'mcp', PRODUCT)
    disk = Disk(tmp_path, log_scan)
    assert disk.start(enabled=True) == restore_lock.Outcome()  # the sentinel, before any profile data
    for profile_id in (A, B):
        disk.add(profile_id)
    disk.add(C, indexed=False)
    return disk


def test_dormant_profiles_are_revoked_once_and_left_alone_after(tmp_path, log_scan):
    """I13: the first start of the switched-off version revokes A, B and the orphan C (one history entry each, new child
    tokens), records it and says so once; the default profile's state is untouched. The next start finds them revoked
    and writes nothing at all, and logs nothing."""
    disk = dormant_disk(tmp_path, log_scan)
    default = (disk.data / 'state.json').read_bytes()
    before = {profile_id: disk.tokens(profile_id) for profile_id in (A, B, C)}
    outcome = disk.start(enabled=False)
    assert outcome == restore_lock.Outcome(dormant=3, revoked=(A, B, C))
    assert (disk.data / 'state.json').read_bytes() == default
    for profile_id, (token, child) in before.items():
        now = disk.tokens(profile_id)
        assert now[0] is None and now[1] not in (token, child)
        assert disk.state(profile_id)['token_history'][0]['action'] == 'revoke'
    record = restore_lock.read_record(disk.data)
    assert record['restore'] is None and set(record['dormant']) == {'at'}
    assert [(row['id'], row['token']) for row in record['profiles']] == [
        (DEFAULT, 'kept'), (A, 'revoked'), (B, 'revoked'), (C, 'revoked')]
    lines = guard_lines(log_scan)
    assert lines[-1] == restore_lock.DORMANT_NOTICE % 3 and len(lines) == 4
    assert disk.detection(False) == rd.Detection(False, True, rd.CONSISTENT)
    profile_tree = tree(disk.layout.profiles)
    record_bytes = (disk.data / profiles.RESTORE_RECORD_NAME).read_bytes()
    assert disk.start(enabled=False) == restore_lock.Outcome(dormant=3)
    assert tree(disk.layout.profiles) == profile_tree
    assert (disk.data / profiles.RESTORE_RECORD_NAME).read_bytes() == record_bytes
    assert len(guard_lines(log_scan)) == 4


def test_an_unreadable_dormant_profile_is_quarantined(tmp_path, log_scan):
    """Plan 8.4 C, as part of the dormant handling: a directory that cannot be opened cannot be proven revoked, so it
    is quarantined (never served, delete only); the others are revoked."""
    disk = dormant_disk(tmp_path, log_scan)
    break_state(disk.layout.profile(B), 'an unknown key')
    outcome = disk.start(enabled=False)
    assert outcome.dormant == 2 and outcome.revoked == (A, C)
    assert [profiles.parse_quarantine_name(name)[0] for name in outcome.quarantined] == [B]
    assert profiles.scan_profiles(disk.layout).profiles == (A, C)


def test_a_dormant_revocation_that_never_reached_the_disk_stops_the_start(tmp_path, log_scan, monkeypatch):
    """Plan 8.4 E for the dormant handling (I13; HM-13b review S-2): the check reads every profile directory again from
    disk, not through the stores that wrote; a revocation its store reported done but never wrote (the old token still
    on disk) stops the start, as for a restore, although the dormant check is not the strict one. The next start
    revokes it."""
    disk = dormant_disk(tmp_path, log_scan)
    token = disk.tokens(A)[0]
    with monkeypatch.context() as patch:
        lying_revocation(patch, A)
        with pytest.raises(ConfigError):
            disk.start(enabled=False)
    assert disk.tokens(A)[0] == token is not None
    assert guard_lines(log_scan)[-1] == restore_lock.UNFINISHED % 'the check after revoking did not pass'
    assert disk.start(enabled=False) == restore_lock.Outcome(dormant=3, revoked=(A,))
    assert disk.tokens(A)[0] is None


def test_profile_data_without_a_profile_directory_is_dormant_with_none(tmp_path, log_scan):
    """An index whose directories are gone (or only profiles/ left): profile data, dormant, nothing to revoke: nothing
    written, nothing logged."""
    disk = dormant_disk(tmp_path, log_scan)
    for profile_id in (A, B, C):
        profiles.remove_profile_directory(disk.layout, profile_id)
    assert disk.start(enabled=False) == restore_lock.Outcome(dormant=0)
    assert not (disk.data / profiles.RESTORE_RECORD_NAME).exists() and guard_lines(log_scan) == []


def test_switched_off_with_profile_data_a_restore_revokes_everything_before_the_marker_goes(tmp_path, log_scan):
    """Plan 10.3 (開關關＋帳號資料＋標記 → 全撤銷才刪標記): the guard is not behind the switch: a restore with profile
    data revokes the default profile too (DQ-03 (b)) and every dormant profile; a start stopped right before the
    marker's removal has every token revoked already and the restore still visible; the next start finishes."""
    disk = dormant_disk(tmp_path, log_scan)
    backup = disk.backup()
    disk.restore(backup)
    counting = StopAt()
    assert disk.start_under(counting, enabled=False) == restore_lock.Outcome(
        restored=True, dormant=3, default_revoked=True, revoked=(A, B, C))
    last = counting.calls.index(('unlink', MARKER)) + 1  # the marker's removal: the guard's last change but one
    disk.restore(backup)
    with pytest.raises(Crash):
        disk.start_under(StopAt(last), enabled=False)
    assert MARKER in disk.names() and disk.detection(False).restored
    assert all(disk.tokens(profile_id)[0] is None for profile_id in (DEFAULT, A, B, C))
    assert disk.start(enabled=False).restored and MARKER not in disk.names()
    record = restore_lock.read_record(disk.data)
    assert record['restore'] is not None and record['dormant'] is not None


async def test_the_bootstrap_of_a_dormant_add_on_only_adds_dormant_profiles(tmp_path, log_scan, switched_off):
    """Contract 1.2: switched off with profile data, 8099 and 8081 are today's (no /api/profiles, no X-MCP-Profile,
    only the default profile served) and the bootstrap has one more field, dormant_profiles; a dormant profile's old
    token gets an unknown token's bytes."""
    disk = dormant_disk(tmp_path, log_scan, configured_default=True)
    old = disk.tokens(A)[0]
    async with production_runtime(PRODUCT, disk.data) as runtime:
        await settle(runtime, 'configured')
        async with runtime.admin() as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            assert set(boot) == BOOTSTRAP_COMMON | BOOTSTRAP_EXTRA[PRODUCT] | {'dormant_profiles'}
            assert boot['dormant_profiles'] == 3 and 'profile' not in boot
            assert (await admin.get('/api/profiles', headers=ADMIN)).status_code == 404
        async with runtime.mcp() as client:
            for path, headers in paths(old):
                response = await client.post(path, headers=headers, json=initialize_message())
                assert answer(response) == (NOT_FOUND if path.startswith('/private_') else BEARER_REQUIRED)
            token = disk.tokens()[0]
            response = await client.post(f'/private_{token}/mcp', headers=ACCEPT, json=initialize_message())
            assert response.status_code == 200


async def test_the_c1_m1_attack_sequence_leaves_no_old_token_valid(tmp_path, log_scan):
    """Plan 8.4 (C1-M1): version N switched on makes B; N+1 switches the product off (dormant: B revoked) and a daily
    backup K is made; N+2 switches it on again and B gets a new token after its check; K is restored, Supervisor puts
    N+1's image back (switched off): signals 1 and 2, the guard (not behind the switch) revokes B and, with profile
    data, the default profile; updated to N+2 again, neither B's tokens nor the default profile's old ones work."""
    disk = Disk(tmp_path, log_scan)
    assert disk.start(enabled=True) == restore_lock.Outcome()  # N: its first start, then B
    disk.add(B)
    first = disk.tokens(B)[0]
    default_before = disk.tokens()[0]
    assert disk.start(enabled=False) == restore_lock.Outcome(dormant=1, revoked=(B,))  # N+1
    daily = disk.backup()
    assert disk.start(enabled=True) == restore_lock.Outcome()  # N+2
    reissued = disk.rotate(B).token
    default_now = disk.rotate().token
    disk.restore(daily)  # Supervisor: K's data and N+1's image
    assert disk.start(enabled=False) == restore_lock.Outcome(restored=True, dormant=1, default_revoked=True,
                                                             revoked=(B,))
    children = Children()
    children.add(3000, MockChild(PRODUCT, disk.data))
    async with multi_profile_runtime(PRODUCT, disk.data, children=children) as runtime:  # N+2 again
        async with runtime.mcp() as client:
            for token in (first, reissued, default_before, default_now):
                for path, headers in paths(token):
                    response = await client.post(path, headers=headers, json=initialize_message())
                    assert answer(response) == (NOT_FOUND if path.startswith('/private_') else BEARER_REQUIRED)
    assert disk.tokens()[0] is None and disk.tokens(B)[0] is None


def test_switching_the_product_on_again_keeps_dormant_tokens_revoked(tmp_path, log_scan):
    """Plan 8.4: once switched on again, a dormant profile stays revoked until it is checked and a new token issued
    (HM-13c); the switched-on start without a restore changes nothing."""
    disk = dormant_disk(tmp_path, log_scan)
    disk.start(enabled=False)
    revoked = {profile_id: disk.tokens(profile_id) for profile_id in (A, B, C)}
    assert disk.start(enabled=True) == restore_lock.Outcome()
    assert {profile_id: disk.tokens(profile_id) for profile_id in (A, B, C)} == revoked
    assert json.loads((disk.data / profiles.RESTORE_RECORD_NAME).read_text())['dormant'] is not None
