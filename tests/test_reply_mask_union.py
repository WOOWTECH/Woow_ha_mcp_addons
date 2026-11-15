"""HM-08: the reply mask of a switched-on product is the union (multi-profile plan 5.1 point 8, 8.6; contract 2.7;
plan 8.8 #38; DQ-40 (a) ⑧; C1-S1; FM-76, FM-151).

What a profile's gateway relays (a child's JSON or SSE reply, the health check's reason inside a refused tools/call,
the management answers that carry a child's or a backend's text: backend/test, diagnostics) is masked with that
profile's own credentials (redact.secret_values of its state: its tokens, its backend's secrets and their Basic forms,
as today) and with every token and child token the add-on holds: every profile's (the default profile's, every indexed
one's) and every orphan profile directory's. A's backend may hold B's secret URL (an n8n workflow, an Odoo note); a
256-bit random token cannot be guessed by writing it into a backend and reading it back, a person's password can (G3
345): so another profile's backend password is not in the mask. Switched off (the repository), the mask is today's:
the profile's own credentials only.
"""
import json

import httpx
import pytest

from admin_write_headers import reviewed_headers
from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import Children, create_profile, ids, multi_profile_runtime, stored
from mcp_admin_core import profiles, redact
from mcp_admin_core.products import PROBES, ProductState
from test_profile_runtime import ProfileChild
from test_single_profile_golden import ACCEPT, ADMIN, configure, initialize_message, probe_name, settle

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'odoo'
B, C, O = ids(3)
LABELS = {B: 'Beta Ops', C: 'Gamma Ops'}
TOOL, ARGUMENTS = PROBES[PRODUCT]
UNHELD = 'U' * 21 + 'n' * 22  # token-shaped, 43 characters, held by nobody: never masked


class EchoChild(ProfileChild):
    """A ProfileChild whose tools/calls answer `text` (as JSON, or as one SSE event when sse is set), whose readiness
    probe, when probe_error is set, fails with that text as the backend's error, and whose initialize, when
    initialize_error is set, answers a JSON-RPC error carrying that text (its message and data)."""

    def __init__(self, *args):
        super().__init__(*args)
        self.sse = False
        self.probe_error = None
        self.initialize_error = None

    async def __call__(self, request):
        message = json.loads(request.content) if request.content else {}
        if self.initialize_error is not None and message.get('method') == 'initialize':
            self.requests.append(request)
            return httpx.Response(200, json={'jsonrpc': '2.0', 'id': message['id'], 'error': {
                'code': -32603, 'message': self.initialize_error, 'data': {'detail': self.initialize_error}}})
        response = await super().__call__(request)
        if message.get('method') != 'tools/call' or response.status_code != 200:
            return response
        if message['params']['name'] == probe_name(self.product):
            if self.probe_error is None:
                return response
            return httpx.Response(200, json={'jsonrpc': '2.0', 'id': message['id'], 'result': {
                'content': [{'type': 'text', 'text': json.dumps({'error': self.probe_error})}], 'isError': True}})
        if self.sse:
            return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                                  content=b'event: message\ndata: ' + response.content + b'\n\n')
        return response


def bearer(token):
    return {**ACCEPT, 'Authorization': 'Bearer ' + token}


def setup(tmp_path):
    """The default profile, B and C indexed, O an orphan directory (never routed, still masked)."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    create_profile(data, PRODUCT, B, label=LABELS[B], port=18000)
    create_profile(data, PRODUCT, C, label=LABELS[C], port=18001)
    create_profile(data, PRODUCT, O, label='Orphan Ops', port=18002, indexed=False)
    return data


def children_of(data):
    children = Children()
    children.add(3000, EchoChild('default', PRODUCT, data))
    for port, profile_id in ((18000, B), (18001, C)):
        children.add(port, EchoChild('p' + profile_id[:4], PRODUCT, profiles.Layout(data).profile(profile_id)))
    return children


def state_of(directory):
    return ProductState.model_validate(stored(directory))


def held_tokens(data):
    """Every token and child token under data: the default profile's, every profile directory's (the orphan's too)."""
    layout = profiles.Layout(data)
    found = []
    for directory in (data, layout.profile(B), layout.profile(C), layout.profile(O)):
        value = stored(directory)
        found += [value['token'], value['child_token']]
    return [value for value in found if value]


def masked(text, secrets):
    for secret in sorted(set(secrets), key=len, reverse=True):
        text = text.replace(secret, redact.SECRET_MASK)
    return text


def watch(log_scan, data):
    for token in held_tokens(data):
        log_scan.watch(token)
    layout = profiles.Layout(data)
    for directory in (data, layout.profile(B), layout.profile(C), layout.profile(O)):
        log_scan.watch(*(value for value in redact.secret_values(state_of(directory)) if len(value) >= 8),
                       kind='secret')
    log_scan.watch('Beta Ops', 'Gamma Ops', 'Orphan Ops', kind='name')


def echo_text(data):
    """A backend reply of B's that carries every token the add-on holds, a secret URL of C, C's and B's own backend
    passwords, and a token-shaped value nobody holds."""
    layout = profiles.Layout(data)
    c_state, b_state = state_of(layout.profile(C)), state_of(layout.profile(B))
    return ('note: ' + ' '.join(held_tokens(data)) + f' url=https://ha.invalid/private_{c_state.token}/mcp'
            f' c_password={c_state.connection.password} b_password={b_state.connection.password} other={UNHELD}')


async def tool_text(client, token, ident=5):
    init = await client.post('/mcp', headers=bearer(token), json=initialize_message())
    headers = {**bearer(token), 'Mcp-Session-Id': init.headers['mcp-session-id']}
    response = await client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
                                                                'params': {'name': TOOL, 'arguments': ARGUMENTS}})
    assert response.status_code == 200, response.content[:300]
    if response.headers['content-type'] == 'text/event-stream':
        data, = [line[6:] for line in response.text.splitlines() if line.startswith('data: ')]
        return json.loads(data)
    return response.json()


@pytest.mark.parametrize('framing', ['json', 'sse'])
async def test_a_reply_never_carries_any_token_the_add_on_holds(tmp_path, log_scan, framing):
    """B's child relays its backend's text holding every profile's token and child token (the default profile's, C's,
    its own, the orphan's), C's secret URL, C's and B's backend passwords and a value nobody holds: every token is
    [REDACTED] and so is B's own password (redact.secret_values of B's state, as today); C's password is not in B's
    mask (plan 5.1 point 8); the value nobody holds is shown. JSON replies and SSE events alike."""
    data = setup(tmp_path)
    children = children_of(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        child = children.by_port[18000]
        child.text, child.sse = echo_text(data), framing == 'sse'
        async with runtime.mcp() as client:
            body = await tool_text(client, runtime.token(B))
        shown = body['result']['content'][0]['text']
        layout = profiles.Layout(data)
        expected = masked(child.text, [*held_tokens(data), *redact.secret_values(state_of(layout.profile(B)))])
        assert shown == expected
        assert all(token not in shown for token in held_tokens(data))
        assert state_of(layout.profile(C)).connection.password in shown and UNHELD in shown
        assert state_of(layout.profile(B)).connection.password not in shown


async def test_a_token_rotated_elsewhere_is_masked_at_once(tmp_path, log_scan):
    """C's token rotated through C's own management app: the next reply of B that carries the new token masks it
    (the mask reads every profile's current state; plan 5.1 point 4's signatures)."""
    data = setup(tmp_path)
    children = children_of(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        async with runtime.admin(C) as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            rotated = (await admin.post('/api/token/rotate', headers=reviewed_headers(boot, ADMIN))).json()['token']
        log_scan.watch(rotated)
        child = children.by_port[18000]
        child.text = f'new C token {rotated} old default {runtime.token("default")}'
        async with runtime.mcp() as client:
            shown = (await tool_text(client, runtime.token(B)))['result']['content'][0]['text']
        assert shown == 'new C token [REDACTED] old default [REDACTED]'


async def test_a_health_reason_with_another_profiles_token_is_masked_in_the_refusal(tmp_path, log_scan):
    """B's readiness probe fails with C's token in the backend's error: the health monitor keeps the reason masked with
    B's own credentials (health.py, as today), and the refused tools/call that carries the reason (-32603 Backend
    unreachable) masks C's token too."""
    data = setup(tmp_path)
    children = children_of(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        c_token = runtime.token(C)
        children.by_port[18000].probe_error = f'login refused for {c_token}'
        profile = runtime.manager.get(B).runtime
        await profile.health.check()
        await profile.health.check()  # HM-09 (DQ-25): two failed checks in a row judge the backend unreachable
        assert profile.health.availability()['backend'] == 'unreachable'
        async with runtime.mcp() as client:
            body = await tool_text(client, runtime.token(B))
        assert body['error']['message'] == 'Backend unreachable'
        assert body['error']['data']['reason'] == 'login refused for [REDACTED]'


async def test_the_management_answers_carry_no_token_either(tmp_path, log_scan):
    """The default profile's backend/test answer (the backend's own text) is masked with the union as well."""
    data = setup(tmp_path)
    children = children_of(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        children.by_port[3000].probe_error = f'login refused for {runtime.token(B)} and {runtime.token(C)}'
        async with runtime.admin() as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            response = await admin.post('/api/backend/test', headers=reviewed_headers(boot, ADMIN))
        assert response.status_code == 200
        assert response.json()['reason'] == 'login refused for [REDACTED] and [REDACTED]'


async def test_a_childs_initialize_error_is_masked_once_switched_on(tmp_path, log_scan):
    """B's child answers initialize with a JSON-RPC error whose message and data carry its backend's text (every token
    the add-on holds, C's secret URL, both backend passwords, a value nobody holds): switched on, the gateway masks it
    as every other relayed text (HM-08 review S-4 (a)): every token and B's own password [REDACTED], C's password and
    the value nobody holds shown. Switched off the error is relayed as before (an existing gap, left to HM-14)."""
    data = setup(tmp_path)
    children = children_of(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        child = children.by_port[18000]
        child.initialize_error = echo_text(data)
        async with runtime.mcp() as client:
            response = await client.post('/mcp', headers=bearer(runtime.token(B)), json=initialize_message())
        assert response.status_code == 200 and 'mcp-session-id' not in response.headers
        layout = profiles.Layout(data)
        expected = masked(child.initialize_error, [*held_tokens(data), *redact.secret_values(state_of(layout.profile(B)))])
        assert response.json() == {'jsonrpc': '2.0', 'id': 1, 'error': {'code': -32603, 'message': expected,
                                                                         'data': {'detail': expected}}}
        assert all(token not in response.text for token in held_tokens(data))
        assert state_of(layout.profile(C)).connection.password in expected and UNHELD in expected


async def test_diagnostics_carry_no_token_either(tmp_path, log_scan):
    """B's child output holds C's token and the default profile's: B's diagnostics answer (its child's output, from
    B's own management app) masks them with the union too (HM-08 review S-4 (b), mutation K06)."""
    data = setup(tmp_path)
    async with multi_profile_runtime(PRODUCT, data, children=children_of(data)) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        line = f'upstream said {runtime.token(C)} and {runtime.token("default")} and {UNHELD}'
        runtime.manager.get(B).runtime.supervisor.logs.append('stdout', line, 1)
        async with runtime.admin(B) as admin:
            response = await admin.get('/api/diagnostics', headers=ADMIN)
        assert response.status_code == 200
        assert [entry['text'] for entry in response.json()['logs']['entries']] == [
            f'upstream said [REDACTED] and [REDACTED] and {UNHELD}']


async def test_switched_off_the_mask_is_the_profiles_own(tmp_path, log_scan):
    """Switched off, a reply is masked with the profile's own credentials only, as today: the default profile's own
    token is [REDACTED]; another profile directory's token on disk (dormant: not routed, HM-13b revokes it) and a value
    nobody holds are shown."""
    data = setup(tmp_path)
    children = children_of(data)
    async with multi_profile_runtime(PRODUCT, data, switch=False, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        b_token = stored(profiles.Layout(data).profile(B))['token']
        child = children.by_port[3000]
        child.text = f'own {runtime.token("default")} other {b_token} unheld {UNHELD}'
        async with runtime.mcp() as client:
            shown = (await tool_text(client, runtime.token('default')))['result']['content'][0]['text']
        assert shown == f'own [REDACTED] other {b_token} unheld {UNHELD}'
