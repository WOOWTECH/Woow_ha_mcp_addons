# Admin write contracts implementation plan

**Goal:** Require the reviewed configuration revision for every persisted admin mutation; durably identify token rotate/revoke and child restart attempts.

**Architecture:** The existing single-writer Store and gateway mutation lock own a private atomic operation journal. An intent precedes its effect; incomplete intents remain unknown and cannot repeat. The UI retains only non-secret operation identity across a tab reload and offers authenticated receipt lookup.

**Tech stack:** Python/Starlette, atomic fsync/rename persistence, existing vanilla JavaScript UI, pytest and Node/browser tests.

## Steps

1. Add `mcp_admin_core/operations.py` and `tests/test_admin_operations.py`: bounded private journal, strict decoding, actor/payload binding, expiry, replay, crash and disk failure tests.
2. Update `gateway.py`: mandatory exact If-Match on persisted writes; fresh role checks before query/replay; durable token/restart intents; no historical secret in receipts. Preserve cancellation ownership and unknown outcomes.
3. Update `mcp-admin-ui/src/api.js` and `app.js`: revision on token mutations, Idempotency-Key, session-scoped pending identity, explicit lookup/retry with the same ID, fixed errors and no automatic mutation replay. Update fixture contracts and focused tests.
4. Run focused gateway/auth/lifecycle tests plus UI unit/browser coverage; update old positive-test requests to the mandatory contract without weakening negative checks. Document compatibility, restore boundaries and runtime hash changes for main's ledger/version integration.

## Wire contract shared with the PaaS owner

- Header `Idempotency-Key`: 13-digit epoch milliseconds + `.` + 16–64 URL-safe random characters. Server bootstrap publishes time to avoid client clock skew.
- Kinds `token.rotate`, `token.revoke`, `mcp.restart`; GET `/api/operations/{id}`.
- Public receipt `{id, kind, state: completed|unknown, replayed}`. Query body `{operation, result}`; result contains fixed, non-secret status only.
- Fresh mutation: mandatory exact If-Match; missing = 428, stale/multiple/wildcard = 409. Observation/reveal are not persisted mutations.
- Same ID + same operation returns its completed receipt without repeating effects, even after revision change/process restart. Incomplete receipt = 409 operation_outcome_unknown. Changed kind/payload = 409 operation_id_conflict. Old IDs = 410; missing = 428; malformed = 400.
- Every path revalidates current admin authority. HA additionally HMAC-binds receipts to the HA user; a different admin sees 404. Completed replay never returns a token. First successful rotation may return it; explicit reveal reads only the current token.
- 24-hour retention, 128 receipts, fail closed at capacity/corruption. Restoring an older/deleted data directory cannot preserve newer receipts; it requires reviewing live state, not blindly replaying old operations. No exactly-once claim across disk loss/restore.

No version, image, runtime ledger, publication, production or website edits.
