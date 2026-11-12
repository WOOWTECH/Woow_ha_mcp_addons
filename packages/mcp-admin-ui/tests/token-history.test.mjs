import test from 'node:test';
import assert from 'node:assert/strict';
import {maskedCurrentToken, tokenHistory} from '../src/contracts.js';

const event = {action:'rotate', rotated_at:'2026-10-29T00:00:00+00:00',
  previous_token_masked:'Ab12' + '*'.repeat(20) + 'xy_9'};

test('history supports older HA servers and accepts only bounded masked events', () => {
  assert.deepEqual(tokenHistory({}), []);
  assert.deepEqual(tokenHistory({token_history:[event]}), [event]);
  for (const value of [null, {}, [event,event,event,event,event,event],
    [{...event, previous_token_masked:'A'.repeat(43)}], [{...event, token:'A'.repeat(43)}],
    [{...event, action:'set'}], [{...event, rotated_at:'2026-10-29T08:00:00+08:00'}]]) {
    assert.equal(tokenHistory({token_history:value}), null);
  }
});

test('current token mask accepts only a masked value', () => {
  assert.equal(maskedCurrentToken({}), null);
  assert.equal(maskedCurrentToken({token_masked:event.previous_token_masked}), event.previous_token_masked);
  assert.equal(maskedCurrentToken({token_masked:''}), '');
  assert.equal(maskedCurrentToken({token_masked:'A'.repeat(43)}), null);
});
