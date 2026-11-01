# EMQX public output-schema parity

This source change prepares a later HA MCP release. It does not alter the published 0.4.9 images, the frozen 0.4.10 release candidate, a HAOS installation, or any PaaS tenant.

## Observed contract gap

The PaaS c195 image source (`c195d5d50d0a8fa8022a825f0568bce8a989e3f1`) and the published HA 0.4.9 image source (`2a485662ecfa8b2452d5e02d83ca39cebf5d3bb0`) declare the same 39 EMQX child tools. Offline extraction with their pinned FastMCP 4.1.3 / MCP 2.3.0 SDKs found **39/39 equal input schemas and 39/39 equal child output schemas**, but the HA gateway exposed **0/39 output schemas**: EMQX had no reviewed gateway pins. The canonical hash of the 39 tool-to-output-schema digests is `dd6ef3dcc321b5537147b0a3df36a7dd1e98930de655c5dddbd0c1850715e0c0`. The per-tool comparison receipt is `docs/provenance/emqx-39-source-schemas.json`, SHA-256 `78a2712fa6c76c619e09fe74d850200fb8f1f7faf888b22b5271e951602ac94d`.

This is **source and offline SDK evidence**, not a comparison of two running OCI images or calls to the same EMQX broker. It establishes a metadata gap, not full behavior parity.

## Controlled publication

`output_schemas.json` now binds all 39 exact `(product, tool, schema)` contracts to their handler source, package lock, vendored source files, and source commit. The registry checks both schema and binding digests. The gateway returns the reviewed schema only when the child candidate equals that exact pin; changed, absent, or unknown child schemas remain omitted. No general child-schema relay was added.

Two EMQX contracts use integer or Boolean defaults. The finite validator now accepts bounded integer defaults only on integer nodes and Boolean defaults only on Boolean nodes, while continuing to reject floating-point, container, mismatched-type, and oversized integer defaults. The generated fallback snapshot was rebuilt from the pinned EMQX child. Tool names, input schemas, connection settings, and operation permissions are unchanged.

## Validation and release boundary

Local focused validation passed 176 output-schema and real-child snapshot tests. The EMQX snapshot test launched the child and gateway against a fake API, compared their full `tools/list` results with the gateway fallback, and observed no fake-backend mutation. Full PR CI, exact-image build and checks, anonymous provenance, and HAOS Supervisor acceptance remain required. The 0.4.10 release source must not be rebound to this branch; merge this source-only patch only after that release's frozen image-source plan is resolved.
