"""HM-12: a switched-on Odoo profile's MCP token stays bound to one backend identity (multi-profile plan 9 Odoo row,
12.3 HM-12, 10.3; DQ-05; contract 2.3, 3.1, 4.1, section 9 #40, #59 and HM-12's rows; invariant I11; FM-81; UC-21).

Once Odoo is switched on (features.enabled), a save of the backend (PUT backend or backend/patch, through the 8099
dispatcher) that changes url, database or username, a cleared connection included, while the token is active and the
saved connection is complete, does in this order: the profile's old child is stopped (no child runs on the old
credentials once a new token exists anywhere: UC-21), then one durable write holds the new connection, the new token and
its masked history entry (action rotate, as a token rotation: no new action name, section 9 #59), then the token change
is published (TokenAccess: every request of the old token ends, on both connection paths; the 8081 dispatcher routes
the old token to no profile, and the profile's own app refuses it too), then the child starts on the committed state.
The answer says token_rotated: true, carries the new state's ETag (the panel's next If-Match) and never the token. A
password change alone and the first setup keep the token; a revoked token stays revoked.

A stop that fails writes nothing (503, the old child relaunched, the old token still served). A write that fails answers
today's 503 state unavailable whatever it raises, and the token on disk decides the rest: still the old one (the store
refused the write, it failed before the state file was replaced, or it raised something unexpected first), nothing was
written, so the old child is relaunched and the old token still served; a write that fails once the state file is being
replaced has an unknown outcome and poisons the store as every such failure does today (503 until the add-on restarts,
which serves what is on disk, token and identity together; every profile's 503 once the default profile's new state
file is in place, as when the default state cannot be read); a new token on disk although the write raised (a failure
after the rename that leaves the store usable) is served with no child. The old child stays stopped in both. A new child
that cannot start leaves the new token and never the old child (config_apply_failed with token_rotated). Switched off,
nothing changes (plan 3.3): the save commits first and restarts the child, the token stays, the answer is today's. The
other switched-on products keep their token (Nextcloud HM-22, Hermes HM-24).

PaaS (woow-mcp-server 69ac425): packages/mcp-admin-core/mcp_admin_core/config/store.py:502-533 patch_connection_bound
and its tests packages/mcp-admin-core/tests/test_config_store.py:102-170 (test_bound_connection_rotation_is_atomic_and_
preserves_password_changes, test_initial_bound_connection_setup_keeps_issued_url,
test_failed_account_rebind_restores_old_child_and_url), packages/mcp-admin-core/tests/test_connection_type_parity.py:89
(test_odoo_account_rebind_revokes_old_url_without_rotating_on_password_change) and the restore failure's one log line
(packages/mcp-admin-core/tests/conftest.py:157). Every case runs the production runtime in process
(tests/multi_profile_runtime.py: NoProcessSupervisor, the children behind one MockTransport) under the HM-01 log scan.
"""
import asyncio
from contextlib import closing
import errno
import json
import logging
from pathlib import Path
import secrets
import stat

import httpx
import pytest

from admin_write_headers import reviewed_headers
from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import Children, all_tokens, create_profile, ids, multi_profile_runtime, stored
from mcp_admin_core import config as config_module, features, profiles
from mcp_admin_core.access import TokenAccess, masked_token
from mcp_admin_core.config import ConfigError
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS
from switched_gateway import GatewayChild, call, quota, until
from test_profile_runtime import connection_of
from test_single_profile_golden import (ACCEPT, ADMIN, BEARER_REQUIRED, GENUINE_CLIENT, INGRESS, NOT_FOUND,
                                        NoProcessSupervisor, answer, configure, initialize_message,
                                        production_runtime, settle)

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'odoo'
B, = ids(1)
LABELS = {B: 'Beta Ops'}
PORTS = {B: 18000}
# The new identity values a test saves (tests/fixtures/owner_defaults/README.md rules: .invalid hosts, DUMMY- values).
REBOUND = {'url': 'https://rebound.odoo.invalid', 'database': 'DUMMY-db-two', 'username': 'DUMMY-user-two'}
NEW_PASSWORD = 'DUMMY-rebound-odoo-password'
WARNING_PREFIX = 'multi-profile: the backend identity change of profile '


@pytest.fixture(autouse=True)
def memory_readings(monkeypatch):
    """The memory readings are the test's (no cgroup limit, 4 GiB available): a save of an additional profile starts
    its child whatever the host has (contract 5's check is HM-09's tests)."""
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: None)
    monkeypatch.setattr(profiles, 'available_memory_mib', lambda: 4096)


def directory(data, profile_id):
    return Path(data) if profile_id == 'default' else profiles.Layout(Path(data)).profile(profile_id)


def setup(tmp_path, extras=(B,), configured=True):
    """The default profile configured as the golden one, the additional profiles extras on their PORTS (their own
    synthetic backends when configured), and every profile's child behind one MockTransport."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    children = Children()
    children.profile_child(3000, 'default', PRODUCT, data)
    for profile_id in extras:
        create_profile(data, PRODUCT, profile_id, label=LABELS[profile_id], port=PORTS[profile_id],
                       configured=configured)
        children.profile_child(PORTS[profile_id], 'p' + profile_id[:4], PRODUCT, directory(data, profile_id))
    return data, children


def watch(log_scan, data):
    """Every token, child token and synthetic credential stored under data, and every label (the log scan's needles);
    a test watches a token made later (a rotation's) once it exists."""
    log_scan.watch(*all_tokens(data))
    for path in [Path(data) / 'state.json', *sorted((Path(data) / 'profiles').glob('*/state.json'))]:
        connection = json.loads(path.read_text()).get('connection') or {}
        log_scan.watch(*(value for name, value in connection.items() if name == 'password'), kind='secret')
    log_scan.watch(NEW_PASSWORD, kind='secret')
    log_scan.watch(*LABELS.values(), kind='name')


class Journal:
    """The order of what a save does to one profile (watch() names it): each effective stop of its child (the token
    and the username its state held on disk then), each identity write (its child's status then), each published
    token change and each start (the username its spec carries). What a test injects: refuse_stop and refuse_start
    (that many of the next ones fail), hold_start (an Event the next start waits for)."""

    def __init__(self):
        self.events = []
        self.directory = self.instance = None
        self.refuse_stop = self.refuse_start = 0
        self.hold_start = None

    def watch(self, data, profile_id, supervisor=None):
        self.directory, self.instance = directory(data, profile_id), supervisor
        self.events.clear()

    def mine(self, supervisor):
        if self.directory is None:
            return False
        if self.instance is None and supervisor.spec is not None and supervisor.spec.cwd.parent == self.directory:
            self.instance = supervisor  # switched off: the only profile, found by its spec's directory
        return supervisor is self.instance

    def supervisor(self):
        journal = self

        class Recorded(NoProcessSupervisor):
            async def start(self):
                if journal.mine(self) and journal.hold_start is not None:
                    gate, journal.hold_start = journal.hold_start, None
                    journal.events.append(('start waits',))
                    await gate.wait()
                await super().start()

            def _start_child(self):
                if journal.mine(self) and self.spec is not None:
                    username = self.spec.env['ODOO_USERNAME']
                    if journal.refuse_start:
                        journal.refuse_start -= 1
                        journal.events.append(('start refused', username))
                        raise RuntimeError('HM-12 test: the child does not start')
                    journal.events.append(('start', username))
                super()._start_child()

            async def _stop_child(self):
                if journal.mine(self) and self.status in ('running', 'starting'):
                    if journal.refuse_stop:
                        journal.refuse_stop -= 1
                        journal.events.append(('stop refused',))
                        self.status = 'failed'  # a real Supervisor marks a child it could not stop failed
                        raise RuntimeError('HM-12 test: the child does not stop')
                    on_disk = stored(journal.directory)
                    journal.events.append(('stop', on_disk['token'], (on_disk['connection'] or {}).get('username')))
                await super()._stop_child()
        return Recorded


def record_writes(monkeypatch, journal, *, refuse=None):
    """Each identity write (ProductStore.rebind) and each published token change (TokenAccess.committed) of the
    journal's profile, in its journal; refuse: (exception class, message) the write raises before anything is written
    (the store's own ConfigError for an update it cannot take, or anything else it might raise)."""
    rebind = ProductStore.rebind

    def recorded_rebind(store, changes, token):
        if Path(store.directory) == journal.directory:
            journal.events.append(('write', journal.instance.status))
            if refuse is not None:
                kind, message = refuse
                raise kind(message)
        return rebind(store, changes, token)
    monkeypatch.setattr(ProductStore, 'rebind', recorded_rebind)
    committed = TokenAccess.committed

    def recorded_committed(access):
        if Path(access.store.directory) == journal.directory:
            journal.events.append(('publish',))
        committed(access)
    monkeypatch.setattr(TokenAccess, 'committed', recorded_committed)


def bearer(token):
    return {**ACCEPT, 'Authorization': 'Bearer ' + token}


def paths(token):
    """Both connection paths of one token: (path, headers)."""
    return (('/mcp', bearer(token)), (f'/private_{token}/mcp', dict(ACCEPT)))


async def refused_everywhere(runtime, token):
    """Whether token is refused on both connection paths as a token no profile holds: Bearer 401, secret path 404."""
    async with runtime.mcp() as client:
        found = [answer(await client.post(path, headers=headers, json=initialize_message()))
                 for path, headers in paths(token)]
    return found == [BEARER_REQUIRED, NOT_FOUND]


async def opened_by(runtime, token, child):
    """Whether token opens a session with the profile's child on both connection paths (the child's own session)."""
    opened = []
    async with runtime.mcp() as client:
        for path, headers in paths(token):
            response = await client.post(path, headers=headers, json=initialize_message())
            opened.append(response.status_code == 200 and response.headers.get('mcp-session-id') in child.sessions)
    return opened == [True, True]


async def save(runtime, profile_id, route, body):
    async with runtime.admin(profile_id) as admin:
        boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
        return await admin.put('/api/' + route, json=body, headers=reviewed_headers(boot, ADMIN))


async def next_etag(runtime, profile_id):
    """The ETag of the profile's next bootstrap, the quoted revision of its state (the If-Match the panel's next save
    sends): what a save's answer must carry once it changed the state (HM-12 review S-3)."""
    async with runtime.admin(profile_id) as admin:
        fresh = await admin.get('/api/bootstrap', headers=ADMIN)
    assert fresh.headers['etag'] == '"' + fresh.json()['configuration']['revision'] + '"'
    return fresh.headers['etag']


def routed_to(runtime, token):
    """The profiles the 8081 dispatcher routes token to (profile_router.McpDispatcher.resolve), before any profile's
    own app checks it again (HM-12 review S-4: the dispatcher itself drops a rotated token)."""
    return [entry.profile_id for entry in runtime.mcp_app.resolve(token.encode())]


def identity_body(route, field, value, connection, password=None):
    """A save of one identity field: the whole connection (PUT backend) or the field alone (backend/patch; with the
    password when one is brought)."""
    if route == 'backend':
        return {'connection': {**connection, field: value, **({'password': password} if password else {})}}
    return {'changes': {field: value, **({'password': password} if password else {})}}


def count_writes(monkeypatch, path):
    """How many times the state file at path is replaced (Store._write's os.replace): one write, one replace."""
    replaced = []
    replace = config_module.os.replace

    def counting(source, target, *args, **kwargs):
        if Path(target) == path:
            replaced.append(target)
        return replace(source, target, *args, **kwargs)
    monkeypatch.setattr(config_module.os, 'replace', counting)
    return replaced


def warnings_of(log_scan):
    return [record.getMessage() for record in log_scan.records
            if record.levelno == logging.WARNING and record.getMessage().startswith(WARNING_PREFIX)]


# ---- the rotation (PaaS test_bound_connection_rotation_is_atomic_and_preserves_password_changes and
# test_odoo_account_rebind_revokes_old_url_without_rotating_on_password_change) ----

CASES = [('url', 'backend', None), ('url', 'backend/patch', NEW_PASSWORD), ('url path', 'backend/patch', None),
         ('database', 'backend', None), ('database', 'backend/patch', None), ('username', 'backend', None),
         ('username', 'backend/patch', None)]


@pytest.mark.parametrize('case, route, password', CASES, ids=[f'{c}-{r}' for c, r, _ in CASES])
async def test_a_changed_identity_stops_the_old_child_then_rotates_the_token_in_one_write(
        tmp_path, log_scan, monkeypatch, case, route, password):
    """B's url, database or username saved anew (a url on another origin brings its password, DQ-40 ⑨; a path on the
    same origin does not need it): the old child stops while the old token is still the one on disk; the write comes
    with no child running; then the token change is published; then the new child starts on the new identity. 200
    {"saved", "token_rotated": true, "configuration"} with B's echo, no token in it, and the new state's ETag (the one
    B's next bootstrap carries). The state has the new connection (the other fields and, unless brought, the password
    as they were), a new 43-character token and one history entry (rotate, the old token masked), all of it in one
    write of the state file. The 8081 dispatcher routes the old token to no profile and the new one to B; the old token
    is refused on both paths; the new one opens a session with B's child on both; the default profile's state and token
    are untouched (invariant I6)."""
    data, children = setup(tmp_path)
    journal = Journal()
    record_writes(monkeypatch, journal)
    replaced = count_writes(monkeypatch, directory(data, B) / 'state.json')
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        journal.watch(data, B, runtime.manager.get(B).runtime.supervisor)
        before = stored(directory(data, B))
        old, default_state = before['token'], (data / 'state.json').read_bytes()
        field = 'url' if case == 'url path' else case
        value = before['connection']['url'] + '/odoo' if case == 'url path' else REBOUND[field]
        replaced.clear()
        saved = await save(runtime, B, route, identity_body(route, field, value, before['connection'], password))
        assert saved.status_code == 200, saved.text
        assert len(replaced) == 1, 'the connection, the token and its history are one write'
        body = saved.json()
        assert list(body) == ['saved', 'token_rotated', 'configuration', 'profile']
        assert (body['saved'], body['token_rotated'], body['profile']) == (True, True, {'id': B})
        after = stored(directory(data, B))
        new = after['token']
        log_scan.watch(new)
        assert new not in (None, old) and len(new) == 43 and new not in saved.text and old not in saved.text
        assert after['child_token'] == before['child_token']
        assert after['connection'] == {**before['connection'], field: value,
                                       **({'password': password} if password else {})}
        assert len(after['token_history']) == 1
        entry = after['token_history'][0]
        assert (entry['action'], entry['previous_token_masked']) == ('rotate', masked_token(old))
        username = after['connection']['username']
        assert journal.events == [('stop', old, before['connection']['username']), ('write', 'stopped'),
                                  ('publish',), ('start', username)]
        assert saved.headers['etag'] == await next_etag(runtime, B)
        assert routed_to(runtime, old) == [] and routed_to(runtime, new) == [B]
        assert await refused_everywhere(runtime, old)
        assert await opened_by(runtime, new, children.by_port[PORTS[B]])
        assert (data / 'state.json').read_bytes() == default_state
        assert await opened_by(runtime, runtime.token('default'), children.by_port[3000])


async def test_the_default_profile_is_bound_to_its_identity_too_once_switched_on(tmp_path, log_scan, monkeypatch):
    """Switched on, the default profile is a profile like the others (plan 7.2 point 7): its username saved anew
    rotates its token in the same order, the answer carrying its new ETag; the dispatcher routes its old token to no
    profile, which its own app then refuses on both paths (no profile holds it), and the new one to it, which opens a
    session with its child; B's state and token stay as they were."""
    data, children = setup(tmp_path)
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        journal.watch(data, 'default', runtime.manager.get('default').runtime.supervisor)
        old, extra_state = runtime.token('default'), directory(data, B).joinpath('state.json').read_bytes()
        saved = await save(runtime, 'default', 'backend/patch', {'changes': {'username': REBOUND['username']}})
        assert saved.status_code == 200 and saved.json()['token_rotated'] is True, saved.text
        new = runtime.token('default')
        log_scan.watch(new)
        assert new != old and journal.events == [('stop', old, 'DUMMY-user'), ('write', 'stopped'), ('publish',),
                                                 ('start', REBOUND['username'])]
        assert saved.headers['etag'] == await next_etag(runtime, 'default')
        assert routed_to(runtime, old) == [] and routed_to(runtime, new) == ['default']
        assert await refused_everywhere(runtime, old)
        assert await opened_by(runtime, new, children.by_port[3000])
        assert directory(data, B).joinpath('state.json').read_bytes() == extra_state
        assert await opened_by(runtime, runtime.token(B), children.by_port[PORTS[B]])


async def test_a_password_change_or_the_first_setup_keeps_the_token(tmp_path, log_scan, monkeypatch):
    """PaaS test_initial_bound_connection_setup_keeps_issued_url and the password half of
    test_bound_connection_rotation_is_atomic_and_preserves_password_changes: B's first connection (it had none), then
    a new password alone (backend/patch), then the whole connection again with the same identity and another password
    (PUT backend), then the same URL with a trailing slash (the saved value, once validated): every answer is today's
    (no token_rotated), the token B was born with stays, no history entry is written, and each save restarts the child
    after its write (today's order: the state on disk is the new one when the child stops). A revoked token stays
    revoked through an identity change (no new token, no new history entry beyond the revocation's)."""
    data, children = setup(tmp_path, configured=False)
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        journal.watch(data, B, runtime.manager.get(B).runtime.supervisor)
        token = runtime.token(B)
        assert stored(directory(data, B))['connection'] is None
        first = connection_of(PRODUCT, 'p' + B[:4])
        log_scan.watch(first['password'], kind='secret')
        for route, body in (('backend', {'connection': first}),
                            ('backend/patch', {'changes': {'password': NEW_PASSWORD}}),
                            ('backend', {'connection': {**first, 'password': first['password']}}),
                            ('backend/patch', {'changes': {'url': first['url'] + '/'}})):
            saved = await save(runtime, B, route, body)
            assert saved.status_code == 200, saved.text
            assert list(saved.json()) == ['saved', 'configuration', 'profile'], route
        state = stored(directory(data, B))
        assert state['token'] == token and 'token_history' not in state
        assert state['connection'] == first
        assert journal.events == [('start', 'DUMMY-user'), ('stop', token, 'DUMMY-user'), ('start', 'DUMMY-user'),
                                  ('stop', token, 'DUMMY-user'), ('start', 'DUMMY-user'),
                                  ('stop', token, 'DUMMY-user'), ('start', 'DUMMY-user')]
        assert await opened_by(runtime, token, children.by_port[PORTS[B]])
        async with runtime.admin(B) as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            revoked = await admin.post('/api/token/revoke', headers=reviewed_headers(boot, ADMIN))
            assert revoked.status_code == 200, revoked.text
        saved = await save(runtime, B, 'backend/patch', {'changes': {'username': REBOUND['username']}})
        assert saved.status_code == 200 and list(saved.json()) == ['saved', 'configuration', 'profile'], saved.text
        state = stored(directory(data, B))
        assert state['token'] is None and [entry['action'] for entry in state['token_history']] == ['revoke']
        assert state['connection']['username'] == REBOUND['username']
        assert await refused_everywhere(runtime, token)


async def test_a_cleared_connection_rotates_the_token(tmp_path, log_scan, monkeypatch):
    """PUT backend {"connection": null} clears a complete identity (PaaS: a cleared identity field is a change): the
    old child stops, the write holds the new token, nothing is started (no connection); the old token is refused, the
    new one connects to the gateway's own answers (no child: no backend configured)."""
    data, children = setup(tmp_path)
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        journal.watch(data, B, runtime.manager.get(B).runtime.supervisor)
        old = runtime.token(B)
        saved = await save(runtime, B, 'backend', {'connection': None})
        assert saved.status_code == 200 and saved.json()['token_rotated'] is True, saved.text
        new = runtime.token(B)
        log_scan.watch(new)
        assert new != old and stored(directory(data, B))['connection'] is None
        assert journal.events == [('stop', old, 'DUMMY-user'), ('write', 'stopped'), ('publish',)]
        assert await refused_everywhere(runtime, old)
        async with runtime.mcp() as client:
            local = await client.post('/mcp', headers=bearer(new), json=initialize_message())
        assert local.status_code == 200 and local.headers['mcp-session-id'].startswith('woow-local-')


# ---- what fails (PaaS test_failed_account_rebind_restores_old_child_and_url; conftest.py:157, the one line) ----

FAILURES = ('stop', 'refused', 'refused and no restart', 'unexpected', 'write')
# What the write raises before anything is written: the store's own refusal, or anything else ProductStore.rebind
# raises (its ValueError for a call that is no rebind; HM-12 review S-5: still the fixed 503, never a 500)
REFUSED = (ConfigError, 'invalid state update')
REFUSALS = {'refused': REFUSED, 'refused and no restart': REFUSED,
            'unexpected': (ValueError, 'invalid identity rebind')}
RELAUNCHED = 'its child was relaunched on the saved connection'
NOT_RELAUNCHED = 'its child could not be relaunched'
UNKNOWN = ' failed while its state file was being replaced: whether it was saved is unknown, so its child stays ' \
          'stopped until the add-on restarts and reads the state on disk'


def disk_full(monkeypatch, directory):
    """The disk takes no new file in directory: a new state file (Store._write's .state-<hex>) cannot be made there,
    so nothing reaches state.json (os.open of the temporary file fails, ENOSPC)."""
    real_open = config_module.os.open

    def refusing(path, flags, *args, **kwargs):
        if isinstance(path, (str, Path)) and Path(path).parent == directory and Path(path).name.startswith('.state-'):
            raise OSError(errno.ENOSPC, 'HM-12 test: no space left for a new state file')
        return real_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(config_module.os, 'open', refusing)


@pytest.mark.parametrize('failure', FAILURES)
async def test_a_failed_identity_change_keeps_the_old_identity_its_token_and_its_child(tmp_path, log_scan,
                                                                                      monkeypatch, failure):
    """Nothing is saved, the old token is served on both paths and the old child is relaunched on the saved state
    (PaaS: the failed write leaves the old token and account intact and restores the old child). stop: the old child
    does not stop: nothing is written (503 {"error":"request denied"}), the child is relaunched (the stop is tried
    again first). refused: the store refuses the write before writing (its ConfigError: today's 503 state
    unavailable). refused and no restart: the same, and the child does not come back either (apply_state failed).
    unexpected: the write raises something that is no ConfigError before writing (HM-12 review S-5): the same fixed
    503 state unavailable, never a 500. write: the new state file cannot be written (the disk is full): the state file
    was never replaced, so the store stays usable (unlike a failure once the replace began, below) and the answer is
    today's 503 state unavailable. Each writes one WARNING naming B's id's first 8 characters (never a token, URL or
    label) and whether the child was relaunched."""
    data, children = setup(tmp_path)
    journal = Journal()
    record_writes(monkeypatch, journal, refuse=REFUSALS.get(failure))
    state_path = directory(data, B) / 'state.json'
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        journal.watch(data, B, runtime.manager.get(B).runtime.supervisor)
        journal.refuse_stop = int(failure == 'stop')
        journal.refuse_start = int(failure == 'refused and no restart')
        if failure == 'write':
            disk_full(monkeypatch, state_path.parent)
        before_bytes, old = state_path.read_bytes(), runtime.token(B)
        saved = await save(runtime, B, 'backend/patch', {'changes': {'username': REBOUND['username']}})
        expected = (b'{"error":"request denied"}' if failure == 'stop' else b'{"error":"state unavailable"}')
        assert (saved.status_code, saved.content) == (503, expected)
        assert state_path.read_bytes() == before_bytes and old not in saved.text
        assert not list(state_path.parent.glob('.state-*'))
        restart = ('start refused' if failure == 'refused and no restart' else 'start', 'DUMMY-user')
        assert journal.events == ([('stop refused',), restart] if failure == 'stop' else
                                  [('stop', old, 'DUMMY-user'), ('write', 'stopped'), restart])
        lines = warnings_of(log_scan)
        assert len(lines) == 1 and B[:8] in lines[0] and B not in lines[0], lines
        cause = 'its child could not be stopped' if failure == 'stop' else 'the new state could not be written'
        came_back = failure != 'refused and no restart'
        assert lines[0] == (WARNING_PREFIX + B[:8] + ' was not saved: ' + cause + '; '
                            + (RELAUNCHED if came_back else NOT_RELAUNCHED)), lines
        if came_back:
            assert await opened_by(runtime, old, children.by_port[PORTS[B]])
        else:
            async with runtime.admin(B) as admin:
                configuration = (await admin.get('/api/configuration', headers=ADMIN)).json()['configuration']
            assert (configuration['apply_state'], configuration['last_error_code']) == ('failed', 'child_start_failed')
            assert await opened_by(runtime, old, children.by_port[PORTS[B]]) is False
            assert await refused_everywhere(runtime, old) is False  # still B's token: the gateway's own answers


def directory_sync_refused(monkeypatch, directory):
    """fsync(2) of directory fails (EIO): Store._write has replaced state.json by then (a new inode at its name), but
    cannot tell that the rename is on disk."""
    real_fsync = config_module.os.fsync
    identity = (directory.stat().st_dev, directory.stat().st_ino)

    def refusing(fd):
        info = config_module.os.fstat(fd)
        if stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == identity:
            raise OSError(errno.EIO, 'HM-12 test: the directory cannot be synced')
        return real_fsync(fd)
    monkeypatch.setattr(config_module.os, 'fsync', refusing)


def replace_refused(monkeypatch, state_path):
    """os.replace onto state_path fails (EIO): an error the store cannot read as \"nothing changed\"."""
    real_replace = config_module.os.replace

    def refusing(source, target, *args, **kwargs):
        if Path(target) == state_path:
            raise OSError(errno.EIO, 'HM-12 test: the state file cannot be replaced')
        return real_replace(source, target, *args, **kwargs)
    monkeypatch.setattr(config_module.os, 'replace', refusing)


@pytest.mark.parametrize('stage', ['replace', 'directory sync'])
async def test_a_write_whose_outcome_is_unknown_leaves_the_profile_closed_until_the_add_on_restarts(
        tmp_path, log_scan, monkeypatch, stage):
    """The write fails once the state file is being replaced (os.replace itself, or the fsync of the directory after
    it): whether the new state is on disk is unknown, so the store is poisoned as every such failure leaves it today
    (fail closed), today's 503 state unavailable is the answer, and the old child is NOT relaunched (a new token may be
    on disk: no child runs on the old credentials then; UC-21). B is closed to both tokens until the add-on restarts:
    replace (nothing renamed, B's routing digest is the old one): the old token gets B's 503; directory sync (B's state
    file is another one now, which the dispatcher cannot read through the poisoned store): B is not routed, both tokens
    are unknown (401, 404). One WARNING (B's id's first 8 characters). Once the add-on restarts, what is on disk is
    served, its token and its identity together: the old ones (replace) or the new ones (directory sync)."""
    data, children = setup(tmp_path)
    journal = Journal()
    record_writes(monkeypatch, journal)
    state_path = directory(data, B) / 'state.json'
    with pytest.MonkeyPatch.context() as disk:
        async with multi_profile_runtime(PRODUCT, data, children=children,
                                         supervisor=journal.supervisor()) as runtime:
            await settle(runtime, 'configured')
            watch(log_scan, data)
            journal.watch(data, B, runtime.manager.get(B).runtime.supervisor)
            old = runtime.token(B)
            if stage == 'replace':
                replace_refused(disk, state_path)
            else:
                directory_sync_refused(disk, state_path.parent)
            saved = await save(runtime, B, 'backend/patch', {'changes': {'username': REBOUND['username']}})
            assert (saved.status_code, saved.content) == (503, b'{"error":"state unavailable"}')
            assert old not in saved.text
            assert journal.events == [('stop', old, 'DUMMY-user'), ('write', 'stopped')]
            stopped = runtime.manager.get(B).runtime.supervisor
            # stopped and its spec dropped (ProfileRuntime.stop_child): nothing starts it again on the old credentials
            assert stopped.status == 'stopped' and stopped.spec is None
            on_disk = stored(directory(data, B))
            assert (on_disk['connection']['username'] == REBOUND['username']) is (stage == 'directory sync')
            new = on_disk['token']
            log_scan.watch(new)
            lines = warnings_of(log_scan)
            assert lines == [WARNING_PREFIX + B[:8] + UNKNOWN], lines
            if stage == 'replace':
                assert new == old
                async with runtime.mcp() as client:
                    for path, headers in paths(old):
                        closed = await client.post(path, headers=headers, json=initialize_message())
                        assert (closed.status_code, closed.content) == (503, b'{"error":"state unavailable"}')
            else:
                assert new != old
                assert await refused_everywhere(runtime, old) and await refused_everywhere(runtime, new)
            assert ('start', REBOUND['username']) not in journal.events
    # the disk works again; the add-on restarts and reads what is on disk
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        assert runtime.token(B) == new
        username = stored(directory(data, B))['connection']['username']
        assert username == ('DUMMY-user' if stage == 'replace' else REBOUND['username'])
        assert runtime.manager.get(B).runtime.supervisor.spec.env['ODOO_USERNAME'] == username
        assert await opened_by(runtime, new, children.by_port[PORTS[B]])
        if new != old:
            assert await refused_everywhere(runtime, old)


def cleanup_refused(monkeypatch, directory):
    """Removing the temporary state file fails (EROFS: the file system went read-only) once state.json is replaced and
    the directory synced: Store._write raises that OSError from its cleanup, not its own ConfigError, and the store
    stays usable with the new state on disk (no poisoning: the rename and its sync succeeded)."""
    real_unlink = Path.unlink

    def refusing(path, *args, **kwargs):
        if Path(path).parent == directory and Path(path).name.startswith('.state-'):
            raise OSError(errno.EROFS, 'HM-12 test: the file system is read-only now')
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', refusing)


async def test_a_write_that_raises_with_its_new_token_on_disk_never_relaunches_the_old_child(tmp_path, log_scan,
                                                                                             monkeypatch):
    """The write raises although its new state reached the disk and the store is still usable (its cleanup failed
    after the rename): what is on disk decides, not what was raised (HM-12 review S-5). A new token is on disk, so the
    old child is not relaunched (no child runs on the old credentials while a new token exists: UC-21); the answer is
    today's fixed 503 state unavailable and one WARNING says the outcome is unknown. Until the add-on restarts the old
    token is refused on both paths and the new one gets the gateway's own answers, reaching no child; once it
    restarts, the new token and the new identity are served together."""
    data, children = setup(tmp_path)
    journal = Journal()
    record_writes(monkeypatch, journal)
    state_path = directory(data, B) / 'state.json'
    with pytest.MonkeyPatch.context() as disk:
        async with multi_profile_runtime(PRODUCT, data, children=children,
                                         supervisor=journal.supervisor()) as runtime:
            await settle(runtime, 'configured')
            watch(log_scan, data)
            journal.watch(data, B, runtime.manager.get(B).runtime.supervisor)
            old = runtime.token(B)
            cleanup_refused(disk, state_path.parent)
            saved = await save(runtime, B, 'backend/patch', {'changes': {'username': REBOUND['username']}})
            new = runtime.token(B)
            log_scan.watch(new)
            assert (saved.status_code, saved.content) == (503, b'{"error":"state unavailable"}')
            assert new != old and stored(directory(data, B))['connection']['username'] == REBOUND['username']
            assert journal.events == [('stop', old, 'DUMMY-user'), ('write', 'stopped')]
            stopped = runtime.manager.get(B).runtime.supervisor
            assert stopped.status == 'stopped' and stopped.spec is None
            assert warnings_of(log_scan) == [WARNING_PREFIX + B[:8] + UNKNOWN]
            assert await refused_everywhere(runtime, old)
            reached = len(children.by_port[PORTS[B]].requests)
            async with runtime.mcp() as client:
                local = await client.post('/mcp', headers=bearer(new), json=initialize_message())
            assert local.status_code == 200 and local.headers['mcp-session-id'].startswith('woow-local-')
            assert len(children.by_port[PORTS[B]].requests) == reached, 'a request reached a stopped child'
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        assert runtime.token(B) == new
        assert runtime.manager.get(B).runtime.supervisor.spec.env['ODOO_USERNAME'] == REBOUND['username']
        assert await opened_by(runtime, new, children.by_port[PORTS[B]])
        assert await refused_everywhere(runtime, old)


@pytest.mark.parametrize('stage', ['replace', 'directory sync'])
async def test_the_default_profiles_write_of_unknown_outcome_closes_what_reads_its_state(tmp_path, log_scan,
                                                                                         monkeypatch, stage):
    """The default profile's identity write fails once its state file is being replaced (HM-12 review S-2; contract
    2.3, 3.1). replace (its state file is the old one, so the dispatcher's digest of it holds): only the default
    profile is closed (its old token 503 on both paths) and B is served as before. directory sync (another state file
    at its name now, which the dispatcher must read to route any token and cannot through the poisoned store): every
    request that names a token gets 503 state unavailable on both paths, B's included, as when the default state
    cannot be read today. Its child is not relaunched; one WARNING ('default'). Once the add-on restarts, what is on
    disk is served and B is served again."""
    data, children = setup(tmp_path)
    journal = Journal()
    record_writes(monkeypatch, journal)
    state_path = data / 'state.json'
    with pytest.MonkeyPatch.context() as disk:
        async with multi_profile_runtime(PRODUCT, data, children=children,
                                         supervisor=journal.supervisor()) as runtime:
            await settle(runtime, 'configured')
            watch(log_scan, data)
            journal.watch(data, 'default', runtime.manager.get('default').runtime.supervisor)
            old, other = runtime.token('default'), runtime.token(B)
            if stage == 'replace':
                replace_refused(disk, state_path)
            else:
                directory_sync_refused(disk, data)
            saved = await save(runtime, 'default', 'backend/patch', {'changes': {'username': REBOUND['username']}})
            new = stored(data)['token']
            log_scan.watch(new)
            assert (saved.status_code, saved.content) == (503, b'{"error":"state unavailable"}')
            assert (new == old) is (stage == 'replace')
            assert journal.events == [('stop', old, 'DUMMY-user'), ('write', 'stopped')]
            assert warnings_of(log_scan) == [WARNING_PREFIX + 'default' + UNKNOWN]
            closed = [old] if stage == 'replace' else [old, new, other]
            async with runtime.mcp() as client:
                for token in closed:
                    for path, headers in paths(token):
                        reply = await client.post(path, headers=headers, json=initialize_message())
                        assert (reply.status_code, reply.content) == (503, b'{"error":"state unavailable"}')
            if stage == 'replace':
                assert await opened_by(runtime, other, children.by_port[PORTS[B]])
            assert ('start', REBOUND['username']) not in journal.events
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        assert runtime.token('default') == new
        assert stored(data)['connection']['username'] == ('DUMMY-user' if stage == 'replace' else REBOUND['username'])
        assert await opened_by(runtime, new, children.by_port[3000])
        assert await opened_by(runtime, other, children.by_port[PORTS[B]])


async def test_make_apps_takes_a_child_stop_it_can_call(tmp_path):
    """make_apps' stop_child (HM-12): keyword-only, None by default (no child of its own: nothing is stopped), and
    anything that cannot be called is refused before an app is made, as every other callable option is."""
    import inspect

    parameter = inspect.signature(make_apps).parameters['stop_child']
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default is None

    async def stop():
        pass
    with closing(ProductStore(tmp_path / 'store', PRODUCT)) as store:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as child:
            for wrong in (object(), 'stop', 3):
                with pytest.raises(ValueError, match='invalid child stop'):
                    make_apps(store, TOOLS[PRODUCT], child, stop_child=wrong)
            make_apps(store, TOOLS[PRODUCT], child, stop_child=stop)


STORE_CONNECTION = {'url': 'https://store.odoo.invalid', 'database': 'DUMMY-db', 'username': 'DUMMY-user',
                    'password': 'DUMMY-store-odoo-password'}


@pytest.mark.parametrize('stage', [None, 'new file', 'replace', 'directory sync'])
def test_the_store_writes_the_identity_and_its_token_at_once_and_fails_closed_only_when_unsure(tmp_path, log_scan,
                                                                                                stage):
    """ProductStore.rebind (PaaS test_bound_connection_rotation_is_atomic_and_preserves_password_changes, the store's
    half): the new connection, the new token and one history entry (rotate, the old token masked; the password kept)
    in one replace of the state file. The new file cannot be written: ConfigError, the file's bytes and the store as
    they were, still usable (PaaS: the old token stays); every other write (Store.update, switched on or off) still
    fails closed on the same failure, as today. The replace itself or the directory sync after it fails: ConfigError
    and a poisoned store; reopened, the store holds what is on disk, token and identity together. A revoked token or
    the same token is no rebind."""
    with closing(ProductStore(tmp_path / 'store', PRODUCT)) as store, pytest.MonkeyPatch.context() as disk:
        store.update(connection=STORE_CONNECTION)
        before = store.load()
        log_scan.watch_state(before)
        raw, new = store.path.read_bytes(), secrets.token_urlsafe(32)
        log_scan.watch(new)
        changes = {'connection': {**STORE_CONNECTION, 'username': REBOUND['username']}}
        replaced = count_writes(disk, store.path)
        if stage is None:
            updated = store.rebind(changes, new)
            assert len(replaced) == 1 and store.load() == updated
            assert (updated.token, updated.child_token) == (new, before.child_token)
            assert updated.connection.model_dump() == {**STORE_CONNECTION, 'username': REBOUND['username']}
            entry, = updated.token_history
            assert (entry.action, entry.previous_token_masked) == ('rotate', masked_token(before.token))
            for token in (None, new):
                with pytest.raises(ValueError):
                    store.rebind(changes, token)
            store.change_token(None, action='revoke')
            with pytest.raises(ValueError):
                store.rebind(changes, secrets.token_urlsafe(32))
            return
        if stage == 'new file':
            disk_full(disk, store.directory)
            with pytest.raises(ConfigError):
                store.rebind(changes, new)
            assert store.path.read_bytes() == raw and store.load() == before and not replaced
            with pytest.raises(ConfigError):
                store.update(writes_enabled=not before.writes_enabled)  # any other write: today's rule
            with pytest.raises(ConfigError):
                store.load()
            return
        (replace_refused(disk, store.path) if stage == 'replace' else directory_sync_refused(disk, store.directory))
        with pytest.raises(ConfigError):
            store.rebind(changes, new)
        with pytest.raises(ConfigError):
            store.load()
    with closing(ProductStore(tmp_path / 'store', PRODUCT)) as reopened:
        state = reopened.load()
        assert state.token == (before.token if stage == 'replace' else new)
        assert state.connection.username == ('DUMMY-user' if stage == 'replace' else REBOUND['username'])


async def test_a_new_child_that_cannot_start_leaves_the_new_token_and_never_the_old_child(tmp_path, log_scan,
                                                                                        monkeypatch):
    """The write and the token change are done when the new child does not start: 503 shape D (saved, the
    config_apply_failed code) with token_rotated: true, B's echo and the new state's ETag (the panel's restart sends
    it); the old token is refused on both paths, the old child is not started again (its credentials no longer serve
    anyone); the new token gets the gateway's own answers until the panel's restart starts the child on the new
    identity."""
    data, children = setup(tmp_path)
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        journal.watch(data, B, runtime.manager.get(B).runtime.supervisor)
        journal.refuse_start = 1
        old = runtime.token(B)
        saved = await save(runtime, B, 'backend/patch', {'changes': {'username': REBOUND['username']}})
        assert saved.status_code == 503, saved.text
        body = saved.json()
        assert list(body) == ['saved', 'token_rotated', 'detail', 'configuration', 'profile']
        assert (body['saved'], body['token_rotated'], body['detail']) == (True, True, {'code': 'config_apply_failed'})
        new = runtime.token(B)
        log_scan.watch(new)
        assert new != old and journal.events == [('stop', old, 'DUMMY-user'), ('write', 'stopped'), ('publish',),
                                                 ('start refused', REBOUND['username'])]
        assert saved.headers['etag'] == await next_etag(runtime, B)
        assert await refused_everywhere(runtime, old)
        reached = len(children.by_port[PORTS[B]].requests)
        async with runtime.mcp() as client:
            local = await client.post('/mcp', headers=bearer(new), json=initialize_message())
        assert local.status_code == 200 and local.headers['mcp-session-id'].startswith('woow-local-')
        assert len(children.by_port[PORTS[B]].requests) == reached, 'a request reached the port of a stopped child'
        async with runtime.admin(B) as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            restarted = await admin.post('/api/child/restart', headers=reviewed_headers(boot, ADMIN))
        assert restarted.status_code == 202, restarted.text
        assert journal.events[-1] == ('start', REBOUND['username'])
        assert ('start', 'DUMMY-user') not in journal.events
        assert await opened_by(runtime, new, children.by_port[PORTS[B]])


# ---- the new token never reaches the old child (UC-21); requests of the old token end (HM-08, HM-14) ----

async def test_the_new_token_reaches_no_child_before_the_new_one_and_the_old_tokens_requests_end(tmp_path, log_scan,
                                                                                              monkeypatch):
    """B's two forwarding slots are held by calls of the old token and a third waits in B's queue (HM-14) when B's
    username is saved anew. The new child's start is held: by then the old child has stopped and the new token is
    published; the held calls end (401) and the waiting one is refused (401) without ever reaching the child, the old
    token is refused on both paths, and the new token reaches no child at all: its initialize is the gateway's own
    answer (no child runs). Once the new child starts, the new token opens a session with it."""
    quota(monkeypatch, forward_slots=2, forward_wait_seconds=30, queue=4)
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    create_profile(data, PRODUCT, B, label=LABELS[B], port=PORTS[B])
    children = Children()
    children.add(3000, GatewayChild('default', PRODUCT, data))
    child = children.add(PORTS[B], GatewayChild('p' + B[:4], PRODUCT, directory(data, B)))
    child.hold_calls = True
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        journal.watch(data, B, runtime.manager.get(B).runtime.supervisor)
        old = runtime.token(B)
        lanes = runtime.manager.get(B).runtime.mcp_app.state.lanes
        async with runtime.mcp() as client:
            init = await client.post('/mcp', headers=bearer(old), json=initialize_message())
            in_session = {**bearer(old), 'Content-Type': 'application/json',
                          'Mcp-Session-Id': init.headers['mcp-session-id']}
            held = [asyncio.create_task(client.post('/mcp', headers=in_session, json=call(100 + n))) for n in range(2)]
            await until(lambda: child.waiting == 2)
            queued = asyncio.create_task(client.post('/mcp', headers=in_session, json=call(200)))
            await until(lambda: lanes['ordinary'].waiting == 1)
            gate = journal.hold_start = asyncio.Event()
            saving = asyncio.create_task(save(runtime, B, 'backend/patch', {'changes': {'username':
                                                                                         REBOUND['username']}}))
            await until(lambda: ('start waits',) in journal.events)
            new = runtime.token(B)
            log_scan.watch(new)
            assert journal.events == [('stop', old, 'DUMMY-user'), ('write', 'stopped'), ('publish',),
                                      ('start waits',)]
            ended = await asyncio.wait_for(asyncio.gather(*held, queued), 10)
            assert [response.status_code for response in ended] == [401, 401, 401]
            assert child.client_calls() == [100, 101]  # the waiting call never reached a child
            assert await refused_everywhere(runtime, old)
            seen = len(child.seen)
            local = await client.post('/mcp', headers=bearer(new), json=initialize_message())
            assert local.status_code == 200 and local.headers['mcp-session-id'].startswith('woow-local-')
            assert len(child.seen) == seen, 'the new token reached a child before the new one started'
            gate.set()
            saved = await asyncio.wait_for(saving, 10)
            assert saved.status_code == 200 and saved.json()['token_rotated'] is True, saved.text
            assert journal.events[-1] == ('start', REBOUND['username'])
            opened = await client.post('/mcp', headers=bearer(new), json=initialize_message())
            assert opened.status_code == 200 and opened.headers['mcp-session-id'] in child.sessions
            child.free.set()


# ---- switched off: today's answer, today's order, the same token (plan 3.3) ----

async def test_switched_off_an_identity_change_keeps_todays_answer_order_and_token(tmp_path, log_scan):
    """A product not switched on keeps today's behaviour for its only profile: a changed username (backend/patch) and
    a changed url (PUT backend, the password kept) are written first, then the child restarts (the state on disk
    already holds the new username when the child stops); the answer is {"saved", "configuration"}, the token and its
    history are unchanged and still served, and a new origin without the password is saved as today (DQ-40 ⑨ is
    behind the switch too)."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    journal = Journal()
    async with production_runtime(PRODUCT, data, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        assert not features.enabled(PRODUCT)
        watch(log_scan, data)
        journal.watch(data, 'default')
        token = stored(data)['token']
        async with runtime.admin() as admin:
            def whole(url):  # made when it is sent: the whole connection saved by then, another url
                return {'connection': {**stored(data)['connection'], 'url': url}}
            for route, body in (('backend/patch', lambda: {'changes': {'username': REBOUND['username']}}),
                                ('backend', lambda: whole(REBOUND['url'])),
                                ('backend/patch', lambda: {'changes': {'url': 'https://moved.odoo.invalid'}})):
                body = body()
                boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
                saved = await admin.put('/api/' + route, json=body, headers=reviewed_headers(boot, ADMIN))
                assert saved.status_code == 200, saved.text
                assert list(saved.json()) == ['saved', 'configuration'] and saved.json()['saved'] is True
        state = stored(data)
        assert state['token'] == token and 'token_history' not in state
        assert (state['connection']['url'], state['connection']['username']) == (
            'https://moved.odoo.invalid', REBOUND['username'])
        assert journal.events == [('stop', token, REBOUND['username']), ('start', REBOUND['username'])] * 3
        async with runtime.mcp() as client:
            for path, headers in paths(token):
                assert (await client.post(path, headers=headers, json=initialize_message())).status_code == 200


# ---- the other products keep their token, switched on (Nextcloud: HM-22; Hermes: HM-24) ----

OTHERS = {
    'hermes': ({'gateway_url': 'https://hermes.invalid', 'gateway_api_key': 'DUMMY-rotation-hermes-key',
                'dashboard_url': 'https://hermes.invalid:9119', 'dashboard_username': 'DUMMY-user',
                'dashboard_password': 'DUMMY-rotation-dashboard-password'},
               {'dashboard_username': 'DUMMY-user-two', 'gateway_url': 'https://other-hermes.invalid',
                'gateway_api_key': 'DUMMY-rotation-hermes-key-two'}),
    'nextcloud': ({'url': 'https://nextcloud.invalid', 'username': 'DUMMY-user',
                   'app_password': 'DUMMY-rotation-nextcloud-password'},
                  {'username': 'DUMMY-user-two'}),
    'emqx': ({'url': 'https://emqx.invalid', 'api_key': 'DUMMY-rotation-emqx-key',
              'api_secret': 'DUMMY-rotation-emqx-secret'},
             {'url': 'https://other-emqx.invalid', 'api_key': 'DUMMY-rotation-emqx-key-two',
              'api_secret': 'DUMMY-rotation-emqx-secret-two'}),
    'litellm': ({'url': 'https://litellm.invalid', 'master_key': 'DUMMY-rotation-litellm-key'},
                {'url': 'https://other-litellm.invalid', 'master_key': 'DUMMY-rotation-litellm-key-two'}),
    'headscale': ({'url': 'https://headscale.invalid', 'api_key': 'DUMMY-rotation-headscale-key'},
                  {'url': 'https://other-headscale.invalid', 'api_key': 'DUMMY-rotation-headscale-key-two'}),
}


@pytest.mark.parametrize('product', sorted(OTHERS))
async def test_switched_on_the_other_products_keep_their_token_on_a_changed_backend(tmp_path, log_scan, monkeypatch,
                                                                                    product):
    """Only Odoo is bound to its identity in this slice: a switched-on Hermes, Nextcloud, EMQX, LiteLLM or Headscale
    backend saved with another account or server (its secrets brought) keeps its token and answers as today."""
    monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset({product}))
    saved_connection, changes = OTHERS[product]
    restarts = []

    async def administrator(user):
        return user == ADMIN['X-Remote-User-Id']

    async def restart(state):
        restarts.append(state)

    store = ProductStore(tmp_path / product, product)
    try:
        store.update(connection=saved_connection)
        log_scan.watch_state(store.load())
        log_scan.watch(*(value for name, value in changes.items() if 'key' in name or 'secret' in name), kind='secret')
        token = store.load().token
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as child:
            admin, _ = make_apps(store, TOOLS[product], child, verify_admin=administrator, backend_changed=restart)
            async with GENUINE_CLIENT(transport=httpx.ASGITransport(admin, client=INGRESS),
                                      base_url='http://admin') as client:
                boot = (await client.get('/api/bootstrap', headers=ADMIN)).json()
                saved = await client.put('/api/backend/patch', json={'changes': changes},
                                         headers=reviewed_headers(boot, ADMIN))
        assert saved.status_code == 200, saved.text
        assert list(saved.json()) == ['saved', 'configuration'] and len(restarts) == 1
        state = store.load()
        assert state.token == token and state.token_history is None
        assert all(getattr(state.connection, name) == value for name, value in changes.items())
    finally:
        store.close()
