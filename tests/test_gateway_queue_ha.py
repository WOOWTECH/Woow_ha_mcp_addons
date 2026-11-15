"""HM-14: a switched-on profile's forwarding queue (multi-profile plan 12.3 HM-14, 5.2; contract 2.4, 5; C3-SF-2;
FM-51), against the PaaS #148 gateway (woow-mcp-server 69ac425 gateway_pool.py; its tests
packages/mcp-admin-core/tests/test_gateway_queue.py, with the later timing fixes of 82c6929).

A request whose body is read waits for one of its profile's forwarding slots (gateway.take_slot): at once when one is
free; otherwise, unless its lane's queue is full (32 waiting for the default profile, 16 for an additional one, each lane
counted on its own: refused at once), for at most 1 s while its client is watched. A client that closes its connection
while its request waits is dropped and the request is never forwarded, even when a slot comes free in the same instant
(the slot is given back): without it, a write the client gave up on would run once a slot came free, and again when
the client retries (PaaS Q6: 3/3 written to Odoo). A request that already holds a slot keeps today's meaning: the child
handles it, the gateway does not cancel it. Only a closed connection counts as leaving (the MCP SDK's own timeouts and
cancellations send notifications/cancelled and keep the POST's connection open; contract 2.4, threat-model.md 3).

HA's values differ from the PaaS ones (plan 8.8 #15: 1 s instead of 10, 32/16 queued, 4 reserved) and are program
constants, not environment variables (plan 8.8 #45). The mechanism tests drive gateway.take_slot directly (in process,
an audited semaphore); the end-to-end ones run the switched-on runtime, one of them on a real loopback listener (the
server's own disconnect).
"""
import asyncio
import json
import logging
import random

import httpx
import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import Children, multi_profile_runtime
from mcp_admin_core import gateway, profile_router, profiles
from switched_gateway import (B, PRODUCT, Exchange, GatewayChild, bearer, call, json_body, quota, session_of, setup,
                              until, watch)
from test_single_profile_golden import GENUINE_CLIENT

pytestmark = pytest.mark.usefixtures('log_scan')
ORDINARY, RESERVED = 'ordinary', 'reserved'  # gateway.ORDINARY_LANE, RESERVED_LANE


class AuditedSemaphore(asyncio.Semaphore):
    """An asyncio.Semaphore that counts (PaaS _AuditedSemaphore): held (acquired, not released), over_released
    (released with none held: a slot that grew), pending (acquires still waiting: an orphan waiter after a timeout)."""

    def __init__(self, value):
        super().__init__(value)
        self.held = self.over_released = self.pending = 0

    async def acquire(self):
        self.pending += 1
        try:
            await super().acquire()
        finally:
            self.pending -= 1
        self.held += 1
        return True

    def release(self):
        if self.held == 0:
            self.over_released += 1
        else:
            self.held -= 1
        super().release()


def lane(limit, name=ORDINARY):
    made = gateway.Lane(name, limit)
    made.semaphore = AuditedSemaphore(limit)
    return made


def never():
    return asyncio.Event().wait()


async def settle(rounds=20):
    """Event loop rounds for the callbacks already scheduled (a given-up acquire's hand-back): rounds, not time."""
    for _ in range(rounds):
        await asyncio.sleep(0)


def clean(audit):
    return (audit.held, audit.over_released, audit.pending) == (0, 0, 0) and not audit.locked()


class Forwarder:
    """What serve() does with a lane: take a slot, then 'forward' (record the case) and hold it until released."""

    def __init__(self, lane_, queue=32, wait=30.0):
        self.lane, self.queue, self.wait = lane_, queue, wait
        self.sent = []

    async def __call__(self, case, gone=never):
        outcome = await gateway.take_slot(self.lane, self.queue, self.wait, gone)
        if outcome == 'taken':
            self.sent.append(case)
        return outcome

    def done(self):
        self.lane.semaphore.release()


# ---- the queue mechanism (PaaS test_gateway_queue.py cases 8-11, 13, 15, 18, 20, 23, 24) ----

async def test_queued_request_is_dropped_when_its_client_goes_away_and_is_never_sent():
    forward = Forwarder(lane(1))
    assert await forward('held') == 'taken'
    gone = asyncio.Event()
    queued = asyncio.create_task(forward('doomed', gone.wait))
    await until(lambda: forward.lane.waiting == 1)
    gone.set()
    assert await asyncio.wait_for(queued, 30) == 'abandoned'
    assert forward.lane.waiting == 0 and forward.sent == ['held']
    forward.done()
    await settle()
    assert forward.sent == ['held'], 'a request whose client left is not sent once a slot comes free'
    assert await forward('later') == 'taken' and forward.sent == ['held', 'later']  # its slot was not eaten
    forward.done()
    await settle()
    assert clean(forward.lane.semaphore)


async def test_slot_granted_in_the_same_instant_the_client_leaves_is_given_back_not_used():
    """The slot comes free (the waiter is woken) as its client leaves: not sent, the slot goes back exactly once (an
    anchor keeps another slot held all along, so a slot given back twice would show as over_released)."""
    forward = Forwarder(lane(2), wait=5)
    assert await forward('anchor') == 'taken' and await forward('held') == 'taken'
    gone = asyncio.Event()
    queued = asyncio.create_task(forward('doomed', gone.wait))
    await until(lambda: forward.lane.waiting == 1)
    forward.done()  # 'held' ends: the waiter is woken ...
    gone.set()  # ... as its client leaves
    assert await asyncio.wait_for(queued, 30) == 'abandoned'
    await settle()
    audit = forward.lane.semaphore
    assert forward.sent == ['anchor', 'held'] and forward.lane.waiting == 0
    assert (audit.held, audit.over_released, audit.pending) == (1, 0, 0), 'the slot went back more than once'
    assert await asyncio.wait_for(forward('later'), 30) == 'taken'  # a free slot at once
    forward.done()
    forward.done()
    await settle()
    assert clean(audit)


async def test_cancelling_a_queued_request_returns_nothing_and_leaks_no_slot():
    forward = Forwarder(lane(2), wait=5)
    assert await forward('anchor') == 'taken' and await forward('held') == 'taken'
    for _ in range(3):  # cancelled while it waits, at different moments
        queued = asyncio.create_task(forward('cancelled', asyncio.Event().wait))
        await asyncio.sleep(.02)
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
    assert forward.lane.waiting == 0
    racing = asyncio.create_task(forward('racing', asyncio.Event().wait))
    await asyncio.sleep(.02)
    forward.done()  # the waiter is woken, and cancelled in the same instant: its slot goes back
    racing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await racing
    await settle()
    audit = forward.lane.semaphore
    assert (audit.held, audit.over_released, audit.pending) == (1, 0, 0)
    assert await asyncio.wait_for(forward('later'), 30) == 'taken'
    forward.done()
    forward.done()
    await settle()
    assert clean(audit) and forward.sent == ['anchor', 'held', 'later']


async def test_a_broken_disconnect_watcher_does_not_look_like_a_disconnect():
    """A watcher that fails (its receive raised) is no client gone and ends no wait early: the slot decides."""
    forward = Forwarder(lane(1))

    async def broken():
        raise RuntimeError('receive went wrong')
    assert await forward('held') == 'taken'
    queued = asyncio.create_task(forward('patient', broken))
    await asyncio.sleep(.1)
    assert not queued.done() and forward.lane.waiting == 1
    forward.done()
    assert await asyncio.wait_for(queued, 30) == 'taken'
    forward.done()
    await settle()
    assert clean(forward.lane.semaphore)


async def test_queue_cap_refuses_the_overflow_at_once_and_other_lanes_are_unaffected():
    """2 waiting: the next three are refused at once ("queue"), none waits; another profile's lane (its own) takes a
    slot meanwhile; once the queue empties requests wait again. queue 0: a busy lane refuses at once (the mechanism;
    HA's queues are 32 and 16, program constants: plan 8.8 #45)."""
    forward = Forwarder(lane(1), queue=2)
    other = Forwarder(lane(1))
    assert await forward('held') == 'taken'
    waiters = [asyncio.create_task(forward('waiting')) for _ in range(2)]
    await until(lambda: forward.lane.waiting == 2)
    loop = asyncio.get_running_loop()
    started = loop.time()
    assert [await forward('overflow') for _ in range(3)] == ['queue'] * 3
    assert loop.time() - started < 1 and forward.lane.waiting == 2
    assert await other('elsewhere') == 'taken'
    forward.done()
    assert await waiters[0] == 'taken'
    forward.done()
    assert await waiters[1] == 'taken'
    forward.done()
    other.done()
    zero = Forwarder(lane(1), queue=0)
    assert await zero('held') == 'taken'
    started = loop.time()
    assert await zero('refused') == 'queue' and loop.time() - started < 1
    zero.done()
    await settle()
    assert all(clean(f.lane.semaphore) for f in (forward, other, zero))
    assert forward.sent == ['held', 'waiting', 'waiting'] and 'overflow' not in forward.sent


@pytest.mark.parametrize('name', [ORDINARY, RESERVED])
async def test_a_request_that_waited_for_a_slot_keeps_holding_it_until_its_response_closes(name):
    """PaaS N2: a request that got its slot after waiting holds it until its answer ends (UpstreamOwner.close
    releases it): the next one waits; everything released, the semaphore is back at its limit, not over it."""
    forward = Forwarder(lane(1, name), wait=300)
    audit = forward.lane.semaphore
    holder = gateway.UpstreamOwner(audit)
    assert await forward('holder') == 'taken'
    waiter = asyncio.create_task(forward('waiter'))
    await until(lambda: forward.lane.waiting == 1)
    await holder.close()  # the holder's answer ends: the waiter gets the slot
    assert await asyncio.wait_for(waiter, 30) == 'taken'
    granted = gateway.UpstreamOwner(audit)
    await settle()
    assert forward.lane.waiting == 0 and audit.locked(), 'a slot taken after waiting is held'
    newcomer = asyncio.create_task(forward('newcomer'))
    await until(lambda: forward.lane.waiting == 1 or newcomer.done())
    assert not newcomer.done(), 'the slot is held: the next request waits'
    await granted.close()
    assert await asyncio.wait_for(newcomer, 30) == 'taken'
    await gateway.UpstreamOwner(audit).close()
    await settle()
    assert clean(audit)


async def test_queue_limit_counts_each_lane_on_its_own():
    """PaaS N4: each lane has its own queue (ordinary, reserved): the ordinary queue full does not refuse a
    notification; a profile has at most two queues' worth waiting."""
    ordinary, reserved = Forwarder(lane(1), queue=2, wait=300), Forwarder(lane(1, RESERVED), queue=2, wait=300)
    assert await ordinary('held') == 'taken' and await reserved('held') == 'taken'
    waiters = [asyncio.create_task(ordinary('waiting')) for _ in range(2)]
    await until(lambda: ordinary.lane.waiting == 2)
    assert await ordinary('overflow') == 'queue'
    notes = [asyncio.create_task(reserved('note')) for _ in range(2)]
    await until(lambda: reserved.lane.waiting == 2)
    assert not any(note.done() for note in notes), 'notifications were refused by the ordinary queue'
    assert await reserved('overflow') == 'queue'
    for task in waiters + notes:
        task.cancel()
    await asyncio.gather(*waiters, *notes, return_exceptions=True)
    ordinary.done()
    reserved.done()
    await settle()
    assert clean(ordinary.lane.semaphore) and clean(reserved.lane.semaphore)


async def test_closing_the_same_answer_twice_returns_the_slot_only_once():
    """PaaS N9: UpstreamOwner.close twice releases its slot once (a second release would free another request's)."""
    forward = Forwarder(lane(2))
    audit = forward.lane.semaphore
    assert await forward('anchor') == 'taken' and await forward('doomed') == 'taken'
    owner = gateway.UpstreamOwner(audit)
    await owner.close()
    await owner.close()
    assert (audit.held, audit.over_released) == (1, 0), 'one answer closed twice released two slots'
    forward.done()
    await settle()
    assert clean(audit)


async def test_requests_that_timed_out_leave_no_orphan_waiter_on_the_semaphore():
    """PaaS N9: a request that waited in vain cancels its acquire: no orphan waiter keeps a place in the semaphore's
    queue (it would not count against the queue cap and would grow with every timeout)."""
    forward = Forwarder(lane(1), wait=.05)
    assert await forward('holder') == 'taken'
    for _ in range(5):
        assert await forward('late') == 'wait'
    await until(lambda: forward.lane.semaphore.pending == 0)
    assert forward.lane.waiting == 0
    forward.done()
    await settle()
    assert clean(forward.lane.semaphore)


@pytest.mark.parametrize('seed', range(6))
async def test_slot_accounting_survives_random_cancellation_disconnects_timeouts_and_overflow(seed):
    """Many requests race for few slots in two lanes, each at a random moment cancelled, left by its client, timed
    out, refused by its queue or served. Afterwards no slot, waiter or queue place is left over and both lanes hand out
    their full count again (no semaphore slot leaked or grown). PaaS GATEWAY_STRESS_SEEDS: 6 seeds here."""
    rng = random.Random(seed)
    lanes = {ORDINARY: lane(3), RESERVED: lane(2, RESERVED)}
    outcomes = []

    async def one():
        gone = asyncio.Event()
        chosen = lanes[RESERVED if rng.random() < .3 else ORDINARY]
        work = asyncio.create_task(gateway.take_slot(chosen, 4, .05, gone.wait if rng.random() < .8 else never))
        action = rng.choice(['finish', 'finish', 'leave', 'cancel'])
        await asyncio.sleep(rng.random() * .06)
        if action == 'leave':
            gone.set()
        elif action == 'cancel':
            work.cancel()
        try:
            outcome = await work
        except asyncio.CancelledError:
            outcomes.append('cancelled')
            return
        outcomes.append(outcome)
        if outcome == 'taken':
            await asyncio.sleep(rng.random() * .03)
            chosen.semaphore.release()

    await gateway.take_slot(lanes[ORDINARY], 4, .05, never)  # an anchor held throughout
    await asyncio.gather(*(one() for _ in range(120)))
    await settle(50)
    assert {'taken'} <= set(outcomes) and {'abandoned', 'wait', 'queue'} & set(outcomes), set(outcomes)
    assert all(item.waiting == 0 for item in lanes.values())
    assert [await asyncio.wait_for(gateway.take_slot(lanes[ORDINARY], 4, 1, never), 30) for _ in range(2)] == ['taken'] * 2
    assert [await asyncio.wait_for(gateway.take_slot(lanes[RESERVED], 4, 1, never), 30) for _ in range(2)] == ['taken'] * 2
    for item in lanes.values():
        for _ in range(item.limit):
            item.semaphore.release()
    await settle()
    assert all(clean(item.semaphore) for item in lanes.values()), seed


# ---- end to end (PaaS test_gateway_queue.py cases 1-3) ----

def holding_runtime(tmp_path, monkeypatch, **changes):
    quota(monkeypatch, **changes)
    data = setup(tmp_path)
    children = Children()
    children.add(3000, GatewayChild('default', PRODUCT, data))
    child = children.add(18000, GatewayChild('p' + B[:4], PRODUCT, profiles.Layout(data).profile(B)))
    child.hold_calls = True
    return data, children, child


def router_warnings(log_scan):
    return [record for record in log_scan.records
            if record.name == 'mcp_admin_core.profile_router' and record.levelno == logging.WARNING]


async def test_request_abandoned_while_queued_never_reaches_the_child_on_a_real_listener(tmp_path, log_scan,
                                                                                       monkeypatch):
    """PaaS Q6 on the real 8081 listener (uvicorn, h11, TCP): B's 2 slots held, a patient write queued, another write
    whose client gives up after 0.5 s (its HTTP client closes the connection on its timeout). Once the slots come free
    the child gets the patient write and never the abandoned one; one WARNING (B's id's first 8 characters), no ERROR
    and no traceback."""
    data, children, child = holding_runtime(tmp_path, monkeypatch, forward_slots=2, forward_wait_seconds=30)
    async with multi_profile_runtime(PRODUCT, data, children=children, sockets=True) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        url = f'http://127.0.0.1:{runtime.mcp_port}/mcp'
        async with GENUINE_CLIENT(timeout=30, limits=httpx.Limits(max_connections=20)) as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token, url)}
            held = [asyncio.create_task(client.post(url, headers=headers, json=call(1000 + n))) for n in range(2)]
            await until(lambda: child.waiting == 2)
            patient = asyncio.create_task(client.post(url, headers=headers, json=call(88)))
            await until(lambda: any(lane_.waiting == 1 for lane_ in lanes_of(runtime, B)))
            with pytest.raises(httpx.TimeoutException):
                await client.post(url, headers=headers, json=call(77), timeout=.5)
            await until(lambda: sum(lane_.waiting for lane_ in lanes_of(runtime, B)) == 1, 5)
            assert 77 not in child.client_calls()
            child.free.set()
            assert [response.status_code for response in await asyncio.gather(*held)] == [200, 200]
            served = await asyncio.wait_for(patient, 10)
            assert served.status_code == 200 and served.json()['id'] == 88
    assert 77 not in child.client_calls() and 88 in child.client_calls(), 'the abandoned write reached the child'
    warnings = router_warnings(log_scan)
    abandoned = [r for r in warnings if 'closed its connection while its request waited' in r.getMessage()]
    assert len(abandoned) == 1 and 'profile=' + B[:8] in abandoned[0].getMessage()
    assert not [r for r in log_scan.records if r.levelno >= logging.ERROR or r.exc_info]


def lanes_of(runtime, profile_id):
    """The profile's two lanes (gateway.make_apps keeps them on its MCP app's state, for diagnostics and tests)."""
    lanes = runtime.manager.get(profile_id).runtime.mcp_app.state.lanes
    return [lanes[ORDINARY], lanes[RESERVED]]


async def test_clients_leaving_the_queue_are_noticed_at_once_and_take_nothing(tmp_path, log_scan, monkeypatch):
    """Five POSTs and a GET stream queued behind B's held slots, their clients leave: each is out of the queue at once
    (not after the 30 s wait), none reaches the child, nothing is answered to them (499, which no server sends to a
    client gone), the slots stay as they were and serve the next request once free; one WARNING for all of them."""
    data, children, child = holding_runtime(tmp_path, monkeypatch, forward_slots=2, forward_wait_seconds=30)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            session = await session_of(client, token)
            headers = {**bearer(token), 'Mcp-Session-Id': session}
            held = [asyncio.create_task(client.post('/mcp', headers=headers, json=call(1000 + n))) for n in range(2)]
            await until(lambda: child.waiting == 2)
            leavers = []
            for n in range(5):
                request_headers, body = json_body(token, call(200 + n), session)
                leavers.append(Exchange(runtime.mcp_app, 'POST', '/mcp', request_headers, body).start())
            stream_headers = [(k, v) for k, v in bearer(token).items()] + [('mcp-session-id', session)]
            leavers.append(Exchange(runtime.mcp_app, 'GET', '/mcp', stream_headers).start())
            lanes = lanes_of(runtime, B)
            await until(lambda: sum(item.waiting for item in lanes) == 6)
            loop = asyncio.get_running_loop()
            started = loop.time()
            for exchange in leavers:
                exchange.leave()
            await asyncio.wait_for(asyncio.gather(*(exchange.task for exchange in leavers)), 5)
            assert loop.time() - started < 5 and sum(item.waiting for item in lanes) == 0
            assert all(exchange.status in (None, 499) for exchange in leavers)
            assert lanes[0].semaphore.locked() and child.waiting == 2
            child.free.set()
            await asyncio.gather(*held)
            child.hold_calls = False
            after = await client.post('/mcp', headers=headers, json=call(9))
            assert after.status_code == 200 and after.json()['id'] == 9 and 'result' in after.json()
        assert not [i for i in child.client_calls() if 200 <= i < 205], 'an abandoned request reached the child'
        assert [method for method, *_ in child.seen].count('GET') == 0
        notes = [r.getMessage() for r in router_warnings(log_scan)]
        assert len([line for line in notes if 'closed its connection' in line]) == 1, notes


async def test_the_queue_is_capped_per_profile_and_the_overflow_gets_a_clean_busy_answer(tmp_path, log_scan,
                                                                                        monkeypatch):
    """B's queue cap 3: with its 2 slots held and 3 requests queued, two more writes get 200 + -32003 under their ids +
    Retry-After 5 at once (not after the 30 s wait), their text naming the queue; a GET 503 + -32003 id null; none is
    queued or reaches the child; the queued ones are served once the slots come free; one WARNING (rate limited). The
    default profile's queue is its own: its calls are answered meanwhile."""
    data, children, child = holding_runtime(tmp_path, monkeypatch, forward_slots=2, forward_wait_seconds=30, queue=3)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            held = [asyncio.create_task(client.post('/mcp', headers=headers, json=call(1000 + n))) for n in range(2)]
            await until(lambda: child.waiting == 2)
            queued = [asyncio.create_task(client.post('/mcp', headers=headers, json=call(300 + n))) for n in range(3)]
            lanes = lanes_of(runtime, B)
            await until(lambda: lanes[0].waiting == 3)
            loop = asyncio.get_running_loop()
            started = loop.time()
            refused = [await client.post('/mcp', headers=headers, json=call(400 + n)) for n in range(2)]
            no_id = await client.get('/mcp', headers=headers)
            assert loop.time() - started < 3, 'over the cap is refused at once'
            text = profile_router.queue_text(3, 2)
            for n, response in enumerate(refused):
                assert response.status_code == 200 and response.headers['retry-after'] == '5'
                assert response.json() == {'jsonrpc': '2.0', 'id': 400 + n, 'error': {'code': -32003, 'message': text}}
                assert '3 requests' in text and '3 個請求' in text
            assert no_id.status_code == 503 and no_id.headers['retry-after'] == '5'
            assert no_id.json() == {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32003, 'message': text}}
            assert lanes[0].waiting == 3
            default_token = runtime.token('default')
            default_headers = {**bearer(default_token), 'Mcp-Session-Id': await session_of(client, default_token)}
            assert 'result' in (await client.post('/mcp', headers=default_headers, json=call(5))).json()
            child.free.set()
            assert [r.status_code for r in await asyncio.gather(*queued, *held)] == [200] * 5
        assert not [i for i in child.client_calls() if i in (400, 401)]
        lines = [r.getMessage() for r in router_warnings(log_scan) if 'were waiting for one of its' in r.getMessage()]
        assert len(lines) == 1 and 'profile=' + B[:8] in lines[0] and '3 requests' in lines[0], lines
        assert all(json.dumps(token) not in line for line in lines)


def test_every_profiles_own_client_has_room_for_its_slots_and_its_reserve():
    """PaaS cases 16 and 19 pin its one shared httpx pool's size; HA has none (plan 8.8 #15): each profile has its own
    client (40 connections for the default profile, 24 for an additional one). Its forwarding slots and its reserve
    fit in it with room for the health check's two connections, so a profile's own forwards never wait for its client."""
    for quota_ in (profiles.DEFAULT_PROFILE_QUOTA, profiles.EXTRA_PROFILE_QUOTA):
        assert quota_.forward_slots + quota_.reserved_notifications + 2 <= quota_.child_connections, quota_
    assert (profiles.DEFAULT_PROFILE_QUOTA.queue, profiles.EXTRA_PROFILE_QUOTA.queue) == (32, 16)
    assert profiles.DEFAULT_PROFILE_QUOTA.reserved_notifications == profiles.EXTRA_PROFILE_QUOTA.reserved_notifications == 4
