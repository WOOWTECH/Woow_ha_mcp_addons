"""HM-20: a switched-on product's child refuses a loopback backend when it connects (multi-profile plan 8.7, DQ-10).

The management process decides: products.loopback_refused(product) is features.enabled(product) and nothing else. For a
switched-on product, products.child_spec and n8n_adapter.child_spec add WOOW_MCP_DENY_LOOPBACK=1 to the environment
they build (never inherited), on every port: the default profile's child (3000) and each additional profile's (18000
and up). No child code between that environment and the policy names the variable or removes it, nor does HM-09's exec
wrapper, which starts an additional profile's child (both checked by source; end to end, run_product's ProfileManager
starts real Odoo children for the default profile and an additional one); the child's policy reads it once, when it
loads:

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

A child's environment holds this test's tokens and keys: an assertion compares first and drops the spec or the
environment before it asserts, so that a failure never prints one (HM-20 review S-6).
"""
import ast
import asyncio
from contextlib import closing, contextmanager, nullcontext
import importlib.util
import itertools
import json
import os
from pathlib import Path
import re
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
from test_child_port_param import CASES, PORTS, SNAPSHOT, case_state, normalized
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


@pytest.mark.parametrize('port', PORTS)
@pytest.mark.parametrize('case', CASES)
def test_an_additional_profile_s_child_gets_the_variable_too(tmp_path, log_scan, switch, case, port):
    """An additional profile's child (18000 and up: the multi-profile plan 5.4) is the one the rule protects most: on
    its port, switched on, the spec is the switched-off one plus WOOW_MCP_DENY_LOOPBACK=1 (argv, cwd and every other
    variable in its order the same); switched off, or with the test double, it has no such variable (HM-20 review
    MF-1). The specs hold this test's tokens and keys: compared first, dropped before any assertion."""
    with case_state(case, tmp_path, log_scan) as (product, state, data, build):
        switch()
        off = build(state, data, port=port)
        switch(product)
        on = build(state, data, port=port)
        with loopback_backends.allowed():
            double = build(state, data, port=port)
    built = all(spec is not None for spec in (off, on, double))
    off_has = built and ENV in off.env
    value = on.env.get(ENV) if built else None
    rest = built and [item for item in on.env.items() if item[0] != ENV] == list(off.env.items())
    same = built and (on.argv, on.cwd) == (off.argv, off.cwd)
    as_off = built and (list(double.env.items()), double.argv, double.cwd) == (list(off.env.items()), off.argv, off.cwd)
    del off, on, double
    assert built, 'every case has a child'
    assert not off_has, 'switched off: the child must not get the variable'
    assert value == '1', value
    assert rest and same, 'switched on: everything but the variable must be the switched-off spec'
    assert as_off, 'with the test double: the switched-off spec'


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


# Between the environment child_spec builds and the policy that reads it runs only code of apps/: the launchers
# (run_child.py, session_idle.py, each app's launch.py and Odoo's start_switches.py) and the vendored servers. Only
# the end-to-end test below starts a real entry point (Odoo's), so the others are pinned by their source.
NAMES_THE_VARIABLE = {'apps/runtime/backend_policy.py', 'apps/n8n/backend_policy.cjs',  # the two policies read it
                      'apps/n8n/n8n_adapter.py'}  # the management process's n8n spec sets it
REMOVES = {'pop', 'popitem', 'clear'}  # os.environ's methods that take a variable away
OTHER_ENVIRONMENT = {'execve', 'execle', 'execlpe', 'execvpe', 'spawnve', 'spawnle', 'spawnlpe', 'spawnvpe',
                     'posix_spawn', 'posix_spawnp'}  # start a program with an environment of their own
STARTS = {'Popen', 'run', 'call', 'check_call', 'check_output', 'create_subprocess_exec', 'create_subprocess_shell'}


def child_sources():
    """The program files under apps/, its dependencies (node_modules, .venv) and tests aside."""
    for directory, names, files in os.walk(ROOT / 'apps'):
        names[:] = sorted(name for name in names if name not in ('node_modules', '.venv', '__pycache__', 'tests'))
        for name in sorted(files):
            if name.endswith(('.py', '.cjs', '.js', '.mjs')):
                yield Path(directory) / name


def environment_changes(tree):
    """The lines where a Python module takes a variable out of its own environment, empties or replaces it, or starts
    another program with an environment of its own."""
    def environ(node):
        return (isinstance(node, ast.Attribute) and node.attr == 'environ') or (isinstance(node, ast.Name)
                                                                                and node.id == 'environ')
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, 'attr', getattr(node.func, 'id', None))
            if ((name in REMOVES and environ(getattr(node.func, 'value', None))) or name == 'unsetenv'
                    or name in OTHER_ENVIRONMENT or (name in STARTS and any(k.arg == 'env' for k in node.keywords))):
                lines.append(node.lineno)
        elif isinstance(node, ast.Delete):
            lines += [node.lineno for target in node.targets
                      if isinstance(target, ast.Subscript) and environ(target.value)]
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            lines += [node.lineno for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
                      if environ(target)]
    return lines


def test_no_child_code_names_or_removes_the_variable():
    """HM-20 review S-3: no file of apps/ but the two policies and the n8n spec names WOOW_MCP_DENY_LOOPBACK (nor the
    Python policy's DENY_LOOPBACK, which a launcher could reset), and none takes a variable out of its own environment,
    empties or replaces it, or starts another program with an environment of its own (a launcher that did would turn
    the rule off for every product it starts: EMQX, LiteLLM and Nextcloud through run_child.py, Hermes, OpenDesign and
    Headscale through their launch.py). A new finding needs review, and then a reason here."""
    sources = list(child_sources())
    assert {'apps/runtime/run_child.py', 'apps/runtime/session_idle.py', 'apps/hermes/launch.py',
            'apps/odoo/start_switches.py', 'apps/runtime/backend_policy.py',
            'apps/n8n/backend_policy.cjs'} <= {str(path.relative_to(ROOT)) for path in sources}
    findings = []
    for path in sources:
        relative, text = str(path.relative_to(ROOT)), path.read_text(errors='replace')
        if 'DENY_LOOPBACK' in text and relative not in NAMES_THE_VARIABLE:
            findings.append((relative, 'names the variable'))
        if path.suffix == '.py':
            findings += [(relative, line) for line in environment_changes(ast.parse(text, relative))]
        elif re.search(r'process\.env\s*=(?!=)|delete\s+process\.env|deleteProperty\(\s*process\.env', text):
            findings.append((relative, 'removes from its environment'))
    assert findings == []


def test_the_exec_wrapper_hands_the_variable_on():
    """HM-09's exec wrapper (lifecycle.EXEC_WRAPPER, packages/mcp-admin-core: not under apps/, so not seen above) runs
    between the fork and an additional profile's real command. It takes only LC_CTYPE out of its environment (what its
    own interpreter's start added, PEP 538; set back to the spec's value when the spec has one), never names the
    variable, and execs with os.execv, which hands the real command that environment. The static half of
    test_every_profile_s_real_child_refuses_its_loopback_fake_backend_end_to_end (the rebase onto HM-09)."""
    from mcp_admin_core import lifecycle
    tree = ast.parse(lifecycle.EXEC_WRAPPER)
    removals = [node for node in ast.walk(tree)
                if isinstance(node, ast.Call) and getattr(node.func, 'attr', None) in REMOVES]
    execs = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call)
             and getattr(node.func, 'attr', '').startswith(('exec', 'spawn', 'posix_spawn'))]
    assert 'DENY_LOOPBACK' not in lifecycle.EXEC_WRAPPER
    assert [ast.literal_eval(node.args[0]) for node in removals] == ['LC_CTYPE']
    assert environment_changes(tree) == [node.lineno for node in removals]
    assert execs == ['execv']


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
    variable = spec.env.get(ENV)
    del spec  # its environment holds this test's tokens and keys: never in a failing assertion
    assert (variable == '1') is on, variable
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
    variables = spec.env.get(ENV), spec.env.get('WEBHOOK_SECURITY_MODE')  # never spec.env itself in an assertion
    assert variables == ('1', 'permissive'), variables
    result = await pinned_agents(spec, LOOPBACK_URLS + LAN_URLS, **LOOKALIKES)
    assert {url: result[url] for url in LOOPBACK_URLS} == {url: NODE_DENIED for url in LOOPBACK_URLS}
    assert {url: result[url] for url in LAN_URLS} == {url: True for url in LAN_URLS}


async def test_n8n_switched_off_connects_to_loopback_as_before(tmp_path, switch):
    switch()
    spec = n8n_spec(tmp_path)
    variable = spec.env.get(ENV)  # never spec.env itself in an assertion
    assert variable is None, variable
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


async def test_the_official_mcp_pinned_fetch_refuses_a_mixed_answer(tmp_path, switch):
    """A name the official MCP client resolves to a LAN address and a loopback one, in either order, is refused as a
    whole, as the API client's answers are (HM-20 review S-2); all LAN answers still pass."""
    switch('n8n')
    spec = n8n_spec(tmp_path)
    code = IMPORT + '''
(async () => {
    const out = {};
    for (const set of [[['10.0.0.2', 4], ['127.0.0.1', 4]], [['127.0.0.1', 4], ['10.0.0.2', 4]],
                       [['fd12::1', 6], ['::1', 6]], [['10.0.0.2', 4], ['fd12::1', 6]]]) {
        const key = set.map(([address]) => address).join(',');
        try { await SSRFProtection.createPinnedFetch(set.map(([address, family]) => ({address, family}))).close();
              out[key] = true; } catch (error) { out[key] = error.message; }
    }
    console.log(JSON.stringify(out));
})();
'''
    status, out, err = await node(spec, code)
    assert status == 0, err[-3000:]
    assert json.loads(out.splitlines()[-1]) == {'10.0.0.2,127.0.0.1': NODE_DENIED, '127.0.0.1,10.0.0.2': NODE_DENIED,
                                                 'fd12::1,::1': NODE_DENIED, '10.0.0.2,fd12::1': True}


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


# --- end to end: run_product's ProfileManager, real children, the default profile and an additional one ---------


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


def running_its_program(supervisor):
    """Whether the child of *supervisor* runs its spec's own program now: an additional profile's child is spawned
    through HM-09's exec wrapper (lifecycle.EXEC_WRAPPER, a fresh interpreter between the fork and the real command),
    whose /proc entry shows the wrapper until it execs."""
    from lifecycle_runtime import proc_cmdline
    process, spec = supervisor.process, supervisor.spec
    if process is None or spec is None:
        return False
    try:
        return proc_cmdline(process.pid) == list(spec.argv)
    except OSError:
        return False


def environment_facts(supervisor):
    """(WOOW_MCP_DENY_LOOPBACK in the /proc environment of the child of *supervisor*, or None; whether that
    environment is exactly the one its spec was spawned with: the spec's own, plus what this test process's spawn
    guard adds to every child, tests/owned_network.guarded_env). The environment holds the child's credentials and
    this test's tokens: only these two facts leave this function (HM-20 review S-6)."""
    from owned_network import guarded_env
    entries = Path(f'/proc/{supervisor.process.pid}/environ').read_bytes().split(b'\0')
    environment = dict(entry.split(b'=', 1) for entry in entries if entry)
    expected = {name.encode(): value.encode() for name, value in guarded_env(supervisor.spec.env).items()}
    facts = environment.get(ENV.encode()), environment == expected
    del entries, environment, expected
    return facts


async def probe_reply(client, token, double):
    """The tools/call of Odoo's probe tool (list_models) through 8081 with *token*, once the gateway forwards or
    refuses it (not the not-ready answer of a child that has not answered its health check yet), as text."""
    from test_real_products import PROBES, rpc
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json, text/event-stream'}
    result = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
        'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'local-test', 'version': '0'}}})
    headers['MCP-Protocol-Version'] = result['protocolVersion']
    await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    name, arguments = PROBES['odoo']
    call = {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}}
    try:
        async with asyncio.timeout(30):
            while True:
                text = reply_text(await client.post('/mcp', headers=headers, json=call), 3)
                if answered(text) or (not double and 'MCP_SERVER_NOT_READY' not in text):
                    return text
                await asyncio.sleep(.25)
    finally:
        await client.delete('/mcp', headers=headers)


@pytest.mark.parametrize('double', [False, True])
async def test_every_profile_s_real_child_refuses_its_loopback_fake_backend_end_to_end(tmp_path, log_scan,
                                                                                       monkeypatch, double):
    """HM-20 after HM-08 and HM-09: run_product.run with Odoo switched on builds the ProfileManager
    (tests/multi_profile_runtime.py, here with the real Supervisor and real clients), which starts the default
    profile's real Odoo child directly and an additional profile's through HM-09's exec wrapper
    (lifecycle.EXEC_WRAPPER: a fresh interpreter between the fork and the real command writes the child's resources
    and execs it with the environment it was given). Each child runs its own program with WOOW_MCP_DENY_LOOPBACK=1:
    its /proc environment is exactly the one its spec was spawned with (only that, and the variable's value, is looked
    at). Each profile has its own loopback fake backend, up all along: neither ever gets a request, and each profile's
    tools/call through 8081 is refused. With the test double around the same run, neither child has the variable and
    the same calls reach the same fakes, as switched off (HM-20 rebase: the wrapper passes the variable through)."""
    from lifecycle_runtime import until
    from mcp_admin_core import health as health_module, lifecycle
    from multi_profile_runtime import all_tokens, create_profile, free_port, multi_profile_runtime, update_profile
    from test_real_products import backend
    monkeypatch.setattr(health_module, 'HEALTH_INTERVAL', 0.5)  # every profile's first health check within a second
    extra, label = 'b' * 24, 'Loopback fake B'
    data = tmp_path / 'data'
    with backend('odoo', bind_host='127.0.0.1') as (default_url, default_calls, _), \
            backend('odoo', bind_host='127.0.0.1') as (extra_url, extra_calls, _):
        store = ProductStore(data, 'odoo')
        store.update(connection=connection('odoo', default_url), writes_enabled=False, enabled_write_tools=[])
        store.close()
        create_profile(data, 'odoo', extra, label=label, port=free_port(), configured=False)
        update_profile(data, 'odoo', extra, connection=connection('odoo', extra_url))
        log_scan.watch(*all_tokens(data))
        log_scan.watch(label, kind='name')
        with loopback_backends.allowed() if double else nullcontext():
            async with multi_profile_runtime('odoo', data, supervisor=lifecycle.Supervisor, real_children=True,
                                             default_port=free_port()) as runtime:
                supervisors = {profile_id: runtime.manager.get(profile_id).runtime.supervisor
                               for profile_id in ('default', extra)}
                healths = [runtime.manager.get(profile_id).runtime.health for profile_id in supervisors]
                await until(lambda: all(map(running_its_program, supervisors.values()))
                            and all(health.availability()['ready'] for health in healths), timeout=60)
                wrapped = {profile_id: supervisor.resources is not None
                           for profile_id, supervisor in supervisors.items()}
                facts = {profile_id: environment_facts(supervisor) for profile_id, supervisor in supervisors.items()}
                replies = {}
                async with runtime.mcp() as client:
                    for profile_id in supervisors:
                        replies[profile_id] = await probe_reply(client, runtime.token(profile_id), double)
                if not double:
                    await asyncio.sleep(2)  # a request that was on its way would have arrived by now
                calls = {'default': list(default_calls), extra: list(extra_calls)}
    assert wrapped == {'default': False, extra: True}, 'only the additional profile goes through the wrapper'
    variable = None if double else b'1'
    assert facts == {'default': (variable, True), extra: (variable, True)}, 'the child environment is wrong'
    for profile_id, text in replies.items():
        if double:
            assert answered(text) and calls[profile_id], (profile_id, text, calls[profile_id])
        else:
            assert not answered(text), (profile_id, text)
            assert DENIED in text or 'Backend unreachable' in text, (profile_id, text)
            assert calls[profile_id] == [], (profile_id, calls[profile_id])  # never reached the fake
