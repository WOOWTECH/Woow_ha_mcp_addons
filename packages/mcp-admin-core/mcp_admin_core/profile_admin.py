"""The profile management of a switched-on product on 8099: list, create, rename, delete, the index quarantine
(multi-profile plan 4.3, 4.4, 5.3; contract 3, 4.1; DQ-12, DQ-13, DQ-14, DQ-15, DQ-16, DQ-28; HM-10).

profile_router.AdminDispatcher runs the shared management pipeline (contract 3.2: identity, the management slots, the
bounded body read, the disconnect watch, the method table and the request's shape, the first role check) and hands a
request for a global path here. What follows is steps 8 to 11: the add-on's profile lock (and, for a deletion, the
profile's own lock; for the index quarantine, every registered additional profile's), at most 2 s each (503); the
second, final role check, after which nothing is awaited before the answer is disclosed or the change committed; then
every check that reads state, in a fixed order, and the commit.
A caller who is not an administrator never gets here (step 6), so nothing below is ever told to one (invariant I10).

- The index ETag "p1-<64 hex>" (contract 3.5) is an HMAC, with a key of this process, of the index's entries in their
  order (ids, labels, ports): every write of the index needs it in If-Match (428 without one, 409 config_conflict for a
  malformed, repeated or stale one). An unusable index (corrupt, or changed behind the add-on's back: DQ-12) is
  identified by an HMAC of its file's signature and raw bytes instead (the default profile's bootstrap shows it as
  profile_index_etag): only the index quarantine takes that one.
- Creation, deletion and the index quarantine also take an Idempotency-Key; their receipts are kept beside the index
  (operations.PROFILE_RESULTS in /data/mcp/.profiles.json.operations.json), each with its subject (the profile's id,
  the quarantined index's name). A replay of a completed operation answers what it did, never a token (plan 4.3).
- Every write of the index passes the view the manager holds (profiles.write_index expected=: read at startup, written
  last, or read after the quarantine; HM-07 review checklist), never a fresh read: a write refused because the index
  changed keeps the manager's verdict (the recheck), so DQ-12's "503 until a restart" is never washed away.
- A creation writes the profile once with its final first state (products.profile_initial_state: new tokens, no
  connection, the default profile's policy now; DQ-02), then the index (the commit), then registers and starts it
  (an unconfigured profile's child waits for its connection: status unconfigured). Its answer never carries a token:
  token/reveal with X-MCP-Profile <the new id> does for other products; Headscale requires rotation.
- A deletion (plan 4.4, DQ-14): the token revoked and the requests it carries ended (TokenAccess.committed), the
  backend credentials wiped, the profile no longer routed and its monitor and child stopped, its client and store
  closed, its index entry removed (only now is its port free), its directory removed without following a link (a
  failure leaves an orphan: one WARNING with the id's first 8 characters), then every blocked profile reevaluated
  (PaaS B-17). An orphan directory (not in the index) is deleted the same way; nothing is ever deleted on its own.
- The index quarantine (DQ-12; FM-131): every profile directory's token revoked, then profiles.json renamed to a free
  profiles.json.quarantine-<UTC>[-n] (HM-07 review S-15): the default profile serves 8081 again at once, every profile
  directory is an orphan, deletable one by one. It holds every registered additional profile's own lock too (HM-10
  review S-1), from before its final role check until the profile is unregistered: no token change, save or restart of
  one of them runs in between (a token written after the revocation would be routed until its profile is
  unregistered, past its If-Match).
- Locks are taken in one order: the add-on's profile lock first, then profiles' own locks (a deletion its target's, the
  quarantine every registered one's in id order; "revoke all" the default profile's, then every registered one's in id
  order). A profile's action takes only its own lock, and the starts of reevaluate (ProfileRuntime.launch) take only
  theirs, after every profile lock taken here is released: no wait ever closes a circle.

HM-13c (multi-profile plan 6, 8.4 全部撤銷 / 核對後才重發, 10.3; contract 1.3, 3.1, 3.5, 3.6, 4.1, 4.2; FM-79, 80, 120):
- "Revoke all" (POST profiles/revoke-all; If-Match: the index ETag, or the unusable index's own ETag: it works while
  the index cannot be used, the emergency stop; Idempotency-Key): under the add-on's profile lock, the default
  profile's lock and every registered profile's lock (id order), after the final role check, the receipt begun, then
  restore_lock.revoke_all in a worker thread (synchronous: two state writes and their fsyncs a profile; 8081, 8099
  and the health checks go on meanwhile) with every registered profile's own store. Then every registered profile's
  requests that carry its old token end (TokenAccess.committed), every revoked one's child starts again on its new
  child token (as the panel's restart), and the default profile's restore notice is gone. Every profile revoked and the
  check passed: 200 {"revoked": "all", "results": [...]} and the receipt completed. Otherwise 409
  operation_outcome_unknown with the results: the receipt stays unknown, .revoke-all-pending stays (the next start
  finishes the job before anything is served), and the old token of every registered profile that failed is fenced on
  8081 (503 state unavailable, profile_runtime.ProfileManager.revoke_fence) until a "revoke all" finishes. Without
  any result (its marker could not be saved, the default profile's state could not be read, or any other exception
  stopped it: HM-13c review S-4, one fixed line in the log) every registered profile's old token is fenced. The fence
  only refuses what 8081's dispatcher matches from then on; a request it matched before that had no token lease yet
  (for example one beyond a full admission whose small body is still read, at most 2 s) takes its lease afterwards
  against the state on disk, and is served when that still holds the token (HM-13c review S-6); every request that
  held a lease was ended by committed(). When the restore record could not be used, a "revoke all" that finished
  leaves a new one (every profile revoked, none reviewed: restore_lock.revoke_all).
- The restore record (GET profiles/restore-record): {"record": <the guard's record, restore_lock.check_record>|null};
  usable whatever the index.
- A restore review (POST profiles/<id>/restore-review; the index ETag; Idempotency-Key): the record's row of a profile
  that still exists gets its reviewed_at; until then a token/rotate of a profile whose token the guard revoked answers
  409 restore_review_required (review_required, make_apps' option of the same name).
- The quarantine directories (contract 1.1): listed with the profile list ("quarantined", only when there is one) and
  deleted one by one (POST profiles/quarantine/<id>-<UTC>[-n]/delete; the index ETag; Idempotency-Key), as an orphan
  is: its token revoked and its credentials wiped first when its state can be opened now, then its directory removed
  without following a link. Never served; never deleted on their own.
- The default profile's bootstrap says what waits for a review (restore_review: pending, restore_at, dormant_at; the
  record unreadable: pending null), and every profile's bootstrap whether its new token waits for one
  (restore_review_required: true).

HM-27 (multi-profile plan 8.7, 12.3 HM-27; DQ-11 (a); contract 2.6, 3.1, 3.5, 4.1): the add-on's Origin policy of the
secret path (origin_policy.OriginPolicy, the manager's origin) is one more global path, {base}/api/origin-policy:
- GET (origin_policy): after the second role check, the policy as the panel shows it ({"mode", "allowed_origins",
  "origin_policy_state"}: default without a file, saved, or unusable with neither) and its ETag "o1-<64 hex>";
- PUT (save_origin_policy) {"mode", "allowed_origins"}: the policy's own lock (2 s, 503), the second role check, then
  as a creation: If-Match (428; a malformed, repeated or stale one 409 config_conflict with the current ETag; an
  unusable file takes its own ETag, so a save replaces it), the Idempotency-Key (428, 400; a completed replay answers
  the policy now and its receipt before the ETag is compared; another request under the same key 409
  operation_id_conflict; one not completed 409 operation_outcome_unknown), the request's rules (422
  origin_policy_invalid), the receipt begun, the file written, the receipt completed (receipts beside the file:
  .origin-policy.json.operations.json, kind origin.policy). A write that fails once the receipt began: 409
  operation_outcome_unknown, the receipt left unknown (never a second write under its key).
Neither carries a profile echo, a token or server text. A product with its own rule (Headscale: the manager made no
policy) answers both as an unknown operation (404, no body).

HM-25 (multi-profile plan 4.4 刪除順序 "產品清理"; plan 9 n8n row; DQ-04; FM-23): once a deleted profile's directory
is gone (a profile's, an orphan's or a quarantine directory's), the product's cleanup runs (Registry.removed: the
manager's profile_removed; n8n removes the profile's catalog copy outside /data). It runs whether or not the directory
could be removed completely; a cleanup that fails is one WARNING and the deletion stands.

What this module uses of profile_runtime.ProfileManager (HM-08's registry, HM-09's lifecycle) is in one class,
Registry, so that a change of that interface is made in one place.
"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import astuple, dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import os
import re
import secrets

from starlette.responses import JSONResponse, Response

from . import origin_policy, profiles, restore_lock
from .admin_auth import BadRequest
from .config import ConfigError
from .operations import PROFILE_RESULTS, OperationJournal
from .products import ProductStore, profile_initial_state

logger = logging.getLogger(__name__)

LOCK_SECONDS = 2  # every lock of a management request is waited for at most this long (503), as admin_action's
HEADERS = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}  # as admin_action's answers
ETAG = re.compile(r'"p1-[0-9a-f]{64}"')
CREATE, DELETE, QUARANTINE = 'profile.create', 'profile.delete', 'profile.index_quarantine'
# HM-13c: "revoke all", a restore review, a quarantine directory's deletion (their receipts beside the index too).
REVOKE_ALL, REVIEW, QUARANTINE_DELETE = 'profile.revoke_all', 'profile.restore_review', 'profile.quarantine_delete'
# A profile's Supervisor status as the list shows it (contract 3.6): "stopped" is a child not started yet (start_all
# has not reached it) or between the stop and the start of a relaunch.
STATUS = {'stopped': 'starting', 'starting': 'starting', 'running': 'running', 'backoff': 'backoff',
          'blocked': 'blocked', 'failed': 'failed', 'unconfigured': 'unconfigured'}
UNAVAILABLE = 'profile_unavailable'  # an indexed profile the add-on could not open (HA's own disabled_reason)
# What a deletion wipes before the directory goes (DQ-14): every stored backend field (identity_fields BACKEND).
WIPED = {'connection': None, 'backend_url': None, 'backend_key': None, 'mcp_access_token': None}
# HM-13c review S-4: "revoke all" stopped by an exception it does not expect (%s: its class): answered as one whose
# outcome is unknown (every registered profile's old token fenced on 8081 until a "revoke all" finishes).
REVOKE_ALL_STOPPED = ('multi-profile: "revoke all" stopped on an unexpected error (%s); its outcome is unknown and '
                      "every profile's token from before it is refused on 8081 until a \"revoke all\" finishes")


def refused(status, code, **fields):
    """A new code's refusal: shape A ({"error":"request denied","detail":{"code":...}}), no server text."""
    return BadRequest(status, {'code': code, **fields})


@dataclass(frozen=True)
class Call:
    """One management request as the dispatcher hands it over after the first role check."""
    request: object
    user: str
    value: object
    peer_disconnected: asyncio.Event
    committed: asyncio.Event


class Registry:
    """Everything profile management uses of profile_runtime.ProfileManager, in one place (HM-08 built the registry,
    HM-09 the lifecycle; HM-09's review may still move a name: change it here)."""

    def __init__(self, manager):
        self.manager = manager

    @property
    def layout(self):
        return self.manager.layout

    @property
    def product(self):
        return self.manager.product

    def default_port(self):
        return self.manager.port

    def default_store(self):
        return self.manager.store

    def default_state(self):
        return self.manager.store.load()

    def restore_notice(self):
        """HM-13c: the default profile's restore notice (restore_lock.Notice), or None."""
        return self.manager.restore_notice

    def fence(self, digests):
        """HM-13c: sha256 digests of tokens a "revoke all" could not revoke: 503 on 8081 until one finishes."""
        self.manager.revoke_fence.update(digests)

    def unfence(self):
        self.manager.revoke_fence.clear()

    @staticmethod
    def token_digest(entry):
        """The digest of the profile's token now (its credentials' refresh; the last one read when its state cannot be
        read now), or None when it has none."""
        try:
            return entry.credentials.refresh()
        except ConfigError:
            return entry.credentials.digest

    @staticmethod
    async def restart(entry):
        """Start the profile's child again on its state now (a new child token: HM-06 review S-07), as the panel's
        restart does (make_apps restart_child)."""
        await entry.runtime.backend_changed(entry.store.load())

    def view(self):
        """The index view the manager holds after its per-request recheck (sticky MODIFIED; DQ-12), and whether it can
        be used (False also when the profiles directory could not be listed at startup)."""
        usable = self.manager.serves_mcp()
        return self.manager.index, usable

    def adopt(self, view):
        self.manager.adopt_index(view)

    def capacity(self):
        return self.manager.capacity

    def files_for_extras(self):
        """Whether the open file limit holds additional profiles (HM-08's file budget; False: the default only)."""
        return self.manager.files_for_extras

    def memory_limit(self):
        return self.manager.memory_limit

    def entry(self, profile_id):
        return self.manager.get(profile_id)

    def extra_ids(self):
        return [entry.profile_id for entry in self.manager.profiles() if entry.profile_id != profiles.DEFAULT_PROFILE]

    def free_port(self):
        return self.manager.free_port()

    def secrets(self):
        return self.manager.reply_secrets()

    def set_orphan_secrets(self, values):
        self.manager.orphan_secrets = frozenset(values)

    def relabel(self, profile_id, label):
        self.manager.relabel(profile_id, label)

    def origin(self):
        """HM-27: the add-on's Origin policy (origin_policy.OriginPolicy), or None for a product with its own rule."""
        return self.manager.origin

    @staticmethod
    def held_tokens(directory):
        from .profile_runtime import held_tokens  # profile_runtime imports this module
        return held_tokens(directory)

    async def register(self, profile_id, store, port, label):
        """Serve a new profile (routed from now on), reevaluate every disabled reason, then start its child (a
        creation: the memory check applies) under the profile's own lock, as a save starts it: a panel request for the
        new id that came in meanwhile (its id is listed once the index is written) never relaunches it at the same
        time (HM-09 review S-12)."""
        entry = await self.manager.add(profile_id, store, port=port, label=label)
        await self.manager.reevaluate()
        async with self.mutation_lock(entry):
            await self.manager.start_profile(profile_id)

    async def unregister(self, profile_id):
        """No longer routed; its monitor stopped, its client and child closed, its store closed."""
        await self.manager.remove(profile_id)

    def removed(self, profile_id):
        """HM-25: the product's cleanup once a deleted profile's directory is gone (n8n: its catalog copy)."""
        self.manager.removed(profile_id)

    async def reevaluate(self):
        await self.manager.reevaluate()

    @staticmethod
    def supervisor(entry):
        return entry.runtime.supervisor

    @staticmethod
    def token_access(entry):
        return entry.runtime.token_access

    @staticmethod
    def mutation_lock(entry):
        return entry.runtime.mutation_lock

    @staticmethod
    def store(entry):
        return entry.store

    @staticmethod
    def disabled(entry):
        return entry.disabled

    @staticmethod
    def directory_ok(entry):
        """Whether the profile's directory is still the one opened (HM-07 review S-08: the management side; ConfigError
        when it is not, or its state cannot be read)."""
        entry.credentials.refresh()


class ProfileAdmin:
    """The global management paths of one switched-on add-on (see the module docstring). manager: its
    profile_runtime.ProfileManager; final_role: the add-on's AdminAuthority.verify (the second role check)."""

    def __init__(self, manager, final_role):
        self.registry = Registry(manager)
        self.final_role = final_role
        self.lock = asyncio.Lock()  # creation, rename, deletion and the index quarantine, one at a time
        self._key = secrets.token_bytes(32)
        self.journal = OperationJournal(self.registry.layout.index, results=PROFILE_RESULTS, subjects=True)
        self._record_seen = (None, None)  # HM-13c: (the restore record's signature, its value) last read

    # ---- what the dispatcher and the profiles' apps read ----

    def etag(self, entries):
        raw = json.dumps([[entry.id, entry.label, entry.port] for entry in entries], ensure_ascii=True,
                         separators=(',', ':')).encode()
        return '"p1-' + hmac.new(self._key, b'index\0' + raw, hashlib.sha256).hexdigest() + '"'

    def raw_etag(self):
        """The ETag of the index file as it is now, usable or not: its signature and raw bytes."""
        signature, raw = profiles.index_bytes(self.registry.layout.index)
        described = json.dumps(None if signature is None else astuple(signature)).encode()
        return '"p1-' + hmac.new(self._key, b'raw\0' + described + b'\0' + raw, hashlib.sha256).hexdigest() + '"'

    def bootstrap_fields(self, profile_id):
        """What a profile's bootstrap carries after its echo (make_apps bootstrap_fields; contract 3.6): whether the
        product has additional profiles (DQ-28) and, for the default profile, the index's state: "ok", or "corrupt"
        (corrupt, or changed behind the add-on's back: DQ-12) with the ETag the quarantine takes."""
        fields = {'profiles_supported': profiles.supports_profiles(self.registry.product)}
        if profile_id == profiles.DEFAULT_PROFILE:
            view, usable = self.registry.view()
            fields['profile_index_state'] = 'ok' if usable else 'corrupt'
            if not usable:
                fields['profile_index_etag'] = self.raw_etag()
            review = self._review_summary(view)
            if review is not None:
                fields['restore_review'] = review  # HM-13c
        try:
            gated = self.review_required(profile_id)
        except ConfigError:
            gated = False  # the record cannot be read: the default profile's restore_review says so (pending null)
        if gated:
            fields['restore_review_required'] = True  # HM-13c
        return fields

    # ---- HM-13c: the restore record and the review gate ----

    def _record(self):
        """The guard's restore record (restore_lock.read_record, check_record), or None when there is none: read again
        only when its file changed. ConfigError when it cannot be used."""
        path = self.registry.layout.restore_record
        try:
            info = os.lstat(path)
            signature = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        except FileNotFoundError:
            self._record_seen = (None, None)
            return None
        except OSError:
            raise ConfigError('restore record unavailable') from None
        seen, value = self._record_seen
        if seen != signature:
            value = restore_lock.read_record(self.registry.layout.root)
            value = None if value is None else restore_lock.check_record(value)
            self._record_seen = (signature, value)
        return value

    def review_required(self, profile_id):
        """Whether a new token for profile_id waits for its restore review (contract 4.1 restore_review_required): the
        record's row of it says the guard revoked its token and nobody reviewed it yet. ConfigError when the record
        cannot be used (the gate fails closed)."""
        record = self._record()
        if record is None:
            return False
        row = next((row for row in record['profiles'] if row['id'] == profile_id), None)
        return row is not None and row['token'] in restore_lock.REVIEWED_TOKENS and row['reviewed_at'] is None

    def _pending(self, record, view):
        listed = {item.id for item in view.entries}
        return [row for row in record['profiles']
                if row['token'] in restore_lock.REVIEWED_TOKENS and row['reviewed_at'] is None
                and (row['id'] == profiles.DEFAULT_PROFILE or row['id'] in listed)]

    def _review_summary(self, view):
        """The default bootstrap's restore_review: how many profiles that still exist wait for a review, and when the
        restore or the dormant revocation was; None when none waits. The record unreadable: pending null."""
        try:
            record = self._record()
        except ConfigError:
            return {'pending': None, 'restore_at': None, 'dormant_at': None}
        if record is None:
            return None
        pending = len(self._pending(record, view))
        if not pending:
            return None
        return {'pending': pending, 'restore_at': (record['restore'] or {}).get('at'),
                'dormant_at': (record['dormant'] or {}).get('at')}

    def profile_entry(self, profile_id):
        """Step 7 for an additional profile's id (X-MCP-Profile, well formed): its registered entry. 503
        profile_index_corrupt while the index cannot be used; 404 profile_not_found when the index does not list it
        (an orphan, a deleted profile: never the default profile instead); 503 state unavailable when it is listed
        but not served (profile_unavailable: deletable only) or its directory is not the one opened."""
        view, usable = self.registry.view()
        if not usable:
            raise refused(503, 'profile_index_corrupt')
        if profile_id not in {item.id for item in view.entries}:
            raise refused(404, 'profile_not_found')
        entry = self.registry.entry(profile_id)
        if entry is None:
            raise ConfigError('profile unavailable')
        Registry.directory_ok(entry)
        return entry

    # ---- the global paths (steps 8 to 11) ----

    async def list(self, call):
        await self._final(call)
        view = self._usable_view()
        scan = self._scan()
        body = {'profiles': self._rows(view), 'orphans': self._orphans(view, scan)}
        quarantined = [{'name': profiles.quarantine_entry_name(name), 'id': profiles.parse_quarantine_name(name)[0]}
                       for name in scan.quarantined]
        if quarantined:
            body['quarantined'] = quarantined  # HM-13c: only when there is one
        return self._answer(body, etag=self.etag(view.entries))

    async def create(self, call):
        async with self._locked(self.lock):
            await self._final(call)
            # Nothing is awaited from here to the commit (the index write).
            view = self._usable_view()
            etag = self.etag(view.entries)
            given = self._if_match(call)
            if given is None:
                return self._conflict(etag)
            key, data, prior, fingerprint = self._idempotency(call, CREATE, call.value['label'])
            if prior is not None:
                return self._replay_create(prior, key, view, etag)
            if given != etag:
                return self._conflict(etag)
            try:
                label = profiles.normalize_label(call.value['label'])
            except profiles.LabelError:
                raise refused(422, 'profile_label_invalid') from None
            if not profiles.supports_profiles(self.registry.product):
                raise refused(409, 'profile_product_unsupported')
            self._capacity_check(len(view.entries))
            if profiles.label_taken(label, [item.label for item in view.entries]):
                raise refused(409, 'profile_label_conflict')
            port = self.registry.free_port()
            if port is None:
                raise refused(409, 'profile_port_unavailable')
            scan = self._scan()
            taken = {item.id for item in view.entries} | set(scan.profiles)
            taken |= {profiles.parse_quarantine_name(name)[0] for name in scan.quarantined}
            profile_id = profiles.new_profile_id(taken)
            state = profile_initial_state(self.registry.default_state(), taken=self.registry.secrets())
            self.journal.begin(key, data, CREATE, call.user, fingerprint, subject=profile_id)
            try:
                profiles.ensure_profiles_directory(self.registry.layout)
                store = ProductStore(self.registry.layout.profile(profile_id), self.registry.product, create=state)
            except (ConfigError, profiles.ProfileDataError, OSError):
                raise refused(409, 'operation_outcome_unknown') from None
            try:
                written = profiles.write_index(self.registry.layout.index,
                                               [*view.entries, profiles.IndexEntry(profile_id, label, port)],
                                               expected=view)
            except profiles.ProfileDataError:
                store.close()
                profiles.remove_profile_directory(self.registry.layout, profile_id)  # never routed, never told
                self.registry.view()  # the recheck keeps the verdict (MODIFIED stays until a restart)
                raise refused(409, 'operation_outcome_unknown') from None
            call.committed.set()  # committed: the rest runs to its end whatever the client does
            self.registry.adopt(written)
            try:
                await self.registry.register(profile_id, store, port, label)
            except Exception:
                if self.registry.entry(profile_id) is None:
                    store.close()
                logger.warning('multi-profile: profile %s was created but could not be served; it is listed as '
                               'unavailable and can be deleted', profiles.log_id(profile_id))
            operation = self._complete(key, data)
            return self._answer({**self._row(written, profile_id), 'operation': operation}, status=201,
                                etag=self.etag(written.entries))

    async def rename(self, call, profile_id):
        async with self._locked(self.lock):
            await self._final(call)
            view = self._usable_view()
            etag = self.etag(view.entries)
            if self._if_match(call) != etag:
                return self._conflict(etag)
            if profile_id == profiles.DEFAULT_PROFILE:
                raise refused(422, 'profile_default_immutable')
            items = {item.id: item for item in view.entries}
            if profile_id not in items:
                raise refused(404, 'profile_not_found')
            try:
                label = profiles.normalize_label(call.value['label'])
            except profiles.LabelError:
                raise refused(422, 'profile_label_invalid') from None
            if profiles.label_taken(label, [item.label for item in view.entries if item.id != profile_id]):
                raise refused(409, 'profile_label_conflict')
            entries = [profiles.IndexEntry(item.id, label, item.port) if item.id == profile_id else item
                       for item in view.entries]
            try:
                written = profiles.write_index(self.registry.layout.index, entries, expected=view)
            except profiles.ProfileDataError:
                self.registry.view()
                raise refused(409, 'operation_outcome_unknown') from None
            call.committed.set()
            self.registry.adopt(written)
            if self.registry.entry(profile_id) is not None:
                self.registry.relabel(profile_id, label)  # the profile echo shows the new label at once
            return self._answer(self._row(written, profile_id), etag=self.etag(written.entries))

    async def delete(self, call, profile_id):
        async with self._locked(self.lock):
            entry = None if profile_id == profiles.DEFAULT_PROFILE else self.registry.entry(profile_id)
            lock = None if entry is None else Registry.mutation_lock(entry)
            async with self._locked(lock):
                await self._final(call)
                view = self._usable_view()
                etag = self.etag(view.entries)
                given = self._if_match(call)
                if given is None:
                    return self._conflict(etag)
                key, data, prior, fingerprint = self._idempotency(call, DELETE, profile_id)
                if prior is not None:
                    return self._replay(prior, key, {'deleted': profile_id}, etag)
                if given != etag:
                    return self._conflict(etag)
                if profile_id == profiles.DEFAULT_PROFILE:
                    raise refused(422, 'profile_default_immutable')
                indexed = profile_id in {item.id for item in view.entries}
                if not indexed and profile_id not in self._scan().profiles:
                    raise refused(404, 'profile_not_found')
                self.journal.begin(key, data, DELETE, call.user, fingerprint, subject=profile_id)
                store, opened = self._profile_store(entry, profile_id)
                try:
                    self._revoke(store, entry, profile_id)
                    call.committed.set()  # the token is revoked: the deletion runs to its end
                    try:
                        store is not None and store.update(**WIPED)
                    except ConfigError:
                        logger.warning('multi-profile: the credentials of profile %s could not be wiped before its '
                                       'deletion', profiles.log_id(profile_id))
                finally:
                    if opened:
                        store.close()
                if entry is not None:
                    try:
                        await self.registry.unregister(profile_id)
                    except Exception:
                        logger.warning('multi-profile: the child of profile %s did not stop cleanly',
                                       profiles.log_id(profile_id))
            # The profile's lock is released: the profile is no longer served; its index entry goes now.
            written = view
            if indexed:
                try:
                    written = profiles.write_index(self.registry.layout.index,
                                                   [item for item in view.entries if item.id != profile_id],
                                                   expected=view)
                except profiles.ProfileDataError:
                    self.registry.view()
                    raise refused(409, 'operation_outcome_unknown') from None
                self.registry.adopt(written)
            if not profiles.remove_profile_directory(self.registry.layout, profile_id):
                logger.warning('multi-profile: the directory of deleted profile %s could not be removed completely; '
                               'what is left is an orphan and can be deleted again', profiles.log_id(profile_id))
            self.registry.removed(profile_id)  # HM-25: the product's cleanup (n8n: the catalog copy)
            self._refresh_orphan_secrets(written)
            await self.registry.reevaluate()  # PaaS B-17: a profile its port or the limit held back starts now
            operation = self._complete(key, data)
            return self._answer({'deleted': profile_id, 'operation': operation}, etag=self.etag(written.entries))

    async def quarantine(self, call):
        async with self._locked(self.lock):
            # HM-10 review S-1: every registered additional profile's own lock as well, from before the final role
            # check until the profile is unregistered, as a deletion holds its target's. A token change, save or
            # restart of one of them already under way is waited for (done first, then revoked below); one that comes
            # in meanwhile waits and then finds the profile's store closed (503). So the one revocation below is the
            # last word on their tokens: none is routed once the index is moved aside, and no If-Match taken before
            # the quarantine writes over the revoked state.
            async with self._registered_profiles_locked() as registered:
                await self._final(call)
                view, usable = self.registry.view()
                etag = self.etag(view.entries) if usable else self.raw_etag()
                given = self._if_match(call)
                if given is None:
                    return self._conflict(etag)
                key, data, prior, fingerprint = self._idempotency(call, QUARANTINE, None)
                if prior is not None:
                    return self._replay(prior, key, {'quarantined': prior['subject']}, etag)
                if usable or given != etag:
                    return self._conflict(etag)  # a usable index is never quarantined: no ETag of it matches
                if profiles.signature_of_or_none(self.registry.layout.index) is None:
                    # Unusable without an index file (the profiles directory could not be listed at the start):
                    # nothing to move aside; the add-on is restarted instead. Refused before anything is revoked or
                    # recorded.
                    return self._conflict(etag)
                try:
                    name = profiles.free_index_quarantine_name(self.registry.layout, datetime.now(timezone.utc))
                except profiles.ProfileDataError:
                    raise BadRequest(503) from None
                # Listed before the receipt begins: a profiles directory that cannot be listed (503) leaves no receipt.
                directories = sorted(set(self._scan().profiles) | set(registered))
                self.journal.begin(key, data, QUARANTINE, call.user, fingerprint, subject=name)
                unrevoked = 0
                for profile_id in directories:
                    entry = self.registry.entry(profile_id)
                    store, opened = self._profile_store(entry, profile_id)
                    try:
                        if not self._revoke(store, entry, profile_id):
                            unrevoked += 1
                    finally:
                        if opened:
                            store.close()
                call.committed.set()
                try:
                    profiles.move_index_aside(self.registry.layout, name)
                except profiles.ProfileDataError:
                    raise refused(409, 'operation_outcome_unknown') from None
                written = profiles.read_index(self.registry.layout.index)  # absent: the default profile serves again
                self.registry.adopt(written)
                if unrevoked:
                    logger.warning('multi-profile: the profile index was quarantined; the token of %d profile '
                                   'directory(ies) could not be revoked (their state cannot be read, so they are '
                                   'never served)', unrevoked)
                for profile_id in registered:
                    if self.registry.entry(profile_id) is not None:
                        try:
                            await self.registry.unregister(profile_id)  # an orphan now: never served
                        except Exception:
                            logger.warning('multi-profile: the child of profile %s did not stop cleanly',
                                           profiles.log_id(profile_id))
            # The profiles' locks are released: a start takes its profile's lock (ProfileRuntime.launch).
            self._refresh_orphan_secrets(written)
            await self.registry.reevaluate()
            operation = self._complete(key, data)
            return self._answer({'quarantined': name, 'operation': operation}, etag=self.etag(written.entries))

    # ---- HM-13c: "revoke all", the restore record and its review, the quarantine directories ----

    async def revoke_all(self, call):
        default = self.registry.entry(profiles.DEFAULT_PROFILE)
        async with self._locked(self.lock):
            # The default profile's own lock, then every registered profile's (id order), as the index quarantine
            # holds them: a token change, save or restart under way is done first; one that comes in meanwhile waits
            # and then finds the token revoked. Only then the final role check.
            async with self._locked(None if default is None else Registry.mutation_lock(default)):
                async with self._registered_profiles_locked() as registered:
                    await self._final(call)
                    view, usable = self.registry.view()
                    etag = self.etag(view.entries) if usable else self.raw_etag()
                    given = self._if_match(call)
                    if given is None:
                        return self._conflict(etag)
                    key, data, prior, fingerprint = self._idempotency(call, REVOKE_ALL, None)
                    if prior is not None:
                        return self._replay(prior, key, {'revoked': 'all'}, etag)
                    if given != etag:
                        return self._conflict(etag)
                    entries = {profile_id: self.registry.entry(profile_id) for profile_id in registered}
                    entries = {profile_id: entry for profile_id, entry in entries.items() if entry is not None}
                    held = {profiles.DEFAULT_PROFILE: default, **entries} if default is not None else dict(entries)
                    before = {profile_id: Registry.token_digest(entry) for profile_id, entry in held.items()}
                    self.journal.begin(key, data, REVOKE_ALL, call.user, fingerprint, subject='all')
                    call.committed.set()  # the receipt is begun: it runs to its end whatever the client does
                    try:
                        done = await asyncio.to_thread(
                            restore_lock.revoke_all, self.registry.default_store(), self.registry.product,
                            stores={profile_id: Registry.store(entry) for profile_id, entry in entries.items()})
                    except (ConfigError, OSError, ValueError):
                        done = None  # not even begun (.revoke-all-pending could not be saved), or no answer: unknown
                    except Exception as error:  # HM-13c review S-4: whatever else stopped it, fail closed the same way
                        logger.warning(REVOKE_ALL_STOPPED, type(error).__name__)
                        done = None
                    results = [] if done is None else [{'id': item.profile_id, 'result': item.result}
                                                       for item in done.results]
                    outcome = {item['id']: item['result'] for item in results}
                    for profile_id, entry in held.items():
                        Registry.token_access(entry).committed()  # requests that carry the old token end now
                    if done is not None and done.finished:
                        self.registry.unfence()
                    else:
                        self.registry.fence(digest for profile_id, digest in before.items()
                                            if digest is not None and outcome.get(profile_id) != 'revoked')
                    if outcome.get(profiles.DEFAULT_PROFILE) == 'revoked':
                        notice = self.registry.restore_notice()
                        if notice is not None:
                            notice.clear()  # the default profile's token is not the backup's any more
                    for profile_id, entry in held.items():
                        if outcome.get(profile_id) == 'revoked':
                            try:
                                await Registry.restart(entry)
                            except Exception:
                                logger.warning('multi-profile: the child of profile %s did not start again after '
                                               '"revoke all" (its new child token waits for a restart)',
                                               profiles.log_id(profile_id))
                    self._refresh_orphan_secrets(view)
                    if done is None or not done.finished:
                        public = self.journal.public(key, data['receipts'][key])
                        raise refused(409, 'operation_outcome_unknown', operation=public, results=results)
                    operation = self._complete(key, data)
                    return self._answer({'revoked': 'all', 'results': results, 'operation': operation}, etag=etag)

    async def restore_record(self, call):
        await self._final(call)
        view, usable = self.registry.view()
        return self._answer({'record': self._record()}, etag=self.etag(view.entries) if usable else self.raw_etag())

    async def restore_review(self, call, profile_id):
        async with self._locked(self.lock):
            await self._final(call)
            view = self._usable_view()
            etag = self.etag(view.entries)
            given = self._if_match(call)
            if given is None:
                return self._conflict(etag)
            key, data, prior, fingerprint = self._idempotency(call, REVIEW, profile_id)
            if prior is not None:
                return self._replay(prior, key, {'reviewed': profile_id, 'reviewed_at': self._reviewed_at(profile_id)},
                                    etag)
            if given != etag:
                return self._conflict(etag)
            record = self._record()
            listed = profile_id == profiles.DEFAULT_PROFILE or profile_id in {item.id for item in view.entries}
            if record is None or not listed or not any(row['id'] == profile_id for row in record['profiles']):
                raise refused(404, 'profile_not_found')
            self.journal.begin(key, data, REVIEW, call.user, fingerprint, subject=profile_id)
            call.committed.set()
            try:
                reviewed_at = restore_lock.review(self.registry.layout.root, profile_id)
            except (ConfigError, LookupError, OSError, ValueError):
                raise refused(409, 'operation_outcome_unknown') from None
            operation = self._complete(key, data)
            return self._answer({'reviewed': profile_id, 'reviewed_at': reviewed_at, 'operation': operation},
                                etag=etag)

    def _reviewed_at(self, profile_id):
        try:
            record = self._record()
        except ConfigError:
            return None
        row = None if record is None else next((row for row in record['profiles'] if row['id'] == profile_id), None)
        return None if row is None else row['reviewed_at']

    async def delete_quarantined(self, call, name):
        directory = profiles.quarantine_directory_name(name)  # step 5 checked the name
        async with self._locked(self.lock):
            await self._final(call)
            view = self._usable_view()
            etag = self.etag(view.entries)
            given = self._if_match(call)
            if given is None:
                return self._conflict(etag)
            key, data, prior, fingerprint = self._idempotency(call, QUARANTINE_DELETE, name)
            if prior is not None:
                return self._replay(prior, key, {'deleted': name}, etag)
            if given != etag:
                return self._conflict(etag)
            if directory not in self._scan().quarantined:
                raise refused(404, 'profile_not_found')
            self.journal.begin(key, data, QUARANTINE_DELETE, call.user, fingerprint, subject=name)
            call.committed.set()
            self._wipe(self.registry.layout.profiles / directory, name)
            if not profiles.remove_quarantine_directory(self.registry.layout, directory):
                logger.warning('multi-profile: a quarantine directory of profile %s could not be removed completely; '
                               'it is still listed and can be deleted again', profiles.log_id(name[:24]))
            quarantined = profiles.parse_quarantine_name(directory)[0]
            if self.registry.entry(quarantined) is None:
                self.registry.removed(quarantined)  # HM-25: the product's cleanup, unless that id is served again
            operation = self._complete(key, data)
            return self._answer({'deleted': name, 'operation': operation}, etag=etag)

    def _wipe(self, directory, name):
        """DQ-14 for a quarantine directory: when its state can be opened now (its quarantine may have come from an
        error that went away), its token is revoked and its backend credentials wiped before it goes."""
        try:
            store = ProductStore(directory, self.registry.product, existing_only=True)
        except (ConfigError, ValueError):
            return  # its state cannot be read: nothing in it is ever served
        try:
            store.change_token(None, action='revoke')
            store.update(**WIPED)
        except ConfigError:
            logger.warning('multi-profile: the credentials of a quarantine directory of profile %s could not be '
                           'wiped before its deletion', profiles.log_id(name[:24]))
        finally:
            store.close()

    # ---- HM-27: the add-on's Origin policy of the secret path (see the module docstring) ----

    async def origin_policy(self, call):
        origin = self.registry.origin()
        if origin is None:
            return Response(status_code=404)  # its own rule (Headscale): as an unknown operation, after the role check
        await self._final(call)
        found = origin.file.read()
        return self._answer(origin.view(found), etag=origin.etag(found))

    async def save_origin_policy(self, call):
        origin = self.registry.origin()
        if origin is None:
            return Response(status_code=404)
        async with self._locked(origin.lock):
            await self._final(call)
            # Nothing is awaited from here to the answer.
            found = origin.file.read()
            etag = origin.etag(found)
            given = self._if_match(call, origin_policy.ETAG)
            if given is None:
                return self._conflict(etag)
            key, data, prior, fingerprint = self._idempotency(call, origin_policy.KIND, call.value, origin.journal)
            if prior is not None:
                return self._replay(prior, key, origin.view(found), etag, origin.journal)
            if given != etag:
                return self._conflict(etag)
            policy = origin_policy.requested(call.value)
            origin.journal.begin(key, data, origin_policy.KIND, call.user, fingerprint)
            call.committed.set()  # the intent is durable: the save runs to its end whatever the client does
            try:
                written = origin.file.write(policy, expected=found.signature)
            except OSError:
                raise refused(409, 'operation_outcome_unknown') from None
            operation = self._complete(key, data, origin.journal)
            return self._answer({**origin.view(written), 'operation': operation}, etag=origin.etag(written))

    # ---- the steps ----

    @asynccontextmanager
    async def _locked(self, lock):
        """Step 8: hold lock (None: nothing to hold), waited for at most LOCK_SECONDS (503)."""
        if lock is None:
            yield
            return
        try:
            async with asyncio.timeout(LOCK_SECONDS):
                await lock.acquire()
        except TimeoutError:
            raise BadRequest(503) from None
        try:
            yield
        finally:
            lock.release()

    @asynccontextmanager
    async def _registered_profiles_locked(self):
        """Step 8 of the index quarantine, after the add-on's profile lock: every registered additional profile's own
        lock, in id order, each waited for at most LOCK_SECONDS (503: the ones already taken are released). Yields the
        ids, which stay registered until the quarantine unregisters them (only it and a deletion, both under the
        add-on's profile lock, unregister a profile while the add-on runs)."""
        registered = sorted(self.registry.extra_ids())
        async with AsyncExitStack() as stack:
            for profile_id in registered:
                entry = self.registry.entry(profile_id)
                await stack.enter_async_context(self._locked(None if entry is None else Registry.mutation_lock(entry)))
            yield registered

    async def _final(self, call):
        """Step 10, the final role check: nothing is awaited after it before the answer or the commit."""
        if call.peer_disconnected.is_set():
            raise BadRequest(403)
        await self.final_role(call.user)
        if call.peer_disconnected.is_set():
            raise BadRequest(403)

    def _usable_view(self):
        view, usable = self.registry.view()
        if not usable:
            raise refused(503, 'profile_index_corrupt')
        return view

    @staticmethod
    def _if_match(call, pattern=ETAG):
        """The one well-formed If-Match (428 config_revision_required without; 409 config_conflict, shape B, for more
        than one or a malformed one: returned by the caller, see _conflict). pattern: the index's ETag form, or
        (HM-27) the Origin policy's."""
        matches = call.request.headers.getlist('if-match')
        if not matches:
            raise BadRequest(428, {'code': 'config_revision_required'})
        if len(matches) != 1 or not pattern.fullmatch(matches[0]):
            return None  # never equal to an ETag: the caller answers config_conflict
        return matches[0]

    def _idempotency(self, call, kind, payload, journal=None):
        """(key, journal data, the completed receipt of a replay or None, fingerprint); 428 operation_id_required, 400
        operation_id_invalid, 410 operation_id_expired, 409 operation_id_conflict, 404 operation_not_found (another
        administrator's key), 409 operation_outcome_unknown (not completed), 503 operation_journal_unavailable.
        journal: the index's receipts, or (HM-27) the Origin policy's."""
        journal = self.journal if journal is None else journal
        ids = call.request.headers.getlist('idempotency-key')
        if not ids:
            raise BadRequest(428, {'code': 'operation_id_required'})
        if len(ids) != 1:
            raise BadRequest(400, {'code': 'operation_id_invalid'})
        data, prior, fingerprint = journal.inspect(ids[0], kind, call.user, payload)
        if prior is not None and prior['state'] != 'completed':
            public = journal.public(ids[0], prior, replayed=True)
            raise BadRequest(409, {'code': 'operation_outcome_unknown', 'operation': public})
        return ids[0], data, prior, fingerprint

    def _complete(self, key, data, journal=None):
        try:
            return (self.journal if journal is None else journal).complete(key, data)
        except (OSError, ValueError):
            raise refused(409, 'operation_outcome_unknown') from None

    def _replay(self, prior, key, body, etag, journal=None):
        """A completed operation's replay: what it did and its receipt, the index (HM-27: the Origin policy) as it is now
        (no token)."""
        journal = self.journal if journal is None else journal
        return self._answer({**body, 'operation': journal.public(key, prior, replayed=True)}, etag=etag)

    def _replay_create(self, prior, key, view, etag):
        profile_id = prior['subject']
        body = (self._row(view, profile_id) if profile_id in {item.id for item in view.entries}
                else {'id': profile_id})  # deleted since: its id only
        return self._replay(prior, key, body, etag)

    def _conflict(self, etag):
        return JSONResponse({'detail': {'code': 'config_conflict'}}, status_code=409, headers={**HEADERS, 'ETag': etag})

    @staticmethod
    def _answer(body, *, status=200, etag):
        return JSONResponse(body, status_code=status, headers={**HEADERS, 'ETag': etag})

    def _capacity_check(self, extras):
        """profile_limit_reached, then profile_memory_insufficient (PaaS order; contract 4.1, 5): with a cgroup memory
        limit the PaaS formula decides; without one MemAvailable must hold one more child (its MiB + 256; HM-09's
        rule for a start), and when it cannot be read the profile is created (one WARNING: never assumed enough). An
        add-on whose open file limit does not hold additional profiles serves none (HM-08): its limit is 0 now."""
        capacity = self.registry.capacity()
        if not self.registry.files_for_extras():
            raise refused(409, 'profile_limit_reached', limit=0)
        if extras >= capacity.policy_limit:
            raise refused(409, 'profile_limit_reached', limit=capacity.policy_limit)
        if capacity.memory_extra_limit is not None:
            if extras >= capacity.memory_extra_limit:
                raise refused(409, 'profile_memory_insufficient', limit=capacity.memory_extra_limit,
                              required_memory_mib=capacity.required_memory_mib(extras + 1),
                              memory_limit_mib=capacity.memory_limit_mib,
                              available_memory_mib=profiles.available_memory_mib())
            return
        child = profiles.CHILD_MEMORY_MIB.get(self.registry.product)
        if child is None:
            return
        needed = child + profiles.PROFILE_MEMORY_RESERVE_MIB
        available = profiles.available_memory_mib()
        if available is None:
            logger.warning('multi-profile: MemAvailable cannot be read; the profile is created without the memory '
                           'check')
            return
        if available < needed:
            raise refused(409, 'profile_memory_insufficient', limit=extras, required_memory_mib=needed,
                          available_memory_mib=available)

    def _scan(self):
        try:
            return profiles.scan_profiles(self.registry.layout)
        except profiles.ProfileDataError:
            raise ConfigError('profiles directory unavailable') from None

    def _profile_store(self, entry, profile_id):
        """(store, opened here): a registered profile's own store, else its directory opened existing-only (None when
        that cannot be done: its state cannot be read, so it is never served)."""
        if entry is not None:
            return Registry.store(entry), False
        try:
            return ProductStore(self.registry.layout.profile(profile_id), self.registry.product,
                                existing_only=True), True
        except (ConfigError, ValueError):
            return None, False

    @staticmethod
    def _revoke(store, entry, profile_id):
        """Revoke the profile's token; a registered profile's requests that carry it end at once. False when its state
        cannot be written (then it cannot be read either: never served)."""
        if store is None:
            return False
        try:
            store.change_token(None, action='revoke')
        except (ConfigError, OSError):
            logger.warning('multi-profile: the token of profile %s could not be revoked', profiles.log_id(profile_id))
            return False
        if entry is not None:
            Registry.token_access(entry).committed()
        return True

    def _refresh_orphan_secrets(self, view):
        """The reply mask's orphans after a deletion or the quarantine: every profile directory the index does not
        list (profile_runtime.held_tokens: read without its lock, never opened)."""
        listed = {item.id for item in view.entries}
        try:
            directories = profiles.scan_profiles(self.registry.layout).profiles
        except profiles.ProfileDataError:
            return
        found = set()
        for profile_id in directories:
            if profile_id not in listed:
                held = Registry.held_tokens(self.registry.layout.profile(profile_id))
                found.update(value for value in held or () if value)
        self.registry.set_orphan_secrets(found)

    # ---- the rows (contract 3.6) ----

    def _rows(self, view):
        return [self._default_row(), *(self._row(view, item.id) for item in view.entries)]

    def _default_row(self):
        entry = self.registry.entry(profiles.DEFAULT_PROFILE)
        return {'id': profiles.DEFAULT_PROFILE, 'label': profiles.DEFAULT_LABEL, 'port': self.registry.default_port(),
                'is_default': True, 'disabled_reason': None, **self._status(entry)}

    def _row(self, view, profile_id):
        item = next(item for item in view.entries if item.id == profile_id)
        entry = self.registry.entry(profile_id)
        if entry is None:
            disabled = {'disabled_reason': UNAVAILABLE}
        else:
            disabled = Registry.disabled(entry) or {'disabled_reason': None}
        return {'id': item.id, 'label': item.label, 'port': item.port, 'is_default': False, **disabled,
                **self._status(entry)}

    @staticmethod
    def _status(entry):
        if entry is None:
            return {'status': 'failed', 'blocked_reason': None}
        supervisor = Registry.supervisor(entry)
        status = STATUS.get(getattr(supervisor, 'status', None), 'failed')
        return {'status': status, 'blocked_reason': supervisor.blocked_reason if status == 'blocked' else None}

    def _orphans(self, view, scan):
        """Profile directories the index does not list (plan 4.4: never opened or routed, listed for deletion;
        DQ-14: never deleted on their own)."""
        listed = {item.id for item in view.entries}
        return [{'id': profile_id} for profile_id in scan.profiles if profile_id not in listed]
