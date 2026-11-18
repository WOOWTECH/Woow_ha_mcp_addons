"""HM-13b test harness: an add-on's /data/mcp on disk, HA backups and Supervisor restores of it, and the boot guard.

Disk holds what the runtime and HM-10 make: the default profile's store, additional profiles created as HM-10 creates
them (tests/multi_profile_runtime.create_profile: born complete, with a synthetic backend, an index entry unless an
orphan), operation receipts written through operations.OperationJournal, and the instance sentinel of restore detection
(HM-13a) once a start saw the product switched on. backup() copies /data/mcp as an HA backup holds it; restore() puts a
copy back as Supervisor does (remove, copytree with links kept, no chown: test_restore_detection.supervisor_restore)
and leaves the marker the entrypoint saves on a root-owned restore (signal 1) unless told not to. start() is the
management process's start up to the guard (run_product: the default profile's store, then restore_lock.guard);
nothing is served. Tokens are made at run time (plan 12.0 rule 4) and watched by the log scan, labels too.

StopAt is the os module of the guard's modules for fault injection: a start stopped (Crash) at the nth call that
changes the disk, before it runs or right after, or a call failing with an OSError (a full disk).
"""
from __future__ import annotations

from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import time

import pytest

from mcp_admin_core import config, operations, origin_policy, profiles, restore_detect, restore_lock
from mcp_admin_core.products import ProductStore
from multi_profile_runtime import create_profile
from test_restore_detection import Crash, after_tick, supervisor_restore

ACTOR = 'restore-guard-tester'
LABELS = {'a': 'Ledger Alpha', 'b': 'Ledger Bravo', 'c': 'Ledger Charlie', 'd': 'Ledger Delta', 'e': 'Ledger Echo'}
DEFAULT = profiles.DEFAULT_PROFILE
# The modules whose os calls write the data directory while the guard runs (the stores, the receipts, the layout, the
# sentinel, the guard itself).
GUARD_MODULES = (config, operations, profiles, restore_detect, restore_lock)


def newest_ctime(root):
    return max(path.lstat().st_ctime_ns for path in [Path(root), *Path(root).rglob('*')])


class Disk:
    def __init__(self, parent, log_scan, product='odoo'):
        self.parent = Path(parent)
        self.data = self.parent / 'mcp'
        self.product, self.log_scan = product, log_scan
        self.layout = profiles.Layout(self.data)
        self.ports = iter(range(18000, 18100))
        self.backups = 0
        store = ProductStore(self.data, product)
        try:
            self.watch(store.load())
        finally:
            store.close()

    def watch(self, state):
        self.log_scan.watch_state(state)
        return state

    def add(self, profile_id, *, indexed=True, label=None):
        """An additional profile as HM-10 creates it (indexed=False: an orphan, its directory only). Its label is LABELS'
        (never text a log line has: the log scan matches labels in any letter case)."""
        label = label or LABELS[profile_id[0]]
        self.log_scan.watch(label, kind='name')
        return self.watch(create_profile(self.data, self.product, profile_id, label=label, port=next(self.ports),
                                         indexed=indexed))

    def directory(self, profile_id=DEFAULT):
        return self.data if profile_id == DEFAULT else self.layout.profile(profile_id)

    def state(self, profile_id=DEFAULT):
        return json.loads((self.directory(profile_id) / 'state.json').read_text())

    def tokens(self, profile_id=DEFAULT):
        value = self.state(profile_id)
        return value['token'], value['child_token']

    def held(self):
        """Every token and child token in a state.json under /data/mcp (profile and quarantine directories too)."""
        found = set()
        for path in [self.data / 'state.json', *self.layout.profiles.glob('*/state.json')]:
            try:
                value = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            found.update(v for v in (value.get('token'), value.get('child_token')) if isinstance(v, str))
        return found

    def store(self, profile_id=DEFAULT):
        if profile_id == DEFAULT:
            return ProductStore(self.data, self.product)
        return ProductStore(self.layout.profile(profile_id), self.product, existing_only=True)

    def rotate(self, profile_id=DEFAULT):
        """A token/rotate, as the panel makes one (its state only)."""
        store = self.store(profile_id)
        try:
            return self.watch(store.change_token(secrets.token_urlsafe(32), action='rotate')[0])
        finally:
            store.close()

    def receipt(self, profile_id=DEFAULT, kind='token.revoke', *, when_ms=None):
        """A completed operation receipt in the profile's journal ('index': the journal beside the index, a creation
        receipt of an additional profile's id; HM-27 'origin': the journal beside the add-on's Origin policy, a save of
        it). Returns its operation id."""
        if profile_id == 'index':
            journal = operations.OperationJournal(self.layout.index, results=operations.PROFILE_RESULTS, subjects=True)
            kind, subject = 'profile.create', 'e' * 24
        elif profile_id == 'origin':
            journal = operations.OperationJournal(self.layout.origin_policy, results=origin_policy.RESULTS)
            kind, subject = origin_policy.KIND, None
        else:
            journal = operations.OperationJournal(self.directory(profile_id) / 'state.json')
            subject = None
        operation_id = f'{when_ms or int(time.time() * 1000)}.{secrets.token_hex(12)}'
        data, prior, fingerprint = journal.inspect(operation_id, kind, ACTOR)
        assert prior is None
        journal.begin(operation_id, data, kind, ACTOR, fingerprint, **({} if subject is None else {'subject': subject}))
        journal.complete(operation_id, data)
        return operation_id

    def replay(self, operation_id, profile_id=DEFAULT, kind='token.revoke'):
        """What a replay of operation_id finds in the journal now: 'completed', 'new' or the refusal's (status, code)."""
        if profile_id == 'index':
            journal = operations.OperationJournal(self.layout.index, results=operations.PROFILE_RESULTS, subjects=True)
            kind = 'profile.create'
        elif profile_id == 'origin':
            journal = operations.OperationJournal(self.layout.origin_policy, results=origin_policy.RESULTS)
            kind = origin_policy.KIND
        else:
            journal = operations.OperationJournal(self.directory(profile_id) / 'state.json')
        try:
            _, prior, _ = journal.inspect(operation_id, kind, ACTOR)
        except Exception as error:  # admin_auth.BadRequest
            return error.status, (error.detail or {}).get('code')
        return 'new' if prior is None else prior['state']

    def start(self, *, enabled, **options):
        """The management process's start up to the guard: the default profile's store, then the guard."""
        store = ProductStore(self.data, self.product)
        try:
            return restore_lock.guard(store, self.product, enabled=enabled, **options)
        finally:
            store.close()

    def start_under(self, proxy, *, enabled, **options):
        """start() with proxy (StopAt) as the os of the guard's modules once the default profile's store is open."""
        store = ProductStore(self.data, self.product)
        try:
            with guard_os(proxy):
                return restore_lock.guard(store, self.product, enabled=enabled, **options)
        finally:
            store.close()

    def detection(self, enabled):
        """What restore detection sees now, without writing anything (the sentinel must already be there)."""
        verdict = restore_detect.detect(self.data, enabled=enabled)
        assert verdict.sentinel not in (restore_detect.ESTABLISHED, restore_detect.REBUILT)
        return verdict

    def backup(self):
        """An HA backup of /data/mcp now (a copy outside it)."""
        self.backups += 1
        copy = self.parent / f'backup-{self.backups}'
        shutil.copytree(self.data, copy, symlinks=True)
        return copy

    def restore(self, backup, *, marker=True):
        """Supervisor's restore of backup (a new file for every entry, a ctime of now), and the entrypoint's marker."""
        after_tick(self.parent, max(newest_ctime(self.data), newest_ctime(backup)))
        supervisor_restore(backup, self.data)
        if marker:
            os.close(os.open(self.data / profiles.RESTORE_MARKER_NAME,
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))

    def names(self):
        return sorted(path.name for path in self.data.iterdir())

    def quarantines(self):
        return sorted(path.name for path in self.layout.profiles.iterdir()
                      if profiles.parse_quarantine_name(path.name)) if self.layout.profiles.exists() else []


def tree(root):
    """Every entry under root (root itself included): kind, mode, inode, links, size, mtime, ctime, a file's bytes."""
    found = {}
    for path in [Path(root), *sorted(Path(root).rglob('*'))]:
        info = path.lstat()
        content = path.read_bytes() if stat.S_ISREG(info.st_mode) else None
        found[str(path.relative_to(root))] = (stat.S_IFMT(info.st_mode), stat.S_IMODE(info.st_mode), info.st_ino,
                                              info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                                              content)
    return found


def break_state(directory, kind):
    """Make a profile directory one the store cannot open (plan 8.4 C: any reason)."""
    directory = Path(directory)
    state = directory / 'state.json'
    if kind == 'no writer lock':
        (directory / '.writer.lock').unlink()
    elif kind == 'an unknown key':
        value = json.loads(state.read_text())
        value['unknown'] = 1
        state.write_text(json.dumps(value))
    elif kind == 'a second link':
        os.link(state, directory / 'state-copy.json')
    elif kind == 'too large':
        value = json.loads(state.read_text())
        value['disabled'] = ['x' * 100] * 700
        state.write_text(json.dumps(value))
    elif kind == 'another product':
        value = json.loads(state.read_text())
        value['product'] = 'emqx'
        state.write_text(json.dumps(value))
    elif kind == 'no state':
        state.unlink()
    elif kind == 'not JSON':
        state.write_bytes(b'{"token": ')
    else:
        raise AssertionError(kind)


class StopAt:
    """os for GUARD_MODULES: counts the calls that change the disk (a file created, written, synced, renamed, replaced
    or removed, a directory made or removed), and stops the start at the nth: Crash before the call runs (after=False)
    or right after it (after=True). error: an OSError raised for every such call of the kinds named in fail instead."""

    CHANGES = frozenset({'write', 'fsync', 'replace', 'rename', 'unlink', 'rmdir', 'mkdir', 'link', 'open'})

    def __init__(self, nth=None, *, after=False, fail=(), error=None):
        self.nth, self.after, self.fail, self.error = nth, after, frozenset(fail), error
        self.count = 0
        self.calls = []

    def __getattr__(self, name):
        real = getattr(os, name)
        if name not in self.CHANGES:
            return real

        def call(*args, **kwargs):
            if name == 'open':
                flags = args[1] if len(args) > 1 else kwargs.get('flags', 0)
                if not flags & os.O_CREAT:
                    return real(*args, **kwargs)
            if name in self.fail:
                raise self.error
            self.count += 1
            subject = os.fspath(args[0]) if args and isinstance(args[0], (str, os.PathLike)) else None
            self.calls.append((name, subject))
            if self.count == self.nth and not self.after:
                raise Crash(f'stopped before call {self.count} ({name})')
            try:
                result = real(*args, **kwargs)
            except BaseException:
                if self.count == self.nth and self.after:
                    raise Crash(f'stopped after call {self.count} ({name}), which failed') from None
                raise
            if self.count == self.nth and self.after:
                raise Crash(f'stopped after call {self.count} ({name})')
            return result
        return call


@contextmanager
def guard_os(proxy):
    """proxy as the os module of every GUARD_MODULE, and every store the guard opens kept, so that a stopped start's
    stores are closed as its process would have ended (its writer locks released)."""
    opened = []

    class Kept(ProductStore):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            opened.append(self)

    with pytest.MonkeyPatch.context() as patch:
        for module in GUARD_MODULES:
            patch.setattr(module, 'os', proxy)
        patch.setattr(restore_lock, 'ProductStore', Kept)
        try:
            yield proxy
        finally:
            for store in opened:
                store.close()


DISK_FULL = OSError(errno.ENOSPC, 'No space left on device')


def lying_revocation(monkeypatch, profile_id):
    """A store of profile_id whose token revocation reports success and writes nothing (a write that never reached
    the disk): what the independent check (E) is there for."""
    real = ProductStore.change_token

    def change_token(self, token, *, action):
        if self.directory.name == profile_id:
            return self.load(), True
        return real(self, token, action=action)
    monkeypatch.setattr(ProductStore, 'change_token', change_token)


def unlistable_once(monkeypatch, failures=1):
    """profiles.scan_profiles fails as it does for any OSError on opening or listing profiles/ (EMFILE, ENFILE, ENOMEM,
    EIO, EACCES) for its first *failures* calls, then lists again: a profiles directory that cannot be listed for a
    while (HM-13b review MF-2). A mode of 000 would not do: root, as the CI runs, lists it all the same. Returns the
    calls made."""
    real, calls = profiles.scan_profiles, []

    def scan(layout):
        calls.append(layout)
        if len(calls) <= failures:
            raise profiles.ProfileDataError('profiles directory unavailable')
        return real(layout)
    monkeypatch.setattr(profiles, 'scan_profiles', scan)
    return calls


def during_the_record(monkeypatch, change):
    """change() runs right before the guard saves restore-record.json (step D), between what it did (B, C) and its
    independent check (E): a stray change on disk that E has to see."""
    real = restore_lock._write_record

    def write_record(root, value):
        change()
        return real(root, value)
    monkeypatch.setattr(restore_lock, '_write_record', write_record)
