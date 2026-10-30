# 0.4.9 release candidate

Status: source preparation only; six image builds, gates, publication and distribution are pending.

This candidate follows the eventual green normal merge of PR #43, whose reviewed head is
`9f12adae3930876bc311ec668e42f1e38594ca32`. Main must bind the actual merge, candidate source commit
and tree before building. This document does not assign an unobserved merge or image identity.

Hermes ports the two reviewed functions and unchanged session-mutation helper from PaaS
`052887fa68d5e67b86c622ef92f46dd7f75a08ca`. DELETE reads fresh Agent fences, sends one request,
verifies absence and permits only explicit replay of the unchanged three-field identity.
It does not resend DELETE after401 or an uncertain response. The Agent mutation-snapshot/receipt
contract is required; no unfenced fallback is added. See [the exact contract](../../apps/hermes/docs/session-delete-contract.md).
The session description and optional arguments change; the 11 tool names, grants, destination policy,
redaction, shared state format and other products' behavior retain the reviewed source contracts.

Seven add-on manifests and seven Dockerfile defaults advance together. Only Odoo, n8n, Hermes,
EMQX, LiteLLM and Nextcloud are enabled for publication; OpenDesign remains disabled and Odoo Manage
remains archived. Python 3.13.18, Node/uv pins, dependency locks, scanner policy and precise triage stay pinned.

Use the existing 0.4.8 private flow with new exact-source bindings: source CI, six immutable image builds,
P1–P5 and exact UI/runtime checks, immediate successful-gate private cleanup, accepted-ID publication,
anonymous manifest/config/ordered-layer verification and fresh remote full-blob/diffID verification.
Preserve the accepted 0.4.8 image IDs and all historical receipts. Generate 0.4.9 provenance only from
actual new receipts. A later docs commit must pass normal required checks and readiness before Main
merges the version PR; the normal merge pipeline then emits six Stable Releases and syncs Store/Local Download.

Shared-daemon and unsigned-provenance limits remain. Source/image gates do not claim actual HAOS,
customer backend, backup or restore acceptance. No image publication or builder GO is recorded here.
