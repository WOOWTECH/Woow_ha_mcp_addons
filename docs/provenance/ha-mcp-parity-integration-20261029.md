# HA MCP 0.4.4 integration source record — 2026-10-29

Status: draft release candidate; no 0.4.4 image built or published. Mainline owns the private builder and merge.
After the single candidate push, freeze that head for the builder; any later source edit requires a new explicit
freeze and fresh exact-source acceptance. The PR description records the resulting source commit SHA.

## Fixed inputs and clean source boundary

| Input | Exact commit | Treatment |
| --- | --- | --- |
| PR29 prepared base | `a3030679f69b6b68266e9a0f98a46b14b88a479e` | Fresh worktree initially created at this Git tree |
| PR29 protected merge | `f378a7752538d0cdbf2a23db4af3dfb7ceee0e39` | Final integration parent; merged 2026-10-29 03:31:39 UTC |
| PR30 Odoo isError | `23574112a9a6528d54c37088e32dc3de1094f2d6` | Both commits from `f71fb75` |
| PR31 four switches | `0704c9a3ca23952be3901edd39cd7e5b0b4e5ee1` | Four commits from `f71fb75` |
| PR32 token history | `ca064c2ab05d852a3c0e29001c9763997bc86dde` | Only `0704c9a3..ca064c2`, avoiding duplicate PR31 |
| PR33 Nextcloud redaction | `d81bc7c578746b0a94ea762e103db81b7d101f30` | Its single commit; no helper-only `21cd303` changes |

The two PR29 commits have identical tree `a1b4d2217fbf24687ec85f23eca2532804f5d110`.
Only this new branch's parent was updated after verifying equality. No other worktree or PR branch was reset.
The worktree is `/data/pi-agent/home/work/ha-mcp-parity-integration-20261029`.
All four feature inputs had clean **tracked** source at inspection; existing untracked venvs, reports and test
artifacts were excluded. Only committed Git blobs were imported. Remote PR heads matched these full hashes.

The 0.4.3 image source is `a1c118191a004a08e92273674de58bb7c24b18b4`. Its diff to `a3030679` contains only
`docs/operations/evidence/0.4.3-synthetic-fixture-triage.md`, `docs/operations/release-decision-0.4.3.md` and
`docs/provenance/release-0.4.3-images.json`; those three files remain byte-identical in this integration.
No 0.4.3 image-source worktree was copied or edited. Existing 0.4.3 images/readiness are not acceptance of 0.4.4.

Final source audit: **28 feature source/test files match their fixed input bytes**, **19 executable version paths
change only 0.4.3 to 0.4.4**, and **75 protected paths remain byte-identical to the base**. Protected paths include
all dependency locks, Odoo wheel patch scripts, all vendor files except the two explicitly imported PR33 files,
archived Odoo Manage Dockerfile, 0.4.3 receipts/decision/triage, supply-chain code and secret triage, and publication
workflow control files. Seven source manifests share 0.4.4; only six Store-enabled products may publish.

## Conflict resolution and provenance review

- Only `CHANGELOG.md` and `upgrade-notes.yaml` had textual cherry-pick conflicts. Preserve the complete historical
  0.4.3 sections; combine the new behavior under one unreleased 0.4.4 candidate. Replace the earlier planned
  0.4.5/0.4.6 sequence in the candidate's Odoo/token documents. Original PRs remain unchanged.
- Runtime code merged without conflicts. `start_switches.py` installs the idle/body guard before importing the
  Odoo server, then the switch overlay. PR30's unchanged `launch.py` installs `odoo_tool_errors` around those
  handlers before `BoundedTools` and `keep_error_text`. Real-child tests assert switch refusals carry isError and
  their text JSON equals the unwrapped structuredContent; the SDK schema checks cover all 41 published tools.
- `products.py`, `gateway.py`, `migration.py`, access/configuration, UI API/contracts/app and Odoo listing/snapshot
  retain their exact fixed-input implementation. Combined state tests additionally prove switch saves, token
  changes, schema-4 migration preview and owner-policy restore preserve both optional fields and outer revocations.
- `odoo_write_gates.py` retains PaaS #89 `38a9041` bytes and SHA-256
  `b4852fb0ebd78b6d10c4a3fcd401d0d16eeb21a129ea3b2ece3b19e30c4a4b8d`.
  All guarded upstream wheel hashes remain unchanged. `n8n_arguments.py` is unchanged; its guarded snapshot hash
  changes only because PR31 expands the Odoo execute_method description. n8n snapshot entries remain unchanged.
- `__init__.py` is the only new runtime re-pin beyond the feature inputs: VERSION 0.4.3 to 0.4.4, with no logic
  change. The ledger retains the PR29 0.4.3 version history and adds the actual 0.4.4 difference.
- PR33 applies cleanly to different tool-surface entries: Nextcloud `client.py` supplies known configured password
  and username:password to `server_message`; `webdav.py` masks their literal/URL/JSON/base64 forms after parsing but
  before folding/truncation. `runtime-sources.json` records those exact local modifications and SHA-256 values;
  `tool-surface.json` retains PR30's launcher/error-wrapper entries and adds both PR33 hashes. No gateway redactor,
  auth latch, dependency, output schema or diagnostic policy is changed by PR33.
- `tests/test_odoo_child_switch_runtime.py` and `tests/test_token_history.py` add only the integration assertions
  described above. All other imported executable/test files match their input commits exactly.

Changed ledger entries (full hashes; unchanged hashes indicate review-note or guarded-source changes):

| File | Base SHA-256 | Candidate SHA-256 |
| --- | --- | --- |
| `packages/mcp-admin-core/mcp_admin_core/products.py` | `99becc3f6e5d47e648a72da99d730c202ef0227aa5ce96d874871189cd7af52b` | `4d786a9d0ea4adf962a6bd696424bbe7890b26d605e09bc677120d79944d0df5` |
| `apps/odoo/launch.py` | `58c18c19323594e056503b64b6f7a249e8f590842597d340c8461651f56fd47f` | `6210bde53d83a89210943ccf62941eda6ef010d0dfe4dd9508e8f0a8cbca388b` |
| `packages/mcp-admin-core/mcp_admin_core/gateway.py` | `8098a7e6c3dd6fbca41a2e8f0cb53461e4fa742e8e96b91bc6b64cba0831ff0f` | `435e0b861c4e82af6226c1d8a101987e5fcfc2abdaa5d537dc97312bd2cbef13` |
| `apps/runtime/odoo_tool_errors.py` | `new` | `6957e4229fa5e93d7a5bddcb0be35e1c36ba5bf7b3e856c984b4ccc9fb71f482` |
| `packages/mcp-admin-core/mcp_admin_core/__init__.py` | `c148a190aada3a35b8436bf6ead9ffe9cc36e93b1272fcbb906851e057dd9a10` | `8986756d1abfc1413c6e1870a011ce1488f710959f3039b7c532a5a93d550e69` |
| `packages/mcp-admin-core/mcp_admin_core/access.py` | `6343679e18f57ee070f1c24da83b4f2ac95a7d10ddc7ecb28ac7343a2c63abbd` | `e31b5f1851604f25c89dcf3f4327b6344c23825c8dc72b35a9e8654b7948a8d3` |
| `packages/mcp-admin-core/mcp_admin_core/configuration.py` | `d2286d7d7ee3c4210c295b5e02910a8d63fc5dc03ba879a5b36112f778fd55dc` | `8590c837577b8dd0e41e6dac7cf4f370e7926c48b87d753989350877d491b0d8` |
| `packages/mcp-admin-ui/src/app.js` | `64fa533dadf50d73b4f2c56543ff32372f380269c7c18682cbb8d5ff99595518` | `7361d3a123652cb435bb087df6945399965cf6d4f5e2def0c40d918bc0de700a` |
| `packages/mcp-admin-core/mcp_admin_core/n8n_arguments.py` | `68c88a56ec36d4aaf2cb4fd38d41082506f63c1734851ece60e4b258ba22cd8e` | `68c88a56ec36d4aaf2cb4fd38d41082506f63c1734851ece60e4b258ba22cd8e` |
| `packages/mcp-admin-core/mcp_admin_core/migration.py` | `new` | `bd12e4960f81c5735e1da8771b1ddba9e9a338393ed4936659963f06cb304f77` |
| `packages/mcp-admin-core/mcp_admin_core/odoo_write_gates.py` | `new` | `b4852fb0ebd78b6d10c4a3fcd401d0d16eeb21a129ea3b2ece3b19e30c4a4b8d` |
| `packages/mcp-admin-core/mcp_admin_core/odoo_switch_listing.py` | `new` | `0a5b85fca13a315a30a4d7922bf819d00dd9be9fa35046867ef41450942d89d9` |
| `packages/mcp-admin-core/mcp_admin_core/tool_snapshot.py` | `new` | `993abc6802c3f42d5e4428d20b7d6d1e51ac8715f7589c6720bd5926f4c714f2` |
| `apps/odoo/odoo_switch_overlay.py` | `new` | `d152e371f98a5ffab992aa7048cb773edb2263305272ec564a077b65215ff8f4` |
| `apps/odoo/start_switches.py` | `new` | `d3c366ee8c392875d0f712efc7bbafb2ab5aec04371018dadfad7827e268d85a` |
| `packages/mcp-admin-ui/src/api.js` | `new` | `3e4fac77c62e7558f8b1e5f3e981ede67c7ee58f2e290535ab769ac81b607154` |
| `packages/mcp-admin-ui/src/contracts.js` | `new` | `298719a961fd715269097eec699aa39584522d9bc724f3acf7220622baa6e8e9` |

PR33 vendor hashes are `26d45cc8b9c5339a154f260160d042c9fbc68f2614a9f30015bdf214679f8881` (client.py) and
`b0e79f7446957f775a53e78444e0071c43b5c0c725a8c958bd9e68d6c64c83a5` (webdav.py). Full runtime ledger, guarded-source
and vendor-source hashes were checked from this worktree; the six inventory tests and inventory generator pass.

## Local verification

| Check | Actual result |
| --- | --- |
| Odoo/core/token/migration/lease/configuration/boundary/inventory selection | 479 passed, 0 failures/errors/skips; 2 dependency deprecation warnings; 48.21s |
| PR33 Nextcloud error/child/diagnostics/raw-error + inventory selection | 76 passed, 0 failures/errors/skips; 225.19s |
| Packaging unittest discovery | 158 run; OK; 5 root-only tests skipped; 17.45s |
| UI Node tests | 39 passed, 0 failures/skips |
| UI build and build closure | Passed; 434 identical fonts, 435 local references and six notices |
| Focused Playwright Odoo selection | 8 passed, including all six switch cases and two typed backend forms; 16.4s |
| Focused Playwright token-history case | 1 passed; 3.4s |
| Packaging validator, tool inventory and diff whitespace | Passed |
| 0.4.3 decoder against synthetic candidate state | Neither key: accepted; switches only/history only/both: rejected without rewriting; pre-upgrade backup accepted in every case |

The 479-test selection ran before the additive PR33 import; the Odoo/core/UI bytes it verifies were unchanged by
PR33. The final 76-test selection rechecked the affected Nextcloud path and all six inventory/provenance tests.
The first Python attempt stopped at the repository's shared test-lock setup after 120 seconds (479 setup errors,
no test bodies). Another agent owned the lock; no process was stopped or lock removed. The successful retry began
once the lock was available. Both attempt logs are retained locally. Browser tests use a 60-second teardown budget;
no browser timeout occurred in these selected cases. The full ~20-minute suite was not run locally.

Environments are new directories inside this worktree, never symlinks to another agent's venv. The initial shared
uv cache supplied already-patched Odoo bytes; its patch commands were no-ops. Before tests, Odoo was reinstalled
from an empty worktree-owned cache with `--link-mode copy`, both checked-in patches applied afresh, and nlink=1
verified. Other venvs also use copy mode. Local Python is 3.13.2, Node is 22.23.3; hosted CI pins 3.13.16/26.12.1.
This is focused source verification with fake backends, not exact-image or live HA/PaaS/production acceptance.

Reproducible focused commands (after locked installs, wheel/n8n patches and the local UI build):

```sh
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_odoo_error_result_parity.py tests/test_odoo_read_exists.py \
  tests/test_odoo_child_switches.py tests/test_odoo_child_switch_runtime.py \
  tests/test_odoo_write_descriptions.py tests/test_token_history.py \
  tests/test_migration_preview.py tests/test_owner_defaults.py \
  tests/test_configuration_status.py tests/test_configuration_runtime.py \
  tests/test_active_token_leases.py tests/test_product_boundary.py tests/test_tool_inventory.py \
  'tests/test_tool_snapshot.py::test_snapshot_equals_the_real_child[odoo]' \
  'tests/test_session_idle.py::test_real_child_ends_an_idle_session_and_keeps_an_active_one[odoo]'
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_nextcloud_error_secrets.py tests/test_nextcloud_child.py \
  tests/test_child_diagnostics.py tests/test_raw_backend_errors.py tests/test_tool_inventory.py -k 'not actual_odoo'
TMPDIR=/tmp .venv/bin/python -m unittest discover -s packaging -p 'test_*.py' -v
npm test --prefix packages/mcp-admin-ui
npm run build --prefix packages/mcp-admin-ui
node packages/mcp-admin-ui/tests/build-closure.mjs
npm run test:browser --prefix packages/mcp-admin-ui -- --grep 'Odoo|token history' --timeout=60000
npm run test:browser --prefix packages/mcp-admin-ui -- tests/browser/ui.spec.mjs --grep 'MOCK token card' --timeout=60000
.venv/bin/python packaging/validate.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/tool_inventory.py
git diff --check
```

Local raw logs, JUnit XML, source-audit output and baseline-decoder results are under `.integration-evidence/` in
this worktree (ignored, not shipped). The baseline decoder was extracted from the immutable a303067 Git tree into
that directory; only generated fake state was used, and no production state or credentials were accessed.

## Mainline handoff and remaining risks

- New draft targets `claude-delivery` on its merged PR29 base. It proposes replacing PR30–33 as separate release
  paths, with all four originals left open for mainline coordination. One source commit/push starts one hosted CI
  run; do not revise its head while the private builder is freezing it.
- No textual/runtime conflict remains locally. Later independent merges of any feature PR would duplicate these
  changes and require mainline reconciliation; independent PR33 review remains owned by mainline.
- A saved `odoo_write_switches` or `token_history` prevents a binary-only downgrade to 0.4.3. Restore the pre-update
  backup and review restored grants/tokens; do not remove fields manually. Source-level decoder behavior is tested,
  but no live HAOS downgrade was performed.
- PaaS exact model.method allowlist editing remains absent in HA. The outer execute_method grant still gates the
  whole tool, including reviewed reads. Nextcloud masking is bounded to configured credentials/explicit encodings;
  unknown secrets, arbitrary encodings and backend-provided fragments remain outside its contract.
- Images, exact-image/source-history/layer secret scans, SBOM/CVE/license/container gates, anonymous readback,
  readiness, protected merge, stable Releases and Store synchronization are pending mainline work. The 0.4.3
  evidence stays historical and is not reused as 0.4.4 acceptance. No fabricated 0.4.4 receipt is added.

## Complete changed-file inventory

This is the complete candidate delta from `f378a775` (the same tree as a303067), including this record.

| File | Source / purpose |
| --- | --- |
| `.github/workflows/ci.yaml` | 0.4.4 version binding only |
| `.github/workflows/release.yaml` | 0.4.4 version binding only |
| `CHANGELOG.md` | PR30 + PR32 + integration/release reconciliation |
| `README.md` | 0.4.4 release documentation |
| `addons/emqx/CHANGELOG.md` | 0.4.4 release documentation |
| `addons/emqx/config.yaml` | 0.4.4 version binding only |
| `addons/hermes/CHANGELOG.md` | 0.4.4 release documentation |
| `addons/hermes/config.yaml` | 0.4.4 version binding only |
| `addons/litellm/CHANGELOG.md` | 0.4.4 release documentation |
| `addons/litellm/config.yaml` | 0.4.4 version binding only |
| `addons/n8n/CHANGELOG.md` | 0.4.4 release documentation |
| `addons/n8n/config.yaml` | 0.4.4 version binding only |
| `addons/nextcloud/CHANGELOG.md` | 0.4.4 release documentation |
| `addons/nextcloud/config.yaml` | 0.4.4 version binding only |
| `addons/odoo/CHANGELOG.md` | 0.4.4 release documentation |
| `addons/odoo/DOCS.md` | 0.4.4 release documentation |
| `addons/odoo/config.yaml` | 0.4.4 version binding only |
| `addons/opendesign/CHANGELOG.md` | 0.4.4 release documentation |
| `addons/opendesign/config.yaml` | 0.4.4 version binding only |
| `apps/emqx/Dockerfile` | 0.4.4 version binding only |
| `apps/hermes/Dockerfile` | 0.4.4 version binding only |
| `apps/litellm/Dockerfile` | 0.4.4 version binding only |
| `apps/n8n/Dockerfile` | 0.4.4 version binding only |
| `apps/nextcloud/Dockerfile` | 0.4.4 version binding only |
| `apps/nextcloud/vendor/nextcloud_mcp_server/client.py` | PR33 |
| `apps/nextcloud/vendor/nextcloud_mcp_server/webdav.py` | PR33 |
| `apps/odoo/Dockerfile` | 0.4.4 version binding only |
| `apps/odoo/launch.py` | PR30 |
| `apps/odoo/odoo_switch_overlay.py` | PR31 |
| `apps/odoo/start_switches.py` | PR31 |
| `apps/opendesign/Dockerfile` | 0.4.4 version binding only |
| `apps/runtime/odoo_tool_errors.py` | PR30 |
| `docs/operations/release-decision-0.4.4.md` | 0.4.4 release documentation |
| `docs/operations/update-backup-rollback.md` | 0.4.4 release documentation |
| `docs/plans/2026-10-29-ha-mcp-parity-integration.md` | 0.4.4 release documentation |
| `docs/plans/2026-10-29-odoo-write-switches.md` | PR31 |
| `docs/provenance/ha-mcp-parity-integration-20261029.md` | 0.4.4 release documentation |
| `docs/provenance/nextcloud-error-secrets-20261029.md` | PR33 |
| `docs/provenance/odoo-write-switches-20261029.md` | PR31 |
| `docs/provenance/runtime-patches.json` | PR30 + PR31 + PR32 + integration/release reconciliation |
| `docs/provenance/runtime-sources.json` | PR33 |
| `docs/provenance/token-history-20261029.md` | PR32 |
| `docs/tool-surface.json` | PR30 + PR33 |
| `packages/mcp-admin-core/mcp_admin_core/__init__.py` | 0.4.4 version binding only |
| `packages/mcp-admin-core/mcp_admin_core/access.py` | PR32 |
| `packages/mcp-admin-core/mcp_admin_core/configuration.py` | PR31 |
| `packages/mcp-admin-core/mcp_admin_core/gateway.py` | PR31 + PR32 |
| `packages/mcp-admin-core/mcp_admin_core/migration.py` | PR31 + PR32 |
| `packages/mcp-admin-core/mcp_admin_core/odoo_switch_listing.py` | PR31 |
| `packages/mcp-admin-core/mcp_admin_core/odoo_write_gates.py` | PR31 |
| `packages/mcp-admin-core/mcp_admin_core/products.py` | PR31 + PR32 |
| `packages/mcp-admin-core/mcp_admin_core/tool_snapshot.py` | PR31 |
| `packages/mcp-admin-ui/fixtures/server.mjs` | PR31 + PR32 |
| `packages/mcp-admin-ui/src/api.js` | PR31 |
| `packages/mcp-admin-ui/src/app.js` | PR31 + PR32 |
| `packages/mcp-admin-ui/src/contracts.js` | PR31 + PR32 |
| `packages/mcp-admin-ui/tests/browser/odoo-switches.spec.mjs` | PR31 |
| `packages/mcp-admin-ui/tests/browser/ui.spec.mjs` | PR32 |
| `packages/mcp-admin-ui/tests/odoo-switches.test.mjs` | PR31 |
| `packages/mcp-admin-ui/tests/token-history.test.mjs` | PR32 |
| `packaging/inputs.json` | 0.4.4 version binding only |
| `packaging/validate.py` | 0.4.4 version binding only |
| `tests/test_nextcloud_error_secrets.py` | PR33 |
| `tests/test_odoo_child_switch_runtime.py` | PR31 + integration assertions |
| `tests/test_odoo_child_switches.py` | PR31 |
| `tests/test_odoo_error_result_parity.py` | PR30 |
| `tests/test_odoo_read_exists.py` | PR30 |
| `tests/test_odoo_write_descriptions.py` | PR31 |
| `tests/test_six_egress.py` | PR31 |
| `tests/test_token_history.py` | PR32 + integration assertions |
| `upgrade-notes.yaml` | PR32 + integration/release reconciliation |
