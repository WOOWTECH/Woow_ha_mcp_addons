# 0.4.5 release decision — 2026-10-29

Status: **six exact-source images published and independently verified**. Protected merge and distribution outcomes are recorded in [PR #38](https://github.com/WOOWTECH/Woow_ha_mcp_addons/pull/38) and its post-merge release workflow; this decision records the image-publication gate.

This integrates PR35 (`d730837a41c988398032677bb5adfff58d3e13ee`) and PR36
(`3c933c95f014f6f36b33a13aa738c5278c57eb7a`) on the protected 0.4.4 merge
`8e813b68a75099b4554c90d096c9f95f2735b396`. The final image source is selected only after
committing this integration and obtaining its own hosted checks and Release train success.
The existing 0.4.4 images, receipt and readiness do not prove this source is built.

## Contents and compatibility

- n8n native `success:false` tool results set MCP `isError:true`, retaining text and structuredContent;
  `valid:false` validation results stay normal results. The pinned idempotent patch preserves the earlier test-run error patch.
- Three n8n selectors expose 22 reviewed operations: agents.action (15), workflow test.method (5), catalog.kind (2).
  The existing 33 write grants are unchanged. Whole-write tool grants remain required even for a reviewed read operation.
  Missing required, unknown, null or malformed selectors refuse before dispatch. Missing/ECMAScript-blank test method
  retains native auto; denying trigger also denies auto/default. `exposeToMcp` still requires its updater grant.
- LiteLLM registry describes the actual existing `PATCH /model/{model_id}/update` handler; routing and arguments are unchanged.
- PR36's hosted checks exposed two stale tests: the fixed operation-effect projection and a migration test that
  inadvertently borrowed current selectors for the historical catalog. The legacy catalog itself remains byte-identical.
  The corrected baseline checks restore the previous whole-write projection to verify that all other effects are unchanged.
- The first integration CI run exposed the recurring standalone-browser context teardown race (63 browser tests
  passed, one teardown timed out). The test harness now rejects new sends and drains retained route responses
  before closing their API context, while keeping destination guards installed. A deterministic lifecycle
  regression fails before this correction and passes after it. This changes test cleanup only, not the shipped UI.
- No schema number or state key changes. Downgrading to 0.4.4 with new operation denies retains those restrictions but
  suppresses the entire affected tool because the old policy lacks that selector metadata. Back up first; review
  `upgrade-notes.yaml` and restore the pre-upgrade backup when old behavior is required. Backup restore may restore tokens.

## Required release evidence

1. Exact committed source: fresh full hosted checks and WVT; independent focused migration/selector/child tests.
2. Six fresh linux/amd64 images through the existing private builder, each with exact-image P1–P5, secret scans
   (current source, full history, all image layers), SBOM/CVE/license policy, installed Debian versions, UI and UID gates.
   Existing scanner/policy/triage bytes remain unchanged; a policy pass does not mean zero CVEs.
3. Only accepted immutable IDs may publish; anonymous complete pulls and independent manifest/config/layer/source checks.
   Provenance is unsigned and the private Docker daemon is shared; no host isolation or SLSA claim.
4. Add the actual receipt only after publication. Final PR head must pass required checks and readiness before normal merge.
5. Independently verify six stable Releases, Store and Local Download contents after merge. Synthetic HAOS and isolated
   real-backend acceptance are separate evidence scopes; neither is a ws97 reinstall or full production restore.

Seven source manifests share 0.4.5; only Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud publish.
OpenDesign stays disabled and Odoo Manage remains archived. No claim is made that the wider parity backlog is finished.


## Exact-image publication

Image source: `2910f5ee65cf27c04eb2d39072c2a357347d657c` (PR38); tree `4297c99ad05206e164e2b1f2e18355e613b8116f`. This later evidence commit is not the image source.
Hosted source checks passed 2879 Python tests and 64 browser cases, with WVT green.
Main independently verified 39 UI unit tests, all 64 browser cases and 47 private-helper guards.

All six linux/amd64 images passed P1–P5, actual packaged runtime with owned mocks, current/full-history/layer
secret scans, SBOM/CVE/license policy, final installed Debian package versions, exact UI bytes and UID10001 DAC.
The six prior 0.4.4 image IDs were preserved; new 0.4.5 tags were unused before this publication. Scanner/policy/triage
bytes are unchanged from 0.4.4. A policy pass does not imply zero vulnerabilities; no broad secret/CVE exception was added.

Only accepted immutable IDs were published. Anonymous complete pulls and a separate manifest/config/ordered-layer/
source/version/platform comparison passed. Temporary publisher aliases and credentials were cleaned; accepted local
images remain. See [provenance](../provenance/release-0.4.5-images.json). Provenance is unsigned and the private daemon
is shared: no SLSA or host isolation claim.

| Product | Immutable published reference |
| --- | --- |
| odoo | `ghcr.io/woowtech/amd64-mcp-odoo@sha256:63dbf2f7dc556fc20f9a3fc2e3304fa58111dac81f82e9028c971bba9c99adaa` |
| n8n | `ghcr.io/woowtech/amd64-mcp-n8n@sha256:12da73540d7711653cc599c13eb7f32bade4561bf36263546ddfb919eb2a8745` |
| hermes | `ghcr.io/woowtech/amd64-mcp-hermes@sha256:76a83979a84e6ed17675b4272a42cb7b07f5bfd9555ac88370569a0a1f448cd8` |
| emqx | `ghcr.io/woowtech/amd64-mcp-emqx@sha256:ab6ad1cb6e761c5ab3386ccbcb25178a55439acb3947794aa81e97ad344a0f22` |
| litellm | `ghcr.io/woowtech/amd64-mcp-litellm@sha256:3118d1de5cb8df6762aacad899ec636bf1442aedbe05bfa9b390d261cd88525b` |
| nextcloud | `ghcr.io/woowtech/amd64-mcp-nextcloud@sha256:97a15aada2f4f60142b813c9019725b27954adb3aaee01866f0c804fde8a3091` |

Final publication-record checks/readiness, normal protected merge and Store/Local Download readback are separate gates.
Synthetic HAOS and isolated real-backend acceptance are reported separately; these image gates do not prove a ws97 reinstall or full production restore.
