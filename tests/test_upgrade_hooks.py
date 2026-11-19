"""The Store upgrade comparison hooks (multi-profile HM-16; plan 12.3 HM-16; FM-102, FM-135; review C4-SF-14): the drafts
packaging/hooks/seed and verify, which HM-19a moves into addons/odoo/upgrade-check/ with the Odoo 0.5.0 release PR.

Both run here as the Store runs them (python3, the standard library, the add-on's /data and its 8081), against a mock
add-on on loopback: they only read the add-on's data (every entry's bytes, owner, mode, size, mtime and ctime are
unchanged), they assert nothing that depends on a version, and verify fails for each thing an upgrade must not do.
Then against the real runtime (HM-16 review SF-6): run_product through the owned executable, the old version not
switched on and the new one switched on (the 0.5.0 upgrade's shape) or neither, so what the hooks assume of today's
gateway is tested, not only of the mock. Every token is made when a test runs; none appears in a report, the hook
state or the output (the HM-01 log scan).
"""
import ast
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import signal
import stat
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from batch2_owned_port import reserve_port
from log_scan import log_scan  # noqa: F401  (fixture)
from owned_executable import Executable
import product_switch

pytestmark = pytest.mark.usefixtures('log_scan')
ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / 'packaging/hooks'


def load(name):
    """A hook as a module (the files have no .py suffix, as the Store wants them)."""
    loader = importlib.machinery.SourceFileLoader('hook_' + name, str(HOOKS / name))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


seed, verify = load('seed'), load('verify')


class AddOn(ThreadingHTTPServer):
    """8081 of the add-on as the hooks see it: its token on Bearer /mcp and on /private_<token>/mcp opens a session
    (DELETE ends it); any other token is refused (Bearer 401, secret URL 404). faults break one rule each."""

    def __init__(self, token):
        super().__init__(('127.0.0.1', 0), AddOnHandler)
        self.token, self.faults, self.sessions = token, set(), set()
        threading.Thread(target=self.serve_forever, args=(.05,), daemon=True).start()  # a quick shutdown

    @property
    def port(self):
        return self.server_address[1]


class AddOnHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def answer(self, status, headers=()):
        body = b'{}' if status == 200 else b''
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def served(self):
        faults, token = self.server.faults, self.server.token
        if self.path == '/mcp':
            value = self.headers.get('Authorization', '')
            given = value[7:] if value.startswith('Bearer ') else None
            return given is not None and 'refuses bearer' not in faults and (given == token or 'serves any token' in faults)
        match = re.fullmatch(r'/private_([A-Za-z0-9_-]{43})/mcp', self.path)
        return bool(match) and 'refuses secret' not in faults and (match.group(1) == token or 'serves any token' in faults)

    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        if not self.served():
            return self.answer(401 if self.path == '/mcp' else 404)
        session = 'woow-local-' + secrets.token_hex(8)
        self.server.sessions.add(session)
        self.answer(200, [('Content-Type', 'application/json'), ('Mcp-Session-Id', session)])

    def do_DELETE(self):
        session = self.headers.get('Mcp-Session-Id')
        if not self.served() or session not in self.server.sessions or 'keeps sessions' in self.server.faults:
            return self.answer(404)
        self.server.sessions.discard(session)
        self.answer(200)


@pytest.fixture
def upgrade(tmp_path, log_scan):
    """The Store's upgrade test as the hooks see it: /data/mcp as an add-on leaves it (its token made now), the hook
    state and report directories, the add-on on loopback."""
    token = secrets.token_urlsafe(32)
    log_scan.watch(token)
    data = tmp_path / 'data'
    (data / 'mcp').mkdir(parents=True)
    (data / 'mcp').chmod(0o700)
    state = data / 'mcp' / 'state.json'
    state.write_text(json.dumps({'schema_version': 4, 'token': token, 'child_token': secrets.token_urlsafe(32),
                                 'product': 'odoo', 'connection': None}))
    state.chmod(0o600)
    for name in ('hook-state', 'reports'):
        (tmp_path / name).mkdir()
    servers = []

    def serve():
        servers.append(AddOn(token))
        return servers[-1]
    value = {'token': token, 'data': data, 'addon': serve(), 'serve': serve, 'environ': {
        'DATA_DIR_DATA': str(data), 'HOOK_STATE_DIR': str(tmp_path / 'hook-state'), 'REPORT_DIR': str(tmp_path / 'reports'),
        'ADDON_HOST': '127.0.0.1', 'ADDON_URL': 'http://127.0.0.1:8099', 'ADDON_VERSION': '0.5.0', 'PHASE': 'old',
        'ADDON_IMAGE': 'ghcr.io/woowtech/amd64-mcp-odoo', 'SUPERVISOR_URL': 'http://supervisor.invalid',
        'SUPERVISOR_TOKEN': 'DUMMY-supervisor'}, 'reports': tmp_path / 'reports', 'hook_state': tmp_path / 'hook-state'}
    yield value
    for server in servers:
        server.shutdown()
        server.server_close()


def run(hook, upgrade, **environ):
    """Run a hook as the test's runtime user (the files are this process's), against the mock add-on."""
    return hook.main({**upgrade['environ'], **environ}, mcp_port=upgrade['addon'].port, runtime=(os.getuid(), os.getgid()),
                     wait=0)


def report(upgrade, hook):
    return {item['name']: item for item in json.loads((upgrade['reports'] / (hook + '.json')).read_text())['checks']}


def snapshot(root):
    """Every entry under /data, as a read must leave it (atime aside)."""
    found = {}
    for path in [root, *sorted(root.rglob('*'))]:
        info = os.lstat(path)
        content = path.read_bytes() if stat.S_ISREG(info.st_mode) else None
        found[str(path.relative_to(root))] = (info.st_ino, info.st_mode, info.st_uid, info.st_gid, info.st_size,
                                              info.st_mtime_ns, info.st_ctime_ns, content)
    return found


def test_an_untouched_upgrade_passes_and_both_hooks_only_read(upgrade, capsys):
    before = snapshot(upgrade['data'])
    assert run(seed, upgrade) == 0
    assert run(verify, upgrade, PHASE='new') == 0
    assert snapshot(upgrade['data']) == before
    assert upgrade['addon'].sessions == set()  # every session the hooks opened was ended
    seeded, verified = report(upgrade, 'seed'), report(upgrade, 'verify')
    assert {item['result'] for item in [*seeded.values(), *verified.values()]} == {'pass'}
    assert sorted(seeded) == sorted(['/data/mcp owner and mode', 'state.json owner and mode', 'default token in state.json',
                                     'default token over Bearer', 'default token over secret URL',
                                     'random token over Bearer refused', 'random token over secret URL refused',
                                     'no restore marker'])
    assert set(verified) - set(seeded) == {'seed left its digests', 'state.json unchanged by the upgrade',
                                           'profiles.json as before the upgrade', 'profiles as before the upgrade'}
    state = json.loads((upgrade['hook_state'] / seed.HOOK_STATE).read_text())
    assert set(state) == {'state_sha256', 'index_sha256', 'names'} and state['index_sha256'] is None
    assert state['state_sha256'] == hashlib.sha256((upgrade['data'] / 'mcp/state.json').read_bytes()).hexdigest()
    written = ''.join(path.read_text() for directory in ('reports', 'hook_state') for path in upgrade[directory].iterdir())
    output = capsys.readouterr()
    assert upgrade['token'] not in written + output.out + output.err


UPGRADE_FAULTS = {
    'rewrites state.json': (lambda u: (u['data'] / 'mcp/state.json').write_text(
        (u['data'] / 'mcp/state.json').read_text() + ' '), 'state.json unchanged by the upgrade'),
    'makes an index': (lambda u: (u['data'] / 'mcp/profiles.json').write_text('{}'), 'profiles.json as before the upgrade'),
    'makes a profiles directory': (lambda u: (u['data'] / 'mcp/profiles').mkdir(), 'profiles as before the upgrade'),
    'leaves a restore marker': (lambda u: (u['data'] / 'mcp/.restore-detected').write_bytes(b''), 'no restore marker'),
    'opens /data/mcp': (lambda u: (u['data'] / 'mcp').chmod(0o755), '/data/mcp owner and mode'),
    'opens state.json': (lambda u: (u['data'] / 'mcp/state.json').chmod(0o644), 'state.json owner and mode'),
    'refuses the token over Bearer': (lambda u: u['addon'].faults.add('refuses bearer'), 'default token over Bearer'),
    'refuses the secret URL': (lambda u: u['addon'].faults.add('refuses secret'), 'default token over secret URL'),
    'serves any token': (lambda u: u['addon'].faults.add('serves any token'), 'random token over Bearer refused'),
    'keeps its sessions': (lambda u: u['addon'].faults.add('keeps sessions'), 'default token over Bearer'),
    'lost what seed left': (lambda u: (u['hook_state'] / seed.HOOK_STATE).unlink(), 'seed left its digests'),
}


@pytest.mark.parametrize('fault', sorted(UPGRADE_FAULTS))
def test_what_an_upgrade_must_not_do_fails_verify(upgrade, fault):
    assert run(seed, upgrade) == 0
    change, failing = UPGRADE_FAULTS[fault]
    change(upgrade)
    assert run(verify, upgrade, PHASE='new') == 1
    checks = report(upgrade, 'verify')
    assert checks[failing]['result'] == 'fail'
    assert upgrade['token'] not in json.dumps(checks)


def test_a_present_index_keeps_its_bytes(upgrade):
    """After the first release that serves profiles, the old version may hold an index: it must keep its bytes."""
    index = upgrade['data'] / 'mcp/profiles.json'
    index.write_text('{"version":1,"profile_index":{}}')
    index.chmod(0o600)
    assert run(seed, upgrade) == 0
    assert run(verify, upgrade, PHASE='new') == 0
    assert report(upgrade, 'verify')['profiles.json as before the upgrade']['detail'] == 'present, same bytes'
    index.write_text('{"version":1,"profile_index":{} }')
    assert run(verify, upgrade, PHASE='new') == 1
    assert report(upgrade, 'verify')['profiles.json as before the upgrade']['result'] == 'fail'


def test_seed_fails_on_another_owner_an_unreadable_state_or_an_unreachable_add_on(upgrade):
    assert seed.main(upgrade['environ'], mcp_port=upgrade['addon'].port, runtime=(os.getuid() + 1, os.getgid()),
                     wait=0) == 1
    assert report(upgrade, 'seed')['state.json owner and mode']['result'] == 'fail'
    gone = upgrade['serve']()
    gone.shutdown()
    gone.server_close()  # nothing listens on its port now
    assert seed.main(upgrade['environ'], mcp_port=gone.port, runtime=(os.getuid(), os.getgid()), wait=0) == 1
    assert report(upgrade, 'seed')['default token over Bearer']['detail'] == 'initialize 0, DELETE None'
    (upgrade['data'] / 'mcp/state.json').write_text('{"token": null}')
    assert run(seed, upgrade) == 1
    assert report(upgrade, 'seed')['default token in state.json']['result'] == 'fail'


# A hook in a process of its own, as the Store starts it, against the mock add-on's port (the hook's 8081 is fixed).
HOOK_PROCESS = '''import importlib.machinery, importlib.util, json, sys
path, port, uid, gid = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
loader = importlib.machinery.SourceFileLoader('hook', path)
module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(module)
sys.exit(module.main(json.loads(sys.stdin.read()), mcp_port=port, runtime=(uid, gid), wait=0))
'''


def test_the_hooks_go_straight_to_the_add_on_whatever_proxy_their_container_has(upgrade):
    """The hook container's proxy settings are never used. Each hook runs in a process of its own started with them
    (review SF-9: an opener built at import, or urllib's own, reads the environment then, so setting it in this
    process after the hooks were loaded proved nothing)."""
    proxies = {name: 'http://127.0.0.1:9' for name in ('http_proxy', 'HTTP_PROXY', 'https_proxy', 'HTTPS_PROXY',
                                                        'all_proxy', 'ALL_PROXY')}  # nothing answers (no name to resolve)
    for hook, phase in (('seed', 'old'), ('verify', 'new')):
        done = subprocess.run([sys.executable, '-I', '-c', HOOK_PROCESS, str(HOOKS / hook), str(upgrade['addon'].port),
                               str(os.getuid()), str(os.getgid())], input=json.dumps({**upgrade['environ'], 'PHASE': phase}),
                              env={'PATH': '/usr/bin:/bin', **proxies}, cwd='/', capture_output=True, text=True, timeout=120)
        assert upgrade['token'] not in done.stdout + done.stderr
        assert done.returncode == 0, report(upgrade, hook)
        assert {item['result'] for item in report(upgrade, hook).values()} == {'pass'}
    assert upgrade['addon'].sessions == set()


def test_an_index_that_is_a_link_is_never_read_through(upgrade, tmp_path):
    """Review SF-8: the hooks run as root, so a link at the index is never followed (what it points to is not the
    index's bytes), and verify cannot confirm such an index unchanged."""
    elsewhere = tmp_path / 'elsewhere.json'
    elsewhere.write_text('{"version":1,"profile_index":{}}')
    (upgrade['data'] / 'mcp/profiles.json').symlink_to(elsewhere)
    assert run(seed, upgrade) == 0
    assert json.loads((upgrade['hook_state'] / seed.HOOK_STATE).read_text())['index_sha256'] == 'unreadable'
    assert run(verify, upgrade, PHASE='new') == 1
    assert report(upgrade, 'verify')['profiles.json as before the upgrade'] == {
        'name': 'profiles.json as before the upgrade', 'result': 'fail', 'detail': 'present, unreadable'}


def test_the_hooks_assert_nothing_that_depends_on_a_version(upgrade):
    assert run(seed, upgrade) == 0
    results = []
    for version, image, phase in (('0.5.0', 'ghcr.io/woowtech/amd64-mcp-odoo', 'new'), ('9.9.9', 'local/other', 'old'),
                                  ('', '', '')):
        assert run(verify, upgrade, ADDON_VERSION=version, ADDON_IMAGE=image, PHASE=phase) == 0
        results.append(report(upgrade, 'verify'))
    assert results[0] == results[1] == results[2]
    for hook in ('seed', 'verify'):
        source = (HOOKS / hook).read_text()
        for word in ('ADDON_VERSION', 'ADDON_IMAGE', 'PHASE', 'serverInfo', 'tools/list', 'SUPERVISOR_TOKEN'):
            assert word not in source.split('"""', 2)[2], (hook, word)  # the code, not its docstring


def test_the_hook_files_are_what_the_store_runs():
    """The Store: an executable with a python3 or busybox sh #!, LF line ends, in python:3.12-alpine (standard library)."""
    for hook in ('seed', 'verify'):
        path = HOOKS / hook
        raw = path.read_bytes()
        assert raw.startswith(b'#!/usr/bin/env python3\n') and b'\r' not in raw
        assert path.stat().st_mode & 0o111 == 0o111
        tree = ast.parse(raw.decode(), feature_version=(3, 12))
        imported = {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                    for alias in node.names}
        imported |= {node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        assert imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names)
    # verify reuses seed's readers: one set of rules for both phases
    assert verify.seed.read_state.__code__.co_code == seed.read_state.__code__.co_code


# ---- the real runtime (HM-16 review SF-6; the reviewer's experiment E1) ----

def free_port():
    with reserve_port() as sock:
        return sock.getsockname()[1]


def entries(root):
    """Every entry under /data as the hooks must leave it: kind, mode, owner, inode and a file's bytes (not its times:
    the runtime's own reads of state.json change its ctime meanwhile)."""
    found = {}
    for path in [root, *sorted(root.rglob('*'))]:
        info = os.lstat(path)
        found[str(path.relative_to(root))] = (stat.S_IFMT(info.st_mode), stat.S_IMODE(info.st_mode), info.st_uid,
                                              info.st_gid, info.st_ino,
                                              path.read_bytes() if stat.S_ISREG(info.st_mode) else None)
    return found


class Runtime:
    """run_product of one product on a /data/mcp, through the owned executable; switched on in its preamble or not."""

    def __init__(self, home, product, data, switched_on):
        self.port, admin_port = free_port(), free_port()
        home.mkdir()
        self.runner = Executable(home, product, [self.port, admin_port])
        # HM-26: switched off pinned in the preamble too, whatever the repository's switch says
        preamble = (f'from mcp_admin_core import features; features.MULTI_PROFILE_PRODUCTS = frozenset({{{product!r}}}); '
                    if switched_on else product_switch.preamble(product))
        code = preamble + 'from mcp_admin_core import run_product; ' + self.runner.code('run_product') + 'run_product.main()'
        self.runner.release()
        self.log = (home / 'runtime.log').open('wb')
        self.process = subprocess.Popen(
            [str(ROOT / '.venv/bin/python'), '-c', code, product, '--data', str(data), '--host', '127.0.0.1',
             '--mcp-port', str(self.port), '--admin-port', str(admin_port)], cwd=ROOT,
            env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(ROOT / 'packages/mcp-admin-core')},
            stdout=self.log, stderr=self.log)

    async def ready(self):
        await self.runner.ready(self.process)
        await self.runner.guard_url(f'http://127.0.0.1:{self.port}/mcp')  # this runtime's own listener, proved

    def stop(self):
        self.process.send_signal(signal.SIGTERM)
        try:
            self.process.wait(15)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
            pytest.fail('runtime did not stop')
        finally:
            self.log.close()
        assert self.process.returncode == 0


@pytest.mark.parametrize('product', ['odoo', 'emqx', 'headscale'])  # HM-26: Headscale's 0.5.0 runs these hooks too
@pytest.mark.parametrize('switched_on', [True, False], ids=['old-off-new-on', 'off-both'])
async def test_the_hooks_pass_an_upgrade_of_the_real_runtime_and_only_read(tmp_path, log_scan, product, switched_on):
    """As the Store's upgrade test runs them: seed once the old version started on an empty /data (unconfigured, as the
    Store leaves it), verify once the new version started on the same /data. The old version is not switched on; the
    new one is (the 0.5.0 upgrade's shape), or is not either. Both run this checkout's code: what is tested is what the
    hooks assume of the gateway (a session the gateway answers itself can be ended; a random token is refused; a start
    rewrites nothing), not 0.4.13. The hooks pass and change nothing under /data; a first switched-on start writes no
    index and no profiles directory (verify's 'as before the upgrade')."""
    data_root = tmp_path / 'data'
    data = data_root / 'mcp'
    data.mkdir(parents=True)
    data.chmod(0o700)  # as packaging/entrypoint.py prepares it
    for name in ('hook-state', 'reports'):
        (tmp_path / name).mkdir()
    environ = {'DATA_DIR_DATA': str(data_root), 'HOOK_STATE_DIR': str(tmp_path / 'hook-state'),
               'REPORT_DIR': str(tmp_path / 'reports'), 'ADDON_HOST': '127.0.0.1', 'ADDON_URL': 'http://127.0.0.1:8099',
               'ADDON_VERSION': '0.0.0', 'PHASE': 'old', 'ADDON_IMAGE': 'local/upgrade-hooks',
               'SUPERVISOR_URL': 'http://supervisor.invalid', 'SUPERVISOR_TOKEN': 'DUMMY-supervisor'}
    owner = (os.getuid(), os.getgid())  # the runtime runs as this test's user (the add-on's is 10001)

    def checks(hook):
        return {item['name']: item['result'] for item in
                json.loads((tmp_path / 'reports' / (hook + '.json')).read_text())['checks']}
    old = Runtime(tmp_path / 'old', product, data, False)
    try:
        await old.ready()
        state = json.loads((data / 'state.json').read_text())
        log_scan.watch(state['token'], state['child_token'])
        before = entries(data_root)
        seeded = seed.main(environ, mcp_port=old.port, runtime=owner, wait=10)
        assert entries(data_root) == before, 'seed changed /data'
    finally:
        old.stop()
    assert seeded == 0, checks('seed')
    new = Runtime(tmp_path / 'new', product, data, switched_on)
    try:
        await new.ready()
        before = entries(data_root)
        verified = verify.main({**environ, 'PHASE': 'new'}, mcp_port=new.port, runtime=owner, wait=10)
        assert entries(data_root) == before, 'verify changed /data'
    finally:
        new.stop()
    assert verified == 0, checks('verify')
    assert set(checks('verify').values()) == {'pass'}
    assert not os.path.lexists(data / 'profiles.json') and not os.path.lexists(data / 'profiles')
