"""HM-26: Headscale with additional profiles (multi-profile plan 9 Headscale row, 12.3 HM-21～HM-26; FM-88, FM-89,
FM-90, FM-109; CF-15; DQ-26 (the plan's recommendation: one server with different policies and several servers both
work, a key of its own per profile is recommended and not enforced; the owner's to confirm), DQ-40 ⑨, DQ-11; contract
2.6 and section 9 #9, #39, #41, #115 and HM-26's rows; acceptance T-04, T-05, T-07, T-23, T-24).

A Headscale API key administers the whole Headscale server, and Headscale has no narrower key: profiles on one server
are kept apart by their tool policies alone, whatever keys they use, and a policy that keeps headscale_api_keys create
lets the token's holder make a key no policy covers (HM-26 security review M-1). With one key, a child's check of the
URL and key of the state it reads against its own cannot even tell two such profiles apart (FM-88). Both shapes of
DQ-26 are here: B and C on the default profile's server (B with its key, C with a key of its own), D on a server and
key of its own (CF-15: both are tested). What keeps each profile to its own policy, server and key, with the product
switched on for the test (the repository keeps it off: tests/multi_profile_runtime.py) and, where the add-on as it
serves today has a counterpart, switched off:

- each child is started with its own profile's state (HEADSCALE_MCP_STATE_PATH), working directory, child token,
  server URL and key, and nothing of another profile's (the specs the add-on built);
- the child itself applies that state's policy at every call, whatever the gateway did: run in its own interpreter with
  the environment its spec gives it, one server and one key answer differently for profiles with different policies
  (the vendored policy reader on the profile directories the panel's creation made), a profile that may not create API
  keys included; a profile directory a restore left widened is refused (fail closed) until the profile's store
  tightened it, which the add-on does before any child starts;
- the child reads only a state that is its own (HM-26 security review S-1; not behind the switch): the state's child
  token must be the WOOW_MCP_CHILD_TOKEN the child was started with. A child started on another profile's state.json (B
  has the default profile's server and key, so nothing else tells the two apart), and one still running after its
  profile's child token was replaced ("Revoke all") without a restart, refuse every call;
- real children, two fake Headscale servers, four profiles: through 8081 each token reaches its own child, which sends
  its own key to its own server only (D's server gets D's requests alone, the other server never D's key); straight on
  loopback (a caller holding a child token) each child refuses what its own policy refuses and takes no other
  profile's child token; saving one profile's policy restarts only that profile's child, which then applies the saved
  policy, while the other profiles' sessions go on;
- each token opens only its own profile on both connection methods, a session stays with its profile, and an unknown,
  revoked or rotated-away token gets the default profile's answer (Bearer 401, secret URL 404); switched off, profiles
  on disk are dormant and their tokens are unknown tokens;
- every profile's secret URL takes no Origin but exactly https://claude.ai (403, no line, the child never sees it), the
  Bearer path takes none, and the add-on's Origin policy route stays an unknown operation (contract 2.6: HM-26 keeps it
  as written);
- saving one profile's policy restarts that profile's child only and changes that profile's tool list only, and the
  other profiles' sessions go on (switched off: the default profile's child, as today);
- a profile's URL moved to another origin needs its API key again (422, nothing written, no restart), the same origin
  written otherwise does not, a loopback URL is refused (HM-20), and a save with the key restarts only that profile's
  child and keeps its token (Headscale is not identity-bound: its key decides the account); switched off, the saved key
  follows the URL and a loopback URL is saved, as today;
- a key the Headscale server refuses (401) backs a switched-on profile's health checks off (DQ-25), and only a
  Headscale profile's: another product's monitor that got the same answer does not.
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import socket
import stat
import subprocess
import threading

import httpx
import pytest

from admin_write_headers import reviewed_headers
from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import (Children, all_tokens, create_profile, free_port, ids, multi_profile_runtime,
                                   stored, update_profile)
from mcp_admin_core import health as health_module, profiles
from mcp_admin_core.health import protocol_reply
from mcp_admin_core.products import DENY_LOOPBACK_ENV, ProductStore, child_spec
from test_single_profile_golden import (ACCEPT, ADMIN, BEARER_REQUIRED, CONNECTIONS, GENUINE_CLIENT, NOT_FOUND,
                                        NoProcessSupervisor, answer, initialize_message, settle)
from tool_refusal import refused

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'headscale'
B, C, D = ids(3)  # profiles.EXTRA_PROFILE_LIMITS: Headscale takes 3
PROFILES = ('default', B, C, D)
LABELS = {B: 'Headscale Desk B', C: 'Headscale Desk C', D: 'Headscale Desk D'}
EXTRA_PORTS = {B: 18000, C: 18001, D: 18002}  # each additional profile's mock child
SHARED = CONNECTIONS[PRODUCT]  # the default profile's server and key (synthetic: tests/fixtures/owner_defaults)
OWN_KEY = 'DUMMY-hm26-headscale-own-key'  # C's key of its own on the same server
OTHER = {'url': 'https://headscale-two.invalid', 'api_key': 'DUMMY-hm26-second-server-key'}  # D's own server and key
REPLACEMENT_KEY = 'DUMMY-hm26-headscale-new-key'
CREATED_KEY = 'DUMMY-hm26-headscale-made-key'  # the new key the fake server answers a CreateApiKey with
DENIED_403 = (403, [('content-length', '26'), ('content-type', 'application/json')], b'{"error":"request denied"}')
DENIED_400 = (400, b'{"error":"request denied"}')
NEW_ORIGIN = b'{"error":"request denied","detail":{"code":"CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN"}}'
SWITCH = pytest.mark.parametrize('switched_on', [True, False], ids=['switched-on', 'switched-off'])
# The calls each child is asked (name, arguments): a write, two reads, the write that hands out a key administering
# the whole server (headscale_api_keys create: HM-26 security review M-1, S-4) and the parent's private readiness
# probe, and the request each one sends to the server when it is let through. TOOL_CALLS: all but the probe.
CALLS = [('headscale_users', {'operation': 'create', 'name': 'hm26-user'}),
         ('headscale_users', {'operation': 'list'}),
         ('headscale_nodes', {'operation': 'list'}),
         ('headscale_api_keys', {'operation': 'create', 'expiration': '2099-01-01T00:00:00Z', 'reveal_once': True}),
         ('headscale_health', {})]
REQUESTS = [['POST', '/api/v1/user'], ['GET', '/api/v1/user'], ['GET', '/api/v1/node'], ['POST', '/api/v1/apikey'],
            ['GET', '/api/v1/health']]
TOOL_CALLS = len(CALLS) - 1
# The fake servers' answers (Headscale v0.29.4's v1 shapes, as apps/headscale/tests/test_headscale_child.py has them).
ANSWERS = {('POST', '/api/v1/user'): {'user': {'id': '7', 'name': 'hm26-user'}},
           ('GET', '/api/v1/user'): {'users': [{'id': '7', 'name': 'hm26-user'}]},
           ('GET', '/api/v1/node'): {'nodes': []},
           ('POST', '/api/v1/apikey'): {'apiKey': CREATED_KEY},
           ('GET', '/api/v1/health'): {'databaseConnectivity': True}}
# The four profiles' policies: the default profile keeps every write (a new installation); B (the default profile's
# server and key) loses the users:create and api_keys:create grants and the whole nodes tool; C (the same server, a key
# of its own) has users:list denied; D (a server and key of its own) has the users tool disabled. Per call of CALLS:
# whether the profile's policy lets it through (the readiness probe always: the child keeps its private probe callable
# whatever the policy).
LETS_THROUGH = {'default': [True, True, True, True, True], B: [False, True, False, False, True],
                C: [True, False, True, True, True], D: [False, False, True, True, True]}


@pytest.fixture(autouse=True)
def quick_monitors(monkeypatch):
    """No cgroup limit and plenty of MemAvailable (a save or a restart of an additional profile is never held for memory
    here, whatever the host has: contract 5, HM-09), and every profile's first health check within a second."""
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: None)
    monkeypatch.setattr(profiles, 'available_memory_mib', lambda: 4096)
    monkeypatch.setattr(health_module, 'HEALTH_INTERVAL', 0.5)


def directory(data, profile_id):
    return Path(data) if profile_id == 'default' else profiles.Layout(Path(data)).profile(profile_id)


def give_policies(data, grants, connection, other):
    """B, C and D (created) given their backends and LETS_THROUGH's policies (grants: the default profile's write
    grants, which a profile created now copies): B the default profile's server and key (*connection*), C the same
    server with a key of its own, D another server with its own key (*other*)."""
    kept = [grant for grant in grants if grant not in ('headscale_users:create', 'headscale_api_keys:create')]
    update_profile(data, PRODUCT, B, connection=connection, disabled=['headscale_nodes'], enabled_write_tools=kept)
    update_profile(data, PRODUCT, C, connection={**connection, 'api_key': OWN_KEY},
                   denied_operations={'headscale_users': ['list']})
    update_profile(data, PRODUCT, D, connection=other, disabled=['headscale_users'])


def with_policies(data, *, server=None, other=None, ports=tuple(EXTRA_PORTS.values())):
    """The default profile configured on *server* (left out: the golden one), and B, C and D created as the panel
    creates them (HM-10: profile_initial_state, the index), then given a backend and LETS_THROUGH's policies
    (give_policies; D's server *other*, left out: OTHER). Returns the default profile's write grants."""
    connection = server or SHARED
    store = ProductStore(data, PRODUCT)
    try:
        grants = store.update(connection=connection).enabled_write_tools
    finally:
        store.close()
    for profile_id, port in zip((B, C, D), ports):
        create_profile(data, PRODUCT, profile_id, label=LABELS[profile_id], port=port, configured=False)
    give_policies(data, grants, connection, other or OTHER)
    return grants


def watch(log_scan, data):
    log_scan.watch(*all_tokens(data))
    log_scan.watch(*LABELS.values(), kind='name')
    log_scan.watch(SHARED['api_key'], OWN_KEY, OTHER['api_key'], REPLACEMENT_KEY, CREATED_KEY, kind='secret')


def bearer(token):
    return {**ACCEPT, 'Authorization': 'Bearer ' + token}


def paths(token):
    return (('/mcp', bearer(token)), (f'/private_{token}/mcp', dict(ACCEPT)))


def profile_children(data):
    """Every profile's mock child on its port (tests/test_profile_runtime.ProfileChild: its own child bearer only, its
    own sessions)."""
    children = Children()
    children.profile_child(3000, 'default', PRODUCT, data)
    for profile_id, port in EXTRA_PORTS.items():
        children.profile_child(port, 'p' + profile_id[:4], PRODUCT, directory(data, profile_id))
    return children


def mock_children(children):
    return {'default': children.by_port[3000],
            **{profile_id: children.by_port[port] for profile_id, port in EXTRA_PORTS.items()}}


def recording_supervisor():
    """A NoProcessSupervisor class that keeps every instance the runtime makes (each profile's, the default profile's
    one when switched off) and every spec they start."""
    made, started = [], []

    class Recording(NoProcessSupervisor):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)

        def _start_child(self):
            if self.spec is not None:
                started.append(self.spec)
            super()._start_child()

    return Recording, made, started


def owner_of(data, spec):
    """The profile whose directory holds spec's working directory (<profile directory>/child)."""
    found = [profile_id for profile_id in PROFILES if spec.cwd == directory(data, profile_id) / 'child']
    assert len(found) == 1, spec.cwd
    return found[0]


def supervisors(data, made):
    """{profile id: its Supervisor} of the supervisors that started a child."""
    return {owner_of(data, supervisor.spec): supervisor for supervisor in made if supervisor.spec is not None}


async def until_ready(runtime, served):
    """Until every served profile answered a health check (the gateway forwards to a child that did)."""
    if runtime.manager is None:
        return
    from lifecycle_runtime import until
    await until(lambda: all(runtime.manager.get(profile_id).runtime.health.availability()['ready']
                            for profile_id in served), timeout=15)


async def admin_write(runtime, profile_id, method, route, body=None):
    """The panel's write on one profile (CSRF, If-Match of its current state, Idempotency-Key)."""
    async with runtime.admin(profile_id) as admin:
        boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
        return await admin.request(method, '/api/' + route, json=body, headers=reviewed_headers(boot, ADMIN))


def policy_body(state, **changes):
    """A policy save (PUT /api/policy) of the stored policy with changes."""
    return {**{name: state[name] for name in ('writes_enabled', 'disabled', 'enabled_write_tools',
                                               'denied_operations')}, **changes}


def initializes(mock):
    """How many of the test client's initialize requests (initialize_message's clientInfo) reached a mock child."""
    return sum(1 for request in mock.requests if b'"golden-client"' in request.content)


# ---- the child's own state, one profile each (FM-88) ----

CHILD_PROGRAM = r'''
import asyncio, json, os, sys
import httpx
from headscale_mcp_server.client import HeadscaleClient
from headscale_mcp_server.errors import HeadscaleError
from headscale_mcp_server.server import execute_tool

ANSWERS = {tuple(key.split(' ')): value for key, value in json.loads(sys.argv[2]).items()}


async def main():
    seen = []
    host = httpx.URL(os.environ['HEADSCALE_MCP_BASE_URL']).host

    def server(request):
        seen.append([request.method, request.url.path,
                     request.headers.get('authorization') == 'Bearer ' + os.environ['HEADSCALE_MCP_API_KEY']
                     and request.url.host == host])
        return httpx.Response(200, json=ANSWERS[(request.method, request.url.path)])

    results = []
    async with HeadscaleClient(os.environ['HEADSCALE_MCP_BASE_URL'], os.environ['HEADSCALE_MCP_API_KEY'],
                               transport=httpx.MockTransport(server)) as client:
        for name, arguments in json.loads(sys.argv[1]):
            before = len(seen)
            try:
                await execute_tool(name, arguments, client, state_path=os.environ['HEADSCALE_MCP_STATE_PATH'])
                outcome = 'ok'
            except HeadscaleError as error:
                outcome = error.code
            results.append([outcome, seen[before:]])
    print(json.dumps(results))


asyncio.run(main())
'''


def as_the_child(spec, calls=CALLS, state=None):
    """*calls* run by the vendored child code in the child's own interpreter, environment and working directory (its
    spec): the state it reads is HEADSCALE_MCP_STATE_PATH, at every call; the server is in memory. Per call its outcome
    ('ok' or the child's error code) and the requests the server got: [method, path, whether it carried this child's
    own key to this child's own server]. state: another state.json for HEADSCALE_MCP_STATE_PATH (a child started on the
    wrong profile's state)."""
    answers = {' '.join(key): value for key, value in ANSWERS.items()}
    env = dict(spec.env)
    if state is not None:
        env['HEADSCALE_MCP_STATE_PATH'] = str(state)
    result = subprocess.run([spec.argv[0], '-c', CHILD_PROGRAM, json.dumps(calls), json.dumps(answers)],
                            env=env, cwd=spec.cwd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.splitlines()[-1])


def expected_outcomes(profile_id):
    """What CALLS get from a child that reads profile_id's policy: through, with one request carrying its own key to
    its own server, or refused before any request."""
    return [['ok', [[*request, True]]] if through else ['HEADSCALE_POLICY_DENIED', []]
            for request, through in zip(REQUESTS, LETS_THROUGH[profile_id])]


@SWITCH
async def test_each_child_is_started_on_its_own_profiles_state_and_applies_its_policy(tmp_path, log_scan,
                                                                                      switched_on):
    """FM-88 (plan 9: HEADSCALE_MCP_STATE_PATH per profile; the vendored policy.py on profile directories): the spec
    the add-on built for each profile's child names that profile's state.json, its own empty working directory (cwd and
    HOME), its own child token, server URL and key, and nothing of another profile's (directory, token, child token,
    key); switched on, every child also has WOOW_MCP_DENY_LOOPBACK (HM-20). D's server is not the others' (DQ-26's
    several servers), so the URL check tells a child given another profile's server apart (HM-26 review MF-1). Run with
    that spec, the vendored child code applies its own profile's policy at every call: B on the default profile's
    server and key, C on the same server with a key of its own, D on a server and key of its own, and the four answer
    CALLS differently (LETS_THROUGH), a refused call sending nothing and every request carrying the child's own key to
    its own server. Switched off, the default profile's spec is today's (its state /data/mcp/state.json, no
    WOOW_MCP_DENY_LOOPBACK) and B, C and D are dormant: no spec, no child, their tokens revoked."""
    data = tmp_path / 'data'
    with_policies(data)
    watch(log_scan, data)
    supervisor, made, started = recording_supervisor()
    async with multi_profile_runtime(PRODUCT, data, children=profile_children(data), switch=switched_on,
                                     supervisor=supervisor) as runtime:
        await settle(runtime, 'configured')
    served = PROFILES if switched_on else ('default',)
    specs = {}
    for spec in started:
        specs.setdefault(owner_of(data, spec), spec)
    assert sorted(specs) == sorted(served)
    states = {profile_id: stored(directory(data, profile_id)) for profile_id in PROFILES}
    for profile_id, spec in specs.items():
        own, state, env = directory(data, profile_id), states[profile_id], spec.env
        assert env['HEADSCALE_MCP_STATE_PATH'] == str(own / 'state.json')
        assert env['HOME'] == str(own / 'child') and spec.cwd == own / 'child' and not any(spec.cwd.iterdir())
        assert env['WOOW_MCP_CHILD_TOKEN'] == state['child_token']
        assert (env['HEADSCALE_MCP_BASE_URL'], env['HEADSCALE_MCP_API_KEY']) == (
            state['connection']['url'], state['connection']['api_key'])
        assert env.get(DENY_LOOPBACK_ENV) == ('1' if switched_on else None)
        text = json.dumps([list(spec.argv), sorted(env.items()), str(spec.cwd)])
        assert state['token'] not in text  # the MCP token is the gateway's alone (HM-06)
        for other in PROFILES:
            if other != profile_id:
                assert str(directory(data, other) / 'state.json') not in text, (profile_id, other)
                assert str(directory(data, other) / 'child') not in text, (profile_id, other)
                assert states[other]['child_token'] not in text, (profile_id, other)
                assert not states[other]['token'] or states[other]['token'] not in text, (profile_id, other)
    if not switched_on:
        assert [states[profile_id]['token'] for profile_id in (B, C, D)] == [None] * 3  # dormant: the boot guard
    for profile_id, spec in specs.items():
        assert as_the_child(spec) == expected_outcomes(profile_id), profile_id
    if switched_on:
        assert {profile_id: (spec.env['HEADSCALE_MCP_BASE_URL'], spec.env['HEADSCALE_MCP_API_KEY'])
                for profile_id, spec in specs.items()} == {
            'default': (SHARED['url'], SHARED['api_key']), B: (SHARED['url'], SHARED['api_key']),
            C: (SHARED['url'], OWN_KEY), D: (OTHER['url'], OTHER['api_key'])}


def spec_of(data, profile_id, port):
    """The spec a start of profile_id's child gets from its state as it is now."""
    store = ProductStore(directory(data, profile_id), PRODUCT, existing_only=profile_id != 'default')
    try:
        return child_spec(store.load(), store.directory, port=port)
    finally:
        store.close()


def test_a_child_started_on_another_profiles_state_refuses_every_call(tmp_path, log_scan):
    """HM-26 security review S-1 (FM-88; not behind the switch): the child compares the child token of the state it
    reads with its own (WOOW_MCP_CHILD_TOKEN). B has the default profile's server and key, so the URL and key checks
    cannot tell their two states apart: B's child on the default profile's state.json would apply the default profile's
    policy (every write, api_keys create included) and the default profile's child on B's would apply B's. Both, and
    every other pair (C: the same server with a key of its own; D: another server), serve nothing: every call fails
    closed (HEADSCALE_POLICY_UNAVAILABLE, nothing sent), the probe too; on its own state each child answers as ever."""
    data = tmp_path / 'data'
    with_policies(data)
    watch(log_scan, data)
    specs = {profile_id: spec_of(data, profile_id, port)
             for profile_id, port in zip(PROFILES, (3000, *EXTRA_PORTS.values()))}
    for profile_id, spec in specs.items():
        assert as_the_child(spec) == expected_outcomes(profile_id), profile_id
    refused = [['HEADSCALE_POLICY_UNAVAILABLE', []]] * len(CALLS)
    for profile_id, spec in specs.items():
        for other in PROFILES:
            if other != profile_id:
                assert as_the_child(spec, state=directory(data, other) / 'state.json') == refused, (profile_id, other)


def test_a_child_whose_profile_got_a_new_child_token_serves_nothing_until_it_is_started_again(tmp_path, log_scan):
    """HM-26 security review S-1 (not behind the switch): "Revoke all" gives a profile a new child token and starts its
    child again (restore_lock.Sweep.revoke, profile_admin.revoke_all: a child that did not start again is one line in
    the log; the boot guard changes the token before any child starts). The child still running holds the old token in
    its environment and finds the new one in the state: every call fails closed (nothing sent), where it used to go on
    with whatever policy the state held. Once started again, from the state as it is now, it answers as ever. The
    default profile's child and an additional profile's alike."""
    data = tmp_path / 'data'
    with_policies(data)
    watch(log_scan, data)
    refused = [['HEADSCALE_POLICY_UNAVAILABLE', []]] * len(CALLS)
    for profile_id, port in (('default', 3000), (B, EXTRA_PORTS[B])):
        running = spec_of(data, profile_id, port)
        assert as_the_child(running) == expected_outcomes(profile_id), profile_id
        renewed = secrets.token_urlsafe(32)
        log_scan.watch(renewed)
        update_profile(data, PRODUCT, profile_id, child_token=renewed)
        assert as_the_child(running) == refused, profile_id
        assert as_the_child(spec_of(data, profile_id, port)) == expected_outcomes(profile_id), profile_id


def test_a_profile_directory_a_restore_widened_is_refused_until_its_store_tightens_it(tmp_path, log_scan):
    """The vendored policy reader takes only its own uid's 0700 directory and single-link 0600 state.json, with no link
    on the way. A Supervisor-style restore leaves directories 0755 and files 0644 (plan 8.4): the child then refuses
    every call (HEADSCALE_POLICY_UNAVAILABLE, nothing sent), and so it does when only the directory or only the file is
    wider (each check holds alone). The profile's store, opened existing-only as the add-on opens every additional
    profile before any child starts (ProfileManager; HM-07), tightens both again, and the child applies the profile's
    policy as before. (In the add-on the entrypoint's restore repair gives every restored entry back to the runtime user
    with these modes before the runtime starts: packaging/entrypoint.py, HM-13a.)"""
    data = tmp_path / 'data'
    with_policies(data)
    watch(log_scan, data)
    profile = directory(data, B)
    store = ProductStore(profile, PRODUCT, existing_only=True)
    try:
        spec = child_spec(store.load(), store.directory, port=18000)
    finally:
        store.close()
    assert as_the_child(spec) == expected_outcomes(B)
    for directory_mode, file_mode in ((0o755, 0o600), (0o700, 0o644), (0o755, 0o644)):  # last: what a restore leaves
        profile.chmod(directory_mode)
        (profile / 'state.json').chmod(file_mode)
        refused = [['HEADSCALE_POLICY_UNAVAILABLE', []]] * len(CALLS)
        assert as_the_child(spec) == refused, (oct(directory_mode), oct(file_mode))
    store = ProductStore(profile, PRODUCT, existing_only=True)
    try:
        store.load()
    finally:
        store.close()
    assert stat.S_IMODE(profile.stat().st_mode) == 0o700
    assert stat.S_IMODE((profile / 'state.json').stat().st_mode) == 0o600
    assert as_the_child(spec) == expected_outcomes(B)


def test_a_restore_revokes_every_profile_and_each_child_then_applies_the_backups_policy(tmp_path, log_scan):
    """A Supervisor-style restore of a Headscale volume with profiles (the HA side of PaaS
    test_headscale_volume_*_restores_*, woow-mcp-server 69ac425 packages/mcp-admin-core/tests/test_restore_inplace.py:
    every token dies, the policy and the connection come from the backup): HM-13b's boot guard revokes the default
    profile and B, C and D (DQ-03 (b) A2) and gives each a new child token; the restore record shows each profile's
    Headscale URL (identity: D's is its own server's) and its policy, never a key or a token. Each child, started on
    the guarded state, then applies the backup's policy (a policy saved after the backup is gone with it); the vendored
    reader takes a profile without a token. The guard itself is HM-13b's (tests/test_restore_lock.py); this is
    Headscale's state and child."""
    from mcp_admin_core import restore_lock
    from restore_guard_disk import Disk
    disk = Disk(tmp_path, log_scan, product=PRODUCT)
    assert disk.start(enabled=True) == restore_lock.Outcome()  # the first switched-on start makes the sentinel
    data = disk.data
    store = ProductStore(data, PRODUCT)
    try:
        grants = store.update(connection=SHARED).enabled_write_tools
    finally:
        store.close()
    for profile_id in (B, C, D):
        disk.add(profile_id)
    give_policies(data, grants, SHARED, OTHER)
    watch(log_scan, data)
    assert disk.start(enabled=True) == restore_lock.Outcome()
    backup = disk.backup()
    held = disk.held()
    update_profile(data, PRODUCT, B, disabled=[], enabled_write_tools=grants)  # after the backup: lost by the restore
    disk.restore(backup)
    assert disk.start(enabled=True) == restore_lock.Outcome(restored=True, default_revoked=True, revoked=(B, C, D))
    record = restore_lock.read_record(data)
    rows = {row['id']: row for row in record['profiles']}
    assert {profile_id: rows[profile_id]['identity'] for profile_id in PROFILES} == {
        'default': {'url': SHARED['url']}, B: {'url': SHARED['url']}, C: {'url': SHARED['url']},
        D: {'url': OTHER['url']}}
    assert rows[B]['policy']['disabled'] == ['headscale_nodes']
    raw = (data / profiles.RESTORE_RECORD_NAME).read_text()
    assert not [value for value in (*held, SHARED['api_key'], OWN_KEY, OTHER['api_key']) if value in raw]
    children = set()
    for port, profile_id in zip((3000, *EXTRA_PORTS.values()), PROFILES):
        state = stored(directory(data, profile_id))
        assert state['token'] is None and state['child_token'] not in held | children
        children.add(state['child_token'])
        store = ProductStore(directory(data, profile_id), PRODUCT, existing_only=profile_id != 'default')
        try:
            spec = child_spec(store.load(), store.directory, port=port)
        finally:
            store.close()
        assert spec.env['WOOW_MCP_CHILD_TOKEN'] == state['child_token']
        assert as_the_child(spec) == expected_outcomes(profile_id), profile_id


# ---- real children, two fake Headscale servers (FM-88, FM-109, CF-15; T-04, T-07, T-23) ----

def tool_requests(calls, since=0):
    """The server's requests from index since that a tool call sent: every profile's health monitor checks its server
    meanwhile (GET /api/v1/health), and those are left out."""
    return [call for call in calls[since:] if call[:2] != ('GET', '/api/v1/health')]


@contextmanager
def headscale_server():
    """One fake Headscale v1 API on this host's private address (the Headscale child refuses loopback and every address
    the backend policy refuses: tests/test_real_products.py does the same), recording every request's method, path and
    Authorization."""
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def answer(self):
            length = int(self.headers.get('Content-Length') or 0)
            if length:
                self.rfile.read(length)
            path = self.path.split('?')[0]
            calls.append((self.command, path, self.headers.get('Authorization')))
            body = ANSWERS.get((self.command, path))
            if body is None:
                self.send_error(404)
                return
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = answer

    host = socket.gethostbyname(socket.gethostname())
    server = ThreadingHTTPServer((host, 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://{host}:{server.server_port}', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


async def session(client, url, headers):
    """An initialized MCP session at url with headers (the gateway's /mcp, or a child straight): the headers its
    requests carry."""
    from test_real_products import rpc
    headers = dict(headers)
    result = await rpc(client, url, headers, initialize_message())
    headers['MCP-Protocol-Version'] = result['protocolVersion']
    await rpc(client, url, headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    return headers


def reply_of(response, ident):
    """The JSON-RPC message with id ident in a JSON or event-stream answer."""
    if response.headers.get('content-type', '').startswith('text/event-stream'):
        for event in response.text.replace('\r\n', '\n').split('\n\n'):
            data = '\n'.join(line[5:].lstrip(' ') for line in event.splitlines() if line.startswith('data:'))
            if data:
                message = json.loads(data)
                if message.get('id') == ident:
                    return message
        raise AssertionError('no reply in the event stream')
    return response.json()


async def tool_call(client, url, headers, ident, name, arguments):
    """One tools/call: 'refused' (the gateway's own refusal), 'ok' (a result) or the child's error code."""
    message = {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}}
    response = await client.post(url, headers=headers, json=message)
    if refused(response):
        return 'refused'
    assert response.status_code == 200, response.status_code
    reply = reply_of(response, ident)
    assert reply.get('jsonrpc') == '2.0' and 'result' in reply, reply
    result = reply['result']
    if not result.get('isError'):
        return 'ok'
    text = ' '.join(item.get('text', '') for item in result.get('content', []))
    return 'HEADSCALE_POLICY_DENIED' if 'HEADSCALE_POLICY_DENIED' in text else 'error'


async def test_real_children_keep_their_own_policy_and_key_through_8081_and_on_loopback(tmp_path, log_scan):
    """The real Headscale children of four profiles (run_product's ProfileManager with the real Supervisor: the
    default profile's child directly, the others through HM-09's exec wrapper) on two fake Headscale servers: B shares
    the default profile's server and key, C has a key of its own on that server, D a server and key of its own
    (CF-15: one key and two keys on one server, and several servers; DQ-26; HM-26 review MF-1).

    - Through 8081 each profile's token gets what its policy lets through (the gateway refuses the rest: no server gets
      anything), headscale_api_keys create included (B may not: HM-26 security review S-4); every request carries that
      profile's own key to its own server, and the other server gets nothing.
    - Straight on loopback, a caller holding a child token (T-23): each child takes its own child token only (every
      other profile's: 401) and on its own refuses what its profile's policy refuses (HEADSCALE_POLICY_DENIED, nothing
      sent), while the same call goes through on another profile's child: one server, one key (FM-88).
    - Saving B's policy (T-07) restarts B's child alone (a new PID; the others keep theirs), B's child then lets
      through what the saved policy grants, and the sessions the other profiles opened through 8081 before the save go
      on (HM-26 review SF-3).
    - D's server got D's requests alone, every one with D's key; the other server never got D's key (T-04)."""
    from lifecycle_runtime import until
    from mcp_admin_core import lifecycle
    from test_backend_loopback import running_its_program
    data = tmp_path / 'data'
    with headscale_server() as (url, calls), headscale_server() as (other_url, other_calls):
        server = {'url': url, 'api_key': SHARED['api_key']}
        grants = with_policies(data, server=server, other={'url': other_url, 'api_key': OTHER['api_key']},
                               ports=(free_port(), free_port(), free_port()))
        watch(log_scan, data)
        keys = {'default': SHARED['api_key'], B: SHARED['api_key'], C: OWN_KEY, D: OTHER['api_key']}
        servers = (calls, other_calls)

        def since():
            return [len(found) for found in servers]

        def reached(before):
            """The tool requests each server got since *before* (since()): [the first server's, D's server's]."""
            return [tool_requests(found, start) for found, start in zip(servers, before)]

        def expected(profile_id, number, through):
            """What reached() is after CALLS[number] of profile_id: the request on its own server, with its key."""
            own = [(*REQUESTS[number], 'Bearer ' + keys[profile_id])] if through else []
            return [[], own] if profile_id == D else [own, []]

        async with multi_profile_runtime(PRODUCT, data, supervisor=lifecycle.Supervisor, real_children=True,
                                         default_port=free_port()) as runtime:
            entries = {profile_id: runtime.manager.get(profile_id).runtime for profile_id in PROFILES}

            def serving():
                return all(running_its_program(entry.supervisor) and entry.health.availability()['ready']
                           for entry in entries.values())
            await until(serving, timeout=60)
            pids = {profile_id: entry.supervisor.process.pid for profile_id, entry in entries.items()}
            async with runtime.mcp() as client:
                for profile_id in PROFILES:
                    headers = await session(client, '/mcp', bearer(runtime.token(profile_id)))
                    for number, ((name, arguments), through) in enumerate(zip(CALLS[:TOOL_CALLS],
                                                                              LETS_THROUGH[profile_id])):
                        before = since()
                        found = await tool_call(client, '/mcp', headers, 10 + number, name, arguments)
                        assert found == ('ok' if through else 'refused'), (profile_id, name, found)
                        assert reached(before) == expected(profile_id, number, through), (profile_id, name)
                    await client.delete('/mcp', headers=headers)
            child_tokens = {profile_id: stored(directory(data, profile_id))['child_token'] for profile_id in entries}
            async with GENUINE_CLIENT(trust_env=False, timeout=20) as client:
                for profile_id, entry in entries.items():
                    for other, token in child_tokens.items():
                        if other != profile_id:
                            response = await client.post(entry.child_url, headers=bearer(token),
                                                         json=initialize_message())
                            assert response.status_code == 401, (profile_id, other)
                    headers = await session(client, entry.child_url, bearer(child_tokens[profile_id]))
                    for number, ((name, arguments), through) in enumerate(zip(CALLS[:TOOL_CALLS],
                                                                              LETS_THROUGH[profile_id])):
                        before = since()
                        found = await tool_call(client, entry.child_url, headers, 20 + number, name, arguments)
                        assert found == ('ok' if through else 'HEADSCALE_POLICY_DENIED'), (profile_id, name, found)
                        assert reached(before) == expected(profile_id, number, through), (profile_id, name)
                    await client.delete(entry.child_url, headers=headers)
            async with runtime.mcp() as client:
                kept = {profile_id: await session(client, '/mcp', bearer(runtime.token(profile_id)))
                        for profile_id in PROFILES if profile_id != B}
                saved = await admin_write(runtime, B, 'PUT', 'policy',
                                          policy_body(stored(directory(data, B)), enabled_write_tools=grants))
                assert saved.status_code == 200, saved.text

                def restarted():
                    supervisor = entries[B].supervisor
                    return (supervisor.process is not None and supervisor.process.pid != pids[B]
                            and running_its_program(supervisor) and entries[B].health.availability()['ready'])
                await until(restarted, timeout=60)
                assert {profile_id: entry.supervisor.process.pid for profile_id, entry in entries.items()} == {
                    **pids, B: entries[B].supervisor.process.pid}
                for profile_id, headers in kept.items():
                    ping = await client.post('/mcp', headers=headers,
                                             json={'jsonrpc': '2.0', 'id': 40, 'method': 'ping'})
                    assert ping.status_code == 200 and reply_of(ping, 40).get('result') == {}, profile_id
                    number = LETS_THROUGH[profile_id].index(True)  # a call the profile's policy lets through
                    before = since()
                    assert await tool_call(client, '/mcp', headers, 41, *CALLS[number]) == 'ok', profile_id
                    assert reached(before) == expected(profile_id, number, True), profile_id
                    await client.delete('/mcp', headers=headers)
            async with GENUINE_CLIENT(trust_env=False, timeout=20) as client:
                headers = await session(client, entries[B].child_url, bearer(child_tokens[B]))
                for number in (0, 3):  # the users:create and api_keys:create grants the save gave back
                    before = since()
                    assert await tool_call(client, entries[B].child_url, headers, 30 + number, *CALLS[number]) == 'ok'
                    assert reached(before) == expected(B, number, True), number
                await client.delete(entries[B].child_url, headers=headers)
        assert other_calls and {key for _, _, key in other_calls} == {'Bearer ' + OTHER['api_key']}
        assert 'Bearer ' + OTHER['api_key'] not in {key for _, _, key in calls}


# ---- tokens and connection methods (T-05) ----

@SWITCH
async def test_each_token_opens_only_its_own_profile_on_both_connection_methods(tmp_path, log_scan, switched_on):
    """Switched on: each profile's token opens a session with its own child on both connection methods, and no other
    child gets anything; a session stays with its profile (sent with another profile's token: 404); a token no profile
    holds gets the default profile's own answer (Bearer 401, secret URL 404) and reaches no child; a revoked token and
    a rotated-away one likewise, the other profiles' tokens unaffected. Switched off: B, C and D are dormant (their
    tokens revoked at the start), so their tokens from before are unknown tokens; the default profile is served as
    today."""
    data = tmp_path / 'data'
    with_policies(data)
    before = {profile_id: stored(directory(data, profile_id))['token'] for profile_id in PROFILES}
    watch(log_scan, data)
    children = profile_children(data)
    child = mock_children(children)
    async with multi_profile_runtime(PRODUCT, data, children=children, switch=switched_on) as runtime:
        await settle(runtime, 'configured')
        served = PROFILES if switched_on else ('default',)
        await until_ready(runtime, served)

        async def opened(token, profile_id):
            async with runtime.mcp() as client:
                for path, headers in paths(token):
                    counts = {other: len(mock.requests) for other, mock in child.items()}
                    response = await client.post(path, headers=headers, json=initialize_message())
                    assert response.status_code == 200, (profile_id, path.replace(token, '<token>'))
                    assert response.headers['mcp-session-id'] in child[profile_id].sessions, profile_id
                    assert {other: len(mock.requests) for other, mock in child.items() if other != profile_id} == {
                        other: count for other, count in counts.items() if other != profile_id}

        async def unknown(token):
            counts = {other: len(mock.requests) for other, mock in child.items()}
            async with runtime.mcp() as client:
                found = [answer(await client.post(path, headers=headers, json=initialize_message()))
                         for path, headers in paths(token)]
            assert found == [BEARER_REQUIRED, NOT_FOUND]
            assert {other: len(mock.requests) for other, mock in child.items()} == counts

        for profile_id in served:
            await opened(runtime.token(profile_id), profile_id)
        for profile_id in PROFILES:
            if profile_id not in served:
                await unknown(before[profile_id])
        stranger = secrets.token_urlsafe(32)
        log_scan.watch(stranger)
        await unknown(stranger)
        if not switched_on:
            return
        async with runtime.mcp() as client:
            response = await client.post('/mcp', headers=bearer(runtime.token(B)), json=initialize_message())
            session_id = response.headers['mcp-session-id']
            assert session_id in child[B].sessions
            ping = {'jsonrpc': '2.0', 'id': 2, 'method': 'ping'}
            for token in (runtime.token('default'), runtime.token(C), runtime.token(D)):
                for path, headers in paths(token):
                    crossed = await client.post(path, headers={**headers, 'Mcp-Session-Id': session_id}, json=ping)
                    assert crossed.status_code == 404, path.replace(token, '<token>')
            mine = await client.post('/mcp', headers={**bearer(runtime.token(B)), 'Mcp-Session-Id': session_id},
                                     json=ping)
            assert mine.status_code == 200
        revoked = await admin_write(runtime, B, 'POST', 'token/revoke')
        assert revoked.status_code == 200, revoked.text
        await unknown(before[B])
        old = runtime.token(C)
        rotated = await admin_write(runtime, C, 'POST', 'token/rotate')
        assert rotated.status_code == 200, rotated.text
        log_scan.watch(runtime.token(C))
        await unknown(old)
        for profile_id in ('default', C, D):
            await opened(runtime.token(profile_id), profile_id)


# ---- the secret URL's Origin (FM-90; plan 8.7; contract 2.6, section 9 #9, #10; T-24) ----

REFUSED_ORIGINS = ('https://evil.invalid', 'null', 'https://claude.ai.', 'https://CLAUDE.AI', 'http://claude.ai',
                   'https://claude.ai:443', 'https://claude.ai/', 'https://claude.ai.evil.invalid')


@SWITCH
async def test_every_profiles_secret_url_takes_only_claude_ai_as_origin(tmp_path, log_scan, caplog, switched_on):
    """Headscale keeps its own rule on every profile (the user's HA Headscale decision, R01 H-08; FM-90): a secret URL
    takes a request without Origin or with exactly one Origin that is exactly https://claude.ai (no normalization: other
    letter cases, a trailing dot or slash, the default port written out are refused), else 403 {"error":"request
    denied"} with no line and without reaching the child; the Bearer path takes no Origin at all (403). Headscale has no
    Origin policy: its route stays an unknown operation for every profile (empty 404 after the role check; HM-26 keeps
    contract 2.6 as written) and no policy file is written. Switched off, the default profile answers the same, as
    today."""
    data = tmp_path / 'data'
    with_policies(data)
    watch(log_scan, data)
    children = profile_children(data)
    child = mock_children(children)
    async with multi_profile_runtime(PRODUCT, data, children=children, switch=switched_on) as runtime:
        await settle(runtime, 'configured')
        served = PROFILES if switched_on else ('default',)
        await until_ready(runtime, served)
        async with runtime.mcp() as client:
            for profile_id in served:
                token = runtime.token(profile_id)
                path = f'/private_{token}/mcp'
                since = initializes(child[profile_id])
                for headers in (dict(ACCEPT), {**ACCEPT, 'Origin': 'https://claude.ai'}):
                    response = await client.post(path, headers=headers, json=initialize_message())
                    assert response.status_code == 200, profile_id
                for origin in REFUSED_ORIGINS:
                    response = await client.post(path, headers={**ACCEPT, 'Origin': origin},
                                                 json=initialize_message())
                    assert answer(response) == DENIED_403, (profile_id, origin)
                doubled = [*ACCEPT.items(), ('Origin', 'https://claude.ai'), ('Origin', 'https://claude.ai')]
                assert answer(await client.post(path, headers=doubled, json=initialize_message())) == DENIED_403
                response = await client.post('/mcp', headers={**bearer(token), 'Origin': 'https://claude.ai'},
                                             json=initialize_message())
                assert answer(response) == DENIED_403, profile_id
                assert initializes(child[profile_id]) == since + 2, profile_id
        if switched_on:
            for profile_id in served:
                async with runtime.admin(profile_id) as admin:
                    unknown = answer(await admin.get('/api/no-such-operation', headers=ADMIN))
                    assert unknown[0] == 404 and unknown[2] == b''
                    assert answer(await admin.get('/api/origin-policy', headers=ADMIN)) == unknown, profile_id
    assert not (data / profiles.ORIGIN_POLICY_NAME).exists()
    assert [record.getMessage() for record in caplog.records if record.name.startswith('mcp_admin_core')
            and ('origin' in record.name or 'Origin' in record.getMessage())] == []


# ---- policy saves (T-07) ----

@SWITCH
async def test_saving_one_profiles_policy_restarts_only_its_child(tmp_path, log_scan, switched_on):
    """Headscale's child is restarted when its profile's policy is saved, so that a session sees one tool list (the
    gateway restarts the children that take their policy at start, and Headscale's, which also reads it at every
    call): with profiles, only the child of the profile whose policy was saved (plan 6, 9; FM-64), and the saved policy
    is that profile's alone: its tools/list changes, the other profiles' stay as they were, and a session another
    profile opened before the save goes on (the same Mcp-Session-Id answers a ping: HM-26 review SF-3). Switched off,
    the default profile's child restarts, as today."""
    data = tmp_path / 'data'
    with_policies(data)
    watch(log_scan, data)
    supervisor, made, _ = recording_supervisor()
    children = profile_children(data)
    async with multi_profile_runtime(PRODUCT, data, children=children, switch=switched_on,
                                     supervisor=supervisor) as runtime:
        await settle(runtime, 'configured')
        served = PROFILES if switched_on else ('default',)
        await until_ready(runtime, served)
        target = B if switched_on else 'default'

        def starts():
            return {profile_id: found.starts for profile_id, found in supervisors(data, made).items()}

        async def listed(profile_id):
            async with runtime.mcp() as client:
                headers = await session(client, '/mcp', bearer(runtime.token(profile_id)))
                async with client.stream('POST', '/mcp', headers=headers,
                                         json={'jsonrpc': '2.0', 'id': 5, 'method': 'tools/list'}) as response:
                    result = await protocol_reply(response, 5)
                await client.delete('/mcp', headers=headers)
            return sorted(tool['name'] for tool in result['tools'])

        lists = {profile_id: await listed(profile_id) for profile_id in served}
        assert 'headscale_users' in lists[target]
        before = starts()
        assert sorted(before) == sorted(served)
        state = stored(directory(data, target))
        async with runtime.mcp() as client:
            kept = {profile_id: await session(client, '/mcp', bearer(runtime.token(profile_id)))
                    for profile_id in served if profile_id != target}
            saved = await admin_write(runtime, target, 'PUT', 'policy',
                                      policy_body(state, disabled=sorted({*state['disabled'], 'headscale_users'})))
            assert saved.status_code == 200, saved.text
            assert starts() == {**before, target: before[target] + 1}
            await until_ready(runtime, served)
            for profile_id, headers in kept.items():
                ping = await client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 6, 'method': 'ping'})
                assert ping.status_code == 200 and reply_of(ping, 6).get('result') == {}, profile_id
                await client.delete('/mcp', headers=headers)
        assert await listed(target) == [name for name in lists[target] if name != 'headscale_users']
        for profile_id in served:
            if profile_id != target:
                assert await listed(profile_id) == lists[profile_id], profile_id


# ---- a profile's URL (FM-89; DQ-40 ⑨, contract #41, #115; HM-20, contract #39) ----

@SWITCH
async def test_a_profiles_url_moved_to_another_origin_needs_its_api_key_again(tmp_path, log_scan, switched_on):
    """Switched on (B; an additional profile): backend/patch of the URL alone to another origin (scheme, host or
    effective port) answers 422 CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN, writes nothing and restarts no child;
    the same origin written otherwise (the /api/v1 root, the host's letter case, the default port written out) needs no
    key; with the key the save restarts B's child alone and keeps B's token (Headscale is not identity-bound: no
    token_rotated); a loopback URL is refused (400, HM-20). Switched off (the default profile, as today): the saved key
    follows the URL to another origin and a loopback URL is saved."""
    data = tmp_path / 'data'
    with_policies(data)
    watch(log_scan, data)
    supervisor, made, _ = recording_supervisor()
    async with multi_profile_runtime(PRODUCT, data, children=profile_children(data), switch=switched_on,
                                     supervisor=supervisor) as runtime:
        await settle(runtime, 'configured')
        target = B if switched_on else 'default'
        path = directory(data, target) / 'state.json'

        def starts():
            return {profile_id: found.starts for profile_id, found in supervisors(data, made).items()}

        async def patch(changes):
            return await admin_write(runtime, target, 'PUT', 'backend/patch', {'changes': changes})

        token = stored(directory(data, target))['token']
        for written in (SHARED['url'] + '/api/v1', 'https://HEADSCALE.invalid', 'https://headscale.invalid:443'):
            saved = await patch({'url': written})
            assert saved.status_code == 200, (written, saved.text)
            assert stored(directory(data, target))['connection']['api_key'] == SHARED['api_key']
        before, raw = starts(), path.read_bytes()
        moved = await patch({'url': 'https://elsewhere.invalid'})
        if switched_on:
            assert (moved.status_code, moved.content) == (422, NEW_ORIGIN)
            assert path.read_bytes() == raw and starts() == before
        else:
            assert moved.status_code == 200, moved.text
            assert stored(data)['connection'] == {'url': 'https://elsewhere.invalid', 'api_key': SHARED['api_key']}
        before = starts()
        saved = await patch({'url': 'https://other.invalid:8443', 'api_key': REPLACEMENT_KEY})
        assert saved.status_code == 200 and 'token_rotated' not in saved.json(), saved.text
        assert stored(directory(data, target))['connection'] == {'url': 'https://other.invalid:8443',
                                                                 'api_key': REPLACEMENT_KEY}
        assert stored(directory(data, target))['token'] == token
        assert starts() == {**before, target: before[target] + 1}
        before, raw = starts(), path.read_bytes()
        loopback = await patch({'url': 'http://127.0.0.1:8080', 'api_key': REPLACEMENT_KEY})
        if switched_on:
            assert (loopback.status_code, loopback.content) == DENIED_400
            assert path.read_bytes() == raw and starts() == before
        else:
            assert loopback.status_code == 200, loopback.text
            assert stored(data)['connection']['url'] == 'http://127.0.0.1:8080'


# ---- a key the Headscale server refuses: the monitor's backoff (DQ-25; HM-09) ----

REFUSAL_PROGRAM = r'''
import asyncio, json, os
import httpx
from fastmcp import Client
from headscale_mcp_server.client import HeadscaleClient
from headscale_mcp_server.server import build_server


async def main():
    found = {}
    for status in (401, 403, 500):
        def server(request, status=status):
            return httpx.Response(status, json={'code': 16, 'message': 'Unauthenticated', 'details': []})
        backend = HeadscaleClient(os.environ['HEADSCALE_MCP_BASE_URL'], os.environ['HEADSCALE_MCP_API_KEY'],
                                  transport=httpx.MockTransport(server))
        async with Client(build_server(backend, os.environ['HEADSCALE_MCP_STATE_PATH'])) as mcp:
            result = await mcp.call_tool('headscale_health', {}, raise_on_error=False)
        found[str(status)] = {'isError': result.is_error,
                              'content': [{'type': 'text', 'text': item.text} for item in result.content]}
    print(json.dumps(found))


asyncio.run(main())
'''


def refused_replies(tmp_path):
    """The readiness probe's reply (headscale_health) as the real child answers it when the Headscale server answers
    401 (a revoked, expired or wrong API key), 403 and 500: the vendored child in its own interpreter and environment,
    the server in memory. {status: reply}."""
    store = ProductStore(tmp_path / 'probe', PRODUCT)
    try:
        spec = child_spec(store.update(connection=SHARED), store.directory)
    finally:
        store.close()
    result = subprocess.run([spec.argv[0], '-c', REFUSAL_PROGRAM], env=dict(spec.env), cwd=spec.cwd,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr[-2000:]
    return {int(status): reply for status, reply in json.loads(result.stdout.splitlines()[-1]).items()}


class ProbeChild:
    """A child as the monitor reaches it: initialize, initialized and ping answered; the readiness probe (*probe*)
    answers `reply` (left None: Headscale's success shape)."""

    def __init__(self, probe='headscale_health'):
        self.probe, self.reply = probe, None

    def __call__(self, request):
        if request.method == 'DELETE':
            return httpx.Response(200)
        message = json.loads(request.content)
        if 'id' not in message:
            return httpx.Response(202)
        if message['method'] == 'initialize':
            result = {'protocolVersion': '2025-03-26', 'serverInfo': {'name': 'mock'}}
        elif message['method'] == 'ping':
            result = {}
        else:
            assert message['params']['name'] == self.probe
            result = self.reply or {'content': [{'type': 'text', 'text': json.dumps({'databaseConnectivity': True})}]}
        return httpx.Response(200, headers={'mcp-session-id': 'health'},
                              json={'jsonrpc': '2.0', 'id': message['id'], 'result': result})


class ProbeProcess:
    """A Supervisor's face as the monitor sees it."""

    def __init__(self):
        self.ready, self.status, self.starts = False, 'running', 1

    def health(self):
        return {'state': self.status, 'transport_ready': self.ready, 'starts': self.starts, 'last_exit': None}


@SWITCH
async def test_a_key_the_headscale_server_refuses_backs_the_profiles_checks_off(tmp_path, log_scan, switched_on):
    """DQ-25 (HM-09): once a product is switched on, a profile whose backend refuses its credentials is checked 15, 30,
    60, 120, 300 s apart instead of every 15 s, and any other answer resets it. The Headscale child says a refused key
    only in its error object (HEADSCALE_UPSTREAM_ERROR, http_status 401: the reply the real child gives, made here),
    which the check's reason does not keep (probe_reason keeps an error's "error" or "message"): health.refused_login
    reads the reply for a Headscale profile's monitor with the backoff (ProfileManager's options). A 403, a 500 and a
    success are no refused key; neither is the same object from another product's child (a backend's own text could
    be it: HM-26 security review S-2), nor a check whose child did not answer it as ready (no check the child did not
    answer counts: HM-26 review N-1). Switched off, the monitor has no backoff option (as run_product builds a
    switched-off product's; how the switch gives ProfileManager's options is HM-09's tests) and is today's: every check
    15 s apart. The reason the check records is the same in both modes (the panel's text does not change)."""
    from mcp_admin_core import health
    from mcp_admin_core.products import health_probe
    replies = refused_replies(tmp_path)
    assert health.refused_login(replies[401]) is True
    assert not any(health.refused_login(reply) for reply in (replies[403], replies[500], None, {}, {'isError': True}))
    store = ProductStore(tmp_path / 'state', PRODUCT)
    store.update(connection=SHARED)
    log_scan.watch_state(store.load())
    child, process = ProbeChild(), ProbeProcess()
    options = dict(tolerance=2, auth_backoff=health.AUTH_BACKOFF, own_child_only=True) if switched_on else {}
    async with httpx.AsyncClient(transport=httpx.MockTransport(child)) as client:
        monitor = health.HealthMonitor(store, process, client, **options)
        child.reply = replies[401]
        for expected in (15, 30, 60):
            await monitor.check()
            assert monitor.next_interval() == (expected if switched_on else health.HEALTH_INTERVAL)
        assert monitor.auth_refusals == (3 if switched_on else 0)
        assert monitor.settled[2:] == ('unreachable',
                                       'BACKEND_INVALID_RESPONSE: the health check answer was not the expected one')
        for other in (replies[403], replies[500]):
            child.reply = other
            await monitor.check()
            assert monitor.auth_refusals == 0 and monitor.next_interval() == health.HEALTH_INTERVAL
        child.reply = replies[401]
        await monitor.check()
        child.reply = None
        await monitor.check()
        assert monitor.auth_refusals == 0 and monitor.backend == 'reachable'
        starting = ProbeProcess()
        starting.status = 'starting'  # the child is not ready: the check's answer is not its own (not answered)
        unready = health.HealthMonitor(store, starting, client, **{**options, 'own_child_only': False})
        child.reply = replies[401]
        await unready.check()
        assert unready.auth_refusals == 0 and unready.next_interval() == health.HEALTH_INTERVAL
    store.close()
    other = ProductStore(tmp_path / 'emqx', 'emqx')
    other.update(connection=CONNECTIONS['emqx'])
    log_scan.watch_state(other.load())
    emqx = ProbeChild(health_probe('emqx')[0])
    emqx.reply = replies[401]
    async with httpx.AsyncClient(transport=httpx.MockTransport(emqx)) as client:
        monitor = health.HealthMonitor(other, ProbeProcess(), client, **options)
        for _ in range(2):  # switched on: the second one in a row makes the verdict (tolerance 2)
            await monitor.check()
            assert monitor.auth_refusals == 0 and monitor.next_interval() == health.HEALTH_INTERVAL
        assert monitor.settled[2] == 'unreachable'
    other.close()
