# woow_mcp_hermes 0.4.14 image decision

Status: **exact image accepted, published and anonymously verified** (2026-11-18). The HAOS single-profile regression on
the owner's showroom host (Core 2026.7.2, by the owner's decision), the Stable Release and Store synchronization remain
separate gates; see the shared [0.4.14 record](release-decision-0.4.14.md).

Hermes 0.4.14 accepts Home Assistant Core 2026.11.0, 2026.11.1 and 2026.11.2 (PR #81, PR #120; 0.4.13 accepts Core only up to 2026.10.4) and carries the shared changes merged after 0.4.13; the product CHANGELOG lists every item. Hermes advances from 0.4.13 to 0.4.14.

Source: release PR #119 head `24de6ec1cff584c3d9dd32406bc00ca3090f5fea`. The image was built, accepted and published by `.github/workflows/release.yaml`
(PR #121's route) on GitHub-hosted runners, run 44211883565, attempt 1: `gate` (release admission, the `public-release`
environment settings, validation and packaging tests), `candidate` (no registry authority) and `publish`.

Candidate: tested image ID `sha256:8c52b11eb7def4c9c0d6fc332ed0093d22d29261e54d574bebf6f366a498faff` (linux/amd64, 16 layers). Container/mock acceptance passed,
including the child-bearer 401 and root restore-tree checks; the source, full-history and all-layer secret scans, the
Syft/SPDX all-layer SBOM (153 packages), Grype (database built 2026-11-17T06:20:58Z; 260 matches, none
blocking under `packaging/supply-chain-policy.json`) and the license policy passed. The J1900 instruction-set check under
`qemu-x86_64 -cpu Nehalem` (qemu-x86_64 version 8.2.2 (Debian 1:8.2.2+ds-0ubuntu1.18)) passed: child venv: 81 native modules import natively, natively allowlisted `_tkinter`, QEMU-only allowlisted none; core venv: 79 native modules import natively, natively allowlisted `_tkinter`, QEMU-only allowlisted none.

Publication: the owner delegated the `public-release` approval of this run on 2026-11-18 ("准許你去幫我處理我切手動了"); the publish job
checked the environment settings and the owner's approval record (User 165237880), loaded the handed-over archive,
required the tested image ID, pushed `ghcr.io/woowtech/amd64-mcp-hermes:0.4.14` = manifest `sha256:83d5d702c9de5d464da67b55ce1422ac78c63d33e5620b60ef46a3667cb8026b` and read it
back anonymously. A separate anonymous check fetched every layer from the registry and matched each compressed digest,
size and diff ID ([remote layers](../provenance/release-0.4.14-remote-layers.json)).

Evidence: [release-0.4.14-images.json](../provenance/release-0.4.14-images.json) (subject, scan summary, provenance,
published digest and provenance, J1900, runner and approval records; no secret).
