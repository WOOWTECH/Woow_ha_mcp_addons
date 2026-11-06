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


async def test_a_stale_url_does_not_block_editing_the_other_fields(product_admin):
    product, client, store, applied = product_admin
    if product not in UNRELATED:
        pytest.skip('the URL is its only field')
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
