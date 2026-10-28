# HA MCP 0.4.3 Release Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Publish the six Store-enabled HA MCP add-ons at 0.4.3 from merged PR #26, with exact-image evidence and a verified Store release.

**Architecture:** Freeze a reviewed source commit on an isolated PR branch. The release changes version bindings and records the schema 1–3 one-time all-on migration; OpenDesign receives matching source metadata but no image or Store release. A private disposable builder accepts and publishes the exact six images, then the protected PR merge triggers the stable Releases and Store synchronization.

**Tech Stack:** Python 3.13, Node 26, uv, GitHub Actions, Docker on the private builder, GHCR, WOOW HA App Store.

---

### Task 1: Freeze and describe the release

**Files:** `packaging/inputs.json`, `packaging/validate.py`, `packages/mcp-admin-core/mcp_admin_core/__init__.py`, seven `addons/*/config.yaml`, seven `apps/*/Dockerfile`, `.github/workflows/ci.yaml`, `.github/workflows/release.yaml`, `upgrade-notes.yaml`, `CHANGELOG.md`, `README.md`, seven `addons/*/CHANGELOG.md`, `docs/operations/release-decision-0.4.3.md`.

1. Confirm `origin/claude-delivery` still contains PR #26 at `f71fb75` and the six `0.4.3` tags do not exist.
2. Bump every executable version binding from `0.4.2` to `0.4.3`; leave historic records and the retired Odoo Manage version intact.
3. Move the pending upgrade note to 0.4.3 from 0.4.2. State the schema 1–3 migration, restore path, schema 4 preservation, and rollback via pre-update backup.
4. Record the new behavior in the release decision, top-level and add-on Store changelogs, then run `git diff --check` and `python packaging/validate.py`.
5. Commit the source freeze. A later publication receipt is a separate documentation commit and is not an image source.

### Task 2: Verify the exact source

**Files:** release branch and CI evidence only.

1. Push the source branch and open a PR against `claude-delivery`.
2. Require full `checks` and Release train at the exact source commit. Run local packaging validator, packaging tests, UI build/unit/browser where the environment supports them.
3. If any check fails, fix on a new source commit and repeat the exact-source gates. Do not build an image from a stale commit.

### Task 3: Build and publish six exact images

**Files:** private builder evidence; `docs/provenance/release-0.4.3-images.json`; `docs/operations/release-decision-0.4.3.md`.

1. Confirm private builder identity, clean source bundle, prior image preservation and six absent GHCR tags.
2. Build six fresh linux/amd64 images from the frozen source. Run container acceptance and exact-image P1–P5, source/history/layer secrets, SBOM, CVE, license and UI/UID checks.
3. Push only accepted image IDs. Independently pull anonymous immutable digests and compare manifest, config, ordered layers, architecture and source label.
4. Commit the sanitized receipt, push the PR branch and require green readiness and Release train at the final head.

### Task 4: Merge and verify Store release

**Files:** remote PR, Releases and Store registry.

1. Merge the protected PR only after all required checks are green.
2. Confirm six `woow_mcp_<product>-v0.4.3` stable Releases, release workflow and Store sync results, then read back Store entries.
3. Report exact commits, PR, CI run IDs, immutable image digests and any remaining ws97 acceptance separately. Do not mutate ws97 in this lane.
