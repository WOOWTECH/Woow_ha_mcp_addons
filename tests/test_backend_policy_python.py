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


def _encoded(name):
    """A name as the clients send it: every character outside the unreserved set percent-encoded once."""
    from urllib.parse import quote
    return quote(name, safe='')


def _layers(count):
    """'%41' encoded `count` more times: after the one decode every server performs, it still changes on `count` more."""
    from urllib.parse import quote
    value = '%41'
    for _ in range(count):
        value = quote(value, safe='')
    return value


@pytest.mark.parametrize('name', ['100%-off.txt', '100% done', '%', '50%25.txt', '%E6%AF%9B', 'a%zz', 'a%2eb',
                                  '毛利率35%.xlsx', '%%%', '1.5%', 'report%20final.pdf', '%18 KDV.xlsx', '%10 zam.xlsx',
                                  '%05 indirim.pdf', '%100 Pamuk Tişört.jpg', 'frame_%04d.png', 'out%1d.mp4',
                                  '50%descuento.pdf', '100%Beef.jpg', '%80 indirim.pdf'])
def test_request_path_may_carry_a_literal_percent(name):
    """A file or calendar name may contain '%': it travels encoded once ('%' as '%25'), and decoding again, as a proxy or
    a backend that decodes twice would, keeps the path's shape: '50%25' gives '50%', '%E6%AF%9B' one CJK character,
    'a%2eb' 'a.b' (not a dot segment); a Turkish percent-first name ('%18 KDV') or a printf pattern ('frame_%04d') gives a
    control character that is not a line break; '50%descuento' gives an invalid UTF-8 byte, never an error."""
    destination = policy.Destination('http://configured.invalid/base')
    destination.check_url(f'http://configured.invalid/base/{_encoded(name)}')
    destination.check_url(f'http://configured.invalid/base/{_encoded(name)}/inside.md')
    assert policy.path_value(f'/base/{_encoded(name)}', literal_percent=True) == f'/base/{name}'


@pytest.mark.parametrize('path', [
    # a dot segment, '/', '\', '?', '#', NUL or line break that only a further decode produces, however deeply nested
    '/base/' + _encoded('%2e%2e') + '/secret', '/base/' + _encoded('%2E%2e') + '/secret', '/base/' + _encoded('%2e'),
    '/base/' + _encoded('a%2fb'), '/base/' + _encoded('a%2Fb'), '/base/' + _encoded('a%5cb'),
    '/base/' + _encoded('a%3fb'), '/base/' + _encoded('a%23b'), '/base/a%3Fb' + _encoded('%3F'),
    '/base/' + _encoded('a%00b'), '/base/' + _encoded('a%0ab'), '/base/' + _encoded('a%0db'),
    '/base/' + _encoded('a%C2%85b'), '/base/' + _encoded('a%E2%80%A8b'),
    '/base/' + _encoded(_encoded('%2e%2e')) + '/x', '/base/' + _encoded(_encoded('a%2fb')), '/base/' + _layers(9),
    # a '%' on the wire that does not start a %XX escape (httpx sends it as it is)
    '/base/100%-off.txt', '/base/a%2', '/base/%%32%65%%32%65/x', '/base/.%2g./x', '/base/%u002e%u002e/secret',
    # escapes Python's unquote leaves alone but other decoders read: %uXXXX (IIS, .NET, JavaScript's unescape) at any
    # layer, Unicode decimal or fullwidth hex digits (Java's URLDecoder, int()), Jetty's '>' (14)
    '/base/' + _encoded('%u002e%u002e') + '/secret', '/base/' + _encoded('%U002F'),
    '/base/' + _encoded(_encoded('%u005c')), '/base/' + _encoded('%u００２ｅ'),
    '/base/' + _encoded('%２e%２e') + '/secret', '/base/' + _encoded('%٢e'), '/base/' + _encoded('%2ｅ'),
    '/base/' + _encoded('a%２fb'), '/base/' + _encoded('a%５cb'), '/base/' + _encoded('a%３fb'),
    '/base/' + _encoded('a%０d%０ab'), '/base/%252%3E%252%3E/x',
    # an invalid escape nginx drops into a dot segment ('.%.', '.%2..'); overlong UTF-8 after a further decode
    '/base/.%25./x', '/base/.%252../x', '/base/%25c0%25ae%25c0%25ae/secret', '/base/%25e0%2580%25ae',
    '/base/%25c0%25af', '/base/%25c1%259c'])
def test_literal_percent_never_decodes_into_structure(path):
    """No decoder in front of or inside the backend may read more structure into a request path than its first decode
    gave; also refused: a '%' on the wire that starts no %XX escape, and a path still changing after eight more decodes."""
    with pytest.raises(policy.BackendDenied):
        policy.Destination('http://configured.invalid/base').check_url('http://configured.invalid' + path)


@pytest.mark.parametrize('path', ['/base/%25\ud800', '/base/\udcff%2541', '/base/%25%00%0A', '/base/' + '%25' * 20000,
                                  '/base/' + '%25.' * 20000, '/base/' + '%252.' * 20000])
def test_odd_request_paths_are_refused_or_kept_never_an_error(path):
    try:
        policy.path_value(path, literal_percent=True)
    except policy.BackendDenied:
        pass


def test_a_further_decode_may_keep_what_the_first_decode_gave():
    """Counts are compared, not presence: a configured base path holding an encoded '?' (accepted, as before) still
    serves names with a literal '%'."""
    destination = policy.Destination('http://configured.invalid/a%3Fb')
    destination.check_url('http://configured.invalid/a%3Fb/' + _encoded('50%41.txt'))
    destination.check_url('http://configured.invalid/a%3Fb/' + _encoded('%'))


def test_eight_further_decodes_are_the_limit():
    destination = policy.Destination('http://configured.invalid/base')
    assert policy.path_value('/base/' + _layers(8), literal_percent=True) == '/base/' + _layers(7)
    destination.check_url('http://configured.invalid/base/' + _layers(8))
    with pytest.raises(policy.BackendDenied):
        destination.check_url('http://configured.invalid/base/' + _layers(9))


@pytest.mark.parametrize('kind', ['sync', 'async', 'xmlrpc'])
async def test_transports_check_the_path_they_send(kind):
    """Through the real clients and a loopback backend: an encoded literal '%' arrives encoded exactly once; a bare '%', a
    %uXXXX escape, and a '/' or '..' one decode deeper never leave the gateway."""
    paths = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            paths.append(self.path)
            self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'{}')
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            paths.append(self.path)
            body = b'<?xml version="1.0"?><methodResponse><params><param><value><int>7</int></value></param></params></methodResponse>'
            self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    host = f'127.0.0.1:{server.server_port}'
    async def send(name, **extensions):
        # The children build request URLs relative to the configured base URL.
        if kind == 'sync':
            with policy.sync_client(base_url=f'http://{host}/base', timeout=2) as client:
                return client.get(name, extensions=extensions).status_code
        if kind == 'async':
            async with policy.async_client(base_url=f'http://{host}/base', timeout=2) as client:
                return (await client.get(name, extensions=extensions)).status_code
        return policy.XMLTransport(f'http://{host}/base').request(host, '/base/' + name, b'<methodCall/>')
    try:
        assert await send('100%25-off.txt') in (200, (7,))
        assert paths == ['/base/100%25-off.txt']
        for name in ('100%-off.txt', '%u002e%u002e/secret', '%25u002e%25u002e/secret', 'a%252fb', '%252e%252e/secret'):
            with pytest.raises(policy.BackendDenied):
                await send(name)
        if kind != 'xmlrpc':  # httpcore would send this target instead of the checked path
            with pytest.raises(policy.BackendDenied):
                await send('100%25-off.txt', target=b'/outside/secret')
        assert paths == ['/base/100%25-off.txt']
    finally:
        server.shutdown(); server.server_close(); thread.join()


@pytest.mark.parametrize('kind', ['sync', 'async'])
async def test_clients_refuse_dot_segments_before_httpx_drops_them(kind):
    """httpx resolves '.' and '..' while it builds the URL, so check_url never sees them: a tool argument spliced into a
    path ('..', '../../global/spend/reset?') would reach another endpoint under the base. The clients refuse them in
    the path as written; a '..' in the query string, an encoded one (refused later by path_value) and ordinary paths
    are unaffected."""
    paths = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            paths.append(self.path)
            self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'{}')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    async def send(url):
        if kind == 'sync':
            with policy.sync_client(base_url=f'{origin}/base', timeout=2) as client:
                return client.get(url).status_code
        async with policy.async_client(base_url=f'{origin}/base', timeout=2) as client:
            return (await client.get(url)).status_code
    try:
        for url in ('banned/clientid/..', 'key/../../global/spend/reset?/regenerate', './x', 'x/.', 'a/../b', '..',
                    '/base/x/../y', f'{origin}/base/x/../y', f'{origin}/base/..', httpx.URL('x/../y'),
                    '//[/../x', '//evil.invalid/x', '//base/x'):
            with pytest.raises(policy.BackendDenied):
                await send(url)
        assert paths == []
        for url in ('x', 'a.b/..c/...', 'x?path=../y', f'{origin}/base/x', httpx.URL(f'{origin}/base/x')):
            assert await send(url) == 200
        assert paths == ['/base/x', '/base/a.b/..c/...', '/base/x?path=../y', '/base/x', '/base/x']
        with pytest.raises(policy.BackendDenied):
            await send('%2e%2e/x')
    finally:
        server.shutdown(); server.server_close(); thread.join()


@pytest.mark.parametrize('base', ['http://configured.invalid/next%25cloud', 'http://configured.invalid/%25',
                                  'http://configured.invalid/a/%2e%2e', 'http://configured.invalid/a%5cb'])
def test_configured_base_path_keeps_refusing_percent(base):
    """Only request paths may carry a literal '%'; the configured base URL keeps the strict rule (no '%' after one
    decode), as the admin GUI's save-time check (NextcloudConnection) does."""
    with pytest.raises(policy.BackendDenied):
        policy.Destination(base)


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
            if kind == 'xmlrpc':
                with pytest.raises(Exception, match=f'BACKEND_HTTP_ERROR status={code}'):
                    await fetch('configured.invalid')
            else:  # 0.2.0: the answer goes to the child's own handling (never followed)
                assert await fetch('configured.invalid') == code
            assert len(requests) == before + 1, 'HTTPS redirect was replayed'
    finally:
        server.shutdown(); server.server_close(); thread.join()
