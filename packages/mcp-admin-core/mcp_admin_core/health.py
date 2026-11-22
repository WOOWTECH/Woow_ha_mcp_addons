"""Protocol readiness and separate read-only backend reachability (not E2E).

HM-09 (multi-profile plan 5.4; contract 7; DQ-25, decided 2026-11-15 11:2x: the plan's recommendation): a switched-on
product's ProfileManager gives every profile's monitor its options; left out, the monitor is the one before HM-09
(a check at once, then every 15 s; one failed check is unreachable; it probes whatever the child's state).

- first_check_after: the start point (the default profile at once; an additional one later, staggered); the interval
  stays HEALTH_INTERVAL.
- auth_backoff: while the backend refuses the credentials (auth_refused: the probes' fixed texts of this repository's
  children), the next check waits the table's next step (AUTH_BACKOFF: 15, 30, 60, 120, 300 s; Odoo 18 counts failed
  logins per source address, C-tracer 4.4); any other answer of the child resets it, and so does reset() (a save or
  the panel's restart: new credentials).
- tolerance 2: the verdict unreachable (what makes the gateway refuse a tools/call: the child answered and the backend
  did not) needs two such checks in a row of the same child (C2-MF-4 point 3: a check that another profile's load
  delayed refuses nothing); until then the previous verdict stays (reachable, or unknown after a start). A check the
  child did not answer is recorded as before (not ready; it refuses nothing) and neither counts nor breaks the row.
  test_saved (the panel's backend test) still answers with what it found.
- own_child_only: nothing is sent while the profile's own child is not running (blocked, backing off, failed, stopped):
  the port may be another program's (T-15).

Every product, switched on or off (HM-09 follow-up, 2026-11-16: PR #103's checks; the owner's decision at 13:4x;
contract 1.2; tests/test_monitor_cancel.py): a monitor stops when it is asked to, also when the HTTP stack swallowed the
stop. Every new connection of the child client goes through anyio.connect_tcp, whose task group cancels its own scope
once connected, and a task.cancel() that reaches the task before it runs again joins anyio's CancelledError, which the
scope's exit swallows as its own (anyio 4.15.1 on CPython 3.13; httpcore's read deadline the same). Task.cancelling()
still counts that request: check() raises CancelledError when the count is higher at its end than at its start, so the
monitor and start_all's readiness wait (settle) stop as asked. Only a stop changes; no answer does.
"""
import asyncio
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from . import redact
from .capacity_metrics import active_metrics
from .config import ConfigError, strict_json
from .lifecycle import CHILD_URL

SESSION_ID = re.compile(r"[\x21-\x7e]{1,256}")  # as the gateway accepts from clients
REASON_LIMIT = 1000  # characters of a failed health check's own text kept as the reason
TOOL_ERROR_PREFIX = re.compile(r"^Error executing tool [A-Za-z0-9_.-]{1,128}: ")  # the SDK's wrapping of a tool error
HEALTH_INTERVAL = 15  # seconds between two checks (DQ-25: unchanged)
AUTH_BACKOFF = (15, 30, 60, 120, 300)  # DQ-25: the next check after 1, 2, 3, 4, 5 or more refused logins in a row
# A refusal of the credentials, as the readiness probes of this repository's children word it (the start of the
# probe's reason; tests/test_health_backoff.py pins each text to its child's source): Odoo and Hermes
# BACKEND_AUTH_REJECTED, Headscale HEADSCALE_INVALID_CREDENTIAL, Nextcloud's public code for a 401 and for its
# brute-force throttle (a 429 after failed logins: the same back-off), EMQX's and LiteLLM's 401 texts.
AUTH_REFUSED = re.compile(r"(?:BACKEND_AUTH_REJECTED|HEADSCALE_INVALID_CREDENTIAL)(?![A-Za-z0-9_])"
                          r"|BACKEND_HTTP_ERROR status=(?:401|429)(?![0-9])"
                          r"|EMQX rejected the API credentials \(401\)"
                          r"|LiteLLM rejected the credentials \(401 ")


def auth_refused(reason):
    """Whether a health check's reason says the backend refused the credentials (DQ-25)."""
    return isinstance(reason, str) and AUTH_REFUSED.match(reason) is not None


def probe_reason(reply):
    """0.2.2: why a health check tools/call did not prove the backend reachable, in the child's own words (the backend's
    error text since 0.2.0: "CODE: text", or a JSON payload's error/message), whitespace collapsed and bounded."""
    text = ""
    if isinstance(reply, dict) and isinstance(reply.get("content"), list):
        text = next((item["text"] for item in reply["content"] if isinstance(item, dict) and item.get("type") == "text"
                     and isinstance(item.get("text"), str)), "")
    try:
        payload = strict_json(text)
    except Exception:
        payload = None
    if isinstance(payload, dict):
        found = ""
        for key in ("error", "message"):
            value = payload.get(key)
            if isinstance(value, dict):
                value = value.get("message")
            if isinstance(value, str) and value.strip():
                found = value
                break
        text = found
    text = TOOL_ERROR_PREFIX.sub("", " ".join(text.split()))[:REASON_LIMIT]  # the probe's name is not the client's
    return text or "BACKEND_INVALID_RESPONSE: the health check answer was not the expected one"


async def protocol_reply(response: httpx.Response, expected_id):
    """Read one bounded JSON/SSE RPC reply. Caller owns response cleanup."""
    pending = b""
    is_sse = response.headers.get("content-type", "").split(";")[0] == "text/event-stream"
    if response.status_code != 200:
        raise ValueError("protocol unavailable")
    async for chunk in response.aiter_bytes():
        pending += chunk
        if len(pending) > 8 * 1024 * 1024:
            raise ValueError("oversize protocol response")
        if is_sse:
            # SDK uses LF; tolerate CRLF and comments/heartbeat events.
            pending = pending.replace(b"\r\n", b"\n")
            while b"\n\n" in pending:
                event, pending = pending.split(b"\n\n", 1)
                data = b"\n".join(line[5:].lstrip(b" ") for line in event.splitlines() if line.startswith(b"data:"))
                if data:
                    result = strict_json(data)
                    if result.get("id") == expected_id:
                        if result.get("jsonrpc") != "2.0" or "result" not in result:
                            raise ValueError("failed protocol response")
                        return result["result"]
    if is_sse:
        raise ValueError("missing protocol response")
    result = strict_json(pending)
    if not isinstance(result, dict) or result.get("jsonrpc") != "2.0" or result.get("id") != expected_id or "result" not in result:
        raise ValueError("invalid protocol response")
    return result["result"]


class HealthMonitor:
    def __init__(self, store, process, client, child_url=CHILD_URL, *, first_check_after=0, tolerance=1,
                 auth_backoff=None, own_child_only=False, log=None):
        self.store, self.process, self.client, self.child_url = store, process, client, child_url
        self.backend = "unconfigured"
        self.management = "alive"
        # 0.2.2: the outcome of the last COMPLETED check (child start count, child answered, backend, reason). snapshot()
        # (readiness, the panel) is unchanged and still shows a check in progress; availability() never does.
        self.settled = None
        self._check_lock = asyncio.Lock()
        # HM-09 (see the module docstring); all left out: the monitor before HM-09.
        if type(tolerance) is not int or tolerance < 1:
            raise ValueError('invalid tolerance')
        if auth_backoff is not None and (not auth_backoff or any(not step > 0 for step in auth_backoff)):
            raise ValueError('invalid backoff')
        self.first_check_after, self.tolerance = first_check_after, tolerance
        self.auth_backoff = None if auth_backoff is None else tuple(auth_backoff)
        self.own_child_only, self.log = own_child_only, log
        self.paced = (first_check_after, tolerance, auth_backoff, own_child_only, log) != (0, 1, None, False, None)
        self.auth_refusals = 0  # refused logins in a row
        self.refusals = 0  # checks in a row of the current child that got its answer and found the backend unreachable
        self._generation = None
        self._reachable = None  # the child start whose last answered check found the backend reachable
        self._wake = asyncio.Event()
        self._capacity_metrics = active_metrics()
        if self._capacity_metrics is not None:
            try:
                child_port = urlsplit(str(child_url)).port
            except ValueError:
                child_port = None
            self._capacity_slot = self._capacity_metrics.register_health_monitor(child_port)
        else:
            self._capacity_slot = None
        self._capacity_phase = 0
        self._capacity_timeout = False

    def snapshot(self):
        return {"management": self.management, "child": self.process.health(), "backend": self.backend}

    def availability(self):
        """0.2.2, for the gateway: the child's status now; ready (the last completed check, of this same child start,
        got its initialize and ping answered); backend and reason from that check ("unknown"/None when there is none
        for this start, e.g. right after a restart). Never the in-progress values snapshot() shows."""
        status = getattr(self.process, "status", "stopped")
        settled = self.settled
        current = settled is not None and settled[0] == getattr(self.process, "starts", 0) and status == "running"
        return {"child": status, "ready": bool(current and settled[1]),
                "backend": settled[2] if current else "unknown", "reason": settled[3] if current else None}

    async def check(self, *, capacity_scheduled_at_ns=None):
        # HM-09 follow-up (module docstring): asyncio.timeout and anyio undo their own cancel() requests, so a count above
        # the one at the start is a stop asked of this task that the check did not get as CancelledError.
        task = asyncio.current_task()
        asked = 0 if task is None else task.cancelling()
        started_at_ns = None
        outcome = 4
        try:
            async with self._check_lock:
                if capacity_scheduled_at_ns is not None:
                    started_at_ns = time.monotonic_ns()
                    self._capacity_phase = 0
                    self._capacity_timeout = False
                found = await self._check_saved()
            if task is not None and task.cancelling() > asked:
                raise asyncio.CancelledError
            # Use the check's raw finding, not the tolerated settled verdict.
            outcome = (2 if self._capacity_timeout else
                       0 if found is not None and found[2] == 'reachable' else 1)
        except asyncio.CancelledError:
            outcome = 3
            raise
        finally:
            if capacity_scheduled_at_ns is not None:
                self._capacity_metrics.on_scheduled_health_check(
                    self._capacity_slot, capacity_scheduled_at_ns,
                    started_at_ns, self._capacity_phase if started_at_ns is not None else 0, outcome)

    async def settle(self):
        """HM-09 (ProfileManager.start_all waits for a starting child with it): the outcome of the check running now when
        one is (waited for, not followed by a second probe at the backend), else a check of its own."""
        if self._check_lock.locked():
            async with self._check_lock:
                return
        await self.check()

    async def test_saved(self, state):
        """Explicit read-only check of the saved config, serialized with monitoring.

        The gateway holds its mutation lock throughout. This callback never saves,
        replaces credentials, changes policy or restarts a child. HM-09: it answers with what this check found, also
        while the monitor's verdict still waits for a second failure (tolerance).
        """
        async with self._check_lock:
            found = await self._check_saved()
            backend, reason = ((found[2], found[3]) if found is not None else
                               (self.backend, self.settled[3] if self.settled else None))
            return {"tested_configuration": "saved", "checked_at": datetime.now(timezone.utc).isoformat(),
                    "health": self.snapshot(), "backend": backend, "reason": reason}

    async def _check_saved(self):
        """One check; returns what it found (child start count, child answered, backend, reason), None when the state
        cannot be read. settled is what the monitor makes of it (the same, unless tolerance keeps a verdict)."""
        generation = getattr(self.process, "starts", 0)
        try:
            state = self.store.load()
        except ConfigError:
            self.management = "state_error"
            self.process.ready = False
            self.backend = "unknown"
            self.settled = None
            return None
        self.management = "alive"
        self.process.ready = False
        configured = getattr(state, 'configured', bool(state.backend_url and state.backend_key))
        self.backend = "unreachable" if configured else "unconfigured"
        product = getattr(state, 'product', 'n8n')
        if product != 'n8n' and not configured:
            self.settled = (generation, False, self.backend, None)
            self.auth_refusals = self.refusals = 0
            return self.settled
        if self.own_child_only and getattr(self.process, 'status', 'running') != 'running':
            # HM-09 (T-15): nothing is sent to a port this profile's own child does not hold now.
            self.backend = 'unknown'
            self.settled = (generation, False, 'unknown', None)
            return self.settled
        reason = None
        found = None
        try:
            reason = await self._check(state, configured, product)
        finally:
            answered = bool(self.process.ready)
            if self.backend != "unreachable":
                reason = None
            elif not answered:
                reason = "MCP_SERVER_NOT_READY: the add-on's MCP server did not answer the health check"
            else:
                reason = redact.redact_secrets(reason or "BACKEND_UNAVAILABLE: the health check failed",
                                               redact.secret_values(state))
            found = (generation, answered, self.backend, reason)
            self.settled = self._verdict(found)
            self.backend = self.settled[2]
        return found

    def _verdict(self, found):
        """settled for what a check found: itself, unless tolerance keeps the previous verdict (module docstring); the
        refused logins in a row counted for auth_backoff."""
        generation, answered, backend, reason = found
        if self.auth_backoff is not None:
            if backend == 'unreachable' and auth_refused(reason):
                self.auth_refusals += 1
                if self.log is not None:
                    self.log('auth backoff', 'the backend refused the credentials; next health check in '
                                             f'{self.next_interval():g} s')
            elif answered:
                self.auth_refusals = 0
        if generation != self._generation:
            self._generation, self.refusals = generation, 0
        if not answered:
            return found
        if backend != 'unreachable':
            self.refusals = 0
            if backend == 'reachable':
                self._reachable = generation
            return found
        self.refusals += 1
        if self.refusals >= self.tolerance:
            if self._reachable == generation:
                self._reachable = None
            return found
        return (generation, answered, 'reachable' if self._reachable == generation else 'unknown', None)

    def next_interval(self):
        """Seconds until the next check: HEALTH_INTERVAL, or the backoff after refused logins (auth_backoff)."""
        if self.auth_backoff is not None and self.auth_refusals:
            return self.auth_backoff[min(self.auth_refusals - 1, len(self.auth_backoff) - 1)]
        return HEALTH_INTERVAL

    def reset(self):
        """New credentials (a save, the panel's restart): no backoff any more, and the next check within one
        interval."""
        self.auth_refusals = self.refusals = 0
        self._wake.set()

    async def _pause(self, seconds):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + seconds
        while (left := deadline - loop.time()) > 0:
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), left)
            except TimeoutError:
                return
            deadline = min(deadline, loop.time() + HEALTH_INTERVAL)

    async def _check(self, state, configured, product):
        """One readiness check; returns why the backend was not proven reachable (None when it was or nothing says)."""
        reason = None
        if product == 'n8n':
            probe_name, probe_args = 'n8n_list_workflows', {'limit': 1}
        else:
            from .products import health_probe
            probe_name, probe_args = health_probe(product)
        headers = {"Authorization": "Bearer " + state.child_token, "Accept": "application/json, text/event-stream"}
        session = None
        try:
            if self._capacity_metrics is not None:
                self._capacity_phase = 1
            async with asyncio.timeout(8):
                async with self.client.stream("POST", self.child_url, headers=headers, json={
                    "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                        "protocolVersion": "2025-03-26", "capabilities": {},
                        "clientInfo": {"name": "local-readiness", "version": "0"}}}) as response:
                    session = response.headers.get("mcp-session-id")
                    if session is not None and not SESSION_ID.fullmatch(session):
                        session = None  # never reused, not even by the cleanup DELETE
                        raise ValueError("invalid session id")
                    if session:
                        headers["Mcp-Session-Id"] = session
                    result = await protocol_reply(response, 1)
                    if not isinstance(result, dict) or not isinstance(result.get("serverInfo"), dict) or not isinstance(result.get("protocolVersion"), str):
                        raise ValueError("invalid initialization")
                    if not SESSION_ID.fullmatch(result["protocolVersion"]):
                        raise ValueError("invalid protocol version")  # never sent as a header; the session is closed
                    headers["MCP-Protocol-Version"] = result["protocolVersion"]
                if session:
                    headers["Mcp-Session-Id"] = session
                async with self.client.stream("POST", self.child_url, headers=headers, json={
                    "jsonrpc": "2.0", "method": "notifications/initialized"}) as response:
                    if response.status_code not in (200, 202, 204):
                        raise ValueError("initialized rejected")
                async with self.client.stream("POST", self.child_url, headers=headers, json={
                    "jsonrpc": "2.0", "id": 2, "method": "ping"}) as response:
                    if await protocol_reply(response, 2) != {}:
                        raise ValueError("invalid ping")
                self.process.ready = self.process.status == "running"
            if configured:
                if self._capacity_metrics is not None:
                    self._capacity_phase = 2
                # Use the SAME API client, destination validation and DNS-pinned
                # connection as tools. Never perform a second Python network path.
                async with asyncio.timeout(5):
                    async with self.client.stream("POST", self.child_url, headers=headers, json={
                        "jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                            "name": probe_name, "arguments": probe_args}}) as response:
                        reply = await protocol_reply(response, 3)
                        reason = probe_reason(reply)  # 0.2.2: kept only when the backend stays unreachable
                        if isinstance(reply, dict) and not reply.get("isError"):
                            for item in reply.get("content", []):
                                if isinstance(item, dict) and item.get("type") == "text":
                                    payload = strict_json(item["text"])
                                    if product == 'n8n':
                                        valid = isinstance(payload, dict) and payload.get('success') is True
                                    else:
                                        from .products import health_probe_success
                                        valid = health_probe_success(product, payload)
                                    if valid:
                                        self.backend = "reachable"
        except Exception as error:
            # Whatever a misbehaving child provokes (odd headers, text or shapes) leaves readiness false and
            # the backend unreachable; it must never stop the monitor, which would stop the add-on.
            if reason is None and isinstance(error, TimeoutError):
                reason = "BACKEND_TIMEOUT: the health check got no answer within 5 s"
            if self._capacity_metrics is not None and isinstance(error, TimeoutError):
                self._capacity_timeout = True
        finally:
            if session:
                try:
                    async with asyncio.timeout(3):
                        async with self.client.stream("DELETE", self.child_url, headers=headers):
                            pass
                except Exception:
                    pass
        return reason

    async def _scheduled_check(self):
        if self._capacity_metrics is None:
            await self.check()
            return
        scheduled_at_ns = time.monotonic_ns()
        self._capacity_metrics.on_health_check_scheduled(self._capacity_slot, scheduled_at_ns)
        await self.check(capacity_scheduled_at_ns=scheduled_at_ns)

    async def run(self):
        if not self.paced:
            while True:
                await self._scheduled_check()
                await asyncio.sleep(15)
        if self.first_check_after:
            await self._pause(self.first_check_after)
        while True:
            await self._scheduled_check()
            await self._pause(self.next_interval())
