# 0.4.6 release decision — 2026-10-29

Status: **source integration; pending exact-source CI and image publication**. No 0.4.5 image or receipt covers
this release. The immutable source commit will be recorded only after source review and its required checks.

## Contents and compatibility

- Partial connection editing preserves omitted fields byte-for-byte and explicitly clears only nullable fields.
  Admin bootstrap exposes credential presence only; configured credentials embedded in public display fields,
  including percent encoding, cause the whole display field to be withheld. Existing whole-connection replacement
  remains available. A deliberate URL/account edit may reuse retained credentials at the new destination.
- n8n native sessions can be configured with 60–86400 seconds and 1–100 sessions. Seconds round upward to whole
  minutes, matching PaaS. Absent saved settings retain HA's existing 600 seconds / 20 sessions without a rewrite.
- Odoo administrators can save up to 128 exact public model.method exceptions, with the existing outer tool
  grants, child write switches, standard-write restrictions and chatter policy still enforced. This list does not
  restrict the separately enabled broad unknown-method mode. Existing state means an empty list without a rewrite.
- Native n8n direct inputs retry once only for the pinned SDK's exact inputs.type discriminator validation failure.
  Negotiation is scoped to the official client identity. Other failures do not retry; after the one allowed retry,
  its actual outcome is retained, including uncertain execution/transport failures. No failure is cached and no
  third call is made. Existing backend error text and MCP isError behavior are preserved.
- Reviewed outputSchema is exposed for 35 LiteLLM and eight Nextcloud tools, with exact product/tool/schema matches,
  bounded validation and a source-pinned registry. Missing, changed or unknown live contracts are omitted. Other
  tool schemas and permission boundaries are unchanged; this is not a claim of a complete schema registry.
- LiteLLM normalizes only exact origin-root `/v1` and trailing slashes, preserving prefixed proxy mounts. Health,
  token counting and cost estimation require active-operation permission; old read denies stay effective. Native
  readonly becomes 15 tools, all-enabled remains 40, and HA's existing 25 exact grants are unchanged. Health can
  incur charges/save history; token/cost calculation may fetch resources but does not run inference or billing.

All new management mutations use the current CSRF/role boundary and a required reviewed If-Match revision.
Saving commits before child application; a later application failure remains `saved:true`/`config_apply_failed`.
Saving n8n sessions or Odoo method exceptions adds optional schema-4 fields. Older binaries reject those fields;
downgrade requires the compatible pre-upgrade add-on backup and its binary, with token/permission review afterward.
See [settings contract](partial-settings-contract.md) and the root upgrade notes.

## Required release evidence

1. Fresh checks and Release train success for the exact committed source; independent feature and integration review.
2. Six linux/amd64 images through the existing private builder, each passing exact-image P1–P5, current/full-history/
   layer secret scans, SBOM/CVE/license policy, installed package, packaged runtime, UI and UID gates. A policy pass
   does not mean zero CVEs; existing secret triage remains subject to its precise review conditions.
3. Publish only accepted immutable IDs, then independently verify anonymous manifest/config/ordered layers/source
   identity and fresh remote blob bytes. Preserve failed attempts. Provenance is unsigned and the Docker daemon is
   shared: no host-isolation or SLSA claim.
4. Commit the actual publication record, pass final readiness and all required checks, then merge normally.
5. Verify six stable Releases, Store and Local Download after merge. New isolated HAOS upgrade/settings/rollback
   acceptance is a separate gate; no ws97 reinstall, off-cluster backup or full production restore is implied.

Seven source manifests share the version; only Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud publish.
OpenDesign remains disabled and Odoo Manage archived. This decision will be completed with actual evidence;
no image publication or installed-runtime success is claimed at this stage.
