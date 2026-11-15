"""HM-09: every profile's child under the PaaS watchdog once its product is switched on; nothing changes for a product
that is not (multi-profile plan 5.4, 10.3; contract 7; DQ-20 (b), DQ-21; T-13, T-17, T-18; FM-37, 46, 137, 138).

- Not switched on, a child's Supervisor is today's (lifecycle.py before HM-09): at most four starts in one start (about
  1, 2 and 4 s apart), no reset however long a run lasted, then failed; no log line, no spawn check, no wrapper.
- Switched on, every profile's Supervisor, the default profile's included, is the PaaS watchdog (Pc/process.py
  AUTO_RESTART_DELAYS, STABLE_SECONDS @69ac425, unchanged at cf3d0d5): an exit, a spawn failure or a refused start
  backs off 2, 5, 15, 30, 60, 120, 300 s, then 300 s for ever (no attempt limit), and a run of 120 s or more starts
  the table again. One profile's child crashing never touches another's: their PIDs stay (T-13).
- The add-on's stop (HA gives an add-on 30 s; plan 5.4) stops every child at once: six children that all need their
  SIGKILL take about one grace period, not six.
- Lifecycle events (contract 7; C3-SF-3; PaaS _tag): start, exit with its code, the next backoff, failed, blocked with
  its reason code, each as one WARNING `MCP child [profile=<id's first 8> port=<p> pid=<n>]: ...`, at most one line per
  profile and situation a minute (suppressed=N on the next one). Never a token, a URL or a label.
- DQ-21 (2026-11-15 11:2x, the plan's recommendation): an additional profile's monitor that stops marks only that
  profile failed (its child is stopped; the panel's restart revives both); the default profile's monitor stopping ends
  the add-on as before (run_product: "runtime component stopped"; Supervisor restarts the add-on).

Every child is a real process (tests/lifecycle_runtime.Sleepers) on an ephemeral port; every MCP answer comes from a
MockTransport (no socket on 3000 or 18000-18099). The modules under test are imported at collection: the red half of
this file's red-green table is a test that fails, not a file that cannot be collected (the names it needs did not
exist before HM-09, so it fails at its first use of them).
"""
import asyncio
import os
import signal
import sys
import time

import pytest

from lifecycle_runtime import PRODUCT, lifecycle_lines, manager_rig, until, watch
from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import lifecycle, profile_runtime, profiles
from mcp_admin_core.lifecycle import ChildSpec, Supervisor
from multi_profile_runtime import stored
from test_single_profile_golden import (ACCEPT, NoProcessSupervisor, configure, initialize_message, production_runtime,
                                        settle)

pytestmark = pytest.mark.usefixtures('log_scan')
CRASH = 'raise SystemExit(7)'
SLEEP = 'import time\nwhile True:\n    time.sleep(1)\n'
PAAS_DELAYS = (2, 5, 15, 30, 60, 120, 300)


def spec(code, tmp_path):
    return ChildSpec((sys.executable, '-c', code), {'PATH': '/usr/bin:/bin'}, tmp_path)


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


async def next_backoff(supervisor, starts):
    """Skip the current backoff (retry_now) and wait for the next one: (delay, status) once the start after it
    ended again."""
    supervisor.retry_now()
    await until(lambda: supervisor.starts == starts + 1 and supervisor.retry_in is not None)
    return supervisor.retry_in


# ---- not switched on: today's Supervisor ----

async def test_a_switched_off_supervisor_still_fails_after_four_starts(tmp_path):
    """Supervisor(spec) with no option: four starts, then failed; a run that lasted 200 s (its clock) resets nothing
    (plan 5.4: "未開通的產品維持今天的同一次啟動最多 4 次、不歸零、之後 failed")."""
    clock = FakeClock()
    supervisor = Supervisor(spec(CRASH, tmp_path), backoff=0.01, grace=0.05)
    supervisor.clock = lambda: (setattr(clock, 'now', clock.now + 200), clock.now)[1]
    assert (supervisor.retries, supervisor.delays, supervisor.max_attempts) == (3, None, None)
    assert (supervisor.preflight, supervisor.log, supervisor.resources) == (None, None, None)
    await supervisor.start()
    await until(lambda: supervisor.status == 'failed')
    assert supervisor.starts == 4 and supervisor.last_exit == 7 and supervisor.retry_in is None
    await supervisor.stop()
    assert supervisor.status == 'stopped'


@pytest.mark.parametrize('product', ['odoo', 'hermes', 'emqx', 'litellm', 'nextcloud', 'headscale', 'opendesign'])
async def test_switched_off_run_product_gives_the_default_profile_todays_supervisor(tmp_path, log_scan, product):
    """run_product of a product that is not switched on: the default profile's Supervisor gets no option at all (no
    watchdog, no spawn check, no log, no wrapper), as before HM-09."""
    built = []

    class Recorded(NoProcessSupervisor):
        def __init__(self, spec, **options):
            super().__init__(spec, **options)
            built.append((self, options))

    data = tmp_path / 'data'
    configure(data, product)
    async with production_runtime(product, data, supervisor=Recorded) as runtime:
        await settle(runtime, 'configured')
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        (supervisor, options), = built
        assert options == {} and supervisor.delays is None and supervisor.preflight is None
        assert supervisor.log is None and supervisor.resources is None


# ---- switched on: the PaaS watchdog ----

def test_the_watchdog_is_the_paas_one():
    assert lifecycle.AUTO_RESTART_DELAYS == PAAS_DELAYS and lifecycle.STABLE_SECONDS == 120
    assert lifecycle.WATCHDOG == {'delays': PAAS_DELAYS, 'max_attempts': None, 'stable_seconds': 120}


async def test_switched_on_every_profile_gets_the_watchdog_and_the_spawn_check(tmp_path, log_scan):
    async with manager_rig(tmp_path, extras=2) as rig:
        watch(log_scan, rig)
        for entry in rig.manager.profiles():
            supervisor = entry.runtime.supervisor
            assert (supervisor.delays, supervisor.max_attempts, supervisor.stable_seconds) == (PAAS_DELAYS, None, 120)
            assert callable(supervisor.preflight) and supervisor.log is not None
            assert supervisor.log.port == entry.port and supervisor.log.name == profiles.log_id(entry.profile_id)
            # oom_score_adj 500 and nice +5 for an additional profile's child only (plan 5.4; C2-SF-10)
            expected = None if entry.profile_id == 'default' else lifecycle.EXTRA_CHILD_RESOURCES
            assert supervisor.resources == expected
        assert lifecycle.EXTRA_CHILD_RESOURCES == lifecycle.ChildResources(oom_score_adj=500, nice=5)


async def test_the_watchdog_backs_off_through_the_paas_table_and_never_gives_up(tmp_path, log_scan):
    """A child that exits at once, eleven times: 2, 5, 15, 30, 60, 120, 300, then 300 again and again (each wait
    skipped with retry_now; test_a_backoff_waits_its_delay proves the wait); never failed."""
    supervisor = Supervisor(spec(CRASH, tmp_path), grace=0.05, **lifecycle.WATCHDOG)
    await supervisor.start()
    await until(lambda: supervisor.retry_in is not None)
    seen = [supervisor.retry_in]
    assert supervisor.status == 'backoff' and supervisor.last_exit == 7
    for _ in range(9):
        seen.append(await next_backoff(supervisor, supervisor.starts))
        assert supervisor.status == 'backoff'
    assert seen == [2, 5, 15, 30, 60, 120, 300, 300, 300, 300]
    assert supervisor.starts == 10 and supervisor.failures == 10
    await supervisor.stop()
    assert (supervisor.status, supervisor.retry_in, supervisor.process) == ('stopped', None, None)


async def test_a_watchdog_with_an_attempt_limit_fails_after_it(tmp_path):
    supervisor = Supervisor(spec(CRASH, tmp_path), grace=0.05, delays=(0.01,), max_attempts=3)
    await supervisor.start()
    await until(lambda: supervisor.status == 'failed')
    assert supervisor.starts == 3
    await supervisor.stop()


async def test_a_backoff_waits_its_delay(tmp_path):
    supervisor = Supervisor(spec(CRASH, tmp_path), grace=0.05, delays=(0.3,), stable_seconds=120)
    began = time.monotonic()
    await supervisor.start()
    await until(lambda: supervisor.starts == 3, timeout=10)
    assert time.monotonic() - began >= 0.6
    await supervisor.stop()


async def test_a_run_of_120_seconds_starts_the_table_again(tmp_path, log_scan):
    """The watchdog's clock (Supervisor.clock) decides: a run of 119 s is no stable run (the next delay goes on), one of
    120 s is (the next delay is 2 s again; PaaS _schedule_auto_restart)."""
    clock = FakeClock()
    supervisor = Supervisor(spec(SLEEP, tmp_path), grace=0.05, **lifecycle.WATCHDOG)
    supervisor.clock = clock
    await supervisor.start()

    async def crash(ran):
        await until(lambda: supervisor.status == 'running' and supervisor.process is not None)
        starts = supervisor.starts
        clock.now += ran
        os.kill(supervisor.process.pid, signal.SIGKILL)
        await until(lambda: supervisor.retry_in is not None and supervisor.starts == starts)
        assert supervisor.last_exit == -signal.SIGKILL
        delay = supervisor.retry_in
        supervisor.retry_now()
        return delay

    assert [await crash(1) for _ in range(3)] == [2, 5, 15]
    assert await crash(119) == 30
    assert await crash(120) == 2
    assert await crash(0) == 5
    await supervisor.stop()


async def test_a_stop_during_a_backoff_ends_it_at_once(tmp_path):
    supervisor = Supervisor(spec(CRASH, tmp_path), grace=0.05, **lifecycle.WATCHDOG)
    await supervisor.start()
    await until(lambda: supervisor.retry_in == 2)
    began = time.monotonic()
    await supervisor.stop()
    assert time.monotonic() - began < 1 and supervisor.status == 'stopped' and supervisor.task is None


# ---- T-13: one child crashing ----

async def test_one_child_killed_five_times_keeps_restarting_and_the_others_keep_their_pids(tmp_path, log_scan):
    """T-13 (HA expectation: other profiles' PIDs unchanged; the watchdog as PaaS): B's child is SIGKILLed five times;
    each time the watchdog backs off (2, 5, 15, 30, 60; skipped here) and starts it again with a new PID, while the
    default profile and C keep theirs and keep answering; the log names B's exits and backoffs (its id's first 8
    characters, its port and PID), once a minute with the count of what was left out."""
    async with manager_rig(tmp_path, extras=2) as rig:
        watch(log_scan, rig)
        b, c = rig.extras
        await rig.manager.launch()
        await rig.manager.start_all()
        await until(lambda: all(rig.pid(p) for p in ('default', b, c)))
        others = {p: rig.pid(p) for p in ('default', c)}
        events = rig.manager.events
        clock = FakeClock()
        events.clock = clock
        delays, pids = [], []
        for _ in range(5):
            supervisor = rig.supervisor(b)
            pid, starts = rig.pid(b), supervisor.starts
            pids.append(pid)
            os.kill(pid, signal.SIGKILL)
            await until(lambda: supervisor.retry_in is not None and supervisor.starts == starts)
            delays.append(supervisor.retry_in)
            async with rig.mcp() as client:  # the other profiles answer meanwhile (T-13: 0 errors)
                for profile_id in ('default', c):
                    response = await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer '
                                                                  + rig.token(profile_id)}, json=initialize_message())
                    assert response.status_code == 200
            supervisor.retry_now()
            await until(lambda: supervisor.status == 'running' and rig.pid(b) not in (None, pid))
        assert delays == [2, 5, 15, 30, 60]
        assert len(set(pids)) == 5 and {p: rig.pid(p) for p in ('default', c)} == others
        lines = lifecycle_lines(log_scan)
        name, port = profiles.log_id(b), rig.ports[b]
        exits = [line for line in lines if f'[profile={name} port={port} pid={pids[0]}]' in line and 'exited' in line]
        assert exits == [f'MCP child [profile={name} port={port} pid={pids[0]}]: exited with code -9']
        assert [line for line in lines if f'[profile={name} port={port}]' in line and 'next start in' in line] == [
            f'MCP child [profile={name} port={port}]: next start in 2 s (attempt 1)']
        # A minute later the next exit is written, with the four that were left out.
        clock.now += lifecycle.EVENT_SECONDS
        supervisor, pid = rig.supervisor(b), rig.pid(b)
        os.kill(pid, signal.SIGKILL)
        await until(lambda: supervisor.retry_in is not None and rig.pid(b) is None)
        assert f'MCP child [profile={name} port={port} pid={pid}]: exited with code -9 suppressed=4' in (
            lifecycle_lines(log_scan))
        assert not any(rig.token(p) in line for line in lifecycle_lines(log_scan) for p in rig.ports)


async def test_every_lifecycle_event_names_the_profile_port_and_pid(tmp_path, log_scan):
    """The events of contract 7 (start, exit and its code, the next backoff, failed) with the PaaS tag, at most one
    line per profile and situation a minute (EVENT_SECONDS), suppressed=N on the next one; two profiles never share
    a budget."""
    events = lifecycle.LifecycleLog()
    clock = FakeClock()
    events.clock = clock
    a = lifecycle.ChildLog(events, 'a' * 24, 'aaaaaaaa', 18000)
    default = lifecycle.ChildLog(events, 'default', 'default', 3000)
    supervisor = Supervisor(spec(CRASH, tmp_path), grace=0.05, delays=(0.01,), max_attempts=2, log=a)
    await supervisor.start()
    await until(lambda: supervisor.status == 'failed')
    lines = lifecycle_lines(log_scan)
    pid_lines = [line for line in lines if 'started' in line or 'exited' in line]
    assert len(pid_lines) == 2 and pid_lines[0].startswith('MCP child [profile=aaaaaaaa port=18000 pid=')
    assert pid_lines[0].endswith(']: started') and pid_lines[1].endswith(']: exited with code 7')
    assert 'MCP child [profile=aaaaaaaa port=18000]: next start in 0.01 s (attempt 1)' in lines
    assert 'MCP child [profile=aaaaaaaa port=18000]: failed after 2 starts; it starts again when saved or restarted' \
        in lines
    await supervisor.stop()
    for _ in range(3):
        default('blocked', 'not started (child_port_in_use): another socket is bound to this port')
    a('blocked', 'not started (child_port_in_use): another socket is bound to this port')
    clock.now += lifecycle.EVENT_SECONDS
    default('blocked', 'not started (child_port_in_use): another socket is bound to this port')
    lines = lifecycle_lines(log_scan)
    assert [line for line in lines if 'blocked' in line or 'not started' in line] == [
        'MCP child [profile=default port=3000]: not started (child_port_in_use): another socket is bound to this port',
        'MCP child [profile=aaaaaaaa port=18000]: not started (child_port_in_use): another socket is bound to this port',
        'MCP child [profile=default port=3000]: not started (child_port_in_use): another socket is bound to this port'
        ' suppressed=2']


async def test_the_lifecycle_log_keeps_a_bounded_memory():
    events = lifecycle.LifecycleLog()
    for number in range(lifecycle.MAX_EVENT_KEYS + 50):
        events.warn(f'{number:024x}', 'started', 'MCP child: started')
    assert len(events.state) <= lifecycle.MAX_EVENT_KEYS
    events.forget(f'{lifecycle.MAX_EVENT_KEYS + 49:024x}')
    assert all(key[0] != f'{lifecycle.MAX_EVENT_KEYS + 49:024x}' for key in events.state)


# ---- the add-on's stop: every child at once (T-17; FM-46; §8.8 #53) ----

async def test_stop_all_stops_every_child_at_once_within_haos_30_seconds(tmp_path, log_scan):
    """Six children (the default and five additional profiles) that all ignore SIGTERM, so each Supervisor waits its
    grace (3 s) and SIGKILLs: stopped in parallel, about one grace period in all (one after the other: 18 s or more);
    every process and process group gone; the manager's close stops them the same way."""
    async with manager_rig(tmp_path, extras=5) as rig:
        watch(log_scan, rig)
        rig.sleepers.ignore_term.update(rig.ports.values())
        await rig.manager.launch()
        await rig.manager.start_all()
        await until(lambda: all(rig.pid(p) for p in rig.ports))
        pids = [rig.pid(p) for p in rig.ports]
        assert all(rig.supervisor(p).grace == 3.0 for p in rig.ports)
        began = time.monotonic()
        await rig.manager.stop_all()
        took = time.monotonic() - began
        assert 3.0 <= took < 6.0, took
        assert all(rig.supervisor(p).status == 'stopped' and rig.pid(p) is None for p in rig.ports)
        assert not any(os.path.exists(f'/proc/{pid}') for pid in pids)


async def test_closing_the_manager_stops_the_children_in_parallel_too(tmp_path, log_scan):
    began = None
    async with manager_rig(tmp_path, extras=3) as rig:
        watch(log_scan, rig)
        rig.sleepers.ignore_term.update(rig.ports.values())
        await rig.manager.launch()
        await rig.manager.start_all()
        await until(lambda: all(rig.pid(p) for p in rig.ports))
        pids = [rig.pid(p) for p in rig.ports]
        began = time.monotonic()
    took = time.monotonic() - began
    assert took < 6.0, took
    assert not any(os.path.exists(f'/proc/{pid}') for pid in pids)


# ---- DQ-21: a monitor that stops ----

async def test_an_additional_profiles_monitor_stopping_marks_only_that_profile(tmp_path, log_scan):
    """DQ-21: B's health monitor ends with an error: B is marked failed (its child stopped, one WARNING naming B), the
    default profile and C keep their children and monitors, and the add-on's monitoring goes on (monitor() still
    runs). The panel's restart of B (its backend_changed) starts B's child and its monitor again."""
    broken = {'times': 1}

    async with manager_rig(tmp_path, extras=2) as rig:
        watch(log_scan, rig)
        b, c = rig.extras
        health = rig.health(b)
        working = health.run

        async def run():
            if broken['times']:
                broken['times'] -= 1
                raise RuntimeError('monitor broke')
            await working()
        health.run = run
        await rig.manager.launch()
        monitoring = asyncio.create_task(rig.manager.monitor())
        try:
            await until(lambda: rig.supervisor(b).status == 'failed' and rig.pid(b) is None)
            await until(lambda: rig.pid(c) is not None and rig.supervisor(c).status == 'running')
            assert rig.supervisor('default').status == 'running' and not monitoring.done()
            assert any(f'[profile={profiles.log_id(b)} port={rig.ports[b]}]: its health monitor stopped' in line
                       for line in lifecycle_lines(log_scan))
            pids = {p: rig.pid(p) for p in ('default', c)}
            runtime = rig.entry(b).runtime
            await runtime.backend_changed(runtime.store.load())  # the panel's restart
            await until(lambda: rig.supervisor(b).status == 'running' and rig.pid(b) is not None)
            await until(lambda: health.settled is not None and health.settled[1] is True)
            assert {p: rig.pid(p) for p in ('default', c)} == pids and not monitoring.done()
        finally:
            monitoring.cancel()
            await asyncio.gather(monitoring, return_exceptions=True)


async def test_the_default_profiles_monitor_stopping_ends_the_add_ons_monitoring(tmp_path, log_scan):
    """DQ-21: the default profile keeps today's rule. Its monitor ending ends monitor(), which run_product turns into
    "runtime component stopped" (the add-on exits; Supervisor restarts it)."""
    async with manager_rig(tmp_path, extras=1) as rig:
        watch(log_scan, rig)

        async def run():
            raise RuntimeError('monitor broke')
        rig.health('default').run = run
        await rig.manager.launch()
        with pytest.raises(RuntimeError, match='monitor broke'):
            async with asyncio.timeout(10):
                await rig.manager.monitor()


async def test_monitor_starts_the_additional_profiles_behind_the_default_one(tmp_path, log_scan):
    """run_product calls launch() (the default profile's child, before the listeners serve) and monitor(): monitor()
    starts every additional profile's child (start_all, staggered) and every profile's own monitor."""
    async with manager_rig(tmp_path, extras=2) as rig:
        watch(log_scan, rig)
        await rig.manager.launch()
        assert rig.pid('default') is not None or rig.supervisor('default').status in ('starting', 'running')
        assert all(rig.supervisor(p).status == 'stopped' for p in rig.extras)
        monitoring = asyncio.create_task(rig.manager.monitor())
        try:
            await until(lambda: all(rig.pid(p) for p in rig.ports))
            await until(lambda: all(rig.health(p).settled is not None and rig.health(p).settled[1] is True
                                    for p in rig.ports))
        finally:
            monitoring.cancel()
            await asyncio.gather(monitoring, return_exceptions=True)
        assert set(rig.sleepers.ports()) == set(rig.ports.values())


# ---- run_product (switched on) ----

async def test_switched_on_run_product_runs_the_manager_launch_monitor_and_close(tmp_path, log_scan, monkeypatch):
    """run_product with the switch on: launch() before the listeners, monitor() as its monitoring component, and the
    manager's close (stop_all) when the add-on stops; nothing else in run_product changed."""
    from multi_profile_runtime import multi_profile_runtime
    calls = []
    original = {name: getattr(profile_runtime.ProfileManager, name) for name in ('launch', 'monitor', 'stop_all')}

    def recorded(name):
        async def call(self, *args, **kwargs):
            calls.append(name)
            return await original[name](self, *args, **kwargs)
        return call
    for name in original:
        monkeypatch.setattr(profile_runtime.ProfileManager, name, recorded(name))
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    async with multi_profile_runtime(PRODUCT, data) as runtime:
        await settle(runtime, 'configured')
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        assert calls[:2] == ['launch', 'monitor']
    assert calls[-1] == 'stop_all'
