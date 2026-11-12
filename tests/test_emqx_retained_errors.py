"""Pinned EMQX child + gateway against owned HTTP fixtures; no live broker."""
import base64
import json

import pytest

from test_six_hardening import Quiet, call, runtime, serve
from test_nextcloud_error_secrets import error_result

TOPIC = 'owned/nested/topic'
DIRECT = '/api/v5/mqtt/retainer/message/owned%2Fnested%2Ftopic'


@pytest.mark.parametrize('tool', ['emqx_get_retained', 'emqx_delete_retained'])
@pytest.mark.parametrize('status', [401, 403, 429, 503])
async def test_retained_non404_failure_is_error_without_fallback(tmp_path, tool, status):
    seen, effects = [], []

    class Backend(Quiet):
        def answer(self):
            seen.append((self.command, self.path))
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if self.command in ('DELETE', 'POST'):
                # A server may apply a write before its error response is sent.
                effects.append(self.command)
            if self.path == DIRECT:
                return self.reply({'message': 'owned broker diagnostic'}, status)
            return self.reply({'data': [], 'meta': {}, 'id': 'unexpected-publish'})

        do_GET = do_DELETE = do_POST = answer

    with serve(Backend) as url:
        async with runtime(tmp_path, 'emqx', url, write_grants=['emqx_delete_retained']) as (client, headers, *_):
            response = await client.post('/mcp', headers=headers, json=call(tool, {'topic': TOPIC}))
            result = error_result(response)
            assert response.status_code == 200 and result['isError'] is True
            assert str(status) in json.dumps(result)
    assert seen == [('DELETE' if tool == 'emqx_delete_retained' else 'GET', DIRECT)]
    assert effects == (['DELETE'] if tool == 'emqx_delete_retained' else [])


@pytest.mark.parametrize('tool', ['emqx_get_retained', 'emqx_publish'])
@pytest.mark.parametrize('body', [b'', b'<html>not JSON</html>', b'null', b'42', b'true', b'"text"'])
async def test_empty_or_invalid_json_200_is_error_without_another_request(tmp_path, tool, body):
    seen = []

    class Backend(Quiet):
        def answer(self):
            seen.append((self.command, self.path))
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            self.reply(body)

        do_GET = do_POST = answer

    args = {'topic': TOPIC, **({'payload': 'owned'} if tool == 'emqx_publish' else {})}
    with serve(Backend) as url:
        async with runtime(tmp_path, 'emqx', url, write_grants=['emqx_publish']) as (client, headers, *_):
            result = error_result(await client.post('/mcp', headers=headers, json=call(tool, args)))
            assert result['isError'] is True
            assert 'EMQX_INVALID_RESPONSE' in json.dumps(result)
    assert len(seen) == 1


@pytest.mark.parametrize('found', [False, True])
async def test_retained_lookup_404_preserves_listing_compatibility(tmp_path, found):
    seen = []

    class Backend(Quiet):
        def do_GET(self):
            seen.append(self.path)
            if self.path == DIRECT:
                return self.reply({'message': 'not found'}, 404)
            self.reply({'data': [{'topic': TOPIC}] if found else [], 'meta': {'hasnext': False}})

    with serve(Backend) as url:
        async with runtime(tmp_path, 'emqx', url) as (client, headers, *_):
            result = error_result(await client.post('/mcp', headers=headers,
                json=call('emqx_get_retained', {'topic': TOPIC})))
            assert not result.get('isError', False)
            payload = result['structuredContent']
            assert payload['found'] is found and payload['lookup'] == 'listing'
            assert payload['payload'] is None
    assert len(seen) == 2 and seen[0] == DIRECT
    assert seen[1].startswith('/api/v5/mqtt/retainer/messages?')


async def test_delete_404_does_not_publish_empty_message(tmp_path):
    seen = []

    class Backend(Quiet):
        def answer(self):
            seen.append(self.command)
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            self.reply({'message': 'not found'}, 404 if self.command == 'DELETE' else 200)

        do_DELETE = do_POST = answer

    with serve(Backend) as url:
        async with runtime(tmp_path, 'emqx', url, write_grants=['emqx_delete_retained']) as (client, headers, *_):
            result = error_result(await client.post('/mcp', headers=headers,
                json=call('emqx_delete_retained', {'topic': TOPIC})))
            assert result['isError'] is True
    assert seen == ['DELETE']


async def test_retained_success_and_204_no_content_still_work(tmp_path):
    seen = []

    class Backend(Quiet):
        def do_GET(self):
            seen.append(('GET', self.path))
            self.reply({'payload': base64.b64encode(b'owned payload').decode(), 'qos': 1})

        def do_DELETE(self):
            seen.append(('DELETE', self.path))
            self.reply(b'', 204)

        def do_POST(self):
            seen.append(('POST', self.path))
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            self.reply({'id': 'owned-publish', 'reason_code': 16}, 202)

    with serve(Backend) as url:
        async with runtime(tmp_path, 'emqx', url,
                           write_grants=['emqx_delete_retained', 'emqx_publish']) as (client, headers, *_):
            for tool, args in [('emqx_get_retained', {'topic': TOPIC}),
                               ('emqx_delete_retained', {'topic': TOPIC}),
                               ('emqx_publish', {'topic': TOPIC, 'payload': 'owned'})]:
                result = error_result(await client.post('/mcp', headers=headers, json=call(tool, args)))
                assert not result.get('isError', False)
                payload = result['structuredContent']
                if tool == 'emqx_get_retained':
                    assert payload['found'] and payload['payload'] == 'owned payload'
                    assert payload['lookup'] == 'direct'
                elif tool == 'emqx_delete_retained':
                    assert payload == {'topic': TOPIC, 'deleted': True, 'method': 'delete'}
                else:
                    assert payload['published'] and payload['delivered_to_subscribers'] is False
    assert seen == [('GET', DIRECT), ('DELETE', DIRECT), ('POST', '/api/v5/publish')]
