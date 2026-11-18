# woow_mcp_n8n 0.4.14 image decision

Status: **exact image accepted, published and anonymously verified** (2026-11-18). The HAOS single-profile regression on
the owner's showroom host (Core 2026.7.2, by the owner's decision), the Stable Release and Store synchronization remain
separate gates; see the shared [0.4.14 record](release-decision-0.4.14.md).

n8n 0.4.14 accepts Home Assistant Core 2026.11.0, 2026.11.1 and 2026.11.2 (PR #81, PR #120; 0.4.13 accepts Core only up to 2026.10.4) and carries the shared changes merged after 0.4.13; the product CHANGELOG lists every item. n8n advances from 0.4.13 to 0.4.14.

Source: release PR #119 head `24de6ec1cff584c3d9dd32406bc00ca3090f5fea`. The image was built, accepted and published by `.github/workflows/release.yaml`
(PR #121's route) on GitHub-hosted runners, run 44211880072, attempt 1: `gate` (release admission, the `public-release`
environment settings, validation and packaging tests), `candidate` (no registry authority) and `publish`.

Candidate: tested image ID `sha256:5afcfda1f5ddf7d4f1c2f4678f2a59d52ae7f9818f577a116e5908c6430c3936` (linux/amd64, 26 layers). Container/mock acceptance passed,
including the child-bearer 401 and root restore-tree checks; the source, full-history and all-layer secret scans, the
Syft/SPDX all-layer SBOM (277 packages), Grype (database built 2026-11-17T06:20:58Z; 266 matches, none
blocking under `packaging/supply-chain-policy.json`) and the license policy passed. The J1900 instruction-set check under
`qemu-x86_64 -cpu Nehalem` (qemu-x86_64 version 8.2.2 (Debian 1:8.2.2+ds-0ubuntu1.18)) passed: core venv: 79 native modules import natively, natively allowlisted `_tkinter`, QEMU-only allowlisted none; Node v26.12.1 loads better-sqlite3 with FTS5 and zlib the same way.

Publication: the owner delegated the `public-release` approval of this run on 2026-11-18 ("准許你去幫我處理我切手動了"); the publish job
checked the environment settings and the owner's approval record (User 165237880), loaded the handed-over archive,
required the tested image ID, pushed `ghcr.io/woowtech/amd64-mcp-n8n:0.4.14` = manifest `sha256:e30438e2684d377200e0aea8313b19e532070899ef9b9599f011b11cca851d94` and read it
back anonymously. A separate anonymous check fetched every layer from the registry and matched each compressed digest,
size and diff ID ([remote layers](../provenance/release-0.4.14-remote-layers.json)).

Evidence: [release-0.4.14-images.json](../provenance/release-0.4.14-images.json) (subject, scan summary, provenance,
published digest and provenance, J1900, runner and approval records; no secret).
