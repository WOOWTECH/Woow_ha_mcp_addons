# Unreleased alignment candidate

## Upgrade behavior change

Legacy schema1/2/3 now waits in an HA-admin-authenticated Ingress review before
any ProductStore migration or MCP child starts. The default selected policy is
all_on (full features), but an administrator must confirm it or choose preserve.
Unattended legacy upgrades therefore remain in review until confirmation. Fresh
installs and schema4 retain normal startup. Existing tokens, including revoked
ones, are preserved. Preflight/commit share the existing writer lock, digest and
policy-only recovery; failed writes require protected-state inspection.

Open the add-on panel after upgrade, compare both plans, and confirm. During
review MCP and readiness return503. After confirmation the review listeners stop
and the normal runtime starts on the same ports. For offline migration/recovery,
stop the runtime first and follow docs/operations/legacy-migration.md.

This branch does not change addon versions or publish a Store release.
