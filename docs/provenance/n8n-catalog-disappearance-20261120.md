# n8n persistent catalog disappearance guards

Base: `c2dc1ad64254234cb4c6f8dbc55d36e41725a6fe`. This change extracts the catalog disappearance protections from `a28881623cda2ff1acf6e618cd83f64cd4819de4`.

When a prepared default catalog disappears, child specification creation now fails instead of omitting `NODE_DB_PATH`. For a persistent `NODE_DB_PATH`, the pinned upstream adapter rejects a different resolved database path and opens native SQLite with `fileMustExist`, so it cannot fall back to another catalog or create a missing one. Other product modes retain their existing behavior. These guards supplement the existing native SQLite and schema checks.

Real Node child tests remove the catalog after native preflight and immediately before the subsequent native open. They check that initialization does not succeed, the original and alternate catalogs remain unchanged, no missing catalog is created, no SQLite sidecars appear, and sql.js is not loaded. A separate test covers disappearance before default child specification creation.

**Unresolved security limitation:** These changes do not bind the validated inode to the later SQLite open. An inode can still be replaced between validation and the path-based native open, and the child can open the replacement. The entire persistent child lifetime is therefore not guaranteed to use the validated catalog. This is an open security issue; these disappearance guards must not be described as resolving it. A complete fix requires a separately reviewed design that also accounts for SQLite sidecars and the supported runtime environment.
