"""HM-21 (multi-profile plan 9 LiteLLM row, 12.3 HM-21～HM-26; FM-87; DQ-40 ⑨ and ⑩; contract section 9 #64 and the
HM-21 rows; acceptance T-04, T-05, T-07, T-23): LiteLLM with profiles, each profile holding its own LiteLLM key.

Plan 9 (and PaaS: research R06 3.4, PR-litellm-01): LiteLLM needs no program of its own for profiles. A profile's
LiteLLM account is the key it holds (a proxy_admin_viewer user's key or a virtual key limited to some models; the
panel already advises against the master key), so the docs recommend a different virtual key for each profile.
Changing the key or the URL never rotates the MCP token: LiteLLM is not in products.IDENTITY_BOUND (DQ-40 ⑩ names
Odoo, Nextcloud and Hermes), as PaaS keeps the token when the key changes. Once switched on, a URL moved to another
origin needs the key again (DQ-40 ⑨: tests/test_new_origin_secret.py, every product).

These tests prove that the shared multi-profile code does what LiteLLM needs, with the real LiteLLM children (each in
apps/litellm/.venv, started by run_product's ProfileManager through the real Supervisor, the switch on for the test
only) and one fake LiteLLM gateway (FakeLiteLLM) that knows two virtual keys, each limited to its own model, the later
HAOS case (two model-limited keys on the same LiteLLM). The fake gateway listens on this host's private address, not
on loopback: a switched-on child refuses a loopback backend (HM-20, WOOW_MCP_DENY_LOOPBACK) and keeps that rule here.

- Switched on, two keys on one gateway (T-04): each profile's MCP token, on both connection methods, lists only its own
  key's model; every backend request carries one of the two keys, each profile's child its own (its spec's
  environment); N x N, only the diagonal.
- Switched on, across profiles (T-05): a child token, a virtual key, a random token and a revoked profile token get the
  gateway's own 401 (Bearer) and 404 (secret URL), byte for byte; X-MCP-Profile and, on the secret URL, Authorization
  never choose the profile; a session of one profile is unknown (404) with another profile's token. A revoked profile
  token is refused while the other profile keeps its models.
- Switched on, the child bearer (T-23, HM-06): straight to each real child, every other form (none, the other profile's
  child token, an empty value, two headers...) gets 401 and no session; its own child token opens one.
- Switched on, the backend pool (contract section 9, the HM-21 row on LiteLLM's backend connections): each profile's
  child keeps its own pool of at most four backend connections (backend_policy's transport; the 50 lifespan.py asks
  for is dropped): a fifth and sixth call of one profile wait in that profile's pool, and another profile is served
  meanwhile. HM-21 does not change the limit: the owner decides (provenance note).
- Switched on, the policy of each profile (T-07, FM-87): saving B's policy (every write grant revoked, one read tool
  off) restarts B's child alone, which then runs read-only (LITELLM_MCP_READONLY=true: PaaS's per-profile read-only
  setting; HA's grants are exact per tool, policy_contract woow-v3-exact-grants) without that tool;
  the default profile's child keeps its PID, its tools and its writes; the default profile's state is not written. The
  other way round too.
- Switched off (the repository today; the test switches LiteLLM off itself, whatever the repository says), the same
  data on disk: the default profile alone is served, with its own key;
  B's profile is dormant (HM-13b: its token revoked before anything is served, its child never started, its key never
  sent); /api/profiles is unknown; saving the default profile's policy restarts its child as today.
- In both modes: each profile's child spec differs from another's only in the key, the child token, the working
  directory, the port and the policy's two variables; a new key or URL never rotates the MCP token.

Every test runs under the HM-01 log scan (tokens, child tokens, both virtual keys and the profile label watched). The
virtual keys and model names follow tests/fixtures/owner_defaults/README.md (DUMMY- values); tokens are made at run time.
"""
import asyncio
import collections
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import threading
from urllib.parse import urlsplit

import pytest

from admin_write_headers import reviewed_headers
from lifecycle_runtime import until
from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import create_profile, free_port, ids, multi_profile_runtime, stored, update_profile
from mcp_admin_core import features, health as health_module, identity_fields, lifecycle, products, profiles, run_product
from mcp_admin_core.health import protocol_reply
from mcp_admin_core.policy import enabled as policy_enabled  # products.child_spec's own rule
from mcp_admin_core.products import DENY_LOOPBACK_ENV, IDENTITY_BOUND, TOOLS, ProductStore, child_spec, identity_rebound
from test_backend_loopback import running_its_program
from test_child_bearer import assert_refused, refusals, send
from test_single_profile_golden import (ACCEPT, ADMIN, BEARER_REQUIRED, GENUINE_CLIENT, NOT_FOUND, answer,
                                        initialize_message)
from tool_refusal import refused

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'litellm'
B = ids(1)[0]
LABEL = 'LiteLLM Beta Desk'
# Two virtual keys of one LiteLLM, each limited to its own model (fake values, DUMMY-).
KEYS = {'default': 'DUMMY-hm21-virtual-key-default', B: 'DUMMY-hm21-virtual-key-beta'}
MODELS = {'default': ['DUMMY-hm21-model-default'], B: ['DUMMY-hm21-model-beta']}
LIST, INFO = 'litellm_list_models', 'litellm_model_info'
POOL = 4  # backend_policy.AsyncTransport: max_connections=4 for every child's backend client
CHILD_SECONDS = 60  # both real children started and their first health check passed


@pytest.fixture(autouse=True)
def memory_readings(monkeypatch):
    """The memory check of a save (contract 5) reads the test's values: no cgroup limit, 4 GiB available."""
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: None)
    monkeypatch.setattr(profiles, 'available_memory_mib', lambda: 4096)


# ---- the fake LiteLLM gateway ----

def private_host():
    """This host's private address: a switched-on child refuses loopback backends (HM-20), as in production."""
    host = socket.gethostbyname(socket.gethostname())
    address = ipaddress.ip_address(host)
    assert (address.version == 4 and address.is_private and not address.is_loopback and not address.is_link_local
            and products.allowed_address(host)), 'the fake LiteLLM gateway needs a private address'
    return host


class FakeLiteLLM:
    """One LiteLLM gateway with two virtual keys (KEYS), each limited to its own models (MODELS), as a LiteLLM proxy
    answers a model-limited key: GET /v1/models and GET /model/info list that key's models only; any other key or none
    gets 401. It records, for every request, which profile's key it carried (None: no known key) and the path, never the
    key itself. hold(profile) keeps that key's /model/info requests waiting until release(); in_flight and peak count
    them (the backend pool test)."""

    def __init__(self):
        self.requests = []
        self.lock = threading.Lock()
        self.in_flight = collections.Counter()
        self.peak = collections.Counter()
        self.held = {}

    def profile_of(self, values):
        found = [profile for profile, key in KEYS.items() if values == ['Bearer ' + key]]
        return found[0] if found else None

    def hold(self, profile):
        self.held[profile] = threading.Event()

    def release(self, profile):
        self.held.pop(profile).set()

    def seen(self):
        with self.lock:
            return list(self.requests)

    @contextmanager
    def serving(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # never print a request line

            def reply(self, status, value):
                data = json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                profile = fake.profile_of(self.headers.get_all('Authorization') or [])
                path = urlsplit(self.path).path
                with fake.lock:
                    fake.requests.append((profile, path))
                if profile is None:
                    return self.reply(401, {'error': {'message': 'Authentication Error', 'type': 'auth_error',
                                                      'param': 'None', 'code': '401'}})
                if path == '/v1/models':
                    return self.reply(200, {'object': 'list', 'data': [
                        {'id': model, 'object': 'model', 'created': 0, 'owned_by': 'openai'}
                        for model in MODELS[profile]]})
                if path == '/model/info':
                    with fake.lock:
                        fake.in_flight[profile] += 1
                        fake.peak[profile] = max(fake.peak[profile], fake.in_flight[profile])
                        held = fake.held.get(profile)
                    try:
                        if held is not None:
                            held.wait(30)
                        return self.reply(200, {'data': [
                            {'model_name': model, 'litellm_params': {'model': 'openai/' + model},
                             'model_info': {'id': model + '-deployment'}} for model in MODELS[profile]]})
                    finally:
                        with fake.lock:
                            fake.in_flight[profile] -= 1
                return self.reply(404, {'detail': 'Not Found'})

        server = ThreadingHTTPServer((private_host(), 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f'http://{server.server_address[0]}:{server.server_port}'
        finally:
            for event in list(self.held.values()):
                event.set()
            server.shutdown()
            server.server_close()
            thread.join(10)


# ---- the add-on: the default profile and B, two keys on one gateway ----

def two_profiles(data, url):
    """The default profile on KEYS['default'] and B (created as the panel creates it: the default profile's policy now)
    on KEYS[B], the same gateway URL. The runtime is not running. Returns B's port."""
    store = ProductStore(data, PRODUCT)
    try:
        store.update(connection={'url': url, 'master_key': KEYS['default']})
    finally:
        store.close()
    port = free_port()
    create_profile(data, PRODUCT, B, label=LABEL, port=port, configured=False)
    update_profile(data, PRODUCT, B, connection={'url': url, 'master_key': KEYS[B]})
    return port


def watch(log_scan, data):
    for directory in (Path(data), profiles.Layout(Path(data)).profile(B)):
        if (directory / 'state.json').exists():
            state = stored(directory)
            log_scan.watch(*(value for value in (state['token'], state['child_token']) if value))
    log_scan.watch(*KEYS.values(), kind='secret')
    log_scan.watch(LABEL, kind='name')


def entries(runtime):
    return {profile: runtime.manager.get(profile) for profile in ('default', B)}


async def children_ready(runtime, wanted=('default', B)):
    """Every wanted profile's real child runs its own program and its last health check reached the gateway."""
    found = entries(runtime)

    def ready():
        return all(running_its_program(found[profile].runtime.supervisor)
                   and found[profile].runtime.health.availability()['ready']
                   and found[profile].runtime.health.availability()['backend'] == 'reachable' for profile in wanted)
    await until(ready, timeout=CHILD_SECONDS, step=.1)


async def checked_ready(runtime):
    """Switched off, the health monitor is the one before HM-09 (a check, then 15 s; HEALTH_INTERVAL does not pace it):
    once the real child runs its own program, check now, as the monitor would, until a check found it ready."""
    async with asyncio.timeout(CHILD_SECONDS):
        while not (running_its_program(runtime.supervisor) and runtime.health.availability()['ready']):
            if running_its_program(runtime.supervisor):
                await runtime.health.check()
            await asyncio.sleep(.1)


@contextmanager
def fast_health(monkeypatch):
    """Health checks every half second, so both profiles' first checks come within a second (the default: 15 s)."""
    monkeypatch.setattr(health_module, 'HEALTH_INTERVAL', 0.5)
    yield


# ---- MCP through the gateway ----

def methods(token):
    """The two connection methods of a token: (path, headers)."""
    return (('/mcp', {**ACCEPT, 'Authorization': 'Bearer ' + token}), (f'/private_{token}/mcp', dict(ACCEPT)))


async def rpc(client, path, headers, message):
    """One JSON-RPC exchange (JSON or SSE answer): its result. Keeps the session id the answer names."""
    async with client.stream('POST', path, headers=headers, json=message) as response:
        if response.headers.get('mcp-session-id'):
            headers['Mcp-Session-Id'] = response.headers['mcp-session-id']
        if 'id' not in message:
            assert response.status_code in (200, 202, 204), response.status_code
            return None
        return await protocol_reply(response, message['id'])


async def session(client, path, headers):
    """An initialized session on path: the headers its next requests carry."""
    headers = dict(headers)
    result = await rpc(client, path, headers, initialize_message())
    headers['MCP-Protocol-Version'] = result['protocolVersion']
    await rpc(client, path, headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    return headers


async def call(client, path, headers, name, ident, arguments=None):
    return await rpc(client, path, headers, {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
                                             'params': {'name': name, 'arguments': arguments or {}}})


def models(result):
    """The model names a litellm_list_models or litellm_model_info result lists."""
    assert not result.get('isError'), result
    texts = [json.loads(item['text']) for item in result['content'] if item['type'] == 'text']
    assert len(texts) == 1, result
    return sorted(entry.get('id') or entry['model_name'] for entry in texts[0]['data'])


async def listed(client, path, headers, ident):
    result = await rpc(client, path, headers, {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/list'})
    return {tool['name'] for tool in result['tools']}


async def end(client, path, headers):
    await client.delete(path, headers=headers)


def writers():
    """LiteLLM's write tools (the gateway's own registry: a write or a mixed tool)."""
    return {name for name, tool in TOOLS[PRODUCT].items() if tool.write or tool.write_operations}


# ---- 1. two keys on one gateway, and the 401 / 404 matrix across profiles (switched on) ----

async def test_two_virtual_keys_on_one_litellm_each_profile_sees_only_its_own_models(tmp_path, log_scan, monkeypatch):
    fake = FakeLiteLLM()
    data = tmp_path / 'data'
    with fake.serving() as url, fast_health(monkeypatch):
        two_profiles(data, url)
        watch(log_scan, data)
        async with multi_profile_runtime(PRODUCT, data, supervisor=lifecycle.Supervisor, real_children=True,
                                         default_port=free_port()) as runtime:
            await children_ready(runtime)
            found = entries(runtime)
            for profile, entry in found.items():
                env = entry.runtime.supervisor.spec.env
                assert (env['LITELLM_MCP_BASE_URL'], env['LITELLM_MCP_MASTER_KEY']) == (url, KEYS[profile]), profile
                assert env[DENY_LOOPBACK_ENV] == '1'  # HM-20 stays on: the gateway is on a private address
            async with runtime.mcp() as client:
                # N x N: each token on both methods lists its own key's models only.
                seen = {}
                for profile in ('default', B):
                    for path, headers in methods(runtime.token(profile)):
                        opened = await session(client, path, headers)
                        seen[profile, path.startswith('/private_')] = models(await call(client, path, opened, LIST, 2))
                        await end(client, path, opened)
                assert seen == {(profile, secret): MODELS[profile] for profile in ('default', B)
                                for secret in (False, True)}
                assert {profile for profile, _ in fake.seen()} == {'default', B}  # never an unknown key
                # The headers that must not choose: X-MCP-Profile on 8081, Authorization on the secret URL. A session
                # of the default profile is unknown (404) with B's token, on both methods.
                (bearer_path, bearer_headers), (secret_path, secret_headers) = methods(runtime.token('default'))
                for ident, (path, headers) in enumerate((
                        (bearer_path, {**bearer_headers, 'X-MCP-Profile': B}),
                        (secret_path, {**secret_headers, 'Authorization': 'Bearer ' + runtime.token(B)})), 3):
                    opened = await session(client, path, headers)
                    assert models(await call(client, path, opened, LIST, ident)) == MODELS['default']
                    for other_path, other_headers in methods(runtime.token(B)):
                        crossed = {**other_headers, 'Mcp-Session-Id': opened['Mcp-Session-Id'],
                                   'MCP-Protocol-Version': opened['MCP-Protocol-Version']}
                        response = await client.post(other_path, headers=crossed, json={
                            'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call',
                            'params': {'name': LIST, 'arguments': {}}})
                        assert response.status_code == 404, (ident, other_path.startswith('/private_'),
                                                             response.status_code)
                    await end(client, path, opened)
                # What is not an MCP token of this add-on: the gateway's own 401 and 404, byte for byte.
                wrong = {'default child token': stored(data)['child_token'],
                         'B child token': stored(profiles.Layout(data).profile(B))['child_token'],
                         'default virtual key': KEYS['default'], 'B virtual key': KEYS[B],
                         'random': secrets.token_urlsafe(32)}
                log_scan.watch(wrong['random'])
                for case, value in wrong.items():
                    for path, headers in methods(value):
                        response = await client.post(path, headers=headers, json=initialize_message())
                        expected = NOT_FOUND if path.startswith('/private_') else BEARER_REQUIRED
                        assert answer(response) == expected, (case, path.startswith('/private_'))
            # B's token revoked through B's own management: refused on both methods; the default profile is served.
            old = runtime.token(B)
            async with runtime.admin(B) as admin:
                boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
                revoked = await admin.post('/api/token/revoke', headers=reviewed_headers(boot, ADMIN))
                assert revoked.status_code == 200 and revoked.json()['profile'] == {'id': B}, revoked.status_code
            revoked = stored(profiles.Layout(data).profile(B))['token'] is None
            assert revoked, "B's token was not revoked"  # no token value in a failure message
            async with runtime.mcp() as client:
                for path, headers in methods(old):
                    response = await client.post(path, headers=headers, json=initialize_message())
                    assert answer(response) == (NOT_FOUND if path.startswith('/private_') else BEARER_REQUIRED)
                for path, headers in methods(runtime.token('default')):
                    opened = await session(client, path, headers)
                    assert models(await call(client, path, opened, LIST, 6)) == MODELS['default']
                    await end(client, path, opened)


async def test_each_real_child_serves_only_its_own_child_bearer(tmp_path, log_scan, monkeypatch):
    """T-23 across profiles: straight to each profile's real child (its index port), every Authorization form but its
    own child token (none, the other profile's child token, empty, two headers, ... test_child_bearer.refusals) gets
    401 with no session; its own opens one, which it ends. The gateway's routing never needs the other child's token."""
    fake = FakeLiteLLM()
    data = tmp_path / 'data'
    with fake.serving() as url, fast_health(monkeypatch):
        two_profiles(data, url)
        watch(log_scan, data)
        async with multi_profile_runtime(PRODUCT, data, supervisor=lifecycle.Supervisor, real_children=True,
                                         default_port=free_port()) as runtime:
            await children_ready(runtime)
            found = entries(runtime)
            tokens = {profile: stored(runtime.directory(profile))['child_token'] for profile in ('default', B)}
            async with GENUINE_CLIENT(trust_env=False, timeout=30) as client:
                for profile, other in (('default', B), (B, 'default')):
                    url_of_child = f'http://127.0.0.1:{found[profile].port}/mcp'
                    for case, authorization in refusals(tokens[profile], tokens[other]).items():
                        response, body = await send(client, 'POST', url_of_child, authorization,
                                                    message=initialize_message())
                        assert_refused(response, body, (profile[:8], case))
                    response, result = await send(client, 'POST', url_of_child, ['Bearer ' + tokens[profile]],
                                                  message=initialize_message())
                    assert response.status_code == 200 and response.headers.get('mcp-session-id'), profile[:8]
                    assert result['serverInfo']['name']  # the child's own answer, not the gateway's
                    ended = await client.delete(url_of_child, headers={
                        'Authorization': 'Bearer ' + tokens[profile],
                        'Mcp-Session-Id': response.headers['mcp-session-id'],
                        'MCP-Protocol-Version': result['protocolVersion']})
                    assert ended.status_code in (200, 204), profile[:8]


# ---- 2. each profile's backend pool (switched on) ----

async def test_each_profiles_child_keeps_its_own_four_backend_connections(tmp_path, log_scan, monkeypatch):
    """Six litellm_model_info calls of the default profile at once while the gateway holds them: four reach the backend
    (the child's pool: backend_policy.AsyncTransport, max_connections=4; lifespan.py's 50 is dropped), the fifth and
    sixth wait in the default profile's pool, and B's call is served meanwhile (B's child has a pool of its own). Once
    released every call is answered. Contract section 9, the HM-21 row: PaaS 50 per child, HA 4; unchanged here."""
    fake = FakeLiteLLM()
    data = tmp_path / 'data'
    with fake.serving() as url, fast_health(monkeypatch):
        two_profiles(data, url)
        watch(log_scan, data)
        async with multi_profile_runtime(PRODUCT, data, supervisor=lifecycle.Supervisor, real_children=True,
                                         default_port=free_port()) as runtime:
            await children_ready(runtime)
            async with runtime.mcp(timeout=60) as client:
                path, headers = methods(runtime.token('default'))[0]
                sessions = [await session(client, path, headers) for _ in range(POOL + 2)]
                beta_path, beta_headers = methods(runtime.token(B))[0]
                beta = await session(client, beta_path, beta_headers)
                fake.hold('default')
                waiting = [asyncio.create_task(call(client, path, opened, INFO, 10 + number))
                           for number, opened in enumerate(sessions)]
                await until(lambda: fake.in_flight['default'] >= POOL, timeout=30, step=.05)
                await asyncio.sleep(1)  # time enough for a fifth to arrive, were the pool any larger
                assert (fake.in_flight['default'], fake.peak['default']) == (POOL, POOL)
                assert not any(task.done() for task in waiting)
                async with asyncio.timeout(20):
                    assert models(await call(client, beta_path, beta, INFO, 20)) == MODELS[B]
                assert not any(task.done() for task in waiting)  # B was served while the default profile waited
                fake.release('default')
                async with asyncio.timeout(30):
                    answers = await asyncio.gather(*waiting)
                assert [models(result) for result in answers] == [MODELS['default']] * (POOL + 2)
                assert fake.peak['default'] == POOL and fake.peak[B] == 1
                for opened in sessions:
                    await end(client, path, opened)
                await end(client, beta_path, beta)


# ---- 3. each profile's policy (switched on) ----

async def test_saving_one_profiles_policy_restarts_only_its_own_child(tmp_path, log_scan, monkeypatch):
    fake = FakeLiteLLM()
    data = tmp_path / 'data'
    with fake.serving() as url, fast_health(monkeypatch):
        two_profiles(data, url)
        watch(log_scan, data)
        async with multi_profile_runtime(PRODUCT, data, supervisor=lifecycle.Supervisor, real_children=True,
                                         default_port=free_port()) as runtime:
            await children_ready(runtime)
            found = entries(runtime)
            every = set(TOOLS[PRODUCT])
            assert writers() and INFO in every and INFO not in writers()

            def pids():
                return {profile: found[profile].runtime.supervisor.process.pid for profile in ('default', B)}

            async def saved_policy(profile, policy):
                async with runtime.admin(profile) as admin:
                    boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
                    response = await admin.put('/api/policy', json=policy, headers=reviewed_headers(boot, ADMIN))
                assert response.status_code == 200 and response.json()['profile'] == {'id': profile}, (
                    response.status_code)

            async def tools_of(profile):
                """The tools the gateway lists for the profile's token, and its answer to a call of INFO (the
                gateway's refusal, or the child's result)."""
                async with runtime.mcp() as client:
                    path, headers = methods(runtime.token(profile))[0]
                    opened = await session(client, path, headers)
                    names = await listed(client, path, opened, 2)
                    response = await client.post(path, headers=opened, json={
                        'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': INFO, 'arguments': {}}})
                    result = None if refused(response) else await protocol_reply(response, 3)
                    await end(client, path, opened)
                return names, result

            async def raw_tools(profile):
                """The child's own tools/list, straight to its port with its child bearer: what it registered."""
                token = stored(runtime.directory(profile))['child_token']
                async with GENUINE_CLIENT(trust_env=False, timeout=30) as client:
                    child = f'http://127.0.0.1:{found[profile].port}/mcp'
                    headers = {**ACCEPT, 'Authorization': 'Bearer ' + token}
                    opened = await session(client, child, headers)
                    names = await listed(client, child, opened, 2)
                    await end(client, child, opened)
                return names

            before = pids()
            default_bytes = (data / 'state.json').read_bytes()
            assert {profile: found[profile].runtime.supervisor.spec.env['LITELLM_MCP_READONLY']
                    for profile in ('default', B)} == {'default': 'false', B: 'false'}
            # B: every write grant revoked (the exact grants decide, not writes_enabled) and one read tool off.
            await saved_policy(B, {'writes_enabled': False, 'disabled': [INFO], 'enabled_write_tools': []})
            await children_ready(runtime)
            after = pids()
            assert after['default'] == before['default'] and after[B] != before[B]
            env = {profile: found[profile].runtime.supervisor.spec.env for profile in ('default', B)}
            assert (env[B]['LITELLM_MCP_READONLY'], env['default']['LITELLM_MCP_READONLY']) == ('true', 'false')
            assert INFO in env[B]['LITELLM_MCP_DISABLED_TOOLS'].split(',')
            assert INFO not in env['default']['LITELLM_MCP_DISABLED_TOOLS'].split(',')
            assert (data / 'state.json').read_bytes() == default_bytes
            beta = stored(runtime.directory(B))
            assert (beta['writes_enabled'], beta['disabled'], beta['enabled_write_tools']) == (False, [INFO], [])
            names, info = await tools_of(B)
            assert not names & writers() and INFO not in names and LIST in names
            assert info is None  # the gateway refused it: B disabled it
            names, info = await tools_of('default')
            assert writers() <= names and INFO in names
            assert models(info) == MODELS['default']
            raw = {profile: await raw_tools(profile) for profile in ('default', B)}
            assert not raw[B] & writers() and INFO not in raw[B]  # B's child runs read-only, without the tool
            assert writers() & raw['default'] and INFO in raw['default']
            # The other way round: the default profile's save restarts the default profile's child alone.
            beta_bytes = (profiles.Layout(data).profile(B) / 'state.json').read_bytes()
            await saved_policy('default', {'writes_enabled': True, 'disabled': [LIST],
                                           'enabled_write_tools': products.fresh_write_grants(PRODUCT)})
            await children_ready(runtime)
            again = pids()
            assert again[B] == after[B] and again['default'] != after['default']
            assert (profiles.Layout(data).profile(B) / 'state.json').read_bytes() == beta_bytes
            names, _ = await tools_of('default')
            assert LIST not in names and INFO in names
            names, _ = await tools_of(B)
            assert LIST in names and INFO not in names


# ---- 4. switched off: the same data, the default profile alone ----

async def test_switched_off_the_default_profile_alone_is_served_and_b_stays_dormant(tmp_path, log_scan, monkeypatch):
    fake = FakeLiteLLM()
    data = tmp_path / 'data'
    made = []

    class Recorded(run_product.ProfileRuntime):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)

    monkeypatch.setattr(run_product, 'ProfileRuntime', Recorded)
    # Off for this test whatever the repository's switch says: multi_profile_runtime(switch=False) only leaves it as it
    # is, and LiteLLM's upgrade PR switches it on there.
    monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', features.MULTI_PROFILE_PRODUCTS - {PRODUCT})
    with fake.serving() as url, fast_health(monkeypatch):
        two_profiles(data, url)
        watch(log_scan, data)
        beta = profiles.Layout(data).profile(B)
        old = stored(beta)
        async with multi_profile_runtime(PRODUCT, data, supervisor=lifecycle.Supervisor, real_children=True,
                                         default_port=free_port(), switch=False) as runtime:
            assert runtime.manager is None and not features.enabled(PRODUCT)
            default, = made
            await checked_ready(default)
            env = default.supervisor.spec.env
            assert env['LITELLM_MCP_MASTER_KEY'] == KEYS['default'] and DENY_LOOPBACK_ENV not in env
            dormant = stored(beta)
            revoked, renewed = dormant['token'] is None, dormant['child_token'] != old['child_token']
            assert (revoked, renewed) == (True, True), 'HM-13b: B revoked, its child token new, before serving'
            log_scan.watch(dormant['child_token'])
            async with runtime.mcp() as client:
                for path, headers in methods(runtime.token('default')):
                    opened = await session(client, path, headers)
                    assert models(await call(client, path, opened, LIST, 2)) == MODELS['default']
                    await end(client, path, opened)
                for value in (old['token'], old['child_token'], dormant['child_token'], KEYS[B]):
                    for path, headers in methods(value):
                        response = await client.post(path, headers=headers, json=initialize_message())
                        assert answer(response) == (NOT_FOUND if path.startswith('/private_') else BEARER_REQUIRED)
            async with runtime.admin() as admin:
                assert (await admin.get('/api/profiles', headers=ADMIN)).status_code == 404
                boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
                assert boot['dormant_profiles'] == 1 and 'profile' not in boot
                pid = default.supervisor.process.pid
                beta_bytes = (beta / 'state.json').read_bytes()
                saved = await admin.put('/api/policy', json={'writes_enabled': False, 'disabled': [],
                                                             'enabled_write_tools': []},
                                        headers=reviewed_headers(boot, ADMIN))
                assert saved.status_code == 200 and 'profile' not in saved.json()
            await checked_ready(default)
            assert default.supervisor.process.pid != pid and default.supervisor.spec.env['LITELLM_MCP_READONLY'] == 'true'
            assert (beta / 'state.json').read_bytes() == beta_bytes
        assert {profile for profile, _ in fake.seen()} == {'default'}  # B's key was never sent


# ---- 5. both modes, without a child ----

@pytest.mark.parametrize('switched', [True, False], ids=['on', 'off'])
def test_two_profiles_children_differ_only_in_key_token_directory_port_and_policy(tmp_path, monkeypatch, switched):
    """products.child_spec for two LiteLLM profiles on one gateway: the same program and URL; their own key, child
    token, working directory and port; the policy's two variables from each state (READONLY: PaaS's per-profile
    read-only setting, FM-87); HM-20's variable on both when switched on, on neither when off."""
    monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset({PRODUCT} if switched else ()))
    url = 'https://litellm.invalid'
    states = {'default': products.ProductState(product=PRODUCT, token='T' * 43, child_token='C' * 43,
                                               connection={'url': url, 'master_key': KEYS['default']},
                                               writes_enabled=True,
                                               enabled_write_tools=products.fresh_write_grants(PRODUCT)),
              B: products.ProductState(product=PRODUCT, token='T' * 42 + 'B', child_token='C' * 42 + 'B',
                                       connection={'url': url, 'master_key': KEYS[B]}, writes_enabled=False,
                                       disabled=[INFO], enabled_write_tools=[])}
    directories = {'default': tmp_path / 'data', B: tmp_path / 'data' / 'profiles' / B}
    ports = {'default': lifecycle.CHILD_PORT, B: 18000}
    specs = {}
    for profile, state in states.items():
        directories[profile].mkdir(parents=True)
        specs[profile] = child_spec(state, directories[profile], port=ports[profile])
    a, b = specs['default'], specs[B]
    differs = {name for name in set(a.env) | set(b.env) if a.env.get(name) != b.env.get(name)}
    assert differs == {'LITELLM_MCP_MASTER_KEY', 'WOOW_MCP_CHILD_TOKEN', 'HOME', 'LITELLM_MCP_READONLY',
                       'LITELLM_MCP_DISABLED_TOOLS'}
    assert (a.env['LITELLM_MCP_MASTER_KEY'], b.env['LITELLM_MCP_MASTER_KEY']) == (KEYS['default'], KEYS[B])
    assert a.env['LITELLM_MCP_BASE_URL'] == b.env['LITELLM_MCP_BASE_URL'] == url
    assert (a.env['LITELLM_MCP_READONLY'], b.env['LITELLM_MCP_READONLY']) == ('false', 'true')
    assert INFO in b.env['LITELLM_MCP_DISABLED_TOOLS'].split(',')
    assert INFO not in a.env['LITELLM_MCP_DISABLED_TOOLS'].split(',')
    assert [part for part in a.argv if part != str(ports['default'])] == [
        part for part in b.argv if part != str(ports[B])]
    assert (a.cwd, b.cwd) == (directories['default'] / 'child', directories[B] / 'child')
    assert (DENY_LOOPBACK_ENV in a.env, DENY_LOOPBACK_ENV in b.env) == (switched, switched)
    # Each child's public tools are its own state's (the gateway checks the same policy on every call).
    for profile, state in states.items():
        public = {name for name in TOOLS[PRODUCT] if policy_enabled(name, TOOLS[PRODUCT], state)}
        assert (INFO in public, bool(public & writers())) == ((True, True) if profile == 'default' else (False, False))


@pytest.mark.parametrize('switched', [True, False], ids=['on', 'off'])
def test_a_new_key_or_url_never_rotates_the_mcp_token(monkeypatch, switched):
    """LiteLLM's account is the key it holds, which the add-on cannot read (as PaaS: the key's change keeps the MCP
    token). It is not identity-bound (DQ-40 ⑩: Odoo, Nextcloud, Hermes), switched on or off: a new key, a new URL or
    both keep the token; the panel's identityBound is the same set (tests/test_identity_fields.py)."""
    monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset({PRODUCT} if switched else ()))
    assert PRODUCT not in IDENTITY_BOUND and identity_fields.rotating_fields(PRODUCT) == ()
    assert identity_fields.URL_SECRETS[PRODUCT] == {'url': ('master_key',)}  # DQ-40 ⑨ asks for the key again
    before = products.ProductState(product=PRODUCT, token='T' * 43, child_token='C' * 43,
                                   connection={'url': 'https://litellm.invalid', 'master_key': KEYS['default']})
    for connection in ({'url': 'https://litellm.invalid', 'master_key': KEYS[B]},
                       {'url': 'https://other.litellm.invalid', 'master_key': KEYS['default']},
                       {'url': 'https://other.litellm.invalid', 'master_key': KEYS[B]}, None):
        after = before.model_copy(update={'connection': None if connection is None
                                          else products.LiteLLMConnection(**connection)})
        assert identity_rebound(before, after) is False
