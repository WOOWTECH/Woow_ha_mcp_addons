"""Owned ephemeral fake backend + genuine pinned LiteLLM HTTP child, no inference.

Run only with a granted collaboration slot. conftest owns the shared test lock;
Endpoint rechecks live PID/fd/inode proof before each child HTTP request.
"""
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit

import httpx
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS, child_spec
from owned_runtime import Endpoint
from test_real_products import rpc
from test_litellm_metadata import call, BAD
from litellm_metadata_fixtures import FIXTURES, SECRET


@contextmanager
def fake_backend():
    events, failures = [], []
    control = {'status': 200, 'malformed': False}
    by_path = {fixture[1]: fixture for fixture in FIXTURES.values()}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            path = urlsplit(self.path)
            events.append((self.command, path.path, parse_qs(path.query)))
            try:
                assert self.headers.get('Authorization') == 'Bearer DUMMY'
                assert path.path in by_path or path.path in ('/v1/models', '/health/readiness', '/v2/team/list')
                if path.path == '/v1/models': body = {'data': [{'id': 'old-model'}]}
                elif path.path == '/health/readiness': body = {'status': 'healthy'}
                elif path.path == '/v2/team/list': body = {'teams': [{'team_id':'old-team'}]}
                else: body = by_path[path.path][2]
                if control['malformed']: body = {'unexpected': SECRET}
                if control['status'] != 200: body = {'error': SECRET}
                data = json.dumps(body).encode()
                self.send_response(control['status'])
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers(); self.wfile.write(data)
            except Exception as exc:
                failures.append(type(exc).__name__)
                self.send_error(500)
        def do_POST(self): failures.append('unexpected POST'); self.send_error(405)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fd = server.socket.fileno()
    inode = os.fstat(fd).st_ino
    assert server.server_port != 3000
    assert Path(f'/proc/{os.getpid()}/fd/{fd}').readlink() == Path(f'socket:[{inode}]')
    assert thread.is_alive()
    proof = {'pid':os.getpid(), 'fd':fd, 'inode':inode, 'port':server.server_port}
    print('OWNED_BACKEND', json.dumps(proof))
    try:
        yield f'http://127.0.0.1:{server.server_port}', events, failures, control
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
        assert not thread.is_alive() and server.socket.fileno() == -1
        print('OWNED_BACKEND_CLEANUP', json.dumps(proof))


def payload(reply):
    assert not reply.get('isError'), reply
    return reply.get('structuredContent') or json.loads(reply['content'][0]['text'])


async def test_owned_real_metadata_reads_and_error_regression(tmp_path):
    with fake_backend() as (url, events, failures, control):
        store = ProductStore(tmp_path/'state', 'litellm')
        endpoint = Endpoint('litellm')
        store.update(connection={'url': url, 'master_key': 'DUMMY'})
        process = endpoint.supervisor(child_spec(store.load(), store.directory))
        pid = None
        try:
            await process.start()
            pid = process.process.pid
            print('OWNED_CHILD', json.dumps({'pid':pid,'port':endpoint.port,'proof':endpoint.proof}))
            async with endpoint.client(timeout=10) as child:
                _, app = make_apps(store, TOOLS['litellm'], child, child_url=endpoint.url)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary.test') as client:
                    headers = {'Authorization': 'Bearer '+store.load().token, 'Accept':'application/json, text/event-stream'}
                    init = {'jsonrpc':'2.0','id':1,'method':'initialize','params':{
                        'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'metadata-local-test','version':'0'}}}
                    result = await rpc(client, '/mcp', headers, init)
                    assert result['capabilities'] == {'tools': {}}
                    headers['MCP-Protocol-Version'] = result['protocolVersion']
                    await rpc(client, '/mcp', headers, {'jsonrpc':'2.0','method':'notifications/initialized'})
                    listed = await rpc(client, '/mcp', headers, {'jsonrpc':'2.0','id':2,'method':'tools/list'})
                    assert {t['name'] for t in listed['tools']} == {n for n,t in TOOLS['litellm'].items() if not t.write}
                    for tool in listed['tools']:
                        assert tool['inputSchema'] == TOOLS['litellm'][tool['name']].arguments.model_json_schema()
                    for name, (args,path,body,expected) in FIXTURES.items():
                        before = len(events)
                        reply = await rpc(client, '/mcp', headers, call(name,args))
                        assert payload(reply) == expected
                        assert SECRET not in json.dumps(reply)
                        assert events[before:] == [('GET',path,{k:[str(v)] for k,v in args.items()})]
                    for name in ('litellm_list_models','litellm_health_readiness','litellm_list_teams'):
                        assert not (await rpc(client, '/mcp', headers, call(name,{}))).get('isError')
                    # Public policy disable must deny BEFORE contacting the real child.
                    before, dispatches = len(events), endpoint.dispatches
                    for name, (args,*_) in FIXTURES.items():
                        store.update(disabled=[name])
                        assert (await client.post('/mcp',headers=headers,json=call(name,args))).status_code == 403
                    store.update(disabled=[])
                    for name,args in BAD:
                        assert (await client.post('/mcp',headers=headers,json=call(name,args))).status_code == 403
                    for name in ('litellm_health','litellm_chat_completion','litellm_list_keys','litellm_create_user'):
                        assert (await client.post('/mcp',headers=headers,json=call(name,{}))).status_code == 403
                    assert endpoint.dispatches == dispatches and len(events) == before
                    # Ordinary HTTP failures and wrong envelopes, no attack replay.
                    for status in (401,403,429,500,503):
                        control['status'] = status
                        for name,(args,*_) in FIXTURES.items():
                            reply = await rpc(client, '/mcp', headers, call(name,args))
                            assert reply.get('isError') is True
                            assert SECRET not in json.dumps(reply)
                            assert f'BACKEND_HTTP_ERROR status={status}' in json.dumps(reply)
                    control.update(status=200, malformed=True)
                    for name,(args,*_) in FIXTURES.items():
                        reply = await rpc(client, '/mcp', headers, call(name,args))
                        assert reply.get('isError') is True and SECRET not in json.dumps(reply)
                        assert 'BACKEND_INVALID_RESPONSE' in json.dumps(reply)
                    control['malformed'] = False
                    assert payload(await rpc(client,'/mcp',headers,call('litellm_user_info',{'user_id':'user-1'}))) == FIXTURES['litellm_user_info'][3]
                    await client.delete('/mcp',headers=headers)
                    assert not failures, failures
                    assert all(method == 'GET' for method,_,_ in events)
                    print('METADATA_RUNTIME', json.dumps({'backend_GETs':len(events),'child_dispatches':endpoint.dispatches,'listed':len(listed['tools']),'zero_dispatch_denials':True}))
        finally:
            await process.stop(); endpoint.close(); store.close()
            if pid is not None:
                assert not Path(f'/proc/{pid}').exists(), 'owned child not reaped'
                print('OWNED_CHILD_CLEANUP', json.dumps({'pid':pid,'reaped':True}))
