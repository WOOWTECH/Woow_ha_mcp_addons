"""A backend URL that backend_policy refuses on every call is refused when it is saved, for every product (only
Nextcloud did before), and a state saved before the check still loads so its administrator can correct it."""
from contextlib import closing
import importlib.util
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from mcp_admin_core.config import http_url
from mcp_admin_core.gateway import make_apps
from mcp_admin_core import products
from mcp_admin_core.products import ProductStore, TOOLS, saved_destination

spec = importlib.util.spec_from_file_location('backend_policy_saved', Path(__file__).resolve().parents[1] / 'apps/runtime/backend_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

IDENTITY = {"x-remote-user-id": "synthetic-owner"}
GOOD = {
    'odoo': {'url': 'http://odoo.test', 'database': 'db', 'username': 'synthetic-user', 'password': 'synthetic-password'},
    'odoo-manage': {'url': 'http://odoo.test', 'database': 'db', 'username': 'synthetic-user', 'api_key': 'synthetic-key',
                    'mode': 'read'},
    'hermes': {'gateway_url': 'http://hermes.test', 'gateway_api_key': 'synthetic-key',
               'dashboard_url': 'http://hermes.test:9119', 'dashboard_username': 'admin',
               'dashboard_password': 'synthetic-password'},
    'opendesign': {'url': 'http://od.test'},
    'emqx': {'url': 'http://emqx.test:18083', 'api_key': 'synthetic-key', 'api_secret': 'synthetic-secret'},
    'litellm': {'url': 'http://litellm.test', 'master_key': 'sk-synthetic'},
}
FIELDS = {'odoo': ['url'], 'odoo-manage': ['url'], 'hermes': ['gateway_url', 'dashboard_url'], 'opendesign': ['url'],
          'emqx': ['url'], 'litellm': ['url']}
REFUSED = ['http://backend.test/a/../b', 'http://backend.test/next%25cloud', 'http://backend.test/a%5cb',
           'http://metadata.google.internal', 'http://instance-data/x', 'http://雲端.example.tw', 'http://backend.test/?',
           'http://169.254.169.254', 'http://100.101.102.103:18083', 'http://192.0.2.10:8080', 'http://0.0.0.0',
           'http://[fe80::1]', 'http://[::ffff:192.168.1.5]', 'http://[fe80::1%25eth0]', 'http://backend.test:0']
UNRELATED = {'odoo': ('database', 'next-db'), 'odoo-manage': ('database', 'next-db'),
             'hermes': ('gateway_api_key', 'next-key'), 'emqx': ('api_secret', 'next-secret'),
             'litellm': ('master_key', 'sk-next')}
URL_CASES = ['https://backend.test', 'https://backend.test/', 'https://backend.test/sub', 'http://192.0.2.10:8080/x',
             'https://backend.test/a/./b', 'https://backend.test/a/../b', 'https://backend.test/..',
             'https://backend.test/next%25cloud', 'https://backend.test/a%2e%2e/b', 'https://backend.test/%2e%2e',
             'https://backend.test/a%5cb', 'https://metadata', 'https://METADATA.google.internal./x', 'http://instance-data',
             'https://backend.test/?', 'https://backend.test/#', 'https://@backend.test', 'https://backend.test/a%20b',
             'https://雲端.example.tw', 'https://backend.台灣/x', 'https://xn--suzq78c.example.tw',
             'http://169.254.169.254/x', 'http://100.101.102.103:18083', 'http://10.1.2.3:8069', 'http://127.0.0.1:4000',
             'http://[::1]:8080', 'http://[fd12::1]', 'http://[fe80::1]', 'http://[::ffff:10.0.0.1]', 'http://0.0.0.0:80',
             'http://backend.test:0', 'http://[fe80::1%25eth0]/x']
ADDRESSES = ['127.0.0.1', '10.1.2.3', '172.16.0.1', '192.168.1.1', '8.8.8.8', '100.63.255.255', '100.64.0.1',
             '169.254.169.254', '168.63.129.16', '0.0.0.0', '224.0.0.1', '240.0.0.1', '255.255.255.255', '192.0.0.192',
             '192.0.2.1', '198.51.100.1', '203.0.113.1', '192.88.99.1', '::1', '::', 'fe80::1', 'ff02::1', 'fd12::1',
             'fc00::1', 'fd00:ec2::254', '2606:4700::1111', '2001::1', '2001:db8::1', '2002:7f00:1::', '64:ff9b::1',
             '::ffff:127.0.0.1', 'fe80::1%eth0', 'not-an-address', '1.2.3']


@pytest.fixture(params=sorted(GOOD))
async def product_admin(request, tmp_path):
    product, applied = request.param, []

    async def verify(_):
        return True

    async def backend_changed(state):
        applied.append(state)

    def no_backend_request(_):
        raise AssertionError('saving a connection must not call the backend')

    with closing(ProductStore(tmp_path, product)) as store:
        store.update(connection=GOOD[product])
        async with httpx.AsyncClient(transport=httpx.MockTransport(no_backend_request)) as child:
            admin, _ = make_apps(store, TOOLS[product], child, verify_admin=verify, backend_changed=backend_changed)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)),
                                         base_url='http://admin') as client:
                yield product, client, store, applied


async def _put(client, route, body):
    before = await client.get('/api/bootstrap', headers=IDENTITY)
    assert before.status_code == 200
    return await client.put(route, json=body, headers={**IDENTITY, 'x-csrf-token': before.json()['csrf'],
                                                       'If-Match': before.headers['etag']})


@pytest.mark.parametrize('route', ['/api/backend', '/api/backend/patch'])
async def test_a_url_the_policy_refuses_is_refused_when_saved(product_admin, route):
    product, client, store, applied = product_admin
    raw = store.path.read_bytes()
    for field in FIELDS[product]:
        for url in REFUSED:
            body = ({'connection': {**GOOD[product], field: url}} if route == '/api/backend'
                    else {'changes': {field: url}})
            response = await _put(client, route, body)
            assert response.status_code == 400, (field, url, response.text)
            assert store.path.read_bytes() == raw and not applied


async def test_a_url_the_policy_accepts_is_still_saved(product_admin):
    product, client, store, applied = product_admin
    for url in ('http://backend.test/a%20b/sub', 'https://xn--suzq78c.example.tw'):
        response = await _put(client, '/api/backend/patch', {'changes': {FIELDS[product][0]: url}})
        assert response.status_code == 200, (url, response.text)
        assert getattr(store.load().connection, FIELDS[product][0]) == url
    assert len(applied) == 2


# Only the products that have a field besides their URL (OpenDesign has none): the cases are generated for those, so the
# test never skips (the unit gate of the checks job refuses a run with a skipped test).
@pytest.mark.parametrize('product_admin', sorted(UNRELATED), indirect=True)
async def test_a_stale_url_does_not_block_editing_the_other_fields(product_admin):
    product, client, store, applied = product_admin
    stale = {**GOOD[product], FIELDS[product][0]: 'http://169.254.169.254'}
    store.update(connection=stale)
    name, value = UNRELATED[product]
    response = await _put(client, '/api/backend/patch', {'changes': {name: value}})
    assert response.status_code == 200, response.text
    assert getattr(store.load().connection, name) == value
    response = await _put(client, '/api/backend/patch', {'changes': {FIELDS[product][0]: 'http://192.0.2.10'}})
    assert response.status_code == 400  # a URL this save changes is still checked


async def test_a_state_saved_before_the_check_still_loads_and_can_be_corrected(product_admin):
    product, client, store, applied = product_admin
    stale = {**GOOD[product], FIELDS[product][0]: 'http://backend.test/a/../b'}
    store.update(connection=stale)  # as an earlier version saved it: the models themselves do not refuse it
    assert getattr(store.load().connection, FIELDS[product][0]) == stale[FIELDS[product][0]]
    response = await _put(client, '/api/backend/patch', {'changes': {FIELDS[product][0]: 'http://backend.test/b'}})
    assert response.status_code == 200, response.text
    assert getattr(store.load().connection, FIELDS[product][0]) == 'http://backend.test/b'


def test_saved_and_run_time_checks_agree():
    """A URL accepted when saved works at run time; a URL the policy refuses is refused when saved. For a numeric host
    the run-time check includes the address check made before connecting (no DNS involved)."""
    import ipaddress
    for url in URL_CASES:
        try:
            saved = saved_destination(http_url(url)) is not None
        except ValueError:
            saved = False
        try:
            destination = policy.Destination(url)
            destination.check_url(httpx.URL(url.rstrip('/') + '/api/x'))
            try:
                ipaddress.ip_address(destination.host)
            except ValueError:
                pass
            else:
                policy.checked_answers(destination.host, destination.port)
            runs = urlsplit(url).port != 0
        except (policy.BackendDenied, ValueError, httpx.InvalidURL):
            runs = False
        if saved:
            assert runs, url
        if not runs:
            assert not saved, url


def test_the_address_rule_is_the_policy_rule():
    """products keeps a copy of backend_policy's address rule (importing the policy checks its pinned httpx sources)."""
    assert products._V4_DENY == policy._V4_DENY and products._V6_DENY == policy._V6_DENY
    for address in ADDRESSES:
        assert products.allowed_address(address) == policy.allowed_address(address), address


# ---------------------------------------------------------------------------------------------------------------------
# HM-20 (multi-profile plan 8.7, DQ-10, DQ-40 (7); docs/multi-profile/contract.md section 9 #39): once a product is
# switched on, a backend URL whose host is loopback (127.0.0.0/8, ::1, a localhost name) is refused when saved, for
# every product, n8n's backend URL included (n8n then gets the whole check above, which it never had). The add-on runs
# on Supervisor's bridge network, so a loopback address reaches only its own listeners: 8081, 8099, the children on
# 3000 and 18000 and up. Its own bridge address and host name are not covered (DQ-10's scope; HM-20 review S-4).
# Switched off, every answer is the one above, byte for byte. The run-time half: tests/test_backend_loopback.py.
# ---------------------------------------------------------------------------------------------------------------------
from contextlib import nullcontext  # noqa: E402
import ipaddress  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import socket  # noqa: E402
import subprocess  # noqa: E402

import n8n_adapter  # noqa: E402
import loopback_backends  # noqa: E402
from log_scan import log_scan  # noqa: E402,F401  (fixture)
from mcp_admin_core import backend_edit, features  # noqa: E402
from mcp_admin_core.products import check_saved_destinations  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# Every product, n8n included (test data rules, tests/fixtures/owner_defaults/README.md: .invalid hosts, DUMMY- values).
SWITCHABLE = {
    'n8n': {'url': 'http://n8n.invalid:5678', 'key': 'DUMMY-loopback-n8n-key'},
    'odoo': {'url': 'http://odoo.invalid:8069', 'database': 'DUMMY-db', 'username': 'DUMMY-user',
             'password': 'DUMMY-loopback-odoo-password'},
    'odoo-manage': {'url': 'http://odoo.invalid:8069', 'database': 'DUMMY-db', 'username': 'DUMMY-user',
                    'api_key': 'DUMMY-loopback-manage-key', 'mode': 'read'},
    'hermes': {'gateway_url': 'http://hermes.invalid:8642', 'gateway_api_key': 'DUMMY-loopback-hermes-key',
               'dashboard_url': 'http://hermes.invalid:9119', 'dashboard_username': 'DUMMY-user',
               'dashboard_password': 'DUMMY-loopback-dashboard-password'},
    'opendesign': {'url': 'http://opendesign.invalid'},
    'emqx': {'url': 'http://emqx.invalid:18083', 'api_key': 'DUMMY-loopback-emqx-key',
             'api_secret': 'DUMMY-loopback-emqx-secret'},
    'litellm': {'url': 'http://litellm.invalid:4000', 'master_key': 'DUMMY-loopback-litellm-key'},
    'nextcloud': {'url': 'http://nextcloud.invalid', 'username': 'DUMMY-user',
                  'app_password': 'DUMMY-loopback-nextcloud-password'},
    'headscale': {'url': 'http://headscale.invalid:8080', 'api_key': 'DUMMY-loopback-headscale-key'},
}
URL_NAMES = {product: ['gateway_url', 'dashboard_url'] if product == 'hermes' else ['url'] for product in SWITCHABLE}
# Loopback, which reaches this add-on's own listeners, in the spellings a resolver or a URL parser reads (FM-77: at
# least 8081, 8099, 3000 and the children's ports). IPv4 127.0.0.0/8 dotted, short, decimal, octal and hexadecimal,
# with a trailing dot (glibc's getaddrinfo reads a numeric host as inet_aton(3) does; n8n's Node child parses URLs as
# the WHATWG URL standard says); IPv6 ::1 in any form; localhost, localhost.localdomain and *.localhost in any case,
# with a trailing dot (the PaaS strict SSRF names, Pc/util/ssrf.py, and the Hermes MCP server guard's); 0.0.0.0, which
# also reaches this host, in its numeric spellings; IPv4-mapped forms.
LOOPBACK = ['http://127.0.0.1:8099', 'http://127.0.0.1:8081', 'https://127.0.0.1:3000', 'http://127.0.0.1:18000',
            'http://127.1.2.3', 'http://127.255.255.254:8069',
            'http://[::1]:8081', 'http://[0:0:0:0:0:0:0:1]:3000', 'http://[0000::0001]',
            'http://localhost:8099', 'http://LOCALHOST:3000', 'http://LocalHost.:8081', 'http://localhost.localdomain',
            'http://LOCALHOST.LOCALDOMAIN.:8099', 'http://api.localhost:3000', 'http://x.y.LOCALHOST.',
            'http://127.1:8099', 'http://127.0.1', 'http://0x7f.1', 'http://0X7F.0.0.1:3000', 'http://0x7f000001',
            'http://2130706433:8081', 'http://0177.0.0.1', 'http://017700000001:8099', 'http://127.000.000.001',
            'http://127.0.0.1.:8099', 'http://0x7f.1.',
            'http://0:8099', 'http://0x0:3000', 'http://00:8081', 'http://0.0:18000',
            'http://[::ffff:127.0.0.1]:8099', 'http://[::ffff:7f00:1]']
# The two IPv4-mapped spellings were refused before HM-20 already (a numeric host outside allowed_address).
REFUSED_BEFORE = {'http://[::ffff:127.0.0.1]:8099', 'http://[::ffff:7f00:1]'}
# A switched-on product still saves a LAN, a public or a named backend (HA backends are usually on the LAN; a name is
# checked at run time, once resolved), also in a numeric spelling.
STILL_SAVED = ['http://10.1.2.3:8069', 'http://172.16.0.5', 'http://192.168.1.20:5678', 'http://[fd12::1]:8080',
               'http://8.8.8.8', 'http://[2606:4700::1111]', 'http://backend.invalid', 'https://n8n.example.invalid',
               'http://127-0-0-1.invalid', 'http://localhost-backend.invalid', 'http://notlocalhost.invalid',
               'http://localhost.invalid', 'http://0x7f.invalid', 'http://127.0.0.1.invalid', 'http://0xa000001:8069',
               'http://3232235777']
# What the API test sends (the whole list goes through check_saved_destinations below).
API_LOOPBACK = ['http://127.0.0.1:8099', 'http://[::1]:8081', 'http://localhost:3000', 'http://0x7f.1',
                'http://2130706433:18000', 'http://0:8099']


def candidate(base, product, field, url):
    """The state a save of *url* in *field* validates (gateway.admin_action: the stored state plus the changes)."""
    if product == 'n8n':
        changes = {'backend_url': url, 'backend_key': SWITCHABLE['n8n']['key']}
    else:
        changes = {'connection': {**SWITCHABLE[product], field: url}}
    return type(base).model_validate({**base.model_dump(), **changes})


def saved(state, previous):
    try:
        check_saved_destinations(state, previous)
    except ValueError:
        return False
    return True


@pytest.fixture
def switch(monkeypatch):
    """switch(*products): exactly these products are switched on (features.enabled reads it at every call)."""
    def turn(*names):
        monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset(names))
    return turn


@pytest.mark.usefixtures('log_scan')  # HM-01: every new test runs under the log scan
@pytest.mark.parametrize('product', sorted(SWITCHABLE))
def test_a_loopback_url_is_refused_when_saved_once_the_product_is_switched_on(tmp_path, switch, product):
    with closing(ProductStore(tmp_path, product)) as store:
        base = store.load()
    assert set(SWITCHABLE) == features.KNOWN_PRODUCTS
    for field in URL_NAMES[product]:
        for url in LOOPBACK:
            state = candidate(base, product, field, url)
            before = product != 'n8n' and url in REFUSED_BEFORE  # n8n's URL had no check at all
            switch()
            assert saved(state, base) is not before, (field, url)  # switched off: the answer before HM-20
            switch(product)
            assert not saved(state, base), (field, url)
            with loopback_backends.allowed():  # the test double: as switched off
                assert saved(state, base) is not before, (field, url)
            assert not saved(state, base), (field, url)  # the double is off again after its block


@pytest.mark.usefixtures('log_scan')  # HM-01: every new test runs under the log scan
@pytest.mark.parametrize('product', sorted(SWITCHABLE))
def test_a_switched_on_product_still_saves_a_lan_public_or_named_backend(tmp_path, switch, product):
    with closing(ProductStore(tmp_path, product)) as store:
        base = store.load()
    switch(product)
    for field in URL_NAMES[product]:
        for url in STILL_SAVED:
            assert saved(candidate(base, product, field, url), base), (field, url)


@pytest.mark.usefixtures('log_scan')  # HM-01: every new test runs under the log scan
def test_n8n_gets_the_whole_check_once_switched_on(tmp_path, switch):
    """n8n's backend URL had no save check: once n8n is switched on, it is refused as every other product's is."""
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        base = store.load()
    for url in REFUSED:
        state = candidate(base, 'n8n', 'url', url)
        switch()
        assert saved(state, base), url
        switch('n8n')
        assert not saved(state, base), url


@pytest.mark.usefixtures('log_scan')  # HM-01: every new test runs under the log scan
def test_the_switch_is_per_product(tmp_path, switch):
    switch('odoo')
    for product in sorted(SWITCHABLE):
        with closing(ProductStore(tmp_path / product, product)) as store:
            base = store.load()
        state = candidate(base, product, URL_NAMES[product][0], 'http://127.0.0.1:8099')
        assert saved(state, base) is (product != 'odoo'), product


@pytest.mark.usefixtures('log_scan')  # HM-01: every new test runs under the log scan
def test_only_a_url_this_save_changes_is_checked(tmp_path, switch):
    """As before HM-20: a loopback URL stored before (or by an earlier version) still loads, and editing another field
    of the connection still works; the child refuses it when it connects (tests/test_backend_loopback.py)."""
    switch('odoo', 'n8n')
    for product in ('odoo', 'n8n'):
        with closing(ProductStore(tmp_path / product, product)) as store:
            base = store.load()
        stale = candidate(base, product, 'url', 'http://127.0.0.1:8069')
        if product == 'n8n':
            edited = type(stale).model_validate({**stale.model_dump(), 'backend_key': 'DUMMY-loopback-next-key'})
        else:
            edited = type(stale).model_validate({**stale.model_dump(), 'connection': {
                **stale.connection.model_dump(), 'password': 'DUMMY-loopback-next-password'}})
        assert saved(edited, stale)
        assert not saved(candidate(stale, product, 'url', 'http://localhost:8069'), stale)
        assert saved(candidate(stale, product, 'url', 'http://10.1.2.3:8069'), stale)


@pytest.fixture(params=sorted(SWITCHABLE))
async def switchable_admin(request, tmp_path, log_scan):
    product, applied = request.param, []

    async def verify(_):
        return True

    async def backend_changed(state):
        applied.append(state)

    def no_backend_request(_):
        raise AssertionError('saving a connection must not call the backend')

    with closing(ProductStore(tmp_path, product)) as store:
        if product == 'n8n':
            store.update(backend_url=SWITCHABLE['n8n']['url'], backend_key=SWITCHABLE['n8n']['key'])
        else:
            store.update(connection=SWITCHABLE[product])
        log_scan.watch_state(store.load())
        tools = n8n_adapter.TOOLS if product == 'n8n' else TOOLS[product]
        async with httpx.AsyncClient(transport=httpx.MockTransport(no_backend_request)) as child:
            admin, _ = make_apps(store, tools, child, verify_admin=verify, backend_changed=backend_changed)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)),
                                         base_url='http://admin') as client:
                yield product, client, store, applied


def backend_body(product, route, field, url, secrets=False):
    """A save of url in field. secrets: a partial edit also brings the stored secrets that URL takes to its server
    (HM-12, DQ-40 ⑨: once the product is switched on, a URL moved to another origin must bring them)."""
    if route == '/api/backend/patch':
        stored_values = SWITCHABLE[product]
        brought = {name: stored_values[name] for name in backend_edit.url_secrets(product)[field]
                   if name in stored_values} if secrets else {}
        return {'changes': {field: url, **brought}}
    if product == 'n8n':
        return {'url': url, 'key': SWITCHABLE['n8n']['key']}
    return {'connection': {**SWITCHABLE[product], field: url}}


@pytest.mark.parametrize('route', ['/api/backend', '/api/backend/patch'])
async def test_the_admin_api_refuses_a_loopback_url_once_switched_on(switchable_admin, switch, route):
    """400 with the body every refused save has (contract.md section 4.1, the fixed responses without a code: a format
    check that fails); nothing is written and no child is restarted."""
    product, client, store, applied = switchable_admin
    switch(product)
    raw = store.path.read_bytes()
    for field in URL_NAMES[product]:
        for url in API_LOOPBACK:
            response = await _put(client, route, backend_body(product, route, field, url))
            assert response.status_code == 400, (field, url, response.text)
            assert response.content == b'{"error":"request denied"}'
            # The state's bytes hold its tokens: compared first, so a failure never prints them (HM-20 review S-6).
            unchanged = store.path.read_bytes() == raw
            assert unchanged and not applied, (field, url)
        response = await _put(client, route, backend_body(product, route, field, 'http://10.1.2.3:8069', secrets=True))
        if product == 'n8n':
            assert response.status_code == 400 and store.path.read_bytes() == raw and not applied
            continue  # n8n strict mode rejects private addresses too
        assert response.status_code == 200, response.text  # the LAN stays allowed (its secrets brought: HM-12)
        assert len(applied) == 1
        applied.clear()
        raw = store.path.read_bytes()


@pytest.mark.parametrize('route', ['/api/backend', '/api/backend/patch'])
async def test_switched_off_or_with_the_double_a_loopback_url_is_saved_as_before(switchable_admin, switch, route, monkeypatch):
    product, client, store, applied = switchable_admin
    if product == 'n8n':
        import asyncio
        import socket
        async def resolve(host, port, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', port))]
        monkeypatch.setattr(asyncio.get_running_loop(), 'getaddrinfo', resolve)
    for on in (False, True):
        switch(product) if on else switch()
        # Each URL differs from the stored one (an unchanged URL is never checked): https:// the second time.
        for url in (API_LOOPBACK if not on else [u.replace('http://', 'https://') for u in API_LOOPBACK]):
            with loopback_backends.allowed() if on else nullcontext():
                # switched on, a URL moved to another origin brings its secrets (HM-12, DQ-40 ⑨)
                response = await _put(client, route, backend_body(product, route, URL_NAMES[product][0], url,
                                                                  secrets=on))
            if product == 'n8n':
                assert response.status_code == 400, (on, url, response.text)
                continue  # strict n8n policy is independent of the multi-profile switch
            assert response.status_code == 200, (on, url, response.text)
            stored = store.load()
            value = stored.backend_url if product == 'n8n' else getattr(stored.connection, URL_NAMES[product][0])
            assert value == url
    assert len(applied) == (0 if product == 'n8n' else 2 * len(API_LOOPBACK))


def _whatwg_hosts(hosts):
    """{host: the host n8n's Node child reads from http://<host>/ (WHATWG URL), or None when it refuses the URL}."""
    node = shutil.which('node')
    assert node, 'node is required (packaging/unit.sh installs it)'
    code = ('const out = {}; for (const h of JSON.parse(process.argv[1])) { try { out[h] = new URL("http://" + h + "/")'
            '.hostname; } catch { out[h] = null; } } console.log(JSON.stringify(out));')
    result = subprocess.run([node, '-e', code, json.dumps(hosts)], capture_output=True, text=True, timeout=30,
                            env={'PATH': os.environ['PATH']})
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout)


NUMERIC_HOSTS = ['127.0.0.1', '127.1', '127.0.1', '0x7f.1', '0X7F.0.0.1', '0x7f000001', '2130706433', '0177.0.0.1',
                 '017700000001', '127.000.000.001', '127.0.0.1.', '0x7f.1.', '0', '0x', '00', '0.0', '0x0', '08.0.0.1',
                 '1.2.3.4.5', '127.0.0.256', '4294967295', '4294967296', '0x100000000', '127.65535', '127.0.65535',
                 '127.0.0.1..', '1..1', '.1', '0x7f.0x0.0x0.0x1', '0xg', '1e2', '127.0.0.0x1', '0x0000007f.1',
                 '00000000177.1', '10.0.0.1', '192.168.001.001', '3232235777', '0xa000001', 'localhost',
                 'backend.invalid', '0x7f.invalid', '127.0.0.1.invalid', 'a.0x7f', '1.0x7f']


@pytest.mark.usefixtures('log_scan')  # HM-01: every new test runs under the log scan
def test_numeric_hosts_are_read_as_the_resolver_and_n8n_read_them():
    """products.numeric_host gives the address glibc's inet_aton (what getaddrinfo reads for a numeric host) or the
    WHATWG URL parser (n8n's Node child) gives, for every host either of them reads as an IPv4 address, and None for a
    host neither does: no spelling of a loopback address passes as a name."""
    from mcp_admin_core.products import numeric_host
    whatwg = _whatwg_hosts(NUMERIC_HOSTS)
    for host in NUMERIC_HOSTS:
        readings = set()
        try:
            readings.add(socket.inet_ntoa(socket.inet_aton(host)))
        except OSError:
            pass
        parsed = whatwg[host]
        if parsed is not None and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+', parsed):
            readings.add(parsed)
        assert len(readings) <= 1, (host, readings)
        ours = numeric_host(host)
        if readings:
            assert ours == ipaddress.ip_address(readings.pop()), host
        elif ours is not None:
            # Only an IP literal ipaddress itself reads (an IPv6 one has no dots to misread) may stand alone.
            assert ipaddress.ip_address(host) == ours, host
    assert numeric_host('::1') == ipaddress.ip_address('::1') and numeric_host('fd12::1') is not None


@pytest.mark.usefixtures('log_scan')  # HM-01: every new test runs under the log scan
def test_saved_and_run_time_checks_agree_once_switched_on(monkeypatch):
    """Switched on, for every URL whose host the resolver reads as a number: a URL accepted when saved also passes the
    run-time check of a child that got WOOW_MCP_DENY_LOOPBACK=1, and a URL that check refuses is refused when saved. A
    name is checked at run time only, once resolved (tests/test_backend_loopback.py)."""
    import importlib
    spec = importlib.util.spec_from_file_location('backend_policy_saved_deny', ROOT / 'apps/runtime/backend_policy.py')
    deny = importlib.util.module_from_spec(spec)
    monkeypatch.setenv('WOOW_MCP_DENY_LOOPBACK', '1')
    spec.loader.exec_module(deny)
    monkeypatch.delenv('WOOW_MCP_DENY_LOOPBACK')
    assert deny.DENY_LOOPBACK is True
    real = socket.getaddrinfo

    def numeric_only(host, port, *args, **kwargs):  # no lookup: a name fails here, as it is out of this test
        return real(host, port, 0, socket.SOCK_STREAM, socket.IPPROTO_TCP, socket.AI_NUMERICHOST)

    monkeypatch.setattr(socket, 'getaddrinfo', numeric_only)
    checked = 0
    for url in URL_CASES + LOOPBACK + STILL_SAVED:
        try:
            saved = saved_destination(http_url(url), loopback=True) is not None
        except ValueError:
            saved = False
        try:
            destination = deny.Destination(url)
            destination.check_url(httpx.URL(url.rstrip('/') + '/api/x'))
            # The address rule does not look at the port; 8069 keeps clear of the ports no test may resolve (HM-01).
            deny.connectable(deny.checked_answers(destination.host, 8069))
            runs = urlsplit(url).port != 0
        except socket.gaierror:
            continue
        except (deny.BackendDenied, ValueError, httpx.InvalidURL):
            runs = False
        checked += 1
        if saved:
            assert runs, url
        if not runs:
            assert not saved, url
    assert checked >= 40
