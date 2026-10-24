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

Legacy schema-2/3 automatic `all_on` migration validates the original record before
clearing disables and denies and reseeding grants; retired Odoo Manage retains its
policy. Schema 1 has no deny field. The separate upgrade review gate and offline
migration/recovery adaptation are owned by the root batch3 work, not this change.
