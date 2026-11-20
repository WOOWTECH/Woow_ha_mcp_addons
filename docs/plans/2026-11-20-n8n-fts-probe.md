# n8n FTS probe crash safety Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure a terminated n8n-mcp FTS capability probe never leaves tables in the persistent main database.

**Architecture:** Apply a pinned, fail-closed build patch to both adapter implementations, explicitly creating and dropping a temporary FTS table. Wire the patch into image and test installation, guard the reviewed bytes, and preserve the strict persistent schema policy.

**Tech Stack:** Node 26, better-sqlite3, sql.js, Python, pytest, SQLite.

### Tasks

1. Exercise the actual unpatched Node adapter and kill it immediately after CREATE; observe the main schema residue.
2. Add the exact-byte patch, runtime source guard and install/CI wiring; reject source drift and check idempotence.
3. Test native and sql.js adapters, normal FTS support/refusal, temp/main namespace isolation, and forced termination after creation; maintain the strict schema checks.
4. Update provenance and inventories, verify focused tests and Node 26, review and commit without publishing.
