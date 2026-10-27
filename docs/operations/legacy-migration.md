# Legacy permission migration

## Next release (owner decision 2026-10-27, not yet released): one-time all-on at the first start

The runtime no longer waits for an upgrade review. Before it constructs ProductStore or starts a child, every add-on
(`run_product.py` for Odoo, Hermes, OpenDesign, EMQX, LiteLLM and Nextcloud, `apps/n8n/run.py` for n8n) checks
`/data/mcp/state.json` once (`mcp_admin_core/owner_defaults.py`, `apply_legacy_upgrade`):

| State found | What happens |
|---|---|
| none (new installation) | Normal start: ProductStore writes the all-on defaults, without a marker. |
| schema 4 (0.2.0 or later, including states the 0.3.0–0.4.1 review page migrated) | Not touched. What the administrator chose stays. |
| valid schema 1/2/3 (0.1.x, or the 2026-10-03 prototypes) | Migrated once, then MCP starts at once (no 503). |
| unreadable, invalid, linked, in use, or its recovery record cannot be saved | Nothing is migrated or rewritten (fail safe), see below. |

The migration writes exactly the former review page's `all_on` plan: schema 4, `writes_enabled: true`, every write
grant, no disabled tool, no operation deny; token (also a revoked `null` one), child token, endpoint, backend and the
optional n8n MCP access token keep their values. The retired Odoo Manage keeps its policy. In the same atomic state
write it adds the marker

```json
"owner_defaults_20261025": {"applied": "migrated", "at": "2026-10-27T03:04:05+00:00", "from_schema": 3,
                            "restored_at": null, "acknowledged_at": null}
```

(same name as the PaaS marker). Before that write it saves the legacy policy once as
`/data/mcp/owner-defaults-20261025-recovery.json` (format 2, mode 0600): the `writes_enabled`, `disabled`,
`enabled_write_tools` and `denied_operations` of the old state as validated, the digest of the old state and of the
frozen 0.1.x catalog; never a token, endpoint or backend value. The record is written and fsynced under a temporary
name in the same directory and then linked to its final name, which never replaces an existing file, so that name only
ever holds a complete record: a write that fails (disk full, I/O error) removes its temporary file, and a kill or power
loss can leave only a temporary `.owner-defaults-20261025-recovery.json.<random>.tmp`, which the next start removes. If
the add-on stops between the record and the state write, the next start finds an identical record and continues; any
other existing record stops the migration. The add-on log shows one line: `owner defaults 2026-10-25: the schema N
state was switched once to schema 4 with every tool and write on; ...`.

**Fail safe.** When `state.json` is unreadable or invalid JSON, has duplicate keys or non-finite numbers, is larger than
64 KiB, a symlink or a hard link, has an unknown schema, the wrong product, a missing or extra key, a malformed policy,
or the data directory is not owner-only, `.writer.lock` is missing or held, the recovery record cannot be created, or a
recovery record exists that is not this state's, nothing is migrated or rewritten (bytes, mode and mtime stay; no
record, no temporary file). The add-on log shows one fixed line, then `runtime unavailable; local recovery required`;
the add-on stops, and the panel and MCP are unavailable (as for a corrupt state before):

| Add-on log (after `owner defaults 2026-10-25: `) | What to do |
|---|---|
| `owner-defaults-20261025-recovery.json could not be saved (disk full or I/O error); nothing was migrated or rewritten and no partial record was left; ...` | Free space on the HA data disk and restart the add-on; the migration then completes. |
| `owner-defaults-20261025-recovery.json already exists but is not the complete recovery record of this state.json (incomplete, damaged or from another state); ...` | Restore the add-on backup taken before the update, or check that file (policy only, no secret) and move it out of `/data/mcp`. |
| `state.json is unreadable, invalid, linked or in use, or its recovery record cannot be saved; nothing was migrated or rewritten` | Restore the add-on backup taken before the update. |

Do not edit the state or delete the lock to force a start.

### Panel notice and optional restore

Until the administrator acts, every page of the add-on panel shows **已自動套用預設全開**: when (UTC), from which
schema, and the differences (tools the old state disabled and now enabled, 0.1.x writes it did not grant and now
granted, cleared operation denies, tools and write operations added since 0.1.x). Two actions; each needs the panel's
current revision (`If-Match`), is recorded in the marker and ends the notice:

- **還原升級前的限制** (`POST /api/owner-defaults/restore`): restores the old limits faithfully, as a restrictive merge
  into the current state, reading each list the way the 0.1.x runtime enforced it (`policy.has_grant`, unchanged
  since). `disabled` was a deny list: the tools the old state disabled are disabled again, and a tool added since
  0.1.x stays enabled. `enabled_write_tools` was an allow list: a write it did not list was refused (for n8n
  `n8n_delete_workflow` and OpenDesign `delete_project` the legacy global switch also allowed it). So only the write
  grants the old state held stay granted, and every other write is revoked, the write operations added since 0.1.x
  included, which 0.1.x would have refused as well. Its `writes_enabled` and operation denies come back. The restored
  policy permits exactly the writes the old one did. What the administrator disabled, revoked or denied after the
  upgrade stays so; nothing is enabled or granted; token and backend are the current ones. This is not the 0.3.0
  `preserve` choice, which also disabled every tool whose argument checks moved to the child (for Hermes all 11).
  EMQX, LiteLLM and Nextcloud restart their child afterwards, as for a saved policy. Examples: the ws97 Hermes 0.1.14
  state (`hermes_skill` disabled, no write granted) is restored with `hermes_skill` disabled and none of the 21 write
  grants, so tools/list shows 9 of 11 tools (the write-only `hermes_chat` is not listed); a 0.1.14 default (writes off,
  no grant) is restored without any write to Odoo 33 of 41 tools, n8n 18 of 28, EMQX 27 of 39, LiteLLM 15 of 40,
  OpenDesign 12 of 15 and Nextcloud 5 of 9.
- **保持全開，不再提示** (`POST /api/owner-defaults/dismiss`): records `acknowledged_at`; the restore stays available
  on the 診斷與維護 page.

The panel shows no restore when the record is missing or invalid (then only the notice and the keep action) or when the
old state had no limit to restore. Offline, with the runtime stopped, the same restore is
`--restore-policy /data/mcp/owner-defaults-20261025-recovery.json` (below).

**Rollback.** A migrated state carries the marker key, which 0.4.1 refuses (`runtime unavailable`): to go back to
0.4.1 restore the add-on backup taken before the update. Every state without the marker keeps exactly the 0.4.1 keys.

## Until 0.4.1: authenticated upgrade review (history)

The 0.3.0–0.4.1 runtime detected schema 1/2/3 before constructing ProductStore or
starting a child and served an authenticated Home Assistant Ingress upgrade
review instead: the administrator chose `all_on` (selected by default) or
`preserve` and confirmed. MCP answered 503 `upgrade_review_required` until then
(ws97, 2026-10-26: more than 15 minutes without an administrator), and the review
page refused Core releases after 2026.10.1 (403).

## Offline CLI

The offline CLI remains available for planned maintenance. Run it after stopping
the runtime, as its state owner (production uid/gid 10001). Invocation without
`--apply` is a read-only dry run and never starts a child. Images before 0.3.0 do not contain this workflow; use the exact accepted
0.3.0 image for this tool once its publication gates pass. Existing writers, including a running upgrade-review screen, refuse CLI
apply. Close/stop the runtime before offline recovery.

## Preview and explicit apply

From a source checkout (replace the example directory/product):

```sh
.venv/bin/python scripts/migrate_state.py /path/to/stopped/mcp --product n8n --policy preserve
.venv/bin/python scripts/migrate_state.py /path/to/stopped/mcp --product n8n --policy all_on
```

Both commands report only policy information, a source digest, disabled-list and
grant differences, effective write changes, new tools/operations, unclassified
tools, and read/argument changes needing review. They do not change state, mode,
lock files or recovery records. `--save-recovery /protected/path/policy.json` is
an explicit optional write of a secret-free policy record; its existing parent
directory must be owner-only and the record is created exclusively with mode
0600. No full legacy state is backed up by this tool.

To apply the reviewed choice, use that preview's `source_sha256`:

```sh
.venv/bin/python scripts/migrate_state.py /path/to/stopped/mcp --product n8n --policy preserve --apply --expected-sha256 DIGEST_FROM_PREVIEW
```

Apply acquires the existing runtime writer lock, rereads and validates state, and
refuses a changed digest. It durably creates `migration-policy-recovery.json`
(0600) before atomically replacing state. Existing records are never overwritten.
On a persistence failure, inspect state and the record before retrying; a record is
published only when complete (2026-10-27: temporary file, fsync, link), so a failed
write leaves none, and a completed record is retained. There is no automatic
retry or overwrite. Existing schema 4 is a no-op for either migration choice.
Tokens (including a revoked `null` token), child token, endpoint, backend and
optional n8n MCP credential retain their current values.

## Policy mapping

The frozen catalog is the final 0.1.x bounded surface retained in this repository.
All source fields are validated before applying a choice. Schema 1 is n8n-only;
schema 2 has product/connection fields; schema 3 adds exact write grants. Schema
1/2 start with no exact grants. Unknown versions, wrong-product data, missing or
extra fields, duplicate JSON keys, duplicate grants and malformed policy data are
refused. A field malformed in legacy state is not hidden by an all-on reset.

`all_on` matches the existing valid-state migration: clear disabled tools, enable
the global flag and all current exact writes. Retired Odoo Manage retains policy.

`preserve` retains disabled names and existing exact grants. A true legacy global
flag adds only n8n `n8n_delete_workflow` or OpenDesign `delete_project`; disabled
tools remain disabled even if their grant is saved. Other writes never inherit
that flag. New tool names, including new reads and unclassified tools, are
disabled; new write operations remain ungranted. Hermes `hermes_session` and n8n
`n8n_executions` gain a `get` read operation. Although the new management UI supports operation denies,
preserve still disables these tools pending review because their argument
validation also expanded. The report
identifies this reduction in access.

| Product | Old/current tools | New tool names | New write grants/operations |
|---|---:|---:|---:|
| Odoo | 13 / 41 | 28 | 7 |
| Odoo Manage (retired) | 9 / 9 | 0 | 0 |
| Hermes | 7 / 11 | 4 | 13 |
| OpenDesign | 11 / 15 | 4 | 2 |
| EMQX | 11 / 39 | 28 | 13 |
| LiteLLM | 12 / 40 | 28 | 21 |
| Nextcloud | 9 / 9 | 0 | 0 |
| n8n | 13 / 28 | 15 | 29 |

`emqx_test_rule_sql` and `n8n_audit_instance` are explicitly unverified and treated
as writes by the current catalog. Preserve disables both newly introduced tools.
The tool retains permission selections but cannot recreate old argument limits
or removed backend guards. Every existing tool now delegated to child validation
appears in `argument_review_tools` and is disabled by `preserve` until explicitly
reviewed and re-enabled. This may pause most tools; the preview reports the exact
disabled set. `all_on` remains available for an explicit choice of the expanded
surface. Schema version alone cannot identify the precise binary
inventory of an earlier installation; comparisons explicitly name the final
0.1.x baseline rather than claiming an exact earlier inventory.

## Restrictive policy recovery

`--restore-policy` reads both record formats: `owner-defaults-20261025-recovery.json` (format 2, written by the
one-time all-on migration) is restored faithfully as described above and records `restored_at` in the marker;
`migration-policy-recovery.json` (format 1, written by the 0.3.0–0.4.1 review or the CLI) keeps the behavior below.

After an upgrade, stop the runtime and preview recovery against its **current**
schema 4 state:

```sh
.venv/bin/python scripts/migrate_state.py /path/to/stopped/mcp --product n8n --restore-policy /path/to/stopped/mcp/migration-policy-recovery.json
```

Append `--apply --expected-sha256 DIGEST_FROM_RECOVERY_PREVIEW` to apply. Recovery
unions disabled tools and operation denies, and intersects write grants with the saved preserve policy.
Later revocations therefore remain revoked. All current identity/backend fields
are carried forward; an old token is never present in the recovery record and
cannot be resurrected. A changed catalog or wrong product is refused. This is
policy recovery within schema 4, not a binary/schema downgrade. Never copy an old
full state.json over current state to recover permissions. If a separate binary
rollback requires a sensitive full-state backup, keep it 0600 and reconcile
current token revocations/rotations separately before bringing that binary up.

## Deployment closure

The production entrypoint for this tool is:

```sh
/opt/woow/.venv/bin/python -m mcp_admin_core.migration /data/mcp --product n8n --policy preserve
```

The product image already supplies the core `PYTHONPATH`. `migration.py` and
`legacy_catalog.py` are allowed by `.dockerignore` and copied by every product
Dockerfile's `COPY packages/mcp-admin-core`; n8n adapter imports are unnecessary.
The repository `scripts/` wrapper is excluded from image contexts, so use the
module entrypoint in an image. The deploy owner must include these new files in
the reviewed commit/source bundle. Local closure checks and a copied-core fixture
exercise this command; no candidate image build or live upgrade is claimed here.
