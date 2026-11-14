"""HM-04: the child's loopback port is a parameter; the default profile's child keeps 3000, byte for byte.

- The default port: every product's child spec (argv, environment with its order, working directory), as
  products.child_spec and n8n_adapter.child_spec build it, is bb48449's: tests/contract/child_spec_default.json, made
  by normalized() below from bb48449's code (the checkout path, the data directory, n8n's catalog copy and node binary
  and the child token are placeholders; every other value is the literal one). Asking for port 3000 gives the same
  spec. A deliberate change of a child's spec (HM-06 adds WOOW_MCP_CHILD_TOKEN to the Python children) updates that
  file in the same PR: the failure message shows the current normalized spec of the case.
- Another port (an extra profile's child; multi-profile plan 5.4: 18000 and up): the spec differs from the default
  one in the port only: the --port value; n8n's PORT; Hermes and OpenDesign get --port N appended (their launchers read
  it, and their default argv stays the former one). run_product.run and apps/n8n/run.py run with child_port=N give
  that one port to the child spec, the health monitor, the gateway and the capability probe: every request the child
  gets goes to http://127.0.0.1:N/mcp, and the clients get the same answers as on 3000 (the HM-01 golden session).
- The HM-01 port rule holds: no test here binds, connects to or resolves 3000 or 18000-18099 (owned_network refuses
  and counts any attempt in this process; the children get the same guard). The runtime test's child is
  MockTransport; the real children listen on private ports (owned_runtime replaces the production port and
  owned_child checks the port a launcher passes to run()).
"""
from contextlib import contextmanager
from dataclasses import replace
import inspect
import json
from pathlib import Path
import runpy
import shutil
import sys
import types

import pytest

import n8n_adapter
import owned_network
import owned_runtime
import run as n8n_run
from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import gateway, health, lifecycle, run_product
from mcp_admin_core.products import PRODUCTS, ProductStore, child_spec
from test_owned_ports_bearer import direct_session
from test_real_products import backend, connection
from test_single_profile_golden import (ACCEPT, ADMIN, NoProcessSupervisor, PRODUCTS as SHIPPED, configure, connect,
                                        production_runtime, settle)

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'tests/contract/child_spec_default.json'
DEFAULT = 3000
PORTS = (18000, 18042, 18099)  # an extra profile's child (owned_network.PROFILE_CHILD_PORTS)
ON_PORT_ARGUMENT = ('odoo', 'odoo-manage', 'emqx', 'litellm', 'nextcloud', 'headscale')  # argv '--port', N
LAUNCHERS = ('hermes', 'opendesign')  # no --port at 3000 (bb48449's argv); --port N appended otherwise

# Synthetic backends (tests/fixtures/owner_defaults/README.md rules: DUMMY- credentials, .invalid hosts).
ODOO = {'url': 'https://odoo.invalid', 'database': 'DUMMY-port-db', 'username': 'DUMMY-port-user',
        'password': 'DUMMY-port-odoo-password'}
MANAGE = {'url': 'https://odoo-manage.invalid', 'database': 'DUMMY-port-db', 'username': 'DUMMY-port-user',
          'api_key': 'DUMMY-port-manage-key'}
HERMES = {'gateway_url': 'https://hermes.invalid', 'gateway_api_key': 'DUMMY-port-hermes-key'}
EMQX = {'url': 'https://emqx.invalid', 'api_key': 'DUMMY-port-emqx-key', 'api_secret': 'DUMMY-port-emqx-secret'}
LITELLM = {'url': 'https://litellm.invalid', 'master_key': 'DUMMY-port-litellm-key'}
NEXTCLOUD = {'url': 'https://nextcloud.invalid', 'username': 'DUMMY-port-user',
             'app_password': 'DUMMY-port-nextcloud-password'}
# Each product's states: the plain configured one, and one through the optional branches of its child environment
# (Odoo's switches and allowed methods, Odoo Manage's module mode, Hermes's dashboard, the revoked writes and a disabled
# tool of the READONLY / DISABLED_TOOLS / ALLOW_DELETE children, n8n's backend, MCP access token, session and catalog).
CASES = {
    'odoo/plain': ('odoo', {'connection': ODOO}),
    'odoo/switches': ('odoo', {'connection': ODOO, 'odoo_write_switches': {
        'enable_writes': True, 'allow_direct_writes': False, 'allow_unknown_methods': False, 'chatter_direct': True},
        'odoo_allowed_methods': ['res.partner.message_subscribe', 'sale.order.action_confirm']}),
    'odoo-manage/read': ('odoo-manage', {'connection': MANAGE}),
    'odoo-manage/module': ('odoo-manage', {'connection': {**MANAGE, 'mode': 'module'}}),
    'hermes/gateway': ('hermes', {'connection': HERMES}),
    'hermes/dashboard': ('hermes', {'connection': {
        **HERMES, 'dashboard_url': 'https://hermes-dashboard.invalid', 'dashboard_username': 'DUMMY-port-user',
        'dashboard_password': 'DUMMY-port-dashboard-password'}}),
    'opendesign/plain': ('opendesign', {'connection': {'url': 'https://opendesign.invalid'}}),
    'emqx/plain': ('emqx', {'connection': EMQX}),
    'emqx/restricted': ('emqx', {'connection': EMQX, 'writes_enabled': False, 'enabled_write_tools': [],
                                 'disabled': ['emqx_broker_stats']}),
    'litellm/plain': ('litellm', {'connection': LITELLM}),
    'litellm/restricted': ('litellm', {'connection': LITELLM, 'writes_enabled': False, 'enabled_write_tools': [],
                                       'disabled': ['litellm_chat_completion']}),
    'nextcloud/plain': ('nextcloud', {'connection': NEXTCLOUD}),
    'nextcloud/restricted': ('nextcloud', {'connection': NEXTCLOUD, 'writes_enabled': False,
                                           'enabled_write_tools': [], 'disabled': ['list_tasks']}),
    'headscale/plain': ('headscale', {'connection': {'url': 'https://headscale.invalid',
                                                     'api_key': 'DUMMY-port-headscale-key'}}),
    'n8n/documentation': ('n8n', {}),  # no backend: n8n's child still runs (its documentation tools)
    'n8n/configured': ('n8n', {'backend_url': 'https://n8n.invalid', 'backend_key': 'DUMMY-port-workflow-key',
                               'mcp_access_token': 'DUMMY-port-workflow-access',
                               'n8n_session': {'timeout_seconds': 900, 'max_sessions': 5}}),
}


@pytest.fixture(autouse=True)
def production_ports_untouched():
    """owned_network counts every refused operation on 3000 or 18000-18099 in this process: none may happen here."""
    before = owned_network.forbidden_operations
    yield
    assert owned_network.forbidden_operations == before, 'a test operation tried a production child port'


@contextmanager
def case_state(case, base, log_scan=None):
    """(product, state, data directory, spec builder) of a case. n8n's catalog copy is the module's own global
    (prepare_catalog): set here, the configured case to a file of its own, the other to none."""
    product, changes = CASES[case]
    data, catalog = base / 'state', base / 'catalog/nodes.db'
    store = ProductStore(data, product)
    try:
        if changes:
            store.update(**changes)
        state = store.load()
    finally:
        store.close()
    if log_scan is not None:
        log_scan.watch_state(state)
    with pytest.MonkeyPatch.context() as patch:
        if product == 'n8n':
            if case == 'n8n/configured':
                catalog.parent.mkdir(mode=0o700)
                catalog.write_bytes(b'')
                patch.setattr(n8n_adapter, '_catalog', catalog)
            else:
                patch.setattr(n8n_adapter, '_catalog', None)
        yield product, state, Path(store.directory), (n8n_adapter.child_spec if product == 'n8n' else child_spec)


def normalized(spec, state, data, catalog):
    """A spec as the snapshot holds it: argv, env (NAME=value in its order) and cwd, with placeholders for the
    checkout, the data directory, n8n's catalog copy and node binary and the state's tokens."""
    if spec is None:
        return None
    node = shutil.which('node')

    def text(value):
        if node and value == node:
            return '{NODE}'
        for real, mark in ((state.child_token, '{child_token}'), (state.token, '{token}'), (str(catalog), '{CATALOG}'),
                           (str(data), '{DATA}'), (str(ROOT), '{ROOT}')):
            if real:
                value = value.replace(real, mark)
        return value

    return {'argv': [text(value) for value in spec.argv],
            'env': [f'{name}={text(value)}' for name, value in spec.env.items()],
            'cwd': text(str(spec.cwd))}


def on_port(spec, product, port):
    """The default spec as an extra profile's child on port gets it: the port is the only difference."""
    if product == 'n8n':
        assert spec.env['PORT'] == str(DEFAULT) and '--port' not in spec.argv
        return replace(spec, env={**spec.env, 'PORT': str(port)})  # the same key, so the same place
    if product in LAUNCHERS:
        assert '--port' not in spec.argv
        return replace(spec, argv=(*spec.argv, '--port', str(port)))
    assert product in ON_PORT_ARGUMENT and spec.argv.count('--port') == 1
    argv = list(spec.argv)
    index = argv.index('--port') + 1
    assert argv[index] == str(DEFAULT)
    argv[index] = str(port)
    return replace(spec, argv=tuple(argv))


def same(spec, expected):
    """Equal specs, the environment's order included (ChildSpec equality compares env as a dict)."""
    return spec == expected and list(spec.env.items()) == list(expected.env.items())


def test_the_snapshot_covers_every_product():
    snapshot = json.loads(SNAPSHOT.read_text())
    assert snapshot['baseline'] == 'bb48449'
    assert set(snapshot['specs']) == set(CASES)
    assert {product for product, _ in CASES.values()} == {*PRODUCTS, 'n8n'}


@pytest.mark.parametrize('case', CASES)
def test_the_default_child_spec_is_bb48449s(tmp_path, log_scan, case):
    expected = json.loads(SNAPSHOT.read_text())['specs'][case]
    with case_state(case, tmp_path, log_scan) as (product, state, data, build):
        current = normalized(build(state, data), state, data, tmp_path / 'catalog/nodes.db')
    assert current == expected, (
        f'{case}: the default profile child spec is not bb48449\'s; if the change is deliberate (reviewed), the '
        f'current one is {json.dumps(current, ensure_ascii=False)}')


@pytest.mark.parametrize('case', CASES)
def test_port_3000_is_the_default_spec(tmp_path, case):
    with case_state(case, tmp_path) as (product, state, data, build):
        default = build(state, data)
        assert same(build(state, data, port=DEFAULT), default)
        assert same(build(state, data, DEFAULT), default)


@pytest.mark.parametrize('port', PORTS)
@pytest.mark.parametrize('case', CASES)
def test_another_port_changes_the_port_only(tmp_path, case, port):
    with case_state(case, tmp_path) as (product, state, data, build):
        default = build(state, data)
        moved = build(state, data, port=port)
        assert same(moved, on_port(default, product, port))
        # The HM-01 doubles take it on that port, as an extra profile's test will run it.
        private = owned_runtime.Endpoint(product, production_port=port)
        try:
            prepared = private.prepare(moved)
            assert prepared.cwd == moved.cwd
            if product in LAUNCHERS:
                # owned_child is told the production port; it checks the one the launcher passes to run() (the real
                # children below).
                assert prepared.argv == (moved.argv[0], str(owned_runtime.HERE / 'owned_child.py'), product,
                                         str(private.port), f'--production-port={port}', *moved.argv[1:])
            else:
                with pytest.raises(AssertionError):
                    owned_runtime.private_spec(moved, product, private.port)  # it expects the spec on 3000
        finally:
            private.close()


@pytest.mark.parametrize('product', PRODUCTS)
def test_an_unconfigured_product_has_no_child_on_any_port(tmp_path, product):
    store = ProductStore(tmp_path / 'state', product)
    try:
        state = store.load()
    finally:
        store.close()
    assert child_spec(state, tmp_path / 'state') is None
    assert child_spec(state, tmp_path / 'state', port=18000) is None
    assert not (tmp_path / 'state/child').exists()


@pytest.mark.parametrize('port', [0, 65536, -1, True, False, None, '18000', 18000.0])
def test_a_port_that_is_no_tcp_port_is_refused(tmp_path, port):
    for case in ('odoo/plain', 'hermes/gateway', 'n8n/documentation'):
        with case_state(case, tmp_path / case.replace('/', '-')) as (product, state, data, build):
            with pytest.raises(ValueError, match='invalid child port'):
                build(state, data, port=port)
    store = ProductStore(tmp_path / 'unconfigured', 'odoo')
    try:
        with pytest.raises(ValueError, match='invalid child port'):  # also before the no-child answer
            child_spec(store.load(), tmp_path / 'unconfigured', port=port)
    finally:
        store.close()
    with pytest.raises(ValueError, match='invalid child port'):
        lifecycle.child_url(port)


def test_one_value_names_the_default_child():
    assert lifecycle.CHILD_PORT == DEFAULT
    assert lifecycle.CHILD_URL == lifecycle.child_url() == 'http://127.0.0.1:3000/mcp'
    assert [lifecycle.child_url(port) for port in (18000, 18099, 65535, 1)] == [
        'http://127.0.0.1:18000/mcp', 'http://127.0.0.1:18099/mcp', 'http://127.0.0.1:65535/mcp',
        'http://127.0.0.1:1/mcp']
    assert lifecycle.child_port_text(18000) == '18000'
    # Every default is that value (the runtimes pass it explicitly too: test_one_port_reaches_every_child_request).
    assert inspect.signature(gateway.make_apps).parameters['child_url'].default == lifecycle.CHILD_URL
    assert inspect.signature(health.HealthMonitor).parameters['child_url'].default == lifecycle.CHILD_URL
    for build in (child_spec, n8n_adapter.child_spec):
        assert inspect.signature(build).parameters['port'].default == lifecycle.CHILD_PORT
    for run in (run_product.run, n8n_run.run):
        parameter = inspect.signature(run).parameters['child_port']
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default == lifecycle.CHILD_PORT
    assert n8n_adapter.CHILD_URL == lifecycle.CHILD_URL


# ---- the Hermes and OpenDesign launchers (in this process, their SDK and server modules replaced) ----

class FakeServer:
    def __init__(self, calls):
        self.calls = calls

    def run(self, *args, **kwargs):
        assert not args
        self.calls.append(('run', kwargs))


class Closing:
    def __init__(self, calls, name):
        self.calls, self.name = calls, name

    def close(self):
        self.calls.append(('close', self.name))


def run_launcher(monkeypatch, product, argv):
    """apps/<product>/launch.py run as its child process runs it (__main__, sys.argv), with fake server modules:
    returns what it called, in order."""
    calls = []
    server = FakeServer(calls)
    session_idle = types.ModuleType('session_idle')
    session_idle.install = lambda: calls.append(('install',))
    modules = {'session_idle': session_idle}
    if product == 'hermes':
        modules['hermes_mcp_server'] = types.ModuleType('hermes_mcp_server')
        modules['hermes_mcp_server.server'] = types.SimpleNamespace(mcp=server)
    else:
        modules['opendesign_mcp_server'] = types.ModuleType('opendesign_mcp_server')
        modules['opendesign_mcp_server.od_mcp_server'] = types.SimpleNamespace(
            mcp=server, _get_client=lambda: Closing(calls, 'client'))
        modules['bounded_tools'] = types.SimpleNamespace(
            BoundedTools=lambda mcp, capacity: calls.append(('workers', capacity)) or Closing(calls, 'workers'))
        modules['tool_error_text'] = types.SimpleNamespace(keep_error_text=lambda mcp: calls.append(('errors',)))
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    launcher = ROOT / 'apps' / product / 'launch.py'
    monkeypatch.setattr(sys, 'argv', [str(launcher), *argv])
    try:
        runpy.run_path(str(launcher), run_name='__main__')
    except SystemExit as exit:
        calls.append(('exit', exit.code))
    return calls


def runs_on(calls, port):
    return ('run', {'transport': 'streamable-http', 'host': '127.0.0.1', 'port': port,
                    'streamable_http_path': '/mcp'}) in calls


@pytest.mark.parametrize('argv, port', [
    ([], 3000), (['--port', '3000'], 3000), (['--port', '18000'], 18000), (['--port=18099'], 18099),
    (['--port', '43210'], 43210),
    # Positional arguments are ignored, as the launchers always ignored their arguments (tests/test_resolver_regressions
    # and tests/test_stream_error_redaction run the actual launcher behind wrappers that leave theirs in sys.argv).
    (['read', 'gateway'], 3000), (['43210', '/elsewhere/apps/hermes/launch.py'], 3000),
    (['--port', '18000', 'read', 'gateway'], 18000)])
@pytest.mark.parametrize('product', LAUNCHERS)
def test_the_launcher_runs_on_its_port(monkeypatch, product, argv, port):
    calls = run_launcher(monkeypatch, product, argv)
    assert runs_on(calls, port), calls
    assert ('exit', 2) not in calls
    assert calls.index(('install',)) < [call[0] for call in calls].index('run')  # session_idle before run()
    if product == 'opendesign':
        assert calls[-2:] == [('close', 'workers'), ('close', 'client')]


@pytest.mark.parametrize('argv', [
    ['--port', '0'], ['--port', '65536'], ['--port', '-1'], ['--port', 'x'], ['--port'], ['--port='],
    ['--prot', '18000'], ['--p', '18000'], ['--port', '18000', '--host', '0.0.0.0'], ['-h'], ['--help']])
@pytest.mark.parametrize('product', LAUNCHERS)
def test_the_launcher_refuses_a_bad_port_or_option(monkeypatch, product, argv):
    """Refused before the session limit is installed and before anything serves: a mistyped option never falls back
    to 3000 (the default profile's port)."""
    calls = run_launcher(monkeypatch, product, argv)
    assert calls == [('exit', 2)], calls


# ---- real Hermes and OpenDesign children on a production port (always replaced by a private one) ----

@pytest.mark.parametrize('port', [DEFAULT, 18000])
@pytest.mark.parametrize('product', LAUNCHERS)
async def test_the_real_launcher_serves_the_port_its_spec_names(tmp_path, log_scan, product, port):
    """owned_child checks that the actual launcher passes this production port to run() before it moves the child to
    a private port; on 3000 the spec is bb48449's argv."""
    with backend(product) as (url, _calls, _offline):
        store = ProductStore(tmp_path / 'state', product)
        try:
            store.update(connection=connection(product, url))
            state = store.load()
        finally:
            store.close()
        log_scan.watch_state(state)
        spec = child_spec(state, Path(store.directory), port=port)
        assert ('--port' in spec.argv) is (port != DEFAULT)
        endpoint = owned_runtime.Endpoint(product, production_port=port)
        manager = endpoint.supervisor(spec)
        try:
            await manager.start()
            async with endpoint.client(timeout=15) as client:
                result = await direct_session(client, endpoint.url)
            assert result['serverInfo']
        finally:
            await manager.stop()
            endpoint.close()


# ---- the runtimes: one port for the spec, the health monitor, the gateway and the capability probe ----

@pytest.mark.parametrize('port', [None, 18000])
@pytest.mark.parametrize('product', SHIPPED)
async def test_one_port_reaches_every_child_request(tmp_path, log_scan, monkeypatch, product, port):
    """The production runtime (tests/test_single_profile_golden.py's harness: only the outside replaced), started
    as main() starts it (port None) or with child_port=18000."""
    module = n8n_run if product == 'n8n' else run_product
    if port is not None:
        original = module.run
        monkeypatch.setattr(module, 'run', lambda args: original(args, child_port=port))
    monkeypatch.setattr(n8n_adapter, '_catalog', None)  # the golden harness skips n8n's catalog copy
    data = tmp_path / 'data'
    configure(data, product)
    specs = []

    class Recording(NoProcessSupervisor):
        def _start_child(self):
            specs.append(self.spec)
            super()._start_child()

    async with production_runtime(product, data, supervisor=Recording) as runtime:
        await settle(runtime, 'configured')
        state = json.loads((data / 'state.json').read_text())  # the runtime holds the store's writer lock
        log_scan.watch(state['token'], state['child_token'])
        async with runtime.mcp() as client:
            relayed = await connect(runtime, client, '/mcp',
                                    {**ACCEPT, 'Authorization': 'Bearer ' + state['token']}, 'configured')
            assert relayed == [('POST', 'initialize'), ('POST', 'notifications/initialized'), ('POST', 'tools/list'),
                               ('POST', 'tools/call'), ('DELETE', None)]
        async with runtime.admin() as admin:
            assert (await admin.get('/api/capabilities', headers=ADMIN)).status_code == 200
        requests = list(runtime.child.requests)
    assert {str(request.url) for request in requests} == {f'http://127.0.0.1:{port or DEFAULT}/mcp'}
    clients = {json.loads(request.content)['params']['clientInfo']['name'] for request in requests
               if request.content and json.loads(request.content).get('method') == 'initialize'}
    assert clients == {'local-readiness', 'management-catalog', 'golden-client'}
    # The spec the Supervisor got: the default one, or exactly that one on the port.
    store = ProductStore(data, product)
    try:
        default = (n8n_adapter.child_spec if product == 'n8n' else child_spec)(store.load(), Path(store.directory))
    finally:
        store.close()
    assert len(specs) == 1
    assert same(specs[0], default if port is None else on_port(default, product, port))


@pytest.mark.parametrize('argv', [['--admin-port', '3000'], ['--mcp-port', '3000'],
                                  ['--admin-port', '8081', '--mcp-port', '8081']])
@pytest.mark.parametrize('module', [run_product, n8n_run], ids=['run_product', 'n8n'])
def test_the_listeners_still_refuse_the_default_child_port(monkeypatch, capsys, module, argv):
    prefix = ['emqx'] if module is run_product else []
    monkeypatch.setattr(sys, 'argv', ['runtime', *prefix, *argv])
    with pytest.raises(SystemExit) as exit:
        module.main()
    assert exit.value.code == 2
    assert capsys.readouterr().err.splitlines()[-1] == (
        'runtime: error: listeners must be distinct and cannot use child port 3000')


def test_the_default_child_port_is_outside_the_profile_child_ports():
    """The HM-01 sentinel's two parts: the default profile's child, and the extra profiles' children (HM-09 allocates
    from 18000); this slice's ports stay inside them."""
    assert owned_network.PRODUCTION_PORT == lifecycle.CHILD_PORT
    assert all(port in owned_network.PROFILE_CHILD_PORTS for port in PORTS)
    assert lifecycle.CHILD_PORT not in owned_network.PROFILE_CHILD_PORTS
