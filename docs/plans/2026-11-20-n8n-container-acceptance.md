# n8n Container Acceptance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Exercise the packaged n8n candidate and its persistent catalogs in an isolated container without relaxing production SSRF.

**Architecture:** Give the owned mock an address accepted by production strict validation on a disposable internal bridge. Extend bounded snapshot validation only for the documented n8n catalog layout and retain restore, privacy and ordinary-file limits.

**Tech Stack:** Python, Docker internal networking, SQLite, pytest.

---

### Task 1: Isolated strict backend

**Files:** `packaging/container_acceptance.py`, `packaging/container_probe.py`, their packaging tests.

1. Test bridge creation and inspection, with no external connectivity, for n8n in both switch states.
2. Configure the mock to bind the bridge address and verify strict validators admit it; keep other products unchanged.
3. Run targeted probe and acceptance tests.

### Task 2: Persistent catalog snapshots

**Files:** `packaging/container_profiles.py`, `packaging/container_probe.py`, their packaging tests.

1. Test private n8n catalog paths and bounded large SQLite files, rejecting arbitrary paths, links, malformed files and oversize files.
2. Snapshot incrementally and apply the layout only to n8n; preserve the existing limits for other products.
3. Run targeted snapshot and restore tests.

### Task 3: Reconciliation and verification

**Files:** candidate provenance, affected ledgers if pinned files changed.

1. Update the candidate record and reconcile ledger digests if needed.
2. Run relevant non-root packaging and n8n tests; record five root cases as pending CI and do not run a build or container.
3. Commit the reviewed changes locally without merging or deployment.
