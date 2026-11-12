# 0.4.6 release decision — 2026-10-29

Status: **six exact-source images published and independently verified**. Final publication-record checks, protected merge and distribution remain separate gates in [PR #39](https://github.com/WOOWTECH/Woow_ha_mcp_addons/pull/39).

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
OpenDesign remains disabled and Odoo Manage archived. Installed-runtime acceptance is recorded separately.


## Exact-image publication

Image source: `28b8317ec12c47c81c946fe9aaec18dd1d5ad852`; tree `74366796fc35251a7dba2499528698ea0934bfba`. The later documentation commit is not the image source.
Fresh hosted source checks passed 3,088 Python tests and 68 browser cases; WVT and Upgrade comparison passed.
The fresh UI build also passed 43 unit tests and 68 browser cases; 68 private-helper guards passed.

All six linux/amd64 images passed P1–P5, packaged runtime with owned mocks, current/full-history/layer secret
scans, SBOM/CVE/license policy, final installed package checks, exact UI bytes and UID10001 DAC. Prior 0.4.5
image IDs were preserved. Scanner and precise secret-triage policy bytes are unchanged; their security review
scope and exact exceptions remain explicit. Passing policy does not mean zero vulnerabilities.

Only accepted immutable IDs were published. Anonymous manifest/config/source/platform/ordered-layer metadata
checks passed. A separate fresh download verified 83 unique remote layer blobs
covering 103 ordered image-layer positions and
343,920,204 compressed bytes; every compressed digest/size and uncompressed
diffID matched. This verification used neither Docker nor a local layer cache; CDN cache state is not claimed.
Publisher credentials and owned temporary registry aliases were cleaned. Accepted local images remain.
See [image provenance](../provenance/release-0.4.6-images.json) and
[remote-layer evidence](../provenance/release-0.4.6-remote-layers.json).

Provenance is unsigned and the Docker daemon is shared. No SLSA, host-isolation or hosted BLD2 admission is claimed.

| Product | Immutable published reference |
| --- | --- |
| odoo | `ghcr.io/woowtech/amd64-mcp-odoo@sha256:747a820c93a9db7195cf1f436fc7b89da9ea9a2fb15273d2d722af55d901159f` |
| n8n | `ghcr.io/woowtech/amd64-mcp-n8n@sha256:2963271d91c61495bc12e0945ebeddecb23b102250488b636e72600865ba20f4` |
| hermes | `ghcr.io/woowtech/amd64-mcp-hermes@sha256:41aa90ccf9c5c44c7ad8312137e09104b3a9c48425b349e84b2f92e5baa957aa` |
| emqx | `ghcr.io/woowtech/amd64-mcp-emqx@sha256:1d24f9e9c7176365d0e9bbc89909bd8fc1c238bf03c66e5b1eccd7c5502b0603` |
| litellm | `ghcr.io/woowtech/amd64-mcp-litellm@sha256:36064f52e430f0f7ff9e1bd2a1a9fb3214b06c7ebaf76962279712bb61514abf` |
| nextcloud | `ghcr.io/woowtech/amd64-mcp-nextcloud@sha256:4df8574149d70339e11da27568a7c85f1ef6f13ebf55d1d9fb6ce61204614631` |

HAOS upgrade/settings/partial restore and real-backend acceptance are separate evidence. These image gates do not establish a ws97 reinstall, off-cluster backup or full production restore.
