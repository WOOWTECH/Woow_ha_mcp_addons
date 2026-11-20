"""HM-32 (multi-profile plan 12.3; PaaS #135 3c06b98, #139 009dc99): the LiteLLM and EMQX children keep no idle backend
connection, so the first request after a network outage never waits on a stale socket.

After a brief outage a pooled connection can look alive while the backend no longer answers on it. Reused, it makes the
first request after the backend is reachable again wait for the read timeout (PaaS saw it with EMQX emqx_cluster_status
and LiteLLM litellm_key_info). So every request opens a fresh connection: it resolves the configured name again and
passes the destination checks again (apps/runtime/backend_policy.py: Destination.check_host, checked_answers,
connectable), and nothing is retried (PaaS #135: no retry at all): an ambiguous write is never sent twice, and a read
the backend drops is not sent again either.

Each scenario runs on two pools:
- child: the client exactly as the child builds it (lifespan.build_client / make_client through
  backend_policy.async_client: LiteLLM explicitly opts into 50 connections; EMQX retains 4. Both keep no idle connections.
- asked: the same transport (pinned network backend, destination checks) with its pool built from the limits the
  product's lifespan passes. HM-32 makes both products ask for no idle connection (as PaaS), so they stay right if
  backend_policy ever takes the caller's limits. Red before HM-32: LiteLLM asked for 20 idle connections kept 30 s,
  EMQX for 10.

Each (product, pool) runs once, in the product's pinned environment (apps/<product>/.venv, as CI installs it) and in one
process: the fake backend is a loopback HTTP server on a thread, the product's FastMCP server is reached through
fastmcp's in-memory client. No product child process starts and nothing listens on 3000 or 18000-18099. The environment
is the one products.child_spec builds for the child (fake values: T x 43, C x 43; the configured name is a .invalid name
the harness resolves to the fake backend, and only the fake backend's port is added to the saved URL). The case-by-case
map to PaaS's tests is in docs/provenance/ha-multiprofile-HM-32-20261117.md.
"""
import json
import subprocess

import pytest

import loopback_backends
from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core.products import DENY_LOOPBACK_ENV, ProductState, child_spec

PRODUCTS = ('litellm', 'emqx')
POOLS = ('child', 'asked')
CONNECTIONS = {
    'litellm': {'url': 'http://backend.invalid', 'master_key': 'T' * 43},
    'emqx': {'url': 'http://backend.invalid', 'api_key': 'T' * 43, 'api_secret': 'C' * 43},
}
FAKES = ('T' * 43, 'C' * 43)
READ_TIMEOUT = 2.0  # the child's REQUEST_TIMEOUT in the harness: what a stale socket would cost the first call
UNAVAILABLE = {'litellm': 'BACKEND_UNAVAILABLE', 'emqx': 'EMQX_UNAVAILABLE'}  # the product's own ambiguous-write error

HARNESS = r'''
import asyncio
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PRODUCT, POOL, TIMEOUT = sys.argv[1], sys.argv[2], sys.argv[3]
NAME = 'backend.invalid'  # the configured name, resolved to the fake backend below
DENIED = '169.254.169.254'  # what the name answers once a scenario re-points it: refused by every rule
PROXY = 'http://127.0.0.1:1'  # the proxies the environment names; trust_env=False never uses them
connects = []


def audit(event, args):
    if event == 'socket.connect' and isinstance(args[1], tuple):
        connects.append([str(args[1][0]), args[1][1]])


sys.addaudithook(audit)
for variable in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
    os.environ[variable] = PROXY


def reply(path):
    if path.endswith('/nodes'):
        return [{'node': 'emqx@backend.invalid', 'version': '5.8.9', 'node_status': 'running'}]
    if path.endswith('/key/info'):
        return {'key': 'hashed', 'info': {'key_alias': 'hm32', 'spend': 0}}
    return {'data': []}


class Backend(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        self.lock = threading.Lock()
        self.connections = 0
        self.reset()
        super().__init__(('127.0.0.1', 0), Handler)

    def reset(self):
        with self.lock:
            self.requests, self.served, self.stale = [], set(), set()
            self.available, self.blackhole, self.drop_writes, self.drop_reads = True, False, False, False
            self.release = threading.Event()


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass  # the request line of litellm_key_info carries a key

    def setup(self):
        super().setup()
        with self.server.lock:
            self.server.connections += 1
            self.number = self.server.connections

    def do_GET(self):
        self.answer()

    def do_POST(self):
        self.answer()

    def answer(self):
        server = self.server
        length = int(self.headers.get('Content-Length') or 0)
        if length:
            self.rfile.read(length)
        path = self.path.split('?')[0]
        with server.lock:
            server.requests.append({'method': self.command, 'path': path, 'connection': self.number})
            stale = server.blackhole and self.number in server.stale
            drop = (self.command == 'POST' and server.drop_writes) or (self.command == 'GET' and server.drop_reads)
            available, release = server.available, server.release
            if not (stale or drop):
                server.served.add(self.number)  # recorded before the answer leaves
        if stale or drop:
            # stale: the old pooled connection after the outage, open but answering nothing.
            # drop: an ambiguous write (or a read), received in full; the connection is gone before any answer.
            if stale:
                release.wait(30)
            self.close_connection = True
            return
        body = json.dumps(reply(path) if available else {'error': 'unavailable'}).encode()
        self.send_response(200 if available else 503)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


original = socket.getaddrinfo
resolutions = []
answer = ['127.0.0.1']


def resolve(host, port, *args, **kwargs):
    if host == NAME:
        resolutions.append(answer[0])
        return original(answer[0], port, *args, **kwargs)
    return original(host, port, *args, **kwargs)


socket.getaddrinfo = resolve
backend = Backend()
threading.Thread(target=backend.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True).start()
prefix = {'litellm': 'LITELLM_MCP_', 'emqx': 'EMQX_MCP_'}[PRODUCT]
assert os.environ[prefix + 'BASE_URL'] == 'http://' + NAME, 'the saved URL is the test state one'
os.environ[prefix + 'BASE_URL'] = 'http://%s:%d' % (NAME, backend.server_port)
os.environ[prefix + 'REQUEST_TIMEOUT'] = TIMEOUT  # the read timeout a stale socket would cost

import backend_policy
import fastmcp
import httpx

if PRODUCT == 'litellm':
    from woow_litellm_mcp_server import lifespan as product
    from woow_litellm_mcp_server.errors import litellm_request
    from woow_litellm_mcp_server.server import build_server
    make, path = product.build_client, '/v1/models'
    tool, arguments, tool_path = 'litellm_key_info', {'key': 'C' * 43}, '/key/info'

    async def write(client):
        await litellm_request(client, 'POST', '/key/generate', json_data={'key_alias': 'hm32'})

    async def read(client):
        await litellm_request(client, 'GET', '/v1/models')
else:
    from emqx_mcp_server import lifespan as product
    from emqx_mcp_server.errors import emqx_request
    from emqx_mcp_server.server import build_server
    make, path = product.make_client, '/nodes'
    tool, arguments, tool_path = 'emqx_cluster_status', {}, '/api/v5/nodes'

    async def write(client):
        await emqx_request(client, 'POST', '/mqtt/publish', json={'topic': 'hm32/fresh', 'payload': 'x'})

    async def read(client):
        await emqx_request(client, 'GET', '/nodes')

DEFAULT_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)  # httpx's own default
asked = []
policy_client = backend_policy.async_client


def async_client(*, base_url, **kwargs):
    """The child's async_client; on the 'asked' pool, its transport's pool is rebuilt from the product's limits."""
    limits = kwargs.get('limits') or DEFAULT_LIMITS
    asked.append(limits)
    client = policy_client(base_url=base_url, **kwargs)
    if POOL == 'asked':
        transport = client._transport
        httpx.AsyncHTTPTransport.__init__(transport, trust_env=False, limits=limits)
        transport._pool._network_backend = backend_policy.PinnedAsyncBackend(transport.destination)
    return client


product.async_client = async_client


def described(limits):
    return {'max_connections': limits.max_connections, 'max_keepalive_connections': limits.max_keepalive_connections,
            'keepalive_expiry': limits.keepalive_expiry}


def pool_of(client):
    pool = client._transport._pool
    return {'max_connections': pool._max_connections, 'max_keepalive_connections': pool._max_keepalive_connections,
            'keepalive_expiry': pool._keepalive_expiry}


def health():
    """A fresh connection of its own, as the health probe of PaaS's test."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open('http://127.0.0.1:%d/health' % backend.server_port, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        error.close()
        return error.code


def text_of(result):
    return ' '.join(getattr(item, 'text', '') for item in result.content)[:500]


async def in_a_row():
    """Two requests, then a third once the name answers a refused address."""
    backend.reset()
    del resolutions[:]
    answer[0] = '127.0.0.1'
    async with make() as client:
        pool = pool_of(client)
        statuses, idle, before = [], [], len(connects)
        for _ in range(2):
            statuses.append((await client.get(path)).status_code)
            idle.append(len(client._transport._pool.connections))
        resolved, connected = len(resolutions), len(connects) - before
        answer[0] = DENIED
        try:
            third = 'answered %d' % (await client.get(path)).status_code
        except Exception as exc:
            third = '%s: %s' % (type(exc).__name__, exc)
    return pool, {'statuses': statuses, 'idle_after_each': idle, 'resolutions': resolved, 'connects': connected,
                  'connections': len({r['connection'] for r in backend.requests[:2]}), 'third': third[:500],
                  'third_resolutions': len(resolutions) - resolved, 'third_reached_backend': len(backend.requests) - 2}


async def recovery():
    """PaaS #139: a call, an outage and its recovery seen on fresh connections, then the first call after it."""
    backend.reset()
    answer[0] = '127.0.0.1'
    async with fastmcp.Client(build_server()) as mcp:
        baseline = await mcp.call_tool(tool, arguments, raise_on_error=False)
        with backend.lock:
            backend.available = False
            backend.stale = set(backend.served)  # every connection that answered before the outage
        outage = await asyncio.to_thread(health)
        with backend.lock:
            backend.available = True
        recovered = await asyncio.to_thread(health)
        with backend.lock:
            backend.blackhole = True
        before = len(backend.requests)
        started = time.monotonic()
        first = await mcp.call_tool(tool, arguments, raise_on_error=False)
        elapsed = time.monotonic() - started
        after = [r for r in backend.requests[before:] if r['path'] == tool_path]
    backend.release.set()
    return {'baseline_error': baseline.is_error, 'baseline_text': text_of(baseline) if baseline.is_error else '',
            'outage': outage, 'recovered': recovered, 'stale': len(backend.stale), 'first_error': first.is_error,
            'first_text': text_of(first) if first.is_error else '', 'elapsed': round(elapsed, 3),
            'sent_after_recovery': len(after), 'on_stale': sum(r['connection'] in backend.stale for r in after)}


async def ambiguous_write():
    """The backend reads a write in full and drops the connection before answering."""
    backend.reset()
    answer[0] = '127.0.0.1'
    with backend.lock:
        backend.drop_writes = True
    async with make() as client:
        try:
            await write(client)
            outcome = 'answered'
        except Exception as exc:
            outcome = '%s: %s' % (type(exc).__name__, exc)
    return {'posts': sum(r['method'] == 'POST' for r in backend.requests), 'outcome': outcome[:500]}


async def dropped_read():
    """The backend reads a GET in full and drops the connection before answering: a read is not sent again either."""
    backend.reset()
    answer[0] = '127.0.0.1'
    with backend.lock:
        backend.drop_reads = True
    async with make() as client:
        try:
            await read(client)
            outcome = 'answered'
        except Exception as exc:
            outcome = '%s: %s' % (type(exc).__name__, exc)
    return {'gets': sum(r['method'] == 'GET' for r in backend.requests), 'outcome': outcome[:500]}


async def main():
    pool, row = await in_a_row()
    observed = {'product': PRODUCT, 'pool_kind': POOL, 'pool': pool, 'in_a_row': row, 'recovery': await recovery(),
                'write': await ambiguous_write(), 'read': await dropped_read()}
    observed['asked'] = described(asked[0])
    observed['asked_all_same'] = len(asked) == 4 and all(described(limits) == observed['asked'] for limits in asked)
    observed['unexpected_connects'] = [c for c in connects if c != ['127.0.0.1', backend.server_port]]
    return observed


observed = asyncio.run(main())
backend.release.set()
backend.shutdown()
backend.server_close()
print(json.dumps(observed, sort_keys=True))
'''


@pytest.fixture(autouse=True)
def fake_values_never_logged(log_scan):
    log_scan.watch(*FAKES, kind='secret')


@pytest.fixture(scope='module', params=[(product, pool) for product in PRODUCTS for pool in POOLS], ids='-'.join)
def observed(request, tmp_path_factory):
    product, pool = request.param
    state = ProductState(product=product, token='T' * 43, child_token='C' * 43, connection=CONNECTIONS[product])
    with loopback_backends.allowed():  # once the product is switched on, its child refuses loopback backends (HM-20)
        spec = child_spec(state, tmp_path_factory.mktemp(f'{product}-{pool}'))
    assert DENY_LOOPBACK_ENV not in spec.env
    result = subprocess.run([spec.argv[0], '-c', HARNESS, product, pool, str(READ_TIMEOUT)], env=spec.env,
                            cwd=spec.cwd, capture_output=True, text=True, timeout=120)
    leaked = any(fake in result.stdout + result.stderr for fake in FAKES)
    assert result.returncode == 0, 'harness failed (output withheld: it holds a fake credential)' if leaked else (
        result.stderr)
    assert not leaked, 'a credential reached the harness output'
    return json.loads(result.stdout.splitlines()[-1])


def test_the_pool_keeps_no_idle_connection(observed):
    """child: backend_policy's own pool. asked: the pool built from the limits the product's lifespan passes (HM-32 asks
    for none, as PaaS: LiteLLM 20 kept 30 s -> 0 with keepalive_expiry dropped, PaaS #139; EMQX 10 -> 0, PaaS #135).
    LiteLLM opts into 50 connections; EMQX retains the policy default of 4. The products ask for 50 and 20 respectively."""
    pool, asked = observed['pool'], observed['asked']
    assert observed['asked_all_same'], 'every client the product builds asks for the same pool'
    if observed['pool_kind'] == 'asked':
        assert pool == asked, (pool, asked)
        assert asked['max_connections'] == {'litellm': 50, 'emqx': 20}[observed['product']], asked
    else:
        assert (pool['max_connections'], pool['max_keepalive_connections']) == (
            {'litellm': 50, 'emqx': 4}[observed['product']], 0), pool
    assert pool['max_keepalive_connections'] == 0, pool


def test_each_request_resolves_and_uses_a_fresh_pinned_connection(observed):
    """PaaS #135 test_each_request_resolves_and_uses_fresh_pinned_socket on HA's transport: two requests, two
    resolutions of the configured name, two connections; no connection is left idle after its response, and the
    environment's proxies are never used."""
    row = observed['in_a_row']
    assert row['statuses'] == [200, 200]
    assert row['resolutions'] == 2, 'each request resolves the configured name again'
    assert (row['connects'], row['connections']) == (2, 2), 'idle TCP connections must not survive between requests'
    assert row['idle_after_each'] == [0, 0]
    assert observed['unexpected_connects'] == []


def test_each_request_checks_its_destination_again(observed):
    """Once the name answers a refused address, the next request is refused before it connects: its destination is
    checked again (checked_answers, connectable), not taken from a connection an earlier request left open."""
    row = observed['in_a_row']
    assert row['third'] == 'BackendDenied: BACKEND_DESTINATION_DENIED', row['third']
    assert (row['third_resolutions'], row['third_reached_backend']) == (1, 0), 'resolved once, refused before sending'
    assert observed['unexpected_connects'] == []


def test_the_first_call_after_a_recovery_uses_a_fresh_connection(observed):
    """PaaS #139 test_first_key_info_after_health_recovery_uses_fresh_connection, for both products through the real
    tool (litellm_key_info, emqx_cluster_status): after an outage and a recovery seen on fresh connections, the old
    connection is open but answers nothing; the first call does not touch it and does not wait for the read timeout."""
    row = observed['recovery']
    assert not row['baseline_error'], row['baseline_text']
    assert (row['outage'], row['recovered'], row['stale']) == (503, 200, 1)
    assert not row['first_error'], row['first_text']
    assert row['on_stale'] == 0
    assert row['elapsed'] < READ_TIMEOUT


def test_nothing_is_sent_twice(observed):
    """No retry (PaaS #135: none at all; #139): the first call after the recovery reaches the backend once, and a write
    the backend received but never answered is reported as the product's unavailable error, never sent again. A read
    the backend dropped the same way is not sent again either (through the product's own request function)."""
    row, write, read = observed['recovery'], observed['write'], observed['read']
    assert row['sent_after_recovery'] == 1
    assert write['posts'] == 1, write
    assert write['outcome'] != 'answered' and UNAVAILABLE[observed['product']] in write['outcome'], write['outcome']
    assert read['gets'] == 1, read
    assert read['outcome'] != 'answered' and UNAVAILABLE[observed['product']] in read['outcome'], read['outcome']
