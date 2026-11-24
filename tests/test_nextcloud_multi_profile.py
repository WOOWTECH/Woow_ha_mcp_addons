"""HM-22: Nextcloud switched on (multi-profile plan 9 Nextcloud row, 12.3 HM-21～HM-26; DQ-05, DQ-25, DQ-40 ⑨ ⑩ (a);
contract 3.1, 7, section 9 #39, #40, #54 and HM-22's rows; I1, I4, I11; FM-47, FM-69, FM-91, FM-153; T-03, T-04, T-05,
T-07, T-23; PaaS #152, #154).

What the product's version bump switches on (features.MULTI_PROFILE_PRODUCTS; here each test switches it, as
tests/multi_profile_runtime.py does):

- A profile's MCP token is bound to its Nextcloud account (DQ-40 ⑩ (a); PaaS #154, woow-mcp-server 0f94aa4): a save
  (PUT backend or backend/patch) that changes its url or its username rotates the token in HM-12's order (the old child
  stops, one write holds the connection, the new token and a rotate history entry, the change is published, the new
  child starts) and the old token is refused on both connection paths, for an additional profile and for the default
  profile alike. The app password alone, the first setup and a revoked token keep it, as do the other profiles'
  tokens; while a restored profile waits for its review, such a save is refused (409 restore_review_required) and
  does nothing (HM-13c review S-3). The url is compared as the server it names
  (products.same_identity; PaaS normalize_base_url): the scheme and the host in any letter case and the default port
  written out or not are one server; pasted page suffixes are stripped; path case remains significant.
- A widened policy restarts only the running profile's child; tightening and unchanged saves preserve sessions.
  A stopped child stays stopped, and other profiles are untouched.
- Only a profile's own token reaches its child (T-05) and each child serves its own child bearer only (T-23), also
  with two real Nextcloud children of two users of one fake Nextcloud server whose WebDAV homes stay apart (the LOCAL
  version of the HAOS test).
- A refused login backs off only its own profile's health checks (DQ-25; FM-69; contract 7), and the real child sends
  one failed login per start (its authentication latch); the other profile keeps its checks and its backend. Whether
  Nextcloud throttles by source address, which every profile of the add-on shares, is unconfirmed (UC-12).
- A URL the save refuses (loopback once switched on, a metadata address, whitespace; HM-20, aligned with PaaS #152)
  writes nothing and stops no child.

Switched off, every save is today's (plan 3.3): no rotation, the same answer, the same order. Those cases pin the
mode themselves (nextcloud_fixtures.switched_off), not the repository's switch, so they test the same thing after
the version bump that switches Nextcloud on.

The in-process cases run the production runtime (tests/multi_profile_runtime.py: NoProcessSupervisor, the children
behind one MockTransport); the real-children cases run the vendored Nextcloud child (apps/nextcloud) against this
file's loopback fake, which tests/loopback_backends.py lets through HM-20's loopback rule. Every case runs under the
HM-01 log scan (tokens, child tokens, credentials, usernames, hosts and labels watched).
"""
import base64
import json
import secrets
from urllib.parse import quote, unquote, urlsplit

import httpx
import pytest

from admin_write_headers import reviewed_headers
from lifecycle_runtime import proc_cmdline, until
from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import (Children, all_tokens, create_profile, free_port, ids, multi_profile_runtime,
                                   stored, update_profile)
import loopback_backends
from mcp_admin_core import (features, health as health_module, identity_fields, lifecycle, profile_runtime,
                            restore_lock)
from mcp_admin_core.access import masked_token
from mcp_admin_core.products import IDENTITY_BOUND, ProductState, ProductStore, identity_rebound
from nextcloud_fixtures import OCS_PATH, multistatus, respond
from nextcloud_fixtures import switched_off  # noqa: F401  (fixture: the switched-off cases pin that mode)
from test_odoo_identity_rotation import (Journal, bearer, count_writes, directory, next_etag, opened_by, paths,
                                         record_writes, refused_everywhere, routed_to, save,
                                         warnings_of as rebind_warnings)
from test_profile_admin_api import tree_of
from test_real_products import rpc
from test_restore_review import bootstrap_of, mark_restored
from test_single_profile_golden import (ACCEPT, ADMIN, BEARER_REQUIRED, CONNECTIONS, NOT_FOUND, answer, configure,
                                        initialize_message, production_runtime, settle)
from test_six_hardening import Quiet, serve

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'nextcloud'
B, C = ids(2)
LABELS = {B: 'Files Desk', C: 'Tasks Desk'}
PORTS = {B: 18000, C: 18001}
# Synthetic accounts (tests/fixtures/owner_defaults/README.md rules: DUMMY- credentials, .invalid hosts). B and C are
# two users of one Nextcloud server under a sub-path; the default profile keeps the golden account (DUMMY-user).
SERVER = 'https://cloud.nextcloud.invalid/nc'
ACCOUNTS = {B: {'url': SERVER, 'username': 'DUMMY-bob', 'app_password': 'DUMMY-bob-app-password'},
            C: {'url': SERVER, 'username': 'DUMMY-carol', 'app_password': 'DUMMY-carol-app-password'}}
# The default profile's account where a case changes it (HM-22 review S-3): a third user of B's server, so that each
# change of ROTATIONS is the one it names for the default profile too.
DEFAULT_ACCOUNT = {'url': SERVER, 'username': 'DUMMY-alice', 'app_password': 'DUMMY-alice-app-password'}
NEW_PASSWORD = 'DUMMY-rebound-nextcloud-password'
NEW_USER = 'DUMMY-dave'
WATCHED_HOSTS = ('cloud.nextcloud.invalid', 'other.nextcloud.invalid')
WATCHED_USERS = ('DUMMY-alice', 'DUMMY-bob', 'DUMMY-carol', NEW_USER)
# The JSON-RPC code of the gateway's refusal of a tool the policy disables (policy.ToolCallRefused: Unknown tool).
UNKNOWN_TOOL = -32602


def setup(tmp_path, extras=(B,), configured=True):
    """The default profile on the golden Nextcloud account, the additional profiles extras on their PORTS with their
    own ACCOUNTS when configured, and every profile's child behind one MockTransport."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    children = Children()
    children.profile_child(3000, 'default', PRODUCT, data)
    for profile_id in extras:
        create_profile(data, PRODUCT, profile_id, label=LABELS[profile_id], port=PORTS[profile_id], configured=False)
        if configured:
            update_profile(data, PRODUCT, profile_id, connection=ACCOUNTS[profile_id])
        children.profile_child(PORTS[profile_id], 'p' + profile_id[:4], PRODUCT, directory(data, profile_id))
    return data, children


def watch(log_scan, data):
    """The log scan's needles: every token and child token stored under data, every app password, username and host
    of these tests (no log line may show one: PaaS test_the_identity_change_log_line_has_no_values) and every label."""
    log_scan.watch(*all_tokens(data))
    passwords = [CONNECTIONS[PRODUCT]['app_password'], NEW_PASSWORD, DEFAULT_ACCOUNT['app_password'],
                 *(account['app_password'] for account in ACCOUNTS.values())]
    log_scan.watch(*passwords, *WATCHED_USERS, *WATCHED_HOSTS, kind='secret')
    log_scan.watch(*LABELS.values(), kind='name')


def body_of(route, before, changes):
    """A save of changes: the whole connection (PUT backend: the stored one with the changes) or the changed fields
    alone (backend/patch)."""
    if route == 'backend':
        return {'connection': {**before, **changes}}
    return {'changes': dict(changes)}


def nextcloud_state(connection, token='T' * 43):
    return ProductState(product=PRODUCT, token=token, child_token='C' * 43, connection=connection)


# ---- which saves rebind the token (products.identity_rebound; PaaS test_a_different_spelling_of_the_same_url_is_not_
# an_identity_change, test_a_really_different_url_is_an_identity_change, test_changing_only_the_app_password_keeps_the_
# token) ----

# (what changes, the saved values): the same Nextcloud account, or another one.
SAME_ACCOUNT = [
    ('scheme and host in capitals', {'url': 'HTTPS://CLOUD.Nextcloud.INVALID/nc'}),
    ('default port written out', {'url': 'https://cloud.nextcloud.invalid:443/nc'}),
    ('trailing slashes', {'url': 'https://cloud.nextcloud.invalid/nc//'}),
    ('pasted page path', {'url': 'https://cloud.nextcloud.invalid/nc/index.php/apps/files'}),
    ('app password', {'app_password': NEW_PASSWORD}),
    ('nothing', {}),
]
OTHER_ACCOUNT = [
    ('other host', {'url': 'https://other.nextcloud.invalid/nc'}),
    ('other scheme', {'url': 'http://cloud.nextcloud.invalid/nc'}),
    # HM-22 review S-1: the scheme alone differs (the same port), and the other scheme's default port on https: a
    # comparison that left out the scheme, or took 80 and 443 as every scheme's default, would keep the token.
    ('other scheme on the same port', {'url': 'http://cloud.nextcloud.invalid:443/nc'}),
    ('the http port on https', {'url': 'https://cloud.nextcloud.invalid:80/nc'}),
    ('other port', {'url': 'https://cloud.nextcloud.invalid:8443/nc'}),
    ('other path', {'url': 'https://cloud.nextcloud.invalid/other'}),
    ('path in capitals', {'url': 'https://cloud.nextcloud.invalid/NC'}),
    ('no path', {'url': 'https://cloud.nextcloud.invalid'}),
    ('username', {'username': NEW_USER}),
    ('username in capitals', {'username': 'DUMMY-BOB'}),
]


@pytest.mark.parametrize('case, changes', SAME_ACCOUNT + OTHER_ACCOUNT, ids=[c for c, _ in SAME_ACCOUNT + OTHER_ACCOUNT])
def test_which_saves_rebind_the_token(monkeypatch, log_scan, case, changes):
    """Switched on, a save rebinds the token when the url names another server or path, or the username differs
    (DQ-40 ⑩ (a); PaaS IDENTITY_KEYS base_url, username). A url is compared as the server it names: the scheme and the
    host in any letter case and the default port are one server (PaaS normalize_base_url); the path is compared as
    normalized with its letter case preserved; pasted page suffixes are removed. Switched off, nothing rebinds."""
    previous = nextcloud_state(ACCOUNTS[B])
    candidate = nextcloud_state({**ACCOUNTS[B], **changes})
    log_scan.watch_state(candidate)
    monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset({PRODUCT}))
    assert identity_rebound(previous, candidate) is (case in dict(OTHER_ACCOUNT)), case
    monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset())
    assert identity_rebound(previous, candidate) is False


def test_the_first_setup_a_revoked_token_and_a_cleared_connection(monkeypatch):
    """PaaS test_first_time_setup_keeps_the_issued_url, test_a_revoked_or_missing_token_is_not_replaced_by_an_identity_
    change, test_clearing_the_identity_rotates_and_filling_it_back_does_not: no connection saved before keeps the
    token; a revoked token stays revoked; a cleared connection is a change (filling it in again is a first setup)."""
    monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset({PRODUCT}))
    other = {**ACCOUNTS[B], 'username': NEW_USER}
    assert identity_rebound(nextcloud_state(None), nextcloud_state(other)) is False
    assert identity_rebound(nextcloud_state(ACCOUNTS[B], token=None), nextcloud_state(other, token=None)) is False
    assert identity_rebound(nextcloud_state(ACCOUNTS[B]), nextcloud_state(None)) is True


def test_nextcloud_is_bound_to_its_url_and_username():
    """DQ-40 ⑩ (a): Nextcloud joins Odoo in products.IDENTITY_BOUND (PaaS #154: LaunchPolicy.identity_connection_keys
    base_url, username; the app password is no identity); its url is compared as a server (identity_fields
    .SAME_SERVER_URLS, Nextcloud's only: Odoo's compares as typed, as PaaS #131 does). The panel's list (contracts.js
    identityBound) is checked against IDENTITY_BOUND by tests/test_identity_fields.py."""
    assert IDENTITY_BOUND == frozenset({'odoo', 'nextcloud'})
    assert identity_fields.rotating_fields(PRODUCT) == ('url', 'username')
    assert 'app_password' not in identity_fields.rotating_fields(PRODUCT)
    assert identity_fields.SAME_SERVER_URLS == {'nextcloud': ('url',)}


# ---- the rotation through the switched-on runtime (PaaS test_identity_change_revokes_the_old_url_and_issues_a_new_one,
# test_the_old_child_is_stopped_before_the_new_identity_becomes_durable, test_the_shared_settings_route_rotates_the_
# token_too) ----

# (case, route, the changed fields; backend/patch brings the app password with a URL moved to another origin: DQ-40 ⑨)
ROTATIONS = [
    ('other host', 'backend', {'url': 'https://other.nextcloud.invalid/nc'}),
    ('other host', 'backend/patch', {'url': 'https://other.nextcloud.invalid/nc', 'app_password': NEW_PASSWORD}),
    ('other scheme', 'backend/patch', {'url': 'http://cloud.nextcloud.invalid/nc', 'app_password': NEW_PASSWORD}),
    ('other scheme on the same port', 'backend/patch',
     {'url': 'http://cloud.nextcloud.invalid:443/nc', 'app_password': NEW_PASSWORD}),
    ('the http port on https', 'backend/patch',
     {'url': 'https://cloud.nextcloud.invalid:80/nc', 'app_password': NEW_PASSWORD}),
    ('other port', 'backend/patch', {'url': 'https://cloud.nextcloud.invalid:8443/nc', 'app_password': NEW_PASSWORD}),
    ('other path', 'backend/patch', {'url': 'https://cloud.nextcloud.invalid/other'}),
    ('path in capitals', 'backend/patch', {'url': 'https://cloud.nextcloud.invalid/NC'}),
    ('username', 'backend', {'username': NEW_USER}),
    ('username', 'backend/patch', {'username': NEW_USER}),
]


@pytest.mark.parametrize('case, route, changes', ROTATIONS, ids=[f'{c}-{r}' for c, r, _ in ROTATIONS])
@pytest.mark.parametrize('profile_id', [B, 'default'], ids=['B', 'default'])
async def test_a_changed_account_stops_the_old_child_then_rotates_the_token_in_one_write(
        tmp_path, log_scan, monkeypatch, profile_id, case, route, changes):
    """The url or the username of B, or of the default profile (HM-22 review S-3: once Nextcloud is switched on, every
    single-profile user's own profile, its state at the data root and its child on port 3000), saved anew, both
    accounts on B's server: the old child stops while the old token is still the one on disk; one write holds the new
    connection (the other fields as stored), a new 43-character token and one history entry (rotate, the old token
    masked; PaaS writes backend_identity_change: contract #59); the token change is published; the new child starts on
    the new account (its environment carries the saved URL and username). 200 {"saved", "token_rotated": true,
    "configuration"} with the profile's echo and the new state's ETag, never a token. The 8081 dispatcher routes the
    old token to no profile and the new one to the profile; the old token is refused on both paths and the new one
    opens a session with the profile's child on both; the other profile's state and token are untouched (I6)."""
    data, children = setup(tmp_path)
    if profile_id == 'default':
        configure_store(data, DEFAULT_ACCOUNT)
    other = 'default' if profile_id == B else B
    ports = {'default': 3000, B: PORTS[B]}
    journal = Journal()
    record_writes(monkeypatch, journal)
    replaced = count_writes(monkeypatch, directory(data, profile_id) / 'state.json')
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        journal.watch(data, profile_id, runtime.manager.get(profile_id).runtime.supervisor)
        before = stored(directory(data, profile_id))
        old, other_state = before['token'], (directory(data, other) / 'state.json').read_bytes()
        replaced.clear()
        saved = await save(runtime, profile_id, route, body_of(route, before['connection'], changes))
        assert saved.status_code == 200, saved.text
        assert len(replaced) == 1, 'the connection, the token and its history are one write'
        body = saved.json()
        assert list(body) == ['saved', 'token_rotated', 'configuration', 'profile']
        assert (body['saved'], body['token_rotated'], body['profile']) == (True, True, {'id': profile_id})
        after = stored(directory(data, profile_id))
        new = after['token']
        log_scan.watch(new)
        assert new not in (None, old) and len(new) == 43 and new not in saved.text and old not in saved.text
        assert after['child_token'] == before['child_token']
        assert after['connection'] == {**before['connection'], **changes}
        entry, = after['token_history']
        assert (entry['action'], entry['previous_token_masked']) == ('rotate', masked_token(old))
        assert journal.events == [('stop', old, before['connection']['username']), ('write', 'stopped'), ('publish',),
                                  ('start', after['connection']['username'])]
        # HM-22 review N-4: the new child runs on the saved URL, not only on the saved username.
        env = spec_env(runtime, profile_id)
        assert (env['NEXTCLOUD_MCP_BASE_URL'], env['NEXTCLOUD_MCP_USERNAME']) == (
            after['connection']['url'], after['connection']['username'])
        assert saved.headers['etag'] == await next_etag(runtime, profile_id)
        assert routed_to(runtime, old) == [] and routed_to(runtime, new) == [profile_id]
        assert await refused_everywhere(runtime, old)
        assert await opened_by(runtime, new, children.by_port[ports[profile_id]])
        assert (directory(data, other) / 'state.json').read_bytes() == other_state
        assert await opened_by(runtime, runtime.token(other), children.by_port[ports[other]])


SPELLINGS = [value['url'] for case, value in SAME_ACCOUNT if 'url' in value] + ['  ' + SERVER + '  ']


@pytest.mark.parametrize('route', ['backend', 'backend/patch'])
async def test_the_same_server_written_another_way_keeps_the_token(tmp_path, log_scan, monkeypatch, route):
    """PaaS test_a_different_spelling_of_the_same_url_is_not_an_identity_change and test_a_legacy_unnormalized_stored_
    url_is_not_rotated_by_resaving_the_form: B's url in capitals, with the default port written out or with trailing
    slashes is the same server and path: each save is today's (written first, then the child restarts; the answer has
    no token_rotated), the token stays and no history entry is written. The stored equivalent spelling is retained."""
    data, children = setup(tmp_path)
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        journal.watch(data, B, runtime.manager.get(B).runtime.supervisor)
        token = runtime.token(B)
        for url in [*SPELLINGS, SERVER]:
            connection = stored(directory(data, B))['connection']
            saved = await save(runtime, B, route, body_of(route, connection, {'url': url}))
            assert saved.status_code == 200, (url, saved.text)
            assert list(saved.json()) == ['saved', 'configuration', 'profile'], url
            state = stored(directory(data, B))
            assert state['token'] == token and 'token_history' not in state, url
            assert state['connection'] == {**ACCOUNTS[B], 'url': SERVER}, url
        assert journal.events == [('stop', token, 'DUMMY-bob'), ('start', 'DUMMY-bob')] * (len(SPELLINGS) + 1)
        assert await opened_by(runtime, token, children.by_port[PORTS[B]])


async def test_an_app_password_change_or_the_first_setup_keeps_the_token(tmp_path, log_scan, monkeypatch):
    """PaaS test_first_time_setup_keeps_the_issued_url, test_changing_only_the_app_password_keeps_the_token,
    test_a_password_only_save_adds_no_notice_and_keeps_the_restart_flag_semantics: B's first connection, then a new app
    password alone (backend/patch), then the whole connection again with another app password (PUT backend): each
    answer is today's, the token B was born with stays, no history entry, the child restarts after each write (today's
    order). PaaS test_a_revoked_or_missing_token_is_not_replaced_by_an_identity_change: a revoked token stays revoked
    through a username change."""
    data, children = setup(tmp_path, configured=False)
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        journal.watch(data, B, runtime.manager.get(B).runtime.supervisor)
        token = runtime.token(B)
        assert stored(directory(data, B))['connection'] is None
        for route, body in (('backend', {'connection': ACCOUNTS[B]}),
                            ('backend/patch', {'changes': {'app_password': NEW_PASSWORD}}),
                            ('backend', {'connection': ACCOUNTS[B]})):
            saved = await save(runtime, B, route, body)
            assert saved.status_code == 200, saved.text
            assert list(saved.json()) == ['saved', 'configuration', 'profile'], route
        state = stored(directory(data, B))
        assert state['token'] == token and 'token_history' not in state and state['connection'] == ACCOUNTS[B]
        assert journal.events == [('start', 'DUMMY-bob'), ('stop', token, 'DUMMY-bob'), ('start', 'DUMMY-bob'),
                                  ('stop', token, 'DUMMY-bob'), ('start', 'DUMMY-bob')]
        assert await opened_by(runtime, token, children.by_port[PORTS[B]])
        async with runtime.admin(B) as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            revoked = await admin.post('/api/token/revoke', headers=reviewed_headers(boot, ADMIN))
            assert revoked.status_code == 200, revoked.text
        saved = await save(runtime, B, 'backend/patch', {'changes': {'username': NEW_USER}})
        assert saved.status_code == 200 and list(saved.json()) == ['saved', 'configuration', 'profile'], saved.text
        state = stored(directory(data, B))
        assert state['token'] is None and [entry['action'] for entry in state['token_history']] == ['revoke']
        assert state['connection']['username'] == NEW_USER
        assert await refused_everywhere(runtime, token)


async def test_a_cleared_connection_rotates_the_token_and_the_next_setup_keeps_it(tmp_path, log_scan, monkeypatch):
    """PaaS test_clearing_the_identity_rotates_and_filling_it_back_does_not: PUT backend {"connection": null} clears B's
    account: the old child stops, one write holds the new token, nothing starts (no connection); the old token is
    refused, the new one gets the gateway's own answers. The next connection (another account) is a first setup: the
    token stays and the child starts on it."""
    data, children = setup(tmp_path)
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        journal.watch(data, B, runtime.manager.get(B).runtime.supervisor)
        old = runtime.token(B)
        cleared = await save(runtime, B, 'backend', {'connection': None})
        assert cleared.status_code == 200 and cleared.json()['token_rotated'] is True, cleared.text
        new = runtime.token(B)
        log_scan.watch(new)
        assert new != old and stored(directory(data, B))['connection'] is None
        assert journal.events == [('stop', old, 'DUMMY-bob'), ('write', 'stopped'), ('publish',)]
        assert await refused_everywhere(runtime, old)
        async with runtime.mcp() as client:
            local = await client.post('/mcp', headers=bearer(new), json=initialize_message())
        assert local.status_code == 200 and local.headers['mcp-session-id'].startswith('woow-local-')
        filled = await save(runtime, B, 'backend', {'connection': {**ACCOUNTS[B], 'username': NEW_USER}})
        assert filled.status_code == 200 and 'token_rotated' not in filled.json(), filled.text
        assert runtime.token(B) == new and journal.events[-1] == ('start', NEW_USER)
        assert await opened_by(runtime, new, children.by_port[PORTS[B]])


async def test_one_profiles_new_account_rotates_only_its_own_token(tmp_path, log_scan, monkeypatch):
    """PaaS test_an_extra_account_rotates_only_its_own_token: B and C, two users of one Nextcloud server, beside the
    default profile. B's username saved anew rotates B's token alone: the default profile's and C's states stay byte for
    byte, their children are not restarted and their tokens still open their own children's sessions."""
    data, children = setup(tmp_path, extras=(B, C))
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        journal.watch(data, B, runtime.manager.get(B).runtime.supervisor)
        others = ('default', C)
        kept = {profile_id: (directory(data, profile_id) / 'state.json').read_bytes() for profile_id in others}
        starts = {profile_id: runtime.manager.get(profile_id).runtime.supervisor.starts for profile_id in others}
        old = runtime.token(B)
        saved = await save(runtime, B, 'backend/patch', {'changes': {'username': NEW_USER}})
        assert saved.status_code == 200 and saved.json()['token_rotated'] is True, saved.text
        new = runtime.token(B)
        log_scan.watch(new)
        assert journal.events == [('stop', old, 'DUMMY-bob'), ('write', 'stopped'), ('publish',), ('start', NEW_USER)]
        assert await refused_everywhere(runtime, old)
        assert await opened_by(runtime, new, children.by_port[PORTS[B]])
        for profile_id, port in (('default', 3000), (C, PORTS[C])):
            assert (directory(data, profile_id) / 'state.json').read_bytes() == kept[profile_id], profile_id
            assert runtime.manager.get(profile_id).runtime.supervisor.starts == starts[profile_id], profile_id
            assert await opened_by(runtime, runtime.token(profile_id), children.by_port[port]), profile_id


# ---- the restore review (HM-13c review S-3; HM-22 review N-5): a Nextcloud account change issues a new token, so it
# waits for the profile's review as token/rotate does ----

def restored_switched_off_then_reissued(data):
    """HM-13c review S-3's state (tests/test_restore_review.py) with Nextcloud: the default profile and B restored with
    profile data while Nextcloud is not switched on: the guard revokes both and records them unreviewed. Switched off
    there is no gate, so the administrator issues the default profile a new token (T x43 here). Switched on afterwards,
    the default profile's token is active while its review still waits."""
    mark_restored(data)
    store = ProductStore(data, PRODUCT)
    try:
        outcome = restore_lock.guard(store, PRODUCT, enabled=False)
        assert outcome.restored and outcome.default_revoked
        store.change_token('T' * 43, action='rotate')
    finally:
        store.close()


@pytest.mark.parametrize('route', ['backend', 'backend/patch'])
async def test_an_account_change_waits_for_the_profiles_restore_review(tmp_path, log_scan, monkeypatch, route):
    """HM-13c review S-3 with Nextcloud (HM-22 review N-5): switched on, a save of another username would rotate the
    default profile's active token (products.identity_rebound). While the profile waits for its restore review it
    answers 409 restore_review_required, as token/rotate does, after If-Match and before anything is done: the child is
    not stopped, nothing is written (the tree is the same), no token change is published, the token stays the one 8081
    serves on both paths, and no line is logged. A new app password alone rotates nothing and is saved as today, the
    review still waiting. The gate is HM-13c's and knows no product; the panel's words for the refused save are
    contracts.js identityChange.nextcloud (HM-22 review MF-1)."""
    data, children = setup(tmp_path)
    restored_switched_off_then_reissued(data)
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        journal.watch(data, 'default', runtime.manager.get('default').runtime.supervisor)
        default = await bootstrap_of(runtime)
        assert default['token_active'] is True and default['restore_review_required'] is True
        token, state, before = runtime.token('default'), stored(data), tree_of(data)
        refused = await save(runtime, 'default', route, body_of(route, state['connection'], {'username': NEW_USER}))
        assert (refused.status_code, refused.json()) == (
            409, {'error': 'request denied', 'detail': {'code': 'restore_review_required'}}), refused.text
        assert journal.events == [] and tree_of(data) == before and stored(data) == state
        assert runtime.token('default') == token and await opened_by(runtime, token, children.by_port[3000])
        assert rebind_warnings(log_scan) == []
        kept = await save(runtime, 'default', 'backend/patch', {'changes': {'app_password': NEW_PASSWORD}})
        assert kept.status_code == 200 and kept.json()['saved'] is True and 'token_rotated' not in kept.json(), kept.text
        assert stored(data)['token'] == token and stored(data)['connection']['app_password'] == NEW_PASSWORD
        assert [event[0] for event in journal.events] == ['stop', 'start']  # the child relaunched, no identity write
        assert (await bootstrap_of(runtime))['restore_review_required'] is True


# What a switched-on save refuses before anything happens (400 {"error":"request denied"}): HM-20's loopback rule
# (PaaS #152 blocks these too, and private addresses: contract #39), a metadata host and whitespace (refused switched
# off as well; PaaS strips whitespace: HM-22's row on the URL).
REFUSED_URLS = ('http://127.0.0.1:8080/nc', 'http://localhost/nc', 'http://[::1]/nc', 'http://169.254.169.254/nc',
                'http://metadata.google.internal/nc', 'https://other.nextcloud.invalid/n c')


@pytest.mark.parametrize('route', ['backend', 'backend/patch'])
async def test_a_refused_url_stores_nothing_and_rotates_nothing(tmp_path, log_scan, monkeypatch, route):
    """PaaS test_a_blocked_url_stores_nothing_and_does_not_rotate (PaaS #152's save check): a new account on a URL the
    save refuses is refused with the fixed 400 before the identity change: B's state byte for byte as it was, no child
    stopped or started, no token change; B's token still opens B's child's sessions."""
    data, children = setup(tmp_path)
    journal = Journal()
    record_writes(monkeypatch, journal)
    async with multi_profile_runtime(PRODUCT, data, children=children, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        journal.watch(data, B, runtime.manager.get(B).runtime.supervisor)
        state_path, token = directory(data, B) / 'state.json', runtime.token(B)
        raw = state_path.read_bytes()
        for url in REFUSED_URLS:
            changes = {'url': url, 'username': NEW_USER, 'app_password': NEW_PASSWORD}
            saved = await save(runtime, B, route, body_of(route, ACCOUNTS[B], changes))
            assert (saved.status_code, saved.content) == (400, b'{"error":"request denied"}'), url
            assert state_path.read_bytes() == raw, url
        assert journal.events == []
        assert runtime.token(B) == token and await opened_by(runtime, token, children.by_port[PORTS[B]])


# ---- one profile's tool policy (T-07; FM-47; PaaS test_policy_update_only_restarts_selected_real_child,
# test_enabling_write_tool_restarts_child, test_unchanged_policy_does_not_restart) ----

async def session_of(client, path, headers):
    """An initialized session on path (headers: the connection's own): the headers its next requests carry."""
    headers = dict(headers)
    result = await rpc(client, path, headers, initialize_message())
    headers['MCP-Protocol-Version'] = result['protocolVersion']
    await rpc(client, path, headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    return headers


async def listed(client, path, headers):
    """The tool names tools/list answers in the session of headers."""
    result = await rpc(client, path, headers, {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/list'})
    return {tool['name'] for tool in result['tools']}


def spec_env(runtime, profile_id):
    return runtime.manager.get(profile_id).runtime.supervisor.spec.env


async def test_saving_one_profiles_policy_restarts_only_its_child(tmp_path, log_scan):
    """Tightening and unchanged saves preserve sessions; widening restarts only the selected profile."""
    data, children = setup(tmp_path, extras=(B, C))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        everyone = ('default', B, C)
        supervisors = {p: runtime.manager.get(p).runtime.supervisor for p in everyone}
        async with runtime.mcp() as client:
            sessions = {p: await session_of(client, '/mcp', bearer(runtime.token(p))) for p in everyone}
            starts = {p: s.starts for p, s in supervisors.items()}
            other_states = {p: (directory(data, p) / 'state.json').read_bytes() for p in ('default', C)}
            tightened = {'writes_enabled': True, 'disabled': ['read_text_file']}
            for policy in (tightened, tightened):
                saved = await save(runtime, B, 'policy', policy)
                assert saved.status_code == 200, saved.text
                assert {p: s.starts for p, s in supervisors.items()} == starts
                assert 'read_text_file' not in await listed(client, '/mcp', sessions[B])
                assert 'read_text_file' in spec_env(runtime, B)['NEXTCLOUD_MCP_DISABLED_TOOLS'].split(',')
            refused = await client.post('/mcp', headers={**sessions[B], 'Content-Type': 'application/json'}, json={
                'jsonrpc': '2.0', 'id': 9, 'method': 'tools/call', 'params': {
                    'name': 'read_text_file', 'arguments': {'path': 'a.txt'}}})
            assert refused.status_code == 200 and refused.json()['error']['code'] == UNKNOWN_TOOL
            saved = await save(runtime, B, 'policy', {'writes_enabled': True, 'disabled': []})
            assert saved.status_code == 200, saved.text
            assert {p: s.starts for p, s in supervisors.items()} == {**starts, B: starts[B] + 1}
            for p in ('default', C):
                assert (directory(data, p) / 'state.json').read_bytes() == other_states[p]
                assert 'read_text_file' in await listed(client, '/mcp', sessions[p])


@pytest.mark.parametrize('status', ['stopped', 'backoff', 'failed', 'blocked'])
async def test_policy_widening_does_not_start_a_stopped_child(tmp_path, log_scan, status):
    data, children = setup(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        supervisor = runtime.manager.get(B).runtime.supervisor
        tightened = {'writes_enabled': True, 'disabled': ['read_text_file']}
        assert (await save(runtime, B, 'policy', tightened)).status_code == 200
        await supervisor.stop()
        supervisor.status = status
        starts = supervisor.starts
        saved = await save(runtime, B, 'policy', {'writes_enabled': True, 'disabled': []})
        assert saved.status_code == 200, saved.text
        assert supervisor.starts == starts and supervisor.status == status
        assert 'read_text_file' not in supervisor.spec.env['NEXTCLOUD_MCP_DISABLED_TOOLS'].split(',')
        await supervisor.start()
        assert supervisor.starts == starts + 1
        assert 'read_text_file' not in supervisor.spec.env['NEXTCLOUD_MCP_DISABLED_TOOLS'].split(',')


async def test_a_tightened_policy_is_what_the_next_launch_of_a_running_child_uses(tmp_path, log_scan):
    """Train A review F-2 (the 11/20 PaaS-aligned rule, woow-mcp-server apps/nextcloud/nextcloud_mcp_admin/tool_policy.py):
    a tightening save does not restart the running child, so its environment keeps the wider DISABLED_TOOLS until it
    next launches; the gateway refuses the tool at once (previous test). The stale window must close by itself:
    a crash restart or a later explicit start (supervisor.start) builds its environment from the tightened policy,
    never from the one the child first started with."""
    data, children = setup(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        supervisor = runtime.manager.get(B).runtime.supervisor
        started_with = supervisor.spec.env['NEXTCLOUD_MCP_DISABLED_TOOLS'].split(',')
        assert 'read_text_file' not in started_with
        starts = supervisor.starts
        saved = await save(runtime, B, 'policy', {'writes_enabled': True, 'disabled': ['read_text_file']})
        assert saved.status_code == 200, saved.text
        assert supervisor.starts == starts  # tightening does not restart (PaaS apply_after_update: widened only)
        await supervisor.stop()
        await supervisor.start()
        assert supervisor.starts == starts + 1
        assert 'read_text_file' in supervisor.spec.env['NEXTCLOUD_MCP_DISABLED_TOOLS'].split(',')


async def test_switched_off_a_policy_save_restarts_the_only_child_as_today(tmp_path, log_scan, switched_off):
    """The single-profile mode also preserves its child on tightening; the answer has no echo."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    journal = Journal()
    async with production_runtime(PRODUCT, data, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        assert not features.enabled(PRODUCT)
        log_scan.watch(*all_tokens(data))
        journal.watch(data, 'default')
        token = stored(data)['token']
        async with runtime.admin() as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            saved = await admin.put('/api/policy', json={'writes_enabled': False, 'disabled': ['upload_file']},
                                    headers=reviewed_headers(boot, ADMIN))
        assert saved.status_code == 200 and list(saved.json()) == ['saved', 'configuration'], saved.text
        assert stored(data)['disabled'] == ['upload_file'] and stored(data)['token'] == token
        assert journal.events == []


# ---- switched off: today's save (plan 3.3) ----

async def test_switched_off_a_changed_account_keeps_todays_answer_order_and_token(tmp_path, log_scan, switched_off):
    """A Nextcloud not switched on keeps today's behaviour for its only profile: a username saved anew
    (backend/patch), another server with the app password (PUT backend), a URL moved to another server without it
    (backend/patch: DQ-40 ⑨ is behind the switch too) and the host in capitals are written first, then the child
    restarts (the state on disk already holds the new account when the child stops); the answer is {"saved",
    "configuration"}; the token and its history stay and are still served."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    journal = Journal()
    async with production_runtime(PRODUCT, data, supervisor=journal.supervisor()) as runtime:
        await settle(runtime, 'configured')
        assert not features.enabled(PRODUCT)
        log_scan.watch(*all_tokens(data))
        log_scan.watch(NEW_PASSWORD, *WATCHED_USERS, *WATCHED_HOSTS, kind='secret')
        journal.watch(data, 'default')
        token = stored(data)['token']
        steps = (('backend/patch', lambda current: {'changes': {'username': NEW_USER}}),
                 ('backend', lambda current: {'connection': {**current, 'url': 'https://other.nextcloud.invalid/nc'}}),
                 ('backend/patch', lambda current: {'changes': {'url': SERVER}}),
                 ('backend/patch', lambda current: {'changes': {'url': 'https://CLOUD.nextcloud.invalid/nc'}}))
        async with runtime.admin() as admin:
            for route, body in steps:
                boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
                saved = await admin.put('/api/' + route, json=body(stored(data)['connection']),
                                        headers=reviewed_headers(boot, ADMIN))
                assert saved.status_code == 200, (route, saved.text)
                assert list(saved.json()) == ['saved', 'configuration'] and saved.json()['saved'] is True
        state = stored(data)
        assert state['token'] == token and 'token_history' not in state
        assert (state['connection']['url'], state['connection']['username']) == (
            SERVER, NEW_USER)
        assert journal.events == [('stop', token, NEW_USER), ('start', NEW_USER)] * len(steps)
        async with runtime.mcp() as client:
            for path, headers in paths(token):
                assert (await client.post(path, headers=headers, json=initialize_message())).status_code == 200


# ---- only a profile's own token reaches its child (T-05; I1), both switch modes ----

async def test_only_a_profiles_own_token_reaches_its_child(tmp_path, log_scan):
    """Switched on, default, B and C: each token opens a session with its own child on both paths; B's token rotated
    away and C's revoked one are refused as any unknown token (Bearer 401, secret path 404), as is a random one; the
    default profile's secret path with B's Authorization is the default profile's (the secret path never reads the
    header) and X-MCP-Profile on 8081 changes nothing (FM-29); B's session is unknown with the default profile's token
    (its child never opened it)."""
    data, children = setup(tmp_path, extras=(B, C))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        child = {'default': children.by_port[3000], B: children.by_port[PORTS[B]], C: children.by_port[PORTS[C]]}
        for profile_id in child:
            assert await opened_by(runtime, runtime.token(profile_id), child[profile_id]), profile_id
        old_b, old_c, unknown = runtime.token(B), runtime.token(C), secrets.token_urlsafe(32)
        log_scan.watch(unknown)
        for profile_id, action in ((B, 'rotate'), (C, 'revoke')):
            async with runtime.admin(profile_id) as admin:
                boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
                changed = await admin.post('/api/token/' + action, headers=reviewed_headers(boot, ADMIN))
                assert changed.status_code == 200, (action, changed.text)
        new_b = runtime.token(B)
        log_scan.watch(new_b)
        assert new_b not in (None, old_b) and runtime.token(C) is None
        for token in (old_b, old_c, unknown):
            assert await refused_everywhere(runtime, token)
        assert await opened_by(runtime, new_b, child[B])
        default = runtime.token('default')
        async with runtime.mcp() as client:
            crossed = await client.post(f'/private_{default}/mcp', headers={**ACCEPT, 'Authorization': 'Bearer ' + new_b},
                                        json=initialize_message())
            assert crossed.status_code == 200 and crossed.headers['mcp-session-id'] in child['default'].sessions
            switched = await client.post('/mcp', headers={**bearer(default), 'X-MCP-Profile': B},
                                         json=initialize_message())
            assert switched.status_code == 200 and switched.headers['mcp-session-id'] in child['default'].sessions
            theirs = await session_of(client, '/mcp', bearer(new_b))
            elsewhere = await client.post('/mcp', headers={**theirs, 'Authorization': 'Bearer ' + default,
                                                           'Content-Type': 'application/json'},
                                          json={'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'})
            assert elsewhere.status_code == 404


async def test_switched_off_profile_data_is_dormant_and_only_the_default_token_serves(tmp_path, log_scan,
                                                                                    switched_off):
    """The same disk with Nextcloud not switched on (a release without the switch, plan 3.3): the boot guard revokes
    B's and C's tokens (dormant profiles, I13), so they are refused as unknown tokens on both paths; the default
    profile's token still opens its child's session on both paths, as today."""
    data, children = setup(tmp_path, extras=(B, C))
    tokens = {profile_id: stored(directory(data, profile_id))['token'] for profile_id in (B, C)}
    async with multi_profile_runtime(PRODUCT, data, children=children, switch=False) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        assert runtime.manager is None and not features.enabled(PRODUCT)
        for profile_id, token in tokens.items():
            assert stored(directory(data, profile_id))['token'] is None, profile_id
            assert await refused_everywhere(runtime, token), profile_id
        assert await opened_by(runtime, runtime.token('default'), children.by_port[3000])


# ---- two real Nextcloud children, two users of one server (T-04 and T-23 locally; the HAOS test's shape) ----

ALICE, BOB, CAROL = 'DUMMY-alice', 'DUMMY-bob', 'DUMMY-carol'
PASSWORDS = {ALICE: 'DUMMY-alice-app-password', BOB: 'DUMMY-bob-app-password', CAROL: 'DUMMY-carol-app-password'}
WRONG_PASSWORD = 'DUMMY-bob-wrong-app-password'
HOMES = {ALICE: {'alice-notes.md': '# Alice\n'}, BOB: {'bob-plan.md': '# Bob\n'}, CAROL: {'carol-tasks.md': '# Carol\n'}}


def file_props(text):
    return (f'<d:resourcetype/><d:getcontentlength>{len(text.encode())}</d:getcontentlength>'
            '<d:getlastmodified>Wed, 07 Oct 2026 12:00:00 GMT</d:getlastmodified><d:getetag>"one"</d:getetag>'
            '<d:getcontenttype>text/plain</d:getcontenttype>')


class Cloud(Quiet):
    """One fake Nextcloud server with several users (tests/nextcloud_fixtures.py's shapes: the OCS user, a WebDAV
    listing of the home folder, a file's GET). users: login -> (app password, {file name: text}); a request without a
    user's exact credentials gets 401, a user's home answers that user only (another user's: 404). seen: every request
    as (the login presented, whether its credentials were accepted, method, path)."""
    users = {}
    seen = []

    def presented(self):
        header = self.headers.get('Authorization', '')
        if not header.startswith('Basic '):
            return None, None
        try:
            login, _, password = base64.b64decode(header[6:], validate=True).decode().partition(':')
        except ValueError:
            return None, None
        return login, password

    def nextcloud(self):
        length = int(self.headers.get('Content-Length') or 0)
        if length:
            self.rfile.read(length)
        login, password = self.presented()
        account = self.users.get(login)
        accepted = account is not None and password == account[0]
        self.seen.append((login, accepted, self.command, self.path))
        if not accepted:
            return respond(self, 401, {}, b'')
        files = account[1]
        if self.path == OCS_PATH and self.command == 'GET':
            body = json.dumps({'ocs': {'meta': {'status': 'ok', 'statuscode': 200}, 'data': {'id': login}}}).encode()
            return respond(self, 200, {'Content-Type': 'application/json'}, body)
        home = f'/remote.php/dav/files/{login}/'
        path = unquote(urlsplit(self.path).path)
        if not path.startswith(home):
            return respond(self, 404, {}, b'')
        name = path[len(home):].strip('/')
        if self.command == 'PROPFIND' and name == '':
            entries = [(home, '<d:resourcetype><d:collection/></d:resourcetype><d:getetag>"home"</d:getetag>')]
            entries += [(home + quote(file), file_props(text)) for file, text in sorted(files.items())]
            return respond(self, 207, {'Content-Type': 'application/xml; charset=utf-8'}, multistatus(entries))
        if self.command == 'GET' and name in files:
            return respond(self, 200, {'Content-Type': 'text/plain', 'ETag': '"one"'}, files[name].encode())
        return respond(self, 404, {}, b'')

    do_GET = do_PROPFIND = nextcloud


def cloud(passwords):
    """A Cloud of ALICE, BOB and CAROL, whose app passwords are passwords (one per login)."""
    return type('Cloud', (Cloud,), {'users': {login: (passwords[login], HOMES[login]) for login in HOMES}, 'seen': []})


def account(url, login, password=None):
    return {'url': url, 'username': login, 'app_password': password or PASSWORDS[login]}


def configure_store(data, connection):
    """The default profile's account saved before the runtime starts (configure's way: Store.update)."""
    store = ProductStore(data, PRODUCT)
    try:
        store.update(connection=connection)
    finally:
        store.close()


async def tool(client, path, headers, ident, name, arguments):
    """A tools/call in the session of headers: the tool's structured result."""
    result = await rpc(client, path, headers, {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
                                               'params': {'name': name, 'arguments': arguments}})
    assert result.get('isError') is not True, result
    return result.get('structuredContent') or json.loads(result['content'][0]['text'])


def home_files(tree):
    return sorted(entry['name'] for entry in tree['entries'])


def running_its_program(supervisor):
    """Whether the child of supervisor runs its spec's own program now (an additional profile's child starts through
    HM-09's exec wrapper first: tests/test_backend_loopback.py's check, which that module cannot be imported for here:
    it loads the backend policy, whose client classes need httpx.AsyncClient as the runtime harness replaces it)."""
    process, spec = supervisor.process, supervisor.spec
    if process is None or spec is None:
        return False
    try:
        return proc_cmdline(process.pid) == list(spec.argv)
    except OSError:
        return False


def real_ready(runtime, profile_ids):
    """Every one of profile_ids runs its real child, which answered its last health check."""
    entries = [runtime.manager.get(profile_id).runtime for profile_id in profile_ids]
    return (all(running_its_program(entry.supervisor) for entry in entries)
            and all(entry.health.availability()['ready'] for entry in entries))


def child_answer(port, headers):
    """A direct initialize to the child listening on port (T-23: the gateway is not in the way)."""
    async def send():
        async with httpx.AsyncClient(timeout=10) as child:
            return await child.post(f'http://127.0.0.1:{port}/mcp', headers=headers, json=initialize_message())
    return send()


async def test_two_users_of_one_server_stay_in_their_own_profiles_with_real_children(tmp_path, log_scan,
                                                                                       monkeypatch):
    """The default profile is ALICE and B is BOB, two users of one fake Nextcloud server, each served by its own real
    Nextcloud child (the HAOS test's shape: two Nextcloud users whose WebDAV cannot see each other).

    - T-05 / T-04: each token, on both paths, opens a session with its own child (not the gateway's own) and lists its
      own user's home only; the server saw each user's credentials only on that user's own paths; a random token is
      refused (401, 404); the default profile's secret path with B's Authorization lists ALICE's home.
    - T-23: each child serves its own child bearer only: none, a random one, the other profile's, an empty header, the
      scheme alone and two headers get 401.
    - T-07: tightening keeps both sessions; widening restarts only B and invalidates B's old session.
    - T-03: B's account changed to CAROL (username and app password) rotates B's token: the old one is refused on both
      paths, the new one lists CAROL's home through B's restarted child."""
    monkeypatch.setattr(health_module, 'HEALTH_INTERVAL', 0.5)
    server = cloud(PASSWORDS)
    with serve(server) as url, loopback_backends.allowed():
        data = tmp_path / 'data'
        configure_store(data, account(url, ALICE))
        create_profile(data, PRODUCT, B, label=LABELS[B], port=free_port(), configured=False)
        update_profile(data, PRODUCT, B, connection=account(url, BOB))
        log_scan.watch(*all_tokens(data))
        log_scan.watch(*PASSWORDS.values(), kind='secret')
        log_scan.watch(LABELS[B], kind='name')
        async with multi_profile_runtime(PRODUCT, data, supervisor=lifecycle.Supervisor, real_children=True,
                                         default_port=free_port()) as runtime:
            await until(lambda: real_ready(runtime, ('default', B)), timeout=60)
            supervisors = {p: runtime.manager.get(p).runtime.supervisor for p in ('default', B)}
            ports = {p: runtime.manager.get(p).runtime.port for p in ('default', B)}
            pids = {p: supervisor.process.pid for p, supervisor in supervisors.items()}
            owners = {'default': ALICE, B: BOB}
            async with runtime.mcp() as client:
                sessions = {}
                for profile_id, login in owners.items():
                    token = runtime.token(profile_id)
                    for path, headers in paths(token):
                        session = await session_of(client, path, headers)
                        assert not session['Mcp-Session-Id'].startswith('woow-local-'), (profile_id, path)
                        tree = await tool(client, path, session, 2, 'get_file_tree', {'path': '', 'depth': 1})
                        assert home_files(tree) == sorted(HOMES[login]), (profile_id, path)
                        sessions.setdefault(profile_id, (path, session))
                unknown = secrets.token_urlsafe(32)
                log_scan.watch(unknown)
                assert [answer(await client.post(path, headers=headers, json=initialize_message()))
                        for path, headers in paths(unknown)] == [BEARER_REQUIRED, NOT_FOUND]
                crossed = await session_of(client, f'/private_{runtime.token("default")}/mcp',
                                           {**ACCEPT, 'Authorization': 'Bearer ' + runtime.token(B)})
                tree = await tool(client, f'/private_{runtime.token("default")}/mcp', crossed, 3, 'get_file_tree', {})
                assert home_files(tree) == sorted(HOMES[ALICE])
                for login, accepted, _method, path in server.seen:
                    if path.startswith('/remote.php/dav/files/'):
                        assert accepted and path.startswith(f'/remote.php/dav/files/{login}/'), (login, path)
                # T-23: each real child serves its own child bearer only.
                child_tokens = {p: stored(directory(data, p))['child_token'] for p in owners}
                for profile_id, port in ports.items():
                    other = 'Bearer ' + child_tokens[B if profile_id == 'default' else 'default']
                    own = 'Bearer ' + child_tokens[profile_id]
                    # tests/test_child_bearer.py's refusals: none, a random token, the other profile's, an empty
                    # header, the scheme alone, two headers (both its own, or its own then the other's)
                    for values in ([], ['Bearer ' + secrets.token_urlsafe(32)], [other], [''], ['Bearer'], [own, own],
                                   [own, other]):
                        headers = [('Accept', ACCEPT['Accept'])] + [('Authorization', value) for value in values]
                        assert (await child_answer(port, headers)).status_code == 401, (profile_id, len(values))
                    assert (await child_answer(port, {**ACCEPT, 'Authorization': own})).status_code == 200
                # Tightening is enforced by the gateway without invalidating either session.
                saved = await save(runtime, B, 'policy', {'writes_enabled': True, 'disabled': ['read_text_file']})
                assert saved.status_code == 200 and saved.json()['profile'] == {'id': B}, saved.text
                assert supervisors[B].process.pid == pids[B]
                assert supervisors['default'].process.pid == pids['default']
                default_path, default_session = sessions['default']
                b_path, b_session = sessions[B]
                assert 'read_text_file' in await listed(client, default_path, default_session)
                assert 'read_text_file' not in await listed(client, b_path, b_session)
                # Widening restarts only B so its child registers the enabled tool.
                saved = await save(runtime, B, 'policy', {'writes_enabled': True, 'disabled': []})
                assert saved.status_code == 200
                await until(lambda: real_ready(runtime, (B,)) and supervisors[B].process.pid != pids[B], timeout=60)
                assert supervisors['default'].process.pid == pids['default']
                gone = await client.post(b_path, headers={**b_session, 'Content-Type': 'application/json'},
                                         json={'jsonrpc': '2.0', 'id': 4, 'method': 'tools/list'})
                assert gone.status_code == 404
                fresh = await session_of(client, '/mcp', bearer(runtime.token(B)))
                assert 'read_text_file' in await listed(client, '/mcp', fresh)
                # T-03: B's account changed to CAROL rotates B's token.
                old = runtime.token(B)
                rotated = await save(runtime, B, 'backend/patch', {'changes': {'username': CAROL,
                                                                               'app_password': PASSWORDS[CAROL]}})
                assert rotated.status_code == 200 and rotated.json()['token_rotated'] is True, rotated.text
                new = runtime.token(B)
                log_scan.watch(new)
                assert new != old
                await until(lambda: real_ready(runtime, (B,)), timeout=60)
                assert [answer(await client.post(path, headers=headers, json=initialize_message()))
                        for path, headers in paths(old)] == [BEARER_REQUIRED, NOT_FOUND]
                carol = await session_of(client, '/mcp', bearer(new))
                tree = await tool(client, '/mcp', carol, 5, 'get_file_tree', {})
                assert home_files(tree) == sorted(HOMES[CAROL])
                assert supervisors['default'].process.pid == pids['default']


async def test_a_refused_login_backs_off_only_its_own_profile(tmp_path, log_scan, monkeypatch):
    """DQ-25, FM-69 (contract 7): B (BOB with a wrong app password) and the default profile (ALICE) on one Nextcloud
    server. B's health checks back off (the auth backoff, shortened here: 0.3, 0.6, 1.2 s ...) while its real child sends
    one failed login only, whatever the number of checks (its authentication latch: a 401 latches until the child
    restarts); the default profile's checks keep their interval and its backend stays reachable, and only B's log line
    says it backs off. The app password saved anew (no new account: the token stays) restarts B's child, resets B's
    backoff and makes B's backend reachable. Whether Nextcloud throttles by source address (the add-on's one address)
    stays open (UC-12)."""
    monkeypatch.setattr(health_module, 'HEALTH_INTERVAL', 0.2)
    monkeypatch.setattr(profile_runtime, 'AUTH_BACKOFF', (0.3, 0.6, 1.2, 2.4, 4.8))
    server = cloud(PASSWORDS)
    with serve(server) as url, loopback_backends.allowed():
        data = tmp_path / 'data'
        configure_store(data, account(url, ALICE))
        create_profile(data, PRODUCT, B, label=LABELS[B], port=free_port(), configured=False)
        update_profile(data, PRODUCT, B, connection=account(url, BOB, WRONG_PASSWORD))
        log_scan.watch(*all_tokens(data))
        log_scan.watch(*PASSWORDS.values(), WRONG_PASSWORD, kind='secret')
        log_scan.watch(LABELS[B], kind='name')
        async with multi_profile_runtime(PRODUCT, data, supervisor=lifecycle.Supervisor, real_children=True,
                                         default_port=free_port()) as runtime:
            default, extra = (runtime.manager.get(p).runtime for p in ('default', B))
            token = runtime.token(B)
            await until(lambda: extra.health.auth_refusals >= 3, timeout=60)
            assert extra.health.next_interval() in (1.2, 2.4)
            refused = [entry for entry in server.seen if entry[0] == BOB]
            assert [accepted for _, accepted, _, _ in refused] == [False], 'one failed login per child start'
            assert default.health.auth_refusals == 0 and default.health.availability()['backend'] == 'reachable'
            logins = sum(1 for login, accepted, _, _ in server.seen if login == ALICE and accepted)
            await until(lambda: sum(1 for login, accepted, _, _ in server.seen if login == ALICE and accepted)
                        >= logins + 3, timeout=30)
            lines = [record.getMessage() for record in log_scan.records
                     if 'the backend refused the credentials' in record.getMessage()]
            assert lines and all(f'[profile={B[:8]} ' in line for line in lines), lines
            saved = await save(runtime, B, 'backend/patch', {'changes': {'app_password': PASSWORDS[BOB]}})
            assert saved.status_code == 200 and 'token_rotated' not in saved.json(), saved.text
            await until(lambda: extra.health.availability()['backend'] == 'reachable', timeout=60)
            assert extra.health.auth_refusals == 0 and runtime.token(B) == token
            assert [accepted for login, accepted, _, _ in server.seen if login == BOB].count(False) == 1

@pytest.mark.parametrize('suffix', ['/index.php/apps/files/', '/remote.php/dav/files/user', '/ocs/v2.php',
                                   '/apps/files', '/login', '/settings/user'])
def test_paas_page_urls_normalize_to_nextcloud_root(suffix):
    from mcp_admin_core.products import normalize_nextcloud_url
    assert normalize_nextcloud_url(' HTTPS://Cloud.Nextcloud.INVALID:443/nc' + suffix + ' ') == 'https://cloud.nextcloud.invalid/nc'


def test_nextcloud_normalization_checks_the_entire_original_path():
    from mcp_admin_core.products import normalize_nextcloud_url
    with pytest.raises(ValueError):
        normalize_nextcloud_url('https://cloud.nextcloud.invalid/nc/apps/../secret')

@pytest.mark.parametrize('route', ['backend', 'backend/patch'])
async def test_normalized_credentials_and_legacy_url_on_save(tmp_path, log_scan, route):
    data, children = setup(tmp_path)
    legacy = 'HTTPS://CLOUD.nextcloud.invalid:443/nc/index.php/apps/files'
    update_profile(data, PRODUCT, B, connection={**ACCOUNTS[B], 'url': legacy, 'username': 'alice+files@example.com'})
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        token = runtime.token(B)
        before = stored(directory(data, B))['connection']
        changes = {'url': '  ' + SERVER + '  ', 'username': ' alice+files@example.com ',
                   'app_password': ' DUMMY-néw-password '}
        reply = await save(runtime, B, route, body_of(route, before, changes))
        assert reply.status_code == 200, reply.text
        after = stored(directory(data, B))
        assert after['token'] == token and 'token_rotated' not in reply.json()
        assert after['connection'] == {'url': legacy, 'username': 'alice+files@example.com',
                                       'app_password': 'DUMMY-néw-password'}
