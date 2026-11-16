"""Headscale's owned backend fixture and bind-address guard; the direct child bearer check (HM-06); the restore stage
(multi-profile HM-13a); the mock address of a switched-on product and the single-profile path every candidate runs
unchanged (multi-profile HM-16). Without Docker or root."""
import ast
import asyncio
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/mcp-admin-core'), str(ROOT / 'apps/n8n')]
with patch.object(sys, 'argv', ['container_probe.py', 'headscale']):
    import container_probe as probe
from mcp_admin_core import features  # noqa: E402  (HM-16: the products whose child refuses a loopback backend)

RUNTIME = (10001, 10001)


class HeadscaleBackendTests(unittest.TestCase):
    def setUp(self):
        probe.CALLS.clear()
        probe.OFFLINE.clear()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), probe.Backend)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = httpx.Client(trust_env=False)
        self.url = f'http://127.0.0.1:{self.server.server_port}/api/v1/health'

    def tearDown(self):
        self.client.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        probe.OFFLINE.clear()
        probe.CALLS.clear()

    def test_native_health_requires_key_and_returns_probe_shape(self):
        for headers in ({}, {'Authorization': 'Bearer wrong'}):
            self.assertEqual(self.client.get(self.url, headers=headers).status_code, 401)
        response = self.client.get(self.url, headers={'Authorization': 'Bearer DUMMY'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'databaseConnectivity': True})
        self.assertTrue(probe.probe_success('headscale', response.json()))
        self.assertEqual(self.client.get(self.url.replace('/health', '/node'),
                                         headers={'Authorization': 'Bearer DUMMY'}).status_code, 404)

    def test_offline_health_is_unavailable(self):
        probe.OFFLINE.set()
        self.assertEqual(self.client.get(self.url, headers={'Authorization': 'Bearer DUMMY'}).status_code, 503)

    def test_headscale_requires_private_non_loopback_bind_address(self):
        with patch.object(probe.socket, 'gethostname', return_value='candidate'), \
             patch.object(probe.socket, 'gethostbyname', return_value='172.18.0.2'):
            self.assertEqual(probe.mock_bind_host('headscale'), '172.18.0.2')
        for address in ('127.0.0.1', '169.254.1.2', '100.64.0.1', '192.0.2.1'):
            with self.subTest(address=address), patch.object(probe.socket, 'gethostbyname', return_value=address):
                with self.assertRaises(AssertionError):
                    probe.mock_bind_host('headscale')
        self.assertEqual(probe.mock_bind_host('emqx'), '127.0.0.1')


def switched(*products):
    """The product switch as an upgrade PR sets it (the repository keeps it empty), for this test only."""
    return patch.object(features, 'MULTI_PROFILE_PRODUCTS', frozenset(products))


class SwitchedOnMockBackendTests(unittest.TestCase):
    """Multi-profile HM-16 (HM-20 review MF-2; HM-20 left a tripwire here, now the rule itself): every child of a
    switched-on product (features.MULTI_PROFILE_PRODUCTS) refuses a loopback backend (WOOW_MCP_DENY_LOOPBACK=1), as
    Headscale's always does, so its mock backend listens where Headscale's does: on this container's private address on
    container_acceptance's one-use internal bridge (packaging/test_container_acceptance.py), never on 127.0.0.1; the
    test double tests/loopback_backends.py is in no image. Every product is checked switched on and off."""

    def test_a_switched_on_product_s_mock_listens_on_the_container_s_private_address(self):
        for app in sorted(features.KNOWN_PRODUCTS):
            with self.subTest(app=app), switched(app), patch.object(probe.socket, 'gethostname', return_value='candidate'), \
                    patch.object(probe.socket, 'gethostbyname', return_value='172.18.0.2'):
                self.assertEqual(probe.mock_bind_host(app), '172.18.0.2')
            for address in ('127.0.0.1', '169.254.1.2', '100.64.0.1', '192.0.2.1', '8.8.8.8'):
                with self.subTest(app=app, address=address), switched(app), \
                        patch.object(probe.socket, 'gethostbyname', return_value=address):
                    with self.assertRaises(AssertionError):
                        probe.mock_bind_host(app)

    def test_a_product_not_switched_on_keeps_its_mock_on_loopback_and_headscale_its_bridge(self):
        with switched(), patch.object(probe.socket, 'gethostname', return_value='candidate'), \
                patch.object(probe.socket, 'gethostbyname', return_value='172.18.0.2'):
            for app in sorted(features.KNOWN_PRODUCTS):
                with self.subTest(app=app):
                    self.assertEqual(probe.mock_bind_host(app), '172.18.0.2' if app == 'headscale' else '127.0.0.1')

    def test_the_repository_switch_decides_it(self):
        """What HM-20's tripwire guarded: a product an upgrade PR switches on gets the private address at once."""
        with patch.object(probe.socket, 'gethostname', return_value='candidate'), \
                patch.object(probe.socket, 'gethostbyname', return_value='172.18.0.2'):
            for app in sorted(features.KNOWN_PRODUCTS):
                with self.subTest(app=app):
                    private = app == 'headscale' or app in features.MULTI_PROFILE_PRODUCTS
                    self.assertEqual(probe.mock_bind_host(app), '172.18.0.2' if private else '127.0.0.1')


# The single-profile probe as reviewed before HM-16 (claude-delivery f4c7718). A slice that changes that path on purpose
# moves BASE to the commit its change is reviewed against, and says why in its provenance note. Both sides are compared
# without their switched-on parts (review MF-3): a base that has switched-on parts of its own (HM-13b's restore check,
# its features import) needs nothing but BASE moved.
BASE = 'f4c7718'
# What HM-16 adds for a switched-on product, beyond what BASE has: `import container_profiles`, three statements
# `if ... features.enabled(...)` that each hand over to container_profiles (mock_bind_host, fixture_snapshot, run), and
# the import of features unless BASE has it already.
SWITCHED_ON_BRANCHES = 3


def is_switched_on_branch(node):
    return isinstance(node, ast.If) and any(
        isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == 'enabled'
        and isinstance(call.func.value, ast.Name) and call.func.value.id == 'features' for call in ast.walk(node.test))


class WithoutSwitchedOnAdditions(ast.NodeTransformer):
    """The probe module without its switched-on parts: the imports of features and container_profiles, and every `if`
    statement whose test calls features.enabled, wherever it stands. removed: [(kind, the node)] of each."""

    def __init__(self):
        self.removed = []

    def drop(self, kind, node):
        self.removed.append((kind, node))

    def visit_If(self, node):
        if is_switched_on_branch(node):
            return self.drop('branch', node)
        return self.generic_visit(node)

    def visit_Import(self, node):
        if [alias.name for alias in node.names] == ['container_profiles']:
            return self.drop('container_profiles', node)
        return node

    def visit_ImportFrom(self, node):
        if node.module == 'mcp_admin_core' and [alias.name for alias in node.names] == ['features']:
            return self.drop('features', node)
        return node


def without_switched_on_parts(source):
    """(the module's AST without its switched-on parts, {ast.dump of a removed part: (kind, node, how many)})."""
    tree = ast.parse(source)
    stripping = WithoutSwitchedOnAdditions()
    stripping.visit(tree)
    parts = {}
    for kind, node in stripping.removed:
        dump = ast.dump(node)
        parts[dump] = (kind, node, parts.get(dump, (None, None, 0))[2] + 1)
    return tree, parts


def hands_over_to_container_profiles(node):
    return any(isinstance(name, ast.Name) and name.id == 'container_profiles' for name in ast.walk(node))


class SingleProfilePathTests(unittest.TestCase):
    """Multi-profile HM-16 (plan 12.3 HM-16 acceptance: the single-profile probe path does not change): a product that
    is not switched on runs BASE's probe statement for statement; the switched-on additions are only guarded
    branches, the stage call last."""

    def test_without_the_switched_on_branches_the_probe_is_the_reviewed_one(self):
        base = subprocess.run(['git', '-c', f'safe.directory={ROOT}', '-C', str(ROOT), 'show',
                               f'{BASE}:packaging/container_probe.py'], capture_output=True, text=True, check=True).stdout
        base_tree, base_parts = without_switched_on_parts(base)
        tree, parts = without_switched_on_parts(Path(probe.__file__).read_text())
        self.assertEqual(ast.dump(tree), ast.dump(base_tree))  # every other statement as BASE has it
        # every switched-on part BASE has is still here, unchanged
        self.assertEqual({dump: count for dump, (_, _, count) in base_parts.items()
                          if parts.get(dump, (None, None, 0))[2] < count}, {})
        added = [(kind, node) for dump, (kind, node, count) in parts.items()
                 for _ in range(count - base_parts.get(dump, (None, None, 0))[2])]
        kinds = sorted(kind for kind, _ in added)
        has_features = any(kind == 'features' for kind, _, _ in base_parts.values())
        self.assertEqual(kinds, sorted(['container_profiles', *['branch'] * SWITCHED_ON_BRANCHES,
                                        *([] if has_features else ['features'])]))
        self.assertTrue(all(hands_over_to_container_profiles(node) for kind, node in added if kind == 'branch'))

    def test_the_stage_runs_last_and_only_switched_on(self):
        run = next(node for node in ast.parse(Path(probe.__file__).read_text()).body
                   if isinstance(node, ast.AsyncFunctionDef) and node.name == 'run')
        branches = [node for node in ast.walk(run) if is_switched_on_branch(node)]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(ast.unparse(branch.test), 'features.enabled(APP)')
        self.assertEqual([ast.unparse(statement) for statement in branch.body],
                         ['await container_profiles.stage(sys.modules[__name__], client)'])
        client = next(node for node in ast.walk(run) if isinstance(node, ast.AsyncWith)
                      and ast.unparse(node.items[0].context_expr).startswith('httpx.AsyncClient'))
        self.assertIs(client.body[-1], branch)  # after the last stop of the single-profile path


class FixtureSnapshotTests(unittest.TestCase):
    """fixture_snapshot (C4-SF-5): only a switched-on product's /data/mcp may hold the multi-profile layout."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name) / 'mcp'
        self.data.mkdir(mode=0o700)
        self.data.chmod(0o700)
        for name in ('state.json', '.writer.lock'):
            (self.data / name).write_bytes(b'{"fixture": true}')
            (self.data / name).chmod(0o600)
        patcher = patch.object(probe, 'DATA', self.data)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_product_not_switched_on_keeps_today_s_bounded_regular_files(self):
        with switched():
            found = probe.fixture_snapshot()
            self.assertEqual(sorted(found), ['.writer.lock', 'state.json'])
            self.assertEqual(len(found['state.json']), 8)
            (self.data / 'profiles').mkdir()
            with self.assertRaises(AssertionError):
                probe.fixture_snapshot()
            (self.data / 'profiles').rmdir()
            for number in range(15):
                (self.data / f'extra-{number}').write_bytes(b'')
            with self.assertRaises(AssertionError):
                probe.fixture_snapshot()

    def test_a_switched_on_product_s_is_the_layout_s_tree(self):
        with switched(probe.APP), patch.object(probe.container_profiles, 'tree_snapshot', return_value={'x': 1}) as tree:
            self.assertEqual(probe.fixture_snapshot(), {'x': 1})
        tree.assert_called_once_with(self.data)


CHILD_TOKEN = 'C' * 43  # tests/fixtures/owner_defaults/README.md: a child token in test data
INITIALIZE = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
    'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'container-mock', 'version': '1'}}}


class FakeChild(BaseHTTPRequestHandler):
    """A child on a private port (never 3000): serves only Bearer CHILD_TOKEN unless a fault is set."""
    fault = None
    seen = []

    def log_message(self, *args):
        pass

    def served(self):
        value = self.headers.get('Authorization')
        if self.fault == 'open':
            return True
        if self.fault == 'any bearer':
            return value is not None and value.startswith('Bearer ') and len(value) == len('Bearer ') + 43
        return value == 'Bearer ' + CHILD_TOKEN and self.fault != 'refuses its own'

    def answer(self, status, data=b'', headers=()):
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        message = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        own = self.headers.get('Authorization') == 'Bearer ' + CHILD_TOKEN
        FakeChild.seen.append(('POST', own, self.headers.get('Authorization') is None))
        if not self.served():
            self.answer(401, headers=[('WWW-Authenticate', 'Bearer')])
            return
        reply = {'jsonrpc': '2.0', 'id': message['id'], 'result': {'protocolVersion': '2025-03-26', 'capabilities': {},
                                                                  'serverInfo': {'name': 'fake', 'version': '0'}}}
        self.answer(200, json.dumps(reply).encode(),
                    [('Content-Type', 'application/json'), ('Mcp-Session-Id', 'fake-1')])

    def do_DELETE(self):
        own = self.headers.get('Authorization') == 'Bearer ' + CHILD_TOKEN
        FakeChild.seen.append(('DELETE', own, self.headers.get('Mcp-Session-Id'),
                               self.headers.get('MCP-Protocol-Version')))
        if not self.served():
            self.answer(401)
        else:
            self.answer(404 if self.fault == 'keeps the session' else 200)


class ChildBearerCheckTests(unittest.TestCase):
    """assert_child_bearer, the container probe's direct check of the child on 3000 (here: a fake on a private port)."""

    def setUp(self):
        FakeChild.fault = None
        FakeChild.seen = []
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeChild)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/mcp'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def check(self):
        async def run():
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                await probe.assert_child_bearer(client, CHILD_TOKEN, INITIALIZE, url=self.url)
        asyncio.run(run())

    def test_a_child_serving_only_its_own_bearer_passes(self):
        self.assertEqual(probe.CHILD, 'http://127.0.0.1:3000/mcp')
        self.check()
        # No bearer, another token of the same form, the own one; then the session it opened is ended.
        self.assertEqual(FakeChild.seen, [('POST', False, True), ('POST', False, False), ('POST', True, False),
                                          ('DELETE', True, 'fake-1', '2025-03-26')])

    def test_any_other_child_fails_without_showing_the_token(self):
        for fault, message in (('open', 'child served without its bearer'),
                               ('any bearer', 'child served without its bearer'),
                               ('refuses its own', 'child refused its own bearer'),
                               ('keeps the session', 'child kept the session it opened')):
            with self.subTest(fault=fault):
                FakeChild.fault = fault
                with self.assertRaises(AssertionError) as failed:
                    self.check()
                self.assertEqual(str(failed.exception), message)  # a fixed message: never a token


class Seen:
    """A stat result with the owner Owners records."""

    def __init__(self, info, owner):
        self._info = info
        self.st_uid, self.st_gid = owner

    def __getattr__(self, name):
        return getattr(self._info, name)


class Owners:
    """container_probe's os module without root: chown only changes this map, (st_dev, st_ino) -> owner, and lstat
    reports it; an inode not in it is the runtime user's, as the probe's fixture leaves every entry."""

    def __init__(self):
        self.owners = {}

    def __getattr__(self, name):
        return getattr(os, name)

    def chown(self, path, uid, gid):
        info = os.lstat(path)
        self.owners[(info.st_dev, info.st_ino)] = (uid, gid)

    def lstat(self, path):
        info = os.lstat(path)
        return Seen(info, self.owners.get((info.st_dev, info.st_ino), RUNTIME))


class RestoreStageTests(unittest.TestCase):
    """The restore stage that runs in every release's container acceptance. tests/test_restore_detection.py runs it
    against the real entrypoint as well (unprivileged, and as root in the CI)."""

    def fixture(self):
        """/data/mcp as the first, unconfigured start leaves it: the runtime user's state.json and .writer.lock."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        data = Path(temporary.name) / 'mcp'
        data.mkdir(mode=0o700)
        data.chmod(0o700)  # no setgid bit from a setgid TMPDIR
        for name, content in (('state.json', b'{"fixture": true}'), ('.writer.lock', b'')):
            (data / name).write_bytes(content)
            (data / name).chmod(0o600)
        return data

    def setUp(self):
        self.data = self.fixture()
        self.os = Owners()
        for patcher in (patch.object(probe, 'DATA', self.data), patch.object(probe, 'os', self.os)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def owner(self, path):
        info = path.lstat()
        return self.os.owners.get((info.st_dev, info.st_ino), RUNTIME)

    def test_a_restore_gives_every_entry_to_root_while_stopped(self):
        (self.data / 'child').mkdir(mode=0o700)
        (self.data / 'child' / 'leftover').write_bytes(b'')
        restored, state = probe.restore_as_supervisor()
        self.assertEqual(restored, ['.writer.lock', 'child', 'child/leftover', 'state.json'])
        self.assertEqual(state, b'{"fixture": true}')
        entries = [self.data, *self.data.rglob('*')]
        self.assertEqual({self.owner(path) for path in entries}, {(0, 0)})
        self.assertEqual({str(path.relative_to(self.data)): stat.S_IMODE(path.lstat().st_mode) for path in entries},
                         {'.': 0o700, '.writer.lock': 0o644, 'child': 0o755, 'child/leftover': 0o644,
                          'state.json': 0o644})

    def test_a_restore_refuses_what_the_fixture_never_holds_before_changing_anything(self):
        for unexpected in ('a link', 'a second link', 'a marker'):
            with self.subTest(unexpected=unexpected):
                path = self.data / (probe.MARKER if unexpected == 'a marker' else 'extra')
                if unexpected == 'a link':
                    path.symlink_to('state.json')
                elif unexpected == 'a second link':
                    os.link(self.data / 'state.json', path)
                else:
                    path.write_bytes(b'')
                with self.assertRaises(AssertionError):
                    probe.restore_as_supervisor()
                self.assertEqual(self.os.owners, {})
                self.assertEqual(stat.S_IMODE((self.data / 'state.json').lstat().st_mode), 0o600)
                path.unlink()

    def repaired(self, data):
        """data restored, then as the entrypoint leaves it: every entry the runtime user's again, and the marker."""
        restored, state = probe.restore_as_supervisor()
        self.os.owners.clear()
        for name in restored:
            (data / name).chmod(0o600)
        (data / probe.MARKER).write_bytes(b'')
        (data / probe.MARKER).chmod(0o600)
        return restored, state

    def test_the_check_after_the_restore_start_passes_a_repaired_restore(self):
        probe.check_restored_start(*self.repaired(self.data))

    def test_the_check_after_the_restore_start_needs_the_marker_and_the_repair(self):
        marker = probe.MARKER
        changes = {
            'no marker': lambda data: (data / marker).unlink(),
            'a root-owned marker': lambda data: self.os.chown(data / marker, 0, 0),
            'a readable marker': lambda data: (data / marker).chmod(0o644),
            'a marker with content': lambda data: (data / marker).write_bytes(b'x'),
            'a marker with a second link': lambda data: os.link(data / marker, data / 'marker-copy'),
            'a restored entry still root-owned': lambda data: self.os.chown(data / '.writer.lock', 0, 0),
            'a restored entry still 0644': lambda data: (data / 'state.json').chmod(0o644),
            'a rewritten state': lambda data: (data / 'state.json').write_bytes(b'{"fixture": false}'),
        }
        for label, change in changes.items():
            with self.subTest(label=label), patch.object(probe, 'DATA', self.fixture()) as data:
                restored, state = self.repaired(data)
                change(data)
                with self.assertRaises(AssertionError):
                    probe.check_restored_start(restored, state)

    def stage(self, check=None, exited=False):
        events = []
        process = Mock(**{'poll.return_value': 1 if exited else None})

        async def ready(client, running):
            events.append(('ready', client, running))

        def restore():
            events.append('restore')
            return ['state.json'], b'S'

        def checked(*args):
            events.append(('check', *args))
            if check:
                raise check
        with patch.object(probe, 'restore_as_supervisor', restore), \
             patch.object(probe, 'start', lambda: events.append('start') or process), \
             patch.object(probe, 'ready_listener', ready), patch.object(probe, 'check_restored_start', checked), \
             patch.object(probe, 'stop', lambda running: events.append(('stop', running))):
            try:
                asyncio.run(probe.restored_start('client'))
            except AssertionError:
                events.append('failed')
        return events, process

    def test_the_restore_happens_while_stopped_then_the_start_is_checked_and_stopped(self):
        events, process = self.stage()
        self.assertEqual(events, ['restore', 'start', ('ready', 'client', process), ('check', ['state.json'], b'S'),
                                  ('stop', process)])

    def test_a_failed_check_still_stops_the_runtime_and_fails(self):
        events, process = self.stage(check=AssertionError('restore marker missing'))
        self.assertEqual(events[-2:], [('stop', process), 'failed'])
        events, process = self.stage(check=AssertionError('restore marker missing'), exited=True)
        self.assertNotIn(('stop', process), events)  # an exited runtime has nothing to stop
        self.assertEqual(events[-1], 'failed')

    def test_every_container_acceptance_runs_the_restore_stage_before_configuring(self):
        # The probe is only run for real by the builder: pin where run() takes the stage, by its source.
        run = next(node for node in ast.parse(Path(probe.__file__).read_text()).body
                   if isinstance(node, ast.AsyncFunctionDef) and node.name == 'run')
        named = (node for node in ast.walk(run) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name))
        calls = sorted(named, key=lambda node: (node.lineno, node.col_offset))
        names = [node.func.id for node in calls]
        self.assertEqual(names.count('restored_start'), 1)
        self.assertLess(names.index('stop'), names.index('restored_start'))
        self.assertLess(names.index('restored_start'), names.index('fixture_update'))
        awaited = [node.value for node in ast.walk(run) if isinstance(node, ast.Await)]
        self.assertIn(calls[names.index('restored_start')], awaited)


if __name__ == '__main__':
    unittest.main()
