"""HM-30: the idle profiles' health checks hold while another profile's large replies starve the add-on's CPU
(multi-profile plan 5.4, 5.5; contract 6, 7; DQ-25; §8.8 #18; invariant I8; C2-MF-4 point 3; FM-130), on top of HM-09's
rule: a backend is judged unreachable only after two failed checks in a row of the same child
(tests/test_health_backoff.py tests the rule itself).

- C2 found (cross_profile_probe_sim.py): one profile's replies, processed on the one event loop, made another profile's
  health check exceed its limits (8 + 5 s; health.py), so its tools/calls were refused with backend_unreachable until
  the next check. With the reply worker the loop no longer waits for any reply's processing: while A's 16 replies of
  8 MiB and 16 of 2 MiB cost 0.25 s each per 8 MiB of GIL-holding work (tests/reply_load.py), B's and C's checks keep
  their pace: none times out or fails, and each one is done within d (0.25 s) of when it was due (processed on the
  loop, before HM-30, the same checks were done up to 4.4 s after they were due).
- Should a check still fail while A starves the CPU (here B's backend really fails), one failure refuses nothing, the
  second in a row does, and C stays untouched; a check that passes again ends it.
"""
import asyncio
import json

import httpx
import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from reply_load import B, C, D, bearer, call, session_of, starved
from test_profile_runtime import ProfileChild
from test_single_profile_golden import probe_name

pytestmark = pytest.mark.usefixtures('log_scan')
# How long after it is due a check may finish: one reply's processing (d), far within the check's own limits (8 + 5 s).
# Processed on the loop (before HM-30), a check due while replies are processed waits for every one in its way.
CHECK_SECONDS = D


class FlakyBackend(ProfileChild):
    """A ProfileChild whose readiness probe reports the backend unavailable while failing is set (the child answers:
    a failed check of the backend, not of the child); probes counts the probes it answered."""

    def __init__(self, *args):
        super().__init__(*args)
        self.failing = False
        self.probes = 0

    async def __call__(self, request):
        response = await super().__call__(request)  # its bearer and session rules first
        value = json.loads(request.content) if request.content else {}
        if (response.status_code == 200 and value.get('method') == 'tools/call'
                and value['params']['name'] == probe_name(self.product)):
            self.probes += 1
            if self.failing:
                return httpx.Response(200, json={'jsonrpc': '2.0', 'id': value['id'], 'result': {
                    'content': [{'type': 'text', 'text': 'Error executing tool list_models: BACKEND_UNAVAILABLE: '
                                                         'the synthetic backend failed'}], 'isError': True}})
        return response


async def test_idle_profiles_health_checks_keep_their_pace_while_another_profile_starves_the_cpu(tmp_path, log_scan,
                                                                                                monkeypatch):
    """B's and C's monitors check again and again while A's replies are processed: every check gets the child's answer
    and finds the backend reachable (none times out: 0 against contract 6's threshold), each one done within d of when it
    was due (the loop never waits for a reply's processing), and the checks really reached B's and C's children."""
    loop = asyncio.get_running_loop()
    durations, verdicts = {B: [], C: []}, {B: [], C: []}
    async with starved(tmp_path, log_scan, monkeypatch, child=FlakyBackend) as run:
        runtime = run.runtime
        children = {B: runtime.children.by_port[18000], C: runtime.children.by_port[18001]}
        before = {profile_id: children[profile_id].probes for profile_id in (B, C)}

        async def checking(profile_id):
            monitor = runtime.manager.get(profile_id).runtime.health
            while not all(task.done() for task in run.a_tasks):
                due = loop.time() + 0.1
                await asyncio.sleep(0.1)
                await monitor.check()
                durations[profile_id].append(loop.time() - due)  # from when it was due to when it was done
                verdicts[profile_id].append(monitor.availability())
        await asyncio.gather(checking(B), checking(C))
        token = runtime.token(B)
        async with runtime.mcp() as client:
            response = await client.post('/mcp', headers={**bearer(token), 'Mcp-Session-Id': await session_of(
                client, token)}, json=call(7))
            assert response.status_code == 200 and response.json()['result']['content'][0]['text'] == (
                'profile tool result')
    print('HM-30 health under starvation: ' + ', '.join(
        f'{profile_id[:4]} {len(durations[profile_id])} checks, latest done {max(durations[profile_id]) * 1000:.0f} ms '
        'after it was due'
        for profile_id in (B, C)))
    for profile_id in (B, C):
        assert len(durations[profile_id]) >= 10, durations
        assert children[profile_id].probes - before[profile_id] >= len(durations[profile_id])
        assert all(verdict == {'child': 'running', 'ready': True, 'backend': 'reachable', 'reason': None}
                   for verdict in verdicts[profile_id]), verdicts[profile_id]
        assert max(durations[profile_id]) <= CHECK_SECONDS, durations[profile_id]


async def test_while_another_profile_starves_the_cpu_one_failed_check_refuses_nothing_two_do(tmp_path, log_scan,
                                                                                               monkeypatch):
    """During A's load B's backend fails one check: B's tools/call is still forwarded (the verdict stays reachable);
    after a second failed check in a row it is refused (-32603 Backend unreachable, with the check's reason), while C
    is answered all along; one passing check ends it."""
    async with starved(tmp_path, log_scan, monkeypatch, child=FlakyBackend) as run:
        runtime = run.runtime
        b_child = runtime.children.by_port[18000]
        monitors = {profile_id: runtime.manager.get(profile_id).runtime.health for profile_id in (B, C)}
        async with runtime.mcp(timeout=60) as client:
            sessions = {}
            for profile_id in (B, C):
                sessions[profile_id] = {**bearer(runtime.token(profile_id)),
                                        'Mcp-Session-Id': await session_of(client, runtime.token(profile_id))}

            async def answer(profile_id, ident):
                response = await client.post('/mcp', headers=sessions[profile_id], json=call(ident))
                assert response.status_code == 200
                return response.json()
            await monitors[B].check()
            assert monitors[B].availability()['backend'] == 'reachable'
            b_child.failing = True
            await monitors[B].check()
            assert monitors[B].availability()['backend'] == 'reachable'  # one failure: the verdict stays
            assert (await answer(B, 11))['result']['content'][0]['text'] == 'profile tool result'
            await monitors[B].check()
            available = monitors[B].availability()
            assert (available['backend'], available['reason']) == (
                'unreachable', 'BACKEND_UNAVAILABLE: the synthetic backend failed')
            refused = await answer(B, 12)
            assert refused['error']['message'] == 'Backend unreachable'
            assert refused['error']['data']['reason'] == 'BACKEND_UNAVAILABLE: the synthetic backend failed'
            await monitors[C].check()
            assert monitors[C].availability()['backend'] == 'reachable'
            assert (await answer(C, 13))['result']['content'][0]['text'] == 'profile tool result'
            b_child.failing = False
            await monitors[B].check()
            assert monitors[B].availability()['backend'] == 'reachable'
            assert (await answer(B, 14))['result']['content'][0]['text'] == 'profile tool result'
            assert not all(task.done() for task in run.a_tasks), 'A was no longer loading the add-on'
