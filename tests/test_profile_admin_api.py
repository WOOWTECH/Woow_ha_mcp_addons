"""HM-10: the profile management API on 8099 once a product is switched on (multi-profile plan 4.3, 4.4, 5.3; contract
1.2, 3.1-3.7, 4.1; DQ-02, DQ-12, DQ-13, DQ-14, DQ-15, DQ-16, DQ-17, DQ-28, DQ-40 (a) ①-④; UC-10; FM-01, 05, 06, 07,
08, 12, 18, 19, 21, 22, 23, 24, 25, 26, 33, 47, 53, 54, 93, 131, 139, 148; acceptance T-02, T-06, T-07, T-09).

8099 of a switched-on product is the management dispatcher (profile_router.AdminDispatcher): the shared management
pipeline for every path, then a global path (admin_module().ProfileAdmin: the profile list, creation, rename, deletion,
the index quarantine; X-MCP-Profile never read) or the one profile a profile-scoped path names (exactly one
X-MCP-Profile: missing 400 profile_id_required, two or malformed 400 profile_id_invalid, unknown 404
profile_not_found, never the default profile instead). Every answer of a profile's action carries its echo; the
bootstrap the whole echo and profiles_supported, the default profile's also the index's state. Every write of the
index needs the index ETag in If-Match; a creation, a deletion and the index quarantine an Idempotency-Key too, and no
answer of them (nor their replay) carries a token. A deletion revokes, wipes, stops, unindexes and removes, then lets
every blocked profile start again. Switched off, nothing of this exists: /api/profiles is an unknown operation (404)
and no request needs the header.

The refusal matrix (every route for every caller who is not an administrator) is tests/test_admin_pipeline_matrix.py.
Every case runs the production runtime (tests/multi_profile_runtime.py) under the HM-01 log scan (tokens, child tokens,
credentials and labels watched): in process, NoProcessSupervisor, the children behind one MockTransport.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import time

import httpx
import pytest

from admin_write_headers import reviewed_headers
from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import Children, create_profile, ids, multi_profile_runtime, stored
from mcp_admin_core import profiles
from mcp_admin_core.config import ConfigError
from mcp_admin_core.configuration import ConfigurationState
from mcp_admin_core.products import PROBES, ProductStore
from test_single_profile_golden import (ACCEPT, ADMIN, BEARER_REQUIRED, BOOTSTRAP_COMMON, BOOTSTRAP_EXTRA,
                                        GENUINE_CLIENT, INGRESS, NOT_FOUND, answer, configure, initialize_message,
                                        production_runtime, settle)

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'odoo'
B, C, D, E, F = ids(5)
LABELS = {B: 'Beta Ops', C: 'Gamma Ops', D: 'Delta Ops', E: 'Epsilon Ops', F: 'Zeta Ops'}
NEW_LABELS = ('Kappa Desk', 'Lambda Desk', 'Mu Desk', 'Nu Desk', 'Xi Desk', 'Omicron Desk')
SECOND_ADMIN = {'X-Remote-User-Id': 'golden-admin-two'}
ROW = ['id', 'label', 'port', 'is_default', 'disabled_reason', 'status', 'blocked_reason']
STATE_UNAVAILABLE = (503, b'{"error":"state unavailable"}')


def admin_module():
    import mcp_admin_core.profile_admin as module  # imported when a test runs (the red half of red-green)
    return module


async def administrators(user):
    """The HA administrator check of these tests: two administrators, nobody else."""
    return user in (ADMIN['X-Remote-User-Id'], SECOND_ADMIN['X-Remote-User-Id'])


@pytest.fixture(autouse=True)
def no_test_bind(monkeypatch):
    """tests/owned_network.py refuses every bind on 18000-18099 (a production child's range): a new profile's port is
    allocated without the spawn check's test bind here (HM-09's tests prove that bind). The memory readings are the
    test's, not the host's: no cgroup limit and 4 GiB available, unless a test says otherwise."""
    monkeypatch.setattr(profiles, 'port_occupied', lambda port: None)
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: None)
    monkeypatch.setattr(profiles, 'available_memory_mib', lambda: 4096)


def operation_key(offset_ms=0):
    return f'{int(time.time() * 1000) + offset_ms}.{secrets.token_urlsafe(16)}'


def setup(tmp_path, extras=(B,), configured=True, ports=None):
    """The default profile (configured as the golden one) and the additional profiles extras on ports 18000 and up."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    for number, profile_id in enumerate(extras):
        create_profile(data, PRODUCT, profile_id, label=LABELS[profile_id],
                       port=(ports or {}).get(profile_id, 18000 + number), configured=configured)
    return data


def children_of(data, extras=(B,), ports=None):
    children = Children()
    children.profile_child(3000, 'default', PRODUCT, data)
    for number, profile_id in enumerate(extras):
        port = (ports or {}).get(profile_id, 18000 + number)
        if port not in children.by_port:
            children.profile_child(port, 'p' + profile_id[:4], PRODUCT, profiles.Layout(data).profile(profile_id))
    return children


def watch(log_scan, data):
    """Every token, child token and credential stored under data, and every label (the log scan's needles)."""
    for path in [Path(data) / 'state.json', *sorted((Path(data) / 'profiles').glob('*/state.json'))]:
        try:
            value = json.loads(path.read_text())
        except (OSError, ValueError):
            continue  # missing, or made unreadable by the test
        log_scan.watch(*(v for v in (value['token'], value['child_token']) if v))
    log_scan.watch(*LABELS.values(), *NEW_LABELS, kind='name')


async def csrf_of(runtime):
    async with runtime.admin() as admin:
        return (await admin.get('/api/bootstrap', headers=ADMIN)).json()['csrf']


class Panel:
    """The panel's global management calls (the profile list, creation, rename, deletion, the index quarantine), with
    its CSRF token, the list's ETag and a new Idempotency-Key unless told otherwise."""

    def __init__(self, runtime, csrf, user=ADMIN):
        self.runtime, self.csrf, self.user = runtime, csrf, user

    def client(self, headers=None):
        return GENUINE_CLIENT(transport=httpx.ASGITransport(app=self.runtime.admin_app, client=INGRESS),
                              base_url='http://admin', headers=headers or {})

    def headers(self, etag=None, key=True, **extra):
        values = {**self.user, 'X-CSRF-Token': self.csrf, **extra}
        if etag is not None:
            values['If-Match'] = etag
        if key:
            values['Idempotency-Key'] = operation_key() if key is True else key
        return values

    async def list(self):
        async with self.client() as client:
            response = await client.get('/api/profiles', headers=self.user)
        assert response.status_code == 200, response.content
        return response.json(), response.headers['etag']

    async def etag(self):
        return (await self.list())[1]

    async def create(self, label, **headers):
        etag = headers.pop('etag', None) or await self.etag()
        async with self.client() as client:
            return await client.post('/api/profiles', json={'label': label}, headers=self.headers(etag, **headers))

    async def rename(self, profile_id, label, **headers):
        etag = headers.pop('etag', None) or await self.etag()
        async with self.client() as client:
            return await client.patch(f'/api/profiles/{profile_id}', json={'label': label},
                                      headers=self.headers(etag, key=False, **headers))

    async def delete(self, profile_id, **headers):
        etag = headers.pop('etag', None) or await self.etag()
        async with self.client() as client:
            return await client.delete(f'/api/profiles/{profile_id}', headers=self.headers(etag, **headers))

    async def quarantine(self, etag, **headers):
        async with self.client() as client:
            return await client.post('/api/profiles/index/quarantine', headers=self.headers(etag, **headers))


def code_of(response):
    return response.json()['detail']['code']


def tree_of(data):
    """Every entry under data with its type, mode and (files) content digest: what a refused request must not change
    (the default state's ctime aside: its store chmods it at every read)."""
    found = {}
    for path in sorted(Path(data).rglob('*')):
        info = path.lstat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(info.st_mode) else None
        found[str(path.relative_to(data))] = (stat.S_IFMT(info.st_mode), stat.S_IMODE(info.st_mode), digest)
    return found


def index_bytes(data):
    path = profiles.Layout(Path(data)).index
    return path.read_bytes() if path.exists() else None


def monitor_of(manager, profile_id):
    """The task of an additional profile's health monitor (HM-09's ProfileManager keeps one per profile; HM-09's review
    fixes may move it: change it here only)."""
    return manager._monitors.get(profile_id)


# ---- switched off: nothing of this exists (contract 1.2) ----

async def test_switched_off_the_profile_paths_are_unknown_and_no_header_is_needed(tmp_path, log_scan):
    """A product not switched on keeps today's management API: /api/profiles is an unknown operation (404 with an
    empty body after the role check), PATCH and DELETE are Starlette's 405 before anything else, a profile-scoped
    request needs no X-MCP-Profile and one it carries changes nothing (its bytes are the same), the bootstrap has no
    echo, and nothing is written under /data/mcp."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    async with production_runtime(PRODUCT, data) as runtime:
        await settle(runtime, 'configured')
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        before = tree_of(data)
        async with runtime.admin() as admin:
            boot = await admin.get('/api/bootstrap', headers=ADMIN)
            assert set(boot.json()) == BOOTSTRAP_COMMON | BOOTSTRAP_EXTRA[PRODUCT]
            headers = {**ADMIN, 'X-CSRF-Token': boot.json()['csrf']}
            for method, path, kwargs in (('GET', '/api/profiles', {}), ('POST', '/api/profiles', {}),
                                         ('POST', '/api/profiles/index/quarantine', {})):
                response = await admin.request(method, path, headers=headers, **kwargs)
                assert (response.status_code, response.content) == (404, b''), path
            for method in ('PATCH', 'DELETE'):
                response = await admin.request(method, f'/api/profiles/{B}', headers=headers)
                assert (response.status_code, response.content) == (405, b'Method Not Allowed')
            for value in ('default', B, 'not a profile'):
                with_header = await admin.get('/api/configuration', headers={**ADMIN, 'X-MCP-Profile': value})
                without = await admin.get('/api/configuration', headers=ADMIN)
                assert with_header.status_code == 200 and answer(with_header) == answer(without)
                assert 'profile' not in with_header.json()
        after = tree_of(data)
    assert {name: facts for name, facts in after.items() if name != 'state.json'} == {
        name: facts for name, facts in before.items() if name != 'state.json'}
    assert not profiles.has_profile_data(data)


# ---- the list (contract 3.1, 3.6; FM-18, FM-26, FM-139) ----

async def test_the_list_names_every_profile_with_its_state_and_no_secret(tmp_path, log_scan):
    """GET /api/profiles: the default profile first (id default, label Default, its child port, is_default), then the
    index's order; every row's disabled_reason (PaaS order; profile_unavailable for one the add-on could not open),
    status (unconfigured, running, blocked with blocked_reason) and nothing secret; the orphans (directories the index
    does not list) for deletion; the index ETag; X-MCP-Profile is never read here."""
    data = setup(tmp_path, extras=(B, C, D), ports={B: 18000, C: 18001, D: 18001})
    create_profile(data, PRODUCT, E, label=LABELS[E], port=18003, configured=False)
    create_profile(data, PRODUCT, F, label=LABELS[F], port=18004, indexed=False)  # an orphan
    layout = profiles.Layout(data)
    gone = layout.profile(E)
    shutil.rmtree(gone)  # E: indexed, its directory gone (profile_unavailable)
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C, D),
                                                                       {B: 18000, C: 18001, D: 18001}),
                                     verifier=administrators) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        panel = Panel(runtime, await csrf_of(runtime))
        async with panel.client() as client:
            response = await client.get('/api/profiles', headers={**ADMIN, 'X-MCP-Profile': 'not a profile'})
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store' and admin_module().ETAG.fullmatch(
            response.headers['etag'])
        body = response.json()
        assert list(body) == ['profiles', 'orphans'] and body['orphans'] == [{'id': F}]
        rows = body['profiles']
        assert [list(row) for row in rows] == [ROW] * 5
        assert rows[0] == {'id': 'default', 'label': 'Default', 'port': 3000, 'is_default': True,
                           'disabled_reason': None, 'status': 'running', 'blocked_reason': None}
        assert rows[1] == {'id': B, 'label': LABELS[B], 'port': 18000, 'is_default': False, 'disabled_reason': None,
                           'status': 'running', 'blocked_reason': None}
        for row, profile_id in ((rows[2], C), (rows[3], D)):  # one port twice: both stopped (PaaS _port_collisions)
            assert row == {'id': profile_id, 'label': LABELS[profile_id], 'port': 18001, 'is_default': False,
                           'disabled_reason': 'port_conflict', 'status': 'blocked',
                           'blocked_reason': 'child_port_conflict'}
        assert rows[4] == {'id': E, 'label': LABELS[E], 'port': 18003, 'is_default': False,
                           'disabled_reason': 'profile_unavailable', 'status': 'failed', 'blocked_reason': None}
        for profile_id in ('default', B, C, D, F):
            directory = data if profile_id == 'default' else layout.profile(profile_id)
            value = stored(directory)
            assert value['token'] not in response.text and value['child_token'] not in response.text
        # The same list twice: the same ETag; another administrator gets the same bytes.
        again = await Panel(runtime, await csrf_for(runtime, SECOND_ADMIN), SECOND_ADMIN).list()
        assert again == (body, response.headers['etag'])


async def test_a_profile_over_the_memory_limit_is_listed_with_what_it_needs(tmp_path, log_scan, monkeypatch):
    """PaaS test_memory_disabled_profile_is_listed_with_its_reason_and_logged_when_not_started: with a cgroup memory
    limit of 512 MiB, Odoo runs one additional profile (PaaS formula); the second is disabled memory_capacity with
    required_memory_mib (256 + 3 x 100), blocked with blocked_reason memory_capacity."""
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: 512)
    data = setup(tmp_path, extras=(B, C))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        rows = (await Panel(runtime, await csrf_of(runtime)).list())[0]['profiles']
    assert rows[1]['disabled_reason'] is None and rows[1]['status'] == 'running'
    assert rows[2] == {'id': C, 'label': LABELS[C], 'port': 18001, 'is_default': False,
                       'disabled_reason': 'memory_capacity', 'required_memory_mib': 556, 'status': 'blocked',
                       'blocked_reason': 'memory_capacity'}


# ---- the echo and the global settings (contract 3.1, 3.4; DQ-13; FM-08, FM-12) ----

async def test_every_answer_of_a_profile_names_it(tmp_path, log_scan):
    """The bootstrap carries the whole echo (id, label, is_default) and profiles_supported, the default profile's also
    profile_index_state; every other JSON answer of the profile's action carries profile {id}; a refusal (an
    exception) and a page carry none. A rename shows in the echo at once."""
    data = setup(tmp_path, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data)) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        async with runtime.admin() as admin:
            default = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
        assert set(default) == BOOTSTRAP_COMMON | BOOTSTRAP_EXTRA[PRODUCT] | {
            'profile', 'profiles_supported', 'profile_index_state'}
        assert (default['profile'], default['profiles_supported'], default['profile_index_state']) == (
            {'id': 'default', 'label': 'Default', 'is_default': True}, True, 'ok')
        async with runtime.admin(B) as admin:
            boot = await admin.get('/api/bootstrap', headers=ADMIN)
            body = boot.json()
            assert set(body) == BOOTSTRAP_COMMON | BOOTSTRAP_EXTRA[PRODUCT] | {'profile', 'profiles_supported'}
            assert body['profile'] == {'id': B, 'label': LABELS[B], 'is_default': False}
            assert body['profiles_supported'] is True and body['csrf'] == default['csrf']
            assert body['token_masked'] == runtime.token(B)[:4] + '*' * 20 + runtime.token(B)[-4:]
            configuration = await admin.get('/api/configuration', headers=ADMIN)
            assert configuration.json() == {'configuration': body['configuration'], 'profile': {'id': B}}
            revealed = await admin.post('/api/token/reveal', headers={**ADMIN, 'X-CSRF-Token': body['csrf']})
            assert revealed.json() == {'token': runtime.token(B), 'profile': {'id': B}}
            refused = await admin.put('/api/policy', json={'writes_enabled': False, 'disabled': []},
                                      headers={**ADMIN, 'X-CSRF-Token': body['csrf']})
            assert (refused.status_code, refused.json()) == (
                428, {'error': 'request denied', 'detail': {'code': 'config_revision_required'}})
            stale = await admin.put('/api/policy', json={'writes_enabled': False, 'disabled': []},
                                    headers={**ADMIN, 'X-CSRF-Token': body['csrf'],
                                             'If-Match': '"c1-' + '0' * 64 + '"'})
            assert stale.json() == {'detail': {'code': 'config_conflict'}, 'profile': {'id': B}}
            page = await admin.get('/', headers=ADMIN)
            assert page.status_code == 200 and B.encode() not in page.content
        panel = Panel(runtime, default['csrf'])
        assert (await panel.rename(B, 'Beta Renamed')).status_code == 200
        log_scan.watch('Beta Renamed', kind='name')
        async with runtime.admin(B) as admin:
            assert (await admin.get('/api/bootstrap', headers=ADMIN)).json()['profile']['label'] == 'Beta Renamed'


async def test_the_endpoint_and_the_owner_defaults_notice_are_the_default_profiles(tmp_path, log_scan):
    """DQ-13: the add-on has one endpoint, stored in the default profile's state; an additional profile's bootstrap
    shows it, its PUT endpoint is 409 endpoint_global and changes nothing. FM-08: an additional profile has no
    owner-defaults notice; its restore and dismiss are 409 owner_defaults_unavailable (shape C)."""
    data = setup(tmp_path, extras=(B,))
    endpoint = 'https://ha.invalid/mcp'
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data)) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        async with runtime.admin() as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            saved = await admin.put('/api/endpoint', json={'endpoint': endpoint}, headers=reviewed_headers(boot, ADMIN))
            assert saved.status_code == 200 and saved.json()['profile'] == {'id': 'default'}
        assert stored(data)['endpoint'] == endpoint
        directory = profiles.Layout(data).profile(B)
        before = (directory / 'state.json').read_bytes()
        async with runtime.admin(B) as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            assert boot['endpoint'] == endpoint and 'owner_defaults' not in boot
            refused = await admin.put('/api/endpoint', json={'endpoint': 'https://other.invalid/mcp'},
                                      headers=reviewed_headers(boot, ADMIN))
            assert (refused.status_code, refused.json()) == (
                409, {'error': 'request denied', 'detail': {'code': 'endpoint_global'}})
            for action in ('restore', 'dismiss'):
                answered = await admin.post('/api/owner-defaults/' + action, headers=reviewed_headers(boot, ADMIN))
                assert answered.status_code == 409 and answered.json() == {
                    'error': 'owner_defaults_unavailable', 'detail': {'code': 'owner_defaults_unavailable'},
                    'profile': {'id': B}}
        assert (directory / 'state.json').read_bytes() == before


# ---- X-MCP-Profile (contract 3.3; DQ-17; §8.8 #31, #32, #83; I12) ----

async def test_a_profile_scoped_request_names_exactly_one_known_profile(tmp_path, log_scan):
    """Switched on, every profile-scoped request names its profile: none is 400 profile_id_required, two or one that is
    neither default nor 24 lowercase hex 400 profile_id_invalid, one the index does not list (an orphan, a deleted one,
    any other) 404 profile_not_found, an indexed one the add-on could not open 503 state unavailable; never the default
    profile instead (no token revealed). Global paths and pages never read it. No path fallback (UC-10)."""
    data = setup(tmp_path, extras=(B, C))
    create_profile(data, PRODUCT, D, label=LABELS[D], port=18002, indexed=False)  # an orphan
    shutil.rmtree(profiles.Layout(data).profile(C))  # C: indexed, its directory gone
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B,))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        csrf = await csrf_of(runtime)
        panel = Panel(runtime, csrf)
        write = {**ADMIN, 'X-CSRF-Token': csrf}
        async with panel.client() as client:
            for headers, expected in (
                    ([], (400, 'profile_id_required')),
                    ([('X-MCP-Profile', 'default'), ('X-MCP-Profile', 'default')], (400, 'profile_id_invalid')),
                    ([('X-MCP-Profile', 'default'), ('X-MCP-Profile', B)], (400, 'profile_id_invalid')),
                    ([('X-MCP-Profile', 'Default')], (400, 'profile_id_invalid')),
                    ([('X-MCP-Profile', 'DEFAULT')], (400, 'profile_id_invalid')),
                    ([('X-MCP-Profile', B.upper())], (400, 'profile_id_invalid')),
                    ([('X-MCP-Profile', B[:-1])], (400, 'profile_id_invalid')),
                    ([('X-MCP-Profile', B + 'a')], (400, 'profile_id_invalid')),
                    ([('X-MCP-Profile', 'default, ' + B)], (400, 'profile_id_invalid')),
                    ([('X-MCP-Profile', '.quarantine-' + B + '-20261115T000000Z')], (400, 'profile_id_invalid')),
                    ([('X-MCP-Profile', D)], (404, 'profile_not_found')),
                    ([('X-MCP-Profile', 'f' * 24)], (404, 'profile_not_found'))):
                for method, path in (('POST', '/api/token/reveal'), ('GET', '/api/bootstrap'),
                                     ('POST', '/api/token/rotate')):
                    response = await client.request(method, path, headers=httpx.Headers([*write.items(), *headers]))
                    assert (response.status_code, code_of(response)) == expected, (path, headers)
                    assert response.json() == {'error': 'request denied', 'detail': {'code': expected[1]}}
            unavailable = await client.get('/api/bootstrap', headers={**ADMIN, 'X-MCP-Profile': C})
            assert (unavailable.status_code, unavailable.content) == STATE_UNAVAILABLE
            # Global paths and pages never read it; there is no {base}/api/p/<id>/... fallback (UC-10).
            assert (await client.get('/api/profiles', headers=ADMIN)).status_code == 200
            assert (await client.get('/', headers={**ADMIN, 'X-MCP-Profile': 'bogus'})).status_code == 200
            fallback = await client.get(f'/api/p/{B}/bootstrap', headers={**ADMIN, 'X-MCP-Profile': 'default'})
            assert (fallback.status_code, fallback.content) == (404, b'')
        assert stored(data)['token'] is not None and stored(profiles.Layout(data).profile(B))['token'] is not None


# ---- creation (contract 3.1, 3.5, 3.6, 4.1; plan 4.3; DQ-02, DQ-16, DQ-28; FM-19, 20, 21, 25) ----

async def test_a_new_profile_is_born_complete_starts_and_its_answers_carry_no_token(tmp_path, log_scan, monkeypatch):
    """POST /api/profiles {label}: 201 with its row and the receipt, never a token (and no token in the replay of the
    same Idempotency-Key, 200 with the same row); the directory is born once with its final state (new tokens, no
    connection or endpoint, the default profile's policy now, no history, no n8n session; DQ-02), the index lists it
    last, its receipt is beside the index, the default profile's state is untouched (I6); it is served at once: its
    child is started once, under the profile's own lock as a save starts it (HM-09 review S-12), its token routes to
    it (an unconfigured child: the gateway answers initialize itself), token/reveal with its id gives it, its status
    is unconfigured."""
    data = setup(tmp_path, extras=(B,))
    default_state = data / 'state.json'
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data)) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        async with runtime.admin() as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            saved = await admin.put('/api/policy', json={'writes_enabled': False, 'disabled': ['read_record']},
                                    headers=reviewed_headers(boot, ADMIN))
            assert saved.status_code == 200
        before = os.stat(default_state)
        signature = (hashlib.sha256(default_state.read_bytes()).hexdigest(), before.st_ino, before.st_mtime_ns)
        locked = []
        starting = runtime.manager.start_profile

        async def start_profile(profile_id):
            locked.append(runtime.manager.get(profile_id).runtime.mutation_lock.locked())
            await starting(profile_id)
        monkeypatch.setattr(runtime.manager, 'start_profile', start_profile)
        panel = Panel(runtime, boot['csrf'])
        listed, etag = await panel.list()
        key = operation_key()
        created = await panel.create(NEW_LABELS[0], etag=etag, key=key)
        assert created.status_code == 201, created.content
        assert locked == [True]  # started once, under its own lock
        body = created.json()
        new = body['id']
        assert profiles.is_profile_id(new) and new not in (B,)
        assert list(body) == [*ROW, 'operation']
        assert {name: body[name] for name in ROW} == {
            'id': new, 'label': NEW_LABELS[0], 'port': 18001, 'is_default': False, 'disabled_reason': None,
            'status': 'unconfigured', 'blocked_reason': None}
        assert body['operation'] == {'id': key, 'kind': 'profile.create', 'state': 'completed', 'replayed': False}
        assert created.headers['etag'] != etag and created.headers['etag'] == await panel.etag()
        directory = profiles.Layout(data).profile(new)
        state = stored(directory)
        log_scan.watch(state['token'], state['child_token'])
        assert state['token'] not in created.text and state['child_token'] not in created.text
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert stat.S_IMODE((directory / 'state.json').stat().st_mode) == 0o600
        default = stored(data)
        assert state['token'] not in (default['token'], default['child_token'], runtime.token(B))
        assert len({state['token'], state['child_token'], default['token'], default['child_token']}) == 4
        assert (state['connection'], state['endpoint'], state['writes_enabled'], state['disabled']) == (
            None, None, False, ['read_record'])
        assert state['enabled_write_tools'] == default['enabled_write_tools']
        assert 'token_history' not in state and 'n8n_session' not in state and 'owner_defaults_20261025' not in state
        assert [item.id for item in profiles.read_index(profiles.Layout(data).index).entries] == [B, new]
        journal = data / '.profiles.json.operations.json'
        assert journal.is_file() and stat.S_IMODE(journal.stat().st_mode) == 0o600
        assert not (data / '.state.json.operations.json').exists()
        assert (hashlib.sha256(default_state.read_bytes()).hexdigest(), os.stat(default_state).st_ino,
                os.stat(default_state).st_mtime_ns) == signature
        # The same key again: the same row, no token, nothing created.
        replayed = await panel.create(NEW_LABELS[0], etag=etag, key=key)
        assert replayed.status_code == 200
        assert replayed.json() == {**{name: body[name] for name in ROW},
                                   'operation': {**body['operation'], 'replayed': True}}
        assert len(profiles.read_index(profiles.Layout(data).index).entries) == 2
        # Served at once: token/reveal with its id, its token on both MCP paths.
        async with runtime.admin(new) as admin:
            revealed = await admin.post('/api/token/reveal', headers={**ADMIN, 'X-CSRF-Token': boot['csrf']})
            assert revealed.json() == {'token': state['token'], 'profile': {'id': new}}
        async with runtime.mcp() as client:
            for path, headers in (('/mcp', {**ACCEPT, 'Authorization': 'Bearer ' + state['token']}),
                                  (f"/private_{state['token']}/mcp", ACCEPT)):
                response = await client.post(path, headers=headers, json=initialize_message())
                assert response.status_code == 200 and response.headers['mcp-session-id'].startswith('woow-local-')
        assert runtime.manager.get(new).runtime.supervisor.status == 'unconfigured'


async def test_a_creation_is_refused_for_its_label_its_capacity_and_its_port(tmp_path, log_scan, monkeypatch):
    """422 profile_label_invalid (DQ-16: outer whitespace stripped, 1-80 code points, no control, format, separator,
    surrogate, private-use or unassigned character); 409 profile_label_conflict (NFKC + casefold, default and
    預設帳號 reserved); 409 profile_limit_reached with limit (Odoo: 5); 409 profile_memory_insufficient with limit,
    required_memory_mib and available_memory_mib (and memory_limit_mib under a cgroup limit: the PaaS formula);
    409 profile_port_unavailable. A refusal changes nothing; MemAvailable unreadable creates the profile."""
    data = setup(tmp_path, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data)) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        panel = Panel(runtime, await csrf_of(runtime))
        before = tree_of(data)
        for label in ('', '   ', 'a' * 81, 'zero\u200bwidth', 'bidi\u202eOps', 'bell\x07', 'line\u2028sep',
                      '\ue000private', 'unassigned\u0378'):
            response = await panel.create(label)
            assert (response.status_code, code_of(response)) == (422, 'profile_label_invalid'), repr(label)
        for label in ('BETA OPS', ' beta ops ', '\uff22\uff45\uff54\uff41 Ops', 'default', 'DEFAULT',
                      '\u9810\u8a2d\u5e33\u865f'):
            response = await panel.create(label)
            assert (response.status_code, code_of(response)) == (409, 'profile_label_conflict'), label
        monkeypatch.setattr(profiles, 'available_memory_mib', lambda: 355)  # Odoo needs 100 + 256
        response = await panel.create(NEW_LABELS[0])
        assert (response.status_code, response.json()['detail']) == (409, {
            'code': 'profile_memory_insufficient', 'limit': 1, 'required_memory_mib': 356,
            'available_memory_mib': 355})
        monkeypatch.setattr(profiles, 'available_memory_mib', lambda: 356)
        monkeypatch.setattr(runtime.manager, 'free_port', lambda: None)
        response = await panel.create(NEW_LABELS[0])
        assert (response.status_code, code_of(response)) == (409, 'profile_port_unavailable')
        assert tree_of(data) == {name: facts for name, facts in before.items()}
        monkeypatch.undo()
        monkeypatch.setattr(profiles, 'port_occupied', lambda port: None)
        monkeypatch.setattr(profiles, 'available_memory_mib', lambda: None)  # unreadable: never assumed, created
        for label in NEW_LABELS[:4]:
            assert (await panel.create(label)).status_code == 201
        assert any('MemAvailable cannot be read; the profile is created without the memory check' in record.getMessage()
                   for record in log_scan.records)
        response = await panel.create(NEW_LABELS[4])
        assert (response.status_code, response.json()['detail']) == (409, {'code': 'profile_limit_reached', 'limit': 5})
        # A cgroup memory limit (the PaaS formula): 512 MiB runs one additional Odoo profile.
        monkeypatch.setattr(runtime.manager, 'capacity', profiles.capacity(PRODUCT, 512))
        monkeypatch.setattr(profiles, 'available_memory_mib', lambda: 900)
        before = tree_of(data)
        response = await panel.create(NEW_LABELS[4])
        assert (response.status_code, response.json()['detail']) == (409, {
            'code': 'profile_limit_reached', 'limit': 5})
        listed = (await panel.list())[0]['profiles']
        await panel.delete(listed[-1]['id'])
        await panel.delete(listed[-2]['id'])
        await panel.delete(listed[-3]['id'])
        response = await panel.create(NEW_LABELS[4])
        assert (response.status_code, response.json()['detail']) == (409, {
            'code': 'profile_memory_insufficient', 'limit': 1, 'required_memory_mib': 256 + 4 * 100,
            'memory_limit_mib': 512, 'available_memory_mib': 900})


async def test_a_product_without_profiles_refuses_to_create_one(tmp_path, log_scan):
    """DQ-28: OpenDesign never has additional profiles (it is never switched on; were it, creation would be 409
    profile_product_unsupported and the bootstrap's profiles_supported false, so the panel shows no add button)."""
    data = tmp_path / 'data'
    configure(data, 'opendesign')
    async with multi_profile_runtime('opendesign', data) as runtime:
        await settle(runtime, 'configured')
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        async with runtime.admin() as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
        assert boot['profiles_supported'] is False
        response = await Panel(runtime, boot['csrf']).create(NEW_LABELS[0])
        assert (response.status_code, code_of(response)) == (409, 'profile_product_unsupported')
    assert not profiles.has_profile_data(data)


async def test_no_profile_is_created_while_only_the_default_profile_is_served(tmp_path, log_scan):
    """HM-08's file budget: when the open file limit cannot be raised to what additional profiles need, the add-on
    serves the default profile only (B is listed as profile_unavailable). A creation then is 409 profile_limit_reached
    with limit 0 and writes nothing: no directory, no index entry, no receipt; the new profile would not be served
    after a restart either."""
    from test_router_passthrough import FakeResource
    from mcp_admin_core import profile_runtime
    data = setup(tmp_path, extras=(B,))
    needed, _ = profile_runtime.open_file_budget(PRODUCT)
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data),
                                     resources=FakeResource(256, needed - 1)) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        assert runtime.manager.get(B) is None
        panel = Panel(runtime, await csrf_of(runtime))
        listed = (await panel.list())[0]['profiles']
        assert [(row['id'], row['disabled_reason'], row['status']) for row in listed] == [
            ('default', None, 'running'), (B, 'profile_unavailable', 'failed')]
        before = tree_of(data)
        response = await panel.create(NEW_LABELS[0])
        assert (response.status_code, response.json()['detail']) == (409, {'code': 'profile_limit_reached', 'limit': 0})
        assert tree_of(data) == before and not (data / '.profiles.json.operations.json').exists()


# ---- write protection (contract 3.5; DQ-15; §8.8 #34; FM-06, FM-07, FM-24) ----

async def test_every_profile_write_needs_the_index_etag_and_its_operation_id(tmp_path, log_scan):
    """If-Match (the index ETag): none 428 config_revision_required; malformed, repeated or stale 409 config_conflict
    (shape B, the current ETag in ETag). Idempotency-Key (creation, deletion, quarantine): none 428
    operation_id_required; two 400 operation_id_invalid; reused for another request 409 operation_id_conflict;
    another administrator's 404 operation_not_found; older than 24 h 410 operation_id_expired; from the future 400
    operation_id_invalid. A rename takes none. Nothing changes for any refusal."""
    data = setup(tmp_path, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data), verifier=administrators) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        panel = Panel(runtime, await csrf_of(runtime))
        etag = await panel.etag()
        before = tree_of(data)
        async with panel.client() as client:
            missing = await client.post('/api/profiles', json={'label': NEW_LABELS[0]}, headers=panel.headers())
            assert (missing.status_code, code_of(missing)) == (428, 'config_revision_required')
            for values in (['"bogus"'], [etag, etag], ['"p1-' + '0' * 64 + '"'], ['"c1-' + '0' * 64 + '"']):
                headers = httpx.Headers([*panel.headers().items(), *(('If-Match', value) for value in values)])
                for method, path, kwargs in (('POST', '/api/profiles', {'json': {'label': NEW_LABELS[0]}}),
                                             ('PATCH', f'/api/profiles/{B}', {'json': {'label': NEW_LABELS[0]}}),
                                             ('DELETE', f'/api/profiles/{B}', {})):
                    response = await client.request(method, path, headers=headers, **kwargs)
                    assert (response.status_code, response.content, response.headers['etag']) == (
                        409, b'{"detail":{"code":"config_conflict"}}', etag), (values, method)
            for method, path, kwargs in (('POST', '/api/profiles', {'json': {'label': NEW_LABELS[0]}}),
                                         ('DELETE', f'/api/profiles/{B}', {})):
                response = await client.request(method, path, headers=panel.headers(etag, key=False), **kwargs)
                assert (response.status_code, code_of(response)) == (428, 'operation_id_required')
                twice = httpx.Headers([*panel.headers(etag, key=False).items(), ('Idempotency-Key', operation_key()),
                                       ('Idempotency-Key', operation_key())])
                response = await client.request(method, path, headers=twice, **kwargs)
                assert (response.status_code, code_of(response)) == (400, 'operation_id_invalid')
                for key, expected in ((operation_key(-25 * 3600 * 1000), (410, 'operation_id_expired')),
                                      (operation_key(3600 * 1000), (400, 'operation_id_invalid')),
                                      ('not-an-operation-id', (400, 'operation_id_invalid'))):
                    response = await client.request(method, path, headers=panel.headers(etag, key=key), **kwargs)
                    assert (response.status_code, code_of(response)) == expected, key
        assert tree_of(data) == before
        key = operation_key()
        assert (await panel.create(NEW_LABELS[0], key=key)).status_code == 201
        conflict = await panel.create(NEW_LABELS[1], key=key)
        assert (conflict.status_code, code_of(conflict)) == (409, 'operation_id_conflict')
        other = await Panel(runtime, await csrf_for(runtime, SECOND_ADMIN), SECOND_ADMIN).create(NEW_LABELS[0], key=key)
        assert (other.status_code, code_of(other)) == (404, 'operation_not_found')
        renamed = await panel.rename(B, NEW_LABELS[2])
        assert renamed.status_code == 200 and 'operation' not in renamed.json()
        stale = await panel.rename(B, NEW_LABELS[3], etag=etag)
        assert (stale.status_code, stale.content) == (409, b'{"detail":{"code":"config_conflict"}}')


async def csrf_for(runtime, user):
    async with runtime.admin() as admin:
        return (await admin.get('/api/bootstrap', headers=user)).json()['csrf']


async def test_an_operation_whose_outcome_is_unknown_is_never_repeated(tmp_path, log_scan, monkeypatch):
    """A creation whose receipt cannot be completed after its commit answers 409 operation_outcome_unknown; the same
    key again is 409 operation_outcome_unknown with the receipt (never a second profile); a new key works."""
    data = setup(tmp_path, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data)) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        panel = Panel(runtime, await csrf_of(runtime))
        journal = runtime.manager.admin.journal
        original = journal.complete

        def failing(*args, **kwargs):
            raise OSError('HM-10: the receipt cannot be completed')
        monkeypatch.setattr(journal, 'complete', failing)
        key = operation_key()
        first = await panel.create(NEW_LABELS[0], key=key)
        assert (first.status_code, code_of(first)) == (409, 'operation_outcome_unknown')
        monkeypatch.setattr(journal, 'complete', original)
        again = await panel.create(NEW_LABELS[0], key=key)
        assert (again.status_code, again.json()['detail']) == (409, {
            'code': 'operation_outcome_unknown',
            'operation': {'id': key, 'kind': 'profile.create', 'state': 'unknown', 'replayed': True}})
        assert len(profiles.read_index(profiles.Layout(data).index).entries) == 2  # B and the one first created
        assert (await panel.create(NEW_LABELS[1])).status_code == 201


async def test_another_profiles_etag_is_a_conflict_even_for_the_same_state(tmp_path, log_scan, monkeypatch):
    """DQ-15 (HM-05 review S-3): a profile's ETag is bound to its id. Two profiles whose state.json are byte for byte
    the same, and whose configuration revisions share one key (here forced), still have different ETags: a write to C
    with B's ETag is 409 config_conflict and changes nothing. The control: without a profile id, one key and one state
    give one ETag (so the test can tell)."""
    data = setup(tmp_path, extras=(B, C))
    layout = profiles.Layout(data)
    shutil.copyfile(layout.profile(B) / 'state.json', layout.profile(C) / 'state.json')
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        key = runtime.manager.get(B).runtime.configuration._key
        runtime.manager.get(C).runtime.configuration._key = key  # one key for both: only the id tells them apart
        async with runtime.admin(B) as admin:
            b_boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
        async with runtime.admin(C) as admin:
            c_boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            assert b_boot['configuration']['revision'] != c_boot['configuration']['revision']
            before = (layout.profile(C) / 'state.json').read_bytes()
            conflict = await admin.put('/api/policy', json={'writes_enabled': False, 'disabled': []},
                                       headers=reviewed_headers(b_boot, ADMIN))
            assert (conflict.status_code, conflict.json()) == (
                409, {'detail': {'code': 'config_conflict'}, 'profile': {'id': C}})
            assert (layout.profile(C) / 'state.json').read_bytes() == before
            saved = await admin.put('/api/policy', json={'writes_enabled': False, 'disabled': []},
                                    headers=reviewed_headers(c_boot, ADMIN))
            assert saved.status_code == 200
    store = ProductStore(layout.profile(B), PRODUCT, existing_only=True)
    try:
        state = store.load()
        one, two = ConfigurationState(store), ConfigurationState(store)
        two._key = one._key
        assert one.etag(state) == two.etag(state)  # the control: without the id one key gives one ETag
        one, two = ConfigurationState(store, profile_id=B), ConfigurationState(store, profile_id=C)
        two._key = one._key
        assert one.etag(state) != two.etag(state)
        with pytest.raises(ValueError, match='invalid profile id'):
            ConfigurationState(store, profile_id='Default')
    finally:
        store.close()


# ---- rename (contract 3.1; FM-22) ----

async def test_a_rename_changes_only_the_label(tmp_path, log_scan):
    """PATCH /api/profiles/<id> {label}: 200 with the row; the token, the port and the directory stay. The default
    profile 422 profile_default_immutable; an id the index does not list 404 profile_not_found; a label another
    profile has 409 profile_label_conflict; its own label again 200. A malformed id or body is a fixed 400 (step 5);
    GET on the path is 405."""
    data = setup(tmp_path, extras=(B, C))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        panel = Panel(runtime, await csrf_of(runtime))
        token, before = runtime.token(B), (profiles.Layout(data).profile(B) / 'state.json').read_bytes()
        renamed = await panel.rename(B, '  Beta Two  ')
        log_scan.watch('Beta Two', kind='name')
        assert renamed.status_code == 200 and renamed.json() == {
            'id': B, 'label': 'Beta Two', 'port': 18000, 'is_default': False, 'disabled_reason': None,
            'status': 'running', 'blocked_reason': None}
        assert [(item.id, item.label) for item in profiles.read_index(profiles.Layout(data).index).entries] == [
            (B, 'Beta Two'), (C, LABELS[C])]
        assert runtime.token(B) == token and (profiles.Layout(data).profile(B) / 'state.json').read_bytes() == before
        for profile_id, label, expected in (('default', 'Main', (422, 'profile_default_immutable')),
                                            ('f' * 24, 'Main', (404, 'profile_not_found')),
                                            (B, 'GAMMA OPS', (409, 'profile_label_conflict')),
                                            (B, '', (422, 'profile_label_invalid'))):
            response = await panel.rename(profile_id, label)
            assert (response.status_code, code_of(response)) == expected, (profile_id, label)
        assert (await panel.rename(B, 'Beta Two')).status_code == 200
        etag = await panel.etag()
        async with panel.client() as client:
            for path, body in ((f'/api/profiles/{B.upper()}', {'label': 'x'}), ('/api/profiles/index', {'label': 'x'}),
                               (f'/api/profiles/{B}', {'label': 1}), (f'/api/profiles/{B}', {'label': 'x', 'y': 1}),
                               (f'/api/profiles/{B}', ['x']), (f'/api/profiles/{B}', {})):
                response = await client.patch(path, json=body, headers=panel.headers(etag, key=False))
                assert (response.status_code, response.content) == (400, b'{"error":"request denied"}'), (path, body)
            response = await client.patch(f'/api/profiles/{B}', headers=panel.headers(etag, key=False))
            assert (response.status_code, response.content) == (415, b'{"error":"request denied"}')  # no JSON body
            refused = await client.get(f'/api/profiles/{B}', headers=ADMIN)
            assert (refused.status_code, refused.content, refused.headers['allow']) == (
                405, b'Method Not Allowed', 'PATCH, DELETE')


# ---- deletion (contract 3.1; plan 4.4; DQ-14; T-09; FM-23, FM-33) ----

async def test_a_deletion_revokes_stops_unindexes_and_removes_the_profile(tmp_path, log_scan, monkeypatch):
    """DELETE /api/profiles/<id>: the token stops working at once on both paths, its requests end, the credentials are
    wiped before the directory goes, its monitor and its child stop, its port is free for the next profile, the
    directory is gone, and a profile its port held back starts at once (PaaS B-17); 200 {"deleted", "operation"}, the
    same for the replay. A new profile gets a new id and a new token. The default profile 422; an unknown id 404. The
    default profile's state is never written (I6)."""
    data = setup(tmp_path, extras=(B, C, D), ports={B: 18000, C: 18001, D: 18001})
    layout = profiles.Layout(data)
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C, D),
                                                                       {B: 18000, C: 18001, D: 18001})) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        default_state = (data / 'state.json').read_bytes()
        panel = Panel(runtime, await csrf_of(runtime))
        manager = runtime.manager
        b_token = runtime.token(B)
        assert manager.get(C).runtime.supervisor.status == 'blocked'
        monitor = monitor_of(manager, B)
        assert monitor is not None and not monitor.done()
        ended, wiped = [], []
        access = manager.get(B).runtime.token_access
        original = access.committed
        monkeypatch.setattr(access, 'committed', lambda: (ended.append(True), original())[1])
        removing = profiles.remove_profile_directory

        def remove(layout_, profile_id):
            value = stored(layout_.profile(profile_id))
            wiped.append((value['token'], value['connection']))
            return removing(layout_, profile_id)
        monkeypatch.setattr(profiles, 'remove_profile_directory', remove)
        supervisor = manager.get(B).runtime.supervisor
        key = operation_key()
        deleted = await panel.delete(B, key=key)
        assert deleted.status_code == 200 and deleted.json() == {
            'deleted': B, 'operation': {'id': key, 'kind': 'profile.delete', 'state': 'completed', 'replayed': False}}
        assert ended == [True] and wiped == [(None, None)]
        assert supervisor.status == 'stopped' and manager.get(B) is None
        assert monitor.cancelled() and monitor_of(manager, B) is None  # HM-09 review S-4 (R17): its monitor stopped
        assert not layout.profile(B).exists()
        assert [item.id for item in profiles.read_index(layout.index).entries] == [C, D]
        async with runtime.mcp() as client:
            for path, headers, expected in (('/mcp', {**ACCEPT, 'Authorization': 'Bearer ' + b_token}, BEARER_REQUIRED),
                                            (f'/private_{b_token}/mcp', ACCEPT, NOT_FOUND)):
                assert answer(await client.post(path, headers=headers, json=initialize_message())) == expected
        replayed = await panel.delete(B, key=key)
        assert replayed.status_code == 200 and replayed.json()['operation']['replayed'] is True
        # D goes: C, on D's port, starts at once.
        assert (await panel.delete(D)).status_code == 200
        assert manager.get(C).disabled is None and manager.get(C).runtime.supervisor.status == 'running'
        # B's port is free: the next profile gets it, with a new id and a new token.
        created = await panel.create(NEW_LABELS[0])
        assert created.status_code == 201 and created.json()['port'] == 18000 and created.json()['id'] != B
        new_token = stored(layout.profile(created.json()['id']))['token']
        log_scan.watch(new_token)
        assert new_token != b_token
        for profile_id, expected in (('default', (422, 'profile_default_immutable')),
                                     ('f' * 24, (404, 'profile_not_found'))):
            response = await panel.delete(profile_id)
            assert (response.status_code, code_of(response)) == expected
        assert stored(data)['token'] is not None and (data / 'state.json').read_bytes() == default_state


async def test_deleting_a_profile_under_load_ends_only_its_own_requests(tmp_path, log_scan):
    """I3, T-12 (FM-33): a call of B and one of the default profile wait for their children; deleting B ends B's call
    at once (its token is revoked before anything else: 401 on /mcp), the default profile's call goes on and gets its
    answer."""
    data = setup(tmp_path, extras=(B,))
    children = children_of(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        panel = Panel(runtime, await csrf_of(runtime))
        default_child, b_child = children.by_port[3000], children.by_port[18000]
        tokens = {'default': runtime.token('default'), B: runtime.token(B)}
        async with runtime.mcp() as client:
            sessions = {}
            for profile_id, token in tokens.items():
                init = await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer ' + token},
                                         json=initialize_message())
                assert init.status_code == 200
                sessions[profile_id] = init.headers['mcp-session-id']

            def call(profile_id, ident):
                return asyncio.create_task(client.post('/mcp', json={
                    'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
                    'params': {'name': PROBES[PRODUCT][0], 'arguments': PROBES[PRODUCT][1]}}, headers={
                    **ACCEPT, 'Authorization': 'Bearer ' + tokens[profile_id], 'Mcp-Session-Id': sessions[profile_id]}))
            default_child.hold()
            b_child.hold()
            waiting = {profile_id: call(profile_id, number) for number, profile_id in enumerate(tokens, start=3)}
            await asyncio.wait_for(asyncio.gather(default_child.held.wait(), b_child.held.wait()), 5)
            deleted = await panel.delete(B)
            assert deleted.status_code == 200
            ended = await asyncio.wait_for(waiting[B], 5)
            assert (ended.status_code, ended.json()) == (401, {'error': 'request denied'})
            await asyncio.sleep(.3)
            assert not waiting['default'].done()
            default_child.release.set()
            answered = await asyncio.wait_for(waiting['default'], 5)
            assert answered.status_code == 200 and answered.json()['result']['content'][0]['text'] == (
                default_child.text)


async def test_a_save_waiting_for_a_deleted_profiles_lock_changes_nothing(tmp_path, log_scan, monkeypatch):
    """A save for B that comes in while B is being deleted waits for B's lock; it gets the lock only once B is no
    longer served and its store is closed: 503 state unavailable, nothing written, no child started again for the
    deleted profile, its directory gone."""
    data = setup(tmp_path, extras=(B,))
    layout = profiles.Layout(data)
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data)) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        manager = runtime.manager
        async with runtime.admin(B) as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
        entry = manager.get(B)
        lock, supervisor = entry.runtime.mutation_lock, entry.runtime.supervisor
        starts = supervisor.starts
        save = {}
        removing = manager.remove

        async def remove(profile_id):
            # The deletion holds B's lock now: a save for B waits for it (asyncio.Lock queues its waiters).
            client = runtime.admin(B)
            save['client'] = client
            save['task'] = asyncio.create_task(client.put('/api/odoo/write-switches', json={'odoo_write_switches': {
                'enable_writes': True, 'allow_direct_writes': True, 'allow_unknown_methods': True,
                'chatter_direct': True}}, headers=reviewed_headers(boot, ADMIN)))
            async with asyncio.timeout(5):
                while not lock._waiters:
                    await asyncio.sleep(.01)
            await removing(profile_id)
        monkeypatch.setattr(manager, 'remove', remove)
        deleted = await Panel(runtime, boot['csrf']).delete(B)
        assert deleted.status_code == 200
        try:
            response = await asyncio.wait_for(save['task'], 5)
        finally:
            await save['client'].aclose()
        assert (response.status_code, response.content) == STATE_UNAVAILABLE
        assert supervisor.status == 'stopped' and supervisor.starts == starts
        assert not layout.profile(B).exists() and manager.get(B) is None


async def test_an_orphan_and_an_unavailable_profile_can_be_deleted(tmp_path, log_scan):
    """DQ-14: an orphan (a profile directory the index does not list) is listed and deleted only when asked: revoked,
    wiped, removed; an indexed profile whose state cannot be read (profile_unavailable) is unindexed and removed."""
    data = setup(tmp_path, extras=(B, C))
    layout = profiles.Layout(data)
    create_profile(data, PRODUCT, D, label=LABELS[D], port=18002, indexed=False)
    watch(log_scan, data)
    (layout.profile(C) / 'state.json').write_text('{')  # C cannot be read
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B,))) as runtime:
        await settle(runtime, 'configured')
        panel = Panel(runtime, await csrf_of(runtime))
        listed = (await panel.list())[0]
        assert listed['orphans'] == [{'id': D}]
        assert listed['profiles'][2]['disabled_reason'] == 'profile_unavailable'
        assert layout.profile(D).exists()  # never deleted on its own
        for profile_id in (D, C):
            response = await panel.delete(profile_id)
            assert response.status_code == 200 and response.json()['deleted'] == profile_id
            assert not layout.profile(profile_id).exists()
        listed = (await panel.list())[0]
        assert listed['orphans'] == [] and [row['id'] for row in listed['profiles']] == ['default', B]


async def test_a_deletion_waits_for_the_profiles_lock_and_the_add_ons(tmp_path, log_scan, monkeypatch):
    """Step 8: the add-on's profile lock and the profile's own lock are each waited for at most 2 s (here 0.2 s): a
    deletion while the profile's lock is held, or a creation while the add-on's is, is 503 and changes nothing."""
    monkeypatch.setattr(admin_module(), 'LOCK_SECONDS', 0.2)
    data = setup(tmp_path, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data)) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        panel = Panel(runtime, await csrf_of(runtime))
        before = tree_of(data)
        for lock, request in ((runtime.manager.get(B).runtime.mutation_lock, panel.delete(B)),
                              (runtime.manager.admin.lock, panel.create(NEW_LABELS[0]))):
            await lock.acquire()
            try:
                response = await request
            finally:
                lock.release()
            assert (response.status_code, response.content) == (503, b'{"error":"request denied"}')
        assert tree_of(data) == before


async def test_a_start_after_an_index_change_waits_for_the_profiles_own_lock(tmp_path, log_scan):
    """HM-09 review S-12 (2), wired here: the start a reevaluation makes after an index change (and the boot's start,
    start_all: both ProfileRuntime.launch) holds the profile's own lock, as a save and the panel's restart do, so the
    two never interleave. C and D share a port (both disabled); while a save of C holds C's lock, deleting D frees the
    port: the deletion is committed (D unindexed, its directory gone) but C's child is not started before C's lock is
    released; then it starts once and the deletion answers."""
    ports = {C: 18001, D: 18001}
    data = setup(tmp_path, extras=(C, D), ports=ports)
    layout = profiles.Layout(data)
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (C, D), ports)) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        panel = Panel(runtime, await csrf_of(runtime))
        entry = runtime.manager.get(C)
        supervisor, lock = entry.runtime.supervisor, entry.runtime.mutation_lock
        assert supervisor.status == 'blocked' and entry.disabled == {'disabled_reason': 'port_conflict'}
        starts = supervisor.starts
        etag = await panel.etag()
        await lock.acquire()  # a save of C is under way
        try:
            deleting = asyncio.create_task(panel.delete(D, etag=etag))
            async with asyncio.timeout(5):
                while runtime.manager.get(D) is not None or layout.profile(D).exists():
                    await asyncio.sleep(.01)
            await asyncio.sleep(.2)
            assert [item.id for item in profiles.read_index(layout.index).entries] == [C]
            assert supervisor.status == 'blocked' and supervisor.starts == starts and not deleting.done()
        finally:
            lock.release()
        deleted = await asyncio.wait_for(deleting, 5)
        assert deleted.status_code == 200, deleted.content
        assert entry.disabled is None and supervisor.status == 'running' and supervisor.starts == starts + 1


# ---- the index quarantine (contract 3.6; DQ-12; FM-131) ----

@pytest.mark.parametrize('damage', ['corrupt', 'replaced'])
async def test_quarantining_an_unusable_index_serves_the_default_profile_again(tmp_path, log_scan, damage):
    """An unusable index (corrupt at the start, or replaced behind the add-on's back while it runs): every token 503,
    the list, a creation and B's paths 503 profile_index_corrupt; the default profile's bootstrap says corrupt with the
    ETag of the bytes. The quarantine with that ETag and a key: every profile directory's token revoked, profiles.json
    renamed (bytes kept), 8081 serves the default profile again at once, the directories are orphans (listed,
    deletable). A wrong ETag, or a usable index, is 409 config_conflict; the replay answers what was done."""
    data = setup(tmp_path, extras=(B, C))
    layout = profiles.Layout(data)
    if damage == 'corrupt':
        layout.index.write_bytes(b'{"version": 1, "profile_index": {"..": 1}}')
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data, (B, C))) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        if damage == 'replaced':
            raw = layout.index.read_bytes()
            layout.index.unlink()
            layout.index.write_bytes(raw)
            layout.index.chmod(0o600)
        raw = layout.index.read_bytes()
        default_token = runtime.token('default')
        async with runtime.mcp() as client:
            response = await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer ' + default_token},
                                         json=initialize_message())
            assert (response.status_code, response.content) == STATE_UNAVAILABLE
        async with runtime.admin() as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
        assert boot['profile_index_state'] == 'corrupt' and admin_module().ETAG.fullmatch(boot['profile_index_etag'])
        panel = Panel(runtime, boot['csrf'])
        async with panel.client() as client:
            for method, path, kwargs in (('GET', '/api/profiles', {}),
                                         ('POST', '/api/profiles', {'json': {'label': NEW_LABELS[0]}})):
                response = await client.request(method, path, headers=panel.headers('"p1-' + '0' * 64 + '"'), **kwargs)
                assert (response.status_code, code_of(response)) == (503, 'profile_index_corrupt')
        async with runtime.admin(B) as admin:
            response = await admin.get('/api/bootstrap', headers=ADMIN)
            assert (response.status_code, code_of(response)) == (503, 'profile_index_corrupt')
        wrong = await panel.quarantine('"p1-' + '0' * 64 + '"')
        assert (wrong.status_code, wrong.content) == (409, b'{"detail":{"code":"config_conflict"}}')
        assert layout.index.read_bytes() == raw
        key = operation_key()
        done = await panel.quarantine(boot['profile_index_etag'], key=key)
        assert done.status_code == 200, done.content
        name = done.json()['quarantined']
        assert name.startswith('profiles.json.quarantine-') and done.json()['operation'] == {
            'id': key, 'kind': 'profile.index_quarantine', 'state': 'completed', 'replayed': False}
        assert not layout.index.exists() and (data / name).read_bytes() == raw
        assert all(stored(layout.profile(profile_id))['token'] is None for profile_id in (B, C))
        assert runtime.manager.get(B) is None and runtime.manager.get(C) is None
        async with runtime.mcp() as client:
            response = await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer ' + default_token},
                                         json=initialize_message())
            assert response.status_code == 200
        listed, etag = await panel.list()
        assert [row['id'] for row in listed['profiles']] == ['default'] and listed['orphans'] == [{'id': B}, {'id': C}]
        replayed = await panel.quarantine(boot['profile_index_etag'], key=key)
        assert replayed.json() == {'quarantined': name, 'operation': {**done.json()['operation'], 'replayed': True}}
        usable = await panel.quarantine(etag)
        assert (usable.status_code, usable.content) == (409, b'{"detail":{"code":"config_conflict"}}')
        assert (await panel.delete(B)).status_code == 200 and not layout.profile(B).exists()
        async with runtime.admin() as admin:
            assert (await admin.get('/api/bootstrap', headers=ADMIN)).json()['profile_index_state'] == 'ok'


def test_a_second_quarantine_in_the_same_second_gets_its_own_name(tmp_path):
    """HM-07 review S-15: the index quarantine never renames over an earlier one: the second name of one second gets a
    number."""
    from datetime import datetime, timezone
    layout = profiles.Layout(tmp_path)
    when = datetime(2026, 11, 15, 12, 0, 0, tzinfo=timezone.utc)
    first = profiles.free_index_quarantine_name(layout, when)
    assert first == 'profiles.json.quarantine-20261115T120000Z'
    (tmp_path / first).write_bytes(b'first')
    second = profiles.free_index_quarantine_name(layout, when)
    assert second == first + '-2'
    os.symlink('/nonexistent', tmp_path / second)  # a dangling link takes a name too
    assert profiles.free_index_quarantine_name(layout, when) == first + '-3'


async def test_there_is_nothing_to_quarantine_without_an_index_file(tmp_path, log_scan):
    """A profiles entry that could not be listed at the start (here a file) makes the index unusable without any index
    file (HM-08: every token 503 until a restart; the bootstrap says corrupt). Quarantining then is 409
    config_conflict before anything is revoked or recorded, even once the directory can be listed again: there is no
    index to move aside, so the add-on is restarted instead."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    layout = profiles.Layout(data)
    layout.profiles.write_text('not a directory')
    async with multi_profile_runtime(PRODUCT, data) as runtime:
        await settle(runtime, 'configured')
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        async with runtime.admin() as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
        assert boot['profile_index_state'] == 'corrupt' and admin_module().ETAG.fullmatch(boot['profile_index_etag'])
        layout.profiles.unlink()
        profiles.ensure_profiles_directory(layout)
        before = tree_of(data)
        response = await Panel(runtime, boot['csrf']).quarantine(boot['profile_index_etag'])
        assert (response.status_code, response.content) == (409, b'{"detail":{"code":"config_conflict"}}')
        assert tree_of(data) == before and not (data / '.profiles.json.operations.json').exists()


def test_a_profile_directory_is_removed_without_following_a_link(tmp_path):
    """The last step of a deletion (plan 4.4): the profile's directory and all it holds go, a link inside it removed,
    never followed; a link at the profile's own name, or a profiles directory replaced by a link, is never followed
    (False: what is left is an orphan, deletable again). Nothing there: nothing left (True)."""
    layout = profiles.Layout(tmp_path)
    profiles.ensure_profiles_directory(layout)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'kept').write_text('kept')
    directory = layout.profile(B)
    (directory / 'child').mkdir(parents=True)
    (directory / 'state.json').write_text('{}')
    (directory / 'child' / 'link').symlink_to(outside)
    assert profiles.remove_profile_directory(layout, B) is True and not directory.exists()
    assert profiles.remove_profile_directory(layout, C) is True
    layout.profile(C).symlink_to(outside)
    assert profiles.remove_profile_directory(layout, C) is False and layout.profile(C).is_symlink()
    layout.profile(C).unlink()
    moved = tmp_path / 'moved'
    layout.profiles.rename(moved)
    (moved / D).mkdir()
    layout.profiles.symlink_to(moved)
    assert profiles.remove_profile_directory(layout, D) is False and (moved / D).is_dir()
    assert (outside / 'kept').read_text() == 'kept'


# ---- the pipeline's order for an administrator (contract 3.2) ----

async def test_the_second_role_check_comes_after_every_wait_and_before_any_change(tmp_path, log_scan):
    """Step 10: a role taken away while a request waits (after the first check) refuses it there: 403, nothing
    created, renamed or deleted."""
    data = setup(tmp_path, extras=(B,))
    asked = []

    async def changing(user):
        asked.append(user)
        return user == ADMIN['X-Remote-User-Id'] and not removed.is_set()
    removed = asyncio.Event()
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data), verifier=changing) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        panel = Panel(runtime, await csrf_of(runtime))
        etag = await panel.etag()
        before = tree_of(data)
        lock = runtime.manager.admin.lock
        for request in (lambda: panel.create(NEW_LABELS[0], etag=etag), lambda: panel.rename(B, 'Beta X', etag=etag),
                        lambda: panel.delete(B, etag=etag)):
            removed.clear()
            await lock.acquire()
            task = asyncio.create_task(request())
            count = len(asked)
            async with asyncio.timeout(5):
                while len(asked) == count:  # the first role check has answered: the request waits for the lock
                    await asyncio.sleep(.01)
            removed.set()
            lock.release()
            response = await task
            assert (response.status_code, response.content) == (403, b'{"error":"request denied"}')
        assert tree_of(data) == before


# ---- a profile's own actions (T-07; FM-47; PaaS test_profile_b_restart_completes_while_profile_a_drains) ----

async def test_a_profiles_actions_restart_and_show_only_its_own_child(tmp_path, log_scan):
    """T-07: child/restart and a saved write switch on B restart B's child only, and both complete while a call of the
    default profile waits for its child, which then gets its answer (PaaS
    test_profile_b_restart_completes_while_profile_a_drains); a save with a stale If-Match (PaaS
    test_stale_policy_update_does_not_restart) and a restart naming an unknown profile (PaaS
    test_unknown_profile_does_not_restart: 404 profile_not_found, never the default profile instead) restart nothing;
    diagnostics on B shows B's child output only (§8.8 #29; PaaS test_stream_endpoint_serves_only_the_selected_profile);
    B's receipts are B's own and the default profile's state is never written."""
    data = setup(tmp_path, extras=(B,))
    children = children_of(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        manager = runtime.manager
        default, extra = manager.get('default').runtime.supervisor, manager.get(B).runtime.supervisor
        default.logs.append('stdout', 'default child line', default.starts)
        extra.logs.append('stdout', 'beta child line', extra.starts)
        starts = (default.starts, extra.starts)
        default_state = (data / 'state.json').read_bytes()
        default_child, token = children.by_port[3000], runtime.token('default')
        switches = {'enable_writes': False, 'allow_direct_writes': False, 'allow_unknown_methods': False,
                    'chatter_direct': False}
        async with runtime.mcp() as client:
            init = await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer ' + token},
                                     json=initialize_message())
            assert init.status_code == 200
            default_child.hold()
            waiting = asyncio.create_task(client.post('/mcp', json={
                'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                'params': {'name': PROBES[PRODUCT][0], 'arguments': PROBES[PRODUCT][1]}}, headers={
                **ACCEPT, 'Authorization': 'Bearer ' + token, 'Mcp-Session-Id': init.headers['mcp-session-id']}))
            await asyncio.wait_for(default_child.held.wait(), 5)
            async with runtime.admin(B) as admin:
                boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
                restarted = await admin.post('/api/child/restart', headers=reviewed_headers(boot, ADMIN))
                assert restarted.status_code == 202 and restarted.json()['profile'] == {'id': B}
                saved = await admin.put('/api/odoo/write-switches', json={'odoo_write_switches': switches},
                                        headers=reviewed_headers(boot, ADMIN))
                assert saved.status_code == 200 and saved.json()['profile'] == {'id': B}
                stale = await admin.put('/api/odoo/write-switches', json={'odoo_write_switches': switches},
                                        headers=reviewed_headers(boot, ADMIN))
                assert (stale.status_code, stale.json()['detail']) == (409, {'code': 'config_conflict'})
                shown = (await admin.get('/api/diagnostics', headers=ADMIN)).json()
            async with runtime.admin('f' * 24) as admin:
                unknown = await admin.post('/api/child/restart', headers=reviewed_headers(boot, ADMIN))
                assert (unknown.status_code, code_of(unknown)) == (404, 'profile_not_found')
            assert not waiting.done()  # B's restarts did not wait for the default profile's call
            default_child.release.set()
            answered = await asyncio.wait_for(waiting, 5)
            assert answered.status_code == 200 and answered.json()['result']['content'][0]['text'] == (
                default_child.text)
        assert (default.starts, extra.starts) == (starts[0], starts[1] + 2)
        assert stored(profiles.Layout(data).profile(B))['odoo_write_switches'] == switches
        assert (data / 'state.json').read_bytes() == default_state
        assert [entry['text'] for entry in shown['logs']['entries']] == ['beta child line']
        assert (profiles.Layout(data).profile(B) / '.state.json.operations.json').is_file()
        assert not (data / '.state.json.operations.json').exists()  # the receipt is B's own


def test_the_index_etag_is_bound_to_the_entries_and_this_process():
    """The index ETag "p1-<64 hex>": the same entries the same ETag, another label, port or order another; another
    process (another key) another."""
    class Manager:
        layout = profiles.Layout(Path('/nonexistent'))
        product = PRODUCT

    first = admin_module().ProfileAdmin(Manager(), None)
    second = admin_module().ProfileAdmin(Manager(), None)
    entries = [profiles.IndexEntry(B, 'Beta Ops', 18000), profiles.IndexEntry(C, 'Gamma Ops', 18001)]
    etag = first.etag(entries)
    assert admin_module().ETAG.fullmatch(etag) and first.etag(list(entries)) == etag
    assert first.etag([profiles.IndexEntry(B, 'Beta Two', 18000), entries[1]]) != etag
    assert first.etag([profiles.IndexEntry(B, 'Beta Ops', 18002), entries[1]]) != etag
    assert first.etag(entries[::-1]) != etag and first.etag(()) != etag
    assert second.etag(entries) != etag


def test_a_store_error_is_never_a_server_error():
    """ConfigError reaches error_handler (503 state unavailable), never a 500 (the dispatcher's app has the handler)."""
    from mcp_admin_core.gateway import management_app
    assert ConfigError in management_app(lambda request: None).exception_handlers
