"""HM-12: several Odoo accounts of one database, each bound to its own profile (multi-profile plan 9 Odoo row, 12.3
HM-12, 10.3; DQ-05, DQ-30; acceptance T-03, T-04, T-10; FM-81, FM-82; contract section 9 #40, #60).

- Five accounts on the database the default profile uses, each saved in its own profile (its first connection: the
  URL it was issued keeps working), get five tokens, five ports and five children, each started with its own
  credentials (and the default profile keeps its own); a username saved anew rotates that profile's token alone
  (PaaS apps/odoo/tests/test_multi_profiles.py test_five_odoo_accounts_same_database_are_fixed_to_separate_profiles,
  woow-mcp-server 69ac425). In process, the children behind one MockTransport.
- Odoo's write approval token lives in its child's process (apps/odoo/patches/fix_cross_session_token_store.py: one
  store for every session of the process) and is the digest of the write it approves, whatever the account: the same
  write approved in two profiles gets the same token. Only the child that approved it executes it, so each profile has
  its own child: the default profile's approval is refused by B's child, with the two profiles' states the same but for
  their tokens (the control: the token string itself says nothing about the account), and the default profile's own
  child executes it; B approving the same write itself gets the same token, which only B's child then executes
  (PaaS FM-82: cross-profile rewrite, impersonation and deletion 18/18 refused). The real Odoo children of both
  profiles (the real Supervisor, run_product's ProfileManager), one fake XML-RPC backend (tests/test_expansion_runtime
  .py fake_api) behind 8081: this file's one case with real children.
- DQ-30 (2026-11-15: the first release keeps one read worker): every Odoo tool still runs on the child's one worker.
"""
import ast
from pathlib import Path

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import (Children, all_tokens, create_profile, free_port, ids, multi_profile_runtime,
                                   stored, update_profile)
from mcp_admin_core import profiles
from mcp_admin_core.products import ProductStore
from test_odoo_identity_rotation import opened_by, refused_everywhere, save
from test_single_profile_golden import ADMIN, configure, settle

pytestmark = pytest.mark.usefixtures('log_scan')
ROOT = Path(__file__).resolve().parents[1]
PRODUCT = 'odoo'
LABELS = [f'Desk {number} Ops' for number in range(1, 6)]


@pytest.fixture(autouse=True)
def memory_readings(monkeypatch):
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: None)
    monkeypatch.setattr(profiles, 'available_memory_mib', lambda: 4096)


def account(number):
    """The number-th account of the golden database (synthetic: DUMMY- credentials, an .invalid host)."""
    return {'url': 'https://odoo.invalid', 'database': 'DUMMY-db', 'username': f'DUMMY-user-{number}',
            'password': f'DUMMY-account-{number}-password'}


async def test_five_accounts_of_one_database_stay_bound_to_their_own_profiles(tmp_path, log_scan):
    data = tmp_path / 'data'
    configure(data, PRODUCT)  # the default profile's account: DUMMY-user on DUMMY-db
    extras = ids(5)
    children = Children()
    children.profile_child(3000, 'default', PRODUCT, data)
    for number, profile_id in enumerate(extras):
        create_profile(data, PRODUCT, profile_id, label=LABELS[number], port=18000 + number, configured=False)
        children.profile_child(18000 + number, f'desk{number + 1}', PRODUCT, profiles.Layout(data).profile(profile_id))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        log_scan.watch(*all_tokens(data))
        log_scan.watch(*LABELS, kind='name')
        log_scan.watch(*(account(number)['password'] for number in range(1, 6)), kind='secret')
        issued = {profile_id: runtime.token(profile_id) for profile_id in extras}
        default_state = (data / 'state.json').read_bytes()
        for number, profile_id in enumerate(extras, 1):
            saved = await save(runtime, profile_id, 'backend', {'connection': account(number)})
            assert saved.status_code == 200 and 'token_rotated' not in saved.json(), saved.text
            assert runtime.token(profile_id) == issued[profile_id]  # the first setup keeps the URL it was issued
        states = {profile_id: stored(runtime.directory(profile_id)) for profile_id in ('default', *extras)}
        assert len({state['token'] for state in states.values()}) == 6
        assert len({state['child_token'] for state in states.values()}) == 6
        async with runtime.admin() as admin:
            rows = (await admin.get('/api/profiles', headers=ADMIN)).json()['profiles']
        assert [row['port'] for row in rows] == [3000, *range(18000, 18005)]
        for number, profile_id in enumerate(extras, 1):
            env = runtime.manager.get(profile_id).runtime.supervisor.spec.env
            expected = account(number)
            assert (env['ODOO_URL'], env['ODOO_DB'], env['ODOO_USERNAME'], env['ODOO_PASSWORD']) == (
                expected['url'], 'DUMMY-db', expected['username'], expected['password'])
            assert await opened_by(runtime, runtime.token(profile_id), children.by_port[18000 + number - 1])
        assert runtime.manager.get('default').runtime.supervisor.spec.env['ODOO_USERNAME'] == 'DUMMY-user'
        assert (data / 'state.json').read_bytes() == default_state
        third = extras[2]
        old = runtime.token(third)
        saved = await save(runtime, third, 'backend/patch', {'changes': {'username': 'DUMMY-user-3b'}})
        assert saved.status_code == 200 and saved.json()['token_rotated'] is True, saved.text
        log_scan.watch(runtime.token(third))
        assert await refused_everywhere(runtime, old)
        assert await opened_by(runtime, runtime.token(third), children.by_port[18002])
        for profile_id in ('default', *extras):
            if profile_id != third:
                assert runtime.token(profile_id) == states[profile_id]['token'], profile_id
        assert (data / 'state.json').read_bytes() == default_state


async def session_of(client, token):
    """An initialized MCP session of token on /mcp: the headers its requests carry."""
    from test_real_products import rpc
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json, text/event-stream'}
    result = await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
        'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'approval-test', 'version': '0'}}})
    headers['MCP-Protocol-Version'] = result['protocolVersion']
    await rpc(client, '/mcp', headers, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    return headers


async def test_an_approval_is_executed_only_by_the_child_of_the_profile_that_approved_it(tmp_path, log_scan,
                                                                                        monkeypatch):
    import loopback_backends
    from lifecycle_runtime import until
    from mcp_admin_core import health as health_module, lifecycle
    from test_backend_loopback import running_its_program
    from test_expansion_runtime import fake_api
    from test_odoo_child_switch_runtime import ALL_ON, call
    from test_real_products import connection
    monkeypatch.setattr(health_module, 'HEALTH_INTERVAL', 0.5)  # both profiles' first health checks within a second
    extra, label = ids(1)[0], 'Approval Desk'
    data = tmp_path / 'data'
    # The fake XML-RPC backend is on loopback: the test double lets it through the switched-on loopback rule (HM-20).
    with fake_api() as (url, _events, mutations, failures), loopback_backends.allowed():
        store = ProductStore(data, PRODUCT)
        try:
            store.update(connection=connection(PRODUCT, url), odoo_write_switches=ALL_ON)
        finally:
            store.close()
        create_profile(data, PRODUCT, extra, label=label, port=free_port(), configured=False)
        update_profile(data, PRODUCT, extra, connection=connection(PRODUCT, url))
        own = ('token', 'child_token')
        default_state, extra_state = stored(data), stored(profiles.Layout(data).profile(extra))
        assert ({name: value for name, value in default_state.items() if name not in own}
                == {name: value for name, value in extra_state.items() if name not in own})
        assert all(default_state[name] != extra_state[name] for name in own)
        log_scan.watch(*all_tokens(data))
        log_scan.watch(label, kind='name')
        async with multi_profile_runtime(PRODUCT, data, supervisor=lifecycle.Supervisor, real_children=True,
                                         default_port=free_port()) as runtime:
            entries = [runtime.manager.get(profile_id).runtime for profile_id in ('default', extra)]
            await until(lambda: all(running_its_program(entry.supervisor) for entry in entries)
                        and all(entry.health.availability()['ready'] for entry in entries), timeout=60)
            async with runtime.mcp() as client:
                default, other = await session_of(client, runtime.token('default')), await session_of(
                    client, runtime.token(extra))
                write = {'model': 'res.partner', 'operation': 'create', 'values': {'name': 'HM-12 approved record'}}
                validated = await call(client, '/mcp', default, 2, 'validate_write', write)
                assert validated['success'] is True and validated['valid'] is True and not mutations
                approval = validated['approval']
                crossed = await call(client, '/mcp', other, 3, 'execute_approved_write',
                                     {'approval': approval, 'confirm': True})
                assert crossed['success'] is False, crossed
                assert 'has not been validated in this server session' in crossed['error']
                assert not mutations
                executed = await call(client, '/mcp', default, 4, 'execute_approved_write',
                                      {'approval': approval, 'confirm': True})
                assert executed['success'] is True and len(mutations) == 1, executed
                again = await call(client, '/mcp', other, 5, 'validate_write', write)
                assert again['success'] is True and again['approval']['token'] == approval['token']
                theirs = await call(client, '/mcp', other, 6, 'execute_approved_write',
                                    {'approval': again['approval'], 'confirm': True})
                assert theirs['success'] is True and len(mutations) == 2, theirs
                for headers in (default, other):
                    await client.delete('/mcp', headers=headers)
    assert not failures


def test_every_odoo_tool_still_runs_on_the_childs_one_worker():
    """DQ-30 (2026-11-15, the user took the plan's recommendation): the first release keeps Odoo's reads at one worker
    per child (PaaS: 8 read threads; contract section 9 #60). apps/odoo/launch.py builds BoundedTools once, with
    capacity 1 (tests/test_odoo_tool_timeout.py: a second call meanwhile gets BACKEND_BUSY)."""
    tree = ast.parse((ROOT / 'apps/odoo/launch.py').read_text())
    built = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and getattr(node.func, 'id', getattr(node.func, 'attr', None)) == 'BoundedTools']
    assert len(built) == 1
    assert [(keyword.arg, ast.literal_eval(keyword.value)) for keyword in built[0].keywords] == [('capacity', 1)]
