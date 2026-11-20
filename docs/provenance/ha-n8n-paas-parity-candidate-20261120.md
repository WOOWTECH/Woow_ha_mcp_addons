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
increase disk and backup usage. Existing temporary histories are not migrated. SQLite integrity, catalog objects and columns against the packaged seed, the reviewed
workflow_versions schema, writeability and file ownership/mode are checked; unknown
schemas fail closed.
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

CI job 136215141117 exposed that packaging unittest discovery runs before
`packaging/unit.sh` installs the n8n npm dependencies. The benchmark-address
check against the actual pinned Node client now lives in
`tests/test_backend_loopback.py`, which unit.sh runs after installation and
patching; packaging's dependency-free address and bridge checks remain in place.
The Node test is mandatory and checks the accepted fixture address and the
specific policy denial for private, loopback and link-local addresses.

Local CI-order follow-up: complete packaging unittest discovery ran with the
n8n `node_modules` directory absent and present: each run reported 378 tests,
OK with five existing skips. With installed dependencies and Node 26.12.1,
the moved Node check and the switched-on/off strict loopback checks reported
3 passed. This is not a full CI or root restore run.

Gateway DNS admission follow-up: changed n8n URLs are resolved only after the
locked role and If-Match checks. After the bounded strict DNS check, role,
disconnect and current stored revision are rechecked before disclosing the DNS
result or committing. This does not resolve the separate catalog migration,
schema validation, or global restore-capacity findings.

Local non-root follow-up verification: 147 passed, seven other-product real-child
contract cases deselected, across the DNS admission, admin operations, saved
destinations, n8n persistence and n8n admin contract files. A broader attempt
failed those seven other-product real-child cases because their installed
runtimes are unavailable in this isolated checkout. The five root restore
cases and full CI remain pending.

Catalog refresh follow-up: a seed SHA-256 marker detects upgrades; under the
profile catalog lock, the stopped child's existing reviewed history is copied
column by column into a SQLite backup of the new seed. Both directions of row
comparison and the exact workflow_versions sqlite_sequence are checked before
fsync and atomic replacement. Existing instance_id values are retained, including
the empty environment-mode scope. Unrecognized schemas and SQLite sidecars stop
the child without replacing history. A failure before replacement preserves the
old file; a directory fsync error after replacement is reported and the verified
new file may already be visible. The packaged seed's empty history sequence is
487. A future schema change requires explicit review; it is not auto-migrated.

Refresh takes `nodes`, `node_versions`, templates, FTS indexes and other
catalog objects from the new packaged seed; only reviewed `workflow_versions`
history and its sequence are carried forward. Inspection of n8n-mcp 2.96.2
found catalog write methods used by upstream maintenance and rebuild scripts,
but no caller for them in the supported HA MCP management path. Offline
catalog edits are therefore not preserved by refresh. Supporting those
maintenance operations against the persistent database requires a separate
preservation or conflict policy; this inspection does not prove that every
possible third-party invocation is read-only.

Upstream n8n-mcp 2.96.2 prunes workflow backups older than 30 days at shared
database initialization (configurable by WORKFLOW_VERSION_RETENTION_DAYS),
and its workflow versioning service prunes to ten versions per workflow and
instance after a backup. Persistence does not override that upstream retention.
No global 512-entry restore capacity guarantee has been established: other
writers, quarantines, markers and SQLite sidecars share that whole-tree budget.

Local non-root catalog follow-up verification: 188 passed and five root restore
cases deselected across catalog upgrade, persistent parity, multi-profile and
restore detection tests; the final ten-case real-seed upgrade suite passed
separately. Container acceptance/probe unit tests: 94 passed. No image or HAOS
run is claimed. Full CI and the five root cases remain pending.

Catalog recovery safety follow-up: the catalog lock does not prove that a file
with a reserved `.seed-*.tmp`, `.undo-*.tmp`, or `.previous-<digest>.db` name
was created by the current migration, nor that a target and previous snapshot
have no differences outside workflow history. Encountering any such file now
fails the affected profile's preparation with `catalog recovery required` and
leaves every file untouched, including symlinks and SQLite journals. It does
not choose a target, delete a temporary, or roll back a snapshot automatically.

Manual recovery requires stopping the add-on, preserving a separate complete
copy of the profile's `n8n-mcp` directory including all SQLite sidecars, and
having an operator inspect the target, snapshot, temporaries and their origin.
The operator must decide which complete consistent data to restore, resolving
any conflicts and sidecars without discarding unreviewed evidence. Only after
that decision may the operator remove or move the reviewed recovery files and
restart. There is no automatic recovery guarantee for interrupted publication;
ambiguous files can retain large amounts of disk space and block that profile.
The exception shown externally is intentionally generic and does not expose
paths, URLs or credentials; logs identify the affected profile.
