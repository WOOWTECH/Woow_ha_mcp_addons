"""HM-24: Hermes once it is switched on (multi-profile plan 9 Hermes row, 12.3 HM-21～HM-26, 10.3; DQ-40 ⑩ (a); contract
3.1, section 9 #40, #63 and HM-24's rows #129～#131; FM-86, FM-153; acceptance T-03, T-05, T-07, T-12, T-19, T-23).

The repository switches no product on (features.MULTI_PROFILE_PRODUCTS stays empty until Hermes' own version-bump PR):
every switched-on case here switches Hermes on for the test only (tests/multi_profile_runtime.py), as the Odoo cases
do; the switched-off cases run the production runtime as it ships (tests/test_single_profile_golden.py).

- The MCP token is bound to one backend identity (DQ-40 ⑩ (a); products.IDENTITY_BOUND and the panel's contracts.js
  identityBound): once switched on, a save that changes gateway_url, dashboard_url or dashboard_username rotates the
  token in HM-12's order (the old child stopped, one write of the connection, the new token and a rotate history entry,
  the change published, the new child started). Adding the Dashboard to a Gateway-only connection and clearing it are
  changes too (its three fields go together: HermesConnection.dashboard_complete), as clearing Odoo's connection is
  (HM-12). A secret alone (gateway_api_key, dashboard_password), the first setup and a revoked token keep the token as
  today. Switched off, every save is today's.
- Each profile's child is its own: the launcher's --port (the default profile's child keeps today's argv, port 3000),
  its own environment (its Gateway and Dashboard values, nothing of another profile's) and its own directory (HOME).
- The bearer 401 / secret URL 404 matrix across profiles, switched on and off (switched off: a dormant profile's token).
- A long hermes_chat (the gateway allows a tools/call CALL_SECONDS, 330 s) holds one of its own profile's forwarding
  slots and none of another profile's: with all of them held, that profile answers busy and the others do not wait.
  An identity change ends its own profile's long chats only (T-12).
- Saving one profile's policy changes that profile's tools only and restarts no child (the gateway enforces Hermes'
  policy; its child takes none at launch), switched on and off (T-07).
- Real children (the real Supervisor, apps/hermes's launcher in its pinned venv, one local fake Hermes for both
  profiles): each child logs in to the one Dashboard once with its own account and keeps its own cookie, in its memory
  only (PaaS apps/hermes/tests/test_dashboard_profile_cache.py test_dashboard_health_cookie_follows_profile,
  woow-mcp-server 69ac425: here the cache follows the child, one per profile); every profile pointed at one Dashboard
  logs in from the add-on's one address, so the Dashboard's login limit is shared (contract section 9); a long chat of
  one profile holds up neither another profile's chat nor its own child's other calls; each child serves its own child
  bearer only (T-23); a Dashboard user saved anew rotates the token and the new child logs in as the new user.

Every case runs under the HM-01 log scan (tokens, child tokens, Gateway keys, Dashboard passwords and labels watched).
Test data follows tests/fixtures/owner_defaults/README.md (.invalid hosts, DUMMY- credentials, T or C x43 tokens).
"""
import asyncio
from contextlib import closing, contextmanager
import json
from pathlib import Path
import re
import threading

import pytest

import loopback_backends
from admin_write_headers import reviewed_headers
from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import (Children, all_tokens, create_profile, free_port, ids, multi_profile_runtime, stored,
                                   update_profile)
from mcp_admin_core import features, gateway, identity_fields, products, profile_router, profiles
from mcp_admin_core.access import masked_token
from mcp_admin_core.products import ProductStore, child_spec
from switched_gateway import GatewayChild, session_of, until
from test_odoo_identity_rotation import (Journal as OdooJournal, count_writes, next_etag, opened_by, record_writes,
                                         refused_everywhere, routed_to, save)
from test_profile_quotas import busy
from test_single_profile_golden import (ACCEPT, ADMIN, GENUINE_CLIENT, NoProcessSupervisor, initialize_message,
                                        production_runtime, settle)
from test_six_hardening import Quiet, serve

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'hermes'
B, C = ids(2)
LABELS = {B: 'Beta Desk', C: 'Gamma Desk'}
PORTS = {B: 18000, C: 18001}
NAMES = {'default': 'alpha', B: 'beta', C: 'gamma'}
# What a test saves anew (tests/fixtures/owner_defaults/README.md rules)
REBOUND_GATEWAY = 'https://rebound.hermes.invalid'
MOVED_DASHBOARD = 'https://beta.hermes.invalid:9120'  # B's Dashboard on another port: another origin
NEW_USER = 'DUMMY-user-beta-two'
NEW_KEY = 'DUMMY-hm24-rebound-gateway-key'
NEW_PASSWORD = 'DUMMY-hm24-rebound-dashboard-password'
# The child's environment variable of each connection field (products.child_spec)
SPEC_NAMES = {'gateway_url': 'HERMES_GATEWAY_URL', 'gateway_api_key': 'HERMES_GATEWAY_API_KEY',
              'dashboard_url': 'HERMES_DASHBOARD_URL', 'dashboard_username': 'HERMES_DASHBOARD_USERNAME',
              'dashboard_password': 'HERMES_DASHBOARD_PASSWORD'}
DASHBOARD = ('dashboard_url', 'dashboard_username', 'dashboard_password')


@pytest.fixture(autouse=True)
def memory_readings(monkeypatch):
    """The memory readings are the test's (no cgroup limit, 4 GiB available): a save of an additional profile starts
    its child whatever the host has (contract 5's check is HM-09's tests)."""
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: None)
    monkeypatch.setattr(profiles, 'available_memory_mib', lambda: 4096)


def hermes(name, *, dashboard=True):
    """name's own synthetic Hermes: its Gateway and, unless dashboard is False, its Dashboard on another port of the
    same host, with an account of its own."""
    value = {'gateway_url': f'https://{name}.hermes.invalid', 'gateway_api_key': f'DUMMY-{name}-gateway-key'}
    if dashboard:
        value.update(dashboard_url=f'https://{name}.hermes.invalid:9119', dashboard_username=f'DUMMY-user-{name}',
                     dashboard_password=f'DUMMY-{name}-dashboard-password')
    return value


def identity(connection):
    """The backend identity a saved Hermes connection names (DQ-40 ⑩): its Gateway URL, its Dashboard URL and user."""
    if connection is None:
        return None
    return tuple(connection.get(name) for name in identity_fields.rotating_fields(PRODUCT))


def spec_connection(env):
    """The connection a child's environment carries, by field name (None: not given to the child)."""
    return {name: env.get(variable) for name, variable in SPEC_NAMES.items()}


def directory(data, profile_id):
    return Path(data) if profile_id == 'default' else profiles.Layout(Path(data)).profile(profile_id)


def setup(tmp_path, extras=(B,), connections=None, child=GatewayChild):
    """The default profile and the additional profiles extras (on their PORTS), each with its own Hermes (connections:
    {profile id: connection, or None for none}; left out, hermes(its name)), and every profile's child behind one
    MockTransport."""
    data = tmp_path / 'data'
    chosen = {profile_id: hermes(NAMES[profile_id]) for profile_id in ('default', *extras)} | (connections or {})
    update_profile(data, PRODUCT, 'default', connection=chosen['default'])
    children = Children()
    children.add(3000, child('default', PRODUCT, data))
    for profile_id in extras:
        create_profile(data, PRODUCT, profile_id, label=LABELS[profile_id], port=PORTS[profile_id], configured=False)
        if chosen[profile_id] is not None:
            update_profile(data, PRODUCT, profile_id, connection=chosen[profile_id])
        children.add(PORTS[profile_id], child(NAMES[profile_id], PRODUCT, directory(data, profile_id)))
    return data, children


def watch(log_scan, data):
    """Every token, child token, Gateway key and Dashboard password stored under data, the values tests save anew and
    every label (the log scan's needles); a test watches a token made later (a rotation's) once it exists."""
    log_scan.watch(*all_tokens(data))
    secrets_ = identity_fields.fields(PRODUCT, identity_fields.SECRET)
    for path in [Path(data) / 'state.json', *sorted((Path(data) / 'profiles').glob('*/state.json'))]:
        connection = json.loads(path.read_text()).get('connection') or {}
        log_scan.watch(*(connection[name] for name in secrets_ if connection.get(name)), kind='secret')
    log_scan.watch(NEW_KEY, NEW_PASSWORD, kind='secret')
    log_scan.watch(*LABELS.values(), kind='name')


def bearer(token):
    return {**ACCEPT, 'Authorization': 'Bearer ' + token}


def chat(ident, message='hello'):
    return {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
            'params': {'name': 'hermes_chat', 'arguments': {'message': message}}}


class Journal(OdooJournal):
    """test_odoo_identity_rotation.Journal with Hermes' identity in its events: each effective stop of the profile's
    child (the token on disk and the identity its state held then), each identity write and published token change
    (record_writes) and each start (the identity its spec carries)."""

    def supervisor(self):
        journal = self

        class Recorded(NoProcessSupervisor):
            def _start_child(self):
                if journal.mine(self) and self.spec is not None:
                    journal.events.append(('start', identity(spec_connection(self.spec.env))))
                super()._start_child()

            async def _stop_child(self):
                if journal.mine(self) and self.status in ('running', 'starting'):
                    on_disk = stored(journal.directory)
                    journal.events.append(('stop', on_disk['token'], identity(on_disk['connection'])))
                await super()._stop_child()
        return Recorded


def spec_of(runtime, profile_id):
    return runtime.manager.get(profile_id).runtime.supervisor.spec


# ---- the binding: products.IDENTITY_BOUND and the panel's identityBound (DQ-40 ⑩ (a)) ----

def test_hermes_is_bound_to_its_gateway_and_dashboard_identity():
    """Hermes is in products.IDENTITY_BOUND (the panel's identityBound is the same list: tests/test_identity_fields.py),
    with HM-07's rotating fields: the Gateway URL and the Dashboard's URL and user, never a secret. Nothing is switched
    on in the repository: the binding acts once Hermes' own version-bump PR switches it on."""
    assert PRODUCT in products.IDENTITY_BOUND
    assert identity_fields.rotating_fields(PRODUCT) == ('gateway_url', 'dashboard_url', 'dashboard_username')
    assert not set(identity_fields.rotating_fields(PRODUCT)) & set(identity_fields.fields(PRODUCT,
                                                                                          identity_fields.SECRET))
    assert not features.enabled(PRODUCT)


# ---- a changed identity rotates the token (HM-12's order; PaaS rotates only Odoo's and Nextcloud's) ----

CASES = [
    ('gateway_url', 'backend', {'gateway_url': REBOUND_GATEWAY}),
    ('gateway_url', 'backend/patch', {'gateway_url': REBOUND_GATEWAY, 'gateway_api_key': NEW_KEY}),
    ('gateway_url path', 'backend/patch', {'gateway_url': 'https://beta.hermes.invalid/hermes'}),
    ('dashboard_url', 'backend', {'dashboard_url': MOVED_DASHBOARD}),
    ('dashboard_url', 'backend/patch', {'dashboard_url': MOVED_DASHBOARD, 'dashboard_password': NEW_PASSWORD}),
    ('dashboard_username', 'backend', {'dashboard_username': NEW_USER}),
    ('dashboard_username', 'backend/patch', {'dashboard_username': NEW_USER}),
]


def body(route, connection, changes):
    """A save of changes: the whole connection (PUT backend) or the fields alone (backend/patch)."""
    return {'connection': {**connection, **changes}} if route == 'backend' else {'changes': changes}


@pytest.mark.parametrize('case, route, changes', CASES, ids=[f'{case}-{route}' for case, route, _ in CASES])
async def test_a_changed_hermes_identity_stops_the_old_child_then_rotates_the_token_in_one_write(
        tmp_path, log_scan, monkeypatch, case, route, changes):
    """B's Gateway URL, Dashboard URL or Dashboard user saved anew (a URL on another origin brings the secret it takes
    there, DQ-40 ⑨; a path on the same origin needs none): the old child stops while the old token is still the one on
    disk, the write comes with no child running, then the token change is published, then the new child starts with
    the new connection. 200 {"saved", "token_rotated": true, "configuration"} with B's echo, no token, and the new
    state's ETag. One write of the state file holds the new connection, a new 43-character token and one rotate
    history entry (the old token masked); the child token stays. The dispatcher routes the old token to no profile and
    the new one to B; the old token is refused on both paths, the new one opens a session with B's child on both; the
    default profile's state and token are untouched."""
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
        replaced.clear()
        saved = await save(runtime, B, route, body(route, before['connection'], changes))
        assert saved.status_code == 200, saved.text
        assert len(replaced) == 1, 'the connection, the token and its history are one write'
        answer = saved.json()
        assert list(answer) == ['saved', 'token_rotated', 'configuration', 'profile']
        assert (answer['saved'], answer['token_rotated'], answer['profile']) == (True, True, {'id': B})
        after = stored(directory(data, B))
        new = after['token']
        log_scan.watch(new)
        assert new not in (None, old) and len(new) == 43 and new not in saved.text and old not in saved.text
        assert after['child_token'] == before['child_token']
        assert after['connection'] == {**before['connection'], **changes}
        [entry] = after['token_history']
        assert (entry['action'], entry['previous_token_masked']) == ('rotate', masked_token(old))
        assert journal.events == [('stop', old, identity(before['connection'])), ('write', 'stopped'), ('publish',),
                                  ('start', identity(after['connection']))]
        assert spec_connection(spec_of(runtime, B).env) == after['connection']
        assert saved.headers['etag'] == await next_etag(runtime, B)
        assert routed_to(runtime, old) == [] and routed_to(runtime, new) == [B]
        assert await refused_everywhere(runtime, old)
        assert await opened_by(runtime, new, children.by_port[PORTS[B]])
        assert (data / 'state.json').read_bytes() == default_state
        assert await opened_by(runtime, runtime.token('default'), children.by_port[3000])


async def test_adding_or_clearing_the_dashboard_rotates_the_token(tmp_path, log_scan, monkeypatch):
    """B has a Gateway only. Adding the Dashboard (its three fields) binds the token to another identity: rotated, and
    the new child gets the Dashboard. A partial clear is refused before anything stops (400 request denied: the three
    Dashboard fields go together, HermesConnection.dashboard_complete). Clearing the Dashboard (all three null) rotates
    the token again and the new child has none; clearing the connection rotates it a third time and starts no child
    (none is configured; the new token gets the gateway's own answers). The history keeps the three rotations, newest
    first, and every old token is refused on both paths (PaaS: a cleared identity field is a change, patch_connection_
    bound; the Odoo rule of HM-12, applied to Hermes' optional Dashboard)."""
    data, children = setup(tmp_path, connections={B: hermes('beta', dashboard=False)})
    dashboard = {name: value for name, value in hermes('beta').items() if name in DASHBOARD}
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        log_scan.watch(dashboard['dashboard_password'], kind='secret')
        journal.watch(data, B, runtime.manager.get(B).runtime.supervisor)
        gateway_only = stored(directory(data, B))['connection']
        assert identity(gateway_only) == ('https://beta.hermes.invalid', None, None)
        tokens = [runtime.token(B)]

        added = await save(runtime, B, 'backend/patch', {'changes': dashboard})
        assert added.status_code == 200 and added.json()['token_rotated'] is True, added.text
        tokens.append(runtime.token(B))
        log_scan.watch(tokens[-1])
        with_dashboard = {**gateway_only, **dashboard}
        assert stored(directory(data, B))['connection'] == with_dashboard
        assert journal.events == [('stop', tokens[0], identity(gateway_only)), ('write', 'stopped'), ('publish',),
                                  ('start', identity(with_dashboard))]
        assert spec_connection(spec_of(runtime, B).env) == with_dashboard

        journal.events.clear()
        unchanged = (directory(data, B) / 'state.json').read_bytes()
        partial = await save(runtime, B, 'backend/patch', {'changes': {'dashboard_username': None}})
        assert (partial.status_code, partial.json()) == (400, {'error': 'request denied'})
        assert journal.events == [] and (directory(data, B) / 'state.json').read_bytes() == unchanged

        cleared = await save(runtime, B, 'backend/patch', {'changes': dict.fromkeys(DASHBOARD)})
        assert cleared.status_code == 200 and cleared.json()['token_rotated'] is True, cleared.text
        tokens.append(runtime.token(B))
        log_scan.watch(tokens[-1])
        assert stored(directory(data, B))['connection'] == gateway_only
        assert journal.events == [('stop', tokens[1], identity(with_dashboard)), ('write', 'stopped'), ('publish',),
                                  ('start', identity(gateway_only))]
        assert not {variable for variable in spec_of(runtime, B).env if variable.startswith('HERMES_DASHBOARD_')}

        journal.events.clear()
        gone = await save(runtime, B, 'backend', {'connection': None})
        assert gone.status_code == 200 and gone.json()['token_rotated'] is True, gone.text
        tokens.append(runtime.token(B))
        log_scan.watch(tokens[-1])
        assert stored(directory(data, B))['connection'] is None
        assert journal.events == [('stop', tokens[2], identity(gateway_only)), ('write', 'stopped'), ('publish',)]

        history = stored(directory(data, B))['token_history']
        assert [(entry['action'], entry['previous_token_masked']) for entry in history] == [
            ('rotate', masked_token(token)) for token in reversed(tokens[:3])]
        assert len(set(tokens)) == 4
        for old in tokens[:3]:
            assert await refused_everywhere(runtime, old)
        async with runtime.mcp() as client:
            local = await client.post('/mcp', headers=bearer(tokens[3]), json=initialize_message())
        assert local.status_code == 200 and local.headers['mcp-session-id'].startswith('woow-local-')


async def test_a_secret_change_or_the_first_setup_keeps_the_hermes_token(tmp_path, log_scan, monkeypatch):
    """B's first connection (it had none), then a new Gateway key alone, a new Dashboard password alone, the whole
    connection again with the same identity and the first secrets, and the same two URLs with a trailing slash (the
    saved values, once validated): every answer is today's (no token_rotated), the token B was born with stays, no
    history entry is written, and each save restarts the child after its write (today's order). A revoked token stays
    revoked through an identity change (no new token, no history entry beyond the revocation's)."""
    data, children = setup(tmp_path, connections={B: None})
    first = hermes('beta')
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        log_scan.watch(first['gateway_api_key'], first['dashboard_password'], kind='secret')
        journal.watch(data, B, runtime.manager.get(B).runtime.supervisor)
        token = runtime.token(B)
        assert stored(directory(data, B))['connection'] is None
        for route, saved_body in (('backend', {'connection': first}),
                                  ('backend/patch', {'changes': {'gateway_api_key': NEW_KEY}}),
                                  ('backend/patch', {'changes': {'dashboard_password': NEW_PASSWORD}}),
                                  ('backend', {'connection': dict(first)}),
                                  ('backend/patch', {'changes': {'gateway_url': first['gateway_url'] + '/',
                                                                 'dashboard_url': first['dashboard_url'] + '/'}})):
            saved = await save(runtime, B, route, saved_body)
            assert saved.status_code == 200, saved.text
            assert list(saved.json()) == ['saved', 'configuration', 'profile'], (route, saved_body)
        state = stored(directory(data, B))
        assert state['token'] == token and 'token_history' not in state
        assert state['connection'] == first
        kept = identity(first)
        assert journal.events == [('start', kept)] + [('stop', token, kept), ('start', kept)] * 4
        assert await opened_by(runtime, token, children.by_port[PORTS[B]])
        async with runtime.admin(B) as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            revoked = await admin.post('/api/token/revoke', headers=reviewed_headers(boot, ADMIN))
            assert revoked.status_code == 200, revoked.text
        saved = await save(runtime, B, 'backend/patch', {'changes': {'dashboard_username': NEW_USER}})
        assert saved.status_code == 200 and list(saved.json()) == ['saved', 'configuration', 'profile'], saved.text
        state = stored(directory(data, B))
        assert state['token'] is None and [entry['action'] for entry in state['token_history']] == ['revoke']
        assert state['connection']['dashboard_username'] == NEW_USER
        assert await refused_everywhere(runtime, token)


async def test_the_default_hermes_profile_is_bound_to_its_identity_too(tmp_path, log_scan, monkeypatch):
    """Switched on, the default profile is a profile like the others (plan 7.2): its Dashboard user saved anew rotates
    its token in the same order, the answer carrying its new ETag; its old token is refused on both paths and routed to
    no profile, the new one opens a session with its child; B's state and token stay as they were."""
    data, children = setup(tmp_path)
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        journal.watch(data, 'default', runtime.manager.get('default').runtime.supervisor)
        before = stored(data)
        old, extra_state = before['token'], (directory(data, B) / 'state.json').read_bytes()
        saved = await save(runtime, 'default', 'backend/patch', {'changes': {'dashboard_username': 'DUMMY-user-alpha2'}})
        assert saved.status_code == 200 and saved.json()['token_rotated'] is True, saved.text
        new = runtime.token('default')
        log_scan.watch(new)
        after = stored(data)
        assert new != old and journal.events == [('stop', old, identity(before['connection'])), ('write', 'stopped'),
                                                 ('publish',), ('start', identity(after['connection']))]
        assert saved.headers['etag'] == await next_etag(runtime, 'default')
        assert routed_to(runtime, old) == [] and routed_to(runtime, new) == ['default']
        assert await refused_everywhere(runtime, old)
        assert await opened_by(runtime, new, children.by_port[3000])
        assert (directory(data, B) / 'state.json').read_bytes() == extra_state
        assert await opened_by(runtime, runtime.token(B), children.by_port[PORTS[B]])


async def test_switched_off_a_hermes_identity_change_keeps_todays_answer_order_and_token(tmp_path, log_scan):
    """Hermes not switched on (as the repository ships it) keeps today's behaviour for its only profile although it is
    in IDENTITY_BOUND: a new Dashboard user (backend/patch), a new Gateway URL (PUT backend), a Dashboard URL on
    another origin without its password (saved as today: DQ-40 ⑨ is behind the switch too) and the Dashboard cleared
    are each written first, then the child restarts (the state on disk already holds the new identity when the child
    stops); every answer is {"saved", "configuration"}, the token and its history are unchanged and still served."""
    data = tmp_path / 'data'
    update_profile(data, PRODUCT, 'default', connection=hermes('alpha'))
    journal = Journal()
    async with production_runtime(PRODUCT, data, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        assert not features.enabled(PRODUCT) and PRODUCT in products.IDENTITY_BOUND
        watch(log_scan, data)
        journal.watch(data, 'default')
        token = stored(data)['token']
        saves = (('backend/patch', lambda: {'changes': {'dashboard_username': NEW_USER}}),
                 ('backend', lambda: {'connection': {**stored(data)['connection'], 'gateway_url': REBOUND_GATEWAY}}),
                 ('backend/patch', lambda: {'changes': {'dashboard_url': 'https://moved.hermes.invalid'}}),
                 ('backend/patch', lambda: {'changes': dict.fromkeys(DASHBOARD)}))
        identities = []
        async with runtime.admin() as admin:
            for route, made in saves:
                boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
                saved = await admin.put('/api/' + route, json=made(), headers=reviewed_headers(boot, ADMIN))
                assert saved.status_code == 200, saved.text
                assert list(saved.json()) == ['saved', 'configuration'] and saved.json()['saved'] is True
                identities.append(identity(stored(data)['connection']))
        state = stored(data)
        assert state['token'] == token and 'token_history' not in state
        assert identity(state['connection']) == (REBOUND_GATEWAY, None, None)
        assert journal.events == [event for saved in identities for event in (('stop', token, saved),
                                                                              ('start', saved))]
        async with runtime.mcp() as client:
            for path, headers in (('/mcp', bearer(token)), (f'/private_{token}/mcp', dict(ACCEPT))):
                assert (await client.post(path, headers=headers, json=initialize_message())).status_code == 200


# ---- every profile's own child: port, environment, directory ----

async def test_every_profiles_child_has_its_own_port_environment_and_directory(tmp_path, log_scan):
    """Switched on, each profile's child is started from its own state: the default profile's with today's argv (the
    launcher's default port 3000, no option), an additional profile's with --port and its index port (HM-04); each
    environment holds exactly the add-on's fixed variables, the profile's own child token, the switched-on loopback
    rule (HM-20) and the profile's own Hermes (a profile without a Dashboard gets no HERMES_DASHBOARD_*), and nothing of
    another profile's; HOME and the working directory are the profile's own empty child directory. No profile gets
    HERMES_MCP_CHAT_TIMEOUT: every child keeps the vendored 300 s chat limit, under the gateway's 330 s. Switched off,
    the default profile's spec is today's: the same but for the loopback variable."""
    data, children = setup(tmp_path, extras=(B, C), connections={C: hermes('gamma', dashboard=False)})
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        specs = {profile_id: spec_of(runtime, profile_id) for profile_id in ('default', B, C)}
    app = products.ROOT / 'apps' / PRODUCT
    launcher = (str(app / '.venv/bin/python'), str(app / 'launch.py'))
    assert specs['default'].argv == launcher
    assert specs[B].argv == (*launcher, '--port', str(PORTS[B]))
    assert specs[C].argv == (*launcher, '--port', str(PORTS[C]))
    own = {}
    for profile_id, spec in specs.items():
        state = stored(directory(data, profile_id))
        work = directory(data, profile_id) / 'child'
        assert spec.cwd == work and work.is_dir() and not any(work.iterdir())
        assert spec.env == {'PATH': '/usr/bin:/bin', 'HOME': str(work), 'PYTHONDONTWRITEBYTECODE': '1',
                            'PYTHONUNBUFFERED': '1',
                            'PYTHONPATH': str(app / 'vendor') + ':' + str(products.ROOT / 'apps/runtime'),
                            'WOOW_MCP_CHILD_TOKEN': state['child_token'], products.DENY_LOOPBACK_ENV: '1',
                            **{SPEC_NAMES[name]: value for name, value in state['connection'].items()
                               if value is not None}}, profile_id
        assert 'HERMES_MCP_CHAT_TIMEOUT' not in spec.env
        own[profile_id] = {state['token'], state['child_token'], str(work),
                           *(value for value in state['connection'].values() if value is not None)}
    assert not {name for name in specs[C].env if name.startswith('HERMES_DASHBOARD_')}
    for profile_id, spec in specs.items():
        others = set().union(*(values for other, values in own.items() if other != profile_id))
        assert not others & set(spec.env.values()), profile_id
    with closing(ProductStore(data, PRODUCT)) as store:
        today = child_spec(store.load(), store.directory)
    assert today.argv == specs['default'].argv and today.cwd == specs['default'].cwd
    assert {**today.env, products.DENY_LOOPBACK_ENV: '1'} == specs['default'].env


# ---- the bearer 401 / secret URL 404 matrix across profiles ----

async def test_each_profiles_token_reaches_only_its_own_child_and_every_other_token_is_refused(tmp_path, log_scan):
    """Switched on, three Hermes profiles (one without a Dashboard): each token opens a session with its own child on
    both paths. Then B's token is rotated away by an identity change and C's revoked: these two, a token no profile has
    (T x43), a child token used as an MCP token (the default profile's, and C x43) are each refused on both paths with
    an unknown token's bytes (Bearer 401, secret URL 404) and reach no child. The secret path never reads
    Authorization, and 8081 never reads X-MCP-Profile: the default profile's secret URL with B's token in Authorization
    reaches the default profile's child, B's Bearer token with X-MCP-Profile: default reaches B's."""
    data, children = setup(tmp_path, extras=(B, C), connections={C: hermes('gamma', dashboard=False)})
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        child = {'default': children.by_port[3000], B: children.by_port[PORTS[B]], C: children.by_port[PORTS[C]]}
        for profile_id in child:
            assert await opened_by(runtime, runtime.token(profile_id), child[profile_id]), profile_id
        rotated, revoked = runtime.token(B), runtime.token(C)
        saved = await save(runtime, B, 'backend/patch', {'changes': {'dashboard_username': NEW_USER}})
        assert saved.status_code == 200 and saved.json()['token_rotated'] is True, saved.text
        log_scan.watch(runtime.token(B))
        async with runtime.admin(C) as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            assert (await admin.post('/api/token/revoke', headers=reviewed_headers(boot, ADMIN))).status_code == 200
        assert runtime.token(C) is None
        refused = {'rotated away': rotated, 'revoked': revoked, 'unknown': 'T' * 43, 'a child token':
                   stored(data)['child_token'], 'a child-token-like value': 'C' * 43}
        seen = {profile_id: len(mock.seen) for profile_id, mock in child.items()}
        for what, token in refused.items():
            assert await refused_everywhere(runtime, token), what
            assert routed_to(runtime, token) == [], what
        assert {profile_id: len(mock.seen) for profile_id, mock in child.items()} == seen
        async with runtime.mcp() as client:
            crossed = await client.post(f'/private_{runtime.token("default")}/mcp', json=initialize_message(),
                                        headers={**ACCEPT, 'Authorization': 'Bearer ' + runtime.token(B)})
            assert crossed.status_code == 200 and crossed.headers['mcp-session-id'] in child['default'].sessions
            switched = await client.post('/mcp', json=initialize_message(),
                                         headers={**bearer(runtime.token(B)), 'X-MCP-Profile': 'default'})
            assert switched.status_code == 200 and switched.headers['mcp-session-id'] in child[B].sessions
        for profile_id in ('default', B):
            assert await opened_by(runtime, runtime.token(profile_id), child[profile_id]), profile_id


async def test_switched_off_only_the_default_profiles_token_is_served(tmp_path, log_scan):
    """Switched off (as the repository ships Hermes) with a profile on disk: it is dormant, and the start revoked its
    token before anything was served (HM-13b). The default profile's token opens a session with its child on both
    paths; the dormant profile's token from before the start, a token no profile has, the default profile's child
    token and C x43 are refused on both paths with an unknown token's bytes."""
    data = tmp_path / 'data'
    update_profile(data, PRODUCT, 'default', connection=hermes('alpha'))
    create_profile(data, PRODUCT, B, label=LABELS[B], port=PORTS[B], configured=False)
    update_profile(data, PRODUCT, B, connection=hermes('beta'))
    dormant = stored(directory(data, B))['token']
    watch(log_scan, data)
    async with production_runtime(PRODUCT, data) as runtime:
        await settle(runtime, 'configured')
        assert not features.enabled(PRODUCT)
        token = stored(data)['token']
        log_scan.watch(*all_tokens(data))
        assert await opened_by(runtime, token, runtime.child)
        for what, value in {'dormant': dormant, 'unknown': 'T' * 43, 'a child token': stored(data)['child_token'],
                            'a child-token-like value': 'C' * 43}.items():
            assert await refused_everywhere(runtime, value), what
        assert stored(directory(data, B))['token'] is None


# ---- a long hermes_chat counts in its own profile's quota (plan 9; T-19, T-12) ----

class ChatChild(GatewayChild):
    """GatewayChild that also keeps the timeouts each client hermes_chat was forwarded with (the request's httpx
    extension), as it arrives."""

    def __init__(self, *args):
        super().__init__(*args)
        self.chat_timeouts = []

    async def __call__(self, request):
        message = json.loads(request.content) if request.content else {}
        if message.get('method') == 'tools/call' and message['params']['name'] == 'hermes_chat':
            self.chat_timeouts.append(request.extensions.get('timeout'))
        return await super().__call__(request)


async def session_headers(client, token):
    return {**bearer(token), 'Content-Type': 'application/json', 'Mcp-Session-Id': await session_of(client, token)}


async def test_long_chats_hold_their_own_profiles_slots_and_no_other_profiles(tmp_path, log_scan):
    """Plan 9 (a hermes_chat of up to 330 s counts in its profile's quota): a tools/call is forwarded with the call
    limit (gateway.CALL_SECONDS: 330 s to read and write, above the child's own 300 s chat limit) and holds one of its
    profile's forwarding slots while the child works. B's 16 slots (an additional profile's) held by chats: B's next
    chat waits one second and gets 200 + -32003 (Retry-After 5, the fixed text) without reaching B's child; meanwhile
    the default profile's and C's chats are answered at once by their own children. Released, B's chats are all
    answered."""
    data, children = setup(tmp_path, extras=(B, C), connections={C: hermes('gamma', dashboard=False)}, child=ChatChild)
    slots, wait = profiles.EXTRA_PROFILE_QUOTA.forward_slots, profiles.EXTRA_PROFILE_QUOTA.forward_wait_seconds
    assert (slots, wait, gateway.CALL_SECONDS) == (16, 1, 330)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        beta = children.by_port[PORTS[B]]
        loop = asyncio.get_running_loop()
        async with runtime.mcp() as client:
            sessions = {profile_id: await session_headers(client, runtime.token(profile_id))
                        for profile_id in ('default', B, C)}
            beta.hold_calls = True
            held = [asyncio.create_task(client.post('/mcp', headers=sessions[B], json=chat(100 + n)))
                    for n in range(slots)]
            try:
                await until(lambda: beta.waiting == slots)
                limit = {'connect': 3, 'read': gateway.CALL_SECONDS, 'write': gateway.CALL_SECONDS, 'pool': 3}
                assert beta.chat_timeouts == [limit] * slots
                started = loop.time()
                busy(await client.post('/mcp', headers=sessions[B], json=chat(200)), status=200, retry_after=5,
                     ident=200, text=profile_router.forward_text(slots, wait))
                assert wait * .9 <= loop.time() - started < 5
                assert beta.waiting == slots and len(beta.chat_timeouts) == slots  # never forwarded
                for profile_id in ('default', C):
                    mine = children.by_port[3000 if profile_id == 'default' else PORTS[C]]
                    started = loop.time()
                    answered = await client.post('/mcp', headers=sessions[profile_id], json=chat(300))
                    assert answered.status_code == 200, answered.text
                    assert answered.json()['result']['content'][0]['text'] == mine.text
                    assert loop.time() - started < wait and mine.chat_timeouts == [limit]
            finally:
                beta.free.set()
            done = await asyncio.wait_for(asyncio.gather(*held), 10)
        assert all(response.status_code == 200 and 'result' in response.json() for response in done)


async def test_an_identity_change_ends_its_own_profiles_long_chat_only(tmp_path, log_scan):
    """T-12 with Hermes' long chats: a chat of B and one of the default profile both wait at their children when B's
    Dashboard user is saved anew. B's old child stops and B's token is rotated: B's chat ends with the old token (401;
    HM-12, as any request of a rotated token) and the default profile's goes on, answered once its child answers; B's
    new token reaches B's new child."""
    data, children = setup(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        alpha, beta = children.by_port[3000], children.by_port[PORTS[B]]
        async with runtime.mcp() as client:
            sessions = {profile_id: await session_headers(client, runtime.token(profile_id))
                        for profile_id in ('default', B)}
            alpha.hold_calls = beta.hold_calls = True
            try:
                chats = {profile_id: asyncio.create_task(client.post('/mcp', headers=sessions[profile_id],
                                                                     json=chat(7, 'a long turn')))
                         for profile_id in ('default', B)}
                await until(lambda: alpha.waiting == 1 and beta.waiting == 1)
                old = runtime.token(B)
                saved = await save(runtime, B, 'backend/patch', {'changes': {'dashboard_username': NEW_USER}})
                assert saved.status_code == 200 and saved.json()['token_rotated'] is True, saved.text
                log_scan.watch(runtime.token(B))
                ended = await asyncio.wait_for(chats[B], 10)
                assert ended.status_code == 401
                assert not chats['default'].done()
                alpha.free.set()
                answered = await asyncio.wait_for(chats['default'], 10)
                assert answered.status_code == 200 and answered.json()['result']['content'][0]['text'] == alpha.text
            finally:
                alpha.free.set()
                beta.free.set()
        assert await refused_everywhere(runtime, old)
        beta.hold_calls = False
        assert await opened_by(runtime, runtime.token(B), beta)


# ---- one profile's policy (T-07): its tools only, no child restarted ----

def tool_names(response):
    assert response.status_code == 200, response.text
    return {tool['name'] for tool in response.json()['result']['tools']}


async def test_saving_one_profiles_policy_changes_only_its_tools_and_restarts_no_child(tmp_path, log_scan):
    """B saves a policy that disables hermes_chat: B's tools/list loses it and B's chat is refused (-32602 Unknown
    tool) without reaching B's child; the default profile's and C's lists keep it and their chats reach their children.
    No child restarted (Hermes' children take no policy at launch: the gateway enforces it at every request, read from
    the profile's state), the other profiles' states are untouched. Enabled again, B's chat is back, still with no
    restart."""
    data, children = setup(tmp_path, extras=(B, C), connections={C: hermes('gamma', dashboard=False)})
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        supervisors = {profile_id: runtime.manager.get(profile_id).runtime.supervisor
                       for profile_id in ('default', B, C)}
        starts = {profile_id: supervisor.starts for profile_id, supervisor in supervisors.items()}
        others = {profile_id: (directory(data, profile_id) / 'state.json').read_bytes() for profile_id in ('default', C)}
        child = {'default': children.by_port[3000], B: children.by_port[PORTS[B]], C: children.by_port[PORTS[C]]}
        state = stored(directory(data, B))
        for disabled in (['hermes_chat'], []):
            saved = await save(runtime, B, 'policy', {'writes_enabled': state['writes_enabled'], 'disabled': disabled,
                                                      'enabled_write_tools': state['enabled_write_tools']})
            assert saved.status_code == 200 and saved.json()['profile'] == {'id': B}, saved.text
            assert stored(directory(data, B))['disabled'] == disabled
            async with runtime.mcp() as client:
                for profile_id, mock in child.items():
                    headers = await session_headers(client, runtime.token(profile_id))
                    listed = tool_names(await client.post('/mcp', headers=headers, json={
                        'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}))
                    allowed = profile_id != B or not disabled
                    assert ('hermes_chat' in listed) is allowed, profile_id
                    before = mock.client_calls()
                    reply = (await client.post('/mcp', headers=headers, json=chat(3))).json()
                    if allowed:
                        assert reply['result']['content'][0]['text'] == mock.text and mock.client_calls() == [*before, 3]
                    else:
                        assert reply['error'] == {'code': -32602, 'message': 'Unknown tool',
                                                  'data': {'tool': 'hermes_chat'}}
                        assert mock.client_calls() == before
            assert {profile_id: supervisor.starts for profile_id, supervisor in supervisors.items()} == starts
            assert {profile_id: (directory(data, profile_id) / 'state.json').read_bytes()
                    for profile_id in ('default', C)} == others


async def test_switched_off_a_policy_save_restarts_no_hermes_child(tmp_path, log_scan):
    """Switched off, the same as today: the policy saved on the only profile changes its tools and restarts no child."""
    data = tmp_path / 'data'
    update_profile(data, PRODUCT, 'default', connection=hermes('alpha'))
    made = []

    class Counted(NoProcessSupervisor):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)

    async with production_runtime(PRODUCT, data, supervisor=Counted) as runtime:
        await settle(runtime, 'configured')
        assert not features.enabled(PRODUCT)
        watch(log_scan, data)
        [supervisor] = made
        starts = supervisor.starts
        state = stored(data)
        async with runtime.admin() as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            saved = await admin.put('/api/policy', headers=reviewed_headers(boot, ADMIN), json={
                'writes_enabled': state['writes_enabled'], 'disabled': ['hermes_chat'],
                'enabled_write_tools': state['enabled_write_tools']})
            assert saved.status_code == 200 and list(saved.json()) == ['saved', 'configuration'], saved.text
        async with runtime.mcp() as client:
            init = await client.post('/mcp', headers=bearer(state['token']), json=initialize_message())
            headers = {**bearer(state['token']), 'Mcp-Session-Id': init.headers['mcp-session-id']}
            listed = tool_names(await client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 2,
                                                                                  'method': 'tools/list'}))
        assert 'hermes_chat' not in listed and supervisor.starts == starts


# ---- real children: the Dashboard cookie of each child, long chats, child bearers (T-23) ----

class FakeHermes:
    """One local Hermes for every profile of a test (its Gateway and its Dashboard on one loopback port, as several
    profiles configured with one Hermes reach it). accounts: {name: (Gateway key, Dashboard user, Dashboard
    password)}. A login of a known account gets a cookie of its own (made here, per login) for that user; a Dashboard
    request is answered for the user its cookie belongs to (a cookie it never gave out: 401) and recorded with that
    user; a Gateway request is recorded with the account its key belongs to (another key: 401). A chat of an account in
    hold waits until released (at most 30 s); the others are answered at once."""

    def __init__(self, accounts):
        self.accounts = dict(accounts)
        self.logins, self.dashboard, self.gateway = [], [], []
        self.cookies = {}
        self.hold = set()
        self.waiting = 0
        self.released = threading.Event()
        self.lock = threading.Lock()

    def handler(self):
        fake = self

        class Handler(Quiet):
            def account(self):
                sent = self.headers.get('Authorization', '')
                return next((name for name, (key, _, _) in fake.accounts.items() if sent == 'Bearer ' + key), None)

            def user(self):
                found = re.search(r'hermes_session_at="?([^";]+)', self.headers.get('Cookie') or '')
                return fake.cookies.get(found.group(1)) if found else None

            def do_POST(self):
                data = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                if self.path == '/auth/password-login':
                    login = json.loads(data)
                    users = {(user, password): user for _, user, password in fake.accounts.values()}
                    user = users.get((login.get('username'), login.get('password')))
                    if user is None:
                        return self.reply({'detail': 'Invalid credentials'}, 401)
                    with fake.lock:
                        fake.logins.append(user)
                        cookie = f'login-{len(fake.logins)}'
                        fake.cookies[cookie] = user
                    self.send_response(200)
                    self.send_header('Set-Cookie', f'hermes_session_at={cookie}; Path=/; HttpOnly')
                    self.send_header('Content-Length', '2')
                    self.end_headers()
                    self.wfile.write(b'{}')
                    return
                if self.path == '/v1/responses':
                    name = self.account()
                    fake.gateway.append((name, self.path))
                    if name is None:
                        return self.reply({'error': 'unauthorized'}, 401)
                    if name in fake.hold:
                        with fake.lock:
                            fake.waiting += 1
                        fake.released.wait(30)
                        with fake.lock:
                            fake.waiting -= 1
                    return self.reply({'status': 'completed', 'output': [{'type': 'message', 'content': [
                        {'type': 'output_text', 'text': f'reply to {name}'}]}]})
                self.reply({'detail': 'Not Found'}, 404)

            def do_GET(self):
                if self.path == '/v1/capabilities':
                    name = self.account()
                    fake.gateway.append((name, self.path))
                    return self.reply({'models': []} if name else {'error': 'unauthorized'}, 200 if name else 401)
                if self.path == '/api/status':
                    user = self.user()
                    fake.dashboard.append((user, self.path))
                    if user is None:
                        return self.reply({'detail': 'Unauthorized'}, 401)
                    return self.reply({'version': '0.22.5', 'gateway_running': True,
                                       'gateway_state': f'serving {user}', 'active_sessions': 0})
                self.reply({'detail': 'Not Found'}, 404)
        return Handler

    @contextmanager
    def serving(self):
        try:
            with serve(self.handler()) as url:
                yield url
        finally:
            self.released.set()


def account(name, url):
    """name's connection to the one local Hermes (its Gateway key, its Dashboard account), and that account."""
    key, user, password = f'DUMMY-{name}-gateway-key', f'DUMMY-user-{name}', f'DUMMY-{name}-dashboard-password'
    return ({'gateway_url': url, 'gateway_api_key': key, 'dashboard_url': url, 'dashboard_username': user,
             'dashboard_password': password}, (key, user, password))


async def tool_text(client, headers, ident, name, arguments):
    """The text of a tools/call result (an error result fails)."""
    from test_real_products import rpc
    result = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
                                                 'params': {'name': name, 'arguments': arguments}})
    assert result.get('isError') is not True, result
    return '\n'.join(item['text'] for item in result['content'] if item.get('type') == 'text')


async def test_real_children_keep_their_dashboard_cookies_and_long_chats_apart(tmp_path, log_scan, monkeypatch):
    """Two real Hermes children (the default profile's and B's: the real Supervisor, apps/hermes/launch.py in its
    pinned venv on its own port) and one local Hermes for both, each profile with its own Gateway key and Dashboard
    account:

    - each child logs in once with its own account and every Dashboard request it makes carries the cookie of that
      login (the status each profile gets is its own user's); two profiles on one Dashboard are two logins from the
      add-on's one address (the Dashboard's limit is shared, contract section 9); nothing is written in either child's
      directory (the cookie cache is in the child's memory only);
    - a long chat of B waits at the Gateway while the default profile's chat and B's own status call are answered;
    - each child refuses the other's child bearer (401) and serves its own (T-23 across profiles);
    - B's Dashboard user saved anew rotates B's token, B's new child logs in as the new user, B's old token is refused.
    """
    from mcp_admin_core import health as health_module, lifecycle
    from test_backend_loopback import running_its_program
    from test_odoo_multi_profile import session_of as protocol_session
    monkeypatch.setattr(health_module, 'HEALTH_INTERVAL', 0.5)  # both profiles' first health checks within a second
    data = tmp_path / 'data'
    fake = FakeHermes({})
    with fake.serving() as url, loopback_backends.allowed():  # the local fake Hermes passes HM-20's loopback rule
        mine, fake.accounts['alpha'] = account('alpha', url)
        theirs, fake.accounts['beta'] = account('beta', url)
        moved, fake.accounts['beta2'] = account('beta2', url)
        update_profile(data, PRODUCT, 'default', connection=mine)
        create_profile(data, PRODUCT, B, label=LABELS[B], port=free_port(), configured=False)
        update_profile(data, PRODUCT, B, connection=theirs)
        watch(log_scan, data)
        log_scan.watch(moved['dashboard_password'], kind='secret')
        async with multi_profile_runtime(PRODUCT, data, supervisor=lifecycle.Supervisor, real_children=True,
                                         default_port=free_port()) as runtime:
            entries = {profile_id: runtime.manager.get(profile_id).runtime for profile_id in ('default', B)}

            def ready(*profile_ids):
                return all(running_its_program(entries[p].supervisor) and entries[p].health.availability()['ready']
                           for p in profile_ids)
            await until(lambda: ready('default', B), 60)
            async with runtime.mcp() as client:
                alpha = await protocol_session(client, runtime.token('default'))
                beta = await protocol_session(client, runtime.token(B))
                for ident, (headers, user) in enumerate([(alpha, 'alpha'), (beta, 'beta')] * 2, 10):
                    status = json.loads(await tool_text(client, dict(headers), ident, 'hermes_gateway',
                                                        {'action': 'status'}))
                    assert status['state'] == f'serving DUMMY-user-{user}'
                assert fake.logins == ['DUMMY-user-alpha', 'DUMMY-user-beta']
                assert fake.dashboard == [(f'DUMMY-user-{user}', '/api/status') for user in ('alpha', 'beta') * 2]
                for profile_id in ('default', B):
                    assert not any((directory(data, profile_id) / 'child').iterdir()), profile_id

                fake.hold.add('beta')
                loop = asyncio.get_running_loop()
                long_chat = asyncio.create_task(tool_text(client, dict(beta), 20, 'hermes_chat',
                                                          {'message': 'a long turn'}))
                await until(lambda: fake.waiting == 1, 30)
                started = loop.time()
                assert await tool_text(client, dict(alpha), 21, 'hermes_chat', {'message': 'hi'}) == 'reply to alpha'
                status = json.loads(await tool_text(client, dict(beta), 22, 'hermes_gateway', {'action': 'status'}))
                assert status['state'] == 'serving DUMMY-user-beta'
                assert loop.time() - started < 15 and not long_chat.done()
                fake.released.set()
                assert await asyncio.wait_for(long_chat, 30) == 'reply to beta'
                assert ('beta', '/v1/responses') in fake.gateway and ('alpha', '/v1/responses') in fake.gateway

            async with GENUINE_CLIENT(trust_env=False) as direct:
                for profile_id, entry in entries.items():
                    for other in ('default', B):
                        response = await direct.post(f'http://127.0.0.1:{entry.port}/mcp', json=initialize_message(),
                                                     headers={**ACCEPT, 'Authorization': 'Bearer ' + stored(
                                                         directory(data, other))['child_token']})
                        assert response.status_code == (200 if other == profile_id else 401), (profile_id, other)

            old = runtime.token(B)
            saved = await save(runtime, B, 'backend/patch', {'changes': {
                'dashboard_username': moved['dashboard_username'], 'dashboard_password': moved['dashboard_password']}})
            assert saved.status_code == 200 and saved.json()['token_rotated'] is True, saved.text
            log_scan.watch(runtime.token(B))
            await until(lambda: ready(B), 60)
            assert await refused_everywhere(runtime, old)
            async with runtime.mcp() as client:
                again = await protocol_session(client, runtime.token(B))
                status = json.loads(await tool_text(client, again, 30, 'hermes_gateway', {'action': 'status'}))
            assert status['state'] == 'serving DUMMY-user-beta2'
            assert fake.logins == ['DUMMY-user-alpha', 'DUMMY-user-beta', 'DUMMY-user-beta2']
