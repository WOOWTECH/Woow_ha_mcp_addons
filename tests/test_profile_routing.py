"""HM-08: which profile an MCP request on 8081 belongs to, once the product is switched on (multi-profile plan 5.1;
contract 2.2, 2.3, 4.2; invariants I1, I2, I3; DQ-01 (a), DQ-09, DQ-12, DQ-19; FM-05, 13, 14, 27, 28, 29, 30, 32).

The dispatcher (profile_router.McpDispatcher) only looks at the path and the Authorization header: /private_<token>/mcp
by the default app's own route matcher, /mcp by exactly one literal "Bearer <token>". The candidate is hashed once and
compared with every routable profile's token digest (the default profile and every indexed profile it could read), all
of them, with no early exit. Exactly one match: that profile's own app checks the token again with its own store. No
match: the default profile's app answers, byte for byte as today (404 on the secret path, 401 on /mcp). Two or more
(only a copied directory or a hand edit makes that): 503 {"error":"state unavailable"}, no profile served, one WARNING
per group a minute. An unusable index (corrupt, or changed behind the add-on's back: until a restart) or an unreadable
default state: 503 for every token, the default profile's included (DQ-12), and /health/ready not ready (it speaks for
the default profile only, DQ-19). 8081 never reads X-MCP-Profile, a cookie or the query to choose (FM-29).

Every case runs the production runtime (tests/multi_profile_runtime.py) with the product switched on for the test, and
every test runs under the HM-01 log scan (tokens, child tokens, credentials and profile labels watched).
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import statistics
import time

import httpx
import pytest

from admin_write_headers import reviewed_headers
from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import (Children, SWITCHABLE, create_profile, ids, multi_profile_runtime, stored,
                                   update_profile)
from mcp_admin_core import profiles
from mcp_admin_core.products import PROBES
from test_mcp_contract_freeze import CHANGES, child_problems, contract, expectation, placeholders, raw_http, request_of
from test_profile_runtime import ProfileChild
from test_single_profile_golden import (ACCEPT, ADMIN, BEARER_REQUIRED, NOT_FOUND, READY, MockChild, answer, configure,
                                        initialize_body, initialize_message, settle)

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'odoo'
B, C, D, E, F = ids(5)
LABELS = {B: 'Beta Ops', C: 'Gamma Ops', D: 'Delta Ops', E: 'Epsilon Ops', F: 'Zeta Ops'}
# The two contract cases whose request carries B's token where the server may read it: 8081 serves B there.
B_SERVED = ('cross-bearer-b', 'switch-x-mcp-profile-default-on-b-url')
STATE_UNAVAILABLE = (503, [('content-length', '29'), ('content-type', 'application/json')],
                     b'{"error":"state unavailable"}')


def router():
    import mcp_admin_core.profile_router as module  # imported when a test runs (the red half of red-green)
    return module


def bearer(token):
    return {**ACCEPT, 'Authorization': 'Bearer ' + token}


def paths(token):
    return (('/mcp', bearer(token)), (f'/private_{token}/mcp', dict(ACCEPT)))


def watch(log_scan, data):
    """Every token, child token and credential stored under data, and every label (the log scan's needles)."""
    for path in [Path(data) / 'state.json', *sorted((Path(data) / 'profiles').glob('*/state.json'))]:
        if path.exists():
            value = json.loads(path.read_text())
            log_scan.watch(*(v for v in (value['token'], value['child_token']) if v))
    log_scan.watch(*LABELS.values(), kind='name')


def warnings_of(log_scan, module='profile_router'):
    """The WARNING lines of mcp_admin_core.<module> (the dispatcher's: profile_router; the manager's startup lines:
    profile_runtime)."""
    return [record.getMessage() for record in log_scan.records
            if record.name == 'mcp_admin_core.' + module and record.levelname == 'WARNING']


def setup_profiles(tmp_path, product=PRODUCT, extras=(B, C), configured=True):
    """The default profile (configured as the golden one) and the additional profiles (ports 18000 and up)."""
    data = tmp_path / 'data'
    configure(data, product)
    for number, profile_id in enumerate(extras):
        create_profile(data, product, profile_id, label=LABELS[profile_id], port=18000 + number,
                       configured=configured)
    return data


def golden_children(data, product, extras=(B, C)):
    """Every profile's golden MockChild (its own child bearer, sessions and health-check filter) on its port."""
    children = Children()
    children.add(3000, MockChild(product, data))
    for number, profile_id in enumerate(extras):
        children.add(18000 + number, MockChild(product, profiles.Layout(data).profile(profile_id)))
    return children


def profile_children(data, product, extras=(B, C)):
    children = Children()
    children.profile_child(3000, 'default', product, data)
    for number, profile_id in enumerate(extras):
        children.profile_child(18000 + number, 'p' + profile_id[:4], product, profiles.Layout(data).profile(profile_id))
    return children


async def change_token(runtime, profile_id, action):
    """The panel's token rotate or revoke on one profile's management app (CSRF, If-Match, Idempotency-Key)."""
    async with runtime.admin(profile_id) as admin:
        boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
        response = await admin.post('/api/token/' + action, headers=reviewed_headers(boot, ADMIN))
        assert response.status_code == 200, action
        return response.json().get('token')


async def connects(runtime, client, token):
    """Both paths of token open a session (initialize 200)."""
    for path, headers in paths(token):
        response = await client.post(path, headers=headers, json=initialize_message())
        assert response.status_code == 200, path.replace(token, '<token>')


def response_problems(document, key, product, status, headers, body):
    response = document['responses'][key]
    found = []
    if status != response['status']:
        found.append(f'status {status} != {response["status"]}')
    names = {}
    for name, value in headers:
        names.setdefault(name, []).append(value)
    for name, value in response.get('headers', {}).items():
        if names.get(name) != [value]:
            found.append(f'header {name} {names.get(name)} != [{value!r}]')
    found += [f'header {name} present' for name in response.get('absent', []) if name in names]
    wanted = initialize_body(product) if response['body'] == '<initialize>' else response['body'].encode()
    if body != wanted:
        found.append(f'body {body[:80]!r} != {wanted[:80]!r}')
    return found


# ---- the contract cases (HM-01's profiles_v1_cases.json) on every profile ----

@pytest.mark.parametrize('product', SWITCHABLE)
async def test_the_contract_cases_route_by_token_alone(tmp_path, log_scan, product):
    """Every HM-01 contract case (the 31 URL variants, the unknown tokens, the header switches, the order- cases, the
    two cross cases of I1) on the real listener, twice: A the default profile's token and B an additional profile's,
    then the other way round; P24, the X-MCP-Profile value of the switch cases, is a third profile's real id. A case the
    default profile served in HM-01 is served by A's profile, its child only; the two cases that put B's token where the
    server may read it (cross-bearer-b, Bearer B; switch-x-mcp-profile-default-on-b-url, B's secret URL with
    X-MCP-Profile: default) are served by B; every other case gets HM-01's answer and reaches no child. On the secret
    path the Authorization header is never read (switch-authorization: A's path, Bearer B: A serves; T-05, I1).
    Then each profile's token is rotated and revoked through its own management app: the old token gets the bytes of
    any wrong token on both paths, the new one connects, and every other profile keeps connecting (I3)."""
    document = contract()
    data = setup_profiles(tmp_path, product)
    children = golden_children(data, product)
    failures = []
    async with multi_profile_runtime(product, data, sockets=True, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        child = {'default': children.by_port[3000], B: children.by_port[18000], C: children.by_port[18001]}

        async def send(cases, a, b, values, label=''):
            for case in cases:
                method, target, headers, body = request_of(case, values)
                since = {profile_id: len(mock.requests) for profile_id, mock in child.items()}
                status, answered, content = await raw_http(runtime.mcp_port, method, target, headers, body)
                reached = {profile_id for profile_id, mock in child.items() if mock.forwarded(since[profile_id])}
                if case['id'] in B_SERVED:
                    key, served = 'initialize', {b}
                else:
                    expected = expectation(case, product)
                    key, served = expected['response'], ({a} if expected['child'] else set())
                found = response_problems(document, key, product, status, answered, content)
                if reached != served:
                    found.append(f'served by {sorted(reached)} != {sorted(served)}')
                for profile_id, mock in child.items():
                    found += child_problems(mock.requests[since[profile_id]:],
                                            stored(runtime.directory(profile_id))['child_token'])
                if found:
                    failures.append(f'{case["id"]}{label} [A={a[:8]} B={b[:8]}]: ' + '; '.join(found))

        regular = [case for case in document['cases'] if 'after' not in case]
        for a, b in (('default', B), (B, 'default')):
            values = {**placeholders(runtime.token(a), runtime.token(b)), 'P24': C}
            log_scan.watch(*(values[name] for name in ('AU', 'APA', 'R43', 'R64')))
            await send(regular, a, b, values)
        connect = [case for case in document['cases'] if case['group'] == 'connect']
        for a, others in ((B, ('default', C)), ('default', (C,))):
            for change in CHANGES:
                before = runtime.token(a)
                after = await change_token(runtime, a, change)
                assert runtime.token(a) == after and (after is None) == (change == 'revoke')
                values = {**placeholders(before, runtime.token(others[0])), 'P24': C}
                await send([case for case in document['cases'] if case.get('after') == change], a, others[0],
                           values, f' after {change}')
                if after is not None:
                    log_scan.watch(after)
                    await send(connect, a, others[0], {**values, 'A': after}, f' after {change}')
            for other in others:  # every other profile still connects: a token change stays with its profile
                values = {**placeholders(runtime.token(other), runtime.token(C)), 'P24': C}
                await send(connect, other, C, values, f' after {a[:8]} was revoked')
    detail = '\n'.join(failures)
    for profile_id in ('default', B, C):
        detail = detail.replace(stored(runtime.directory(profile_id))['child_token'], f'<child {profile_id[:8]}>')
    assert not failures, f'{product}: {len(failures)} case(s) differ:\n{detail}'


# ---- no match: the default profile's own answer ----

async def test_an_unknown_token_gets_the_default_apps_own_bytes(tmp_path, log_scan):
    """No profile holds the candidate (unknown, malformed, revoked, rotated away; no candidate at all): the dispatcher
    hands the request to the default profile's app untouched, so the answer is the default app's own, byte for byte
    (plan 5.1 point 3; A-port P1b); such a request takes no profile's admission and reaches no child."""
    data = setup_profiles(tmp_path)
    children = golden_children(data, PRODUCT)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        old_b = runtime.token(B)
        await change_token(runtime, C, 'revoke')
        assert stored(runtime.directory(C))['token'] is None
        new_b = await change_token(runtime, B, 'rotate')  # the old B token is now held by nobody
        log_scan.watch(new_b)
        unknown = secrets.token_urlsafe(32)
        log_scan.watch(unknown)
        requests = []
        for token in (unknown, old_b, 'default', B, 'x', ''):
            requests += [('POST', f'/private_{token}/mcp', ACCEPT), ('GET', f'/private_{token}/mcp', ACCEPT),
                         ('PUT', f'/private_{token}/mcp', ACCEPT),
                         ('POST', '/mcp', {**ACCEPT, 'Authorization': 'Bearer ' + token})]
        requests += [('POST', '/mcp', ACCEPT), ('POST', '/mcp', {**ACCEPT, 'Authorization': 'bearer ' + new_b}),
                     ('POST', '/mcp', {**ACCEPT, 'Authorization': 'Bearer  ' + new_b}),
                     ('POST', '/mcp/', bearer(new_b)), ('POST', f'/private_{new_b}/mcp/', ACCEPT),
                     ('POST', '/no-such-path', bearer(new_b)), ('GET', '/health/ready', {}),
                     ('GET', '/health/ready/', {}), ('POST', f'/private_{new_b}', ACCEPT)]
        default_app = runtime.manager.get('default').runtime.mcp_app
        since = {port: len(mock.requests) for port, mock in children.by_port.items()}
        async with runtime.mcp() as through, httpx.AsyncClient(transport=httpx.ASGITransport(app=default_app),
                                                               base_url='http://mcp') as direct:
            for method, path, headers in requests:
                content = None if method in ('GET', 'PUT') else json.dumps(initialize_message()).encode()
                plain = {**headers, 'Content-Type': 'application/json'} if content else headers
                got = answer(await through.request(method, path, headers=plain, content=content))
                want = answer(await direct.request(method, path, headers=plain, content=content))
                label = path.replace(new_b, '<B>').replace(old_b, '<old B>').replace(unknown, '<unknown>')
                assert got == want, (method, label)
            # Two Authorization headers: no candidate; the default app's 401.
            got = answer(await through.post('/mcp', headers=[('Accept', ACCEPT['Accept']),
                                                             ('Authorization', 'Bearer ' + new_b),
                                                             ('Authorization', 'Bearer ' + new_b)],
                                            json=initialize_message()))
            assert got == BEARER_REQUIRED
        assert all(mock.forwarded(since[port]) == [] for port, mock in children.by_port.items())
        assert all(entry.gate.active == 0 and runtime.manager.budget.used(entry.profile_id) == 0
                   for entry in runtime.manager.profiles())  # HM-31: the bytes are the add-on's budget's


# ---- two profiles, one token (I2, DQ-09) ----

@pytest.mark.parametrize('copy', ['directory', 'default token'])
async def test_a_token_two_profiles_hold_is_refused_and_logged_once_a_minute(tmp_path, log_scan, copy):
    """A profile directory copied into another (its token and child token with it), or the default profile's token in
    an additional profile: the shared token gets 503 {"error":"state unavailable"} on both paths, no profile serves it,
    no child is reached; every other token works (I2, DQ-09). One WARNING a minute for the group, naming the profiles
    by their id's first 8 characters (default for the default profile) and never the token; the next one names how
    many it suppressed (PaaS test_token_duplicated_in_two_profile_files_is_refused_and_logged_once_without_the_token)."""
    data = setup_profiles(tmp_path, extras=(B,))
    layout = profiles.Layout(data)
    if copy == 'directory':
        shutil.copytree(layout.profile(B), layout.profile(C))
        view = profiles.read_index(layout.index)
        profiles.write_index(layout.index, [*view.entries, profiles.IndexEntry(C, LABELS[C], 18001)], expected=view)
        shared, group = stored(layout.profile(B))['token'], (B, C)
    else:
        create_profile(data, PRODUCT, C, label=LABELS[C], port=18001)
        shared = stored(data)['token']
        update_profile(data, PRODUCT, C, token=shared)
        group = ('default', C)
    children = golden_children(data, PRODUCT)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        clock = [1000.0]
        runtime.manager.mcp_app.reports.clock = lambda: clock[0]
        since = {port: len(mock.requests) for port, mock in children.by_port.items()}
        async with runtime.mcp() as client:
            for path, headers in paths(shared):
                response = await client.post(path, headers=headers, json=initialize_message())
                assert answer(response) == STATE_UNAVAILABLE, path.replace(shared, '<shared>')
            assert all(mock.forwarded(since[port]) == [] for port, mock in children.by_port.items())
            assert all(entry.gate.active == 0 for entry in runtime.manager.profiles())
            clock[0] += 61
            response = await client.post(f'/private_{shared}/mcp', headers=ACCEPT, json=initialize_message())
            assert answer(response) == STATE_UNAVAILABLE
            for token in {runtime.token('default'), runtime.token(B)} - {shared}:
                await connects(runtime, client, token)
        lines = [line for line in warnings_of(log_scan) if 'more than one profile' in line]
        assert len(lines) == 2, lines
        for line in lines:
            assert all('profile=' + profiles.log_id(member) in line for member in group), line
        assert 'suppressed' not in lines[0] and lines[1].endswith('suppressed=1')


# ---- what cannot be read (FM-05, DQ-12) ----

async def test_a_corrupt_index_refuses_every_token_and_the_panel_still_opens(tmp_path, log_scan):
    """profiles.json is not an index (DQ-12): 503 {"error":"state unavailable"} for every token, the default profile's
    included (a duplicate token cannot be ruled out); /health/ready answers not ready (it speaks for the default profile,
    which serves nothing now; DQ-19); a path that is no MCP path still gets 404; no child is reached. The default
    profile's management app still answers (HM-10 offers the index quarantine there)."""
    data = setup_profiles(tmp_path, extras=(B,))
    index = profiles.Layout(data).index
    os.unlink(index)
    fd = os.open(index, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, b'{"version": 1, "profile_index": ')
    os.close(fd)
    children = golden_children(data, PRODUCT, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        assert runtime.manager.get(B) is None
        tokens = (runtime.token('default'), runtime.token(B), secrets.token_urlsafe(32))
        log_scan.watch(tokens[2])
        async with runtime.mcp() as client:
            for token in tokens:
                for path, headers in paths(token):
                    assert answer(await client.post(path, headers=headers, json=initialize_message())) == \
                        STATE_UNAVAILABLE
            assert answer(await client.get('/health/ready')) == READY[False]
            assert answer(await client.post('/no-such-path', json=initialize_message())) == NOT_FOUND
        for mock in children.by_port.values():
            assert mock.forwarded() == []
        async with runtime.admin() as admin:
            assert (await admin.get('/api/bootstrap', headers=ADMIN)).status_code == 200


async def test_an_index_changed_behind_the_add_ons_back_refuses_every_token_until_a_restart(tmp_path, log_scan):
    """The index the add-on read at startup is replaced (here with the very same bytes: a new inode): from the next
    request on, every token gets 503 (DQ-12, contract 2.3), also after the original file is put back; a restart
    reads the index again and serves."""
    data = setup_profiles(tmp_path, extras=(B,))
    index = profiles.Layout(data).index
    original = index.read_bytes()
    async with multi_profile_runtime(PRODUCT, data, children=profile_children(data, PRODUCT, (B,))) as runtime:
        watch(log_scan, data)
        tokens = (runtime.token('default'), runtime.token(B))
        async with runtime.mcp() as client:
            for token in tokens:
                await connects(runtime, client, token)
            replacement = index.with_name('profiles.json.new')
            fd = os.open(replacement, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.write(fd, original)
            os.close(fd)
            os.replace(replacement, index)
            for _ in range(2):
                for token in tokens:
                    for path, headers in paths(token):
                        response = await client.post(path, headers=headers, json=initialize_message())
                        assert answer(response) == STATE_UNAVAILABLE
                    assert answer(await client.get('/health/ready')) == READY[False]
                os.utime(index, ns=(1, 1))  # whatever happens to the file next: still refused until a restart
    async with multi_profile_runtime(PRODUCT, data, children=profile_children(data, PRODUCT, (B,))) as runtime:
        async with runtime.mcp() as client:
            for token in tokens:
                await connects(runtime, client, token)


async def test_an_unreadable_default_state_refuses_every_token(tmp_path, log_scan):
    """The default profile's state cannot be read: as today its token gets 503, and so does every other token, since
    a duplicate of the default profile's cannot be ruled out (contract 2.3); once it reads again, every profile
    serves."""
    data = setup_profiles(tmp_path, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=profile_children(data, PRODUCT, (B,))) as runtime:
        watch(log_scan, data)
        state = data / 'state.json'
        good = state.read_bytes()
        tokens = (runtime.token('default'), runtime.token(B))
        async with runtime.mcp() as client:
            with open(state, 'r+b') as stream:  # same inode, other bytes
                stream.write(b'{' + b' ' * (len(good) - 1))
            for token in tokens:
                for path, headers in paths(token):
                    response = await client.post(path, headers=headers, json=initialize_message())
                    assert answer(response) == STATE_UNAVAILABLE
            with open(state, 'r+b') as stream:
                stream.write(good)
            os.utime(state, ns=(time.time_ns(), time.time_ns()))
            for token in tokens:
                await connects(runtime, client, token)


@pytest.mark.parametrize('broken', ['unreadable state', 'missing directory', 'replaced directory'])
async def test_a_profile_that_cannot_be_read_is_not_routed_and_the_others_are(tmp_path, log_scan, broken):
    """An additional profile whose state cannot be read, whose directory is missing at startup, or whose directory was
    replaced while running (another inode at the same name: HM-07 review S-08) is not routed: its token gets the bytes
    of any unknown token (404 on the secret path, 401 on /mcp; FM-05: never served by another profile), while the
    default profile and every other profile serve. A profile missing at startup is named once in a WARNING by its id's
    first 8 characters."""
    data = setup_profiles(tmp_path)
    layout = profiles.Layout(data)
    token = stored(layout.profile(B))['token']
    if broken == 'missing directory':
        shutil.rmtree(layout.profile(B))
    async with multi_profile_runtime(PRODUCT, data, children=profile_children(data, PRODUCT)) as runtime:
        watch(log_scan, data)
        log_scan.watch(token)
        if broken == 'unreadable state':
            (layout.profile(B) / 'state.json').write_bytes(b'not a state')
        elif broken == 'replaced directory':
            moved = layout.profiles / ('moved-' + B)
            os.rename(layout.profile(B), moved)
            shutil.copytree(moved, layout.profile(B))
        async with runtime.mcp() as client:
            for path, headers in paths(token):
                response = await client.post(path, headers=headers, json=initialize_message())
                assert answer(response) == (NOT_FOUND if path.startswith('/private_') else BEARER_REQUIRED)
            for other in ('default', C):
                await connects(runtime, client, runtime.token(other))
        if broken == 'missing directory':
            assert runtime.manager.get(B) is None
            assert [line for line in warnings_of(log_scan, 'profile_runtime') if B[:8] in line]


async def test_an_orphan_profile_directory_is_never_routed(tmp_path, log_scan):
    """A profile directory the index does not list (an orphan: a failed deletion, a restore) is never opened or routed:
    its token gets the bytes of an unknown token; a WARNING names it once by its id's first 8 characters (plan 4.4)."""
    data = setup_profiles(tmp_path, extras=(B,))
    create_profile(data, PRODUCT, C, label=LABELS[C], port=18001, indexed=False)
    orphan = stored(profiles.Layout(data).profile(C))['token']
    async with multi_profile_runtime(PRODUCT, data, children=profile_children(data, PRODUCT)) as runtime:
        watch(log_scan, data)
        assert runtime.manager.get(C) is None
        async with runtime.mcp() as client:
            for path, headers in paths(orphan):
                response = await client.post(path, headers=headers, json=initialize_message())
                assert answer(response) == (NOT_FOUND if path.startswith('/private_') else BEARER_REQUIRED)
        assert [line for line in warnings_of(log_scan, 'profile_runtime') if C[:8] in line and 'orphan' in line]


# ---- every profile its own: tokens, policy, sessions, cookies ----

async def test_rotating_one_profile_ends_none_of_another_profiles_requests(tmp_path, log_scan):
    """A token change commits on one profile's TokenAccess only (I3, T-12): a tools/call of the default profile that
    is waiting for its child completes while B's token is rotated, and the other way round; the old B token is refused
    at once on both paths (PaaS test_profile_token_revocation_is_local, test_two_active_streams_close_on_revocation)."""
    data = setup_profiles(tmp_path, extras=(B,))
    children = profile_children(data, PRODUCT, (B,))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        async with runtime.mcp() as client:
            for waiting, rotated, port in (('default', B, 3000), (B, 'default', 18000)):
                token = runtime.token(waiting)
                init = await client.post('/mcp', headers=bearer(token), json=initialize_message())
                session = init.headers['mcp-session-id']
                child = children.by_port[port]
                child.hold()
                tool, arguments = PROBES[PRODUCT]
                call = asyncio.create_task(client.post('/mcp', headers={**bearer(token), 'Mcp-Session-Id': session},
                                                       json={'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
                                                             'params': {'name': tool, 'arguments': arguments}}))
                await asyncio.wait_for(child.held.wait(), 5)
                old = runtime.token(rotated)
                new = await change_token(runtime, rotated, 'rotate')
                log_scan.watch(new)
                for path, headers in paths(old):
                    response = await client.post(path, headers=headers, json=initialize_message())
                    assert answer(response) == (NOT_FOUND if path.startswith('/private_') else BEARER_REQUIRED)
                child.release.set()
                response = await asyncio.wait_for(call, 5)
                assert response.status_code == 200 and 'result' in response.json(), response.content[:200]
                await connects(runtime, client, new)


async def test_each_token_gets_its_own_profiles_tool_policy(tmp_path, log_scan):
    """Every profile keeps its own policy (PaaS test_profile_token_enforces_its_own_tool_policy): a tool B disabled is
    refused for B's token (-32602 Unknown tool, the child never asked) and still served for the default profile's."""
    data = setup_profiles(tmp_path, extras=(B,))
    tool, arguments = PROBES[PRODUCT]
    update_profile(data, PRODUCT, B, disabled=[tool])
    children = profile_children(data, PRODUCT, (B,))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        call = {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': tool, 'arguments': arguments}}
        async with runtime.mcp() as client:
            for profile_id, allowed in (('default', True), (B, False)):
                token = runtime.token(profile_id)
                init = await client.post('/mcp', headers=bearer(token), json=initialize_message())
                headers = {**bearer(token), 'Mcp-Session-Id': init.headers['mcp-session-id']}
                child = children.by_port[3000 if profile_id == 'default' else 18000]
                before = len(child.requests)
                body = (await client.post('/mcp', headers=headers, json=call)).json()
                if allowed:
                    assert 'result' in body and len(child.requests) == before + 1
                else:
                    assert body['error']['code'] == -32602 and body['error']['message'] == 'Unknown tool'
                    assert len(child.requests) == before


async def test_a_session_of_one_profile_is_unknown_to_another(tmp_path, log_scan):
    """A session id the default profile's child opened, sent with B's token, goes to B's child, which does not know it:
    404 (FM-32; the gateway's own sessions likewise stay with the profile whose app opened them, HM-05)."""
    data = setup_profiles(tmp_path, extras=(B,))
    children = profile_children(data, PRODUCT, (B,))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        async with runtime.mcp() as client:
            init = await client.post('/mcp', headers=bearer(runtime.token('default')), json=initialize_message())
            session = init.headers['mcp-session-id']
            for path, headers in paths(runtime.token(B)):
                response = await client.post(path, headers={**headers, 'Mcp-Session-Id': session},
                                             json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
                assert response.status_code == 404
                assert children.by_port[18000].requests[-1].headers['mcp-session-id'] == session


class CookieChild(ProfileChild):
    """A ProfileChild whose answers set a cookie naming its profile, and that records the Cookie header it gets."""

    def __init__(self, *args):
        super().__init__(*args)
        self.cookies = []

    async def __call__(self, request):
        self.cookies.append(request.headers.get('cookie'))
        response = await super().__call__(request)
        response.headers['Set-Cookie'] = f'woow-child=DUMMY-cookie-{self.name}; Path=/'
        return response


async def test_a_childs_cookie_never_reaches_another_profiles_child(tmp_path, log_scan):
    """Each profile has its own child client (HM-01 note: a client keeps the cookies its child sets and sends them back,
    to any port): the default profile's child cookie comes back to that child only, never to B's (and B's never to the
    default profile's)."""
    data = setup_profiles(tmp_path, extras=(B,))
    children = Children()
    children.add(3000, CookieChild('default', PRODUCT, data))
    children.add(18000, CookieChild('beta', PRODUCT, profiles.Layout(data).profile(B)))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        async with runtime.mcp() as client:
            for profile_id in ('default', B, 'default', B):
                await connects(runtime, client, runtime.token(profile_id))
    assert all(cookie in (None, 'woow-child=DUMMY-cookie-default') for cookie in children.by_port[3000].cookies)
    assert all(cookie in (None, 'woow-child=DUMMY-cookie-beta') for cookie in children.by_port[18000].cookies)
    assert 'woow-child=DUMMY-cookie-default' in children.by_port[3000].cookies


# ---- how the token is compared ----

async def test_every_routable_profile_is_compared_for_every_candidate(tmp_path, log_scan, monkeypatch):
    """The candidate is hashed once and compared with every routable profile's digest, with no early exit (plan 5.1
    point 2): one constant-time comparison per profile holding a token, whichever profile matches or none; a revoked
    profile has nothing to compare."""
    data = setup_profiles(tmp_path)
    module = router()
    calls = []
    original = module.compare_digest

    def counted(a, b):
        calls.append(None)
        return original(a, b)
    monkeypatch.setattr(module, 'compare_digest', counted)
    async with multi_profile_runtime(PRODUCT, data, children=profile_children(data, PRODUCT)) as runtime:
        watch(log_scan, data)
        unknown = secrets.token_urlsafe(32)
        log_scan.watch(unknown)
        for revoked in (None, C):
            if revoked:
                await change_token(runtime, revoked, 'revoke')
            holders = 3 if revoked is None else 2
            for token in (runtime.token('default'), runtime.token(B), unknown):
                for path, headers in paths(token):
                    calls.clear()
                    async with runtime.mcp() as client:
                        await client.post(path, headers=headers, json=initialize_message())
                    assert len(calls) == holders, (path.replace(token, '<token>'), len(calls))


async def test_a_stale_digest_is_refused_by_the_profiles_own_app(tmp_path, log_scan):
    """The profile's own app checks the token again with its own store (contract 2.3: a wrong route can only be
    refused). B's token is rotated, but the dispatcher still believes B holds the old one (a stale digest: a signature
    that did not change within one clock tick, or a later slice's cache): the old token is handed to B's app, which
    answers today's wrong-token bytes on both paths, and B's child gets nothing (HM-08 review S-3, mutation R03)."""
    data = setup_profiles(tmp_path, extras=(B,))
    children = golden_children(data, PRODUCT, extras=(B,))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        old = runtime.token(B)
        new = await change_token(runtime, B, 'rotate')
        log_scan.watch(new)
        entry = runtime.manager.get(B)
        stale = hashlib.sha256(old.encode()).digest()
        entry.credentials.refresh = lambda: stale  # the dispatcher keeps routing the old token to B
        since = {port: len(mock.requests) for port, mock in children.by_port.items()}
        async with runtime.mcp() as client:
            for path, headers in paths(old):
                response = await client.post(path, headers=headers, json=initialize_message())
                assert answer(response) == (NOT_FOUND if path.startswith('/private_') else BEARER_REQUIRED)
        assert all(mock.forwarded(since[port]) == [] for port, mock in children.by_port.items())
        assert entry.gate.active == 0 and runtime.manager.budget.used(entry.profile_id) == 0


async def test_resolving_a_token_among_six_profiles_is_cheap(tmp_path, log_scan, capsys):
    """Plan 12.3 HM-08 acceptance: the cost of resolving a token among six profiles (the default and five additional
    ones) is measured and recorded in the slice's provenance note (FM-14: HM-19c measures on the target hardware).
    Per request: one lstat of the index, one lstat of each additional profile's directory and of every profile's state
    (its signature), one sha256 and six comparisons; a state is read again only when its signature changed. The bounds
    asserted here are generous (a loaded CI runner); the measured values are printed."""
    extras = (B, C, D, E, F)
    data = setup_profiles(tmp_path, extras=extras)
    async with multi_profile_runtime(PRODUCT, data, children=profile_children(data, PRODUCT, extras)) as runtime:
        watch(log_scan, data)
        dispatcher = runtime.manager.mcp_app
        last = runtime.token(F).encode()
        unknown = secrets.token_urlsafe(32).encode()

        def measure(candidate, rounds, touch=None):
            samples = []
            for _ in range(rounds):
                if touch:
                    touch()
                start = time.perf_counter()
                found = dispatcher.resolve(candidate)
                samples.append(time.perf_counter() - start)
            return found, samples

        found, cached = measure(last, 2000)
        assert [entry.profile_id for entry in found] == [F]
        found, missing = measure(unknown, 2000)
        assert found == []
        directories = [data, *(profiles.Layout(data).profile(profile_id) for profile_id in extras)]
        stamp = [time.time_ns()]

        def touch_all():  # every state's signature changes: every state is read again
            stamp[0] += 1000
            for directory in directories:
                os.utime(directory / 'state.json', ns=(stamp[0], stamp[0]))
        found, reread = measure(last, 300, touch_all)
        assert [entry.profile_id for entry in found] == [F]
    report = {name: (statistics.mean(samples) * 1e6, sorted(samples)[int(len(samples) * .95)] * 1e6)
              for name, samples in (('cached', cached), ('unknown', missing), ('reread_all', reread))}
    with capsys.disabled():
        print('\nHM-08 six-profile resolution (mean, p95 microseconds):',
              {name: (round(mean, 1), round(p95, 1)) for name, (mean, p95) in report.items()})
    assert report['cached'][0] < 2000 and report['unknown'][0] < 2000 and report['reread_all'][0] < 20000
