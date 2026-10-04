"""Pinned-handler identity, auxiliary no-I/O, and private dispatcher guards."""
import json
import pytest
from test_batch2_n8n_public_boundaries import node
from test_b3_n8n_policy import CASES, BAD


@pytest.mark.parametrize('source', ['mcp/handlers-official-tools.js', 'mcp/official-mcp-access.js',
                                    'utils/npm-version-checker.js'])
def test_b3_guard_before_loading(source):
    node(r'''
const assert = require('node:assert/strict'), fs = require('node:fs'), Module = require('node:module');
const read = fs.readFileSync, load = Module._load;
let loads = 0;
Module._load = function(name,...args) {
    if (/n8n-mcp\/dist\//.test(String(name)) || String(name).endsWith('metadata_reads.cjs')) loads++;
    return load.call(this,name,...args);
};
fs.readFileSync = function(file,...args) {
    return String(file).endsWith(process.argv[1]) ? Buffer.from('drift') : read.call(this,file,...args);
};
assert.throws(() => require('./apps/n8n/backend_policy.cjs'), /requires source review/);
assert.equal(loads,0);
''', source)


def test_b3_genuine_health_identity_auxiliary_no_io():
    node(r'''
const assert = require('node:assert/strict');
process.env.N8N_API_URL = 'https://owned.invalid';
process.env.N8N_API_KEY = 'B3_DUMMY_KEY';
const root = './apps/n8n/node_modules/n8n-mcp/dist/';
const handlers = require(root+'mcp/handlers-n8n-manager.js');
const npm = require(root+'utils/npm-version-checker.js');
const official = require(root+'mcp/official-mcp-access.js');
const {N8nApiClient} = require(root+'services/n8n-api-client.js');
const axios = require('./apps/n8n/node_modules/axios');
let handlerCalls=0, nativeCalls=0, versionCalls=0, npmCalls=0, officialCalls=0, fetchCalls=0, dnsCalls=0, connects=0, requests=[];
const handler = handlers.handleHealthCheck, native = N8nApiClient.prototype.healthCheck;
handlers.handleHealthCheck = function(...args) {handlerCalls++; return handler.apply(this,args);};
N8nApiClient.prototype.healthCheck = function(...args) {nativeCalls++; return native.apply(this,args);};
const version = N8nApiClient.prototype.getVersion;
N8nApiClient.prototype.getVersion = function(...args) {versionCalls++; return version.apply(this,args);};
const npmOriginal = npm.checkNpmVersion, officialOriginal = official.buildOfficialMcpHealth;
npm.checkNpmVersion = function(...args) {npmCalls++; return npmOriginal.apply(this,args);};
official.buildOfficialMcpHealth = function(...args) {officialCalls++; return officialOriginal.apply(this,args);};
global.fetch = () => {fetchCalls++; throw Error('foreign fetch');};
require('node:dns').promises.lookup = async () => {dnsCalls++; throw Error('DNS forbidden');};
require('node:net').Socket.prototype.connect = function() {connects++; throw Error('connect forbidden');};
// Transport-only stub: the actual pinned handler and client health implementation run.
axios.get = async (url,options) => {requests.push(url); assert.equal(options.maxRedirects,0); return {status:200,data:{status:'ok',private:'B3_DUMMY_KEY'}};};
require('./apps/n8n/backend_policy.cjs');
N8nApiClient.prototype.getPinnedAgents = async () => ({});
(async () => {
    const result = await handlers.handleHealthCheck();
    assert.deepEqual(result,{success:true,data:{status:'ok',scope:'service-availability',authentication:'not-verified'}});
    assert.equal(handlerCalls,1); assert.equal(nativeCalls,1);
    assert.deepEqual(requests,['https://owned.invalid/healthz']);
    assert.deepEqual([versionCalls,npmCalls,officialCalls,fetchCalls,dnsCalls,connects],[0,0,0,0,0,0]);
})().catch(e => {console.error(e); process.exitCode=1;});
''')


@pytest.mark.parametrize('name,args', CASES)
def test_b3_private_dispatch_bad_args_no_handler(name,args):
    # Folder unsupported branches stay the existing parent's responsibility;
    # test the new get branch here rather than changing old native actions.
    bad = [{**args,**change} for change in BAD[name]
           if name != 'n8n_manage_folders' or 'action' not in change]
    node(r'''
const assert = require('node:assert/strict');
const root = './apps/n8n/node_modules/n8n-mcp/dist/';
const {N8NDocumentationMCPServer} = require(root+'mcp/server.js');
let calls=0;
N8NDocumentationMCPServer.prototype.executeTool = async () => {calls++; throw Error('must not dispatch');};
require('./apps/n8n/backend_policy.cjs');
(async () => {
    for (const args of JSON.parse(process.argv[2])) {
        const result = await N8NDocumentationMCPServer.prototype.executeTool.call({},process.argv[1],args);
        assert.equal(result.success,false);
        assert.deepEqual(Object.keys(result).sort(),['code','error','success']);
    }
    assert.equal(calls,0);
})().catch(e => {console.error(e); process.exitCode=1;});
''', name,json.dumps(bad))


@pytest.mark.parametrize('name,args', [case for case in CASES if case[0] != 'n8n_health_check'])
def test_b3_handler_client_identity_and_bounded_transport(name,args):
    node(r'''
const assert = require('node:assert/strict');
process.env.N8N_API_URL='https://owned.invalid'; process.env.N8N_API_KEY='B3_DUMMY_KEY';
const root='./apps/n8n/node_modules/n8n-mcp/dist/';
const manager=require(root+'mcp/handlers-n8n-manager.js'), catalog=require(root+'mcp/handlers-official-tools.js');
const {N8nApiClient}=require(root+'services/n8n-api-client.js');
const name=process.argv[1], args=JSON.parse(process.argv[2]);
const [module,handler,method]= {
 n8n_list_catalog:[catalog,'handleListCatalog','listTags'], n8n_executions:[manager,'handleListExecutions','listExecutions'],
 n8n_health_check:[manager,'handleHealthCheck','healthCheck'], n8n_manage_folders:[manager,'handleGetFolder','getFolder']
}[name];
const genuineHandler=module[handler], genuineClient=N8nApiClient.prototype[method];
let handlers=0,clients=0,requests=0;
module[handler]=function(...args){handlers++;return genuineHandler.apply(this,args);};
N8nApiClient.prototype[method]=function(...args){clients++;return genuineClient.apply(this,args);};
require('./apps/n8n/backend_policy.cjs');
N8nApiClient.prototype.getPinnedAgents=async()=>({});
const client=manager.getN8nApiClient();
client.client.defaults.adapter=async config=>{
 requests++;
 assert.equal(config.timeout,5000); assert.equal(config.maxContentLength,65536);
 assert.equal(config.maxRedirects,0); assert.equal(config.__retryCount,client.maxRetries);
 assert(config.signal);
 let data;
 if(name==='n8n_list_catalog'){assert.equal(config.url,'/tags');assert.deepEqual(config.params,{limit:250});data={data:[{id:'tag1',name:'Useful'}],nextCursor:'NEXT=='};}
 else if(name==='n8n_executions'){assert.equal(config.url,'/executions');assert.equal(config.params.includeData,false);assert.equal(config.params.limit,20);data={data:[{id:'e1',workflowId:'w1',status:'success'}]};}
 else {assert.equal(config.url,'/projects/project1/folders/folder1');data={id:'folder1',name:'Useful'};}
 return {status:200,data,headers:{},config};
};
(async()=>{
 const result=await module[handler](args);
 assert.equal(result.success,true);assert.equal(handlers,1);assert.equal(clients,1);assert.equal(requests,1);
})().catch(e=>{console.error(e);process.exitCode=1;});
''', name,json.dumps(args))
