# Builder runner contract — BLD2 (current route BLOCKED)

**WOOWTECH is a GitHub USER, not an organization. The current personal-repository
route is BLOCKED, not merely unconfigured.** It cannot supply the mandatory
organization/enterprise runner group and selected-workflow restrictions in this
proposal. Required reviewers for private environments are also plan-restricted:
GitHub Free/Pro/Team provide that feature only for public repositories. Source
is NOT cleared for publication. No VM, label, repository variable or operator
assertion can substitute for an unavailable control.

`builder_contract.py` hard-denies this route **before Git/Docker or software-file
access**, even with an otherwise valid `BLD2_APPROVAL`. There is no environment
switch to override it. The group-based workflows are a **future organization-
controlled PROPOSAL only**. Enabling a future route requires an explicitly approved
hosting/control decision, exact account/plan/control evidence and a reviewed code
change (SPEC reverify, then NEW SECURITY). This patch does not change namespace,
transfer source, register a runner, publish source, or choose another hosting path.
A standalone operator-controlled private VM could be a distinct **unapproved next
decision**; it is not an implemented workaround or permission to bypass admission.

No real builder has been downloaded, installed or executed here. This is not an
isolation attestation, image PASS, publication clearance or HA acceptance. No
Engine/client/API/embedded BuildKit version or VM has been approved. All **18
release gates remain false**, `approved_commit` remains null.

## Future path and gates (not enabled)

1. Hosted `unit` stays independent on `ubuntu-24.04`, with `contents: read`.
   Hosted admission fails rather than silently skipping image acceptance: the
   current route always denies; missing/empty/NOT_APPROVED authorization, PRs,
   non-main, wrong source or expired approvals also deny in a future route.
   No `pull_request_target`, CI login or CI package-write authority.
2. Only after a separately reviewed hosting decision could successful admission
   schedule the private `woow-disposable-builder` group, standard
   `self-hosted, linux, x64` labels, and protected `builder-candidate` environment.
   Group names/labels and daemon self-reported identity are not isolation proof.
3. `prepare` rejects Docker/Buildx/BuildKit host/context/config/TLS/API/auth and
   builder overrides. **Every case variant of ordinary proxy variables**, including
   `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `FTP_PROXY`, `NO_PROXY` and lowercase,
   is denied **even when empty and before any Docker query or software setup**.
   Future approved egress proxies require separately reviewed explicit
   configuration, never ambient inheritance.
4. Helper-store/session overrides are also denied before queries: password-store,
   GPG/GNUPG, DBus, keyring, GCM, SSH-agent/askpass and Docker-credential variables.
   Unrecognized `XDG_*` search/session overrides deny. Only absolute PATH entries
   are accepted; the guard rejects `docker-credential-*` directory entries on
   PATH without executing them or reading any credential store.
5. A fresh mode-0700 `$RUNNER_TEMP/woow-builder` is required; reuse denies. Its
   new mode-0700 HOME, XDG config/data/cache/state/runtime directories and Docker
   config are used for **prepare's queries and every subsequent setup, build,
   scanner and candidate step**, via the real `GITHUB_ENV` file. Old HOME/XDG
   values are replaced, never read/copied. The validator rejects workflow/job/
   step environment injection, extra actions, altered run scripts, and added
   `GITHUB_ENV`/`GITHUB_PATH` writes throughout the candidate job. This does not
   defend against a compromised runner or a changed malicious reviewed action;
   external runner and software controls remain mandatory.
6. The mode-0600 Docker config is deliberately **not `{}`**:

   ```json
   {"auths":{"bld2-anonymous.invalid":{}}}
   ```

   This reserved `.invalid` entry contains **no username/password/token**. In the
   actual Buildx v0.28.0 vendored CLI, `LoadDefaultConfigFile` invokes
   `DetectDefaultStore` only when `ContainsAuth()` is false. `ContainsAuth` counts
   auth-map entries, not nonempty passwords. Thus this nonempty map suppresses
   auto-detection; no `credsStore`/`credHelpers` means `GetCredentialsStore` uses
   only this new file. Registry requests with no matching entry get empty auth.
   Empty `{}` would instead detect `pass` (or `secretservice`) on Linux.
   Helper-PATH rejection is additional defense, not an assumption that empty
   configuration disables helpers. Candidate guards require this exact nonsecret
   config and deny added auth/helper/proxy/plugin-search fields.
7. **Pre-execution Buildx byte verification:** the external operator must first
   provision the approved asset at
   `/opt/woow-builder/buildx-v0.28.0.linux-amd64`. `builder_binary.py` has no
   downloader or subprocess. It refuses symlink/nonregular/oversize assets,
   reads bounded bytes, verifies the fixed published SHA256, and writes **those
   same bytes**, exclusively, into the new config's `cli-plugins/docker-buildx`
   with mode 0500. Failure produces no runnable plugin. This occurs before any
   Docker invocation, including metadata/version execution. Setup/verify rehash
   the private plugin before invoking Docker. No checksum can come from an env
   variable or approval JSON.
8. `setup --driver docker` is our Python guard, not `setup-buildx-action`.
   **The downloading action has been removed**, not merely given an empty
   version (which could fall back to downloading latest). Setup only verifies
   the embedded default driver; there is no create/bootstrap/nested BuildKit,
   installer overwrite, privileged container, floated daemon image or alternate
   driver. Buildx v0.28.0's Docker-driver Bootstrap is itself a no-op.
9. Prepare/setup/verify check the enrolled VM's default
   `unix:///var/run/docker.sock` context, exact client/server/API, Linux amd64,
   Engine ID/name, and native runner identity. Setup/verify also check exact
   Buildx `v0.28.0` and real `buildx ls --format json` JSON-Lines shape: one
   current, non-dynamic `default` builder, **driver `docker`**, one running node,
   approved embedded BuildKit, amd64 support, no options/flags/files/proxies.
   Unknown versions, additional contexts/nodes and remote endpoints deny.
   No `inspect --format` fiction, rootless/no-process-sandbox, host-network,
   privileged nesting, mounted/forwarded socket or arbitrary daemon fallback.
10. Build still explicitly selects `builder: default`, root context, single
    `linux/amd64`, `load: true`, `push: false`. The all-layer scanned SBOM,
    unsigned provenance, exact-ID tests/scans and no-rebuild publication chain
    remain unchanged. The private sanitized `identity.json` records source,
    version/engine/driver facts and approval hash, **not isolation attestation**.

### Late release authorization stays separate

Manual protected-main release still requires `check_release.py`, protected
`public-release`, and all independent source/license/secret/publisher/image/HA
clearances. Only the publisher has `packages: write`. Candidate building/scanning
gets no registry/backend credentials. The existing scoped GHCR token appears
only after candidate acceptance, in the existing registry-unused check and login.
The login uses the **same newly created private config**, with no helper store:
CLI `fileStore.Store` adds the GHCR entry without deleting the nonsecret sentinel.
This is short-lived plaintext token storage inside the disposable VM, not a claim
of encrypted storage. It is never copied to the builder/another job or evidence.
Candidate checks deliberately reject such late auth if repeated afterward.
The accepted image is reverified, tagged by tested ID and pushed without rebuild;
anonymous digest verification and existing retained sanitized evidence stay.
Builder approval alone never opens publication. **Do not dispatch release to test
BLD2.**

## External evidence required BEFORE runner registration

No entry below is configured, selected or proved by this patch.

- **Hosting decision first:** explicit approval for a particular private source
  destination/account; operator evidence of organization/enterprise ownership,
  the exact GitHub plan and its selected-workflow/private-environment-review
  capabilities. Record the actual settings and independent administrator review.
  Restrict the group to this private repository and reviewed `ci.yaml` and
  `release.yaml` directly defined on protected main. No label-only route, PR
  scheduling, arbitrary branch/workflow/reusable-job borrowing, or self-attested
  approval variable. Require protected-branch SPEC + security review.
- Independent required reviewers on `builder-candidate` and `public-release`,
  no self-review/admin bypass, main-only deployment policy, private logs/artifacts
  with named readers and bounded retention. If unavailable, **STOP**; no runner
  registration or source publication workaround.
- Named private native-amd64 **single-use VM per job**, with its own exclusive
  Engine/socket/store, runner directly on the VM (not in a job container with
  mounted socket), no production workload/agents/secrets/home mounts, no HA/k3s/
  backend/private-network routes. Normal process/network/seccomp/AppArmor
  confinement; no privileged nesting, host PID/network or capability changes.
- Initial resource estimate per VM: **4–8 vCPU, 16 GiB dedicated RAM, ≥60 GiB free
  scratch and ≥1 million free inodes**, 2–4h maximum lifetime. These are not
  measured reservations. Matrix `max-parallel: 1`; existing 30/40-minute job
  deadlines remain failure boundaries. External watchdog must destroy on
  finish/failure/cancel/expiry; in-job cleanup is insufficient. Record actual
  resource peaks after an approved run.
- Complete externally reviewed VM/client/Engine/API/embedded BuildKit software
  manifest and immutable delivery/provenance, plus Git/Python **3.13.12** and
  Docker CLI plugin-discovery behavior. The private config plugin must take
  precedence with no extra search dirs. Engine and CLI versions are deliberately
  unselected; illustrative Docker CLI v28.3.3 source below is **not a version
  approval**. Review the selected CLI's matching auth/plugin behavior before
  provisioning. Provision the Buildx asset only after software approval; the
  pinned checksum is integrity relative to public release metadata, not a
  signature verification or vulnerability clearance. No real binary has been
  hashed here; only invented test bytes exercise that code.
- Explicit private transfer authorization for the eventual reviewed commit and
  complete reachable Git history, via the approved short-lived read-only source
  channel. No Git config/hooks, agent HOME, auth stores, backend key or new PAT;
  checkout retains `persist-credentials: false`. No public source transfer.
- Outside-executor egress allowlist for necessary public HTTPS/DNS images,
  dependencies, scanners, Playwright and Grype DB. No ambient proxies, private
  routes, unrestricted LAN or inbound published ports. Acceptance containers
  retain `--network none` and owned loopback mocks. Explicit authority for local
  build/load/run/inspect/save/scans and sanitized private evidence only.
- Only then enroll real versions/runner identities, bind the final reviewed SHA,
  and authorize a short-lived candidate run. No real versions or `99.*` fixture
  IDs may be copied from tests. Image acceptance still needs seven real exact-ID
  builds/tests/scans; publication and HA acceptance remain independently CLOSED.

## Future approval schema (cannot unblock current route)

Default: `{"status":"NOT_APPROVED"}`. No valid invented approval is supplied.
After a reviewed hosting change only, `BLD2_APPROVAL` would be an administrator-
controlled repository Actions variable, never a PR/job-generated attestation or
an environment/organization shadow. It cannot prove VM authenticity or isolation.
All and only these JSON fields are required; duplicate/unknown/malformed values deny:

| Field | Required value |
| --- | --- |
| `schema` | integer `1` |
| `status` | `APPROVED` |
| `source` | lowercase 40-character SHA matching event SHA and checkout HEAD |
| `expires` | timezone-aware future ISO-8601 expiry, ≤4h away |
| `review` | external approval reference, 1–160 letters/digits/`._/-`, no secrets |
| `buildx` | `v0.28.0` |
| `client`, `engine` | exact operator-reviewed numeric `major.minor.patch` |
| `api` | exact server numeric `major.minor` |
| `buildkit` | exact embedded numeric `major.minor.patch`, optional `v` |
| `runners` | nonempty exact runner-name map to observed `engine_id` and `daemon_name` |

No automatic renewal. SHA means the eventual reviewed patch commit, not this
uncommitted tree's base and not another worker's changes. Release keeps its own
independent source-binding rule.

## Recovery

Any denial: stop, do not add privileges/change contexts/weaken policy. Restore
NOT_APPROVED and suspend admission if uncertain. Preserve only reviewed private
sanitized source/image/DB-policy-bound receipts; never token/config contents.
Destroy the one-job VM and volumes including source/history, images, scratch,
caches, HOME/XDG/config/token and raw scans. Never broad-prune/kill a shared
Engine. No HA/k3s rollback: neither was touched.

## Public source evidence and test limitations

Unauthenticated public text GETs only; no account/auth queries or binary download:

- [GitHub runner-group scope](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access),
  [selected-workflow controls](https://docs.github.com/en/enterprise-cloud@latest/actions/how-tos/manage-runners/self-hosted-runners/manage-access),
  [private environment plan limits](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).
  Syntax/actionlint does not prove account features exist.
- Buildx **v0.28.0 vendored CLI**:
  [`config.go:167–176`](https://github.com/docker/buildx/blob/v0.28.0/vendor/github.com/docker/cli/cli/config/config.go),
  [`configfile/file.go:119–123,292–320,359–372`](https://github.com/docker/buildx/blob/v0.28.0/vendor/github.com/docker/cli/cli/config/configfile/file.go),
  [`credentials/default_store.go`](https://github.com/docker/buildx/blob/v0.28.0/vendor/github.com/docker/cli/cli/config/credentials/default_store.go),
  [`default_store_linux.go`](https://github.com/docker/buildx/blob/v0.28.0/vendor/github.com/docker/cli/cli/config/credentials/default_store_linux.go),
  [`file_store.go`](https://github.com/docker/buildx/blob/v0.28.0/vendor/github.com/docker/cli/cli/config/credentials/file_store.go).
  These establish ContainsAuth/detection/file-store semantics, including the
  DOCKER_AUTH_CONFIG override (denied), not a fake Docker assumption.
- [Published Buildx checksums](https://github.com/docker/buildx/releases/download/v0.28.0/checksums.txt):
  `buildx-v0.28.0.linux-amd64` =
  `696bc104bac3bb708eff1af3f8bbc09fda0fd88f5757c1f9b404a35117889224`.
- [Removed setup action's main.ts](https://github.com/docker/setup-buildx-action/blob/8d2750c68a42422c14e847fe6c8ac0403b4cbd6f/src/main.ts):
  a supplied version OR unavailable Buildx triggers a download; version checking
  afterward does not authenticate bytes. Removing it avoids both overwrite and
  unavailable-plugin fallback. [Docker driver](https://github.com/docker/buildx/blob/v0.28.0/driver/docker/driver.go)
  Bootstrap is a no-op. [`ls.go`](https://github.com/docker/buildx/blob/v0.28.0/commands/ls.go),
  [`builder.go`](https://github.com/docker/buildx/blob/v0.28.0/builder/builder.go),
  [`node.go`](https://github.com/docker/buildx/blob/v0.28.0/builder/node.go)
  establish the JSON-Lines checks.
- [Illustrative Docker CLI plugin manager v28.3.3](https://github.com/docker/cli/blob/v28.3.3/cli-plugins/manager/manager.go):
  implementation searches extra dirs, config `cli-plugins`, then system dirs;
  our config has no extra dirs. Actual operator-selected CLI must be reviewed.

Tests run real guard/CLI/environment-file serialization and hash/copy code using
owned fake Docker replies, invented environment values and non-executable mock
asset bytes with test-only digest/route patches. Owned helper sentinels are never
executed; bad proxy/helper inputs assert **zero fake Docker queries**. Tests assert
the source-supported config shape, fresh HOME/XDG exports and whole-workflow
policy, not a fake credential-helper implementation. No real credential store
is consulted. `99.*` versions remain **MOCK ONLY**. These are offline regression
facts, not real action/daemon compatibility, VM confinement, resource reservation,
actual binary authentication, seven-image acceptance, publication or HA evidence.
