# 0.4.4 release decision — 2026-10-29

Status: **draft release candidate; images NOT built or published; exact-image acceptance and readiness pending**.

Mainline selected one 0.4.4 release for the integrated PR30/31/32/33 functionality. Seven source manifests,
Dockerfile BUILD_VERSION defaults, core VERSION, packaging inputs/validator and workflow tags now bind 0.4.4.
Only Odoo, n8n, Hermes, EMQX, LiteLLM and Nextcloud are enabled for publication. OpenDesign receives source
metadata only and stays disabled in the Store; Odoo Manage remains archived with unchanged version bindings.

## Exact sources and relationship to existing PRs

The integration was prepared on PR29 `a3030679f69b6b68266e9a0f98a46b14b88a479e` (0.4.3).
After its protected merge at 2026-10-29 03:31:39 UTC, the integration parent was updated to
`f378a7752538d0cdbf2a23db4af3dfb7ceee0e39`; Git tree equality was verified before updating the branch. It incorporates:

- PR30 `23574112a9a6528d54c37088e32dc3de1094f2d6`: Odoo `success:false` becomes MCP `isError:true` with the
  published structuredContent envelope retained; traceback errors are reduced to their final exception line.
- PR31 `0704c9a3ca23952be3901edd39cd7e5b0b4e5ee1`: four saved Odoo child write switches, strict admin API/UI,
  source-guarded PaaS decisions and matching live/offline descriptions.
- PR32-only delta `0704c9a3..ca064c2ab05d852a3c0e29001c9763997bc86dde`: masked current token and at most five
  masked token transitions, atomic persistence and post-commit lease invalidation.
- PR33 `d81bc7c578746b0a94ea762e103db81b7d101f30`: mask configured Nextcloud credentials in parsed backend
  errors before lossy whitespace folding/truncation, retaining detailed diagnostic/error behavior.

The draft proposes replacing the separate feature merge/release paths of PR30/31/32/33. It does not close or modify
those PRs. PR29 completed independently under mainline ownership. This branch must not merge or
publish until mainline verifies all gates and coordinates the feature PRs. The [integration record](../provenance/ha-mcp-parity-integration-20261029.md) lists every changed
file, provenance decision, local check and remaining limitation.

The existing 0.4.3 receipt binds its image source `a1c118191a004a08e92273674de58bb7c24b18b4`. Its receipt and
release decision stay byte-identical to PR29. Neither that receipt, its successful readiness nor its CI is evidence
that this 0.4.4 tree has been built or accepted. The new image source must be the reviewed integration commit
selected after mainline coordination, not any PR30/31/32/33 head or the earlier 0.4.3 source.

## Compatibility and remaining parity

Schema 4 keeps its number and does not rewrite pre-existing state on startup. Missing Odoo switches retain the
prior four-on behavior. Explicitly saving them adds `odoo_write_switches`; a token rotate/revoke adds
`token_history`. **The 0.4.3 exact-key decoder rejects either field.** Take an add-on backup before upgrading;
downgrade after either action requires restoring the pre-upgrade backup with the binary. Review restored
grants/denies and reissue the MCP token/update clients as needed, since restoring a backup can restore an old
token. Do not silently strip new fields or edit state.json. See [upgrade-notes.yaml](../../upgrade-notes.yaml).

Outer tool grants/operation denies remain in force. HA still lacks editable PaaS exact `model.method` allowlists;
revoking the outer `execute_method` grant removes that whole tool, including its reviewed reads. The four child
switches do not introduce a way around this outer permission. Mainline can decide any further parity work
separately; these three requested features and the Nextcloud security fix are integrated together.

The Nextcloud correction covers known configured password/Basic forms (literal, URL quoting, JSON escaping,
standard and URL-safe base64). Unknown backend secrets and arbitrary encodings remain outside the bounded
contract. The unrelated helper-only Nextcloud 401/429 work at `21cd303` is not included. Mainline is reviewing
PR33; this integration does not claim that independent review is complete.

## Gates owned by mainline after this draft

1. Use the frozen draft integration source SHA based on the verified PR29 merge. Complete the single hosted full
   `checks` run and Release train for that source. Local focused tests do not replace these required checks.
2. On the private builder, preserve previous images and check that six target 0.4.4 tags are available. Build only
   the six enabled linux/amd64 products from that source. Run exact-image P1–P5, current-source/full-history/layer
   secret scans, SBOM/CVE/license policy, final Debian security package versions, container mocks, UI and UID gates.
3. Publish only accepted immutable image IDs, then independently read back anonymous digests, config/layers,
   platform and source labels. Add a new `docs/provenance/release-0.4.4-images.json` receipt only when evidence exists.
4. Require green readiness and all protected checks at the final PR head before mainline merges. Verify the six
   stable Releases and Store synchronization after merge. HAOS/ws97 acceptance remains a separate lane.

No image build, release dispatch, publication, protected merge, Store update or HAOS/production change is
performed by preparation of this draft. There is no fabricated 0.4.4 image receipt.
