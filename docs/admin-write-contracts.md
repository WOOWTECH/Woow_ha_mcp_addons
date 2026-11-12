# Admin write contracts (0.4.7 candidate)

## Reviewed configuration

All persisted admin PUTs and owner-default actions require one exact strong `If-Match` returned by bootstrap/configuration. Token rotate/revoke and child restart also require it. Missing revision returns 428 `config_revision_required`; stale, duplicate, weak, wildcard or list values return 409 `config_conflict`, with no new effect. Observation routes (backend test, token reveal) keep their current role/CSRF boundary.

The revision remains process-specific. After restart a new write requires a new reviewed snapshot. A completed operation receipt can be replayed using its original revision because it performs no new effect.

## Durable operations

POST `token/rotate`, `token/revoke`, `child/restart` additionally require `Idempotency-Key` (`<13-digit epoch-ms>.<16–64 URL-safe random characters>`). Bootstrap `operation_contract` version 1 publishes `server_time_ms` and `retention_ms`; use server time to avoid a future timestamp caused by client clock skew. Query with GET `/api/operations/{id}`.

Public operation: `{id, kind, state, replayed}`. Kinds match PaaS `token.rotate`, `token.revoke`, `mcp.restart`. State is `completed` or `unknown`. Completed queries return `{operation, result}` where result contains only fixed non-secret outcome labels. POST replies include `operation`, `status` and the current `configuration`. Revoke now returns JSON 200 (previously empty 204); restart first acceptance remains 202. Rotation's first successful response may include the new token, but completed replay and query never include a token; explicit reveal returns only the current token.

Fresh HA admin authority is checked after the mutation lock is acquired, including replay/query. CSRF remains required on POST. The journal HMAC-binds receipts to the original HA user; another admin receives the same 404 as a missing receipt. Reusing an ID for a different operation is 409 `operation_id_conflict`.

## Failure and recovery boundaries

The private sidecar `.state.json.operations.json` is bounded to 128 receipts and 256 KiB, mode0600, single writer, strict JSON, atomic rename and file/directory fsync. Its intent is durable **before** token persistence or child callback acceptance. Unknown intents never execute again automatically. If the effect completes but its completion receipt cannot be made durable, return 409 `operation_outcome_unknown`. An effect can have happened; do not interpret this as rollback. Journal capacity/corruption/unavailability denies new operations. Old IDs expire after24 hours (410); pruning never makes an expired ID executable again.

This is not an exactly-once transaction with the child process. A crash between intent and completion deliberately leaves uncertainty. Backups must include the entire data directory including the hidden journal. Deleting/restoring older data loses newer receipts; review current state after restore instead of replaying old commands. The state schema remains4; the release integration binds add-on version0.4.7.

## Browser behavior

The tab retains only `{id, route, revision, product}` in sessionStorage, scoped to its ingress mount. No token, backend value, CSRF value or submitted form is persisted there. A failed response preserves that identity across reload. Receipt lookup and resend require an explicit click; resend uses the same ID/revision. Completed replay does not display a historical secret. Ending tracking requires an explicit confirmation that state has been reviewed and does not claim rollback. If browser storage or the operation contract is unavailable, no new token/restart mutation is sent.

## Integration

Main owns version/upgrade notes, runtime provenance ledger, image publication and acceptance. This changes client requirements and revoke response shape; release notes must identify the API change and backup/recovery boundary. Existing state bytes and schema4 are preserved. PaaS uses the same header, ID form, kind names, query path and public state labels; HA additionally binds receipts to its per-user identity. Independent full CI, image and HA ingress acceptance remain separate from the focused source tests.
