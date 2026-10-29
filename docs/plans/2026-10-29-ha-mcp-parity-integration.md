# HA MCP 0.4.4 Release Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prepare one draft 0.4.4 release candidate combining PR30, PR31, PR32 and PR33 on the exact PR29 0.4.3 base, without publishing, merging or changing those PRs.

**Architecture:** Start a clean worktree from `a3030679f69b6b68266e9a0f98a46b14b88a479e`. Apply only committed changes through PR30 `23574112a9a6528d54c37088e32dc3de1094f2d6`, PR31 `0704c9a3ca23952be3901edd39cd7e5b0b4e5ee1`, the PR32-only delta ending at `ca064c2ab05d852a3c0e29001c9763997bc86dde`, and PR33 `d81bc7c578746b0a94ea762e103db81b7d101f30`. Before the candidate commit, move the integration parent to protected merge `f378a7752538d0cdbf2a23db4af3dfb7ceee0e39` only after verifying its tree equals PR29. Review shared-file conflicts, record exact provenance differences and retain the 0.4.3 release artifacts as historical evidence.

**Tech Stack:** Python 3.13, pinned MCP/Odoo runtime, Node UI tests, Playwright Chromium, Git worktrees.

---

### Task 1: Verify and integrate fixed sources

- Read repository AGENTS.md and remote PR metadata; verify all four full commit IDs.
- Record tracked-source cleanliness separately from untracked dependency/test artifacts.
- Apply PR30 (error contract), PR31 (four child switches), then PR32's token-only delta and PR33's Nextcloud redaction fix (before the first push).
- Resolve `CHANGELOG.md`, `upgrade-notes.yaml` and `docs/provenance/runtime-patches.json` using the actual final implementation.
- Keep dependency locks, 0.4.3 release receipts and image-build source fixes byte-identical to PR29. Per the follow-up mainline decision, bump seven manifests/Dockerfiles, core VERSION, validator, inputs and workflow tags to 0.4.4; only six enabled products may eventually publish.

### Task 2: Review compatibility and provenance

- Review the Odoo entrypoint/overlay/error-wrapper ordering together.
- Review schema-4 optional `odoo_write_switches` and `token_history`, atomic writes, migration and downgrade refusal.
- Verify original PaaS gate bytes and unchanged upstream guarded-source hashes; update only changed local hashes with explanations.
- Add `docs/provenance/ha-mcp-parity-integration-20261029.md` with the exact file inventory, conflict decisions and source/image boundary.
- Mark release notes and the combined upgrade-notes entry as an unreleased 0.4.4 candidate; add release-decision-0.4.4.md with images pending; document restoring a pre-upgrade backup on downgrade.

### Task 3: Focused verification in this worktree

- Create independent root and Odoo venvs and UI dependencies inside this directory; never reuse another worktree's environments.
- Run Odoo error/switch/genuine-child tests together; token, migration, owner-defaults, configuration and lease regressions; inventory/provenance checks.
- Add an integration regression only where the combined wrappers or schema keys lack coverage.
- Run the 76 selected Nextcloud error/child/diagnostic/provenance tests after PR33, retaining the Odoo combined-wrapper results.
- Run UI Node tests, UI build/closure, and the focused switch/token browser cases with a sufficient teardown budget.
- Run packaging validation, exact protected-file comparisons and `git diff --check`. Do not run the full ~20-minute CI suite.

### Task 4: Deliver a reviewable draft

- Record actual commands/results, limitations and remaining parity decisions in the integration record.
- Commit only intended files; finish local source checks before a single push so hosted full CI runs once for the release candidate.
- Push only the new integration branch and open a draft PR describing its verified merged #29 base and proposed replacement of #30/#31/#32/#33. Leave feature PR30–33 open and unchanged; PR29 has been merged independently by mainline.
- Report commit, tests and conflict/release risks. Mainline coordination owns image builds/publication, required full checks, independent PR33 review and merge.
