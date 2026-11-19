"""HM-13c: the restore review, "revoke all" and the quarantine directories on 8099, and the panel's restore notice
(multi-profile plan 6 還原與休眠核對卡, 7.4, 8.4 全部撤銷 / 核對後才重發, 10.3, 12.3 HM-13c; contract 1.2, 1.3, 3.1,
3.5, 3.6, 4.1, 4.2, 9 #24, #58, #67, #82, #121-#123; FM-79, 80, 120, 126; I9, I13; DQ-03 (b), DQ-13, DQ-14; T-21).

- The restore notice (the owner's decision of 2026-11-16 on the HM-13b review's Q-1: DQ-03 (b) as written, "面板與
  log 提示"; not behind the switch): a restore that keeps the default profile's token (no profile data) leaves
  restore-notice.json (only its time) before the marker goes; the bootstrap carries "restore_notice" until the token
  changes (token/rotate, a token/revoke that revokes it, "revoke all"); the token stays as restored. An installation
  that was never restored answers as before, byte for byte (HM-01's golden regression and contract freezes, unchanged,
  and the cases here).
- Every journal a restore handles gets a new one, also where the backup had none (a lost operation id answers 410).
- Switched on: GET profiles/restore-record; POST profiles/<id>/restore-review (If-Match, Idempotency-Key); a
  token/rotate waits for the review of a profile whose token the guard revoked (409 restore_review_required);
  "revoke all" (POST profiles/revoke-all) under every lock, in a worker thread, its k-th profile failing (409
  operation_outcome_unknown with the results, 503 on 8081 for its old token until a "revoke all" finishes); the
  quarantine directories listed and deleted only.

Every case runs under the HM-01 log scan (tokens, child tokens, credentials and labels watched), in process: the guard
on a disk (tests/restore_guard_disk.py), the production runtime (tests/test_single_profile_golden.py,
tests/multi_profile_runtime.py; NoProcessSupervisor, the children behind one MockTransport).
"""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import stat
import threading

import httpx
import pytest

from admin_write_headers import reviewed_headers
from log_scan import log_scan  # noqa: F401  (fixture)
from switch_modes import switched_off  # noqa: F401  (fixture: HM-23, the switch a test pins)
from mcp_admin_core import features, operations, profile_admin, profiles, restore_detect as rd, restore_lock
from mcp_admin_core.config import ConfigError
from mcp_admin_core.products import ProductStore
from multi_profile_runtime import create_profile, multi_profile_runtime, stored
from restore_guard_disk import DEFAULT, Disk, StopAt, newest_ctime, tree
from test_profile_admin_api import (LABELS, Panel, children_of, code_of, csrf_of, operation_key, setup, tree_of,
                                    watch)
from test_odoo_identity_rotation import (NEW_PASSWORD, REBOUND, REFUSALS, Journal, opened_by, record_writes,
                                         save as backend_save, warnings_of as rebind_warnings,
                                         watch as watch_identity)
from test_restore_detection import Crash, after_tick
from test_single_profile_golden import (ACCEPT, ADMIN, BEARER_REQUIRED, BOOTSTRAP_COMMON, BOOTSTRAP_EXTRA,
                                        GENUINE_CLIENT, INGRESS, NOT_FOUND, PRODUCTS as GOLDEN_PRODUCTS, answer,
                                        configure, initialize_message, production_runtime, settle)

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'odoo'
B, C, D = 'b' * 24, 'c' * 24, 'd' * 24
MARKER = profiles.RESTORE_MARKER_NAME
NOTICE = profiles.RESTORE_NOTICE_NAME
PENDING = profiles.REVOKE_ALL_MARKER_NAME
LOGGER = 'mcp_admin_core.restore_lock'
ADMIN_LOGGER = 'mcp_admin_core.profile_admin'
STATE_UNAVAILABLE = (503, b'{"error":"state unavailable"}')
REFUSED = (403, b'{"error":"request denied"}')
# Every product run_product or apps/n8n/run.py starts (the golden regression's eight and Odoo Manage).
EVERY_PRODUCT = (*GOLDEN_PRODUCTS, 'odoo-manage')


def guard_clock():
    """(when, clock): the next whole second after now (HM-13b review MF-1: never a fixed date)."""
    when = (datetime.now(timezone.utc) + timedelta(seconds=1)).replace(microsecond=0)
    return when, (lambda: when)


def guard_lines(log_scan):
    return [(record.levelname, record.getMessage()) for record in log_scan.records if record.name == LOGGER]


def mark_restored(data):
    """The entrypoint's marker of a restore (signal 1; HM-13a), as a Supervisor restore leaves it."""
    os.close(os.open(Path(data) / MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))


def notice_of(data):
    return json.loads((Path(data) / NOTICE).read_text())


def private_file(path):
    info = os.lstat(path)
    return (stat.S_ISREG(info.st_mode), info.st_nlink, info.st_uid, stat.S_IMODE(info.st_mode)) == (
        True, 1, os.geteuid(), 0o600)


# ---- the restore notice of a single-profile installation (DQ-03 (b); not behind the switch) ----

@pytest.mark.parametrize('product', EVERY_PRODUCT)
def test_a_single_profile_restore_leaves_the_panel_notice_and_keeps_the_token(tmp_path, log_scan, product):
    """DQ-03 (b) as the owner decided on 2026-11-16 (HM-13b review Q-1): nothing is revoked and the state, its receipts
    and every restored entry stay exactly as restored; restore-notice.json ({"version": 1, "at": <UTC seconds>}, a
    private file of this uid) is the only new entry, and the marker goes. No sentinel, record or restore record."""
    disk = Disk(tmp_path, log_scan, product)
    receipt = disk.receipt()
    disk.restore(disk.backup())
    store = ProductStore(disk.data, product)  # as run_product opens it (its read chmods the state: its ctime)
    try:
        after_tick(tmp_path, newest_ctime(disk.data))
        restored = tree(disk.data)
        when, clock = guard_clock()
        assert restore_lock.guard(store, product, enabled=False, now=clock) == restore_lock.Outcome(restored=True)
        after = tree(disk.data)
    finally:
        store.close()
    assert set(after) - set(restored) == {NOTICE} and set(restored) - set(after) == {MARKER}
    assert {name: facts for name, facts in after.items() if name not in ('.', NOTICE)} == {
        name: facts for name, facts in restored.items() if name not in ('.', MARKER)}
    assert notice_of(disk.data) == {'version': 1, 'at': when.isoformat(timespec='seconds')}
    assert private_file(disk.data / NOTICE)
    assert restore_lock.read_notice(disk.data) == {'at': when.isoformat(timespec='seconds')}
    assert disk.replay(receipt) == 'completed'  # contract 9 #121: the receipts as restored
    assert guard_lines(log_scan) == [('WARNING', restore_lock.KEPT_NOTICE)]
    for name in (profiles.SENTINEL_NAME, profiles.INSTANCE_RECORD_NAME, profiles.RESTORE_RECORD_NAME):
        assert name not in disk.names()
    saved = (disk.data / NOTICE).read_bytes()
    assert disk.start(enabled=False) == restore_lock.Outcome()  # the next start: nothing to do, the notice stays
    assert sorted(after) == sorted(tree(disk.data)) and (disk.data / NOTICE).read_bytes() == saved


def test_without_a_notice_a_start_only_looks_the_name_up(tmp_path, log_scan):
    """An installation that was never restored: read_notice finds nothing, writes nothing and touches nothing (not even
    a ctime), and nothing that is not one this writes counts as a notice."""
    disk = Disk(tmp_path, log_scan)
    before = tree(disk.data)
    assert restore_lock.read_notice(disk.data) is None
    assert tree(disk.data) == before
    for raw in (b'', b'{}', b'{"version": 1}', b'{"version": 2, "at": "2026-11-16T09:30:15+00:00"}',
                b'{"version": 1, "at": "yesterday"}', b'{"at": "2026-11-16T09:30:15+00:00", "version": 1}',
                b'{"version": 1, "at": "2026-11-16T09:30:15+00:00", "x": 1}', b'not json'):
        (disk.data / NOTICE).write_bytes(raw)
        assert restore_lock.read_notice(disk.data) is None, raw
    (disk.data / NOTICE).unlink()
    (disk.data / NOTICE).mkdir()
    assert restore_lock.read_notice(disk.data) is None


def test_a_notice_that_cannot_be_saved_keeps_the_marker_and_still_starts(tmp_path, log_scan, monkeypatch):
    """Without profile data nothing is revoked, so a notice that cannot be saved (a full or read-only disk) stops
    nothing: the marker stays (one more line says so) and the next start saves the notice and removes the marker."""
    disk = Disk(tmp_path, log_scan)
    disk.restore(disk.backup())
    real = restore_lock._write_json

    def full(root, name, value, limit):
        if name == NOTICE:
            raise OSError(28, 'No space left on device')
        return real(root, name, value, limit)
    with monkeypatch.context() as patch:
        patch.setattr(restore_lock, '_write_json', full)
        assert disk.start(enabled=False) == restore_lock.Outcome(restored=True)
    assert MARKER in disk.names() and NOTICE not in disk.names()
    assert guard_lines(log_scan) == [('WARNING', restore_lock.KEPT_NOTICE),
                                     ('WARNING', restore_lock.MARKER_LEFT % 'the panel notice could not be saved')]
    assert disk.start(enabled=False) == restore_lock.Outcome(restored=True)
    assert MARKER not in disk.names() and restore_lock.read_notice(disk.data) is not None


@pytest.mark.parametrize('enabled', [False, True])
def test_a_start_stopped_anywhere_on_the_way_saves_the_notice_at_the_next(tmp_path, log_scan, enabled):
    """The notice is saved before the marker goes, each step durable: a start stopped before or after any call that
    changes the disk leaves either the marker (the next start saves the notice again) or both; never neither. Switched
    on without profile data too (HM-13c review S-1): there the sentinel is rebuilt before the marker goes, so a start
    that removed the marker without the notice would never see the restore again."""
    disk = Disk(tmp_path, log_scan)
    if enabled:
        assert disk.start(enabled=True) == restore_lock.Outcome()  # the first switched-on start's sentinel
    backup = disk.backup()
    counting = StopAt()
    disk.restore(backup)
    disk.start_under(counting, enabled=enabled)
    assert counting.count >= 4
    for nth in range(1, counting.count + 1):
        for after in (False, True):
            disk.restore(backup)
            with pytest.raises(Crash):
                disk.start_under(StopAt(nth, after=after), enabled=enabled)
            assert MARKER in disk.names() or restore_lock.read_notice(disk.data) is not None, (nth, after)
            disk.start(enabled=enabled)
            assert MARKER not in disk.names() and restore_lock.read_notice(disk.data) is not None, (nth, after)
            # A temporary a stop left behind is never read (contract 8, as the record's).


def test_a_directory_at_the_notices_name_is_moved_aside(tmp_path, log_scan):
    """A restored directory at the notice's name (a forged backup: the restore repair accepts directories) is moved
    aside to <name>.quarantine-<UTC>, never deleted, and the notice is saved (contract 9 #120)."""
    disk = Disk(tmp_path, log_scan)
    backup = disk.backup()
    (backup / NOTICE).mkdir()
    (backup / NOTICE / 'kept').write_bytes(b'')
    disk.restore(backup)
    when, clock = guard_clock()
    assert disk.start(enabled=False, now=clock) == restore_lock.Outcome(restored=True)
    aside = NOTICE + '.quarantine-' + when.strftime('%Y%m%dT%H%M%SZ')
    assert (disk.data / aside / 'kept').exists() and private_file(disk.data / NOTICE)
    assert ('WARNING', restore_lock.SET_ASIDE % (NOTICE, aside)) in guard_lines(log_scan)


def test_a_switched_on_restore_without_profile_data_leaves_the_notice_too(tmp_path, log_scan):
    """Switched on, no profile data (HM-13a's leftover marker at the first switched-on start, or a product nobody
    added a profile to): the default profile is kept (DQ-03 (b)); the record says so and the notice is saved, before
    the marker goes."""
    disk = Disk(tmp_path, log_scan)
    assert disk.start(enabled=True) == restore_lock.Outcome()
    disk.restore(disk.backup())
    when, clock = guard_clock()
    assert disk.start(enabled=True, now=clock) == restore_lock.Outcome(restored=True)
    assert restore_lock.read_notice(disk.data) == {'at': when.isoformat(timespec='seconds')}
    assert [(row['id'], row['token']) for row in restore_lock.read_record(disk.data)['profiles']] == [(DEFAULT, 'kept')]
    assert MARKER not in disk.names()


@pytest.mark.parametrize('cause', ['a restore with profile data', 'a pending revoke all'])
def test_a_guard_that_revokes_the_default_profile_removes_a_notice(tmp_path, log_scan, cause):
    """A notice the backup brought back (it was taken while a notice was shown) or an earlier start left is not true
    once the default profile's token is revoked: the guard removes it with the markers."""
    disk = Disk(tmp_path, log_scan)
    disk.restore(disk.backup())
    disk.start(enabled=False)
    assert restore_lock.read_notice(disk.data) is not None
    if cause == 'a restore with profile data':
        assert disk.start(enabled=True) == restore_lock.Outcome()  # switched on: the sentinel, before profile data
        disk.add(B)
        disk.restore(disk.backup())
        assert disk.start(enabled=True).default_revoked
    else:
        os.close(os.open(disk.data / PENDING, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        assert disk.start(enabled=False) == restore_lock.Outcome(revoke_all=True, default_revoked=True)
    assert NOTICE not in disk.names() and disk.tokens()[0] is None


# ---- receipts: every journal a restore handles is new (contract 3.5, 9 #67) ----

def test_a_restore_gives_every_journal_it_handles_a_new_one_even_without_one(tmp_path, log_scan):
    """The backup was made before B, an orphan, and the index ever had a receipt: the operations made after it are
    lost with the restore, and their ids answer 410 operation_restored, not as new operations (PaaS: every
    configuration gets a new journal). With profile data the default profile's journal is renewed as well."""
    disk = Disk(tmp_path, log_scan)
    assert disk.start(enabled=True) == restore_lock.Outcome()
    disk.add(B, indexed=False)
    backup = disk.backup()
    assert not (disk.layout.profile(B) / '.state.json.operations.json').exists()
    lost = {where: disk.receipt(where) for where in (DEFAULT, B, 'index')}  # after the backup
    disk.restore(backup)
    when, clock = guard_clock()
    disk.start(enabled=True, now=clock)
    for where in (DEFAULT, B, 'index'):
        assert disk.replay(lost[where], where) == (410, 'operation_restored'), where
    journal = json.loads((disk.layout.profile(B) / '.state.json.operations.json').read_text())
    assert journal['receipts'] == {} and journal['restored_before_ms'] >= int(when.timestamp() * 1000)
    assert not (disk.layout.profile(B) / '.state.json.operations.json.restored').exists()


def test_without_profile_data_the_default_profiles_receipts_stay_as_restored(tmp_path, log_scan):
    """Contract 9 #121 (DQ-03 (b)): a single-profile restore keeps the default profile's journal as restored, switched
    on or not, also when it had none: no journal is written for it."""
    for enabled in (False, True):
        disk = Disk(tmp_path / str(enabled), log_scan)
        if enabled:
            disk.start(enabled=True)
        backup = disk.backup()
        disk.restore(backup)
        disk.start(enabled=enabled)
        assert not (disk.data / '.state.json.operations.json').exists()


# ---- the panel's notice in the production runtime: the bootstrap only, until the token changes ----

def restored_copy(tmp_path, product, name):
    """A configured data directory of product, restored (its marker saved), under tmp_path/name."""
    data = tmp_path / name / 'data'
    configure(data, product)
    mark_restored(data)
    return data


def comparable(body):
    """A bootstrap without what differs between two starts: the CSRF value, the server time, the health counters and
    the revisions (process-local HMACs with a key of their own: contract 3.5)."""
    found = {key: value for key, value in body.items() if key not in ('csrf', 'operation_contract', 'health')}
    found['configuration'] = {key: value for key, value in body['configuration'].items()
                              if key not in ('revision', 'saved_revision', 'applied_revision')}
    return found


@pytest.mark.parametrize('product', GOLDEN_PRODUCTS)
async def test_after_a_single_profile_restore_the_bootstrap_only_adds_the_notice(tmp_path, log_scan, product,
                                                                                 switched_off):
    """The production runtime of every product, switched off: the same data restored or not. Restored, the bootstrap
    has exactly one key more, restore_notice ({"at"}), and every other key the same value; the token is kept (both
    connection paths serve it). The same start without a restore: today's keys (HM-01's golden regression)."""
    plain = tmp_path / 'plain' / 'data'
    configure(plain, product)
    shutil.copytree(plain, tmp_path / 'restored' / 'data', symlinks=True)
    data = tmp_path / 'restored' / 'data'
    mark_restored(data)
    state = stored(plain)
    log_scan.watch(state['token'], state['child_token'])
    bodies = {}
    for name, where in (('plain', plain), ('restored', data)):
        async with production_runtime(product, where) as runtime:
            await settle(runtime, 'configured')
            async with runtime.admin() as admin:
                bodies[name] = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            async with runtime.mcp() as client:
                for path, headers in (('/mcp', {**ACCEPT, 'Authorization': 'Bearer ' + state['token']}),
                                      (f'/private_{state["token"]}/mcp', ACCEPT)):
                    response = await client.post(path, headers=headers, json=initialize_message())
                    assert response.status_code == 200, (name, path.replace(state['token'], '<token>'))
    expected = BOOTSTRAP_COMMON | BOOTSTRAP_EXTRA.get(product, set())
    assert set(bodies['plain']) == expected
    assert set(bodies['restored']) == expected | {'restore_notice'}
    assert set(bodies['restored']['restore_notice']) == {'at'}
    assert bodies['restored']['restore_notice'] == restore_lock.read_notice(data)
    assert comparable({k: v for k, v in bodies['restored'].items() if k != 'restore_notice'}) == comparable(
        bodies['plain'])
    assert stored(data) == state  # nothing revoked: the token as restored


@pytest.mark.parametrize('change', ['token/rotate', 'token/revoke'])
@pytest.mark.parametrize('product', ['odoo', 'n8n'])
async def test_the_next_token_change_ends_the_notice(tmp_path, log_scan, product, change):
    """The notice shows until the default profile's token changes: a token/rotate, or a token/revoke that revokes it,
    removes restore-notice.json and the bootstrap's restore_notice (the answers of both are today's); the next start
    shows none."""
    data = restored_copy(tmp_path, product, 'one')
    log_scan.watch(stored(data)['token'], stored(data)['child_token'])
    async with production_runtime(product, data) as runtime:
        await settle(runtime, 'configured')
        async with runtime.admin() as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            assert 'restore_notice' in boot
            changed = await admin.post('/api/' + change, headers=reviewed_headers(boot, ADMIN))
            assert changed.status_code == 200 and 'restore_notice' not in changed.json()
            if change == 'token/rotate':
                log_scan.watch(changed.json()['token'])
            assert 'restore_notice' not in (await admin.get('/api/bootstrap', headers=ADMIN)).json()
    assert NOTICE not in os.listdir(data)
    async with production_runtime(product, data) as runtime:
        await settle(runtime, 'configured')
        async with runtime.admin() as admin:
            assert 'restore_notice' not in (await admin.get('/api/bootstrap', headers=ADMIN)).json()


async def test_an_identity_change_that_rotates_the_kept_token_ends_the_notice(tmp_path, log_scan):
    """HM-13c with HM-12 (merged after both): switched on without profile data, a restore keeps the default profile's
    token (DQ-03 (b)) and the bootstrap shows the notice. HM-12's identity change (here its username, backend/patch)
    rotates that token, so the notice ends as after a token/rotate: the bootstrap has no restore_notice and
    restore-notice.json is gone. A change of the password alone keeps the token, and the notice."""
    data = restored_copy(tmp_path, PRODUCT, 'one')
    async with multi_profile_runtime(PRODUCT, data) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        watch_identity(log_scan, data)
        boot = await bootstrap_of(runtime)
        assert 'restore_notice' in boot and 'restore_review_required' not in boot
        token = runtime.token(DEFAULT)
        kept = await backend_save(runtime, DEFAULT, 'backend/patch', {'changes': {'password': NEW_PASSWORD}})
        assert kept.status_code == 200 and 'token_rotated' not in kept.json(), kept.text
        assert runtime.token(DEFAULT) == token and 'restore_notice' in await bootstrap_of(runtime)
        saved = await backend_save(runtime, DEFAULT, 'backend/patch', {'changes': {'username': REBOUND['username']}})
        assert saved.status_code == 200 and saved.json()['token_rotated'] is True, saved.text
        log_scan.watch(runtime.token(DEFAULT))
        assert runtime.token(DEFAULT) not in (None, token)
        assert 'restore_notice' not in await bootstrap_of(runtime)
    assert NOTICE not in os.listdir(data)


@pytest.mark.parametrize('failure', ['stop', 'refused'])
async def test_a_failed_identity_change_keeps_the_kept_tokens_notice(tmp_path, log_scan, monkeypatch, failure):
    """HM-13c merge review S-2 (its experiment X2; mutations M08, M09): the notice ends only once HM-12's identity
    change has published the new token. One that fails before anything is written (the old child cannot be stopped, or
    the store refuses the write) answers 503 and keeps the token, so the notice is still true: the bootstrap still has
    restore_notice and restore-notice.json is still there."""
    data = restored_copy(tmp_path, PRODUCT, 'one')
    journal = Journal()
    record_writes(monkeypatch, journal, refuse=REFUSALS.get(failure))
    async with multi_profile_runtime(PRODUCT, data, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        watch_identity(log_scan, data)
        journal.watch(data, DEFAULT, runtime.manager.get(DEFAULT).runtime.supervisor)
        journal.refuse_stop = int(failure == 'stop')
        assert 'restore_notice' in await bootstrap_of(runtime)
        token = runtime.token(DEFAULT)
        failed = await backend_save(runtime, DEFAULT, 'backend/patch', {'changes': {'username': REBOUND['username']}})
        assert failed.status_code == 503, failed.text
        assert runtime.token(DEFAULT) == token and stored(data)['connection']['username'] == 'DUMMY-user'
        assert 'restore_notice' in await bootstrap_of(runtime)
        assert NOTICE in os.listdir(data)


async def test_a_start_that_was_never_restored_has_no_notice_at_all(tmp_path, log_scan, monkeypatch):
    """Without a notice the runtime gets none (make_apps restore_notice left out): no Notice is made, a token change
    removes nothing and the data directory holds what it held before (contract 1.2: the exception is only for a
    restore)."""
    made = []
    real = restore_lock.Notice

    def watched(*args, **kwargs):
        made.append(args)
        return real(*args, **kwargs)
    monkeypatch.setattr(restore_lock, 'Notice', watched)
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    log_scan.watch(stored(data)['token'], stored(data)['child_token'])
    async with production_runtime(PRODUCT, data) as runtime:
        await settle(runtime, 'configured')
        before = sorted(os.listdir(data))
        async with runtime.admin() as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            assert 'restore_notice' not in boot
            rotated = await admin.post('/api/token/rotate', headers=reviewed_headers(boot, ADMIN))
            assert rotated.status_code == 200
            log_scan.watch(rotated.json()['token'])
    assert made == [] and NOTICE not in os.listdir(data)
    assert sorted(os.listdir(data)) == sorted({*before, '.state.json.operations.json'})


# ---- switched on: the record, the review, the gate (plan 6 核對卡; contract 3.1, 3.6, 4.1) ----

class Admin(Panel):
    """Panel's calls (tests/test_profile_admin_api.py) and HM-13c's: the record, a review, "revoke all", a quarantine
    directory's deletion."""

    async def record(self):
        async with self.client() as client:
            return await client.get('/api/profiles/restore-record', headers=self.user)

    async def review(self, profile_id, **headers):
        etag = headers.pop('etag', None) or await self.etag()
        async with self.client() as client:
            return await client.post(f'/api/profiles/{profile_id}/restore-review', headers=self.headers(etag, **headers))

    async def revoke_all(self, **headers):
        etag = headers.pop('etag', None) or await self.etag()
        async with self.client() as client:
            return await client.post('/api/profiles/revoke-all', headers=self.headers(etag, **headers))

    async def delete_quarantined(self, name, **headers):
        etag = headers.pop('etag', None) or await self.etag()
        async with self.client() as client:
            return await client.post(f'/api/profiles/quarantine/{name}/delete', headers=self.headers(etag, **headers))


async def bootstrap_of(runtime, profile_id='default'):
    async with runtime.admin(profile_id) as admin:
        response = await admin.get('/api/bootstrap', headers=ADMIN)
    assert response.status_code == 200, response.content
    return response.json()


async def rotate(runtime, profile_id):
    async with runtime.admin(profile_id) as admin:
        boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
        return await admin.post('/api/token/rotate', headers=reviewed_headers(boot, ADMIN))


def restored_profiles(tmp_path, extras=(B, C), orphans=(), broken=()):
    """The default profile and extras (configured; tests/test_profile_admin_api.setup), orphans, broken ones (an
    orphan whose writer lock is gone: the guard quarantines it), restored (the marker saved)."""
    data = setup(tmp_path, extras=extras)
    for number, profile_id in enumerate((*orphans, *broken)):
        create_profile(data, PRODUCT, profile_id, label='Orphan Ops', port=18090 + number, indexed=False)
    for profile_id in broken:
        (profiles.Layout(data).profile(profile_id) / '.writer.lock').unlink()
    mark_restored(data)
    return data


async def test_after_a_restore_the_bootstrap_and_the_record_say_what_waits_for_a_review(tmp_path, log_scan):
    """The guard revoked every profile's token (profile data: the default profile's too): the default bootstrap's
    restore_review counts the profiles that wait (pending, restore_at), every gated profile's bootstrap says
    restore_review_required; GET profiles/restore-record is the guard's record (no token, child token or password)."""
    data = restored_profiles(tmp_path)
    before = {where: stored(data if where == DEFAULT else profiles.Layout(data).profile(where))
              for where in (DEFAULT, B, C)}
    for value in before.values():
        log_scan.watch(value['token'], value['child_token'])
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        default = await bootstrap_of(runtime)
        record = restore_lock.read_record(data)
        assert default['restore_review'] == {'pending': 3, 'restore_at': record['restore']['at'], 'dormant_at': None}
        assert default['restore_review_required'] is True and 'restore_notice' not in default
        assert (await bootstrap_of(runtime, B))['restore_review_required'] is True
        panel = Admin(runtime, await csrf_of(runtime))
        shown = await panel.record()
        assert shown.status_code == 200 and shown.json() == {'record': record}
        assert shown.headers['cache-control'] == 'no-store' and shown.headers['etag'] == await panel.etag()
        assert [(row['id'], row['label'], row['token'], row['reviewed_at']) for row in shown.json()['record']['profiles']] == [
            (DEFAULT, 'Default', 'revoked', None), (B, LABELS[B], 'revoked', None), (C, LABELS[C], 'revoked', None)]
        text = shown.text
        for value in before.values():
            assert value['token'] not in text and value['child_token'] not in text
            assert value['connection']['password'] not in text


async def test_a_new_token_waits_for_the_profiles_review(tmp_path, log_scan):
    """Plan 6, 8.4 (核對後才重發): a token/rotate of a profile the guard revoked answers 409 restore_review_required,
    after the If-Match and the Idempotency-Key, with nothing written (no receipt); "已核對" (POST
    profiles/<id>/restore-review: If-Match of the index, an Idempotency-Key, a receipt beside the index) records
    reviewed_at in the record; its replay answers what it did; then the rotation issues the token, which 8081 serves.
    The review of one profile opens no other."""
    data = restored_profiles(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        before = tree_of(data)
        for profile_id in (DEFAULT, B):
            refused = await rotate(runtime, profile_id)
            assert (refused.status_code, code_of(refused)) == (409, 'restore_review_required')
            assert 'profile' not in refused.json()  # a refusal carries no echo (contract 3.4)
        assert tree_of(data) == before
        panel = Admin(runtime, await csrf_of(runtime))
        key = operation_key()
        reviewed = await panel.review(B, key=key)
        assert reviewed.status_code == 200, reviewed.content
        body = reviewed.json()
        assert set(body) == {'reviewed', 'reviewed_at', 'operation'} and body['reviewed'] == B
        assert body['operation'] == {'id': key, 'kind': 'profile.restore_review', 'state': 'completed',
                                     'replayed': False}
        row = next(row for row in restore_lock.read_record(data)['profiles'] if row['id'] == B)
        assert row['reviewed_at'] == body['reviewed_at']
        again = await panel.review(B, key=key)
        assert again.json() == {**body, 'operation': {**body['operation'], 'replayed': True}}
        assert (await bootstrap_of(runtime))['restore_review']['pending'] == 2
        assert 'restore_review_required' not in await bootstrap_of(runtime, B)
        refused = await rotate(runtime, C)
        assert (refused.status_code, code_of(refused)) == (409, 'restore_review_required')
        rotated = await rotate(runtime, B)
        assert rotated.status_code == 200 and rotated.json()['profile'] == {'id': B}
        token = rotated.json()['token']
        log_scan.watch(token)
        async with runtime.mcp() as client:
            served = await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer ' + token},
                                       json=initialize_message())
            assert served.status_code == 200
        later = await panel.review(B)  # reviewed already: the first time stays
        assert later.status_code == 200 and later.json()['reviewed_at'] == body['reviewed_at']


async def test_a_review_takes_the_index_etag_a_key_and_a_profile_of_the_record(tmp_path, log_scan):
    """The review's checks in the pipeline's order (contract 3.2 step 11): If-Match (428 without, 409 stale), the
    Idempotency-Key (428 without), then the profile: 404 profile_not_found for one the record has no row of, one the
    index does not list (an orphan) and one deleted since; nothing written by a refusal."""
    data = restored_profiles(tmp_path, extras=(B,), orphans=(D,))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B,))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        panel = Admin(runtime, await csrf_of(runtime))
        etag = await panel.etag()
        before = tree_of(data)
        async with panel.client() as client:
            missing = await client.post(f'/api/profiles/{B}/restore-review', headers=panel.headers(None))
        assert (missing.status_code, code_of(missing)) == (428, 'config_revision_required')
        stale = await panel.review(B, etag='"p1-' + '0' * 64 + '"')
        assert (stale.status_code, stale.json()) == (409, {'detail': {'code': 'config_conflict'}})
        assert stale.headers['etag'] == etag
        keyless = await panel.review(B, key=False)
        assert (keyless.status_code, code_of(keyless)) == (428, 'operation_id_required')
        for profile_id in ('e' * 24, D):  # no row; an orphan's row (the index does not list it)
            unknown = await panel.review(profile_id)
            assert (unknown.status_code, code_of(unknown)) == (404, 'profile_not_found')
        assert tree_of(data) == before
        async with panel.client() as client:
            bad = await client.post('/api/profiles/not-a-profile/restore-review', headers=panel.headers(etag))
        assert (bad.status_code, bad.content) == (400, b'{"error":"request denied"}')
        assert (await panel.delete(B)).status_code == 200
        gone = await panel.review(B)
        assert (gone.status_code, code_of(gone)) == (404, 'profile_not_found')


async def test_a_record_that_cannot_be_read_holds_every_new_token(tmp_path, log_scan):
    """The gate fails closed: a record that cannot be used (here: not the guard's shape) answers 503 for the record and
    for every token/rotate, and the default bootstrap says the review state is unknown (pending null)."""
    data = restored_profiles(tmp_path, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B,))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        record = profiles.Layout(data).restore_record
        value = json.loads(record.read_text())
        value['profiles'][1]['token'] = 'whatever'
        record.write_text(json.dumps(value))
        panel = Admin(runtime, await csrf_of(runtime))
        assert answer(await panel.record())[::2] == STATE_UNAVAILABLE
        for profile_id in (DEFAULT, B):
            assert answer(await rotate(runtime, profile_id))[::2] == STATE_UNAVAILABLE
        assert (await bootstrap_of(runtime))['restore_review'] == {'pending': None, 'restore_at': None,
                                                                   'dormant_at': None}


async def test_revoke_all_rebuilds_a_record_that_cannot_be_read(tmp_path, log_scan):
    """HM-13c review S-2: a record that cannot be used holds every new token (503) and nothing else in the panel could
    write it again. A "revoke all" that finishes writes a new one: every profile revoked and waiting for its review,
    neither a restore nor a dormant part. From then on the gate works again, a profile at a time. A "revoke all" over a
    record that can be used leaves it as it is."""
    data = restored_profiles(tmp_path, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B,))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        path = profiles.Layout(data).restore_record
        value = json.loads(path.read_text())
        value['profiles'][1]['token'] = 'whatever'
        path.write_text(json.dumps(value))
        assert answer(await rotate(runtime, B))[::2] == STATE_UNAVAILABLE
        panel = Admin(runtime, await csrf_of(runtime))
        done = await panel.revoke_all()
        assert done.status_code == 200, done.content
        record = restore_lock.read_record(data)
        assert restore_lock.check_record(record) == record and (record['restore'], record['dormant']) == (None, None)
        assert [(row['id'], row['token'], row['reviewed_at']) for row in record['profiles']] == [
            (DEFAULT, 'revoked', None), (B, 'revoked', None)]
        assert (await bootstrap_of(runtime))['restore_review'] == {'pending': 2, 'restore_at': None, 'dormant_at': None}
        for profile_id in (DEFAULT, B):
            refused = await rotate(runtime, profile_id)
            assert (refused.status_code, code_of(refused)) == (409, 'restore_review_required'), profile_id
        assert (await panel.review(B)).status_code == 200
        rotated = await rotate(runtime, B)
        assert rotated.status_code == 200
        log_scan.watch(rotated.json()['token'])
        kept = path.read_bytes()
        assert (await panel.revoke_all()).status_code == 200
        assert path.read_bytes() == kept


async def test_a_dormant_profile_switched_on_again_waits_for_its_review(tmp_path, log_scan):
    """I13 (plan 3.3, 8.4 休眠處理: "重新開通後照核對卡流程重發"): a start of a release that does not switch the product on
    revoked B and C (profile data on disk) and recorded it; switched on again, without a restore, the default
    bootstrap's restore_review counts them (dormant_at, no restore_at), each one's token/rotate answers 409
    restore_review_required until it was reviewed, then its new token is served. The default profile was not revoked
    (no restore: DQ-03 is not involved), so its own new token needs no review."""
    data = setup(tmp_path, extras=(B, C))
    for value in tokens_now(data, (DEFAULT, B, C)).values():
        log_scan.watch(value['token'], value['child_token'])
    store = ProductStore(data, PRODUCT)  # run_product's guard of a release that does not switch the product on
    try:
        outcome = restore_lock.guard(store, PRODUCT, enabled=False)
    finally:
        store.close()
    assert outcome.dormant == 2 and set(outcome.revoked) == {B, C} and not outcome.default_revoked
    record = restore_lock.read_record(data)
    assert record['restore'] is None and record['dormant'] is not None
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        default = await bootstrap_of(runtime)
        assert default['restore_review'] == {'pending': 2, 'restore_at': None, 'dormant_at': record['dormant']['at']}
        assert 'restore_review_required' not in default
        assert (await bootstrap_of(runtime, B))['restore_review_required'] is True
        for profile_id in (B, C):
            refused = await rotate(runtime, profile_id)
            assert (refused.status_code, code_of(refused)) == (409, 'restore_review_required')
        own = await rotate(runtime, DEFAULT)
        assert own.status_code == 200
        log_scan.watch(own.json()['token'])
        panel = Admin(runtime, await csrf_of(runtime))
        assert (await panel.review(C)).status_code == 200
        rotated = await rotate(runtime, C)
        assert rotated.status_code == 200
        token = rotated.json()['token']
        log_scan.watch(token)
        async with runtime.mcp() as client:
            served = await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer ' + token},
                                       json=initialize_message())
            assert served.status_code == 200
        refused = await rotate(runtime, B)
        assert (refused.status_code, code_of(refused)) == (409, 'restore_review_required')
        assert (await bootstrap_of(runtime))['restore_review']['pending'] == 1


async def test_a_profile_revoked_before_the_dormant_start_waits_for_its_review_too(tmp_path, log_scan):
    """I13 (HM-13c review S-1): C's token was revoked before the release that does not switch the product on started
    (its token/revoke): the dormant start leaves it as it is and records it already_revoked. Switched on again, C's new
    token waits for its review as B's does (revoked by that start); once reviewed, it is issued."""
    data = setup(tmp_path, extras=(B, C))
    for value in tokens_now(data, (DEFAULT, B, C)).values():
        log_scan.watch(value['token'], value['child_token'])
    store = ProductStore(profiles.Layout(data).profile(C), PRODUCT, existing_only=True)
    try:
        store.change_token(None, action='revoke')
    finally:
        store.close()
    store = ProductStore(data, PRODUCT)  # run_product's guard of a release that does not switch the product on
    try:
        assert restore_lock.guard(store, PRODUCT, enabled=False) == restore_lock.Outcome(dormant=2, revoked=(B,))
    finally:
        store.close()
    assert [(row['id'], row['token']) for row in restore_lock.read_record(data)['profiles']] == [
        (DEFAULT, 'kept'), (B, 'revoked'), (C, 'already_revoked')]
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        assert (await bootstrap_of(runtime, C))['restore_review_required'] is True
        refused = await rotate(runtime, C)
        assert (refused.status_code, code_of(refused)) == (409, 'restore_review_required')
        panel = Admin(runtime, await csrf_of(runtime))
        assert (await panel.review(C)).status_code == 200
        rotated = await rotate(runtime, C)
        assert rotated.status_code == 200
        log_scan.watch(rotated.json()['token'])


@pytest.mark.parametrize('reviewed', [(B,), (B, DEFAULT), (B, DEFAULT, C)])
def test_a_dormant_start_never_drops_a_review_the_last_record_waits_for(tmp_path, log_scan, reviewed):
    """HM-13c review MF-1: a restore with profile data revoked the default profile, B and C (record R1, none reviewed);
    then the profiles in reviewed were reviewed and B got its new token. A start of a release that does not switch the
    product on (dormant: B revoked again) writes its record over R1 without dropping a review R1 still waits for: the
    default profile's row stays R1's, as it was (revoked, not reviewed), while nobody reviewed it (that start keeps the
    default profile: its own row would say kept and open the gate), and R1's restore part stays while one of R1's rows
    still waits. B (revoked again) and C (already revoked) wait in any case."""
    disk = Disk(tmp_path, log_scan)
    assert disk.start(enabled=True) == restore_lock.Outcome()  # the sentinel, before any profile data
    for profile_id in (B, C):
        disk.add(profile_id)
    disk.restore(disk.backup())
    assert disk.start(enabled=True) == restore_lock.Outcome(restored=True, default_revoked=True, revoked=(B, C))
    first = restore_lock.read_record(disk.data)
    for profile_id in reviewed:
        restore_lock.review(disk.data, profile_id)
    disk.rotate(B)  # its new token, after its review
    assert disk.start(enabled=False) == restore_lock.Outcome(dormant=2, revoked=(B,))
    record = restore_lock.read_record(disk.data)
    assert restore_lock.check_record(record) == record and record['dormant'] is not None
    waits = DEFAULT not in reviewed
    assert [(row['id'], row['token'], row['reviewed_at']) for row in record['profiles']] == [
        (DEFAULT, 'revoked' if waits else 'kept', None), (B, 'revoked', None), (C, 'already_revoked', None)]
    if waits:
        assert record['profiles'][0] == first['profiles'][0]
    assert record['restore'] == (None if C in reviewed else first['restore'])
    assert disk.tokens()[0] is None  # the default profile's token is still the one the restore revoked


async def test_after_a_dormant_start_the_default_profile_still_waits_for_its_review(tmp_path, log_scan):
    """HM-13c review MF-1 (its experiment X1): after a restore with profile data, B is reviewed and gets its new token;
    the default profile and C are not reviewed. A release that does not switch the product on starts (an emergency
    stop, plan 3.3, 7.4: B revoked again). Switched on again, the default profile's new token still waits for its review
    (409 restore_review_required, nothing written), as B's and C's do, and the card still names the restore (its time
    and the dormant one's). Once reviewed, the default profile's new token is issued."""
    data = restored_profiles(tmp_path)  # default, B, C; restored (marker)
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        panel = Admin(runtime, await csrf_of(runtime))
        assert (await panel.review(B)).status_code == 200
        rotated = await rotate(runtime, B)
        assert rotated.status_code == 200
        log_scan.watch(rotated.json()['token'])
    first = restore_lock.read_record(data)
    store = ProductStore(data, PRODUCT)  # the emergency release's start
    try:
        assert restore_lock.guard(store, PRODUCT, enabled=False) == restore_lock.Outcome(dormant=2, revoked=(B,))
    finally:
        store.close()
    record = restore_lock.read_record(data)
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        default = await bootstrap_of(runtime)
        assert default['restore_review'] == {'pending': 3, 'restore_at': first['restore']['at'],
                                             'dormant_at': record['dormant']['at']}
        assert default['restore_review_required'] is True
        before = tree_of(data)
        for profile_id in (DEFAULT, B, C):
            refused = await rotate(runtime, profile_id)
            assert (refused.status_code, code_of(refused)) == (409, 'restore_review_required'), profile_id
        assert tree_of(data) == before
        panel = Admin(runtime, await csrf_of(runtime))
        assert (await panel.review(DEFAULT)).status_code == 200
        rotated = await rotate(runtime, DEFAULT)
        assert rotated.status_code == 200
        log_scan.watch(rotated.json()['token'])


# ---- HM-13c review S-3: HM-12's identity change issues a new token too, so it waits for the review as well ----

def restored_switched_off_then_reissued(tmp_path):
    """HM-13c review S-3 (its experiment X7): the default profile and B, restored with profile data while the product is
    not switched on (a release without the switch): the guard revokes both and records them unreviewed. Switched off
    there is no gate and no review route, so the administrator issues the default profile a new token (what a
    switched-off token/rotate writes; contract 3.1). Switched on afterwards, the default profile's token is active
    while its review still waits: waiting for a review is not always being revoked."""
    data = setup(tmp_path, extras=(B,))
    mark_restored(data)
    store = ProductStore(data, PRODUCT)
    try:
        outcome = restore_lock.guard(store, PRODUCT, enabled=False)
        assert outcome.restored and outcome.default_revoked
        store.change_token('T' * 43, action='rotate')
    finally:
        store.close()
    return data


def identity_change(route, state):
    """A save of the default profile's Odoo username anew: the whole connection (PUT backend) or the field alone."""
    if route == 'backend':
        return {'connection': {**state['connection'], 'username': REBOUND['username']}}
    return {'changes': {'username': REBOUND['username']}}


@pytest.mark.parametrize('route', ['backend', 'backend/patch'])
async def test_an_identity_change_waits_for_the_profiles_review_too(tmp_path, log_scan, monkeypatch, route):
    """HM-13c review S-3: switched on, a save that changes the default profile's Odoo identity while its token is
    active would rotate the token (HM-12: products.identity_rebound). While the profile still waits for its restore
    review it answers 409 restore_review_required, as token/rotate does, after If-Match and before anything is done:
    the child is not stopped, nothing is written (the state, the receipts, the record: the tree is the same), no
    token change is published, the token stays the one 8081 serves on both paths, and no line is logged. A change of
    the password alone rotates nothing and is saved as today, the review still waiting."""
    data = restored_switched_off_then_reissued(tmp_path)
    children = children_of(data, (B,))
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        watch_identity(log_scan, data)
        journal.watch(data, DEFAULT, runtime.manager.get(DEFAULT).runtime.supervisor)
        default = await bootstrap_of(runtime)
        assert default['token_active'] is True and default['restore_review_required'] is True
        token, state, before = runtime.token(DEFAULT), stored(data), tree_of(data)
        refused = await backend_save(runtime, DEFAULT, route, identity_change(route, state))
        assert (refused.status_code, refused.json()) == (
            409, {'error': 'request denied', 'detail': {'code': 'restore_review_required'}}), refused.text
        assert journal.events == [] and tree_of(data) == before and stored(data) == state
        assert runtime.token(DEFAULT) == token and await opened_by(runtime, token, children.by_port[3000])
        assert rebind_warnings(log_scan) == []
        kept = await backend_save(runtime, DEFAULT, 'backend/patch', {'changes': {'password': NEW_PASSWORD}})
        assert kept.status_code == 200 and kept.json()['saved'] is True and 'token_rotated' not in kept.json(), kept.text
        assert stored(data)['token'] == token and stored(data)['connection']['password'] == NEW_PASSWORD
        assert [event[0] for event in journal.events] == ['stop', 'start']  # the child relaunched, no identity write
        assert (await bootstrap_of(runtime))['restore_review_required'] is True


async def test_once_reviewed_an_identity_change_rotates_the_token_as_today(tmp_path, log_scan, monkeypatch):
    """HM-13c review S-3, the other side: once the default profile was reviewed ("已核對"), the same save is HM-12's
    identity change as without a restore: the old child stops, one write holds the new username, a new token and its
    history entry, the change is published, the new child starts; 200 with token_rotated, the new token served."""
    data = restored_switched_off_then_reissued(tmp_path)
    children = children_of(data, (B,))
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        watch_identity(log_scan, data)
        journal.watch(data, DEFAULT, runtime.manager.get(DEFAULT).runtime.supervisor)
        panel = Admin(runtime, await csrf_of(runtime))
        assert (await panel.review(DEFAULT)).status_code == 200
        assert 'restore_review_required' not in await bootstrap_of(runtime)
        old = runtime.token(DEFAULT)
        saved = await backend_save(runtime, DEFAULT, 'backend/patch', identity_change('backend/patch', stored(data)))
        assert saved.status_code == 200 and saved.json()['token_rotated'] is True, saved.text
        new = runtime.token(DEFAULT)
        log_scan.watch(new)
        assert new not in (None, old)
        assert journal.events == [('stop', old, 'DUMMY-user'), ('write', 'stopped'), ('publish',),
                                  ('start', REBOUND['username'])]
        assert await opened_by(runtime, new, children.by_port[3000])


@pytest.mark.parametrize('restored', ['without profile data', 'with profile data, reissued'])
async def test_switched_off_an_identity_change_after_a_restore_is_todays(tmp_path, log_scan, restored):
    """HM-13c review S-3 changes nothing for a product not switched on (plan 3.3): there is no gate and no identity
    change then. Restored without profile data (the token kept, the panel's notice) or with it (S-3's own state: the
    record's rows unreviewed, the default profile's token issued again), a changed username is saved as today: the
    answer is {"saved", "configuration"}, the token and its history stay and are still served on both paths."""
    if restored == 'without profile data':
        data = restored_copy(tmp_path, PRODUCT, 'one')
    else:
        data = restored_switched_off_then_reissued(tmp_path)
    journal = Journal()
    async with production_runtime(PRODUCT, data, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        assert not features.enabled(PRODUCT)
        watch(log_scan, data)
        watch_identity(log_scan, data)
        journal.watch(data, DEFAULT)
        before = stored(data)
        async with runtime.admin() as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            assert 'restore_review_required' not in boot
            saved = await admin.put('/api/backend/patch', json=identity_change('backend/patch', before),
                                    headers=reviewed_headers(boot, ADMIN))
        assert saved.status_code == 200, saved.text
        assert list(saved.json()) == ['saved', 'configuration'] and saved.json()['saved'] is True
        after = stored(data)
        assert (after['token'], after.get('token_history')) == (before['token'], before.get('token_history'))
        assert after['connection']['username'] == REBOUND['username']
        assert journal.events == [('stop', before['token'], REBOUND['username']), ('start', REBOUND['username'])]
        async with runtime.mcp() as client:
            for path, headers in (('/mcp', {**ACCEPT, 'Authorization': 'Bearer ' + before['token']}),
                                  (f'/private_{before["token"]}/mcp', ACCEPT)):
                assert (await client.post(path, headers=headers, json=initialize_message())).status_code == 200


async def test_a_record_that_cannot_be_read_holds_an_identity_change_too(tmp_path, log_scan, monkeypatch):
    """As for token/rotate (the gate fails closed): while the restore record cannot be used (here: not the guard's
    shape), an identity change answers today's 503 state unavailable and does nothing; a change of the password alone
    (no new token) is saved."""
    data = restored_switched_off_then_reissued(tmp_path)
    children = children_of(data, (B,))
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        watch_identity(log_scan, data)
        journal.watch(data, DEFAULT, runtime.manager.get(DEFAULT).runtime.supervisor)
        record = profiles.Layout(data).restore_record
        value = json.loads(record.read_text())
        value['profiles'][0]['token'] = 'whatever'
        record.write_text(json.dumps(value))
        token, state, before = runtime.token(DEFAULT), stored(data), tree_of(data)
        refused = await backend_save(runtime, DEFAULT, 'backend/patch', identity_change('backend/patch', state))
        assert answer(refused)[::2] == STATE_UNAVAILABLE
        assert journal.events == [] and tree_of(data) == before and runtime.token(DEFAULT) == token
        kept = await backend_save(runtime, DEFAULT, 'backend/patch', {'changes': {'password': NEW_PASSWORD}})
        assert kept.status_code == 200 and 'token_rotated' not in kept.json(), kept.text
        assert stored(data)['token'] == token


async def test_a_revoked_profile_waiting_for_its_review_saves_an_identity_change_as_today(tmp_path, log_scan,
                                                                                         monkeypatch):
    """HM-13c merge review S-1, S-2 (its experiment X1; mutation M13): the gate holds a new token, not a save. After a
    restore with profile data every token is revoked and waits for its review; a changed Odoo username then rotates
    nothing (products.identity_rebound needs an active token), so it is saved as today, for the default profile and
    for B: 200 without token_rotated, the token still revoked, the review still waiting."""
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: None)  # B's save starts its child whatever the host has
    monkeypatch.setattr(profiles, 'available_memory_mib', lambda: 4096)
    data = restored_profiles(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        watch_identity(log_scan, data)
        for profile_id in (DEFAULT, B):
            boot = await bootstrap_of(runtime, profile_id)
            assert (boot['restore_review_required'], boot['token_active']) == (True, False), profile_id
            change = {'changes': {'username': REBOUND['username']}}
            saved = await backend_save(runtime, profile_id, 'backend/patch', change)
            assert saved.status_code == 200 and saved.json()['saved'] is True, saved.text
            assert 'token_rotated' not in saved.json()
            where = data if profile_id == DEFAULT else profiles.Layout(data).profile(profile_id)
            assert (stored(where)['token'], stored(where)['connection']['username']) == (None, REBOUND['username'])
            assert (await bootstrap_of(runtime, profile_id))['restore_review_required'] is True


async def test_a_new_origin_without_its_password_is_refused_before_the_review_gate(tmp_path, log_scan):
    """HM-13c merge review S-2 (its experiment X3; mutation M03): the order the main conversation decided is If-Match,
    the new-origin check, then the review gate. In S-3's state (the review waits, the token is active) a URL moved to
    another server without its password answers HM-12's 422 CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN, not 409,
    and nothing changes."""
    data = restored_switched_off_then_reissued(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B,))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        watch_identity(log_scan, data)
        assert (await bootstrap_of(runtime))['restore_review_required'] is True
        token, before = runtime.token(DEFAULT), tree_of(data)
        moved = await backend_save(runtime, DEFAULT, 'backend/patch', {'changes': {'url': REBOUND['url']}})
        assert (moved.status_code, moved.json()) == (422, {'error': 'request denied', 'detail': {
            'code': 'CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN'}}), moved.text
        assert tree_of(data) == before and runtime.token(DEFAULT) == token


def test_a_dormant_start_leaves_a_record_it_cannot_read_as_it_is(tmp_path, log_scan):
    """HM-13c review MF-1, the other half: a dormant start cannot tell what a record it cannot use (not the guard's
    shape here) still waits for, so it leaves it as it is and says so: switched on again, every new token keeps waiting
    (503) until a "revoke all" rebuilds it. B is revoked all the same."""
    disk = Disk(tmp_path, log_scan)
    assert disk.start(enabled=True) == restore_lock.Outcome()
    disk.add(B)
    disk.restore(disk.backup())
    assert disk.start(enabled=True).default_revoked
    path = disk.data / profiles.RESTORE_RECORD_NAME
    value = json.loads(path.read_text())
    value['profiles'][1]['token'] = 'whatever'
    path.write_text(json.dumps(value))
    unusable = path.read_bytes()
    disk.rotate(B)
    assert disk.start(enabled=False) == restore_lock.Outcome(dormant=1, revoked=(B,))
    assert path.read_bytes() == unusable and not restore_lock.record_usable(disk.data)
    assert disk.tokens(B)[0] is None
    assert ('WARNING', restore_lock.RECORD_KEPT) in guard_lines(log_scan)


async def test_while_the_index_cannot_be_used_the_record_reads_and_a_review_waits_for_its_quarantine(tmp_path, log_scan):
    """Contract 4.1 profile_index_corrupt (HM-13c): an index changed behind the add-on's back after a restore (DQ-12)
    leaves the record readable (its ETag: the unusable index's own) and every gate shut; a review and a quarantine
    directory's deletion answer 503 profile_index_corrupt with nothing written; the default bootstrap counts only the
    default profile (an unusable index lists none). Once the index is quarantined (HM-10), B is an orphan (never
    counted again) and the default profile is reviewed, then its new token issued."""
    from test_profile_admin_api import replace_index
    data = restored_profiles(tmp_path, extras=(B,), broken=(D,))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B,))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        panel = Admin(runtime, await csrf_of(runtime))
        etag = await panel.etag()
        directory, = [name for name in os.listdir(profiles.Layout(data).profiles)
                      if profiles.parse_quarantine_name(name)]
        name = directory[len(profiles.QUARANTINE_PREFIX):]
        replace_index(data)
        boot = await bootstrap_of(runtime)
        raw = boot['profile_index_etag']
        assert boot['restore_review']['pending'] == 1 and boot['restore_review_required'] is True
        shown = await panel.record()
        assert shown.status_code == 200 and shown.headers['etag'] == raw
        assert [row['id'] for row in shown.json()['record']['profiles']] == [DEFAULT, B]
        before = tree_of(data)
        for response in (await panel.review(DEFAULT, etag=etag), await panel.delete_quarantined(name, etag=etag),
                         await panel.review(DEFAULT, etag=raw)):
            assert (response.status_code, code_of(response)) == (503, 'profile_index_corrupt')
        refused = await rotate(runtime, DEFAULT)
        assert (refused.status_code, code_of(refused)) == (409, 'restore_review_required')
        assert tree_of(data) == before
        assert (await panel.quarantine(raw)).status_code == 200
        assert (await panel.list())[0]['orphans'] == [{'id': B}]
        assert (await panel.review(DEFAULT)).status_code == 200
        assert 'restore_review' not in await bootstrap_of(runtime)  # B is an orphan now: nothing else waits
        rotated = await rotate(runtime, DEFAULT)
        assert rotated.status_code == 200
        log_scan.watch(rotated.json()['token'])


# ---- the quarantine directories: listed, deleted only (contract 1.1, 3.1) ----

async def test_a_quarantine_directory_is_listed_and_can_only_be_deleted(tmp_path, log_scan):
    """The guard quarantined D (its writer lock gone in the backup): the list names it ("quarantined": name and id,
    only when there is one); it is no profile (X-MCP-Profile with its id: 404; DELETE profiles/<id>: 404); POST
    profiles/quarantine/<name>/delete removes it (If-Match, Idempotency-Key, a receipt; its replay answers what it did;
    afterwards 404); a malformed name is a fixed 400 and another method 405."""
    data = restored_profiles(tmp_path, extras=(B,), broken=(D,))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B,))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        layout = profiles.Layout(data)
        directory, = [name for name in os.listdir(layout.profiles) if profiles.parse_quarantine_name(name)]
        name = directory[len(profiles.QUARANTINE_PREFIX):]
        panel = Admin(runtime, await csrf_of(runtime))
        listed, etag = await panel.list()
        assert listed['quarantined'] == [{'name': name, 'id': D}] and listed['orphans'] == []
        async with runtime.admin(D) as admin:
            response = await admin.get('/api/bootstrap', headers=ADMIN)
        assert (response.status_code, code_of(response)) == (404, 'profile_not_found')
        not_a_profile = await panel.delete(D)
        assert (not_a_profile.status_code, code_of(not_a_profile)) == (404, 'profile_not_found')
        async with panel.client() as client:
            for path in (f'/api/profiles/quarantine/{D}/delete', '/api/profiles/quarantine/x-20261116T000000Z/delete',
                         f'/api/profiles/quarantine/{name}.x/delete'):
                bad = await client.post(path, headers=panel.headers(etag))
                assert (bad.status_code, bad.content) == (400, b'{"error":"request denied"}'), path
            wrong = await client.get(f'/api/profiles/quarantine/{name}/delete', headers=ADMIN)
            assert (wrong.status_code, wrong.headers['allow']) == (405, 'POST')
        key = operation_key()
        deleted = await panel.delete_quarantined(name, key=key)
        assert deleted.status_code == 200, deleted.content
        assert deleted.json() == {'deleted': name, 'operation': {'id': key, 'kind': 'profile.quarantine_delete',
                                                                 'state': 'completed', 'replayed': False}}
        assert not (layout.profiles / directory).exists() and 'quarantined' not in (await panel.list())[0]
        again = await panel.delete_quarantined(name, key=key)
        assert again.status_code == 200 and again.json()['operation']['replayed'] is True
        gone = await panel.delete_quarantined(name)
        assert (gone.status_code, code_of(gone)) == (404, 'profile_not_found')


async def test_a_quarantine_directory_whose_state_opens_is_revoked_and_wiped_before_it_goes(tmp_path, log_scan,
                                                                                            monkeypatch):
    """DQ-14 for a quarantine directory (contract 3.1, 9 #123; HM-13c review S-1): one whose state opens now (its
    quarantine may have come from an error that went away) has its token revoked and its backend credentials wiped
    before its directory goes. Here the removal leaves the directory behind (one line says so; it is listed again and
    can be deleted again), so what was written before it can be seen."""
    data = setup(tmp_path, extras=(B,))
    create_profile(data, PRODUCT, D, label='Orphan Ops', port=18090, indexed=False)
    layout = profiles.Layout(data)
    name = f'{D}-20261116T093015Z'
    directory = layout.profiles / (profiles.QUARANTINE_PREFIX + name)
    os.rename(layout.profile(D), directory)
    before = stored(directory)
    assert before['token'] is not None and before['connection'] is not None
    log_scan.watch(before['token'], before['child_token'], before['connection']['password'])
    monkeypatch.setattr(profiles, 'remove_quarantine_directory', lambda layout, entry: False)
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B,))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        panel = Admin(runtime, await csrf_of(runtime))
        assert (await panel.list())[0]['quarantined'] == [{'name': name, 'id': D}]
        deleted = await panel.delete_quarantined(name)
        assert deleted.status_code == 200, deleted.content
        assert (await panel.list())[0]['quarantined'] == [{'name': name, 'id': D}]
    after = stored(directory)
    assert after['token'] is None and after['connection'] is None
    assert after['child_token'] == before['child_token']  # never served: only what DQ-14 asks is changed
    lines = [record.getMessage() for record in log_scan.records if record.name == ADMIN_LOGGER]
    assert any(line.startswith(f'multi-profile: a quarantine directory of profile {D[:8]} could not be removed')
               for line in lines), lines


# ---- "revoke all" (plan 8.4 全部撤銷; contract 1.3, 3.1, 4.1, 4.2; FM-120) ----

def tokens_now(data, ids):
    layout = profiles.Layout(data)
    return {where: stored(data if where == DEFAULT else layout.profile(where)) for where in ids}


async def test_revoke_all_revokes_every_profile_and_starts_every_child_again(tmp_path, log_scan):
    """Every profile's token revoked (the default profile's included), every child token new and every child started
    again on it; requests that carry an old token end and new ones are answered as unknown tokens (404, 401); 200 with
    every profile's result and a completed receipt beside the index; its replay answers what it did; the marker is gone
    and no restore record is made (not a restore)."""
    data = setup(tmp_path, extras=(B, C))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        before = tokens_now(data, (DEFAULT, B, C))
        starts = {where: runtime.manager.get(where).runtime.supervisor.starts for where in (DEFAULT, B, C)}
        changed = {where: runtime.manager.get(where).runtime.token_access.changed for where in (DEFAULT, B, C)}
        panel = Admin(runtime, await csrf_of(runtime))
        key = operation_key()
        done = await panel.revoke_all(key=key)
        assert done.status_code == 200, done.content
        assert done.json() == {'revoked': 'all', 'results': [{'id': where, 'result': 'revoked'}
                                                             for where in (DEFAULT, B, C)],
                               'operation': {'id': key, 'kind': 'profile.revoke_all', 'state': 'completed',
                                             'replayed': False}}
        after = tokens_now(data, (DEFAULT, B, C))
        watch(log_scan, data)
        for where in (DEFAULT, B, C):
            assert after[where]['token'] is None and after[where]['child_token'] != before[where]['child_token']
            assert runtime.manager.get(where).runtime.supervisor.starts == starts[where] + 1
            assert changed[where].is_set()
        assert PENDING not in os.listdir(data) and not profiles.Layout(data).restore_record.exists()
        async with runtime.mcp() as client:
            for where in (DEFAULT, B, C):
                old = before[where]['token']
                assert answer(await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer ' + old},
                                                json=initialize_message())) == BEARER_REQUIRED
                assert answer(await client.post(f'/private_{old}/mcp', headers=ACCEPT,
                                                json=initialize_message())) == NOT_FOUND
        again = await panel.revoke_all(key=key)
        assert again.status_code == 200 and again.json() == {'revoked': 'all', 'operation': {
            'id': key, 'kind': 'profile.revoke_all', 'state': 'completed', 'replayed': True}}
        assert (await rotate(runtime, B)).status_code == 200  # no restore: no review waits


@pytest.mark.parametrize('failing', [DEFAULT, B, C])
async def test_revoke_all_whose_kth_profile_fails(tmp_path, log_scan, monkeypatch, failing):
    """Plan 8.4 (全部撤銷第 k 個失敗): the k-th profile's write fails. 409 operation_outcome_unknown with every
    profile's result (the others revoked); the receipt stays unknown (a resend of its key is 409 again) and
    .revoke-all-pending stays (the next start finishes it). On 8081 the failed profile's old token gets 503 state
    unavailable (not served, whatever its state says) and the others' are unknown tokens; a new "revoke all" that
    finishes lifts it."""
    data = setup(tmp_path, extras=(B, C))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        before = tokens_now(data, (DEFAULT, B, C))
        directory = data if failing == DEFAULT else profiles.Layout(data).profile(failing)
        real = ProductStore.change_token

        def change_token(self, token, *, action):
            if self.directory == directory and action == 'revoke':
                raise ConfigError('durable state write failed; manual recovery required')
            return real(self, token, action=action)
        panel = Admin(runtime, await csrf_of(runtime))
        key = operation_key()
        with monkeypatch.context() as patch:
            patch.setattr(ProductStore, 'change_token', change_token)
            done = await panel.revoke_all(key=key)
        assert done.status_code == 409, done.content
        detail = done.json()['detail']
        assert detail == {'code': 'operation_outcome_unknown',
                          'operation': {'id': key, 'kind': 'profile.revoke_all', 'state': 'unknown',
                                        'replayed': False},
                          'results': [{'id': where, 'result': 'failed' if where == failing else 'revoked'}
                                      for where in (DEFAULT, B, C)]}
        assert PENDING in os.listdir(data) and stored(directory)['token'] == before[failing]['token']
        resent = await panel.revoke_all(key=key)
        assert (resent.status_code, code_of(resent)) == (409, 'operation_outcome_unknown')
        async with runtime.mcp() as client:
            for where in (DEFAULT, B, C):
                old = before[where]['token']
                for path, headers in (('/mcp', {**ACCEPT, 'Authorization': 'Bearer ' + old}),
                                      (f'/private_{old}/mcp', ACCEPT)):
                    response = await client.post(path, headers=headers, json=initialize_message())
                    if where == failing:
                        assert answer(response)[::2] == STATE_UNAVAILABLE
                    else:
                        assert answer(response) == (BEARER_REQUIRED if path == '/mcp' else NOT_FOUND)
        retried = await panel.revoke_all()
        assert retried.status_code == 200 and PENDING not in os.listdir(data)
        async with runtime.mcp() as client:
            old = before[failing]['token']
            assert answer(await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer ' + old},
                                            json=initialize_message())) == BEARER_REQUIRED


@pytest.mark.parametrize('how', ['its marker cannot be saved', 'its end is not done'])
async def test_revoke_all_that_never_began_or_did_not_end(tmp_path, log_scan, monkeypatch, how):
    """Both answer 409 operation_outcome_unknown with the receipt left unknown (contract 4.1). Its marker cannot be
    saved (restore_lock.mark_revoke_all; a full disk): nothing is revoked and there is no result; every registered
    profile's token is refused on 8081 (503) for the rest of this run (fail closed: the administrator asked for all of
    them to stop), and no marker is left, so a restart would not finish it (the panel says so). Its end is not done
    (here: the marker could not be removed): every profile is revoked and its result says so, nothing is fenced, the
    marker stays (the next start does it all again). A "revoke all" that finishes afterwards ends both."""
    data = setup(tmp_path, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B,))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        before = tokens_now(data, (DEFAULT, B))
        panel = Admin(runtime, await csrf_of(runtime))
        with monkeypatch.context() as patch:
            if how == 'its marker cannot be saved':
                def unsaved(root):
                    raise ConfigError('revoke all not started')
                patch.setattr(restore_lock, 'mark_revoke_all', unsaved)
            else:
                def unfinished(root, now, **kwargs):
                    raise restore_lock.Unfinished('a marker could not be removed')
                patch.setattr(restore_lock, '_finish', unfinished)
            done = await panel.revoke_all()
        assert (done.status_code, code_of(done)) == (409, 'operation_outcome_unknown')
        detail = done.json()['detail']
        assert detail['operation']['state'] == 'unknown'
        after = tokens_now(data, (DEFAULT, B))
        watch(log_scan, data)
        if how == 'its marker cannot be saved':
            assert detail['results'] == [] and after == before and PENDING not in os.listdir(data)
            expected = {'/mcp': STATE_UNAVAILABLE, 'private': STATE_UNAVAILABLE}
        else:
            assert detail['results'] == [{'id': DEFAULT, 'result': 'revoked'}, {'id': B, 'result': 'revoked'}]
            assert all(value['token'] is None for value in after.values()) and PENDING in os.listdir(data)
            expected = {'/mcp': BEARER_REQUIRED[::2], 'private': NOT_FOUND[::2]}
        async with runtime.mcp() as client:
            for where in (DEFAULT, B):
                old = before[where]['token']
                bearer = await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer ' + old},
                                           json=initialize_message())
                secret = await client.post(f'/private_{old}/mcp', headers=ACCEPT, json=initialize_message())
                assert (answer(bearer)[::2], answer(secret)[::2]) == (expected['/mcp'], expected['private']), where
        retried = await panel.revoke_all()
        assert retried.status_code == 200 and PENDING not in os.listdir(data)
        async with runtime.mcp() as client:
            for where in (DEFAULT, B):
                old = before[where]['token']
                assert answer(await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer ' + old},
                                                json=initialize_message())) == BEARER_REQUIRED


async def test_revoke_all_stopped_by_an_unexpected_error_fails_closed(tmp_path, log_scan, monkeypatch):
    """HM-13c review S-4 (its experiment X6): an exception "revoke all" does not expect, half way (here: the default
    profile revoked, B not yet), is answered as an outcome nobody knows: 409 operation_outcome_unknown without results
    and the receipt unknown; the requests that carry an old token end, and every registered profile's old token is
    refused on 8081 (503; B's is still on disk and is not served); one fixed line in the log names the exception's
    class, never its text. The marker stays (a restart finishes it); a "revoke all" that finishes lifts the fence."""
    data = setup(tmp_path, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B,))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        before = tokens_now(data, (DEFAULT, B))
        changed = {where: runtime.manager.get(where).runtime.token_access.changed for where in (DEFAULT, B)}
        panel = Admin(runtime, await csrf_of(runtime))

        def stopped(self, **kwargs):
            raise RuntimeError('unexpected, with a secret in its text: ' + before[B]['token'])
        with monkeypatch.context() as patch:
            patch.setattr(restore_lock._Sweep, 'directories_pass', stopped)
            done = await panel.revoke_all()
        assert (done.status_code, code_of(done)) == (409, 'operation_outcome_unknown'), done.content
        detail = done.json()['detail']
        assert detail['results'] == [] and detail['operation']['state'] == 'unknown'
        after = tokens_now(data, (DEFAULT, B))
        watch(log_scan, data)
        assert after[DEFAULT]['token'] is None and after[B]['token'] == before[B]['token']
        assert PENDING in os.listdir(data) and all(event.is_set() for event in changed.values())
        lines = [record.getMessage() for record in log_scan.records if record.name == ADMIN_LOGGER]
        assert profile_admin.REVOKE_ALL_STOPPED % 'RuntimeError' in lines
        async with runtime.mcp() as client:
            for where in (DEFAULT, B):
                old = before[where]['token']
                for path, headers in (('/mcp', {**ACCEPT, 'Authorization': 'Bearer ' + old}),
                                      (f'/private_{old}/mcp', ACCEPT)):
                    response = await client.post(path, headers=headers, json=initialize_message())
                    assert answer(response)[::2] == STATE_UNAVAILABLE, where
        retried = await panel.revoke_all()
        assert retried.status_code == 200 and PENDING not in os.listdir(data)
        async with runtime.mcp() as client:
            for where in (DEFAULT, B):
                old = before[where]['token']
                assert answer(await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer ' + old},
                                                json=initialize_message())) == BEARER_REQUIRED, where


async def test_revoke_all_is_the_emergency_stop_while_the_index_cannot_be_used(tmp_path, log_scan):
    """An unusable index (changed behind the add-on's back: DQ-12) still lets every profile be revoked: If-Match is the
    unusable index's own ETag (the default bootstrap's profile_index_etag; the list's is refused)."""
    from test_profile_admin_api import replace_index
    data = setup(tmp_path, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B,))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        panel = Admin(runtime, await csrf_of(runtime))
        etag = await panel.etag()
        replace_index(data)
        raw = (await bootstrap_of(runtime))['profile_index_etag']
        refused = await panel.revoke_all(etag=etag)
        assert refused.status_code == 409 and refused.headers['etag'] == raw
        done = await panel.revoke_all(etag=raw)
        assert done.status_code == 200, done.content
        assert all(value['token'] is None for value in tokens_now(data, (DEFAULT, B)).values())


async def test_revoke_all_runs_in_a_worker_thread_and_8081_answers_meanwhile(tmp_path, log_scan, monkeypatch):
    """restore_lock.revoke_all is synchronous (two state writes and their fsyncs a profile): it runs in a worker thread,
    so the event loop goes on serving 8081 (and the other listener) while it works."""
    data = setup(tmp_path, extras=(B,))
    started, release = threading.Event(), threading.Event()
    real = restore_lock.revoke_all
    seen = []

    def slow(*args, **kwargs):
        seen.append(threading.current_thread() is threading.main_thread())
        started.set()
        assert release.wait(10)
        return real(*args, **kwargs)
    monkeypatch.setattr(restore_lock, 'revoke_all', slow)
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B,))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        panel = Admin(runtime, await csrf_of(runtime))
        task = asyncio.create_task(panel.revoke_all())
        async with asyncio.timeout(10):
            while not started.is_set():
                await asyncio.sleep(.01)
        async with runtime.mcp() as client:
            async with asyncio.timeout(2):
                ready = await client.get('/health/ready')
        assert ready.status_code in (200, 503) and not task.done()
        release.set()
        assert (await asyncio.wait_for(task, 10)).status_code == 200
    assert seen == [False]


async def test_revoke_all_ends_the_notice_of_a_kept_default_token(tmp_path, log_scan):
    """Switched on without profile data, restored: the default profile's token is kept and the notice shown; "revoke
    all" revokes it, so the notice is gone from the bootstrap and from the disk."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    assert rd.detect(data, enabled=True).sentinel == rd.ESTABLISHED  # the first switched-on start's sentinel
    mark_restored(data)
    async with multi_profile_runtime(PRODUCT, data) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        boot = await bootstrap_of(runtime)
        assert set(boot['restore_notice']) == {'at'} and 'restore_review' not in boot
        panel = Admin(runtime, await csrf_of(runtime))
        assert (await panel.revoke_all()).status_code == 200
        assert 'restore_notice' not in await bootstrap_of(runtime)
    assert NOTICE not in os.listdir(data)


# ---- the pipeline's order for the new routes (HM-10 hand-off: every wait gets its round) ----

async def test_the_new_routes_check_the_role_after_every_wait(tmp_path, log_scan):
    """Step 10 after every lock each new route waits for: a role taken away meanwhile refuses it there (403) and
    nothing changes. "revoke all" waits for the add-on's profile lock, the default profile's lock and every registered
    profile's lock; a review and a quarantine directory's deletion for the add-on's profile lock."""
    data = restored_profiles(tmp_path, extras=(B, C), broken=(D,))
    removed = asyncio.Event()
    asked = []

    async def changing(user):
        asked.append(user)
        return user == ADMIN['X-Remote-User-Id'] and not removed.is_set()

    async def refused_while_held(lock, request):
        removed.clear()
        await lock.acquire()
        try:
            task = asyncio.create_task(request())
            count = len(asked)
            async with asyncio.timeout(5):
                while len(asked) == count:
                    await asyncio.sleep(.01)
            removed.set()
        finally:
            lock.release()
        response = await asyncio.wait_for(task, 10)
        assert answer(response)[::2] == REFUSED
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C)), verifier=changing) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        manager = runtime.manager
        panel = Admin(runtime, await csrf_of(runtime))
        etag = await panel.etag()
        directory, = [name for name in os.listdir(profiles.Layout(data).profiles)
                      if profiles.parse_quarantine_name(name)]
        name = directory[len(profiles.QUARANTINE_PREFIX):]
        before = tree_of(data)
        rounds = [(lock, lambda: panel.revoke_all(etag=etag))
                  for lock in (manager.admin.lock, manager.get(DEFAULT).runtime.mutation_lock,
                               manager.get(B).runtime.mutation_lock, manager.get(C).runtime.mutation_lock)]
        rounds += [(manager.admin.lock, lambda: panel.review(B, etag=etag)),
                   (manager.admin.lock, lambda: panel.delete_quarantined(name, etag=etag))]
        for lock, request in rounds:
            await refused_while_held(lock, request)
        assert tree_of(data) == before
        removed.clear()
        listed = await panel.record()  # the record waits for nothing: the role asked twice (steps 6 and 10)
        assert listed.status_code == 200


# ---- switched off: none of this exists (contract 1.2) ----

async def test_switched_off_the_new_routes_are_unknown(tmp_path, log_scan):
    """A product not switched on has no management route of HM-13c (plan 8.4 休眠處理: no management route while
    switched off; the owner approved only the bootstrap's one field): each is an unknown operation (404, empty), and a
    token/rotate never waits for a review."""
    data = restored_copy(tmp_path, PRODUCT, 'off')
    log_scan.watch(stored(data)['token'], stored(data)['child_token'])
    async with production_runtime(PRODUCT, data) as runtime:
        await settle(runtime, 'configured')
        async with runtime.admin() as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            headers = {**ADMIN, 'X-CSRF-Token': boot['csrf']}
            for method, path in (('POST', '/api/profiles/revoke-all'), ('GET', '/api/profiles/restore-record'),
                                 ('POST', '/api/profiles/default/restore-review'),
                                 ('POST', f'/api/profiles/quarantine/{B}-20261116T000000Z/delete')):
                response = await admin.request(method, path, headers=headers)
                assert (response.status_code, response.content) == (404, b''), path
            rotated = await admin.post('/api/token/rotate', headers=reviewed_headers(boot, ADMIN))
            assert rotated.status_code == 200
            log_scan.watch(rotated.json()['token'])


def test_the_new_receipts_are_kept_beside_the_index():
    """Their kinds and subjects (contract 3.5): "revoke all" (all), a review (the profile's id, the default profile's
    too), a quarantine directory's deletion (its name); anything else is no subject."""
    for subject in ('all', 'default', B, f'{B}-20261116T093015Z', f'{B}-20261116T093015Z-2',
                    'profiles.json.quarantine-20261116T093015Z'):
        assert operations.SUBJECT.fullmatch(subject), subject
    for subject in ('All', 'defaults', f'.quarantine-{B}-20261116T093015Z', f'{B}-2026', 'x'):
        assert not operations.SUBJECT.fullmatch(subject), subject
    assert {'profile.revoke_all', 'profile.restore_review', 'profile.quarantine_delete'} <= set(
        operations.PROFILE_RESULTS)
