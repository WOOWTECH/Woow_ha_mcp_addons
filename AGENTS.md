# AGENTS.md

Rules for every agent and person who changes this repository. The full
release mechanism is described in the Woow_HA_App_Store README (section
"版本策略與同步") and in ADR-0005 of the WOOW addon pipeline.

1. **``claude-delivery`` only changes through a pull request.** A ruleset blocks direct
   pushes, force pushes and deleting the branch, and nobody can bypass it.
   Push a branch, open a PR, wait for the required checks, then merge.
2. **A PR that changes an addon version is a release.** Merging it publishes
   that version to the WOOW App Store. It must pass every required check; the
   checks are the approval, there is no human review step. Every PR runs
   `Upgrade comparison / compare` (pipeline #89); treat a failure as blocking.
   It compares each addon whose version the PR changes with the latest Stable
   Release. A PR that changes no version passes it in seconds. The result is
   in the job summary.
3. **Breaking changes must be declared in `upgrade-notes.yaml`** next to the
   addon's `config.yaml` (here `addons/<x>/upgrade-notes.yaml`). Create the
   file only when the upgrade comparison asks for it; copy `change` and `key`
   from its report and write the migration path. Images are built only on the
   self-hosted builder, never on a PR, so the image vulnerability comparison
   pulls the published GHCR images (the Release's and the new version's amd64
   image, pipeline #148): publish the new version's image with the builder
   before the PR can pass, as `readiness` also requires. The upgrade test
   (pipeline #155) runs on the same published images: each changed addon's
   Release image starts first, then the new version's on the same `/data`,
   and both must answer ingress on 8099 and stay up. No backend is configured,
   so it checks startup only, no data. An unpublished new tag fails both the
   vulnerability comparison and the upgrade test. The release puts these
   entries on the GitHub Release. Rules, change names and the file format: the
   Woow_HA_App_Store README, section "升版比對與 `upgrade-notes.yaml`".
