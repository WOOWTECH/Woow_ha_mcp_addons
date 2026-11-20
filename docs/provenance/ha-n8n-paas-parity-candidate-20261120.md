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

Container/image acceptance is **pending**: no image was built or run. The
acceptance harness now gives n8n a disposable, inspected Docker internal bridge
with a random /24 in `198.18.0.0/15`; the synthetic backend binds only its
container address. The pinned production Node client and both existing strict
address validators accept that benchmarking address while the Node client still
rejects loopback, RFC1918 and link-local examples. No production policy changed.
Docker must be able to allocate the chosen subnet; conflicts fail the probe.

For both default and additional profiles the stopped-fixture snapshot recognizes
only private `n8n-mcp/.seed.lock` and digest-named SQLite catalogs, checks their
header, hashes them by streaming, and applies a 256 MiB fixture-only catalog
bound. Other files retain the existing 1 MiB bound and ownership, mode, link,
filesystem, layout, entry-count and depth checks. Both sides of the multi-profile
restore stage use the same rules. Unit tests cover the network setup and cleanup,
strict policy, snapshot rejection cases and switch-on/off paths; they do not
prove the Docker bridge, real image, Supervisor restore, or HAOS acceptance.

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

Acceptance-harness follow-up verification: Node 26.12.1 and the existing pinned
native dependencies; 273 passed and the five root cases above were deselected in
`packaging/test_container_acceptance.py`, `packaging/test_container_probe.py`,
`packaging/test_container_profiles.py`, `tests/test_n8n_persistent_parity.py`,
`tests/test_n8n_multi_profile.py`, and `tests/test_restore_detection.py`. The
follow-up changes only the acceptance harness, its tests and documentation; no
runtime or tool-surface pinned source changed. Ledger precheck: zero drift among
checked files; 102 runtime-patch and 49 tool-surface installed-only sources still
require CI installations.
