"""HM-12: once a product is switched on, a backend URL moved to another origin takes no stored secret along (DQ-40 ⑨
(a), 2026-11-14; multi-profile plan 8.8 #41, 12.3 HM-12; contract 3.1, 4.1, section 9 #41 and HM-12's row on the
new-origin rule; FM-89, FM-152; plan review C1-S13).

A partial connection edit (PUT backend/patch) of a switched-on product (features.enabled, read at every save) that
moves one of its URLs to another origin (scheme, host or port; a missing port is the scheme's own: 80, 443) must bring
every secret that URL takes to its server and is stored now: Odoo's password, Odoo Manage's API key, n8n's API key and
MCP access token, Hermes' gateway API key (gateway_url) and dashboard password (dashboard_url), EMQX's key and secret,
LiteLLM's master key, Nextcloud's app password, Headscale's API key (identity_fields.URL_SECRETS). A secret brought
counts whatever its value, and so does a nullable one brought as null (it is cleared, not carried). Otherwise 422
{"error":"request denied","detail":{"code":"CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN"}} (the PaaS Headscale code,
in HA's shape for a new code: contract 4.1), at step ⑪ after If-Match, with nothing written and no child restarted.
A URL on the same origin (another path, the host in capitals, the default port spelled out) needs no secret, nor does
OpenDesign (it has none). PUT backend replaces the whole connection, its secrets included, so it never refuses. Not
switched on, every save is today's (backend_edit: an existing credential may be kept at a deliberately changed
destination).

PaaS (woow-mcp-server 69ac425): apps/headscale/headscale_mcp_admin/connection.py:104-109, the only product there with
the rule (base_url and paas_base_url, any change of the whole URL, a retained secret). Every case runs make_apps in
process, or the production runtime with Odoo switched on (tests/multi_profile_runtime.py) for the dispatcher, under the
HM-01 log scan.
"""
from contextlib import asynccontextmanager, closing
from dataclasses import dataclass

import httpx
import pytest

from admin_write_headers import reviewed_headers
from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import Children, all_tokens, create_profile, ids, multi_profile_runtime, stored
from mcp_admin_core import backend_edit, features, identity_fields, profiles
from mcp_admin_core.capabilities import ManagementOptions
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.identity_fields import SECRET
from mcp_admin_core.products import TOOLS, URL_FIELDS, ProductStore
from n8n_adapter import TOOLS as N8N_TOOLS
from test_single_profile_golden import ADMIN, GENUINE_CLIENT, INGRESS, configure, settle

pytestmark = pytest.mark.usefixtures('log_scan')

@pytest.fixture(autouse=True)
def resolve_reserved_test_domains(monkeypatch):
    """Keep origin tests independent of DNS while exercising strict address validation."""
    import asyncio
    import socket
    original = asyncio.BaseEventLoop.getaddrinfo

    async def resolve(loop, host, port, *args, **kwargs):
        if host.lower().endswith('.invalid'):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', port))]
        return await original(loop, host, port, *args, **kwargs)

    monkeypatch.setattr(asyncio.BaseEventLoop, 'getaddrinfo', resolve)

REFUSED = b'{"error":"request denied","detail":{"code":"CREDENTIAL_REPLACEMENT_REQUIRED_FOR_NEW_ORIGIN"}}'
# What each product stores (admin API names; tests/fixtures/owner_defaults/README.md rules: .invalid hosts, DUMMY-
# credentials); every URL names its port, so that the scheme can change alone.
STORED = {
    'n8n': {'url': 'https://n8n.invalid:5678', 'key': 'DUMMY-origin-n8n-key',
            'mcp_access_token': 'DUMMY-origin-n8n-native-token'},
    'odoo': {'url': 'https://odoo.invalid:8069', 'database': 'DUMMY-db', 'username': 'DUMMY-user',
             'password': 'DUMMY-origin-odoo-password'},
    'odoo-manage': {'url': 'https://odoo.invalid:8069', 'database': 'DUMMY-db', 'username': 'DUMMY-user',
                    'api_key': 'DUMMY-origin-manage-key', 'mode': 'read'},
    'hermes': {'gateway_url': 'https://hermes.invalid:8642', 'gateway_api_key': 'DUMMY-origin-hermes-key',
               'dashboard_url': 'https://hermes.invalid:9119', 'dashboard_username': 'DUMMY-user',
               'dashboard_password': 'DUMMY-origin-dashboard-password'},
    'opendesign': {'url': 'https://opendesign.invalid:8443'},
    'emqx': {'url': 'https://emqx.invalid:18083', 'api_key': 'DUMMY-origin-emqx-key',
             'api_secret': 'DUMMY-origin-emqx-secret'},
    'litellm': {'url': 'https://litellm.invalid:4000', 'master_key': 'DUMMY-origin-litellm-key'},
    'nextcloud': {'url': 'https://nextcloud.invalid:8443', 'username': 'DUMMY-user',
                  'app_password': 'DUMMY-origin-nextcloud-password'},
    'headscale': {'url': 'https://headscale.invalid:8080', 'api_key': 'DUMMY-origin-headscale-key'},
}
# The secrets each URL takes to its server (admin API names): the rule's specification, written out here.
CARRIED = {
    'n8n': {'url': ('key', 'mcp_access_token')},
    'odoo': {'url': ('password',)},
    'odoo-manage': {'url': ('api_key',)},
    'hermes': {'gateway_url': ('gateway_api_key',), 'dashboard_url': ('dashboard_password',)},
    'opendesign': {'url': ()},
    'emqx': {'url': ('api_key', 'api_secret')},
    'litellm': {'url': ('master_key',)},
    'nextcloud': {'url': ('app_password',)},
    'headscale': {'url': ('api_key',)},
}
PRODUCTS = sorted(STORED)
B = ids(1)[0]


def moved(url, kind):
    """url (scheme://host:port) on another origin: its scheme, its host or its port changed."""
    scheme, rest = url.split('://')
    host, port = rest.rsplit(':', 1)
    return {'scheme': f'{"http" if scheme == "https" else "https"}://{host}:{port}',
            'host': f'{scheme}://elsewhere-{host}:{port}',
            'port': f'{scheme}://{host}:{int(port) + 1}'}[kind]


def same_origin(product, url):
    """url on its own origin, spelled otherwise: another path (Headscale: its /api/v1 root, which is saved without
    it), the host in capitals."""
    scheme, rest = url.split('://')
    return [url + ('/api/v1' if product == 'headscale' else '/backend'), f'{scheme}://{rest.upper()}']


def new_value(name):
    return 'DUMMY-origin-' + name.replace('_', '-') + '-next'


@dataclass
class Admin:
    product: str
    client: httpx.AsyncClient
    store: ProductStore
    restarts: list

    async def put(self, route, body, **extra):
        boot = await self.client.get('/api/bootstrap', headers=ADMIN)
        assert boot.status_code == 200
        headers = {**reviewed_headers(boot.json(), ADMIN), **extra}
        return await self.client.put('/api/' + route, json=body, headers=headers)

    def secret(self, name):
        """The stored value of an admin API field (n8n's url/key are its backend_url/backend_key)."""
        state = self.store.load()
        if self.product == 'n8n':
            return {'url': state.backend_url, 'key': state.backend_key,
                    'mcp_access_token': state.mcp_access_token}[name]
        return getattr(state.connection, name)


@asynccontextmanager
async def admin_of(directory, product, log_scan, *, saved=None, management=None):
    """make_apps of a product whose backend saved holds (STORED unless given), its child restarts recorded."""
    restarts = []
    values = STORED[product] if saved is None else saved

    async def administrator(user):
        return user == ADMIN['X-Remote-User-Id']

    async def restart(state):
        restarts.append(state)

    with closing(ProductStore(directory, product)) as store:
        if product == 'n8n':
            store.update(backend_url=values['url'], backend_key=values['key'],
                         mcp_access_token=values.get('mcp_access_token'))
        else:
            store.update(connection=values)
        log_scan.watch_state(store.load())
        log_scan.watch(*(new_value(name) for names in CARRIED[product].values() for name in names), kind='secret')
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as child:
            admin, _ = make_apps(store, N8N_TOOLS if product == 'n8n' else TOOLS[product], child,
                                 verify_admin=administrator, backend_changed=restart,
                                 **({'management': management} if management is not None else {}))
            async with GENUINE_CLIENT(transport=httpx.ASGITransport(admin, client=INGRESS),
                                      base_url='http://admin') as client:
                yield Admin(product, client, store, restarts)


@pytest.fixture
def switch(monkeypatch):
    def turn(*products):
        monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset(products))
    return turn


# ---- the rule's table ----

def test_every_url_names_the_secrets_it_takes_to_its_server():
    """identity_fields.URL_SECRETS (stored names) names every backend URL of every product (products.URL_FIELDS, and
    n8n's backend_url), and every secret of the product exactly once (identity_fields' SECRET class); backend_edit
    reads it in the admin API's names, as written out above (CARRIED)."""
    assert set(identity_fields.URL_SECRETS) == set(identity_fields.BACKEND_FIELDS) == features.KNOWN_PRODUCTS
    for product, urls in identity_fields.URL_SECRETS.items():
        assert tuple(urls) == (('backend_url',) if product == 'n8n' else URL_FIELDS[product]), product
        carried = [name for names in urls.values() for name in names]
        assert len(carried) == len(set(carried)) and set(carried) == set(identity_fields.fields(product, SECRET))
        assert backend_edit.url_secrets(product) == CARRIED[product], product


def test_an_origin_is_the_scheme_the_host_and_the_effective_port():
    origin = backend_edit.origin
    assert origin('https://a.invalid') == origin('https://a.invalid:443') == origin('HTTPS://A.INVALID/x')
    assert origin('http://a.invalid') == origin('http://a.invalid:80') == ('http', 'a.invalid', 80)
    assert origin('https://a.invalid') != origin('http://a.invalid:443')  # the scheme alone
    assert origin('https://a.invalid:8443') != origin('https://a.invalid')
    assert origin('https://[fd12::1]:8080') == ('https', 'fd12::1', 8080)


# ---- switched on: a new origin brings its secrets ----

@pytest.mark.parametrize('product', PRODUCTS)
async def test_switched_on_a_url_moved_to_another_origin_must_bring_its_secrets(tmp_path, log_scan, switch, product):
    """For each URL and each way to move it (scheme, host, port): without its secrets 422 with nothing written and no
    restart; with all of them but one, 422 again; with every one of them, saved (one restart, the new values stored)."""
    switch(product)
    for url_name, secrets in CARRIED[product].items():
        for kind in ('scheme', 'host', 'port'):
            destination = moved(STORED[product][url_name], kind)
            async with admin_of(tmp_path / f'{url_name}-{kind}', product, log_scan) as admin:
                raw, token = admin.store.path.read_bytes(), admin.store.load().token
                attempts = [{}] + [{name: new_value(name) for name in secrets if name != left} for left in secrets
                                   if len(secrets) > 1]
                for brought in attempts if secrets else []:
                    response = await admin.put('backend/patch', {'changes': {url_name: destination, **brought}})
                    assert (response.status_code, response.content) == (422, REFUSED), (url_name, kind, brought)
                    unchanged = admin.store.path.read_bytes() == raw  # compared first: a failure prints no secret
                    assert unchanged and not admin.restarts, (url_name, kind)
                assert admin.store.load().token == token
                brought = {name: new_value(name) for name in secrets}
                response = await admin.put('backend/patch', {'changes': {url_name: destination, **brought}})
                assert response.status_code == 200, (url_name, kind, response.text)
                assert len(admin.restarts) == 1 and admin.secret(url_name) == destination
                assert all(admin.secret(name) == value for name, value in brought.items())


@pytest.mark.parametrize('product', PRODUCTS)
async def test_switched_on_a_url_on_its_own_origin_keeps_its_stored_secrets(tmp_path, log_scan, switch, product):
    """Another path on the same origin, the host in capitals: saved without any secret, which stays as stored."""
    switch(product)
    for url_name, secrets in CARRIED[product].items():
        for number, destination in enumerate(same_origin(product, STORED[product][url_name])):
            async with admin_of(tmp_path / f'{url_name}-{number}', product, log_scan) as admin:
                response = await admin.put('backend/patch', {'changes': {url_name: destination}})
                assert response.status_code == 200, (url_name, destination, response.text)
                assert all(admin.secret(name) == STORED[product][name] for name in secrets)


async def test_a_secret_brought_as_null_or_never_stored_is_not_carried(tmp_path, log_scan, switch):
    """n8n's MCP access token brought as null is cleared, not carried: the move is saved with the API key alone; one
    never stored needs nothing. Hermes' dashboard cleared as a whole moves nothing; its URL moved with its password is
    saved, the gateway's key untouched (each URL takes its own secret)."""
    switch('n8n', 'hermes')
    async with admin_of(tmp_path / 'cleared', 'n8n', log_scan) as admin:
        response = await admin.put('backend/patch', {'changes': {
            'url': moved(STORED['n8n']['url'], 'host'), 'key': new_value('key'), 'mcp_access_token': None}})
        assert response.status_code == 200, response.text
        assert admin.secret('mcp_access_token') is None and admin.secret('key') == new_value('key')
    without_token = {**STORED['n8n'], 'mcp_access_token': None}
    async with admin_of(tmp_path / 'never', 'n8n', log_scan, saved=without_token) as admin:
        response = await admin.put('backend/patch', {'changes': {
            'url': moved(STORED['n8n']['url'], 'port'), 'key': new_value('key')}})
        assert response.status_code == 200, response.text
    async with admin_of(tmp_path / 'dashboard', 'hermes', log_scan) as admin:
        response = await admin.put('backend/patch', {'changes': dict.fromkeys(
            ('dashboard_url', 'dashboard_username', 'dashboard_password'))})
        assert response.status_code == 200 and admin.secret('dashboard_url') is None, response.text
    async with admin_of(tmp_path / 'dashboard-moved', 'hermes', log_scan) as admin:
        response = await admin.put('backend/patch', {'changes': {
            'dashboard_url': moved(STORED['hermes']['dashboard_url'], 'host'),
            'dashboard_password': new_value('dashboard_password')}})
        assert response.status_code == 200, response.text
        assert admin.secret('gateway_api_key') == STORED['hermes']['gateway_api_key']


@pytest.mark.parametrize('product', PRODUCTS)
async def test_switched_on_a_whole_connection_brings_its_secrets_and_is_saved(tmp_path, log_scan, switch, product):
    """PUT backend replaces the whole connection, its secrets included: a moved URL is saved."""
    switch(product)
    url_name = next(iter(CARRIED[product]))
    async with admin_of(tmp_path / 'whole', product, log_scan) as admin:
        destination = moved(STORED[product][url_name], 'host')
        if product == 'n8n':
            body = {'url': destination, 'key': STORED['n8n']['key']}
        else:
            body = {'connection': {**STORED[product], url_name: destination}}
        response = await admin.put('backend', body)
        assert response.status_code == 200, response.text
        assert admin.secret(url_name) == destination


async def test_the_refusal_comes_after_the_checks_that_precede_it(tmp_path, log_scan, switch):
    """Step ⑪ (contract 3.2): a caller who is not an administrator gets today's 403, an edit that does not validate
    today's 400, a save without If-Match 428 and a stale one 409 config_conflict; a fixed backend 409 backend_fixed;
    only then the new origin's 422. Nothing is written by any of them."""
    switch('odoo')
    destination = moved(STORED['odoo']['url'], 'host')
    async with admin_of(tmp_path / 'order', 'odoo', log_scan) as admin:
        raw = admin.store.path.read_bytes()
        boot = (await admin.client.get('/api/bootstrap', headers=ADMIN)).json()
        headers = reviewed_headers(boot, ADMIN)
        viewer = await admin.client.put('/api/backend/patch', json={'changes': {'url': destination}},
                                        headers={**headers, 'X-Remote-User-Id': 'golden-viewer'})
        invalid = await admin.client.put('/api/backend/patch', json={'changes': {'url': 'ftp://elsewhere.invalid'}},
                                         headers=headers)
        missing = await admin.client.put('/api/backend/patch', json={'changes': {'url': destination}},
                                         headers={name: value for name, value in headers.items() if name != 'if-match'})
        stale = await admin.client.put('/api/backend/patch', json={'changes': {'url': destination}},
                                       headers={**headers, 'if-match': '"c1-' + '0' * 64 + '"'})
        assert (viewer.status_code, viewer.content) == (403, b'{"error":"request denied"}')
        assert (invalid.status_code, invalid.content) == (400, b'{"error":"request denied"}')
        assert (missing.status_code, missing.json()['detail']) == (428, {'code': 'config_revision_required'})
        assert (stale.status_code, stale.json()) == (409, {'detail': {'code': 'config_conflict'}})
        unchanged = admin.store.path.read_bytes() == raw
        assert unchanged and not admin.restarts
    fixed = ManagementOptions(backend_can_edit=False)
    async with admin_of(tmp_path / 'fixed', 'odoo', log_scan, management=fixed) as admin:
        response = await admin.put('backend/patch', {'changes': {'url': destination}})
        assert (response.status_code, response.content) == (409, b'{"error":"backend_fixed"}')


# ---- switched off: today's save ----

@pytest.mark.parametrize('product', PRODUCTS)
async def test_switched_off_a_url_moved_to_another_origin_keeps_todays_save(tmp_path, log_scan, switch, product):
    """Not switched on, the same edits are saved as today: the stored secrets go with the URL to its new origin, the
    answer is {"saved", "configuration"}, the child restarts once."""
    switch()
    for url_name, secrets in CARRIED[product].items():
        async with admin_of(tmp_path / url_name, product, log_scan) as admin:
            destination = moved(STORED[product][url_name], 'host')
            response = await admin.put('backend/patch', {'changes': {url_name: destination}})
            assert response.status_code == 200, response.text
            assert list(response.json()) == ['saved', 'configuration'] and len(admin.restarts) == 1
            assert admin.secret(url_name) == destination
            assert all(admin.secret(name) == STORED[product][name] for name in secrets)


# ---- through the switched-on dispatcher: the profile named, nothing else ----

async def test_through_the_dispatcher_only_the_named_profile_is_refused_or_saved(tmp_path, log_scan):
    """Odoo switched on with B: B's URL moved without its password is refused (422, the fixed body: an exception's
    answer carries no echo) with every state as it was and no child restarted; with the password it is saved (B's
    echo; the identity changed, so its token is rotated too: tests/test_odoo_identity_rotation.py)."""
    data = tmp_path / 'data'
    configure(data, 'odoo')
    create_profile(data, 'odoo', B, label='Beta Ops', port=18000)
    children = Children()
    children.profile_child(3000, 'default', 'odoo', data)
    children.profile_child(18000, 'p' + B[:4], 'odoo', profiles.Layout(data).profile(B))
    async with multi_profile_runtime('odoo', data, children=children) as runtime:
        await settle(runtime, 'configured')
        log_scan.watch(*all_tokens(data))
        log_scan.watch('Beta Ops', kind='name')
        log_scan.watch(new_value('password'), kind='secret')
        states = {path: path.read_bytes() for path in (data / 'state.json',
                                                       profiles.Layout(data).profile(B) / 'state.json')}
        supervisor = runtime.manager.get(B).runtime.supervisor
        starts, destination = supervisor.starts, moved(stored(profiles.Layout(data).profile(B))['connection']['url']
                                                       + ':8069', 'host')
        async with runtime.admin(B) as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            refused = await admin.put('/api/backend/patch', json={'changes': {'url': destination}},
                                      headers=reviewed_headers(boot, ADMIN))
            assert (refused.status_code, refused.content) == (422, REFUSED)
            assert all(path.read_bytes() == raw for path, raw in states.items()) and supervisor.starts == starts
            saved = await admin.put('/api/backend/patch', json={'changes': {
                'url': destination, 'password': new_value('password')}}, headers=reviewed_headers(boot, ADMIN))
            assert saved.status_code == 200 and saved.json()['profile'] == {'id': B}, saved.text
        log_scan.watch(runtime.token(B))
        assert stored(profiles.Layout(data).profile(B))['connection']['url'] == destination
        assert (data / 'state.json').read_bytes() == states[data / 'state.json']
