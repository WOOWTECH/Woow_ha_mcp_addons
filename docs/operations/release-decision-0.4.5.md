# 0.4.5 release decision — 2026-10-29

Status: **candidate; exact-source images and publication pending**.

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
