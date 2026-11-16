"""HM-13b: the boot guard (multi-profile plan 8.4 "開機守門" A-F, 10.3, 12.3 HM-13b; contract 1.2, 3.5, 3.6, 4.1, 7, 8,
9 #20-#23, #67, #69, #101-#104; FM-04, 07, 13, 16, 79, 80, 118; I9; DQ-03 (b), DQ-39 (a); acceptance T-21).

restore_lock.guard() runs at every start of the management process, after the legacy migration and the default
profile's store, before any child starts or any listener exists (run_product, apps/n8n/run.py). These tests drive it
on a disk (tests/restore_guard_disk.py): HA backups and Supervisor restores of /data/mcp, the entrypoint's marker
(signal 1), the instance sentinel (signal 2). Not behind the multi-profile switch: a product that is not switched on
and has no profile data changes nothing but the marker of a restore; one with profile data, or switched on, gets the
whole guard. Dormant profiles are tests/test_dormant_profiles.py; "revoke all" is tests/test_revoke_all.py.

Every test runs under the HM-01 log scan (every token, child token, credential and label watched).
"""
import ast
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import features, operations, profile_runtime, profiles, restore_detect as rd, restore_lock, \
    run_product
from mcp_admin_core.config import ConfigError
from mcp_admin_core.products import ProductStore
from multi_profile_runtime import Children, multi_profile_runtime
from restore_guard_disk import DEFAULT, DISK_FULL, Disk, StopAt, break_state, newest_ctime, tree
from test_profile_routing import paths
from test_restore_detection import Crash, after_tick
from test_single_profile_golden import (ADMIN, BEARER_REQUIRED, GENUINE_CLIENT, NOT_FOUND, PRODUCTS as GOLDEN_PRODUCTS,
                                        MockChild, NoProcessSupervisor, answer, initialize_message)
from test_upgrade_zero_rewrite import runtime_sources

pytestmark = pytest.mark.usefixtures('log_scan')
ROOT = Path(__file__).resolve().parents[1]
PRODUCT = 'odoo'
A, B, C, Q = 'a' * 24, 'b' * 24, 'c' * 24, 'd' * 24
MARKER = profiles.RESTORE_MARKER_NAME
WHEN = datetime(2026, 11, 16, 9, 30, 15, tzinfo=timezone.utc)
STAMP = '20261116T093015Z'
RESTORED = (410, 'operation_restored')
LOGGER = 'mcp_admin_core.restore_lock'
RECORD_ROW = ['id', 'label', 'is_default', 'token', 'identity', 'policy', 'reviewed_at']
POLICY_KEYS = ['writes_enabled', 'disabled', 'enabled_write_tools', 'denied_operations', 'odoo_write_switches',
               'odoo_allowed_methods', 'n8n_session']


def fixed_now():
    return WHEN


def guard_lines(log_scan):
    """The guard's log lines (logger mcp_admin_core.restore_lock), as dispatched: (level, message)."""
    return [(record.levelname, record.getMessage()) for record in log_scan.records if record.name == LOGGER]


def record_of(disk):
    return restore_lock.read_record(disk.data)


def secrets_held(disk_states):
    """Every token, child token and stored credential value of states (dicts as stored), for the no-secret checks."""
    found = set()
    for value in disk_states:
        for key in ('token', 'child_token', 'backend_key', 'mcp_access_token'):
            if isinstance(value.get(key), str):
                found.add(value[key])
        for key, item in (value.get('connection') or {}).items():
            if key in ('password', 'api_key', 'gateway_api_key', 'dashboard_password', 'master_key', 'app_password',
                       'api_secret') and isinstance(item, str):
                found.add(item)
    return found


def with_profiles(tmp_path, log_scan, *, orphan=True, quarantine=True):
    """The default profile, A (indexed), B (an orphan) and an old quarantine directory of Q, made after the first
    switched-on start (it made the sentinel; profile data without its record reads as a restore, HM-13a)."""
    disk = Disk(tmp_path, log_scan)
    assert disk.start(enabled=True) == restore_lock.Outcome()  # the first switched-on start: the sentinel
    disk.add(A)
    if orphan:
        disk.add(B, indexed=False)
    if quarantine:
        disk.add(Q, indexed=False)
        os.rename(disk.layout.profile(Q), disk.layout.profiles / profiles.quarantine_name(Q, WHEN.replace(day=1)))
    assert disk.start(enabled=True) == restore_lock.Outcome()
    assert disk.detection(True) == rd.Detection(False, True, rd.CONSISTENT)
    return disk


# ---- a single-profile installation: today's, byte for byte ----

@pytest.mark.parametrize('product', GOLDEN_PRODUCTS)
def test_a_single_profile_installation_without_a_restore_is_left_alone(tmp_path, log_scan, product):
    """Not switched on, no profile data, no marker (every installation today): the guard looks up four names and
    changes nothing, not even a ctime, and logs nothing (plan 3.3: "沒有帳號資料時只多一次存在檢查")."""
    disk = Disk(tmp_path, log_scan, product)
    store = ProductStore(disk.data, product)
    try:
        after_tick(tmp_path, newest_ctime(disk.data))
        before = tree(disk.data)
        assert restore_lock.guard(store, product, enabled=False) == restore_lock.Outcome()
        assert tree(disk.data) == before
    finally:
        store.close()
    assert guard_lines(log_scan) == []


@pytest.mark.parametrize('product', GOLDEN_PRODUCTS)
def test_a_single_profile_restore_only_removes_the_marker(tmp_path, log_scan, product):
    """DQ-03 (b): a restore of an installation without profile data revokes nothing and leaves its state, receipts and
    every other entry exactly as restored; one WARNING says the token is back at its backup value; the marker goes. No
    sentinel, record or restore record is made (the product is not switched on)."""
    disk = Disk(tmp_path, log_scan, product)
    receipt = disk.receipt()
    disk.restore(disk.backup())
    store = ProductStore(disk.data, product)
    try:
        after_tick(tmp_path, newest_ctime(disk.data))
        before = tree(disk.data)
        assert restore_lock.guard(store, product, enabled=False) == restore_lock.Outcome(restored=True)
        after = tree(disk.data)
    finally:
        store.close()
    assert set(before) - set(after) == {MARKER} and set(after) <= set(before)
    assert {name: facts for name, facts in after.items() if name != '.'} == {
        name: facts for name, facts in before.items() if name not in ('.', MARKER)}
    assert disk.replay(receipt) == 'completed'
    assert guard_lines(log_scan) == [('WARNING', restore_lock.KEPT_NOTICE)]
    assert disk.start(enabled=False) == restore_lock.Outcome()  # the next start: nothing to do
    assert len(guard_lines(log_scan)) == 1


def test_a_single_profile_restore_whose_marker_cannot_be_removed_still_starts(tmp_path, log_scan, monkeypatch):
    """Without profile data nothing is revoked, so a marker that cannot be removed (a read-only or failing disk) stops
    nothing: one more line says so and the next start tries again (as the entrypoint starts without profile data when
    it cannot save the marker)."""
    disk = Disk(tmp_path, log_scan)
    disk.restore(disk.backup())
    real = os.unlink

    def refused(path, *args, **kwargs):
        if os.fspath(path) == MARKER:
            raise OSError(30, 'Read-only file system')
        return real(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(os, 'unlink', refused)
        assert disk.start(enabled=False) == restore_lock.Outcome(restored=True)
    assert MARKER in disk.names()
    assert guard_lines(log_scan) == [('WARNING', restore_lock.KEPT_NOTICE),
                                     ('WARNING', restore_lock.MARKER_LEFT % 'a marker could not be removed')]
    assert disk.start(enabled=False) == restore_lock.Outcome(restored=True) and MARKER not in disk.names()


# ---- DQ-03: the default profile ----

def test_a_switched_on_restore_without_profile_data_keeps_the_default_token(tmp_path, log_scan):
    """DQ-03 (b) (A2): a switched-on product restored without profile data keeps the default profile's state and
    receipts as restored (§8.8 #21, contract 9 #104); the record says so for the panel (HM-13c), the log says the token
    is back at its backup value; the sentinel is rebuilt and the marker removed."""
    disk = Disk(tmp_path, log_scan)
    assert disk.start(enabled=True) == restore_lock.Outcome()
    receipt = disk.receipt()
    backup = disk.backup()
    disk.rotate()  # after the backup: lost by the restore
    disk.restore(backup)
    restored = (disk.data / 'state.json').read_bytes()
    assert disk.start(enabled=True, now=fixed_now) == restore_lock.Outcome(restored=True)
    assert (disk.data / 'state.json').read_bytes() == restored
    assert disk.replay(receipt) == 'completed'
    assert MARKER not in disk.names() and disk.detection(True) == rd.Detection(False, True, rd.CONSISTENT)
    record = record_of(disk)
    assert record['restore'] == {'at': '2026-11-16T09:30:15+00:00', 'marker': True, 'sentinel': rd.MISMATCH}
    assert record['dormant'] is None and record['index'] == profiles.INDEX_ABSENT
    assert [(row['id'], row['token']) for row in record['profiles']] == [(DEFAULT, 'kept')]
    assert guard_lines(log_scan) == [('WARNING', restore_lock.KEPT_NOTICE)]
    assert disk.start(enabled=True) == restore_lock.Outcome()


def test_dq03_option_a_also_revokes_a_switched_on_default_profile(tmp_path, log_scan, monkeypatch):
    """DQ-03 (a), if it were chosen (DEFAULT_REVOKED_WHEN_SWITCHED_ON): every restore of a switched-on product revokes
    the default profile too, with a new child token and its receipts archived. A product that is not switched on and
    has no profile data is still only told (the plan's (a) is "開通的產品一律撤銷")."""
    monkeypatch.setattr(restore_lock, 'DEFAULT_REVOKED_WHEN_SWITCHED_ON', True)
    disk = Disk(tmp_path, log_scan)
    assert disk.start(enabled=True) == restore_lock.Outcome()
    receipt = disk.receipt()
    backup = disk.backup()
    token, child = disk.tokens()
    disk.restore(backup)
    assert disk.start(enabled=True) == restore_lock.Outcome(restored=True, default_revoked=True)
    now = disk.tokens()
    assert now[0] is None and now[1] not in (token, child)
    assert disk.state()['token_history'][0]['action'] == 'revoke'
    assert disk.replay(receipt) == RESTORED
    other = Disk(tmp_path / 'off', log_scan)
    before = (other.data / 'state.json').read_bytes()
    other.restore(other.backup())
    assert other.start(enabled=False) == restore_lock.Outcome(restored=True)
    assert (other.data / 'state.json').read_bytes() == before


# ---- a restore with profile data: A to F ----

@pytest.mark.parametrize('signals', ['both', 'sentinel only'])
def test_a_restore_with_profile_data_revokes_every_profile(tmp_path, log_scan, signals):
    """Plan 8.4 A-F with profile data on disk (DQ-03 (b): the default profile too): every token of S revoked (one
    history entry each), every child token new (none equal to anything the backup held, none shared), every receipt
    from before the restore answered 410 operation_restored (the restored journals archived as .restored), the record
    written without a single secret, the old quarantine directory only read, the sentinel rebuilt, the marker removed.
    The sentinel alone (no marker) is enough. The next start has nothing to do."""
    disk = with_profiles(tmp_path, log_scan)
    receipts = {where: disk.receipt(where) for where in (DEFAULT, A, 'index')}
    backup = disk.backup()
    held = disk.held()
    states = [disk.state(), disk.state(A), disk.state(B)]
    for where in (DEFAULT, A):
        disk.rotate(where)  # after the backup: lost by the restore
    lost = {where: disk.receipt(where) for where in (DEFAULT, A, 'index')}
    disk.restore(backup, marker=signals == 'both')
    outcome = disk.start(enabled=True, now=fixed_now)
    assert outcome == restore_lock.Outcome(restored=True, default_revoked=True, revoked=(A, B))
    children = set()
    for where in (DEFAULT, A, B):
        token, child = disk.tokens(where)
        assert token is None and child not in held and child not in children
        children.add(child)
    for where in (DEFAULT, A):
        assert disk.state(where)['token_history'][0]['action'] == 'revoke'
    for where in (DEFAULT, A, 'index'):
        assert disk.replay(receipts[where], where) == RESTORED
        assert disk.replay(lost[where], where) == RESTORED
    for config in (disk.data / 'state.json', disk.layout.profile(A) / 'state.json', disk.layout.index):
        archived = json.loads(config.with_name('.' + config.name + '.operations.json.restored').read_text())
        assert len(archived['receipts']) == 1
    assert not (disk.layout.profile(B) / '.state.json.operations.json').exists()  # it never had receipts
    assert MARKER not in disk.names() and disk.detection(True) == rd.Detection(False, True, rd.CONSISTENT)
    record = record_of(disk)
    assert record['restore'] == {'at': '2026-11-16T09:30:15+00:00', 'marker': signals == 'both',
                                 'sentinel': rd.MISMATCH}
    assert [(row['id'], row['label'], row['is_default'], row['token']) for row in record['profiles']] == [
        (DEFAULT, 'Default', True, 'revoked'), (A, 'Ledger Alpha', False, 'revoked'), (B, None, False, 'revoked')]
    for row in record['profiles']:
        assert list(row) == RECORD_ROW and row['reviewed_at'] is None and list(row['policy']) == POLICY_KEYS
    assert record['profiles'][1]['identity'] == {'url': states[1]['connection']['url'],
                                                 'database': states[1]['connection']['database'],
                                                 'username': states[1]['connection']['username']}
    quarantine = profiles.quarantine_name(Q, WHEN.replace(day=1))
    assert record['quarantined'] == [{'name': quarantine, 'id': Q, 'new': False}]
    assert record['profiles_directory'] == 'present' and record['other_entries'] == 0
    raw = (disk.data / profiles.RESTORE_RECORD_NAME).read_text()
    assert not [value for value in held | secrets_held(states) if value in raw]
    lines = [text for level, text in guard_lines(log_scan)]
    assert lines[-1] == restore_lock.REVOKED_NOTICE and len(lines) == 4
    assert {line.split(']')[0] for line in lines[:-1]} == {'restore guard [profile=default', 'restore guard '
                                                           '[profile=aaaaaaaa', 'restore guard [profile=bbbbbbbb'}
    assert disk.start(enabled=True) == restore_lock.Outcome()
    assert len(guard_lines(log_scan)) == 4


@pytest.mark.parametrize('kind', ['no writer lock', 'an unknown key', 'a second link', 'too large', 'another product',
                                  'no state', 'not JSON'])
def test_a_profile_that_cannot_be_opened_is_quarantined(tmp_path, log_scan, kind):
    """Plan 8.4 C: a profile directory the store cannot open, for any reason, is renamed
    profiles/.quarantine-<id>-<UTC> (never routed, delete only); the record lists it; the rest of the guard goes on."""
    disk = with_profiles(tmp_path, log_scan, orphan=False, quarantine=False)
    disk.add(B)
    disk.restore(disk.backup())
    break_state(disk.layout.profile(B), kind)  # after the copy: copytree would make a second link a file of its own
    outcome = disk.start(enabled=True, now=fixed_now)
    name = profiles.quarantine_name(B, WHEN)
    assert outcome == restore_lock.Outcome(restored=True, default_revoked=True, revoked=(A,), quarantined=(name,))
    scan = profiles.scan_profiles(disk.layout)
    assert scan.profiles == (A,) and scan.quarantined == (name,)
    assert record_of(disk)['quarantined'] == [{'name': name, 'id': B, 'new': True}]
    assert [row['id'] for row in record_of(disk)['profiles']] == [DEFAULT, A]
    assert ('WARNING', restore_lock.QUARANTINED % 'bbbbbbbb') in guard_lines(log_scan)


def test_a_second_quarantine_in_the_same_second_gets_its_own_name(tmp_path, log_scan):
    """HM-07 review S-15: the quarantine name never replaces anything at it (rename would replace an empty
    directory): the second one in the same second is <name>-2; both are quarantine directories."""
    disk = with_profiles(tmp_path, log_scan, orphan=False, quarantine=False)
    disk.add(B)
    first = disk.layout.profiles / profiles.quarantine_name(B, WHEN)
    first.mkdir()
    backup = disk.backup()
    break_state(backup / 'profiles' / B, 'no state')
    disk.restore(backup)
    outcome = disk.start(enabled=True, now=fixed_now)
    assert outcome.quarantined == (first.name + '-2',)
    assert profiles.parse_quarantine_name(first.name + '-2') == (B, STAMP + '-2')
    assert profiles.scan_profiles(disk.layout).quarantined == (first.name, first.name + '-2')


async def test_a_quarantined_profile_is_never_served_at_any_later_start(tmp_path, log_scan):
    """Plan 10.3: a state the guard could not read is quarantined and no later start routes it, restored or not: its
    token (still readable in the moved state) gets an unknown token's bytes; the second start leaves it as it is."""
    disk = with_profiles(tmp_path, log_scan, orphan=False, quarantine=False)
    disk.add(B)
    backup = disk.backup()
    token = disk.tokens(B)[0]
    break_state(backup / 'profiles' / B, 'no writer lock')
    disk.restore(backup)
    for start in range(2):
        children = Children()
        children.add(3000, MockChild(PRODUCT, disk.data))
        async with multi_profile_runtime(PRODUCT, disk.data, children=children) as runtime:
            assert runtime.manager.get(B) is None
            async with runtime.mcp() as client:
                for path, headers in paths(token):
                    response = await client.post(path, headers=headers, json=initialize_message())
                    assert answer(response) == (NOT_FOUND if path.startswith('/private_') else BEARER_REQUIRED)
        assert [profiles.parse_quarantine_name(name)[0] for name in disk.quarantines()] == [B]
        assert MARKER not in disk.names()


# ---- failures keep the restore visible and start nothing ----

def test_a_quarantine_that_cannot_be_made_keeps_the_restore_and_stops(tmp_path, log_scan, monkeypatch):
    """Plan 8.4 C: when the rename fails too, the marker stays and the start stops (ConfigError); the directory is
    left where it was, and a later start with a working rename finishes."""
    disk = with_profiles(tmp_path, log_scan, orphan=False, quarantine=False)
    disk.add(B)
    backup = disk.backup()
    break_state(backup / 'profiles' / B, 'not JSON')
    disk.restore(backup)
    real = os.rename

    def refused(source, target, *args, **kwargs):
        if '.quarantine-' in os.fspath(target):
            raise PermissionError(13, 'Permission denied')
        return real(source, target, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(os, 'rename', refused)
        with pytest.raises(ConfigError):
            disk.start(enabled=True)
    assert MARKER in disk.names() and disk.detection(True).restored
    assert profiles.scan_profiles(disk.layout).profiles == (A, B)
    assert ('WARNING', restore_lock.NOT_QUARANTINED % 'bbbbbbbb') in guard_lines(log_scan)
    assert guard_lines(log_scan)[-1] == ('WARNING', restore_lock.UNFINISHED % 'a quarantine could not be made')
    assert disk.start(enabled=True).quarantined
    assert MARKER not in disk.names()


def lying_revocation(monkeypatch, profile_id):
    """A store of profile_id whose token revocation reports success and writes nothing (a write that never reached
    the disk): what the independent check (E) is there for."""
    real = ProductStore.change_token

    def change_token(self, token, *, action):
        if self.directory.name == profile_id:
            return self.load(), True
        return real(self, token, action=action)
    monkeypatch.setattr(ProductStore, 'change_token', change_token)


def test_a_check_that_does_not_pass_keeps_the_restore_and_stops(tmp_path, log_scan, monkeypatch):
    """Plan 8.4 E: the guard reads every directory again from disk, not through the stores that wrote; a token that is
    not None there keeps the marker and stops the start."""
    disk = with_profiles(tmp_path, log_scan, quarantine=False)
    backup = disk.backup()
    token = disk.tokens(A)[0]
    disk.restore(backup)
    with monkeypatch.context() as patch:
        lying_revocation(patch, A)
        with pytest.raises(ConfigError):
            disk.start(enabled=True)
    assert MARKER in disk.names() and disk.detection(True).restored and disk.tokens(A)[0] == token
    assert guard_lines(log_scan)[-1] == ('WARNING', restore_lock.UNFINISHED % 'the check after revoking did not pass')
    assert disk.start(enabled=True).restored and disk.tokens(A)[0] is None


def test_a_default_profile_that_cannot_be_written_keeps_the_restore_and_stops(tmp_path, log_scan, monkeypatch):
    """Plan 8.4 B: a write of the default profile that fails keeps the marker and stops the start (the other profiles
    are revoked all the same: nothing that could be revoked is left); the next start finishes."""
    disk = with_profiles(tmp_path, log_scan, quarantine=False)
    disk.restore(disk.backup())
    real = ProductStore.change_token

    def change_token(self, token, *, action):
        if self.directory == disk.data:
            raise ConfigError('durable state write failed; manual recovery required')
        return real(self, token, action=action)
    with monkeypatch.context() as patch:
        patch.setattr(ProductStore, 'change_token', change_token)
        with pytest.raises(ConfigError):
            disk.start(enabled=True)
    assert MARKER in disk.names() and disk.tokens()[0] is not None
    assert disk.tokens(A)[0] is None and disk.tokens(B)[0] is None
    assert ('WARNING', restore_lock.NOT_REVOKED % ('default', 'ConfigError')) in guard_lines(log_scan)
    assert disk.start(enabled=True).default_revoked and disk.tokens()[0] is None


def test_a_record_that_cannot_be_saved_keeps_the_restore_and_stops(tmp_path, log_scan, monkeypatch):
    """Plan 8.4 D: the restore record not saved keeps the marker and stops the start."""
    disk = with_profiles(tmp_path, log_scan, quarantine=False)
    disk.restore(disk.backup())
    real = os.replace

    def refused(source, target, *args, **kwargs):
        if os.fspath(target).endswith(profiles.RESTORE_RECORD_NAME):
            raise OSError(5, 'Input/output error')
        return real(source, target, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(os, 'replace', refused)
        with pytest.raises(ConfigError):
            disk.start(enabled=True)
    assert MARKER in disk.names() and not (disk.data / profiles.RESTORE_RECORD_NAME).exists()
    assert not [name for name in disk.names() if name.startswith('.' + profiles.RESTORE_RECORD_NAME)]
    assert guard_lines(log_scan)[-1] == ('WARNING', restore_lock.UNFINISHED % 'the restore record could not be saved')
    assert disk.start(enabled=True).restored and record_of(disk)['restore'] is not None


def crash_disk(tmp_path, log_scan):
    """A restored disk for the fault injection: the default profile, A (indexed, with receipts), B (an orphan) and C
    (indexed, its writer lock missing in the backup: quarantined), receipts in three journals."""
    disk = with_profiles(tmp_path, log_scan, quarantine=False)
    disk.add(C)
    receipts = {where: disk.receipt(where) for where in (DEFAULT, A, 'index')}
    backup = disk.backup()
    break_state(backup / 'profiles' / C, 'no writer lock')
    return disk, backup, receipts, disk.held()


def finished(disk, held, receipts):
    """What a finished guard left: no restore to see, every token of S revoked, new and distinct child tokens, C
    quarantined once, every old receipt 410, every archive holding the backup's receipt, the record written."""
    assert MARKER not in disk.names() and disk.detection(True) == rd.Detection(False, True, rd.CONSISTENT)
    children = [disk.tokens(where)[1] for where in (DEFAULT, A, B)]
    assert all(disk.tokens(where)[0] is None for where in (DEFAULT, A, B))
    assert len(set(children)) == 3 and not set(children) & held
    assert [profiles.parse_quarantine_name(name)[0] for name in disk.quarantines()] == [C]
    assert profiles.scan_profiles(disk.layout).profiles == (A, B)
    for where, operation in receipts.items():
        assert disk.replay(operation, where) == RESTORED
        config = disk.layout.index if where == 'index' else disk.directory(where) / 'state.json'
        archive = json.loads(config.with_name('.' + config.name + '.operations.json.restored').read_text())
        assert list(archive['receipts']) == [operation]
    assert [row['id'] for row in record_of(disk)['profiles']] == [DEFAULT, A, B]


def test_a_start_stopped_anywhere_is_finished_by_the_next(tmp_path, log_scan):
    """Plan 8.4 F, 10.3 (故障注入：每一步中途中斷): the guard is stopped at every call that changes the disk, before the
    call and right after it; until the marker is gone the restore stays visible, and the next start finishes the
    job. A finished start's archives keep the backup's receipts (a rerun never archives the empty journal it wrote)."""
    disk, backup, receipts, held = crash_disk(tmp_path, log_scan)
    disk.restore(backup)
    counting = StopAt()
    disk.start_under(counting, enabled=True)
    finished(disk, held, receipts)
    total = counting.count
    assert total >= 40 and counting.calls[-2:] == [('unlink', MARKER), ('fsync', None)]
    for after in (False, True):
        for nth in range(1, total + 1):
            disk.restore(backup)
            with pytest.raises(Crash):
                disk.start_under(StopAt(nth, after=after), enabled=True)
            if MARKER in disk.names():
                assert disk.detection(True).restored
            else:  # stopped after the marker went: everything was done before
                assert (after, nth) in ((True, total - 1), (False, total), (True, total))
            disk.start(enabled=True)
            finished(disk, held, receipts)


def test_a_full_disk_stops_the_start_until_there_is_room(tmp_path, log_scan):
    """10.3 (磁碟滿): nothing can be created, written or synced: the start stops, the restore stays visible and no state
    or journal is lost (each is still the backup's); with room again the next start finishes."""
    disk, backup, receipts, held = crash_disk(tmp_path, log_scan)
    disk.restore(backup)
    states = {where: (disk.directory(where) / 'state.json').read_bytes() for where in (DEFAULT, A, B)}
    with pytest.raises(ConfigError):  # the start's own store was opened before the disk filled up
        disk.start_under(StopAt(fail={'open', 'write', 'fsync'}, error=DISK_FULL), enabled=True)
    assert MARKER in disk.names() and disk.detection(True).restored
    for where, raw in states.items():
        assert (disk.directory(where) / 'state.json').read_bytes() == raw
    for where, operation in receipts.items():
        assert disk.replay(operation, where) == 'completed'
    disk.start(enabled=True)
    finished(disk, held, receipts)


# ---- the receipts (FM-07; contract 3.5, 4.1, 9 #67) ----

def test_each_restore_keeps_one_archive_and_old_ids_answer_410(tmp_path, log_scan):
    """Every profile keeps one archive (.restored): a second restore replaces the first one's; ids of both timelines
    answer 410 operation_restored; a new id is a new operation; a journal the guard wrote and nothing used since is
    not archived again (its restored_before_ms moves forward)."""
    disk = with_profiles(tmp_path, log_scan, orphan=False, quarantine=False)
    first = disk.receipt(A)
    backup = disk.backup()
    disk.restore(backup)
    disk.start(enabled=True)
    config = disk.layout.profile(A) / 'state.json'
    journal = config.with_name('.state.json.operations.json')
    archive = config.with_name('.state.json.operations.json.restored')
    assert list(json.loads(archive.read_text())['receipts']) == [first]
    fresh = json.loads(journal.read_text())
    assert fresh['receipts'] == {} and fresh['restored_before_ms'] >= int(first.split('.')[0])
    second = disk.receipt(A)
    again = disk.backup()
    disk.restore(again)
    disk.start(enabled=True)
    assert list(json.loads(archive.read_text())['receipts']) == [second]
    assert [disk.replay(operation, A) for operation in (first, second)] == [RESTORED, RESTORED]
    assert disk.replay(f'{int(datetime.now(timezone.utc).timestamp() * 1000)}.{"n" * 16}', A) == 'new'
    disk.restore(disk.backup())  # nothing happened since the last restore: its journal holds no receipt
    before = json.loads(journal.read_text())['restored_before_ms']
    disk.start(enabled=True)
    assert list(json.loads(archive.read_text())['receipts']) == [second]
    assert json.loads(journal.read_text())['restored_before_ms'] > before


def test_a_slow_clock_never_lets_a_restored_id_through(tmp_path, log_scan):
    """The new journal's cutoff is never below the archived journal's newest operation id (as PaaS
    _read_journal_floor): a host clock behind the backup's receipts still refuses every one of them."""
    disk = with_profiles(tmp_path, log_scan, orphan=False, quarantine=False)
    operation = disk.receipt(A)
    disk.restore(disk.backup())
    behind = datetime.fromtimestamp(int(operation.split('.')[0]) / 1000 - 3600, timezone.utc)
    assert disk.start(enabled=True, now=lambda: behind).restored
    journal = json.loads((disk.layout.profile(A) / '.state.json.operations.json').read_text())
    assert journal['restored_before_ms'] == int(operation.split('.')[0])
    assert disk.replay(operation, A) == RESTORED


def test_a_far_future_id_in_a_restored_journal_moves_the_cutoff_one_retention_period_at_most(tmp_path, log_scan):
    """A forged backup whose journal holds an id years ahead cannot make every new id 410 for years: the cutoff follows
    the journal's newest id only up to one retention period (24 h) past the restore."""
    disk = Disk(tmp_path, log_scan)
    disk.receipt()
    journal = disk.data / '.state.json.operations.json'
    value = json.loads(journal.read_text())
    (key, item), = value['receipts'].items()
    value['receipts'] = {'9' * 13 + key[13:]: item}
    journal.write_text(json.dumps(value))
    journal.chmod(0o600)
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    assert operations.archive_for_restore(disk.data / 'state.json', now) == 'archived'
    assert json.loads(journal.read_text())['restored_before_ms'] == now + operations.TTL_MS


def test_an_archive_left_without_its_new_journal_gets_one(tmp_path, log_scan):
    """operations.archive_for_restore stopped between moving the journal and writing the new one: the next call writes
    the new one (old ids 410), and with neither a journal nor an archive it writes nothing."""
    disk = Disk(tmp_path, log_scan)
    config = disk.data / 'state.json'
    operation = disk.receipt()
    journal = config.with_name('.state.json.operations.json')
    os.replace(journal, journal.with_name(journal.name + '.restored'))
    assert operations.archive_for_restore(config, 2 ** 41) == 'renewed'
    assert disk.replay(operation) == RESTORED
    other = disk.layout.root / 'other.json'
    assert operations.archive_for_restore(other, 2 ** 41) == 'none' and not list(disk.data.glob('.other.json*'))


def test_a_journal_from_before_this_slice_still_reads(tmp_path, log_scan):
    """The new optional key restored_before_ms only appears in journals the guard wrote: every journal written before
    keeps reading as before, and a malformed value refuses the journal (503)."""
    disk = Disk(tmp_path, log_scan)
    operation = disk.receipt()
    assert disk.replay(operation) == 'completed'
    journal = disk.data / '.state.json.operations.json'
    value = json.loads(journal.read_text())
    assert set(value) == {'version', 'key', 'expired_before_ms', 'receipts'}
    for bad in (True, -1, 1.5, '1'):
        journal.write_text(json.dumps({**value, 'restored_before_ms': bad}))
        assert disk.replay(operation) == (503, 'operation_journal_unavailable')


# ---- UC-24 (plan 8.4: 三個會發生的情境) ----

def test_the_three_restore_situations_of_uc24(tmp_path, log_scan):
    """(i) a backup from before HM-13 restored, its old image started, then updated: no marker, no sentinel, no record,
    no profile data: the first switched-on start only makes the sentinel (nothing revoked; the documented gap, §8.8
    #69). (ii) Supervisor kept the current image for old data: the entrypoint marked the root-owned restore: guarded.
    (iii) a restore of the same version: marker and sentinel: guarded."""
    old = Disk(tmp_path / 'i', log_scan)
    token = old.tokens()
    assert old.start(enabled=True) == restore_lock.Outcome() and old.tokens() == token
    assert old.detection(True) == rd.Detection(False, True, rd.CONSISTENT)
    mixed = Disk(tmp_path / 'ii', log_scan)
    mixed.add(A)
    mixed.restore(mixed.backup())  # the old data, no sentinel yet; the current entrypoint's marker
    assert mixed.start(enabled=True) == restore_lock.Outcome(restored=True, default_revoked=True, revoked=(A,))
    same = with_profiles(tmp_path / 'iii', log_scan, orphan=False, quarantine=False)
    same.restore(same.backup())
    assert same.start(enabled=True) == restore_lock.Outcome(restored=True, default_revoked=True, revoked=(A,))


# ---- the guard's own names (HM-13a review SF-7) ----

@pytest.mark.parametrize('name', [profiles.SENTINEL_NAME, profiles.INSTANCE_RECORD_NAME,
                                  profiles.INSTANCE_RECORD_TEMPORARY_NAME, MARKER, profiles.REVOKE_ALL_MARKER_NAME])
def test_a_directory_at_one_of_the_guards_names_is_moved_aside(tmp_path, log_scan, name):
    """A restored directory at the sentinel's, its record's, the record's temporary, the marker's or the revoke-all
    marker's name (a forged backup: the restore repair accepts directories) is moved aside to
    <name>.quarantine-<UTC>, never deleted: the sentinel is rebuilt, the markers go, and the next start is an ordinary
    one (without it, every rebuild failed and the add-on never started again)."""
    disk = with_profiles(tmp_path, log_scan, orphan=False, quarantine=False)
    backup = disk.backup()
    target = backup / name
    if target.exists():
        target.unlink()
    target.mkdir()
    (target / 'kept').write_bytes(b'')
    disk.restore(backup, marker=name != MARKER)
    assert disk.start(enabled=True, now=fixed_now).restored
    assert (disk.data / (name + '.quarantine-' + STAMP) / 'kept').exists()
    if name in (profiles.SENTINEL_NAME, profiles.INSTANCE_RECORD_NAME):
        assert (disk.data / name).is_file()  # rebuilt
    else:
        assert name not in disk.names()
    assert disk.detection(True) == rd.Detection(False, True, rd.CONSISTENT)
    assert disk.start(enabled=True) == restore_lock.Outcome()


def test_an_unlistable_profiles_entry_is_reported_and_nothing_in_it_is_served(tmp_path, log_scan):
    """A restored profiles entry that is not a directory (contract 9 #102): nothing in it can be listed or opened (and
    HM-08 serves no token while profiles/ cannot be listed); the guard says so, revokes the default profile (profile
    data is on disk) and records it, instead of never starting."""
    disk = Disk(tmp_path, log_scan)
    assert disk.start(enabled=True) == restore_lock.Outcome()
    backup = disk.backup()
    (backup / 'profiles').write_bytes(b'not a directory')
    disk.restore(backup)
    assert disk.start(enabled=True) == restore_lock.Outcome(restored=True, default_revoked=True)
    assert record_of(disk)['profiles_directory'] == 'unlistable'
    assert ('WARNING', restore_lock.UNLISTABLE) in guard_lines(log_scan)


# ---- HM-10's interrupted deletion and index quarantine meet the guard ----

def test_the_guard_meets_an_interrupted_deletion_and_index_quarantine(tmp_path, log_scan):
    """HM-10 handed over: a backup taken while a deletion was half way (the directory without its state, the index
    still listing it, a pending profile.delete receipt beside the index), with an old quarantined index file and a
    pending "revoke all". The half-deleted directory is quarantined, every other profile revoked, the pending
    deletion's id answers 410, the quarantined index file is not touched, both markers go."""
    disk = with_profiles(tmp_path, log_scan, orphan=False, quarantine=False)
    disk.add(B)
    journal = operations.OperationJournal(disk.layout.index, results=operations.PROFILE_RESULTS, subjects=True)
    pending = f'{int(datetime.now(timezone.utc).timestamp() * 1000)}.{"p" * 16}'
    data, _, fingerprint = journal.inspect(pending, 'profile.delete', 'restore-guard-tester', B)
    journal.begin(pending, data, 'profile.delete', 'restore-guard-tester', fingerprint, subject=B)
    (disk.data / 'profiles.json.quarantine-20261101T000000Z').write_bytes(b'{"version": 1}')
    (disk.layout.profile(B) / 'state.json').unlink()  # the deletion was removing the directory
    os.close(os.open(disk.data / profiles.REVOKE_ALL_MARKER_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    backup = disk.backup()
    disk.restore(backup)
    before = (disk.data / 'profiles.json.quarantine-20261101T000000Z').read_bytes()
    outcome = disk.start(enabled=True, now=fixed_now)
    assert outcome == restore_lock.Outcome(restored=True, revoke_all=True, default_revoked=True, revoked=(A,),
                                           quarantined=(profiles.quarantine_name(B, WHEN),))
    assert disk.replay(pending, 'index') == RESTORED
    assert (disk.data / 'profiles.json.quarantine-20261101T000000Z').read_bytes() == before
    assert MARKER not in disk.names() and profiles.REVOKE_ALL_MARKER_NAME not in disk.names()


# ---- the order of a start (plan 8.4; contract 7 啟動順序) ----

async def run_until_listening(args, events, *, module=run_product):
    """run_product.run (or apps/n8n/run.py's run) with the outside replaced, until both listeners serve: events
    records the guard's start and end, every Supervisor made, every child started and every listener made."""
    class Recorded(NoProcessSupervisor):
        def __init__(self, *a, **k):
            events.append('supervisor')
            super().__init__(*a, **k)

        def _start_child(self):
            events.append('child')
            super()._start_child()

    class Listener(module.Listener):
        def __init__(self, config):
            events.append('listener')
            super().__init__(config)

        async def serve(self, sockets=None):
            events.append('serving')
            self.started = True
            while not self.should_exit:
                await asyncio.sleep(.01)
    real = restore_lock.guard

    def guard(*a, **k):
        events.append('guard')
        outcome = real(*a, **k)
        events.append('guarded')
        return outcome

    async def administrator(user):
        return user == ADMIN['X-Remote-User-Id']

    def client(*a, **k):
        k.setdefault('transport', httpx.MockTransport(MockChild(args.product, args.data)))
        return GENUINE_CLIENT(*a, **k)
    with pytest.MonkeyPatch.context() as patch:
        owner = profile_runtime if module is run_product else module
        patch.setattr(owner, 'Supervisor', Recorded)
        patch.setattr(owner.httpx, 'AsyncClient', client)
        patch.setattr(module, 'make_ha_admin_verifier', lambda: administrator)
        patch.setattr(module, 'Listener', Listener)
        patch.setattr(restore_lock, 'guard', guard)
        if module is not run_product:
            patch.setattr(module, 'prepare_catalog', lambda: None)
        task = asyncio.create_task(module.run(args))
        try:
            async with asyncio.timeout(15):
                while events.count('serving') < 2:
                    if task.done():
                        task.result()
                        raise AssertionError('the runtime ended before its listeners served')
                    await asyncio.sleep(.01)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize('switched_on', [True, False])
async def test_the_guard_finishes_before_any_child_or_listener(tmp_path, log_scan, monkeypatch, switched_on):
    """Contract 7: legacy migration, then the guard, then the default profile, then the additional ones; the guard has
    finished before any Supervisor exists, any child starts or any listener is made, switched on or off."""
    disk = with_profiles(tmp_path, log_scan, quarantine=False)
    disk.restore(disk.backup())
    if switched_on:
        monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset({PRODUCT}))
        monkeypatch.setattr(profile_runtime, 'STAGGER_SECONDS', 0.05)
    events = []
    args = SimpleNamespace(data=disk.data, product=PRODUCT, host='127.0.0.1', admin_port=8099, mcp_port=8081)
    await run_until_listening(args, events)
    assert events[:2] == ['guard', 'guarded'] and {'supervisor', 'listener'} <= set(events[2:])
    assert disk.tokens()[0] is None and MARKER not in disk.names()


async def test_n8n_runs_the_guard_before_its_child_and_listeners(tmp_path, log_scan):
    """apps/n8n/run.py too (not gated: every product's next release)."""
    import run as n8n_run
    disk = Disk(tmp_path, log_scan, 'n8n')
    disk.restore(disk.backup())
    events = []
    args = SimpleNamespace(data=disk.data, host='127.0.0.1', admin_port=8099, mcp_port=8081, product='n8n')
    await run_until_listening(args, events, module=n8n_run)
    assert events[:2] == ['guard', 'guarded'] and MARKER not in disk.names()


async def test_a_guard_that_does_not_finish_serves_nothing(tmp_path, log_scan, monkeypatch):
    """Plan 8.4 E (不過 → 保留標記、不開 listener): run_product.run raises ConfigError (main: "runtime unavailable")
    before any Supervisor or listener exists; the marker stays."""
    disk = with_profiles(tmp_path, log_scan, quarantine=False)
    disk.restore(disk.backup())
    monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset({PRODUCT}))
    lying_revocation(monkeypatch, A)
    events = []
    args = SimpleNamespace(data=disk.data, product=PRODUCT, host='127.0.0.1', admin_port=8099, mcp_port=8081)
    with pytest.raises(ConfigError):
        await run_until_listening(args, events)
    assert events == ['guard'] and MARKER in disk.names()


# ---- the sentinel is never chmodded or chowned (HM-13a's invariant; plan 8.4, 12.3) ----

# Every call that sets a mode, an owner or a time in the image's Python sources, reviewed (runtime_sources() of
# tests/test_upgrade_zero_rewrite.py): what each one targets, and why that is never the sentinel. A new call site fails
# here until it is reviewed and added.
REVIEWED = {
    ('apps/headscale/tests/test_headscale_child.py', 'save_state', 'chmod'): 'test code (never run by the add-on)',
    ('apps/headscale/tests/test_headscale_child.py', 'state_path', 'chmod'): 'test code (never run by the add-on)',
    ('apps/headscale/tests/test_headscale_child.py',
     'test_missing_symlink_duplicate_and_wrong_mode_state_fail_closed', 'chmod'): 'test code (never run by the add-on)',
    ('packages/mcp-admin-core/mcp_admin_core/config.py', 'Store.__init__', 'chmod'):
        "the store's own directory (/data/mcp, or profiles/<id>), never a file",
    ('packages/mcp-admin-core/mcp_admin_core/config.py', 'Store._owned_directory', 'fchmod'):
        "an additional profile's directory, through the descriptor it opened",
    ('packages/mcp-admin-core/mcp_admin_core/config.py', 'Store._owned_lock', 'fchmod'):
        "the store's .writer.lock, through its descriptor",
    ('packages/mcp-admin-core/mcp_admin_core/config.py', 'Store.load', 'fchmod'):
        "the store's state.json, through the descriptor it reads",
    ('packages/mcp-admin-core/mcp_admin_core/operations.py', 'OperationJournal._read', 'fchmod'):
        'the operation journal, through the descriptor it reads',
    ('packages/mcp-admin-core/mcp_admin_core/profiles.py', 'ensure_profiles_directory', 'fchmod'):
        'profiles/, through its descriptor',
    ('packages/mcp-admin-core/mcp_admin_core/profiles.py', 'write_index', 'fchmod'):
        "the index's new temporary file, through its descriptor",
    ('packaging/entrypoint.py', '_reown_restored', 'chmod'): 'the restore repair (a restore replaced the sentinel)',
    ('packaging/entrypoint.py', '_reown_restored', 'chown'): 'the restore repair (a restore replaced the sentinel)',
    ('packaging/entrypoint.py', '_reown_restored', 'fchmod'): 'the restore repair (a restore replaced the sentinel)',
    ('packaging/entrypoint.py', '_reown_restored', 'fchown'): 'the restore repair (a restore replaced the sentinel)',
    ('packaging/entrypoint.py', '_repair_restored', 'fchmod'): '/data/mcp itself, at the end of the restore repair',
    ('packaging/entrypoint.py', '_repair_restored', 'fchown'): '/data/mcp itself, at the end of the restore repair',
    ('packaging/entrypoint.py', 'prepare_data', 'fchown'): 'a /data/mcp it just created',
}
MODE_AND_OWNER = frozenset({'chmod', 'fchmod', 'lchmod', 'chown', 'fchown', 'lchown', 'utime', 'copymode',
                            'copystat', 'chflags', 'lchflags'})


def mode_and_owner_calls():
    """(file, enclosing function, call name) of every call named in MODE_AND_OWNER in the image's Python sources."""
    found = {}
    for path in runtime_sources():
        def visit(node, scope):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    visit(child, scope + (child.name,))
                    continue
                if isinstance(child, ast.Call):
                    callee = child.func
                    name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, 'id', None)
                    if name in MODE_AND_OWNER:
                        key = (str(path.relative_to(ROOT)), '.'.join(scope) or '<module>', name)
                        found[key] = found.get(key, 0) + 1
                visit(child, scope)
        visit(ast.parse(path.read_text(), str(path)), ())
    return found


def test_every_mode_and_owner_call_site_is_reviewed():
    """Plan 8.4 (HM-13b 加測試掃描所有 chmod／chown 呼叫點): the sentinel's ctime is its identity; every call that could
    change it by a mode, an owner or a time is listed here with its target. restore_lock and restore_detect have none."""
    found = mode_and_owner_calls()
    assert set(found) == set(REVIEWED) and set(found.values()) == {1}
    assert not [key for key in found if key[0].endswith(('restore_lock.py', 'restore_detect.py'))]


def recorded_targets(monkeypatch):
    """Every inode a mode, owner or time call is made on from now on, by any module (os is wrapped; pathlib's chmod
    goes through os.chmod)."""
    targets = []

    def wrapped(real, follow):
        def call(target, *args, **kwargs):
            try:
                if isinstance(target, int):
                    info = os.fstat(target)
                else:
                    info = os.stat(target, dir_fd=kwargs.get('dir_fd'),
                                   follow_symlinks=follow and kwargs.get('follow_symlinks', True))
                targets.append((info.st_dev, info.st_ino))
            except OSError:
                pass
            return real(target, *args, **kwargs)
        return call
    for name, follow in (('chmod', True), ('chown', True), ('utime', True), ('lchown', False), ('fchmod', True),
                         ('fchown', True), ('lchmod', False)):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, wrapped(getattr(os, name), follow))
    return targets


def sentinel_key(data):
    info = os.lstat(Path(data) / profiles.SENTINEL_NAME)
    return info.st_dev, info.st_ino


async def test_nothing_chmods_or_chowns_the_sentinel(tmp_path, log_scan, monkeypatch):
    """Every path that writes the data directory while the add-on runs or starts, with every mode, owner and time call
    recorded: the switched-on runtime with profiles (starts, token changes, a profile created and deleted through 8099),
    a "revoke all", a restore and its guard, a dormant start. The sentinel's inode is never a target, and after each
    phase it is still the file its record names (restore detection: consistent)."""
    from test_profile_admin_api import Panel, children_of, csrf_of
    disk = with_profiles(tmp_path, log_scan, orphan=False, quarantine=False)
    monkeypatch.setattr(profiles, 'port_occupied', lambda port: None)
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: None)
    monkeypatch.setattr(profiles, 'available_memory_mib', lambda: 4096)
    targets = recorded_targets(monkeypatch)
    key = sentinel_key(disk.data)  # each phase below checks the targets it made (an inode number freed is reused)
    async with multi_profile_runtime(PRODUCT, disk.data, children=children_of(disk.data, (A,))) as runtime:
        panel = Panel(runtime, await csrf_of(runtime))
        for profile_id in (DEFAULT, A):
            async with runtime.admin(profile_id) as admin:
                boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
                rotated = await admin.post('/api/token/rotate', headers={
                    **ADMIN, 'X-CSRF-Token': boot['csrf'], 'If-Match': '"' + boot['configuration']['revision'] + '"',
                    'Idempotency-Key': f'{int(datetime.now(timezone.utc).timestamp() * 1000)}.{"r" * 16}'})
                assert rotated.status_code == 200
                log_scan.watch(rotated.json()['token'])
        created = await panel.create('Kept Desk')
        assert created.status_code == 201, created.content
        log_scan.watch('Kept Desk', kind='name')
        assert (await panel.delete(created.json()['id'])).status_code == 200
    assert key not in targets and disk.detection(True).sentinel == rd.CONSISTENT
    targets.clear()
    store = ProductStore(disk.data, PRODUCT)
    try:
        assert {item.result for item in restore_lock.revoke_all(store, PRODUCT).results} == {'revoked'}
    finally:
        store.close()
    assert key not in targets and disk.detection(True).sentinel == rd.CONSISTENT
    disk.restore(disk.backup())
    disk.start(enabled=True)  # the restore made a new sentinel and the guard another: only consistency says anything
    assert disk.detection(True).sentinel == rd.CONSISTENT
    key = sentinel_key(disk.data)
    targets.clear()
    assert disk.start(enabled=False).dormant == 1
    assert key not in targets and disk.detection(False).sentinel == rd.CONSISTENT
