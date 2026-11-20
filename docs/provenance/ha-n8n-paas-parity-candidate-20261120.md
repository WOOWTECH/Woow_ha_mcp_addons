# n8n PaaS parity candidate

This is an unpublished, unmerged candidate. The comparison uses PaaS `origin/main`
`5ef1046927db4ec239bfde9b4a38c64eeafea399` and HM-25 base
`505212ce0002b441d7d6972532a53f1c3968aa7c`. The 2026-11-20 request explicitly
supersedes the older DQ-04 temporary-history and DQ-10 permissive-webhook decisions.

The default and additional profiles prepare private SQLite catalogs under their own
`n8n-mcp` directories in `/data/mcp`. The SHA-256 filename selects the configured
URL and key; returning to that identity selects its old database. A new identity
gets a new seed, while prior histories remain on disk and in cold backups until the
profile is removed. Snapshots can contain sensitive information and retained databases
increase disk and backup usage. Existing temporary histories are not migrated. SQLite
integrity, a populated nodes table, the workflow_versions table, writeability and file
ownership/mode are checked; the complete PaaS restore schema validation is not ported.
Preparation failure prevents that child starting. The existing runtime UID is shared
between child processes, so profile directories are not an operating-system security
boundary. Inherited HM-25 archive and restore-token behavior is unchanged.

The n8n child uses upstream strict URL validation; the pinned configured API client
also applies it before connecting. Saving a changed n8n backend URL checks DNS answers
in strict mode; HA retains its existing additional URL restrictions. Existing private
backend settings remain stored but cannot be reached; administrators must supply a
publicly reachable endpoint. Other products keep their existing backend policy.

The local non-root restore test exercises the actual bootstrap ownership-repair code
through the existing VirtualRoot fixture and the restore guard after a cold copy; the
multi-profile test exercises a cold copy, per-profile history and token revocation.
This does not prove an actual HA Supervisor restore or root ownership changes. The five
real-root cases in `tests/test_restore_detection.py` are **pending root-capable CI**:
`test_root_backup_restore_and_repair`, `test_root_start_without_a_restore_changes_nothing`,
`test_root_marker_name_taken_by_a_directory[None]`,
`test_root_marker_name_taken_by_a_directory[index]`, and
`test_root_the_container_probes_restore_stage_meets_the_entrypoint`.

Container/image acceptance is **pending**. The existing container probe expects a
private synthetic n8n backend, which strict policy now refuses; its fixture snapshot
also assumes files at most 1 MiB and the old layout, while persistent catalogs are
larger and inside the profile tree. The catalog-specific probe is updated, but the
full acceptance path must be redesigned and run against the real packaged image;
no image build, HA acceptance, release, merge or deployment is claimed here.

The tool-surface generator could not complete in the isolated checkout because the
Odoo and Odoo Manage installed source inventories are absent (0 observed versus 41
and 10 reviewed tools). The candidate updates
only the changed n8n backend-policy source digest in `docs/tool-surface.json`, with no
tool definitions intentionally changed. The full generator and all installed-source
ledger checks remain CI gates. `scripts/ledger_precheck.py` reports 0 checked-file
drift; its missing installed-only sources still need the CI installs.

Non-root candidate verification: 623 tests passed with five root cases deselected
across the n8n, restore and container-profile test files, using Node 26.12.1 and the
pinned better-sqlite3 native binary. The container-profile tests are local unit tests;
they do not run the packaged container acceptance path. The feature candidate changes
no `addons/` files: release-facing wording is staged in
`docs/multi-profile/unreleased-changes.md` for the separate release slice.
