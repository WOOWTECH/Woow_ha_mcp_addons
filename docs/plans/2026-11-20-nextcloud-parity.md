# Nextcloud Parity Implementation Plan

**Goal:** Align HA Nextcloud behavior with the observed PaaS origin/main contract while preserving HA's security and profile isolation.

**Architecture:** Normalize submitted URLs at the management boundary, preserving valid legacy state until an explicit save. Compare normalized identities, and evaluate policy changes against gateway enforcement and child lifecycle behavior.

**Tech Stack:** Python, Pydantic, Starlette, pytest.

1. Compare PaaS Nextcloud URL normalization, identity and policy tests with HA HM-22.
2. Add regression coverage for both save routes, page suffixes, legacy URLs, identity rotation and unsafe input.
3. Implement safe normalization at the save boundary and review policy restart behavior against HA lifecycle guarantees.
4. Update contract and acceptance documentation; run focused tests and report remaining differences.
