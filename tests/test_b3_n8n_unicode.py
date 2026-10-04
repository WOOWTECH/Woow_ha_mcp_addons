"""B3 code-point bounds across public schemas, genuine dispatch and owned HTTP."""
import asyncio
import json

import pytest
from pydantic import ValidationError

from n8n_adapter import TOOLS
from test_batch2_bounds import schema_results
from test_batch2_n8n_public_boundaries import node
import test_batch2_n8n_public_errors as owned
from test_b3_n8n_runtime import backend
from test_expansion_policy import call
from test_real_products import rpc

QUERIES = [
    ('bmp256', '界' * 256, True),
    ('bmp257', '界' * 257, False),
    ('astral128', '𠮷' * 128, True),
    ('astral129', '𠮷' * 129, True),
    ('astral256', '𠮷' * 256, True),
    ('astral257', '𠮷' * 257, False),
    ('mixed256', '界' * 127 + '𠮷' * 129, True),
    ('mixed257', '界' * 128 + '𠮷' * 129, False),
    ('combining256', 'e\u0301' * 128, True),
    ('combining257', 'e\u0301' * 128 + 'e', False),
]


@pytest.mark.parametrize('label,query,valid', QUERIES, ids=[q[0] for q in QUERIES])
def test_b3_unicode_public_contract(label, query, valid):
    model = TOOLS['n8n_list_catalog'].arguments
    schema = model.model_json_schema()
    assert schema['properties']['query']['maxLength'] == 256
    args = {'kind': 'tags', 'query': query}
    assert schema_results(schema, [args]) == [valid]
    if valid:
        assert model.model_validate(args).model_dump()['query'] == query
    else:
        with pytest.raises(ValidationError):
            model.model_validate(args)


@pytest.mark.parametrize('label,query,valid', QUERIES, ids=[q[0] for q in QUERIES])
def test_b3_unicode_private_genuine_dispatch(label, query, valid):
    # Transport stub only: original dispatcher, handler, filter and client run.
    node(r'''
const assert = require('node:assert/strict');
process.env.N8N_API_URL='https://owned.invalid'; process.env.N8N_API_KEY='UNICODE_DUMMY_KEY';
const root='./apps/n8n/node_modules/n8n-mcp/dist/';
const {N8NDocumentationMCPServer}=require(root+'mcp/server.js');
const catalog=require(root+'mcp/handlers-official-tools.js');
const manager=require(root+'mcp/handlers-n8n-manager.js');
const {N8nApiClient}=require(root+'services/n8n-api-client.js');
let handlers=0, clients=0, requests=0, rawQuery;
const handler=catalog.handleListCatalog, native=N8nApiClient.prototype.listTags;
catalog.handleListCatalog=function(args,...rest) {
    handlers++; rawQuery=args.query; return handler.call(this,args,...rest);
};
N8nApiClient.prototype.listTags=function(...args) {clients++;return native.apply(this,args);};
require('./apps/n8n/backend_policy.cjs');
require('node:net').Socket.prototype.connect=function(){throw Error('network forbidden');};
require('node:dns').promises.lookup=async()=>{throw Error('DNS forbidden');};
global.fetch=()=>{throw Error('fetch forbidden');};
N8nApiClient.prototype.getPinnedAgents=async()=>({});
const query=JSON.parse(process.argv[1]), valid=JSON.parse(process.argv[2]);
const client=manager.getN8nApiClient();
client.client.defaults.adapter=async config=>{
    requests++;
    assert.equal(config.url,'/tags'); assert.deepEqual(config.params,{limit:250});
    assert.equal(config.method,'get'); assert.equal(config.timeout,5000);
    assert.equal(config.maxContentLength,65536); assert.equal(config.maxBodyLength,0);
    assert.equal(config.maxRedirects,0); assert.equal(config.__retryCount,client.maxRetries);
    assert(config.signal);
    return {status:200,data:{data:[{id:'tag1',name:query},{id:'other',name:'not matched'}]},headers:{},config};
};
(async()=>{
    const server=Object.assign(Object.create(N8NDocumentationMCPServer.prototype), {
        disabledToolsCache:null, disabledToolOperationsCache:null, additionalToolsByName:new Map(),
    });
    const result=await server.executeTool('n8n_list_catalog',{kind:'tags',query});
    assert.equal(result.success,valid);
    assert.deepEqual([handlers,clients,requests], valid ? [1,1,1] : [0,0,0]);
    if(valid) {
        assert.equal(rawQuery,query);
        assert.deepEqual(result.data,{items:[{id:'tag1',name:query}],scanLimit:250,hasMore:false,scope:'first-page'});
    } else assert.deepEqual(Object.keys(result).sort(),['code','error','success']);
})().catch(e=>{console.error(e);process.exitCode=1;});
''', json.dumps(query), json.dumps(valid))


async def test_b3_unicode_actual_query_boundaries(tmp_path, monkeypatch):
    monkeypatch.setattr(owned, 'backend', backend)
    async with asyncio.timeout(65), owned.runtime(tmp_path) as (_, state, client, headers, wire, dispatches):
        results = []
        for label, query, valid in QUERIES:
            args = {'kind': 'tags', 'query': query, 'limit': 1}
            if not valid:
                before = len(dispatches), len(state['calls'])
                response = await client.post('/mcp', headers=headers, json=call('n8n_list_catalog', args))
                assert response.status_code == 403
                assert (len(dispatches), len(state['calls'])) == before
                continue
            # Both matching and nonmatching use the genuine upstream filter.
            for name, expected in [(query, [{'id': 'tag1', 'name': query}]), ('not matched', [])]:
                state['response'] = {'data': [{'id': 'tag1', 'name': name, 'private': owned.PRIVATE}]}
                before = len(state['calls'])
                reply = await rpc(client, '/mcp', headers, call('n8n_list_catalog', args))
                value = json.loads(reply['content'][0]['text'])
                results.append((label, value.get('success') is True and value.get('data') == {
                    'items': expected, 'scanLimit': 250, 'hasMore': False, 'scope': 'first-page'},
                    state['calls'][before:] == [('GET', '/api/v1/tags', {'limit': ['250']})]))
                assert owned.KEY not in json.dumps(reply) and owned.PRIVATE not in json.dumps(reply)
        # Canonically equivalent text is not normalized: preserve source filtering.
        state['response'] = {'data': [{'id': 'tag1', 'name': 'é' * 128}]}
        reply = await rpc(client, '/mcp', headers, call('n8n_list_catalog', {'kind': 'tags', 'query': 'e\u0301' * 128}))
        assert json.loads(reply['content'][0]['text'])['data']['items'] == []
        assert all(success and one_get for _, success, one_get in results), results
        assert state['keys'] and all(key == owned.KEY for key in state['keys'])
        assert owned.KEY not in b''.join(wire).decode() and owned.PRIVATE not in b''.join(wire).decode()


@pytest.mark.parametrize('kind', ['tag', 'folder'])
async def test_b3_unicode_actual_output_names_and_ascii_guards(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(owned, 'backend', backend)
    async with asyncio.timeout(65), owned.runtime(tmp_path) as (_, state, client, headers, wire, dispatches):
        name, args, path = ('n8n_list_catalog', {'kind': 'tags'}, '/api/v1/tags') if kind == 'tag' else (
            'n8n_manage_folders', {'action': 'get', 'projectId': 'project1', 'folderId': 'folder1'},
            '/api/v1/projects/project1/folders/folder1')
        results = []
        for label, text, valid in QUERIES:
            wire.clear()
            item = {'id': kind + '1', 'name': text, 'private': owned.PRIVATE}
            state['response'] = {'data': [item]} if kind == 'tag' else item
            before = len(state['calls'])
            reply = await rpc(client, '/mcp', headers, call(name, args))
            value = json.loads(reply['content'][0]['text'])
            assert state['calls'][before:] == [('GET', path, {'limit': ['250']} if kind == 'tag' else {})]
            results.append((label, value['success'] == valid))
            if value['success']:
                projected = value['data']['items'][0] if kind == 'tag' else value['data']
                assert projected == {'id': kind + '1', 'name': text, **({'projectId': 'project1'} if kind == 'folder' else {})}
            else:
                owned.error_result(reply, wire, 'BACKEND_INVALID_RESPONSE')
        # The shared text counter must not broaden ASCII identifiers/cursors,
        # timestamps, control-character or sensitive-literal output checks.
        for field, bad in [('id', '𠮷'), ('id', '界' * 128), ('name', 'bad\x00name'),
                           ('name', owned.KEY), ('createdAt', '𠮷')]:
            if kind == 'tag' and field == 'createdAt':
                continue  # tag timestamps are not projected
            wire.clear()
            item = {'id': kind + '1', 'name': 'Safe', field: bad}
            state['response'] = {'data': [item]} if kind == 'tag' else item
            reply = await rpc(client, '/mcp', headers, call(name, args))
            owned.error_result(reply, wire, 'BACKEND_INVALID_RESPONSE')
        if kind == 'tag':
            wire.clear()
            state['response'] = {'data': [], 'nextCursor': '𠮷'}
            reply = await rpc(client, '/mcp', headers, call(name, args))
            owned.error_result(reply, wire, 'BACKEND_INVALID_RESPONSE')
        assert all(success for _, success in results), results


def test_b3_unicode_private_ascii_inputs_still_denied():
    node(r'''
const assert=require('node:assert/strict');
const {N8NDocumentationMCPServer}=require('./apps/n8n/node_modules/n8n-mcp/dist/mcp/server.js');
let calls=0;
N8NDocumentationMCPServer.prototype.executeTool=async()=>{calls++;throw Error('must not dispatch');};
require('./apps/n8n/backend_policy.cjs');
(async()=>{
    for(const value of ['𠮷','界'.repeat(128),'𠮷'.repeat(128)]) {
        for(const key of ['workflowId','projectId','cursor']) {
            const result=await N8NDocumentationMCPServer.prototype.executeTool.call({},'n8n_executions',{action:'list',[key]:value});
            assert.equal(result.success,false);
        }
        const result=await N8NDocumentationMCPServer.prototype.executeTool.call({},'n8n_manage_folders',{action:'get',projectId:'project1',folderId:value});
        assert.equal(result.success,false);
    }
    assert.equal(calls,0);
})().catch(e=>{console.error(e);process.exitCode=1;});
''')
