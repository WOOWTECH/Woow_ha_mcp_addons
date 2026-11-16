"""HM-14: an initialize's answer and its child generation (multi-profile plan 12.3 HM-14; contract 1.2, 2.5; FM-43;
the PaaS initialize fence, woow-mcp-server 69ac425 proxy._generation_send and initialize_fence.py), and the masking of a
child's initialize error, which HM-14 applies whether or not the product is switched on (HM-08 review S-4 (a)).

Switched on, the gateway notes the child generation an initialize goes to (its Supervisor's start count) and hands the
child's session to the client only while that generation is still the one running, checked right before the answer's
headers go out: a child that exited, was stopped or was replaced meanwhile took the session with it, so the client gets
503 BACKEND_UNAVAILABLE with Retry-After 5 and no session id (and reconnects), and the dead session gets no DELETE (it
would reach the next generation). HA keeps its own answers otherwise (the gateway's own session while no child runs,
plan 8.8 #68; the DELETE of a session withheld for other reasons). HA has no PaaS-style drain: a restart never waits for
an answer the gateway is still sending, and headers already going out cannot be recalled (the next request in that dead
session gets the child's 404 and the client initializes again). Whether the listener is still the same process is
HM-15's (FM-41, conditional).

A child's initialize error (its message and data are the child's text) was relayed unmasked: not even the profile's own
credentials were masked there, unlike every other relayed text. HM-14 masks it in every product, switched on or off
(contract 1.2): the profile's own credentials (redact.secret_values) and, switched on, every token the add-on holds.
An error without any of them is relayed byte for byte as before.
"""
import asyncio
import json

import httpx
import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import Children, multi_profile_runtime, stored
from mcp_admin_core import profiles, redact
from switched_gateway import B, PRODUCT, Exchange, GatewayChild, bearer, call, json_body, setup, supervisor, watch
from test_single_profile_golden import (CONNECTIONS, NoProcessSupervisor, answer, configure, initialize_body,
                                        initialize_message, settle)

pytestmark = pytest.mark.usefixtures('log_scan')
FENCED = (503, [('cache-control', 'no-store'), ('content-length', '80'), ('content-type', 'application/json'),
                ('retry-after', '5')],
          b'{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"BACKEND_UNAVAILABLE"}}')


def child_runtime(tmp_path):
    data = setup(tmp_path)
    children = Children()
    children.add(3000, GatewayChild('default', PRODUCT, data))
    child = children.add(18000, GatewayChild('p' + B[:4], PRODUCT, profiles.Layout(data).profile(B)))
    return data, children, child


@pytest.mark.parametrize('how', ['restarted', 'exited', 'stopped'])
async def test_an_initialize_whose_generation_changed_is_not_handed_out(tmp_path, log_scan, how):
    """The child gets the initialize, then (before its answer goes out) its generation is replaced, it exits or it is
    stopped: the client gets FENCED (no session id), and no DELETE goes to the child for the session it had opened."""
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token, child_supervisor = runtime.token(B), supervisor(runtime, B)

        def change():
            if how == 'restarted':
                child_supervisor.starts += 1
            else:
                child_supervisor.status = 'backoff' if how == 'exited' else 'stopped'
        child.on_initialize = change
        # HM-09's staggered start already had B's child answer a health check (its readiness session counts too)
        opened = child.opened
        async with runtime.mcp() as client:
            response = await client.post('/mcp', headers=bearer(token), json=initialize_message())
        assert answer(response) == FENCED and 'mcp-session-id' not in response.headers
        assert child.opened == opened + 1, 'the child did open a session'
        # no DELETE for the client's session (the readiness check ends its own session with one: not counted)
        assert [request.method for request in child.requests if request.method == 'DELETE'
                and request.headers.get('mcp-session-id') not in child.checks] == []


async def test_an_initialize_to_the_running_generation_is_handed_out_as_before(tmp_path, log_scan):
    """No change: the session goes out with the gateway's own initialize result, byte for byte, and serves a call."""
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            response = await client.post('/mcp', headers=bearer(token), json=initialize_message())
            assert response.status_code == 200 and response.content == initialize_body(PRODUCT)
            session = response.headers['mcp-session-id']
            # the session B's child opened for this client (not its readiness check's: HM-09's staggered start checks)
            assert session == f'p{B[:4]}-session-{child.opened}' and session not in child.checks
            served = await client.post('/mcp', headers={**bearer(token), 'Mcp-Session-Id': session}, json=call(2))
            assert served.json()['result']['content'][0]['text'] == child.text


async def test_a_restart_never_waits_for_an_initialize_answer_still_going_out(tmp_path, log_scan):
    """The PaaS drain (test_initialize_stop_recovery.py) has no HA counterpart: B's initialize answer is stuck behind
    a client that does not read, and B's child restarts meanwhile (the panel's restart: backend_changed); the restart
    does not wait for it. Headers already going out cannot be recalled: once the client reads, it gets the session the
    old generation opened, and its next request there gets the new child's 404, so it initializes again."""
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token, profile = runtime.token(B), runtime.manager.get(B).runtime
        exchange = Exchange(runtime.mcp_app, 'POST', '/mcp', *json_body(token, initialize_message()),
                            hold_start=True).start()
        await asyncio.wait_for(exchange.blocked.wait(), 5)
        starts = profile.supervisor.starts
        await asyncio.wait_for(profile.backend_changed(profile.store.load()), 2)
        child.sessions.clear()  # the old process took its sessions with it
        assert profile.supervisor.starts == starts + 1 and profile.supervisor.status == 'running'
        exchange.let_through()
        await asyncio.wait_for(exchange.task, 5)
        session = dict(exchange.response_headers)['mcp-session-id']
        async with runtime.mcp() as client:
            gone = await client.post('/mcp', headers={**bearer(token), 'Mcp-Session-Id': session}, json=call(3))
            assert gone.status_code == 404
            assert (await client.post('/mcp', headers=bearer(token), json=initialize_message())).status_code == 200


async def test_switched_off_the_session_is_handed_out_as_before(tmp_path, log_scan):
    """The repository (switched off): no generation fence; the session goes out as today even when the child's start
    count changed meanwhile."""
    made = []

    class Recorded(NoProcessSupervisor):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    children = Children()
    child = children.add(3000, GatewayChild('default', PRODUCT, data))
    async with multi_profile_runtime(PRODUCT, data, switch=False, children=children, supervisor=Recorded) as runtime:
        await settle(runtime, 'configured')
        token = runtime.token('default')
        log_scan.watch(token, stored(data)['child_token'])
        child.on_initialize = lambda: setattr(made[0], 'starts', made[0].starts + 1)
        async with runtime.mcp() as client:
            response = await client.post('/mcp', headers=bearer(token), json=initialize_message())
        assert response.status_code == 200 and response.content == initialize_body(PRODUCT)
        assert response.headers['mcp-session-id'].startswith('default-session-')


# ---- a child's initialize error: masked whether or not the product is switched on (contract 1.2) ----

def initialize_error(text):
    return lambda message: httpx.Response(200, json={'jsonrpc': '2.0', 'id': message['id'], 'error': {
        'code': -32603, 'message': text, 'data': {'detail': text}}})


async def test_switched_off_a_childs_initialize_error_is_masked_with_the_profiles_own_credentials(tmp_path,
                                                                                                log_scan):
    """The repository: the default profile's child answers initialize with an error that carries the profile's own
    token, child token and backend password (a child echoing what it was given): each is [REDACTED] in the message
    and the data, the rest of the text stays; 200, JSON, no session. Before HM-14 this one answer was relayed as is."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    children = Children()
    child = children.add(3000, GatewayChild('default', PRODUCT, data))
    async with multi_profile_runtime(PRODUCT, data, switch=False, children=children) as runtime:
        await settle(runtime, 'configured')
        state = stored(data)
        log_scan.watch(state['token'], state['child_token'])
        password = CONNECTIONS[PRODUCT]['password']
        text = (f"login refused for {state['token']} with child {state['child_token']} and password {password}; "
                'try again')
        child.initialize_answer = initialize_error(text)
        async with runtime.mcp() as client:
            response = await client.post('/mcp', headers=bearer(state['token']), json=initialize_message())
        expected = ('login refused for [REDACTED] with child [REDACTED] and password [REDACTED]; try again')
        assert response.status_code == 200 and 'mcp-session-id' not in response.headers
        assert response.json() == {'jsonrpc': '2.0', 'id': 1, 'error': {
            'code': -32603, 'message': expected, 'data': {'detail': expected}}}
        assert all(secret not in response.text for secret in (state['token'], state['child_token'], password))
        assert redact.SECRET_MASK == '[REDACTED]'


async def test_switched_off_an_initialize_error_without_a_credential_is_relayed_as_before(tmp_path, log_scan):
    """An initialize error that carries none of the profile's credentials: the same bytes as before HM-14 (the
    gateway's own error object, compact JSON with ASCII escapes, the headers it relays)."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    children = Children()
    child = children.add(3000, GatewayChild('default', PRODUCT, data))
    async with multi_profile_runtime(PRODUCT, data, switch=False, children=children) as runtime:
        await settle(runtime, 'configured')
        token = runtime.token('default')
        log_scan.watch(token)
        child.initialize_answer = initialize_error('backend 帳號鎖定 (locked)')
        async with runtime.mcp() as client:
            response = await client.post('/mcp', headers=bearer(token), json=initialize_message())
        body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'error': {
            'code': -32603, 'message': 'backend 帳號鎖定 (locked)', 'data': {'detail': 'backend 帳號鎖定 (locked)'}}},
            separators=(',', ':')).encode()
        assert answer(response) == (200, [('cache-control', 'no-store'), ('content-length', str(len(body))),
                                          ('content-type', 'application/json')], body)


async def test_switched_on_the_initialize_error_mask_is_unchanged(tmp_path, log_scan):
    """Switched on, the mask stays HM-08's union (tests/test_reply_mask_union.py): another profile's token in B's
    child's initialize error is [REDACTED] too."""
    data, children, child = child_runtime(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        token, other = runtime.token(B), runtime.token('default')
        child.initialize_answer = initialize_error(f'saw {other} and {token}')
        async with runtime.mcp() as client:
            response = await client.post('/mcp', headers=bearer(token), json=initialize_message())
        assert response.json()['error']['message'] == 'saw [REDACTED] and [REDACTED]'
