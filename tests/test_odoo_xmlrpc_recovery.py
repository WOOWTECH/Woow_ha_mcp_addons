"""The pinned Odoo SDK's retry policy against an owned, loopback XML-RPC peer."""
import importlib.util
import json
import socket
import subprocess
import threading
import xmlrpc.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('odoo_recovery_policy', ROOT / 'apps/runtime/backend_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

CLIENT = r'''
import json
import sys
import xmlrpc.client

from backend_policy import BackendFailure, XMLTransport, backend_error_text, public_backend_error
from odoo_mcp.odoo_client import OdooClient

base, method = sys.argv[1:]
client = OdooClient.__new__(OdooClient)
client.lang = None
client.transport = "xmlrpc"
client.db, client.uid, client.password = "test", 7, "DUMMY"
client._models = xmlrpc.client.ServerProxy(
    base + "/xmlrpc/2/object", transport=XMLTransport(base, timeout=2), allow_none=True
)
try:
    value = client._execute("res.partner", method, [])
except Exception as exc:
    wrapped = BackendFailure(exc)
    print(json.dumps({"error_type": type(exc).__name__, "error_text": str(exc),
                      "public_text": backend_error_text(exc), "public_code": public_backend_error(exc),
                      "wrapped_text": str(wrapped), "wrapped_code": wrapped.code}))
else:
    print(json.dumps({"value": value}))
'''


@pytest.mark.parametrize(('method', 'drops', 'attempts', 'recovers'), [
    ('search_read', 1, 2, True),
    ('read', 1, 2, True),
    ('search_read', 99, 2, False),
    ('create', 1, 1, False),
])
def test_only_upstream_read_only_methods_retry_connection_drop(method, drops, attempts, recovers):
    seen = []

    class FakeOdoo(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            assert self.path == '/xmlrpc/2/object'
            body = self.rfile.read(int(self.headers['Content-Length']))
            params, rpc_method = xmlrpc.client.loads(body)
            assert rpc_method == 'execute_kw'
            assert params[:5] == ('test', 7, 'DUMMY', 'res.partner', method)
            seen.append(params[4])
            if len(seen) <= drops:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            payload = xmlrpc.client.dumps((([{'id': 503}] if method != 'create' else 503),),
                                          methodresponse=True).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/xml')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(('127.0.0.1', 0), FakeOdoo)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'apps/runtime'),
               'PYTHONDONTWRITEBYTECODE': '1', 'ODOO_MCP_RETRY_ATTEMPTS': '1',
               'ODOO_MCP_RETRY_BACKOFF': '0'}
        finished = subprocess.run(
            [str(ROOT / 'apps/odoo/.venv/bin/python'), '-B', '-c', CLIENT,
             f'http://127.0.0.1:{server.server_port}', method],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=15, check=False,
        )
        assert finished.returncode == 0, finished.stderr
        result = json.loads(finished.stdout)
        assert len(seen) == attempts, (seen, result)
        if recovers:
            assert result == {'value': [{'id': 503}]}
        else:
            assert result['error_type'] == 'ConnectionError'
            assert result['error_text'].startswith('BACKEND_UNAVAILABLE: ')
            assert result['public_text'] == result['error_text']
            assert result['public_code'] == 'BACKEND_UNAVAILABLE'
            assert result['wrapped_text'] == result['error_text']
            assert result['wrapped_code'] == 'BACKEND_UNAVAILABLE'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_timeout_keeps_safe_public_category_and_retryable_type(monkeypatch):
    transport = policy.XMLTransport('http://127.0.0.1:12001')
    calls = []

    def timeout(*_args):
        calls.append('one exchange')
        raise TimeoutError('synthetic timeout')

    monkeypatch.setattr(transport, 'single_request', timeout)
    with pytest.raises(TimeoutError, match='^BACKEND_TIMEOUT: synthetic timeout$') as raised:
        transport.request('127.0.0.1:12001', '/xmlrpc/2/object', b'<methodCall/>')
    assert calls == ['one exchange']
    assert policy.public_backend_error(raised.value) == 'BACKEND_TIMEOUT'
    assert policy.backend_error_text(raised.value) == 'BACKEND_TIMEOUT: synthetic timeout'


@pytest.mark.parametrize(('method', 'attempts'), [('read', 2), ('create', 1)])
def test_upstream_timeout_retries_only_reads(method, attempts):
    script = r'''
import json
import sys
import xmlrpc.client
from backend_policy import XMLTransport
from odoo_mcp.odoo_client import OdooClient

method = sys.argv[1]
transport = XMLTransport('http://127.0.0.1:12001')
calls = []
def timed_out(*_args):
    calls.append(1)
    raise TimeoutError('synthetic timeout')
transport.single_request = timed_out
client = OdooClient.__new__(OdooClient)
client.lang = None
client.transport = 'xmlrpc'
client.db, client.uid, client.password = 'test', 7, 'DUMMY'
client._models = xmlrpc.client.ServerProxy('http://127.0.0.1:12001/xmlrpc/2/object',
                                            transport=transport, allow_none=True)
try:
    client._execute('res.partner', method, [])
except TimeoutError as exc:
    print(json.dumps({'attempts': len(calls), 'error': str(exc)}))
else:
    raise AssertionError('timeout unexpectedly succeeded')
'''
    finished = subprocess.run(
        [str(ROOT / 'apps/odoo/.venv/bin/python'), '-B', '-c', script, method],
        cwd=ROOT, env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'apps/runtime'),
                       'PYTHONDONTWRITEBYTECODE': '1', 'ODOO_MCP_RETRY_ATTEMPTS': '1',
                       'ODOO_MCP_RETRY_BACKOFF': '0'},
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert finished.returncode == 0, finished.stderr
    assert json.loads(finished.stdout) == {'attempts': attempts,
                                           'error': 'BACKEND_TIMEOUT: synthetic timeout'}


@pytest.mark.parametrize('failure', [policy.BackendDenied, policy.BackendBusy])
def test_policy_denial_and_busy_are_never_reclassified_or_retried(monkeypatch, failure):
    transport = policy.XMLTransport('http://127.0.0.1:12001')
    calls = []

    def blocked(*_args):
        calls.append('one exchange')
        raise failure()

    monkeypatch.setattr(transport, 'single_request', blocked)
    with pytest.raises(failure):
        transport.request('127.0.0.1:12001', '/xmlrpc/2/object', b'<methodCall/>')
    assert calls == ['one exchange']


def test_redirect_and_foreign_host_fail_before_any_replay():
    paths = []
    sink_posts = []

    class Sink(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            sink_posts.append(self.path)
            self.send_error(500)

    sink = ThreadingHTTPServer(('127.0.0.1', 0), Sink)
    sink_thread = threading.Thread(target=sink.serve_forever, daemon=True)
    sink_thread.start()

    class Redirect(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            paths.append(self.path)
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(307)
            self.send_header('location', f'http://127.0.0.1:{sink.server_port}/xmlrpc/2/object')
            self.send_header('Content-Length', '0')
            self.end_headers()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f'http://127.0.0.1:{server.server_port}'
        transport = policy.XMLTransport(base)
        proxy = xmlrpc.client.ServerProxy(base + '/xmlrpc/2/object', transport=transport)
        with pytest.raises(ValueError, match='BACKEND_HTTP_ERROR status=307'):
            proxy.execute_kw('test', 7, 'DUMMY', 'res.partner', 'read', [[]])
        assert paths == ['/xmlrpc/2/object']
        assert sink_posts == []

        foreign = xmlrpc.client.ServerProxy('http://foreign.invalid/xmlrpc/2/object',
                                            transport=transport)
        with pytest.raises(policy.BackendDenied):
            foreign.execute_kw('test', 7, 'DUMMY', 'res.partner', 'read', [[]])
        assert paths == ['/xmlrpc/2/object']
        assert sink_posts == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        sink.shutdown()
        sink.server_close()
        sink_thread.join(timeout=5)
