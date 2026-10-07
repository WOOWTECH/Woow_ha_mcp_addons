"""Executed ONLY in a disposable network-none image with tmpfs /data.

Actual packaged entrypoint and real child; owned loopback mock backend. Fixture
state edits occur ONLY while stopped. No production administrator trust bypass.
Do not run this against a real /data; host harness always supplies an empty tmpfs.
"""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import xmlrpc.client

import httpx
from denial_probe import assert_denials, WRITE_CASES
from mcp_admin_core.health import protocol_reply
from mcp_admin_core.products import ProductStore, PROBES, TOOLS, probe_success

APP = sys.argv[1]
ROOT = Path('/opt/woow')
DATA = Path('/data/mcp')
ENDPOINT = 'http://127.0.0.1:8081/mcp'
CALLS = []
OFFLINE = threading.Event()


class Backend(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, data, kind='application/json'):
        if not isinstance(data, bytes):
            data = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        CALLS.append(('GET', self.path))
        if OFFLINE.is_set():
            self.send_error(503)
            return
        values = {'/v1/capabilities': {'models': []}, '/api/health': {'status': 'ok'},
                  '/api/v5/nodes': [{'node': 'fake@local', 'version': '5.fake'}],
                  '/v1/models': {'data': [{'id': 'fake-model'}]},
                  # Nextcloud OCS: the account answer the child (and its private health probe) reads first.
                  '/ocs/v2.php/cloud/user?format=json': {'ocs': {'meta': {'status': 'ok', 'statuscode': 200},
                                                                 'data': {'id': 'tester'}}}}
        if self.path.startswith('/api/v1/workflows'):
            self.respond({'data': [], 'nextCursor': None})
        elif self.path in values:
            self.respond(values[self.path])
        else:
            self.send_error(404)

    def do_PROPFIND(self):
        # Nextcloud WebDAV: the home folder with one file (get_file_tree, the representative read).
        CALLS.append(('PROPFIND', self.path))
        self.rfile.read(int(self.headers.get('Content-Length', 0)))
        if OFFLINE.is_set():
            self.send_error(503)
            return
        if self.path != '/remote.php/dav/files/tester/':
            self.send_error(404)
            return
        prop = ('<d:response><d:href>/remote.php/dav/files/tester/%s</d:href><d:propstat><d:prop>%s</d:prop>'
                '<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>')
        data = ('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'
                + prop % ('', '<d:resourcetype><d:collection/></d:resourcetype><d:getetag>"home"</d:getetag>')
                + prop % ('notes.md', '<d:resourcetype/><d:getcontentlength>5</d:getcontentlength>'
                                      '<d:getetag>"one"</d:getetag><d:getcontenttype>text/markdown</d:getcontenttype>')
                + '</d:multistatus>').encode()
        self.send_response(207)
        self.send_header('Content-Type', 'application/xml; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_DELETE(self):
        # Any dispatch mutation may write ONLY to this disposable fake.
        CALLS.append(('DELETE', self.path))
        self.respond({'success': True})

    def do_POST(self):
        CALLS.append(('POST', self.path))
        if OFFLINE.is_set():
            self.send_error(503)
            return
        assert self.path.startswith('/xmlrpc/2/')
        params, method = xmlrpc.client.loads(self.rfile.read(int(self.headers['Content-Length'])))
        CALLS.append(('XMLRPC', method))
        if method == 'version':
            value = {'server_version': '18.0', 'server_version_info': [18, 0, 0, 'final', 0]}
        elif method == 'authenticate':
            assert params[:3] == ('test', 'tester', 'DUMMY')
            value = 7
        elif method == 'execute_kw':
            assert params[:3] == ('test', 7, 'DUMMY')
            assert params[3] == 'ir.model' and params[4] in ('search', 'read', 'search_read')
            value = [1] if params[4] == 'search' else [{'id': 1, 'model': 'res.partner', 'name': 'Contact'}]
        else:
            raise AssertionError('unreviewed mock operation')
        self.respond(xmlrpc.client.dumps((value,), methodresponse=True, allow_none=True).encode(), 'text/xml')


def start():
    return subprocess.Popen(['/usr/local/bin/python', str(ROOT / 'packaging/entrypoint.py'), APP],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def children(process):
    return Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()


def stop(process):
    owned = children(process) if process.poll() is None else []
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(12)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise AssertionError('runtime shutdown deadline exceeded')
    assert process.returncode == 0
    assert all(not Path('/proc/' + pid).exists() for pid in owned), 'orphan child'


async def ready_listener(client, process):
    async with asyncio.timeout(40):
        while True:
            assert process.poll() is None, 'packaged entrypoint exited'
            try:
                result = await client.get('http://127.0.0.1:8081/health/ready')
                if result.status_code in (200, 503):
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(.2)
    status = Path(f'/proc/{process.pid}/status').read_text()
    assert 'Uid:\t10001\t10001\t10001\t10001' in status
    assert 'Gid:\t10001\t10001\t10001\t10001' in status
    assert 'NoNewPrivs:\t1' in status
    assert 'CapEff:\t0000000000000000' in status
    assert (DATA.stat().st_uid, DATA.stat().st_mode & 0o777) == (10001, 0o700)
    assert ((DATA / 'state.json').stat().st_uid, (DATA / 'state.json').stat().st_mode & 0o777) == (10001, 0o600)


def fixture_update(**updates):
    # Fixture-only ownership restoration after an atomic root-owned test update.
    store = ProductStore(DATA, APP)
    state = store.update(**updates) if updates else store.load()
    store.close()
    for name in ('state.json', '.writer.lock'):
        os.chown(DATA / name, 10001, 10001)
    return state


async def rpc(client, headers, message):
    async with client.stream('POST', ENDPOINT, headers=headers, json=message) as response:
        if response.headers.get('mcp-session-id'):
            headers['Mcp-Session-Id'] = response.headers['mcp-session-id']
        if 'id' not in message:
            assert response.status_code in (200, 202, 204)
            return None
        return await protocol_reply(response, message['id'])


async def run():
    assert APP in ('odoo', 'odoo-manage', 'n8n', 'hermes', 'opendesign', 'emqx', 'litellm', 'nextcloud')
    assert {p.name for p in (ROOT / 'apps').iterdir()} == {APP, 'runtime'}, 'sibling application shipped'
    assert not DATA.exists(), 'refuse non-disposable state'
    assert not (ROOT / '.git').exists()
    from mcp_admin_core.ui import UI_ROOT
    assert UI_ROOT == ROOT / 'packages/mcp-admin-ui/dist'
    assert '__MCP_UI_BASE__' in (UI_ROOT / 'index.html').read_text()
    assert list((UI_ROOT / 'assets').rglob('*.woff2'))
    assert (UI_ROOT / 'licenses').is_dir()
    assert not (UI_ROOT.parent / 'fixtures').exists()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Backend)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    process = None
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
            process = start()
            await ready_listener(client, process)
            assert (await client.get('http://127.0.0.1:8081/health/ready')).status_code == 503
            assert not CALLS, 'unconfigured backend contacted'
            if APP != 'n8n':
                assert not children(process), 'unconfigured child launched'
            stop(process)
            process = None
            if APP == 'n8n':
                state = fixture_update(backend_url=url, backend_key='DUMMY')
                from n8n_adapter import TOOLS as public_tools
                name, args = 'n8n_list_workflows', {'limit': 1}
            else:
                connections = {
                    'odoo': dict(url=url, database='test', username='tester', password='DUMMY'),
                    'odoo-manage': dict(url=url, database='test', username='tester', api_key='DUMMY'),
                    'hermes': dict(gateway_url=url, gateway_api_key='DUMMY'),
                    'opendesign': dict(url=url), 'emqx': dict(url=url, api_key='DUMMY', api_secret='DUMMY'),
                    'litellm': dict(url=url, master_key='DUMMY'),
                    'nextcloud': dict(url=url, username='tester', app_password='DUMMY')}
                state = fixture_update(connection=connections[APP])
                public_tools = TOOLS[APP]
                name, args = PROBES[APP]
            # Valid complete v2 backup fixture: actual executable migrates it
            # under writer ownership, preserving settings and denying new writes.
            legacy = state.model_dump()
            legacy.pop('enabled_write_tools')
            legacy['schema_version'] = 2
            (DATA / 'state.json').write_text(json.dumps(legacy))
            process = start()
            await ready_listener(client, process)
            migrated = json.loads((DATA / 'state.json').read_text())
            assert migrated['schema_version'] == 3 and migrated['enabled_write_tools'] == []
            assert migrated == state.model_dump()
            name_write, valid_write = WRITE_CASES[APP]
            public_tools[name_write].arguments.model_validate(valid_write)
            headers = {'Authorization': 'Bearer ' + state.token, 'Accept': 'application/json, text/event-stream'}
            initialize = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'container-mock', 'version': '1'}}}
            async with asyncio.timeout(40):
                while True:
                    try:
                        result = await rpc(client, headers, initialize)
                        break
                    except (httpx.HTTPError, ValueError):
                        assert process.poll() is None
                        await asyncio.sleep(.25)
            assert result['capabilities'] == {'tools': {}}
            headers['MCP-Protocol-Version'] = result['protocolVersion']
            await rpc(client, headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            result = await rpc(client, headers, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
            assert {t['name'] for t in result['tools']} == {n for n, t in public_tools.items() if not t.write}
            message = {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': name, 'arguments': args}}
            result = await rpc(client, headers, message)
            assert not result.get('isError') and CALLS
            texts = [json.loads(t['text']) for t in result['content'] if t['type'] == 'text']
            assert any(t.get('success') is True if APP == 'n8n' else probe_success(APP, t) for t in texts)
            for auth in ({}, {'Authorization': 'Bearer wrong'}):
                assert (await client.post(ENDPOINT, headers=auth, json=initialize)).status_code == 401
            for method in ('resources/list', 'prompts/list', 'tasks/get'):
                assert (await client.post(ENDPOINT, headers=headers, json={'jsonrpc': '2.0', 'id': 4, 'method': method})).status_code == 403
            await assert_denials(client, ENDPOINT, headers, APP, lambda: len(CALLS))
            # Missing identity and forged role/peer headers must still deny,
            # including after the separately implemented real verifier integrates.
            # Loopback is NOT trusted Ingress; this is no positive role test.
            for fake_identity in ({}, {'X-Remote-User-Id': 'admin',
                                      'X-Forwarded-For': '172.30.32.2',
                                      'X-Remote-User-Admin': 'true'}):
                assert (await client.get('http://127.0.0.1:8099/api/bootstrap',
                                         headers=fake_identity)).status_code == 403
            # Child 3000 must bind only IPv4 loopback (0BB8 is 3000).
            rows = Path('/proc/net/tcp').read_text().splitlines()[1:]
            listeners = [row.split()[1] for row in rows if row.split()[3] == '0A' and row.split()[1].endswith(':0BB8')]
            assert listeners == ['0100007F:0BB8']
            async with asyncio.timeout(22):
                while (await client.get('http://127.0.0.1:8081/health/ready')).status_code != 200:
                    await asyncio.sleep(.25)
            pids = children(process)
            assert len(pids) == 1
            OFFLINE.set()
            async with asyncio.timeout(22):
                while (await client.get('http://127.0.0.1:8081/health/ready')).status_code != 503:
                    await asyncio.sleep(.25)
            assert children(process) == pids and process.poll() is None, 'backend-driven restart'
            assert await rpc(client, headers, {'jsonrpc': '2.0', 'id': 6, 'method': 'ping'}) == {}
            stop(process)
            process = None
            persisted = fixture_update()
            assert persisted == state, 'restart rewrote settings'
            import secrets
            # Persist one exact grant (still never call a writer here), then
            # verify restart does not lose it. Manage requires preexisting module
            # mode; keep it read-only here rather than invent backend ACL support.
            grants = public_tools[name_write].grants(name_write) if APP != 'odoo-manage' else []
            fixture_update(token=secrets.token_urlsafe(32), disabled=[name, name_write], enabled_write_tools=grants)
            OFFLINE.clear()
            process = start()
            await ready_listener(client, process)
            assert (await client.post(ENDPOINT, headers=headers, json=initialize)).status_code == 401
            # Read only this disposable fixture, never log tokens/state.
            restored = json.loads((DATA / 'state.json').read_text())
            assert restored['schema_version'] == 3 and restored['enabled_write_tools'] == grants
            token = restored['token']
            assert (await client.post(ENDPOINT, headers={'Authorization': 'Bearer ' + token}, json=message)).status_code == 403
            stop(process)
            process = None
        print('PASS: actual packaged runtime + owned mock; no HA/backend E2E claim')
    finally:
        if process is not None and process.poll() is None:
            stop(process)
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    asyncio.run(run())
