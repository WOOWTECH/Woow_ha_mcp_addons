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
        'NEXTCLOUD_MCP_DISABLED_TOOLS': ','.join(sorted(WRITERS)), 'NEXTCLOUD_MCP_ERROR_CODES': 'true',
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
    """backend_policy.async_client builds the child's client (upstream passes only auth, timeout and headers to it),
    TLS verification cannot be turned off through it, and a broken policy module stops the child before any request."""
    spec = child_spec(state(), tmp_path)
    program = '''
import asyncio, ssl
import backend_policy
from nextcloud_mcp_server.client import NextcloudClient
from nextcloud_mcp_server.settings import load_settings
from nextcloud_mcp_server.settings import Settings
assert 'error_codes' in Settings.model_fields  # the env name child_spec sets must still exist upstream
nc = NextcloudClient(load_settings(verify_tls=False))
assert nc.policy is backend_policy.async_client and nc.code_mode is True
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
    # Local change (client.py): no backend_policy module at all never falls back to an unrestricted client.
    env = {**spec.env, 'PYTHONPATH': str(ROOT / 'apps/nextcloud/vendor')}
    result = subprocess.run(list(spec.argv), env=env, cwd=spec.cwd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2, (result.returncode, result.stderr)
    assert 'backend_policy is required' in result.stderr and 'Uvicorn running' not in result.stderr


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
    base = ''  # this fake's own URL: a followed redirect would come back here

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
            headers['Location'] = f'{self.base}/remote.php/dav/{CANARY}'
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
        ('get_file_tree', {'path': 'x'}, 200, 'BACKEND_HTTP_ERROR status=200'),  # a 2xx that is not 207
        ('get_file_tree', {'path': 'x'}, 'invalid-xml', 'BACKEND_INVALID_RESPONSE'),
        ('get_file_tree', {'path': 'x'}, 'not-multistatus', 'BACKEND_INVALID_RESPONSE'),
        ('list_calendars', {}, 404, 'BACKEND_HTTP_ERROR status=404: This account has no calendar home'),
        ('create_text_file', {'path': 'a/b.md', 'content': 'x'}, 412, 'BACKEND_HTTP_ERROR status=412: \\"a/b.md\\" already exists; read it first'),
        ('create_text_file', {'path': 'a/b.md', 'content': 'x'}, 404, 'BACKEND_HTTP_ERROR status=404: The parent folder of'),
        ('create_text_file', {'path': 'a/b.md', 'content': 'x'}, 423, 'BACKEND_HTTP_ERROR status=423: \\"a/b.md\\" is locked'),
        ('create_text_file', {'path': 'a/b.md', 'content': 'x'}, 507, 'BACKEND_HTTP_ERROR status=507'),
        ('upload_file', {'path': 'a/b.bin', 'content_base64': 'AA=='}, 413, 'BACKEND_HTTP_ERROR status=413'),
    ] + [('get_file_tree', {'path': 'x'}, status, f'BACKEND_HTTP_ERROR status={status}') for status in (301, 302, 307, 308)]
    # Last: an authentication failure (the child may stop contacting the backend after it).
    cases.append(('get_file_tree', {'path': 'x'}, 401, 'BACKEND_HTTP_ERROR status=401: Nextcloud rejected the username or app password.'))
    with serve(Sabre) as url:
        Sabre.base = url
        async with runtime(tmp_path, 'nextcloud', url, json_response=json_response, write_grants=grants) as (client, headers, *_):
            for index, (name, args, status, expected) in enumerate(cases):
                Sabre.mode['status'] = status
                before = len(Sabre.seen)
                response = await client.post('/mcp', headers=headers, json=call(name, args))
                # Exactly the tool's own request (plus the account lookup on the first call): a redirect is never
                # followed, not even to this same server.
                assert response.status_code == 200 and len(Sabre.seen) - before == (2 if index == 0 else 1), (
                    name, status, Sabre.seen[before:])
                assert CANARY not in response.text and CANARY.lower() not in response.text, (name, status, response.text)
                assert '"isError":true' in response.text.replace(' ', ''), (name, status, response.text)
                assert expected in response.text, (name, status, expected, response.text)
                assert len(response.content) < 4096
    assert not any(CANARY in path for _, path in Sabre.seen)


async def test_stale_etag_write_reports_current_etag_and_writes_nothing(tmp_path):
    fake = NextcloudFake()

    class Backend(Quiet):
        def handle_api(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            respond(self, *fake.handle(self.command, self.path, self.headers, body))
        do_GET = do_PUT = do_DELETE = do_PROPFIND = do_REPORT = handle_api

    with serve(Backend) as url:
        async with runtime(tmp_path, 'nextcloud', url, write_grants=sorted(WRITERS)) as (client, headers, *_):
            # Contract A: a backend 412 is BACKEND_HTTP_ERROR status=412; delete's local etag pre-check (after a PROPFIND)
            # sends no DELETE and is ETAG_MISMATCH (never a BACKEND_ code). The current etag is shown after the code.
            for name, args, prefix in (
                    ('update_text_file', {'path': 'Documents/notes.md', 'content': 'x', 'expected_etag': 'stale'},
                     'BACKEND_HTTP_ERROR status=412: '),
                    ('delete_file_checked', {'path': 'Documents/notes.md', 'expected_etag': 'stale'}, 'ETAG_MISMATCH: '),
                    ('upload_file', {'path': 'Documents/notes.md', 'content_base64': 'AA==', 'expected_etag': 'stale'},
                     'BACKEND_HTTP_ERROR status=412: ')):
                reply = await rpc(client, '/mcp', headers, call(name, args))
                text = reply['content'][0]['text']
                assert reply.get('isError') and text.startswith(prefix) and 'current etag one' in text, (name, reply)
            # A 412 whose follow-up PROPFIND shows the file is gone is reported as status=404.
            for name, args in (('update_text_file', {'path': 'Documents/gone.md', 'content': 'x', 'expected_etag': 'e1'}),
                               ('upload_file', {'path': 'Documents/gone.md', 'content_base64': 'AA==', 'expected_etag': 'e1'})):
                reply = await rpc(client, '/mcp', headers, call(name, args))
                text = reply['content'][0]['text']
                assert reply.get('isError') and text.startswith('BACKEND_HTTP_ERROR status=404: ') and 'does not exist' in text, reply
            for name, args in (('create_text_file', {'path': 'Documents/notes.md', 'content': 'x'}),
                               # upload_file without an etag only creates: If-None-Match: * (the fake answers 428 to
                               # a PUT without any precondition, so a dropped header cannot overwrite silently).
                               ('upload_file', {'path': 'Documents/notes.md', 'content_base64': 'AA=='})):
                reply = await rpc(client, '/mcp', headers, call(name, args))
                text = reply['content'][0]['text']
                assert reply.get('isError') and text.startswith('BACKEND_HTTP_ERROR status=412: ') and 'already exists' in text, (name, reply)
            reply = await rpc(client, '/mcp', headers, call('delete_file_checked', {'path': 'Documents', 'expected_etag': 'docs'}))
            assert reply.get('isError') and reply['content'][0]['text'].startswith('"Documents" is a folder')  # tool refusal: uncoded
            assert fake.mutations == [] and fake.files['Documents/notes.md'][1] == 'one'
            text = payload(await rpc(client, '/mcp', headers, call('read_text_file', {'path': 'Documents/notes.md'})))
            assert text['etag'] == 'one' and text['content'].startswith('# Notes')
            assert payload(await rpc(client, '/mcp', headers, call('get_file_content', {'path': 'Documents/notes.md'})),
                           plain=True)['text'] == text['content']


# (tool, arguments, the request of that tool that breaks): every earlier request of the call answers normally, so the
# failure reaches the tool's own body handling (file GET, CalDAV REPORT, writer PUT/DELETE, PROPFIND listings).
LATE_CASES = [
    ('get_file_tree', {}, 'PROPFIND'), ('list_calendars', {}, 'PROPFIND'),
    ('read_text_file', {'path': 'Documents/notes.md'}, 'GET'), ('get_file_content', {'path': 'Documents/notes.md'}, 'GET'),
    ('list_tasks', {}, 'REPORT'),
    ('create_text_file', {'path': 'Owned/new.md', 'content': 'x'}, 'PUT'),
    ('update_text_file', {'path': 'Documents/notes.md', 'content': 'x', 'expected_etag': 'one'}, 'PUT'),
    ('upload_file', {'path': 'Owned/new.bin', 'content_base64': 'AA=='}, 'PUT'),
    ('delete_file_checked', {'path': 'Documents/old.txt', 'expected_etag': 'old'}, 'DELETE'),
]


@pytest.mark.parametrize('failure', ['chunk', 'disconnect', 'gzip', 'invalid-xml'])
async def test_late_body_failures_of_each_tools_own_request_are_public_codes(tmp_path, failure):
    """The account lookup and every earlier request succeed; then the tool's own request answers its expected
    success status with a broken body: only public codes, never the body (which echoes the app password)."""
    broken = {'command': None}
    seen = []

    class Backend(Quiet):
        def handle_api(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            # A fresh fake per request: the real status for this request, from an unchanged file set.
            status, headers, data = NextcloudFake(password=CANARY).handle(self.command, self.path, self.headers, body)
            if self.path == OCS_PATH or self.command != broken['command']:
                return respond(self, status, headers, data)
            seen.append((self.command, self.path))
            echoed = __import__('base64').b64decode(self.headers['Authorization'].split()[1]).decode().split(':', 1)[1]
            assert echoed == CANARY
            status = 200 if status == 204 else status  # a 204 cannot carry the broken body
            if failure == 'invalid-xml':
                return respond(self, status, {'Content-Type': 'application/xml'}, b'<' + echoed.encode())
            self.send_response(status)
            if failure == 'chunk':
                self.send_header('Transfer-Encoding', 'chunked')
                data = echoed.encode() + b'\r\n'
            elif failure == 'disconnect':
                self.send_header('Content-Length', '10000')
                data = echoed.encode()
            else:
                data = echoed.encode()
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Content-Encoding', 'gzip')
            self.end_headers()
            self.wfile.write(data)
            self.wfile.flush()
            self.close_connection = True
        do_GET = do_PUT = do_DELETE = do_PROPFIND = do_REPORT = handle_api

    code = 'BACKEND_STREAM_ERROR' if failure in ('chunk', 'disconnect') else 'BACKEND_INVALID_RESPONSE'
    with serve(Backend) as url:
        async with runtime(tmp_path, 'nextcloud', url, canary=CANARY, write_grants=sorted(WRITERS)) as (client, headers, *_):
            for name, args, command in LATE_CASES:
                if failure == 'invalid-xml' and command in ('GET', 'PUT', 'DELETE'):
                    continue  # bodies the child does not parse: a valid read of any bytes is not an error
                broken['command'] = command
                before = len(seen)
                response = await client.post('/mcp', headers=headers, json=call(name, args))
                assert len(seen) == before + 1 and seen[-1][0] == command, (name, seen[before:])
                assert CANARY not in response.text, (name, failure, response.text)
                assert code in response.text, (name, failure, response.text)


async def test_listing_outside_the_home_folder_is_refused_without_backend_paths(tmp_path):
    """tools.py: a multistatus whose hrefs are all outside the account's files home is refused with a public code;
    neither the home path (it contains the backend's user id) nor the foreign hrefs reach the client."""
    class Backend(Quiet):
        def handle_api(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if self.path == OCS_PATH:
                return respond(self, 200, {'Content-Type': 'application/json'},
                               b'{"ocs": {"data": {"id": "%s"}}}' % CANARY.encode())
            foreign = [(f'/remote.php/dav/files/{CANARY}-other/{n}', '<d:resourcetype/>') for n in ('a', 'b')]
            respond(self, 207, {'Content-Type': 'application/xml'}, nextcloud_fixtures.multistatus(foreign))
        do_PROPFIND = do_GET = handle_api

    with serve(Backend) as url:
        async with runtime(tmp_path, 'nextcloud', url) as (client, headers, *_):
            response = await client.post('/mcp', headers=headers, json=call('get_file_tree', {}))
            assert 'BACKEND_INVALID_RESPONSE' in response.text and 'outside the account' in response.text
            assert CANARY not in response.text and '/remote.php/dav/files' not in response.text, response.text


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


URL_CASES = ['https://cloud.example.test', 'https://cloud.example.test/', 'https://cloud.example.test/nextcloud',
             'http://192.0.2.10:8080/nc', 'https://cloud.example.test/a/./b', 'https://cloud.example.test/a/../b',
             'https://cloud.example.test/..', 'https://cloud.example.test/next%25cloud', 'https://cloud.example.test/a%2e%2e/b',
             'https://cloud.example.test/%2e%2e', 'https://cloud.example.test/a%5cb', 'https://metadata',
             'https://METADATA.google.internal./x', 'http://instance-data', 'https://cloud.example.test/?',
             'https://cloud.example.test/#', 'https://@cloud.example.test', 'https://cloud.example.test/a%20b',
             'https://雲端.example.tw', 'https://cloud.台灣/nc', 'https://xn--suzq78c.example.tw']
CREDENTIALS = [('tester', 'DUMMY'), ('test user', 'DUMMY pass'), ('   ', 'DUMMY'), (' tester', 'DUMMY'), ('tester ', 'DUMMY'),
               ('tester', '   '), ('tester', ' DUMMY'), ('tester', 'DUMMY ')]


def test_every_saved_connection_is_accepted_by_backend_policy_and_child_settings(tmp_path):
    """What the GUI saves (NextcloudConnection) must be what backend_policy.Destination and the child's Settings
    accept: a URL either is refused when saved, or works at run time; blank or padded credentials are refused."""
    from pydantic import ValidationError
    from mcp_admin_core.products import NextcloudConnection
    spec = child_spec(state(), tmp_path)  # only argv[0] and PYTHONPATH are used
    cases = [(url, user, password) for url in URL_CASES for user, password in CREDENTIALS[:1]]
    cases += [(URL_CASES[0], user, password) for user, password in CREDENTIALS[1:]]
    program = '''
import json, sys
import httpx
from backend_policy import BackendDenied, Destination
from nextcloud_mcp_server.settings import SettingsError, load_settings
result = []
for url, user, password in json.loads(sys.stdin.read()):
    try:  # the URL a real request uses, checked the way the transport checks it
        Destination(url).check_url(httpx.URL(url.rstrip('/') + '/ocs/v2.php/cloud/user')); policy = True
    except (BackendDenied, ValueError, httpx.InvalidURL):
        policy = False
    try:
        load_settings(base_url=url, username=user, app_password=password, _env_file=None); settings = True
    except SettingsError:
        settings = False
    result.append([policy, settings])
print(json.dumps(result))
'''
    run = subprocess.run([spec.argv[0], '-c', program], input=json.dumps(cases), env={
        'PATH': '/usr/bin:/bin', 'PYTHONPATH': spec.env['PYTHONPATH'], 'PYTHONDONTWRITEBYTECODE': '1'},
        capture_output=True, text=True, timeout=30, cwd='/')
    assert run.returncode == 0, run.stderr
    accepted_somewhere = False
    for (url, user, password), (policy, settings) in zip(cases, json.loads(run.stdout)):
        try:
            NextcloudConnection.model_validate({'url': url, 'username': user, 'app_password': password})
            saved = True
        except ValidationError:
            saved = False
        if saved:
            accepted_somewhere = True
            assert policy and settings, (url, user, policy, settings)
        if not policy or not settings:
            assert not saved, (url, user)
    assert accepted_somewhere
    for bad in ('https://cloud.example.test/a/../b', 'https://cloud.example.test/next%25cloud', 'https://metadata',
                'https://雲端.example.tw'):
        with pytest.raises(ValidationError):
            NextcloudConnection.model_validate({'url': bad, 'username': 'tester', 'app_password': 'DUMMY'})
    NextcloudConnection.model_validate({'url': 'https://xn--suzq78c.example.tw', 'username': 'tester', 'app_password': 'DUMMY'})
    # R2 #7: blank or padded credentials are refused by the saved model itself, not only by agreement with the child.
    for user, password in ((' tester', 'DUMMY'), ('tester ', 'DUMMY'), ('tester', ' DUMMY'), ('tester', 'DUMMY '),
                           ('   ', 'DUMMY'), ('tester', '   ')):
        with pytest.raises(ValidationError):
            NextcloudConnection.model_validate({'url': 'https://cloud.example.test', 'username': user, 'app_password': password})


async def test_auth_failure_latches_tools_and_probe_until_restart(tmp_path):
    """R1 #1: after a 401 the child sends nothing more with these credentials (tools and the private health probe);
    readiness reports the backend unreachable; a restarted child (e.g. after new credentials) contacts it again."""
    seen = []
    status = {'value': 401}

    class Backend(Quiet):
        def handle_api(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            seen.append((self.command, self.path))
            if self.path == OCS_PATH and status['value'] == 200:
                return respond(self, *NextcloudFake().handle('GET', self.path, self.headers, b''))
            respond(self, status['value'], {'Content-Type': 'application/json'}, b'{"detail": "%s"}' % CANARY.encode())
        do_GET = do_PROPFIND = do_REPORT = handle_api

    with serve(Backend) as url:
        async with runtime(tmp_path, 'nextcloud', url) as (client, headers, store, manager, child):
            response = await client.post('/mcp', headers=headers, json=call('get_file_tree', {}))
            assert 'BACKEND_HTTP_ERROR status=401' in response.text and CANARY not in response.text
            assert len(seen) == 1
            monitor = HealthMonitor(store, manager, child, child_url=manager.endpoint.url)
            for name, args in (('list_calendars', {}), ('read_text_file', {'path': 'Documents/notes.md'}), ('get_file_tree', {})):
                response = await client.post('/mcp', headers=headers, json=call(name, args))
                assert 'BACKEND_HTTP_ERROR status=401' in response.text, response.text
                await monitor.check()
                assert monitor.backend == 'unreachable'
            assert len(seen) == 1, seen  # nothing after the first failed login
            status['value'] = 200
            await monitor.check()
            assert monitor.backend == 'unreachable' and len(seen) == 1  # fixed backend, same credentials: still latched
            await manager.stop()
            await manager.start()  # what saving the backend settings does (backend_changed restarts the child)
            async with asyncio.timeout(20):
                while True:
                    await monitor.check()
                    if monitor.backend == 'reachable':
                        break
                    await asyncio.sleep(.2)
            assert seen[1:] and all(event == ('GET', OCS_PATH) for event in seen[1:])


def test_throttle_latch_expires_and_errors_keep_public_codes(tmp_path):
    """R1 #1: a 429 latches the credentials until Retry-After (or 5 min when the gateway transport hides the
    headers), then requests resume; a different password is not latched; every message starts with its code."""
    spec = child_spec(state(), tmp_path)
    program = '''
import asyncio, httpx
import nextcloud_mcp_server.client as client_module
from nextcloud_mcp_server.client import NextcloudClient
from nextcloud_mcp_server.settings import load_settings
now = [1000.0]
client_module._clock = lambda: now[0]
calls = []
def answer(request):
    calls.append(request.url.path)
    return httpx.Response(429, headers={'Retry-After': '2'})
async def main():
    settings = load_settings(error_codes='true')  # no backend_policy here: code mode forced on
    nc = NextcloudClient(settings, transport=httpx.MockTransport(answer), policy=None)
    for _ in range(3):
        try:
            await nc.probe()
        except Exception as exc:
            assert str(exc).startswith('BACKEND_HTTP_ERROR status=429: '), str(exc)
    assert len(calls) == 1, calls
    other = NextcloudClient(load_settings(app_password='DUMMY-other', error_codes='true'),
                            transport=httpx.MockTransport(answer), policy=None)
    try:
        await other.probe()
    except Exception:
        pass
    assert len(calls) == 2, calls  # other credentials: their own latch
    now[0] += 2.5
    try:
        await nc.probe()
    except Exception:
        pass
    assert len(calls) == 3, calls  # Retry-After passed: one more attempt
    # Through backend_policy the 429 arrives without headers: the default 5 minutes apply.
    client_module.reset_auth_latch()
    assert client_module.retry_after_seconds(None) == 300.0
asyncio.run(main())
'''
    result = subprocess.run([spec.argv[0], '-c', program], env=spec.env, cwd=spec.cwd, capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_policy_denied_destination_is_a_public_code_for_tools_and_probe(tmp_path):
    """R1 #3: backend_policy refusing the base URL while the client is built (metadata host, '%'/'..' path) gives
    BACKEND_DESTINATION_DENIED for a tool request and for the private probe, without any connection attempt."""
    spec = child_spec(state(), tmp_path)
    program = '''
import asyncio, socket
from nextcloud_mcp_server.client import NextcloudClient
from nextcloud_mcp_server.server import create_server
from nextcloud_mcp_server.settings import load_settings
def forbidden(*args, **kwargs):
    raise AssertionError('no DNS or connection for a refused destination')
socket.getaddrinfo = forbidden
socket.socket.connect = forbidden
async def main():
    for url in ('https://metadata', 'https://cloud.example.test/next%25cloud', 'https://cloud.example.test/a/../b'):
        settings = load_settings(base_url=url)
        nc = NextcloudClient(settings)
        for call in (nc.user_id, nc.probe):
            try:
                await call()
            except Exception as exc:
                # Inside the client the code is attached; tools and probe() render it as the message prefix.
                assert str(nc.render(exc)).startswith('BACKEND_DESTINATION_DENIED: '), (url, str(exc))
            else:
                raise AssertionError(url)
        server = create_server(settings)
        try:
            await server.call_tool('woow_backend_probe', {})
        except Exception as exc:
            assert 'BACKEND_DESTINATION_DENIED' in str(exc), (url, str(exc))
        else:
            raise AssertionError(url)
asyncio.run(main())
'''
    result = subprocess.run([spec.argv[0], '-c', program], env=spec.env, cwd=spec.cwd, capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr


async def test_tree_skips_policy_refused_sub_folder_and_marks_truncated(tmp_path):
    """R1 #5: a sub-folder whose name has '%' is refused by backend_policy; get_file_tree (depth >= 2) skips it,
    sets truncated and still lists everything else; nothing is sent for the refused folder."""
    files = nextcloud_fixtures.initial_files()
    files['100% done'] = (None, 'pct')
    files['100% done/inside.md'] = (b'x', 'in')
    fake = NextcloudFake(files)
    seen = []

    class Backend(Quiet):
        def handle_api(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            seen.append((self.command, self.path))
            respond(self, *fake.handle(self.command, self.path, self.headers, body))
        do_GET = do_PROPFIND = handle_api

    with serve(Backend) as url:
        async with runtime(tmp_path, 'nextcloud', url) as (client, headers, *_):
            shallow = payload(await rpc(client, '/mcp', headers, call('get_file_tree', {'depth': 1})))
            assert '100% done' in {e['path'] for e in shallow['entries']} and shallow['truncated'] is False
            deep = payload(await rpc(client, '/mcp', headers, call('get_file_tree', {'depth': 2})))
            paths = {e['path'] for e in deep['entries']}
            assert deep['truncated'] is True
            assert {'Documents/notes.md', 'Documents/old.txt', '100% done'} <= paths and '100% done/inside.md' not in paths
            assert not any('100' in path for _, path in seen)
            reply = await rpc(client, '/mcp', headers, call('read_text_file', {'path': '100% done/inside.md'}))
            assert reply.get('isError') and 'BACKEND_DESTINATION_DENIED' in json.dumps(reply)


def _broken_body(handler, failure, echoed, status=200):
    """Answer `status` with a body that breaks the way `failure` says; the body echoes the app password."""
    if failure == 'json':
        return respond(handler, status, {'Content-Type': 'application/json'}, b'{"' + echoed.encode())
    handler.send_response(status)
    if failure == 'chunk':
        handler.send_header('Transfer-Encoding', 'chunked')
        data = echoed.encode() + b'\r\n'
    elif failure == 'disconnect':
        handler.send_header('Content-Length', '10000')
        data = echoed.encode()
    else:
        data = echoed.encode()
        handler.send_header('Content-Length', str(len(data)))
        handler.send_header('Content-Encoding', 'gzip')
    handler.end_headers()
    handler.wfile.write(data)
    handler.wfile.flush()
    handler.close_connection = True


def _password(handler):
    return __import__('base64').b64decode(handler.headers['Authorization'].split()[1]).decode().split(':', 1)[1]


@pytest.mark.parametrize('failure', ['chunk', 'disconnect', 'gzip', 'json'])
async def test_account_lookup_body_failures_before_the_first_lookup_are_public_codes(tmp_path, failure):
    """R2 #6: the account lookup (OCS cloud/user, never cached until it succeeds) answers 200 with a broken body that
    echoes the app password: every call and the private probe report a public code, never the body."""
    seen = []

    class Backend(Quiet):
        def do_GET(self):
            seen.append(self.path)
            assert self.path == OCS_PATH
            _broken_body(self, failure, _password(self))

    code = 'BACKEND_STREAM_ERROR' if failure in ('chunk', 'disconnect') else 'BACKEND_INVALID_RESPONSE'
    with serve(Backend) as url:
        async with runtime(tmp_path, 'nextcloud', url, canary=CANARY) as (client, headers, store, manager, child):
            for name, args in (('get_file_tree', {}), ('list_calendars', {}), ('read_text_file', {'path': 'a.md'})):
                before = len(seen)
                response = await client.post('/mcp', headers=headers, json=call(name, args))
                assert len(seen) == before + 1, (name, seen[before:])
                assert CANARY not in response.text and code in response.text, (name, failure, response.text)
            raw = await rpc(child, manager.endpoint.url, headers, call(ODOO_HEALTH_PROBE, {}, id=9))
            assert raw.get('isError') and CANARY not in json.dumps(raw) and code in json.dumps(raw), raw


@pytest.mark.parametrize('failure', ['chunk', 'gzip', 'invalid-xml'])
async def test_write_without_etag_header_and_broken_follow_up_lookup(tmp_path, failure):
    """R2 #6: the PUT succeeds without an ETag header, so the child asks for the etag with a PROPFIND; that answer is
    broken (and echoes the app password): the write still reports success with etag null, and nothing leaks."""
    fake = NextcloudFake(password=CANARY)
    seen = []

    class Backend(Quiet):
        def handle_api(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            seen.append((self.command, self.path))
            status, headers, data = fake.handle(self.command, self.path, self.headers, body)
            if self.command == 'PUT':
                headers = {k: v for k, v in headers.items() if k.lower() != 'etag'}
                return respond(self, status, headers, data)
            if self.command == 'PROPFIND' and self.headers.get('Depth') == '0' and 'Owned/' in self.path:
                if failure == 'invalid-xml':
                    return respond(self, 207, {'Content-Type': 'application/xml'}, b'<' + _password(self).encode())
                return _broken_body(self, failure, _password(self), 207)
            respond(self, status, headers, data)
        do_GET = do_PUT = do_PROPFIND = handle_api

    with serve(Backend) as url:
        async with runtime(tmp_path, 'nextcloud', url, canary=CANARY, write_grants=sorted(WRITERS)) as (client, headers, *_):
            for name, args in (('create_text_file', {'path': 'Owned/new.md', 'content': 'x'}),
                               ('upload_file', {'path': 'Owned/new.bin', 'content_base64': 'AA=='})):
                reply = await rpc(client, '/mcp', headers, call(name, args))
                assert CANARY not in json.dumps(reply), reply
                result = payload(reply)
                assert result['status'] == 'created' and result['etag'] is None, result
            assert [c for c, p in seen if 'Owned/' in p] == ['PUT', 'PROPFIND', 'PUT', 'PROPFIND']


async def test_slow_401_still_latches_after_health_check_timeouts(tmp_path):
    """R2 observation: a 401 that arrives after HealthMonitor's 5 s probe timeout (Nextcloud may delay failed logins)
    still latches: at most two failed logins, then none (FastMCP 3.4.5 lets the probe finish after the session
    ends; an upgrade that cancels it would fail here)."""
    import time
    seen = []

    class Slow(Quiet):
        def do_GET(self):
            seen.append(time.monotonic())
            time.sleep(6.5)
            try:
                respond(self, 401, {'Content-Type': 'application/json'}, b'{}')
            except (BrokenPipeError, ConnectionResetError):
                pass

    with serve(Slow) as url:
        async with runtime(tmp_path, 'nextcloud', url) as (client, headers, store, manager, child):
            monitor = HealthMonitor(store, manager, child, child_url=manager.endpoint.url)
            for _ in range(2):
                await monitor.check()
                assert monitor.backend == 'unreachable'
            assert len(seen) <= 2
            await asyncio.sleep(7.5)  # every pending login has answered 401 by now
            before = len(seen)
            for _ in range(2):
                await monitor.check()
                assert monitor.backend == 'unreachable'
            response = await client.post('/mcp', headers=headers, json=call('get_file_tree', {}))
            assert 'BACKEND_HTTP_ERROR status=401' in response.text
            assert len(seen) == before <= 2, len(seen)


async def test_too_large_listing_is_invalid_response(tmp_path):
    """Contract A: a listing over the child's 8 MiB cap is BACKEND_INVALID_RESPONSE; its body is never shown."""
    class Backend(Quiet):
        def handle_api(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if self.path == OCS_PATH:
                return respond(self, *NextcloudFake().handle('GET', self.path, self.headers, b''))
            entry = '<d:response><d:href>/remote.php/dav/files/tester/%s</d:href></d:response>' % CANARY
            data = ('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">' + entry * (9 * 1024 * 1024 // len(entry))
                    + '</d:multistatus>').encode()
            respond(self, 207, {'Content-Type': 'application/xml'}, data)
        do_GET = do_PROPFIND = handle_api

    with serve(Backend) as url:
        async with runtime(tmp_path, 'nextcloud', url) as (client, headers, *_):
            reply = await rpc(client, '/mcp', headers, call('get_file_tree', {}))
            text = reply['content'][0]['text']
            assert reply.get('isError') and text.startswith('BACKEND_INVALID_RESPONSE: ') and 'too large' in text, text
            assert CANARY not in json.dumps(reply)


async def test_list_tasks_skips_policy_refused_calendars(tmp_path):
    """A calendar whose id contains '%' is refused by backend_policy: list_tasks() skips it and reports
    skipped_calendars; naming it explicitly is BACKEND_DESTINATION_DENIED; nothing is sent for it."""
    seen = []
    calendars = nextcloud_fixtures.CALENDARS

    class Backend(Quiet):
        def handle_api(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            seen.append((self.command, self.path))
            if self.command == 'PROPFIND' and self.path == calendars:
                todo = ('<d:resourcetype><d:collection/><c:calendar/></d:resourcetype><c:supported-calendar-component-set>'
                        '<c:comp name="VTODO"/></c:supported-calendar-component-set>')
                data = nextcloud_fixtures.multistatus([
                    (calendars, '<d:resourcetype><d:collection/></d:resourcetype>'),
                    (calendars + 'personal/', '<d:displayname>Personal</d:displayname>' + todo),
                    (calendars + 'a%25b/', '<d:displayname>Shared</d:displayname>' + todo)])
                return respond(self, 207, {'Content-Type': 'application/xml'}, data)
            respond(self, *NextcloudFake().handle(self.command, self.path, self.headers, body))
        do_GET = do_PROPFIND = do_REPORT = handle_api

    with serve(Backend) as url:
        async with runtime(tmp_path, 'nextcloud', url) as (client, headers, *_):
            listed = payload(await rpc(client, '/mcp', headers, call('list_calendars', {})))
            assert sorted(c['id'] for c in listed['calendars']) == ['a%b', 'personal']
            tasks = payload(await rpc(client, '/mcp', headers, call('list_tasks', {})))
            assert [t['uid'] for t in tasks['tasks']] == ['owned-task'] and tasks['skipped_calendars'] == 1, tasks
            reply = await rpc(client, '/mcp', headers, call('list_tasks', {'calendar': 'a%b'}))
            assert reply.get('isError') and reply['content'][0]['text'].startswith('BACKEND_DESTINATION_DENIED: ')
            assert not any('a%25b' in path or 'a%b' in path for command, path in seen if command == 'REPORT')
