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
values and the add-on's reply mask as keyword-only options; left out, it is built as before.

HM-09 (plan 5.4; contract 7; DQ-20 (b), DQ-21, DQ-25): the manager runs every profile's child. Each Supervisor gets
the PaaS watchdog and the spawn check (lifecycle.WATCHDOG; spawn_refusal), an additional profile's child its
resources (oom_score_adj 500, nice +5) and the memory check of a save or the panel's restart (hold); each health
monitor is staggered, backs off refused logins and needs two failures in a row (health.py). launch() starts the
default profile's child before the listeners serve, as before; monitor() runs start_all() (the additional profiles,
staggered) and every profile's monitor (DQ-21: an additional profile's monitor ending marks only that profile); the
manager's close stops every child at once (stop_all). A ProfileRuntime takes hold, monitor_options and
report_blocked as keyword-only options; left out (run_product's default profile of a product not switched on), it
is built as before.

HM-10 (plan 5.3; contract 3; DQ-13, DQ-15, DQ-40 (a) ②): 8099 of a switched-on add-on is the manager's management
dispatcher (profile_router.AdminDispatcher; admin_app), which runs the shared pipeline and then a global path
(profile_admin.ProfileAdmin: list, create, rename, delete, the index quarantine) or a profile's own action
(ProfileRuntime.admin_action). Every profile's answers carry its echo (profile_view; the bootstrap also
bootstrap_fields); an additional profile shows the add-on's one endpoint, the default profile's (default_endpoint).
A ProfileRuntime binds its revisions (ETags) to its profile id in every mode (ConfigurationState profile_id: opaque,
process-local values, so nothing a client sees changes for a product not switched on) and takes default_endpoint and
bootstrap_fields as keyword-only options, given by the manager only.

HM-31 (plan 12.3 HM-31; contract 2.4, 5; PaaS #155): the manager holds the add-on's one request body budget
(request_budget.RequestBudget, derived when the manager is made: at startup, with every profile the product may run
counted); each profile's app charges its share (ProfileGate.budget_share, make_apps body_budget). A switched-off
add-on's only profile has a budget of its own (make_apps makes it).

HM-12 (plan 9 Odoo row, 12.3 HM-12; contract 3.1; DQ-05): every ProfileRuntime gives its apps stop_child (make_apps
stop_child), which stops the child and drops its spec. Only a switched-on product's backend identity change uses it
(gateway.make_apps: stop, one write of the connection and a new token, publish, start); switched off, nothing calls it.

HM-30 (plan 5.5; contract 6): run_product gives the manager the add-on's one reply worker (reply_worker.ReplyWorker)
and the manager gives every profile's runtime its own turn on it (a Lane, make_apps reply_worker): every profile's
replies are processed there, the profiles taking turns. Each gate also bounds its profile's answers not received yet
(profiles.ProfileQuota.pending_reply_bytes; profile_router). A ProfileRuntime takes reply_worker as a keyword-only
option; left out, its replies are processed on the event loop, as before.

HM-13b (plan 8.4; contract 1.2, 7; not gated): run_product runs the boot guard (restore_lock.guard) before it builds
the manager or the default profile's lone runtime: no child starts and no listener exists before a restore, an
unfinished "revoke all" and dormant profiles are handled. A product that is not switched on but has profile data gets a
ProfileRuntime with dormant_profiles (the number the guard left revoked, for the bootstrap; make_apps' option of the
same name); left out, the runtime is built as before.

HM-13c (plan 6, 8.4; contract 1.2, 3.6, 4.1, 4.2): run_product hands the restore notice a start found
(restore_lock.Notice; DQ-03 (b): the default profile's token is the backup's) to the default profile's runtime
(restore_notice, make_apps' option of the same name), switched on (the manager's restore_notice) or not; left out (no
notice: every installation that was never restored), the runtime is built as before. A switched-on profile's runtime
also gets review_required (its token/rotate waits for its restore review: ProfileAdmin.review_required; so does
HM-12's identity change when it would rotate the token, HM-13c review S-3: gateway.make_apps), and the manager keeps
revoke_fence: the digests of tokens a "revoke all" could not revoke, which 8081 refuses (503).

HM-27 (plan 8.7, 12.3 HM-27; DQ-11 (a); contract 2.6, 3.1): the manager holds the add-on's one Origin policy of the
secret path (origin_policy.OriginPolicy; /data/mcp/origin-policy.json, read when asked, written only by the panel's save)
unless the product keeps its own rule (Headscale: secret_path_allowed_origins), and gives every profile's apps its
check (make_apps origin_policy). A ProfileRuntime takes origin_policy as a keyword-only option; left out (every
switched-off product), the secret path takes any Origin, as before.
"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, nullcontext
from dataclasses import dataclass, field
from functools import partial
import logging
import os
from pathlib import Path
import re
import resource
import stat

import httpx

from . import health as health_module, origin_policy, profiles, request_budget
from .child_identity import ListenerGuard
from .access import TokenAccess
from .admin_auth import AdminAuthority
from .config import ConfigError, strict_json
from .configuration import ConfigurationState
from .gateway import ADMIN_SLOTS, AdminPipeline, make_apps, profile_echo
from .health import AUTH_BACKOFF, HealthMonitor
from .lifecycle import (CHILD_PORT, CHILD_PORT_CONFLICT, CHILD_PORT_IN_USE, EXTRA_CHILD_RESOURCES, MEMORY_CAPACITY,
                        WATCHDOG, ChildLog, LifecycleLog, Supervisor, child_url)
from .products import CONNECTIONS, ProductStore
from .profile_admin import ProfileAdmin
from .profile_router import AdminDispatcher, Credentials, McpDispatcher, ProfileGate, Reports, Unavailable
from .reply_memory import ReplyMemory
from .profiles import PROFILE_ID

logger = logging.getLogger(__name__)
DEFAULT_PROFILE = profiles.DEFAULT_PROFILE
CHILD_CONNECTIONS = 40  # the child client's connection limit, as before (plan 5.2: the default profile keeps 40)
# What the runtime gives make_apps itself; app_options cannot name them.
RUNTIME_OPTIONS = frozenset({'child_url', 'health', 'backend_changed', 'configuration', 'backend_check',
                             'restart_child', 'diagnostics', 'availability', 'token_access', 'mutation_lock',
                             'authority', 'admin_slots', 'admin_pipeline', 'profile_view', 'forward_slots',
                             'slot_busy', 'reply_secrets', 'child_blocked', 'default_endpoint', 'bootstrap_fields',
                             'body_budget', 'stop_child', 'reply_worker', 'dormant_profiles', 'restore_notice',
                             'review_required', 'origin_policy'})
MANAGEMENT_LISTENER_LIMIT = 64  # 8099's limit_concurrency (run_product), switched on or off
# HM-09 (plan 5.4; C2-SF-4): after the default profile's child, at most STAGGER_SLOTS additional children start at
# once; a place is freed when its child answered a health check, could not start, or after STAGGER_SECONDS.
STAGGER_SLOTS = 2
STAGGER_SECONDS = 30
STAGGER_POLL_SECONDS = 0.5  # how often a starting child is checked (a refused connection costs the backend nothing)
SPAWN_POLL_SECONDS = 0.02  # how often a child not spawned yet is looked at
REVIVE_POLL_SECONDS = 1.0  # DQ-21: how often a failed profile is looked at, until the panel restarts it
CHILD_UP = ('starting', 'running')
# Why a disabled profile (profiles.disabled_reasons: index order, PaaS order) is not started: its blocked reason and
# the log's words. profile_limit has no reason code of its own (contract 3.6): the list's disabled_reason says it.
DISABLED_HOLDS = {
    'port_conflict': (CHILD_PORT_CONFLICT, 'the profile index gives this port to another profile or to the default '
                                           'child (port_conflict)'),
    'memory_capacity': (MEMORY_CAPACITY, 'the memory limit runs fewer additional profiles (memory_capacity)'),
    'profile_limit': (None, 'the product allows fewer additional profiles (profile_limit)'),
}


@dataclass(frozen=True)
class SharedAdmin:
    """What every profile of one add-on shares on the management listener (plan 3.2, FM-54): one AdminAuthority (one
    CSRF key; one HA role verifier, so one bound on its concurrent queries), one set of management slots and,
    optionally, a pipeline each profile's app hands its requests to (gateway.make_apps admin_pipeline, HM-05's
    injection point). HM-10's 8099 dispatcher does not use one: it runs the shared pipeline itself, with this authority
    and these slots, and calls each profile's action once it has chosen the profile (profile_router.AdminDispatcher)."""
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
    the answer when one stays busy, the add-on's reply mask), passed only when given. HM-31: body_budget likewise (the
    profile's share of the add-on's request body budget; left out, make_apps makes a budget of its own).

    HM-09 (likewise): hold(memory=...): why the child must not start now ((reason, detail) for Supervisor.block, or
    None), asked at every start before the spec is built (memory False: the profile's own verdict, e.g. disabled) and,
    for a save or the panel's restart of a configured profile, after it (memory True: the memory check too); the boot
    (launch) asks memory False only. monitor_options: the HealthMonitor's keyword options (staggered start, auth
    backoff, tolerance). report_blocked: child/restart answers with blocked_reason (make_apps child_blocked).

    HM-10 (likewise): default_endpoint, bootstrap_fields: make_apps' options of the same names, passed only when given.
    admin_action (after open()) is the profile's action for the management dispatcher (make_apps' admin app state).

    HM-30 (likewise): reply_worker: the profile's turn on the add-on's reply worker (reply_worker.Lane; make_apps
    reply_worker).

    HM-13b (run_product, for a product not switched on that has profile data): dormant_profiles, make_apps' option of
    the same name, passed only when given.

    HM-13c: restore_notice (the default profile's, from run_product or the manager) and review_required (a switched-on
    profile's, from the manager), make_apps' options of the same names, passed only when given.

    HM-27 (likewise): origin_policy: the profile's check of the add-on's Origin policy (OriginPolicy.guard; make_apps
    origin_policy).

    mcp_listener_limit: 8081's limit_concurrency when this runtime serves the add-on alone: 64, as before."""
    mcp_listener_limit = 64

    def __init__(self, store, tools, child_spec, *, port=CHILD_PORT, profile_id=DEFAULT_PROFILE, lifecycle=None,
                 shared=None, profile_view=None, app_options=None, child_connections=CHILD_CONNECTIONS,
                 forward_slots=None, slot_busy=None, reply_secrets=None, hold=None, monitor_options=None,
                 report_blocked=False, default_endpoint=None, bootstrap_fields=None, body_budget=None,
                 reply_worker=None, dormant_profiles=None, restore_notice=None, review_required=None,
                 origin_policy=None, listener_identity=False):
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
        self.reply_worker = reply_worker
        self.gateway_options = {name: value for name, value in (
            ('forward_slots', forward_slots), ('slot_busy', slot_busy), ('reply_secrets', reply_secrets),
            ('default_endpoint', default_endpoint), ('bootstrap_fields', bootstrap_fields),
            ('body_budget', body_budget), ('reply_worker', reply_worker),
            ('dormant_profiles', dormant_profiles), ('restore_notice', restore_notice),
            ('review_required', review_required), ('origin_policy', origin_policy)) if value is not None}
        if hold is not None and not callable(hold):
            raise ValueError('invalid start hold')
        self.hold = hold
        self.monitor_options = dict(monitor_options or {})
        if report_blocked:
            self.gateway_options['child_blocked'] = self.blocked_reason
        self.listener_identity = listener_identity
        self.lifecycle = dict(lifecycle or {})
        self.shared, self.profile_view = shared, profile_view
        self.supervisor = self.child = self.health = self.configuration = None
        self.token_access = self.mutation_lock = None
        self.admin_app = self.mcp_app = self.admin_action = None
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
            limits = httpx.Limits(max_connections=self.child_connections)
            guard = ListenerGuard(manager, self.port, limits=limits) if self.listener_identity else None
            manager.listener_identity = guard
            self.child = child = await stack.enter_async_context(httpx.AsyncClient(
                trust_env=False, follow_redirects=False, timeout=httpx.Timeout(10, connect=3),
                limits=limits, **({"transport": guard} if guard is not None else {})))
            self.health = health = HealthMonitor(self.store, manager, child, child_url=self.child_url,
                                                 **self.monitor_options)
            # HM-10 (DQ-15): the profile's ETags are bound to its id.
            self.configuration = configuration = ConfigurationState(self.store, manager, health,
                                                                    profile_id=self.profile_id)
            self.token_access, self.mutation_lock = TokenAccess(self.store), asyncio.Lock()
            if self.profile_view is not None and profile_echo(self.profile_view())['id'] != self.profile_id:
                raise ValueError('invalid profile echo')
            self.admin_app, self.mcp_app = make_apps(
                self.store, self.tools, child, child_url=self.child_url, health=health.snapshot,
                backend_changed=self.backend_changed, policy_changed=self.policy_changed, configuration=configuration,
                backend_check=getattr(health, 'test_saved', None), restart_child=self.backend_changed,
                stop_child=self.stop_child,
                diagnostics=getattr(manager, 'diagnostics', None), availability=health.availability,
                token_access=self.token_access, mutation_lock=self.mutation_lock, **self._shared_options(),
                **self.gateway_options, **self.app_options)
            # HM-10: the profile's action, for the switched-on management dispatcher (make_apps keeps it on its admin
            # app's state). An admin app without one (a stand-in some tests pass for make_apps' apps) leaves it None:
            # only the switched-on dispatcher calls it, and run_product serves any admin app it is given as before.
            self.admin_action = getattr(getattr(self.admin_app, 'state', None), 'profile_action', None)
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

    def blocked_reason(self):
        """Why the child is not started now (Supervisor.blocked_reason), for make_apps child_blocked (HM-09)."""
        return None if self.supervisor is None else self.supervisor.blocked_reason

    async def backend_changed(self, state):
        """Relaunch the profile's child on state (make_apps backend_changed and restart_child). The child is stopped
        before the replacement spec is built: old credentials never keep serving a newly saved state after a failure.
        A failure is recorded (configuration: child_start_failed) and raised. HM-09: a save or the panel's restart,
        so the hold's memory check applies (hold memory=True), and the health monitor's backoff starts again."""
        await self._relaunch(state, asked=True)

    async def policy_changed(self, previous, state):
        """Apply Nextcloud policy at the gateway; restart a running child only when tools widen."""
        from .policy import enabled
        before = {name for name in self.tools if enabled(name, self.tools, previous)}
        after = {name for name in self.tools if enabled(name, self.tools, state)}
        manager = self.supervisor
        if after - before and manager.status in ('running', 'starting'):
            await self._relaunch(state, asked=True)
            return
        # A watchdog retry or a later explicit start must use the saved policy even
        # when this save does not itself restart or start the child.
        if manager.spec is not None:
            manager.spec = self.child_spec(state, self.store.directory, port=self.port)
        self.configuration.policy_accepted(previous, state)

    async def stop_child(self):
        """HM-12 (contract 3.1; DQ-05; make_apps stop_child): stop the child before its backend identity changes, so
        that no child runs on the old credentials once a new token exists (UC-21). Its spec is dropped: until a relaunch
        on a given state (backend_changed: the new state, or the saved one when the change failed) nothing can start it
        again on the old credentials. Called holding the profile's mutation_lock (the change's). A stop that fails is
        raised (the child may still run; the caller writes nothing)."""
        await self.supervisor.stop()
        self.supervisor.spec = None

    async def launch(self):
        """Start the child on the saved state, before the listeners serve. A failure is not raised: management stays
        available to report it (configuration: child_start_failed) and to retry; no third-party exception text shows.
        HM-09: the boot, so no memory check (hold memory=False only). HM-10 (HM-09 review S-12): under the profile's
        mutation_lock, which a save and the panel's restart hold while they relaunch it, so the boot's start
        (start_all) and the start after an index change (ProfileManager.reevaluate) never interleave with them; it
        waits for a change under way to finish (bounded: an action holds the lock until its relaunch is done)."""
        lock = self.mutation_lock if self.mutation_lock is not None else nullcontext()
        try:
            async with lock:
                await self._relaunch(self.store.load(), asked=False)
        except Exception:
            pass

    async def _relaunch(self, state, *, asked):
        self.configuration.begin(state)
        self.health.backend = 'unknown'
        try:
            await self.supervisor.stop()
            held = None if self.hold is None else self.hold(memory=False)
            if held is None:
                self.supervisor.spec = self.child_spec(state, self.store.directory, port=self.port)
                if asked and self.hold is not None and self.supervisor.spec is not None:
                    held = self.hold(memory=True)
            if held is not None:
                self.supervisor.block(*held)  # HM-09: saved, not started (blocked with its reason)
            else:
                await self.supervisor.start()
                if self.supervisor.spec is None and self.lifecycle.get('log') is not None:
                    # HM-09 (contract 7): which connection fields are missing, by name only.
                    self.lifecycle['log']('unconfigured', 'not started: no connection is saved yet ('
                                          + ', '.join(missing_connection_fields(state))
                                          + '); it starts once one is saved')
        except Exception:
            self.configuration.failed('child_start_failed')
            raise
        if asked and self.monitor_options:
            self.health.reset()  # HM-09 (DQ-25): new credentials, no backoff left

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
    """Every profile of one switched-on add-on (multi-profile plan 3.1, 3.2, 12.2; HM-08 built this skeleton, HM-09 runs
    the children). run_product builds it on the default profile's store (opened after the legacy migration) when
    features.enabled(product); it serves as a ProfileRuntime serves: async with, admin_app and mcp_app for the two
    listeners, mcp_listener_limit for 8081, launch() and monitor().

    open():
    - one SharedAdmin for every profile (one AdminAuthority on the product's verify_admin: one CSRF key, one bound on
      the role queries; one set of 16 management slots; HM-10 adds the shared pipeline);
    - the default profile's runtime on the default store and child port, with the default quota
      (profiles.DEFAULT_PROFILE_QUOTA: 40 child connections, 32 forwarding slots);
    - the index (profiles.read_index; a corrupt one, or one that changes later: every token 503, DQ-12) and the profiles
      directory (scan_profiles; when it cannot be listed: every token 503); the open-file budget (open_file_budget,
      raise_open_file_limit): when the soft limit cannot cover it, no additional profile is served and 8081 keeps 64;
      HM-09: the cgroup memory limit (profiles.memory_limit_mib: capacity, the PaaS formula when there is one);
    - every profile the index lists, in index order: its store opened existing-only (never created), its runtime with
      the additional quota (24 connections, 16 slots) on its index port, its gate; one that cannot be opened is not
      served and is named once in a WARNING (its id's first 8 characters); an orphan directory (not in the index) is
      never opened: its token and child token are read once, for the reply mask only; profiles sharing a token or child
      token are named once (DQ-09: the dispatcher answers 503 for a shared token);
    - the 8081 dispatcher (profile_router.McpDispatcher).
    Every runtime gets the busy answer of its gate (make_apps slot_busy), the add-on's reply mask (reply_secrets) and
    its share of the add-on's request body budget (body_budget: budget, one RequestBudget derived when the manager is
    made, with 1 + the product's additional-profile capacity as the accounts; HM-31).

    HM-09 (plan 5.4; contract 7): every profile's runtime, the default profile's included, gets
    - the PaaS watchdog (lifecycle.WATCHDOG, DQ-20 (b)) and the spawn check (spawn_refusal: an add-on listener port
      or another profile's running child on its port, child_port_conflict; a socket bound there, child_port_in_use),
      its lifecycle events (ChildLog on events: one line per profile and situation a minute) and
      child/restart's blocked_reason (report_blocked);
    - its health monitor's options (DQ-25): its own start point (the default profile at once; the k-th additional
      one HEALTH_INTERVAL x (1 + k / (limit + 1)) after its start), the auth backoff, tolerance 2, own child only;
    - an additional profile only: oom_score_adj 500 and nice +5 (lifecycle.EXTRA_CHILD_RESOURCES) and the hold of
      _hold: a disabled profile (entry.disabled) is never started (blocked; reevaluate() after an index change starts
      it once it is no longer disabled), and a save or the panel's restart checks MemAvailable when no cgroup limit
      decides (contract 5: blocked memory_capacity; the boot and the watchdog never check).
    launch() starts the default profile's child (before the listeners serve, as run_product did). start_all() starts
    the others after it (the default profile's first health check or STAGGER_SECONDS, then at most STAGGER_SLOTS
    starting at once; one that cannot start is marked and frees its place). monitor() is run_product's monitoring
    component: start_all() and every additional profile's monitor beside the default profile's monitor, which alone
    ends it (DQ-21: an additional profile's monitor that stops marks that profile failed, its child stopped, until the
    panel restarts it). stop_all() (the manager's close too) stops every child at once, within HA's 30 s.

    HM-10 (plan 5.3; contract 3): admin_app, 8099, is the management dispatcher (profile_router.AdminDispatcher) with
    the add-on's profile management (admin: profile_admin.ProfileAdmin), which registers and drops profiles at run
    time: add(profile_id, store, ...) and remove(profile_id); an index it wrote (profiles.write_index(expected=
    manager.index)) is adopted with adopt_index(view), then reevaluate(); start_profile(profile_id) starts a profile
    added while the add-on runs; free_port() allocates the port of a new profile; relabel() renames one's echo. Every
    profile's runtime gets its echo (echo(): id, label, is_default; DQ-40 (a) ②), its bootstrap fields and, for an
    additional profile, the default profile's endpoint (DQ-13); get(profile_id).runtime.admin_action is each
    profile's action.

    HM-30 (plan 5.5): reply_worker is the add-on's one reply worker (run_product starts and stops it); every runtime
    gets its own turn on it (reply_worker.lane(profile_id)), the default profile's included. Left out (tests that
    build a manager alone), every profile's replies are processed on the event loop.

    HM-27 (plan 8.7, 12.3 HM-27; DQ-11 (a)): origin is the add-on's one Origin policy of the secret path
    (origin_policy.OriginPolicy on the default profile's store directory), made at open() unless the product keeps its
    own rule (app_options secret_path_allowed_origins: Headscale; then None). Every profile's runtime gets its check
    (origin.guard(profile_id)); profile_admin serves the policy's route. open() reads the file once, so that one that
    cannot be used is named in a WARNING before anything is served; nothing is written."""

    def __init__(self, store, product, tools, child_spec, *, port=CHILD_PORT, app_options=None, reply_worker=None,
                 restore_notice=None):
        self.store, self.product, self.tools, self.child_spec = store, product, tools, child_spec
        self.port = port
        self.reply_worker = reply_worker
        # HM-13c: the default profile's restore notice (restore_lock.Notice, or None) and the digests of tokens a
        # "revoke all" could not revoke (8081 refuses them: profile_router.McpDispatcher.resolve).
        self.restore_notice = restore_notice
        self.revoke_fence = set()
        self.app_options = dict(app_options or {})
        self.layout = profiles.Layout(Path(store.directory))
        self.reports = Reports()
        # HM-31: the add-on's request body budget, every profile's share of it (derived now: at startup)
        self.odoo_memory_enabled = True
        initial_limits = None
        if product == 'odoo':
            ceiling, source = request_budget.memory_ceiling()
            accounts, _ = request_budget.runtime_inputs(product, switched_on=True,
                                                         memory_limit=ceiling if source == 'cgroup' else None)
            self.odoo_memory_enabled = request_budget.odoo_switched_memory_fits(ceiling, accounts, source)
            if self.odoo_memory_enabled:
                initial_limits = request_budget.odoo_switched_limits(ceiling, accounts, source)
        self.budget = request_budget.RequestBudget(initial_limits or request_budget.BudgetLimits.derive(
            product, switched_on=self.odoo_memory_enabled))
        self.reply_memory = ReplyMemory() if product == 'odoo' and self.odoo_memory_enabled else None
        if not self.odoo_memory_enabled:
            self.reply_worker = None  # default profile keeps its prior reply path
        self.shared = self.index = self.mcp_app = None
        self.mcp_listener_limit = 64
        self.orphan_secrets = frozenset()
        self.unusable = False  # the profiles directory could not be listed at startup
        # HM-10: whether the open file limit holds additional profiles (raise_open_file_limit at open): when it does not,
        # none is served and none can be created (409 profile_limit_reached, limit 0).
        self.files_for_extras = False
        self.events = LifecycleLog()  # HM-09: the children's lifecycle events, every profile's
        self.admin = self.dispatcher = None  # HM-10: the profile management and the 8099 dispatcher (open())
        self.origin = None  # HM-27: the add-on's Origin policy of the secret path (open(); None for Headscale)
        self._labels = {DEFAULT_PROFILE: profiles.DEFAULT_LABEL}  # HM-10: every echo's label (kept after removal)
        self.memory_limit = None  # HM-09: the cgroup memory limit read at open (None: none, MemAvailable decides)
        self.capacity = profiles.capacity(product)
        self.started = asyncio.Event()  # HM-09: start_all() finished
        self._entries = {}
        self._logs = {}
        self._launched = set()
        self._monitors = {}
        self._serving = False
        self._stack = None
        self._index_reported = False

    # ---- what the listeners and run_product use ----

    @property
    def admin_app(self):
        """8099: the management dispatcher (HM-10; before it, the default profile's management app)."""
        return self.dispatcher

    def echo(self, profile_id):
        """A profile's echo (make_apps profile_view; contract 3.4): its id, its label now, whether it is the default."""
        return {'id': profile_id, 'label': self._labels[profile_id], 'is_default': profile_id == DEFAULT_PROFILE}

    def relabel(self, profile_id, label):
        """HM-10: a rename the index committed; the profile's echo shows it from now on."""
        self._labels[profile_id] = label
        entry = self.get(profile_id)
        if entry is not None:
            entry.label = label

    def default_endpoint(self):
        """The add-on's one endpoint (DQ-13): the default profile's, read from its state when asked."""
        return self.store.load().endpoint

    def profiles(self):
        """The registered profiles: the default profile first, then the index's order."""
        return tuple(self._entries.values())

    def get(self, profile_id):
        return self._entries.get(profile_id)

    async def launch(self):
        """The default profile's child, as run_product started it before the listeners serve (start_all: the others)."""
        self._launched.add(DEFAULT_PROFILE)
        await self.get(DEFAULT_PROFILE).runtime.launch()

    async def start_all(self):
        """Every registered profile's child not started yet (plan 5.4; C2-SF-4): the default profile's first (unless
        launch() did), then, once it answered a health check or STAGGER_SECONDS went by, the additional ones in index
        order, at most STAGGER_SLOTS starting at once; a place is freed when its child answered a health check, is not
        starting any more (blocked, unconfigured, a failed spec: marked, never in the others' way) or after
        STAGGER_SECONDS. Sets started when done. A profile whose start or wait fails (HM-09 review S-12: no such path
        is known) is named in one line and frees its place; the others start anyway."""
        default = self.get(DEFAULT_PROFILE)
        if DEFAULT_PROFILE not in self._launched:
            await self.launch()
        try:
            await self._started(default)
        except Exception as error:
            self._start_failed(default, error)
        slots = asyncio.Semaphore(STAGGER_SLOTS)
        tasks = []

        async def one(entry):
            try:
                await entry.runtime.launch()
                await self._started(entry)
            except Exception as error:
                self._start_failed(entry, error)
            finally:
                slots.release()
            if self._serving and self._entries.get(entry.profile_id) is entry:
                self._watch(entry)
        try:
            for entry in self.profiles():
                if entry.profile_id in self._launched:
                    continue
                await slots.acquire()
                if self._entries.get(entry.profile_id) is not entry:
                    slots.release()  # removed meanwhile
                    continue
                self._launched.add(entry.profile_id)
                tasks.append(asyncio.create_task(one(entry)))
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        self.started.set()

    def _start_failed(self, entry, error):
        """One line for a profile whose staggered start failed (its exception's class only); start_all goes on."""
        log = self._logs.get(entry.profile_id)
        if log is not None:
            log('start failed', f'its staggered start failed ({type(error).__name__}); the other profiles start anyway')

    async def _started(self, entry):
        """Until entry's child answered a health check (availability ready), it is not starting or running any more,
        or STAGGER_SECONDS went by. Checks while it waits (a child not listening yet is a refused connection: the
        backend sees nothing until the child answers); a child that already answered is not checked again, and a check
        its monitor is running is waited for (HealthMonitor.settle)."""
        runtime = entry.runtime
        loop = asyncio.get_running_loop()
        deadline = loop.time() + STAGGER_SECONDS
        while True:
            if runtime.health.availability()['ready'] or runtime.supervisor.status not in CHILD_UP:
                return
            left = deadline - loop.time()
            if left <= 0:
                return
            if runtime.supervisor.status == 'starting':
                # Not spawned yet (the Supervisor's task runs next): look again in a moment, nothing to check yet.
                await asyncio.sleep(min(SPAWN_POLL_SECONDS, left))
                continue
            try:
                async with asyncio.timeout(left):
                    await runtime.health.settle()  # never a second probe right after a check running now
            except TimeoutError:
                return
            if runtime.health.availability()['ready'] or runtime.supervisor.status not in CHILD_UP:
                return
            await asyncio.sleep(max(0, min(STAGGER_POLL_SECONDS, deadline - loop.time())))

    async def start_profile(self, profile_id):
        """HM-10: start a profile added while the add-on runs (a creation: the memory check applies) and its monitor."""
        entry = self.get(profile_id)
        self._launched.add(profile_id)
        await entry.runtime.backend_changed(entry.runtime.store.load())
        if self._serving:
            self._watch(entry)

    def monitor(self):
        """run_product's monitoring component (see the class docstring): ends only when the default profile's monitor
        does (DQ-21), with its error."""
        return self._monitor()

    async def _monitor(self):
        self._serving = True
        starting = None
        try:
            for entry in self.profiles():
                if entry.profile_id != DEFAULT_PROFILE and entry.profile_id in self._launched:
                    self._watch(entry)
            starting = asyncio.create_task(self.start_all())
            await self.get(DEFAULT_PROFILE).runtime.monitor()
        finally:
            self._serving = False
            if starting is not None:
                starting.cancel()
                await asyncio.gather(starting, return_exceptions=True)
            await self._stop_monitors()

    def _watch(self, entry):
        task = self._monitors.get(entry.profile_id)
        if task is None or task.done():
            self._monitors[entry.profile_id] = asyncio.create_task(self._watched(entry))

    async def _watched(self, entry):
        """An additional profile's monitor (DQ-21): when it ends, only this profile is marked failed (its child
        stopped, one WARNING); it runs again once the profile's child is started again (a save, the panel's restart)."""
        runtime = entry.runtime
        while True:
            try:
                await runtime.monitor()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            self._logs[entry.profile_id]('monitor stopped', 'its health monitor stopped; the profile is marked failed '
                                                            'and its child stopped until it is saved or restarted')
            try:
                await runtime.supervisor.give_up()
            except Exception:
                runtime.supervisor.status = 'failed'
            while runtime.supervisor.status == 'failed':
                await asyncio.sleep(REVIVE_POLL_SECONDS)

    async def _stop_monitors(self):
        tasks, self._monitors = list(self._monitors.values()), {}
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_all(self):
        """Every child stopped at once (plan 5.4; contract 7: HA gives an add-on 30 s; one child takes at most its grace
        3 s, 4 s more after SIGKILL and 1 s for its output). The additional profiles' monitors stop first. A stop that
        fails is left to the runtime's close, which tries again."""
        await self._stop_monitors()
        supervisors = [entry.runtime.supervisor for entry in self._entries.values()
                       if entry.runtime.supervisor is not None]
        results = await asyncio.gather(*(supervisor.stop() for supervisor in supervisors), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException) and not isinstance(result, Exception):
                raise result

    # ---- the spawn check and what holds a start (HM-09) ----

    def spawn_refusal(self, profile_id):
        """Why profile_id's child must not start on its port now (plan 5.4; PaaS process._port_refusal and
        ProfileRegistry.port_conflict): an add-on listener's port (8081, 8099: HM-07 review MF-1) or another profile's
        child running on it is child_port_conflict; a socket bound there (profiles.port_occupied) is
        child_port_in_use. None: it may start. The index's own conflicts (a duplicate, the default child's 3000) never
        get here: those profiles are disabled (_hold)."""
        entry = self._entries.get(profile_id)
        if entry is None:
            return CHILD_PORT_CONFLICT, 'the profile is no longer registered'
        port = entry.port
        if port in profiles.LISTENER_PORTS:
            return CHILD_PORT_CONFLICT, 'an add-on listener uses this port'
        for other in self._entries.values():
            supervisor = other.runtime.supervisor
            if other is not entry and other.port == port and supervisor is not None and supervisor.process is not None:
                return CHILD_PORT_CONFLICT, f'the child of profile {profiles.log_id(other.profile_id)} runs on this port'
        occupied = profiles.port_occupied(port)
        if occupied is not None:
            return CHILD_PORT_IN_USE, 'another socket is bound to this port: ' + occupied
        return None

    def _hold(self, profile_id, *, memory):
        """An additional profile's start hold (ProfileRuntime hold): its disabled reason (never started), and for a
        save or the panel's restart (memory) the memory check of contract 5 when no cgroup limit decides."""
        entry = self._entries.get(profile_id)
        if entry is None:
            return None
        if entry.disabled:
            reason = entry.disabled.get('disabled_reason')
            return DISABLED_HOLDS.get(reason, (None, f'the profile is disabled ({reason})'))
        if memory and self.memory_limit is None:
            child = profiles.CHILD_MEMORY_MIB.get(self.product)
            if child is None:
                return None
            needed = child + profiles.PROFILE_MEMORY_RESERVE_MIB
            available = profiles.available_memory_mib()
            if available is None:
                self._logs[profile_id]('memory', 'MemAvailable cannot be read; the child starts without the memory '
                                                 'check')
                return None
            if available < needed:
                return MEMORY_CAPACITY, f'{available} MiB of memory available, {needed} MiB needed'
        return None

    async def reevaluate(self):
        """After the index changed (HM-10 adopted the index it wrote: a profile created or deleted): every additional
        profile's disabled reason again (FM-40; PaaS B-17 needed a restart): one no longer disabled starts at once,
        one newly disabled stops; a profile the spawn check holds back (blocked, waiting out its backoff) is checked
        again at once."""
        listed = [item for item in (self.index.entries if self.index is not None and self.index.serves_mcp else ())
                  if item.id in self._entries]
        reasons = profiles.disabled_reasons(listed, self.capacity)
        for entry in self.profiles():
            if entry.profile_id == DEFAULT_PROFILE:
                continue
            before, entry.disabled = entry.disabled, reasons.get(entry.profile_id)
            supervisor = entry.runtime.supervisor
            if before != entry.disabled:
                self._launched.add(entry.profile_id)
                await entry.runtime.launch()
                if self._serving:
                    self._watch(entry)
            elif supervisor is not None and supervisor.status == 'blocked' and supervisor.task is not None:
                supervisor.retry_now()

    def free_port(self):
        """The port for a new additional profile (HM-10; None: 409 profile_port_unavailable): the first of 18000-18099
        that is not 3000, 8081 or 8099, the default child's, an indexed or a registered profile's, and that no socket
        holds (profiles.port_occupied, plan 5.4)."""
        taken = {self.port, *(entry.port for entry in self._entries.values())}
        if self.index is not None:
            taken.update(item.port for item in self.index.entries)
        return profiles.allocate_port(taken, occupied=profiles.port_occupied)

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

    def _first_check(self, position):
        """A profile's monitor start point (DQ-25): the default profile at once (as before), the position-th additional
        one an interval plus its share of it after its child started (the readiness check of start_all comes first)."""
        if position == 0:
            return 0
        interval = health_module.HEALTH_INTERVAL
        return interval + interval * position / (self.capacity.policy_limit + 1)

    async def add(self, profile_id, store, *, port, label=None, disabled=None):
        """Open profile_id's runtime on its open store and register it (routed from now on). The default profile with
        the default quota, any other with the additional one. The caller keeps the store until it is registered; from
        then on an additional profile's store is the manager's to close."""
        if profile_id in self._entries:
            raise ValueError('profile already registered')
        default = profile_id == DEFAULT_PROFILE
        quota = profiles.DEFAULT_PROFILE_QUOTA if default else profiles.EXTRA_PROFILE_QUOTA
        gate = ProfileGate(profile_id, quota, self.budget, self.reports, self.reply_memory)
        credentials = Credentials(store, owned=not default)
        log = ChildLog(self.events, profile_id, profiles.log_id(profile_id), port)
        lifecycle = dict(WATCHDOG, preflight=partial(self.spawn_refusal, profile_id), log=log)
        if not default:
            lifecycle['resources'] = EXTRA_CHILD_RESOURCES
        monitor = dict(first_check_after=self._first_check(len(self._entries)), tolerance=2, auth_backoff=AUTH_BACKOFF,
                       own_child_only=True, log=log)
        if not default:
            self._labels[profile_id] = label  # HM-10: the echo's label (the index's)
        runtime = ProfileRuntime(store, self.tools, self.child_spec, port=port, profile_id=profile_id,
                                 shared=self.shared, app_options=self.app_options,
                                 child_connections=quota.child_connections, forward_slots=quota.forward_slots,
                                 slot_busy=gate.slot_busy, reply_secrets=self.reply_secrets, lifecycle=lifecycle,
                                 hold=None if default else partial(self._hold, profile_id), monitor_options=monitor,
                                 report_blocked=True, listener_identity=True, profile_view=partial(self.echo, profile_id),
                                 bootstrap_fields=partial(self.admin.bootstrap_fields, profile_id),
                                 default_endpoint=None if default else self.default_endpoint,
                                 body_budget=gate.budget_share,
                                 reply_worker=None if self.reply_worker is None else self.reply_worker.lane(profile_id),
                                 restore_notice=self.restore_notice if default else None,
                                 review_required=partial(self.admin.review_required, profile_id),
                                 origin_policy=None if self.origin is None else self.origin.guard(profile_id))
        await runtime.open()
        entry = RegisteredProfile(profile_id, port, label, runtime, store, gate, credentials, disabled)
        self._entries[profile_id] = entry
        self._logs[profile_id] = log
        return entry

    async def remove(self, profile_id):
        """Drop an additional profile: no longer routed, its monitor stopped, its runtime closed (its client, then its
        child), its store closed. HM-10's deletion revokes the token and commits the index first."""
        if profile_id == DEFAULT_PROFILE:
            raise ValueError('the default profile stays')
        entry = self._entries.pop(profile_id)
        self._launched.discard(profile_id)
        monitor = self._monitors.pop(profile_id, None)
        if monitor is not None:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
        try:
            await entry.runtime.aclose()
        finally:
            entry.store.close()
            self._logs.pop(profile_id, None)
            self.events.forget(profile_id)

    def adopt_index(self, view):
        """HM-10: the index this process wrote last (profiles.write_index's view) is the one to compare with; then
        reevaluate()."""
        self.index = view

    # ---- open and close ----

    async def open(self):
        if self._stack is not None:
            raise RuntimeError('profile manager already open')
        self._stack = AsyncExitStack()
        try:
            if self.product == 'odoo':
                # Recheck before wiring the default app to a budget: readings may change since construction.
                ceiling, source = request_budget.memory_ceiling()
                accounts, _ = request_budget.runtime_inputs(self.product, switched_on=True,
                                                             memory_limit=ceiling if source == 'cgroup' else None)
                if self.odoo_memory_enabled and request_budget.odoo_switched_memory_fits(ceiling, accounts, source):
                    self.budget = request_budget.RequestBudget(
                        request_budget.odoo_switched_limits(ceiling, accounts, source))
                else:
                    self.odoo_memory_enabled = False
                    self.budget = request_budget.RequestBudget(request_budget.BudgetLimits.derive(
                        self.product, switched_on=False))
                    self.reply_memory = self.reply_worker = None
                self.memory_limit = ceiling if source == 'cgroup' else None
            self.shared = SharedAdmin(AdminAuthority(self.app_options.get('verify_admin')))
            if origin_policy.applies(self.app_options):
                # HM-27: one policy for every profile; read once now (an unusable file: its WARNING), never written here
                self.origin = origin_policy.OriginPolicy(self.layout.root)
                self.origin.file.read()
            # HM-10: the profile management and 8099's dispatcher (the second role check is the shared authority's).
            self.admin = ProfileAdmin(self, self.shared.authority.verify)
            self.dispatcher = AdminDispatcher(self, self.admin)
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
            served = self.files_for_extras = raise_open_file_limit(needed, target)
            if served:
                self.mcp_listener_limit = profiles.mcp_listener_limit(self.product)
            if self.product != 'odoo':
                self.memory_limit = profiles.memory_limit_mib()
            self.capacity = profiles.capacity(self.product, self.memory_limit)
            if self.product == 'odoo' and not self.odoo_memory_enabled:
                # Keep the manager's authenticated capacity-denial route and dormant tokens, but start no extra child.
                self.capacity = profiles.ProfileCapacity(self.capacity.policy_limit, self.memory_limit, 100, 0)
                self.mcp_listener_limit = 64
            listed = (self.index.entries if served and not self.unusable and profiles.supports_profiles(self.product)
                      else ())
            await self._open_listed(listed, scan)
        except BaseException:
            await self.aclose()
            raise
        return self

    async def _open_listed(self, listed, scan):
        reasons = profiles.disabled_reasons(listed, self.capacity)
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
        """Close every runtime: every child stopped at once first (stop_all), then the additional profiles' runtimes
        and stores and the default profile's runtime (each its client, then its child); the default profile's store
        stays run_product's."""
        stack, self._stack = self._stack, None
        if stack is not None:
            try:
                await self.stop_all()
            finally:
                await stack.aclose()
        self._entries.clear()

    async def __aenter__(self):
        return await self.open()

    async def __aexit__(self, *exc_info):
        await self.aclose()


def missing_connection_fields(state):
    """The names of the connection fields a product state without a connection lacks (its required fields; n8n:
    backend_url and backend_key), never a value."""
    model = CONNECTIONS.get(getattr(state, 'product', 'n8n'))
    if model is None:
        return ('backend_url', 'backend_key')
    return tuple(name for name, field_info in model.model_fields.items() if field_info.is_required())


def profiles_store(directory, product):
    """An additional profile's store, opened existing-only (HM-07: never created, owner checked)."""
    return ProductStore(directory, product, existing_only=True)
