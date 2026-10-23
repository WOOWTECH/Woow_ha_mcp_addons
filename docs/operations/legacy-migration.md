# Offline legacy permission migration

The existing add-on startup still uses its established all-on migration. It does
not import or invoke this CLI. The tool requires an explicit `preserve` or
`all_on` choice; invocation without `--apply` is a read-only dry run. It never
starts a backend or an MCP child.

Run the candidate tool **after stopping the runtime and before upgrading/starting
the new add-on normally**. Normal startup can otherwise consume schema 1/2/3 and
replace the old policy before it is previewed. The installed 0.1.14 image does
not contain this new tool. Use the candidate Python environment or candidate
image with its normal entrypoint overridden, against the stopped data directory,
as the runtime owner (production uid/gid 10001). An active writer is refused.

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
On a persistence failure, inspect state and the record before retrying; a partial
record fails validation and a completed record is retained. There is no automatic
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
`n8n_executions` gain a `get` read operation that cannot be separately disabled in
schema 4, so preserve disables those whole tools pending review. The report
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

After an upgrade, stop the runtime and preview recovery against its **current**
schema 4 state:

```sh
.venv/bin/python scripts/migrate_state.py /path/to/stopped/mcp --product n8n --restore-policy /path/to/stopped/mcp/migration-policy-recovery.json
```

Append `--apply --expected-sha256 DIGEST_FROM_RECOVERY_PREVIEW` to apply. Recovery
unions disabled tools and intersects write grants with the saved preserve policy.
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
