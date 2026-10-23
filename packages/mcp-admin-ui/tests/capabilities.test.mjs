import test from 'node:test';
import assert from 'node:assert/strict';
import { AdminApi } from '../src/api.js';
import { catalogSummary, environmentLabels, policySummary } from '../src/contracts.js';

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
  const api=new AdminApi('/mount', async (path, options) => {
    calls.push({path,options});
    return new Response(JSON.stringify(path.endsWith('bootstrap') ? {product:'n8n',base_path:'/mount',api_base:'/mount/api',csrf:'fresh_csrf_value_1234'} :
      operation === 'backend/test' ? {tested_configuration:'saved'} : {accepted:true,apply_state:'pending'}), {status:200});
  });
  await api.mutate(operation, {password:'SHOULD_NOT_SEND'});
  assert.equal(calls.length,2);
  assert.equal(calls[1].options.method,'POST');
  assert.equal(calls[1].options.headers['X-CSRF-Token'],'fresh_csrf_value_1234');
  assert.equal(calls[1].options.body, undefined);
});
