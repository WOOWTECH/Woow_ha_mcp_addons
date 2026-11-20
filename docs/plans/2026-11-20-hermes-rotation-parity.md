# Hermes Rotation Parity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Match PaaS Hermes connection saves, which do not rotate MCP tokens on backend identity changes.

**Architecture:** Remove Hermes from the backend and UI identity-bound policy while retaining the common profile routing, origin credential guard and Odoo rotation. Replace affected Hermes rotation assertions with behavioral coverage for both save routes, profile isolation, restore review and child restart; update current contract and security notes.

**Tech Stack:** Python, pytest, JavaScript, Node test runner, Markdown.

---

### Task 1: Update policy and regression tests

**Files:** `packages/mcp-admin-core/mcp_admin_core/products.py`, `packages/mcp-admin-ui/src/contracts.js`, `tests/test_hermes_multi_profile.py`, `packages/mcp-admin-ui/tests/profiles.test.mjs`.

1. Remove Hermes from `IDENTITY_BOUND` and `identityBound`; keep Odoo.
2. Assert identity changes, Dashboard additions and removals preserve the active token and history for default and additional profiles, and verify existing cross-profile protections.
3. Verify the restore review gate still governs explicit token rotation, while a Hermes connection save does not rotate.
4. Run focused Hermes, Odoo, identity-field and UI tests.

### Task 2: Update current documentation

**Files:** `docs/multi-profile/contract.md`, `decisions.md`, `acceptance-matrix.md`, `threat-model.md`, `deviation-trace.md`, `unreleased-changes.md`.

1. Record the user decision and security tradeoff, update active contract and acceptance claims, and preserve historical entries as history.
2. Review the diff, run applicable checks, and record the resulting SHA without merging or publishing.
