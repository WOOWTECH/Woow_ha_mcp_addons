"""HM-09: every profile's health monitor once its product is switched on (multi-profile plan 5.4; contract 7; DQ-25,
2026-11-15 11:2x: the plan's recommendation; §8.8 #18; FM-68, 69, 91; C-tracer 4.4; C2-MF-4 point 3).

- Each profile has its own monitor on its own child client (no pool is shared: plan 3.2), and the start points are
  staggered: the default profile checks at once (as before), an additional profile's monitor first checks one interval
  plus its share of it after its start (15 s x position / (product limit + 1)); the interval stays 15 s.
- When the backend refuses the credentials, that profile's checks back off 15, 30, 60, 120, 300 s (Odoo 18 counts
  failed logins per source address: 5 in 60 s cool every profile of the add-on down); any other answer resets it, and
  so do a save and the panel's restart (new credentials). One WARNING a minute says so.
- Switched on, a backend is judged unreachable only after two failed checks in a row of the same child (a single
  check another profile's load delayed refuses nothing); a check whose child did not answer is no such failure (it
  refuses nothing either). The panel's explicit backend test still reports what it found.
- A monitor never sends anything to a port its own child does not hold (blocked, backing off, failed, stopped: T-15's
  "the program that took the port gets nothing").
- Not switched on, the monitor is today's: every 15 s, one failed check is unreachable, no backoff.

Which answers are a refusal of the credentials: the readiness probes' fixed texts of the children of this repository
(pinned to their sources below), and Nextcloud's brute-force throttle (429 after failed logins).
"""
import asyncio
import json
from pathlib import Path
import time

import httpx
import pytest

from lifecycle_runtime import lifecycle_lines, manager_rig, until, watch
from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import health, profiles
from mcp_admin_core.config import Store
from mcp_admin_core.health import HealthMonitor

pytestmark = pytest.mark.usefixtures('log_scan')
ROOT = Path(__file__).resolve().parents[1]
ODOO_REFUSED = ("BACKEND_AUTH_REJECTED: Odoo 憑證被拒 (credentials rejected); check the database, username and password "
                "in the add-on's connection settings.")


class Process:
    """A Supervisor's face as the monitor sees it."""

    def __init__(self, status='running', starts=1):
        self.ready, self.status, self.starts = False, status, starts

    def health(self):
        return {'state': self.status, 'transport_ready': self.ready, 'starts': self.starts, 'last_exit': None}


class Child:
    """A child as the monitor reaches it: initialize, initialized, ping and the n8n probe; probe holds what the probe
    answers: None (success), a text (the tool error), or 'silent' (no answer at all: a refused connection)."""

    def __init__(self):
        self.probe = None
        self.requests = []

    async def __call__(self, request):
        self.requests.append(request)
        if self.probe == 'silent':
            raise httpx.ConnectError('nothing listens', request=request)
        if request.method == 'DELETE':
            return httpx.Response(200)
        message = json.loads(request.content)
        if 'id' not in message:
            return httpx.Response(202)
        if message['method'] == 'initialize':
            result = {'protocolVersion': '2025-03-26', 'serverInfo': {'name': 'mock'}}
        elif message['method'] == 'ping':
            result = {}
        elif self.probe is None:
            result = {'content': [{'type': 'text', 'text': json.dumps({'success': True})}]}
        else:
            result = {'content': [{'type': 'text', 'text': 'Error executing tool n8n_list_workflows: ' + self.probe}],
                      'isError': True}
        return httpx.Response(200, headers={'mcp-session-id': 'health'},
                              json={'jsonrpc': '2.0', 'id': message['id'], 'result': result})


async def monitored(tmp_path, **options):
    store = Store(tmp_path / 'state')
    store.update(backend_url='https://backend.invalid', backend_key='DUMMY-backoff-key')
    child = Child()
    client = httpx.AsyncClient(transport=httpx.MockTransport(child))
    process = Process()
    return store, child, client, process, HealthMonitor(store, process, client, **options)


def switched_on():
    """The options ProfileManager gives every profile's monitor (read when a test runs: before HM-09 there was no
    AUTH_BACKOFF, and each test then failed on its own)."""
    return dict(tolerance=2, auth_backoff=health.AUTH_BACKOFF, own_child_only=True)


def test_the_backoff_and_the_interval_are_the_decided_ones():
    assert health.HEALTH_INTERVAL == 15 and health.AUTH_BACKOFF == (15, 30, 60, 120, 300)


# ---- which answers refuse the credentials ----

REFUSALS = {
    'odoo': (ODOO_REFUSED, 'apps/odoo/launch.py', ['BACKEND_AUTH_REJECTED: Odoo 憑證被拒 (credentials rejected)']),
    'hermes': ('BACKEND_AUTH_REJECTED status=401: Hermes gateway 憑證被拒 (credentials rejected)',
               'apps/hermes/vendor/hermes_mcp_server/errors.py', ['f"BACKEND_AUTH_REJECTED status={status}: '
                                                                  '{label} 憑證被拒 "']),
    'nextcloud': ('BACKEND_HTTP_ERROR status=401: Nextcloud rejected the username or app password.',
                  'apps/nextcloud/vendor/nextcloud_mcp_server/errors.py',
                  ['return f"BACKEND_HTTP_ERROR status={int(status)}"',
                   'AUTH_MESSAGE = "Nextcloud rejected the username or app password."']),
    'nextcloud throttle': ('BACKEND_HTTP_ERROR status=429: Nextcloud is throttling requests from this server (too many '
                           'failed logins); ask the Nextcloud administrator to reset brute-force protection for this '
                           'IP, then restart the server.', 'apps/nextcloud/vendor/nextcloud_mcp_server/errors.py',
                           ['"Nextcloud is throttling requests from this server (too many failed logins); ask the "']),
    'emqx': ('EMQX rejected the API credentials (401). The configured API key or secret is wrong, expired, or disabled.',
             'apps/emqx/vendor/emqx_mcp_server/errors.py', ['"EMQX rejected the API credentials (401). The configured '
                                                            'API key "']),
    'litellm': ('LiteLLM rejected the credentials (401 Unauthorized). The LITELLM_MCP_MASTER_KEY is missing or wrong. '
                'Details: {"error": "Authentication Error"}', 'apps/litellm/vendor/woow_litellm_mcp_server/errors.py',
                ['"LiteLLM rejected the credentials (401 Unauthorized). The "']),
    'headscale': ('HEADSCALE_INVALID_CREDENTIAL', 'apps/headscale/vendor/headscale_mcp_server/client.py',
                  ['raise HeadscaleError("HEADSCALE_INVALID_CREDENTIAL")']),
}
NOT_REFUSALS = ('BACKEND_UNAVAILABLE', 'BACKEND_TIMEOUT: the health check got no answer within 5 s',
                "MCP_SERVER_NOT_READY: the add-on's MCP server did not answer the health check",
                'BACKEND_HTTP_ERROR status=404: "x" does not exist.', 'BACKEND_HTTP_ERROR status=4010: odd',
                'EMQX has no such resource (404).', 'LiteLLM forbade the request (403).', 'EMQX_UNAVAILABLE: x',
                'the backend said BACKEND_AUTH_REJECTED somewhere', 'HEADSCALE_INVALID_CREDENTIALS', '', None, 401)


@pytest.mark.parametrize('product', sorted(REFUSALS))
def test_every_childs_refused_credentials_text_is_recognised(product):
    text, source, pinned = REFUSALS[product]
    assert health.auth_refused(text)
    code = (ROOT / source).read_text()
    for fragment in pinned:  # the child's own text: a change there must change the rule here
        assert fragment in code, (source, fragment)


@pytest.mark.parametrize('text', NOT_REFUSALS)
def test_other_failures_are_no_refusal_of_the_credentials(text):
    assert not health.auth_refused(text)


# ---- the backoff ----

async def test_refused_credentials_back_off_15_30_60_120_300_and_any_other_answer_resets(tmp_path, log_scan):
    store, child, client, process, monitor = await monitored(tmp_path, **switched_on())
    try:
        assert monitor.next_interval() == 15
        child.probe = ODOO_REFUSED
        intervals = []
        for _ in range(7):
            await monitor.check()
            intervals.append(monitor.next_interval())
        assert intervals == [15, 30, 60, 120, 300, 300, 300]
        child.probe = 'BACKEND_TIMEOUT: slow'
        await monitor.check()
        assert monitor.next_interval() == 15 and monitor.auth_refusals == 0
        child.probe = ODOO_REFUSED
        await monitor.check()
        await monitor.check()
        assert monitor.next_interval() == 30
        child.probe = None
        await monitor.check()
        assert monitor.next_interval() == 15 and monitor.availability()['backend'] == 'reachable'
    finally:
        await client.aclose()
        store.close()


async def test_the_monitor_waits_the_backoff_between_its_checks(tmp_path, log_scan):
    """run() uses next_interval(): with a scaled table (0.1, 0.2, 0.4) every refused check waits the next step."""
    store, child, client, process, monitor = await monitored(tmp_path, tolerance=2, auth_backoff=(0.1, 0.2, 0.4),
                                                             own_child_only=True)
    child.probe = ODOO_REFUSED
    checks = []
    original = monitor.check

    async def timed():
        checks.append(time.monotonic())
        await original()
    monitor.check = timed
    task = asyncio.create_task(monitor.run())
    try:
        await until(lambda: len(checks) == 5, timeout=10)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await client.aclose()
        store.close()
    gaps = [later - earlier for earlier, later in zip(checks, checks[1:])]
    assert [round(gap, 1) for gap in gaps] == [0.1, 0.2, 0.4, 0.4], gaps


async def test_a_save_or_restart_resets_the_backoff_and_checks_within_one_interval(tmp_path, log_scan, monkeypatch):
    """New credentials (ProfileRuntime: a save, the panel's restart) reset the backoff: a monitor waiting 300 s checks
    again within one interval (scaled to 0.2 s here)."""
    monkeypatch.setattr(health, 'HEALTH_INTERVAL', 0.2)
    store, child, client, process, monitor = await monitored(tmp_path, tolerance=2, auth_backoff=(300,),
                                                             own_child_only=True)
    child.probe = ODOO_REFUSED
    checks = []
    original = monitor.check

    async def timed():
        checks.append(time.monotonic())
        await original()
    monitor.check = timed
    task = asyncio.create_task(monitor.run())
    try:
        await until(lambda: len(checks) == 1)
        await asyncio.sleep(0.3)
        assert len(checks) == 1 and monitor.next_interval() == 300
        reset = time.monotonic()
        monitor.reset()
        assert monitor.auth_refusals == 0 and monitor.next_interval() == 0.2
        await until(lambda: len(checks) == 2, timeout=2)
        assert checks[1] - reset < 0.5
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await client.aclose()
        store.close()


async def test_a_refused_login_is_reported_once_a_minute(tmp_path, log_scan):
    async with manager_rig(tmp_path, extras=1) as rig:
        watch(log_scan, rig)
        b, = rig.extras
        child = rig.children.by_port[rig.ports[b]]
        await rig.manager.launch()
        await rig.manager.start_all()
        monitor = rig.health(b)
        original = child.__call__

        async def refusing(request):
            message = json.loads(request.content) if request.content else {}
            if message.get('method') == 'tools/call':
                return httpx.Response(200, json={'jsonrpc': '2.0', 'id': message['id'], 'result': {
                    'content': [{'type': 'text', 'text': 'Error executing tool woow_backend_probe: ' + ODOO_REFUSED}],
                    'isError': True}})
            return await original(request)
        rig.children.by_port[rig.ports[b]] = refusing
        for _ in range(3):
            await monitor.check()
        lines = [line for line in lifecycle_lines(log_scan) if 'refused the credentials' in line]
        assert lines == [f'MCP child [profile={profiles.log_id(b)} port={rig.ports[b]}]: the backend refused the '
                         'credentials; next health check in 15 s']
        assert monitor.next_interval() == 60


# ---- two failed checks in a row ----

async def test_two_failed_checks_in_a_row_judge_the_backend_unreachable(tmp_path, log_scan):
    store, child, client, process, monitor = await monitored(tmp_path, **switched_on())
    try:
        await monitor.check()
        assert monitor.availability()['backend'] == 'reachable'
        child.probe = 'BACKEND_TIMEOUT: slow'
        await monitor.check()  # one: still reachable (and the panel's health says so)
        assert monitor.availability() == {'child': 'running', 'ready': True, 'backend': 'reachable', 'reason': None}
        assert monitor.snapshot()['backend'] == 'reachable'
        await monitor.check()  # two in a row: unreachable, with the reason
        assert monitor.availability() == {'child': 'running', 'ready': True, 'backend': 'unreachable',
                                          'reason': 'BACKEND_TIMEOUT: slow'}
        child.probe = None
        await monitor.check()
        assert monitor.availability()['backend'] == 'reachable'
        child.probe = 'BACKEND_TIMEOUT: slow'
        await monitor.check()
        child.probe = None
        await monitor.check()
        child.probe = 'BACKEND_TIMEOUT: slow'
        await monitor.check()  # failures that are not in a row never add up
        assert monitor.availability()['backend'] == 'reachable'
        # A new child (a restart): the count starts again; one failure is no verdict ("unknown"), two are.
        process.starts += 1
        await monitor.check()
        assert monitor.availability()['backend'] == 'unknown' and monitor.availability()['ready'] is True
        await monitor.check()
        assert monitor.availability()['backend'] == 'unreachable'
    finally:
        await client.aclose()
        store.close()


async def test_a_child_that_does_not_answer_is_no_failure_of_the_backend(tmp_path, log_scan):
    """A check whose child did not answer (it refuses nothing: the gateway's own answers serve) neither counts as a
    failure nor breaks a row of them."""
    store, child, client, process, monitor = await monitored(tmp_path, **switched_on())
    try:
        await monitor.check()
        child.probe = 'BACKEND_TIMEOUT: slow'
        await monitor.check()
        child.probe = 'silent'
        await monitor.check()
        assert monitor.availability()['ready'] is False
        child.probe = 'BACKEND_TIMEOUT: slow'
        await monitor.check()
        assert monitor.availability()['backend'] == 'unreachable'  # the two failures around the silent one
    finally:
        await client.aclose()
        store.close()


async def test_switched_off_one_failed_check_is_unreachable_as_before(tmp_path, log_scan):
    store, child, client, process, monitor = await monitored(tmp_path)
    try:
        await monitor.check()
        child.probe = ODOO_REFUSED
        await monitor.check()
        assert monitor.availability()['backend'] == 'unreachable'
        assert monitor.next_interval() == 15 and monitor.auth_refusals == 0
        for _ in range(3):
            await monitor.check()
        assert monitor.next_interval() == 15
    finally:
        await client.aclose()
        store.close()


async def test_the_panels_backend_test_reports_what_it_found(tmp_path, log_scan):
    """backend/test (test_saved) after a reachable check, with the backend now failing: its answer says unreachable and
    why; the monitor's verdict for the gateway still needs a second failure."""
    store, child, client, process, monitor = await monitored(tmp_path, **switched_on())
    try:
        await monitor.check()
        child.probe = 'BACKEND_TIMEOUT: slow'
        result = await monitor.test_saved(store.load())
        assert (result['backend'], result['reason']) == ('unreachable', 'BACKEND_TIMEOUT: slow')
        assert monitor.availability()['backend'] == 'reachable'
        await monitor.check()
        assert monitor.availability()['backend'] == 'unreachable'
    finally:
        await client.aclose()
        store.close()


async def test_a_tools_call_is_refused_only_after_two_failed_checks(tmp_path, log_scan):
    """Through the gateway (switched on): B's backend fails one check, B's tools/call is still forwarded; after the
    second, it is refused (-32603 Backend unreachable, with the reason)."""
    from test_profile_runtime import public_read
    async with manager_rig(tmp_path, extras=1) as rig:
        watch(log_scan, rig)
        b, = rig.extras
        await rig.manager.launch()
        await rig.manager.start_all()
        child = rig.children.by_port[rig.ports[b]]
        monitor = rig.health(b)
        await monitor.check()
        assert monitor.availability()['backend'] == 'reachable'
        original = child.__call__

        async def failing(request):
            message = json.loads(request.content) if request.content else {}
            if message.get('method') == 'tools/call' and message['params']['name'] == 'woow_backend_probe':
                return httpx.Response(200, json={'jsonrpc': '2.0', 'id': message['id'], 'result': {
                    'content': [{'type': 'text', 'text': 'Error executing tool woow_backend_probe: BACKEND_UNAVAILABLE'}],
                    'isError': True}})
            return await original(request)
        rig.children.by_port[rig.ports[b]] = failing
        tool, arguments = public_read('odoo')

        async def call():
            headers = {'Accept': 'application/json, text/event-stream', 'Authorization': 'Bearer ' + rig.token(b)}
            async with rig.mcp() as client:
                init = await client.post('/mcp', headers=headers, json={
                    'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                        'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'c', 'version': '0'}}})
                session = {**headers, 'Mcp-Session-Id': init.headers['mcp-session-id']}
                await client.post('/mcp', headers=session, json={'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                return (await client.post('/mcp', headers=session, json={
                    'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                    'params': {'name': tool, 'arguments': arguments}})).json()
        await monitor.check()
        assert 'result' in await call()
        await monitor.check()
        refused = await call()
        assert refused['error']['message'] == 'Backend unreachable'
        assert refused['error']['data']['reason'] == 'BACKEND_UNAVAILABLE'


# ---- staggered, own client, own child only ----

async def test_every_profile_has_its_own_monitor_client_and_staggered_start(tmp_path, log_scan):
    """The default profile's monitor checks at once; the k-th additional one first checks 15 + 15 x k / (limit + 1) s
    after it starts (Odoo, limit 5: 17.5, 20, 22.5 s); every monitor uses its own profile's child client."""
    async with manager_rig(tmp_path, extras=3) as rig:
        watch(log_scan, rig)
        monitors = [rig.health(p) for p in ['default', *rig.extras]]
        assert [monitor.first_check_after for monitor in monitors] == [0, 17.5, 20.0, 22.5]
        assert all(monitor.client is rig.entry(p).runtime.child for monitor, p in zip(monitors, ['default', *rig.extras]))
        assert len({id(monitor.client) for monitor in monitors}) == 4
        assert all((monitor.tolerance, monitor.auth_backoff, monitor.own_child_only) == (2, health.AUTH_BACKOFF, True)
                   for monitor in monitors)


@pytest.mark.parametrize('status', ['blocked', 'backoff', 'failed', 'stopped', 'starting'])
async def test_a_monitor_never_probes_a_child_that_is_not_running(tmp_path, log_scan, status):
    store, child, client, process, monitor = await monitored(tmp_path, **switched_on())
    try:
        process.status = status
        await monitor.check()
        assert child.requests == []
        assert monitor.availability() == {'child': status, 'ready': False, 'backend': 'unknown', 'reason': None}
        assert monitor.snapshot()['backend'] == 'unknown'
    finally:
        await client.aclose()
        store.close()


async def test_switched_off_the_monitor_probes_as_before_whatever_the_childs_state(tmp_path, log_scan):
    store, child, client, process, monitor = await monitored(tmp_path)
    try:
        process.status = 'backoff'
        await monitor.check()
        assert child.requests and monitor.snapshot()['backend'] == 'reachable'
    finally:
        await client.aclose()
        store.close()


async def test_switched_off_the_monitor_loop_is_todays(tmp_path, log_scan, monkeypatch):
    """No option: run() is a check, then asyncio.sleep(15), for ever (the first check at once)."""
    store, child, client, process, monitor = await monitored(tmp_path)
    slept = []

    async def sleep(seconds):
        slept.append(seconds)
        if len(slept) == 3:
            raise asyncio.CancelledError
    monkeypatch.setattr(health.asyncio, 'sleep', sleep)
    try:
        with pytest.raises(asyncio.CancelledError):
            await monitor.run()
        assert slept == [15, 15, 15] and monitor.first_check_after == 0
    finally:
        await client.aclose()
        store.close()
