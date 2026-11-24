"""A JSON-RPC request id that is already in flight in the same MCP session is refused before it reaches the child (the PaaS
#161 gateway, woow-mcp-server 81fd50a, ad03275, 39891b6; its tests packages/mcp-admin-core/tests/test_proxy_inflight_ids.py;
contract 1.2, 2.8, 4.2, section 9 #134). Not gated: every product, switched on or off.

Why: the MCP Python SDK's Streamable HTTP keys the stream of a request's answer by str(message.id) (mcp 2.3.0,
server/streamable_http.py: request_id = str(message.id), self._request_streams[request_id]; in SSE and JSON mode alike),
so two requests of one session that are in flight together with the same id overwrite each other's stream. PaaS measured
8 requests with id 7: none got its own answer, one got another's, seven hung until the gateway's own limit. The gateway
registers (profile, Mcp-Session-Id, str(id)) when a request is about to be forwarded and gives it back when the request
ends (its forwarding slot's release); a second request with the same key is refused at once: HTTP 400, JSON-RPC -32600,
id null, the id named in the text, never sent to the child.

| PaaS test (test_proxy_inflight_ids.py) | here |
|---|---|
| second_inflight_request_with_same_id_is_refused_fast_first_completes | test_a_second_request_with_an_id_in_flight_is_refused_at_once_and_never_sent (both paths, JSON and SSE answers, both modes) |
| duplicate_refusals_are_logged_through_the_throttled_gateway_report | test_the_refusals_are_logged_once_a_minute_per_profile_without_the_id_or_the_session |
| int_and_string_ids_collide | test_the_int_and_the_string_form_of_an_id_are_the_same_id |
| completed_id_can_be_reused | test_an_id_can_be_used_again_once_its_request_ended |
| same_id_in_different_sessions_is_fine, registry_keys_by_profile_and_session | test_the_same_id_in_another_session_is_not_a_duplicate, test_two_profiles_with_the_same_session_and_id_do_not_see_each_other, the registry unit tests |
| duplicate_inside_a_batch, batch_overlapping_an_inflight_request | not applicable: HA's policy lets single messages only through (policy.authorize: 403 before any slot); test_a_batch_and_a_response_never_reach_the_table shows it |
| notifications_initialize_and_missing_session_are_unaffected | test_notifications_initialize_and_a_missing_session_are_not_registered |
| client_response_and_initialize_with_session_id_are_not_registered | test_a_batch_and_a_response_never_reach_the_table, test_notifications_initialize_and_a_missing_session_are_not_registered |
| released_after_client_disconnect | test_an_id_is_released_when_the_client_leaves_mid_answer |
| released_after_gateway_timeout | test_an_id_is_released_when_the_gateway_gives_up_on_the_child (and test_an_id_is_released_when_the_request_is_cancelled) |
| released_after_upstream_error_and_exception | test_an_id_is_released_after_every_way_the_child_or_the_gateway_fails |
| release_is_idempotent_and_leaves_no_residue | test_release_is_idempotent_and_leaves_no_residue |
| table_is_bounded_and_fails_open, one_profile_cannot_fill_the_table_for_others | the registry unit tests (the caps), test_a_full_table_lets_the_request_through_and_logs_one_line, test_a_profile_at_its_limit_lets_the_request_through_and_logs_one_line |
| oversized_post_is_not_registered | not applicable (no batch); the id's own bound instead: test_an_id_longer_than_the_bound_is_not_registered |
| max_entries_env_is_validated | not applicable: HA's limits are program constants (contract 9 #45); test_the_environment_changes_nothing |
| gateway_limits_doc_describes_duplicate_ids | test_the_contract_describes_the_duplicate_id_rule |

HA only: two profiles of one add-on (the key has the profile), a token changed mid-answer (-32005 or, switched off, the
server's disconnect), the child's connection broken (-32004), a GET stream and a DELETE (never registered, never
refused), the answers the gateway gives itself (never registered), a table that is full, a profile at its limit, an id
too long to register, the id free before the client takes the child's reply.
"""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import json
import logging
import re

import httpx
import pytest

from admin_write_headers import current_headers
from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import Children, create_profile, multi_profile_runtime
from mcp_admin_core import gateway, profiles, request_budget
from switched_gateway import (B, FAILURES, LABELS, PRODUCT, Exchange, GatewayChild, bearer, call, json_body, ping,
                              session_of, setup, sse_messages, until, watch)
from test_single_profile_golden import ACCEPT, ADMIN, ROOT, configure, initialize_message, settle

try:
    from mcp_admin_core import inflight_ids
except ImportError:  # the red half: without the module every test of it fails on its own
    inflight_ids = None

pytestmark = pytest.mark.usefixtures('log_scan')
MODES = pytest.mark.parametrize('switch', [False, True], ids=['switched off', 'switched on'])
PATHS = pytest.mark.parametrize('path', ['bearer', 'secret'])
KINDS = pytest.mark.parametrize('kind', ['json', 'sse'])
PAPER_TEXT = (  # the PaaS text (inflight_ids.duplicate_message) for a plain id: HA's differs only in how an odd id shows
    "Duplicate in-flight JSON-RPC request id '7' in this MCP session: a request with the same id is still being "
    "processed, so this request was not sent. Use a unique id per request (ids must not be reused within a session "
    "while in flight). (同一個 MCP session 內已有進行中的請求使用相同的 id '7'，這個請求沒有送出；請求 id 在同一個 session "
    "內不得重複使用。)")


# ---- the rig: one product's production runtime, switched on (the additional profile B is under test) or off ----

@dataclass
class Rig:
    runtime: object
    switch: bool
    profile: str          # the profile under test: B switched on, the default profile switched off
    child: GatewayChild   # its child
    token: str
    table: object         # inflight_ids.InflightIds: the table its gateway registers in
    limit: int            # how many requests it forwards at once (its forwarding slots): the table's per-profile cap

    def target(self, path='bearer'):
        return '/mcp' if path == 'bearer' else f'/private_{self.token}/mcp'

    def headers(self, session, path='bearer'):
        base = bearer(self.token) if path == 'bearer' else {**ACCEPT, 'Content-Type': 'application/json'}
        return {**base, 'Mcp-Session-Id': session}

    def post(self, client, session, message, path='bearer'):
        return client.post(self.target(path), headers=self.headers(session, path), json=message)

    def start(self, session, message, path='bearer', method='POST'):
        """One request driven by hand (its answer streams while the test goes on)."""
        body = json.dumps(message).encode() if message is not None else b''
        return Exchange(self.runtime.mcp_app, method, self.target(path), list(self.headers(session, path).items()),
                        body).start()


def in_flight(rig, count):
    return lambda: len(rig.table) == count


async def drained(table, seconds=5):
    try:
        await until(lambda: len(table) == 0, seconds)
    except TimeoutError:
        return False
    return True


@asynccontextmanager
async def rig(tmp_path, log_scan, switch, *, configured=True):
    """The runtime of PRODUCT on tmp_path. Switched on: the default profile and the additional profile B (the profile
    under test); switched off: the default profile alone. Whatever the test left registered is looked for at the end:
    every request of the test ended, so the table must be empty."""
    data = tmp_path / 'data'
    children = Children()
    if switch and configured:
        data = setup(tmp_path)
    elif switch:
        create_profile(data, PRODUCT, B, label=LABELS[B], port=18000, configured=False)
    elif configured:
        configure(data, PRODUCT)
    default = children.add(3000, GatewayChild('default', PRODUCT, data))
    child = default
    if switch:
        child = children.add(18000, GatewayChild('p' + B[:4], PRODUCT, profiles.Layout(data).profile(B)))
    async with multi_profile_runtime(PRODUCT, data, switch=switch, children=children) as runtime:
        await settle(runtime, 'configured' if configured else 'fresh')
        profile = B if switch else 'default'
        watch(log_scan, data, *([B] if switch else []))
        app = runtime.manager.get(profile).runtime.mcp_app if switch else runtime.mcp_app
        limit = (profiles.EXTRA_PROFILE_QUOTA if switch else profiles.DEFAULT_PROFILE_QUOTA).forward_slots
        made = Rig(runtime, switch, profile, child, runtime.token(profile), app.state.inflight, limit)
        try:
            yield made
        finally:
            for each in children.by_port.values():
                each.free.set()  # nothing stays held
        assert await drained(made.table), 'an id was registered and never given back'


def refused(response, shown="'7'"):
    """The refusal of a duplicate in-flight id: 400, JSON-RPC -32600 under id null, the id named in the text."""
    assert response.status_code == 400, response.text
    assert response.headers['cache-control'] == 'no-store' and response.headers['content-type'] == 'application/json'
    assert 'retry-after' not in response.headers
    body = response.json()
    assert list(body) == ['jsonrpc', 'id', 'error'] and body['jsonrpc'] == '2.0' and body['id'] is None
    assert list(body['error']) == ['code', 'message'] and body['error']['code'] == -32600
    assert f' id {shown}' in body['error']['message'] and 'in-flight' in body['error']['message']
    return body


def own_answer(response, ident, text):
    """A tools/call answer with the id and text of the child's reply (JSON or SSE)."""
    assert response.status_code == 200, response.text
    if response.headers['content-type'].startswith('text/event-stream'):
        replies = [m for m in sse_messages(response.content) if m.get('id') == ident]
        assert len(replies) == 1
        message = replies[0]
    else:
        message = response.json()
    assert message['id'] == ident and message['result']['content'][0]['text'] == text, message


def ponged(response, ident):
    """A ping's answer under its id. The tests overlap requests of one profile with a ping: it takes no reply ticket
    (reply_memory: a switched-on Odoo profile has one, so a second tools/call of it, while the first is in flight, is
    answered busy -32003 before it is forwarded, duplicate or not)."""
    assert response.status_code == 200, response.text
    assert response.json() == {'jsonrpc': '2.0', 'id': ident, 'result': {}}, response.text


def warnings_about(log_scan, text='in flight'):
    return [record for record in log_scan.records
            if record.levelno == logging.WARNING and text in record.getMessage()]


def reports_of(rig_):
    """The throttle the profile's WARNINGs go through (the add-on's Reports; switched off: the budget share's own)."""
    return rig_.runtime.manager.reports if rig_.switch else rig_.runtime.mcp_app.state.body_budget.reports


def hold(rig_, kind):
    """The next tools/call the child gets is held (kind 'json': it answers after free; 'sse': it streams ': working'
    and answers after free); release_following() lets the ones after it through."""
    if kind == 'json':
        rig_.child.hold_calls = True
    else:
        rig_.child.streaming = True


def release_following(rig_):
    rig_.child.hold_calls = rig_.child.streaming = False


async def rotate_token(rig_):
    """The panel's token rotation (the admin API, as an administrator sends it), then the profile's new token."""
    async with rig_.runtime.admin(rig_.profile) as admin:
        headers = await current_headers(admin, ADMIN)
        response = await admin.post('/api/token/rotate', headers=headers)
        assert response.status_code == 200, response.text
    return rig_.runtime.token(rig_.profile)


# ---- 1. a request with an id in flight is refused at once, the first one completes ----

@MODES
@PATHS
@KINDS
async def test_a_second_request_with_an_id_in_flight_is_refused_at_once_and_never_sent(tmp_path, log_scan, switch, path,
                                                                                    kind):
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            hold(r, kind)
            first = r.start(session, call(7), path)
            await until(lambda: r.child.client_calls() == [7])
            assert len(r.table) == 1
            release_following(r)
            loop = asyncio.get_running_loop()
            started = loop.time()
            second = await r.post(client, session, call(7), path)
            elapsed = loop.time() - started
            refused(second)
            assert elapsed < 1.0, f'the refusal took {elapsed:.2f} s'
            assert r.child.client_calls() == [7], 'the duplicate was sent to the child'
            assert len(r.table) == 1, 'the refused request left a registration'
            r.child.free.set()
            await asyncio.wait_for(first.task, 5)
            assert first.task.exception() is None and first.ended
            own_answer(httpx.Response(first.status, headers=dict(first.response_headers), content=first.content), 7,
                       'streamed' if kind == 'sse' else 'profile tool result')
        assert r.child.client_calls() == [7]


async def test_the_refusal_is_the_documented_answer_byte_for_byte(tmp_path, log_scan):
    async with rig(tmp_path, log_scan, False) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            hold(r, 'sse')
            first = r.start(session, call(7))
            await until(lambda: len(r.table) == 1)
            release_following(r)
            second = await r.post(client, session, call(7))
            body = json.dumps({'jsonrpc': '2.0', 'id': None,
                               'error': {'code': -32600, 'message': PAPER_TEXT}}, separators=(',', ':')).encode()
            assert second.content == body, second.content
            assert sorted((k, v) for k, v in second.headers.items()) == [
                ('cache-control', 'no-store'), ('content-length', str(len(body))), ('content-type', 'application/json')]
            r.child.free.set()
            await asyncio.wait_for(first.task, 5)


@MODES
@pytest.mark.parametrize('first_id,second_id', [(7, '7'), ('7', 7)], ids=['7 then "7"', '"7" then 7'])
async def test_the_int_and_the_string_form_of_an_id_are_the_same_id(tmp_path, log_scan, switch, first_id, second_id):
    """str(id), as the SDK keys it: 7 and "7" are one id."""
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            hold(r, 'sse')
            first = r.start(session, call(first_id))
            await until(lambda: len(r.table) == 1)
            release_following(r)
            refused(await r.post(client, session, call(second_id)))
            r.child.free.set()
            await asyncio.wait_for(first.task, 5)


@MODES
async def test_the_same_number_is_not_the_same_id_as_another_spelling(tmp_path, log_scan, switch):
    """"1" and "01", "1" and "1.0", "1" and 10 are different ids: str(id) differs, as the SDK keys them."""
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            hold(r, 'sse')
            first = r.start(session, call('1'))
            await until(lambda: len(r.table) == 1)
            release_following(r)
            for other in ('01', '1.0', 10, ' 1', '1 '):
                ponged(await r.post(client, session, ping(other)), other)
            r.child.free.set()
            await asyncio.wait_for(first.task, 5)


# ---- 2. only what is in flight counts ----

@MODES
@KINDS
async def test_an_id_can_be_used_again_once_its_request_ended(tmp_path, log_scan, switch, kind):
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            if kind == 'sse':
                r.child.streaming = True
                r.child.free.set()  # it answers at once, as an event stream
            for _ in range(3):
                own_answer(await r.post(client, session, call(7)), 7, 'streamed' if kind == 'sse' else
                           'profile tool result')
                assert len(r.table) == 0
        assert r.child.client_calls() == [7, 7, 7]


@MODES
@KINDS
async def test_the_id_is_free_before_the_client_takes_the_childs_reply(tmp_path, log_scan, switch, kind):
    """The child has answered: the id is no longer in flight. A client that takes the reply and reuses the id at once
    (before the stream's clean-up is done) finds it free: the table is already empty as the server is handed the reply."""
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            held_at = []

            class Watching(Exchange):
                async def send(self, message):
                    if message['type'] == 'http.response.body' and b'"result"' in message.get('body', b''):
                        held_at.append(len(r.table))  # what the table holds as the server is handed the reply
                    await super().send(message)
            if kind == 'sse':
                r.child.streaming = True
                r.child.free.set()  # it answers at once, as an event stream
            exchange = Watching(r.runtime.mcp_app, 'POST', '/mcp', *json_body(r.token, call(7), session)).start()
            await asyncio.wait_for(exchange.task, 5)
            assert exchange.task.exception() is None and exchange.ended
            assert held_at == [0], held_at


@MODES
async def test_the_same_id_in_another_session_is_not_a_duplicate(tmp_path, log_scan, switch):
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            one, two = await session_of(client, r.token), await session_of(client, r.token)
            assert one != two
            hold(r, 'sse')
            first = r.start(one, call(7))
            await until(lambda: len(r.table) == 1)
            release_following(r)
            ponged(await r.post(client, two, ping(7)), 7)  # id 7 of the other session: not a duplicate
            refused(await r.post(client, one, call(7)))
            r.child.free.set()
            await asyncio.wait_for(first.task, 5)


async def test_two_profiles_with_the_same_session_and_id_do_not_see_each_other(tmp_path, log_scan):
    """The key has the profile: both children name their session the same, and both profiles use id 7 together."""
    data = setup(tmp_path)
    children = Children()
    default = children.add(3000, GatewayChild('same', PRODUCT, data))
    extra = children.add(18000, GatewayChild('same', PRODUCT, profiles.Layout(data).profile(B)))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data, B)
        table = runtime.manager.inflight
        assert all(entry.runtime.mcp_app.state.inflight is table for entry in runtime.manager.profiles())
        tokens = {'default': runtime.token('default'), B: runtime.token(B)}
        async with runtime.mcp() as client:
            sessions = {name: await session_of(client, token) for name, token in tokens.items()}
            assert sessions['default'] == sessions[B]  # one session id string, two profiles
            default.streaming = extra.streaming = True
            held = {name: Exchange(runtime.mcp_app, 'POST', '/mcp', *json_body(tokens[name], call(7), sessions[name]))
                    .start() for name in tokens}
            await until(lambda: default.client_calls() == [7] and extra.client_calls() == [7])
            assert len(table) == 2 and table.count('default') == 1 and table.count(B) == 1
            default.streaming = extra.streaming = False
            for name, token in tokens.items():  # inside each profile the id is still a duplicate
                refused(await client.post('/mcp', headers={**bearer(token), 'Mcp-Session-Id': sessions[name]},
                                          json=call(7)))
            default.free.set()
            extra.free.set()
            for exchange in held.values():
                await asyncio.wait_for(exchange.task, 5)
                assert exchange.task.exception() is None and exchange.ended
        assert default.client_calls() == [7] and extra.client_calls() == [7]
        assert await drained(table)


# ---- 3. what is never registered, never refused ----

@MODES
async def test_notifications_initialize_and_a_missing_session_are_not_registered(tmp_path, log_scan, switch):
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            hold(r, 'sse')
            first = r.start(session, call(7))
            await until(lambda: len(r.table) == 1)
            release_following(r)
            note = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}
            for _ in range(3):  # no id: the forwarded one and the one the gateway answers itself
                assert (await r.post(client, session, note)).status_code == 202
                assert (await r.post(client, session, {**note, 'method': 'notifications/cancelled'})).status_code == 202
            for _ in range(2):  # an initialize is never registered, with the session's header too, whatever its id
                opened = await client.post('/mcp', headers=bearer(r.token), json=initialize_message(7))
                assert opened.status_code == 200 and 'mcp-session-id' in opened.headers
                again = await r.post(client, session, initialize_message(7))
                assert again.status_code == 200 and again.json()['id'] == 7
            nothing = await client.post('/mcp', headers=bearer(r.token), json=call(7))  # no session id at all
            assert nothing.status_code == 400 and nothing.json()['error']['code'] == -32000
            assert len(r.table) == 1  # only the request in flight
            r.child.free.set()
            await asyncio.wait_for(first.task, 5)


@MODES
async def test_a_batch_and_a_response_never_reach_the_table(tmp_path, log_scan, switch):
    """HA's policy lets single requests only through (403 before any slot): nothing of a batch, or of the answer a client
    gives to a server request, is registered or sent, whatever ids it carries."""
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            hold(r, 'sse')
            first = r.start(session, call(7))
            await until(lambda: len(r.table) == 1)
            release_following(r)
            for body in ([call(5), call('5')], [call(7)], {'jsonrpc': '2.0', 'id': 7, 'result': {}},
                         {'jsonrpc': '2.0', 'id': 7, 'error': {'code': -1, 'message': 'x'}}):
                response = await r.post(client, session, body)
                assert response.status_code == 403 and response.json() == {'error': 'request denied'}
                assert len(r.table) == 1
            assert r.child.client_calls() == [7]
            r.child.free.set()
            await asyncio.wait_for(first.task, 5)


@MODES
async def test_a_get_stream_and_a_delete_are_neither_registered_nor_refused(tmp_path, log_scan, switch):
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            hold(r, 'sse')
            first = r.start(session, call(7))
            await until(lambda: len(r.table) == 1)
            release_following(r)
            streams = [r.start(session, None, method='GET') for _ in range(2)]
            await until(lambda: all(b': open' in stream.content for stream in streams))
            assert len(r.table) == 1 and all(stream.status == 200 for stream in streams)
            ended = await client.delete(r.target(), headers=r.headers(session))
            assert ended.status_code == 200 and len(r.table) == 1
            r.child.free.set()
            for exchange in (first, *streams):
                await asyncio.wait_for(exchange.task, 5)
                assert exchange.task.exception() is None


@MODES
async def test_what_the_gateway_answers_itself_is_never_registered(tmp_path, log_scan, switch, monkeypatch):
    """No backend saved: the gateway answers initialize, ping, tools/list and tools/call itself, in a session of its own
    (contract 2.4: no child is asked). Two requests with one id, one after the other or together, are both answered:
    nothing of them reaches the table. The same for a call the policy refuses and a method the gateway does not know."""
    calls = []
    real = inflight_ids.InflightIds.begin

    def spy(self, *args):
        calls.append(args)
        return real(self, *args)
    monkeypatch.setattr(inflight_ids.InflightIds, 'begin', spy)
    async with rig(tmp_path, log_scan, switch, configured=False) as r:
        async with r.runtime.mcp() as client:
            opened = await client.post('/mcp', headers=bearer(r.token), json=initialize_message())
            assert opened.status_code == 200 and opened.headers['mcp-session-id'].startswith('woow-local-')
            session = opened.headers['mcp-session-id']
            assert (await r.post(client, session, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                    ).status_code == 202
            messages = [ping(7), {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/list'}, call(7),
                        {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call', 'params': {'name': 'no-such-tool'}},
                        {'jsonrpc': '2.0', 'id': 7, 'method': 'server/discover'}]
            for message in messages:
                for response in await asyncio.gather(r.post(client, session, message), r.post(client, session, message)):
                    assert response.status_code == 200 and response.json()['id'] == 7, message
                    assert 'Duplicate' not in response.text
        assert calls == [] and len(r.table) == 0
        assert r.child.client_calls() == [] and r.child.client_pings() == []


@MODES
async def test_what_goes_to_the_child_is_registered_with_the_profile_the_session_and_the_id(tmp_path, log_scan, switch,
                                                                                         monkeypatch):
    calls = []
    real = inflight_ids.InflightIds.begin

    def spy(self, *args):
        calls.append(args)
        return real(self, *args)
    monkeypatch.setattr(inflight_ids.InflightIds, 'begin', spy)
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            for message in (ping(3), {'jsonrpc': '2.0', 'id': 'four', 'method': 'tools/list'}, call(5)):
                assert (await r.post(client, session, message)).status_code == 200
        assert calls == [(r.profile, session, 3, r.limit), (r.profile, session, 'four', r.limit),
                         (r.profile, session, 5, r.limit)]


# ---- 4. the id is given back whichever way the request ends ----

@MODES
async def test_an_id_is_released_when_the_client_leaves_mid_answer(tmp_path, log_scan, switch):
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            hold(r, 'sse')
            first = r.start(session, call(7))
            await until(lambda: b': working' in first.content)  # the answer started: the id is in flight
            assert len(r.table) == 1
            first.leave()
            await asyncio.wait_for(first.task, 5)
            assert await drained(r.table)
            release_following(r)
            own_answer(await r.post(client, session, call(7)), 7, 'profile tool result')  # no duplicate


@MODES
@KINDS
async def test_an_id_is_released_when_the_request_is_cancelled(tmp_path, log_scan, switch, kind):
    """The server cancels the request task (asyncio's own cancellation, as at a shutdown) while the child's answer is
    awaited (JSON) or streamed (SSE): the clean-up is shielded, and gives the id back with the slot."""
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            hold(r, kind)
            first = r.start(session, call(7))
            await until(lambda: r.child.client_calls() == [7] and len(r.table) == 1)
            first.task.cancel()
            await asyncio.gather(first.task, return_exceptions=True)
            assert await drained(r.table)
            release_following(r)
            own_answer(await r.post(client, session, call(7)), 7, 'profile tool result')  # not a duplicate


@MODES
async def test_an_id_is_released_when_the_gateway_gives_up_on_the_child(tmp_path, log_scan, switch, monkeypatch):
    monkeypatch.setattr(gateway, 'CALL_SECONDS', .3)  # a tools/call's reply may take this long (330 s in production)
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            hold(r, 'sse')
            loop = asyncio.get_running_loop()
            started = loop.time()
            response = await r.post(client, session, call(7))  # the stream ends without a reply
            assert response.status_code == 200 and b'"result"' not in response.content
            assert .25 < loop.time() - started < 5
            assert len(r.table) == 0
            release_following(r)
            own_answer(await r.post(client, session, call(7)), 7, 'profile tool result')


def child_wrong(kind):
    if kind == 'refused':
        return lambda message: httpx.Response(403)
    if kind == 'malformed':
        return lambda message: httpx.Response(200, headers={'content-type': 'application/json'}, content=b'{"jsonrpc"')
    raise AssertionError(kind)


@MODES
@pytest.mark.parametrize('how', ['refused', 'malformed', 'broken json', 'broken sse', 'unreachable', 'exception',
                                 'budget'])
async def test_an_id_is_released_after_every_way_the_child_or_the_gateway_fails(tmp_path, log_scan, switch, monkeypatch,
                                                                             how):
    """The answer is the gateway's today (502, -32004 switched on, a busy -32003 for the budget), and the id is not
    held by it: the same id is not a duplicate afterwards."""
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            if how in ('refused', 'malformed'):
                r.child.reply = child_wrong(how)
            elif how == 'broken json':
                r.child.broken = 'json'
            elif how == 'broken sse':
                r.child.broken = 'sse'
            elif how == 'unreachable':
                r.child.fail = FAILURES[0]
            elif how == 'exception':
                def explode(message):
                    raise RuntimeError('the transport failed')
                r.child.reply = explode
            else:
                def too_big(self, size):
                    raise request_budget.BudgetExceeded('profile', 1)
                monkeypatch.setattr(request_budget.Reservation, 'forward', too_big)
            for _ in range(2):  # the second one would be refused if the first still held its id
                if how == 'exception':
                    with pytest.raises(RuntimeError):
                        await r.post(client, session, call(7))
                else:
                    response = await r.post(client, session, call(7))
                    assert 'Duplicate' not in response.text, how
                    assert response.status_code in (200, 502), (how, response.status_code)
                assert len(r.table) == 0, how
            if how == 'budget':
                monkeypatch.undo()
            for name in ('reply', 'broken', 'fail'):
                setattr(r.child, name, None)
            own_answer(await r.post(client, session, call(7)), 7, 'profile tool result')


@MODES
async def test_an_id_is_released_when_the_token_changes_mid_answer(tmp_path, log_scan, switch):
    """Switched on the stream ends with one -32005 event; switched off the server is given the disconnect (today's
    ClientDisconnect): the id is given back either way, and the new token's session uses it again."""
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            hold(r, 'sse')
            first = r.start(session, call(7))
            await until(lambda: b': working' in first.content and len(r.table) == 1)
            new = await rotate_token(r)
            log_scan.watch(new)
            await asyncio.wait_for(asyncio.gather(first.task, return_exceptions=True), 5)
            if switch:
                assert first.task.exception() is None
                assert [(event['id'], event['error']['code']) for event in sse_messages(first.content)] == [(7, -32005)]
            assert await drained(r.table)
            release_following(r)
            r.token = new
            fresh = await session_of(client, new)
            own_answer(await r.post(client, fresh, call(7)), 7, 'profile tool result')


@pytest.mark.parametrize('broken', ['json', 'sse'])
async def test_an_id_is_released_when_the_childs_connection_breaks_mid_answer(tmp_path, log_scan, broken):
    """-32004 (switched on): before the headers (a JSON answer) and on an event stream."""
    async with rig(tmp_path, log_scan, True) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            r.child.broken = broken
            response = await r.post(client, session, call(7))
            if broken == 'json':
                assert response.status_code == 502 and response.json()['error']['code'] == -32004
            else:
                assert [(event['id'], event['error']['code']) for event in sse_messages(response.content)] == [
                    (7, -32004)]
            assert len(r.table) == 0
            r.child.broken = None
            own_answer(await r.post(client, session, call(7)), 7, 'profile tool result')


def test_release_is_idempotent_and_leaves_no_residue():
    table = inflight_ids.InflightIds(max_entries=100)
    release, outcome = table.begin('p', 's', 1, 10)
    other, _ = table.begin('p', 's', 2, 10)
    assert outcome == inflight_ids.REGISTERED and len(table) == 2 and table.count('p') == 2
    release()
    release()  # the second call changes nothing of anyone else's
    assert len(table) == 1 and table.count('p') == 1
    other()
    assert len(table) == 0 and table.count('p') == 0 and table.held() == {}
    release, outcome = table.begin('p', 's', 1, 10)  # the id of a released entry is free again
    assert outcome == inflight_ids.REGISTERED
    release()


# ---- 5. the table's own rules (units) ----

def test_the_key_is_the_profile_the_session_and_the_string_form_of_the_id():
    table = inflight_ids.InflightIds(max_entries=100)
    release, outcome = table.begin('default', 's1', 7, 10)
    assert outcome == inflight_ids.REGISTERED
    assert table.begin('default', 's1', 7, 10) == (None, inflight_ids.DUPLICATE)
    assert table.begin('default', 's1', '7', 10) == (None, inflight_ids.DUPLICATE)
    for profile, session, ident in (('other', 's1', 7), ('default', 's2', 7), ('default', 's1', 8),
                                    ('default', 's1', '07')):
        each, outcome = table.begin(profile, session, ident, 10)
        assert outcome == inflight_ids.REGISTERED and each is not None, (profile, session, ident)
        each()
    release()
    assert len(table) == 0


def test_the_table_is_bounded_and_fails_open_for_the_whole_table():
    table = inflight_ids.InflightIds(max_entries=16)
    releases = [table.begin(f'p{n}', 's', 1, 16)[0] for n in range(16)]
    assert len(table) == 16 and all(releases)
    assert table.begin('p-new', 's', 1, 16) == (None, inflight_ids.TABLE_FULL)  # not registered, not refused
    assert table.begin('p0', 's', 1, 16) == (None, inflight_ids.DUPLICATE)  # a known entry is still a duplicate
    assert len(table) == 16
    releases[0]()
    release, outcome = table.begin('p-new', 's', 1, 16)
    assert outcome == inflight_ids.REGISTERED
    release()
    for each in releases[1:]:
        each()
    assert len(table) == 0


def test_one_profile_cannot_fill_the_table_for_the_others():
    table = inflight_ids.InflightIds(max_entries=64)
    releases = [table.begin('A', 's', n, 16)[0] for n in range(16)]
    assert all(releases) and table.count('A') == 16
    assert table.begin('A', 's2', 99, 16) == (None, inflight_ids.PROFILE_FULL)  # over its own limit: not registered
    release_b, outcome = table.begin('B', 's9', 1, 16)  # another profile still has its share and its protection
    assert outcome == inflight_ids.REGISTERED
    assert table.begin('B', 's9', 1, 16) == (None, inflight_ids.DUPLICATE)
    for each in (*releases, release_b):
        each()
    assert len(table) == 0 and table.held() == {}


def test_the_global_cap_holds_every_profile_the_add_on_can_run():
    """A request holds a forwarding slot as long as it holds its id, so a profile never has more ids than slots; the
    table's size is at least what every profile of the add-on could hold at once (contract 5, 2.8)."""
    for product, extras in profiles.EXTRA_PROFILE_LIMITS.items():
        needed = (profiles.DEFAULT_PROFILE_QUOTA.forward_slots
                  + profiles.EXTRA_PROFILE_QUOTA.forward_slots * min(profiles.MAX_EXTRA_PROFILES, extras))
        assert needed <= inflight_ids.MAX_ENTRIES, product


def test_an_id_longer_than_the_bound_is_not_registered():
    """O(1) on the event loop: the key is hashed and compared, so its size is bounded (the same 256 characters that
    request_limits.head_tail_id reads of an id); a client with such an id has no duplicate check, as before."""
    table = inflight_ids.InflightIds(max_entries=100)
    longest = 'x' * inflight_ids.MAX_ID_LENGTH
    release, outcome = table.begin('p', 's', longest, 10)
    assert outcome == inflight_ids.REGISTERED
    assert table.begin('p', 's', longest, 10) == (None, inflight_ids.DUPLICATE)
    assert table.begin('p', 's', longest + 'x', 10) == (None, inflight_ids.ID_TOO_LONG)
    assert table.begin('p', 's', 'x' * 1_000_000, 10) == (None, inflight_ids.ID_TOO_LONG)
    assert table.begin('p', 's', 10 ** 4299, 10) == (None, inflight_ids.ID_TOO_LONG)  # the longest number JSON allows
    assert table.begin('p', 's', -(10 ** 18), 10)[1] == inflight_ids.REGISTERED  # numbers of request_limits' size
    release()

    class Watched(set):
        looked_at = 0

        def __contains__(self, item):
            Watched.looked_at += 1
            return super().__contains__(item)
    table._entries = Watched()
    for too_long in ('x' * 1_000_000, 10 ** 4299, 2 ** 100_000):  # never hashed, never looked up: O(1)
        assert table.begin('p', 's', too_long, 10) == (None, inflight_ids.ID_TOO_LONG)
    assert Watched.looked_at == 0 and len(table) == 0


def test_the_environment_changes_nothing(monkeypatch):
    """HA's limits are program constants (contract 9 #45): the PaaS variable MCP_GATEWAY_MAX_INFLIGHT_IDS is not read."""
    monkeypatch.setenv('MCP_GATEWAY_MAX_INFLIGHT_IDS', '16')
    assert inflight_ids.InflightIds().max_entries == inflight_ids.MAX_ENTRIES == 512


def test_the_text_names_the_id_but_shows_a_bounded_escaped_form_of_it():
    assert inflight_ids.duplicate_text(7) == inflight_ids.duplicate_text('7') == PAPER_TEXT
    odd = 'it\'s a "quote"\n\\\u202e\U0001f600\x00\x1b[31m'
    text = inflight_ids.duplicate_text(odd)
    shown = ascii(odd)
    assert shown in text and '\n' not in text and '\u202e' not in text and '\x1b' not in text and '\x00' not in text
    assert text.count('\\u202e') == 2 and '\\U0001f600' in text  # shown twice (English, Chinese), escaped
    long = 'a' * 200
    text = inflight_ids.duplicate_text(long)
    assert 'a' * inflight_ids.SHOWN_ID_LENGTH in text and 'a' * (inflight_ids.SHOWN_ID_LENGTH + 1) not in text
    assert "... (200 characters)" in text and len(text) < 700
    huge = inflight_ids.duplicate_text('b' * 5_000_000)  # whatever the caller passes, the answer stays small
    assert len(huge) < 700 and '5000000 characters' in huge
    assert len(inflight_ids.duplicate_text('\U0001f600' * 5_000)) < 2000  # escaped characters count after the cut


# ---- 6. what a full table, a profile at its limit and a long id do ----

@MODES
async def test_a_full_table_lets_the_request_through_and_logs_one_line(tmp_path, log_scan, switch):
    async with rig(tmp_path, log_scan, switch) as r:
        fillers = [r.table.begin('filler', 's', n, 10 ** 9)[0] for n in range(inflight_ids.MAX_ENTRIES - len(r.table))]
        assert len(r.table) == inflight_ids.MAX_ENTRIES
        try:
            async with r.runtime.mcp() as client:
                session = await session_of(client, r.token)
                hold(r, 'sse')
                first = r.start(session, call(7))
                await until(lambda: r.child.client_calls() == [7])
                release_following(r)
                for _ in range(4):  # not registered, so not checked: sent like any request, today's behaviour
                    ponged(await r.post(client, session, ping(7)), 7)
                assert r.child.client_calls() == [7] and r.child.client_pings() == [7] * 4
                assert len(r.table) == inflight_ids.MAX_ENTRIES
                r.child.free.set()
                await asyncio.wait_for(first.task, 5)
            lines = warnings_about(log_scan, 'table of in-flight')
            assert len(lines) == 1, [line.getMessage() for line in lines]  # five requests, one line a minute
            message = lines[0].getMessage()
            assert message.startswith(f'MCP gateway [profile={profiles.log_id(r.profile)}]: ')
            assert str(inflight_ids.MAX_ENTRIES) in message and 'without the duplicate-id check' in message
        finally:
            for release in fillers:
                release()


@MODES
async def test_a_profile_at_its_limit_lets_the_request_through_and_logs_one_line(tmp_path, log_scan, switch):
    async with rig(tmp_path, log_scan, switch) as r:
        fillers = [r.table.begin(r.profile, 'filler', n, r.limit)[0] for n in range(r.limit)]
        assert all(fillers) and r.table.count(r.profile) == r.limit
        try:
            async with r.runtime.mcp() as client:
                session = await session_of(client, r.token)
                for _ in range(3):
                    own_answer(await r.post(client, session, call(7)), 7, 'profile tool result')
            lines = warnings_about(log_scan, 'in-flight JSON-RPC ids')
            assert len(lines) == 1, [line.getMessage() for line in lines]
            message = lines[0].getMessage()
            assert message.startswith(f'MCP gateway [profile={profiles.log_id(r.profile)}]: ')
            assert f'{r.limit} in-flight' in message and 'forwarding slots' in message
            assert r.table.count(r.profile) == r.limit
        finally:
            for release in fillers:
                release()


@MODES
async def test_an_id_longer_than_the_bound_goes_through_unchecked_and_logs_one_line(tmp_path, log_scan, switch):
    long = 'DUMMY-long-id-' + 'z' * inflight_ids.MAX_ID_LENGTH
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            hold(r, 'sse')
            first = r.start(session, call(long))
            await until(lambda: r.child.client_calls() == [long])
            assert len(r.table) == 0
            release_following(r)
            for _ in range(3):
                ponged(await r.post(client, session, ping(long)), long)
            assert r.child.client_calls() == [long] and r.child.client_pings() == [long] * 3
            r.child.free.set()
            await asyncio.wait_for(first.task, 5)
        lines = warnings_about(log_scan, 'longer than')
        assert len(lines) == 1 and str(inflight_ids.MAX_ID_LENGTH) in lines[0].getMessage()
        log_scan.watch(long, kind='secret')  # what the client chose never reaches a log record


# ---- 7. the log ----

@MODES
async def test_the_refusals_are_logged_once_a_minute_per_profile_without_the_id_or_the_session(tmp_path, log_scan, switch):
    ident = 'DUMMY-client-chosen-id-4711'
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            hold(r, 'sse')
            first = r.start(session, call(ident))
            await until(lambda: len(r.table) == 1)
            release_following(r)
            for _ in range(4):
                refused(await r.post(client, session, call(ident)), shown=f"'{ident}'")
            lines = warnings_about(log_scan, 'already in flight')
            assert len(lines) == 1, [line.getMessage() for line in lines]  # four refusals, one line
            message = lines[0].getMessage()
            assert message.startswith(f'MCP gateway [profile={profiles.log_id(r.profile)}]: ')
            assert 'HTTP 400' in message and '-32600' in message and 'suppressed' not in message
            reports = reports_of(r)
            base = reports.clock()
            reports.clock = lambda: base + 61  # the minute is over: the next line says how many it held back
            refused(await r.post(client, session, call(ident)), shown=f"'{ident}'")
            lines = warnings_about(log_scan, 'already in flight')
            assert len(lines) == 2 and lines[1].getMessage().endswith(' suppressed=3'), [
                line.getMessage() for line in lines]
            r.child.free.set()
            await asyncio.wait_for(first.task, 5)
        log_scan.watch(session, ident, kind='secret')  # neither the session id nor the client's id is ever logged


@MODES
async def test_the_refusal_names_a_long_id_in_a_bounded_escaped_form(tmp_path, log_scan, switch):
    ident = ('q"\'\\\n' + 'k' * 195)[:inflight_ids.MAX_ID_LENGTH]  # a long id with a newline, quotes and a backslash
    async with rig(tmp_path, log_scan, switch) as r:
        async with r.runtime.mcp() as client:
            session = await session_of(client, r.token)
            hold(r, 'sse')
            first = r.start(session, call(ident))
            await until(lambda: len(r.table) == 1)
            release_following(r)
            response = await r.post(client, session, call(ident))
            message = refused(response, shown=ascii(ident[:inflight_ids.SHOWN_ID_LENGTH]))['error']['message']
            assert '... (%d characters)' % len(ident) in message and '\n' not in message and len(message) < 700
            assert 'k' * 100 not in message  # the id's tail is not echoed
            for secret in (r.token, session, r.profile, 'profile=', LABELS[B]):
                assert secret not in message and secret not in response.text, secret
            r.child.free.set()
            await asyncio.wait_for(first.task, 5)


# ---- 8. the contract says it ----

def test_the_contract_describes_the_duplicate_id_rule():
    text = (ROOT / 'docs/multi-profile/contract.md').read_text(encoding='utf-8')
    section = re.search(r'^### 2\.8 .*?(?=^##? )', text, re.S | re.M)
    assert section, 'contract.md has no section 2.8'
    for needle in ('Mcp-Session-Id', 'str(id)', '-32600', '"id": null', '進行中', 'inflight_ids', 'initialize', 'GET',
                   'DELETE', str(inflight_ids.MAX_ENTRIES), str(inflight_ids.MAX_ID_LENGTH), 'batch', '#134'):
        assert needle in section.group(0), needle
    assert re.search(r'^\| 134 \|', text, re.M), 'section 9 has no row 134'
    assert re.search(r'^\| JSON-RPC `-32600` \| 400 \|', text, re.M), 'section 4.2 has no -32600 row'
    assert '不受開關管變更：同一個 session 內進行中的 JSON-RPC id 不可重複' in text  # section 1.2
