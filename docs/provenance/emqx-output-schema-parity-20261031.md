# EMQX public output-schema parity

This source change was reviewed separately from the earlier frozen 0.4.10 candidate. The owner's later #54 merge placed it on `claude-delivery`; release PR #47 now rebinds its 0.4.10 source candidate to that merge. It does not alter the published 0.4.9 images, a HAOS installation, or any PaaS tenant, and the earlier 0.4.10 freeze does not prove the rebound candidate.

## Observed contract gap

The PaaS c195 image source (`c195d5d50d0a8fa8022a825f0568bce8a989e3f1`) and the published HA 0.4.9 image source (`2a485662ecfa8b2452d5e02d83ca39cebf5d3bb0`) declare the same 39 EMQX child tools. Offline extraction with their pinned FastMCP 4.1.3 / MCP 2.3.0 SDKs found **39/39 equal input schemas and 39/39 equal child output schemas**, but the HA gateway exposed **0/39 output schemas**: EMQX had no reviewed gateway pins. The canonical hash of the 39 tool-to-output-schema digests is `dd6ef3dcc321b5537147b0a3df36a7dd1e98930de655c5dddbd0c1850715e0c0`. The per-tool comparison receipt is `docs/provenance/emqx-39-source-schemas.json`, SHA-256 `78a2712fa6c76c619e09fe74d850200fb8f1f7faf888b22b5271e951602ac94d`.

This is **source and offline SDK evidence**, not a comparison of two running OCI images or calls to the same EMQX broker. It establishes a metadata gap, not full behavior parity.

## Controlled publication

`output_schemas.json` now binds all 39 exact `(product, tool, schema)` contracts to their handler source, package lock, vendored source files, and source commit. The registry checks both schema and binding digests. The gateway returns the reviewed schema only when the child candidate equals that exact pin; changed, absent, or unknown child schemas remain omitted. No general child-schema relay was added.

Two EMQX contracts use integer or Boolean defaults. The finite validator now accepts bounded integer defaults only on integer nodes and Boolean defaults only on Boolean nodes, while continuing to reject floating-point, container, mismatched-type, and oversized integer defaults. The generated fallback snapshot was rebuilt from the pinned EMQX child. Tool names, input schemas, connection settings, and operation permissions are unchanged.

## Validation and release boundary

Local focused validation passed 176 output-schema and real-child snapshot tests. The EMQX snapshot test launched the child and gateway against a fake API, compared their full `tools/list` results with the gateway fallback, and observed no fake-backend mutation. Full PR CI, exact-image build and checks, anonymous provenance, and HAOS Supervisor acceptance remain required. This source-only evidence did not clear the earlier frozen 0.4.10 source. The owner subsequently merged integration PR #54 into `claude-delivery` at `274f226edc1e4616a63835247b37ef8de6d6d25f` and requested a new source binding for release PR #47. Its new head requires a fresh freeze and independent builder gates; the old freeze and CI cannot be reused.

## 2026-11-01 source-only integration with EMQX error guidance

The integration of source PR #51 changes only `apps/emqx/vendor/emqx_mcp_server/errors.py` among the 20 EMQX files bound by this registry. All seven handler files for the 39 output contracts are byte-identical to the published 0.4.9 source in the receipt above. The registry's integrated EMQX source is therefore rebound to commit `083959f241994ed82b87cec6e395d807c4eebcb2`, whose 20 bound files match this tree, with `errors.py` SHA-256 `c4ec6ebe98df07ec625d2a438f316e8f2c43d78e825ba6194d121a9e37755b11`. The per-tool comparison receipt remains historical source/SDK evidence for 0.4.9; it is not an OCI or real-broker acceptance of the integrated tree.
