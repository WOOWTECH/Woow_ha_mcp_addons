import test from 'node:test';
import assert from 'node:assert/strict';
import { AdminApi } from '../src/api.js';
import { catalogSummary, operationSummary, environmentLabels, policySummary } from '../src/contracts.js';

test('operation totals distinguish catalog, saved policy, observed zero, and unknown effectiveness', () => {
  const catalog = {catalog_count:3, policy_enabled_count:2, effective_count:2,
    operation_count:4, policy_enabled_operation_count:1, effective_operation_count:1};
  assert.equal(catalogSummary(catalog), '目錄 3 · 政策允許 2 · 子行程有效 2；操作目錄 4 · 已儲存政策允許 1 · 子行程有效 1');
  assert.match(catalogSummary({...catalog, effective_operation_count:null}), /操作目錄 4 · 已儲存政策允許 1 · 子行程有效 未知$/);
  assert.match(catalogSummary({...catalog, effective_operation_count:0}), /操作目錄 4 · 已儲存政策允許 1 · 子行程有效 0$/);
  assert.equal(catalogSummary({catalog_count:3, policy_enabled_count:2, effective_count:null}), '目錄 3 · 政策允許 2 · 子行程有效 未知');
});

test('operation effectiveness is displayed independently of saved policy, with null or absent as unknown', () => {
  const operation = {name:'list', write:false, policy_enabled:true};
  assert.equal(operationSummary({...operation, effective:true}), 'list · 讀取 · 已儲存政策允許 · 子行程有效');
  assert.equal(operationSummary({...operation, effective:false}), 'list · 讀取 · 已儲存政策允許 · 子行程未生效');
  for (const effective of [null, undefined]) {
    assert.equal(operationSummary({...operation, effective}), 'list · 讀取 · 已儲存政策允許 · 子行程有效狀態未知');
  }
  assert.equal(operationSummary({name:'delete', write:true, policy_enabled:false, effective:false}),
    'delete · 寫入 · 已儲存政策禁止 · 子行程未生效');
});

test('unknown counts and deployment labels do not imply read-only or HA authority', () => {
  assert.match(catalogSummary({catalog_count:11,policy_enabled_count:9,effective_count:null}), /未知/);
  assert.equal(environmentLabels({deployment:{kind:'builtin'},admin:{authority:'paas-password'}}).authority, 'PaaS 管理授權');
  assert.match(policySummary({disabled:[],writes_enabled:true,enabled_write_tools:['mixed:write'],tools:{
    legacy:{write:true,legacy_write:true,write_grants:['legacy']},
    mixed:{write:false,legacy_write:false,write_grants:['mixed:write'],operation_parameter:'action'},
  }}), /2 \/ 2/);
});
for (const operation of ['backend/test', 'child/restart']) test(`${operation} requires fresh CSRF and sends no form values`, async () => {
  const calls=[];
  const data=new Map();const storage={getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};
  const api=new AdminApi('/mount', async (path, options) => {
    calls.push({path,options});
    return new Response(JSON.stringify(path.endsWith('bootstrap') ? {product:'n8n',base_path:'/mount',api_base:'/mount/api',csrf:'fresh_csrf_value_1234',operation_contract:{version:1,server_time_ms:Date.now()}} :
      operation === 'backend/test' ? {tested_configuration:'saved'} : {status:'ok',operation:{id:options.headers['Idempotency-Key'],kind:'mcp.restart',state:'completed',replayed:false},accepted:true,apply_state:'pending'}), {status:200});
  },storage);
  await api.mutate(operation, {password:'SHOULD_NOT_SEND'}, 'c1-'+'a'.repeat(64));
  assert.equal(calls.length,2);
  assert.equal(calls[1].options.method,'POST');
  assert.equal(calls[1].options.headers['X-CSRF-Token'],'fresh_csrf_value_1234');
  assert.equal(calls[1].options.body, undefined);
});
