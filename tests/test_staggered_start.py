"""HM-09: the start after a boot or a cold backup (multi-profile plan 5.4; contract 7; C2-SF-4; §8.8 #53; T-14; FM-46,
133).

- The default profile's child first (run_product: launch(), before the listeners serve, as today); once it passed its
  health check (its child answered) or 30 s went by (STAGGER_SECONDS), the additional profiles in index order, at most
  two starting at once: the next one starts when one of the two passed its health check or after its 30 s. A profile that cannot start (its spec fails, it is
  blocked, its child exits) is marked and frees its place at once: it never holds up the others.
- A disabled profile (profile_limit, memory_capacity, port_conflict) is not started at all.
- The listeners serve the default profile while the others are still starting.
"""
import asyncio
import json
import time

import pytest

from lifecycle_runtime import manager_rig, until, watch
from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import profile_runtime
from multi_profile_runtime import Children, multi_profile_runtime, stored
from test_single_profile_golden import ACCEPT, MockChild, configure, initialize_message, settle

pytestmark = pytest.mark.usefixtures('log_scan')


def test_the_stagger_is_the_planned_one():
    assert (profile_runtime.STAGGER_SLOTS, profile_runtime.STAGGER_SECONDS) == (2, 30)


async def test_the_default_starts_first_then_at_most_two_others_at_once(tmp_path, log_scan):
    """Five additional profiles whose children answer only when the test lets them: B and C start right after the
    default profile; D waits until C answered its first health check, E until B did, F until D did."""
    async with manager_rig(tmp_path, extras=5, answering=False) as rig:
        watch(log_scan, rig)
        b, c, d, e, f = rig.extras
        rig.answer('default')
        await rig.manager.launch()
        assert rig.sleepers.ports() == [rig.default_port]
        starting = asyncio.create_task(rig.manager.start_all())
        try:
            def started():
                return [p for p in rig.extras if rig.supervisor(p).starts]
            await until(lambda: started() == [b, c])
            await asyncio.sleep(0.5)
            assert started() == [b, c]
            rig.answer(c)
            await until(lambda: started() == [b, c, d])
            await asyncio.sleep(0.3)
            assert started() == [b, c, d]
            rig.answer(b)
            await until(lambda: started() == [b, c, d, e])
            rig.answer(d)
            await until(lambda: started() == [b, c, d, e, f])
            rig.answer(e)
            rig.answer(f)
            async with asyncio.timeout(10):
                await starting
        finally:
            starting.cancel()
            await asyncio.gather(starting, return_exceptions=True)
        assert rig.sleepers.ports() == [rig.ports[p] for p in ['default', b, c, d, e, f]]
        assert all(rig.health(p).availability()['ready'] for p in rig.ports)


async def test_start_all_never_checks_a_child_that_already_answered(tmp_path, log_scan):
    """The default profile's child answered its monitor's check already: start_all asks nothing more of it before it
    starts the others (each check of a configured child is a login at the backend; DQ-25, C-tracer 4.4)."""
    async with manager_rig(tmp_path, extras=1) as rig:
        watch(log_scan, rig)
        await rig.manager.launch()
        await until(lambda: rig.supervisor('default').status == 'running')
        await rig.health('default').check()
        assert rig.health('default').availability()['ready'] is True
        child = rig.children.by_port[rig.default_port]
        before = len(child.requests)
        await rig.manager.start_all()
        assert len(child.requests) == before and rig.supervisor(rig.extras[0]).starts == 1


async def test_start_all_waits_for_a_check_running_now_instead_of_probing_again(tmp_path, log_scan):
    """The default profile's monitor is checking right now (its child has not answered yet): start_all waits for that
    check and takes its outcome; it does not send a second initialize (and login) right after it."""
    async with manager_rig(tmp_path, extras=1, answering=False) as rig:
        watch(log_scan, rig)
        original = rig.answer('default')
        rig.answer(rig.extras[0])
        gate, seen = asyncio.Event(), []

        async def gated(request):
            seen.append(request)
            await gate.wait()
            return await original(request)
        rig.children.by_port[rig.default_port] = gated
        await rig.manager.launch()
        await until(lambda: rig.supervisor('default').status == 'running')
        running = asyncio.create_task(rig.health('default').check())
        await until(lambda: len(seen) == 1)
        starting = asyncio.create_task(rig.manager.start_all())
        await asyncio.sleep(0.1)
        assert not starting.done() and rig.supervisor(rig.extras[0]).starts == 0
        gate.set()
        await running
        async with asyncio.timeout(10):
            await starting
        initializes = [request for request in seen if request.content
                       and json.loads(request.content).get('method') == 'initialize']
        assert len(initializes) == 1 and rig.supervisor(rig.extras[0]).starts == 1


async def test_a_child_that_never_answers_frees_its_place_after_30_seconds(tmp_path, log_scan, monkeypatch):
    """STAGGER_SECONDS (30 s; 0.5 s here): nobody answers, so every place is freed by the timeout: B and C at once, D
    and E one timeout later, F one more."""
    monkeypatch.setattr(profile_runtime, 'STAGGER_SECONDS', 0.5)
    async with manager_rig(tmp_path, extras=5, answering=False) as rig:
        watch(log_scan, rig)
        rig.answer('default')
        await rig.manager.launch()
        began = time.monotonic()
        moments = {}
        starting = asyncio.create_task(rig.manager.start_all())

        def note():
            for profile_id in rig.extras:
                if rig.supervisor(profile_id).starts and profile_id not in moments:
                    moments[profile_id] = time.monotonic() - began
            return len(moments) == 5
        await until(note, timeout=10)
        async with asyncio.timeout(10):
            await starting
        b, c, d, e, f = (moments[p] for p in rig.extras)
        assert max(b, c) < 0.4 and min(d, e) - max(b, c) >= 0.45 and f - max(d, e) >= 0.45, moments
        assert f < 5, moments


async def test_a_profile_that_cannot_start_never_holds_up_the_others(tmp_path, log_scan, monkeypatch):
    """C's child spec fails (the start is marked: configuration child_start_failed) and D's child is refused by the
    spawn check: neither keeps its place, so E starts without waiting for anybody."""
    monkeypatch.setattr(profile_runtime, 'STAGGER_SECONDS', 30)
    from multi_profile_runtime import free_port
    # D's index port is an add-on listener's: the spawn check refuses it (child_port_conflict).
    async with manager_rig(tmp_path, extras=4, answering=False,
                           ports=[free_port(), free_port(), 8081, free_port()]) as rig:
        watch(log_scan, rig)
        b, c, d, e = rig.extras
        rig.answer('default')
        rig.sleepers.refuse.add(rig.ports[c])
        await rig.manager.launch()
        starting = asyncio.create_task(rig.manager.start_all())
        try:
            await until(lambda: rig.supervisor(e).starts == 1, timeout=5)
            assert rig.supervisor(b).starts == 1 and rig.supervisor(c).starts == 0
            assert rig.supervisor(d).status == 'blocked' and rig.supervisor(d).blocked_reason == 'child_port_conflict'
            async with rig.admin(c) as admin:
                configuration = (await admin.get('/api/configuration', headers={'X-Remote-User-Id': 'golden-admin'}))
            assert configuration.json()['configuration']['last_error_code'] == 'child_start_failed'
            rig.answer(b)
            rig.answer(e)
            async with asyncio.timeout(10):
                await starting
        finally:
            starting.cancel()
            await asyncio.gather(starting, return_exceptions=True)


async def test_disabled_profiles_are_not_started(tmp_path, log_scan):
    """EMQX allows three additional profiles: the fourth in the index is disabled profile_limit (PaaS order), never
    started (blocked, no reason code: the list's disabled_reason says why); the first three start."""
    async with manager_rig(tmp_path, product='emqx', extras=4) as rig:
        watch(log_scan, rig)
        await rig.manager.launch()
        await rig.manager.start_all()
        *started, last = rig.extras
        assert rig.entry(last).disabled == {'disabled_reason': 'profile_limit'}
        supervisor = rig.supervisor(last)
        assert (supervisor.status, supervisor.blocked_reason, supervisor.starts) == ('blocked', None, 0)
        assert all(rig.supervisor(p).starts == 1 for p in started)
        assert rig.ports[last] not in rig.sleepers.ports()


async def test_the_listeners_serve_the_default_profile_while_the_others_start(tmp_path, log_scan):
    """run_product: the default profile answers through the dispatcher while start_all still waits for additional
    children that do not answer yet (their 30 s are not over)."""
    from multi_profile_runtime import create_profile
    data = tmp_path / 'data'
    configure(data, 'odoo')
    for number, profile_id in enumerate(('b' * 24, 'c' * 24, 'd' * 24)):
        create_profile(data, 'odoo', profile_id, label=f'Stagger {number}', port=18000 + number)
        log_scan.watch(f'Stagger {number}', kind='name')
    children = Children()
    children.add(3000, MockChild('odoo', data))
    async with multi_profile_runtime('odoo', data, children=children, launch_extras=False, stagger=30) as runtime:
        await settle(runtime, 'configured')
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        assert not runtime.manager.started.is_set()
        async with runtime.mcp() as client:
            response = await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer '
                                                          + stored(data)['token']}, json=initialize_message())
        assert response.status_code == 200
        assert not runtime.manager.started.is_set()
