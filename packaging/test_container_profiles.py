"""The container probe's multi-profile stage (multi-profile HM-16; packaging/container_profiles.py), without Docker or
root. Each part runs against fakes of what the candidate container gives it (/proc, the 8081 listener, the children,
the add-on process); the fixture and the restore detection run the real library on a temporary /data/mcp; the stage
itself runs with every part replaced, for its order. Tokens are made when a test runs and never appear in a message."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/mcp-admin-core'), str(ROOT / 'apps/n8n')]
with patch.object(sys, 'argv', ['container_probe.py', 'headscale']):
    import container_probe as probe  # noqa: E402
import container_profiles as stage  # noqa: E402
import entrypoint  # noqa: E402
from mcp_admin_core import profiles, restore_detect  # noqa: E402
from mcp_admin_core.products import ProductStore  # noqa: E402
from test_container_probe import Owners  # noqa: E402  (chown without root: lstat reports the owner it recorded)

RUNTIME = (10001, 10001)
CONNECTION = {'url': 'http://backend.invalid:18083', 'api_key': 'DUMMY', 'api_secret': 'DUMMY'}
A, B = 'a' * 24, 'b' * 24


def temporary(test):
    directory = tempfile.TemporaryDirectory()
    test.addCleanup(directory.cleanup)
    return Path(directory.name)


def private_dir(path):
    path.mkdir(mode=0o700)
    path.chmod(0o700)  # no setgid bit from a setgid TMPDIR
    return path


def private_file(path, content=b'{}'):
    path.write_bytes(content)
    path.chmod(0o600)
    return path


def layout_tree(root):
    """/data/mcp as a switched-on product leaves it once its children ran: the default profile, the index, the restore
    files and two additional profiles, each with its child's empty working directory."""
    data = private_dir(root / 'mcp')
    for name in ('state.json', '.writer.lock', stage.JOURNAL, profiles.INDEX_NAME, profiles.SENTINEL_NAME,
                 profiles.INSTANCE_RECORD_NAME):
        private_file(data / name)
    private_dir(data / 'child')
    private_dir(data / 'profiles')
    for profile_id in (A, B):
        directory = private_dir(data / 'profiles' / profile_id)
        for name in ('state.json', '.writer.lock'):
            private_file(directory / name)
        private_dir(directory / 'child')
    return data


class TreeSnapshotTests(unittest.TestCase):
    """tree_snapshot: fixture_snapshot of a switched-on product (C4-SF-5), the restore repair's rules (FM-16)."""

    def setUp(self):
        self.os = Owners()
        patcher = patch.object(stage, 'os', self.os)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_layout_after_the_children_ran_is_taken_entry_by_entry(self):
        data = layout_tree(temporary(self))
        found = stage.tree_snapshot(data)
        profile = [f'profiles/{p}/{name}' for p in (A, B) for name in ('.writer.lock', 'child', 'state.json')]
        self.assertEqual(sorted(found), sorted(['state.json', '.writer.lock', stage.JOURNAL, profiles.INDEX_NAME,
                                                profiles.SENTINEL_NAME, profiles.INSTANCE_RECORD_NAME, 'child',
                                                'profiles', f'profiles/{A}', f'profiles/{B}', *profile]))
        self.assertEqual(found['state.json'][1:3], RUNTIME)
        self.assertEqual(len(found['state.json'][7]), 64)
        self.assertIsNone(found['profiles'][7])
        # every name the layout gives the top of /data/mcp, as the kind of entry it is
        for name in sorted(stage.TOP_NAMES - stage.DIRECTORIES):
            self.assertTrue(stage._designed((name,), False), name)
            self.assertFalse(stage._designed((name,), True), name)
        self.assertTrue(stage._designed(('profiles.json.quarantine-20261116T010203Z-2',), False))
        quarantined = profiles.quarantine_name(A, datetime(2026, 11, 16, 1, 2, 3, tzinfo=timezone.utc))
        self.assertTrue(stage._designed(('profiles', quarantined), True))
        self.assertTrue(stage._designed(('profiles', quarantined, 'state.json'), False))

    def test_what_the_layout_never_holds_is_refused(self):
        changes = {
            'a link': (lambda d: (d / 'profiles' / A / 'extra').symlink_to('state.json'), 'not a plain entry'),
            'a second link': (lambda d: os.link(d / 'profiles' / A / 'state.json', d / 'profiles' / A / 'copy'),
                              'not a plain entry'),
            'a file in a child directory': (lambda d: private_file(d / 'profiles' / B / 'child' / 'cache'),
                                            'child working directory not empty'),
            "a file in the default child's": (lambda d: private_file(d / 'child' / 'cache'),
                                              'child working directory not empty'),
            'an unknown name': (lambda d: private_file(d / 'notes.json'), 'not a name of the layout'),
            'an unknown name in a profile': (lambda d: private_file(d / 'profiles' / A / 'notes.json'),
                                             'not a name of the layout'),
            'a profiles entry that is no profile': (lambda d: private_dir(d / 'profiles' / 'not-a-profile'),
                                                    'not a name of the layout'),
            'a file named as a profile': (lambda d: private_file(d / 'profiles' / ('c' * 24)),
                                          'not a name of the layout'),
            'a directory at a file name': (lambda d: private_dir(d / profiles.RESTORE_RECORD_NAME),
                                           'not a name of the layout'),
            "an entry that is not the runtime user's": (lambda d: self.os.chown(d / 'profiles' / A, 0, 0),
                                                        "not the runtime user's"),
            'a readable file': (lambda d: (d / 'profiles' / B / 'state.json').chmod(0o644), 'not private'),
            'an open directory': (lambda d: (d / 'profiles').chmod(0o755), 'not private'),
            'an oversize file': (lambda d: private_file(d / profiles.RESTORE_RECORD_NAME,
                                                        b'x' * (stage.MAX_FILE_BYTES + 1)), 'oversize entry'),
        }
        for label, (change, message) in changes.items():
            with self.subTest(label=label):
                data = layout_tree(temporary(self))
                change(data)
                with self.assertRaisesRegex(AssertionError, message):
                    stage.tree_snapshot(data)

    def test_the_repair_budget_and_depth_bound_the_tree(self):
        with patch.object(entrypoint, 'MAX_RESTORED_ENTRIES', 5):
            with self.assertRaisesRegex(AssertionError, 'tree over the repair budget'):
                stage.tree_snapshot(layout_tree(temporary(self)))
        with patch.object(entrypoint, 'MAX_RESTORED_DEPTH', 1):
            with self.assertRaisesRegex(AssertionError, 'tree deeper than the repair goes'):
                stage.tree_snapshot(layout_tree(temporary(self)))
        self.assertEqual((entrypoint.MAX_RESTORED_ENTRIES, entrypoint.MAX_RESTORED_DEPTH), (512, 8))

    def test_another_filesystem_is_refused(self):
        data = layout_tree(temporary(self))
        mounted = os.lstat(data / 'profiles' / B).st_ino
        owners = self.os

        class Elsewhere:
            """An entry's stat result on another device."""

            def __init__(self, info):
                self._info, self.st_dev = info, info.st_dev + 1

            def __getattr__(self, name):
                return getattr(self._info, name)

        class Devices:
            def __getattr__(self, name):
                return getattr(owners, name)

            def lstat(self, path):
                info = owners.lstat(path)
                return Elsewhere(info) if info.st_ino == mounted else info
        with patch.object(stage, 'os', Devices()):
            with self.assertRaisesRegex(AssertionError, 'tree crosses a filesystem'):
                stage.tree_snapshot(data)

    def test_the_journal_name_is_the_operation_journal_s(self):
        from mcp_admin_core.operations import OperationJournal
        self.assertEqual(OperationJournal(Path(tempfile.gettempdir()) / 'state.json').path.name, stage.JOURNAL)


class ProfileFixtureTests(unittest.TestCase):
    """create_profiles: two additional profiles as the panel's creation makes them, given to the runtime user."""

    def setUp(self):
        self.data = temporary(self) / 'mcp'
        store = ProductStore(self.data, 'emqx')
        self.default = store.update(connection=CONNECTION, disabled=['emqx_list_clients'])
        store.close()
        self.probe = SimpleNamespace(DATA=self.data, fixture_update=self.load)
        self.os = Owners()
        patcher = patch.object(stage, 'os', self.os)
        patcher.start()
        self.addCleanup(patcher.stop)

    def load(self):
        store = ProductStore(self.data, 'emqx')
        try:
            return store.load()
        finally:
            store.close()

    def test_two_profiles_are_born_complete_indexed_and_given_to_the_runtime_user(self):
        before = (self.data / 'state.json').read_bytes()
        created = stage.create_profiles(self.probe)
        layout = profiles.Layout(self.data)
        self.assertEqual([port for _, port in created], [18000, 18001])
        view = profiles.read_index(layout.index)
        self.assertEqual([(e.id, e.label, e.port) for e in view.entries],
                         [(created[0][0], 'Probe B', 18000), (created[1][0], 'Probe C', 18001)])
        seen = {self.default.token, self.default.child_token}
        for profile_id, _ in created:
            store = ProductStore(layout.profile(profile_id), 'emqx', existing_only=True)
            try:
                state = store.load()
            finally:
                store.close()
            self.assertEqual(state.connection.model_dump(), self.default.connection.model_dump())
            self.assertEqual((state.disabled, state.writes_enabled, state.enabled_write_tools),
                             (self.default.disabled, self.default.writes_enabled, self.default.enabled_write_tools))
            self.assertTrue(seen.isdisjoint({state.token, state.child_token}))
            seen |= {state.token, state.child_token}
        self.assertEqual((self.data / 'state.json').read_bytes(), before)  # the default profile is never written
        made = [layout.index, layout.profiles, *layout.profiles.rglob('*')]
        identities = {(os.lstat(path).st_dev, os.lstat(path).st_ino) for path in made}
        self.assertEqual(set(self.os.owners), identities)  # every entry it made, and nothing else
        self.assertEqual(set(self.os.owners.values()), {RUNTIME})
        found = stage.credentials(self.data, created)
        self.assertEqual([(label, port) for label, port, _, _ in found],
                         [('default', 3000), (created[0][0][:8], 18000), (created[1][0][:8], 18001)])
        self.assertEqual(len({token for _, _, token, _ in found} | {child for _, _, _, child in found}), 6)

    def test_a_default_profile_without_a_backend_is_no_fixture(self):
        store = ProductStore(self.data, 'emqx')
        store.update(connection=None)
        store.close()
        with self.assertRaisesRegex(AssertionError, 'no backend to share'):
            stage.create_profiles(self.probe)
        self.assertFalse(profiles.Layout(self.data).index.exists())

    def test_kept_bytes_are_every_state_the_index_and_the_record(self):
        created = stage.create_profiles(self.probe)
        private_file(self.data / profiles.INSTANCE_RECORD_NAME, b'{"record": true}')
        kept = stage.kept_bytes(self.data, created)
        self.assertEqual(sorted(kept), sorted(['state.json', *(f'profiles/{p}/state.json' for p, _ in created),
                                               profiles.INDEX_NAME, profiles.INSTANCE_RECORD_NAME]))


class RestoreDetectionTests(unittest.TestCase):
    """detect_as_runtime: restore_detect.detect in a process of its own (the runtime user's in the container)."""

    def test_the_sentinel_is_made_kept_and_then_seen_restored(self):
        data = private_dir(temporary(self) / 'mcp')

        def detect():
            return stage.detect_as_runtime(data, user=None)
        self.assertEqual(detect(), stage.detected(False, restore_detect.ESTABLISHED))
        self.assertEqual(sorted(os.listdir(data)), [profiles.INSTANCE_RECORD_NAME, profiles.SENTINEL_NAME])
        self.assertEqual(detect(), stage.detected(False, restore_detect.CONSISTENT))
        (data / profiles.SENTINEL_NAME).chmod(0o644)  # any chmod or chown changes the ctime, as a restore does
        (data / profiles.SENTINEL_NAME).chmod(0o600)
        self.assertEqual(detect(), stage.detected(False, restore_detect.MISMATCH))
        private_file(data / profiles.RESTORE_MARKER_NAME, b'')
        self.assertEqual(detect(), stage.detected(True, restore_detect.MISMATCH))

    def test_profile_data_before_the_sentinel_is_a_restore(self):
        data = private_dir(temporary(self) / 'mcp')
        private_file(data / profiles.INDEX_NAME)
        self.assertEqual(stage.detect_as_runtime(data, user=None), stage.detected(False, restore_detect.RECORD_MISSING))

    def test_the_runtime_user_and_no_other_group_run_it_in_the_container(self):
        calls = []

        def run(*args, **kwargs):
            calls.append(kwargs)
            return subprocess.CompletedProcess(args, 0, '{"marker": false, "active": true, "sentinel": "consistent"}', '')
        with patch.object(stage.subprocess, 'run', run):
            stage.detect_as_runtime(Path('/data/mcp'))
        self.assertEqual({key: calls[0][key] for key in ('user', 'group', 'extra_groups', 'cwd')},
                         {'user': 10001, 'group': 10001, 'extra_groups': [], 'cwd': '/'})
        self.assertEqual(set(calls[0]['env']), {'PATH', 'PYTHONDONTWRITEBYTECODE', 'PYTHONPATH'})

    def test_the_marker_of_the_single_profile_stage_is_ended_once(self):
        data = private_dir(temporary(self) / 'mcp')
        private_file(data / profiles.RESTORE_MARKER_NAME, b'')
        stage.end_restore_marker(data)
        self.assertFalse((data / profiles.RESTORE_MARKER_NAME).exists())
        with self.assertRaisesRegex(AssertionError, 'left no marker'):
            stage.end_restore_marker(data)


TCP_HEADER = '  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n'


def tcp_row(address, port, state='0A'):
    return f'   0: {address}:{port:04X} 00000000:0000 {state} 00000000:00000000 00:00000000 00000000 10001 0 1 1\n'


class FakeProc:
    """A /proc of the candidate container: processes (command line, oom_score_adj, nice) and the TCP listeners."""

    def __init__(self, test):
        self.root = temporary(test) / 'proc'
        (self.root / 'net').mkdir(parents=True)
        self.listening = {}  # port -> address hex
        self.write_net()

    def process(self, pid, argv, adj=0, nice=0):
        directory = self.root / str(pid)
        directory.mkdir(exist_ok=True)
        (directory / 'cmdline').write_bytes(b''.join(value.encode() + b'\0' for value in argv))
        (directory / 'oom_score_adj').write_text(f'{adj}\n')
        (directory / 'stat').write_text(f'{pid} (odd) 7 (python) S ' + ' '.join(['0'] * 15 + [str(nice)] + ['0'] * 5))

    def gone(self, pid):
        for name in ('cmdline', 'oom_score_adj', 'stat'):
            (self.root / str(pid) / name).unlink()
        (self.root / str(pid)).rmdir()

    def listen(self, port, address='0100007F'):
        self.listening[port] = address
        self.write_net()

    def close(self, port):
        self.listening.pop(port, None)
        self.write_net()

    def write_net(self):
        rows = ''.join(tcp_row(address, port) for port, address in self.listening.items())
        (self.root / 'net' / 'tcp').write_text(TCP_HEADER + rows + tcp_row('0100007F', 8081, '01'))


def child(port=None):
    return ['/opt/woow/apps/x/.venv/bin/python', 'launch.py', '--host', '127.0.0.1',
            *(() if port is None else ('--port', str(port)))]


class RunningChildrenTests(unittest.TestCase):
    """What the stage reads of the running add-on: its children's ports, listeners and resources (HM-09)."""

    def setUp(self):
        self.proc = FakeProc(self)
        self.pids = []
        self.probe = SimpleNamespace(children=lambda process: [str(pid) for pid in self.pids])
        self.process = Mock(pid=1, **{'poll.return_value': None})
        self.proc.process(1, ['/opt/woow/.venv/bin/python', 'management_launcher.py'])

    def spawn(self, pid, port, **resources):
        self.proc.process(pid, child(port), **resources)
        self.pids.append(pid)

    def test_a_child_s_port_is_its_command_line_s(self):
        self.assertEqual(stage.child_port(child(18000)), 18000)
        self.assertEqual(stage.child_port(['x', '--port=18001']), 18001)
        for argv in (child(), ['x', '--port'], ['x', '--port', 'abc'], ['x', '--port=']):
            self.assertIsNone(stage.child_port(argv))

    def test_children_by_port_leave_out_the_gone_and_the_unreaped(self):
        self.spawn(10, None)  # the default child of Hermes and OpenDesign names no port
        self.spawn(11, 18000)
        self.spawn(12, 18001)
        self.proc.process(13, [])  # a zombie's command line is empty
        self.pids += [13, 14]  # 14 is gone already
        self.assertEqual(stage.child_ports(self.probe, self.process, self.proc.root), {3000: 10, 18000: 11, 18001: 12})
        self.spawn(15, 18000)
        with self.assertRaisesRegex(AssertionError, 'two children on one port'):
            stage.child_ports(self.probe, self.process, self.proc.root)

    def test_listeners_are_every_listening_socket_by_port(self):
        self.proc.listen(3000)
        self.proc.listen(18000, '00000000')
        self.assertEqual(stage.listeners(self.proc.root), {3000: ['0100007F'], 18000: ['00000000']})
        (self.proc.root / 'net' / 'tcp6').write_text(TCP_HEADER + tcp_row('0' * 32, 18001))
        self.assertEqual(stage.listeners(self.proc.root)[18001], ['0' * 32])

    def test_profiles_are_up_once_each_child_listens_on_loopback_only(self):
        self.spawn(10, 3000)
        self.spawn(11, 18000)
        self.proc.listen(3000)

        async def up(timeout=.25):
            return await stage.profiles_up(self.probe, self.process, [3000, 18000], timeout=timeout,
                                           proc=self.proc.root, pause=.01)
        with self.assertRaisesRegex(AssertionError, r'^children up on \[3000\] of \[3000, 18000\]$'):
            asyncio.run(up())
        self.proc.listen(18000, '00000000')  # a child on every address is not up
        with self.assertRaisesRegex(AssertionError, r'^children up on \[3000\] of \[3000, 18000\]$'):
            asyncio.run(up())
        self.proc.listen(18000)
        self.assertEqual(asyncio.run(up()), {3000: 10, 18000: 11})
        self.process.poll.return_value = 1
        with self.assertRaisesRegex(AssertionError, 'packaged entrypoint exited'):
            asyncio.run(up())

    def test_an_additional_child_is_raised_by_five_and_scored_500_the_default_keeps_the_management_s(self):
        for management in ((0, 0), (200, 2)):  # HA gives an add-on oom_score_adj 200
            with self.subTest(management=management):
                adj, nice = management
                self.proc.process(1, ['management'], adj, nice)
                self.proc.process(10, child(3000), adj, nice)
                self.proc.process(11, child(18000), 500, nice + 5)
                stage.check_resources(self.process, {3000: 10, 18000: 11}, self.proc.root)
                self.proc.process(11, child(18000), 500, 5 if nice else 0)  # set to 5, or not raised
                with self.assertRaisesRegex(AssertionError, 'additional child resources not applied'):
                    stage.check_resources(self.process, {3000: 10, 18000: 11}, self.proc.root)
                self.proc.process(11, child(18000), 500, nice + 5)
                self.proc.process(10, child(3000), 500, nice)
                with self.assertRaisesRegex(AssertionError, 'default child resources changed'):
                    stage.check_resources(self.process, {3000: 10, 18000: 11}, self.proc.root)


class KillTests(unittest.TestCase):
    """kill_one (T-13): the killed child comes back with a new PID; every other child keeps its PID."""

    def setUp(self):
        self.proc = FakeProc(self)
        self.pids = [10, 11, 12]
        for pid, port in zip(self.pids, (3000, 18000, 18001)):
            self.proc.process(pid, child(port))
            self.proc.listen(port)
        self.probe = SimpleNamespace(children=lambda process: [str(pid) for pid in self.pids])
        self.process = Mock(pid=1, **{'poll.return_value': None})
        self.killed = []

    def restart(self, old, new, port):
        self.pids.remove(old)
        self.proc.gone(old)
        self.proc.close(port)
        self.proc.process(new, child(port))
        self.pids.append(new)
        self.proc.listen(port)

    def kill(self, then=None):
        def kill(pid, sig):
            self.killed.append((pid, sig))
            if then:
                then()
        return kill

    def run_kill(self, kill, timeout=.25):
        return asyncio.run(stage.kill_one(self.probe, self.process, 18000, timeout=timeout, proc=self.proc.root,
                                          kill=kill, pause=.01))

    def test_only_the_named_child_is_killed_and_it_starts_again(self):
        self.assertEqual(self.run_kill(self.kill(lambda: self.restart(11, 21, 18000))), {3000: 10, 18000: 21, 18001: 12})
        self.assertEqual(self.killed, [(11, signal.SIGKILL)])

    def test_another_child_restarted_fails(self):
        def both():
            self.restart(11, 21, 18000)
            self.restart(12, 22, 18001)
        with self.assertRaisesRegex(AssertionError, "another profile's child was restarted"):
            self.run_kill(self.kill(both))

    def test_a_child_that_never_comes_back_times_out(self):
        def gone():
            self.pids.remove(11)
            self.proc.gone(11)
            self.proc.close(18000)
        with self.assertRaisesRegex(AssertionError, '^the child on 18000 did not start again$'):
            self.run_kill(self.kill(gone))


class Process:
    """The add-on process as stop_within sees it."""

    def __init__(self, waited=None, returncode=0):
        self.waited, self.returncode, self.signals = waited, returncode, []
        self.pid = 1

    def send_signal(self, sig):
        self.signals.append(sig)

    def wait(self, timeout=None):
        if self.waited is not None and timeout is not None:
            raise subprocess.TimeoutExpired('runtime', timeout)

    def kill(self):
        self.signals.append(signal.SIGKILL)
        self.waited = None


class StopTests(unittest.TestCase):
    """stop_within (plan 5.4, contract 7): SIGTERM, exit 0 within HA's 30 s, every child reaped."""

    def setUp(self):
        self.proc = FakeProc(self)
        self.probe = SimpleNamespace(children=lambda process: ['10', '11'])

    def clock(self, *times):
        values = iter(times)
        return lambda: next(values)

    def test_a_stop_within_30_s_is_measured(self):
        process = Process()
        self.assertEqual(stage.stop_within(self.probe, process, clock=self.clock(100.0, 104.5), proc=self.proc.root),
                         4.5)
        self.assertEqual(process.signals, [signal.SIGTERM])

    def test_a_late_failed_or_orphaning_stop_fails(self):
        cases = (
            (Process(waited=True), self.clock(0.0, 0.0), "over HA's 30 s"),
            (Process(), self.clock(0.0, 30.0), "over HA's 30 s"),
            (Process(returncode=1), self.clock(0.0, 1.0), 'shutdown failed'),
        )
        for process, clock, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(AssertionError, message):
                stage.stop_within(self.probe, process, clock=clock, proc=self.proc.root)
        self.proc.process(11, child(18000))
        with self.assertRaisesRegex(AssertionError, 'orphan child'):
            stage.stop_within(self.probe, Process(), clock=self.clock(0.0, 1.0), proc=self.proc.root)


class Gateway(ThreadingHTTPServer):
    """8081 of a switched-on add-on, as the routing check sees it: a token chooses the profile on both connection
    methods and that profile's child opens the session (the gateway hands out the child's own session id); a session
    belongs to the profile whose token opened it; faults break one rule each ('swaps children': the two additional
    profiles are served by each other's child, every other rule kept)."""

    def __init__(self, tokens, faults=()):
        super().__init__(('127.0.0.1', 0), GatewayHandler)
        self.tokens, self.faults, self.sessions, self.lock = dict(tokens), set(faults), {}, threading.Lock()
        self.route = {label: label for label in self.tokens.values()}  # profile -> the child its requests reach
        if 'swaps children' in self.faults:
            self.route[A[:8]], self.route[B[:8]] = B[:8], A[:8]
        threading.Thread(target=self.serve_forever, args=(.05,), daemon=True).start()  # a quick shutdown

    @property
    def base(self):
        return f'http://127.0.0.1:{self.server_address[1]}'


class GatewayHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def answer(self, status, body=None, headers=()):
        raw = b'' if body is None else json.dumps(body).encode()
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def token(self):
        faults = self.server.faults
        if self.path == '/mcp':
            value = self.headers.get('Authorization', '')
            token = value[7:] if value.startswith('Bearer ') else None
            if token is not None and token not in self.server.tokens and 'serves an unknown bearer' in faults:
                return token
        else:
            match = re.fullmatch(r'/private_([A-Za-z0-9_-]{43})/mcp', self.path)
            token = match.group(1) if match else None
            if token is not None and 'refuses the secret url' in faults:
                return None
            if token is not None and token not in self.server.tokens and 'serves an unknown secret url' in faults:
                return token
        return token if token in self.server.tokens else None

    def refused(self):
        self.answer(401 if self.path == '/mcp' else 404)

    def owned(self, token):
        session = self.headers.get('Mcp-Session-Id')
        owner = self.server.sessions.get(session)
        return owner is not None and (owner[0] == token or 'crosses sessions' in self.server.faults), session

    def do_POST(self):
        message = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        token = self.token()
        if token is None:
            return self.refused()
        if message['method'] == 'initialize':
            prefix = 'woow-local-' if 'answers itself' in self.server.faults else 'child-'
            session = prefix + secrets.token_hex(8)
            child = self.server.route.get(self.server.tokens.get(token))  # None: an unknown token served by a fault
            with self.server.lock:
                self.server.sessions[session] = (token, child)
            return self.answer(200, {'jsonrpc': '2.0', 'id': message['id'], 'result': {
                'protocolVersion': '2025-03-26', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'fake'}}},
                [('Mcp-Session-Id', session)])
        owned, _ = self.owned(token)
        if not owned:
            return self.answer(404)
        if message['method'] == 'notifications/initialized':
            return self.answer(202)
        names = ['a', 'b']
        if 'differs' in self.server.faults and self.server.tokens.get(token) != 'default':
            names = ['a']
        self.answer(200, {'jsonrpc': '2.0', 'id': message['id'], 'result': {'tools': [{'name': n} for n in names]}})

    def do_DELETE(self):
        token = self.token()
        if token is None:
            return self.refused()
        owned, session = self.owned(token)
        if not owned or 'keeps sessions' in self.server.faults:
            return self.answer(404)
        with self.server.lock:
            self.server.sessions.pop(session, None)
        self.answer(200)


class ProfileChild(ThreadingHTTPServer):
    """A profile's child, asked straight by the routing check: it serves its own child bearer only, and knows only the
    sessions the gateway opened with it (any other session id: 404, as the MCP SDK answers an unknown session)."""

    def __init__(self, gateway, label, child_token):
        super().__init__(('127.0.0.1', 0), ProfileChildHandler)
        self.gateway, self.label, self.child_token = gateway, label, child_token
        threading.Thread(target=self.serve_forever, args=(.05,), daemon=True).start()  # a quick shutdown

    @property
    def port(self):
        return self.server_address[1]


class ProfileChildHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        message = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        child, body = self.server, None
        if self.headers.get('Authorization') != 'Bearer ' + child.child_token:
            status = 401
        else:
            owner = child.gateway.sessions.get(self.headers.get('Mcp-Session-Id'))
            known = owner is not None and (owner[1] == child.label or 'a child knows every session' in child.gateway.faults)
            status = 200 if known else 404
            body = {'jsonrpc': '2.0', 'id': message['id'], 'result': {}} if known else None
        raw = b'' if body is None else json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class RoutingTests(unittest.TestCase):
    """check_routing (T-05): each token its own profile on both connection methods and its session its own child's,
    sessions never cross profiles, an unknown token refused; every session it opened is ended, also when it fails."""

    def setUp(self):
        self.labels = ('default', A[:8], B[:8])
        self.tokens = {secrets.token_urlsafe(32): label for label in self.labels}
        self.child_tokens = {label: secrets.token_urlsafe(32) for label in self.labels}

    def check(self, faults=()):
        gateway = Gateway(self.tokens, faults)
        self.addCleanup(gateway.server_close)
        self.addCleanup(gateway.shutdown)
        children = {label: ProfileChild(gateway, label, self.child_tokens[label]) for label in self.labels}
        for child in children.values():
            self.addCleanup(child.server_close)
            self.addCleanup(child.shutdown)
        found = [(label, children[label].port, token, self.child_tokens[label]) for token, label in self.tokens.items()]

        async def run():
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                await stage.check_routing(client, found, stage.initialize_message(), base=gateway.base)
        try:
            asyncio.run(run())
        finally:
            self.left = dict(gateway.sessions)

    def secrets_in(self, text):
        return any(value in text for value in [*self.tokens, *self.child_tokens.values()])

    def test_isolated_profiles_pass_and_every_session_is_ended(self):
        self.check()
        self.assertEqual(self.left, {})

    def test_each_broken_rule_fails_without_naming_a_token(self):
        for fault, message in (('crosses sessions', 'session served with the token of'),
                               ('answers itself', 'no child answered its initialize'),
                               ('swaps children', "its session is not its own child's"),
                               ('a child knows every session', 'knows its session'),
                               ('serves an unknown bearer', 'unknown Bearer token served'),
                               ('serves an unknown secret url', 'unknown secret URL served'),
                               ('refuses the secret url', 'its token opened no session'),
                               ('differs', 'policy differs'),
                               ('keeps sessions', 'its session was not ended')):
            with self.subTest(fault=fault):
                with self.assertRaisesRegex(AssertionError, message) as failed:
                    self.check({fault})
                self.assertFalse(self.secrets_in(str(failed.exception)))
                if fault != 'keeps sessions':
                    self.assertEqual(self.left, {})  # ended, also on a failure

    def test_a_swap_names_the_profile_whose_session_another_child_holds(self):
        """Review SF-1 (experiment X1): B and C served by each other's child keep every other rule; only asking each
        child straight sees it."""
        with self.assertRaisesRegex(AssertionError, f"^{A[:8]}: its session is not its own child's$"):
            self.check({'swaps children'})


class ChildHandler(BaseHTTPRequestHandler):
    """A profile's child on a private port: serves its own child bearer only, unless it also takes another's."""

    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        value = self.headers.get('Authorization')
        if value not in ('Bearer ' + token for token in self.server.accepts):
            self.send_response(401)
            self.send_header('Content-Length', '0')
            return self.end_headers()
        raw = json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {'protocolVersion': '2025-03-26', 'capabilities': {},
                                                                'serverInfo': {'name': 'fake'}}}).encode()
        self.send_response(200)
        for name, item in (('Content-Type', 'application/json'), ('Mcp-Session-Id', 'child-1'),
                           ('Content-Length', str(len(raw)))):
            self.send_header(name, item)
        self.end_headers()
        self.wfile.write(raw)

    def do_DELETE(self):
        self.send_response(200 if self.headers.get('Authorization') == 'Bearer ' + self.server.accepts[0] else 401)
        self.send_header('Content-Length', '0')
        self.end_headers()


class ChildBearerTests(unittest.TestCase):
    """check_child_bearers (T-23; HM-06's assert_child_bearer on each child, and every other profile's child token)."""

    def children(self, also=False):
        tokens = [secrets.token_urlsafe(32) for _ in range(3)]
        found = []
        for number, own in enumerate(tokens):
            server = ThreadingHTTPServer(('127.0.0.1', 0), ChildHandler)
            server.accepts = [own, *([tokens[0]] if also and number == 2 else [])]
            threading.Thread(target=server.serve_forever, args=(.05,), daemon=True).start()  # a quick shutdown
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            found.append((('default', A[:8], B[:8])[number], server.server_address[1], own))
        return found, tokens

    def check(self, children):
        async def run():
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                await stage.check_child_bearers(probe, client, children, stage.initialize_message())
        asyncio.run(run())

    def test_children_serving_only_their_own_bearer_pass(self):
        self.check(self.children()[0])

    def test_a_child_serving_another_profile_s_child_bearer_fails_without_naming_it(self):
        children, tokens = self.children(also=True)
        with self.assertRaisesRegex(AssertionError, f'{B[:8]}: child served the child token of default') as failed:
            self.check(children)
        self.assertFalse(any(token in str(failed.exception) for token in tokens))


class Each:
    """A replaced step's results, one for each call in turn."""

    def __init__(self, *values):
        self.values = list(values)


ESTABLISHED = stage.detected(False, restore_detect.ESTABLISHED)
CONSISTENT = stage.detected(False, restore_detect.CONSISTENT)
RESTORED = stage.detected(True, restore_detect.MISMATCH)  # both restore signals: the marker and the sentinel


class StageTests(unittest.TestCase):
    """stage(): the order of its steps (the module docstring) with every step replaced, what each step is given, and
    the stage's own verdicts (HM-16 review MF-1: the sentinel established by the fixture and untouched by the runtime,
    the restored bytes kept, both restore signals seen); a failure still stops the runtime it started."""

    def run_stage(self, fail=None, verdicts=(ESTABLISHED, CONSISTENT, RESTORED), kept=None, app='odoo'):
        """(events, the replaced steps' calls {name: [(args, kwargs)]}, failure messages, the stage's inputs)."""
        events, calls, failures = [], {}, []
        process = Mock(**{'poll.return_value': None})

        def record(name, result=None):
            def step(*args, **kwargs):
                events.append(name)
                calls.setdefault(name, []).append((args, kwargs))
                if name == fail:
                    raise AssertionError(name + ' failed')
                return result.values.pop(0) if isinstance(result, Each) else result
            return step

        def arecord(name, result=None):
            sync = record(name, result)

            async def step(*args, **kwargs):
                return sync(*args, **kwargs)
            return step
        found = [(label, port, secrets.token_urlsafe(32), secrets.token_urlsafe(32))
                 for label, port in (('default', 3000), (A[:8], 18000), (B[:8], 18001))]
        created, pids = [(A, 18000), (B, 18001)], {3000: 10, 18000: 11, 18001: 12}
        fake = SimpleNamespace(APP=app, DATA=Path('/data/mcp'), start=record('start', process),
                               ready_listener=arecord('ready'), stop=record('stop'),
                               restore_as_supervisor=record('restore', (['state.json'], b'S')),
                               check_restored_start=record('repaired'))
        replaced = {'end_restore_marker': record('end marker'), 'detect_as_runtime': record('detect', Each(*verdicts)),
                    'create_profiles': record('create', created),
                    'credentials': record('credentials', found), 'profiles_up': arecord('up', pids),
                    'check_routing': arecord('routing'), 'check_child_bearers': arecord('child bearers'),
                    'check_resources': record('resources'), 'kill_one': arecord('kill'),
                    'initialize_on': arecord('served again', (200, 'child-1', '2025-03-26')),
                    'end_session': arecord('ended', 200), 'stop_within': record('stop within 30 s', 1.5),
                    'tree_snapshot': record('tree', {'state.json': ()}),
                    'kept_bytes': record('kept', Each(*(kept or ({'state.json': b'S'}, {'state.json': b'S'}))))}
        with patch.multiple(stage, **replaced), patch('builtins.print'):
            try:
                asyncio.run(stage.stage(fake, 'client'))
            except AssertionError as error:
                events.append('failed')
                failures.append(str(error))
        inputs = SimpleNamespace(fake=fake, process=process, found=found, created=created, pids=pids)
        return events, calls, failures, inputs

    def assert_every_start_stopped(self, events):
        self.assertEqual(events.count('start'), events.count('stop') + events.count('stop within 30 s'))

    def test_the_steps_run_in_order(self):
        events, _, failures, _ = self.run_stage()
        self.assertEqual(failures, [])
        self.assertEqual(events, [
            'end marker', 'detect', 'create', 'credentials', 'start', 'ready', 'up', 'routing', 'child bearers',
            'resources', 'kill', 'served again', 'ended', 'stop within 30 s', 'detect', 'tree', 'kept', 'restore',
            'start', 'ready', 'repaired', 'kept', 'up', 'stop within 30 s', 'detect'])

    def test_every_step_is_given_all_three_profiles_and_the_kill_an_additional_one(self):
        _, calls, failures, given = self.run_stage()
        self.assertEqual(failures, [])
        data, ports = Path('/data/mcp'), [3000, 18000, 18001]

        def args(name):
            return [arguments for arguments, _ in calls[name]]
        self.assertEqual(args('detect'), [(data,)] * 3)
        self.assertEqual(args('create'), [(given.fake,)])
        self.assertEqual(args('credentials'), [(data, given.created)])
        self.assertEqual(args('up'), [(given.fake, given.process, ports)] * 2)  # every child, both starts
        self.assertEqual(args('routing'), [('client', given.found, stage.initialize_message())])
        self.assertEqual(args('child bearers'), [(given.fake, 'client',
                                                  [(label, port, child) for label, port, _, child in given.found],
                                                  stage.initialize_message())])
        self.assertEqual(args('resources'), [(given.process, given.pids)])
        token = given.found[1][2]
        self.assertEqual(args('kill'), [(given.fake, given.process, 18000)])  # an additional profile's child, not 3000
        bearer = {'Authorization': 'Bearer ' + token}
        self.assertEqual(args('served again'), [('client', stage.MCP + '/mcp', bearer, stage.initialize_message())])
        self.assertEqual(args('ended'), [('client', stage.MCP + '/mcp', bearer, 'child-1', '2025-03-26')])
        self.assertEqual(args('stop within 30 s'), [(given.fake, given.process)] * 2)
        self.assertEqual(args('kept'), [(data, given.created)] * 2)
        self.assertEqual(args('repaired'), [(['state.json'], b'S')])

    def test_a_sentinel_the_fixture_did_not_establish_fails_before_anything_starts(self):
        for first in (CONSISTENT, RESTORED, stage.detected(False, restore_detect.MISMATCH),
                      stage.detected(False, restore_detect.RECORD_MISSING)):
            with self.subTest(first=first):
                events, _, failures, _ = self.run_stage(verdicts=(first, CONSISTENT, RESTORED))
                self.assertEqual(failures, ['sentinel not established'])
                self.assertEqual(events, ['end marker', 'detect', 'failed'])  # no profile data, no start

    def test_a_sentinel_the_runtime_touched_fails_once_it_stopped(self):
        """A chmod of the sentinel (mismatch: its ctime), or a marker, after the first start: no restore follows."""
        for second in (stage.detected(False, restore_detect.MISMATCH), stage.detected(True, restore_detect.CONSISTENT),
                       RESTORED):
            with self.subTest(second=second):
                events, _, failures, _ = self.run_stage(verdicts=(ESTABLISHED, second, RESTORED))
                self.assertEqual(failures, ['sentinel touched by the runtime'])
                self.assertEqual(events[-3:], ['stop within 30 s', 'detect', 'failed'])
                self.assertNotIn('restore', events)
                self.assert_every_start_stopped(events)

    def test_a_restore_not_seen_by_both_signals_fails(self):
        for third in (stage.detected(False, restore_detect.MISMATCH), stage.detected(True, restore_detect.CONSISTENT),
                      CONSISTENT):
            with self.subTest(third=third):
                events, _, failures, _ = self.run_stage(verdicts=(ESTABLISHED, CONSISTENT, third))
                self.assertEqual(failures, ['restore not seen by both signals'])
                self.assertEqual(events.count('start'), 2)
                self.assert_every_start_stopped(events)

    def test_restored_profile_data_rewritten_fails_and_stops_the_runtime(self):
        events, _, failures, _ = self.run_stage(kept=({'state.json': b'S'}, {'state.json': b'T'}))
        self.assertEqual(failures, ['restored profile data rewritten'])
        self.assertEqual(events[-3:], ['kept', 'stop', 'failed'])
        self.assertEqual(events.count('up'), 1)  # the restored start's children are never waited for
        self.assert_every_start_stopped(events)

    def test_a_failed_step_stops_the_runtime_it_started(self):
        events, _, _, _ = self.run_stage(fail='routing')
        self.assertEqual(events[-2:], ['stop', 'failed'])
        self.assert_every_start_stopped(events)
        events, _, _, _ = self.run_stage(fail='repaired')
        self.assertEqual(events[-2:], ['stop', 'failed'])
        self.assertEqual(events.count('restore'), 1)
        self.assert_every_start_stopped(events)

    def test_n8n_is_refused_before_anything_changes(self):
        """Review SF-2: n8n's children name their port in their environment only (HM-25)."""
        events, _, failures, _ = self.run_stage(app='n8n')
        self.assertEqual((events, failures), (['failed'], ["n8n's children name their port in their environment only "
                                                           '(HM-25)']))


if __name__ == '__main__':
    unittest.main()
