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
"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

import httpx

from .access import TokenAccess
from .admin_auth import AdminAuthority
from .configuration import ConfigurationState
from .gateway import ADMIN_SLOTS, PROFILE_ID, AdminPipeline, make_apps, profile_echo
from .health import HealthMonitor
from .lifecycle import CHILD_PORT, Supervisor, child_url

DEFAULT_PROFILE = 'default'
CHILD_CONNECTIONS = 40  # the child client's connection limit, as before (plan 5.2: the default profile keeps 40)
# What the runtime gives make_apps itself; app_options cannot name them.
RUNTIME_OPTIONS = frozenset({'child_url', 'health', 'backend_changed', 'configuration', 'backend_check',
                             'restart_child', 'diagnostics', 'availability', 'token_access', 'mutation_lock',
                             'authority', 'admin_slots', 'admin_pipeline', 'profile_view'})


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
    secret_path_allowed_origins)."""

    def __init__(self, store, tools, child_spec, *, port=CHILD_PORT, profile_id=DEFAULT_PROFILE, lifecycle=None,
                 shared=None, profile_view=None, app_options=None):
        if not isinstance(profile_id, str) or not PROFILE_ID.fullmatch(profile_id):
            raise ValueError('invalid profile id')
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
                limits=httpx.Limits(max_connections=CHILD_CONNECTIONS)))
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
                **self.app_options)
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
