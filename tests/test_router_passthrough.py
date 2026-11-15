"""HM-08: the switch decides whether 8081 gets the token dispatcher (multi-profile plan 3.3, 5.2, 7.1, 7.3; contract 1.2,
5; acceptance of plan 12.3 HM-08: "開關關時 HM-01 逐位元；開關開時全過").

Switched off (the repository: MULTI_PROFILE_PRODUCTS is empty), run_product serves what it served before HM-08: the
default profile's own apps on both listeners, limit_concurrency 64 on each, no profile index or profile directory
read, no file limit touched; profile data on disk changes nothing (its tokens are unknown tokens; HM-13b revokes
them). HM-01's golden regression and both contract freezes keep proving the bytes.

Switched on, the default profile alone answers every HM-01 golden, MCP-contract and management-contract case byte for
byte through the dispatcher (those tests run again here with the switch on; plan 7.3). The 8081 listener's outer
bound becomes 64 + 32 x the product's additional-profile limit, 8099 keeps 64, and the soft RLIMIT_NOFILE is raised to
what that needs plus 25% when it is lower (never above the hard limit, no privilege needed). When the limit cannot be
read or raised enough, the add-on degrades instead of guessing: no additional profile is served, the outer bound stays
64, and one WARNING says so (HM-03a confirms the HAOS values).

n8n keeps its own runtime (apps/n8n/run.py) until HM-25; OpenDesign and Odoo Manage have no additional profiles
(DQ-28) and are never switched on.
"""
import pytest

import test_admin_contract_freeze as admin_freeze
import test_mcp_contract_freeze as mcp_freeze
import test_single_profile_golden as golden
from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import (SWITCHABLE, Children, create_profile, multi_profile_runtime, stored, switched_on)
from mcp_admin_core import profile_runtime, profiles
from test_single_profile_golden import (ACCEPT, BEARER_REQUIRED, NOT_FOUND, answer, configure, initialize_message,
                                        production_runtime, settle)
from test_upgrade_zero_rewrite import tree_facts

pytestmark = pytest.mark.usefixtures('log_scan')
RUN_PRODUCTS = [product for product in golden.PRODUCTS if product != 'n8n']
B = 'a' * 24


def router():
    import mcp_admin_core.profile_router as module  # imported when a test runs (the red half of red-green)
    return module


class FakeResource:
    """The resource module's RLIMIT_NOFILE interface (getrlimit, setrlimit), recording every call; fail names the call
    that raises (OSError for getrlimit, ValueError for setrlimit, as the module raises)."""
    RLIMIT_NOFILE = 7
    RLIM_INFINITY = -1

    def __init__(self, soft, hard, fail=None):
        self.limits, self.fail, self.calls = (soft, hard), fail, []

    def getrlimit(self, which):
        assert which == self.RLIMIT_NOFILE
        self.calls.append(('get',))
        if self.fail == 'get':
            raise OSError('getrlimit refused')
        return self.limits

    def setrlimit(self, which, limits):
        assert which == self.RLIMIT_NOFILE
        self.calls.append(('set', limits))
        soft, hard = limits
        if self.fail == 'set' or hard != self.limits[1] or (self.limits[1] != self.RLIM_INFINITY
                                                             and soft > self.limits[1]):
            raise ValueError('not allowed')
        self.limits = (soft, hard)


class Forbidden:
    """Anything a switched-off start must never call or look into: calling it or reading any attribute of it (the
    resource module's getrlimit, say) fails the test. An AttributeError would not: raise_open_file_limit catches it as
    a module without RLIMIT_NOFILE (HM-08 review S-2, mutation O01)."""

    def __init__(self, name):
        self.name = name

    def __call__(self, *args, **kwargs):
        raise AssertionError(f'{self.name} called while the product is switched off')

    def __getattr__(self, attribute):
        raise AssertionError(f'{self.name}.{attribute} used while the product is switched off')


# ---- switched off: nothing changes ----

@pytest.mark.parametrize('product', RUN_PRODUCTS)
async def test_switched_off_run_product_serves_the_default_profile_alone(tmp_path, log_scan, monkeypatch, product):
    """No dispatcher (8081 is the default profile's own MCP app), no ProfileManager, no index or profile directory
    read, no file limit touched, 64 on both listeners: as before HM-08, profile data on disk or not."""
    for name in ('read_index', 'recheck_index', 'scan_profiles', 'check_consistency'):
        monkeypatch.setattr(profiles, name, Forbidden('profiles.' + name))
    monkeypatch.setattr(profile_runtime, 'resource', Forbidden('resource'))
    data = tmp_path / 'data'
    configure(data, product)
    async with multi_profile_runtime(product, data, switch=False) as runtime:
        await settle(runtime, 'configured')
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        assert runtime.manager is None
        assert any(getattr(route, 'path', None) == '/mcp' for route in runtime.mcp_app.routes)
        assert not isinstance(runtime.mcp_app, router().McpDispatcher)
        assert runtime.limits() == {'admin': 64, 'mcp': 64}


@pytest.mark.parametrize('product', [product for product in RUN_PRODUCTS if product in SWITCHABLE])
async def test_switched_off_profile_data_on_disk_changes_nothing(tmp_path, log_scan, product):
    """Profile data on disk (an index and a profile directory) while the product is switched off: its token is an
    unknown token on both paths (the dormant-profile revocation is HM-13b's, plan 3.3), and the start leaves every
    entry under /data/mcp as it was, the index and the profile directory included (ctime aside: the default state is
    re-chmod'ed at every read, test_upgrade_zero_rewrite.start_facts)."""
    data = tmp_path / 'data'
    configure(data, product)
    create_profile(data, product, B, label='Beta Ops', port=18000)
    log_scan.watch('Beta Ops', kind='name')
    token = stored(profiles.Layout(data).profile(B))['token']
    log_scan.watch(token, stored(profiles.Layout(data).profile(B))['child_token'])
    before = {name: facts[:6] + facts[7:] for name, facts in tree_facts(data).items() if name != 'child'}
    async with multi_profile_runtime(product, data, switch=False) as runtime:
        await settle(runtime, 'configured')
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        async with runtime.mcp() as client:
            for path, headers in (('/mcp', {**ACCEPT, 'Authorization': 'Bearer ' + token}),
                                  (f'/private_{token}/mcp', ACCEPT)):
                response = await client.post(path, headers=headers, json=initialize_message())
                assert answer(response) == (NOT_FOUND if path.startswith('/private_') else BEARER_REQUIRED)
    after = {name: facts[:6] + facts[7:] for name, facts in tree_facts(data).items()
             if name != 'child' and not name.startswith('child/')}
    assert {name: after[name] for name in before if name != '.'} == {n: f for n, f in before.items() if n != '.'}


# ---- switched on, the default profile alone: HM-01 byte for byte ----

@pytest.mark.parametrize('mode', golden.MODES)
@pytest.mark.parametrize('product', SWITCHABLE)
async def test_switched_on_the_default_profile_keeps_its_golden_answers(tmp_path, log_scan, product, mode):
    """HM-01's golden regression with the product switched on and no additional profile: both connection paths, the
    error answers, /health/ready, the bootstrap fields, what the child gets and what comes back, and a state.json that
    nothing rewrites, through the dispatcher (plan 7.3: both modes)."""
    async with switched_on(product):
        await golden.test_default_profile_golden(tmp_path, log_scan, product, mode)


@pytest.mark.parametrize('product', SWITCHABLE)
async def test_switched_on_the_mcp_contract_freeze_holds(tmp_path, log_scan, product):
    async with switched_on(product):
        await mcp_freeze.test_mcp_contract_freeze(tmp_path, log_scan, product)


@pytest.mark.parametrize('product', SWITCHABLE)
async def test_switched_on_the_management_contract_freeze_holds(tmp_path, log_scan, product):
    """8099 is the default profile's management app with the add-on's shared administration (one AdminAuthority, one
    set of management slots); every frozen answer shape stays (HM-10 brings the profile routes and X-MCP-Profile)."""
    async with switched_on(product):
        await admin_freeze.test_management_answer_shapes(tmp_path / 'shapes', log_scan, product)
        await admin_freeze.test_builtin_only_answer_shapes(tmp_path / 'builtin', log_scan, product)


async def test_switched_on_the_runtime_is_the_profile_manager(tmp_path, log_scan):
    """Switched on, run_product builds a ProfileManager on the default store: 8081 is its dispatcher (whose routes are
    the default app's, for whoever looks), 8099 the default profile's management app, every profile shares one
    administration (SharedAdmin), and production_runtime of HM-01 finds both listeners unchanged."""
    data = tmp_path / 'data'
    configure(data, 'odoo')
    async with switched_on('odoo'):
        async with production_runtime('odoo', data) as runtime:
            await settle(runtime, 'configured')
            log_scan.watch(stored(data)['token'], stored(data)['child_token'])
            dispatcher = runtime.mcp_app
            assert isinstance(dispatcher, router().McpDispatcher)
            manager = dispatcher.manager
            default = manager.get('default')
            assert runtime.admin_app is default.runtime.admin_app is manager.admin_app
            assert default.runtime.shared is manager.shared and default.runtime.profile_view is None
            assert dispatcher.routes == default.runtime.mcp_app.routes
            assert [entry.profile_id for entry in manager.profiles()] == ['default']


# ---- switched on: the listener bound and the file limit ----

@pytest.mark.parametrize('product', SWITCHABLE)
async def test_switched_on_the_mcp_listener_bound_follows_the_product_limit(tmp_path, log_scan, product):
    data = tmp_path / 'data'
    configure(data, product)
    resources = FakeResource(1 << 20, 1 << 20)
    async with multi_profile_runtime(product, data, resources=resources) as runtime:
        await settle(runtime, 'configured')
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        assert runtime.limits() == {'admin': 64, 'mcp': 64 + 32 * profiles.capacity(product).policy_limit}
        assert runtime.limits()['mcp'] == profiles.mcp_listener_limit(product) == runtime.manager.mcp_listener_limit
        assert [call for call in resources.calls if call[0] == 'set'] == []  # already enough: nothing set


def test_the_file_budget_counts_every_listener_client_and_child():
    """The open-file budget (plan 5.2, C2-SF-5; an estimate until HM-03a and HM-19c measure): both listeners' bounds,
    every profile's child client, the HA role queries, each child's pipes and a fixed base, plus 25%."""
    budget = profile_runtime.open_file_budget
    for product in SWITCHABLE:
        limit = profiles.capacity(product).policy_limit
        expected = (profiles.mcp_listener_limit(product) + 64 + 40 + 24 * limit + profile_runtime.ROLE_QUERY_FILES
                    + profile_runtime.CHILD_FILES * (limit + 1) + profile_runtime.BASE_FILES)
        assert budget(product) == (expected, -(-expected * 5 // 4))
    assert budget('odoo')[0] < budget('odoo')[1] < 1024  # Odoo, six profiles: under a common soft limit of 1024


@pytest.mark.parametrize('case', ['raised', 'hard too low', 'unreadable', 'refused'])
async def test_the_file_limit_is_raised_or_the_add_on_serves_the_default_profile_only(tmp_path, log_scan, case):
    """Switched on, the soft RLIMIT_NOFILE is raised to the budget plus 25% (at most the hard limit) when it is lower.
    Hard limit too low for the budget, getrlimit failing or setrlimit refusing: one WARNING (the numbers, nothing
    else), no additional profile is served (B's token is then an unknown token) and 8081 keeps 64."""
    data = tmp_path / 'data'
    configure(data, 'odoo')
    create_profile(data, 'odoo', B, label='Beta Ops', port=18000)
    log_scan.watch('Beta Ops', kind='name')
    needed, target = profile_runtime.open_file_budget('odoo')
    resources = {'raised': FakeResource(256, 4096), 'hard too low': FakeResource(256, needed - 1),
                 'unreadable': FakeResource(256, 4096, fail='get'), 'refused': FakeResource(256, 4096, fail='set')}[case]
    children = Children()
    children.profile_child(3000, 'default', 'odoo', data)
    children.profile_child(18000, 'beta', 'odoo', profiles.Layout(data).profile(B))
    async with multi_profile_runtime('odoo', data, resources=resources, children=children) as runtime:
        await settle(runtime, 'configured')
        token = stored(profiles.Layout(data).profile(B))['token']
        log_scan.watch(token, stored(data)['token'], stored(data)['child_token'])
        warnings = [record.getMessage() for record in log_scan.records
                    if record.name == 'mcp_admin_core.profile_runtime' and record.levelname == 'WARNING']
        async with runtime.mcp() as client:
            response = await client.post(f'/private_{token}/mcp', headers=ACCEPT, json=initialize_message())
        if case == 'raised':
            assert resources.limits == (target, 4096) and ('set', (target, 4096)) in resources.calls
            assert runtime.manager.get(B) is not None and response.status_code == 200
            assert runtime.limits()['mcp'] == profiles.mcp_listener_limit('odoo') and warnings == []
        else:
            assert runtime.manager.get(B) is None and answer(response) == NOT_FOUND
            assert runtime.limits() == {'admin': 64, 'mcp': 64}
            assert len(warnings) == 1 and 'file' in warnings[0] and 'additional profiles' in warnings[0], warnings
            assert token not in warnings[0]
            async with runtime.mcp() as client:  # the default profile serves
                response = await client.post('/mcp', headers={**ACCEPT, 'Authorization': 'Bearer '
                                                              + stored(data)['token']}, json=initialize_message())
                assert response.status_code == 200
