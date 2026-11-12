# Partial settings management contract

This describes source behavior; publication and installed-runtime acceptance are separate release gates.

## Connection edits

Existing `PUT /api/backend` still replaces the complete connection. New `PUT /api/backend/patch` accepts
`{"changes":{"url":"https://new.example"}}` (Hermes uses `gateway_url`). It operates only on an already
configured backend. Omitted fields retain their exact saved values; optional fields can be explicitly cleared with
`null`. Required credentials cannot be cleared individually; the existing whole-connection clear action is retained.
Unknown fields and empty patches are refused. Hermes dashboard fields still require a complete valid group.

The patch requires the configuration ETag the administrator reviewed (`If-Match`). Role and CSRF are checked by the
same management boundary as other edits. The server validates the merged connection, commits atomically, and owns
the subsequent child restart even when the caller disconnects. A failed application reports `saved:true` with the
existing `config_apply_failed` code; it never reports that the old configuration was restored.

Authorized bootstrap responses expose `backend_edit` with contract `woow-connection-patch-v1`, explicit nonsecret
`values` and per-secret `secret_set` booleans. Passwords, API keys and native tokens are never prefilled. The UI has
per-field keep/set/optional-clear choices. It explains that existing credentials will be used at a changed destination.
This deliberate URL/account change requires the current revision; there is no automatic cross-destination migration.
If a display field contains a configured credential, including reversible percent encoding, its whole value is
withheld as `null` and its name appears in `withheld_fields`. The stored connection is unchanged. Keep preserves
that value; replacing it requires fresh input. A display mask is never sent back as a connection value.

## n8n native sessions

`PUT /api/n8n/session` accepts `{"n8n_session":{"timeout_seconds":600,"max_sessions":20}}` with `If-Match`.
Both fields are required strict JSON integers: timeout 60–86400 seconds, maximum 1–100 sessions. Unknown fields,
null, booleans and string numbers are refused. Other products cannot save this setting.

The pinned child reads integer `SESSION_TIMEOUT_MINUTES`, so seconds are rounded upward to minutes (61 seconds
becomes 2 minutes), matching PaaS conversion. The UI displays the conversion. Native cleanup scheduling can delay
actual eviction beyond this configured idle threshold; this is not a deadline for canceling backend workflow work.
`N8N_MCP_MAX_SESSIONS` receives the saved limit. The gateway's own session bookkeeping remains independent.

Old schema-4 state without `n8n_session` keeps 600 seconds / 20 sessions without being rewritten at startup. Saving
adds an optional strict object. Child application identity includes its effective native values, and saving restarts
the child. Downgrading after saving this optional field requires a compatible pre-upgrade backup; changing only the
schema number is not a supported rollback.

## Odoo exact method list

`PUT /api/odoo/allowed-methods` accepts `{"odoo_allowed_methods":["sale.order.action_confirm"]}` with `If-Match`.
An empty list removes only these explicit exceptions. Up to 128 unique exact public method names, 256 characters
per entry and 16384 serialized bytes are supported. Wildcards and private method names are refused.

The effective list is supplied to the pinned child through its existing `ODOO_MCP_ALLOWED_SIDE_EFFECT_METHODS`
contract. It does not grant the outer `execute_method` permission, bypass the write/chatter switches, or allow
standard create/write/unlink when direct writes are disabled. A broad unknown-method mode still permits other
methods according to existing switches; the UI describes that separately instead of pretending this list restricts it.
Existing states have an empty list without a startup rewrite. Saving this optional field requires a pre-upgrade backup
for subsequent downgrade to a binary that does not recognize it.
