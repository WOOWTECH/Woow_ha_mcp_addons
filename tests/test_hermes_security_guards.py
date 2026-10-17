"""Commercial acceptance AI-HMCP-001-1 / -001-3 / -002-2 (PaaS QA service 249, 2026-10-16; the same code is vendored
here and was still open after #5):

- 001-1: hermes_session / hermes_cron / hermes_webhook / hermes_tools / hermes_mcp put session_id, job_id and names into
  the dashboard URL with an f-string. HTTPX normalizes ".." before sending, so session_id="../config/raw" read
  GET /api/config/raw (the raw yaml with the provider api_key in plain text). backend_policy's path check sees the
  already-normalized /api/config/raw and lets it through.
- 001-3: hermes_config set compared keys with exact string equality: "terminal" (replaces the whole subtree with a
  scalar), "Terminal.Backend", surrounding spaces, full-width or zero-width characters, "model", "mcp_servers.x"...
- 002-2: hermes_mcp add only refused a lower-case "stdio:" / "command:" prefix ("STDIO:", " stdio:", file://, link-local
  and loopback URLs were registered in Hermes).

The real Hermes child against a LOCAL fake dashboard that records every request: a refusal must send nothing.
"""
import json

import pytest

from test_six_hardening import Quiet, call, runtime, serve


def dashboard(requests):
    class Dashboard(Quiet):
        def _record(self, method):
            length = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(length) if length else b''
            if self.path == '/auth/password-login':
                self.send_response(200)
                self.send_header('Set-Cookie', 'hermes_session_at=session-cookie-0815')
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'{}')
                return
            requests.append((method, self.path, body))
            self.reply({'ok': True, 'display': {'compact': False}})

        def do_GET(self):
            self._record('GET')

        def do_POST(self):
            self._record('POST')

        def do_PUT(self):
            self._record('PUT')

        def do_DELETE(self):
            self._record('DELETE')
    return Dashboard


def reply_of(response):
    assert response.status_code == 200, response.text
    body = response.text
    data = next((line[5:].strip() for line in body.splitlines() if line.startswith('data:')), body)
    return json.loads(data)['result']


def text_of(response):
    return json.loads(reply_of(response)['content'][0]['text'])


TRAVERSAL = ['..', '.', '../config/raw', '../status', 'a/../../config/raw', 'a/b', '%2e%2e', '..%2fconfig', 'x?y=1',
             'x#f', 'a\\..\\b', 'x\u200b', ' lead']
VALID = ['20261016_193839_d56dfbc7', '4f7520a8-b5bc-4a89-b360-0046f2125c8c', 'ac584d0a4512']


def id_calls(value):
    return [
        ('hermes_session', {'action': 'get', 'session_id': value}),
        ('hermes_session', {'action': 'delete', 'session_id': value}),
        ('hermes_cron', {'action': 'update', 'job_id': value, 'prompt': 'p'}),
        ('hermes_cron', {'action': 'delete', 'job_id': value}),
        ('hermes_cron', {'action': 'trigger', 'job_id': value}),
        ('hermes_cron', {'action': 'pause', 'job_id': value}),
        ('hermes_cron', {'action': 'resume', 'job_id': value}),
        ('hermes_webhook', {'action': 'delete', 'name': value}),
        ('hermes_webhook', {'action': 'toggle', 'name': value}),
        ('hermes_tools', {'action': 'enable', 'toolset': value}),
        ('hermes_tools', {'action': 'disable', 'toolset': value}),
        ('hermes_mcp', {'action': 'remove', 'name': value}),
    ]


ALL_WRITES = ['hermes_session:delete', 'hermes_cron:update', 'hermes_cron:delete', 'hermes_cron:trigger',
              'hermes_cron:pause', 'hermes_cron:resume', 'hermes_webhook:delete', 'hermes_webhook:toggle',
              'hermes_tools:enable', 'hermes_tools:disable', 'hermes_mcp:remove', 'hermes_mcp:add', 'hermes_config:set']


async def test_ids_with_path_syntax_never_reach_the_dashboard(tmp_path):
    requests = []
    with serve(dashboard(requests)) as url:
        async with runtime(tmp_path, 'hermes', url, write_grants=ALL_WRITES) as (client, headers, *_):
            for value in TRAVERSAL:
                for name, arguments in id_calls(value):
                    out = text_of(await client.post('/mcp', headers=headers, json=call(name, arguments)))
                    assert 'error' in out and 'invalid' in out['error'], (name, value, out)
            assert requests == [], requests

            for value in VALID:
                for name, arguments in id_calls(value):
                    await client.post('/mcp', headers=headers, json=call(name, arguments))
            paths = {path for _, path, _ in requests}
            assert not any('/config' in p or '/status' in p for p in paths), paths
            assert '/api/sessions/20261016_193839_d56dfbc7' in paths
            assert '/api/cron/jobs/ac584d0a4512/trigger' in paths
            assert '/api/mcp/servers/4f7520a8-b5bc-4a89-b360-0046f2125c8c' in paths


DENIED_KEYS = ['terminal.backend', 'Terminal.Backend', 'TERMINAL.BACKEND', ' terminal.backend ', 'terminal..backend',
               'terminal.backend[0]', 'terminal', 'terminal.cwd', 'ｔｅｒｍｉｎａｌ.backend',
               'terminal\u200b.backend', 'ter\u00admi\u00adnal', 'secrets', 'secrets.a', 'api_server', 'api_server.host',
               'dashboard', 'dashboard.basic_auth.password', 'model', 'model.provider', 'mcp_servers', 'mcp_servers.x',
               'security.tirith_path', 'providers.openrouter', 'custom_providers', 'display.api_key',
               'agent.access_token', '_config_version', 'a b', '   ']


async def test_config_deny_list_is_normalized(tmp_path):
    requests = []
    with serve(dashboard(requests)) as url:
        async with runtime(tmp_path, 'hermes', url, write_grants=['hermes_config:set']) as (client, headers, *_):
            for key in DENIED_KEYS:
                for dry_run in (True, False):
                    out = text_of(await client.post('/mcp', headers=headers, json=call('hermes_config', {
                        'action': 'set', 'key': key, 'value': '"local"', 'dry_run': dry_run})))
                    assert 'error' in out and out.get('dry_run') is not True, (key, out)
            assert not any(method == 'PUT' for method, _, _ in requests), requests

            for key in ('display.compact', 'max_live_sessions', 'Display.Compact'):
                out = text_of(await client.post('/mcp', headers=headers, json=call('hermes_config', {
                    'action': 'set', 'key': key, 'value': 'true'})))
                assert out == {'ok': True, 'key': key, 'value': True}, out
            puts = [json.loads(body) for method, _, body in requests if method == 'PUT']
            assert puts == [{'config': {'display.compact': True}}, {'config': {'max_live_sessions': True}},
                            {'config': {'Display.Compact': True}}]


BLOCKED_MCP_URLS = ['stdio:/bin/true', 'STDIO:/bin/true', ' stdio:/bin/true', '\tStdIo:/bin/true', 'command:/bin/true',
                    'COMMAND:/bin/true', 'file:///bin/true', 'gopher://example.com/', '/bin/true', 'example.com/mcp',
                    'http://169.254.169.254/', 'http://127.0.0.1:8000/mcp', 'http://[::1]:8000/mcp',
                    'http://0.0.0.0:8000/mcp', 'http://localhost:8000/mcp', 'http://100.100.100.200/',
                    'http://metadata.google.internal/', 'http://user:pass@192.168.1.10/mcp', '   ']


async def test_mcp_add_accepts_only_http_servers_the_backend_policy_allows(tmp_path):
    requests = []
    with serve(dashboard(requests)) as url:
        async with runtime(tmp_path, 'hermes', url, write_grants=['hermes_mcp:add']) as (client, headers, *_):
            for target in BLOCKED_MCP_URLS:
                out = text_of(await client.post('/mcp', headers=headers, json=call('hermes_mcp', {
                    'action': 'add', 'name': 'qa', 'url': target})))
                assert 'error' in out, (target, out)
            out = text_of(await client.post('/mcp', headers=headers, json=call('hermes_mcp', {
                'action': 'add', 'name': '../x', 'url': 'http://192.168.1.10:8123/mcp'})))
            assert 'error' in out
            assert requests == [], requests

            # A LAN MCP server (the add-on's backend policy allows private addresses) is registered, URL stripped.
            out = text_of(await client.post('/mcp', headers=headers, json=call('hermes_mcp', {
                'action': 'add', 'name': 'lan', 'url': '  http://192.168.1.10:8123/mcp '})))
            assert out == {'ok': True, 'name': 'lan', 'added': True}, out
            assert [(m, p, json.loads(b)) for m, p, b in requests] == [('POST', '/api/mcp/servers', {
                'name': 'lan', 'transport': 'streamable-http', 'url': 'http://192.168.1.10:8123/mcp'})]
