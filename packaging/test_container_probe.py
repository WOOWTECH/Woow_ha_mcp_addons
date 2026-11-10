"""Headscale's owned backend fixture and bind-address guard, without Docker."""
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/mcp-admin-core'), str(ROOT / 'apps/n8n')]
with patch.object(sys, 'argv', ['container_probe.py', 'headscale']):
    import container_probe as probe


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


if __name__ == '__main__':
    unittest.main()
