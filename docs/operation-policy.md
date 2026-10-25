# Operation restrictions

Schema 4 adds `denied_operations`, a map of tool names to nonempty lists of
operation names, defaulting to `{}`. Existing schema-4 state receives only this
default at startup; saved grants, whole-tool disables, connections and tokens are
retained. Missing other required fields and malformed deny maps are rejected.
Stale tool/operation names remain stored. Maps are limited to 256 tools, 128
unique operations per tool, 128-character names, and 16 KiB of compact JSON.

The admin `PUT /api/policy` accepts the existing `writes_enabled`, `disabled`, and
optional `enabled_write_tools`, plus optional `denied_operations`:

```json
{
  "writes_enabled": false,
  "disabled": [],
  "enabled_write_tools": ["n8n_executions:delete"],
  "denied_operations": {"n8n_executions": ["get"]}
}
```

Omission preserves saved denies. A supplied map replaces them; `{}` clears them.
New entries must match the registry's audited `Tool` operations. Previously
saved stale entries may be retained or removed, but cannot be added anew. Denies
never supply a write grant. Whole-tool disabling continues to override calls.

Bootstrap returns the saved map and each tool's audited `operations` (name/write),
`operation_parameter`, and `default_operation`. Capabilities advertises
`operation_denies` when storage supports it and includes operation policy/effective
states and counts. An unobserved child has unknown effective counts, never zero.
Tools with no permitted audited operations are excluded from filtered tools/list.

Calls use only the audited selector/default from Tool/surface, not inferred enums
from a child schema. For tools with a nonempty deny list, missing required,
unknown, null, and non-string selectors are refused before dispatch. A known
omitted default is checked exactly as an explicit selector. Unrestricted calls
retain the existing child-validation/write-grant behavior. Both Bearer and private
token paths share authorization; refused calls return the existing JSON-RPC
`Operation not permitted` error without contacting a JSON or SSE child. No legacy
SSE endpoints are added.

The UI edits read/write denies separately from write grants and preserves stale
denies on unrelated saves. It displays stored grants even when an operation deny
makes them ineffective. Clearing a deny does not create a missing grant.

For n8n, `exposeToMcp=true` on `n8n_workflow_versions` or `n8n_test_workflow`
can persistently enable a workflow's "Available in MCP" setting. It additionally
requires the existing `n8n_update_partial_workflow` grant with that tool enabled
and not denied. Normal history reads with exposure omitted/false remain available;
the test-workflow tool still needs its own grant. Capabilities reports this as
`conditional_writes`, without adding a grant or disabling the whole read tool.
The existing UI write grant for `n8n_update_partial_workflow` controls this
dependency; no new grant control or automatic grant is introduced.
The legacy `writes_enabled` switch alone cannot authorize this write.

For all 28 n8n tools, the gateway follows the pinned child's one-level JSON
`output` extraction before checking operation grants/denies and forwarding the
same effective arguments. This prevents an outer read selector from hiding an
inner write selector. The two exposure tools also follow the child's trimmed
`"true"`/`"false"` flag conversion. A second eligible output wrapper is refused
as ambiguous. Authorization is idempotent; encoded request byte/element/depth
limits still apply first.
There are still 28 tools/33 write grants, and fresh all-on keeps all features.
Schema 4, saved grants, tokens and backend fields are unchanged; no auto-grant or
state migration occurs. Reverting the binary also reverts this security guard.

Legacy schema-2/3 automatic `all_on` migration validates the original record before
clearing disables and denies and reseeding grants; retired Odoo Manage retains its
policy. Schema 1 has no deny field. The separate upgrade review gate and offline
migration/recovery adaptation are owned by the root batch3 work, not this change.

## n8n 條件寫入的畫面說明

工具權限頁直接使用能力快照的 `conditional_writes`，在
`n8n_workflow_versions`、`n8n_test_workflow` 顯示「含條件寫入」與相依工具。
`exposeToMcp` 正規化後為 `true` 會額外將工作流程設為可由 MCP 存取；
即使所選操作是讀取，仍須明確授權 `n8n_update_partial_workflow`，且該工具
未停用、沒有禁止操作。`false` 或省略只略過這項額外檢查，原工具與所選操作
仍須授權，尤其 `n8n_test_workflow` 的自身 grant 不可省略。

「相依權限：已儲存政策允許／禁止／未知」只描述既有相依工具政策，
不代表完整呼叫、子行程或後端帳號已可用。未儲存的勾選不提前變成允許；
儲存成功後依伺服器回讀立即更新，對新呼叫生效。未知狀態不會從 schema、
子行程清單或草稿推測。既有精確 grant、操作限制、全功能出廠預設、CSRF、
設定版本檢查與 Ingress 路徑保持不變，沒有新增 `expose` grant 或自動授權。

瀏覽器測試 `conditional-writes.spec.mjs` 使用隔離本地 fixture 驗證兩個工具、
允許／禁止／未知、儲存與失敗草稿、既有 grant／限制及 320／360／1440px。
正式 guard 與 28 工具／33 grant 預設由 `test_n8n_exposure_policy.py` 驗證；
這些本地測試不代表線上 HA 或 n8n 實測。
