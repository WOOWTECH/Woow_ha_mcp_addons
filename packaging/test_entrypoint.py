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
            with patch.object(e, 'UID', os.getuid() + 1), self.assertRaises(RuntimeError):
                e.prepare_data(root)
            self.assertEqual(child.stat().st_uid, os.getuid())

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


if __name__ == '__main__':
    unittest.main()
