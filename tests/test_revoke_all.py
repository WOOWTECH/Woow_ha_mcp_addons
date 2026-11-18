"""HM-13b: "revoke all" (multi-profile plan 8.4 全部撤銷, C1-S6, 10.3; contract 3.1, 4.1, 9 #82, #120; FM-120).

restore_lock.revoke_all() is what HM-13c's route POST profiles/revoke-all runs: .revoke-all-pending saved durably
before any token is touched; every profile revoked (the default profile's included) with a new child token, in a fixed
order (the default profile, then the profile directories by id); the independent check of the boot guard's step E;
the marker removed only when every profile was revoked and the check passed. A profile that fails is reported failed
(the others are revoked all the same) and the marker stays, so the next start's guard finishes the job before anything
is served, whatever the switch says. A caller that holds profiles' stores open (HM-13c: the running manager's) passes
them; a directory whose writer lock someone else holds is never quarantined, only failed.

The disk is tests/restore_guard_disk.py; every test runs under the HM-01 log scan.
"""
import fcntl
import os

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import profiles, restore_detect as rd, restore_lock
from mcp_admin_core.config import ConfigError
from mcp_admin_core.products import ProductStore
from restore_guard_disk import DEFAULT, Disk, StopAt, guard_os, unlistable_once
from test_restore_detection import Crash

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'odoo'
A, B = 'a' * 24, 'b' * 24
PENDING = profiles.REVOKE_ALL_MARKER_NAME
ALL = (DEFAULT, A, B)


def disk_with_profiles(tmp_path, log_scan):
    disk = Disk(tmp_path, log_scan)
    assert disk.start(enabled=True) == restore_lock.Outcome()  # the sentinel, before any profile data
    disk.add(A)
    disk.add(B, indexed=False)
    return disk


def revoke_all(disk, proxy=None, **options):
    """revoke_all on the default profile's store, opened first (as the running add-on holds it); proxy: StopAt as the
    os of the guard's modules while it runs."""
    store = ProductStore(disk.data, PRODUCT)
    try:
        if proxy is None:
            return restore_lock.revoke_all(store, PRODUCT, **options)
        with guard_os(proxy):
            return restore_lock.revoke_all(store, PRODUCT, **options)
    finally:
        store.close()


def all_revoked(disk, before):
    children = [disk.tokens(where)[1] for where in ALL]
    assert all(disk.tokens(where)[0] is None for where in ALL)
    assert len(set(children)) == 3 and not set(children) & before


def test_revoke_all_marks_first_then_revokes_every_profile_then_clears(tmp_path, log_scan):
    """The marker is the first change and its removal comes after every state write; every token revoked (one history
    entry each), every child token new; receipts stay (not a restore); no restore record."""
    disk = disk_with_profiles(tmp_path, log_scan)
    receipt = disk.receipt(A)
    before = disk.held()
    counting = StopAt()
    done = revoke_all(disk, counting)
    assert done == restore_lock.RevokeAll((restore_lock.Revocation(DEFAULT, 'revoked'),
                                           restore_lock.Revocation(A, 'revoked'),
                                           restore_lock.Revocation(B, 'revoked')), True)
    assert counting.calls[0] == ('open', PENDING)
    replaced = [number for number, (name, _) in enumerate(counting.calls) if name == 'replace']
    assert counting.calls.index(('unlink', PENDING)) > max(replaced)
    all_revoked(disk, before)
    for where in ALL:
        assert disk.state(where)['token_history'][0]['action'] == 'revoke'
    assert disk.replay(receipt, A) == 'completed'
    assert PENDING not in disk.names() and not (disk.data / profiles.RESTORE_RECORD_NAME).exists()
    assert not restore_lock.revoke_all_pending(disk.data)


@pytest.mark.parametrize('switched_on', [True, False])
@pytest.mark.parametrize('failing', ALL)
def test_a_profile_that_fails_keeps_the_marker_and_the_next_start_finishes(tmp_path, log_scan, monkeypatch, failing,
                                                                          switched_on):
    """Plan 8.4 (全部撤銷第 k 個失敗): the k-th profile's write fails: it is failed, every other one revoked, the marker
    stays; the next start (switched on or off: the guard is not behind the switch) finishes before anything is
    served."""
    disk = disk_with_profiles(tmp_path, log_scan)
    before = disk.held()
    real = ProductStore.change_token

    def change_token(self, token, *, action):
        if self.directory == disk.directory(failing):
            raise ConfigError('durable state write failed; manual recovery required')
        return real(self, token, action=action)
    with monkeypatch.context() as patch:
        patch.setattr(ProductStore, 'change_token', change_token)
        done = revoke_all(disk)
    assert done.finished is False
    assert {item.profile_id: item.result for item in done.results} == {
        where: 'failed' if where == failing else 'revoked' for where in ALL}
    assert disk.tokens(failing)[0] is not None and PENDING in disk.names()
    assert restore_lock.revoke_all_pending(disk.data)
    assert disk.start(enabled=switched_on) == restore_lock.Outcome(
        revoke_all=True, default_revoked=True, revoked=(A, B), dormant=None if switched_on else 2)
    all_revoked(disk, before)
    assert PENDING not in disk.names()


@pytest.mark.parametrize('how', ['empty', 'garbage', 'stopped after it was created', 'a directory'])
def test_a_marker_left_half_written_still_finishes_at_the_next_start(tmp_path, log_scan, how):
    """Plan 10.3 (標記寫一半): whatever is at the marker's name (empty, any bytes, a start stopped before it was synced,
    even a directory) means "not finished": the next start revokes every profile and removes it (a directory is moved
    aside, never deleted)."""
    disk = disk_with_profiles(tmp_path, log_scan)
    before = disk.held()
    marker = disk.data / PENDING
    if how == 'empty':
        marker.write_bytes(b'')
    elif how == 'garbage':
        marker.write_bytes(b'\x00half')
    elif how == 'a directory':
        marker.mkdir()
    else:
        with pytest.raises(Crash):
            revoke_all(disk, StopAt(1, after=True))  # the marker created, nothing synced yet
        assert marker.exists() and disk.held() == before
    assert disk.start(enabled=True).revoke_all
    all_revoked(disk, before)
    assert PENDING not in disk.names()


def test_a_pending_revoke_all_of_a_single_profile_installation_is_finished(tmp_path, log_scan):
    """No profile data, switched off: a pending "revoke all" still revokes the default profile at the next start (the
    administrator asked for it), and no sentinel is made (the product is not active)."""
    disk = Disk(tmp_path, log_scan)
    os.close(os.open(disk.data / PENDING, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    assert disk.start(enabled=False) == restore_lock.Outcome(revoke_all=True, default_revoked=True)
    assert disk.tokens()[0] is None and PENDING not in disk.names()
    assert profiles.SENTINEL_NAME not in disk.names()
    assert rd.detect(disk.data, enabled=False) == rd.Detection(False, False, rd.INACTIVE)


def test_revoke_all_uses_the_stores_its_caller_holds(tmp_path, log_scan):
    """HM-13c's running manager holds every registered profile's store (its writer lock): revoke_all takes those, and a
    directory whose lock someone else holds is failed, never quarantined (its directory stays where it is)."""
    disk = disk_with_profiles(tmp_path, log_scan)
    held = disk.store(A)
    try:
        done = revoke_all(disk, stores={A: held})
        assert done.finished and disk.tokens(A)[0] is None
        lock = os.open(disk.layout.profile(B) / '.writer.lock', os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            done = revoke_all(disk, stores={A: held})
        finally:
            os.close(lock)
    finally:
        held.close()
    assert not done.finished and restore_lock.Revocation(B, 'failed') in done.results
    assert profiles.scan_profiles(disk.layout).profiles == (A, B) and PENDING in disk.names()


def test_a_profiles_directory_that_cannot_be_listed_keeps_the_marker(tmp_path, log_scan, monkeypatch):
    """HM-13b review MF-2: profiles/ cannot be listed for a while (EMFILE, EIO, ENOMEM ...). "Revoke all" still revokes
    the default profile and every store its caller holds (each one in results), but it has not finished: the marker
    stays (what it could not list may hold a valid token: here the orphan B), and the next start finishes the job
    before anything is served."""
    disk = disk_with_profiles(tmp_path, log_scan)
    before = disk.held()
    token = disk.tokens(B)[0]
    held = disk.store(A)
    try:
        with monkeypatch.context() as patch:
            unlistable_once(patch)
            done = revoke_all(disk, stores={A: held})
    finally:
        held.close()
    assert done == restore_lock.RevokeAll((restore_lock.Revocation(DEFAULT, 'revoked'),
                                           restore_lock.Revocation(A, 'revoked')), False)
    assert disk.tokens()[0] is None and disk.tokens(A)[0] is None and disk.tokens(B)[0] == token is not None
    assert PENDING in disk.names() and restore_lock.revoke_all_pending(disk.data)
    assert disk.start(enabled=True) == restore_lock.Outcome(revoke_all=True, default_revoked=True, revoked=(A, B))
    all_revoked(disk, before)
    assert PENDING not in disk.names()


def test_a_revocation_that_never_reached_the_disk_is_failed_whatever_else_failed(tmp_path, log_scan, monkeypatch):
    """Step E runs whatever failed before it: A's store reports its revocation done but never wrote it while B's write
    fails; both are failed in results (HM-13c answers 503 for each until a retry succeeds), not A revoked."""
    disk = disk_with_profiles(tmp_path, log_scan)
    lying = disk.tokens(A)[0]
    real = ProductStore.change_token

    def change_token(self, token, *, action):
        if self.directory.name == A:
            return self.load(), True
        if self.directory.name == B:
            raise ConfigError('durable state write failed; manual recovery required')
        return real(self, token, action=action)
    with monkeypatch.context() as patch:
        patch.setattr(ProductStore, 'change_token', change_token)
        done = revoke_all(disk)
    assert done == restore_lock.RevokeAll((restore_lock.Revocation(DEFAULT, 'revoked'),
                                           restore_lock.Revocation(A, 'failed'),
                                           restore_lock.Revocation(B, 'failed')), False)
    assert disk.tokens(A)[0] == lying and PENDING in disk.names()


def test_revoke_all_refuses_a_store_that_is_not_an_additional_profiles(tmp_path, log_scan):
    """stores holds additional profiles only (the default profile's store is its own argument): anything else is
    refused before the marker or any token is touched."""
    disk = disk_with_profiles(tmp_path, log_scan)
    held = disk.store(A)
    try:
        for stores in ({DEFAULT: held}, {'A' * 24: held}):
            with pytest.raises(ValueError):
                revoke_all(disk, stores=stores)
    finally:
        held.close()
    assert PENDING not in disk.names() and disk.tokens()[0] is not None and disk.tokens(A)[0] is not None


def test_a_revoke_all_whose_check_does_not_pass_keeps_its_marker(tmp_path, log_scan, monkeypatch):
    """The independent check (step E) reads every state from disk: a revocation that never reached it fails that
    profile and keeps the marker."""
    disk = disk_with_profiles(tmp_path, log_scan)
    real = ProductStore.change_token

    def lying(self, token, *, action):
        if self.directory.name == A:
            return self.load(), True
        return real(self, token, action=action)
    with monkeypatch.context() as patch:
        patch.setattr(ProductStore, 'change_token', lying)
        done = revoke_all(disk)
    assert not done.finished and restore_lock.Revocation(A, 'failed') in done.results
    assert PENDING in disk.names() and disk.tokens(A)[0] is not None


def test_a_failure_the_store_reports_keeps_the_marker_even_when_the_disk_shows_it_done(tmp_path, log_scan, monkeypatch):
    """A store write that fails after its new state was put in place (the directory's fsync, say) leaves the disk
    revoked but the outcome unknown: that profile is failed and the marker stays although the independent check passes;
    the next start does it again and removes the marker."""
    disk = disk_with_profiles(tmp_path, log_scan)
    before = disk.held()
    real = ProductStore.update

    def update(self, **changes):
        updated = real(self, **changes)
        if self.directory.name == A and 'child_token' in changes:
            raise ConfigError('durable state write failed; manual recovery required')
        return updated
    with monkeypatch.context() as patch:
        patch.setattr(ProductStore, 'update', update)
        done = revoke_all(disk)
    assert not done.finished and restore_lock.Revocation(A, 'failed') in done.results
    assert disk.tokens(A)[0] is None and disk.tokens(A)[1] not in before and PENDING in disk.names()
    assert disk.start(enabled=True).revoke_all and PENDING not in disk.names()
    all_revoked(disk, before)
