"""Real HA child/gateway, owned local HTTP fixture. No HAOS or external Agent claim."""
import json
import socket
from urllib.parse import parse_qs, urlsplit
import pytest
from test_six_hardening import Quiet, call, runtime, serve
from test_real_products import rpc
from tool_refusal import refused

SID = 'owned-native-session'
CANARY = 'DUMMY-HERMES-SESSION-CREDENTIAL'


def backend(state):
    class Backend(Quiet):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if self.path == '/auth/password-login':
                state['logins'] += 1
                self.send_response(200)
                self.send_header('Set-Cookie', f'hermes_session_at=owned-session-cookie-{state["logins"]}')
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'{}')
                return
            self.reply({}, 404)

        def do_GET(self):
            state['http'].append(('GET', self.path))
            state['cookies'].append(self.headers.get('Cookie'))
            if state.get('read_401', 0):
                state['read_401'] -= 1
                return self.reply({'detail': CANARY}, 401)
            if self.path == '/api/sessions':
                return self.reply({'sessions': [{'id': SID}] if state['exists'] else []})
            if self.path != f'/api/sessions/{SID}/mutation-snapshot':
                return self.reply({'detail': 'Not Found'}, 404)
            if state.get('missing_contract'):
                return self.reply({'detail': 'Not Found'}, 404)
            return self.reply({'session_id': SID, 'exists': state['exists'], 'runtime_revision': 7 if state['exists'] else 0, 'runtime_generation': 3 if state['exists'] else None})

        def do_DELETE(self):
            url = urlsplit(self.path)
            values = {key: value[0] for key, value in parse_qs(url.query).items()}
            state['http'].append(('DELETE', url.path))
            state['deletes'].append(values)
            state['delete_headers'].append(dict(self.headers))
            if state.get('refusal'):
                return self.reply({'detail': CANARY}, state['refusal'])
            if url.path != f'/api/sessions/{SID}' or set(values) != {'request_id', 'expected_revision', 'expected_generation'}:
                return self.reply({'detail': 'client_upgrade_required'}, 409)
            key = values['request_id']
            if key in state['receipts']:
                old = state['receipts'][key]
                return self.reply({'ok': True, 'deleted_ids': [SID]} if values == old else {'detail': 'admission_conflict'}, 200 if values == old else 409)
            if (values['expected_revision'], values['expected_generation']) != ('7', '3') or state.get('race'):
                return self.reply({'detail': 'revision_conflict'}, 409)
            state['exists'] = False
            state['effects'] += 1
            state['receipts'][key] = values
            if state.get('commit_401'):
                return self.reply({'detail': CANARY}, 401)
            if state.get('lose_reply'):
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            return self.reply({'ok': True, 'deleted_ids': [SID]})
    return Backend


def fresh():
    return dict(exists=True, effects=0, receipts={}, deletes=[], http=[], logins=0, cookies=[], delete_headers=[])


def text(result):
    return '\n'.join(c.get('text', '') for c in result.get('content', []))


async def test_real_child_schema_denial_zero_HTTP_then_granted_effect(tmp_path):
    state = fresh()
    with serve(backend(state)) as url:
        async with runtime(tmp_path, 'hermes', url, write_grants=[]) as (client, headers, store, *_):
            listing = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'})
            session = next(t for t in listing['tools'] if t['name'] == 'hermes_session')
            assert len(listing['tools']) == 10  # hermes_chat is hidden without its write grant
            assert {'request_id', 'expected_revision', 'expected_generation'} <= session['inputSchema']['properties'].keys()
            denied = await client.post('/mcp', headers=headers, json=call('hermes_session', {'action': 'delete', 'session_id': SID}))
            assert refused(denied, 'Operation not permitted')
            assert state['http'] == [] and state['effects'] == 0
            store.update(enabled_write_tools=['hermes_session:delete', 'hermes_chat'])
            full = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/list'})
            assert len(full['tools']) == 11
            invalid = await rpc(client, '/mcp', headers, call('hermes_session', {'action': 'delete', 'session_id': SID, 'request_id': 'incomplete'}))
            assert invalid.get('isError') and state['http'] == []
            done = await rpc(client, '/mcp', headers, call('hermes_session', {'action': 'delete', 'session_id': SID}))
            assert not done.get('isError') and json.loads(text(done)) == {'ok': True, 'deleted': SID}
            assert [method for method, _ in state['http']] == ['GET', 'DELETE', 'GET']
            assert state['effects'] == 1 and state['exists'] is False


async def test_real_child_lost_reply_exact_explicit_replay_one_effect(tmp_path):
    state = fresh()
    state['lose_reply'] = True
    with serve(backend(state)) as url:
        async with runtime(tmp_path, 'hermes', url, write_grants=['hermes_session:delete']) as (client, headers, *_):
            async def invoke(**identity):
                return await rpc(client, '/mcp', headers, call('hermes_session', {'action': 'delete', 'session_id': SID, **identity}))
            failed = await invoke()
            assert failed.get('isError') and 'OUTCOME_UNKNOWN' in text(failed)
            assert state['effects'] == len(state['deletes']) == 1
            sent = state['deletes'][0]
            assert sent['request_id'] in text(failed)
            identity = dict(request_id=sent['request_id'], expected_revision=7, expected_generation=3)
            replay = await invoke(**identity)
            assert not replay.get('isError') and state['effects'] == 1
            assert state['deletes'][-1] == sent
            conflict = await invoke(**{**identity, 'expected_generation': 4})
            assert conflict.get('isError') and state['effects'] == 1


@pytest.mark.parametrize('status', [401, 403, 409, 503])
async def test_real_child_backend_refusal_redacts_credentials_and_never_retries(tmp_path, status):
    state = fresh()
    state['refusal'] = status
    with serve(backend(state)) as url:
        async with runtime(tmp_path, 'hermes', url, canary=CANARY, write_grants=['hermes_session:delete']) as (client, headers, *_):
            failed = await rpc(client, '/mcp', headers, call('hermes_session', {'action': 'delete', 'session_id': SID}))
            assert failed.get('isError') and str(status) in text(failed)
            assert CANARY not in json.dumps(failed)
            assert state['exists'] and state['effects'] == 0 and len(state['deletes']) == 1


@pytest.mark.parametrize('failures', [1, 2])
async def test_real_authenticated_child_read_401_refreshes_at_most_once(tmp_path, failures):
    state = fresh()
    state['read_401'] = failures
    with serve(backend(state)) as url:
        async with runtime(tmp_path, 'hermes', url) as (client, headers, *_):
            result = await rpc(client, '/mcp', headers, call('hermes_session', {'action': 'list'}))
            if failures == 1:
                assert not result.get('isError')
                assert json.loads(text(result))['sessions'] == [{'id': SID}]
            else:
                assert result.get('isError') and '401' in text(result)
            assert CANARY not in json.dumps(result)
    assert state['logins'] == 2
    assert state['http'] == [('GET', '/api/sessions')] * 2
    assert state['cookies'] == ['hermes_session_at="owned-session-cookie-1"',
                                'hermes_session_at="owned-session-cookie-2"']
    assert state['effects'] == 0


@pytest.mark.parametrize('explicit_identity,committed', [(False, False), (True, False), (False, True)])
async def test_real_authenticated_child_delete_401_returns_once_even_after_commit(
    tmp_path, explicit_identity, committed,
):
    state = fresh()
    state['commit_401' if committed else 'refusal'] = True if committed else 401
    identity = dict(request_id='owned-replay', expected_revision=7, expected_generation=3) if explicit_identity else {}
    with serve(backend(state)) as url:
        async with runtime(tmp_path, 'hermes', url, canary=CANARY,
                           write_grants=['hermes_session:delete']) as (client, headers, *_):
            result = await rpc(client, '/mcp', headers, call('hermes_session', {
                'action': 'delete', 'session_id': SID, **identity,
            }))
            assert result.get('isError') and '401' in text(result)
            assert CANARY not in json.dumps(result)
    assert state['logins'] == 1  # No refresh or implicit resend from the real auth wrapper.
    assert state['http'] == [('GET', f'/api/sessions/{SID}/mutation-snapshot'), ('DELETE', f'/api/sessions/{SID}')]
    assert len(state['deletes']) == 1 and state['effects'] == int(committed)
    assert state['exists'] is not committed
    assert set(state['deletes'][0]) == {'request_id', 'expected_revision', 'expected_generation'}
    assert not any('hermes_no_auth_retry' in key.lower() for key in state['delete_headers'][0])
    if explicit_identity:
        assert state['deletes'][0] == {key: str(value) for key, value in identity.items()}


@pytest.mark.parametrize('failure', ['missing_contract', 'race'])
async def test_real_child_missing_contract_or_stale_snapshot_never_falls_back(tmp_path, failure):
    state = fresh()
    state[failure] = True
    with serve(backend(state)) as url:
        async with runtime(tmp_path, 'hermes', url, write_grants=['hermes_session:delete']) as (client, headers, *_):
            result = await rpc(client, '/mcp', headers, call('hermes_session', {'action': 'delete', 'session_id': SID}))
            assert result.get('isError')
            assert ('contract' if failure == 'missing_contract' else '409') in text(result)
    assert len(state['deletes']) == int(failure == 'race')
    assert state['exists'] and state['effects'] == 0
