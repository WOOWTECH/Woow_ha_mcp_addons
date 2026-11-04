# HA MCP 0.4.10 Release Candidate Implementation Plan

This earlier local-candidate plan is retained for the version-binding audit. The active release decision is [release-decision-0.4.10.md](../operations/release-decision-0.4.10.md); it supersedes the local-only stop after the candidate was rebased onto merged PR #48, #49 and #50.

**Goal:** Prepare a reviewable 0.4.10 candidate that includes the merged Odoo read-error/result-size, Odoo output-schema, n8n output-schema and Hermes output-schema corrections, without modifying the 0.4.9 evidence.

**Architecture:** Start from the verified `claude-delivery` merge `cc7844780d7f054ae8ea1593537634e283edd78f`. Change only the version bindings, per-product release notes, the core-version and n8n output-registry source-binding hashes, and a pending release decision. The six enabled products need fresh images from the eventual exact candidate commit; OpenDesign stays disabled and Odoo Manage remains archived.

**Tech Stack:** Git worktree, Python 3.13, uv, PyYAML, unittest/pytest, Home Assistant Supervisor add-on manifests, GitHub Actions YAML.

---

### Task 1: Bind the local candidate

**Files:** seven `addons/*/config.yaml`, seven `apps/*/Dockerfile`, `packages/mcp-admin-core/mcp_admin_core/__init__.py`, `packaging/inputs.json`, `packaging/validate.py`, `.github/workflows/ci.yaml`, `.github/workflows/release.yaml`.

1. Confirm the release commit is based on the specified merge before changing files.
2. Replace the exact `0.4.9` version bindings in those files with `0.4.10`; preserve all manifest permissions, architectures, image repository names, options, dependency locks and base digests.
3. Run `python packaging/validate.py`; expected: the strict seven-manifest and version checks pass.

### Task 2: Keep provenance and user-facing state truthful

**Files:** `docs/provenance/runtime-patches.json`, `CHANGELOG.md`, `README.md`, seven `addons/*/CHANGELOG.md`, `docs/operations/release-decision-0.4.10.md`.

1. Recompute the core `__init__.py` SHA-256 ledger entry after changing `VERSION` and repin the n8n registry's source Dockerfile and guarded registry hashes after changing the versioned Dockerfile. Check every other ledger file digest against the worktree.
2. Describe the Odoo read-error propagation and default 2 MiB generic-read result bound, Odoo's 41 gateway output schemas, n8n's corrected workflow validator output schemas, and Hermes's 11 reviewed gateway/fallback output schemas. Label all 0.4.10 image, Store and HAOS claims **pending**. Never copy a 0.4.9 image digest into a 0.4.10 claim.
3. Record exact future gates and stop conditions: candidate source checks and upgrade comparison; six fresh linux/amd64 private-builder P1–P5 checks; accepted-ID-only publication; independent anonymous immutable readback and fresh layer/diffID verification; provenance; readiness; protected merge; Stable Release/Store readback; isolated HAOS/backend acceptance.

### Task 3: Verify the local candidate and freeze evidence

**Files:** local validation receipt outside the tracked release record.

1. Run strict packaging validation and the packaging unittest suite; run focused Odoo read-size and runtime-ledger tests with the pinned local dependencies. Run `git diff --check` and a mechanical diff audit confirming no runtime source, permission, lock, base digest or existing image receipt changed.
2. Record the observed commands, exits, test counts, base merge, candidate Git tree/commit, source hashes and all unexecuted gates. If the exact source is later changed, rerun source checks and build fresh images.
3. Continue through the gates in the active release decision; this historical local-only stop no longer applies.
