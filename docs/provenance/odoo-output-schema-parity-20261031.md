# Odoo public output-schema parity

Source change for the next HA MCP release. No version, OCI image, HAOS add-on, or
PaaS tenant is changed by this commit.

## Observed gap

An authenticated, read-only `tools/list` from existing PaaS Odoo service 175
(pinned `accea2e6` image) advertised `outputSchema` for all 41 tools. The
released HA 0.4.9 Odoo image, run in an isolated Pod outside HAOS Supervisor,
advertised none. The earlier 41/41 parity result covered names and input
schemas only. The full PaaS output schemas were compared by canonical SHA-256
against raw `tools/list` from the actual pinned HA Odoo child with a fake Odoo
API: **41/41 identical**. The HA gateway removed them because Odoo had no
reviewed public output-schema pins. This is a gateway publication gap, not an
upstream Odoo child schema difference.

Local evidence: `PAAS-ODOO-OUTPUT-SCHEMA-READONLY-v3-20261031.json`,
`HA049-ODOO-IMAGE-RUNTIME-RAW.json`, and
`HA-ODOO-CHILD-OUTPUT-SCHEMAS-20261031.json` in the tool-parity-live lane.
The PaaS probe made no business call or admin write, deleted its MCP session,
and checked the same Pod UID, image ID, and unchanged configuration afterward.
These files are local acceptance evidence; the CI tests independently capture
the pinned HA child again.

## Controlled publication

`output_schemas.json` now pins all 41 Odoo tool contracts by canonical schema
digest and a second `{product, tool, schema}` binding digest. The source record
pins `odoo-mcp==1.3.0` via `apps/odoo/uv.lock`, the SDK versions, the launcher
and switch overlay files at protected source commit `fc5c7cf4`. Every entry's
handler source points to the locked package manifest. The generated fallback
snapshot was rebuilt from the real child; it gains only the 41 Odoo
`outputSchema` values. Tool names, inputs, authorization, and other products'
metadata remain unchanged.

The validator still requires exact product/tool/schema equality and returns a
fresh copy. Its finite vocabulary now admits the features in these reviewed
Odoo contracts: bounded title/description text, null or short string defaults,
five nested `additionalProperties` schemas, empty nested JSON nodes, and four
references to definitions inside the same root schema. It does not resolve
references. External, missing, and recursive references, regex patterns,
formats, unknown keywords, excessive depth/size, changed child contracts, and
damaged registry data fail closed. No arbitrary child metadata is relayed.

## Verification and release boundary

Focused local validation before CI: 116 schema-contract tests, the actual
Odoo child and gateway/fallback comparisons, and Python MCP 2 plus TypeScript
SDK 1.32.2 calls through the real gateway to a fake Odoo API. The existing
Odoo error-result test checks that failure `structuredContent` fits the
declared schema for every tool. Full repository CI and package/source inventory
must pass on the PR head. The next release still requires six exact OCI images,
image-level P1–P5, anonymous pull checks, provenance, and HAOS Supervisor
acceptance. The 0.4.9 images retain the observed omission.
