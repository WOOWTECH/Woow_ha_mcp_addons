"""HA-host side of the P9 kit: MCP checks against one app's host-mapped MCP port.

Runs on the Home Assistant host (SSH app shell) with the python3 standard library only. Tokens arrive on
stdin and are never printed. Every MCP session the probe opens is closed with DELETE, so the shared session
cap of the app is not consumed. Modes that change state touch only the named app: `restart` restarts it
through the `ha` CLI, and `childkill` SIGKILLs the MCP child processes of its management launcher inside
its container (with --child-port, multi-profile HM-16: only the child of the profile on that port). `cross`
(multi-profile HM-16) checks that the profiles of a switched-on app never serve each other's sessions.
See docs/operations/ha-p9-kit.md.
"""
import argparse
import json
import re
import secrets
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request

PROTOCOL = '2025-06-18'
INITIALIZE = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
    'protocolVersion': PROTOCOL, 'capabilities': {}, 'clientInfo': {'name': 'woow-p9-probe', 'version': '1'}}}

# Runs inside the app container: PIDs whose parent is the management launcher (the MCP child processes).
CHILD_SCRIPT = r'''
import os, sys
root = sys.argv[1] if len(sys.argv) > 1 else "/proc"
procs = {}
for name in os.listdir(root):
    if not name.isdigit():
        continue
    try:
        with open(os.path.join(root, name, "cmdline"), "rb") as f:
            cmd = f.read().split(b"\0")
        with open(os.path.join(root, name, "stat")) as f:
            ppid = int(f.read().rsplit(")", 1)[1].split()[1])
    except (OSError, IndexError, ValueError):
        continue
    procs[int(name)] = (cmd, ppid)
launchers = {pid for pid, (cmd, _) in procs.items() if any(arg.endswith(b"management_launcher.py") for arg in cmd)}
print(" ".join(str(pid) for pid, (_, ppid) in sorted(procs.items()) if ppid in launchers))
'''
KILL_SCRIPT = 'import os, sys\nfor pid in sys.argv[1:]: os.kill(int(pid), 9)'
# Multi-profile HM-16: each MCP child of the management launcher with the port its command line names ("-": none; the
# default profile's child of Hermes and OpenDesign runs on its launcher's own default, 3000). A child that exited and
# is not reaped yet has an empty command line and is left out.
CHILD_PORT_SCRIPT = r'''
import os, sys
root = sys.argv[1] if len(sys.argv) > 1 else "/proc"
procs = {}
for name in os.listdir(root):
    if not name.isdigit():
        continue
    try:
        with open(os.path.join(root, name, "cmdline"), "rb") as f:
            cmd = f.read().split(b"\0")
        with open(os.path.join(root, name, "stat")) as f:
            ppid = int(f.read().rsplit(")", 1)[1].split()[1])
    except (OSError, IndexError, ValueError):
        continue
    procs[int(name)] = (cmd, ppid)
launchers = {pid for pid, (cmd, _) in procs.items() if any(arg.endswith(b"management_launcher.py") for arg in cmd)}
for pid, (cmd, ppid) in sorted(procs.items()):
    if ppid not in launchers or cmd == [b""]:
        continue
    port = "-"
    for index, arg in enumerate(cmd):
        if arg == b"--port" and index + 1 < len(cmd) and cmd[index + 1].isdigit():
            port = cmd[index + 1].decode()
        elif arg.startswith(b"--port=") and arg[7:].isdigit():
            port = arg[7:].decode()
    print(pid, port)
'''
DEFAULT_CHILD_PORT = 3000
CROSS_LABEL = re.compile(r'default|[0-9a-f]{8}')  # a profile's log id: never its name


def run(args, timeout=300):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


class Client:
    def __init__(self, port, token, host='127.0.0.1', timeout=30, secret=False, extra=None):
        # secret (multi-profile HM-16): the token's secret URL /private_<token>/mcp, without an Authorization header.
        # extra: more request headers (HM-16: an X-MCP-Profile that the MCP port must never read).
        self.url = ('http://%s:%d/private_%s/mcp' % (host, port, token)) if secret else 'http://%s:%d/mcp' % (host, port)
        self.token = token
        self.timeout = timeout
        self.secret = secret
        self.extra = dict(extra or {})

    def request(self, method, body=None, sid=None, timeout=None):
        headers = {'Authorization': 'Bearer ' + self.token, 'MCP-Protocol-Version': PROTOCOL, **self.extra}
        if self.secret:
            del headers['Authorization']
        if body is not None:
            headers.update({'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'})
        if sid:
            headers['Mcp-Session-Id'] = sid
        data = None if body is None else json.dumps(body).encode()
        try:
            response = urllib.request.urlopen(urllib.request.Request(self.url, data=data, headers=headers,
                                                                     method=method), timeout=timeout or self.timeout)
        except urllib.error.HTTPError as error:
            try:  # keep a short error body for the report (a JSON-RPC error or plain text)
                raw = error.read(2048).decode('utf-8', 'replace').strip()
            except OSError:
                raw = ''
            finally:
                error.close()
            try:
                body = json.loads(raw) if raw else None
            except ValueError:
                body = None
            if raw and not isinstance(body, dict):
                body = {'error': {'message': raw[:300]}}
            return error.code, body, error.headers.get('Mcp-Session-Id')  # an error must not open a session
        except (urllib.error.URLError, OSError):
            return 0, None, sid
        with response:
            raw = response.read().decode()
            sid = response.headers.get('Mcp-Session-Id') or sid
            event_stream = 'event-stream' in response.headers.get('Content-Type', '')
            status = response.status
        if not raw.strip():
            return status, None, sid
        if event_stream:
            data = [line[5:].strip() for line in raw.splitlines() if line.startswith('data:')]
            return status, json.loads(data[-1]) if data else None, sid
        return status, json.loads(raw), sid

    def open(self):
        status, message, sid = self.request('POST', INITIALIZE)
        if status == 200:
            self.request('POST', {'jsonrpc': '2.0', 'method': 'notifications/initialized'}, sid)
        return status, message, sid

    def close(self, sid):
        return self.request('DELETE', sid=sid)[0] if sid else None

    def tools(self, sid):
        status, message, _ = self.request('POST', {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}, sid)
        return status, [t['name'] for t in ((message or {}).get('result') or {}).get('tools', [])]

    def call(self, sid, name, arguments, ident=10):
        status, message, _ = self.request('POST', {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
                                                   'params': {'name': name, 'arguments': arguments}}, sid, timeout=60)
        result = (message or {}).get('result') if isinstance(message, dict) else None
        return status, (result or {}).get('isError') if isinstance(result, dict) else None

    def call_text(self, sid, name, arguments, ident=10):
        status, message, _ = self.call_reply(sid, name, arguments, ident)
        self.last_message = message  # for gateway_refused()
        result = (message or {}).get('result') if isinstance(message, dict) else None
        result = result if isinstance(result, dict) else {}
        text = ' '.join(c.get('text', '') for c in result.get('content', []) if isinstance(c, dict))
        error = message.get('error') if isinstance(message, dict) else None
        if not text and isinstance(error, dict):
            text = 'error %s: %s' % (error.get('code', ''), str(error.get('message', ''))[:200])
        return status, result.get('isError'), text

    def call_reply(self, sid, name, arguments, ident=10):
        return self.request('POST', {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
                                     'params': {'name': name, 'arguments': arguments}}, sid, timeout=60)


def gateway_refused(status, message, ident):
    """The gateway's refusal of a tools/call: 403 (no session, or a gateway before 0.1.14), or from 0.1.14 inside a
    session HTTP 200 with its own JSON-RPC error for this id (-32602, or -32603 for a backend not configured) and no
    result. A child's reply (a result, isError or another code) is never a refusal."""
    if status == 403:
        return True
    if status != 200 or not isinstance(message, dict) or 'result' in message:
        return False
    error = message.get('error')
    return (type(message.get('id')) is int and message['id'] == ident and isinstance(error, dict)
            and error.get('code') in (-32602, -32603))


def first_call(client, sid, opts):
    """One representative request: the configured tool, else tools/list."""
    if opts.tool:
        return client.call(sid, opts.tool, json.loads(opts.args))
    return client.tools(sid)[0], None


def wait_ready(client, opts, limit=240.0, sleep=time.sleep):
    start = time.monotonic()
    while time.monotonic() - start < limit:
        status, _, sid = client.open()
        if status == 200:
            ready = time.monotonic() - start
            begin = time.monotonic()
            call_status, is_error = first_call(client, sid, opts)
            elapsed = time.monotonic() - begin
            client.close(sid)
            return {'ready_s': round(ready, 2), 'first_call_http': call_status, 'first_call_isError': is_error,
                    'first_call_s': round(elapsed, 3)}
        sleep(0.5)
    return {'ready_s': None}


def container_name(slug):
    names = set(run(['docker', 'ps', '-a', '--format', '{{.Names}}']).stdout.split())
    for name in ('app_' + slug, 'addon_' + slug):
        if name in names:
            return name
    raise SystemExit('no container for app %s' % slug)


def container_state(container):
    out = run(['docker', 'inspect', container, '--format', '{{.RestartCount}} {{.State.StartedAt}}']).stdout.split()
    return {'restart_count': int(out[0]), 'started_at': out[1]} if len(out) == 2 else {}


def child_pids(container):
    return run(['docker', 'exec', container, 'python', '-c', CHILD_SCRIPT]).stdout.split()


def child_ports(container):
    """Multi-profile HM-16: [(pid, port or None)] of the MCP children (CHILD_PORT_SCRIPT)."""
    pairs = []
    for line in run(['docker', 'exec', container, 'python', '-c', CHILD_PORT_SCRIPT]).stdout.splitlines():
        pid, _, port = line.partition(' ')
        pairs.append((pid, None if port == '-' else int(port)))
    return pairs


def serving(pairs, port):
    """The PIDs of the children serving *port*: the one naming it, or for 3000 the one naming no port."""
    return [pid for pid, named in pairs if named == port or (named is None and port == DEFAULT_CHILD_PORT)]


def percentile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def timing(values):
    return {'n': len(values), 'p50_ms': round(percentile(values, .5), 1), 'p95_ms': round(percentile(values, .95), 1),
            'max_ms': round(max(values), 1), 'mean_ms': round(statistics.mean(values), 1)}


def mode_check(opts, stdin, out):
    rows = []
    for line in stdin:
        label, _, token = line.rstrip('\n').partition('\t')
        client = Client(opts.port, token)
        status, _, sid = client.open()
        tools = client.tools(sid) if status == 200 else (None, [])
        closed = client.close(sid) if status == 200 else None
        rows.append({'label': label, 'initialize': status, 'tools_list': tools[0], 'tools': len(tools[1]),
                     'delete': closed})
        out.write('%-26s initialize=%s tools/list=%s tools=%s delete=%s\n' % (label, status, tools[0],
                                                                             len(tools[1]), closed))
    return {'check': rows}


def mode_restart(opts, client, out):
    container = container_name(opts.slug)
    before = container_state(container)
    begin = time.monotonic()
    rc = run(['ha', 'apps', 'restart', opts.slug]).returncode
    cli = round(time.monotonic() - begin, 2)
    ready = wait_ready(client, opts)
    result = {'restart_rc': rc, 'cli_s': cli, **ready, 'before': before, 'after': container_state(container)}
    out.write('ha apps restart rc=%s cli=%ss; MCP ready %ss later; first call http=%s isError=%s %ss\n' % (
        rc, cli, ready.get('ready_s'), ready.get('first_call_http'), ready.get('first_call_isError'),
        ready.get('first_call_s')))
    out.write('container before=%s after=%s\n' % (before, result['after']))
    return {'restart': result}


def mode_childkill(opts, client, out):
    container = container_name(opts.slug)
    if opts.child_port is not None:
        return profile_childkill(opts, client, out, container)
    pids, before = child_pids(container), container_state(container)
    if not pids:
        raise SystemExit('no MCP child found under the management launcher')
    status, _, old = client.open()
    kill = run(['docker', 'exec', container, 'python', '-c', KILL_SCRIPT] + pids)
    old_status = client.tools(old)[0]
    ready = wait_ready(client, opts)
    result = {'initialize_before': status, 'child_pids_before': pids, 'kill_rc': kill.returncode,
              'old_session_after_kill': old_status, **ready, 'child_pids_after': child_pids(container),
              'before': before, 'after': container_state(container)}
    out.write('child pids %s killed rc=%s; old session tools/list=%s; recovered in %ss (first call http=%s); '
              'child pids now %s\n' % (pids, kill.returncode, old_status, ready.get('ready_s'),
                                       ready.get('first_call_http'), result['child_pids_after']))
    out.write('container before=%s after=%s\n' % (before, result['after']))
    return {'childkill': result}


def profile_childkill(opts, client, out, container):
    """Multi-profile HM-16 (FM-107; T-13): SIGKILL only the child of the profile on --child-port (its token is the
    client's); it must start again, and every other profile's child keep its PID. A port no single child names kills
    nothing."""
    pairs, before = child_ports(container), container_state(container)
    targets = serving(pairs, opts.child_port)
    if len(targets) != 1:
        raise SystemExit('cannot tell which MCP child serves port %d' % opts.child_port)
    target = targets[0]
    others = sorted((pid for pid, _ in pairs if pid != target), key=int)
    status, _, old = client.open()
    kill = run(['docker', 'exec', container, 'python', '-c', KILL_SCRIPT, target])
    old_status = client.tools(old)[0]
    ready = wait_ready(client, opts)
    after = child_ports(container)
    now = serving(after, opts.child_port)
    others_after = sorted((pid for pid, _ in after if pid not in now), key=int)
    unchanged = others_after == others
    back = len(now) == 1 and now[0] != target and ready.get('ready_s') is not None
    result = {'child_port': opts.child_port, 'initialize_before': status, 'child_pid_before': target,
              'kill_rc': kill.returncode, 'old_session_after_kill': old_status, **ready,
              'child_pid_after': now[0] if len(now) == 1 else None, 'others_before': others,
              'others_after': others_after, 'others_unchanged': unchanged, 'pass': unchanged and back,
              'before': before, 'after': container_state(container)}
    out.write('child on port %d: pid %s killed rc=%s; old session tools/list=%s; recovered in %ss (first call http=%s); '
              'child pid now %s; other children %s -> %s (%s)\n' % (
                  opts.child_port, target, kill.returncode, old_status, ready.get('ready_s'),
                  ready.get('first_call_http'), result['child_pid_after'], others, others_after,
                  'unchanged' if unchanged else 'CHANGED'))
    out.write('container before=%s after=%s\n' % (before, result['after']))
    return {'childkill': result}


def cross_rows(stdin):
    """The cross mode's lines: label TAB live|gone TAB token, one per profile (label: its log id)."""
    rows = []
    for line in stdin:
        parts = line.rstrip('\n').split('\t')
        if (len(parts) != 3 or not CROSS_LABEL.fullmatch(parts[0]) or parts[1] not in ('live', 'gone')
                or not parts[2]):
            raise SystemExit('cross: each line is: profile log id TAB live|gone TAB token')
        rows.append(tuple(parts))
    if not rows or len({row[0] for row in rows}) != len(rows):
        raise SystemExit('cross: one line for each profile')
    return rows


def mode_cross(opts, stdin, out):
    """Multi-profile HM-16 (FM-107; T-05): every live token opens a session on both connection methods (Bearer, and
    its secret URL) and lists the tools; each of those sessions is unknown (404) with every other live token on both
    methods; a gone token (a deleted or revoked profile's) and an unknown one made here are refused (Bearer 401,
    secret URL 404). Every session is opened with X-MCP-Profile: default, which the MCP port never reads (contract
    2.2): had it chosen the default profile, that session would be the default token's. Every session opened is
    ended. Tokens are never printed; a profile is named by its log id."""
    rows = cross_rows(stdin)
    checks, sessions = [], []

    def check(name, ok, detail):
        checks.append({'check': name, 'pass': bool(ok), 'detail': detail})
        out.write('%-4s %s: %s\n' % ('PASS' if ok else 'FAIL', name, detail))
    try:
        for label, kind, token in rows:
            if kind != 'live':
                continue
            for method in ('bearer', 'secret'):
                client = Client(opts.port, token, secret=method == 'secret', extra={'X-MCP-Profile': 'default'})
                status, _, sid = client.open()
                if sid:
                    sessions.append((label, method, client, sid))
                listed = client.tools(sid)[0] if status == 200 and sid else None
                check('%s %s' % (label, method), status == 200 and sid and listed == 200,
                      'initialize=%s tools/list=%s' % (status, listed))
        for label, method, _, sid in list(sessions):
            for other, kind, token in rows:
                if kind != 'live' or other == label:
                    continue
                for other_method in ('bearer', 'secret'):
                    status = Client(opts.port, token, secret=other_method == 'secret').tools(sid)[0]
                    check('%s session with %s %s' % (label, other, other_method), status == 404, 'tools/list=%s' % status)
        refused = [('unknown', secrets.token_urlsafe(32))] + [(label, token) for label, kind, token in rows if kind == 'gone']
        for label, token in refused:
            answers = []
            for method in ('bearer', 'secret'):
                client = Client(opts.port, token, secret=method == 'secret')
                status, _, sid = client.open()
                if sid:
                    sessions.append((label, method, client, sid))
                answers.append(status)
            check('%s refused' % label, answers == [401, 404], 'bearer=%s secret=%s' % tuple(answers))
    finally:
        for _, _, client, sid in sessions:
            client.close(sid)
    passed = sum(item['pass'] for item in checks)
    out.write('cross: %d/%d pass\n' % (passed, len(checks)))
    return {'cross': {'pass': passed == len(checks), 'checks': checks}}


def mode_bench(opts, client, out):
    opens = []
    for _ in range(opts.sessions):
        begin = time.monotonic()
        status, _, sid = client.open()
        opens.append((time.monotonic() - begin) * 1000)
        client.close(sid)
        if status != 200:
            raise SystemExit('initialize returned %s' % status)
    status, _, sid = client.open()
    lists, calls = [], []
    try:
        for _ in range(opts.requests):
            begin = time.monotonic()
            if client.tools(sid)[0] != 200:
                raise SystemExit('tools/list failed')
            lists.append((time.monotonic() - begin) * 1000)
        if opts.tool:
            for i in range(opts.requests):
                begin = time.monotonic()
                call_status, is_error = client.call(sid, opts.tool, json.loads(opts.args), ident=100 + i)
                if call_status != 200 or is_error:
                    raise SystemExit('tools/call %s failed: http %s isError %s' % (opts.tool, call_status, is_error))
                calls.append((time.monotonic() - begin) * 1000)
    finally:
        client.close(sid)
    result = {'initialize': timing(opens), 'tools_list': timing(lists)}
    if calls:
        result['tools_call'] = dict(timing(calls), tool=opts.tool)
    for name, value in result.items():
        out.write('%-12s %s\n' % (name, json.dumps(value)))
    return {'bench': result}


def mode_cycle(opts, client, out):
    pairs = []
    for _ in range(opts.cycles):
        status, _, sid = client.open()
        pairs.append('%s/%s' % (status, client.close(sid) if status == 200 else None))
    out.write('%d x (initialize, DELETE): %s\n' % (opts.cycles, ' '.join(pairs)))
    return {'cycle': pairs}


def backend_failed(text):
    """Tool output that reports a backend failure in-band (n8n-mcp style {"success": false, ...})."""
    try:
        value = json.loads(text)
    except ValueError:
        return False
    return isinstance(value, dict) and value.get('success') is False


def describe(message):
    """serverInfo name or the JSON-RPC error of an initialize reply, for the report."""
    if not isinstance(message, dict):
        return 'no JSON body'
    if isinstance(message.get('error'), dict):
        return 'error %s: %s' % (message['error'].get('code', ''), str(message['error'].get('message', ''))[:200])
    info = (message.get('result') or {}).get('serverInfo') if isinstance(message.get('result'), dict) else None
    return 'serverInfo=%s' % (info.get('name') if isinstance(info, dict) else None)


def mode_plan(opts, client, out, plan):
    """reads must succeed (HTTP 200, not isError, no in-band failure); denials must be refused by the gateway (HTTP 403,
    or from 0.1.14 inside a session HTTP 200 with the gateway's JSON-RPC -32602/-32603 error: gateway_refused()).

    With --expect-backend-down, every read must still be answered (HTTP 200: local tools keep working,
    backend tools report the failure) and at least one read must fail in a structured way (isError or an
    in-band failure), proving the server answers instead of hanging or crashing during an outage. A child
    that cannot open a session without its backend makes the gateway refuse initialize with HTTP 503 and
    BACKEND_UNAVAILABLE (0.1.2); that refusal is the structured failure, and denials (sent without a session) must
    still be 403.
    """
    status, message, sid = client.open()
    refused = (opts.expect_backend_down and opts.allow_initialize_refusal and status == 503
               and describe(message) == 'error -32000: BACKEND_UNAVAILABLE')
    if status != 200 and not refused:
        raise SystemExit('initialize returned %s' % status)
    out.write('initialize http=%s %s\n' % (status, describe(message)))
    rows = []
    try:
        if refused:
            listed, kinds = set(), ('denials',)  # no session for reads; the gateway refuses denials first
        else:
            list_status, names = client.tools(sid)
            listed, kinds = set(names), ('reads', 'denials')
            out.write('tools/list http=%s tools=%d\n' % (list_status, len(listed)))
        for kind in kinds:
            for i, (name, arguments) in enumerate(plan.get(kind, [])):
                ident = 300 + len(rows)
                call_status, is_error, text = client.call_text(sid, name, arguments, ident=ident)
                structured = bool(is_error or backend_failed(text))
                answered = isinstance(client.last_message, dict) and isinstance(client.last_message.get('result'), dict)
                if kind == 'reads' and opts.expect_backend_down:
                    ok = call_status == 200 and not gateway_refused(call_status, client.last_message, ident)
                elif kind == 'reads':  # 0.1.14: a gateway refusal is HTTP 200 too, without a result
                    ok = call_status == 200 and answered and not is_error and not backend_failed(text)
                else:
                    ok = gateway_refused(call_status, client.last_message, ident)
                rows.append({'kind': kind, 'tool': name, 'listed': name in listed, 'http': call_status,
                             'isError': is_error, 'structured_failure': structured, 'pass': ok})
                out.write('%-7s %-5s %-34s listed=%-5s http=%s isError=%s | %s\n' % (
                    kind[:-1], 'PASS' if ok else 'FAIL', name, name in listed, call_status, is_error,
                    text.replace('\n', ' ')[:opts.width]))
    finally:
        client.close(sid)
    if refused:
        rows.append({'kind': 'outage', 'tool': '(initialize)', 'listed': None, 'http': 503, 'isError': None,
                     'structured_failure': True, 'pass': sid is None})
        out.write('outage: initialize refused with BACKEND_UNAVAILABLE, session id %s\n'
                  % ('absent' if sid is None else 'PRESENT'))
    elif opts.expect_backend_down:
        failed_reads = sum(r['structured_failure'] for r in rows if r['kind'] == 'reads')
        rows.append({'kind': 'outage', 'tool': '(any backend read)', 'listed': None, 'http': None, 'isError': None,
                     'structured_failure': failed_reads, 'pass': failed_reads > 0})
        out.write('outage: %d read(s) failed in a structured way\n' % failed_reads)
    passed = sum(r['pass'] for r in rows)
    out.write('plan: %d/%d pass\n' % (passed, len(rows)))
    return {'plan': {'passed': passed, 'total': len(rows), 'rows': rows}}


def main(argv=None, stdin=sys.stdin, out=sys.stdout):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('check', 'restart', 'childkill', 'bench', 'cycle', 'plan', 'cross'))
    parser.add_argument('--port', type=int, required=True, help='host port mapped to the app MCP port 8081')
    parser.add_argument('--slug', help='installed app slug (restart/childkill)')
    parser.add_argument('--tool', help='read-only tool for first-call and bench timing')
    parser.add_argument('--args', default='{}', help='JSON arguments for --tool')
    parser.add_argument('--sessions', type=int, default=5)
    parser.add_argument('--requests', type=int, default=50)
    parser.add_argument('--cycles', type=int, default=25)
    parser.add_argument('--width', type=int, default=120, help='characters of tool output shown per plan row')
    parser.add_argument('--expect-backend-down', action='store_true', help='plan: reads must fail in a structured way')
    parser.add_argument('--child-port', type=int,
                        help='childkill (multi-profile): only the MCP child of the profile on this child port')
    parser.add_argument('--allow-initialize-refusal', action='store_true',
                        help='plan with --expect-backend-down: a 503 BACKEND_UNAVAILABLE initialize without a session id '
                             'is the structured failure (only for a child that needs its backend per session)')
    opts = parser.parse_args(argv)
    json.loads(opts.args)
    if opts.mode in ('restart', 'childkill') and not opts.slug:
        parser.error('--slug is required for %s' % opts.mode)
    if opts.mode == 'check':
        summary = mode_check(opts, stdin, out)
    elif opts.mode == 'cross':
        summary = mode_cross(opts, stdin, out)
    elif opts.mode == 'plan':
        client = Client(opts.port, stdin.readline().strip())
        summary = mode_plan(opts, client, out, json.loads(stdin.read()))
    else:
        client = Client(opts.port, stdin.readline().strip())
        summary = {'restart': mode_restart, 'childkill': mode_childkill, 'bench': mode_bench,
                   'cycle': mode_cycle}[opts.mode](opts, client, out)
    out.write('SUMMARY ' + json.dumps(summary, sort_keys=True) + '\n')
    if opts.mode == 'plan' and summary['plan']['passed'] != summary['plan']['total']:
        raise SystemExit(1)
    if opts.mode == 'cross' and not summary['cross']['pass']:
        raise SystemExit(1)
    if opts.mode == 'childkill' and summary['childkill'].get('pass') is False:
        raise SystemExit(1)
    return summary


if __name__ == '__main__':
    main()
