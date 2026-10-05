# Local n8n tracer contract (W1)

This is an executable local tracer, **not an installable HA Add-on**. Packaging,
shared UI, real HA role integration, release clearance and backend/client E2E are
still gated. There is no production allow-all administrator shortcut.

## Local setup and tests

```sh
uv sync --frozen --python python3.13
npm ci --prefix apps/n8n --ignore-scripts --no-audit --no-fund
uv run --frozen pytest -q -s
PYTHONPATH=packages/mcp-admin-core:apps/n8n .venv/bin/python apps/n8n/run.py
```

The last command defaults to `/data/mcp` (dedicated 0700 directory), admin port
8099, MCP port 8081 and child loopback port 3000. For disposable development use
`--data <empty-disposable-directory> --host 127.0.0.1` and free listener ports.
It creates its own strong tokens, never a default password. It does not read HA
options or overwrite GUI-owned values. Do not map the admin or child port to LAN.
No runtime package download or production backend is required for bundled
`tools_documentation` / `search_nodes` smoke calls.

The real subprocess tests use disposable state and two TCP listeners. They require
port 3000 to be free and never stop an existing service. One tests the locked real
n8n subprocess with **no backend URL/key**; the configured cases use an invented
dummy key and a disposable loopback fake backend, checking default queries and
null rejection as well as session disconnect/reconnection. None is production
n8n/HA E2E.

All pytest runs automatically acquire a **LOCAL TEST ONLY**, same-user cross-process
`flock` at `/tmp/woow-ha-mcp-local-tests-$(id -u).lock` for the entire test session.
Contending runs wait up to 120 seconds, then fail explicitly (never skip or kill
other processes). The persistent lock file must not be unlinked while runs may
exist. The OS releases the lock when its owning test process closes/exits; children
do not inherit it. Standalone local experiments binding child port 3000 must use
the same lock, for example:

```sh
flock -w 120 /tmp/woow-ha-mcp-local-tests-$(id -u).lock <experiment-command>
```

Do not wrap pytest, which acquires its own lock. This is
coordination among cooperating tests, not a production port reservation: a foreign
listener still causes an explicit bind failure, without being stopped. Additional ASGI 2.3 tests disconnect 45 times per
scenario through real HTTPX loopback sockets and verify pool/FD cleanup; other
identity and backend-fault tests are explicitly LOCAL/MOCK.

## Trust and routes

### Admin listener only

The socket peer MUST be `172.30.32.2`; Uvicorn proxy-header handling is disabled.
`X-Forwarded-For`, an MCP Bearer and `panel_admin` cannot grant management access.
The adapter accepts an async `verify_admin(user_id) -> bool` integration interface.
An absent provider, timeout, exception, missing identity or non-True result denies
access. **The executable installs no provider and denies all management requests.**
A trusted HA role lookup and real non-admin rejection evidence remain external gates.
Tests inject a role verifier only into the test app factory.

Ingress is expected to strip its prefix before forwarding. After authenticating
the socket and role, the API validates `X-Ingress-Path` and returns `base_path` and
`api_base`. The UI must join these explicit bases, including on refresh/deep links;
it must not use absolute `/api` URLs or infer the MCP endpoint from browser origin.
Static resources/navigation/UI are deferred to W3 and not claimed tested.

| Route | Contract |
|---|---|
| GET `/api/bootstrap` | Sanitized settings, health, explicit endpoint (initially null), base path, per-user/per-prefix CSRF token |
| PUT `/api/backend` | Exactly `{url, key}`; backend server base URL, not `/api/v1`; null explicitly clears a value. Restart only child to apply. No command/env fields |
| PUT `/api/endpoint` | Exactly `{endpoint}`; explicit HTTP(S) URL ending `/mcp`, or null; never derived from request host |
| PUT `/api/policy` | Exactly `{writes_enabled: boolean, disabled: [audited tool names]}` |
| POST `/api/token/reveal` | Explicit privileged reveal, empty body, CSRF required |
| POST `/api/token/rotate` | Generate new 256-bit external token and return it once; empty body, CSRF required |
| POST `/api/token/revoke` | Disable external auth, empty body, CSRF required |

All mutators require `X-CSRF-Token` obtained through authenticated bootstrap.
Cross-site fetch metadata is rejected, no CORS is enabled, and secret responses
use `Cache-Control: no-store`. Ordinary settings responses never include token,
child token or backend credential values. There is no generic configuration API.
Credential input is preserved exactly (not trimmed); null is explicit deletion.
Keys must contain only printable ASCII (U+0020–U+007E) and be 1–8192 characters.
Unsupported header characters are rejected with a sanitized 400 before persistence;
old incompatible state fails closed with a manual-recovery error, without rewriting.

### MCP listener only

POST/GET/DELETE `/mcp` requires the current Bearer on **every** request. No admin
routes, legacy SSE routes, arbitrary paths/query strings, token URLs or client
instance-override headers are proxied. Browser Origins are denied in this tracer;
non-browser Streamable HTTP clients are the supported local contract.

Only initialize, initialized notification, ping, tools/list and audited tools/call
are forwarded. Batches, tool notifications, duplicate JSON keys, nonfinite JSON,
unknown methods, invalid IDs/params/arguments and unknown/disabled/write-disallowed
tools fail before the upstream request. Notifications/initialized is the only
accepted notification. See provenance for the narrow source-backed tool subset.

The gateway preserves the upstream status of non-2xx replies, notifications and DELETE.
It forwards four headers only when well formed (session and protocol ids
`[\x21-\x7e]{1,256}` as for requests, numeric Retry-After, printable Content-Type) and
drops them otherwise. A 2xx body must be one the gateway parses and filters
itself (0.1.2): for GET an SSE stream, for a request (POST with an id) an SSE stream or
a plain 200 JSON reply; other 2xx codes and other, duplicate or missing media types
are 502 and not one byte of such a body is relayed, even when it is declared empty
(framing headers can lie: `Content-Length: 0` with chunked encoding still carries a
body); an initialize declared empty is 503 `BACKEND_UNAVAILABLE`. Replies to
notifications and to DELETE carry only the status and the forwarded headers (plus
`Cache-Control: no-store`), never the child's body. HEAD is 405 (`Allow: GET, POST,
DELETE`) and never reaches the child. Media types compare case-insensitively without
parameters; a 2xx reply always reaches the client as plain `text/event-stream` or
`application/json` (non-2xx bodies pass through with the child's Content-Type, and the
pinned clients read them only as error text). Every JSON reply to a request is parsed, must
be one object answering that request (same id and JSON type, `result` or `error`, no
`method`), is filtered and re-serialized with ASCII escapes; batches are 502. SSE events
are rebuilt from the lines the gateway understood: data, `id`/`event` values of up to 256
characters without spaces (as `Last-Event-ID` allows), numeric `retry` and printable-ASCII
comments up to 1024 characters; other lines (a BOM, unknown fields, non-ASCII comments)
are dropped. A lone CR (a line end for SSE parsers, not for the gateway's scan) refuses
the event: initialize is 502, other streams stop. An event whose data is empty (an MCP
2025-11-25 priming event) passes as an empty event; a batch in an event stops the stream;
a server-to-client request (an event with `method` and `id`: elicitation, sampling,
roots, ping) is dropped, since the client could not answer it through the gateway and it
would carry child text to the user; notifications (no id) still pass.
Request bodies with lone surrogates anywhere are 400; numbers that overflow to infinity
(e.g. `1e400`) are refused like NaN/Infinity (request 400, reply 502), so nothing is
re-serialized as `Infinity`. The child receives initialize with
`capabilities: {}`, since the gateway answers no server-to-client request (sampling,
elicitation, roots). Initialize is further special-cased: the gateway reads a 200 reply
up to the JSON-RPC response for the request and answers with that one response (SSE
keeps only its id/event/retry lines; other events are dropped). A 200 without that
response (empty body, stream ended or broken, only notifications/other ids) becomes HTTP
503 with JSON-RPC error -32000 `BACKEND_UNAVAILABLE`, Retry-After 5 and no session id:
the child gave no reply, e.g. its per-session lifespan could not reach the backend.
Malformed or oversize replies are 502; non-2xx replies pass through. JSON/SSE tool lists use the exact
local argument model's inputSchema, not the broader upstream schema. On a permitted
call, the gateway forwards the **validated model's serialized arguments**, including
reviewed defaults and field-specific omission rules, not the raw client object.
Reauthorization immediately before dispatch uses the same normalized values.
Strict types, bounds and unknown-field rejection remain unchanged; no extra upstream
arguments are enabled.

| Tracer tool | Executable default / omission contract |
|---|---|
| `tools_documentation` | Missing `topic` becomes `"overview"`; missing `depth` becomes `"essentials"`. Both match the pinned handler's overview fallback / depth default. Explicit null is rejected. |
| `search_nodes` | Missing `limit` becomes `20` (1–100), matching the pinned handler. `query` remains required; neither accepts null. Other search options remain denied. |
| `n8n_list_workflows` | Missing `limit` becomes **20** (1–100), deliberately overriding the pinned handler's omission default of 100. `active` is optional **boolean only**: omission means no active filter, false remains false, true remains true. Explicit null for either field is rejected before upstream dispatch. The internal None omission sentinel is neither advertised nor serialized. |
| `n8n_delete_workflow` | No defaults; `id` is required and non-null. Writes remain disabled unless explicitly enabled. This repair tests writer normalization only with a mock, never a real delete. |

The upstream workflow handler retains `excludePinnedData=true`; that option is not
client-configurable in this tracer. Source references (installed n8n-mcp 2.91.0):
`dist/mcp/server.js` cases `tools_documentation` / `search_nodes` and
`getToolsDocumentation`; `dist/mcp/handlers-n8n-manager.js` `listWorkflowsSchema` /
`handleListWorkflows`. Real-child/fake-backend tests assert the actual GET query,
including absent `active`, limit 20 and explicit booleans; JSON/SSE tests assert the
public boolean-only schema independently of model equality.

These **four tools remain a partial W1 tracer**. W2a now inventories all 28 pinned
upstream tools in `tool-surface.json` / `tool-surface.md`; expansion remains W2b.

Initialize
advertises only `tools: {}` (no resources/prompts/logging/listChanged). Resumed GET SSE
streams are rebuilt and filtered the same way (a non-SSE 2xx GET reply is 502). Every call is authorized independently. Compression is disabled on the internal hop;
redirects, response cookies and hop-by-hop headers are not forwarded.

Limits: 256 KiB request body, 10-second request-body timeout; 32 concurrent upstream
streams; 3-second connect/pool and 30-second upstream inactivity timeout; 120-second
stream lifetime and 8 MiB response budget. Oversize/truncated streams close rather
than invent a successful protocol result (initialize: 502 oversize, 503 without a reply). Clients may reconnect with a fresh
Bearer and session/event headers. A response owner joins its reader cancellation
and upstream close under a 3-second cleanup budget, shields ASGI 2.3 AnyIO level
cancellation and joins direct asyncio cancellation, then unconditionally releases
its slot. Headers/body/send/idle disconnect paths share that owner; cleanup is not
detached from response completion.

Rotation/revocation does not change the independent child token. Old Bearers are
immediately rejected on new requests (including cached session IDs). Existing
streams are checked every 200 ms and stop forwarding on revocation or invalid
state, even while idle. Already dispatched work is NOT transactionally rolled back;
rotation is not a backend cancellation mechanism. A new authorized token can use
a known existing child session; session IDs are not additional credentials.

## Persistence and lifecycle

The executable now uses product-tagged `state.json` version 2, 0600 (W2a).
Under the exclusive writer lock it validates and migrates complete n8n v1 state,
preserving both tokens, backend, endpoint and policy. Wrong-product, corrupt,
incomplete and future state fails closed without rewriting. The old v1 Store
refuses v2; rollback requires a protected v1 backup, not changing the version number.
Exclusive temporary writes, file fsync, atomic replace and directory fsync provide the durability path. A lifetime file lock
permits one writer process, not Uvicorn multi-worker deployments. No-follow reads,
regular-file/single-link checks and directory symlink refusal protect the managed
state boundary. A prior lock marker plus missing state fails closed instead of
silently generating replacement credentials. Back up the **whole state directory**.

Corrupt, incomplete and unsupported past/future schemas fail closed without
rewriting the file. There is no pre-v1 migration: this is a new repository, not a
legacy-config import. Restore a compatible protected backup rather than changing
a version number. Write failure latches a state error until explicit recovery.
Do not copy runtime state, temporary state, backups or credentials into Git/images.

The supervisor spawns only the fixed per-app command/environment in a new process
group. Stop is cooperative: it wakes the run loop rather than cancelling an
in-progress natural-exit cleanup. Stop/restart await actual group termination and
reaping before clearing process state or starting a replacement. Child stdout/stderr are discarded; health exposes state/exit count/code,
not credential-bearing logs. There are at most three restarts per supervision run,
exponential capped backoff with jitter, and a terminal failed state (management
remains available for diagnosis). Backend failures never trigger child/container
restarts. A deliberate administrator backend change starts a new child budget.

Linux unprivileged child-subreaper mode reaps adopted descendants of the known
process group after SIGTERM/deadline/SIGKILL. It never calls waitpid(-1) or signals
unrelated groups. Same-group descendants are tested; hostile children escaping
into new sessions are outside this fixed trusted-runtime supervisor's sandbox
claim. Container init/protection mode remain necessary packaging controls.

## Health, not a watchdog shortcut

Authenticated admin bootstrap exposes three dimensions: management state,
child lifecycle plus protocol readiness, and backend reachability. Protocol
readiness performs a bounded initialize → initialized → ping → session DELETE,
not just TCP connect or upstream `/health`. Backend reachability uses a separate
5-second, internal `n8n_list_workflows(limit=1)` probe in that session and requires
its success payload. Thus health uses the same Node backend network policy as the
tool, not an unrestricted Python HTTP path. This automatic read-only health probe
runs independently of client tool visibility (as the previous direct health GET
did); it never enables a client call or performs writes. Checks repeat every 15
seconds. An unexpected monitor exit/exception stops the runtime with a sanitized
recovery message and nonzero exit, not a discarded exception/clean exit.

## Single configured backend network policy

`apps/n8n/backend_policy.cjs` is an explicit adapter for the pinned API client's
`getPinnedAgents` method. The fixed launcher preloads it; an API-client source hash
guard fails closed on package drift. It does **not** change global webhook SSRF
validation or set `WEBHOOK_SECURITY_MODE=permissive`.

- Only the GUI-owned exact HTTP(S) origin **and base path** may create backend
  agents. No userinfo/query/fragment; no client-selected URL/key headers or arbitrary
  network tools. Webhook validators retain upstream strict behavior.
- That selected backend may be loopback, RFC1918 LAN/HA, IPv6 ULA or public unicast.
  Public IPv6 is limited to global-unicast 2000::/3, excluding classified transition
  ranges. Link-local, metadata (including AWS ULA/Azure virtual endpoint), multicast,
  unspecified, reserved, CGNAT and IPv6 mapped/translation/tunnel addresses deny.
- Every DNS answer must pass validation. Each API request resolves again; validated
  addresses are pinned through socket connection (no second DNS lookup). Socket
  agents also check original hostname, port and protocol; numeric/absolute URL
  substitution cannot bypass the origin check. HTTPS certificate verification is
  unchanged. Existing upstream redirect denial (`maxRedirects: 0`) is retained.
- Changing a backend requires the authenticated administrator path and restarts
  the child. Metadata-invalid/unresolvable backend destinations are unreachable;
  they cannot become ready merely because a different health path accepts them.

Numeric LAN/IPv6 policy tests perform validation only, not LAN requests. Successful
backend traffic in this suite reaches only disposable loopback fake servers. This
is not a claim of real HA network, TLS, backend credentials or client acceptance.

The only public non-MCP exception is minimal GET `/health/ready`, which returns
503 until protocol transport and configured backend reachability are both ready.
It exposes only `{ready: boolean}`. **Do not use this backend-dependent readiness
endpoint as a Supervisor watchdog**: backend outage must not restart the container.
No watchdog is configured or unconditional `/healthz` supplied by W1. W3 must
choose and test an appropriate local-supervisor liveness/watchdog contract.

Backup/restore, migration/rollback operations on HA, seven images, release CI,
real clients, real Ingress browser UX, trusted HA roles and production E2E have
not been validated by these local contracts.
