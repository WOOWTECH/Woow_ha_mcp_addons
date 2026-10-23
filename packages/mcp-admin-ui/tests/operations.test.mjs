import test from 'node:test';
import assert from 'node:assert/strict';
import { operationPolicy, toolRows, savedGrant, effectiveGrant, policyPayload, policyFingerprint, policySummary } from '../src/contracts.js';

const state = {
  product: 'n8n', policy_contract: 'woow-v3-exact-grants', writes_enabled: false,
  disabled: [], enabled_write_tools: ['mixed:delete'], denied_operations: { mixed: ['get', 'delete', 'retired'], removed: ['old'] },
  tools: {
    mixed: { write: false, legacy_write: false, write_grants: ['mixed:delete'], operation_parameter: 'action', default_operation: 'list',
      operations: [{name: 'list', write: false}, {name: 'get', write: false}, {name: 'delete', write: true}],
      inputSchema: {properties: {irrelevant: {enum: ['not_an_operation']}}} },
  },
};
test('audited read denies, saved grants, effective state, and fingerprints are independent', () => {
  assert.equal(operationPolicy(state), true);
  const row = toolRows(state)[0];
  assert.deepEqual(row.auditedOperations.map(op => op.name), ['list', 'get', 'delete']);
  assert.equal(savedGrant(state, row, 'delete'), true);
  assert.equal(effectiveGrant(state, row, 'delete'), false);
  assert.match(policySummary(state), /0 \/ 1/);
  assert.match(policySummary(state), /已禁止 4 項操作/);
  assert.notEqual(policyFingerprint(state), policyFingerprint({...state, denied_operations: {}}));
});
test('omitted selection preserves every deny; edits preserve stale restrictions without granting writes', () => {
  assert.deepEqual(policyPayload(state, [], []).denied_operations, state.denied_operations);
  const payload = policyPayload(state, [], [{tool:'mixed', operation:'delete'}], [{tool:'mixed', operation:'get'}]);
  assert.deepEqual(payload.denied_operations, {mixed:['retired', 'get'], removed:['old']});
  assert.deepEqual(payload.enabled_write_tools, ['mixed:delete']);
  const cleared = policyPayload(state, [], [], []);
  assert.deepEqual(cleared.denied_operations, {mixed:['retired'], removed:['old']});
  assert.deepEqual(cleared.enabled_write_tools, []);
  assert.throws(() => policyPayload(state, [], [], [{tool:'mixed', operation:'not_an_operation'}]));
});
test('whole-tool disable retains operation restrictions', () => {
  assert.deepEqual(policyPayload(state, ['mixed'], [], [{tool:'mixed',operation:'get'}]).denied_operations,
    {mixed:['retired', 'get'], removed:['old']});
});
test('malformed operation contract blocks saves; old servers retain their original request shape', () => {
  for (const denied_operations of [null, [], {mixed:'get'}, {mixed:[null]}, {mixed:['get','get']}]) {
    const broken = {...state, denied_operations};
    assert.equal(operationPolicy(broken), false);
    assert.throws(() => policyPayload(broken, [], []));
  }
  const old = structuredClone(state);
  delete old.denied_operations;
  assert.equal(operationPolicy(old), false);
  assert.equal(Object.hasOwn(policyPayload(old, [], []), 'denied_operations'), false);
});
