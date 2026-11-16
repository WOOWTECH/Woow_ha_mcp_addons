"""HM-10: the management pipeline's refusal matrix, generated from its route table (multi-profile plan 5.3 point 2;
contract 3.2, 4.1; invariant I10; §8.8 #11, #12; FM-148; acceptance T-06; PaaS
test_unauthenticated_put_does_not_restart, test_protected_api_requires_token, test_bearer_token_grants_access,
test_invalid_token_rejected, test_mcp_token_rotation_keeps_current_admin_session_and_revoked_session_denied,
test_root_path_never_bypasses_admin_authentication).

The route table is gateway.PROFILE_OPERATIONS (every profile-scoped operation a profile's action answers) and
profile_router.GLOBAL_ROUTES (the global paths), plus the panel's pages. Every route of it, for every way a caller can
fail to be the HA administrator (not the ingress proxy, no or two X-Remote-User-Id, an MCP token instead, no or a wrong
CSRF token, a cross-site request, not an administrator, an HA Core this release has not reviewed), is 403, and nothing
changed: the index, the profile directories, the receipts, every child. A caller who is not an administrator gets the
very same bytes whatever the profiles' state: a label that exists or not, the limit reached or not, a profile that
exists or not, X-MCP-Profile sent or not (the first role check comes before anything that reads state). A new
operation of admin_action that is not in the table fails here; so does a table route the dispatcher does not route.

Also here (HM-01's hand-off, provenance note section 4.1): the fixed answers that had no byte-for-byte case, switched
off as today and switched on through the dispatcher, the same bytes: 503 for full management slots, for a profile lock
held over 2 s and for a state that cannot be read; 408 for a body not read within its time; 413 for a body too large;
403 for a client gone while its request waits.

Every case runs in process (tests/multi_profile_runtime.py, HM-01's production_runtime) under the HM-01 log scan.
"""
import ast
import asyncio
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import stat
import time

import httpx
import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import Children, create_profile, ids, multi_profile_runtime, stored
from mcp_admin_core import gateway, profile_router, profiles, run_product
from mcp_admin_core.ha_role import Unreviewed
from mcp_admin_core.profile_runtime import ProfileRuntime
from test_single_profile_golden import ADMIN, GENUINE_CLIENT, INGRESS, answer, configure, production_runtime, settle

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'odoo'
B, C, D, E, F = ids(5)
LABELS = {B: 'Beta Ops', C: 'Gamma Ops', D: 'Delta Ops', E: 'Epsilon Ops', F: 'Zeta Ops'}
VIEWER = 'golden-viewer'          # a signed-in HA user who is not an administrator
UNREVIEWED = 'golden-unreviewed'  # an administrator on an HA Core this release has not reviewed
CORE = '2099.1.0'
SECURITY = (('cache-control', 'no-store'), ('content-security-policy', gateway.ui.HEADERS['Content-Security-Policy']),
            ('referrer-policy', 'no-referrer'), ('x-content-type-options', 'nosniff'))


def fixed(status, body, content_type='application/json'):
    headers = [*SECURITY, ('content-length', str(len(body)))]
    if content_type is not None:
        headers.append(('content-type', content_type))
    return status, sorted(headers), body


DENIED = fixed(403, b'{"error":"request denied"}')
UNREVIEWED_DENIED = fixed(403, json.dumps({'error': 'request denied', 'detail': {
    'code': 'core_version_unreviewed', 'ha_version': CORE}}, separators=(',', ':')).encode())


def admin_module():
    import mcp_admin_core.profile_admin as module  # imported when a test runs (the red half of red-green)
    return module


async def verifier(user):
    if user == UNREVIEWED:
        return Unreviewed(CORE)
    return user == ADMIN['X-Remote-User-Id']


@pytest.fixture(autouse=True)
def no_test_bind(monkeypatch):
    monkeypatch.setattr(profiles, 'port_occupied', lambda port: None)  # tests/owned_network.py: 18000-18099
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: None)  # the test's memory, not the host's
    monkeypatch.setattr(profiles, 'available_memory_mib', lambda: 4096)


# ---- the route table ----

def literals(node):
    """The string values an expression of admin_action compares the operation name with."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return set().union(*(literals(item) for item in node.elts))
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'odoo_methods':
        return {getattr(gateway.odoo_methods, node.attr)}
    return set()


def action_operations():
    """Every operation name gateway.make_apps' admin_action compares its name with (an operation it answers)."""
    tree = ast.parse(Path(gateway.__file__).read_text())
    action = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.AsyncFunctionDef) and node.name == 'admin_action')
    names = set()
    for node in ast.walk(action):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == 'name':
            for comparator in node.comparators:
                names |= literals(comparator)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'startswith'
                and isinstance(node.func.value, ast.Name) and node.func.value.id == 'name'):
            names |= {value + '{id}' for value in literals(node.args[0])}
    return names - {'__ui__'}


def test_the_route_table_has_every_operation_a_profile_answers():
    """A new operation of admin_action must be added to gateway.PROFILE_OPERATIONS (and so to this matrix); every
    global route has a ProfileAdmin handler; the table's JSON operations are the ones whose body is read."""
    table = {name for name, _ in gateway.PROFILE_OPERATIONS}
    assert action_operations() == table
    assert len(set(gateway.PROFILE_OPERATIONS)) == len(gateway.PROFILE_OPERATIONS)
    assert gateway.JSON_OPERATIONS == {name for name, method in gateway.PROFILE_OPERATIONS if method == 'PUT'}
    for route in profile_router.GLOBAL_ROUTES:
        assert profile_router.is_global(route.template)
        for method, (handler, _) in route.methods.items():
            assert method in profile_router.ALL_METHODS and callable(getattr(admin_module().ProfileAdmin, handler))
    assert not {name for name in table if profile_router.is_global(name)}


def bodies():
    """A well-formed JSON body for each operation that takes one (what a caller sends to get past step 3)."""
    return {'backend': {'connection': {'url': 'https://matrix.invalid', 'database': 'DUMMY-db',
                                       'username': 'DUMMY-user', 'password': 'DUMMY-matrix-password'}},
            'backend/patch': {'changes': {'url': 'https://matrix.invalid'}},
            'policy': {'writes_enabled': False, 'disabled': []},
            'endpoint': {'endpoint': 'https://matrix.invalid/mcp'},
            'odoo/write-switches': {'odoo_write_switches': {'enable_writes': False, 'allow_direct_writes': False,
                                                            'allow_unknown_methods': False, 'chatter_direct': False}},
            'n8n/session': {'n8n_session': {'timeout_seconds': 600, 'max_sessions': 2}},
            gateway.odoo_methods.ROUTE: {'odoo_allowed_methods': []}}


def routes(profile=B, target=B, label='Beta Ops'):
    """Every route of the table as (name, method, path, JSON body or None, extra headers): profile is the
    X-MCP-Profile of a profile-scoped route (None: not sent), target the id in a global route's path, label the one a
    creation or a rename names."""
    found = []
    header = {} if profile is None else {'X-MCP-Profile': profile}
    for name, method in gateway.PROFILE_OPERATIONS:
        path = '/api/' + name.replace('{id}', f'{1_700_000_000_000}.{"a" * 22}')
        found.append((name, method, path, bodies().get(name) if method == 'PUT' else None, header))
    for route in profile_router.GLOBAL_ROUTES:
        for method, (_, takes_json) in route.methods.items():
            found.append((route.template, method, '/api/' + route.template.replace('{id}', target),
                          {'label': label} if takes_json else None, {}))
    found += [('page', 'GET', '/', None, {}), ('page', 'GET', '/overview', None, {})]
    return found


# ---- the matrix ----

class Caller:
    """One way to fail to be the administrator: the client address, the headers (the CSRF token computed as the
    add-on computes it, so a caller with a valid identity really reaches the role check)."""

    def __init__(self, name, *, client=INGRESS, users=(ADMIN['X-Remote-User-Id'],), csrf='own', extra=(),
                 writes_only=False, expected=DENIED):
        self.name, self.client, self.users, self.csrf, self.extra = name, client, users, csrf, extra
        self.writes_only, self.expected = writes_only, expected

    def headers(self, authority, method):
        values = [('X-Remote-User-Id', user) for user in self.users]
        if method not in ('GET', 'HEAD') and self.csrf is not None:
            user = self.users[0] if self.users else ''
            token = (hmac.new(authority.csrf_key, (user + '\0').encode(), hashlib.sha256).hexdigest()
                     if self.csrf == 'own' else self.csrf)
            values.append(('X-CSRF-Token', token))
        return [*values, *self.extra]


def callers(token):
    return [
        Caller('not the ingress proxy', client=('127.0.0.1', 1)),
        Caller('no X-Remote-User-Id', users=()),
        Caller('two X-Remote-User-Id', users=(ADMIN['X-Remote-User-Id'], ADMIN['X-Remote-User-Id'])),
        Caller('an MCP token instead', users=(), extra=(('Authorization', 'Bearer ' + token),)),
        Caller('no CSRF token', csrf=None, writes_only=True),
        Caller('a wrong CSRF token', csrf='0' * 64, writes_only=True),
        Caller('cross-site', extra=(('Sec-Fetch-Site', 'cross-site'),), writes_only=True),
        Caller('not an administrator', users=(VIEWER,)),
        Caller('HA Core not reviewed', users=(UNREVIEWED,), expected=UNREVIEWED_DENIED),
    ]


def snapshot(runtime):
    """What a refused request must not change: every entry under /data/mcp (type, mode, content), every profile's
    child (status, starts) and the manager's index view."""
    tree = {}
    for path in sorted(runtime.data.rglob('*')):
        info = path.lstat()
        tree[str(path.relative_to(runtime.data))] = (
            stat.S_IFMT(info.st_mode), stat.S_IMODE(info.st_mode),
            hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(info.st_mode) else None)
    children = {entry.profile_id: (entry.runtime.supervisor.status, entry.runtime.supervisor.starts)
                for entry in runtime.manager.profiles()}
    return tree, children, runtime.manager.index


async def send(runtime, caller, method, path, body, extra):
    async with GENUINE_CLIENT(transport=httpx.ASGITransport(app=runtime.admin_app, client=caller.client),
                              base_url='http://admin') as client:
        headers = httpx.Headers([*caller.headers(runtime.manager.shared.authority, method), *extra.items()])
        return await client.request(method, path, headers=headers,
                                    **({'json': body} if body is not None else {}))


def setup(tmp_path):
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    create_profile(data, PRODUCT, B, label=LABELS[B], port=18000)
    return data


def children_of(data):
    children = Children()
    children.profile_child(3000, 'default', PRODUCT, data)
    children.profile_child(18000, 'pbbbb', PRODUCT, profiles.Layout(data).profile(B))
    return children


async def test_every_route_refuses_every_caller_who_is_not_an_administrator(tmp_path, log_scan):
    """Every route x every refusal: 403 (core_version_unreviewed for an unreviewed Core), the same bytes for every route
    and every profile state, and nothing changed. The state is changed between two rounds (a label taken, the limit
    reached, more profiles); every round sends each route with X-MCP-Profile missing, malformed, unknown, the default
    profile's and B's, a global path's id known and unknown, a label taken and a new one."""
    data = setup(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data), verifier=verifier) as runtime:
        await settle(runtime, 'configured')
        for path in [data / 'state.json', *sorted((data / 'profiles').glob('*/state.json'))]:
            value = json.loads(path.read_text())
            log_scan.watch(value['token'], value['child_token'])
        log_scan.watch(*LABELS.values(), 'Fresh Desk', kind='name')
        token = runtime.token('default')
        rounds = []
        for _ in range(2):
            seen, before = [], snapshot(runtime)
            for caller in callers(token):
                for profile, target, label in ((None, 'f' * 24, 'Fresh Desk'), ('default', B, 'Beta Ops'),
                                               (B, B, 'Fresh Desk'), ('f' * 24, 'f' * 24, 'Beta Ops'),
                                               ('Not A Profile', 'default', 'Fresh Desk')):
                    for name, method, path, body, extra in routes(profile, target, label):
                        if caller.writes_only and method in ('GET', 'HEAD'):
                            continue
                        response = await send(runtime, caller, method, path, body, extra)
                        expected = caller.expected
                        if caller.name == 'HA Core not reviewed' and name == 'page':
                            assert response.status_code == 403 and b'<!doctype html>' in response.content
                            continue
                        assert answer(response) == expected, (caller.name, method, path, profile)
                        seen.append(answer(response))
            assert snapshot(runtime) == before
            rounds.append(seen)
            # The next round: the limit reached (Odoo: 5), labels taken, B's index entry renamed.
            async with runtime.admin() as admin:
                csrf = (await admin.get('/api/bootstrap', headers=ADMIN)).json()['csrf']
            async with GENUINE_CLIENT(transport=httpx.ASGITransport(app=runtime.admin_app, client=INGRESS),
                                      base_url='http://admin') as admin:
                for label in ('Fresh Desk', LABELS[C], LABELS[D], LABELS[E]):
                    listed = await admin.get('/api/profiles', headers=ADMIN)
                    if len(listed.json()['profiles']) > 5:
                        break
                    created = await admin.post('/api/profiles', json={'label': label}, headers={
                        **ADMIN, 'X-CSRF-Token': csrf, 'If-Match': listed.headers['etag'],
                        'Idempotency-Key': f'{int(time.time() * 1000)}.{secrets.token_urlsafe(16)}'})
                    assert created.status_code in (201, 409), created.content
            for path in sorted((data / 'profiles').glob('*/state.json')):
                value = json.loads(path.read_text())
                log_scan.watch(value['token'], value['child_token'])
        assert rounds[0] == rounds[1]


async def test_the_dispatcher_routes_every_route_of_its_table(tmp_path, log_scan):
    """For the administrator every route of the table reaches its handler (never the empty 404 of an unknown
    operation, never a 405); an unknown path under profiles/ is that 404 after the role check, as an unknown
    profile-scoped operation is; PATCH and DELETE anywhere but profiles/{id} are Starlette's 405 with the path's
    methods (after the identity check)."""
    data = setup(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data), verifier=verifier) as runtime:
        await settle(runtime, 'configured')
        log_scan.watch(runtime.token('default'), runtime.token(B))
        log_scan.watch(*LABELS.values(), 'Fresh Desk', kind='name')
        admin = Caller('administrator')
        for name, method, path, body, extra in routes('default', 'f' * 24, 'Fresh Desk'):
            response = await send(runtime, admin, method, path, body, extra)
            assert response.status_code != 405 and (response.status_code, response.content) != (404, b''), (
                name, method, response.status_code, response.content[:80])
        for path, extra in (('/api/profiles/a/b', {}), ('/api/profiles/', {}), ('/api/no-such-operation',
                                                                               {'X-MCP-Profile': 'default'})):
            response = await send(runtime, admin, 'GET', path, None, extra)
            assert answer(response) == fixed(404, b'', content_type=None), path
        for method, path, allow in (('PATCH', '/api/bootstrap', 'GET, HEAD, POST, PUT'),
                                    ('DELETE', '/api/token/revoke', 'GET, HEAD, POST, PUT'),
                                    ('DELETE', '/overview', 'GET, HEAD, POST, PUT'),
                                    ('PUT', '/api/profiles', 'GET, POST'), ('GET', '/api/profiles/index/quarantine',
                                                                            'POST'),
                                    ('POST', f'/api/profiles/{B}', 'PATCH, DELETE')):
            response = await send(runtime, admin, method, path, None, {'X-MCP-Profile': 'default'})
            status, headers, body = fixed(405, b'Method Not Allowed', content_type='text/plain; charset=utf-8')
            assert answer(response) == (status, sorted([*headers, ('allow', allow)]), body), (method, path)
        refused = await send(runtime, Caller('outside', client=('127.0.0.1', 1)), 'PATCH', '/api/bootstrap', None, {})
        assert answer(refused) == DENIED  # the identity check comes first now (switched off: Starlette's 405 first)


# ---- the fixed answers without a byte-for-byte case until HM-10, switched off and on ----

def raw_scope(method, path, headers, client=INGRESS):
    return {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': method, 'scheme': 'http',
            'path': path, 'raw_path': path.encode(), 'query_string': b'', 'root_path': '', 'client': client,
            'server': ('admin', 80), 'headers': [(b'host', b'admin'), *((k.lower().encode(), v.encode())
                                                                     for k, v in headers)]}


async def raw_call(app, method, path, headers, chunks, *, then=None):
    """One ASGI request: chunks is the body's parts (more_body until the last); then what receive gives after them:
    'disconnect' at once, 'wait' an event that never comes (the default), 'hold' as 'wait' but before any chunk.
    Returns (status, sorted headers, body)."""
    sent, queue = [], list(chunks)

    async def receive():
        if then == 'hold' or not queue:
            if then == 'disconnect' and not queue:
                return {'type': 'http.disconnect'}
            await asyncio.Event().wait()
        part = queue.pop(0)
        return {'type': 'http.request', 'body': part, 'more_body': bool(queue) or then == 'more'}

    async def emit(message):
        sent.append(message)
    await app(raw_scope(method, path, headers), receive, emit)
    start = next(message for message in sent if message['type'] == 'http.response.start')
    body = b''.join(message.get('body', b'') for message in sent if message['type'] == 'http.response.body')
    return start['status'], sorted((k.decode(), v.decode()) for k, v in start['headers']), body


class Recorded(ProfileRuntime):
    made = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        Recorded.made.append(self)


@pytest.mark.parametrize('mode', ['switched off', 'switched on'])
async def test_the_fixed_answers_of_the_pipeline_stay_byte_for_byte(tmp_path, log_scan, monkeypatch, mode):
    """HM-01's hand-off (its provenance note 4.1): 503 when the 16 management slots are taken, 503 when the profile's
    lock stays held for 2 s, 503 {"error":"state unavailable"} when the state cannot be read, 408 for a body not read
    within its time (here 0.2 s), 413 for a body over the limit (here 64 bytes), 403 for a client gone while its
    request waits: today's bytes, and the same through the switched-on dispatcher (the extracted pipeline)."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    Recorded.made = []
    monkeypatch.setattr(run_product, 'ProfileRuntime', Recorded)
    if mode == 'switched off':
        context = production_runtime(PRODUCT, data)
    else:
        context = multi_profile_runtime(PRODUCT, data)
    async with context as runtime:
        await settle(runtime, 'configured')
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        app = runtime.admin_app
        default = runtime.manager.get('default').runtime if mode == 'switched on' else Recorded.made[0]
        async with runtime.admin() as admin:
            csrf = (await admin.get('/api/bootstrap', headers=ADMIN)).json()['csrf']
        user = [('X-Remote-User-Id', ADMIN['X-Remote-User-Id'])] + (
            [('X-MCP-Profile', 'default')] if mode == 'switched on' else [])
        write = [*user, ('X-CSRF-Token', csrf), ('Content-Type', 'application/json')]
        denied_503 = fixed(503, b'{"error":"request denied"}')
        # The slots: 16 requests whose body never arrives hold them; the 17th is 503 at once.
        held = [asyncio.create_task(raw_call(app, 'GET', '/api/configuration', user, [b''], then='hold'))
                for _ in range(gateway.ADMIN_SLOTS)]
        await asyncio.sleep(.1)
        assert not any(task.done() for task in held)
        assert await raw_call(app, 'GET', '/api/configuration', user, [b'']) == denied_503
        for task in held:
            task.cancel()
        await asyncio.gather(*held, return_exceptions=True)
        # The profile's lock held: 503 after 2 s; a client gone meanwhile: 403 at once.
        await default.mutation_lock.acquire()
        try:
            assert await raw_call(app, 'PUT', '/api/policy', write, [b'{"writes_enabled":true,"disabled":[]}']) == (
                denied_503)
            gone = await raw_call(app, 'PUT', '/api/policy', write, [b'{"writes_enabled":true,"disabled":[]}'],
                                  then='disconnect')
            assert gone == DENIED
        finally:
            default.mutation_lock.release()
        # The state cannot be read.
        state = data / 'state.json'
        saved = state.read_bytes()
        state.write_bytes(b'{')
        try:
            assert await raw_call(app, 'GET', '/api/configuration', user, [b'']) == fixed(
                503, b'{"error":"state unavailable"}')
        finally:
            state.write_bytes(saved)
        # 408 and 413.
        monkeypatch.setattr(gateway, 'BODY_SECONDS', 0.2)
        assert await raw_call(app, 'PUT', '/api/policy', write, [b'{"writes_enabled":'], then='more') == fixed(
            408, b'{"error":"request denied"}')
        monkeypatch.setattr(gateway, 'MAX_REQUEST', 64)
        assert await raw_call(app, 'PUT', '/api/policy', write, [b'{"disabled":[],"writes_enabled":true,' + b' ' * 64
                                                                 + b'}']) == fixed(413, b'{"error":"request denied"}')
