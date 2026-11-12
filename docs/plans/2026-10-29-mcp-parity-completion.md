# MCP parity completion Implementation Plan

> Execute with the dispatching-parallel-agents and verification-before-completion skills; independent worktrees, main integration and separate spec/code review.

**Goal:** Close the seven remaining MCP feature gaps and the two PaaS template deployment gaps with traceable source, behavior tests and normal release evidence.

**Architecture:** Preserve deployment-specific identity and network boundaries. Use additive optional state with old defaults, explicit management contracts, optimistic concurrency and existing child lifecycle ownership. Published 0.4.5 artifacts are immutable; any new release is independently built from its own checked source.

**Tech Stack:** Python/Pydantic/Starlette, JavaScript management UI and Playwright, pinned n8n Node child, GitHub/Gitea, k3s.

## 1. Existing PaaS release / Linnaeus

- Read latest .279 source, checks, artifact/CD and formal DB/runtime/template receipts in a new followup directory.
- Preserve owner03's release ownership and artifact-specific human approval. Do not create a competing platform release.
- When formal templates match the exact new image and service265 is unchanged, restore only template deployment policy, resolving the same image/chart within the transaction; no redeploy. Read back config, UID, Helm7 and Ready.
- Acceptance: sources, formal templates and runtime are distinguished; if an external release gate is pending, record the exact remaining stage.

## 2. Native n8n inputs / Aristotle

- HA files: `apps/n8n/patches/`, `apps/n8n/backend_policy.cjs`, `apps/n8n/Dockerfile`, focused tests.
- Port the pinned direct-input compatibility call-site from PaaS without replacing HA's error-message/isError patches.
- Retry tagged/untagged inputs only on the native invalid-discriminator validation response, preserve unrelated errors, cache only accepted formats.
- Check PaaS reverse error-message gap and patch if still missing in an independent worktree.
- Acceptance: actual patched child fixtures for both schema profiles, no duplicate request on runtime/backend errors, expected hash chain and error preservation.

## 3. LiteLLM URLs and effects / Boyle

- HA files: product-specific connection validation and vendor registry; separate PaaS corresponding files and focused tests.
- Handle root `/v1` without duplicating API paths; preserve prefixed proxy mount semantics. Main supplies UI help.
- Audit pinned health/token_counter/spend_calculate behavior and align effects based on provider calls/cost, not HTTP verb alone. Preserve explicit grants for operations that may cause effects.
- Acceptance: captured HTTP paths for root, root/v1 and prefixed mounts; denied grant causes zero backend calls, allowed grant dispatches expected request; no paid provider calls.

## 4. Controlled outputSchema / Tesla

- Files: `packages/mcp-admin-core/mcp_admin_core/policy.py`, new reviewed schema module/data, focused tests.
- Expose exact digest-pinned reviewed schemas for useful known tools; retain filtering for unknown/changed/external schemas and existing metadata policies.
- Acceptance: accepted pinned schema and structuredContent compatibility; unknown/external reference refusal; fallback snapshot consistent with actual child.

## 5. n8n session settings / main

- Files: `products.py`, `gateway.py`, `configuration.py`, `apps/n8n/n8n_adapter.py`, UI contracts/app and focused tests.
- Add optional `n8n_session` object, strict `timeout_seconds` 60..86400 and `max_sessions` 1..100. Missing field means prior 600 seconds/20, without rewriting old states. Match PaaS/native timeout parser behavior: round seconds upward to whole minutes and expose the effective minutes.
- Add `PUT /api/n8n/session` requiring current revision; restart only child after durable commit, report application state.
- UI supports save/reload, explains units/defaults; bad values/wrong product/stale revision change nothing.

## 6. Connection credential preservation / main

- Files: new backend-edit contract helper, `gateway.py`, UI contracts/app, API tests and browser cases.
- Keep existing `PUT backend` whole-replace semantics. Add explicit partial edit contract: omitted fields keep values, explicit null clears nullable fields; required credentials cannot be null. Whole disconnection remains explicit.
- Return only nonsecret connection fields and secret-set booleans to management bootstrap. Scope changes (URL/account) must be deliberate and revision checked.
- Acceptance: URL-only edit preserves exact secret bytes, explicit replacement changes only supplied key, optional clearing works, required clearing refuses, no secret in bootstrap/errors, stale/demoted/disconnected requests do not commit.

## 7. Odoo exact method allowlist / main

- Files: `products.py`, `gateway.py`, child env mapping, UI contracts/app, Odoo policy/runtime tests.
- Add optional bounded exact `model.method` list; no wildcards/private methods. Expose current list and edit/save/reload.
- Map to upstream reviewed env allowlist; preserve outer tool grants and the four child switches. Do not confuse allowlisting with disabling existing broad-unknown mode; UI explains effective behavior.
- Acceptance: known exact pair allowed with unknown-method switch off, near match denied, writes/chatter/outer grant still enforced, state persisted across reopen and child restart.

## 8. Integration, review and delivery / main

- Review each feature against its acceptance scope, then code quality; resolve all findings before integration.
- Update runtime provenance hashes/version/upgrade notes once for the integrated result, after all worker commits. Optional new state fields require a pre-upgrade backup to downgrade after saving them.
- Run focused API/state/UI tests followed by repository required checks on the final source. Build/release only through the existing exact-image gates; no reuse of 0.4.5 receipts for new source.
- Validate packaged runtime and isolated HAOS UI/save/restart behavior. Keep original failures/recovery evidence and clean owned fixtures.
- Synchronize published source/images/Store/catalogs and update the guide with actual evidence. A source-only change is not marked deployed.
