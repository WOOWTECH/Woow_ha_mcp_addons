"""HM-09 test harness: one switched-on product's ProfileManager with the real Supervisor, real child processes and
every profile's MCP answers behind one MockTransport.

- The product's child_spec is replaced by Sleepers: a real Python process per start that sleeps (on a port listed in
  ignore_term it also ignores SIGTERM, so the Supervisor needs its SIGKILL). So the watchdog, the spawn check, the
  process group cleanup and the parallel stop run for real, and a test can SIGKILL a profile's child by its PID.
- What the gateway, the health monitor and the capability probe reach is multi_profile_runtime.Children: a callable
  (test_profile_runtime.ProfileChild) per port of one MockTransport; a port nobody answers is a refused connection.
  No test opens a socket on 3000 or 18000-18099 (tests/owned_network.py): every port here is an ephemeral one that a
  test may bind itself, to occupy it (the spawn check's test bind then fails: child_port_in_use).
- The ProfileManager is built as run_product builds it (the default profile's store, the product's TOOLS and make_apps
  options), opened, and closed again by the rig; the default profile's child port is ephemeral too.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys

import httpx
import pytest

from mcp_admin_core import features, lifecycle, profile_runtime, profiles
from mcp_admin_core.lifecycle import ChildSpec
from mcp_admin_core.products import TOOLS, ProductStore
from multi_profile_runtime import Children, create_profile, free_port, ids, stored
from test_profile_runtime import product_options
from test_single_profile_golden import ADMIN, GENUINE_CLIENT, INGRESS, configure

PRODUCT = 'odoo'


async def until(predicate, timeout=10, step=0.01):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(step)


class Sleepers:
    """child_spec(state, directory, port): a real sleeping Python child per start, recorded as (directory, port).
    ignore_term: ports whose child ignores SIGTERM; refuse: ports whose spec cannot be built (RuntimeError, as a
    product's child_spec raises for a missing environment)."""

    def __init__(self):
        self.calls = []
        self.ignore_term = set()
        self.refuse = set()

    def __call__(self, state, directory, port=lifecycle.CHILD_PORT):
        self.calls.append((Path(directory), port))
        if not state.configured:
            return None
        if port in self.refuse:
            raise RuntimeError('pinned child environment not installed')
        code = ('import signal, time\n'
                + ('signal.signal(signal.SIGTERM, signal.SIG_IGN)\n' if port in self.ignore_term else '')
                + 'while True:\n    time.sleep(1)\n')
        cwd = Path(directory) / 'child'
        cwd.mkdir(mode=0o700, exist_ok=True)
        return ChildSpec((sys.executable, '-c', code), {'PATH': '/usr/bin:/bin'}, cwd)

    def ports(self):
        return [port for _, port in self.calls]


@dataclass
class Rig:
    product: str
    data: Path
    manager: object
    children: Children
    sleepers: Sleepers
    default_port: int
    extras: list
    ports: dict = field(default_factory=dict)  # profile id -> its child port

    def entry(self, profile_id):
        return self.manager.get(profile_id)

    def supervisor(self, profile_id):
        return self.manager.get(profile_id).runtime.supervisor

    def health(self, profile_id):
        return self.manager.get(profile_id).runtime.health

    def pid(self, profile_id):
        process = self.supervisor(profile_id).process
        return None if process is None else process.pid

    def directory(self, profile_id):
        return self.data if profile_id == 'default' else profiles.Layout(self.data).profile(profile_id)

    def token(self, profile_id):
        return stored(self.directory(profile_id))['token']

    def answer(self, profile_id):
        """Let profile_id's child answer MCP on its port from now on (a ProfileChild for its own child bearer)."""
        name = 'default' if profile_id == 'default' else 'p' + profile_id[:4]
        return self.children.profile_child(self.ports[profile_id], name, self.product, self.directory(profile_id))

    def silence(self, profile_id):
        """Nobody answers on profile_id's port from now on (a refused connection, as a child not listening yet)."""
        self.children.by_port.pop(self.ports[profile_id], None)

    def mcp(self):
        return GENUINE_CLIENT(transport=httpx.ASGITransport(app=self.manager.mcp_app), base_url='http://mcp')

    def admin(self, profile_id='default'):
        app = self.manager.get(profile_id).runtime.admin_app
        return GENUINE_CLIENT(transport=httpx.ASGITransport(app=app, client=INGRESS), base_url='http://admin')


async def administrator(user):
    return user == ADMIN['X-Remote-User-Id']


@asynccontextmanager
async def manager_rig(tmp_path, *, product=PRODUCT, extras=2, ports=None, answering=True, configured=True,
                      sleepers=None, before_open=None, default_port=None):
    """A switched-on product's ProfileManager on tmp_path/data: the default profile configured (the golden backend),
    extras additional profiles (ids multi_profile_runtime.ids) on ports (ephemeral ones when left out), each child a
    real sleeper; answering: every profile's ProfileChild answers MCP on its port from the start (False: none does;
    Rig.answer opens one). default_port: the default profile's child port (an ephemeral one when left out).
    before_open(rig) runs before the manager opens (to change what it will read). Nothing is started: the test calls
    launch(), start_all() or monitor()."""
    data = tmp_path / 'data'
    configure(data, product)
    ports = list(ports) if ports is not None else [free_port() for _ in range(extras)]
    extra_ids = ids(len(ports))
    for number, (profile_id, port) in enumerate(zip(extra_ids, ports)):
        create_profile(data, product, profile_id, label=f'Lifecycle {number}', port=port, configured=configured)
    children = Children()
    sleepers = sleepers or Sleepers()
    default_port = free_port() if default_port is None else default_port
    rig_ports = {'default': default_port, **dict(zip(extra_ids, ports))}

    def child_client(*args, **kwargs):
        kwargs.setdefault('transport', httpx.MockTransport(children.route))
        return GENUINE_CLIENT(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset({product}))
        patch.setattr(profile_runtime.httpx, 'AsyncClient', child_client)
        store = ProductStore(data, product)
        try:
            manager = profile_runtime.ProfileManager(store, product, TOOLS[product], sleepers, port=default_port,
                                                     app_options={**product_options(product),
                                                                  'verify_admin': administrator})
            rig = Rig(product, data, manager, children, sleepers, default_port, extra_ids, rig_ports)
            if answering:
                for profile_id in rig_ports:
                    rig.answer(profile_id)
            if before_open is not None:
                before_open(rig)
            async with manager:
                yield rig
        finally:
            store.close()


def lifecycle_lines(log_scan):
    """The lifecycle WARNINGs (lifecycle and health events) the test wrote, as text."""
    return [record.getMessage() for record in log_scan.records
            if record.name in ('mcp_admin_core.lifecycle', 'mcp_admin_core.health') and record.levelname == 'WARNING']


def watch(log_scan, rig):
    """Every token and child token of the rig's profiles, and their labels, for the HM-01 log scan."""
    for profile_id in rig.ports:
        state = stored(rig.directory(profile_id))
        log_scan.watch(*(value for value in (state['token'], state['child_token']) if value))
    for number in range(len(rig.extras)):
        log_scan.watch(f'Lifecycle {number}', kind='name')


def open_fds():
    return len(os.listdir('/proc/self/fd'))


def proc_cmdline(pid):
    return [part.decode() for part in Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[:-1]]


def read_json(path):
    return json.loads(Path(path).read_text())
