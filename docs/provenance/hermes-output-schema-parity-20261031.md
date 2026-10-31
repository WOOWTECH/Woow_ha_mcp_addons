# Hermes public output-schema parity

This source change prepares a later HA MCP release. It does not change the current 0.4.9 images, the 0.4.10 release PR, a HAOS installation, or any PaaS tenant.

## Observed contract gap

An authenticated, read-only `tools/list` on the existing PaaS Hermes tenant image (`accea2e6`) advertised output schemas for all 11 Hermes tools. The exact HA release-candidate source at `33bc36e7` produced the same 11 schemas from its pinned Hermes child with a synthetic backend, but its gateway advertised **0/11**. The HA registry had no Hermes pins, so the gateway deliberately omitted the child-owned output metadata. All 11 child schemas matched the PaaS runtime schemas by canonical SHA-256; the PaaS output hash-map SHA-256 was `442e23b55b5db7a24604296aa51f46c286383232576383b69b662a727aa3b83e`. The PaaS metadata probe made no business-tool call or admin write, deleted its session, and confirmed the service configuration was unchanged. The HA probe used only a local fake API; it was not a published image or HAOS run.

## Controlled publication

`output_schemas.json` now pins those 11 exact `(product, tool, schema)` contracts with separate schema and binding digests. It binds the Hermes SDK lock, launcher, and vendored handler bytes at the protected `0c337996` source base. Every schema passes the existing finite, bounded validator; no vocabulary or general child-schema relay is added. The generated fallback snapshot was rebuilt from the real pinned child and now includes its 11 reviewed output schemas. Tool names, input schemas, connection settings, and operation policy are unchanged. A changed or missing child output schema remains omitted.

## Validation and release boundary

Local focused validation passed 136 schema/runtime/snapshot tests plus two Python MCP 2 and TypeScript SDK 1.32.2 client calls through the real gateway to the fake Hermes API. Full PR CI, exact-image build, P1–P5/security checks, anonymous provenance, and HAOS Supervisor acceptance remain required. The 0.4.10 source freeze and builder plan must not be silently rebound to this branch; if this fix is included in 0.4.10, both must be regenerated and independently reviewed.
