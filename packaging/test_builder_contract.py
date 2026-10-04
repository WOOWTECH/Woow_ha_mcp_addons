"""Owned fake-Docker replies only: no builder, daemon or isolation verification."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import builder_contract as b


class BuilderContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Test-only route/bytes. Production CLI remains hard BLOCKED.
        self.route_patch = patch.object(b, 'HOSTING_ROUTE', 'REVIEWED_ORGANIZATION')
        self.route_patch.start()
        self.addCleanup(self.route_patch.stop)
        source = self.root / 'mock-buildx-bytes'
        source.write_bytes(b'MOCK BYTES ONLY - never executed')
        for patcher in (patch.object(b.builder_binary, 'SOURCE', source),
                        patch.object(b.builder_binary, 'SHA256', hashlib.sha256(source.read_bytes()).hexdigest())):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.env_log = self.root / 'environments.jsonl'
        self.log = self.root / 'commands.jsonl'
        self.replies = self.root / 'replies.json'
        # These versions/IDs are invented test fixtures, NOT operator approvals.
        self.approval = dict(schema=1, status='APPROVED', source='a' * 40,
            expires=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            review='MOCK-ONLY', buildx=b.BUILDX_VERSION, client='99.1.0',
            engine='99.2.0', api='1.99', buildkit='v99.3.0',
            runners={'mock-vm': {'engine_id': 'mock-engine', 'daemon_name': 'mock-daemon'}})
        self.env = {'PATH': str(self.root) + os.pathsep + '/usr/bin:/bin',
            'RUNNER_TEMP': str(self.root), 'RUNNER_NAME': 'mock-vm',
            'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64',
            'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main',
            'GITHUB_SHA': 'a' * 40, 'BLD2_APPROVAL': json.dumps(self.approval)}
        self.node = dict(Name='default', Endpoint='default', Status='running',
                         Version='v99.3.0', Platforms=['linux/amd64', 'linux/386'])
        self.builder = dict(Name='default', Driver='docker', Current=True,
                            Dynamic=False, Nodes=[self.node])
        self.responses = {
            'context show': 'default',
            'context inspect default': [dict(Name='default', Endpoints={
                'docker': {'Host': b.ENDPOINT, 'SkipTLSVerify': False}}, TLSMaterial={})],
            'version --format {{json .}}': {
                'Client': {'Version': '99.1.0', 'Os': 'linux', 'Arch': 'amd64'},
                'Server': {'Version': '99.2.0', 'ApiVersion': '1.99',
                           'Os': 'linux', 'Arch': 'amd64'}},
            'info --format {{json .}}': {'ID': 'mock-engine', 'Name': 'mock-daemon',
                'OSType': 'linux', 'Architecture': 'x86_64'},
            'buildx version': 'github.com/docker/buildx ' + b.BUILDX_VERSION + ' mock-revision',
            'buildx ls --format json': self.builder,
        }
        docker = self.root / 'docker'
        docker.write_text('#!' + sys.executable + '\nimport json,sys,os\n'
            + 'from pathlib import Path\n'
            + f'log=Path({str(self.log)!r}); replies=Path({str(self.replies)!r})\n'
            + f'env_log=Path({str(self.env_log)!r})\n'
            + 'with env_log.open("a") as f: f.write(json.dumps(dict(os.environ))+"\\n")\n'
            + 'key=" ".join(sys.argv[1:])\n'
            + 'with log.open("a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
            + 'r=json.loads(replies.read_text())[key]\n'
            + 'print(r if isinstance(r,str) else json.dumps(r))\n')
        docker.chmod(0o700)
        self.sync()

    def sync(self):
        self.env['BLD2_APPROVAL'] = json.dumps(self.approval)
        self.replies.write_text(json.dumps(self.responses))

    def prepare(self):
        self.sync()
        with patch.object(b.platform, 'machine', return_value='x86_64'):
            b.prepare(self.env)
        self.env.update(b.exports(self.env))

    def test_personal_route_cannot_be_enabled_by_approval_or_labels(self):
        self.route_patch.stop()  # Production route, no mock admission.
        with self.assertRaisesRegex(b.Denied, 'BLOCKED.*personal'):
            b.approval(dict(self.env, BLD2_HOSTING_APPROVED='true',
                            RUNNER_GROUP='woow-disposable-builder'))
        self.assertFalse(self.log.exists())

    def test_proxy_and_helper_environment_denied_before_any_query(self):
        keys = ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'FTP_PROXY',
                'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy', 'ftp_proxy',
                'PASSWORD_STORE_DIR', 'PASSWORD_STORE_GPG_OPTS', 'GNUPGHOME',
                'GPG_AGENT_INFO', 'DBUS_SESSION_BUS_ADDRESS', 'SSH_AUTH_SOCK',
                'KEYRING_PATH', 'DOCKER_CREDENTIAL_HELPER', 'GCM_CREDENTIAL_STORE']
        for key in keys:
            for value in ('', 'INVENTED-ONLY'):
                with self.subTest(key=key, value=value), self.assertRaises(b.Denied):
                    b.prepare(dict(self.env, **{key: value}))
                self.assertFalse(self.log.exists())

    def test_owned_helper_sentinels_denied_without_execution(self):
        sentinel = self.root / 'helper-executed'
        for name in ('pass', 'docker-credential-pass', 'docker-credential-secretservice'):
            helper = self.root / name
            helper.write_text('#!/bin/sh\ntouch ' + str(sentinel) + '\n')
            helper.chmod(0o700)
        with self.assertRaises(b.Denied):
            b.prepare(self.env)
        self.assertFalse(sentinel.exists())
        self.assertFalse(self.log.exists())

    def test_private_auth_config_is_not_empty_and_exports_whole_environment(self):
        self.env.update(HOME='/invented/ambient', XDG_DATA_HOME='/invented/data',
                        XDG_RUNTIME_DIR='/invented/runtime')
        self.prepare()
        config = json.loads(Path(self.env['DOCKER_CONFIG'], 'config.json').read_text())
        # Pinned CLI ContainsAuth counts map entries, not nonempty passwords.
        # These data assertions are NOT a fake Docker credential implementation.
        self.assertEqual(config, {'auths': {'bld2-anonymous.invalid': {}}})
        exports = b.exports(self.env)
        self.assertEqual(set(exports), {'HOME', 'DOCKER_CONFIG', 'XDG_CONFIG_HOME',
            'XDG_DATA_HOME', 'XDG_CACHE_HOME', 'XDG_STATE_HOME', 'XDG_RUNTIME_DIR'})
        for key, value in exports.items():
            self.assertEqual(self.env[key], value)
            self.assertTrue(Path(value).is_relative_to(self.root / 'woow-builder'))
            self.assertEqual(Path(value).stat().st_mode & 0o777, 0o700)
        for observed in map(json.loads, self.env_log.read_text().splitlines()):
            for key, value in exports.items():
                self.assertEqual(observed[key], value)
        for key in exports:
            with self.subTest(key=key), self.assertRaises(b.Denied):
                b.environment(dict(self.env, **{key: '/invented/ambient'}), prepared=True)

    def test_workflow_github_env_scopes_prepare_setup_build_and_candidate(self):
        # Drive the real CLI entry point and its real GITHUB_ENV serialization.
        # Future route/asset are mocked; only owned fake Docker is executable.
        import validate as v
        workflow = v.load(v.ROOT / '.github/workflows/ci.yaml')
        github_env = self.root / 'github-env'
        env = dict(self.env, HOME='/invented/old-home', XDG_CONFIG_HOME='/invented/old-xdg',
                   GITHUB_ENV=str(github_env))
        steps = workflow['jobs']['images']['steps']
        self.assertEqual(steps[1]['run'], 'python3 packaging/builder_contract.py prepare')
        with patch.dict(os.environ, env, clear=True), patch.object(sys, 'argv', ['guard', 'prepare']), \
             patch.object(b.subprocess, 'check_output', return_value='a' * 40), \
             patch.object(b.platform, 'machine', return_value='x86_64'):
            b.main()
        exported = dict(line.split('=', 1) for line in github_env.read_text().splitlines())
        self.assertEqual(exported, b.exports(env))
        env.update(exported)  # Exactly how subsequent workflow steps receive it.
        b.setup(env, 'docker')
        b.verify(env)
        # Simulate downstream process environment, NOT Docker build/auth semantics.
        for stage in ('build', 'candidate'):
            output = subprocess.check_output([sys.executable, '-c',
                'import os,json; print(json.dumps(dict(os.environ)))'], env=env, text=True)
            inherited = json.loads(output)
            for key, value in exported.items():
                self.assertEqual(inherited[key], value, stage)
            self.assertFalse(any(key.upper().endswith('_PROXY') for key in inherited))
        for observed in map(json.loads, self.env_log.read_text().splitlines()):
            for key, value in exported.items():
                self.assertEqual(observed[key], value)

    def test_later_proxy_helper_and_config_changes_deny_without_query(self):
        self.prepare()
        self.log.unlink()
        for key in ('NO_PROXY', 'https_proxy', 'PASSWORD_STORE_DIR', 'DBUS_SESSION_BUS_ADDRESS',
                    'XDG_CONFIG_DIRS', 'XDG_DATA_DIRS'):
            with self.subTest(key=key), self.assertRaises(b.Denied):
                b.verify(dict(self.env, **{key: 'INVENTED-ONLY'}))
            self.assertFalse(self.log.exists())
        config = Path(self.env['DOCKER_CONFIG'], 'config.json')
        for value in ({}, {'auths': {}}, dict(b.ANONYMOUS_CONFIG, credsStore='pass'),
                      dict(b.ANONYMOUS_CONFIG, credHelpers={'ghcr.io': 'secretservice'}),
                      dict(b.ANONYMOUS_CONFIG, proxies={'default': {'httpsProxy': 'invented'}}),
                      {'auths': {'ghcr.io': {'auth': 'INVENTED-NOT-A-CREDENTIAL'}}}):
            config.write_text(json.dumps(value))
            with self.subTest(config=value), self.assertRaises(b.Denied):
                b.verify(self.env)
            self.assertFalse(self.log.exists())

    def test_private_config_survives_source_defined_late_file_store_shape(self):
        self.prepare()
        # Pinned file_store.Store updates a single registry entry, retaining the
        # sentinel. This shape permits the later login in our NEW config only.
        # No Docker/helper/login is run; candidate verify must reject late auth.
        config = Path(self.env['DOCKER_CONFIG'], 'config.json')
        value = json.loads(config.read_text())
        value['auths']['ghcr.io'] = {'auth': 'INVENTED-NOT-A-CREDENTIAL'}
        config.write_text(json.dumps(value))
        self.assertEqual(value['auths']['bld2-anonymous.invalid'], {})
        self.log.unlink()
        with self.assertRaises(b.Denied):
            b.verify(self.env)
        self.assertFalse(self.log.exists())

    def test_missing_unapproved_and_unknown_approval_never_call_docker(self):
        for approval in (None, {}, {'status': 'NOT_APPROVED'},
                         dict(self.approval, engine=None),
                         dict(self.approval, engine='latest'),
                         dict(self.approval, buildkit='unknown'),
                         dict(self.approval, buildx='latest'),
                         dict(self.approval, extra='--privileged'),
                         dict(self.approval, expires='2000-01-01T00:00:00+00:00')):
            with self.subTest(approval=approval):
                env = dict(self.env, BLD2_APPROVAL=json.dumps(approval))
                with self.assertRaises(b.Denied):
                    b.prepare(env)
                self.assertFalse(self.log.exists())

    def test_pr_wrong_source_and_unenrolled_runner_deny_before_docker(self):
        for key, value in [('GITHUB_EVENT_NAME', 'pull_request'),
                           ('GITHUB_REF', 'refs/heads/other'), ('GITHUB_SHA', 'b' * 40),
                           ('RUNNER_NAME', 'ambient'), ('RUNNER_ARCH', 'ARM64')]:
            with self.subTest(key=key), self.assertRaises(b.Denied):
                b.prepare(dict(self.env, **{key: value}))
            self.assertFalse(self.log.exists())

    def test_ambient_endpoints_and_unsafe_options_deny_before_docker(self):
        for key, value in [('DOCKER_HOST', 'unix:///var/run/docker.sock'),
                           ('DOCKER_CONTEXT', 'default'), ('DOCKER_CONFIG', '/private'),
                           ('DOCKER_TLS_VERIFY', ''), ('DOCKER_API_VERSION', '1.99'),
                           ('DOCKER_AUTH_CONFIG', '{}'), ('BUILDX_BUILDER', 'remote'),
                           ('BUILDX_CONFIG', '/private'), ('BUILDKIT_HOST', 'tcp://remote'),
                           ('BUILDKITD_FLAGS', '--oci-worker-no-process-sandbox'),
                           ('BUILDER_NODE_0_AUTH_TLS_CERT', 'mock')]:
            with self.subTest(key=key), self.assertRaises(b.Denied):
                b.prepare(dict(self.env, **{key: value}))
            self.assertFalse(self.log.exists())

    def test_mock_identity_receipt_not_isolation_attestation(self):
        self.prepare()
        receipt = b.verify(self.env)
        self.assertEqual(receipt['driver'], 'docker')
        self.assertEqual(receipt['buildkit'], 'v99.3.0')
        self.assertEqual(receipt['engine_id'], 'mock-engine')
        self.assertNotIn('isolation_verified', receipt)
        commands = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertFalse(any('run' in c or 'create' in c or '--bootstrap' in c for c in commands))
        self.assertEqual(json.loads((self.root / 'woow-builder/identity.json').read_text()), receipt)

    def test_remote_context_denied_before_engine_contact(self):
        self.responses['context inspect default'][0]['Endpoints']['docker']['Host'] = 'tcp://remote:2375'
        with self.assertRaises(b.Denied):
            self.prepare()
        self.assertNotIn('version', self.log.read_text())

    def test_runtime_engine_identity_and_arch_mismatch(self):
        for section, key, value in [('Server', 'Version', '99.2.1'),
                                    ('Client', 'Version', '99.0.0'),
                                    ('Server', 'Arch', 'arm64'),
                                    ('Server', 'ApiVersion', '1.98')]:
            with self.subTest(key=key):
                original = copy.deepcopy(self.responses['version --format {{json .}}'])
                self.responses['version --format {{json .}}'][section][key] = value
                self.sync()
                with self.assertRaises(b.Denied):
                    b.engine_facts(self.approval, self.env, self.env)
                self.responses['version --format {{json .}}'] = original
        self.responses['info --format {{json .}}']['ID'] = 'someone-elses-engine'
        self.sync()
        with self.assertRaises(b.Denied):
            b.engine_facts(self.approval, self.env, self.env)

    def test_wrong_driver_buildkit_arch_multi_node_and_unsafe_options(self):
        self.prepare()
        mutations = [('Driver', 'docker-container'), ('Driver', 'remote'),
                     ('Current', False), ('Dynamic', True),
                     ('Nodes', [self.node, self.node])]
        for key, value in mutations:
            self.responses['buildx ls --format json'] = dict(self.builder, **{key: value})
            self.sync()
            with self.subTest(key=key, value=value), self.assertRaises(b.Denied):
                b.verify(self.env)
        for key, value in [('Version', ''), ('Version', 'v99.3.1'),
                           ('Platforms', ['linux/arm64']), ('Endpoint', 'tcp://remote'),
                           ('Flags', ['--oci-worker-no-process-sandbox']),
                           ('Flags', ['--allow-insecure-entitlement=network.host']),
                           ('DriverOpts', {'network': 'host'}),
                           ('Files', {'buildkitd.toml': 'mock'}), ('Status', 'stopped')]:
            self.responses['buildx ls --format json'] = dict(self.builder,
                Nodes=[dict(self.node, **{key: value})])
            self.sync()
            with self.subTest(key=key, value=value), self.assertRaises(b.Denied):
                b.verify(self.env)

    def test_cli_default_denial_is_nonzero_and_no_docker(self):
        env = dict(self.env)
        del env['BLD2_APPROVAL']
        result = subprocess.run([sys.executable, str(Path(b.__file__)), 'admit'],
                                env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Builder gate DENIED', result.stderr)
        self.assertNotIn('PASS', result.stdout)
        self.assertFalse(self.log.exists())

    def test_real_cli_approved_marker_cannot_unblock_personal_route(self):
        # Unlike in-process fixtures, a real CLI has no patched hosting route.
        env = dict(self.env, BLD2_HOSTING_APPROVED='true', RUNNER_GROUP='woow-disposable-builder')
        for args in (['admit'], ['prepare'], ['setup', '--driver', 'docker'], ['verify']):
            result = subprocess.run([sys.executable, str(Path(b.__file__)), *args],
                                    env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('personal-repository route BLOCKED', result.stderr)
            self.assertNotIn('contract matched', result.stdout)
            self.assertFalse(self.log.exists())
            self.assertFalse((self.root / 'woow-builder').exists())

    def test_fresh_config_required_and_verify_rejects_changed_environment(self):
        self.prepare()
        with self.assertRaises(b.Denied):
            b.prepare(self.env)
        for key, value in [('DOCKER_CONFIG', '/private/ambient'),
                           ('DOCKER_HOST', b.ENDPOINT), ('BUILDX_BUILDER', 'default')]:
            with self.subTest(key=key), self.assertRaises(b.Denied):
                b.verify(dict(self.env, **{key: value}))
        env = dict(self.env)
        del env['DOCKER_CONFIG']
        with self.assertRaises(b.Denied):
            b.prepare(env)

    def test_bad_json_command_failure_and_buildx_version_deny(self):
        self.prepare()
        for key, value in [('buildx ls --format json', 'not-json'),
                           ('buildx version', 'github.com/docker/buildx v0.0.0 mock')]:
            original = self.responses[key]
            self.responses[key] = value
            self.sync()
            with self.subTest(key=key), self.assertRaises(b.Denied):
                b.verify(self.env)
            self.responses[key] = original
        del self.responses['buildx version']
        self.sync()
        with self.assertRaises(b.Denied):
            b.verify(self.env)


if __name__ == '__main__':
    unittest.main()
