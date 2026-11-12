# woow_mcp_headscale 0.4.18 image decision

Status: **source candidate; exact image build, supply-chain gates and publication pending**. Stable Release, Store synchronization and both HAOS upgrades remain separate acceptance gates.

0.4.18 publishes the output-schema metadata reviewed and merged in PR #86. All 11 Headscale tools now expose the pinned child server's object output schema through public `tools/list`. The existing binding hashes and runtime drift checks remain fail closed: if a child schema or reviewed source binding changes, the gateway omits that output schema instead of inventing or forwarding unreviewed metadata.

This release does not change the 11 tool names, 29 native Headscale v0.29.4 operations, input schemas, write grants, backend requests, Origin policy, DNS fallback or state schema. Headscale alone advances from 0.4.17 to 0.4.18; the shared default remains 0.4.13 and no other Add-on version changes in this release.

Before publication, the exact frozen source must pass the complete source/history/all-layer secret scans, container acceptance, Syft and SPDX SBOM generation, Grype vulnerability policy, license policy and final same-image verification. The authenticated registry check must confirm `ghcr.io/woowtech/amd64-mcp-headscale:0.4.18` is unused; only that accepted image ID may be pushed. Anonymous immutable pull verification and digest-linked sanitized provenance must then be added here before the release PR can merge.

After publication, the normal protected PR checks must pass readiness and the 0.4.17→0.4.18 upgrade comparison. Merge must create `woow_mcp_headscale-v0.4.18` and synchronize the Store before both HAOS hosts are upgraded. Post-upgrade acceptance must verify the published digest, 11 output schemas, all 29 native operations against disposable real Headscale backends, real pending approve/reject flows, Origin denial, state/token persistence and the non-public MCP port boundary.
