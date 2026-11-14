"""Headscale's owned backend fixture and bind-address guard; the direct child bearer check (HM-06). Without Docker."""
import asyncio
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


if __name__ == '__main__':
    unittest.main()
