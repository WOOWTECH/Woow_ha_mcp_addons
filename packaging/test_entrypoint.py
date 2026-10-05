"""Bootstrap tests use owned temporary directories only, never real /data."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import entrypoint as e


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

    def test_n8n_runtime_token_passthrough_only(self):
        # Replace environ itself: never inspect/copy the test runner environment.
        # This verifies the future real run.py exec contract, not provider wiring.
        dummy = 'INVENTED-PACKAGING-ONLY-NOT-A-CREDENTIAL'
        source = {'SUPERVISOR_TOKEN': dummy, 'HASSIO_TOKEN': 'invented-legacy',
                  'HTTP_PROXY': 'http://example.invalid', 'PYTHONPATH': '/untrusted',
                  'HA_ROLE_URL': 'ws://example.invalid', 'HA_ROLE_METHOD': 'auth/list'}
        path, argv, env = self.bootstrap_exec('n8n', source)
        self.assertEqual(path, '/opt/woow/.venv/bin/python')
        self.assertEqual(argv, [path, '/opt/woow/packaging/management_launcher.py', 'n8n'])
        self.assertEqual(env, {
            'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/data/mcp',
            'PYTHONPATH': '/opt/woow/packages/mcp-admin-core:/opt/woow/apps/n8n',
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
            'SUPERVISOR_TOKEN': dummy})
        self.assertNotIn(dummy, argv)
        self.assertEqual(source['SUPERVISOR_TOKEN'], dummy)

    def test_n8n_missing_or_empty_token_is_not_synthesized(self):
        for source in ({}, {'SUPERVISOR_TOKEN': ''}):
            with self.subTest(source=source):
                _, _, env = self.bootstrap_exec('n8n', source)
                self.assertNotIn('SUPERVISOR_TOKEN', env)

    def test_other_six_never_read_or_inherit_supervisor_token(self):
        class NoEnvironmentAccess(dict):
            def get(self, *args):
                raise AssertionError('other products must not read environment')

            def __getitem__(self, key):
                raise AssertionError('other products must not read environment')

        for product in e.PRODUCTS:
            if product == 'n8n':
                continue
            with self.subTest(product=product):
                source = NoEnvironmentAccess(SUPERVISOR_TOKEN='INVENTED-ONLY')
                path, argv, env = self.bootstrap_exec(product, source)
                self.assertEqual(argv, [path, '/opt/woow/packaging/management_launcher.py', product])
                self.assertEqual(set(env), {'PATH', 'HOME', 'PYTHONPATH',
                                           'PYTHONDONTWRITEBYTECODE', 'PYTHONUNBUFFERED'})


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

    def refused(self, build, **limits):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = restored_tree(root)
            build(root, child)
            calls = []
            with patch.object(e, 'RESTORE_OWNER', (os.getuid(), os.getgid())), \
                 patch.object(e, 'UID', os.getuid() + 1), patch.object(e, 'GID', os.getgid() + 1), \
                 patch.object(e.os, 'geteuid', return_value=0), \
                 patch.object(e.os, 'fchown', side_effect=lambda *a: calls.append(a)), \
                 patch.multiple(e, **(limits or {'MAX_RESTORED_ENTRIES': e.MAX_RESTORED_ENTRIES})), \
                 self.assertRaises(RuntimeError):
                e.prepare_data(root)
            self.assertEqual(calls, [])  # pass 1 refuses before any change
            self.assertEqual((child / 'state.json').stat().st_mode & 0o777, 0o644)

    def test_links_special_files_and_limits_refused_without_changes(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: [p.unlink() for p in outside.iterdir()] and None or outside.rmdir())
        (outside / 'secret').write_bytes(b's')
        self.refused(lambda root, child: (child / 'link').symlink_to(outside / 'secret'))
        self.refused(lambda root, child: (child / 'dirlink').symlink_to(outside, target_is_directory=True))
        self.refused(lambda root, child: os.link(child / 'state.json', child / 'second-name'))
        self.refused(lambda root, child: os.mkfifo(child / 'fifo'))
        self.refused(lambda root, child: None, MAX_RESTORED_ENTRIES=3)
        self.refused(lambda root, child: None, MAX_RESTORED_DEPTH=0)
        self.assertEqual((outside / 'secret').read_bytes(), b's')

    def test_runtime_owned_state_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            restored_tree(root)
            calls = []
            with patch.object(e, 'RESTORE_OWNER', (os.getuid() + 5, os.getgid() + 5)), \
                 patch.object(e, 'UID', os.getuid()), patch.object(e, 'GID', os.getgid()), \
                 patch.object(e.os, 'geteuid', return_value=0), \
                 patch.object(e.os, 'fchown', side_effect=lambda *a: calls.append(a)):
                e.prepare_data(root)
            self.assertEqual(calls, [])
            self.assertEqual((root / 'mcp' / 'state.json').stat().st_mode & 0o777, 0o644)

    @unittest.skipUnless(os.geteuid() == 0, 'creating root-owned restored state needs root')
    def test_root_owned_restore_is_reowned_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = restored_tree(root)
            with patch.object(e, 'UID', 10001), patch.object(e, 'GID', 10001):
                e.prepare_data(root)
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


if __name__ == '__main__':
    unittest.main()
