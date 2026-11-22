# HM-19c Gateway Ingress Profiling Implementation Plan

> For this local task: profile first, then implement only a measured, contract-preserving improvement.

**Goal:** Explain and reduce object-burst gateway latency without weakening UTF-8, JSON, element, depth, or admission rules.

**Architecture:** Use a local isolated worktree at exact candidate head and an external artifact profiling script that drives the actual gateway `json_body` path with both contract payloads. Record phase wall/CPU time, event-loop lag, accepted versus rejected synthetic admissions, and memory. If a safe bottleneck is demonstrated, edit the smallest gateway seam and add targeted regression coverage.

**Tech Stack:** Python 3.13, asyncio, Starlette Request, pytest, existing mcp_admin_core.

---

### Task 1: Baseline

**Files:** Create external artifact `artifacts/ha-multiprofile-parity-20261114/wave5/hm19c-ingress-local-20261122/profile.py`.

1. Generate 99,990 small dicts (800,036-byte body) and near-16 MiB ASCII with one emoji.
2. Drive `gateway.json_body(request, gateway.STRUCTURE_LIMITS)` for 4 and 64 offered calls; bound simultaneously parsed mixed calls to the contract's four 16 MiB slots. Instrument body read, structure guard, `strict_json`, UTF-8 validation serialization, and event-loop lag.
3. Run baseline three times and save raw JSON. Record local-machine and admission-model limitations.

### Task 2: Targeted change, only if supported

**Files:** likely `packages/mcp-admin-core/mcp_admin_core/gateway.py`, `tests/test_request_structure.py` or a focused new test.

1. Write a regression test that fails on the measured responsiveness or duplicate work while asserting exact refusal behavior and strict parsing invariants.
2. Implement one bounded change at the measured seam; preserve all limits, token/policy checks, request and forwarded byte accounting.
3. Run focused tests, benchmark same load, inspect memory and fairness; revert if no improvement or unacceptable regression.

### Task 3: Verify and report

1. Run relevant gateway, structure, budget, and routing tests, plus syntax checks.
2. Commit the isolated branch only after verification. Record exact commit and tests.
3. Report whether candidate image must be rebuilt and which capacity claims remain unproven without J6412.
