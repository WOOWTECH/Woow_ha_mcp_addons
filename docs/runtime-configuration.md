# Saved settings, running settings and active credentials

The authenticated management API adds `configuration` to bootstrap, successful
setting saves and child restart responses. `GET /api/configuration` returns the
same object without replacing an editor's form data. Existing settings, schema4,
full-tool defaults and backend health fields are unchanged.

| Field | Meaning |
| --- | --- |
| `revision` | Opaque revision of the whole editable snapshot, including credential and policy changes. |
| `saved_revision` | Opaque revision of launch-relevant saved settings. Public token and endpoint changes do not change it. Native EMQX, LiteLLM and Nextcloud policies are launch inputs. |
| `applied_revision` | Launch revision verified by a completed protocol probe of the current child generation, or null. |
| `apply_state` | `pending`, `applied`, `failed`, `unconfigured`, or `unknown`. |
| `last_error_code` | Fixed safe failure code, or null; never exception text or a credential. |

Revisions are keyed with a random process-local HMAC key. They disclose neither
raw configuration nor reusable credential hashes. They change across management
process restarts; an editor opened before restart must reload. Application
metadata is not persisted and does not require a schema migration. A child that
has merely spawned is pending. A completed probe from an older generation cannot
apply a newer save. Application is separate from backend reachability and from
the success of any business operation. Token and endpoint updates do not restart
the child. Policy updates retain existing product-specific restart behavior.

Bootstrap's `ETag` is the quoted `configuration.revision` from the same snapshot.
A setting save may send that exact value as `If-Match`. An obsolete or malformed
conditional value returns HTTP409 with `detail.code="config_conflict"` before
any write or child replacement. The condition is checked under the mutation
lock after the final administrator-role verification. Clients omitting the
header retain their prior behavior and do not receive stale-edit protection.

The new UI captures each form's revision when rendering it. Refreshing CSRF or
application status never advances that revision. A conflict preserves the draft
in the current page, disables its save controls, and requires explicit reload
and review before another submission. Reload clears the draft, including secret
fields. Drafts and credentials are not written to browser storage. Old servers
without configuration metadata remain usable, without conditional protection.

A committed backend save whose child replacement fails returns HTTP503 with
`saved:true`, `detail.code="config_apply_failed"`, and configuration status.
The UI explicitly says the settings were saved but not applied. It never retries
the mutation automatically. Reload status, inspect diagnostics, and explicitly
retry child startup if appropriate. Losing a caller after commit does not detach
the owned lifecycle transition or release its mutation lock prematurely.

## Active token revocation

The same shared credential protects Bearer `/mcp` and `/private_<token>/mcp`.
HA exposes no legacy `/sse` or `/messages` transport. The normal token rotate and
revoke APIs publish cancellation only after the durable state update succeeds.
Existing request leases cover request bodies, pending child headers/body reads,
and actual ASGI sends, including backpressure. Rotation and revocation do not
restart the child. A corrupt or externally replaced state also fails closed,
with a bounded fallback check for requests already waiting.

Before response start, revoked access receives the usual Bearer401 or secret-path
404. Once HTTP has started, the gateway closes the connection; it cannot change
the status already sent. No further buffered SSE frame is emitted. Owned child
responses, readers and concurrency slots are closed/joined. A newly initialized
child session whose answer was withheld is ended through the existing bounded
cleanup DELETE. Bytes already delivered and backend work already dispatched
cannot be recalled or rolled back by revocation.

Regression coverage includes two real socket clients (Bearer and secret path),
GET and POST SSE, rotate and revoke, reissue, upstream closure, blocked headers,
blocked send, coalesced frames, all product connection routes, stale concurrent
editors, commit/application failures and browser draft preservation. These are
owned local fixtures, not evidence of HA Ingress or a live third-party backend.
