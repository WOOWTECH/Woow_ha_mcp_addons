"""Commercial acceptance (PaaS Hermes MCP 249 -> Hermes 247, Hermes 0.21.6; the same vendored server ships here):

- AI-HMCP-001-2: hermes_model set sent {model[,provider]}; POST /api/model/set requires {scope, provider, model}: always
  422. list_providers was a fixed list, not Hermes' /api/model/options.
- AI-HMCP-001-4: hermes_config set display.compact PUT the dotted key as a literal top-level key and answered ok.
- AI-HMCP-001-5: hermes_chat ignored session_id: every turn was a new session.
- AI-HMCP-001-6: a hermes_chat timeout left the Hermes turn running (the add-on's 300 s limit stays; the turn is now
  streamed so a timeout closes it and Hermes stops the turn).
- AI-HMCP-001-7: hermes_webhook taught {{payload}}; Hermes renders {field.path} / {__raw__}.
- AI-HMCP-001-8: deleting a missing session answered ok:true (Hermes says already_absent).
- AI-HMCP-003-1: the dashboard cookie was cached 10 min per URL and kept after a 401.

The real Hermes child against a LOCAL fake Hermes (gateway and dashboard on one port) that follows Hermes 0.21.6.
"""
import copy
import json
import threading
import time

from test_hermes_chat_timeout import boundary
from test_six_hardening import Quiet, call, runtime, serve

GRANTS = ['hermes_model:set', 'hermes_config:set', 'hermes_session:delete', 'hermes_webhook:create', 'hermes_chat']


def merge(base, incoming):
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = value


def hermes(state):
    lock = threading.Lock()
    state.setdefault('config', {'display': {'compact': False, 'skin': 'default'}})
    state.setdefault('model', {'model': 'qwen/qwen3.8-flash', 'provider': 'custom'})
    state.setdefault('cookie', 'session-cookie-0815')
    state.setdefault('password', 'DUMMY')
    state.update(requests=[], logins=0, stream_closed=False)

    class Hermes(Quiet):
        def body(self):
            raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            data = json.loads(raw) if raw else None
            with lock:
                state['requests'].append((self.command, self.path, data))
            return data

        def authed(self):
            if f'hermes_session_at="{state["cookie"]}"' not in self.headers.get('Cookie', ''):
                self.reply({'detail': 'Not authenticated'}, 401)
                return False
            return True

        def do_POST(self):
            data = self.body()
            if self.path == '/auth/password-login':
                state['logins'] += 1
                if data.get('password') != state['password']:
                    return self.reply({'detail': 'Invalid credentials'}, 401)
                body = b'{}'
                self.send_response(200)
                self.send_header('Set-Cookie', f'hermes_session_at={state["cookie"]}')
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == '/v1/responses':
                return self.respond(data)
            if not self.authed():
                return
            if self.path == '/api/model/set':
                missing = [f for f in ('scope', 'provider', 'model') if f not in data]
                if missing:
                    return self.reply({'detail': [{'loc': ['body', f], 'msg': 'Field required'} for f in missing]}, 422)
                state['model'] = {'model': data['model'], 'provider': data['provider']}
                return self.reply({'ok': True, 'scope': 'main', **state['model']})
            if self.path == '/api/webhooks':
                return self.reply({'name': data['name'], 'secret': 's'})
            self.reply({'detail': 'Not Found'}, 404)

        def do_GET(self):
            self.body()
            if not self.authed():
                return
            if self.path == '/api/model/info':
                return self.reply(state['model'])
            if self.path == '/api/model/options':
                return self.reply({**state['model'], 'providers': [
                    {'slug': 'custom', 'name': 'Custom endpoint', 'is_current': True, 'models': ['qwen/qwen3.8-flash']},
                    {'slug': 'openrouter', 'name': 'OpenRouter', 'is_current': False, 'models': ['a', 'b', 'c']}]})
            if self.path == '/api/config':
                return self.reply(state['config'])
            if self.path == '/api/status':
                return self.reply({'version': '0.21.6', 'gateway_running': True, 'gateway_state': 'running',
                                   'active_sessions': 1})
            self.reply({'detail': 'Not Found'}, 404)

        def do_PUT(self):
            data = self.body()
            if not self.authed():
                return
            if self.path == '/api/config':
                if not state.get('ignore_writes'):
                    merge(state['config'], data['config'])
                return self.reply({'ok': True})
            self.reply({'detail': 'Not Found'}, 404)

        def do_DELETE(self):
            self.body()
            if not self.authed():
                return
            if self.path.startswith('/api/sessions/'):
                return self.reply({'ok': True, 'already_absent': True})
            self.reply({'detail': 'Not Found'}, 404)

        def respond(self, data):
            envelope = {'id': 'resp_abc', 'status': 'completed', 'output': [
                {'type': 'message', 'content': [{'type': 'output_text', 'text': 'PELICAN-7319'}]}]}
            if not data.get('stream'):
                return self.reply(envelope)
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            try:
                self.wfile.write(b'event: response.created\ndata: {"type": "response.created"}\n\n')
                self.wfile.flush()
                if state.get('hang'):
                    while True:  # Hermes writes SSE keepalives while the agent works
                        time.sleep(.05)
                        self.wfile.write(b': keepalive\n\n')
                        self.wfile.flush()
                event = json.dumps({'type': 'response.completed', 'response': envelope})
                self.wfile.write(f'event: response.completed\ndata: {event}\n\n'.encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                state['stream_closed'] = True
            self.close_connection = True

    return Hermes


def result_of(response):
    assert response.status_code == 200, response.text
    body = response.text
    data = next((line[5:].strip() for line in body.splitlines() if line.startswith('data:')), body)
    reply = json.loads(data)
    assert 'result' in reply, body
    return reply['result']


def text(result):
    return result['content'][0]['text']


def sent(state, method, path):
    return [body for m, p, body in state['requests'] if (m, p) == (method, path)]


async def tool(client, headers, name, arguments, id=2):
    return result_of(await client.post('/mcp', headers=headers, json=call(name, arguments, id=id)))


async def test_model_set_list_providers_and_config_set(tmp_path):
    state = {}
    with serve(hermes(state)) as url:
        async with runtime(tmp_path, 'hermes', url, write_grants=GRANTS) as (client, headers, *_):
            result = await tool(client, headers, 'hermes_model', {'action': 'set', 'model': 'qwen/qwen3.8-plus'})
            assert not result.get('isError'), result
            assert sent(state, 'POST', '/api/model/set') == [
                {'scope': 'main', 'provider': 'custom', 'model': 'qwen/qwen3.8-plus'}]

            result = await tool(client, headers, 'hermes_model', {'action': 'list_providers'}, id=3)
            providers = json.loads(text(result))['providers']
            assert [p['slug'] for p in providers] == ['custom', 'openrouter'] and providers[1]['total_models'] == 3

            result = await tool(client, headers, 'hermes_config',
                                {'action': 'set', 'key': 'display.compact', 'value': 'true'}, id=4)
            assert not result.get('isError'), result
            assert sent(state, 'PUT', '/api/config') == [{'config': {'display': {'compact': True}}}]
            assert state['config']['display'] == {'compact': True, 'skin': 'default'}

            state['ignore_writes'] = True
            result = await tool(client, headers, 'hermes_config',
                                {'action': 'set', 'key': 'display.skin', 'value': 'mono'}, id=5)
            assert result.get('isError') is True and 'display.skin' in text(result), result


async def test_chat_session_id_maps_to_conversation(tmp_path):
    state = {}
    with serve(hermes(state)) as url:
        async with runtime(tmp_path, 'hermes', url, write_grants=GRANTS) as (client, headers, *_):
            result = await tool(client, headers, 'hermes_chat', {'message': 'hi', 'session_id': 'qa-mem'})
            assert not result.get('isError') and text(result) == 'PELICAN-7319', result
            result = await tool(client, headers, 'hermes_chat', {'message': 'next', 'session_id': 'resp_abc'}, id=3)
            first, second = sent(state, 'POST', '/v1/responses')
            assert first['conversation'] == 'qa-mem' and first['stream'] is True
            assert second['previous_response_id'] == 'resp_abc' and 'conversation' not in second


async def test_chat_timeout_stops_the_turn(tmp_path):
    state = {'hang': True}
    with serve(hermes(state)) as url:
        async with boundary(tmp_path, url, {'HERMES_MCP_CHAT_TIMEOUT': '1'}) as (client, headers):
            started = time.monotonic()
            result = await tool(client, headers, 'hermes_chat', {'message': 'sleep 50'})
            took = time.monotonic() - started
            assert result.get('isError') is True, result
            assert 'BACKEND_TIMEOUT' in text(result) and 'stopped' in text(result), result
            assert took < 10
            for _ in range(50):
                if state['stream_closed']:
                    break
                time.sleep(.1)
            assert state['stream_closed'], 'the timed-out turn was not closed, so Hermes keeps running it'


async def test_webhook_placeholder_and_missing_session(tmp_path):
    state = {}
    with serve(hermes(state)) as url:
        async with runtime(tmp_path, 'hermes', url, write_grants=GRANTS) as (client, headers, *_):
            result = await tool(client, headers, 'hermes_webhook',
                                {'action': 'create', 'name': 'qa', 'prompt': 'QA {{payload}}'})
            assert not result.get('isError'), result
            assert sent(state, 'POST', '/api/webhooks')[0]['prompt'] == 'QA {__raw__}'

            result = await tool(client, headers, 'hermes_session', {'action': 'delete', 'session_id': 'nope'}, id=3)
            assert result.get('isError') is True, result
            assert 'status=404' in text(result) and 'not found' in text(result), result

            listed = await client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 4, 'method': 'tools/list'})
            description = next(t for t in result_of(listed)['tools'] if t['name'] == 'hermes_webhook')['description']
            assert '{{payload}}' not in description and '{__raw__}' in description


async def test_stale_cookie_401_relogs_once(tmp_path):
    state = {}
    with serve(hermes(state)) as url:
        async with runtime(tmp_path, 'hermes', url) as (client, headers, *_):
            assert not (await tool(client, headers, 'hermes_gateway', {'action': 'status'})).get('isError')
            assert state['logins'] == 1
            state['cookie'] = 'session-cookie-0816'  # Hermes restarted: the cached cookie is stale
            result = await tool(client, headers, 'hermes_gateway', {'action': 'status'}, id=3)
            assert not result.get('isError'), result
            assert state['logins'] == 2

            state['cookie'] = 'session-cookie-0817'
            state['password'] = 'rotated'  # and now the password changed too: one login attempt, then the error
            result = await tool(client, headers, 'hermes_gateway', {'action': 'status'}, id=4)
            assert result.get('isError') is True and '401' in text(result), result
            assert state['logins'] == 3
