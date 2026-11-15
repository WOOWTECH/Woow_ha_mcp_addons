"""HM-20: a switched-on product's child refuses a loopback backend when it connects (multi-profile plan 8.7, DQ-10).

The management process decides: products.loopback_refused(product) is features.enabled(product) and nothing else. For a
switched-on product, products.child_spec and n8n_adapter.child_spec add WOOW_MCP_DENY_LOOPBACK=1 to the environment
they build (never inherited); the child's policy reads it once, when it loads:

- apps/runtime/backend_policy.py (the seven Python children and the retired Odoo Manage): every connection to the
  configured backend (httpx sync and async, XML-RPC over HTTP and HTTPS) refuses an answer in 127.0.0.0/8 or ::1, for
  a numeric host and for every address a name resolves to, before the first connect; Headscale's own transport refused
  loopback before (http_policy.py) and still does.
- apps/n8n/backend_policy.cjs: the API client's pinned agents and the official MCP client's pinned fetch (the same
  configured origin, with the instance-level MCP access token) refuse 127.0.0.0/8, ::1 and 0.0.0.0, IPv4-mapped
  forms included; the webhook, chat and form clients keep WEBHOOK_SECURITY_MODE=permissive (owner decision
  2026-10-15, kept 2026-11-15 15:3x; reviewed again before n8n is switched on, HM-25).

Switched off, the variable is absent and every spec is the snapshot's (tests/contract/child_spec_default.json); any
value but 1 makes the child refuse to start. The test double tests/loopback_backends.py turns the rule off inside a
test's own process only. The save-time half: tests/test_saved_destinations.py.
"""
import ast
import asyncio
from contextlib import closing, contextmanager
import importlib.util
import itertools
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import textwrap
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import xmlrpc.client

import pytest

import loopback_backends
import n8n_adapter
from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import features, products
from mcp_admin_core.products import PRODUCTS, ProductState, ProductStore, child_spec
from test_child_port_param import CASES, SNAPSHOT, case_state, normalized
from test_real_products import connection
from test_upgrade_zero_rewrite import references, runtime_sources

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan
ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'apps/runtime/backend_policy.py'
ENV = 'WOOW_MCP_DENY_LOOPBACK'
DIST = ROOT / 'apps/n8n/node_modules/n8n-mcp/dist'
DENIED = 'BACKEND_DESTINATION_DENIED'
NODE_DENIED = 'configured backend network policy denied'  # backend_policy.cjs denied()
# Variables that look as if they could turn the refusal off; none does (only WOOW_MCP_DENY_LOOPBACK decides).
LOOKALIKES = {'WOOW_MCP_DENY_LOOPBACK_OFF': '1', 'WOOW_MCP_ALLOW_LOOPBACK': '1', 'WOOW_MCP_LOOPBACK_BACKENDS': '1',
              'LOOPBACK_BACKENDS': '1', 'PYTEST_CURRENT_TEST': 'x', 'NODE_ENV': 'test'}
_copies = itertools.count()


@pytest.fixture
def switch(monkeypatch):
    def turn(*names):
        monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset(names))
    return turn


# --- the variable -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize('case', CASES)
def test_a_switched_on_product_s_child_gets_the_variable_and_nothing_else_changes(tmp_path, log_scan, switch, case):
    """Switched on: the snapshot's spec (argv, cwd, every variable in its order) plus WOOW_MCP_DENY_LOOPBACK=1, once.
    Switched off, or with the test double: the snapshot's spec exactly."""
    expected = json.loads(SNAPSHOT.read_text())['specs'][case]
    catalog = tmp_path / 'catalog/nodes.db'
    with case_state(case, tmp_path, log_scan) as (product, state, data, build):
        switch()
        assert normalized(build(state, data), state, data, catalog) == expected
        switch(product)
        on = normalized(build(state, data), state, data, catalog)
        with loopback_backends.allowed():
            assert normalized(build(state, data), state, data, catalog) == expected
        assert normalized(build(state, data), state, data, catalog) == on
    assert on['argv'] == expected['argv'] and on['cwd'] == expected['cwd']
    assert [entry for entry in on['env'] if entry.startswith(ENV + '=')] == [ENV + '=1']
    assert [entry for entry in on['env'] if entry != ENV + '=1'] == expected['env']


def test_the_rule_is_the_product_switch_alone():
    """products.loopback_refused returns features.enabled(product) and reads nothing else (no environment, file or
    option); an unknown product stays an error."""
    tree = ast.parse((ROOT / 'packages/mcp-admin-core/mcp_admin_core/products.py').read_text())
    [function] = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'loopback_refused']
    body = [node for node in function.body if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))]
    assert ast.unparse(body[0]) == 'return features.enabled(product)' and len(body) == 1
    with pytest.raises(ValueError):
        products.loopback_refused('bogus')


def test_no_variable_of_the_management_process_turns_the_rule_off(tmp_path):
    """In a fresh interpreter that runs only production code (no test double) and whose environment carries lookalike
    variables, a switched-on product still refuses a loopback URL when saved and its child still gets the variable."""
    code = textwrap.dedent('''
        import json, sys
        from pathlib import Path
        from mcp_admin_core import features, products
        import n8n_adapter
        features.MULTI_PROFILE_PRODUCTS = frozenset({"odoo", "n8n"})
        base, out = Path(sys.argv[1]), {}
        for product in ("odoo", "n8n"):
            store = products.ProductStore(base / product, product)
            state = store.load()
            changes = ({"backend_url": "http://127.0.0.1:5678", "backend_key": "DUMMY-loopback-n8n-key"}
                       if product == "n8n" else {"connection": {"url": "http://127.0.0.1:8069", "database": "DUMMY-db",
                                                                "username": "DUMMY-user",
                                                                "password": "DUMMY-loopback-odoo-password"}})
            candidate = type(state).model_validate({**state.model_dump(), **changes})
            try:
                products.check_saved_destinations(candidate, state)
                out[product + "/saved"] = True
            except ValueError:
                out[product + "/saved"] = False
            build = n8n_adapter.child_spec if product == "n8n" else products.child_spec
            out[product + "/variable"] = build(candidate, store.directory).env.get("WOOW_MCP_DENY_LOOPBACK")
            store.close()
        print(json.dumps(out))
    ''')
    env = {'PATH': os.environ['PATH'], 'PYTHONDONTWRITEBYTECODE': '1', ENV: '0', 'MULTI_PROFILE_PRODUCTS': '',
           'WEBHOOK_SECURITY_MODE': 'permissive', **LOOKALIKES,
           'PYTHONPATH': str(ROOT / 'packages/mcp-admin-core') + ':' + str(ROOT / 'apps/n8n')}
    result = subprocess.run([str(ROOT / '.venv/bin/python'), '-c', code, str(tmp_path)], capture_output=True,
                            text=True, cwd=ROOT, timeout=120, env=env)
    assert result.returncode == 0, result.stderr[-2000:]
    assert json.loads(result.stdout.splitlines()[-1]) == {'odoo/saved': False, 'odoo/variable': '1',
                                                          'n8n/saved': False, 'n8n/variable': '1'}


# --- the Python policy (apps/runtime/backend_policy.py), in this process -----------------------------------------


def load_policy(value, **extra):
    """A fresh copy of the policy module, loaded with WOOW_MCP_DENY_LOOPBACK=value (None: unset) and *extra*."""
    spec = importlib.util.spec_from_file_location(f'backend_policy_hm20_{next(_copies)}', POLICY)
    module = importlib.util.module_from_spec(spec)
    with pytest.MonkeyPatch.context() as patch:
        patch.delenv(ENV, raising=False)
        if value is not None:
            patch.setenv(ENV, value)
        for name, text in extra.items():
            patch.setenv(name, text)
        spec.loader.exec_module(module)
    return module


DENY, ALLOW = load_policy('1'), load_policy(None)


def test_the_variable_is_read_once_when_the_policy_loads():
    assert DENY.DENY_LOOPBACK is True and ALLOW.DENY_LOOPBACK is False
    assert load_policy('1', **LOOKALIKES).DENY_LOOPBACK is True
    assert load_policy(None, **LOOKALIKES).DENY_LOOPBACK is False


@pytest.mark.parametrize('value', ['0', '', 'true', 'yes', ' 1', '1 ', '01', 'deny', 'ON'])
def test_any_other_value_refuses_to_start(value):
    with pytest.raises(RuntimeError) as refused:
        load_policy(value)
    assert str(refused.value) == 'backend policy: WOOW_MCP_DENY_LOOPBACK must be 1 when set'


@pytest.mark.parametrize('address', ['127.0.0.1', '127.1.2.3', '127.255.255.254', '::1'])
def test_a_loopback_answer_is_refused_only_with_the_variable(address):
    answers = ALLOW.checked_answers(address, 8069)  # numeric: no lookup
    assert ALLOW.connectable(answers) == answers
    with pytest.raises(DENY.BackendDenied):
        DENY.connectable(DENY.checked_answers(address, 8069))


@pytest.mark.parametrize('answers,refused', [
    (['10.0.0.2', '127.0.0.1'], True), (['127.0.0.1', '10.0.0.2'], True), (['fd12::1', '::1'], True),
    (['10.0.0.2', '192.168.1.5'], False), (['fd12::1'], False), (['8.8.8.8'], False)])
def test_every_answer_a_name_resolves_to_is_checked(monkeypatch, answers, refused):
    monkeypatch.setattr(socket, 'getaddrinfo', resolver({'rebind.invalid': answers}))
    checked = DENY.checked_answers('rebind.invalid', 8069)
    if refused:
        with pytest.raises(DENY.BackendDenied):
            DENY.connectable(checked)
    else:
        assert DENY.connectable(checked) == checked
    assert ALLOW.connectable(ALLOW.checked_answers('rebind.invalid', 8069))  # without the variable: as before


def resolver(names):
    """A getaddrinfo that answers *names* ({name: [address, ...]}) and reads a numeric host as the real one does,
    without any lookup."""
    real = socket.getaddrinfo

    def resolve(host, port, *args, **kwargs):
        host = host.decode() if isinstance(host, bytes) else host
        if host in names:
            rows = []
            for address in names[host]:
                family = socket.AF_INET6 if ':' in address else socket.AF_INET
                where = (address, int(port), 0, 0) if family == socket.AF_INET6 else (address, int(port))
                rows.append((family, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', where))
            return rows
        return real(host, port, 0, socket.SOCK_STREAM, socket.IPPROTO_TCP, socket.AI_NUMERICHOST)
    return resolve


@contextmanager
def fake_backend():
    """An HTTP and XML-RPC fake on 127.0.0.1 that records every request it gets."""
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, body, kind):
            self.send_response(200)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            calls.append(('GET', self.path))
            self.reply(b'{}', 'application/json')

        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            calls.append(('POST', self.path))
            self.reply(xmlrpc.client.dumps(({'server_version': '18.0'},), methodresponse=True).encode(), 'text/xml')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


async def one_request(policy, kind, url):
    """One backend request through *policy*'s transport of *kind*: None when it got an answer, else its error code."""
    try:
        if kind == 'httpx-sync':
            with policy.sync_client(base_url=url, timeout=5) as client:
                await asyncio.to_thread(client.get, '/api/x')
        elif kind == 'httpx-async':
            async with policy.async_client(base_url=url, timeout=5) as client:
                await client.get('/api/x')
        else:
            proxy = xmlrpc.client.ServerProxy(url + '/xmlrpc/2/common', transport=policy.XMLTransport(url, timeout=5))
            await asyncio.to_thread(proxy.version)
    except Exception as exc:
        return policy.error_code(exc)
    return None


@pytest.mark.parametrize('kind', ['httpx-sync', 'httpx-async', 'xmlrpc'])
@pytest.mark.parametrize('host', ['127.0.0.1', 'rebind.invalid'])
async def test_each_transport_refuses_a_loopback_backend_before_any_request(monkeypatch, kind, host):
    """With the variable: refused before the first connect (the fake gets nothing). Without it (as switched off, and
    as with the test double): the same request reaches the same fake."""
    with fake_backend() as (port, calls):
        monkeypatch.setattr(socket, 'getaddrinfo', resolver({'rebind.invalid': ['127.0.0.1']}))
        url = f'http://{host}:{port}'
        assert await one_request(DENY, kind, url) == DENIED
        assert calls == []
        assert await one_request(ALLOW, kind, url) is None
        assert len(calls) == 1


async def test_xml_rpc_over_https_refuses_a_loopback_backend_before_the_handshake(monkeypatch):
    with fake_backend() as (port, calls):
        assert await one_request(DENY, 'xmlrpc', f'https://127.0.0.1:{port}') == DENIED
        # Without the variable it connects (the plain HTTP fake fails the TLS handshake: not a policy refusal).
        assert await one_request(ALLOW, 'xmlrpc', f'https://127.0.0.1:{port}') not in (None, DENIED)
        assert calls == []


@pytest.mark.parametrize('kind', ['httpx-sync', 'httpx-async', 'xmlrpc'])
async def test_a_lan_backend_still_connects_with_the_variable(monkeypatch, kind):
    attempts = []

    def stop(self, address):
        attempts.append(tuple(address[:2]))
        raise OSError(111, 'intercepted before connect')

    monkeypatch.setattr(socket, 'getaddrinfo', resolver({'lan.invalid': ['10.0.0.2']}))
    monkeypatch.setattr(socket.socket, 'connect', stop)
    monkeypatch.setattr(socket.socket, 'connect_ex', stop)
    assert await one_request(DENY, kind, 'http://lan.invalid:8069') not in (None, DENIED)
    assert ('10.0.0.2', 8069) in attempts


# --- every product's child, with its own environment and its own client --------------------------------------------

PROGRAM = r'''
import asyncio, json, os, runpy, socket
attempts = []
answers = json.loads(os.environ['ANSWERS'])
real = socket.getaddrinfo
def resolve(host, port, *args, **kwargs):
    host = host.decode() if isinstance(host, bytes) else host
    try:  # a numeric host as the resolver reads it, no lookup
        return real(host, port, 0, socket.SOCK_STREAM, socket.IPPROTO_TCP, socket.AI_NUMERICHOST)
    except socket.gaierror:
        pass
    rows = []
    for ip in answers:
        family = socket.AF_INET6 if ':' in ip else socket.AF_INET
        where = (ip, int(port), 0, 0) if family == socket.AF_INET6 else (ip, int(port))
        rows.append((family, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', where))
    return rows
def stop(self, address):
    attempts.append([address[0], address[1]])
    raise OSError(111, 'intercepted before connect')
socket.getaddrinfo = resolve; socket.socket.connect = stop; socket.socket.connect_ex = stop
p = os.environ['PRODUCT']
async def main():
    outcome = ''
    try:
        if p in ('odoo', 'odoo-manage') and os.environ.get('POLICY_LAUNCH'):
            runpy.run_path(os.environ['POLICY_LAUNCH'], run_name='policy_test')
        if p == 'odoo':
            from odoo_mcp.odoo_client import get_odoo_client
            get_odoo_client()
        elif p == 'odoo-manage':
            from mcp_server_odoo.config import OdooConfig
            from mcp_server_odoo.odoo_connection import OdooConnection
            OdooConnection(OdooConfig.from_env()).connect()
        elif p == 'hermes':
            from hermes_mcp_server.server import hermes_inspect
            outcome = await hermes_inspect(target='capabilities')
            from mcp.types import CallToolResult
            if isinstance(outcome, CallToolResult):
                outcome = '\n'.join(item.text for item in outcome.content if item.type == 'text')
        elif p == 'opendesign':
            from opendesign_mcp_server.od_mcp_server import health
            health()
        elif p == 'emqx':
            from emqx_mcp_server.lifespan import make_client
            async with make_client() as c:
                await c.get('/nodes')
        elif p == 'nextcloud':
            from nextcloud_mcp_server.client import NextcloudClient
            from nextcloud_mcp_server.settings import load_settings
            nc = NextcloudClient(load_settings())
            try:
                await nc.probe()
            finally:
                await nc.aclose()
        elif p == 'headscale':
            from headscale_mcp_server.client import HeadscaleClient
            async with HeadscaleClient(os.environ['HEADSCALE_MCP_BASE_URL'], os.environ['HEADSCALE_MCP_API_KEY']) as c:
                await c.request('Health')
        else:
            from woow_litellm_mcp_server.lifespan import build_client
            async with build_client() as c:
                await c.get('/v1/models')
    except Exception as exc:
        outcome = str(exc)
    print(json.dumps({'outcome': str(outcome), 'attempts': attempts}))
asyncio.run(main())
'''
CHILD_CASES = {  # (switched on, URL host, what a name resolves to)
    'on-literal': (True, '127.0.0.1', []), 'on-dns': (True, 'rebind.invalid', ['127.0.0.1']),
    'on-lan': (True, 'lan.invalid', ['10.0.0.2']), 'off-dns': (False, 'rebind.invalid', ['127.0.0.1'])}


def run_child_client(tmp_path, product, url, answers):
    state = ProductState(product=product, token='T' * 43, child_token='C' * 43, connection=connection(product, url))
    spec = child_spec(state, tmp_path)
    launcher = str(Path(spec.argv[1]).with_name('launch.py')) if product in ('odoo', 'odoo-manage') else ''
    result = subprocess.run([spec.argv[0], '-c', PROGRAM], env={**spec.env, 'PRODUCT': product,
                            'ANSWERS': json.dumps(answers), 'POLICY_LAUNCH': launcher}, cwd=spec.cwd,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr[-3000:]
    return spec, json.loads(result.stdout.splitlines()[-1])


@pytest.mark.parametrize('product', PRODUCTS)
@pytest.mark.parametrize('case', CHILD_CASES)
def test_the_child_refuses_a_loopback_backend_when_it_connects(tmp_path, switch, product, case):
    on, host, answers = CHILD_CASES[case]
    switch(product) if on else switch()
    spec, result = run_child_client(tmp_path, product, f'http://{host}:8069', answers)
    assert (spec.env.get(ENV) == '1') is on
    denied = 'HEADSCALE_DESTINATION_DENIED' if product == 'headscale' else DENIED
    if case == 'on-lan':
        assert ['10.0.0.2', 8069] in result['attempts'], result  # the LAN stays reachable
        assert denied not in result['outcome'], result
    elif on or product == 'headscale':  # Headscale's own transport refused loopback before HM-20 and still does
        assert result['attempts'] == [], result
        assert denied in result['outcome'], result
    else:
        assert ['127.0.0.1', 8069] in result['attempts'], result  # switched off: connects as before
        assert DENIED not in result['outcome'], result


# --- n8n (apps/n8n/backend_policy.cjs) ----------------------------------------------------------------------------

IMPORT = (f"const {{N8nApiClient}} = require({str(DIST / 'services/n8n-api-client.js')!r});\n"
          f"const {{N8nOfficialMcpClient}} = require({str(DIST / 'services/n8n-official-mcp-client.js')!r});\n"
          f"const {{SSRFProtection}} = require({str(DIST / 'utils/ssrf-protection.js')!r});\n")
DNS = '''
const dns = require('node:dns');
const names = {'localhost': [{address: '127.0.0.1', family: 4}, {address: '::1', family: 6}],
               'rebind.invalid': [{address: '127.0.0.1', family: 4}], 'rebind6.invalid': [{address: '::1', family: 6}],
               'mixed.invalid': [{address: '10.0.0.2', family: 4}, {address: '127.0.0.1', family: 4}],
               'zero.invalid': [{address: '0.0.0.0', family: 4}], 'lan.invalid': [{address: '10.0.0.2', family: 4}]};
dns.promises.lookup = async (host) => {
    if (!names[host]) throw Object.assign(new Error('getaddrinfo ENOTFOUND ' + host), {code: 'ENOTFOUND'});
    return names[host];
};
'''
LOOPBACK_URLS = ['http://127.0.0.1:5678', 'http://127.1:5678', 'http://0x7f000001:5678', 'http://2130706433:5678',
                 'http://0177.0.0.1:5678', 'http://127.0.0.1.:5678', 'http://[::1]:5678', 'http://[0::1]:5678',
                 'http://localhost:5678', 'http://rebind.invalid:5678', 'http://rebind6.invalid:5678',
                 'http://mixed.invalid:5678']
LAN_URLS = ['http://10.1.2.3:5678', 'http://192.168.1.50:5678', 'http://[fd12::1]:5678', 'http://lan.invalid:5678']


def n8n_spec(tmp_path, url='http://n8n.invalid:5678'):
    with closing(ProductStore(tmp_path / 'n8n', 'n8n')) as store:
        store.update(backend_url=url, backend_key='DUMMY-loopback-n8n-key')
        return n8n_adapter.child_spec(store.load(), store.directory)


async def node(spec, code, **extra):
    process = await asyncio.create_subprocess_exec(*spec.argv[:-1], '-e', code, cwd=spec.cwd,
                                                   env={**spec.env, **extra}, stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.PIPE)
    out, err = await asyncio.wait_for(process.communicate(), 60)
    return process.returncode, out.decode(), err.decode()


async def pinned_agents(spec, urls, **extra):
    code = IMPORT + DNS + f'const urls = {json.dumps(urls)};' + '''
(async () => {
    const out = {};
    for (const url of urls) {
        process.env.N8N_API_URL = url;
        try {
            await new N8nApiClient({baseUrl: url, apiKey: 'DUMMY', maxRetries: 0, timeout: 1000}).getPinnedAgents();
            out[url] = true;
        } catch (error) { out[url] = error.message; }
    }
    console.log(JSON.stringify(out));
})();
'''
    status, out, err = await node(spec, code, **extra)
    assert status == 0, err[-3000:]
    return json.loads(out.splitlines()[-1])


async def test_n8n_refuses_a_loopback_backend_once_switched_on(tmp_path, switch):
    switch('n8n')
    spec = n8n_spec(tmp_path)
    assert spec.env[ENV] == '1' and spec.env['WEBHOOK_SECURITY_MODE'] == 'permissive'
    result = await pinned_agents(spec, LOOPBACK_URLS + LAN_URLS, **LOOKALIKES)
    assert {url: result[url] for url in LOOPBACK_URLS} == {url: NODE_DENIED for url in LOOPBACK_URLS}
    assert {url: result[url] for url in LAN_URLS} == {url: True for url in LAN_URLS}


async def test_n8n_switched_off_connects_to_loopback_as_before(tmp_path, switch):
    switch()
    spec = n8n_spec(tmp_path)
    assert ENV not in spec.env
    urls = ['http://127.0.0.1:5678', 'http://[::1]:5678', 'http://localhost:5678', 'http://rebind.invalid:5678']
    assert await pinned_agents(spec, urls) == {url: True for url in urls}


FAKE_N8N = '''
const http = require('node:http');
const seen = [];
const fake = http.createServer((request, response) => {
    seen.push(request.method + ' ' + request.url);
    request.resume();
    response.writeHead(404, {'Content-Type': 'application/json', 'Connection': 'close'});
    response.end('{}');
});
'''


@pytest.mark.parametrize('on', [True, False])
async def test_the_api_and_the_official_mcp_client_reach_a_loopback_n8n_only_when_switched_off(tmp_path, switch, on):
    """Both clients of the configured instance: the API (pinned agents) and the official MCP endpoint
    (<origin>/mcp-server/http with the instance-level MCP access token, pinned fetch)."""
    switch('n8n') if on else switch()
    spec = n8n_spec(tmp_path)
    code = IMPORT + FAKE_N8N + '''
fake.listen(0, '127.0.0.1', async () => {
    const origin = 'http://127.0.0.1:' + fake.address().port;
    process.env.N8N_API_URL = origin;
    const out = {};
    try { await new N8nApiClient({baseUrl: origin, apiKey: 'DUMMY', maxRetries: 0, timeout: 2000}).listWorkflows({limit: 1});
          out.api = 'answered'; } catch (error) { out.api = error.message; }
    const api = seen.length;
    const official = new N8nOfficialMcpClient({endpoint: origin + '/mcp-server/http', token: 'DUMMY'});
    try { await official.connect(); out.official = 'connected'; } catch (error) { out.official = error.message; }
    await official.close().catch(() => undefined);
    out.api_requests = api; out.official_requests = seen.length - api;
    console.log(JSON.stringify(out));
    fake.close();
});
'''
    status, out, err = await node(spec, code)
    assert status == 0, err[-3000:]
    result = json.loads(out.splitlines()[-1])
    if on:
        assert result['api_requests'] == 0 and result['official_requests'] == 0, result
        assert NODE_DENIED in result['api'] and result['official'] == NODE_DENIED, result
    else:
        assert result['api_requests'] >= 1 and result['official_requests'] >= 1, result


async def test_n8n_webhooks_stay_permissive_with_the_variable(tmp_path, switch):
    """WEBHOOK_SECURITY_MODE=permissive is kept (owner decision 2026-10-15, kept 2026-11-15; HM-25 reviews it before
    n8n is switched on): a loopback webhook URL is still valid and its pinned agents are still made. Only the
    configured instance's own clients refuse loopback."""
    switch('n8n')
    spec = n8n_spec(tmp_path)
    code = IMPORT + '''
(async () => {
    const out = {};
    out.webhook = (await SSRFProtection.validateWebhookUrl('http://127.0.0.1:5678/webhook/x')).valid;
    out.agents = typeof SSRFProtection.createPinnedAgents([{address: '127.0.0.1', family: 4}]).httpAgent;
    const fetches = {};
    for (const address of ['10.0.0.2', 'fd12::1', '127.0.0.1', '127.9.9.9', '::1', '0.0.0.0', '::',
                           '::ffff:127.0.0.1', '::ffff:0.0.0.0']) {
        try { await SSRFProtection.createPinnedFetch([{address, family: address.includes(':') ? 6 : 4}]).close();
              fetches[address] = true; } catch (error) { fetches[address] = error.message; }
    }
    out.fetches = fetches;
    console.log(JSON.stringify(out));
})();
'''
    status, out, err = await node(spec, code)
    assert status == 0, err[-3000:]
    result = json.loads(out.splitlines()[-1])
    assert result['webhook'] is True and result['agents'] == 'object'
    assert result['fetches'] == {'10.0.0.2': True, 'fd12::1': True, '127.0.0.1': NODE_DENIED, '127.9.9.9': NODE_DENIED,
                                 '::1': NODE_DENIED, '0.0.0.0': NODE_DENIED, '::': NODE_DENIED,
                                 '::ffff:127.0.0.1': NODE_DENIED, '::ffff:0.0.0.0': NODE_DENIED}


@pytest.mark.parametrize('value', [None, '1', '0', '', 'true', 'yes', ' 1', '1 ', '01', 'deny', 'ON'])
async def test_the_n8n_child_starts_only_without_the_variable_or_with_1(tmp_path, switch, value):
    switch()
    spec = n8n_spec(tmp_path)
    extra = {} if value is None else {ENV: value}
    status, out, err = await node(spec, 'console.log("STARTED");', **extra)
    if value in (None, '1'):
        assert status == 0 and out.strip() == 'STARTED', err[-2000:]
    else:
        assert status != 0 and 'STARTED' not in out
        assert 'backend loopback policy requires WOOW_MCP_DENY_LOOPBACK=1 or unset' in err


def test_only_the_official_mcp_client_makes_a_pinned_fetch():
    """backend_policy.cjs refuses a loopback answer in SSRFProtection.createPinnedFetch because its only caller is the
    official MCP client of the configured instance; a pinned n8n-mcp that calls it anywhere else (a webhook, say)
    needs review before its next release."""
    callers = {str(path.relative_to(DIST)) for path in DIST.rglob('*.js') if 'createPinnedFetch' in path.read_text()}
    assert callers == {'utils/ssrf-protection.js', 'services/n8n-official-mcp-client.js'}
    endpoint = (DIST / 'config/n8n-api.js').read_text()
    assert "return new URL(instanceUrl).origin + '/mcp-server/http';" in endpoint  # the configured origin


# --- the test double ---------------------------------------------------------------------------------------------


def test_the_double_is_test_code_no_image_carries():
    # No file of an image imports it (any import form, tests/test_upgrade_zero_rewrite.references), and no image copies
    # tests/.
    assert [str(path.relative_to(ROOT)) for path in runtime_sources() if references(path, 'loopback_backends')] == []
    sources = []
    for dockerfile in sorted((ROOT / 'apps').glob('*/Dockerfile')):
        for line in dockerfile.read_text().splitlines():
            words = line.split()
            if words[:1] == ['COPY'] and not any(word.startswith('--from') for word in words):
                sources += [(dockerfile.parent.name, word) for word in words[1:-1] if not word.startswith('--')]
    assert {app for app, _ in sources} == {path.parent.name for path in (ROOT / 'apps').glob('*/Dockerfile')}
    assert {'n8n', *PRODUCTS} - {'odoo-manage'} <= {app for app, _ in sources}
    assert [s for s in sources if s[1].rstrip('/') in ('.', 'tests') or s[1].startswith(('tests/', './tests'))] == []


def test_the_double_is_on_only_inside_its_block(tmp_path, switch):
    switch('odoo')
    assert products.loopback_refused('odoo') is True
    with loopback_backends.allowed():
        assert products.loopback_refused('odoo') is False
        with pytest.raises(ValueError):
            products.loopback_refused('bogus')
    assert products.loopback_refused('odoo') is True
    with pytest.raises(RuntimeError):
        with loopback_backends.allowed():
            raise RuntimeError('inside')
    assert products.loopback_refused('odoo') is True
    assert re.search(r'\bloopback_refused\b', (ROOT / 'apps/n8n/n8n_adapter.py').read_text())


def test_the_double_in_a_subprocess_preamble(tmp_path):
    """install(), for the preamble of a subprocess a test starts: on for that process; without it, the same process
    code refuses."""
    code = textwrap.dedent('''
        import json, sys
        from pathlib import Path
        from mcp_admin_core import features, products
        features.MULTI_PROFILE_PRODUCTS = frozenset({"odoo"})
        if sys.argv[2] == "double":
            import loopback_backends
            loopback_backends.install()
        store = products.ProductStore(Path(sys.argv[1]), "odoo")
        state = store.load()
        candidate = type(state).model_validate({**state.model_dump(), "connection": {
            "url": "http://127.0.0.1:8069", "database": "DUMMY-db", "username": "DUMMY-user",
            "password": "DUMMY-loopback-odoo-password"}})
        try:
            products.check_saved_destinations(candidate, state)
            saved = True
        except ValueError:
            saved = False
        variable = products.child_spec(candidate, store.directory).env.get("WOOW_MCP_DENY_LOOPBACK")
        store.close()
        print(json.dumps({"saved": saved, "variable": variable}))
    ''')
    for mode, expected in (('double', {'saved': True, 'variable': None}), ('plain', {'saved': False, 'variable': '1'})):
        result = subprocess.run([str(ROOT / '.venv/bin/python'), '-c', code, str(tmp_path / mode), mode],
                                capture_output=True, text=True, cwd=ROOT, timeout=120,
                                env={'PATH': os.environ['PATH'], 'PYTHONDONTWRITEBYTECODE': '1',
                                     'PYTHONPATH': str(ROOT / 'packages/mcp-admin-core') + ':' + str(ROOT / 'tests')})
        assert result.returncode == 0, result.stderr[-2000:]
        assert json.loads(result.stdout.splitlines()[-1]) == expected, mode


# --- end to end: the real management process and the real Odoo child ----------------------------------------------


def reply_text(response, ident):
    """The JSON-RPC message with *ident* of a gateway answer (JSON or an SSE stream), as text."""
    if response.headers.get('content-type', '').startswith('text/event-stream'):
        for line in response.text.splitlines():
            if line.startswith('data:'):
                message = json.loads(line[5:])
                if message.get('id') == ident:
                    return json.dumps(message)
        raise AssertionError('no reply in the stream')
    message = response.json()
    assert message.get('id') == ident
    return json.dumps(message)


def answered(text):
    """A tools/call result that is not an error (MCP leaves isError out or false)."""
    message = json.loads(text)
    return 'result' in message and not message['result'].get('isError')


@pytest.mark.parametrize('double', [False, True])
async def test_a_switched_on_odoo_refuses_its_loopback_fake_backend_end_to_end(tmp_path, double):
    """run_product with Odoo switched on in its preamble: the real Odoo child runs with WOOW_MCP_DENY_LOOPBACK=1 (its
    /proc environment; only that entry is looked at) and the loopback fake backend, which is up, never gets a request;
    the client's tools/call is refused ("Backend unreachable" once the health check has run: Odoo's private probe tells
    only BACKEND_UNAVAILABLE, apps/odoo/launch.py probe_failure; the tool's own error before that). With the test double
    in the same preamble the child has no such variable and the same call reaches the same fake, as switched off
    (tests/test_real_products.py)."""
    import httpx
    from owned_executable import Executable
    from test_real_products import PROBES, backend, free_port, rpc
    with backend('odoo') as (url, calls, offline):
        store = ProductStore(tmp_path / 'state', 'odoo')
        store.update(connection=connection('odoo', url), writes_enabled=False, enabled_write_tools=[])
        state = store.load()
        store.close()
        port, admin_port = free_port(), free_port()
        endpoint = f'http://127.0.0.1:{port}/mcp'
        log_path = tmp_path / 'owned-runtime.log'
        runner = Executable(tmp_path, 'odoo', [port, admin_port])
        preamble = 'from mcp_admin_core import features; features.MULTI_PROFILE_PRODUCTS = frozenset({"odoo"}); '
        if double:
            preamble += 'import loopback_backends; loopback_backends.install(); '
        code = preamble + 'from mcp_admin_core import run_product; ' + runner.code('run_product') + 'run_product.main()'
        runner.release()
        with log_path.open('wb') as log:
            process = subprocess.Popen([str(ROOT / '.venv/bin/python'), '-c', code, 'odoo', '--data', str(tmp_path / 'state'),
                                        '--host', '127.0.0.1', '--mcp-port', str(port), '--admin-port', str(admin_port)],
                                       cwd=ROOT, env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1',
                                                      'PYTHONPATH': str(ROOT / 'packages/mcp-admin-core')},
                                       stdout=log, stderr=log)
            try:
                await runner.ready(process)
                async with httpx.AsyncClient(trust_env=False, timeout=15, event_hooks={'request': [runner.guard]}) as client:
                    headers = {'Authorization': 'Bearer ' + state.token, 'Accept': 'application/json, text/event-stream'}
                    init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                        'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'local-test', 'version': '0'}}}
                    async with asyncio.timeout(30):
                        while True:
                            assert process.poll() is None, log_path.read_text()
                            try:
                                result = await rpc(client, endpoint, headers, init)
                                break
                            except (httpx.HTTPError, ValueError):
                                await asyncio.sleep(.25)
                    headers['MCP-Protocol-Version'] = result['protocolVersion']
                    await rpc(client, endpoint, headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                    name, arguments = PROBES['odoo']
                    answers = []
                    async with asyncio.timeout(40):
                        while True:  # until the child's backend answers, or the call is refused once the child is up
                            response = await client.post(endpoint, headers=headers, json={
                                'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                                'params': {'name': name, 'arguments': arguments}})
                            answers.append(reply_text(response, 3))
                            if answered(answers[-1]) or (not double and 'MCP_SERVER_NOT_READY' not in answers[-1]
                                                         and ('Backend unreachable' in answers[-1]
                                                              or '"isError": true' in answers[-1])):
                                break
                            await asyncio.sleep(.5)
                    # The child answered (refused calls come only once it is up), so it runs its own program now.
                    [child] = Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()
                    environment = Path(f'/proc/{child}/environ').read_bytes().split(b'\0')
                    assert (b'WOOW_MCP_DENY_LOOPBACK=1' in environment) is (not double), 'the child variable is wrong'
                    del environment  # it holds the child's credentials: never printed
                    if double:
                        assert answered(answers[-1]) and calls, (answers, calls)
                    else:
                        assert not answered(answers[-1]), answers
                        assert DENIED in answers[-1] or 'Backend unreachable' in answers[-1], answers
                        await asyncio.sleep(2)
                        assert calls == [], calls  # nothing ever reached the fake, which was up all along
                    await client.delete(endpoint, headers=headers)
            finally:
                process.send_signal(signal.SIGTERM)
                try:
                    await asyncio.to_thread(process.wait, 10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    await asyncio.to_thread(process.wait)
        assert process.returncode == 0, log_path.read_text()
