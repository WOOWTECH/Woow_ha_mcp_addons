"""0.2.2 (test VM 2026-10-16, G2): hermes_chat had a fixed 30 s limit, and a Hermes agent turn with a free model took
28-30 s: 2 of 3 turns failed with BACKEND_TIMEOUT although Hermes finished them. A chat turn now may take 300 s
(HERMES_MCP_CHAT_TIMEOUT), the other Gateway/Dashboard calls keep 30 s, and the add-on's gateway lets a tools/call reply
be idle and last up to CALL_SECONDS (330 s) instead of 30 s idle / 120 s. The real Hermes child, LOCAL fake Hermes.
"""
import asyncio
from contextlib import asynccontextmanager, closing
import time

import httpx

from mcp_admin_core import gateway
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS, child_spec
from owned_runtime import Endpoint
from test_real_products import connection, rpc
from test_six_hardening import Quiet, call, serve

ACCEPT = {'Accept': 'application/json, text/event-stream'}


def hermes(delay, seen):
    class Hermes(Quiet):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            seen.append(self.path)
            if self.path == '/v1/responses':
                time.sleep(delay)
                return self.reply({'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'pong'}]}]})
            self.reply({}, 404)

        def do_GET(self):
            seen.append(self.path)
            time.sleep(delay)
            self.reply({'capabilities': []})
    return Hermes


@asynccontextmanager
async def boundary(tmp_path, url, env=None):
    with closing(ProductStore(tmp_path / 'state', 'hermes')) as store:
        store.update(connection=connection('hermes', url))
        spec = child_spec(store.load(), store.directory)
        spec.env.update(env or {})
        endpoint = Endpoint('hermes')
        manager = endpoint.supervisor(spec)
        try:
            await manager.start()
            async with endpoint.client(timeout=None) as child:
                _, app = make_apps(store, TOOLS['hermes'], child, child_url=endpoint.url)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://boundary',
                                             timeout=None) as client:
                    headers = {'Authorization': 'Bearer ' + store.load().token, **ACCEPT}
                    init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                        'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'chat', 'version': '0'}}}
                    for _ in range(100):
                        try:
                            await rpc(client, '/mcp', headers, init)
                            break
                        except (httpx.HTTPError, ValueError):
                            await asyncio.sleep(.1)
                    yield client, headers
        finally:
            await manager.stop(); endpoint.close()


async def test_a_chat_turn_longer_than_30_seconds_is_answered(tmp_path):
    seen = []
    with serve(hermes(33, seen)) as url:
        async with boundary(tmp_path, url) as (client, headers):
            started = time.monotonic()
            response = await client.post('/mcp', headers=headers, json=call('hermes_chat', {'message': 'ping'}))
            took = time.monotonic() - started
    assert response.status_code == 200, response.text
    assert '"text":"pong"' in response.text.replace(' ', '') and 'BACKEND_TIMEOUT' not in response.text
    assert 33 <= took < 60 and seen == ['/v1/responses']


async def test_the_chat_limit_is_configurable_and_other_calls_keep_theirs(tmp_path):
    seen = []
    with serve(hermes(3, seen)) as url:
        async with boundary(tmp_path, url, {'HERMES_MCP_CHAT_TIMEOUT': '1'}) as (client, headers):
            started = time.monotonic()
            response = await client.post('/mcp', headers=headers, json=call('hermes_chat', {'message': 'ping'}))
            assert time.monotonic() - started < 3
            assert 'BACKEND_TIMEOUT' in response.text, response.text
            # A management call is not a chat turn: its 30 s limit is not the chat setting.
            inspect = await client.post('/mcp', headers=headers, json=call('hermes_inspect', {'target': 'capabilities'}))
            assert 'BACKEND_TIMEOUT' not in inspect.text and '"capabilities"' in inspect.text.replace('\\', ''), inspect.text


def test_the_gateway_allows_a_tools_call_its_longest_child_limit():
    assert gateway.CALL_SECONDS > 300 and gateway.STREAM_SECONDS == 120


async def test_only_a_tools_call_reply_may_outlast_the_stream_limit(tmp_path, monkeypatch):
    """The Python SDK children keep an idle SSE reply alive with a comment every 15 s, so the binding limit was the
    120 s total (STREAM_SECONDS); a tools/call reply now has CALL_SECONDS. Scaled down: 1 s and 5 s."""
    monkeypatch.setattr(gateway, 'STREAM_SECONDS', 1)
    monkeypatch.setattr(gateway, 'CALL_SECONDS', 5)

    def child(request):
        import json as jsonlib
        message = jsonlib.loads(request.content)
        async def events():
            for _ in range(7):  # 2.1 s of keep-alive comments, then the reply
                yield b': ping\n\n'
                await asyncio.sleep(.3)
            yield ('event: message\ndata: ' + jsonlib.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': (
                {'content': [{'type': 'text', 'text': 'late'}]} if message['method'] == 'tools/call' else {})}) + '\n\n').encode()
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=events())

    with closing(ProductStore(tmp_path / 'state', 'hermes')) as store:
        async with httpx.AsyncClient(transport=httpx.MockTransport(child)) as to_child:
            _, app = make_apps(store, TOOLS['hermes'], to_child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://boundary') as client:
                headers = {'Authorization': 'Bearer ' + store.load().token, 'Mcp-Session-Id': 's', **ACCEPT}
                answered = await client.post('/mcp', headers=headers, json=call('hermes_inspect', {}))
                assert '"text": "late"' in answered.text or '"text":"late"' in answered.text, answered.text
                cut = await client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 3, 'method': 'ping'})
                assert '"result"' not in cut.text  # any other reply keeps STREAM_SECONDS
