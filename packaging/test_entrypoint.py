"""Bootstrap tests use owned temporary directories only, never real /data."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import call, patch

import entrypoint as e

REAL_CHOWN = os.chown  # tests that plant foreign owners must bypass the recording spies


class BootstrapTests(unittest.TestCase):
    def test_new_directory_and_second_boot(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            # Test filesystem operations with this test user's actual uid/gid.
            with patch.object(e, 'UID', os.getuid()), patch.object(e, 'GID', os.getgid()):
                e.prepare_data(parent)
                state = parent / 'mcp' / 'fixture-state'
                state.write_bytes(b'owned-test-state')
                e.prepare_data(parent)
                self.assertEqual(state.read_bytes(), b'owned-test-state')
                self.assertEqual((parent / 'mcp').stat().st_mode & 0o777, 0o700)

    def test_symlink_parent_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'target').mkdir()
            (root / 'alias').symlink_to(root / 'target', target_is_directory=True)
            with self.assertRaises(OSError):
                e.prepare_data(root / 'alias')
            self.assertFalse((root / 'target/mcp').exists())

    def test_symlink_child_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'target'
            target.mkdir(mode=0o755)
            (root / 'mcp').symlink_to(target, target_is_directory=True)
            before = target.stat()
            with self.assertRaises(OSError):
                e.prepare_data(root)
            after = target.stat()
            self.assertEqual((before.st_uid, before.st_gid, before.st_mode), (after.st_uid, after.st_gid, after.st_mode))

    def test_existing_wrong_mode_or_owner_not_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / 'mcp'
            child.mkdir(mode=0o755)
            with patch.object(e, 'UID', os.getuid()), patch.object(e, 'GID', os.getgid()):
                with self.assertRaises(RuntimeError):
                    e.prepare_data(root)
            self.assertEqual(child.stat().st_mode & 0o777, 0o755)
            child.chmod(0o700)
            foreign = os.getuid()
            if os.geteuid() == 0:  # root-owned is the HA-restore case; use an owner that is neither
                foreign = 4242
                os.chown(child, foreign, foreign)
            with patch.object(e, 'UID', os.getuid() + 1), self.assertRaises(RuntimeError):
                e.prepare_data(root)
            self.assertEqual(child.stat().st_uid, foreign)

    def test_command_override_refused_before_filesystem_access(self):
        with patch.object(e.sys, 'argv', ['entrypoint.py', 'n8n', '/bin/sh']), patch.object(e, 'prepare_data') as prepare:
            with self.assertRaises(RuntimeError):
                e.main()
            prepare.assert_not_called()

    def bootstrap_exec(self, product, source_env):
        calls = []
        fake_libc = type('Libc', (), {'prctl': lambda *args: 0})()
        # No actual process identity or current-directory changes in unit tests.
        with patch.object(e.sys, 'argv', ['entrypoint.py', product]), \
             patch.object(e.os, 'environ', source_env), \
             patch.object(e, 'prepare_data'), patch.object(e.os, 'umask'), \
             patch.object(e.os, 'geteuid', side_effect=[0, 10001]), \
             patch.object(e.os, 'getuid', return_value=10001), \
             patch.object(e.os, 'getgid', return_value=10001), \
             patch.object(e.os, 'setgroups', side_effect=lambda x: calls.append(('groups', x))), \
             patch.object(e.os, 'setgid', side_effect=lambda x: calls.append(('gid', x))), \
             patch.object(e.os, 'setuid', side_effect=lambda x: calls.append(('uid', x))), \
             patch.object(e.ctypes, 'CDLL', return_value=fake_libc), \
             patch.object(e.os, 'chdir'), patch.object(e.os, 'execve') as execute:
            e.main()
        self.assertEqual(calls, [('groups', []), ('gid', 10001), ('uid', 10001)])
        return execute.call_args.args

    def test_fixed_exec_after_privilege_drop(self):
        path, argv, env = self.bootstrap_exec('emqx', {})
        self.assertEqual(path, '/opt/woow/.venv/bin/python')
        self.assertEqual(argv, [path, '/opt/woow/packaging/management_launcher.py', 'emqx'])
        self.assertEqual(set(env), {'PATH', 'HOME', 'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE', 'PYTHONUNBUFFERED'})
        self.assertNotIn('SUPERVISOR_TOKEN', env)

    def test_runtime_token_passthrough_only(self):
        # Replace environ itself: never inspect/copy the test runner environment.
        # All eight management verifiers are approved (n8n 2026-10-04, the other six 2026-10-05, Nextcloud 2026-10-08).
        dummy = 'INVENTED-PACKAGING-ONLY-NOT-A-CREDENTIAL'
        for product in e.PRODUCTS:
            with self.subTest(product=product):
                source = {'SUPERVISOR_TOKEN': dummy, 'HASSIO_TOKEN': 'invented-legacy',
                          'HTTP_PROXY': 'http://example.invalid', 'PYTHONPATH': '/untrusted',
                          'HA_ROLE_URL': 'ws://example.invalid', 'HA_ROLE_METHOD': 'auth/list'}
                path, argv, env = self.bootstrap_exec(product, source)
                self.assertEqual(path, '/opt/woow/.venv/bin/python')
                self.assertEqual(argv, [path, '/opt/woow/packaging/management_launcher.py', product])
                self.assertEqual(env, {
                    'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/data/mcp',
                    'PYTHONPATH': '/opt/woow/packages/mcp-admin-core:/opt/woow/apps/n8n',
                    'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
                    'SUPERVISOR_TOKEN': dummy})
                self.assertNotIn(dummy, argv)
                self.assertEqual(source['SUPERVISOR_TOKEN'], dummy)

    def test_missing_or_empty_token_is_not_synthesized(self):
        for product in e.PRODUCTS:
            for source in ({}, {'SUPERVISOR_TOKEN': ''}):
                with self.subTest(product=product, source=source):
                    _, _, env = self.bootstrap_exec(product, source)
                    self.assertNotIn('SUPERVISOR_TOKEN', env)

    def test_only_the_token_is_read_from_the_environment(self):
        class OnlyToken(dict):
            def get(self, key, *default):
                assert key == 'SUPERVISOR_TOKEN', key
                return dict.get(self, key, *default)

            def __getitem__(self, key):
                raise AssertionError('bootstrap must not index the environment')

        for product in e.PRODUCTS:
            with self.subTest(product=product):
                _, _, env = self.bootstrap_exec(product, OnlyToken(SUPERVISOR_TOKEN='INVENTED-ONLY', HASSIO_TOKEN='x'))
                self.assertEqual(env['SUPERVISOR_TOKEN'], 'INVENTED-ONLY')


def restored_tree(root):
    """The shape Home Assistant left after a partial restore: dir 0700, files 0644, owner = extractor."""
    child = root / 'mcp'
    child.mkdir(mode=0o700)
    for name in ('state.json', '.writer.lock'):
        (child / name).write_bytes(b'{"restored": true}' if name == 'state.json' else b'')
        (child / name).chmod(0o644)
    (child / 'sub').mkdir(mode=0o755)
    (child / 'sub' / 'nested').write_bytes(b'n')
    return child


class RestoredStateTests(unittest.TestCase):
    """The current user plays the restore owner; the runtime user is someone else; fchown is recorded."""

    def refused(self, build, expected='', **limits):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = restored_tree(root)
            build(root, child)
            calls = []
            with patch.object(e, 'RESTORE_OWNER', (os.getuid(), os.getgid())), \
                 patch.object(e, 'UID', os.getuid() + 1), patch.object(e, 'GID', os.getgid() + 1), \
                 patch.object(e.os, 'geteuid', return_value=0), \
                 patch.object(e.os, 'fchown', side_effect=lambda *a: calls.append(a)), \
                 patch.object(e.os, 'fchmod', side_effect=lambda *a: calls.append(a)), \
                 patch.object(e.os, 'chown', side_effect=lambda *a: calls.append(a)), \
                 patch.object(e.os, 'chmod', side_effect=lambda *a: calls.append(a)), \
                 patch.multiple(e, **(limits or {'MAX_RESTORED_ENTRIES': e.MAX_RESTORED_ENTRIES})), \
                 self.assertRaisesRegex(RuntimeError, expected):
                e.prepare_data(root)
            self.assertEqual(calls, [])  # pass 1 refuses before any change
            self.assertEqual((child / 'state.json').stat().st_mode & 0o777, 0o644)

    def test_links_special_files_and_limits_refused_without_changes(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: [p.unlink() for p in outside.iterdir()] and None or outside.rmdir())
        (outside / 'secret').write_bytes(b's')
        self.refused(lambda root, child: (child / 'link').symlink_to(outside / 'secret'), 'unsupported')
        self.refused(lambda root, child: (child / 'dirlink').symlink_to(outside, target_is_directory=True), 'unsupported')
        self.refused(lambda root, child: os.link(child / 'state.json', child / 'second-name'), 'unsupported')
        self.refused(lambda root, child: os.mkfifo(child / 'fifo'), 'unsupported')
        self.refused(lambda root, child: None, 'too large', MAX_RESTORED_ENTRIES=3)
        self.refused(lambda root, child: None, 'too deep', MAX_RESTORED_DEPTH=0)
        self.assertEqual((outside / 'secret').read_bytes(), b's')

    def test_runtime_owned_state_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            restored_tree(root)
            calls = []
            with patch.object(e, 'RESTORE_OWNER', (os.getuid() + 5, os.getgid() + 5)), \
                 patch.object(e, 'UID', os.getuid()), patch.object(e, 'GID', os.getgid()), \
                 patch.object(e.os, 'geteuid', return_value=0), \
                 patch.object(e.os, 'fchown', side_effect=lambda *a: calls.append(a)), \
                 patch.object(e.os, 'fchmod', side_effect=lambda *a: calls.append(a)), \
                 patch.object(e.os, 'chown', side_effect=lambda *a: calls.append(a)), \
                 patch.object(e.os, 'chmod', side_effect=lambda *a: calls.append(a)):
                e.prepare_data(root)
            self.assertEqual(calls, [])
            self.assertEqual((root / 'mcp' / 'state.json').stat().st_mode & 0o777, 0o644)

    @unittest.skipUnless(os.geteuid() == 0, 'creating root-owned restored state needs root')
    def test_root_owned_restore_is_reowned_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = restored_tree(root)
            log = io.StringIO()
            with patch.object(e, 'UID', 10001), patch.object(e, 'GID', 10001):
                with contextlib.redirect_stderr(log):
                    e.prepare_data(root)
                self.assertEqual(log.getvalue(), 'bootstrap: re-owned 4 restored entries in /data/mcp\n')
                for path in [child, *child.rglob('*')]:
                    info = path.lstat()
                    self.assertEqual((info.st_uid, info.st_gid), (10001, 10001), path)
                    self.assertEqual(info.st_mode & 0o777, 0o700 if path.is_dir() else 0o600, path)
                self.assertEqual((child / 'state.json').read_bytes(), b'{"restored": true}')
                e.prepare_data(root)  # second boot: runtime-owned, unchanged

    @unittest.skipUnless(os.geteuid() == 0, 'creating root-owned restored state needs root')
    def test_foreign_owner_inside_restore_refused_without_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = restored_tree(root)
            os.chown(child / 'sub' / 'nested', 4242, 4242)
            with patch.object(e, 'UID', 10001), patch.object(e, 'GID', 10001), self.assertRaises(RuntimeError):
                e.prepare_data(root)
            self.assertEqual({p.lstat().st_uid for p in (child, child / 'state.json', child / 'sub')}, {0})



class CrossPassTests(unittest.TestCase):
    """R1: pass 2 may touch only what pass 1 approved, by identity. Runs unprivileged: the current user plays
    the restore owner, ownership/mode changes are recorded by inode instead of applied."""

    def run_restore(self, mutate=None, open_hook=None):
        touched, mutated = set(), {}

        def by_fd(fd, *args):
            info = os.fstat(fd)
            touched.add((info.st_dev, info.st_ino))

        def by_path(path, *args, **kwargs):
            info = os.stat(path)
            touched.add((info.st_dev, info.st_ino))

        real_reown, real_open = e._reown_restored, os.open
        state = {'mutated': False}

        def reown(*args, **kwargs):
            if mutate and not state['mutated']:
                state['mutated'] = True
                mutated.update(mutate(child))
            return real_reown(*args, **kwargs)

        def opener(path, flags, *args, **kwargs):
            if open_hook:
                open_hook(path, flags, kwargs.get('dir_fd'), state)
            return real_open(path, flags, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = restored_tree(root)
            with patch.object(e, 'RESTORE_OWNER', (os.getuid(), os.getgid())), \
                 patch.object(e, 'UID', os.getuid() + 1), patch.object(e, 'GID', os.getgid() + 1), \
                 patch.object(e.os, 'geteuid', return_value=0), \
                 patch.object(e.os, 'fchown', side_effect=by_fd), patch.object(e.os, 'fchmod', side_effect=by_fd), \
                 patch.object(e.os, 'chown', side_effect=by_path), patch.object(e.os, 'chmod', side_effect=by_path), \
                 patch.object(e, '_reown_restored', side_effect=reown), patch.object(e.os, 'open', side_effect=opener):
                with self.assertRaisesRegex(RuntimeError, 'changed'):
                    e.prepare_data(root)
            return touched, mutated

    def test_file_replaced_between_passes_is_never_touched(self):
        def mutate(child):
            (child / 'state.json').unlink()
            (child / 'state.json').write_bytes(b'{"swapped": true}')
            info = (child / 'state.json').stat()
            return {'new': (info.st_dev, info.st_ino)}
        touched, mutated = self.run_restore(mutate)
        self.assertNotIn(mutated['new'], touched)

    def test_entry_added_between_passes_is_never_touched(self):
        def mutate(child):
            (child / 'sub' / 'added').write_bytes(b'a')
            info = (child / 'sub' / 'added').stat()
            return {'new': (info.st_dev, info.st_ino)}
        touched, mutated = self.run_restore(mutate)
        self.assertNotIn(mutated['new'], touched)

    def test_entry_removed_between_passes_is_refused(self):
        self.run_restore(lambda child: (child / 'sub' / 'nested').unlink() or {})

    def test_directory_swapped_between_stat_and_open_is_refused(self):
        swapped = {}

        def hook(path, flags, dir_fd, state):
            if path == 'sub' and flags & os.O_DIRECTORY and not state['mutated'] and not swapped:
                parent = Path('/proc/self/fd/%d' % dir_fd).resolve()
                (parent / 'sub').rename(parent / 'sub-approved')
                (parent / 'sub').mkdir(mode=0o755)
                (parent / 'sub' / 'planted').write_bytes(b'p')
                swapped['dir'] = (parent / 'sub').stat()
                swapped['file'] = (parent / 'sub' / 'planted').stat()
        touched, _ = self.run_restore(open_hook=hook)
        for info in swapped.values():
            self.assertNotIn((info.st_dev, info.st_ino), touched)

    @unittest.skipUnless(os.geteuid() == 0, 'creating a foreign-owned file needs root')
    def test_foreign_file_planted_between_passes_keeps_its_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = restored_tree(root)
            real_reown = e._reown_restored
            planted = child / 'sub' / 'planted'

            def reown(*args, **kwargs):
                if not planted.exists():
                    (child / 'state.json').unlink()
                    planted.write_bytes(b'x')
                    os.chown(planted, 4242, 4242)
                return real_reown(*args, **kwargs)
            with patch.object(e, 'UID', 10001), patch.object(e, 'GID', 10001), \
                 patch.object(e, '_reown_restored', side_effect=reown), self.assertRaises(RuntimeError):
                e.prepare_data(root)
            self.assertEqual((planted.stat().st_uid, planted.stat().st_mode & 0o777), (4242, 0o644))


class RepairUnitTests(unittest.TestCase):
    """Each pass-1/pass-2 check pinned on its own (unprivileged unless marked); changes are recorded by inode."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.child = restored_tree(self.root)
        self.fd = os.open(self.child, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        self.touched, self.pinned, self.calls = set(), [], []
        self.addCleanup(lambda: [os.close(f) for f in self.pinned])

        def spy(op, info):
            self.touched.add((info.st_dev, info.st_ino))
            self.calls.append((op, (info.st_dev, info.st_ino)))

        def by_fd_mode(fd, *args):
            spy('mode', os.fstat(fd))

        def by_fd_owner(fd, *args):
            spy('owner', os.fstat(fd))

        def by_path_mode(path, *args, **kwargs):
            spy('mode', os.stat(path))

        def by_path_owner(path, *args, **kwargs):
            spy('owner', os.stat(path))
        for target, value in (('RESTORE_OWNER', (os.getuid(), os.getgid())), ('UID', os.getuid() + 1),
                              ('GID', os.getgid() + 1)):
            patcher = patch.object(e, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, fake in (('fchown', by_fd_owner), ('fchmod', by_fd_mode), ('chown', by_path_owner),
                           ('chmod', by_path_mode)):
            patcher = patch.object(e.os, name, side_effect=fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def approve(self, budget=None):
        return e._approve_restored(self.fd, os.fstat(self.fd).st_dev, 0, [budget or e.MAX_RESTORED_ENTRIES], self.pinned)

    def ident(self, path):
        info = path.stat()
        return (info.st_dev, info.st_ino)

    def test_clean_tree_repairs_exactly_the_approved_inodes(self):
        expected = {self.ident(p) for p in self.child.rglob('*')}
        e._reown_restored(self.fd, self.approve())
        self.assertEqual(self.touched, expected)

    def test_mode_is_set_before_owner_for_every_inode_and_data_mcp(self):
        # An interrupted repair must leave root-owned entries (repaired again next boot), never a runtime-owned
        # entry with a stale mode (refused forever).
        with contextlib.redirect_stderr(io.StringIO()):
            e._repair_restored(self.fd, os.fstat(self.fd))
        inodes = {self.ident(p) for p in self.child.rglob('*')} | {self.ident(self.child)}
        self.assertEqual(self.touched, inodes)
        for inode in inodes:
            ops = [op for op, target in self.calls if target == inode]
            self.assertEqual(ops, ['mode', 'owner'], inode)

    def test_pass2_refuses_a_foreign_owner_unprivileged(self):
        # The same check the root-only owner test exercises, reachable without root by faking the held stat.
        approved = self.approve()
        held = approved['state.json'][0]
        real_fstat = os.fstat

        def fake_fstat(fd):
            info = real_fstat(fd)
            if fd == held:
                values = list(info)
                values[4], values[5] = 4242, 4242  # st_uid, st_gid
                return os.stat_result(values)
            return info
        with patch.object(e.os, 'fstat', side_effect=fake_fstat), self.assertRaisesRegex(RuntimeError, 'changed'):
            e._reown_restored(self.fd, approved)
        self.assertNotIn(self.ident(self.child / 'state.json'), self.touched)

    def test_pass1_refuses_a_directory_swapped_between_stat_and_open(self):
        real_open = os.open

        def opener(path, flags, *args, **kwargs):
            if path == 'sub' and flags & os.O_DIRECTORY:
                (self.child / 'sub').rename(self.child / 'sub-approved')
                (self.child / 'sub').mkdir(mode=0o755)
            return real_open(path, flags, *args, **kwargs)
        with patch.object(e.os, 'open', side_effect=opener), self.assertRaisesRegex(RuntimeError, 'changed'):
            self.approve()

    def test_pass1_refuses_a_filesystem_boundary(self):
        real_stat = os.stat

        def fake_stat(path, *args, **kwargs):
            info = real_stat(path, *args, **kwargs)
            if path == 'sub':
                values = list(info)
                values[2] = info.st_dev + 1  # st_dev of a mount point
                return os.stat_result(values)
            return info
        with patch.object(e.os, 'stat', side_effect=fake_stat), self.assertRaisesRegex(RuntimeError, 'boundary'):
            self.approve()

    def test_pass1_listing_stops_at_the_limit(self):
        produced = []

        class Entries:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def __iter__(self):
                for i in range(100000):
                    produced.append(i)
                    yield type('Entry', (), {'name': 'f%d' % i})()
        with patch.object(e.os, 'scandir', return_value=Entries()), self.assertRaisesRegex(RuntimeError, 'too large'):
            self.approve(budget=10)
        self.assertEqual(len(produced), 11)

    def test_pass1_budget_covers_nested_levels(self):
        for i in range(4):
            (self.child / 'sub' / ('n%d' % i)).write_bytes(b'n')
        with self.assertRaisesRegex(RuntimeError, 'too large'):
            self.approve(budget=5)  # 3 top-level names + 5 nested would pass a per-level check

    def test_pass2_refuses_a_rename_between_passes(self):
        approved = self.approve()
        (self.child / 'state.json').rename(self.child / 'renamed.json')
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            e._reown_restored(self.fd, approved)
        self.assertNotIn(self.ident(self.child / 'renamed.json'), self.touched)

    def test_repair_checks_the_descriptor_budget_before_any_change(self):
        with patch.object(e, '_descriptor_budget', side_effect=RuntimeError('descriptor limit too low')), \
             self.assertRaisesRegex(RuntimeError, 'descriptor'):
            e._repair_restored(self.fd, os.fstat(self.fd))
        self.assertEqual(self.touched, set())

    def test_pass2_refuses_a_file_moved_out_and_replaced(self):
        # The pinned inode keeps one link (moved outside the tree) and the name set is unchanged; only the
        # name-to-pinned-inode check notices.
        approved = self.approve()
        (self.child / 'state.json').rename(self.root / 'moved-out.json')
        (self.child / 'state.json').write_bytes(b'{"swapped": true}')
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            e._reown_restored(self.fd, approved)
        self.assertNotIn(self.ident(self.root / 'moved-out.json'), self.touched)
        self.assertNotIn(self.ident(self.child / 'state.json'), self.touched)

    def test_pass2_refuses_a_hardlink_made_outside_between_passes(self):
        approved = self.approve()
        os.link(self.child / 'state.json', self.root / 'outside-link')
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            e._reown_restored(self.fd, approved)
        self.assertNotIn(self.ident(self.root / 'outside-link'), self.touched)

    def test_same_tick_replacement_is_refused_every_time(self):
        # The approved inode stays pinned, so a replacement can never reuse its inode number.
        for _ in range(50):
            approved = self.approve()
            (self.child / 'state.json').unlink()
            (self.child / 'state.json').write_bytes(b'{"swapped": true}')
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                e._reown_restored(self.fd, approved)
            self.assertNotIn(self.ident(self.child / 'state.json'), self.touched)
            for fd in self.pinned:
                os.close(fd)
            self.pinned.clear()

    @unittest.skipUnless(os.geteuid() == 0, 'a foreign owner needs root')
    def test_pass1_refuses_a_foreign_owner(self):
        REAL_CHOWN(self.child / 'sub' / 'nested', 4242, 4242)
        with self.assertRaisesRegex(RuntimeError, 'foreign'):
            self.approve()

    @unittest.skipUnless(os.geteuid() == 0, 'a foreign owner needs root')
    def test_pass2_refuses_an_owner_changed_between_passes(self):
        approved = self.approve()
        REAL_CHOWN(self.child / 'state.json', 4242, 4242)
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            e._reown_restored(self.fd, approved)
        self.assertNotIn(self.ident(self.child / 'state.json'), self.touched)


class DescriptorBudgetTests(unittest.TestCase):
    def test_soft_limit_is_raised_and_a_low_hard_limit_refused(self):
        need = e.MAX_RESTORED_ENTRIES + 64
        with patch.object(e.resource, 'getrlimit', return_value=(100, 10000)), \
             patch.object(e.resource, 'setrlimit') as setrlimit:
            self.assertEqual(e._descriptor_budget(), (100, 10000))
        setrlimit.assert_called_once_with(e.resource.RLIMIT_NOFILE, (need, 10000))
        with patch.object(e.resource, 'getrlimit', return_value=(100, 200)), \
             patch.object(e.resource, 'setrlimit') as setrlimit, self.assertRaises(RuntimeError):
            e._descriptor_budget()
        setrlimit.assert_not_called()
        with patch.object(e.resource, 'getrlimit', return_value=(need, 10000)), \
             patch.object(e.resource, 'setrlimit') as setrlimit:
            self.assertIsNone(e._descriptor_budget())
        setrlimit.assert_not_called()

    def test_repair_restores_the_soft_limit_even_when_it_fails(self):
        need = e.MAX_RESTORED_ENTRIES + 64
        for failure in (None, RuntimeError(e.CHANGED)):
            with self.subTest(failure=failure), \
                 patch.object(e.resource, 'getrlimit', return_value=(100, 10000)), \
                 patch.object(e.resource, 'setrlimit') as setrlimit, \
                 patch.object(e, '_approve_restored', return_value={}), \
                 patch.object(e, '_reown_restored', side_effect=failure), \
                 patch.object(e.os, 'fchmod'), patch.object(e.os, 'fchown'):
                if failure is None:
                    log = io.StringIO()
                    with contextlib.redirect_stderr(log):
                        self.assertEqual(e._repair_restored(5, os.stat('/')), 0)
                    self.assertEqual(log.getvalue(), '')  # prepare_data reports, after its final check
                else:
                    with self.assertRaises(RuntimeError):
                        e._repair_restored(5, os.stat('/'))
            self.assertEqual(setrlimit.call_args_list, [
                call(e.resource.RLIMIT_NOFILE, (need, 10000)),
                call(e.resource.RLIMIT_NOFILE, (100, 10000))])


class RepairReportTests(unittest.TestCase):
    def test_success_is_reported_only_after_the_final_ownership_check(self):
        # A repair that leaves /data/mcp with the wrong owner must fail without claiming success.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            restored_tree(root)
            log = io.StringIO()
            with patch.object(e, 'RESTORE_OWNER', (os.getuid(), os.getgid())), \
                 patch.object(e, 'UID', os.getuid() + 1), patch.object(e, 'GID', os.getgid() + 1), \
                 patch.object(e.os, 'geteuid', return_value=0), \
                 patch.object(e, '_repair_restored', return_value=4) as repair, \
                 contextlib.redirect_stderr(log), self.assertRaisesRegex(RuntimeError, 'incompatible data ownership'):
                e.prepare_data(root)
            repair.assert_called_once()
            self.assertEqual(log.getvalue(), '')

if __name__ == '__main__':
    unittest.main()
