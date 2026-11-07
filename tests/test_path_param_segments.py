"""Tool arguments that become URL path segments, through the pinned children and the gateway against owned HTTP
fixtures (no live backend). quote() leaves dots alone and httpx drops '.' and '..' segments while it builds a URL, so
an argument '..' (or one spliced without encoding) reached another endpoint under the configured base: unban '..'
became DELETE /banned (every ban cleared), regenerate key '../../global/spend/reset?' became POST /global/spend/reset."""
import json

import pytest

from test_nextcloud_error_secrets import error_result
from test_six_hardening import Quiet, call, runtime, serve

REFUSED = "must not be empty, '.' or '..'."


def recording(prefixes, lookups=None):
    """Records every request to a path under `prefixes`, except the lookups a tool makes first (answered as given)."""
    seen, lookups = [], lookups or {}

    class Backend(Quiet):
        def answer(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0) or 0))
            if self.path in lookups:
                return self.reply(lookups[self.path])
            if self.path.startswith(prefixes):
                seen.append((self.command, self.path))
            self.reply({'data': [], 'meta': {}})
        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = answer
    return Backend, seen


async def outcome(client, headers, tool, arguments):
    result = error_result(await client.post('/mcp', headers=headers, json=call(tool, arguments)))
    return result.get('isError') is True, json.dumps(result)


EMQX_REFUSED = [
    ('emqx_get_client', {'clientid': '..'}, 'clientid'),
    ('emqx_client_subscriptions', {'clientid': '..'}, 'clientid'),
    ('emqx_kick_client', {'clientid': '.'}, 'clientid'),
    ('emqx_client_subscribe', {'clientid': '..', 'topic': 'owned/t'}, 'clientid'),
    ('emqx_client_unsubscribe', {'clientid': '', 'topic': 'owned/t'}, 'clientid'),
    ('emqx_node_detail', {'node': '..'}, 'node'),
    ('emqx_manage_authn_users', {'operation': 'read', 'authenticator_id': '..'}, 'authenticator_id'),
    ('emqx_manage_authn_users', {'operation': 'delete', 'user_id': '..'}, 'user_id'),
    ('emqx_manage_authz_rules', {'operation': 'delete', 'subject_type': 'username', 'subject': '..'}, 'subject'),
    ('emqx_unban', {'subject_type': 'clientid', 'who': '..'}, 'who'),
    ('emqx_get_trace_log', {'name': '..'}, 'name'),
    ('emqx_delete_trace', {'name': '..'}, 'name'),
    ('emqx_get_rule_metrics', {'rule_id': '..'}, 'rule_id'),
    ('emqx_toggle_rule', {'rule_id': '..', 'enable': True}, 'rule_id'),
    ('emqx_delete_retained', {'topic': '..'}, 'topic'),
]
EMQX_ENCODED = [  # one per path family: a '/' in the argument stays inside its segment
    ('emqx_unban', {'subject_type': 'clientid', 'who': 'owned/x'}, ('DELETE', '/api/v5/banned/clientid/owned%2Fx')),
    ('emqx_get_client', {'clientid': 'a/b'}, ('GET', '/api/v5/clients/a%2Fb')),
    ('emqx_manage_authn_users', {'operation': 'delete', 'user_id': 'u/1'},
     ('DELETE', '/api/v5/authentication/password_based%3Abuilt_in_database/users/u%2F1')),
    ('emqx_manage_authz_rules', {'operation': 'delete', 'subject_type': 'username', 'subject': 's/1'},
     ('DELETE', '/api/v5/authorization/sources/built_in_database/rules/users/s%2F1')),
    ('emqx_get_rule_metrics', {'rule_id': 'r/1'}, ('GET', '/api/v5/rules/r%2F1/metrics')),
    ('emqx_delete_trace', {'name': 't/1'}, ('DELETE', '/api/v5/trace/t%2F1')),
    ('emqx_delete_retained', {'topic': 'a/b'}, ('DELETE', '/api/v5/mqtt/retainer/message/a%2Fb')),
    ('emqx_node_detail', {'node': 'emqx@owned'}, ('GET', '/api/v5/nodes/emqx@owned')),  # '@' as it was sent before
]


async def test_emqx_refuses_dot_segments_and_encodes_the_rest(tmp_path):
    backend, seen = recording(('/api/v5/banned', '/api/v5/authentication', '/api/v5/authorization', '/api/v5/nodes/',
                               '/api/v5/clients', '/api/v5/trace', '/api/v5/rules', '/api/v5/mqtt', '/api/v5/api_key'),
                              {'/api/v5/authorization/sources': {'sources': [{'type': 'built_in_database'}]}})
    grants = ['emqx_unban', 'emqx_manage_authn_users:delete', 'emqx_manage_authz_rules:delete', 'emqx_kick_client',
              'emqx_client_subscribe', 'emqx_client_unsubscribe', 'emqx_delete_trace', 'emqx_toggle_rule',
              'emqx_delete_retained']
    with serve(backend) as url:
        async with runtime(tmp_path, 'emqx', url, write_grants=grants) as (client, headers, *_):
            for tool, arguments, field in EMQX_REFUSED:
                is_error, text = await outcome(client, headers, tool, arguments)
                assert is_error and f'{field} {REFUSED}' in text, (tool, arguments, text)
            # encoded to one segment, refused by backend_policy after one decode: the PaaS server's text
            is_error, text = await outcome(client, headers, 'emqx_node_detail', {'node': '../api_key'})
            assert is_error and 'EMQX_DESTINATION_DENIED' in text, text
            assert seen == []
            for tool, arguments, _ in EMQX_ENCODED:
                await outcome(client, headers, tool, arguments)  # the fixture's reply may not fit; the path counts
            assert seen == [request for _, _, request in EMQX_ENCODED]
            # '..' is a valid MQTT topic no path segment can carry: the read goes straight to the listing scan
            seen.clear()
            is_error, text = await outcome(client, headers, 'emqx_get_retained', {'topic': '..'})
            assert not is_error, text
            assert seen == [('GET', '/api/v5/mqtt/retainer/messages?page=1&limit=200')]


async def test_litellm_refuses_dot_segments_and_encodes_the_key(tmp_path):
    backend, seen = recording(('/key/', '/global/', '/claude-code/', '/model/'))
    grants = ['litellm_regenerate_key', 'litellm_enable_plugin', 'litellm_update_model']
    with serve(backend) as url:
        async with runtime(tmp_path, 'litellm', url, write_grants=grants) as (client, headers, *_):
            for tool, arguments, expected in [
                    ('litellm_regenerate_key', {'key': '..'}, 'key ' + REFUSED),
                    ('litellm_enable_plugin', {'plugin_name': '..'}, 'plugin_name ' + REFUSED),
                    ('litellm_update_model', {'model_id': '.', 'model_name': 'x'}, 'model_id ' + REFUSED),
                    # encoded to one segment, refused by backend_policy after one decode ('..' segments)
                    ('litellm_regenerate_key', {'key': '../../global/spend/reset?'}, 'BACKEND_DESTINATION_DENIED')]:
                is_error, text = await outcome(client, headers, tool, arguments)
                assert is_error and expected in text, (tool, arguments, text)
            assert seen == []
            is_error, text = await outcome(client, headers, 'litellm_regenerate_key', {'key': 'sk-owned'})
            assert not is_error, text
            await outcome(client, headers, 'litellm_update_model', {'model_id': 'm/1', 'model_name': 'x'})
    assert seen == [('POST', '/key/sk-owned/regenerate'), ('PATCH', '/model/m%2F1/update')]


async def test_opendesign_encodes_project_ids_and_file_paths(tmp_path):
    backend, seen = recording(('/api/projects', '/api/x', '/api/secret'))
    with serve(backend) as url:
        async with runtime(tmp_path, 'opendesign', url, write_grants=['delete_project']) as (client, headers, *_):
            for tool, arguments in [('get_project', {'project_id': '..'}),
                                    ('delete_project', {'project_id': '../x'}),
                                    ('read_file', {'project_id': 'p', 'file_path': '../../secret'})]:
                is_error, text = await outcome(client, headers, tool, arguments)
                assert is_error and 'BACKEND_DESTINATION_DENIED' in text, (tool, arguments, text)
            assert seen == []
            for tool, arguments in [('delete_project', {'project_id': 'x/files/a.html'}),
                                    ('read_file', {'project_id': 'p', 'file_path': 'dir/a b(1)+x.html'})]:
                is_error, text = await outcome(client, headers, tool, arguments)
                assert not is_error, (tool, text)
    assert seen == [('DELETE', '/api/projects/x%2Ffiles%2Fa.html'), ('GET', '/api/projects/p/files/dir/a%20b(1)+x.html')]
