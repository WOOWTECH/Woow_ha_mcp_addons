# Fenced session deletion port for the next HA release

Source: PaaS `052887fa68d5e67b86c622ef92f46dd7f75a08ca` (PR99 session CAS and PR100 authentication retry correction). The mutation helper and the `hermes_session` / `_relogin_on_401` function bodies are copied exactly. HA keeps its existing network destination policy, error classification, credential redaction and operation grants.

The published Agent `20261025.0421@sha256:39718ca149934e1c4da240a5f41b53d45e0d5b62dba508b79c32fb0ef1aaf0f0` rejects an unfenced session DELETE with `409 client_upgrade_required`. Deletion now reads a fresh authenticated mutation snapshot and submits one request with a UUID `request_id`, `expected_revision` and `expected_generation`. Successful acknowledgement is followed by an absence snapshot. Missing contracts and malformed or foreign snapshots fail closed; there is no legacy unfenced fallback.

A lost reply, server error or unverifiable acknowledgement reports `SESSION_DELETE_OUTCOME_UNKNOWN` and the exact identity. The adapter neither refreshes fences after conflict nor automatically resends DELETE. An explicit caller replay must provide all three identity fields unchanged; the Agent owns durable receipts and decides replay or conflict, even if the session is already absent.

The HTTP client's `hermes_no_auth_retry` extension prevents the cookie-refresh wrapper from resending this DELETE after401. It is local request metadata, not an HTTP header or query field. This applies to default and explicit identities. Read requests retain at most one cookie refresh. A401 can also follow a committed write: callers must inspect the session; the error is not proof that no write occurred.

The tool count remains11. Session list/get and existing successful deletion shapes are preserved. The three optional recovery fields must be supplied together, only on delete; revision and generation accept nonnegative integers, not booleans or coerced numeric strings. The existing `hermes_session:delete` grant still gates all paths.

## Local validation

The tests use synthetic credentials, the pinned MCP2.3.0 child, the real HA gateway and owned ephemeral HTTP servers. The five auth cases cover read401 then200, read401 twice, default DELETE401, explicit DELETE401, and a committed DELETE whose response is401. Other cases cover denied zero-contact writes, stale fences, malformed/missing contracts, lost replies, explicit identity replay, verified absence and credential redaction. The shared expansion fixture models the same fenced contract.

With the existing locked root and Hermes environments installed, run from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_hermes_session_mutations.py tests/test_hermes_session_child.py \
  tests/test_hermes_parity.py tests/test_hermes_config_redaction.py \
  tests/test_hermes_mcp_url_guard.py tests/test_hermes_chat_timeout.py \
  'tests/test_expansion_runtime.py::test_real_expanded_reads_and_explicit_writes[hermes]' \
  tests/test_raw_backend_errors.py::test_real_hermes_child_reports_status_and_body_of_a_rejected_request \
  tests/test_six_hardening.py::test_hermes_dashboard_login_and_cookie_errors_are_safe \
  'tests/test_tool_snapshot.py::test_snapshot_equals_the_real_child[hermes]' \
  tests/test_tool_snapshot.py::test_snapshot_names_are_the_classified_surface
```

The root session-contract test starts the app interpreter and reuses the root pytest libraries read-only. It verifies all28 ported contract cases ran without skips. No dependency or lockfile change is needed.

## Integration boundary

This source port is based on merged HA0.4.8 commit `0807d4dfb8c2ce958ac052bbe14395c98bd0f298`, with no release version change. It does not establish acceptance of an HA image, HAOS ingress or an external LLM. The existing PaaS actual-Agent receipts are provenance only.

The Hermes entry in `packages/mcp-admin-core/mcp_admin_core/tool_snapshot.py` has been regenerated from the actual child and integrated. Its fallback list exposes the same optional recovery fields and description. All27 integration tests, including equality with the actual child snapshot, passed after rebasing onto HA0.4.8. The embedded contract suite also ran all28 cases without skips.

Publication and actual HAOS acceptance belong to the subsequent release. This port does not change the published0.4.8 images, builder, Docker base or running services.
