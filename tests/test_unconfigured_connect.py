"""0.2.2: a client (Claude.ai) connects whatever the backend's state.

Before 0.2.2 an add-on without a backend had no child, so initialize on its MCP URL was HTTP 502 and the connector could
not even be added. Now, with make_apps(listing=...) (both launchers pass it), the gateway answers initialize,
notifications/initialized, ping and tools/list itself when no child can answer, from the packaged snapshot
(tool_snapshot.py) through the same filter_list, in a session of its own ("woow-local-..."), and refuses tools/call:

- no backend configured: -32603 Backend not configured (n8n's child runs without one: its documentation tools still
  answer, every other tool is refused before the child);
- a configured backend the last completed health check found unreachable: -32603 Backend unreachable with the check's
  reason, never forwarded (the child keeps answering initialize and tools/list);
- a child that is not up: the gateway's own answers, and Backend unreachable with MCP_SERVER_NOT_READY.

Readiness (/health/ready) and the panel are unchanged. LOCAL/MOCK children here; the real children's listings are
compared with the snapshot in tests/test_tool_snapshot.py, real executables in test_unconfigured_connect_runtime below.
"""
import asyncio
from contextlib import closing
import json
import signal
import subprocess
import sys

import httpx
import pytest

from mcp_admin_core import VERSION, gateway
from mcp_admin_core.gateway import PROTOCOL_VERSIONS, make_apps
from mcp_admin_core.health import HealthMonitor, probe_reason, protocol_reply
from mcp_admin_core.products import ProductStore, TOOLS
from mcp_admin_core.surface import BACKEND_FREE, FULL_PRODUCTS, listing
from n8n_adapter import TOOLS as N8N_TOOLS
from owned_executable import Executable
from test_expansion_policy import call
from test_expansion_runtime import fake_api
from test_full_surface import COUNTS
from test_real_products import ROOT, connection, free_port, rpc
from tool_refusal import refusal

ACCEPT = {'Accept': 'application/json, text/event-stream'}
INIT = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
    'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'claude-ai', 'version': '0'}}}
INITIALIZED = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}
LIST = {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}
NO_CHILD = {'child': 'unconfigured', 'ready': False, 'backend': 'unknown', 'reason': None}
DOWN = {'child': 'backoff', 'ready': False, 'backend': 'unknown', 'reason': None}
UNREACHABLE = {'child': 'running', 'ready': True, 'backend': 'unreachable',
               'reason': 'BACKEND_UNAVAILABLE: [Errno 111] Connection refused'}
UP = {'child': 'running', 'ready': True, 'backend': 'reachable', 'reason': None}
PROBE = {'emqx': 'emqx_list_clients', 'odoo': 'search_records', 'n8n': 'n8n_list_workflows', 'hermes': 'hermes_inspect',
         'opendesign': 'list_projects', 'litellm': 'litellm_list_models', 'nextcloud': 'get_file_tree'}


def tools_of(product):
    return N8N_TOOLS if product == 'n8n' else TOOLS[product]


class Child:
    """A MOCK child: records every request; answers initialize with a session, everything else with an empty result."""
    def __init__(self, fail=None):
        self.seen, self.fail = [], fail

    def __call__(self, request):
        if self.fail is not None:
            raise self.fail('child not listening', request=request)
        message = json.loads(request.content) if request.content else None
        self.seen.append((request.method, message))
        if request.method == 'DELETE':
            return httpx.Response(200)
        if 'id' not in message:
            return httpx.Response(202)
        result = {'content': [{'type': 'text', 'text': 'child'}]}
        if message['method'] == 'initialize':
            result = {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'child', 'version': '0'}}
            return httpx.Response(200, headers={'mcp-session-id': 'child-session'},
                                  json={'jsonrpc': '2.0', 'id': message['id'], 'result': result})
        if message['method'] == 'tools/list':
            result = {'tools': listing(self.product)}
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': message['id'], 'result': result})


class Boundary:
    def __init__(self, store, product, available, child=None, path=None):
        self.store, self.product, self.available = store, product, dict(available)
        self.child = child or Child()
        self.child.product = product
        self.path = path

    async def __aenter__(self):
        self.to_child = httpx.AsyncClient(transport=httpx.MockTransport(self.child))
        _, app = make_apps(self.store, tools_of(self.product), self.to_child, listing=listing(self.product),
                           availability=lambda: dict(self.available), server_name='woow-mcp-' + self.product)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://mcp')
        token = self.store.load().token
        self.url = f'/private_{token}/mcp' if self.path == 'secret' else '/mcp'
        self.headers = dict(ACCEPT) if self.path == 'secret' else {'Authorization': 'Bearer ' + token, **ACCEPT}
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()
        await self.to_child.aclose()

    async def post(self, message, headers=None):
        return await asyncio.wait_for(self.client.post(self.url, headers={**self.headers, **(headers or {})}, json=message), 10)

    async def connect(self):
        """initialize + notifications/initialized + tools/list, as Claude.ai connects."""
        response = await self.post(INIT)
        assert response.status_code == 200, response.text
        self.headers['Mcp-Session-Id'] = response.headers['mcp-session-id']
        initialized = await self.post(INITIALIZED)
        assert initialized.status_code == 202
        listed = await self.post(LIST)
        assert listed.status_code == 200 and listed.headers['cache-control'] == 'no-store'
        return response, listed.json()['result']['tools']


def store_for(tmp_path, product, url=None):
    store = ProductStore(tmp_path / ('state-' + product), product)
    if url is not None:
        if product == 'n8n':
            store.update(backend_url=url, backend_key='DUMMY-held-key')
        else:
            store.update(connection=connection(product, url))
    return store


@pytest.mark.parametrize('product', FULL_PRODUCTS)
@pytest.mark.parametrize('path', ['bearer', 'secret'])
async def test_unconfigured_client_connects_lists_everything_and_gets_backend_not_configured(tmp_path, product, path):
    available = NO_CHILD if product != 'n8n' else UP  # n8n's child runs without a backend
    with closing(store_for(tmp_path, product)) as store:
        async with Boundary(store, product, available, path=path) as boundary:
            response, tools = await boundary.connect()
            result = response.json()['result']
            assert result['serverInfo'] == {'name': 'woow-mcp-' + product, 'version': VERSION}
            assert result['capabilities'] == {'tools': {}} and result['protocolVersion'] == '2025-06-18'
            assert len(tools) == COUNTS[product] and {t['name'] for t in tools} == set(tools_of(product))
            name = PROBE[product]
            refused = await boundary.post(call(name, {}))
            assert refusal(refused) == {'code': -32603, 'message': 'Backend not configured', 'data': {'tool': name}}
            assert (await boundary.post({'jsonrpc': '2.0', 'id': 4, 'method': 'ping'})).json()['result'] == {}
            if product == 'n8n':
                # The child's session; tools/list and the refused call never reached it, a documentation tool does.
                assert boundary.headers['Mcp-Session-Id'] == 'child-session'
                assert [m['method'] for _, m in boundary.child.seen] == ['initialize', 'notifications/initialized', 'ping']
                docs = await boundary.post(call('search_nodes', {'query': 'webhook'}))
                assert docs.status_code == 200 and docs.json()['result']['content'][0]['text'] == 'child'
            else:
                assert boundary.headers['Mcp-Session-Id'].startswith('woow-local-')
                assert boundary.child.seen == []  # no child exists: none is asked


async def test_the_own_answers_follow_the_policy_and_the_session_rules(tmp_path):
    with closing(store_for(tmp_path, 'emqx')) as store:
        store.update(disabled=['emqx_list_clients'],
                     enabled_write_tools=[g for g in store.load().enabled_write_tools if g != 'emqx_publish'])
        async with Boundary(store, 'emqx', NO_CHILD) as boundary:
            _, tools = await boundary.connect()
            listed = {t['name'] for t in tools}
            assert 'emqx_list_clients' not in listed and 'emqx_publish' not in listed and len(listed) == COUNTS['emqx'] - 2
            # Policy refusals keep their own answers (and come first).
            assert refusal(await boundary.post(call('emqx_list_clients', {})))['message'] == 'Unknown tool'
            assert refusal(await boundary.post(call('emqx_ban', []))) ['message'] == 'Invalid params'
            # Other methods: unchanged (-32601 before any session; malformed 403; no session 400).
            discover = await boundary.post({'jsonrpc': '2.0', 'id': 9, 'method': 'server/discover'})
            assert discover.json()['error']['code'] == -32601
            assert (await boundary.post({'jsonrpc': '2.0', 'id': 9, 'method': 'tools/list', 'params': []})).status_code == 403
            session = boundary.headers.pop('Mcp-Session-Id')
            assert (await boundary.post(LIST)).status_code == 400
            boundary.headers['Mcp-Session-Id'] = session
            # No server-to-client stream; DELETE ends the session, which then is unknown (404, as a child answers).
            stream = await boundary.client.get(boundary.url, headers=boundary.headers)
            assert stream.status_code == 405 and stream.headers['allow'] == 'POST, DELETE'
            assert (await boundary.client.delete(boundary.url, headers=boundary.headers)).status_code == 200
            gone = await boundary.post(LIST)
            assert gone.status_code == 404 and gone.json()['error'] == {'code': -32000, 'message': 'Not Found'}
            assert (await boundary.post(LIST, {'Mcp-Session-Id': 'made-up'})).status_code == 404
            # An unreviewed protocol version gets the newest reviewed one (as the children answer).
            other = await boundary.post({**INIT, 'params': {**INIT['params'], 'protocolVersion': '2024-06-25'}})
            assert other.json()['result']['protocolVersion'] == max(PROTOCOL_VERSIONS)
            # Readiness is unchanged: no backend, not ready.
            assert (await boundary.client.get('/health/ready')).status_code == 503
            assert boundary.child.seen == []


async def test_a_wrong_token_never_gets_an_own_answer(tmp_path):
    with closing(store_for(tmp_path, 'emqx')) as store:
        async with Boundary(store, 'emqx', NO_CHILD) as boundary:
            assert (await boundary.post(INIT, {'Authorization': 'Bearer ' + 'x' * 43})).status_code == 401
            response = await boundary.client.post('/private_' + 'x' * 43 + '/mcp', headers=ACCEPT, json=INIT)
            assert response.status_code == 404 and 'mcp-session-id' not in response.headers
            _, _ = await boundary.connect()
            store.update(token=None)  # revoked: the gateway's own session is refused as any other
            assert (await boundary.post(LIST)).status_code == 401


@pytest.mark.parametrize('product', ['emqx', 'n8n', 'odoo'])
async def test_unreachable_backend_lists_through_the_child_and_refuses_calls_with_the_reason(tmp_path, product):
    with closing(store_for(tmp_path, product, 'http://127.0.0.1:9')) as store:
        async with Boundary(store, product, UNREACHABLE) as boundary:
            response, tools = await boundary.connect()
            assert boundary.headers['Mcp-Session-Id'] == 'child-session' and len(tools) == COUNTS[product]
            name = PROBE[product]
            refused = await boundary.post(call(name, {}))
            assert refusal(refused) == {'code': -32603, 'message': 'Backend unreachable',
                                        'data': {'tool': name, 'reason': UNREACHABLE['reason']}}
            assert [m['method'] for _, m in boundary.child.seen] == ['initialize', 'notifications/initialized', 'tools/list']
            if product == 'n8n':  # documentation tools need no backend
                assert (await boundary.post(call('tools_documentation', {}))).json()['result']['content'][0]['text'] == 'child'
            # Reachable again (the next completed check): forwarded as before.
            boundary.available.update(backend='reachable', reason=None)
            forwarded = await boundary.post(call(name, {}))
            assert forwarded.status_code == 200 and forwarded.json()['result']['content'][0]['text'] == 'child'
            # Without a completed check for this child start the call is forwarded too (never refused on a guess).
            boundary.available.update(backend='unknown', ready=False)
            assert (await boundary.post(call(name, {}))).json()['result']['content'][0]['text'] == 'child'


async def test_a_child_that_is_down_gets_own_answers_and_its_sessions_end(tmp_path):
    with closing(store_for(tmp_path, 'litellm', 'http://127.0.0.1:9')) as store:
        async with Boundary(store, 'litellm', DOWN) as boundary:
            # A session the stopped child had opened: gone (404), so the client initializes again.
            assert (await boundary.post(LIST, {'Mcp-Session-Id': 'child-session'})).status_code == 404
            _, tools = await boundary.connect()
            assert boundary.headers['Mcp-Session-Id'].startswith('woow-local-') and len(tools) == COUNTS['litellm']
            refused = refusal(await boundary.post(call('litellm_list_models', {})))
            assert refused['message'] == 'Backend unreachable'
            assert refused['data']['reason'] == "MCP_SERVER_NOT_READY: the add-on's MCP server is backoff; try again shortly"
            boundary.available.update(backend='unreachable', reason='BACKEND_TIMEOUT: the health check got no answer within 5 s')
            assert refusal(await boundary.post(call('litellm_list_models', {})))['data']['reason'].startswith('BACKEND_TIMEOUT')
            assert boundary.child.seen == []
            # The child is up and answered a health check: the own session ends (404) and the client re-initializes
            # with the child.
            boundary.available.update(UP)
            assert (await boundary.post(LIST)).status_code == 404
            boundary.headers.pop('Mcp-Session-Id')
            await boundary.connect()
            assert boundary.headers['Mcp-Session-Id'] == 'child-session'


async def test_initialize_waits_for_a_starting_child_then_answers_itself(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, 'CHILD_WAIT_SECONDS', .6)
    with closing(store_for(tmp_path, 'hermes', 'http://127.0.0.1:9')) as store:
        child = Child(fail=httpx.ConnectError)
        async with Boundary(store, 'hermes', {'child': 'running', 'ready': False, 'backend': 'unknown', 'reason': None},
                            child=child) as boundary:
            started = asyncio.get_running_loop().time()
            _, tools = await boundary.connect()
            assert asyncio.get_running_loop().time() - started >= .5
            assert boundary.headers['Mcp-Session-Id'].startswith('woow-local-') and len(tools) == COUNTS['hermes']
            # A child session whose child does not listen any more: gone.
            assert (await boundary.post(LIST, {'Mcp-Session-Id': 'child-session'})).status_code == 404
            # The child listens again: initialize reaches it at once.
            child.fail = None
            boundary.headers.pop('Mcp-Session-Id')
            await boundary.connect()
            assert boundary.headers['Mcp-Session-Id'] == 'child-session'


async def test_own_sessions_are_bounded_and_end_when_idle(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, 'LOCAL_SESSION_LIMIT', 2)
    with closing(store_for(tmp_path, 'nextcloud')) as store:
        async with Boundary(store, 'nextcloud', NO_CHILD) as boundary:
            sessions = [(await boundary.post(INIT)).headers['mcp-session-id'] for _ in range(3)]
            ping = {'jsonrpc': '2.0', 'id': 3, 'method': 'ping'}
            assert [(await boundary.post(ping, {'Mcp-Session-Id': s})).status_code for s in sessions] == [404, 200, 200]
            monkeypatch.setattr(gateway, 'LOCAL_SESSION_SECONDS', 0)
            assert (await boundary.post(ping, {'Mcp-Session-Id': sessions[2]})).status_code == 404


def test_without_a_listing_nothing_changes():
    # Odoo Manage (bounded, retired) and older callers pass no listing: the 0.2.1 behavior (tests elsewhere: 502/503).
    assert 'odoo-manage' not in FULL_PRODUCTS
    with pytest.raises(ValueError):
        make_apps(None, {}, None, listing=[{'no': 'name'}])


@pytest.mark.parametrize('text,reason', [
    ('BACKEND_UNAVAILABLE: [Errno 111] Connection refused', 'BACKEND_UNAVAILABLE: [Errno 111] Connection refused'),
    (json.dumps({'success': False, 'error': 'BACKEND_HTTP_ERROR status=401: 401 Unauthorized'}),
     'BACKEND_HTTP_ERROR status=401: 401 Unauthorized'),
    (json.dumps({'error': {'message': 'nested'}}), 'nested'),
    ('Error executing tool woow_backend_probe: BACKEND_UNAVAILABLE', 'BACKEND_UNAVAILABLE'),
    (json.dumps({'ok': False}), 'BACKEND_INVALID_RESPONSE: the health check answer was not the expected one'),
    ('a\n  b' + ' x' * 2000, None),
])
def test_probe_reason(text, reason):
    found = probe_reason({'content': [{'type': 'text', 'text': text}], 'isError': True})
    if reason is None:
        assert found.startswith('a b x') and len(found) == 1000
    else:
        assert found == reason


class Process:
    def __init__(self):
        self.ready, self.status, self.starts = False, 'running', 1

    def health(self):
        return {'state': self.status, 'transport_ready': self.ready, 'starts': self.starts}


async def test_availability_is_the_last_completed_check_of_this_child_start(tmp_path):
    key = 'DUMMY-held-key'
    probe = {'reply': {'content': [{'type': 'text', 'text': f'BACKEND_UNAVAILABLE: refused (key {key})'}], 'isError': True}}
    def handler(request):
        if request.method == 'DELETE':
            return httpx.Response(204)
        message = json.loads(request.content)
        if message['method'] == 'notifications/initialized':
            return httpx.Response(202)
        result = {}
        if message['method'] == 'initialize':
            result = {'protocolVersion': '2025-03-26', 'serverInfo': {'name': 'mock'}}
        elif message['method'] == 'tools/call':
            result = probe['reply']
        return httpx.Response(200, headers={'mcp-session-id': 'health'},
                              json={'jsonrpc': '2.0', 'id': message['id'], 'result': result})
    with closing(store_for(tmp_path, 'n8n')) as store:
        process = Process()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            monitor = HealthMonitor(store, process, client)
            assert monitor.availability() == {'child': 'running', 'ready': False, 'backend': 'unknown', 'reason': None}
            await monitor.check()  # unconfigured n8n: the child answers, no backend
            assert monitor.availability() == {'child': 'running', 'ready': True, 'backend': 'unconfigured', 'reason': None}
            store.update(backend_url='http://backend.test', backend_key=key)
            await monitor.check()
            assert monitor.availability() == {'child': 'running', 'ready': True, 'backend': 'unreachable',
                                              'reason': 'BACKEND_UNAVAILABLE: refused (key [REDACTED])'}
            assert monitor.snapshot()['backend'] == 'unreachable'  # readiness and the panel: unchanged
            process.starts = 2  # the child restarted (e.g. new settings): no completed check for it yet
            assert monitor.availability()['ready'] is False and monitor.availability()['backend'] == 'unknown'
            probe['reply'] = {'content': [{'type': 'text', 'text': json.dumps({'success': True})}]}
            await monitor.check()
            assert monitor.availability() == {'child': 'running', 'ready': True, 'backend': 'reachable', 'reason': None}
            process.status = 'backoff'
            assert monitor.availability()['ready'] is False and monitor.availability()['child'] == 'backoff'


async def test_a_child_that_does_not_answer_is_not_ready(tmp_path):
    def handler(request):
        raise httpx.ConnectError('refused', request=request)
    with closing(store_for(tmp_path, 'emqx', 'http://127.0.0.1:9')) as store:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            monitor = HealthMonitor(store, Process(), client)
            await monitor.check()
            assert monitor.availability() == {'child': 'running', 'ready': False, 'backend': 'unreachable', 'reason':
                                              "MCP_SERVER_NOT_READY: the add-on's MCP server did not answer the health check"}


# Real executables (run_product / apps/n8n/run.py) and real children.

async def launch(tmp_path, product, store):
    store.close()
    port, admin_port = free_port(), free_port()
    runner = Executable(tmp_path, product, [port, admin_port])
    if product == 'n8n':
        code = 'import run; ' + runner.code('run') + 'run.main()'
        argv = [sys.executable, '-c', code]
        path = str(ROOT / 'packages/mcp-admin-core') + ':' + str(ROOT / 'apps/n8n')
    else:
        code = 'from mcp_admin_core import run_product; ' + runner.code('run_product') + 'run_product.main()'
        argv = [str(ROOT / '.venv/bin/python'), '-c', code, product]
        path = str(ROOT / 'packages/mcp-admin-core')
    runner.release()
    log = (tmp_path / 'runtime.log').open('wb')
    process = subprocess.Popen(argv + ['--data', str(tmp_path / ('state-' + product)), '--host', '127.0.0.1',
                                       '--mcp-port', str(port), '--admin-port', str(admin_port)],
                               cwd=tmp_path if product == 'n8n' else ROOT, stdout=log, stderr=log,
                               env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': path, 'PYTHONDONTWRITEBYTECODE': '1'})
    await runner.ready(process)
    return process, runner, f'http://127.0.0.1:{port}/mcp', log


async def stop(process, log):
    process.send_signal(signal.SIGTERM)
    try:
        await asyncio.to_thread(process.wait, 10)
    except subprocess.TimeoutExpired:
        process.kill(); await asyncio.to_thread(process.wait)
    log.close()
    assert process.returncode == 0


@pytest.mark.parametrize('product', FULL_PRODUCTS)
async def test_unconfigured_connect_runtime(tmp_path, product):
    """The real add-on with no backend (n8n: its real child runs): Claude.ai's connection sequence succeeds."""
    store = store_for(tmp_path, product)
    token = store.load().token
    process, runner, url, log = await launch(tmp_path, product, store)
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=20, event_hooks={'request': [runner.guard]}) as client:
            headers = {'Authorization': 'Bearer ' + token, **ACCEPT}
            result = await rpc(client, url, headers, INIT)
            assert result['serverInfo'] == {'name': 'woow-mcp-' + product, 'version': VERSION}
            await rpc(client, url, headers, INITIALIZED)
            tools = (await rpc(client, url, headers, LIST))['tools']
            assert {t['name'] for t in tools} == set(tools_of(product)) and len(tools) == COUNTS[product]
            response = await client.post(url, headers=headers, json=call(PROBE[product], {}))
            assert refusal(response) == {'code': -32603, 'message': 'Backend not configured', 'data': {'tool': PROBE[product]}}
            assert (await client.get(url.replace('/mcp', '/health/ready'))).status_code == 503
            if product == 'n8n':
                async with asyncio.timeout(25):  # its child answers documentation tools once up
                    while True:
                        async with client.stream('POST', url, headers=headers,
                                                 json=call('search_nodes', {'query': 'webhook'})) as reply:
                            if reply.status_code == 404:  # an own session while the child started: connect again
                                headers.pop('Mcp-Session-Id')
                                await rpc(client, url, headers, INIT)
                                continue
                            try:
                                found = await protocol_reply(reply, 1)
                                break
                            except ValueError:  # Backend unreachable (MCP_SERVER_NOT_READY) while it starts
                                pass
                        await asyncio.sleep(.25)
                assert 'webhook' in found['content'][0]['text'].lower()
    finally:
        await stop(process, log)


@pytest.mark.parametrize('product', ['emqx', 'odoo', 'n8n'])
async def test_unreachable_backend_runtime(tmp_path, product):
    """The real add-on and child with a configured backend that does not answer: initialize and the full tools/list
    through the child; after the first health check tools/call is refused with the check's reason."""
    with fake_api() as (live, events, mutations, failures):
        pass  # bound then released: nothing listens on this address any more
    store = store_for(tmp_path, product, live)
    token = store.load().token
    process, runner, url, log = await launch(tmp_path, product, store)
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=20, event_hooks={'request': [runner.guard]}) as client:
            headers = {'Authorization': 'Bearer ' + token, **ACCEPT}
            async with asyncio.timeout(40):
                while True:  # the child answers initialize (an own session only while it starts)
                    attempt = dict(headers)
                    result = await rpc(client, url, attempt, INIT)
                    if not attempt['Mcp-Session-Id'].startswith('woow-local-'):
                        break
                    await asyncio.sleep(.5)
            headers = {**attempt, 'MCP-Protocol-Version': result['protocolVersion']}
            await rpc(client, url, headers, INITIALIZED)
            tools = (await rpc(client, url, headers, LIST))['tools']
            assert len(tools) == COUNTS[product]
            async with asyncio.timeout(40):  # the first completed health check (every 15 s)
                while True:
                    response = await client.post(url, headers=headers, json=call(PROBE[product], {}))
                    error = refusal(response)
                    if error is not None:
                        break
                    await asyncio.sleep(.5)
            assert error['message'] == 'Backend unreachable' and error['data']['tool'] == PROBE[product]
            assert isinstance(error['data']['reason'], str) and error['data']['reason'], error
            print(f"LOCAL {product} unreachable reason: {error['data']['reason']}")
            assert 'DUMMY' not in json.dumps(error)
            assert (await client.get(url.replace('/mcp', '/health/ready'))).status_code == 503
    finally:
        await stop(process, log)
