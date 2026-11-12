import test from 'node:test';
import assert from 'node:assert/strict';
import {backendEdit, backendPatchPayload, n8nSession, n8nSessionPayload} from '../src/contracts.js';
import {AdminApi} from '../src/api.js';
const state = {product:'n8n', connection_configured:true, backend_edit:{contract:'woow-connection-patch-v1', values:{url:'http://old.test'}, secret_set:{key:true,mcp_access_token:true}},
  n8n_session:{timeout_seconds:600,max_sessions:20}, n8n_session_source:'legacy_default'};
test('partial editing has explicit keep/set/clear and never echoes existing credentials', () => {
  const keep = {url:'keep',key:'keep',mcp_access_token:'keep'};
  assert(backendEdit(state));
  assert.equal(backendPatchPayload(state,keep,{}),null);
  assert.deepEqual(backendPatchPayload(state,{...keep,url:'set'},{url:'http://new.test/'}), {changes:{url:'http://new.test'}});
  assert.deepEqual(backendPatchPayload(state,{...keep,mcp_access_token:'clear'},{}), {changes:{mcp_access_token:null}});
  assert.deepEqual(backendPatchPayload(state,{...keep,key:'set'},{key:' exact bytes '}), {changes:{key:' exact bytes '}});
  assert.throws(() => backendPatchPayload(state,{...keep,key:'clear'},{}));
  assert.throws(() => backendPatchPayload(state,{...keep,key:'set'},{key:''}));
  assert.equal(backendEdit({...state,backend_edit:{...state.backend_edit, values:{url:'x',key:'secret'}}}),null);
  assert.throws(() => backendPatchPayload({...state,connection_configured:false},keep,{}));
});
test('session contract uses strict bounded integers and exposes old defaults', () => {
  assert.deepEqual(n8nSession(state),{timeout_seconds:600,max_sessions:20});
  assert.deepEqual(n8nSessionPayload(state,{timeout_seconds:'61',max_sessions:'30'}),{n8n_session:{timeout_seconds:61,max_sessions:30}});
  for (const value of ['59','86401','1e3','1.5',' 60']) assert.throws(() => n8nSessionPayload(state,{timeout_seconds:value,max_sessions:'20'}));
  for (const value of ['0','101','true']) assert.throws(() => n8nSessionPayload(state,{timeout_seconds:'600',max_sessions:value}));
  assert.equal(n8nSession({...state,product:'odoo'}),null);
});
test('partial and session APIs cannot mutate without the reviewed configuration revision', async () => {
  const calls=[];
  const api = new AdminApi('',async(url,options) => {
    calls.push({url,options});return new Response(JSON.stringify(url.endsWith('/bootstrap') ? {...state,base_path:'',api_base:'/api',csrf:'synthetic_csrf_1234567890'}:{saved:true}),{status:200});
  });
  for (const op of ['backend/patch','n8n/session']) {
    await assert.rejects(() => api.mutate(op,{}),/缺少設定版本/);
    assert.equal(calls.at(-1).url,'/api/bootstrap');
    await api.mutate(op,{},'c1-'+'a'.repeat(64));
    assert.equal(calls.at(-1).options.method,'PUT');
    assert.equal(calls.at(-1).options.headers['If-Match'],'"c1-'+'a'.repeat(64)+'"');
  }
});

import {odooMethods,odooMethodsPayload} from '../src/contracts.js';
const odoo={product:'odoo',odoo_allowed_methods:[],odoo_allowed_methods_source:'legacy_empty'};
test('Odoo methods require exact unique public pairs and preserve an explicit empty list', () => {
  assert.deepEqual(odooMethods(odoo),[]);
  assert.deepEqual(odooMethodsPayload(odoo,'sale.order.action_confirm\nres.partner.copy'), {odoo_allowed_methods:['sale.order.action_confirm','res.partner.copy']});
  assert.deepEqual(odooMethodsPayload(odoo,''),{odoo_allowed_methods:[]});
  for (const value of ['sale.order.*','res.partner._private','sale.order.action_confirm\nsale.order.action_confirm','action_confirm']) assert.throws(() => odooMethodsPayload(odoo,value));
  assert.equal(odooMethods({...odoo,product:'n8n'}),null);
});
