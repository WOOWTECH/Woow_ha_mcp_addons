"""HM-23: EMQX with additional profiles (multi-profile plan 9 EMQX row, 12.3 HM-21 to HM-26; DQ-27 as the plan
recommends it, UC-22; acceptance T-04, T-05, T-07, T-23; FM-37, FM-92; contract section 9 #54, #65, #130).

Each EMQX profile has its own child, bearer, backend credentials and saved policy. The gateway and child both enforce
policy; the child reads its bound state for every tool list and call. The fixed read-only health probe remains callable
at the child even when publicly disabled. Policy saves restart only the affected child. These tests use real children
and synthetic brokers to cover profile isolation, direct child bearer calls and both profile switch modes.

The brokers listen on this runner's private address, not on loopback: a switched-on product's child refuses a loopback
backend (HM-20) and this test keeps that rule in force (tests/test_real_products.py's Headscale fixture does the same).
Switched on, every running profile's health monitor asks its own broker for the nodes every HEALTH_INTERVAL, whatever
the test does (PROBE): a check that a broker was asked nothing else leaves those requests out (HM-23 review MF-1).
"""
import asyncio
import base64
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import socket
import threading

import httpx
import pytest

from admin_write_headers import reviewed_headers
from lifecycle_runtime import until
from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import health as health_module, lifecycle, profiles
from mcp_admin_core.products import DENY_LOOPBACK_ENV, health_probe
from multi_profile_runtime import (all_tokens, create_profile, free_port, ids, multi_profile_runtime, stored,
                                   update_profile)
from test_backend_loopback import environment_facts, running_its_program
from test_child_bearer import assert_refused, refusals, send
from test_single_profile_golden import ACCEPT, ADMIN, BEARER_REQUIRED, NOT_FOUND, answer, initialize_message
from tool_refusal import refused

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'emqx'
B, C = ids(2)
LABELS = {B: 'Broker Beta', C: 'Broker Gamma'}
NAMES = {'default': 'default', B: 'beta', C: 'gamma'}
# The restricted profile B: no write grant (the gateway refuses every write; contract #130) and one read tool off;
# C keeps every tool but one operation of a mixed tool; both gateway and child refuse it.
B_POLICY = {'writes_enabled': False, 'enabled_write_tools': [], 'disabled': ['emqx_list_clients', 'emqx_cluster_status']}
C_DENIED = {'emqx_manage_authn_users': ['delete']}
DELETE_USER = {'operation': 'delete', 'user_id': 'u-hm23'}
UP_SECONDS = 90  # three real children, the additional ones staggered (HM-09)
# The health monitor's probe (products.health_probe: emqx_cluster_status, the child's GET /nodes), which every running
# profile's monitor sends its own broker every HEALTH_INTERVAL; the diagonal (T-04) takes emqx_broker_stats (GET
# /stats), which nothing else calls.
PROBE_TOOL, PROBE = 'emqx_cluster_status', ('GET', '/api/v5/nodes')
DIAGONAL_TOOL, DIAGONAL = 'emqx_broker_stats', ('GET', '/api/v5/stats')


def credentials(profile_id):
    """A profile's synthetic API key and secret (tests/fixtures/owner_defaults/README.md: DUMMY- values)."""
    name = NAMES[profile_id]
    return f'DUMMY-emqx-{name}-key', f'DUMMY-emqx-{name}-secret'


def private_host():
    """This runner's own private address (a switched-on product's child refuses loopback: HM-20)."""
    host = socket.gethostbyname(socket.gethostname())
    assert not host.startswith('127.'), 'the runner has no private address for the fake brokers'
    return host


class Broker:
    """One profile's fake EMQX REST API (/api/v5) on the runner's private address: it answers only its own profile's
    API key (HTTP Basic), records every request, and answers a cluster status the child accepts."""

    def __init__(self, profile_id):
        key, secret = credentials(profile_id)
        self.expected = 'Basic ' + base64.b64encode(f'{key}:{secret}'.encode()).decode()
        self.requests = []
        broker = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def respond(self):
                length = int(self.headers.get('Content-Length') or 0)
                if length:
                    self.rfile.read(length)
                own = self.headers.get('Authorization') == broker.expected
                broker.requests.append((self.command, self.path.split('?')[0], own))
                if not own:
                    status, value = 401, {'code': 'BAD_API_KEY_OR_SECRET'}
                elif self.path.split('?')[0].endswith('/nodes'):
                    status, value = 200, [{'node': 'emqx@hm23.invalid', 'version': '5.8.9', 'node_status': 'running'}]
                else:
                    status, value = 200, {'data': [], 'meta': {'count': 0}}
                body = json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = do_PUT = do_DELETE = respond

        self.server = ThreadingHTTPServer((private_host(), 0), Handler)
        self.server.daemon_threads = True
        self.url = f'http://{self.server.server_address[0]}:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def since(self, count):
        return self.requests[count:]

    def asked(self, count):
        """The requests since count but the health monitor's probes (PROBE), which come at their own pace."""
        return [request for request in self.requests[count:] if request[:2] != PROBE]


@contextmanager
def brokers():
    made = {}
    try:
        for profile_id in ('default', B, C):
            made[profile_id] = Broker(profile_id)
        yield made
    finally:
        for broker in made.values():
            broker.close()


def connection(profile_id, broker):
    key, secret = credentials(profile_id)
    return {'url': broker.url, 'api_key': key, 'api_secret': secret}


def setup(tmp_path, made):
    """The default profile and two additional ones, each on its own broker with its own key; B restricted, C with one
    operation denied. Returns the data directory; the ports are free loopback ports (the children's own)."""
    data = tmp_path / 'data'
    update_profile(data, PRODUCT, 'default', connection=connection('default', made['default']))
    for profile_id in (B, C):
        create_profile(data, PRODUCT, profile_id, label=LABELS[profile_id], port=free_port(), configured=False)
        update_profile(data, PRODUCT, profile_id, connection=connection(profile_id, made[profile_id]))
    update_profile(data, PRODUCT, B, **B_POLICY)
    update_profile(data, PRODUCT, C, denied_operations=C_DENIED)
    return data


def watch(log_scan, data):
    log_scan.watch(*all_tokens(data))
    log_scan.watch(*LABELS.values(), kind='name')
    log_scan.watch(*(value for profile_id in NAMES for value in credentials(profile_id)), kind='secret')


def paths(token):
    return (('/mcp', {**ACCEPT, 'Authorization': 'Bearer ' + token}), (f'/private_{token}/mcp', dict(ACCEPT)))


def entries(runtime, profile_ids=('default', B, C)):
    return {profile_id: runtime.manager.get(profile_id).runtime for profile_id in profile_ids}


async def all_up(entries_by_id):
    await until(lambda: all(running_its_program(entry.supervisor) and entry.health.availability()['ready']
                            for entry in entries_by_id.values()), timeout=UP_SECONDS, step=0.1)


def child_url(entry):
    return entry.child_url


def env_policy(entry):
    env = entry.supervisor.spec.env
    return env['EMQX_MCP_READONLY'], sorted(filter(None, env['EMQX_MCP_DISABLED_TOOLS'].split(',')))


async def child_session(client, url, token):
    """A session the child at url opens for its own child bearer: its session id."""
    response, result = await send(client, 'POST', url, ['Bearer ' + token], message=initialize_message(5))
    assert response.status_code == 200 and result['protocolVersion'], response.status_code
    return response.headers['mcp-session-id']


async def child_tools(client, url, token):
    """The child's own tools/list for its own child bearer (the policy its launch environment gave it)."""
    session = await child_session(client, url, token)
    response, _ = await send(client, 'POST', url, ['Bearer ' + token],
                             message={'jsonrpc': '2.0', 'method': 'notifications/initialized'}, session=session)
    assert response.status_code == 202
    response, listed = await send(client, 'POST', url, ['Bearer ' + token],
                                  message={'jsonrpc': '2.0', 'id': 6, 'method': 'tools/list'}, session=session)
    assert response.status_code == 200
    return {tool['name'] for tool in listed['tools']}


async def knows_session(client, url, token, session):
    """Whether the child at url knows session (asked with its own child bearer): 200 for a ping in it."""
    response, _ = await send(client, 'POST', url, ['Bearer ' + token],
                             message={'jsonrpc': '2.0', 'id': 7, 'method': 'ping'}, session=session)
    return response.status_code == 200


async def mcp_session(client, path, headers):
    response = await client.post(path, headers=headers, json=initialize_message())
    assert response.status_code == 200, response.status_code
    session = response.headers['mcp-session-id']
    in_session = {**headers, 'Mcp-Session-Id': session, 'MCP-Protocol-Version': result_of(response)['protocolVersion']}
    assert (await client.post(path, headers=in_session, json={'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            ).status_code == 202
    return session, in_session


async def tool_call(client, path, headers, name, arguments, ident=9):
    return await client.post(path, headers=headers, json={'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
                                                         'params': {'name': name, 'arguments': arguments}})


def result_of(response):
    """The JSON-RPC result of a 200 tools/call answer (a JSON body or one SSE message)."""
    assert response.status_code == 200, response.status_code
    if response.headers.get('content-type', '').startswith('text/event-stream'):
        data = [line[5:].strip() for line in response.text.splitlines() if line.startswith('data:')]
        return json.loads(data[-1]).get('result')
    return response.json().get('result')


async def listed_names(client, path, headers):
    response = await client.post(path, headers=headers, json={'jsonrpc': '2.0', 'id': 8, 'method': 'tools/list'})
    return {tool['name'] for tool in result_of(response)['tools']}


async def save_policy(runtime, profile_id, policy):
    async with runtime.admin(profile_id) as admin:
        boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
        return await admin.put('/api/policy', json=policy, headers=reviewed_headers(boot, ADMIN))


@pytest.fixture(autouse=True)
def quick_health(monkeypatch):
    """Every profile's first health checks within a second (HM-09 staggers them over the interval)."""
    monkeypatch.setattr(health_module, 'HEALTH_INTERVAL', 0.5)
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: None)
    monkeypatch.setattr(profiles, 'available_memory_mib', lambda: 4096)


async def test_switched_on_each_profile_has_its_own_child_broker_and_policy(tmp_path, log_scan):
    assert health_probe(PRODUCT) == (PROBE_TOOL, {})  # PROBE is its request; the diagonal's tool is another one
    with brokers() as made:
        data = setup(tmp_path, made)
        watch(log_scan, data)
        async with multi_profile_runtime(PRODUCT, data, supervisor=lifecycle.Supervisor, real_children=True,
                                         default_port=free_port()) as runtime:
            running = entries(runtime)
            await all_up(running)
            states = {profile_id: stored(runtime.directory(profile_id)) for profile_id in running}
            tokens = {profile_id: state['token'] for profile_id, state in states.items()}
            children = {profile_id: state['child_token'] for profile_id, state in states.items()}
            assert len(set(tokens.values())) == len(set(children.values())) == 3

            # Each child: the switched-on environment (HM-20), its own profile's policy, nothing of another profile.
            for profile_id, entry in running.items():
                env = entry.supervisor.spec.env
                assert env[DENY_LOOPBACK_ENV] == '1' and environment_facts(entry.supervisor)[0] == b'1', profile_id
                key, secret = credentials(profile_id)
                assert (env['EMQX_MCP_BASE_URL'], env['EMQX_MCP_API_KEY'], env['EMQX_MCP_API_SECRET']) == (
                    made[profile_id].url, key, secret), profile_id
                assert env['WOOW_MCP_CHILD_TOKEN'] == children[profile_id], profile_id
                others = [value for other in running if other != profile_id
                          for value in (*credentials(other), tokens[other], children[other], made[other].url)]
                assert not any(value in text for value in others for text in env.values()), profile_id
                # Each child can read only its own profile's policy path as configured by the launcher.
                assert 'MCP_ADMIN_CONFIG' not in env and 'EMQX_MCP_DISABLED_OPERATIONS' not in env, profile_id
                assert env['EMQX_MCP_STATE_PATH'] == str(runtime.directory(profile_id) / 'state.json')
                assert not any(profiles.INDEX_NAME in text for text in env.values()), profile_id
            assert env_policy(running['default']) == ('false', [])
            readonly, disabled = env_policy(running[B])
            # B has no write grant, yet its child runs with READONLY false: the mixed tools (authn users, authz rules)
            # stay registered for their read operation; both gateway and child check write grants. A read-only backend key
            # remains useful defense in depth (UC-22).
            assert readonly == 'false' and 'emqx_list_clients' in disabled and 'emqx_publish' in disabled
            assert env_policy(running[C]) == ('false', [])  # C's denied operation is not the child's to know

            async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=30) as direct:
                # T-23: each child serves its own child bearer only (none, empty, malformed, another profile's, two
                # headers: 401 with no body), and its own opens a session.
                for profile_id, entry in running.items():
                    other = children[B if profile_id != B else C]
                    for case, values in refusals(children[profile_id], other).items():
                        assert_refused(*await send(direct, 'POST', child_url(entry), values,
                                                   message=initialize_message()), f'{NAMES[profile_id]}: {case}')
                    await child_session(direct, child_url(entry), children[profile_id])
                # Each child's own tool list is its own profile's policy (READONLY, DISABLED_TOOLS).
                native = {profile_id: await child_tools(direct, child_url(entry), children[profile_id])
                          for profile_id, entry in running.items()}
                assert 'emqx_list_clients' in native['default'] and 'emqx_publish' in native['default']
                assert 'emqx_list_clients' not in native[B] and 'emqx_publish' not in native[B]
                assert PROBE_TOOL in native[B]  # the health probe's tool stays registered (child_spec)
                assert 'emqx_manage_authn_users' in native[B]  # a mixed tool, for its read operation (see above)
                assert 'emqx_manage_authn_users' in native[C] and native[C] == native['default']
                # B disables the public probe, but the private health monitor must still reach it.
                probe_session = await child_session(direct, child_url(running[B]), children[B])
                await send(direct, 'POST', child_url(running[B]), ['Bearer ' + children[B]],
                           message={'jsonrpc': '2.0', 'method': 'notifications/initialized'}, session=probe_session)
                _, probe = await send(direct, 'POST', child_url(running[B]), ['Bearer ' + children[B]],
                                      message={'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
                                               'params': {'name': PROBE_TOOL, 'arguments': {}}}, session=probe_session)
                assert probe['isError'] is False

                # A caller with the child bearer still cannot bypass B's grants or C's operation deny.
                for profile_id, args in ((B, {'operation': 'create', 'user_id': 'u', 'password': 'p'}),
                                         (C, DELETE_USER)):
                    entry = running[profile_id]
                    session = await child_session(direct, child_url(entry), children[profile_id])
                    await send(direct, 'POST', child_url(entry), ['Bearer ' + children[profile_id]],
                               message={'jsonrpc': '2.0', 'method': 'notifications/initialized'}, session=session)
                    before = len(made[profile_id].requests)
                    _, denied = await send(direct, 'POST', child_url(entry), ['Bearer ' + children[profile_id]],
                                           message={'jsonrpc': '2.0', 'id': 8, 'method': 'tools/call',
                                                    'params': {'name': 'emqx_manage_authn_users', 'arguments': args}},
                                           session=session)
                    assert denied['isError'] is True
                    assert 'EMQX_POLICY_DENIED' in str(denied)
                    assert not any('/authentication/' in path for _, path, _ in made[profile_id].since(before))

                # Change C's saved policy without restarting: the same child session sees revocation and re-enable.
                path = runtime.directory(C) / 'state.json'
                original = path.read_bytes()
                def replace_state(raw):
                    temporary = path.with_name('test-state.tmp')
                    temporary.write_bytes(raw)
                    temporary.chmod(0o600)
                    os.replace(temporary, path)
                session = await child_session(direct, child_url(running[C]), children[C])
                await send(direct, 'POST', child_url(running[C]), ['Bearer ' + children[C]],
                           message={'jsonrpc': '2.0', 'method': 'notifications/initialized'}, session=session)
                async def direct_stats():
                    return await send(direct, 'POST', child_url(running[C]), ['Bearer ' + children[C]],
                                      message={'jsonrpc': '2.0', 'id': 10, 'method': 'tools/call',
                                               'params': {'name': DIAGONAL_TOOL, 'arguments': {}}}, session=session)
                try:
                    changed = json.loads(original)
                    changed['disabled'].append(DIAGONAL_TOOL)
                    replace_state(json.dumps(changed).encode())
                    _, denied = await direct_stats()
                    assert denied['isError'] and 'EMQX_POLICY_DENIED' in str(denied)
                    replace_state(b'{broken')
                    _, denied = await direct_stats()
                    assert denied['isError'] and 'EMQX_POLICY_UNAVAILABLE' in str(denied)
                    changed = json.loads(original)
                    changed['connection']['api_key'] = 'wrong-key'
                    replace_state(json.dumps(changed).encode())
                    _, denied = await direct_stats()
                    assert denied['isError'] and 'EMQX_POLICY_UNAVAILABLE' in str(denied)
                    replace_state(original)
                    path.chmod(0o640)
                    _, denied = await direct_stats()
                    assert denied['isError'] and 'EMQX_POLICY_UNAVAILABLE' in str(denied)
                    replace_state(original)
                    _, allowed = await direct_stats()
                    assert allowed['isError'] is False
                finally:
                    replace_state(original)

                async with runtime.mcp() as client:
                    # T-05: each token, on both paths, opens a session with its own child and with no other.
                    sessions = {}
                    for profile_id in running:
                        for path, headers in paths(tokens[profile_id]):
                            session, in_session = await mcp_session(client, path, headers)
                            assert not session.startswith('woow-local-'), (NAMES[profile_id], path[:9])
                            owners = [other for other, entry in running.items()
                                      if await knows_session(direct, child_url(entry), children[other], session)]
                            assert owners == [profile_id], (NAMES[profile_id], path[:9])
                            sessions.setdefault(profile_id, (path, in_session))
                    # A token no profile holds gets HM-01's bytes on both paths; so does another profile's session.
                    for token in ('T' * 43, 'C' * 43, children['default']):
                        found = [answer(await client.post(path, headers=headers, json=initialize_message()))
                                 for path, headers in paths(token)]
                        assert found == [BEARER_REQUIRED, NOT_FOUND]
                    path, default_session = sessions['default']
                    for profile_id in (B, C):
                        for other_path, headers in paths(tokens[profile_id]):
                            crossed = await client.post(other_path, json={'jsonrpc': '2.0', 'id': 3, 'method': 'ping'},
                                                        headers={**headers,
                                                                 'Mcp-Session-Id': default_session['Mcp-Session-Id']})
                            assert crossed.status_code == 404, (NAMES[profile_id], other_path[:9])

                    # T-04: every call reaches its own profile's broker only, with that profile's key: a tool the health
                    # monitor never calls (DIAGONAL), so the brokers asked are exactly those the call reached.
                    for profile_id, (path, headers) in sessions.items():
                        before = {other: len(broker.requests) for other, broker in made.items()}
                        result = result_of(await tool_call(client, path, headers, DIAGONAL_TOOL, {}))
                        assert result['isError'] is False, NAMES[profile_id]
                        asked = {NAMES[other]: broker.asked(before[other]) for other, broker in made.items()}
                        assert asked == {name: [(*DIAGONAL, True)] if name == NAMES[profile_id] else []
                                         for name in asked}, NAMES[profile_id]
                    assert all(own for broker in made.values() for _, _, own in broker.requests)  # the probes too

                    # Each profile's policy at the gateway: B's disabled tool is unknown to B and reaches no broker,
                    # the default profile still has it; C's denied operation is refused at the gateway and child; the default
                    # profile's same call reaches its broker. No broker is asked anything
                    # but its health probes (asked) while the gateway refuses.
                    listed = {profile_id: await listed_names(client, *sessions[profile_id]) for profile_id in sessions}
                    assert 'emqx_list_clients' in listed['default'] and 'emqx_list_clients' not in listed[B]
                    assert 'emqx_publish' not in listed[B] and listed[C] == listed['default']
                    before = {other: len(broker.requests) for other, broker in made.items()}
                    assert refused(await tool_call(client, *sessions[B], 'emqx_list_clients', {}), 'Unknown tool')
                    assert refused(await tool_call(client, *sessions[C], 'emqx_manage_authn_users', DELETE_USER),
                                   'Operation not permitted')
                    asked = {NAMES[other]: broker.asked(before[other]) for other, broker in made.items()}
                    assert asked == {name: [] for name in asked}
                    served = result_of(await tool_call(client, *sessions['default'], 'emqx_list_clients', {}))
                    assert served['isError'] is False
                    await tool_call(client, *sessions['default'], 'emqx_manage_authn_users', DELETE_USER)
                    assert [method for method, path_, _ in made['default'].since(before['default'])
                            if '/authentication/' in path_] == ['DELETE']
                    assert made[B].asked(before[B]) == [] and made[C].asked(before[C]) == []

                    # T-07: saving B's policy relaunches B's child alone, with B's new policy.
                    pids = {profile_id: entry.supervisor.process.pid for profile_id, entry in running.items()}
                    starts = {profile_id: entry.supervisor.starts for profile_id, entry in running.items()}
                    envs = {profile_id: dict(entry.supervisor.spec.env) for profile_id, entry in running.items()}
                    default_state = (data / 'state.json').read_bytes()
                    c_state = (runtime.directory(C) / 'state.json').read_bytes()
                    saved = await save_policy(runtime, B, {'writes_enabled': False, 'enabled_write_tools': [],
                                                           'disabled': ['emqx_list_topics']})
                    assert saved.status_code == 200 and saved.json()['saved'] is True, saved.status_code
                    assert saved.json()['profile'] == {'id': B}
                    await all_up(running)
                    assert running[B].supervisor.starts == starts[B] + 1
                    assert running[B].supervisor.process.pid != pids[B]
                    for profile_id in ('default', C):
                        assert running[profile_id].supervisor.starts == starts[profile_id], NAMES[profile_id]
                        assert running[profile_id].supervisor.process.pid == pids[profile_id], NAMES[profile_id]
                        assert running[profile_id].supervisor.spec.env == envs[profile_id], NAMES[profile_id]
                    readonly, disabled = env_policy(running[B])
                    assert readonly == 'false' and 'emqx_list_topics' in disabled
                    assert 'emqx_list_clients' not in disabled
                    assert 'emqx_publish' in disabled
                    assert (data / 'state.json').read_bytes() == default_state
                    assert (runtime.directory(C) / 'state.json').read_bytes() == c_state
                    path, headers = paths(tokens[B])[0]
                    _, b_session = await mcp_session(client, path, headers)
                    after = await listed_names(client, path, b_session)
                    assert 'emqx_list_topics' not in after and 'emqx_list_clients' in after
                    assert await listed_names(client, *sessions['default']) == listed['default']
                    assert 'emqx_list_topics' not in await child_tools(direct, child_url(running[B]), children[B])


async def test_switched_off_only_the_default_profile_serves(tmp_path, log_scan):
    """The same data on disk with the product switched off: the add-on is the single-profile one. Only the default
    profile's child runs (no WOOW_MCP_DENY_LOOPBACK, HM-20); B's and C's tokens are any unknown token's on both paths
    (the boot guard revoked them: HM-13b, plan 3.3), and their brokers are never asked; the panel names no profile and a
    policy save relaunches the default profile's child with the new policy, as before HM-23."""
    built = []

    class Recorded(lifecycle.Supervisor):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            built.append(self)

    with brokers() as made:
        data = setup(tmp_path, made)
        watch(log_scan, data)
        issued = {profile_id: stored(profiles.Layout(data).profile(profile_id))['token'] for profile_id in (B, C)}
        port = free_port()
        async with multi_profile_runtime(PRODUCT, data, supervisor=Recorded, real_children=True,
                                         default_port=port, switch=False) as runtime:
            assert runtime.manager is None and len(built) == 1  # the default profile's runtime alone
            supervisor, = built
            await until(lambda: running_its_program(supervisor), timeout=UP_SECONDS, step=0.1)
            assert DENY_LOOPBACK_ENV not in supervisor.spec.env and environment_facts(supervisor)[0] is None
            token = stored(data)['token']
            async with runtime.mcp() as client:
                for path, headers in paths(token):
                    await until_ready(client, path, headers)
                # The default child serves its own child bearer only, another profile's (renewed by the guard) too.
                own, other = stored(data)['child_token'], stored(profiles.Layout(data).profile(B))['child_token']
                async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=30) as direct:
                    url = f'http://127.0.0.1:{port}/mcp'
                    for case, values in refusals(own, other).items():
                        assert_refused(*await send(direct, 'POST', url, values, message=initialize_message()), case)
                    await child_session(direct, url, own)
                for profile_id in (B, C):
                    assert stored(profiles.Layout(data).profile(profile_id))['token'] is None
                    found = [answer(await client.post(path, headers=headers, json=initialize_message()))
                             for path, headers in paths(issued[profile_id])]
                    assert found == [BEARER_REQUIRED, NOT_FOUND], NAMES[profile_id]
                starts, pid = supervisor.starts, supervisor.process.pid
                async with runtime.admin() as admin:
                    boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
                    assert 'profile' not in boot and 'profiles_supported' not in boot
                    saved = await admin.put('/api/policy',
                                            json={'writes_enabled': True, 'disabled': ['emqx_list_topics']},
                                            headers=reviewed_headers(boot, ADMIN))
                assert saved.status_code == 200 and saved.json()['saved'] is True and 'profile' not in saved.json()
                await until(lambda: running_its_program(supervisor) and supervisor.starts == starts + 1,
                            timeout=UP_SECONDS, step=0.1)
                assert supervisor.process.pid != pid and len(built) == 1
                assert 'emqx_list_topics' in supervisor.spec.env['EMQX_MCP_DISABLED_TOOLS'].split(',')
                path, headers = paths(token)[0]
                await until_ready(client, path, headers)
                _, in_session = await mcp_session(client, path, headers)
                assert 'emqx_list_topics' not in await listed_names(client, path, in_session)
        assert made[B].requests == [] and made[C].requests == []


async def until_ready(client, path, headers):
    """Until the token's initialize is answered by the child itself (not the gateway's own local session)."""
    async with asyncio.timeout(UP_SECONDS):
        while True:
            response = await client.post(path, headers=headers, json=initialize_message())
            if response.status_code == 200 and not response.headers.get('mcp-session-id', '').startswith('woow-local-'):
                return
            await asyncio.sleep(0.1)
