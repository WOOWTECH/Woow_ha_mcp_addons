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
            if run_fails and command[:2] == ['docker', 'run']:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)

        with patch.object(acceptance.subprocess, 'check_output', side_effect=output), \
             patch.object(acceptance.subprocess, 'run', side_effect=run), \
             patch.object(acceptance.secrets, 'token_hex', return_value='c' * 16):
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

    def test_every_product_whose_child_refuses_loopback_gets_the_one_use_bridge(self):
        """Multi-profile HM-20 (plan 8.7): the child of a switched-on product (features.MULTI_PROFILE_PRODUCTS) gets
        WOOW_MCP_DENY_LOOPBACK=1 and refuses a loopback backend, as Headscale's child always does, so the probe's mock
        backend cannot be on 127.0.0.1 for it either: it needs this one-use internal bridge, and a private address
        (container_probe.mock_bind_host, packaging/test_container_probe.py). The test double tests/loopback_backends.py
        is in no image. The set is empty today, so this checks Headscale; the release PR that switches a product on
        (HM-19a, HM-21 to HM-26) fails here until its candidate gets the bridge."""
        for app in sorted({'headscale', *features.MULTI_PROFILE_PRODUCTS}):
            with self.subTest(app=app):
                commands = self.invoke(app)
                self.assertEqual(commands[1][:4], ['docker', 'network', 'create', '--internal'])
                self.assertEqual(commands[3][:6], ['docker', 'run', '--rm', '--init', '--network', NETWORK_ID])
                self.assertEqual(commands[-1], ['docker', 'network', 'rm', NETWORK_ID])


if __name__ == '__main__':
    unittest.main()
