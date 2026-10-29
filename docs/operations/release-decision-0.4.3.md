# 0.4.3 release decision — 2026-10-28

Status: **source candidate; exact-image publication and protected merge pending**.
Source branch: `release/ha-mcp-0.4.3-20261028`, based on merged PR #26 at
`f71fb756baf5ca3458b32c5c20635e0689c13118`. The exact image source
commit and six immutable digests will be recorded after the source checks and
private builder acceptance. A later publication receipt commit is not image
source.

## Scope and compatibility

Six Store-enabled add-ons (Odoo, n8n, Hermes, EMQX, LiteLLM, Nextcloud) take
the merged one-time all-on change from PR #26. On first start, a schema 1/2/3
state is saved as schema 4 with every tool and write allowed, matching the PaaS
default. A policy-only recovery record is saved first, and the normal admin
panel shows a notice with an optional restrictive restore. Token, child token,
backend and endpoint are retained. The old upgrade review page and its 503
gate are removed. A schema 4 state is not rewritten. An invalid or unreadable
legacy state, or a recovery write failure, stops before the child starts.

This is a security-relevant behavior change for legacy installations: writes
that the old policy denied become available until an administrator restores
the previous limits. The Store changelogs tell owners to open the panel after
the upgrade. `upgrade-notes.yaml` and the
[migration guide](legacy-migration.md) explain the exact restore, failure and
rollback path. A migrated state has the new `owner_defaults_20261025` marker;
0.4.2 rejects it, so a binary rollback requires the pre-update add-on backup.
An installation already at schema 4 keeps its state and can return to 0.4.2
without state conversion. Downgrades still require live verification.

The six tool inventories, runtime dependency locks, image names, architecture,
ports, options and state schema remain as in 0.4.2. OpenDesign stays disabled
in the Store and receives only matching source metadata; do not build or
publish an OpenDesign image.

The Odoo child-error contract correction in PR #30 is outside 0.4.3. A child
reply with `success:false` can still surface as MCP `isError:false` in this
release; the PaaS #89 result is `isError:true`. PR #30 will be reviewed and
released separately as 0.4.4.

## Release gates

1. Freeze and verify the exact source SHA. `packaging/inputs.json`, seven
   manifests and Dockerfiles, runtime `VERSION`, validator and CI tags must
   all say `0.4.3`; the retired Odoo Manage version remains untouched. Run
   validator, full unit/integration suite, UI build and browser tests, plus
   `checks` and Release train at that SHA.
   The first 0.4.3 builder attempt from `193c281` stopped at the source
   Gitleaks gate before publication: three #26 migration fixtures share one
   synthetic dummy backend key. The follow-up source binds an exception to
   that one whole value, its fixed SHA256 and three exact fixture paths in
   `packaging/secret-triage.json`. The default scanner rules and blocked
   vulnerability policy remain unchanged. Review this new exception and rerun
   both current-source and full-history scans from the new source; the failed
   attempt is not image acceptance evidence.
   A second attempt from `049b7d1` built Odoo and passed container/mock,
   source/history secret, image secret, and SBOM checks, but the policy gate
   rejected two fixed High findings for `CVE-2026-84782` in the pinned Python
   base's `libssl3` and `openssl` `3.0.22-1~deb12u1`. It produced no candidate
   receipt or publication. [Debian's bookworm security fix](https://security-tracker.debian.org/tracker/CVE-2026-84782)
   is `3.0.22-1~deb12u2`; `packaging/inputs.json` now binds both packages to that
   exact version from the signature-checked `20261028T000000Z` Debian security
   snapshot, using the repository's preexisting `os_upgrades.py` mechanism in
   each Dockerfile. The six images must be rebuilt and all gates rerun from
   this later source. The vulnerability policy is unchanged.
2. On the same private builder route as 0.4.2, preserve the six 0.4.2 image
   IDs and confirm six 0.4.3 tags are absent. Build six new `linux/amd64`
   images from the frozen source, then run exact-image P1–P5, source/history/
   all-layer secret scans, SBOM, vulnerability and license policy, container
   acceptance, UI asset and UID 10001 checks.
3. Publish only those accepted image IDs. Independently pull each immutable
   digest anonymously, comparing manifest, config, ordered layers, platform
   and source label. Commit the sanitized receipt to this branch; readiness
   must become green before the protected merge.
4. After merge, verify six stable `<slug>-v0.4.3` Releases and WOOW HA App
   Store sync. The live ws97 upgrade, backup, notification and restore
   acceptance is owned by the separate HAOS lane and is not inferred from
   image publication or Store visibility.

Until these gates have actual receipts, this document is a plan rather than
proof of image acceptance or publication.
