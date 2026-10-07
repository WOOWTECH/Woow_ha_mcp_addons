"""0.1.7 Nextcloud: exact child contract, Host guard, public errors and the private probe.

Actual vendored child (apps/nextcloud) through the actual gateway; only owned loopback fakes and dummy credentials.
"""
import asyncio
import json
from pathlib import Path
import subprocess
import threading

import httpx
import pytest

from mcp_admin_core.gateway import make_apps
from mcp_admin_core.health import HealthMonitor
from mcp_admin_core.native_inventory import NAMES
from mcp_admin_core.products import (ODOO_HEALTH_PROBE, PROBES, ROOT, ProductState, ProductStore, TOOLS, child_spec,
                                     health_probe, health_probe_success, probe_success)
from owned_runtime import Endpoint
import nextcloud_fixtures
from nextcloud_fixtures import NextcloudFake, OCS_PATH, respond
from test_real_products import connection, rpc
from test_six_hardening import Quiet, call, runtime, serve
from test_expansion_runtime import payload

CANARY = 'DUMMY-NEXTCLOUD-BACKEND-TEXT'
WRITERS = {name for name, tool in TOOLS['nextcloud'].items() if tool.write}
READERS = set(TOOLS['nextcloud']) - WRITERS


def state(grants=(), **kwargs):
    return ProductState(product='nextcloud', token='a'*43, child_token='b'*43,
                        connection=connection('nextcloud', 'https://cloud.example.test'),
                        enabled_write_tools=list(grants), **kwargs)


def test_contract_names_tools_and_probe_shapes():
    assert NAMES['nextcloud'] == tuple(sorted(TOOLS['nextcloud']))
    assert READERS == {'get_file_tree', 'get_file_content', 'read_text_file', 'list_calendars', 'list_tasks'}
    assert WRITERS == {'create_text_file', 'update_text_file', 'upload_file', 'delete_file_checked'}
    assert all(not tool.legacy_write and not tool.write_operations for tool in TOOLS['nextcloud'].values())
    assert health_probe('nextcloud') == (ODOO_HEALTH_PROBE, {}) and ODOO_HEALTH_PROBE not in NAMES['nextcloud']
    assert health_probe_success('nextcloud', {'ok': True, 'user_id': 'tester'})
    for bad in ({'ok': True}, {'ok': 1, 'user_id': 'x'}, {'ok': True, 'user_id': ''}, {'ok': True, 'user_id': 7},
                {'ok': True, 'user_id': 'x', 'files': []}, {'uid': 7}, {'ok': True, 'user_id': 'x' * 257}, [], 'ok'):
        assert not health_probe_success('nextcloud', bad), bad
    entry = {'path': 'a', 'name': 'a', 'type': 'file', 'size': 1, 'modified': None, 'etag': 'e', 'content_type': None}
    assert PROBES['nextcloud'] == ('get_file_tree', {'path': '', 'depth': 1})
    assert probe_success('nextcloud', {'path': '', 'entries': [entry], 'truncated': False})
    assert probe_success('nextcloud', {'path': '', 'entries': [], 'truncated': True})
    for bad in ({'path': 'Documents', 'entries': [], 'truncated': False}, {'path': '', 'entries': {}, 'truncated': False},
                {'path': '', 'entries': [], 'truncated': 0}, {'path': '', 'entries': [{**entry, 'type': 'link'}], 'truncated': False},
                {'path': '', 'entries': [], 'truncated': False, 'error': 'x'}):
        assert not probe_success('nextcloud', bad), bad


def test_child_spec_is_exact_and_grant_driven(tmp_path):
    spec = child_spec(state(), tmp_path)
    app = ROOT / 'apps/nextcloud'
    assert spec.argv == (str(app / '.venv/bin/python'), '-m', 'nextcloud_mcp_server.server', '--transport', 'http',
                         '--host', '127.0.0.1', '--port', '3000', '--path', '/mcp')
    assert spec.cwd == tmp_path / 'child' and not list(spec.cwd.iterdir())
    assert spec.env == {
        'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path / 'child'), 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
        'PYTHONPATH': f'{app / "vendor"}:{ROOT / "apps/runtime"}',
        'NEXTCLOUD_MCP_BASE_URL': 'https://cloud.example.test', 'NEXTCLOUD_MCP_USERNAME': 'tester',
        'NEXTCLOUD_MCP_APP_PASSWORD': 'DUMMY', 'NEXTCLOUD_MCP_READONLY': 'true', 'NEXTCLOUD_MCP_ALLOW_DELETE': 'false',
        'NEXTCLOUD_MCP_DISABLED_TOOLS': ','.join(sorted(WRITERS)),
        'FASTMCP_CHECK_FOR_UPDATES': 'off', 'FASTMCP_SHOW_SERVER_BANNER': 'false'}
    # A writer grant alone: READONLY off, delete still not registered, the other writers disabled natively.
    env = child_spec(state(['update_text_file']), tmp_path).env
    assert (env['NEXTCLOUD_MCP_READONLY'], env['NEXTCLOUD_MCP_ALLOW_DELETE']) == ('false', 'false')
    assert env['NEXTCLOUD_MCP_DISABLED_TOOLS'] == 'create_text_file,delete_file_checked,upload_file'
    env = child_spec(state(['delete_file_checked']), tmp_path).env
    assert (env['NEXTCLOUD_MCP_READONLY'], env['NEXTCLOUD_MCP_ALLOW_DELETE']) == ('false', 'true')
    assert env['NEXTCLOUD_MCP_DISABLED_TOOLS'] == 'create_text_file,update_text_file,upload_file'
    # Disabled wins over a grant; a disabled read is not registered either; the private probe never is listed.
    env = child_spec(state(['delete_file_checked'], disabled=['delete_file_checked', 'list_tasks']), tmp_path).env
    assert (env['NEXTCLOUD_MCP_READONLY'], env['NEXTCLOUD_MCP_ALLOW_DELETE']) == ('true', 'false')
    assert set(env['NEXTCLOUD_MCP_DISABLED_TOOLS'].split(',')) == WRITERS | {'list_tasks'}
    env = child_spec(state(disabled=list(TOOLS['nextcloud'])), tmp_path).env
    assert env['NEXTCLOUD_MCP_DISABLED_TOOLS'].split(',') == list(NAMES['nextcloud'])
    # The legacy global switch grants nothing here.
    assert child_spec(state(writes_enabled=True), tmp_path).env['NEXTCLOUD_MCP_READONLY'] == 'true'


@pytest.mark.parametrize('disabled', [[], ['get_file_tree'], list(NAMES['nextcloud'])])
def test_child_accepts_every_generated_disable_list_and_keeps_probe(tmp_path, disabled):
    """The child exits 2 on unknown DISABLED_TOOLS names: every generated list must be accepted as-is."""
    spec = child_spec(state(sorted(WRITERS), disabled=disabled), tmp_path)
    program = '''
import asyncio, os
from nextcloud_mcp_server.server import create_server
from nextcloud_mcp_server.settings import load_settings
server = create_server(load_settings())
names = sorted(t.name for t in asyncio.run(server.list_tools()))
print(','.join(names))
'''
    result = subprocess.run([spec.argv[0], '-c', program], env=spec.env, cwd=spec.cwd, capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert set(result.stdout.strip().split(',')) == set(NAMES['nextcloud']) - set(disabled) | {ODOO_HEALTH_PROBE}


def test_child_policy_client_and_mandatory_backend_policy(tmp_path):
    """backend_policy.async_client builds the child's client (the v0.1.0 kwargs clash is patched), TLS verification
    cannot be turned off through it, and a broken policy module stops the child (exit 2) before any request."""
    spec = child_spec(state(), tmp_path)
    program = '''
import asyncio, ssl
import backend_policy
from nextcloud_mcp_server.client import NextcloudClient
from nextcloud_mcp_server.settings import load_settings
nc = NextcloudClient(load_settings(verify_tls=False))
assert nc.policy is backend_policy.async_client
async def main():
    client = await nc.http()
    assert isinstance(client._transport, backend_policy.AsyncTransport)
    assert client.follow_redirects is False and client.trust_env is False
    context = client._transport._pool._ssl_context
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    await nc.aclose()
asyncio.run(main())
'''
    result = subprocess.run([spec.argv[0], '-c', program], env=spec.env, cwd=spec.cwd, capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    broken = tmp_path / 'broken'
    broken.mkdir()
    (broken / 'backend_policy.py').write_text('raise RuntimeError("HTTP backend transport requires source review")\n')
    env = {**spec.env, 'PYTHONPATH': f'{broken}:{spec.env["PYTHONPATH"]}'}
    result = subprocess.run(list(spec.argv), env=env, cwd=spec.cwd, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0 and 'Uvicorn running' not in result.stderr


async def test_child_host_origin_guard_accepts_the_gateway_only(tmp_path):
    with serve(Quiet) as url:
        store = ProductStore(tmp_path / 'state', 'nextcloud')
        store.update(connection=connection('nextcloud', url))
        spec = child_spec(store.load(), store.directory)
        assert not {'NEXTCLOUD_MCP_ALLOWED_HOSTS', 'NEXTCLOUD_MCP_CA_BUNDLE', 'NEXTCLOUD_MCP_VERIFY_TLS'} & set(spec.env)
        endpoint = Endpoint('nextcloud')
        manager = endpoint.supervisor(spec)
        init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'host-guard', 'version': '0'}}}
        try:
            await manager.start()
            async with endpoint.client(timeout=10) as child:
                base = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'}
                async with asyncio.timeout(20):
                    while True:
                        try:
                            # The gateway's own request: Host 127.0.0.1:<port> from its fixed child URL.
                            response = await child.post(endpoint.url, headers=base, json=init)
                            break
                        except httpx.HTTPError:
                            await asyncio.sleep(.1)
                assert response.status_code == 200, response.text
                assert response.headers.get('mcp-session-id')
                for headers, status in (({'Host': 'evil.example'}, 421), ({'Host': 'cloud.example.test'}, 421),
                                        ({'Origin': 'https://evil.example'}, 403)):
                    refused = await child.post(endpoint.url, headers={**base, **headers}, json=init)
                    assert refused.status_code == status, (headers, refused.status_code)
                # The gateway itself, through its fixed child URL, works end to end.
                _, app = make_apps(store, TOOLS['nextcloud'], child, child_url=endpoint.url)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as client:
                    headers = {'Authorization': 'Bearer ' + store.load().token, 'Accept': 'application/json, text/event-stream'}
                    result = await rpc(client, '/mcp', headers, init)
                    assert result['serverInfo']['name'] == 'Woow Nextcloud'
        finally:
            await manager.stop()
            endpoint.close()
            store.close()



class Sabre(Quiet):
    """OCS answers normally; every other request answers the status in `mode` with backend text (Sabre message,
    Location) that must never reach a client."""
    mode = {'status': 404}
    seen = []

    def nextcloud(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.seen.append((self.command, self.path))
        if self.path == OCS_PATH:
            return respond(self, *NextcloudFake().handle('GET', self.path, self.headers, body))
        status = self.mode['status']
        if status == 'invalid-xml':
            return respond(self, 207, {'Content-Type': 'application/xml'}, b'<d:multistatus xmlns:d="DAV:">' + CANARY.encode())
        if status == 'not-multistatus':
            return respond(self, 207, {'Content-Type': 'application/xml'}, b'<x>' + CANARY.encode() + b'</x>')
        text = ('<?xml version="1.0"?><d:error xmlns:d="DAV:" xmlns:s="http://sabredav.org/ns">'
                f'<s:exception>Sabre\\DAV\\Exception</s:exception><s:message>{CANARY}</s:message></d:error>').encode()
        headers = {'Content-Type': 'application/xml', 'X-Debug': CANARY}
        if 300 <= status < 400:
            headers['Location'] = f'https://{CANARY.lower()}.example/remote.php/dav/'
        respond(self, status, headers, text)

    do_GET = do_PUT = do_DELETE = do_PROPFIND = do_REPORT = nextcloud


@pytest.mark.parametrize('json_response', [False, True])
async def test_backend_statuses_become_public_codes_without_backend_text(tmp_path, json_response):
    Sabre.seen = []
    grants = sorted(WRITERS)
    cases = [
        ('get_file_tree', {'path': 'x'}, 404, 'BACKEND_HTTP_ERROR status=404: \\"x\\" does not exist.'),
        ('get_file_tree', {'path': 'x'}, 403, 'BACKEND_HTTP_ERROR status=403: Permission denied for'),
        ('get_file_tree', {'path': 'x'}, 500, 'BACKEND_HTTP_ERROR status=500'),
        ('get_file_tree', {'path': 'x'}, 503, 'BACKEND_HTTP_ERROR status=503'),
        ('get_file_tree', {'path': 'x'}, 422, 'BACKEND_HTTP_ERROR status=422'),
        ('get_file_tree', {'path': 'x'}, 401, 'BACKEND_HTTP_ERROR status=401: Nextcloud rejected the username or app password.'),
        ('get_file_tree', {'path': 'x'}, 200, 'BACKEND_HTTP_ERROR status=200'),  # a 2xx that is not 207
        ('get_file_tree', {'path': 'x'}, 'invalid-xml', 'BACKEND_INVALID_RESPONSE'),
        ('get_file_tree', {'path': 'x'}, 'not-multistatus', 'BACKEND_INVALID_RESPONSE'),
        ('list_calendars', {}, 404, 'no calendar home'),
        ('create_text_file', {'path': 'a/b.md', 'content': 'x'}, 412, 'already exists; read it first'),
        ('create_text_file', {'path': 'a/b.md', 'content': 'x'}, 404, 'The parent folder of'),
        ('create_text_file', {'path': 'a/b.md', 'content': 'x'}, 423, 'is locked'),
        ('create_text_file', {'path': 'a/b.md', 'content': 'x'}, 507, 'BACKEND_HTTP_ERROR status=507'),
        ('upload_file', {'path': 'a/b.bin', 'content_base64': 'AA=='}, 413, 'BACKEND_HTTP_ERROR status=413'),
    ] + [('get_file_tree', {'path': 'x'}, status, f'BACKEND_HTTP_ERROR status={status}') for status in (301, 302, 307, 308)]
    with serve(Sabre) as url:
        async with runtime(tmp_path, 'nextcloud', url, json_response=json_response, write_grants=grants) as (client, headers, *_):
            for name, args, status, expected in cases:
                Sabre.mode['status'] = status
                before = len(Sabre.seen)
                response = await client.post('/mcp', headers=headers, json=call(name, args))
                assert response.status_code == 200 and len(Sabre.seen) > before
                assert CANARY not in response.text and CANARY.lower() not in response.text, (name, status, response.text)
                assert '"isError":true' in response.text.replace(' ', ''), (name, status, response.text)
                assert expected in response.text, (name, status, expected, response.text)
                assert len(response.content) < 4096
    # Redirects are never followed: only the one request per call, never the Location.
    assert not any(CANARY.lower() in path for _, path in Sabre.seen)


async def test_stale_etag_write_reports_current_etag_and_writes_nothing(tmp_path):
    fake = NextcloudFake()

    class Backend(Quiet):
        def handle_api(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            respond(self, *fake.handle(self.command, self.path, self.headers, body))
        do_GET = do_PUT = do_DELETE = do_PROPFIND = do_REPORT = handle_api

    with serve(Backend) as url:
        async with runtime(tmp_path, 'nextcloud', url, write_grants=sorted(WRITERS)) as (client, headers, *_):
            for name, args in (('update_text_file', {'path': 'Documents/notes.md', 'content': 'x', 'expected_etag': 'stale'}),
                               ('delete_file_checked', {'path': 'Documents/notes.md', 'expected_etag': 'stale'}),
                               ('upload_file', {'path': 'Documents/notes.md', 'content_base64': 'AA==', 'expected_etag': 'stale'})):
                reply = await rpc(client, '/mcp', headers, call(name, args))
                assert reply.get('isError') and 'current etag one' in json.dumps(reply), (name, reply)
            reply = await rpc(client, '/mcp', headers, call('create_text_file', {'path': 'Documents/notes.md', 'content': 'x'}))
            assert reply.get('isError') and 'already exists' in json.dumps(reply)
            reply = await rpc(client, '/mcp', headers, call('delete_file_checked', {'path': 'Documents', 'expected_etag': 'docs'}))
            assert reply.get('isError') and 'is a folder' in json.dumps(reply)
            assert fake.mutations == [] and fake.files['Documents/notes.md'][1] == 'one'
            text = payload(await rpc(client, '/mcp', headers, call('read_text_file', {'path': 'Documents/notes.md'})))
            assert text['etag'] == 'one' and text['content'].startswith('# Notes')
            assert payload(await rpc(client, '/mcp', headers, call('get_file_content', {'path': 'Documents/notes.md'})),
                           plain=True)['text'] == text['content']


@pytest.mark.parametrize('failure', ['chunk', 'disconnect', 'gzip', 'invalid-xml'])
async def test_late_body_failures_after_account_lookup_are_public_codes(tmp_path, failure):
    """The account lookup succeeds; then WebDAV/CalDAV/file bodies break: only public codes, never the body."""
    seen = []
    fake = NextcloudFake()

    class Backend(Quiet):
        def handle_api(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            # The real answer's status (207 multistatus or 200 file), then a broken body.
            status, headers, _ = fake.handle(self.command, self.path, self.headers, body)
            if self.path == OCS_PATH:
                return respond(self, *fake.handle(self.command, self.path, self.headers, body))
            seen.append((self.command, self.path))
            if failure == 'invalid-xml':
                return respond(self, status, {'Content-Type': 'application/xml'}, b'<' + CANARY.encode())
            self.send_response(status)
            if failure == 'chunk':
                self.send_header('Transfer-Encoding', 'chunked')
                data = CANARY.encode() + b'\r\n'
            elif failure == 'disconnect':
                self.send_header('Content-Length', '10000')
                data = CANARY.encode()
            else:
                data = CANARY.encode()
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Content-Encoding', 'gzip')
            self.end_headers()
            self.wfile.write(data)
            self.wfile.flush()
            self.close_connection = True
        do_GET = do_PUT = do_DELETE = do_PROPFIND = do_REPORT = handle_api

    code = 'BACKEND_STREAM_ERROR' if failure in ('chunk', 'disconnect') else 'BACKEND_INVALID_RESPONSE'
    with serve(Backend) as url:
        async with runtime(tmp_path, 'nextcloud', url) as (client, headers, *_):
            for name, args in (('get_file_tree', {}), ('list_calendars', {}), ('list_tasks', {}),
                               ('read_text_file', {'path': 'Documents/notes.md'})):
                before = len(seen)
                response = await client.post('/mcp', headers=headers, json=call(name, args))
                assert len(seen) > before, (name, response.text)
                assert CANARY not in response.text, (name, failure, response.text)
                assert code in response.text, (name, failure, response.text)


async def test_private_probe_never_waits_for_busy_tool_connections(tmp_path):
    """Four hung WebDAV reads hold every connection of the tools' client (backend_policy: 4); more calls queue
    for it. The private probe opens its own client, so HealthMonitor still reads the backend at once."""
    entered, release = threading.Semaphore(0), threading.Event()
    seen = []

    class Slow(Quiet):
        def handle_api(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            seen.append((self.command, self.path))
            if self.command == 'PROPFIND':
                entered.release()
                release.wait(15)
            try:
                respond(self, *NextcloudFake().handle(self.command, self.path, self.headers, body))
            except (BrokenPipeError, ConnectionResetError):
                pass
        do_GET = do_PROPFIND = handle_api

    with serve(Slow) as url:
        try:
            async with runtime(tmp_path, 'nextcloud', url) as (client, headers, store, manager, child):
                tasks = [asyncio.create_task(rpc(client, '/mcp', dict(headers), call('get_file_tree', {}, id=10 + i)))
                         for i in range(6)]
                try:
                    for _ in range(4):
                        assert await asyncio.to_thread(entered.acquire, True, 10)
                    await asyncio.sleep(.3)
                    assert sum(1 for c, _ in seen if c == 'PROPFIND') == 4  # the pool is full, two calls wait
                    monitor = HealthMonitor(store, manager, child, child_url=manager.endpoint.url)
                    before = len(seen)
                    async with asyncio.timeout(4):
                        await monitor.check()
                    assert monitor.backend == 'reachable'
                    assert seen[before:] == [('GET', OCS_PATH)]
                    assert not any(t.done() for t in tasks)
                finally:
                    release.set()
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                assert all(isinstance(r, dict) and not r.get('isError') for r in results), results
        finally:
            release.set()
