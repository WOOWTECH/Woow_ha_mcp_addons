# Headscale Inventory and Provenance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the reviewed 11 Headscale tools and 29 Headscale v0.29.4 native operations to the source inventory, drift baselines, and provenance documents.

**Architecture:** Parse the vendored registry, native operation map, and registration loop with Python AST without importing the child. Compare every extracted name and operation with independent reviewed baselines, then generate the existing JSON and Markdown manifests. Pin final vendor bytes to the source revision and record modifications only after the vendor copy is stable.

**Tech Stack:** Python AST, pytest, SHA-256, existing `scripts/tool_inventory.py` manifest generator.

---

### Task 1: Source extraction and structural drift

**Files:** `scripts/tool_inventory.py`, `tests/test_tool_inventory.py`

1. Add tests that reject nonliteral group/native maps, duplicate keys, unregistered native operations, and unexpected registration paths.
2. Run `pytest tests/test_tool_inventory.py -q` to observe the failing cases.
3. Extract `_GROUPS`, `_FIXED`, `NATIVE_OPERATIONS`, and `server.add_tool` through AST. Require exact one-to-one coverage of 29 native operations and 11 tool names.
4. Run the focused tests again.

### Task 2: Reviewed classifications and generated surface

**Files:** `docs/tool-review.json`, `docs/tool-surface.json`, `docs/tool-surface.md`, `tests/test_expansion_drift.py`

1. Add 11 individual Headscale review rows and preserve the prior products' independent drift digests.
2. Add a Headscale effect and operation baseline, then generate the JSON and Markdown surface with `python scripts/tool_inventory.py --write`.
3. Run `python scripts/tool_inventory.py` and the focused pytest files to verify exact document equality.

### Task 3: Final vendor provenance

**Files:** `docs/provenance/runtime-sources.json`, `docs/provenance/six-runtimes.md`, `docs/provenance/headscale-source.md`, `tests/test_tool_inventory.py`

1. After the vendor copy is final, compare each vendored Python file with the source worktree revision and record upstream and local SHA-256 values with modification reasons.
2. Record the child and Headscale API version and the license evidence; do not infer a license from the API dependency.
3. Run provenance, inventory, and drift tests against the actual final files; confirm the generated documents match the files byte for byte.

No commit, push, PR, or merge is part of this task.
