"""hosted_runner.py, the preflight of the candidate and publish jobs, against an owned fake Docker host: no Docker, sudo
or daemon change."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import hosted_runner as h

CLASSIC = [['Backing Filesystem', 'extfs'], ['Supports d_type', 'true'], ['Using metacopy', 'false'],
           ['Native Overlay Diff', 'true'], ['userxattr', 'false']]
CONTAINERD = [['driver-type', 'io.containerd.snapshotter.v1']]
GITHUB_DAEMON = {'exec-opts': ['native.cgroupdriver=cgroupfs'], 'cgroup-parent': '/actions_job'}


class FakeHost:
    """Answers the commands the preflight runs; `sudo install` copies the staged file to the owned daemon.json path and
    a restart applies its containerd-snapshotter feature unless `restart_fixes` is off; `comes_back` off keeps the
    daemon down after the restart."""

    def __init__(self, daemon_json, store='classic', restart_fixes=True, context='default',
                 host='unix:///var/run/docker.sock', buildx='github.com/docker/buildx v0.38.2 0a1b2c3', driver=None,
                 comes_back=True, server_os='linux', server_arch='amd64', status=None):
        self.calls, self.daemon_json, self.store, self.down = [], daemon_json, store, False
        self.restart_fixes, self.context, self.host, self.buildx, self.driver = restart_fixes, context, host, buildx, driver
        self.comes_back, self.server_os, self.server_arch, self.status = comes_back, server_os, server_arch, status

    def info(self):
        if self.store == 'containerd':
            return {'Driver': 'overlayfs', 'DriverStatus': CONTAINERD, 'OSType': 'linux', 'Architecture': 'x86_64',
                    'OperatingSystem': 'Ubuntu 24.04.3 LTS'}
        return {'Driver': self.driver or 'overlay2', 'DriverStatus': self.status or CLASSIC, 'OSType': 'linux',
                'Architecture': 'x86_64', 'OperatingSystem': 'Ubuntu 24.04.3 LTS', 'Name': 'runner-host-name'}

    def __call__(self, argv, timeout=120):
        self.calls.append(list(argv))
        if argv[:3] == ['docker', 'context', 'show']:
            return self.context + '\n'
        if argv[:3] == ['docker', 'context', 'inspect']:
            return json.dumps([{'Name': 'default', 'Endpoints': {'docker': {'Host': self.host, 'SkipTLSVerify': False}}}])
        if argv[:2] == ['docker', 'info']:
            if self.down:
                raise h.Closed('docker info failed (exit 1)')
            return json.dumps(self.info())
        if argv[:2] == ['docker', 'version']:
            return json.dumps({'Client': {'Version': '28.0.4'}, 'Server': {
                'Version': '28.0.4', 'ApiVersion': '1.48', 'Os': self.server_os, 'Arch': self.server_arch,
                'Components': [{'Name': 'Engine', 'Version': '28.0.4'}, {'Name': 'containerd', 'Version': '1.7.27'},
                               {'Name': 'runc', 'Version': '1.2.5'}]}})
        if argv[:3] == ['docker', 'buildx', 'version']:
            return self.buildx + '\n'
        if argv[:3] == ['sudo', '-n', 'install']:
            assert argv[3:9] == ['-o', 'root', '-g', 'root', '-m', '0644'] and argv[-1] == str(self.daemon_json), argv
            shutil.copyfile(argv[-2], self.daemon_json)
            return ''
        if argv == ['sudo', '-n', 'systemctl', 'restart', 'docker.service']:
            features = json.loads(self.daemon_json.read_text()).get('features', {})
            if self.restart_fixes and features.get('containerd-snapshotter') is False:
                self.store, self.status = 'classic', None
            self.down = not self.comes_back
            return ''
        raise AssertionError('unexpected command: %r' % (argv,))


class HostedRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / 'checkout'
        for rel in h.READABLE:
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text('invented\n')
            os.chmod(self.root / rel, 0o644)
        for rel in h.TRAVERSABLE:
            (self.root / rel).mkdir(parents=True, exist_ok=True)
            os.chmod(self.root / rel, 0o755)
        self.daemon_json = self.base / 'daemon.json'
        self.record = self.base / 'release-evidence' / 'hosted-runner.json'
        self.env = {'RUNNER_ENVIRONMENT': 'github-hosted', 'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64',
                    'RUNNER_TEMP': str(self.base), 'ImageOS': 'ubuntu24', 'ImageVersion': '20261111.370.1',
                    'DOCKER_BUILD_SUMMARY': 'false', 'DOCKER_BUILD_RECORD_UPLOAD': 'false', 'PATH': '/usr/bin:/bin'}

    def tearDown(self):
        self.temporary.cleanup()

    def preflight(self, host, kind='github-hosted', env=None):
        with patch.object(h, 'run', side_effect=host), patch.object(h.platform, 'machine', return_value='x86_64'), \
             patch.object(h.time, 'sleep'):
            return h.preflight(kind, self.record, env=self.env if env is None else env, root=self.root,
                               daemon_json=self.daemon_json)

    def fresh(self):
        shutil.rmtree(self.record.parent, ignore_errors=True)

    def test_classic_store_passes_without_touching_the_daemon_and_records_versions(self):
        host = FakeHost(self.daemon_json)
        record = self.preflight(host)
        self.assertFalse(any(call[0] == 'sudo' for call in host.calls))
        self.assertFalse(self.daemon_json.exists())
        self.assertEqual(json.loads(self.record.read_text()), record)
        self.assertEqual(self.record.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.record.stat().st_mode & 0o777, 0o600)
        self.assertEqual(record['runner'], {'environment': 'github-hosted', 'os': 'Linux', 'arch': 'X64',
                                            'image_os': 'ubuntu24', 'image_version': '20261111.370.1',
                                            'kernel': record['runner']['kernel']})
        docker = record['docker']
        self.assertEqual((docker['client'], docker['server'], docker['api'], docker['storage_driver']),
                         ('28.0.4', '28.0.4', '1.48', 'overlay2'))
        self.assertEqual(docker['components'], {'Engine': '28.0.4', 'containerd': '1.7.27', 'runc': '1.2.5'})
        self.assertIs(docker['switched_from_containerd_store'], False)
        self.assertEqual(record['buildx'], 'github.com/docker/buildx v0.38.2 0a1b2c3')
        self.assertNotIn('runner-host-name', json.dumps(record))  # only the listed facts, not the whole docker info
        for line in ('github.com/docker/buildx v0.38.2 0a1b2c3', 'github.com/docker/buildx 0.21.1+azure-1 d1ab2c3',
                     'github.com/docker/buildx v0.38.2'):
            self.assertIsNotNone(h.BUILDX.fullmatch(line), line)
        for line in ('buildx version unknown', 'github.com/other/buildx v0.38.2 x', ''):
            self.assertIsNone(h.BUILDX.fullmatch(line), line)

    def test_an_existing_evidence_directory_is_used_but_an_existing_record_is_refused(self):
        # The publish job's approval record is written into the same directory first.
        self.record.parent.mkdir(mode=0o700)
        (self.record.parent / 'approval.json').write_text('{}\n')
        self.preflight(FakeHost(self.daemon_json))
        with self.assertRaisesRegex(h.Closed, 'runner record already exists'):
            self.preflight(FakeHost(self.daemon_json))
        self.fresh()
        self.record.parent.parent.joinpath('elsewhere').mkdir()
        self.record.parent.symlink_to(self.record.parent.parent / 'elsewhere')
        with self.assertRaisesRegex(h.Closed, 'not a plain directory'):
            self.preflight(FakeHost(self.daemon_json))

    def test_containerd_store_is_switched_off_keeping_the_runner_settings(self):
        self.daemon_json.write_text(json.dumps(GITHUB_DAEMON))
        host = FakeHost(self.daemon_json, store='containerd')
        record = self.preflight(host)
        self.assertEqual(json.loads(self.daemon_json.read_text()),
                         {**GITHUB_DAEMON, 'features': {'containerd-snapshotter': False}})
        sudo = [call for call in host.calls if call[0] == 'sudo']
        self.assertEqual([call[:4] for call in sudo], [['sudo', '-n', 'install', '-o'], ['sudo', '-n', 'systemctl', 'restart']])
        self.assertLess(host.calls.index(sudo[1]), max(i for i, c in enumerate(host.calls) if c[:2] == ['docker', 'info']))
        self.assertIs(record['docker']['switched_from_containerd_store'], True)
        self.assertEqual(record['docker']['storage_driver'], 'overlay2')
        # A runner without daemon.json gets one with only the feature, and other features are kept.
        for before, after in (('', {'features': {'containerd-snapshotter': False}}),
                              (json.dumps({'features': {'other': True}}), {'features': {'other': True, 'containerd-snapshotter': False}}),
                              (json.dumps({'features': {'containerd-snapshotter': True}}), {'features': {'containerd-snapshotter': False}})):
            with self.subTest(before=before):
                self.assertEqual(h.without_containerd_store(before), after)

    def test_overlay2_with_the_containerd_snapshotter_marker_is_not_the_classic_store(self):
        marked = {'Driver': 'overlay2', 'DriverStatus': CONTAINERD}
        self.assertFalse(h.classic_store(marked))
        self.assertTrue(h.containerd_store(marked))
        self.assertTrue(h.classic_store({'Driver': 'overlay2', 'DriverStatus': None}))
        self.assertFalse(h.classic_store({'Driver': 'overlayfs', 'DriverStatus': None}))
        # The preflight switches it off; a marker that survives the restart fails closed.
        self.daemon_json.write_text(json.dumps(GITHUB_DAEMON))
        self.assertIs(self.preflight(FakeHost(self.daemon_json, status=CONTAINERD))['docker']['switched_from_containerd_store'], True)
        self.fresh()
        self.daemon_json.write_text(json.dumps(GITHUB_DAEMON))
        with self.assertRaisesRegex(h.Closed, 'still uses the containerd image store'):
            self.preflight(FakeHost(self.daemon_json, status=CONTAINERD, restart_fixes=False))

    def test_docker_that_never_comes_back_after_the_restart_fails_closed(self):
        self.daemon_json.write_text(json.dumps(GITHUB_DAEMON))
        host = FakeHost(self.daemon_json, store='containerd', comes_back=False)
        with patch.object(h, 'run', side_effect=host), patch.object(h.platform, 'machine', return_value='x86_64'), \
             patch.object(h.time, 'sleep') as sleep, self.assertRaisesRegex(h.Closed, 'did not come back'):
            h.preflight('github-hosted', self.record, env=self.env, root=self.root, daemon_json=self.daemon_json)
        self.assertEqual(sleep.call_count, 60)
        self.assertFalse(self.record.exists())

    def test_still_containerd_after_the_restart_or_unreadable_settings_fail_closed(self):
        self.daemon_json.write_text(json.dumps(GITHUB_DAEMON))
        with self.assertRaisesRegex(h.Closed, 'still uses the containerd image store'):
            self.preflight(FakeHost(self.daemon_json, store='containerd', restart_fixes=False))
        for text in ('[]', '{not json', json.dumps({'features': ['containerd-snapshotter']}),
                     json.dumps({'storage-driver': 'vfs'})):
            self.fresh()
            self.daemon_json.write_text(text)
            host = FakeHost(self.daemon_json, store='containerd')
            with self.subTest(text=text), self.assertRaises(h.Closed):
                self.preflight(host)
            self.assertEqual(self.daemon_json.read_text(), text)  # never replaced with a guess
            self.assertFalse(any(call[:3] == ['sudo', '-n', 'systemctl'] for call in host.calls))

    def test_another_storage_driver_or_server_platform_is_refused(self):
        host = FakeHost(self.daemon_json, driver='vfs')
        with self.assertRaisesRegex(h.Closed, 'not overlay2'):
            self.preflight(host)
        self.assertFalse(any(call[0] == 'sudo' for call in host.calls))
        for server_os, server_arch in (('windows', 'amd64'), ('linux', 'arm64'), ('', '')):
            self.fresh()
            with self.subTest(os=server_os, arch=server_arch), self.assertRaisesRegex(h.Closed, 'Docker server platform'):
                self.preflight(FakeHost(self.daemon_json, server_os=server_os, server_arch=server_arch))

    def test_only_a_github_hosted_linux_x64_runner(self):
        for kind, extra in (('self-hosted', {}), ('', {}), ('github-hosted', {'RUNNER_ENVIRONMENT': 'self-hosted'}),
                            ('github-hosted', {'RUNNER_OS': 'Windows'}), ('github-hosted', {'RUNNER_ARCH': 'ARM64'})):
            host = FakeHost(self.daemon_json)
            with self.subTest(kind=kind, extra=extra), self.assertRaises(h.Closed):
                self.preflight(host, kind=kind, env={**self.env, **extra})
            self.assertEqual(host.calls, [])
            self.assertFalse(self.record.exists())
        with patch.object(h.platform, 'machine', return_value='aarch64'), self.assertRaises(h.Closed):
            h.preflight('github-hosted', self.record, env=self.env, root=self.root, daemon_json=self.daemon_json)

    def test_ambient_daemon_builder_or_platform_overrides_are_refused_before_any_docker_call(self):
        for name in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG', 'BUILDX_BUILDER', 'BUILDKIT_HOST',
                     'DOCKER_DEFAULT_PLATFORM', 'DOCKER_TLS_VERIFY'):
            host = FakeHost(self.daemon_json)
            with self.subTest(name=name), self.assertRaisesRegex(h.Closed, name):
                self.preflight(host, env={**self.env, name: 'invented'})
            self.assertEqual(host.calls, [])
        for host in (FakeHost(self.daemon_json, context='remote'), FakeHost(self.daemon_json, host='tcp://invented.invalid:2376'),
                     FakeHost(self.daemon_json, buildx='buildx version unknown')):
            self.fresh()
            with self.subTest(context=host.context, host=host.host, buildx=host.buildx), self.assertRaises(h.Closed):
                self.preflight(host)

    def test_unreadable_build_inputs_are_refused(self):
        os.chmod(self.root / 'packaging/entrypoint.py', 0o600)
        with self.assertRaisesRegex(h.Closed, 'packaging/entrypoint.py'):
            self.preflight(FakeHost(self.daemon_json))
        os.chmod(self.root / 'packaging/entrypoint.py', 0o644)
        os.chmod(self.root / 'apps', 0o700)
        with self.assertRaisesRegex(h.Closed, 'directory not readable'):
            self.preflight(FakeHost(self.daemon_json))
        os.chmod(self.root / 'apps', 0o755)

    def test_the_preflight_writes_no_workflow_environment_and_reads_no_secret(self):
        source = Path(h.__file__).read_text()
        for absent in ('GITHUB_ENV', 'GITHUB_PATH', 'GITHUB_OUTPUT', 'GITHUB_TOKEN', 'GHCR_TOKEN', 'GH_TOKEN', 'secrets'):
            self.assertNotIn(absent, source)

    def test_main_needs_two_arguments(self):
        with self.assertRaisesRegex(h.Closed, 'usage'):
            h.main(['github-hosted'])


if __name__ == '__main__':
    unittest.main()
