import test from 'node:test';
import assert from 'node:assert/strict';
import { granularPolicy, policyPayload, backendPayload } from '../src/contracts.js';
const state = { policy_contract: 'woow-v3-exact-grants', writes_enabled: true, disabled: [], enabled_write_tools: ['mixed:create'], tools: {
  legacy: {write:true, legacy_write:true, write_grants:['legacy'], operation_parameter:null, inputSchema:{}},
  mixed: {write:false, legacy_write:false, write_grants:['mixed:create','mixed:delete'], operation_parameter:'action', inputSchema:{}},
} };
test('real v3 contract replaces every exact grant and disables global authorization', () => {
  assert.equal(granularPolicy(state), true);
  assert.deepEqual(policyPayload(state, [], [{tool:'mixed',operation:'create'}]), {writes_enabled:false,disabled:[],enabled_write_tools:['mixed:create']});
  assert.deepEqual(policyPayload(state, [], []), {writes_enabled:false,disabled:[],enabled_write_tools:[]});
  assert.throws(() => policyPayload({...state,policy_contract:undefined},[],[]));
  assert.throws(() => policyPayload(state,['mixed'],[{tool:'mixed',operation:'create'}]));
  assert.throws(() => policyPayload(state,[],[{tool:'mixed',operation:'unknown'}]));
});
test('Manage mode is explicit read/module, never silently coerced', () => {
  const values={url:'https://backend.example.test',database:'fixture',username:'fixture',api_key:'dummy',mode:'module'};
  assert.equal(backendPayload('odoo-manage','replace',values).connection.mode,'module');
  assert.throws(() => backendPayload('odoo-manage','replace',{...values,mode:'all'}));
});
