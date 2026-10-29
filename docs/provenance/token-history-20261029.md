# HA token history parity: source-only candidate

The PaaS #89 token panel already shows a masked current token and five recent masked changes. HA 0.4.2 and the
pending 0.4.3 source show only an active/revoked flag. This branch adds the masked display to the HA Ingress panel,
using the existing role/CSRF checks and the existing single-writer atomic state file.

## State and rollback contract

- An existing schema 4 state is not rewritten at startup. `token_history` is absent until a rotate or revoke.
- Each event contains exactly `action`, `rotated_at` (canonical UTC second) and `previous_token_masked` (first four,
  20 asterisks, last four, or empty after a prior revoke). The list is capped at five. The state decoder rejects
  plaintext, unknown fields, malformed times and oversized history without repairing or rewriting the file.
- The token and event are committed by one `Store.update`. Request leases are invalidated only after that durable
  commit; a failed write does not create an event. A repeated revoke is idempotent and does not alter file bytes.
- A 0.4.5 or older binary will reject the optional key after it is written. The planned 0.4.6 upgrade notes require
  a pre-update add-on backup for downgrade. The release train must amend these version numbers if release order
  changes; no source-only branch is a published image.

## Verification

- `tests/test_token_history.py` covers startup bytes, bounded events, idempotent revoke, malformed input, injected
  durable-write failure and authenticated bootstrap redaction.
- `packages/mcp-admin-ui/tests/token-history.test.mjs` covers old-server compatibility and exact mask validation.
- The existing owner-defaults, migration preview, Odoo switch and active-lease tests are the regression gate for
  the shared state and token behavior. No production token or HAOS add-on is changed by this source branch.
