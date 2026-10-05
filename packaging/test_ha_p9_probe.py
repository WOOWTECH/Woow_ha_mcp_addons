"""Offline tests for the P9 kit probe against a scripted MCP server. No HA, Docker or network."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
import uuid

import ha_p9_probe as probe

TOKEN = 'tok-' + 'x' * 40
TOOLS = [{'name': 'search_nodes'}, {'name': 'tools_documentation'}, {'name': 'n8n_list_workflows'}]
DENIED = {'n8n_delete_workflow', 'definitely_not_a_tool'}  # the gateway refuses these with HTTP 403
BACKEND_TOOLS = {'n8n_list_workflows'}


class FakeMCP(ThreadingHTTPServer):
    """Bearer auth, initialize/notifications/tools, DELETE, a session cap (429) like n8n-mcp."""

    def __init__(self, cap=20):
        super().__init__(('127.0.0.1', 0), Handler)
        self.cap, self.sessions, self.lock = cap, set(), threading.Lock()
        self.outage = False
        self.calls = []
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def port(self):
        return self.server_address[1]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body=None, headers=None, sse=False):
        raw = b'' if body is None else (('event: message\ndata: %s\n\n' % json.dumps(body)) if sse
                                        else json.dumps(body)).encode()
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header('Content-Type', 'text/event-stream' if sse else 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        return self.headers.get('Authorization') == 'Bearer ' + TOKEN

    def do_DELETE(self):
        if not self.authorized():
            return self.reply(401)
        with self.server.lock:
            sid = self.headers.get('Mcp-Session-Id')
            if sid not in self.server.sessions:
                return self.reply(404)
            self.server.sessions.discard(sid)
        self.reply(204)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.calls.append(body.get('method'))
        if not self.authorized():
            return self.reply(401)
        method, sid = body.get('method'), self.headers.get('Mcp-Session-Id')
        if method == 'initialize':
            with self.server.lock:
                if len(self.server.sessions) >= self.server.cap:
                    return self.reply(429, {'error': 'Session limit reached'})
                sid = uuid.uuid4().hex
                self.server.sessions.add(sid)
            return self.reply(200, {'jsonrpc': '2.0', 'id': body['id'], 'result': {'serverInfo': {'name': 'fake'}}},
                              {'Mcp-Session-Id': sid})
        if sid not in self.server.sessions:
            return self.reply(404)
        if method == 'notifications/initialized':
            return self.reply(202)
        if method == 'tools/list':
            return self.reply(200, {'jsonrpc': '2.0', 'id': body['id'], 'result': {'tools': TOOLS}}, sse=True)
        if method == 'tools/call':
            name = body['params']['name']
            if name in DENIED:
                return self.reply(403, {'jsonrpc': '2.0', 'id': body['id'],
                                        'error': {'code': -32001, 'message': 'request denied'}})
            if name == 'not_ready_tool':  # a plain-text error body, like a proxy in front of the gateway
                raw = b'child transport not ready'
                self.send_response(503)
                self.send_header('Content-Type', 'text/plain')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                return self.wfile.write(raw)
            known = name in {t['name'] for t in TOOLS}
            text = '{"success": false, "code": "NO_RESPONSE"}' if self.server.outage and name in BACKEND_TOOLS else 'ok'
            return self.reply(200, {'jsonrpc': '2.0', 'id': body['id'], 'result': {
                'content': [{'type': 'text', 'text': text}], 'isError': not known}})
        self.reply(400)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeMCP(cap=3)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def main(self, *argv, stdin=''):
        out = io.StringIO()
        summary = probe.main(['--port', str(self.server.port)] + list(argv), io.StringIO(stdin), out)
        self.assertNotIn(TOKEN, out.getvalue())
        return summary, out.getvalue()

    def test_check_reports_each_token_and_closes_sessions(self):
        summary, text = self.main('check', stdin='valid\t%s\nwrong\tnope\n' % TOKEN)
        rows = {row['label']: row for row in summary['check']}
        self.assertEqual((rows['valid']['initialize'], rows['valid']['tools_list'], rows['valid']['tools'],
                          rows['valid']['delete']), (200, 200, 3, 204))
        self.assertEqual((rows['wrong']['initialize'], rows['wrong']['tools']), (401, 0))
        self.assertEqual(self.server.sessions, set())
        self.assertIn('SUMMARY ', text)

    def test_cycle_and_bench_never_exhaust_the_session_cap(self):
        summary, _ = self.main('cycle', '--cycles', '10', stdin=TOKEN + '\n')
        self.assertEqual(summary['cycle'], ['200/204'] * 10)
        summary, _ = self.main('bench', '--sessions', '5', '--requests', '7', '--tool', 'search_nodes',
                               '--args', '{"query": "x"}', stdin=TOKEN + '\n')
        bench = summary['bench']
        self.assertEqual((bench['initialize']['n'], bench['tools_list']['n'], bench['tools_call']['n']), (5, 7, 7))
        self.assertEqual(self.server.sessions, set())

    def test_leaked_sessions_hit_the_cap(self):
        client = probe.Client(self.server.port, TOKEN)
        statuses = [client.open()[0] for _ in range(4)]
        self.assertEqual(statuses, [200, 200, 200, 429])

    def test_bench_fails_closed_on_tool_error(self):
        with self.assertRaises(SystemExit):
            self.main('bench', '--sessions', '1', '--requests', '1', '--tool', 'not_a_tool', stdin=TOKEN + '\n')
        self.assertEqual(self.server.sessions, set())

    PLAN = {'reads': [['search_nodes', {'query': 'x'}], ['n8n_list_workflows', {'limit': 2}]],
            'denials': [['n8n_delete_workflow', {'id': 'none'}], ['definitely_not_a_tool', {}]]}

    def test_plan_reads_succeed_and_denials_are_refused(self):
        summary, text = self.main('plan', stdin=TOKEN + '\n' + json.dumps(self.PLAN))
        self.assertEqual((summary['plan']['passed'], summary['plan']['total']), (4, 4))
        self.assertEqual([r['listed'] for r in summary['plan']['rows']], [True, True, False, False])
        self.assertEqual(self.server.sessions, set())

    def test_plan_outage_requires_structured_failures(self):
        self.server.outage = True
        summary, _ = self.main('plan', '--expect-backend-down', stdin=TOKEN + '\n' + json.dumps(
            {'reads': [['n8n_list_workflows', {}], ['search_nodes', {'query': 'x'}]],
             'denials': [['n8n_delete_workflow', {}]]}))
        # The local tool still answers, the backend tool fails in a structured way, the denial stays 403.
        self.assertEqual((summary['plan']['passed'], summary['plan']['total']), (4, 4))
        with self.assertRaises(SystemExit):  # the same outage without the flag is a failed read
            self.main('plan', stdin=TOKEN + '\n' + json.dumps({'reads': [['n8n_list_workflows', {}]]}))
        self.server.outage = False
        with self.assertRaises(SystemExit):  # a healthy backend is not a structured outage failure
            self.main('plan', '--expect-backend-down', stdin=TOKEN + '\n' + json.dumps({'reads': [['n8n_list_workflows', {}]]}))

    def test_plan_reports_short_error_bodies(self):
        out = io.StringIO()
        plan = {'denials': [['n8n_delete_workflow', {}], ['not_ready_tool', {}]]}
        with self.assertRaises(SystemExit):  # the 503 is not a refusal
            probe.main(['--port', str(self.server.port), 'plan'], io.StringIO(TOKEN + '\n' + json.dumps(plan)), out)
        self.assertIn('http=403 isError=None | error -32001: request denied', out.getvalue())
        self.assertIn('http=503 isError=None | error : child transport not ready', out.getvalue())

    def test_plan_fails_when_a_read_is_denied_or_a_denial_succeeds(self):
        for plan in ({'reads': [['n8n_delete_workflow', {}]]}, {'denials': [['search_nodes', {'query': 'x'}]]}):
            with self.subTest(plan=plan), self.assertRaises(SystemExit):
                self.main('plan', stdin=TOKEN + '\n' + json.dumps(plan))
        self.assertEqual(self.server.sessions, set())

    def test_restart_and_childkill_use_only_the_named_app(self):
        commands = []

        def fake_run(args, timeout=300):
            commands.append(args)
            out = ''
            if args[:2] == ['docker', 'ps']:
                out = 'app_other\napp_repo_woow_mcp_n8n\n'
            elif args[:2] == ['docker', 'inspect']:
                out = '0 2026-10-05T08:06:11Z'
            elif args[:2] == ['docker', 'exec'] and probe.CHILD_SCRIPT in args:
                out = '8\n'
            return subprocess.CompletedProcess(args, 0, out, '')

        with patch.object(probe, 'run', fake_run):
            summary, _ = self.main('restart', '--slug', 'repo_woow_mcp_n8n', stdin=TOKEN + '\n')
            self.assertEqual(summary['restart']['restart_rc'], 0)
            self.assertEqual(summary['restart']['first_call_http'], 200)
            summary, _ = self.main('childkill', '--slug', 'repo_woow_mcp_n8n', '--tool', 'search_nodes',
                                   stdin=TOKEN + '\n')
        self.assertEqual(summary['childkill']['child_pids_before'], ['8'])
        self.assertIn(['ha', 'apps', 'restart', 'repo_woow_mcp_n8n'], commands)
        kills = [c for c in commands if probe.KILL_SCRIPT in c]
        self.assertEqual(kills, [['docker', 'exec', 'app_repo_woow_mcp_n8n', 'python', '-c', probe.KILL_SCRIPT, '8']])
        targets = {c[2] for c in commands if c[:2] in (['docker', 'exec'], ['docker', 'inspect'])}
        self.assertEqual(targets, {'app_repo_woow_mcp_n8n'})

    def test_restart_requires_slug_and_valid_args(self):
        with self.assertRaises(SystemExit), patch('sys.stderr', io.StringIO()):
            self.main('restart', stdin=TOKEN + '\n')
        with self.assertRaises(ValueError):
            self.main('bench', '--args', '{not json', stdin=TOKEN + '\n')


class ChildScriptTests(unittest.TestCase):
    def test_finds_only_children_of_the_management_launcher(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        table = {1: ('/sbin/docker-init', 'docker-init', 0),
                 7: ('/usr/local/bin/python /opt/woow/packaging/entrypoint.py n8n', 'python', 1),
                 9: ('/opt/woow/.venv/bin/python /opt/woow/packaging/management_launcher.py n8n', 'python', 7),
                 12: ('/usr/local/bin/node --require x.cjs index.js', 'node', 9),
                 13: ('/opt/child', 'odd) 7 (name', 9),  # comm may contain ') <digits> ('
                 20: ('/bin/sh -c sleep', 'sh', 1)}
        for pid, (cmd, comm, ppid) in table.items():
            (root / str(pid)).mkdir()
            (root / str(pid) / 'cmdline').write_bytes(b'\0'.join(a.encode() for a in cmd.split(' ')) + b'\0')
            (root / str(pid) / 'stat').write_text('%d (%s) S %d 1 1 0' % (pid, comm, ppid))
        (root / 'self').mkdir()
        out = subprocess.run([sys.executable, '-c', probe.CHILD_SCRIPT, str(root)], capture_output=True,
                             text=True, check=True).stdout.split()
        self.assertEqual(out, ['12', '13'])


class DriverSyntaxTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'node not installed')
    def test_driver_parses(self):
        driver = Path(__file__).with_name('ha_p9_driver.mjs')
        subprocess.run(['node', '--check', str(driver)], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
