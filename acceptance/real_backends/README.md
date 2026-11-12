# Real backend acceptance

These are operator-run integration tests against real, disposable servers and
unchanged published MCP images. They create resources only in a separately leased
namespace. They are not an unattended CI job or a production deployment script.

The 2026-10-30 baseline is HA 0.4.6 source `28b8317` and PaaS source `f748090`.
`images.json` pins every gateway and backend manifest digest. Odoo uses Odoo 18
with PostgreSQL, Nextcloud uses SQLite and the packaged PHP server, and EMQX uses
its disk retainer. These backend versions are coverage boundaries, not tests of
every supported version. PaaS `f748090` has eight published products and **no EMQX
adapter**. Never count that cell as tested or passing.

## Preconditions and ownership

- Read the applicable AGENTS.md and obtain main's `MAIN-RESOURCE-LEASE.json`.
  It must authorize this namespace, node UID, resource envelope, launch deadline,
  and cleanup deadline. The checked-in defaults identify the original run; use
  a fresh lane directory and namespace for a new run.
- Set `BACKEND_EVIDENCE_DIR` to the lane directory (receipts go in `evidence/`).
  Optional `BACKEND_CONTEXT`, `BACKEND_NAMESPACE`, and `BACKEND_NODE` select the
  leased cluster and resources. Keep this environment for every command.
- Require Python 3.10+ and authorized kubectl locally. Test clients run inside the
  pinned images. The HA checkout must contain source commit `28b8317`; PaaS source
  currently lives at `/data/pi-agent/home/work/paas-parity-integration-20261029`.
  `controller.source_proof` hashes the installed gateway and child source files
  against those frozen commits, not the current branch.
- Inspect earlier receipts before resuming. `run_family` is for a fresh family;
  it must not be rerun after partial success. Use the individual phases after
  reading native state. No business mutation automatically retries.

## Run

From the repository root, after the lease is present:

```sh
python3 -m py_compile acceptance/real_backends/*.py
python3 acceptance/real_backends/provision.py namespace
python3 acceptance/real_backends/registry.py prepare
python3 acceptance/real_backends/provision.py odoo
python3 acceptance/real_backends/controller.py run odoo
python3 acceptance/real_backends/controller.py remove odoo
python3 acceptance/real_backends/provision.py nextcloud
python3 acceptance/real_backends/controller.py run nextcloud
python3 acceptance/real_backends/controller.py remove nextcloud
python3 acceptance/real_backends/provision.py emqx
python3 acceptance/real_backends/controller.py run emqx
python3 acceptance/real_backends/controller.py remove emqx
python3 acceptance/real_backends/cleanup.py
```

The registry helper copies only the existing institutional JCR pull identity,
in memory, into a namespace-owned pull Secret. Its authorized source defaults to
`paas-ws-b83741fc/paas-registry`; override `REGISTRY_SOURCE_NAMESPACE` and
`REGISTRY_SOURCE_SECRET` when the approved registry credential location differs.
It never disables authentication, alters the source Secret, or saves credentials
locally. `registry.py nextcloud` verifies authenticated manifest and config bytes
before deciding an image is absent. Customer/backend credentials are never reused.

Each family has one pod on the UID-bound node. Servers and clients communicate
through loopback, under default-deny ingress/egress, no Service/Ingress, no service
account token, no PVC, and no host mounts. Accounts and credentials are generated
for this run. A watchdog expires the namespace; every cleanup checks ownership.
Deleting the namespace is also the recovery path after a failed test when there
is no safe way to delete a specific owned record. Record that as failed acceptance
with fixture cleanup, not successful record-level cleanup.

## Assertions and boundaries

`probe.py` configures each management API and makes genuine HTTP MCP calls.
Odoo grants and its child write switch are tested separately. Successful creates,
updates, and reads are checked with native XML-RPC/WebDAV/EMQX REST observations.
Denied writes must return the expected error and leave the native target unchanged.
Invalid Odoo fields, stale Nextcloud etags, and wildcard EMQX publishes are error
cases. Cleanup deletes only the exact owned record/path/topic. Odoo additionally
hashes the complete partner table before and after the sequence.

The backend container actually restarts, and the owned updated value must survive.
The gateway container also restarts; persisted management state must be byte-equal
and revoked writes must remain denied. A stop command can return 137 when its
container exits: the harness records this and requires Kubernetes restartCount
to increase with the same pod UID and an operational backend. It does not infer
restart success from the command exit code or silently replay a mutation.

Persistence here means container restart with the same emptyDir, not PVC,
pod-reschedule, disaster recovery, or HAOS lifecycle persistence. `ha_runtime.py`
uses the shipped runtime with an explicitly synthetic loopback administrator
identity. This is **not HAOS ingress authentication acceptance**. Avicenna owns
that independent acceptance. Main owns production release and Sites.

Receipts are exclusive-create JSON and omit credentials/private logs. Earlier
failed attempts remain visible. A changed harness is not a rebuilt gateway image;
image and installed-source evidence establish which released code actually ran.
The original run's lane contains the cell manifest, failed-attempt dispositions,
SHA-256 inventory, final cleanup, and source commit for main's handoff.

Audit the original preserved run and exercise rejection of false evidence:

```sh
python3 -m unittest discover -s acceptance/real_backends -p 'test_*.py' -v
python3 acceptance/real_backends/verify_evidence.py "$BACKEND_EVIDENCE_DIR"
```

The auditor understands the original run's archived Nextcloud HA attempt and
requires explicit dispositions for every failed receipt. It checks native
effects, source bytes, actual image IDs, same-pod restarts, post-restart reads and
denials, record cleanup, namespace cleanup, and watchdog exit. Its ordering check
uses preserved local file times; it does not claim cryptographic timestamps.
It requires strict reason assertions in the later denial/error receipts without
inventing those assertions for the earliest Odoo receipts.

EMQX's gateway can temporarily return `-32603 Backend unreachable` after the
broker's HTTP API returns. A read-only reproduction recovered in about three
seconds. The final harness waits for both applied configuration and gateway
backend reachability before verifying persistence; it never retries a write.
