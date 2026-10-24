"""Real HA child + gateway against an owned fake backend: PaaS functional contract."""
import json

from test_six_hardening import Quiet, call, runtime, serve
from test_real_products import rpc


def deep_merge(target, incoming):
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_merge(target[key], value)
        else:
            target[key] = value


def backend(state):
    class Backend(Quiet):
        def do_GET(self):
            state['paths'].append(self.path)
            if self.path == '/api/model/info':
                return self.reply({'provider': 'custom', 'model': 'old'})
            if self.path == '/api/model/options':
                return self.reply({'provider': 'custom', 'model': 'old', 'providers': [
                    {'slug': 'custom', 'name': 'Local', 'models': ['old', 'new']} ]})
            if self.path == '/api/config':
                return self.reply(state['config'])
            return self.reply({'detail': 'Session not found'}, 404)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            state['requests'].append((self.path, body))
            if self.path == '/auth/password-login':
                self.send_response(200)
                self.send_header('Set-Cookie', 'hermes_session_at=parity-cookie')
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'{}')
                return
            if self.path == '/api/model/set':
                if not body.get('confirm_expensive_model'):
                    return self.reply({'confirm_required': True, 'confirm_message': 'cost confirmation'})
                return self.reply({'ok': True, **body})
            if self.path == '/v1/responses':
                if body['input'] == 'incomplete':
                    return self.reply({'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'}})
                return self.reply({'status': 'completed', 'output': [
                    {'type': 'message', 'content': [{'type': 'output_text', 'text': 'pong'}]}]})
            return self.reply({}, 404)

        def do_PUT(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state['requests'].append((self.path, body))
            if not state.get('ignore_write'):
                deep_merge(state['config'], body['config'])
            return self.reply({'ok': True})
    return Backend


def result_text(reply):
    return reply['content'][0]['text']


async def test_real_child_model_config_chat_and_path_contract(tmp_path):
    state = {'config': {'display': {'compact': False}}, 'requests': [], 'paths': []}
    with serve(backend(state)) as url:
        async with runtime(tmp_path, 'hermes', url, write_grants=[
            'hermes_model:set', 'hermes_config:set', 'hermes_chat']) as (client, headers, *_):
            async def invoke(name, **args):
                return await rpc(client, '/mcp', headers, call(name, args))
            listing = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'})
            model = next(t for t in listing['tools'] if t['name'] == 'hermes_model')
            assert 'confirm_expensive' in model['inputSchema']['properties']
            options = await invoke('hermes_model', action='list_providers')
            assert json.loads(result_text(options))['providers'][0]['slug'] == 'custom'
            confirm = await invoke('hermes_model', action='set', model='new')
            assert confirm['isError'] is True
            switched = await invoke('hermes_model', action='set', model='new', confirm_expensive=True)
            assert not switched.get('isError')
            assert state['requests'][-1] == ('/api/model/set', {
                'scope': 'main', 'provider': 'custom', 'model': 'new', 'confirm_expensive_model': True})
            saved = await invoke('hermes_config', action='set', key='display.compact', value='true')
            assert not saved.get('isError') and state['config']['display']['compact'] is True
            state['ignore_write'] = True
            ignored = await invoke('hermes_config', action='set', key='display.compact', value='false')
            assert ignored['isError'] is True
            for sid, key in [('thread-one', 'conversation'), ('resp_123', 'previous_response_id')]:
                chat = await invoke('hermes_chat', message='ping', session_id=sid)
                assert result_text(chat) == 'pong'
                assert state['requests'][-1][1][key] == sid
            incomplete = await invoke('hermes_chat', message='incomplete')
            assert incomplete['isError'] is True
            assert 'max_output_tokens' in result_text(incomplete)
            traversed = await invoke('hermes_session', action='get', session_id='../config/raw')
            assert traversed['isError'] is True
            assert '/api/config/raw' not in state['paths']


async def test_real_child_config_parent_guard_and_deep_merge(tmp_path):
    state = {'config': {'display': {'compact': False, 'theme': 'dark'}}, 'requests': [], 'paths': []}
    with serve(backend(state)) as url:
        async with runtime(tmp_path, 'hermes', url, write_grants=['hermes_config:set']) as (client, headers, *_):
            async def config(**args):
                return await rpc(client, '/mcp', headers, call('hermes_config', {'action': 'set', **args}))
            for value in ({'secret': 'CANARY-denied-secret'},
                          {'items': [{'credentials': {'password': 'CANARY-denied-secret'}}]},
                          {'items': [{'ＡＰＩ＿ＫＥＹ': 'CANARY-denied-secret'}]}):
                for dry_run in (False, True):
                    reply = await config(key='webhooks.signing', value=json.dumps(value), dry_run=dry_run)
                    assert 'denied' in result_text(reply)
                    assert 'CANARY-denied-secret' not in result_text(reply)
            for name in ('clientSecret', 'accessToken'):
                for dry_run in (False, True):
                    for key, value in [
                        ('webhooks.signing.' + name, 'CANARY-camel-secret'),
                        ('webhooks.signing', {'items': [{name: 'CANARY-camel-secret'}]}),
                        ('webhooks.signing', json.dumps({'items': [{name: 'CANARY-camel-secret'}]})),
                    ]:
                        reply = await config(key=key, value=value, dry_run=dry_run)
                        assert 'denied' in result_text(reply)
                        assert 'CANARY-camel-secret' not in result_text(reply)
            assert not any(path == '/api/config' for path, _ in state['requests'])
            reply = await config(key='display', value='{"compact":true}')
            assert not reply.get('isError') and json.loads(result_text(reply))['ok']
            assert state['config']['display'] == {'compact': True, 'theme': 'dark'}
            state['ignore_write'] = True
            reply = await config(key='display', value='{"compact":false}')
            assert reply['isError'] is True
            for requested, actual in [
                ([True], [1]),
                ([{'enabled': True}], [{'enabled': 1}]),
                ([{'enabled': True}], [{'enabled': True, 'extra': 1}]),
            ]:
                state['config']['display']['flags'] = actual
                reply = await config(key='display', value={'flags': requested})
                assert reply['isError'] is True
