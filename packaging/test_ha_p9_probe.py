"""Offline tests for the P9 kit probe against a scripted MCP server. No HA, Docker or network."""
import io
import json
import os
from pathlib import Path
import re
import secrets
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
# The gateway refuses these: HTTP 403 without a session, from 0.1.14 inside one HTTP 200 with JSON-RPC -32602.
DENIED = {'n8n_delete_workflow', 'definitely_not_a_tool'}
BACKEND_TOOLS = {'n8n_list_workflows'}


class FakeMCP(ThreadingHTTPServer):
    """Bearer auth, initialize/notifications/tools, DELETE, a session cap (429) like n8n-mcp."""

    def __init__(self, cap=20):
        super().__init__(('127.0.0.1', 0), Handler)
        self.cap, self.sessions, self.lock = cap, set(), threading.Lock()
        self.outage = False
        self.refuse_initialize = False  # 0.1.2 gateway: a child that cannot open a session without its backend
        self.refusal_session = None
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
        if method == 'initialize' and self.server.refuse_initialize:
            headers = {'Mcp-Session-Id': self.server.refusal_session} if self.server.refusal_session else None
            return self.reply(503, {'jsonrpc': '2.0', 'id': body['id'],
                                    'error': {'code': -32000, 'message': 'BACKEND_UNAVAILABLE'}}, headers)
        if method == 'initialize':
            with self.server.lock:
                if len(self.server.sessions) >= self.server.cap:
                    return self.reply(429, {'error': 'Session limit reached'})
                sid = uuid.uuid4().hex
                self.server.sessions.add(sid)
            return self.reply(200, {'jsonrpc': '2.0', 'id': body['id'], 'result': {'serverInfo': {'name': 'fake'}}},
                              {'Mcp-Session-Id': sid})
        if method == 'tools/call' and body['params']['name'] in DENIED and sid not in self.server.sessions:
            return self.reply(403, {'jsonrpc': '2.0', 'id': body['id'],
                                    'error': {'code': -32001, 'message': 'request denied'}})
        if sid not in self.server.sessions:
            return self.reply(404)
        if method == 'notifications/initialized':
            return self.reply(202)
        if method == 'tools/list':
            return self.reply(200, {'jsonrpc': '2.0', 'id': body['id'], 'result': {'tools': TOOLS}}, sse=True)
        if method == 'tools/call':
            name = body['params']['name']
            if name in DENIED:  # 0.1.14: the gateway's own JSON-RPC answer inside a session
                return self.reply(200, {'jsonrpc': '2.0', 'id': body['id'],
                                        'error': {'code': -32602, 'message': 'Unknown tool', 'data': {'tool': name}}})
            if name == 'child_error_tool':  # a child's JSON-RPC error is not a gateway refusal
                return self.reply(200, {'jsonrpc': '2.0', 'id': body['id'],
                                        'error': {'code': -32000, 'message': 'child failed'}})
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
        self.assertIn('initialize http=200 serverInfo=fake\ntools/list http=200 tools=3\n', text)
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

    def test_plan_outage_accepts_a_refused_initialize_only_when_allowed(self):
        self.server.refuse_initialize = True
        plan = {'reads': [['n8n_list_workflows', {}]], 'denials': [['n8n_delete_workflow', {}]]}
        stdin = TOKEN + '\n' + json.dumps(plan)
        summary, text = self.main('plan', '--expect-backend-down', '--allow-initialize-refusal', stdin=stdin)
        self.assertEqual([(r['kind'], r['pass']) for r in summary['plan']['rows']], [('denials', True), ('outage', True)])
        self.assertIn('initialize http=503 error -32000: BACKEND_UNAVAILABLE', text)
        self.assertIn('session id absent', text)
        for argv in (('plan', '--expect-backend-down'), ('plan',)):  # not opted in, or not an outage run
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                self.main(*argv, stdin=stdin)
        self.server.refusal_session = 'leaked'  # a refusal must not hand out a session id
        with self.assertRaises(SystemExit):
            self.main('plan', '--expect-backend-down', '--allow-initialize-refusal', stdin=stdin)
        self.assertEqual(self.server.sessions, set())

    def test_plan_reports_short_error_bodies(self):
        out = io.StringIO()
        plan = {'denials': [['n8n_delete_workflow', {}], ['not_ready_tool', {}]]}
        with self.assertRaises(SystemExit):  # the 503 is not a refusal
            probe.main(['--port', str(self.server.port), 'plan'], io.StringIO(TOKEN + '\n' + json.dumps(plan)), out)
        self.assertIn('http=200 isError=None | error -32602: Unknown tool', out.getvalue())
        self.assertIn('http=503 isError=None | error : child transport not ready', out.getvalue())

    def test_plan_fails_when_a_read_is_denied_or_a_denial_succeeds(self):
        for plan in ({'reads': [['n8n_delete_workflow', {}]]}, {'denials': [['search_nodes', {'query': 'x'}]]},
                     {'denials': [['child_error_tool', {}]]}, {'denials': [['not_a_listed_tool', {}]]}):
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


class ProfilesMCP(ThreadingHTTPServer):
    """8081 of a switched-on add-on (multi-profile HM-16): a token chooses its profile on /mcp (Bearer) and on its secret
    URL /private_<token>/mcp; a session belongs to the token that opened it; faults break one rule each."""

    def __init__(self, tokens, faults=()):
        super().__init__(('127.0.0.1', 0), ProfilesHandler)
        self.tokens, self.faults, self.sessions, self.lock = set(tokens), set(faults), {}, threading.Lock()
        self.default = tokens[0]  # the default profile's token (the test lists it first)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def port(self):
        return self.server_address[1]


class ProfilesHandler(Handler):
    def token(self):
        if self.path == '/mcp':
            value = self.headers.get('Authorization', '')
            token = value[7:] if value.startswith('Bearer ') else None
        else:
            match = re.fullmatch(r'/private_([A-Za-z0-9_-]+)/mcp', self.path)
            token = match.group(1) if match else None
        if token is not None and 'serves any token' in self.server.faults:
            return token
        if token in self.server.tokens and 'switches by header' in self.server.faults \
                and self.headers.get('X-MCP-Profile') == 'default':
            return self.server.default  # as if the MCP port chose the profile by the management header
        return token if token in self.server.tokens else None

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        token = self.token()
        if token is None:
            return self.reply(401 if self.path == '/mcp' else 404)
        method, sid = body.get('method'), self.headers.get('Mcp-Session-Id')
        if method == 'initialize':
            sid = uuid.uuid4().hex
            with self.server.lock:
                self.server.sessions[sid] = token
            return self.reply(200, {'jsonrpc': '2.0', 'id': body['id'], 'result': {'serverInfo': {'name': 'fake'}}},
                              {'Mcp-Session-Id': sid})
        owner = self.server.sessions.get(sid)
        if owner is None or (owner != token and 'crosses sessions' not in self.server.faults):
            return self.reply(404)
        if method == 'notifications/initialized':
            return self.reply(202)
        if method == 'tools/list':
            return self.reply(200, {'jsonrpc': '2.0', 'id': body['id'], 'result': {'tools': TOOLS}}, sse=True)
        self.reply(400)

    def do_DELETE(self):
        token = self.token()
        if token is None:
            return self.reply(401 if self.path == '/mcp' else 404)
        sid = self.headers.get('Mcp-Session-Id')
        with self.server.lock:
            if self.server.sessions.get(sid) != token:
                return self.reply(404)
            del self.server.sessions[sid]
        self.reply(204)


class CrossMatrixTests(unittest.TestCase):
    """cross mode (multi-profile HM-16; FM-107, T-05): every live token on both connection methods, sessions never cross
    profiles, gone and unknown tokens refused; every session ended; tokens never printed; exit 1 on a failure."""

    def setUp(self):
        self.tokens = [secrets.token_urlsafe(32) for _ in range(3)]
        self.lines = ''.join(f'{label}\tlive\t{token}\n' for label, token in zip(('default', 'b' * 8, 'c' * 8),
                                                                                  self.tokens))

    def cross(self, server, stdin):
        out = io.StringIO()
        try:
            return probe.main(['--port', str(server.port), 'cross'], io.StringIO(stdin), out), out.getvalue()
        finally:
            self.assertFalse(any(token in out.getvalue() for token in self.tokens))

    def serve(self, tokens, faults=()):
        server = ProfilesMCP(tokens, faults)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def test_isolated_profiles_pass_and_every_session_is_ended(self):
        server = self.serve(self.tokens)
        summary, text = self.cross(server, self.lines)
        checks = summary['cross']['checks']
        self.assertTrue(summary['cross']['pass'])
        # 3 profiles x 2 methods open; each of the 6 sessions with the 2 other profiles' 2 methods; the unknown token
        self.assertEqual(len(checks), 6 + 6 * 4 + 1)
        self.assertEqual(server.sessions, {})
        self.assertIn('default session with bbbbbbbb secret: tools/list=404', text)
        self.assertIn('unknown refused: bearer=401 secret=404', text)

    def test_a_gone_token_is_refused_like_an_unknown_one(self):
        gone = secrets.token_urlsafe(32)
        self.tokens.append(gone)
        stdin = self.lines + f'dddddddd\tgone\t{gone}\n'
        summary, text = self.cross(self.serve(self.tokens[:3]), stdin)
        self.assertTrue(summary['cross']['pass'])
        self.assertIn('dddddddd refused: bearer=401 secret=404', text)
        with self.assertRaises(SystemExit) as failed:  # the add-on still serves it
            self.cross(self.serve(self.tokens), stdin)
        self.assertEqual(failed.exception.code, 1)

    def test_a_crossing_session_a_header_chosen_profile_or_a_served_unknown_token_fails(self):
        for fault in ('crosses sessions', 'switches by header', 'serves any token'):
            with self.subTest(fault=fault):
                server = self.serve(self.tokens, {fault})
                with self.assertRaises(SystemExit) as failed:
                    self.cross(server, self.lines)
                self.assertEqual(failed.exception.code, 1)
                self.assertEqual(server.sessions, {})

    def test_only_well_formed_lines_naming_each_profile_once(self):
        server = self.serve(self.tokens)
        for stdin in ('default\tlive\n', f'Default\tlive\t{self.tokens[0]}\n', f'default\tdead\t{self.tokens[0]}\n',
                      f'default\tlive\t{self.tokens[0]}\ndefault\tlive\t{self.tokens[1]}\n', ''):
            with self.subTest(stdin=stdin.replace(self.tokens[0], '<token>').replace(self.tokens[1], '<token>')):
                with self.assertRaises(SystemExit) as failed:
                    self.cross(server, stdin)
                self.assertTrue(str(failed.exception.code).startswith('cross: '))
        self.assertEqual(server.sessions, {})


class ProfileChildKillTests(unittest.TestCase):
    """childkill --child-port (multi-profile HM-16; FM-107, T-13): only the child of the named profile's port is
    killed; it must come back, and every other child keep its PID."""

    def setUp(self):
        self.server = FakeMCP(cap=3)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.children = '8 3000\n9 18000\n10 18001\n'
        self.commands = []

    def fake_run(self, after):
        def run(args, timeout=300):
            self.commands.append(args)
            out = ''
            if args[:2] == ['docker', 'ps']:
                out = 'app_repo_woow_mcp_odoo\n'
            elif args[:2] == ['docker', 'inspect']:
                out = '0 2026-11-16T08:06:11Z'
            elif args[:2] == ['docker', 'exec'] and probe.CHILD_PORT_SCRIPT in args:
                out = self.children
            elif args[:2] == ['docker', 'exec'] and probe.KILL_SCRIPT in args:
                self.children = after
            return subprocess.CompletedProcess(args, 0, out, '')
        return run

    def childkill(self, port, after):
        out = io.StringIO()
        with patch.object(probe, 'run', self.fake_run(after)):
            try:
                return probe.main(['--port', str(self.server.port), 'childkill', '--slug', 'repo_woow_mcp_odoo',
                                   '--child-port', str(port)], io.StringIO(TOKEN + '\n'), out)
            finally:
                self.assertNotIn(TOKEN, out.getvalue())

    def test_only_the_profile_s_child_is_killed_and_the_others_keep_their_pids(self):
        summary = self.childkill(18000, '8 3000\n19 18000\n10 18001\n')['childkill']
        kills = [command for command in self.commands if probe.KILL_SCRIPT in command]
        self.assertEqual(kills, [['docker', 'exec', 'app_repo_woow_mcp_odoo', 'python', '-c', probe.KILL_SCRIPT, '9']])
        self.assertEqual((summary['child_pid_before'], summary['child_pid_after']), ('9', '19'))
        self.assertEqual((summary['others_before'], summary['others_after']), (['8', '10'], ['8', '10']))
        self.assertTrue(summary['others_unchanged'] and summary['pass'])

    def test_the_default_child_is_the_one_on_3000_or_naming_no_port(self):
        self.children = '8 -\n9 18000\n'
        summary = self.childkill(3000, '18 -\n9 18000\n')['childkill']
        self.assertEqual((summary['child_pid_before'], summary['others_before']), ('8', ['9']))
        self.assertTrue(summary['pass'])

    def test_another_child_restarted_or_the_child_not_back_fails(self):
        for after in ('8 3000\n19 18000\n20 18001\n', '8 3000\n10 18001\n'):
            with self.subTest(after=after), self.assertRaises(SystemExit) as failed:
                self.childkill(18000, after)
            self.assertEqual(failed.exception.code, 1)

    def test_a_port_no_single_child_names_kills_nothing(self):
        for children, port in (('8 -\n9 -\n', 3000), ('8 3000\n', 18000), ('8 18000\n9 18000\n', 18000)):
            with self.subTest(children=children, port=port):
                self.children, self.commands = children, []
                with self.assertRaises(SystemExit) as failed:
                    self.childkill(port, children)
                self.assertEqual(failed.exception.code, f'cannot tell which MCP child serves port {port}')
                self.assertFalse(any(probe.KILL_SCRIPT in command for command in self.commands))


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

    def test_names_each_child_s_port_and_leaves_out_an_unreaped_one(self):
        """multi-profile HM-16: childkill --child-port tells the children apart by the --port of their command line."""
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        table = {7: ('/usr/local/bin/python /opt/woow/packaging/entrypoint.py odoo', 'python', 1),
                 9: ('/opt/woow/.venv/bin/python /opt/woow/packaging/management_launcher.py odoo', 'python', 7),
                 12: ('/opt/woow/apps/odoo/.venv/bin/python start_switches.py --port 3000 --path /mcp', 'python', 9),
                 13: ('/opt/woow/apps/hermes/.venv/bin/python launch.py', 'python', 9),
                 14: ('/opt/woow/apps/odoo/.venv/bin/python start_switches.py --port=18001', 'odd) 7 (name', 9),
                 15: ('', 'python', 9),  # exited, not reaped: an empty command line
                 20: ('/bin/sh -c --port 18005', 'sh', 1)}
        for pid, (cmd, comm, ppid) in table.items():
            (root / str(pid)).mkdir()
            (root / str(pid) / 'cmdline').write_bytes(b''.join(a.encode() + b'\0' for a in cmd.split(' ')) if cmd else b'')
            (root / str(pid) / 'stat').write_text('%d (%s) S %d 1 1 0' % (pid, comm, ppid))
        out = subprocess.run([sys.executable, '-c', probe.CHILD_PORT_SCRIPT, str(root)], capture_output=True,
                             text=True, check=True).stdout
        self.assertEqual(out, '12 3000\n13 -\n14 18001\n')


class DriverSyntaxTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'node not installed')
    def test_driver_parses(self):
        driver = Path(__file__).with_name('ha_p9_driver.mjs')
        subprocess.run(['node', '--check', str(driver)], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
