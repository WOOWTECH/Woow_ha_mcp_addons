"""HM-09: child ports and the spawn check (multi-profile plan 5.4, 10.3; contract 3.6, 7, 8; T-15; FM-38, 39, 40, 96;
PaaS child_identity.port_occupied, process._port_refusal, profiles.port_conflict @69ac425, unchanged at cf3d0d5).

- Allocation (HM-10 uses it to create a profile): the first port of 18000-18099 that is not 3000, 8081 or 8099, not an
  indexed port, not a running child's, and that no socket holds (the PaaS test bind of four addresses: 127.0.0.1,
  0.0.0.0, ::1 and :: with SO_REUSEADDR, :: v6only). profiles.allocate_port alone stays pure (HM-07's rule).
- Before every spawn, four kinds of conflict start nothing (status blocked, its reason code; nothing is sent to the
  port either: the health monitor never probes a child that is not running): an add-on listener port (8081, 8099:
  child_port_conflict, HM-07 review MF-1), an index port another profile or the default child holds (the profile is
  disabled port_conflict at open, blocked child_port_conflict, never retried until the index changes), another
  profile's running child on that port (child_port_conflict), and a socket bound there (child_port_in_use).
- T-15 (HA expectation: a conflict stops only the profiles involved; an occupied port backs off with the watchdog and
  recovers once freed): after the eighth backoff (300 s) the port is freed and the child starts; the program that took
  the port of a crashed child gets nothing.
- After an index change (HM-10 writes and adopts the index) the manager re-evaluates at once (reevaluate(): PaaS B-17
  needed a restart): a profile no longer in conflict starts, a newly disabled one stops, a blocked one is retried.
- The spawn check fails closed (one that raises refuses the start), and an IPv6 test bind the platform refuses
  (EACCES, EPERM) is skipped with one WARNING (HM-09 review S-2, S-6).
- child/restart answers with blocked_reason once the product is switched on (PaaS B-22); switched off, its answer is
  today's.
"""
import dataclasses
import errno
import os
import socket
import sys

import pytest

from admin_write_headers import reviewed_headers
from lifecycle_runtime import lifecycle_lines, manager_rig, until, watch
from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import profiles
from multi_profile_runtime import free_port, stored
from test_single_profile_golden import (ACCEPT, ADMIN, configure, initialize_message, production_runtime, settle)

pytestmark = pytest.mark.usefixtures('log_scan')
FOUR = [(socket.AF_INET, '127.0.0.1'), (socket.AF_INET, '0.0.0.0'), (socket.AF_INET6, '::1'), (socket.AF_INET6, '::')]


def hold(family, address, port=0, *, listen=True):
    """A socket that holds a port the way another program would (no SO_REUSEADDR); the caller closes it."""
    holder = socket.socket(family, socket.SOCK_STREAM)
    if family == socket.AF_INET6:
        holder.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    holder.bind((address, port))
    if listen:
        holder.listen()
    found = holder.getsockname()[1]
    assert found != 3000 and found not in range(18000, 18100)
    return holder


class Grabber:
    """What answers on a port when another program took it: every request recorded, every answer a 200."""

    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        import httpx
        return httpx.Response(200, json={'grabbed': True})


async def initialize(rig, profile_id):
    async with rig.mcp() as client:
        return await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer ' + rig.token(profile_id)},
                                 json=initialize_message())


# ---- allocation ----

def test_allocation_skips_reserved_taken_and_occupied_ports():
    assert profiles.allocate_port() == 18000  # pure as HM-07 made it: nothing is bound
    occupied = {18000: 'IPv4 test bind failed (EADDRINUSE)', 18002: 'IPv6 test bind failed (EADDRINUSE)'}
    assert profiles.allocate_port([18001], occupied=occupied.get) == 18003
    assert profiles.allocate_port([3000, 8081, 8099], occupied=occupied.get) == 18001
    assert profiles.allocate_port(range(18000, 18050), occupied=lambda port: 'held' if port < 18099 else None) == 18099
    assert profiles.allocate_port((), occupied=lambda port: 'held') is None


async def test_the_manager_allocates_around_indexed_running_and_occupied_ports(tmp_path, log_scan, monkeypatch):
    """ProfileManager.free_port() (for HM-10): the index's ports, every running child's port and whatever the four-address
    test bind finds held are skipped; 3000, 8081 and 8099 always."""
    tested = []

    def occupied(port):
        tested.append(port)
        return 'IPv4 test bind failed (EADDRINUSE)' if port == 18001 else None
    monkeypatch.setattr(profiles, 'port_occupied', occupied)
    async with manager_rig(tmp_path, extras=1, ports=[18000]) as rig:
        watch(log_scan, rig)
        assert rig.manager.free_port() == 18002
        assert 18000 not in tested and 3000 not in tested


# ---- the test bind (PaaS port_occupied) ----

@pytest.mark.parametrize('listen', [True, False], ids=['listening', 'bound'])
@pytest.mark.parametrize('family,address', FOUR, ids=[address for _, address in FOUR])
def test_a_socket_on_any_of_the_four_addresses_makes_the_port_occupied(family, address, listen):
    holder = hold(family, address, listen=listen)
    port = holder.getsockname()[1]
    try:
        reason = profiles.port_occupied(port)
        assert reason is not None and reason.startswith('IPv6' if family == socket.AF_INET6 else 'IPv4'), reason
        assert reason.endswith('(EADDRINUSE)') and 'test bind failed' in reason
    finally:
        holder.close()
    assert profiles.port_occupied(port) is None


def test_a_free_port_is_not_occupied_and_the_test_bind_leaves_nothing_behind():
    port = free_port()
    assert profiles.port_occupied(port) is None
    assert profiles.port_occupied(port) is None  # the probes are closed: nothing holds the port afterwards
    with socket.socket() as again:
        again.bind(('127.0.0.1', port))


class RefusedSockets:
    """profiles.socket as a platform that refuses some binds (AppArmor or seccomp): refused maps an address family to
    the errno its binds fail with; the other families bind for real (an ephemeral port nobody holds)."""

    def __init__(self, refused):
        self.refused = refused
        for name in ('AF_INET', 'AF_INET6', 'SOCK_STREAM', 'SOL_SOCKET', 'SO_REUSEADDR', 'IPPROTO_IPV6',
                     'IPV6_V6ONLY'):
            setattr(self, name, getattr(socket, name))

    def socket(self, family, kind):
        code = self.refused.get(family)
        if code is None:
            return socket.socket(family, kind)

        class Refused:  # no real socket: the refusal needs no IPv6 on the test machine
            def setsockopt(self, *args):
                pass

            def bind(self, address):
                raise OSError(code, os.strerror(code))

            def close(self):
                pass
        return Refused()


@pytest.mark.parametrize('code', [errno.EACCES, errno.EPERM], ids=['EACCES', 'EPERM'])
def test_an_ipv6_test_bind_the_platform_refuses_is_skipped_with_one_warning(log_scan, monkeypatch, code):
    """HM-09 review S-6 (a platform fact read when it runs; HM-03a tries the four binds on HAOS): IPv6 binds refused
    with EACCES or EPERM say nothing about the port (no program of the add-on can bind IPv6 then; the child binds
    127.0.0.1): skipped, one WARNING per address and errno however often the check runs. Refused on IPv4, the port
    stays occupied (the child could not bind it either)."""
    monkeypatch.setattr(profiles, '_reported_binds', set())
    port = free_port()
    monkeypatch.setattr(profiles, 'socket', RefusedSockets({socket.AF_INET6: code}))
    assert profiles.port_occupied(port) is None
    assert profiles.port_occupied(port) is None
    name = errno.errorcode[code]
    lines = [record.getMessage() for record in log_scan.records if record.name == 'mcp_admin_core.profiles']
    assert lines == [f'multi-profile: the IPv6 test bind on {address} is refused ({name}); the spawn check skips '
                     'that address' for address in ('::1', '::')]
    monkeypatch.setattr(profiles, 'socket', RefusedSockets({socket.AF_INET: code}))
    assert profiles.port_occupied(port) == f'IPv4 test bind failed ({name})'


def test_the_test_bind_never_touches_a_production_child_port_in_these_tests():
    """tests/owned_network.py refuses any bind on 3000 and 18000-18099 in this process: the spawn check of a test
    therefore always runs on an ephemeral port (manager_rig), and a refusal of the guard is not taken for a free port."""
    from batch2_owned_port import OwnershipError
    with pytest.raises(OwnershipError):
        profiles.port_occupied(18000)


# ---- the four kinds of conflict never spawn ----

@pytest.mark.parametrize('listener', sorted(profiles.LISTENER_PORTS))
async def test_a_profile_on_an_add_on_listener_port_is_blocked(tmp_path, log_scan, listener):
    """HM-07 review MF-1: an index port that is 8081 or 8099 is no index conflict (PaaS _port_collisions); the spawn
    check refuses it, child_port_conflict, and the watchdog keeps retrying (PaaS: every refusal is retried) without
    ever spawning or binding it. The other profiles start."""
    async with manager_rig(tmp_path, extras=2, ports=[listener, free_port()]) as rig:
        watch(log_scan, rig)
        b, c = rig.extras
        await rig.manager.launch()
        await rig.manager.start_all()
        supervisor = rig.supervisor(b)
        await until(lambda: supervisor.status == 'blocked' and supervisor.retry_in is not None)
        assert (supervisor.blocked_reason, supervisor.starts, supervisor.process) == ('child_port_conflict', 0, None)
        assert rig.entry(b).disabled is None  # not an index verdict
        supervisor.retry_now()
        await until(lambda: supervisor.retry_in == 5)
        assert supervisor.starts == 0 and supervisor.status == 'blocked'
        await until(lambda: rig.pid('default') is not None and rig.pid(c) is not None)
        assert any(f'[profile={profiles.log_id(b)} port={listener}]: not started (child_port_conflict)' in line
                   for line in lifecycle_lines(log_scan))


async def test_a_spawn_check_that_fails_refuses_the_start(tmp_path, log_scan):
    """HM-09 review S-2 (E3; T-15's "the program that took the port gets nothing"): a spawn check that raises is a
    refusal, never a pass (fail closed): blocked child_port_in_use, nothing spawned, one line naming the error's class
    only, and the watchdog checks again after its backoff (still refused while it keeps failing)."""
    from mcp_admin_core import lifecycle
    from mcp_admin_core.lifecycle import ChildSpec, Supervisor

    def broken():
        raise RuntimeError('the check broke')
    log = lifecycle.ChildLog(lifecycle.LifecycleLog(), 'a' * 24, 'aaaaaaaa', 18000)
    spec = ChildSpec((sys.executable, '-c', 'import time\nwhile True:\n    time.sleep(1)\n'), {'PATH': '/usr/bin:/bin'},
                     tmp_path)
    supervisor = Supervisor(spec, grace=0.05, preflight=broken, log=log, **lifecycle.WATCHDOG)
    await supervisor.start()
    assert (supervisor.status, supervisor.blocked_reason, supervisor.process, supervisor.starts) == (
        'blocked', 'child_port_in_use', None, 0)
    await until(lambda: supervisor.retry_in == 2)
    supervisor.retry_now()
    await until(lambda: supervisor.retry_in == 5)
    assert (supervisor.status, supervisor.blocked_reason, supervisor.starts) == ('blocked', 'child_port_in_use', 0)
    assert ('MCP child [profile=aaaaaaaa port=18000]: not started (child_port_in_use): the port check failed '
            '(RuntimeError)') in lifecycle_lines(log_scan)
    await supervisor.stop()
    assert supervisor.status == 'stopped'


@pytest.mark.parametrize('shared', ['duplicate', 'default child port'])
async def test_an_index_port_conflict_stops_only_the_profiles_holding_it(tmp_path, log_scan, shared):
    """FM-40, T-15 (index cases): two profiles on one index port, or one on the default child's 3000, are disabled
    port_conflict when the manager opens (HM-07 port_conflicts, PaaS _port_collisions): blocked child_port_conflict,
    never spawned and never retried (no test bind either; the index has to change); the others start."""
    port = free_port()
    ports = [port, port, free_port()] if shared == 'duplicate' else [3000, free_port(), free_port()]
    async with manager_rig(tmp_path, extras=3, ports=ports) as rig:
        watch(log_scan, rig)
        held = rig.extras[:2] if shared == 'duplicate' else rig.extras[:1]
        others = [profile_id for profile_id in rig.extras if profile_id not in held]
        await rig.manager.launch()
        await rig.manager.start_all()
        for profile_id in held:
            supervisor = rig.supervisor(profile_id)
            assert rig.entry(profile_id).disabled == {'disabled_reason': 'port_conflict'}
            assert (supervisor.status, supervisor.blocked_reason) == ('blocked', 'child_port_conflict')
            assert supervisor.starts == 0 and supervisor.task is None and supervisor.retry_in is None
        await until(lambda: all(rig.pid(p) is not None for p in ['default', *others]))
        for profile_id in held:  # the panel's restart does not start it either
            runtime = rig.entry(profile_id).runtime
            await runtime.backend_changed(runtime.store.load())
            assert rig.supervisor(profile_id).status == 'blocked' and rig.supervisor(profile_id).starts == 0
            assert rig.supervisor(profile_id).process is None


async def test_a_port_another_profiles_running_child_uses_is_a_conflict(tmp_path, log_scan):
    """The default profile's child runs on the port the index gives B (a hand edit or a restore that the index rules do
    not catch: they know 3000 as the default child's port, and this default child runs elsewhere): B is blocked
    child_port_conflict, the default keeps its port."""
    port = free_port()
    async with manager_rig(tmp_path, extras=1, ports=[port], default_port=port, answering=False) as rig:
        b, = rig.extras
        rig.answer('default')
        assert rig.entry(b).disabled is None  # the index rules do not see it
        watch(log_scan, rig)
        await rig.manager.launch()
        await until(lambda: rig.pid('default') is not None)
        await rig.manager.start_all()
        supervisor = rig.supervisor(b)
        await until(lambda: supervisor.status == 'blocked')
        assert supervisor.blocked_reason == 'child_port_conflict' and supervisor.starts == 0
        assert rig.pid('default') is not None


async def test_an_occupied_port_backs_off_and_recovers_after_the_eighth_backoff(tmp_path, log_scan):
    """T-15 (occupied before the start): B's port is held by another program: blocked child_port_in_use, nothing
    spawned and nothing sent to the holder; the watchdog retries 2, 5, 15, 30, 60, 120, 300, 300 s (waits skipped with
    retry_now), still blocked; the port is freed after the eighth backoff and the next attempt starts B's child, which
    then answers."""
    port = free_port()
    holder = hold(socket.AF_INET, '127.0.0.1', port)
    try:
        async with manager_rig(tmp_path, extras=1, ports=[port]) as rig:
            watch(log_scan, rig)
            b, = rig.extras
            grabber = Grabber()
            rig.children.add(port, grabber)  # whatever answers on the port is the other program
            await rig.manager.launch()
            await rig.manager.start_all()
            supervisor = rig.supervisor(b)
            await until(lambda: supervisor.status == 'blocked' and supervisor.retry_in is not None)
            assert supervisor.blocked_reason == 'child_port_in_use' and supervisor.starts == 0
            delays = [supervisor.retry_in]
            for _ in range(7):
                previous = supervisor.failures
                supervisor.retry_now()
                await until(lambda: supervisor.failures == previous + 1 and supervisor.retry_in is not None)
                delays.append(supervisor.retry_in)
                assert (supervisor.status, supervisor.blocked_reason) == ('blocked', 'child_port_in_use')
            assert delays == [2, 5, 15, 30, 60, 120, 300, 300] and supervisor.starts == 0
            response = await initialize(rig, b)  # the gateway answers itself: nothing is forwarded
            assert response.status_code == 200 and response.headers['mcp-session-id'].startswith('woow-local-')
            await rig.health(b).check()
            assert grabber.requests == []
            holder.close()
            rig.answer(b)
            supervisor.retry_now()
            await until(lambda: supervisor.status == 'running' and rig.pid(b) is not None)
            assert supervisor.blocked_reason is None and supervisor.starts == 1
            await rig.health(b).check()
            assert rig.health(b).availability()['ready'] is True
            assert grabber.requests == []
    finally:
        holder.close()


async def test_a_crashed_childs_port_taken_by_another_program_gets_it_nothing(tmp_path, log_scan):
    """T-15 (a running child crashes and another program takes its port at once): the watchdog's next attempt is refused
    child_port_in_use; meanwhile no MCP request, no health check and no child bearer reaches that program; once it lets
    go, B starts again and answers."""
    async with manager_rig(tmp_path, extras=2) as rig:
        watch(log_scan, rig)
        b, c = rig.extras
        await rig.manager.launch()
        await rig.manager.start_all()
        await until(lambda: rig.pid(b) is not None and rig.pid(c) is not None)
        c_pid, supervisor = rig.pid(c), rig.supervisor(b)
        grabber = Grabber()
        rig.children.add(rig.ports[b], grabber)
        holder = hold(socket.AF_INET, '0.0.0.0', rig.ports[b], listen=False)
        try:
            import os
            import signal
            os.kill(rig.pid(b), signal.SIGKILL)
            await until(lambda: supervisor.retry_in is not None)
            supervisor.retry_now()
            await until(lambda: supervisor.status == 'blocked' and supervisor.retry_in is not None)
            assert supervisor.blocked_reason == 'child_port_in_use'
            response = await initialize(rig, b)
            assert response.status_code == 200 and response.headers['mcp-session-id'].startswith('woow-local-')
            await rig.health(b).check()
            assert grabber.requests == [] and rig.pid(c) == c_pid
        finally:
            holder.close()
        rig.answer(b)
        supervisor.retry_now()
        await until(lambda: supervisor.status == 'running' and rig.pid(b) is not None)
        response = await initialize(rig, b)
        assert response.status_code == 200 and not response.headers['mcp-session-id'].startswith('woow-local-')
        assert grabber.requests == []


# ---- an index change re-evaluates at once (B-17) ----

async def test_deleting_the_other_holder_of_a_port_starts_the_one_left_at_once(tmp_path, log_scan):
    """T-09 / FM-40: B and C share an index port (both disabled port_conflict). HM-10 deletes C (remove, write the index
    without it, adopt it); reevaluate() then starts B right away (no restart, no backoff to wait for)."""
    port = free_port()
    async with manager_rig(tmp_path, extras=2, ports=[port, port]) as rig:
        watch(log_scan, rig)
        b, c = rig.extras
        await rig.manager.launch()
        await rig.manager.start_all()
        assert rig.supervisor(b).blocked_reason == 'child_port_conflict'
        await rig.manager.remove(c)
        layout = profiles.Layout(rig.data)
        kept = [entry for entry in rig.manager.index.entries if entry.id == b]
        rig.manager.adopt_index(profiles.write_index(layout.index, kept, expected=rig.manager.index))
        await rig.manager.reevaluate()
        assert rig.entry(b).disabled is None
        await until(lambda: rig.supervisor(b).status == 'running' and rig.pid(b) is not None)


async def test_reevaluating_stops_a_profile_the_new_index_disables(tmp_path, log_scan):
    """HM-09 review S-4 (HM-10 calls reevaluate() after it adopts the index it wrote): a running profile the new index
    disables stops at once (blocked with its reason, its child reaped), as one no longer disabled starts at once; the
    default profile and the others keep their children. Here the index gives C B's port: both are disabled
    port_conflict."""
    async with manager_rig(tmp_path, extras=3) as rig:
        watch(log_scan, rig)
        b, c, d = rig.extras
        await rig.manager.launch()
        await rig.manager.start_all()
        await until(lambda: all(rig.pid(p) is not None for p in rig.ports))
        pids = {p: rig.pid(p) for p in rig.ports}
        layout = profiles.Layout(rig.data)
        entries = [dataclasses.replace(item, port=rig.ports[b]) if item.id == c else item
                   for item in rig.manager.index.entries]
        rig.manager.adopt_index(profiles.write_index(layout.index, entries, expected=rig.manager.index))
        await rig.manager.reevaluate()
        for profile_id in (b, c):
            supervisor = rig.supervisor(profile_id)
            assert rig.entry(profile_id).disabled == {'disabled_reason': 'port_conflict'}
            assert (supervisor.status, supervisor.blocked_reason, supervisor.process) == (
                'blocked', 'child_port_conflict', None)
            assert not os.path.exists(f'/proc/{pids[profile_id]}')
        assert {p: rig.pid(p) for p in ('default', d)} == {p: pids[p] for p in ('default', d)}


async def test_reevaluating_retries_a_blocked_profile_at_once(tmp_path, log_scan):
    port = free_port()
    holder = hold(socket.AF_INET, '127.0.0.1', port)
    try:
        async with manager_rig(tmp_path, extras=1, ports=[port]) as rig:
            watch(log_scan, rig)
            b, = rig.extras
            await rig.manager.launch()
            await rig.manager.start_all()
            supervisor = rig.supervisor(b)
            await until(lambda: supervisor.status == 'blocked' and supervisor.retry_in == 2)
            holder.close()
            await rig.manager.reevaluate()
            await until(lambda: supervisor.status == 'running', timeout=1.5)  # well before the 2 s backoff ends
    finally:
        holder.close()


# ---- child/restart and its blocked_reason ----

async def test_child_restart_answers_with_the_blocked_reason(tmp_path, log_scan):
    """Switched on, child/restart (202) carries blocked_reason: null when the child started, the reason code when the
    spawn check refused it (PaaS B-22: a refused restart looked like a success)."""
    port = free_port()
    async with manager_rig(tmp_path, extras=1, ports=[port]) as rig:
        watch(log_scan, rig)
        b, = rig.extras
        await rig.manager.launch()
        await rig.manager.start_all()
        await until(lambda: rig.pid(b) is not None)
        for profile_id, expected in (('default', None), (b, None)):
            async with rig.admin(profile_id) as admin:
                boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
                response = await admin.post('/api/child/restart', headers=reviewed_headers(boot, ADMIN))
            assert response.status_code == 202 and response.json()['blocked_reason'] == expected
        holder = hold(socket.AF_INET, '127.0.0.1', port, listen=False)
        try:
            async with rig.admin(b) as admin:
                boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
                response = await admin.post('/api/child/restart', headers=reviewed_headers(boot, ADMIN))
            assert response.status_code == 202 and response.json()['blocked_reason'] == 'child_port_in_use'
            assert response.json()['health']['child']['state'] == 'blocked'
        finally:
            holder.close()


async def test_switched_off_child_restart_answers_as_before(tmp_path, log_scan):
    data = tmp_path / 'data'
    configure(data, 'odoo')
    async with production_runtime('odoo', data) as runtime:
        await settle(runtime, 'configured')
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        async with runtime.admin() as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            response = await admin.post('/api/child/restart', headers=reviewed_headers(boot, ADMIN))
        assert response.status_code == 202
        assert set(response.json()) == {'status', 'child_state', 'apply_state', 'operation', 'configuration',
                                        'accepted', 'health'}


def test_a_refused_test_bind_names_only_the_family_and_errno():
    port = free_port()
    holder = hold(socket.AF_INET, '127.0.0.1', port)
    try:
        assert profiles.port_occupied(port) == f'IPv4 test bind failed ({errno.errorcode[errno.EADDRINUSE]})'
    finally:
        holder.close()
