"""Run under pinned LiteLLM interpreter; genuine registered functions, no server.

Fixtures follow BerriAI/litellm be4481779ee8a73579af82a3b5394f62f4e4b057
model_info_v1/model_group_info, team_info, get_users/_build_user_info_response.
Unknown fields are synthetic confidentiality sentinels, not real credentials.
"""
import asyncio
import copy
import json
import sys
from types import SimpleNamespace
import unittest
import httpx
from jsonschema import Draft202012Validator
from woow_litellm_mcp_server.tools import models, teams, users
from woow_litellm_mcp_server.errors import LiteLLMApiError
from woow_litellm_mcp_server import metadata

INPUT = json.load(sys.stdin)
from litellm_metadata_fixtures import FIXTURES, SECRET
class Capture:
    def __init__(self): self.functions = {}
    def tool(self, *, name, **kwargs):
        def register(fn): self.functions[name] = fn; return fn
        return register
class Gate:
    def is_tool_enabled(self, name): return name in FIXTURES

class MetadataTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        mcp = Capture()
        for module in (models, teams, users): module.register(mcp, Gate())
        self.functions = mcp.functions
        self.requests = []

    async def invoke(self, name, body, *, status=200, args=None, content=None, headers=None):
        def respond(request):
            self.requests.append(request)
            return httpx.Response(status, json=body if content is None else None, content=content, headers=headers)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url='http://owned-fake.test', headers={'Authorization': 'Bearer DUMMY'}) as client:
            ctx = SimpleNamespace(lifespan_context={'litellm': client})
            return await self.functions[name](ctx, **(FIXTURES[name][0] if args is None else args))

    async def test_real_handlers_positive_projection_and_get_contract(self):
        for name, (args, path, body, expected) in FIXTURES.items():
            with self.subTest(name=name):
                actual = await self.invoke(name, body)
                self.assertEqual(actual, expected)
                self.assertNotIn(SECRET, json.dumps(actual))
                request = self.requests[-1]
                self.assertEqual(request.method, 'GET'); self.assertEqual(request.url.path, path)
                self.assertEqual(dict(request.url.params), {k:str(v) for k,v in args.items()})
                self.assertEqual(request.content, b'')

    async def test_user_filters_use_existing_wire_names(self):
        name = 'litellm_list_users'
        args = {'page': 1, 'page_size': 50, 'role': 'internal_user', 'user_ids': ['u1','u2'], 'team':'t1'}
        await self.invoke(name, FIXTURES[name][2], args=args)
        self.assertEqual(dict(self.requests[-1].url.params), {'page':'1','page_size':'50','role':'internal_user','user_ids':'u1,u2','team':'t1'})

    async def test_http_errors_not_empty_or_raw(self):
        for name in FIXTURES:
            for status in (401,403,404,429,500,503):
                with self.subTest(name=name, status=status):
                    with self.assertRaisesRegex(LiteLLMApiError, '^BACKEND_HTTP_ERROR status='+str(status)+'$'):
                        await self.invoke(name, {'error': SECRET}, status=status)

    async def test_missing_wrong_shapes_and_empty_details_fail(self):
        for name in FIXTURES:
            for body in ({}, None, [], {'error': SECRET}, {'data': {}}, {'data': []}):
                with self.subTest(name=name, body=body):
                    with self.assertRaisesRegex(LiteLLMApiError, '^BACKEND_INVALID_RESPONSE$'):
                        await self.invoke(name, body)
        for name, (_,_,body,_) in FIXTURES.items():
            with self.subTest(name=name):
                bad = copy.deepcopy(body)
                if name == 'litellm_model_info': bad['data'][0]['model_info'] = {'id': {}}
                elif name == 'litellm_model_group_info': bad['data'][0]['mode'] = {'config': SECRET}
                elif name == 'litellm_team_info': bad['team_info']['team_id'] = 'wrong-id'
                elif name == 'litellm_user_info': bad['user_info']['user_role'] = ['proxy_admin']
                else: bad['users'][0]['user_id'] = None
                with self.assertRaisesRegex(LiteLLMApiError, '^BACKEND_INVALID_RESPONSE$'):
                    await self.invoke(name, bad)

    async def test_pagination_empty_valid_bounds_and_shape(self):
        empty = {'users': [], 'total':0, 'page':1, 'page_size':50, 'total_pages':0}
        self.assertEqual(await self.invoke('litellm_list_users', empty), empty)
        for change in ({'users': [{}]*51}, {'page': 2}, {'page_size': 100}, {'total': True}, {'total_pages': '1'}, {'total': -1}):
            with self.assertRaisesRegex(LiteLLMApiError, '^BACKEND_INVALID_RESPONSE$'):
                await self.invoke('litellm_list_users', {**empty, **change})

    async def test_input_validation_precedes_backend(self):
        for name, args, valid in INPUT['cases']:
            if valid: continue
            self.requests.clear()
            with self.subTest(name=name, args=args):
                with self.assertRaises((ValueError, TypeError)):
                    await self.invoke(name, FIXTURES[name][2], args=args)
                self.assertEqual(self.requests, [])

    async def test_json_and_resource_bounds(self):
        name = 'litellm_user_info'
        for content in (b'not-json', b'{}', b'x'*(256*1024+1)):
            with self.assertRaisesRegex(LiteLLMApiError, '^BACKEND_INVALID_RESPONSE$'):
                await self.invoke(name, None, content=content)
        for extra in ([0]*101, {'x': {'x': {'x': {'x': {'x': {'x': {'x': {'x': {}}}}}}}}}):
            body = copy.deepcopy(FIXTURES[name][2]); body['ignored'] = extra
            with self.assertRaisesRegex(LiteLLMApiError, '^BACKEND_INVALID_RESPONSE$'):
                await self.invoke(name, body)
        body = copy.deepcopy(FIXTURES[name][2]); body['user_info']['max_budget'] = float('nan')
        with self.assertRaisesRegex(LiteLLMApiError, '^BACKEND_INVALID_RESPONSE$'):
            await self.invoke(name, None, content=json.dumps(body).encode())

    async def test_stream_bounds_deadline_and_owned_cleanup(self):
        class Stream(httpx.AsyncByteStream):
            def __init__(self, chunks, delay=0):
                self.chunks, self.delay, self.closed = chunks, delay, False
            async def __aiter__(self):
                for chunk in self.chunks:
                    await asyncio.sleep(self.delay)
                    yield chunk
            async def aclose(self): self.closed = True
        name = 'litellm_user_info'
        body = json.dumps(FIXTURES[name][2]).encode()
        for stream, error in [(Stream([body[:20], body[20:]]), None),
                              (Stream([b' '*65536]*5), 'BACKEND_INVALID_RESPONSE'),
                              (Stream([body], .1), 'BACKEND_TIMEOUT')]:
            old_timeout = metadata.TIMEOUT
            metadata.TIMEOUT = .02 if stream.delay else 5
            try:
                async with httpx.AsyncClient(base_url='http://owned-fake.test', transport=httpx.MockTransport(
                        lambda request: httpx.Response(200, stream=stream))) as client:
                    ctx = SimpleNamespace(lifespan_context={'litellm': client})
                    if error:
                        with self.assertRaisesRegex(LiteLLMApiError, '^'+error+'$'):
                            await self.functions[name](ctx, **FIXTURES[name][0])
                    else:
                        self.assertEqual(await self.functions[name](ctx, **FIXTURES[name][0]), FIXTURES[name][3])
                self.assertTrue(stream.closed)
            finally:
                metadata.TIMEOUT = old_timeout
        stream = Stream([body], 5)
        async with httpx.AsyncClient(base_url='http://owned-fake.test', transport=httpx.MockTransport(
                lambda request: httpx.Response(200, stream=stream))) as client:
            ctx = SimpleNamespace(lifespan_context={'litellm': client})
            task = asyncio.create_task(self.functions[name](ctx, **FIXTURES[name][0]))
            await asyncio.sleep(.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
            self.assertTrue(stream.closed)

    async def test_identity_and_selected_scalar_boundaries(self):
        for name, (_, _, original, _) in FIXTURES.items():
            body = copy.deepcopy(original)
            if name == 'litellm_model_info': body['data'][0]['model_info']['id'] = 'other'
            elif name == 'litellm_model_group_info': body['data'].append(copy.deepcopy(body['data'][0]))
            elif name == 'litellm_team_info': body['team_info']['blocked'] = 1
            elif name == 'litellm_user_info': body['user_info']['user_alias'] = 'x'*257
            else: body['users'][0]['max_budget'] = {'value': 10}
            with self.subTest(name=name):
                with self.assertRaisesRegex(LiteLLMApiError, '^BACKEND_INVALID_RESPONSE$'):
                    await self.invoke(name, body)
        for status in (204,):
            with self.assertRaisesRegex(LiteLLMApiError, '^BACKEND_INVALID_RESPONSE$'):
                await self.invoke('litellm_user_info', None, status=status, content=b'')

    def test_public_schemas_agree_with_cases(self):
        for name, args, valid in INPUT['cases']:
            schema = INPUT['schemas'][name]
            Draft202012Validator.check_schema(schema)
            self.assertEqual(Draft202012Validator(schema).is_valid(args), valid, (name,args))

if __name__ == '__main__': unittest.main(verbosity=2)
