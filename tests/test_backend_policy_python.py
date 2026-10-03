"""Transport address, pinning, scope and TLS contract (no external connects)."""
import importlib.util
from pathlib import Path
import socket
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

spec = importlib.util.spec_from_file_location('backend_policy', Path(__file__).resolve().parents[1] / 'apps/runtime/backend_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def test_source_guard_fails_closed(monkeypatch):
    monkeypatch.setitem(policy._SOURCE_HASHES, 'httpx/_transports/default.py', '0' * 64)
    with pytest.raises(RuntimeError, match='requires source review'):
        policy.check_sources()


@pytest.mark.parametrize('address', ['169.254.169.254', '100.100.100.200', '168.63.129.16',
    '0.0.0.0', '224.0.0.1', '240.0.0.1', '192.0.0.192', '192.0.2.1', '198.51.100.1',
    '203.0.113.1', '192.88.99.1', '::', 'fe80::1', 'ff02::1', '::ffff:127.0.0.1',
    '::ffff:0:127.0.0.1', '64:ff9b::1', '64:ff9b:1::1', '2002:7f00:1::', '2001::1',
    '2001:db8::1', 'fd00:ec2::254', 'fc00::1%eth0'])
def test_denied_addresses(address):
    assert not policy.allowed_address(address)


@pytest.mark.parametrize('address', ['127.0.0.1', '10.1.2.3', '172.16.0.1', '192.168.1.1',
    '8.8.8.8', '::1', 'fd12::1', '2606:4700:4700::1111'])
def test_intended_addresses(address):
    assert policy.allowed_address(address)


@pytest.mark.parametrize('url', ['http://other.invalid/base/a', 'http://configured.invalid:81/base/a',
    'https://configured.invalid/base/a', 'http://configured.invalid/outside',
    'http://configured.invalid/baseball/a', 'http://configured.invalid/base/%2e%2e/secret',
    'http://configured.invalid/base/%252e%252e/secret'])
def test_origin_base_path(url):
    with pytest.raises(policy.BackendDenied):
        policy.Destination('http://configured.invalid/base').check_url(url)


@pytest.mark.parametrize('kind', ['sync', 'async', 'xmlrpc'])
async def test_dns_is_pinned_without_second_lookup(monkeypatch, kind):
    looked_up, connected = [], []
    def resolve(host, port, *args, **kwargs):
        looked_up.append(host)
        ip = '127.0.0.1' if len(looked_up) == 1 else '169.254.169.254'
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (ip, port))]
    def intercept(self, address):
        connected.append(address)
        raise OSError('owned test interceptor')
    monkeypatch.setattr(socket, 'getaddrinfo', resolve)
    monkeypatch.setattr(socket.socket, 'connect', intercept)
    with pytest.raises(Exception):
        if kind == 'sync':
            with policy.sync_client(base_url='http://configured.invalid', timeout=1) as client:
                client.get('/path')
        elif kind == 'async':
            async with policy.async_client(base_url='http://configured.invalid', timeout=1) as client:
                await client.get('/path')
        else:
            policy.XMLTransport('http://configured.invalid').request('configured.invalid', '/xmlrpc/2/common', b'canary')
    assert looked_up == ['configured.invalid']
    assert connected == [('127.0.0.1', 80)]


@pytest.mark.parametrize('kind', ['sync', 'async', 'xmlrpc'])
@pytest.mark.parametrize('fallback', [False, True])
async def test_https_original_hostname_verification_and_sni(tmp_path, monkeypatch, kind, fallback):
    # Disposable self-signed test CA/leaf, never a real credential. Only loopback.
    cert, key = tmp_path / 'test.crt', tmp_path / 'test.key'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
        '-subj', '/CN=configured.invalid', '-addext', 'subjectAltName=DNS:configured.invalid',
        '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True)
    sni, requests = [], []
    status = {'value': 200}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            requests.append(self.headers['Host'])
            self.send_response(status['value']); self.send_header('location', '/capture')
            self.send_header('Content-Length','2'); self.end_headers(); self.wfile.write(b'{}')
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            requests.append(self.headers['Host'])
            body=b'<?xml version="1.0"?><methodResponse><params><param><value><int>7</int></value></param></params></methodResponse>'
            self.send_response(status['value']); self.send_header('location', '/capture')
            self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(cert,key)
    ctx.set_servername_callback(lambda sock, name, context: sni.append(name))
    server.socket=ctx.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    original=ssl.create_default_context
    def trusted(*args, **kwargs):
        result=original(*args, **kwargs); result.load_verify_locations(cert); return result
    def resolve(host, port, *a, **kw):
        answers = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('127.0.0.1', port))]
        if fallback:
            answers.insert(0, (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('::1', port, 0, 0)))
        return answers
    monkeypatch.setattr(socket, 'getaddrinfo', resolve)
    async def fetch(host):
        base=f'https://{host}:{server.server_port}'
        if kind=='sync':
            with policy.sync_client(base_url=base,timeout=2) as client: return client.get('/base').status_code
        if kind=='async':
            async with policy.async_client(base_url=base,timeout=2) as client: return (await client.get('/base')).status_code
        return policy.XMLTransport(base).request(f'{host}:{server.server_port}','/xmlrpc/2/common',b'<methodCall/>')
    try:
        with pytest.raises(Exception): await fetch('configured.invalid')  # untrusted cert
        assert not requests
        monkeypatch.setattr(ssl,'create_default_context',trusted)
        monkeypatch.setattr(ssl,'_create_default_https_context',trusted)
        assert await fetch('configured.invalid') in (200, (7,))
        assert requests == [f'configured.invalid:{server.server_port}']
        with pytest.raises(Exception): await fetch('wrong.invalid')  # trusted, wrong name
        assert len(requests)==1
        assert 'configured.invalid' in sni and 'wrong.invalid' in sni
        for code in (301, 302, 303, 307, 308):
            status['value'] = code
            before = len(requests)
            with pytest.raises(Exception, match=f'BACKEND_HTTP_ERROR status={code}'):
                await fetch('configured.invalid')
            assert len(requests) == before + 1, 'HTTPS redirect was replayed'
    finally:
        server.shutdown(); server.server_close(); thread.join()
