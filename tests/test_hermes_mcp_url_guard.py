"""AI-HMCP-002-2 (commercial acceptance 2026-10-16), loopback part restored in 0.3.4.

``hermes_mcp`` action=add registers a URL that Hermes itself connects to later, from its own host. The finding required
refusing stdio/command transports and loopback and link-local MCP server URLs (the old HA test,
fix/hermes-mcp-security-20261018 tests/test_hermes_security_guards.py, listed them in BLOCKED_MCP_URLS). 0.3.0's guard
reuses apps/runtime/backend_policy.py (Destination and the resolver's address classes), which deliberately permits
loopback for the add-on's own configured backends, so ``http://127.0.0.1:8000/mcp``, ``http://[::1]:8000/mcp`` and
``http://localhost:8000/mcp`` were registered again. The Hermes guard now refuses localhost names (localhost,
*.localhost, localhost.localdomain) and every loopback answer (127.0.0.0/8, ::1, IPv4-mapped loopback); LAN destinations
stay allowed (the HA add-on lets Hermes use LAN services), metadata, link-local and 0.0.0.0 stay refused as before, and
backend_policy's own rule is unchanged.

The real Hermes child against a LOCAL fake dashboard that records every request: a refused URL sends no dashboard API
request (the dashboard login that every dashboard tool performs first, unchanged from the PaaS server, is recorded
separately); errors are 0.3.0's stable error text, not JSON.
"""
import json

from test_real_products import rpc
from test_six_hardening import Quiet, call, runtime, serve

# The old list, unchanged.
BLOCKED_MCP_URLS = ['stdio:/bin/true', 'STDIO:/bin/true', ' stdio:/bin/true', '\tStdIo:/bin/true', 'command:/bin/true',
                    'COMMAND:/bin/true', 'file:///bin/true', 'gopher://example.com/', '/bin/true', 'example.com/mcp',
                    'http://169.254.169.254/', 'http://127.0.0.1:8000/mcp', 'http://[::1]:8000/mcp',
                    'http://0.0.0.0:8000/mcp', 'http://localhost:8000/mcp', 'http://100.100.100.200/',
                    'http://metadata.google.internal/', 'http://user:pass@192.168.1.10/mcp', '   ']
# Other spellings of the same loopback destinations (names, numeric forms, mapped and expanded IPv6), and link-local.
LOOPBACK_SPELLINGS = ['http://LOCALHOST:8000/mcp', 'http://localhost.:8000/mcp', 'http://api.localhost:8000/mcp',
                      'http://localhost.localdomain:8000/mcp', 'http://127.1:8000/mcp', 'http://2130706433:8000/mcp',
                      'http://127.255.255.254/mcp', 'http://[0:0:0:0:0:0:0:1]:8000/mcp',
                      'https://[::ffff:127.0.0.1]:8443/mcp', 'http://[fe80::1]/mcp', 'http://169.254.10.10/mcp']
LOOPBACK = ['http://127.0.0.1:8000/mcp', 'http://[::1]:8000/mcp', 'http://localhost:8000/mcp',
            *[u for u in LOOPBACK_SPELLINGS if '[fe80' not in u and '169.254' not in u and 'ffff' not in u]]


def dashboard(logins, requests):
    class Dashboard(Quiet):
        def _record(self, method):
            length = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(length) if length else b''
            if self.path == '/auth/password-login':
                logins.append(method)
                self.send_response(200)
                self.send_header('Set-Cookie', 'hermes_session_at=session-cookie-0315')
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'{}')
                return
            requests.append((method, self.path, body))
            self.reply({'ok': True})

        def do_GET(self):
            self._record('GET')

        def do_POST(self):
            self._record('POST')

        def do_PUT(self):
            self._record('PUT')

        def do_DELETE(self):
            self._record('DELETE')
    return Dashboard


def text(result):
    return result['content'][0]['text']


async def test_mcp_add_refuses_loopback_and_keeps_lan_servers(tmp_path):
    logins, requests = [], []
    with serve(dashboard(logins, requests)) as url:
        async with runtime(tmp_path, 'hermes', url, write_grants=['hermes_mcp:add']) as (client, headers, *_):
            async def add(name, target):
                return await rpc(client, '/mcp', headers, call('hermes_mcp', {'action': 'add', 'name': name, 'url': target}))

            for target in BLOCKED_MCP_URLS + LOOPBACK_SPELLINGS:
                result = await add('qa', target)
                assert result.get('isError') is True, (target, result)
                if target in LOOPBACK:
                    assert 'loopback MCP servers' in text(result), (target, result)
            refused = await add('../x', 'http://192.168.1.10:8123/mcp')
            assert refused.get('isError') is True, refused
            assert requests == [], requests  # nothing reached the dashboard API

            # LAN MCP servers (private and ULA addresses, which backend_policy allows) are registered, URL stripped.
            for name, target in [('lan', '  http://192.168.1.10:8123/mcp '), ('ula', 'http://[fd00::5]:8123/mcp')]:
                result = await add(name, target)
                assert not result.get('isError') and json.loads(text(result)) == {'ok': True, 'name': name, 'added': True}
            assert [(m, p, json.loads(b)) for m, p, b in requests] == [
                ('POST', '/api/mcp/servers', {'name': 'lan', 'transport': 'streamable-http', 'url': 'http://192.168.1.10:8123/mcp'}),
                ('POST', '/api/mcp/servers', {'name': 'ula', 'transport': 'streamable-http', 'url': 'http://[fd00::5]:8123/mcp'})]
            assert logins and set(logins) == {'POST'}  # the dashboard login, the only other contact
