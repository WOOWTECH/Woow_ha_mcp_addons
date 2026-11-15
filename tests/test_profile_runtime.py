"""HM-05: one profile's runtime (mcp_admin_core.profile_runtime); the default profile is built with it and serves as before.

Multi-profile plan 3.2 and 12.3 HM-05 (FM-06, 32, 33, 37, 47, 54, 65, 76); HM-00 contract 1.2: not gated, so nothing a
client or the panel gets may change (tests/test_single_profile_golden.py and the two contract freezes keep proving it,
byte for byte). What is new is reachable from code only, and only the tests here reach it:

- ProfileRuntime: what one profile owns (plan 3.2). Its store's two apps (gateway.make_apps); its child: a Supervisor
  (lifecycle: the Supervisor's own options) on the spec the product builds from the profile's state and directory, on
  the profile's port (HM-04); the child's httpx client, HealthMonitor and ConfigurationState; its TokenAccess and
  mutation lock, created by the runtime so that the add-on can reach them. Two runtimes in one process share none of
  it: a token, a session (the child's or the gateway's own), a child URL and spec, the child client (with the options
  run_product gave it), a token change, a save and its restart, the apply status, the receipts, the child's output and
  the reply redaction all stay with their profile. Not proven here: the forwarding slots (32 in every make_apps; HM-08's
  quota tests take them across profiles) and n8n's catalog copy (one per process; DQ-04, HM-25).
- SharedAdmin: what the whole add-on shares on 8099 (plan 3.2, FM-54), given to every profile: one AdminAuthority (one
  CSRF key, one HA role verifier), one set of 16 management slots and, for HM-10, the shared management pipeline. One
  CSRF token then works for every profile, and another profile's ETag is a conflict (409 config_conflict; FM-06): the
  two profiles' states differ (their tokens), so their revisions do. Each profile's ConfigurationState also has a
  random key of its own, a second layer these tests do not prove on its own (HM-10: contract 3.5, DQ-15).
- make_apps' keyword-only parameters for them (authority, admin_slots, admin_pipeline, token_access, mutation_lock,
  profile_view: the profile echo of plan 5.3 item 5); left out, each is created as before.
- run_product builds the default profile with it, and starting the default profile adds no file to its data directory
  (/data/mcp in the add-on).

Every child here is a MockTransport behind its profile's port (no socket is opened: owned_network's count of refused
operations on 3000 and 18000-18099 must not grow), every Supervisor is the real one without a process
(tests/test_single_profile_golden.py: NoProcessSupervisor; FM-37: one per profile in one process), and every test runs
under the HM-01 log scan, watching the tokens, credentials and profile names it uses.

The module under test is imported when a test runs, not at collection: before HM-05 every test here failed on its own
(the red half of the provenance note's red-green table) instead of the whole file failing to collect.
"""
import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass
import hashlib
import inspect
import json
from pathlib import Path
import re
from types import SimpleNamespace

import httpx
import pytest
from starlette.responses import JSONResponse

import n8n_adapter
import owned_network
from admin_write_headers import reviewed_headers
from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import gateway, lifecycle, run_product, version_for_product
from mcp_admin_core.access import TokenAccess
from mcp_admin_core.admin_auth import AdminAuthority, BadRequest
from mcp_admin_core.capabilities import ManagementOptions
from mcp_admin_core.diagnostics import MAX_BYTES, MAX_ENTRIES
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import INSTRUCTIONS, PROBES, TOOLS, ProductStore, child_spec
from mcp_admin_core.surface import FULL_PRODUCTS, listing
from test_single_profile_golden import (ACCEPT, ADMIN, BEARER_REQUIRED, BOOTSTRAP_COMMON, BOOTSTRAP_EXTRA, CONNECTIONS,
                                        GENUINE_CLIENT, INGRESS, LISTED_SHA256, NOT_FOUND, NoProcessSupervisor,
                                        PROBE_ANSWERS, PRODUCTS, SESSION_DELETED, answer, configure, expected_entries,
                                        initialize_message, probe_name, production_runtime, settle, stat_signature,
                                        stored)

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan
DEFAULT_PORT = lifecycle.CHILD_PORT  # the default profile's child (HM-04)
EXTRA_PORT = 18000  # an extra profile's child (plan 5.4: 18000 and up; owned_network.PROFILE_CHILD_PORTS)
EXTRA_ID = 'ab' * 12  # an extra profile's id: 24 lowercase hex (contract 1.1)
PRODUCT = 'odoo'  # the product of the single-product tests: the first to ship profiles (plan 9)
SHARED_ECHO = {'id': EXTRA_ID, 'label': 'Alpha Prod', 'is_default': False}  # a profile name the log scan watches
# What the multi-profile slices will add next to the default profile's state (contract 8; plan 4.1): none of these
# may appear while profiles are not shipped.
PROFILE_FILES = ('profiles', 'profiles.json', '.profiles.json.operations.json', '.restore-detected',
                 'restore-record.json')


def runtime_module():
    import mcp_admin_core.profile_runtime as module  # see the module docstring: imported when a test runs
    return module


@pytest.fixture(autouse=True)
def no_production_port():
    """owned_network counts every refused operation on 3000 or 18000-18099 in this process: none may happen here."""
    before = owned_network.forbidden_operations
    yield
    assert owned_network.forbidden_operations == before, 'a test operation tried a production child port'


# ---- the children: one per profile, each on its own port ----

def connection_of(product, name):
    """The golden backend with this profile's own credentials (DUMMY-<name>-..., <name>.<host>.invalid)."""
    if product == 'n8n':
        return {'backend_url': f'https://{name}.n8n.invalid', 'backend_key': f'DUMMY-{name}-workflow-key'}
    return {key: value.replace('DUMMY-golden-', f'DUMMY-{name}-').replace('https://', f'https://{name}.')
            for key, value in CONNECTIONS[product].items()}


def identity_of(product, name):
    """The values of this profile's backend that name it (its credentials and URLs; DUMMY-user and DUMMY-db are the
    same for every profile)."""
    return {value for value in connection_of(product, name).values()
            if value.startswith((f'DUMMY-{name}-', f'https://{name}.'))}


class ProfileChild:
    """One profile's child as its runtime reaches it: only that profile's child bearer is answered (an HM-06 child's
    rule); initialize opens a session named after the profile, and a request in a session it never opened gets 404 (as
    the pinned SDK children answer); the readiness probe gets the product's success shape, tools/list the packaged
    listing, any other tools/call `text` (hold() keeps the next one waiting until release is set). Every request is
    recorded."""

    def __init__(self, name, product, data):
        self.name, self.product, self.state = name, product, Path(data) / 'state.json'
        self.requests = []
        self.sessions = set()
        self.opened = 0
        self.text = 'profile tool result'
        self.holding = False
        self.held, self.release = asyncio.Event(), asyncio.Event()

    def hold(self):
        self.holding = True
        self.held, self.release = asyncio.Event(), asyncio.Event()

    async def __call__(self, request):
        self.requests.append(request)
        token = json.loads(self.state.read_text())['child_token']
        if request.headers.get_list('authorization') != ['Bearer ' + token] or request.url.path != '/mcp':
            return httpx.Response(401)
        message = json.loads(request.content) if request.content else {}
        session = request.headers.get('mcp-session-id')
        if message.get('method') != 'initialize' and session not in self.sessions:
            return httpx.Response(404)
        if request.method == 'DELETE':
            self.sessions.discard(session)
            return httpx.Response(200)
        if 'id' not in message:
            return httpx.Response(202)
        method = message['method']
        if method == 'initialize':
            self.opened += 1
            session = f'{self.name}-session-{self.opened}'
            self.sessions.add(session)
            return httpx.Response(200, headers={'mcp-session-id': session}, json={
                'jsonrpc': '2.0', 'id': message['id'], 'result': {
                    'protocolVersion': message['params']['protocolVersion'], 'capabilities': {'tools': {}},
                    'serverInfo': {'name': 'profile-child', 'version': '0'}}})
        if method == 'ping':
            result = {}
        elif method == 'tools/list':
            result = {'tools': listing(self.product)}
        else:
            name = message['params']['name']
            if name == probe_name(self.product):
                text = json.dumps(PROBE_ANSWERS[self.product])
            else:
                if self.holding:
                    self.holding = False
                    self.held.set()
                    await self.release.wait()
                text = self.text
            result = {'content': [{'type': 'text', 'text': text}], 'isError': False}
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': message['id'], 'result': result})


def public_read(product):
    return ('n8n_list_workflows', {'limit': 1}) if product == 'n8n' else PROBES[product]


def product_options(product):
    """make_apps' product options as the product's runtime passes them (run_product; apps/n8n/run.py for n8n)."""
    if product == 'n8n':
        return dict(management=ManagementOptions(kind='ha-addon', authority='ha-admin'), server_name='woow-mcp-n8n',
                    listing=listing('n8n'))
    return dict(management=ManagementOptions(kind='ha-addon', authority='ha-admin',
                                             product_version=version_for_product(product)),
                server_name='woow-mcp-' + product, instructions=INSTRUCTIONS.get(product),
                listing=listing(product) if product in FULL_PRODUCTS else None,
                secret_path_allowed_origins=frozenset({'https://claude.ai'}) if product == 'headscale' else None)


class RecordingSupervisor(NoProcessSupervisor):
    """NoProcessSupervisor that keeps every spec it was started on, and whether its runtime's child client (client, when
    a test names it) was already closed each time it was stopped."""

    def __init__(self, spec, **options):
        super().__init__(spec, **options)
        self.options, self.started, self.stopped = options, [], []
        self.client = None

    def _start_child(self):
        if self.spec is not None:
            self.started.append(self.spec)
        super()._start_child()

    async def stop(self):
        self.stopped.append(None if self.client is None else self.client.is_closed)
        await super().stop()


@dataclass
class Profile:
    name: str
    product: str
    directory: Path
    runtime: object
    child: ProfileChild

    @property
    def token(self):
        return stored(self.directory)['token']

    def mcp(self):
        return GENUINE_CLIENT(transport=httpx.ASGITransport(app=self.runtime.mcp_app), base_url='http://mcp')

    def admin(self):
        return GENUINE_CLIENT(transport=httpx.ASGITransport(app=self.runtime.admin_app, client=INGRESS),
                              base_url='http://admin')


class Profiles:
    """ProfileRuntimes opened in this process; each profile's child behind its own port of one MockTransport. Closing
    closes every runtime, then the stores (the runtime borrows its store: the opener closes it)."""

    def __init__(self, tmp_path, monkeypatch, log_scan):
        self.tmp_path, self.log_scan = tmp_path, log_scan
        self.children = {}  # port -> ProfileChild
        self.sent = {}  # profile name -> the URLs its runtime's own child client requested
        self.verified = []  # every user the role verifier was asked about
        self.stack = AsyncExitStack()
        self.module = runtime_module()
        monkeypatch.setattr(self.module, 'Supervisor', RecordingSupervisor)
        monkeypatch.setattr(self.module.httpx, 'AsyncClient', self.client)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.stack.__aexit__(*exc)

    def client(self, *args, **kwargs):
        kwargs.setdefault('transport', httpx.MockTransport(self.route))
        return GENUINE_CLIENT(*args, **kwargs)

    async def route(self, request):
        child = self.children.get(request.url.port) if request.url.host == '127.0.0.1' else None
        if child is None:
            raise httpx.ConnectError('nothing listens on this port', request=request)
        return await child(request)

    async def verify(self, user):
        self.verified.append(user)
        return user == ADMIN['X-Remote-User-Id']

    def shared(self, **kwargs):
        return self.module.SharedAdmin(AdminAuthority(self.verify), **kwargs)

    def requests(self):
        return sum(len(child.requests) for child in self.children.values())

    async def open(self, name, product=PRODUCT, *, port, profile_id='default', configured=True, shared=None,
                   view=None, lifecycle=None, options=None):
        directory = self.tmp_path / name
        if configured:
            store = ProductStore(directory, product)
            try:
                store.update(**(connection_of(product, name) if product == 'n8n'
                                else {'connection': connection_of(product, name)}))
            finally:
                store.close()
        child = self.children[port] = ProfileChild(name, product, directory)
        store = ProductStore(directory, product)
        self.stack.callback(store.close)
        self.log_scan.watch_state(store.load())
        tools, spec = (n8n_adapter.TOOLS, n8n_adapter.child_spec) if product == 'n8n' else (TOOLS[product], child_spec)
        app_options = {**product_options(product), **(options or {})}
        if shared is None:
            app_options.setdefault('verify_admin', self.verify)
        runtime = self.module.ProfileRuntime(store, tools, spec, port=port, profile_id=profile_id, lifecycle=lifecycle,
                                             shared=shared, profile_view=view, app_options=app_options)
        await self.stack.enter_async_context(runtime)
        sent = self.sent.setdefault(name, set())

        async def record(request):
            sent.add(str(request.url))
        runtime.child.event_hooks['request'].append(record)
        await runtime.launch()
        await runtime.health.check()
        return Profile(name, product, directory, runtime, child)


def bearer(token):
    return {**ACCEPT, 'Authorization': 'Bearer ' + token}


def paths(token):
    """Both connection paths of one token: (path, headers)."""
    return (('/mcp', bearer(token)), (f'/private_{token}/mcp', dict(ACCEPT)))


async def bootstrap(profile):
    async with profile.admin() as admin:
        response = await admin.get('/api/bootstrap', headers=ADMIN)
        assert response.status_code == 200
        return response.json()


async def apply_state(profile):
    return (await bootstrap(profile))['configuration']['apply_state']


async def token_action(profile, action):
    """The panel's token rotate or revoke on this profile (its CSRF token, If-Match and Idempotency-Key)."""
    async with profile.admin() as admin:
        boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
        response = await admin.post('/api/token/' + action, headers=reviewed_headers(boot, ADMIN))
        assert response.status_code == 200, action
        return response.json().get('token')


async def opened_session(client, path, headers):
    init = await client.post(path, headers=headers, json=initialize_message())
    assert init.status_code == 200, init.status_code
    return init.headers['mcp-session-id']


def tool_call(ident, product=PRODUCT):
    tool, arguments = public_read(product)
    return {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call', 'params': {'name': tool, 'arguments': arguments}}


# ---- the runtime: what it carries, what it refuses ----

def test_make_apps_takes_the_shared_and_external_objects_as_keyword_only_options():
    parameters = inspect.signature(make_apps).parameters
    assert list(parameters)[:3] == ['store', 'tools', 'child']
    for name in ('authority', 'admin_slots', 'admin_pipeline', 'token_access', 'mutation_lock', 'profile_view'):
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY and parameters[name].default is None, name
    module = runtime_module()
    parameters = inspect.signature(module.ProfileRuntime).parameters
    assert list(parameters)[:3] == ['store', 'tools', 'child_spec']
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in list(parameters.values())[3:])
    assert parameters['port'].default == lifecycle.CHILD_PORT
    assert parameters['profile_id'].default == module.DEFAULT_PROFILE == 'default'


async def test_a_runtime_carries_its_profile_id_port_and_store(tmp_path, monkeypatch, log_scan):
    """PaaS test_default_manager_and_registry_managers_carry_their_profile_id: every profile's runtime is its own."""
    async with Profiles(tmp_path, monkeypatch, log_scan) as profiles:
        default = await profiles.open('default', port=DEFAULT_PORT)
        extra = await profiles.open('extra', port=EXTRA_PORT, profile_id=EXTRA_ID)
        for profile, profile_id, port in ((default, 'default', DEFAULT_PORT), (extra, EXTRA_ID, EXTRA_PORT)):
            runtime = profile.runtime
            assert (runtime.profile_id, runtime.port) == (profile_id, port)
            assert runtime.child_url == lifecycle.child_url(port) == f'http://127.0.0.1:{port}/mcp'
            assert Path(runtime.store.directory) == profile.directory
            assert runtime.token_access.store is runtime.store and isinstance(runtime.token_access, TokenAccess)
            assert isinstance(runtime.mutation_lock, asyncio.Lock)
            assert runtime.supervisor.options == {}  # no lifecycle options: Supervisor(None), as run_product had it
        pieces = ('supervisor', 'child', 'health', 'configuration', 'token_access', 'mutation_lock', 'admin_app',
                  'mcp_app')
        assert all(getattr(default.runtime, name) is not getattr(extra.runtime, name) for name in pieces)


async def test_a_runtime_refuses_what_is_not_its_own(tmp_path):
    module = runtime_module()
    store = ProductStore(tmp_path / 'state', PRODUCT)
    try:
        def build(**kwargs):
            return module.ProfileRuntime(store, TOOLS[PRODUCT], child_spec, **kwargs)
        build(profile_id=EXTRA_ID, port=EXTRA_PORT)
        for profile_id in ('Default', 'DEFAULT', ' default', 'default\n', 'AB' * 12, 'ab' * 11 + 'a', 'ab' * 13,
                           'g' * 24, '', None, 1):
            with pytest.raises(ValueError, match='invalid profile id'):
                build(profile_id=profile_id)
        for port in (0, 65536, -1, True, None, '18000', 18000.0):
            with pytest.raises(ValueError, match='invalid child port'):
                build(port=port)
        for name in ('child_url', 'health', 'backend_changed', 'configuration', 'backend_check', 'restart_child',
                     'diagnostics', 'availability', 'token_access', 'mutation_lock', 'authority', 'admin_slots',
                     'admin_pipeline', 'profile_view'):
            with pytest.raises(ValueError, match='the runtime passes'):
                build(app_options={name: None})
        with pytest.raises(ValueError, match='not a shared administration'):
            build(shared=object())
        with pytest.raises(ValueError, match='invalid profile echo'):
            build(profile_view={'id': 'default'})
    finally:
        store.close()


async def test_lifecycle_options_reach_the_profiles_supervisor(tmp_path, monkeypatch, log_scan):
    async with Profiles(tmp_path, monkeypatch, log_scan) as profiles:
        extra = await profiles.open('extra', port=EXTRA_PORT, profile_id=EXTRA_ID,
                                    lifecycle={'retries': 0, 'backoff': .5, 'grace': 1.0})
        supervisor = extra.runtime.supervisor
        assert supervisor.options == {'retries': 0, 'backoff': .5, 'grace': 1.0}
        assert (supervisor.retries, supervisor.backoff, supervisor.grace) == (0, .5, 1.0)


# ---- two runtimes in one process share nothing ----

@pytest.mark.parametrize('product', PRODUCTS)
async def test_two_runtimes_keep_their_tokens_and_children_apart(tmp_path, monkeypatch, log_scan, product):
    """Every shipped product's child_spec(state, directory, port) fits the runtime (plan risk 19): two profiles of it
    in one process, each answering its own token only, each child reached on its own port with its own bearer. n8n's
    catalog copy (n8n_adapter.prepare_catalog's nodes.db, the child's NODE_DB_PATH) is not made here: it is one per
    process, and where an extra profile's copy goes is DQ-04 (HM-25)."""
    async with Profiles(tmp_path, monkeypatch, log_scan) as profiles:
        default = await profiles.open('default', product, port=DEFAULT_PORT)
        extra = await profiles.open('extra', product, port=EXTRA_PORT, profile_id=EXTRA_ID)
        for own, other in ((default, extra), (extra, default)):
            token = own.token
            async with own.mcp() as client:
                for path, headers in paths(token):
                    session = await opened_session(client, path, headers)
                    assert re.fullmatch(own.name + r'-session-[0-9]+', session), path.replace(token, '<token>')
                    listed = await client.post(path, headers={**headers, 'Mcp-Session-Id': session},
                                               json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
                    # The same answer as the golden default profile's: the profile's own gateway, the same rewrite.
                    assert hashlib.sha256(listed.content).hexdigest() == LISTED_SHA256[product]
                    deleted = await client.delete(path, headers={**headers, 'Mcp-Session-Id': session})
                    assert answer(deleted) == SESSION_DELETED
            # Its token on the other profile: the answers of any wrong token, and no child is asked.
            since = profiles.requests()
            async with other.mcp() as client:
                bearer_answer = await client.post('/mcp', headers=bearer(token), json=initialize_message())
                secret_answer = await client.post(f'/private_{token}/mcp', headers=ACCEPT, json=initialize_message())
            assert answer(bearer_answer) == BEARER_REQUIRED and answer(secret_answer) == NOT_FOUND
            assert profiles.requests() == since
        # Every request a runtime's own child client sent (health check, capability probe aside, every client request)
        # went to its own child, which answers only its own bearer.
        assert profiles.sent == {'default': {lifecycle.child_url(DEFAULT_PORT)},
                                 'extra': {lifecycle.child_url(EXTRA_PORT)}}
        assert all(request.url.port == DEFAULT_PORT for request in default.child.requests)
        assert all(request.url.port == EXTRA_PORT for request in extra.child.requests)


@pytest.mark.parametrize('product', PRODUCTS)
async def test_each_child_is_started_on_its_own_state_directory_and_port(tmp_path, monkeypatch, log_scan, product):
    """PaaS test_registry_reloads_saved_profiles_and_child_env_uses_their_files: each profile's child runs on the spec
    its own saved state and directory give, on its own port (HM-04 decides what a port changes in a spec)."""
    async with Profiles(tmp_path, monkeypatch, log_scan) as profiles:
        default = await profiles.open('default', product, port=DEFAULT_PORT)
        extra = await profiles.open('extra', product, port=EXTRA_PORT, profile_id=EXTRA_ID)
        build = n8n_adapter.child_spec if product == 'n8n' else child_spec
        for profile, port in ((default, DEFAULT_PORT), (extra, EXTRA_PORT)):
            started = profile.runtime.supervisor.started
            assert len(started) == 1
            spec = started[0]
            assert spec == build(profile.runtime.store.load(), profile.directory, port=port)
            assert Path(spec.cwd).is_relative_to(profile.directory)
            values = set(spec.env.values())
            other = extra if profile is default else default
            assert identity_of(product, profile.name) <= values and not identity_of(product, other.name) & values


async def test_child_sessions_stay_with_their_profile(tmp_path, monkeypatch, log_scan):
    """FM-32: a session the default profile's child opened is unknown to the extra profile (its child answers 404, as
    for any session it never opened); the extra profile cannot end it either; the default profile's child is not
    asked; the session still serves the default profile afterwards."""
    async with Profiles(tmp_path, monkeypatch, log_scan) as profiles:
        default = await profiles.open('default', port=DEFAULT_PORT)
        extra = await profiles.open('extra', port=EXTRA_PORT, profile_id=EXTRA_ID)
        async with default.mcp() as default_client, extra.mcp() as extra_client:
            session = await opened_session(default_client, '/mcp', bearer(default.token))
            asked = len(default.child.requests)
            in_session = {**bearer(extra.token), 'Mcp-Session-Id': session}
            listed = await extra_client.post('/mcp', headers=in_session,
                                             json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
            assert listed.status_code == 404 and listed.json() == {
                'jsonrpc': '2.0', 'id': 2, 'error': {'code': -32000, 'message': 'Not Found'}}
            assert (await extra_client.delete('/mcp', headers=in_session)).status_code == 404
            assert len(default.child.requests) == asked
            pinged = await default_client.post('/mcp', headers={**bearer(default.token), 'Mcp-Session-Id': session},
                                               json={'jsonrpc': '2.0', 'id': 3, 'method': 'ping'})
            assert pinged.status_code == 200 and pinged.json() == {'jsonrpc': '2.0', 'id': 3, 'result': {}}


async def test_the_gateways_own_sessions_stay_with_their_profile(tmp_path, monkeypatch, log_scan):
    """FM-32: without a backend the gateway opens a session of its own (woow-local-...); it is a session of that
    profile's gateway only: the other profile answers 404 for it and cannot end it."""
    async with Profiles(tmp_path, monkeypatch, log_scan) as profiles:
        default = await profiles.open('default', port=DEFAULT_PORT, configured=False)
        extra = await profiles.open('extra', port=EXTRA_PORT, profile_id=EXTRA_ID, configured=False)
        async with default.mcp() as default_client, extra.mcp() as extra_client:
            session = await opened_session(default_client, '/mcp', bearer(default.token))
            assert re.fullmatch(r'woow-local-[0-9a-f]{32}', session)
            in_session = {**bearer(extra.token), 'Mcp-Session-Id': session}
            listed = await extra_client.post('/mcp', headers=in_session,
                                             json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
            assert listed.status_code == 404
            assert (await extra_client.delete('/mcp', headers=in_session)).status_code == 404
            pinged = await default_client.post('/mcp', headers={**bearer(default.token), 'Mcp-Session-Id': session},
                                               json={'jsonrpc': '2.0', 'id': 3, 'method': 'ping'})
            assert pinged.status_code == 200 and pinged.json() == {'jsonrpc': '2.0', 'id': 3, 'result': {}}
        assert profiles.requests() == 0  # no child: nothing configured


async def test_a_token_change_ends_only_its_own_profiles_requests(tmp_path, monkeypatch, log_scan):
    """FM-33, invariant I3: each profile's TokenAccess. Rotating the extra profile's token while a call of the default
    profile waits for its child does not end that call; revoking the default profile's token ends its call at once
    and not the extra profile's."""
    async with Profiles(tmp_path, monkeypatch, log_scan) as profiles:
        default = await profiles.open('default', port=DEFAULT_PORT)
        extra = await profiles.open('extra', port=EXTRA_PORT, profile_id=EXTRA_ID)
        async with default.mcp() as default_client, extra.mcp() as extra_client:
            default_token, extra_token = default.token, extra.token
            default_session = await opened_session(default_client, '/mcp', bearer(default_token))
            extra_session = await opened_session(extra_client, '/mcp', bearer(extra_token))

            def call(client, token, session, ident):
                return asyncio.create_task(client.post('/mcp', json=tool_call(ident),
                                                       headers={**bearer(token), 'Mcp-Session-Id': session}))

            default.child.hold()
            pending = call(default_client, default_token, default_session, 3)
            await asyncio.wait_for(default.child.held.wait(), 5)
            rotated = await token_action(extra, 'rotate')
            log_scan.watch(rotated)
            await asyncio.sleep(.5)  # longer than a lease's revocation poll (access.py: .2 s)
            assert not pending.done()
            default.child.release.set()
            answered = await asyncio.wait_for(pending, 5)
            assert answered.status_code == 200 and answered.json()['result']['content'][0]['text'] == default.child.text
            refused = await extra_client.post('/mcp', headers=bearer(extra_token), json=initialize_message())
            assert answer(refused) == BEARER_REQUIRED  # the old token, on its own profile

            extra_session = await opened_session(extra_client, '/mcp', bearer(rotated))
            extra.child.hold()
            extra_pending = call(extra_client, rotated, extra_session, 4)
            await asyncio.wait_for(extra.child.held.wait(), 5)
            default.child.hold()
            default_pending = call(default_client, default_token, default_session, 5)
            await asyncio.wait_for(default.child.held.wait(), 5)
            assert await token_action(default, 'revoke') is None
            ended = await asyncio.wait_for(default_pending, 5)
            assert ended.status_code == 401 and ended.json() == {'error': 'request denied'}
            await asyncio.sleep(.5)
            assert not extra_pending.done()
            extra.child.release.set()
            answered = await asyncio.wait_for(extra_pending, 5)
            assert answered.status_code == 200 and answered.json()['result']['content'][0]['text'] == extra.child.text


async def test_a_save_restarts_only_its_own_child(tmp_path, monkeypatch, log_scan):
    """FM-47 and T-16 (the apply status is per profile): a backend saved on the default profile restarts its child on
    the new state; the extra profile's child is not stopped or restarted and its status stays applied."""
    async with Profiles(tmp_path, monkeypatch, log_scan) as profiles:
        default = await profiles.open('default', port=DEFAULT_PORT)
        extra = await profiles.open('extra', port=EXTRA_PORT, profile_id=EXTRA_ID)
        assert [await apply_state(profile) for profile in (default, extra)] == ['applied', 'applied']
        before = stat_signature(extra.directory / 'state.json')
        password = 'DUMMY-default-odoo-password-saved'
        log_scan.watch(password, kind='secret')
        async with default.admin() as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            saved = await admin.put('/api/backend', headers=reviewed_headers(boot, ADMIN),
                                    json={'connection': {**connection_of(PRODUCT, 'default'), 'password': password}})
        assert saved.status_code == 200 and saved.json()['saved'] is True
        assert [len(profile.runtime.supervisor.started) for profile in (default, extra)] == [2, 1]
        assert default.runtime.supervisor.started[-1].env['ODOO_PASSWORD'] == password
        assert extra.runtime.supervisor.started[-1].env['ODOO_PASSWORD'] == 'DUMMY-extra-odoo-password'
        assert extra.runtime.supervisor.status == 'running'
        assert [await apply_state(profile) for profile in (default, extra)] == ['pending', 'applied']
        await default.runtime.health.check()
        assert [await apply_state(profile) for profile in (default, extra)] == ['applied', 'applied']
        assert stat_signature(extra.directory / 'state.json') == before


async def test_each_profile_keeps_its_own_child_output(tmp_path, monkeypatch, log_scan):
    """FM-65, T-18 (PaaS test_busy_profile_cannot_empty_a_quiet_profiles_logs_page, ..._keeps_its_own_newest_lines_up_
    to_its_cap, test_all_live_profiles_fit_in_the_buffer_limit, test_total_buffer_memory_stays_under_the_documented_
    ceiling): every profile's Supervisor keeps its own child output (contract 8.8 #29: 200 lines, 128 KiB each). A
    flooded profile keeps its newest lines and empties no other profile's page; six profiles hold at most six times
    one buffer."""
    async with Profiles(tmp_path, monkeypatch, log_scan) as profiles:
        quiet = await profiles.open('default', port=DEFAULT_PORT)
        busy = [await profiles.open(f'extra{index}', port=EXTRA_PORT + index, profile_id=f'{index:024x}')
                for index in range(1, 6)]
        for line in ('quiet one', 'quiet two'):
            quiet.runtime.supervisor.logs.append('stdout', line, 1)
        for profile in busy:
            for index in range(MAX_ENTRIES * 3):
                profile.runtime.supervisor.logs.append('stderr', f'{profile.name} line {index} ' + 'x' * 600, 1)
        pages = {}
        for profile in (quiet, *busy):
            async with profile.admin() as admin:
                response = await admin.get('/api/diagnostics', headers=ADMIN)
            assert response.status_code == 200
            pages[profile.name] = response.json()['logs']
        assert [entry['text'] for entry in pages['default']['entries']] == ['quiet one', 'quiet two']
        for profile in busy:
            page = pages[profile.name]
            texts = [entry['text'] for entry in page['entries']]
            assert texts and all(text.startswith(profile.name + ' line ') for text in texts)
            assert texts[-1].startswith(f'{profile.name} line {MAX_ENTRIES * 3 - 1} ')
            assert len(texts) <= MAX_ENTRIES and page['bytes'] <= MAX_BYTES and page['dropped'] > 0
        assert sum(page['bytes'] for page in pages.values()) <= 6 * MAX_BYTES


async def test_each_profile_redacts_its_replies_with_its_own_secrets(tmp_path, monkeypatch, log_scan):
    """FM-76: every profile's app redacts what its child relays with its own state's credentials."""
    async with Profiles(tmp_path, monkeypatch, log_scan) as profiles:
        default = await profiles.open('default', port=DEFAULT_PORT)
        extra = await profiles.open('extra', port=EXTRA_PORT, profile_id=EXTRA_ID)
        for profile in (default, extra):
            password = connection_of(PRODUCT, profile.name)['password']
            profile.child.text = f'the backend said: {password}'
            async with profile.mcp() as client:
                session = await opened_session(client, '/mcp', bearer(profile.token))
                called = await client.post('/mcp', json=tool_call(3),
                                           headers={**bearer(profile.token), 'Mcp-Session-Id': session})
            assert called.status_code == 200 and password.encode() not in called.content
            assert called.json()['result']['content'][0]['text'] == 'the backend said: [REDACTED]'


async def test_each_runtime_makes_its_child_client_as_run_product_did(tmp_path, monkeypatch, log_scan):
    """The child client of every runtime has the options run_product.run gave it before HM-05 (plan 3.2, 5.2): no proxy
    or .netrc from the environment (trust_env=False: a child bearer never goes through HTTP(S)_PROXY), no redirect
    followed, 10 s per request (3 s to connect) and 40 connections (the default profile's number; HM-08 sets the extra
    profiles' own)."""
    made = []
    async with Profiles(tmp_path, monkeypatch, log_scan) as profiles:
        build = profiles.client

        def recording(*args, **kwargs):
            made.append(dict(kwargs))
            return build(*args, **kwargs)
        monkeypatch.setattr(profiles.module.httpx, 'AsyncClient', recording)
        await profiles.open('default', port=DEFAULT_PORT)
        await profiles.open('extra', port=EXTRA_PORT, profile_id=EXTRA_ID)
    expected = dict(trust_env=False, follow_redirects=False, timeout=httpx.Timeout(10, connect=3),
                    limits=httpx.Limits(max_connections=40))
    assert made == [expected, expected]


async def test_each_profile_keeps_its_own_receipts(tmp_path, monkeypatch, log_scan):
    """Plan 3.2 (receipts are per profile; contract 3.5: the profile directory's .state.json.operations.json): a token
    rotation on either profile writes its receipt in that profile's directory only, and only that profile knows the
    operation (the other answers 404 operation_not_found); the other profile's directory is unchanged."""
    async with Profiles(tmp_path, monkeypatch, log_scan) as profiles:
        default = await profiles.open('default', port=DEFAULT_PORT)
        extra = await profiles.open('extra', port=EXTRA_PORT, profile_id=EXTRA_ID)
        for own, other in ((extra, default), (default, extra)):
            before = tree(other.directory)
            async with own.admin() as admin:
                boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
                rotated = await admin.post('/api/token/rotate', headers=reviewed_headers(boot, ADMIN))
                assert rotated.status_code == 200
                log_scan.watch(rotated.json()['token'])
                operation = rotated.json()['operation']['id']
                assert (await admin.get('/api/operations/' + operation, headers=ADMIN)).status_code == 200
            assert (own.directory / '.state.json.operations.json').is_file()
            assert tree(other.directory) == before
            async with other.admin() as admin:
                unknown = await admin.get('/api/operations/' + operation, headers=ADMIN)
            assert unknown.status_code == 404 and unknown.json() == {
                'error': 'request denied', 'detail': {'code': 'operation_not_found'}}


# ---- what the add-on shares: one administration ----

async def test_one_shared_authority_one_csrf_and_another_profiles_etag_is_a_conflict(tmp_path, monkeypatch, log_scan):
    """FM-54 and FM-06 (PaaS test_admin_logout_uses_global_store_across_profiles; plan A-port P2): with one SharedAdmin
    the panel's CSRF token is the same for every profile and is accepted by every profile, while a write that names
    another profile's ETag is a conflict (409 config_conflict, shape B) and changes nothing. Without it, each profile's
    apps have their own key (as two add-ons would)."""
    async with Profiles(tmp_path, monkeypatch, log_scan) as profiles:
        shared = profiles.shared()
        default = await profiles.open('default', port=DEFAULT_PORT, shared=shared)
        extra = await profiles.open('extra', port=EXTRA_PORT, profile_id=EXTRA_ID, shared=shared)
        default_boot, extra_boot = await bootstrap(default), await bootstrap(extra)
        assert default_boot['csrf'] == extra_boot['csrf']
        assert default_boot['configuration']['revision'] != extra_boot['configuration']['revision']
        policy = {'writes_enabled': False, 'disabled': []}
        signatures = {profile.name: stat_signature(profile.directory / 'state.json') for profile in (default, extra)}
        async with extra.admin() as admin:
            conflict = await admin.put('/api/policy', json=policy,
                                       headers={**ADMIN, 'X-CSRF-Token': default_boot['csrf'],
                                                'If-Match': '"' + default_boot['configuration']['revision'] + '"'})
            assert conflict.status_code == 409 and conflict.content == b'{"detail":{"code":"config_conflict"}}'
            assert {profile.name: stat_signature(profile.directory / 'state.json')
                    for profile in (default, extra)} == signatures
            saved = await admin.put('/api/policy', json=policy,
                                    headers={**ADMIN, 'X-CSRF-Token': default_boot['csrf'],
                                             'If-Match': '"' + extra_boot['configuration']['revision'] + '"'})
            assert saved.status_code == 200 and saved.json()['saved'] is True
        assert stored(extra.directory)['writes_enabled'] is False
        assert stat_signature(default.directory / 'state.json') == signatures['default']
        assert stored(default.directory)['writes_enabled'] is True
        # The one role verifier was asked for both profiles' requests.
        assert set(profiles.verified) == {ADMIN['X-Remote-User-Id']} and len(profiles.verified) >= 4
    async with Profiles(tmp_path / 'apart', monkeypatch, log_scan) as profiles:
        default = await profiles.open('default', port=DEFAULT_PORT)
        extra = await profiles.open('extra', port=EXTRA_PORT, profile_id=EXTRA_ID)
        default_boot, extra_boot = await bootstrap(default), await bootstrap(extra)
        assert default_boot['csrf'] != extra_boot['csrf']
        async with extra.admin() as admin:
            refused = await admin.put('/api/policy', json={'writes_enabled': False, 'disabled': []},
                                      headers={**ADMIN, 'X-CSRF-Token': default_boot['csrf'],
                                               'If-Match': '"' + extra_boot['configuration']['revision'] + '"'})
        assert refused.status_code == 403 and refused.content == b'{"error":"request denied"}'


async def test_shared_management_slots_are_one_budget_for_every_profile(tmp_path, monkeypatch, log_scan):
    """FM-54: the add-on's 16 management slots (gateway.ADMIN_SLOTS). Eight requests on each of two profiles that
    share them hold all 16, so a seventeenth on either is refused (503) before its body is read; profiles that do not
    share them have 16 each."""
    assert gateway.ADMIN_SLOTS == 16
    for share in (True, False):
        async with Profiles(tmp_path / str(share), monkeypatch, log_scan) as profiles:
            shared = profiles.shared() if share else None
            default = await profiles.open('default', port=DEFAULT_PORT, shared=shared)
            extra = await profiles.open('extra', port=EXTRA_PORT, profile_id=EXTRA_ID, shared=shared)
            gate = asyncio.Event()
            held = []

            def hold(app):
                scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': 'GET',
                         'scheme': 'http', 'path': '/api/bootstrap', 'raw_path': b'/api/bootstrap',
                         'query_string': b'', 'root_path': '', 'client': INGRESS, 'server': ('admin', 80),
                         'headers': [(b'host', b'admin'), (b'x-remote-user-id', ADMIN['X-Remote-User-Id'].encode())]}
                sent = []
                received = []

                async def receive():
                    if not received:
                        received.append(True)
                        await gate.wait()  # the body never arrives until the gate opens: the slot stays taken
                        return {'type': 'http.request', 'body': b'', 'more_body': False}
                    await asyncio.Event().wait()

                async def send(message):
                    sent.append(message)
                held.append(sent)
                return asyncio.create_task(app(scope, receive, send))

            tasks = [hold(profile.runtime.admin_app) for profile in (default, extra) for _ in range(8)]
            await asyncio.sleep(.1)
            assert not any(task.done() for task in tasks)
            for profile in (default, extra):
                async with profile.admin() as admin:
                    response = await admin.get('/api/bootstrap', headers=ADMIN)
                if share:
                    assert response.status_code == 503 and response.content == b'{"error":"request denied"}'
                else:
                    assert response.status_code == 200
            gate.set()
            await asyncio.wait_for(asyncio.gather(*tasks), 5)
            assert [messages[0]['status'] for messages in held] == [200] * 16


# ---- make_apps' new options, one by one ----

@pytest.fixture
def two_stores(tmp_path):
    stores = [ProductStore(tmp_path / name, PRODUCT) for name in ('first', 'second')]
    yield stores
    for store in stores:
        store.close()


def apps(store, **kwargs):
    return make_apps(store, TOOLS[PRODUCT], GENUINE_CLIENT(transport=httpx.MockTransport(lambda _: httpx.Response(500))),
                     **kwargs)


def admin_client(app):
    return GENUINE_CLIENT(transport=httpx.ASGITransport(app=app, client=INGRESS), base_url='http://admin')


async def allowed(user):
    return user == ADMIN['X-Remote-User-Id']


async def test_a_shared_authority_is_the_one_role_verifier(two_stores):
    """The role verifier is the authority's (one HA role verifier and its concurrent-query bound for every profile):
    verify_admin, when also given, must be that verifier."""
    first, _ = two_stores
    authority = AdminAuthority(allowed)

    async def other(user):
        return True
    apps(first, authority=authority)
    apps(first, authority=authority, verify_admin=allowed)
    for value in (dict(authority=authority, verify_admin=other), dict(authority=object())):
        with pytest.raises(ValueError, match='one administrator authority'):
            apps(first, **value)


async def test_external_objects_must_be_this_profiles(two_stores):
    first, second = two_stores
    with pytest.raises(ValueError, match='token access of another store'):
        apps(first, token_access=TokenAccess(second))
    for name, value in (('token_access', object()), ('mutation_lock', object()), ('admin_slots', object()),
                        ('admin_pipeline', object()), ('profile_view', object())):
        with pytest.raises(ValueError):
            apps(first, **{name: value})
    for view in ({'id': 'default'}, {'id': 'default', 'label': 'Default', 'is_default': 1},
                 {'id': 'Default', 'label': 'Default', 'is_default': True},
                 {'id': EXTRA_ID, 'label': '', 'is_default': False},
                 {'id': EXTRA_ID, 'label': 'Alpha Prod', 'is_default': True},
                 {'id': 'default', 'label': 'Default', 'is_default': False},
                 {'id': 'default', 'label': 'Default', 'is_default': True, 'port': 3000}, None):
        with pytest.raises(ValueError, match='invalid profile echo'):
            apps(first, profile_view=lambda value=view: value)


async def test_the_apps_use_the_token_access_and_lock_they_are_given(two_stores, log_scan):
    """token_access: the app ends this store's leases through it after a token change (its committed());
    mutation_lock: every management change of the app waits for it."""
    first, _ = two_stores
    log_scan.watch_state(first.load())
    access, lock = TokenAccess(first), asyncio.Lock()
    committed = []
    original = access.committed
    access.committed = lambda: (committed.append(True), original())[1]
    admin, _ = apps(first, verify_admin=allowed, token_access=access, mutation_lock=lock)
    async with admin_client(admin) as client:
        boot = (await client.get('/api/bootstrap', headers=ADMIN)).json()
        await lock.acquire()
        saving = asyncio.create_task(client.put('/api/policy', headers=reviewed_headers(boot, ADMIN),
                                                json={'writes_enabled': False, 'disabled': []}))
        await asyncio.sleep(.3)
        assert not saving.done()  # waits for the profile's lock (bounded: 2 s, then 503)
        lock.release()
        assert (await asyncio.wait_for(saving, 5)).status_code == 200
        boot = (await client.get('/api/bootstrap', headers=ADMIN)).json()
        rotated = await client.post('/api/token/rotate', headers=reviewed_headers(boot, ADMIN))
        assert rotated.status_code == 200
        log_scan.watch(rotated.json()['token'])
    assert committed == [True]


async def test_the_profile_echo_marks_this_profiles_answers(two_stores, log_scan):
    """profile_view (plan 5.3 item 5, contract 3.4; DQ-40 point 2): the bootstrap names the profile (id, label,
    is_default) and says profiles_supported; every other JSON answer of the profile's action names its id. A refusal
    (not an administrator, a missing If-Match) and a page are answered as without it: the echo follows the final role
    check and never shows before it (invariant I10). The view is read for every answer (a rename shows at once)."""
    first, second = two_stores
    log_scan.watch(SHARED_ECHO['label'], 'Beta Prod', kind='name')
    log_scan.watch_state(first.load())
    authority = AdminAuthority(allowed)
    view = dict(SHARED_ECHO)
    echoing, _ = apps(first, authority=authority, profile_view=lambda: dict(view))
    plain, _ = apps(second, authority=authority)
    async with admin_client(echoing) as client, admin_client(plain) as other:
        boot = await client.get('/api/bootstrap', headers=ADMIN)
        body = boot.json()
        assert set(body) == BOOTSTRAP_COMMON | BOOTSTRAP_EXTRA[PRODUCT] | {'profile', 'profiles_supported'}
        assert body['profile'] == SHARED_ECHO and body['profiles_supported'] is True
        assert list(body)[-2:] == ['profile', 'profiles_supported']
        plain_body = (await other.get('/api/bootstrap', headers=ADMIN)).json()
        assert set(plain_body) == BOOTSTRAP_COMMON | BOOTSTRAP_EXTRA[PRODUCT]
        configuration = await client.get('/api/configuration', headers=ADMIN)
        assert configuration.json() == {'configuration': body['configuration'], 'profile': {'id': EXTRA_ID}}
        assert configuration.headers['etag'] == '"' + body['configuration']['revision'] + '"'
        stale = await client.put('/api/policy', json={'writes_enabled': True, 'disabled': []},
                                 headers={**ADMIN, 'X-CSRF-Token': body['csrf'], 'If-Match': '"c1-' + '0' * 64 + '"'})
        assert stale.status_code == 409 and stale.json() == {'detail': {'code': 'config_conflict'},
                                                             'profile': {'id': EXTRA_ID}}
        saved = await client.put('/api/policy', json={'writes_enabled': False, 'disabled': []},
                                 headers=reviewed_headers(body, ADMIN))
        assert saved.status_code == 200 and saved.json()['saved'] is True and saved.json()['profile'] == {
            'id': EXTRA_ID}
        # As without the echo: a non-administrator's 403, a missing If-Match (428, shape A), a page.
        for path, method, headers in (('/api/bootstrap', 'GET', {'X-Remote-User-Id': 'someone-else'}),
                                      ('/api/policy', 'PUT', {**ADMIN, 'X-CSRF-Token': body['csrf']}),
                                      ('/', 'GET', ADMIN)):
            kwargs = {'json': {'writes_enabled': True, 'disabled': []}} if method == 'PUT' else {}
            echoed = await client.request(method, path, headers=headers, **kwargs)
            without = await other.request(method, path, headers=headers, **kwargs)
            assert echoed.status_code in (403, 428, 200) and answer(echoed) == answer(without), path
            assert b'Alpha Prod' not in echoed.content and EXTRA_ID.encode() not in echoed.content
        view['label'] = 'Beta Prod'
        assert (await client.get('/api/bootstrap', headers=ADMIN)).json()['profile']['label'] == 'Beta Prod'


async def test_an_injected_pipeline_takes_every_management_request(two_stores, log_scan):
    """admin_pipeline (the shared management pipeline's injection point, plan 5.3; HM-10 builds the pipeline): every
    management request (a page, an API call) that passed the page checks goes to it with the profile's own action; the
    action is this profile's (its state, its lock, the final role check), and its answer carries the profile's echo; a
    request the pipeline refuses never reaches the action, and what the pipeline answers itself carries no echo."""
    first, second = two_stores
    for store in two_stores:
        log_scan.watch_state(store.load())
    log_scan.watch(SHARED_ECHO['label'], kind='name')
    asked, seen = [], []

    async def verifier(user):
        asked.append(user)
        return await allowed(user)
    authority = AdminAuthority(verifier)

    async def pipeline(request, action):
        seen.append((request.path_params['operation'], action))
        if request.headers.get('x-test-refuse') == 'raise':
            raise BadRequest(403)
        if request.headers.get('x-test-refuse') == 'answer':
            return JSONResponse({'error': 'request denied'}, status_code=400)
        user, base, csrf = authority.identity(request)
        return await action(request, user, base, csrf, None, asyncio.Event(), asyncio.Event())

    first_admin, _ = apps(first, authority=authority, admin_pipeline=pipeline, profile_view=lambda: SHARED_ECHO)
    second_admin, _ = apps(second, authority=authority, admin_pipeline=pipeline)
    async with admin_client(first_admin) as one, admin_client(second_admin) as two:
        first_boot = await one.get('/api/bootstrap', headers=ADMIN)
        second_boot = await two.get('/api/bootstrap', headers=ADMIN)
        page = await one.get('/', headers=ADMIN)
        assert first_boot.status_code == second_boot.status_code == page.status_code == 200
        assert first_boot.json()['token_masked'] == first.load().token[:4] + '*' * 20 + first.load().token[-4:]
        assert second_boot.json()['token_masked'] == second.load().token[:4] + '*' * 20 + second.load().token[-4:]
        assert first_boot.json()['profile'] == SHARED_ECHO and 'profile' not in second_boot.json()
        assert [name for name, _ in seen] == ['bootstrap', 'bootstrap', '__ui__']
        assert seen[0][1] is not seen[1][1] and seen[0][1] is seen[2][1]
        before = len(asked)
        refused = await one.get('/api/bootstrap', headers={**ADMIN, 'X-Test-Refuse': 'raise'})
        assert refused.status_code == 403 and len(asked) == before
        answered = await one.get('/api/bootstrap', headers={**ADMIN, 'X-Test-Refuse': 'answer'})
        assert answered.status_code == 400 and answered.content == b'{"error":"request denied"}'
        assert len(asked) == before


# ---- run_product: the default profile ----

@pytest.mark.parametrize('product', [product for product in PRODUCTS if product != 'n8n'])
async def test_run_product_serves_the_default_profiles_runtime(tmp_path, monkeypatch, log_scan, product):
    """run_product builds the default profile with ProfileRuntime: one runtime, profile 'default' on the child port
    3000, on the data directory's store, with no shared administration and no lifecycle option (so make_apps creates
    its authority and slots as before) and no echo; the two listeners serve its two apps; make_apps gets the runtime's
    TokenAccess and lock. n8n keeps its own runtime until HM-25 (plan 12.2)."""
    module = runtime_module()
    built, calls = [], []

    class Recorded(module.ProfileRuntime):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            built.append(self)

    original = module.make_apps

    def recording(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(run_product, 'ProfileRuntime', Recorded)
    monkeypatch.setattr(module, 'make_apps', recording)
    data = tmp_path / 'data'
    configure(data, product)
    async with production_runtime(product, data) as runtime:
        await settle(runtime, 'configured')
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        profile, = built
        assert (profile.profile_id, profile.port, Path(profile.store.directory)) == ('default', DEFAULT_PORT, data)
        assert profile.shared is None and profile.lifecycle == {} and profile.profile_view is None
        assert runtime.admin_app is profile.admin_app and runtime.mcp_app is profile.mcp_app
        kwargs, = calls
        assert kwargs['token_access'] is profile.token_access and kwargs['mutation_lock'] is profile.mutation_lock
        assert not {'authority', 'admin_slots', 'admin_pipeline', 'profile_view'} & set(kwargs)
        assert kwargs['child_url'] == lifecycle.CHILD_URL and kwargs['server_name'] == 'woow-mcp-' + product


@pytest.mark.parametrize('port', [0, 65536, True, '3000'])
async def test_an_invalid_child_port_is_refused_before_anything_starts(tmp_path, monkeypatch, port):
    """run_product.run refuses an invalid child port first, as before HM-05 (its child_url call was the first line):
    before the legacy migration, before the store, so nothing is written."""
    from mcp_admin_core import owner_defaults
    migrated = []
    monkeypatch.setattr(owner_defaults, 'apply_legacy_upgrade', lambda *args: migrated.append(args))
    data = tmp_path / 'data'
    with pytest.raises(ValueError, match='invalid child port'):
        await run_product.run(SimpleNamespace(data=data, product=PRODUCT, host='127.0.0.1', admin_port=8099,
                                              mcp_port=8081), child_port=port)
    assert migrated == [] and not data.exists()


def tree(directory):
    """Every entry of a data directory: its relative path, file type and permission bits."""
    return {str(path.relative_to(directory)): path.lstat().st_mode for path in Path(directory).rglob('*')}


@pytest.mark.parametrize('mode', ['fresh', 'configured'])
@pytest.mark.parametrize('product', PRODUCTS)
async def test_starting_the_default_profile_adds_no_file(tmp_path, log_scan, product, mode):
    """Acceptance (plan 12.3 HM-05): /data/mcp gets no new file. The first start of an installation leaves exactly the
    entries bb48449 left (the store's lock and state; a configured product child's empty working directory), none of
    the files the multi-profile slices will add; while it serves, and after a second start, every entry is as it
    was (path, type, mode) and state.json is not even rewritten."""
    data = tmp_path / 'data'
    if mode == 'configured':
        configure(data, product)
    async with production_runtime(product, data) as runtime:
        await settle(runtime, mode)
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        serving = tree(data)
    first = tree(data)
    assert sorted(first) == expected_entries(product, mode) and first == serving
    assert not set(PROFILE_FILES) & set(first)
    state = stat_signature(data / 'state.json')
    async with production_runtime(product, data) as runtime:
        await settle(runtime, mode)
        async with runtime.admin() as admin:
            for operation in ('bootstrap', 'configuration', 'capabilities', 'diagnostics'):
                assert (await admin.get('/api/' + operation, headers=ADMIN)).status_code == 200, operation
        async with runtime.mcp() as client:
            assert (await client.post('/mcp', headers=bearer(stored(data)['token']),
                                      json=initialize_message())).status_code == 200
        assert tree(data) == first
    assert tree(data) == first and stat_signature(data / 'state.json') == state


async def test_closing_a_runtime_stops_only_its_child_and_lets_the_store_close(tmp_path, monkeypatch, log_scan):
    """A runtime closes its child client, then stops its child (the order run_product.run had: its client's async with
    ended before its finally stopped the Supervisor); the other profile keeps serving; the store is the opener's:
    closed afterwards, its writer lock is free again. An extra runtime writes nothing in the default profile's
    directory."""
    async with Profiles(tmp_path, monkeypatch, log_scan) as profiles:
        default = await profiles.open('default', port=DEFAULT_PORT)
        before = tree(default.directory)
        stack = AsyncExitStack()
        async with stack:
            store = ProductStore(tmp_path / 'extra', PRODUCT)
            stack.callback(store.close)
            profiles.children[EXTRA_PORT] = ProfileChild('extra', PRODUCT, tmp_path / 'extra')
            extra = runtime_module().ProfileRuntime(store, TOOLS[PRODUCT], child_spec, port=EXTRA_PORT,
                                                    profile_id=EXTRA_ID,
                                                    app_options={**product_options(PRODUCT),
                                                                 'verify_admin': profiles.verify})
            log_scan.watch_state(store.load())
            await stack.enter_async_context(extra)
            extra.supervisor.client = extra.child
            await extra.launch()
            assert extra.supervisor.status == 'unconfigured' and extra.supervisor.stopped == [False]
        assert extra.supervisor.status == 'stopped' and extra.child.is_closed
        assert extra.supervisor.stopped == [False, True]  # launch()'s stop, then the close's: after the client
        reopened = ProductStore(tmp_path / 'extra', PRODUCT)  # the writer lock was released
        reopened.close()
        assert default.runtime.supervisor.status == 'running' and not default.runtime.child.is_closed
        async with default.mcp() as client:
            assert (await client.post('/mcp', headers=bearer(default.token),
                                      json=initialize_message())).status_code == 200
        assert tree(default.directory) == before


@pytest.mark.parametrize('broken', ['server identity', 'profile echo'])
async def test_a_runtime_that_cannot_open_leaves_nothing_running(tmp_path, monkeypatch, log_scan, broken):
    """An open that fails (make_apps refuses the server identity; the echo names another profile than the runtime's)
    stops the Supervisor it made and closes the child client; the store stays the opener's."""
    async with Profiles(tmp_path, monkeypatch, log_scan) as profiles:
        store = ProductStore(tmp_path / 'broken', PRODUCT)
        try:
            if broken == 'server identity':
                kwargs = {'app_options': {'server_name': 'Not A Name', 'verify_admin': profiles.verify}}
            else:
                kwargs = {'app_options': {'verify_admin': profiles.verify}, 'profile_view': lambda: SHARED_ECHO}
            runtime = profiles.module.ProfileRuntime(store, TOOLS[PRODUCT], child_spec, **kwargs)
            before = set(asyncio.all_tasks())
            with pytest.raises(ValueError, match='invalid ' + broken):
                await runtime.open()
            assert runtime.supervisor.status == 'stopped' and runtime.child.is_closed
            assert runtime.supervisor.stopped == [None]  # stopped once, by the failed open's cleanup
            assert set(asyncio.all_tasks()) <= before
            assert store.load().token  # still open: the runtime borrows its store
        finally:
            store.close()
