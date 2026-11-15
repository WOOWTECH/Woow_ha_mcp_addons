"""One profile's runtime: what a profile of the add-on owns, put together (multi-profile plan 3.2; HM-05).

A profile is one backend connection, one MCP token, one tool policy and one child; the default profile is the data
directory itself (/data/mcp/state.json, as before). ProfileRuntime builds what one profile owns, as run_product.run
built it for the only profile there was:

- its child: a Supervisor (lifecycle: the Supervisor's own options; none for the default profile, as before) on the
  spec the product's child_spec builds from the profile's state and directory, on the profile's port (HM-04: 3000 for
  the default profile; plan 5.4: 18000 and up for the others);
- the child's own httpx client (CHILD_CONNECTIONS), HealthMonitor and ConfigurationState (the profile's ETag key and
  apply status);
- backend_changed: the child stopped, then started on the saved state (every save that relaunches the child, and the
  panel's restart);
- its TokenAccess and mutation lock, made here so that the add-on can reach them (a token change of one profile ends
  only that profile's requests; deleting a profile takes its lock: plan 4.4, HM-10);
- its two apps (gateway.make_apps), with the product's options (app_options) and the runtime's own.

What every profile of an add-on shares (plan 3.2: the AdminAuthority with its CSRF key and HA role verifier, the
management slots, HM-10's shared management pipeline) comes in as SharedAdmin. Without it, the profile's apps make
their own, as before: run_product builds the default profile so, and nothing it serves changed (HM-01's golden
regression and contract freezes, byte for byte).

The runtime borrows its store: the caller opened it (for the default profile after the legacy migration) and closes it
after the runtime. The runtime writes no file of its own; what is written is what the store, the child spec (the
child's working directory) and the operation journal wrote before.

HM-08 (plan 3.1, 5.1, 5.2, 12.2): ProfileManager is every profile of one switched-on add-on (features.enabled; the
repository switches no product on). run_product builds it instead of the default profile's lone ProfileRuntime: one
SharedAdmin for every profile, the default profile's runtime, every profile the index lists (its store opened
existing-only, its runtime with its quota: child connections and forwarding slots), their gates and the 8081 token
dispatcher (profile_router), and the soft open-file limit the 8081 bound needs. A ProfileRuntime takes the quota's
values and the add-on's reply mask as keyword-only options; left out, it is built as before. HM-09 adds start_all and
stop_all to the manager (see its docstring).
"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import re
import resource
import stat

import httpx

from . import profiles
from .access import TokenAccess
from .admin_auth import AdminAuthority
from .config import ConfigError, strict_json
from .configuration import ConfigurationState
from .gateway import ADMIN_SLOTS, AdminPipeline, make_apps, profile_echo
from .health import HealthMonitor
from .lifecycle import CHILD_PORT, Supervisor, child_url
from .products import ProductStore
from .profile_router import Credentials, McpDispatcher, ProfileGate, RefusalAllowance, Reports, Unavailable
from .profiles import PROFILE_ID

logger = logging.getLogger(__name__)
DEFAULT_PROFILE = profiles.DEFAULT_PROFILE
CHILD_CONNECTIONS = 40  # the child client's connection limit, as before (plan 5.2: the default profile keeps 40)
# What the runtime gives make_apps itself; app_options cannot name them.
RUNTIME_OPTIONS = frozenset({'child_url', 'health', 'backend_changed', 'configuration', 'backend_check',
                             'restart_child', 'diagnostics', 'availability', 'token_access', 'mutation_lock',
                             'authority', 'admin_slots', 'admin_pipeline', 'profile_view', 'forward_slots',
                             'slot_busy', 'reply_secrets'})
MANAGEMENT_LISTENER_LIMIT = 64  # 8099's limit_concurrency (run_product), switched on or off


@dataclass(frozen=True)
class SharedAdmin:
    """What every profile of one add-on shares on the management listener (plan 3.2, FM-54): one AdminAuthority (one
    CSRF key; one HA role verifier, so one bound on its concurrent queries), one set of management slots and, from
    HM-10, the shared management pipeline (gateway.make_apps admin_pipeline)."""
    authority: AdminAuthority
    slots: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(ADMIN_SLOTS))
    pipeline: AdminPipeline | None = None


class ProfileRuntime:
    """One profile's runtime (see the module docstring). Open it (async with, or open() and aclose()), launch() its
    child, run monitor() in a task; its two apps are admin_app and mcp_app.

    store: the profile's open ProductStore. tools, child_spec: the product's tool registry and child spec builder
    (child_spec(state, directory, port=...); products.child_spec, n8n_adapter.child_spec). port: the child's loopback
    port. profile_id: 'default' or 24 lowercase hexadecimal characters (contract 1.1). lifecycle: keyword options of
    the profile's Supervisor. shared: SharedAdmin, or None for apps with an administration of their own. profile_view:
    the profile's echo for make_apps (a callable returning {"id", "label", "is_default"}), or None. app_options: the
    product's make_apps options (verify_admin, management, server_name, instructions, listing,
    secret_path_allowed_origins).

    HM-08 (ProfileManager passes them for a switched-on product; left out, the runtime is built as before):
    child_connections: the child client's connection limit (CHILD_CONNECTIONS; an additional profile has 24).
    forward_slots, slot_busy, reply_secrets: make_apps' options of the same names (the profile's forwarding slots,
    the answer when one stays busy, the add-on's reply mask), passed only when given.

    mcp_listener_limit: 8081's limit_concurrency when this runtime serves the add-on alone: 64, as before."""
    mcp_listener_limit = 64

    def __init__(self, store, tools, child_spec, *, port=CHILD_PORT, profile_id=DEFAULT_PROFILE, lifecycle=None,
                 shared=None, profile_view=None, app_options=None, child_connections=CHILD_CONNECTIONS,
                 forward_slots=None, slot_busy=None, reply_secrets=None):
        if not isinstance(profile_id, str) or not PROFILE_ID.fullmatch(profile_id):
            raise ValueError('invalid profile id')
        if type(child_connections) is not int or child_connections < 1:
            raise ValueError('invalid child connections')
        self.child_url = child_url(port)  # an invalid port is refused before anything is made
        if shared is not None and not isinstance(shared, SharedAdmin):
            raise ValueError('not a shared administration')
        if profile_view is not None and not callable(profile_view):
            raise ValueError('invalid profile echo')
        self.app_options = dict(app_options or {})
        if RUNTIME_OPTIONS & self.app_options.keys():
            raise ValueError('the runtime passes ' + ', '.join(sorted(RUNTIME_OPTIONS & self.app_options.keys())))
        self.store, self.tools, self.child_spec = store, tools, child_spec
        self.port, self.profile_id = port, profile_id
        self.child_connections = child_connections
        self.gateway_options = {name: value for name, value in (
            ('forward_slots', forward_slots), ('slot_busy', slot_busy), ('reply_secrets', reply_secrets))
            if value is not None}
        self.lifecycle = dict(lifecycle or {})
        self.shared, self.profile_view = shared, profile_view
        self.supervisor = self.child = self.health = self.configuration = None
        self.token_access = self.mutation_lock = None
        self.admin_app = self.mcp_app = None
        self._stack = None

    async def open(self):
        """Make the profile's child Supervisor, child client, health monitor, configuration status, token access, lock
        and apps. If any of it fails, what was made is closed again (the client closed, the Supervisor stopped) and the
        error raised; the store stays open."""
        if self._stack is not None:
            raise RuntimeError('profile runtime already open')
        self._stack = stack = AsyncExitStack()
        try:
            self.supervisor = manager = Supervisor(None, **self.lifecycle)
            stack.push_async_callback(manager.stop)  # closed in reverse: the child client first, then the child
            self.child = child = await stack.enter_async_context(httpx.AsyncClient(
                trust_env=False, follow_redirects=False, timeout=httpx.Timeout(10, connect=3),
                limits=httpx.Limits(max_connections=self.child_connections)))
            self.health = health = HealthMonitor(self.store, manager, child, child_url=self.child_url)
            self.configuration = configuration = ConfigurationState(self.store, manager, health)
            self.token_access, self.mutation_lock = TokenAccess(self.store), asyncio.Lock()
            if self.profile_view is not None and profile_echo(self.profile_view())['id'] != self.profile_id:
                raise ValueError('invalid profile echo')
            self.admin_app, self.mcp_app = make_apps(
                self.store, self.tools, child, child_url=self.child_url, health=health.snapshot,
                backend_changed=self.backend_changed, configuration=configuration,
                backend_check=getattr(health, 'test_saved', None), restart_child=self.backend_changed,
                diagnostics=getattr(manager, 'diagnostics', None), availability=health.availability,
                token_access=self.token_access, mutation_lock=self.mutation_lock, **self._shared_options(),
                **self.gateway_options, **self.app_options)
        except BaseException:
            await self.aclose()
            raise
        return self

    def _shared_options(self):
        options = {}
        if self.shared is not None:
            options.update(authority=self.shared.authority, admin_slots=self.shared.slots)
            if self.shared.pipeline is not None:
                options['admin_pipeline'] = self.shared.pipeline
        if self.profile_view is not None:
            options['profile_view'] = self.profile_view
        return options

    async def aclose(self):
        """Close what open() made: the child client, then the child (stopped and reaped). The store stays open."""
        stack, self._stack = self._stack, None
        if stack is not None:
            await stack.aclose()

    async def __aenter__(self):
        return await self.open()

    async def __aexit__(self, *exc_info):
        stack, self._stack = self._stack, None
        if stack is not None:
            await stack.__aexit__(*exc_info)

    async def backend_changed(self, state):
        """Relaunch the profile's child on state (make_apps backend_changed and restart_child). The child is stopped
        before the replacement spec is built: old credentials never keep serving a newly saved state after a failure.
        A failure is recorded (configuration: child_start_failed) and raised."""
        self.configuration.begin(state)
        self.health.backend = 'unknown'
        try:
            await self.supervisor.stop()
            self.supervisor.spec = self.child_spec(state, self.store.directory, port=self.port)
            await self.supervisor.start()
        except Exception:
            self.configuration.failed('child_start_failed')
            raise

    async def launch(self):
        """Start the child on the saved state, before the listeners serve. A failure is not raised: management stays
        available to report it (configuration: child_start_failed) and to retry; no third-party exception text shows."""
        try:
            await self.backend_changed(self.store.load())
        except Exception:
            pass

    def monitor(self):
        """The health monitor's loop, for the caller's task: a check at once, then every 15 s, until cancelled."""
        return self.health.run()


# ---- HM-08: the open-file budget of a switched-on add-on (plan 5.2, C2-SF-5; an estimate HM-03a and HM-19c check) ----

ROLE_QUERY_FILES = 8   # the HA Core role queries at once (ha_role: one socket each)
CHILD_FILES = 4        # one child's stdin, stdout and stderr pipes and its process handle
BASE_FILES = 64        # the interpreter, event loop, listening sockets, logs and state reads


def open_file_budget(product):
    """(needed, target): the descriptors a switched-on product may hold at worst (8081's bound, 8099's, every
    profile's child client up to the product's additional-profile limit, the role queries, every child's pipes and a
    base), and that plus 25% (the soft limit raise_open_file_limit asks for)."""
    extras = profiles.capacity(product).policy_limit
    needed = (profiles.mcp_listener_limit(product) + MANAGEMENT_LISTENER_LIMIT
              + profiles.DEFAULT_PROFILE_QUOTA.child_connections + profiles.EXTRA_PROFILE_QUOTA.child_connections * extras
              + ROLE_QUERY_FILES + CHILD_FILES * (extras + 1) + BASE_FILES)
    return needed, -(-needed * 5 // 4)


def raise_open_file_limit(needed, target):
    """Make the soft RLIMIT_NOFILE at least needed: when it is below target, ask for target (never above the hard
    limit; raising the soft limit needs no privilege). True when the soft limit is at least needed afterwards. What
    the platform allows is read when it runs (HM-03a has not measured the HAOS values): a limit that cannot be read or
    set is never assumed to be enough; one WARNING (the numbers only) says what is given up."""
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    except (OSError, ValueError, AttributeError):
        soft = hard = None
    infinite = getattr(resource, 'RLIM_INFINITY', None)
    if soft is not None and (soft == infinite or soft >= target):
        return True
    if soft is not None and (hard == infinite or hard >= needed):
        wanted = target if hard == infinite else min(target, hard)
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (wanted, hard))
            return True
        except (OSError, ValueError):
            pass
    if soft is not None and soft >= needed:
        return True
    shown = 'unreadable' if soft is None else f'soft {soft}, hard {hard}'
    logger.warning('multi-profile: the open file limit (%s) is below the %d this product needs once additional '
                   'profiles are served; additional profiles are not served and the MCP listener keeps its 64 '
                   'connections', shown, needed)
    return False


_TOKEN = re.compile(r'[A-Za-z0-9_-]{43}')


def held_tokens(directory):
    """(token, child token) in a profile directory's state.json (None for one that is missing or malformed), read
    without its lock or any change (an orphan: never opened, never routed; plan 4.4), for the reply mask and the
    consistency report; None when the file cannot be read."""
    try:
        fd = os.open(Path(directory) / 'state.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    chunks, size = [], 0
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                or info.st_size > 65536):
            return None
        while chunk := os.read(fd, 65537 - size):
            chunks.append(chunk)
            size += len(chunk)
            if size > 65536:
                return None
    except OSError:
        return None
    finally:
        os.close(fd)
    try:
        value = strict_json(b''.join(chunks))
    except (ValueError, RecursionError):
        return None
    if not isinstance(value, dict):
        return None
    return tuple(found if isinstance(found, str) and _TOKEN.fullmatch(found) else None
                 for found in (value.get('token'), value.get('child_token')))


@dataclass(eq=False)
class RegisteredProfile:
    """One profile as the manager keeps it: its id, index port and label (None for the default profile), its runtime
    and store (an additional profile's store is the manager's to close; the default profile's is run_product's), its
    gate on 8081 (profile_router.ProfileGate), its credentials (the dispatcher's digest, the reply mask's values) and why
    its child must not start (profiles.disabled_reasons: profile_limit, memory_capacity, port_conflict; HM-09 acts on
    it, HM-10 lists it)."""
    profile_id: str
    port: int
    label: str | None
    runtime: ProfileRuntime
    store: object
    gate: ProfileGate
    credentials: Credentials
    disabled: dict | None = None


class ProfileManager:
    """Every profile of one switched-on add-on (multi-profile plan 3.1, 3.2, 12.2; HM-08 builds this skeleton, HM-09
    adds start_all and stop_all). run_product builds it on the default profile's store (opened after the legacy
    migration) when features.enabled(product); it serves as a ProfileRuntime serves: async with, admin_app and mcp_app
    for the two listeners, mcp_listener_limit for 8081, launch() and monitor().

    open():
    - one SharedAdmin for every profile (one AdminAuthority on the product's verify_admin: one CSRF key, one bound on
      the role queries; one set of 16 management slots; HM-10 adds the shared pipeline);
    - the default profile's runtime on the default store and child port, with the default quota
      (profiles.DEFAULT_PROFILE_QUOTA: 40 child connections, 32 forwarding slots);
    - the index (profiles.read_index; a corrupt one, or one that changes later: every token 503, DQ-12) and the profiles
      directory (scan_profiles; when it cannot be listed: every token 503); the open-file budget (open_file_budget,
      raise_open_file_limit): when the soft limit cannot cover it, no additional profile is served and 8081 keeps 64;
    - every profile the index lists, in index order: its store opened existing-only (never created), its runtime with
      the additional quota (24 connections, 16 slots) on its index port, its gate; one that cannot be opened is not
      served and is named once in a WARNING (its id's first 8 characters); an orphan directory (not in the index) is
      never opened: its token and child token are read once, for the reply mask only; profiles sharing a token or child
      token are named once (DQ-09: the dispatcher answers 503 for a shared token);
    - the 8081 dispatcher (profile_router.McpDispatcher).
    Every runtime gets the busy answer of its gate (make_apps slot_busy) and the add-on's reply mask (reply_secrets).

    What HM-08 does not do (HM-09): launch() starts the default profile's child only, as run_product did, and monitor()
    is the default profile's monitor (DQ-21: any of its components stopping ends the add-on). Additional profiles are
    opened, routed and answered by their own apps (initialize, ping and tools/list by the gateway itself, tools/call
    refused while no child runs), but their children are not started.

    For HM-09: start_all() (the default profile first, then the additional ones, at most two starting at once, each
    after the previous one's health check passed or 30 s; one that cannot start is marked, the others go on; a profile
    with a disabled reason is not started), stop_all() (every Supervisor in parallel within HA's 30 s), every profile's
    monitor (DQ-21: an additional profile's monitor ending marks only that profile; DQ-25: start points staggered).
    entry.runtime.lifecycle takes the watchdog options (DQ-20); entry.disabled the reason not to start.
    For HM-10: add(entry) and remove(profile_id) register and drop a profile at run time (an index entry written with
    profiles.write_index(expected=manager.index) is adopted with adopt_index(view)); shared.pipeline the shared
    management pipeline; get(profile_id).runtime.admin_app each profile's management app."""

    def __init__(self, store, product, tools, child_spec, *, port=CHILD_PORT, app_options=None):
        self.store, self.product, self.tools, self.child_spec = store, product, tools, child_spec
        self.port = port
        self.app_options = dict(app_options or {})
        self.layout = profiles.Layout(Path(store.directory))
        self.reports = Reports()
        self.allowance = RefusalAllowance()
        self.shared = self.index = self.mcp_app = None
        self.mcp_listener_limit = 64
        self.orphan_secrets = frozenset()
        self.unusable = False  # the profiles directory could not be listed at startup
        self._entries = {}
        self._stack = None
        self._index_reported = False

    # ---- what the listeners and run_product use ----

    @property
    def admin_app(self):
        return self.get(DEFAULT_PROFILE).runtime.admin_app

    def profiles(self):
        """The registered profiles: the default profile first, then the index's order."""
        return tuple(self._entries.values())

    def get(self, profile_id):
        return self._entries.get(profile_id)

    async def launch(self):
        """The default profile's child, as run_product started it (HM-09: start_all for every profile)."""
        await self.get(DEFAULT_PROFILE).runtime.launch()

    def monitor(self):
        """The default profile's health monitor loop (HM-09: every profile's, with DQ-21's isolation)."""
        return self.get(DEFAULT_PROFILE).runtime.monitor()

    # ---- what the dispatcher uses ----

    def check(self):
        """Unavailable while which profile holds a token cannot be trusted: the profiles directory could not be listed,
        or the index is corrupt or changed behind the add-on's back since it was read (sticky until a restart;
        DQ-12). One lstat of the index."""
        if self.unusable:
            raise Unavailable()
        view = profiles.recheck_index(self.layout.index, self.index)
        if view is not self.index:
            self.index = view
            if view.state == profiles.INDEX_MODIFIED and not self._index_reported:
                self._index_reported = True
                logger.warning('multi-profile: the profile index changed outside the add-on; MCP requests are refused '
                               '(503) until the add-on restarts')
        if not view.serves_mcp:
            raise Unavailable()

    def serves_mcp(self):
        try:
            self.check()
        except Unavailable:
            return False
        return True

    def reply_secrets(self):
        """Every token and child token the add-on holds now (plan 5.1 point 8): every registered profile's (read again
        when its state changed; what was read last when it cannot be read now) and every orphan's."""
        found = set(self.orphan_secrets)
        for entry in self._entries.values():
            try:
                entry.credentials.refresh()
            except ConfigError:
                pass
            found.update(entry.credentials.values)
        return found

    # ---- registration ----

    async def add(self, profile_id, store, *, port, label=None, disabled=None):
        """Open profile_id's runtime on its open store and register it (routed from now on). The default profile with
        the default quota, any other with the additional one. The caller keeps the store until it is registered; from
        then on an additional profile's store is the manager's to close."""
        if profile_id in self._entries:
            raise ValueError('profile already registered')
        default = profile_id == DEFAULT_PROFILE
        quota = profiles.DEFAULT_PROFILE_QUOTA if default else profiles.EXTRA_PROFILE_QUOTA
        gate = ProfileGate(profile_id, quota, self.allowance, self.reports)
        credentials = Credentials(store, owned=not default)
        runtime = ProfileRuntime(store, self.tools, self.child_spec, port=port, profile_id=profile_id,
                                 shared=self.shared, app_options=self.app_options,
                                 child_connections=quota.child_connections, forward_slots=quota.forward_slots,
                                 slot_busy=gate.slot_busy, reply_secrets=self.reply_secrets)
        await runtime.open()
        entry = RegisteredProfile(profile_id, port, label, runtime, store, gate, credentials, disabled)
        self._entries[profile_id] = entry
        return entry

    async def remove(self, profile_id):
        """Drop an additional profile: no longer routed, its runtime closed (its client, then its child), its store
        closed. HM-10's deletion revokes the token and commits the index first."""
        if profile_id == DEFAULT_PROFILE:
            raise ValueError('the default profile stays')
        entry = self._entries.pop(profile_id)
        try:
            await entry.runtime.aclose()
        finally:
            entry.store.close()

    def adopt_index(self, view):
        """HM-10: the index this process wrote last (profiles.write_index's view) is the one to compare with."""
        self.index = view

    # ---- open and close ----

    async def open(self):
        if self._stack is not None:
            raise RuntimeError('profile manager already open')
        self._stack = AsyncExitStack()
        try:
            self.shared = SharedAdmin(AdminAuthority(self.app_options.get('verify_admin')))
            default = await self.add(DEFAULT_PROFILE, self.store, port=self.port)
            self._stack.push_async_callback(default.runtime.aclose)
            self.mcp_app = McpDispatcher(self, self.reports)
            self.index = profiles.read_index(self.layout.index)
            if self.index.state == profiles.INDEX_CORRUPT:
                logger.warning('multi-profile: the profile index cannot be used; MCP requests are refused (503) for '
                               'every token until it is quarantined or a backup is restored')
            try:
                scan = profiles.scan_profiles(self.layout)
            except profiles.ProfileDataError:
                self.unusable, scan = True, profiles.ProfilesScan((), (), 0)
                logger.warning('multi-profile: the profiles directory cannot be listed; MCP requests are refused (503) '
                               'for every token')
            needed, target = open_file_budget(self.product)
            served = raise_open_file_limit(needed, target)
            if served:
                self.mcp_listener_limit = profiles.mcp_listener_limit(self.product)
            listed = (self.index.entries if served and not self.unusable and profiles.supports_profiles(self.product)
                      else ())
            await self._open_listed(listed, scan)
        except BaseException:
            await self.aclose()
            raise
        return self

    async def _open_listed(self, listed, scan):
        reasons = profiles.disabled_reasons(listed, profiles.capacity(self.product))
        for item in listed:
            try:
                store = profiles_store(self.layout.profile(item.id), self.product)
            except (ConfigError, ValueError):
                logger.warning('multi-profile: profile %s is in the profile index but its data cannot be read; it is '
                               'not served', profiles.log_id(item.id))
                continue
            try:
                entry = await self.add(item.id, store, port=item.port, label=item.label, disabled=reasons.get(item.id))
            except Exception:
                store.close()
                logger.warning('multi-profile: profile %s could not be opened; it is not served',
                               profiles.log_id(item.id))
                continue
            self._stack.push_async_callback(self._close_extra, entry)
        # Profile directories not served (orphans; or, with an unusable index or no file budget, every one): never
        # opened or routed, their tokens read once for the reply mask.
        indexed = {item.id for item in self.index.entries}
        credentials, secrets = {}, set()
        for profile_id in scan.profiles:
            if profile_id in self._entries:
                continue
            pair = credentials[profile_id] = held_tokens(self.layout.profile(profile_id))
            secrets.update(value for value in pair or () if value)
            if profile_id not in indexed and self.index.serves_mcp:
                logger.warning('multi-profile: profile directory %s is not in the profile index (an orphan); it is never '
                               'served', profiles.log_id(profile_id))
        self.orphan_secrets = frozenset(secrets)
        for entry in self._entries.values():
            try:
                entry.credentials.refresh()
                state = entry.store.load()
                credentials[entry.profile_id] = (state.token, state.child_token)
            except ConfigError:
                credentials[entry.profile_id] = None
        consistency = profiles.check_consistency(listed, scan, credentials)
        for group in consistency.shared_secrets:
            logger.warning('multi-profile: profiles %s share a token or child token (a copied directory?); a request '
                           'with a shared token is refused (503)', ', '.join(profiles.log_id(p) for p in group))

    async def _close_extra(self, entry):
        if self._entries.get(entry.profile_id) is entry:
            await self.remove(entry.profile_id)

    async def aclose(self):
        """Close every runtime (the additional profiles' first; each its client, then its child) and the additional
        profiles' stores; the default profile's store stays run_product's."""
        stack, self._stack = self._stack, None
        if stack is not None:
            await stack.aclose()
        self._entries.clear()

    async def __aenter__(self):
        return await self.open()

    async def __aexit__(self, *exc_info):
        await self.aclose()


def profiles_store(directory, product):
    """An additional profile's store, opened existing-only (HM-07: never created, owner checked)."""
    return ProductStore(directory, product, existing_only=True)
