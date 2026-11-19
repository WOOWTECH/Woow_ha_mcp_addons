# HM-15 listener review: local evidence and limits

The gateway connects to IPv4 `127.0.0.1`. Listener inspection matches that
destination and IPv4 wildcard listeners, plus IPv4-mapped IPv6 listeners.
An IPv6 wildcard may be IPv6-only or dual-stack; procfs does not expose that
socket option, so its presence at the port makes identity unavailable unless
a complete FD scan already proves a definite listener belongs elsewhere; that
definite mismatch takes precedence. An FD
that disappears during enumeration makes a negative ownership result unavailable;
an already observed complete match remains owned. As designed, unavailable
continues with child bearer protection, so this is best-effort detection, not
a same-UID security boundary. Listener replacement after the check and before
connection also remains a race.

The local Odoo test starts the pinned, patched Odoo MCP child and the real
management guard (including `PR_SET_DUMPABLE=0` and its verification) in a
separate process, exercises the gateway and MCP calls against a disposable fake
XML-RPC backend, and joins the processes. It turns on the multi-profile feature
and requires an `owned` result from the real `ListenerGuard` on a successful
child request. The owned test harness redirects the child's production port to
an ephemeral port; the test-only guard subclass uses that same private port.
The harness disables HM-20's loopback-backend refusal solely so the disposable
local XML-RPC backend can answer; this test does not validate that policy.
It runs only the default profile as UID 1000 here, not the add-on's UID 10001
or an additional profile. The separate
`test_uid10001_nondumpable_self_and_own_child_proof` uses a real non-dumpable
UID 10001 manager and an exec'd synthetic listener, including a non-dumpable
child negative case, but requires root and was not run in this unprivileged
environment. Neither test establishes behavior on HAOS, an actual Odoo
backend, or under the deployed container's procfs and security policy. A
joined UID 10001 Odoo multi-profile/HAOS test remains needed for that claim.

Local ledger precheck against `origin/claude-delivery`: zero drift, missing or
unlisted runtime files; 92 runtime-patch and 45 tool-surface entries require
the other CI installations and were not checked locally. UI: 118 unit tests,
build and build-closure check passed; `dist/` is ignored and built in images.
An independent security review identified that IPv6 wildcard ambiguity and
FD churn can cause the documented unavailable/bearer fallback; it also noted
the existing check-to-connect race. A separate specification review identified
stale status after child restart (fixed by resetting it on probe), and the
absence of an end-to-end real foreign-listener rejection test. These remain
limits of the local evidence, including the security review's fail-open risks.
