# n8n Persistent Catalog Native SQLite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refuse to start an n8n child if its persistent catalog cannot use native SQLite, without changing other applications or existing schema validation.

**Architecture:** The child preload checks the specified catalog using the actual native binding before the HTTP listener starts. A fail-closed, exact-byte upstream adapter patch also prevents a later native initialization failure from falling back to sql.js when the child has a persistent catalog. Existing nonpersistent upstream behavior remains unchanged. Both gates are scoped to n8n and covered by source guards and CI installation.

**Tech Stack:** Node 26, better-sqlite3, n8n-mcp 2.96.2, Python, pytest.

1. Reproduce missing native module and native constructor failure with actual n8n adapter and child using disposable catalogs.
2. Add exact pinned patch and synchronous preload, test no listener, no sql.js and byte preservation on failures.
3. Exercise actual native child initialization and workflow history, plus nonpersistent fallback and existing FTS/schema security checks.
4. Update CI/build wiring, byte pins and provenance, verify, and commit without publishing.
