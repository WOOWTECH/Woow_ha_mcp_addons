import test from 'node:test';
import assert from 'node:assert/strict';
import { conditionalWriteSummary } from '../src/contracts.js';

test('條件寫入說明區分相依政策的允許、禁止與未知', () => {
  for (const [policy_enabled, label] of [[true, '允許'], [false, '禁止'], [undefined, '未知']]) {
    const text = conditionalWriteSummary({parameter:'exposeToMcp', requires_tool:'n8n_update_partial_workflow', policy_enabled});
    assert.match(text, /exposeToMcp/);
    assert.match(text, /n8n_update_partial_workflow/);
    assert.match(text, /將工作流程開放給 MCP 存取/);
    assert.ok(text.includes(`相依權限：已儲存政策${label}`));
  }
});
