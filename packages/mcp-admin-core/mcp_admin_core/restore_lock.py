"""The boot guard (multi-profile HM-13b; plan 8.4 "開機守門", I9, I13; contract 1.2, 3.5, 3.6, 4.1, 7, 8, 9).

What the management process does about a restore of its data, an unfinished "revoke all" and dormant profiles, before
any child starts and before any listener exists. Not behind the multi-profile switch (plan 3.3; contract 1.2): every
product's next release carries it. run_product and apps/n8n/run.py call guard() right after the legacy migration and
the default profile's store; a failure raises ConfigError, nothing is served ("runtime unavailable"), and the next
start runs the guard again.

When it acts (any of):
- a restore: restore_detect.detect() (HM-13a) sees the entrypoint's marker (signal 1) or a sentinel that is not the one
  its record names (signal 2);
- an unfinished "revoke all": anything at .revoke-all-pending (plan 8.4 全部撤銷, C1-S6; HM-13c serves the route);
- dormant profiles: the product is not switched on but profile data is on disk (I13): at every start.
A product that is not switched on and has no profile data (every installation today) is left alone: detect() looks
up three names and writes nothing, and one more name is looked up here. After a restore, one WARNING says that the MCP
token is back at its value at the time of the backup (DQ-03 (b)) and the marker is removed; nothing else is read or
written.

Scope S (plan 8.4): the default profile, every 24 hex directory under profiles/ (indexed, an orphan, or behind an
unusable index: the index never decides; only its labels are shown in the record), the existing quarantine directories
(read for the snapshot only, never opened as a profile); other names are counted. A profiles entry that is not a
directory holds nothing that can be opened or served (contract 9 #119: the guard goes on); a profiles directory that
cannot be listed now (EMFILE, EIO, ENOMEM, no permission, another uid's: HM-13b review MF-2) may hold the backup's
tokens, so nothing finishes until it can be listed. A restore runs:
A  the snapshot: every readable state's token and child token, in memory only.
B  the default profile (DQ-03 (b) A2; DEFAULT_REVOKED_WHEN_SWITCHED_ON): with profile data on disk revoked (token None,
   one history entry), a new child token and its receipts archived; without, left exactly as restored: a notice.
C  every profile directory, opened existing-only (never created): revoked, a new child token, its receipts archived;
   one that cannot be opened for any reason (no writer lock, an unknown key, a second link, more than 64 KiB, another
   product, no state ...) is renamed profiles/.quarantine-<id>-<UTC>[-n] (never routed, delete only), unless its writer
   lock is held (then it fails: never moved away from under its holder). The receipts beside the index are archived too
   (operations.archive_for_restore: every older operation id answers 410 operation_restored).
D  restore-record.json: when, the two signals, what each profile is (id, label, identity fields, policy) and what was
   done to its token, reviewed_at null, the quarantine directories; never a token or a credential (identity_fields).
E  the independent check (PaaS restore_inplace._verify: "nothing that authenticated against the backup authenticates
   now"): every directory of S read again from disk, not through the stores that wrote: each revoked token is None,
   each new child token differs from what A found, no token or child token equals any value A found (the default
   profile's own two aside while it is kept, and then they must be unchanged), the profile directories are those A
   found minus the quarantined ones, and every quarantine directory is one (never a profile).
F  each write was durable as it went; the sentinel and its record are rebuilt (restore_detect.rebuild), then the markers
   are removed: .revoke-all-pending, the restore marker last.
Any failure keeps the markers and stops the start; every profile that can be revoked is revoked first. A start stopped
anywhere before F's last step sees the restore again and redoes everything (each step is idempotent: a token already
None gets no second history entry, a child token is renewed again, a journal without receipts is not archived again,
the record is written again).

Dormant profiles (plan 3.3, 8.4 休眠處理): every profile directory whose token is not revoked yet is revoked with a new
child token (one already revoked is not touched at all) and one that cannot be opened is quarantined; the default
profile is left as it is unless a restore is seen at the same start. When anything was done, restore-record.json says
so (its "dormant" part). Outcome.dormant is the number of profile directories: the bootstrap's dormant_profiles.

"Revoke all": revoke_all() saves .revoke-all-pending first (mark_revoke_all), revokes every profile (the default
profile's included, and every store its caller holds even when profiles/ cannot be listed) with a new child token, runs
E, and removes the marker only when every profile was revoked and the check passed; otherwise the marker stays and the
next start finishes it, whatever the switch.

The sentinel: nothing here chmods, chowns, writes, links or renames it, except restore_detect.rebuild() in F (HM-13a's
invariant; tests/test_restore_lock.py reviews every call that sets a mode, an owner or a time). An entry at one of the
guard's own names (profiles.ASIDE_NAMES: the sentinel's, its record's and the record's temporary, the two markers', the
restore record's, a receipts archive's) that is a directory (a forged backup: the restore repair accepts directories;
HM-13a review SF-7, HM-13b review S-1) is moved aside to <name>.quarantine-<UTC>[-n], never deleted, so that the
rebuild, the markers' removal, the record and the archives can work.

Log lines (logger mcp_admin_core.restore_lock, WARNING: the add-on log shows WARNING and above): fixed text; a profile is
named by its id's first 8 characters (I7); never a token, a label, a value or an exception's text.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import fcntl
import json
import logging
import os
from pathlib import Path
import re
import secrets
import stat

from . import identity_fields, operations, profiles, restore_detect
from .config import ConfigError, strict_json
from .products import ProductStore

logger = logging.getLogger(__name__)

# DQ-03 (2026-11-14, the owner took (b) A2): a restore revokes the default profile only when profile data is on disk.
# True would be option (a): every restore of a switched-on product revokes it too (PaaS restore_guard); changing it is a
# decision of its own (DQ-35 first).
DEFAULT_REVOKED_WHEN_SWITCHED_ON = False

DEFAULT = profiles.DEFAULT_PROFILE
MARKER = profiles.RESTORE_MARKER_NAME
REVOKE_ALL = profiles.REVOKE_ALL_MARKER_NAME
RECORD = profiles.RESTORE_RECORD_NAME
SENTINEL_NAMES = (profiles.SENTINEL_NAME, profiles.INSTANCE_RECORD_NAME, profiles.INSTANCE_RECORD_TEMPORARY_NAME)
RECORD_VERSION = 1
# A state is at most 64 KiB (Store) and a row shows a part of one: 1 MiB holds the default profile, the index's five
# and ten orphans with states that large; a record over it (only a backup put together by hand) stops the guard.
RECORD_LIMIT = 1048576
STATE_LIMIT = 65536  # a state.json, as Store reads it
SHOWN = (identity_fields.POLICY, identity_fields.SESSION)  # the state fields the record shows besides the identity
_TOKEN = re.compile(r'[A-Za-z0-9_-]{43}')

# The log lines (fixed text; %s: a profile's id's first 8 characters, an exception class, a reason below).
KEPT_NOTICE = ('restore guard: the data was restored from a backup; the MCP token is back to its value at the time of '
               'that backup (nothing was revoked: no profile data). Rotate it in the panel if it may have leaked '
               'since')
REVOKED_NOTICE = ('restore guard: the data was restored from a backup; the MCP token of every profile (the default '
                  "profile's included) was revoked and its child token renewed. Check each profile in the panel before "
                  'issuing new tokens')
DORMANT_NOTICE = ('restore guard: this version serves no additional profiles; the MCP token of %d dormant profile(s) '
                  'is revoked (new tokens are issued after a check once the product serves them again)')
REVOKE_ALL_NOTICE = ('restore guard: a "revoke all" had not finished when the add-on stopped; it is finished now (the '
                     'MCP token of every profile revoked)')
REVOKED = 'restore guard [profile=%s]: token revoked, child token renewed'
QUARANTINED = ('restore guard [profile=%s]: its state cannot be read; its directory was moved to the quarantine '
               '(never served; it can only be deleted)')
NOT_REVOKED = 'restore guard [profile=%s]: its token could not be revoked (%s)'
NOT_QUARANTINED = ('restore guard [profile=%s]: its state cannot be read and its directory could not be moved to the '
                   'quarantine')
LOCKED = ('restore guard [profile=%s]: its state is held by another writer; it was neither revoked nor moved to the '
          'quarantine')
NOT_ARCHIVED = 'restore guard [profile=%s]: its operation receipts could not be archived'
INDEX_NOT_ARCHIVED = 'restore guard: the operation receipts beside the profile index could not be archived'
UNLISTABLE = 'restore guard: the profiles directory cannot be listed; nothing in it is served'
SET_ASIDE = 'restore guard: %s was not a plain file; it was moved aside to %s'
SET_ASIDE_IN_PROFILE = 'restore guard [profile=%s]: %s was not a plain file; it was moved aside to %s'
UNFINISHED = ('restore guard: not finished (%s); nothing is served and no child is started. The guard runs again at '
              'the next start')
MARKER_LEFT = 'restore guard: %s; starting (no profile data: nothing to revoke), the next start tries again'


def _utc_now():
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Outcome:
    """What one start's guard found and did (never a secret). restored: a restore was seen; revoke_all: a pending
    "revoke all" was finished; dormant: switched off with profile data, the number of profile directories (every one
    revoked), else None; default_revoked: the default profile's token was revoked; revoked: the profile directories
    whose token this start revoked, by id; quarantined: the quarantine directories this start made."""
    restored: bool = False
    revoke_all: bool = False
    dormant: int | None = None
    default_revoked: bool = False
    revoked: tuple[str, ...] = ()
    quarantined: tuple[str, ...] = ()


@dataclass(frozen=True)
class Revocation:
    """One profile's part of a "revoke all" (contract 3.1: results [{id, result}]): 'revoked', 'failed' or
    'quarantined' (a directory that could not be opened: moved to the quarantine, never served)."""
    profile_id: str
    result: str


@dataclass(frozen=True)
class RevokeAll:
    """A "revoke all": every profile's result, the default profile first, then the profile directories by id; finished
    False when the marker stays (a profile failed or the check did not pass: the next start finishes it)."""
    results: tuple[Revocation, ...]
    finished: bool


class Unfinished(Exception):
    """The guard cannot finish now; carries the reason of its log line."""


def guard(store, product, *, enabled, now=None) -> Outcome:
    """The boot guard for the default profile's open store (its directory is the data directory, normally /data/mcp).
    enabled: the product's multi-profile switch (features.enabled, read by the caller at this start). now: the clock
    (tests). Returns what it did; ConfigError, with every marker kept, when it could not finish."""
    now = now or _utc_now
    root = Path(store.directory)
    detection = restore_detect.detect(root, enabled=enabled)  # the first switched-on start makes the sentinel here
    pending = revoke_all_pending(root)
    if not (detection.active or pending):
        # Not switched on, no profile data: today's installation. A restore only gets its notice (DQ-03 (b)); a marker
        # that cannot be removed is left for the next start (nothing here is revoked, as the entrypoint starts without
        # profile data when it cannot save the marker).
        if detection.restored:
            logger.warning(KEPT_NOTICE)
            try:
                _finish(root, now, markers=(MARKER,))
            except Unfinished as stop:
                logger.warning(MARKER_LEFT, stop.args[0])
        return Outcome(restored=detection.restored)
    data = profiles.has_profile_data(root)
    restored, dormant = detection.restored, not enabled and data
    if not (restored or pending or dormant):
        return Outcome()
    revoke_default = pending or (restored and (data or (enabled and DEFAULT_REVOKED_WHEN_SWITCHED_ON)))
    sweep = _Sweep(store, product, now)
    try:
        sweep.look()
        cutoff = int(now().timestamp() * 1000) if restored else None
        if revoke_default and sweep.revoke(DEFAULT, store) and cutoff is not None:
            sweep.archive(DEFAULT, store.path, cutoff)
        sweep.directories_pass(skip_revoked=not (restored or pending), cutoff=cutoff)
        if cutoff is not None:
            sweep.archive(None, sweep.layout.index, cutoff)
        sweep.raise_failures()
        if restored or (dormant and (sweep.revoked or sweep.quarantined)):
            sweep.record(detection if restored else None, dormant=dormant, default_revoked=revoke_default)
        if sweep.check(strict=restored or pending, default_kept=not revoke_default):
            raise Unfinished('the check after revoking did not pass')
        markers = (REVOKE_ALL,) * pending + (MARKER,) * restored
        _finish(root, now, rebuild=restored and detection.active, enabled=enabled, markers=markers)
    except Unfinished as stop:
        logger.warning(UNFINISHED, stop.args[0])
        raise ConfigError('restore guard unfinished') from None
    revoked = tuple(where for where in sweep.revoked if where != DEFAULT)
    if pending:
        logger.warning(REVOKE_ALL_NOTICE)
    if restored:
        logger.warning(REVOKED_NOTICE if revoke_default else KEPT_NOTICE)
    elif dormant and revoked and not pending:
        logger.warning(DORMANT_NOTICE, len(revoked))
    return Outcome(restored=restored, revoke_all=pending, dormant=sweep.remaining() if dormant else None,
                   default_revoked=revoke_default, revoked=revoked,
                   quarantined=tuple(name for _, name in sweep.quarantined))


def mark_revoke_all(root) -> None:
    """Begin a "revoke all": .revoke-all-pending saved, file and directory fsynced, before any token is touched (one
    already there is kept: any entry counts). ConfigError when it cannot be saved (then nothing was revoked)."""
    try:
        fd = _open_directory(root)
    except OSError:
        raise ConfigError('revoke all not started') from None
    try:
        try:
            marker = os.open(REVOKE_ALL, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            pass
        else:
            try:
                os.fsync(marker)
            finally:
                os.close(marker)
        os.fsync(fd)
    except OSError:
        raise ConfigError('revoke all not started') from None
    finally:
        os.close(fd)


def revoke_all_pending(root) -> bool:
    """Whether a "revoke all" has not finished: any entry at .revoke-all-pending, or one a lookup cannot rule out."""
    return _present(Path(root) / REVOKE_ALL)


def revoke_all(store, product, *, stores=None, now=None) -> RevokeAll:
    """'Revoke all' (plan 8.4 全部撤銷, C1-S6; contract 3.1; HM-13c's route): mark_revoke_all(), then every profile
    revoked with a new child token, the default profile first, then the profile directories and the stores the caller
    holds, by id (a directory that cannot be opened is quarantined, one whose writer lock is held elsewhere failed);
    then step E, whatever failed (a revocation that never reached the disk is failed too); the marker is removed only
    when nothing failed, profiles/ could be listed and the check passed. store: the default profile's open store.
    stores: {additional profile id: open store} the caller holds (the running manager's registered profiles; their
    writer locks are held): used instead of opening those directories, and revoked even when profiles/ cannot be listed
    (HM-13b review MF-2). results: the default profile, then every profile directory found and every store given.
    ConfigError when the marker cannot be saved (nothing was revoked); ValueError for a store that is not an additional
    profile's (nothing was done).

    The caller (HM-13c) holds the add-on's profile lock (ProfileAdmin.lock: what a creation, a deletion and the index
    quarantine take) and every registered profile's own lock, so that no profile is half created or half deleted meanwhile
    (a directory being created would read as one that cannot be opened and be quarantined); and it runs this in a worker
    thread (asyncio.to_thread): it is synchronous, with two state writes and their fsyncs per profile."""
    if any(not profiles.is_profile_id(profile_id) for profile_id in stores or {}):
        raise ValueError('stores: additional profiles only')
    now = now or _utc_now
    root = Path(store.directory)
    mark_revoke_all(root)
    sweep = _Sweep(store, product, now, stores)
    sweep.look()
    sweep.revoke(DEFAULT, store)
    sweep.directories_pass(skip_revoked=False, cutoff=None)
    finished = not (sweep.failed or sweep.reasons)
    if sweep.check(strict=True, default_kept=False):
        finished = False
    if finished:
        try:
            _finish(root, now, markers=(REVOKE_ALL,))
        except Unfinished:
            finished = False
    moved = {profile_id for profile_id, _ in sweep.quarantined}
    results = [Revocation(DEFAULT, sweep.result(DEFAULT))]
    results += [Revocation(profile_id, 'quarantined' if profile_id in moved else sweep.result(profile_id))
                for profile_id in sweep.targets()]
    return RevokeAll(tuple(results), finished)


def read_record(root) -> dict | None:
    """restore-record.json as the guard wrote it (HM-13c reads it): None when there is none; ConfigError when it is not
    a single-link regular file of this uid within RECORD_LIMIT holding strict JSON of RECORD_VERSION."""
    try:
        fd = os.open(Path(root) / RECORD, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError:
        raise ConfigError('restore record unavailable') from None
    try:
        raw = _read_bounded(fd, RECORD_LIMIT)
    finally:
        os.close(fd)
    try:
        value = strict_json(raw) if raw is not None else None
    except (ValueError, RecursionError):
        value = None
    if not isinstance(value, dict) or value.get('version') != RECORD_VERSION:
        raise ConfigError('restore record unavailable')
    return value


def read_tokens(directory):
    """(token, child token) of the state.json in directory, read from disk without its lock and without any change;
    None when it is not a single-link regular file of this uid within 64 KiB holding a token (or null) and a child
    token of the stored form."""
    try:
        fd = os.open(Path(directory) / 'state.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        raw = _read_bounded(fd, STATE_LIMIT)
    finally:
        os.close(fd)
    if raw is None:
        return None
    try:
        value = strict_json(raw)
    except (ValueError, RecursionError):
        return None
    if not isinstance(value, dict) or 'token' not in value:
        return None
    token, child = value['token'], value.get('child_token')
    if token is not None and not (isinstance(token, str) and _TOKEN.fullmatch(token)):
        return None
    if not (isinstance(child, str) and _TOKEN.fullmatch(child)):
        return None
    return token, child


def facts(state):
    """What the record shows of a profile's state (plan 8.4 D; contract 3.6): its identity fields (identity_fields
    IDENTITY: which backend and account) and its policy (POLICY and SESSION fields); never a credential or a token."""
    product = state.product
    source = state if product == 'n8n' else state.connection
    identity = {name: None if source is None else getattr(source, name, None)
                for name in identity_fields.fields(product, identity_fields.IDENTITY)}
    shown = [name for name, kind in identity_fields.STATE_FIELDS.items() if kind in SHOWN]
    stored = state.model_dump(mode='json', include=set(shown))
    return {'identity': identity, 'policy': {name: stored.get(name) for name in shown}}


class _Sweep:
    """One start's (or one "revoke all"'s) walk over S: what it found (A), revoked (B, C), recorded (D) and checked
    (E). Every failure is collected, never raised mid-way: every profile that can be revoked is revoked."""

    def __init__(self, store, product, now, stores=None):
        self.store, self.product, self.now = store, product, now
        self.root = Path(store.directory)
        self.layout = profiles.Layout(self.root)
        self.stores = dict(stores or {})
        self.found = {}          # A: DEFAULT, a profile id or a quarantine name -> (token, child token) or None
        self.old = set()         # every value A found
        self.directories = None  # the profile directories A found, by id; None: profiles/ cannot be listed
        self.quarantines = ()    # the quarantine directories A found
        self.other = 0
        self.shown = {}          # profile id or DEFAULT -> facts() for the record
        self.revoked, self.untouched, self.failed = [], [], []
        self.renewed = {}        # where -> the child token A found
        self.issued = set()      # the new child tokens
        self.quarantined = []    # (profile id, quarantine name) made now
        self.reasons = []        # why it cannot finish (the first one is logged)

    def look(self):
        """A: the snapshot (in memory; never logged). A profiles entry that is not a directory holds nothing that can
        be opened or served (contract 9 #119); one that is a directory, or that a lookup cannot tell, and cannot be
        listed now may hold the backup's tokens: a failure, so that nothing finishes and every marker stays until it
        can be listed (I9; HM-13b review MF-2)."""
        state = self.store.load()  # its store was opened a moment ago: ConfigError stops the start
        self.found[DEFAULT] = (state.token, state.child_token)
        self.shown[DEFAULT] = facts(state)
        try:
            scan = profiles.scan_profiles(self.layout)
        except profiles.ProfileDataError:
            scan = None
            if _maybe_directory(self.layout.profiles):
                self._fail(None, 'the profiles directory cannot be listed', UNLISTABLE)
            else:
                logger.warning(UNLISTABLE)
        if scan is not None:
            self.directories, self.quarantines, self.other = scan.profiles, scan.quarantined, scan.other
            for profile_id in scan.profiles:
                self.found[profile_id] = read_tokens(self.layout.profile(profile_id))
            for name in scan.quarantined:
                self.found[name] = read_tokens(self.layout.profiles / name)
        self.old = {value for pair in self.found.values() if pair for value in pair if value}

    def revoke(self, where, store):
        """Revoke where's token (no second history entry when it is None already) and give it a new child token."""
        try:
            before = store.load()
            store.change_token(None, action='revoke')
            store.update(child_token=self._new_child())
        except (ConfigError, OSError, ValueError) as error:
            self._fail(where, 'a token could not be revoked', NOT_REVOKED, profiles.log_id(where), type(error).__name__)
            return False
        self.revoked.append(where)
        self.renewed[where] = before.child_token
        logger.warning(REVOKED, profiles.log_id(where))
        return True

    def _new_child(self):
        while (value := secrets.token_urlsafe(32)) in self.old or value in self.issued:
            pass
        self.issued.add(value)
        return value

    def targets(self):
        """C's profiles, by id: every profile directory A found and every store the caller holds (a "revoke all"
        revokes those even when profiles/ cannot be listed)."""
        return sorted({*(self.directories or ()), *self.stores})

    def directories_pass(self, *, skip_revoked, cutoff):
        """C, for every one of targets(); skip_revoked (dormant only): one already revoked is not touched."""
        for profile_id in self.targets():
            store, opened = self._store(profile_id)
            if store is None:
                self._quarantine(profile_id)
                continue
            try:
                try:
                    state = store.load()
                except ConfigError as error:
                    self._fail(profile_id, 'a token could not be revoked', NOT_REVOKED, profiles.log_id(profile_id),
                               type(error).__name__)
                    continue
                self.shown[profile_id] = facts(state)
                if skip_revoked and state.token is None:
                    self.untouched.append(profile_id)
                    continue
                if self.revoke(profile_id, store) and cutoff is not None:
                    self.archive(profile_id, store.path, cutoff)
            finally:
                if opened:
                    store.close()

    def _store(self, profile_id):
        """(store, opened here): the caller's store of the profile, else its directory opened existing-only; (None,
        False) when it cannot be opened."""
        if profile_id in self.stores:
            return self.stores[profile_id], False
        try:
            return ProductStore(self.layout.profile(profile_id), self.product, existing_only=True), True
        except (ConfigError, ValueError):
            return None, False

    def _quarantine(self, profile_id):
        """C: a directory that cannot be opened moves to a free quarantine name (S-15: never over anything), and
        profiles/ is fsynced; never one whose writer lock someone else holds."""
        directory = self.layout.profile(profile_id)
        if _lock_held(directory):
            self._fail(profile_id, 'a profile is held by another writer', LOCKED, profiles.log_id(profile_id))
            return
        try:
            name = profiles.free_quarantine_name(self.layout, profile_id, self.now())
            os.rename(directory, self.layout.profiles / name)
            _fsync_directory(self.layout.profiles)
        except (OSError, profiles.ProfileDataError):
            self._fail(profile_id, 'a quarantine could not be made', NOT_QUARANTINED, profiles.log_id(profile_id))
            return
        self.quarantined.append((profile_id, name))
        logger.warning(QUARANTINED, profiles.log_id(profile_id))

    def archive(self, where, config_path, cutoff):
        """C: the receipts of a restore (where None: the journal beside the index). A directory at the archive's name
        (a forged backup: the journal could never be moved there) is moved aside first."""
        journal = operations.journal_path(config_path)
        try:
            _clear(journal.parent, journal.name + operations.RESTORED_SUFFIX, self.now,
                   None if where in (None, DEFAULT) else where)
            operations.archive_for_restore(config_path, cutoff)
        except (OSError, ValueError, Unfinished):
            if where is None:
                self._fail(None, 'receipts could not be archived', INDEX_NOT_ARCHIVED)
            else:
                self._fail(where, 'receipts could not be archived', NOT_ARCHIVED, profiles.log_id(where))

    def _fail(self, where, reason, line, *args):
        if where is not None:
            self.failed.append(where)
        self.reasons.append(reason)
        logger.warning(line, *args)

    def raise_failures(self):
        if self.reasons:
            raise Unfinished(self.reasons[0])

    def result(self, where):
        return 'failed' if where in self.failed else 'revoked'

    def remaining(self):
        """The profile directories left (A's minus the quarantined ones): the bootstrap's dormant_profiles."""
        return len(self.directories or ()) - len(self.quarantined)

    def record(self, detection, *, dormant, default_revoked):
        """D: restore-record.json (contract 3.6; HM-13c reads it), atomically: never a token or a credential."""
        at = self.now().astimezone(timezone.utc).isoformat(timespec='seconds')
        index = profiles.read_index(self.layout.index)
        labels = {entry.id: entry.label for entry in index.entries}
        moved = {profile_id for profile_id, _ in self.quarantined}
        rows = [self._row(DEFAULT, profiles.DEFAULT_LABEL, 'revoked' if default_revoked else 'kept')]
        for profile_id in self.directories or ():
            if profile_id not in moved and profile_id in self.shown:
                rows.append(self._row(profile_id, labels.get(profile_id),
                                      'already_revoked' if profile_id in self.untouched else 'revoked'))
        made = {name for _, name in self.quarantined}
        quarantine = [{'name': name, 'id': profiles.parse_quarantine_name(name)[0], 'new': name in made}
                      for name in sorted({*self.quarantines, *made})]
        directory = ('unlistable' if self.directories is None
                     else 'present' if os.path.lexists(self.layout.profiles) else 'absent')
        value = {'version': RECORD_VERSION,
                 'restore': None if detection is None else {'at': at, 'marker': detection.marker,
                                                            'sentinel': detection.sentinel},
                 'dormant': {'at': at} if dormant else None,
                 'index': index.state, 'profiles': rows, 'quarantined': quarantine,
                 'profiles_directory': directory, 'other_entries': self.other}
        _clear(self.root, RECORD, self.now)  # a directory at its name (a forged backup) is moved aside first
        try:
            _write_record(self.root, value)
        except (OSError, ValueError):
            raise Unfinished('the restore record could not be saved') from None

    def _row(self, where, label, token):
        return {'id': where, 'label': label, 'is_default': where == DEFAULT, 'token': token, **self.shown[where],
                'reviewed_at': None}

    def check(self, *, strict, default_kept):
        """E. True when it does not pass (the culprits are added to failed)."""
        now = {DEFAULT: read_tokens(self.root)}
        broken = now[DEFAULT] is None
        if self.directories is not None:
            try:
                scan = profiles.scan_profiles(self.layout)
            except profiles.ProfileDataError:
                return True
            moved = {profile_id for profile_id, _ in self.quarantined}
            made = {name for _, name in self.quarantined}
            if (set(scan.profiles) != set(self.directories) - moved
                    or not {*self.quarantines, *made} <= set(scan.quarantined)):
                broken = True
            for profile_id in scan.profiles:
                now[profile_id] = read_tokens(self.layout.profile(profile_id))
                if now[profile_id] is None or now[profile_id][0] is not None:  # every profile directory: revoked
                    self.failed.append(profile_id)
        for where in sorted({*self.revoked, *self.renewed} - set(now)):  # a store held by the caller, not listed
            now[where] = read_tokens(self.layout.profile(where))
        for where in self.revoked:
            if now.get(where) is None or now[where][0] is not None:
                self.failed.append(where)
        for where, child in self.renewed.items():
            current = now.get(where)
            if current is None or current[1] == child or current[1] in self.old:
                self.failed.append(where)
        if default_kept and now[DEFAULT] != self.found[DEFAULT]:
            broken = True  # DQ-03 (b): the default profile is left exactly as it was
        if strict:
            old = self.old - (set(self.found[DEFAULT]) if default_kept else set())
            for where, pair in now.items():
                if pair is not None and any(value in old for value in pair if value):
                    self.failed.append(where)
        return broken or bool(self.failed)


def _finish(root, now, *, rebuild=False, enabled=False, markers=()):
    """F: the sentinel and its record rebuilt (when asked), then the markers removed in order, then the directory
    fsynced. An entry at one of these names that is a directory is moved aside, never deleted."""
    try:
        fd = _open_directory(root)
    except OSError:
        raise Unfinished('the data directory cannot be opened') from None
    try:
        if rebuild:
            for name in SENTINEL_NAMES:
                try:
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if not stat.S_ISREG(info.st_mode):
                    _set_aside(root, fd, name, now)
            try:
                restore_detect.rebuild(root, enabled=enabled)
            except ConfigError:
                raise Unfinished('the sentinel could not be rebuilt') from None
        for name in markers:
            try:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISDIR(info.st_mode):
                _set_aside(root, fd, name, now)
            else:
                os.unlink(name, dir_fd=fd)
        os.fsync(fd)
    except OSError:
        raise Unfinished('a marker could not be removed') from None
    finally:
        os.close(fd)


def _set_aside(root, fd, name, now, profile_id=None):
    """Move what is at name (not a plain file) to a free <name>.quarantine-<UTC>[-n] in the same directory (root, or
    profile_id's directory)."""
    try:
        aside = profiles.free_aside_name(Path(root), name, now())
        os.rename(name, aside, src_dir_fd=fd, dst_dir_fd=fd)
    except (OSError, profiles.ProfileDataError):
        raise Unfinished('an entry at one of its names could not be moved aside') from None
    if profile_id is None:
        logger.warning(SET_ASIDE, name, aside)
    else:
        logger.warning(SET_ASIDE_IN_PROFILE, profiles.log_id(profile_id), name, aside)


def _clear(directory, name, now, profile_id=None):
    """A directory at name (one of profiles.ASIDE_NAMES) in directory, where the guard puts a file, is moved aside
    (_set_aside; a forged backup: the restore repair accepts directories); anything else is left to the write."""
    try:
        if not stat.S_ISDIR(os.lstat(Path(directory) / name).st_mode):
            return
    except OSError:
        return  # nothing there, or a lookup that fails: the write that follows tells
    try:
        fd = _open_directory(directory)
    except OSError:
        raise Unfinished('an entry at one of its names could not be moved aside') from None
    try:
        _set_aside(directory, fd, name, now, profile_id)
    finally:
        os.close(fd)


def _maybe_directory(path):
    """Whether path is a directory, or what it is cannot be told (a link is not followed)."""
    try:
        return stat.S_ISDIR(os.lstat(path).st_mode)
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _write_record(root, value):
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(raw) > RECORD_LIMIT:
        raise ValueError('restore record too large')
    fd = _open_directory(root)
    temporary = '.' + RECORD + '.tmp-' + secrets.token_hex(8)
    try:
        out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            view = memoryview(raw)
            while view:
                view = view[os.write(out, view):]
            os.fsync(out)
        finally:
            os.close(out)
        os.replace(temporary, RECORD, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    except OSError:
        try:
            os.unlink(temporary, dir_fd=fd)
        except OSError:
            pass
        raise
    finally:
        os.close(fd)


def _lock_held(directory):
    """Whether another open file holds the directory's writer lock (a running store): then it is never moved away."""
    try:
        fd = os.open(Path(directory) / '.writer.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    except OSError as error:
        return error.errno in (errno.EAGAIN, errno.EWOULDBLOCK)
    finally:
        os.close(fd)  # closing it releases the lock taken just now
    return False


def _read_bounded(fd, limit):
    """At most limit bytes of a single-link regular file of this uid (fstat and what is read both within it), or None."""
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                or info.st_size > limit):
            return None
        chunks, size = [], 0
        while chunk := os.read(fd, limit + 1 - size):
            chunks.append(chunk)
            size += len(chunk)
            if size > limit:
                return None
        return b''.join(chunks)
    except OSError:
        return None


def _present(path):
    """Any kind of entry counts, and so does one a lookup cannot rule out (as restore_detect)."""
    try:
        os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return True
    return True


def _open_directory(root):
    return os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _fsync_directory(path):
    fd = _open_directory(path)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
