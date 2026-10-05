"""OpenDesign /api/agents gets a longer read timeout; every other read keeps the upstream 5 s (0.1.1 HA test)."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'apps/opendesign'
DELAY = 5.6  # past the upstream 5 s read timeout, well inside the 20 s granted to /api/agents

PROGRAM = r'''
import json, runpy, time
import httpx
runpy.run_path(%r, run_name='slow_read_test')  # installs the read helper, does not start the server
import opendesign_mcp_server.od_mcp_server as od
started = time.monotonic()
agents = od.list_agents()
agents_s = time.monotonic() - started
started = time.monotonic()
try:
    od._api_get('/api/projects')
    projects = 'answered'
except httpx.TimeoutException as exc:
    projects = str(exc)
print(json.dumps({'agents': agents, 'agents_s': agents_s, 'projects': projects,
                  'projects_s': time.monotonic() - started}))
''' % str(APP / 'launch.py')


def test_only_agents_waits_past_the_upstream_timeout():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            time.sleep(DELAY)
            body = json.dumps({'agents': [{'id': 'claude', 'available': True}, {'id': 'codex', 'available': False}]}
                              if self.path == '/api/agents' else {'projects': []}).encode()
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                pass  # the client gave up (the timeout under test)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = subprocess.run([str(APP / '.venv/bin/python'), '-c', PROGRAM], capture_output=True, text=True, timeout=60,
                                env={'PATH': '/usr/bin:/bin', 'HOME': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1',
                                     'PYTHONPATH': str(APP / 'vendor') + ':' + str(ROOT / 'apps/runtime'),
                                     'OD_API_BASE': 'http://127.0.0.1:%d' % server.server_port})
    finally:
        server.shutdown()
        server.server_close()
    assert result.returncode == 0, result.stderr[-2000:]
    value = json.loads(result.stdout.strip().splitlines()[-1])
    assert value['agents'] == {'available_agents': [{'id': 'claude', 'available': True}],
                               'total_defined': 2, 'total_available': 1}
    assert DELAY <= value['agents_s'] < 20
    assert value['projects'] == 'BACKEND_TIMEOUT' and 4.5 < value['projects_s'] < DELAY
