"""Candidate Docker invocation contract; all Docker calls are mocked."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import container_acceptance as acceptance

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'packages/mcp-admin-core')]
from mcp_admin_core import features  # noqa: E402  (HM-20: the products whose child refuses a loopback backend)


IMAGE_ID = 'sha256:' + 'a' * 64
NETWORK_ID = 'b' * 64


def switched(*products):
    """The product switch as an upgrade PR sets it (the repository keeps it empty), for this test only."""
    return patch.object(features, 'MULTI_PROFILE_PRODUCTS', frozenset(products))


def probe_run(app, network):
    """The docker run of the probe before HM-16, word for word."""
    probe = Path(acceptance.__file__).resolve().parent
    return ['docker', 'run', '--rm', '--init', '--network', network, '--read-only',
            '--tmpfs', '/data:rw,nosuid,nodev,mode=0755', '--tmpfs', '/tmp:rw,nosuid,nodev,mode=1777',
            '--mount', f'type=bind,source={probe},target=/probe-package,readonly',
            '--entrypoint', '/opt/woow/.venv/bin/python', IMAGE_ID, '/probe-package/container_probe.py', app]


class CandidateInvocationTests(unittest.TestCase):
    def invoke(self, app, *, internal=True, run_fails=False):
        version = acceptance.version_for(app)
        image = f'local/mcp-{app}:{version}'
        metadata = {'Architecture': 'amd64', 'Os': 'linux', 'Id': IMAGE_ID,
                    'Config': {'Labels': {'io.hass.type': 'app', 'io.hass.arch': 'amd64',
                                          'io.hass.version': version},
                               'ExposedPorts': {'8081/tcp': {}},
                               'Entrypoint': ['/usr/local/bin/python', '/opt/woow/packaging/entrypoint.py', app]}}
        commands = []
        self.limits = []

        def output(command, **kwargs):
            commands.append(command)
            if command[:3] == ['docker', 'image', 'inspect']:
                return json.dumps([metadata]).encode()
            if command[:3] == ['docker', 'network', 'create']:
                return NETWORK_ID + '\n'
            if command[:3] == ['docker', 'network', 'inspect']:
                return json.dumps([{'Id': NETWORK_ID, 'Internal': internal,
                                    'Driver': 'bridge', 'Containers': {}}]).encode()
            raise AssertionError(command)

        def run(command, **kwargs):
            commands.append(command)
            if command[:2] == ['docker', 'run']:
                self.limits.append(kwargs.get('timeout'))
            if run_fails and command[:2] == ['docker', 'run']:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)

        with patch.object(acceptance.subprocess, 'check_output', side_effect=output), \
             patch.object(acceptance.subprocess, 'run', side_effect=run), \
             patch.object(acceptance.secrets, 'token_hex', return_value='c' * 16), \
             patch('builtins.print'):
            if run_fails:
                with self.assertRaises(subprocess.CalledProcessError):
                    acceptance.main(app, image, expected_id=IMAGE_ID)
            elif not internal:
                with self.assertRaisesRegex(AssertionError, 'mock network not isolated'):
                    acceptance.main(app, image, expected_id=IMAGE_ID)
            else:
                acceptance.main(app, image, expected_id=IMAGE_ID)
        return commands

    def test_headscale_uses_one_use_internal_bridge_and_cleans_up(self):
        commands = self.invoke('headscale')
        self.assertEqual(commands[1], ['docker', 'network', 'create', '--internal', '--driver', 'bridge',
                                       'woow-headscale-candidate-' + 'c' * 16])
        self.assertEqual(commands[2], ['docker', 'network', 'inspect', NETWORK_ID])
        runtime = commands[3]
        self.assertEqual(runtime[:7], ['docker', 'run', '--rm', '--init', '--network', NETWORK_ID, '--read-only'])
        self.assertIn('/probe-package/container_probe.py', runtime)
        self.assertEqual(commands[4], ['docker', 'network', 'rm', NETWORK_ID])

    def test_headscale_removes_network_when_runtime_or_isolation_check_fails(self):
        for options in ({'run_fails': True}, {'internal': False}):
            with self.subTest(options=options):
                commands = self.invoke('headscale', **options)
                self.assertEqual(commands[-1], ['docker', 'network', 'rm', NETWORK_ID])

    def test_existing_candidate_keeps_network_none(self):
        commands = self.invoke('emqx')
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[1][:7], ['docker', 'run', '--rm', '--init', '--network', 'none', '--read-only'])

    def test_a_candidate_not_switched_on_is_invoked_as_before(self):
        """Multi-profile HM-16: every store product not switched on gets the docker commands and the 180 s limit it got
        before HM-16 (Headscale its one-use bridge, every other product network none)."""
        with switched():
            for app in acceptance.PRODUCTS:
                with self.subTest(app=app):
                    commands = self.invoke(app)
                    if app == 'headscale':
                        self.assertEqual(commands[1:], [
                            ['docker', 'network', 'create', '--internal', '--driver', 'bridge',
                             'woow-headscale-candidate-' + 'c' * 16], ['docker', 'network', 'inspect', NETWORK_ID],
                            probe_run(app, NETWORK_ID), ['docker', 'network', 'rm', NETWORK_ID]])
                    else:
                        self.assertEqual(commands[1:], [probe_run(app, 'none')])
                    self.assertEqual(self.limits, [180])

    def test_a_switched_on_candidate_gets_the_one_use_bridge_and_the_longer_limit(self):
        """Multi-profile HM-16 (HM-20 review MF-2; HM-20 left a tripwire here, now the rule itself): every child of a
        switched-on product gets WOOW_MCP_DENY_LOOPBACK=1 and refuses a loopback backend, as Headscale's child always
        does, so the probe's mock backend needs this one-use internal bridge and a private address
        (container_probe.mock_bind_host, packaging/test_container_probe.py); tests/loopback_backends.py is in no image.
        The probe runs the multi-profile stage after the single-profile path: 360 s instead of 180."""
        for app in acceptance.PRODUCTS:
            with self.subTest(app=app), switched(app):
                commands = self.invoke(app)
                self.assertEqual(commands[1:], [
                    ['docker', 'network', 'create', '--internal', '--driver', 'bridge',
                     f'woow-{app}-candidate-' + 'c' * 16], ['docker', 'network', 'inspect', NETWORK_ID],
                    probe_run(app, NETWORK_ID), ['docker', 'network', 'rm', NETWORK_ID]])
                self.assertEqual(self.limits, [acceptance.MULTI_PROFILE_PROBE_SECONDS])
                self.assertEqual(acceptance.MULTI_PROFILE_PROBE_SECONDS, 360)
                commands = self.invoke(app, run_fails=True)
                self.assertEqual(commands[-1], ['docker', 'network', 'rm', NETWORK_ID])

    def test_the_repository_switch_decides_it(self):
        """What HM-20's tripwire guarded: a product an upgrade PR switches on gets the bridge at once."""
        for app in acceptance.PRODUCTS:
            with self.subTest(app=app):
                commands = self.invoke(app)
                bridged = app == 'headscale' or app in features.MULTI_PROFILE_PRODUCTS
                self.assertEqual(commands[1][:4] == ['docker', 'network', 'create', '--internal'], bridged)


if __name__ == '__main__':
    unittest.main()
