"""HM-31: the gateway's request body byte budget, the unit (multi-profile plan 12.3 HM-31; contract 2.4, 5; the PaaS
#155 budget, woow-mcp-server d7f5849 request_budget.py and its tests test_gateway_request_budget.py (sections 1-3),
test_gateway_budget_defaults.py, test_gateway_budget_round2.py and test_gateway_budget_round3.py (their unit cases); the
case-by-case map is in docs/provenance/ha-multiprofile-HM-31-20261116.md).

One budget of the add-on, two layers (PaaS): the whole add-on, and each profile's share, which HA caps at the profile's
quota (64 MiB, DQ-07: HA stricter than PaaS, contract 9). Derived from the memory when the gateway is made: the cgroup
limit when the container has one (PaaS), else MemAvailable less the plan's 256 MiB reserve (HA has no Pod limit), else a
fixed 32 MiB. A request is charged the larger of its body as read and as forwarded (HA re-serializes: HM-08 review S-1),
once that is over 64 KiB; a small one is never charged nor refused. No environment variable is read (contract 9, #45).

The memory readers are replaced by hand-made files or functions; no test depends on the machine's memory.
"""
import json
import logging
import random
import sys

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import profiles

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan
MiB = 1024 * 1024
CAP = 16 * MiB


def rb():
    import mcp_admin_core.request_budget as module  # imported when a test runs (the red half of red-green)
    return module


@pytest.fixture
def kernel_files(tmp_path, monkeypatch):
    """The cgroup limit files (v2, v1) and /proc/meminfo, as test files: what profiles' readers (HM-09) read, and so
    the budget (HM-31 review S-6: it has no copy of them). Absent until a test writes them."""
    v2, v1, meminfo = tmp_path / 'memory.max', tmp_path / 'memory.limit_in_bytes', tmp_path / 'meminfo'
    monkeypatch.setattr(profiles, 'CGROUP_MEMORY_LIMITS', (v2, v1))
    monkeypatch.setattr(profiles, 'MEMINFO', meminfo)
    return v2, v1, meminfo


def ceiling(monkeypatch, mib, source='cgroup'):
    """The memory the defaults are derived from, as memory_ceiling() would read it."""
    module = rb()
    monkeypatch.setattr(module, 'memory_ceiling', lambda: (mib, source if mib is not None else 'none'))
    return module


def budget(total_mib=32, per_mib=20):
    module = rb()
    return module.RequestBudget(module.BudgetLimits(total=total_mib * MiB, per_profile=per_mib * MiB))


def share(owner, profile_id='default', cap=64 * MiB):
    return owner.share(profile_id, cap=cap)


# ---- the defaults (PaaS test_gateway_request_budget.py section 1, test_gateway_budget_defaults.py) ----

def test_defaults_follow_the_paas_formula_on_a_cgroup_limit(monkeypatch):
    """1 GiB, one account with the 160 MiB child estimate: (1024 - 76 - 160 - 150) MiB / 20; a profile's share is half
    of it, at least 16 MiB; budget x 20 + the gateway and the child stay within 1 GiB less the safety margin."""
    module = ceiling(monkeypatch, 1024)
    limits = module.BudgetLimits.derive(None)
    expected = int((1024 - module.GATEWAY_BASELINE_MIB - module.DEFAULT_CHILD_MEMORY_MIB - module.SAFETY_MARGIN_MIB)
                   * MiB / module.AMPLIFICATION)
    assert (limits.total, limits.source) == (expected, 'cgroup')
    assert limits.per_profile == max(16 * MiB, expected // 2) == 16 * MiB
    assert limits.total * module.AMPLIFICATION + (module.GATEWAY_BASELINE_MIB + module.DEFAULT_CHILD_MEMORY_MIB) * MiB \
        <= (1024 - module.SAFETY_MARGIN_MIB) * MiB + 1


def test_without_any_memory_reading_the_budget_is_fixed_and_small_ceilings_are_clamped(monkeypatch):
    module = ceiling(monkeypatch, None)
    limits = module.BudgetLimits.derive(None)
    assert (limits.total, limits.source) == (module.FALLBACK_TOTAL_BYTES, 'none') and limits.total == 32 * MiB
    module = ceiling(monkeypatch, 128)  # a tiny ceiling: never below the single-request ceiling
    small = module.BudgetLimits.derive(None)
    assert small.total == 16 * MiB and small.per_profile == 16 * MiB


def test_without_a_cgroup_limit_memavailable_less_the_reserve_is_the_ceiling(kernel_files):
    """HA (plan 5.2's memory check; an add-on has no Pod limit): no cgroup limit ("max", or v1's no-limit value), so
    MemAvailable of /proc/meminfo less the plan's reserve (256 MiB) is the ceiling, read when the budget is made."""
    module = rb()
    v2, v1, meminfo = kernel_files
    meminfo.write_text('MemTotal:        8000000 kB\nMemFree:         1000000 kB\nMemAvailable:    3145728 kB\n')
    for limit in ('max\n', None):
        if limit is None:
            v2.unlink()
            v1.write_text(str(2 ** 63 - 4096))  # cgroup v1's "no limit"
        else:
            v2.write_text(limit)
        assert profiles.memory_limit_mib() is None
        assert module.memory_ceiling() == (3072 - module.HOST_RESERVE_MIB, 'meminfo')
    assert module.HOST_RESERVE_MIB == profiles.PROFILE_MEMORY_RESERVE_MIB == 256
    limits = module.BudgetLimits.derive('odoo')
    assert limits.source == 'meminfo'
    assert limits.total == int((3072 - 256 - 76 - 100 - 150) * MiB / 20)  # Odoo's child: 100 MiB
    v1.unlink()
    v2.write_text(str(2 * 1024 * MiB))  # a real limit wins over MemAvailable
    assert module.memory_ceiling() == (2048, 'cgroup')
    v2.unlink()
    meminfo.write_text('MemTotal: 8000000 kB\n')  # no MemAvailable line
    assert module.memory_ceiling() == (None, 'none')
    meminfo.unlink()
    assert profiles.available_memory_mib() is None
    meminfo.write_text('MemAvailable:   100 kB\n')  # less than the reserve: 0, the floor decides
    assert module.memory_ceiling() == (0, 'meminfo')
    assert module.BudgetLimits.derive(None).total == 16 * MiB


GIB3 = 'MemTotal:        8000000 kB\nMemFree:         1000000 kB\nMemAvailable:    3145728 kB\n'  # 3,072 MiB
V1_NO_LIMIT = str(2 ** 63 - 4096)
DIRECTORY = object()
# (memory.max, memory.limit_in_bytes, /proc/meminfo; None: the file is absent) and the ceiling the budget derives from
CEILING_CASES = {
    'v2 max: MemAvailable less the reserve': ('max\n', None, GIB3, (3072 - 256, 'meminfo')),
    'v1 no limit': (None, V1_NO_LIMIT, GIB3, (3072 - 256, 'meminfo')),
    'v2 limit wins over MemAvailable': ('2147483648\n', None, GIB3, (2048, 'cgroup')),
    'v2 limit with spaces': (' 1073741824 ', None, None, (1024, 'cgroup')),
    'v2 under one MiB': ('1048575', None, GIB3, (0, 'cgroup')),
    'v2 one TiB is still a limit': (str(1024 ** 4), None, GIB3, (1024 * 1024, 'cgroup')),
    'v2 over one TiB is none': (str(1024 ** 4 + 1024 * 1024), None, GIB3, (3072 - 256, 'meminfo')),
    'v2 not a number, v1 read': ('abc', '536870912\n', GIB3, (512, 'cgroup')),
    'v2 empty, no v1': ('', None, GIB3, (3072 - 256, 'meminfo')),
    'v2 a directory, v1 read': (DIRECTORY, '536870912', None, (512, 'cgroup')),
    'v2 negative': ('-1048576', None, GIB3, (-1, 'cgroup')),
    'nothing readable': (None, None, None, (None, 'none')),
    'no MemAvailable line': (None, None, 'MemTotal: 8000000 kB\n', (None, 'none')),
    'MemAvailable not in kB': (None, None, 'MemAvailable: 3072 MB\n', (None, 'none')),
    'MemAvailable below the reserve': (None, None, 'MemAvailable:   100 kB\n', (0, 'meminfo')),
    'the first MemAvailable line decides': (None, None, 'MemAvailable: 5.5 kB\nMemAvailable: 3145728 kB\n',
                                            (None, 'none')),
    'MemAvailable past the first 64 KiB': (None, None, 'x' * 70000 + '\n' + GIB3, (None, 'none')),
}


@pytest.mark.parametrize('v2_text, v1_text, meminfo_text, expected', CEILING_CASES.values(), ids=CEILING_CASES)
def test_the_ceiling_is_read_from_the_kernel_files_case_by_case(kernel_files, v2_text, v1_text, meminfo_text,
                                                                expected):
    """HM-31 review S-6 (part 2): the ceiling the budget derives from for each state of the kernel files, pinned before
    the budget's own copy of the memory readers gave way to profiles' (HM-09) and unchanged after it (the two copies
    read the same way: the provenance note's rebase section)."""
    for path, value in zip(kernel_files, (v2_text, v1_text, meminfo_text)):
        if value is DIRECTORY:
            path.mkdir()
        elif value is not None:
            path.write_text(value)
    assert rb().memory_ceiling() == expected


def test_the_budget_reads_the_memory_with_the_profile_capacitys_readers(monkeypatch):
    """HM-31 review S-6 (part 2): one copy of the memory readers, HM-09's (profiles.memory_limit_mib,
    available_memory_mib), which the profile capacity and the memory check use: the budget has none of its own, and its
    ceiling follows them, the cgroup limit first (MemAvailable is not read then), MemAvailable less the reserve without
    one, nothing readable: none."""
    module = rb()
    for name in ('memory_limit_mib', 'available_memory_mib', 'CGROUP_MEMORY_LIMITS', 'MEMINFO'):
        assert not hasattr(module, name), f'request_budget keeps a copy: {name}'

    def forbidden():
        raise AssertionError('MemAvailable read although the cgroup limit decides')
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: 777)
    monkeypatch.setattr(profiles, 'available_memory_mib', forbidden)
    assert module.memory_ceiling() == (777, 'cgroup')
    assert module.BudgetLimits.derive('odoo', switched_on=True).source == 'cgroup'
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: None)
    monkeypatch.setattr(profiles, 'available_memory_mib', lambda: 1000)
    assert module.memory_ceiling() == (1000 - module.HOST_RESERVE_MIB, 'meminfo')
    assert module.BudgetLimits.derive('odoo').source == 'meminfo'
    monkeypatch.setattr(profiles, 'available_memory_mib', lambda: None)
    assert module.memory_ceiling() == (None, 'none')


def test_the_add_on_reads_no_environment_variable(monkeypatch):
    """PaaS's MCP_GATEWAY_MAX_BUFFERED_BYTES, _PER_PROFILE, MCP_GATEWAY_BODY_IDLE_SECONDS and _TOTAL_SECONDS change
    nothing: HA's limits are program constants (contract 9, #45; PaaS
    test_environment_overrides_and_invalid_values_warn, test_environment_variables_still_win,
    test_invalid_idle_env_warns_without_echoing_the_value and
    test_total_upload_deadline_env_is_validated have nothing to set here)."""
    module = ceiling(monkeypatch, 1024)
    before = module.BudgetLimits.derive('odoo')
    for name, value in (('MCP_GATEWAY_MAX_BUFFERED_BYTES', str(200 * MiB)),
                        ('MCP_GATEWAY_MAX_BUFFERED_BYTES_PER_PROFILE', str(50 * MiB)),
                        ('MCP_GATEWAY_BODY_IDLE_SECONDS', '1'), ('MCP_GATEWAY_BODY_TOTAL_SECONDS', '3')):
        monkeypatch.setenv(name, value)
    assert module.BudgetLimits.derive('odoo') == before
    assert before.idle_seconds == module.BODY_IDLE_SECONDS == 30


def test_each_profiles_share_is_capped_at_its_quota():
    """HA stricter than PaaS (contract 9): a profile's share is at most its quota's byte budget (64 MiB, DQ-07's value)
    however large the add-on's budget is; below it, the PaaS share (half the budget, at least 16 MiB)."""
    large = budget(1024, 512)
    assert profiles.DEFAULT_PROFILE_QUOTA.body_bytes == profiles.EXTRA_PROFILE_QUOTA.body_bytes == 64 * MiB
    assert large.share('default', cap=profiles.DEFAULT_PROFILE_QUOTA.body_bytes).limit == 64 * MiB
    small = budget(40, 20)
    assert small.share('default', cap=64 * MiB).limit == 20 * MiB
    module = rb()
    assert module.default_per_profile_bytes(40 * MiB) == 20 * MiB
    assert module.default_per_profile_bytes(16 * MiB) == 16 * MiB  # half of the floor is less than one request


def test_switched_off_counts_one_account_and_switched_on_the_products_capacity(monkeypatch):
    """Switched off, the default profile alone runs (one account); switched on, the default profile and the product's
    additional-profile capacity (PaaS: 1 + current_profile_capacity().limit), each with the product's child estimate."""
    module = rb()
    assert module.runtime_inputs('odoo', switched_on=False) == (1, 100)
    assert module.runtime_inputs('odoo', switched_on=True) == (6, 100)
    assert module.runtime_inputs('n8n', switched_on=True) == (3, 300)
    assert module.runtime_inputs('hermes', switched_on=True) == (4, 160)
    assert module.runtime_inputs('opendesign', switched_on=True) == (1, 160)  # no additional profile (DQ-28)
    assert module.runtime_inputs(None, switched_on=True) == (1, 160)
    # under a cgroup limit, the memory caps the capacity as the profile capacity does: 600 MiB fits 3 Odoo children
    assert module.runtime_inputs('odoo', switched_on=True, memory_limit=600) == (3, 100)
    ceiling(monkeypatch, 4096)
    off, on = module.BudgetLimits.derive('odoo'), module.BudgetLimits.derive('odoo', switched_on=True)
    assert off.total == int((4096 - 76 - 100 - 150) * MiB / 20)
    assert on.total == int((4096 - 256 - 76 - 600 - 150 - 512 - 221 - 64) * MiB
                           / module.ODOO_ADMISSION_AMPLIFICATION) < off.total
    assert off.small_minimum == 0
    assert module.BudgetLimits.derive('n8n', switched_on=True).small_minimum == 0


def test_odoo_reply_and_body_reservations_fit_three_gib_without_relaxing_release_gate(monkeypatch):
    module = ceiling(monkeypatch, 3072)
    limits = module.BudgetLimits.derive('odoo', switched_on=True)
    assert module.AMPLIFICATION == 20  # the §5 release gate, distinct from conservative admission
    assert module.ODOO_ADMISSION_AMPLIFICATION == 64
    assert limits.total >= 16 * MiB and limits.per_profile == 16 * MiB
    accounted = (256 + 76 + 600 + 150 + 512 + 221 + 64  # 0.5.1: 64 GET streams x 1 MiB
                 + limits.total / MiB * module.ODOO_ADMISSION_AMPLIFICATION)
    assert accounted <= 3072
    assert limits.small_minimum == 64 * 1024
    assert module.odoo_switched_memory_fits(3072, 6, 'cgroup')
    assert not module.odoo_switched_memory_fits(2048, 6, 'cgroup')
    assert not module.odoo_switched_memory_fits(None, 6, 'none')


def test_odoo_host_memavailable_is_reserved_once_and_switched_off_is_unchanged(monkeypatch):
    module = ceiling(monkeypatch, 5970, 'meminfo')  # memory_ceiling already removed 256 MiB
    on = module.BudgetLimits.derive('odoo', switched_on=True)
    assert on.total == int((5970 - 76 - 600 - 150 - 512 - 221 - 64) * MiB / 64)
    off = module.BudgetLimits.derive('odoo', switched_on=False)
    assert off.total == int((5970 - 76 - 100 - 150) * MiB / 20)


@pytest.mark.parametrize('ceiling_mib,source,fits', [
    (2048, 'cgroup', False), (2902, 'cgroup', False), (2903, 'cgroup', True),  # 0.5.1: 2,839 + 64 stream MiB
    (3072, 'cgroup', True), (2646, 'meminfo', False), (2647, 'meminfo', True),
    (None, 'none', False),
])
def test_odoo_activation_requires_joint_floor(ceiling_mib, source, fits):
    module = rb()
    assert module.odoo_switched_memory_fits(ceiling_mib, 6, source) is fits


async def test_odoo_small_body_reserves_before_parse_and_refunds_after_end():
    module = rb()
    limits = module.BudgetLimits(total=module.SMALL_REQUEST_BYTES * 2,
                                 per_profile=module.SMALL_REQUEST_BYTES * 2,
                                 small_minimum=module.SMALL_REQUEST_BYTES)
    owner = module.RequestBudget(limits)

    class Small:
        method = 'POST'

        def __init__(self):
            from starlette.datastructures import Headers
            self.headers = Headers(raw=[(b'content-length', b'56127')])
            self.read = False

        async def stream(self):
            self.read = True
            assert owner.used() >= module.SMALL_REQUEST_BYTES  # ingress reserved before parser receives bytes
            yield b'{' + b' ' * 56125 + b'}'

    live = []
    for profile in ('a', 'b'):
        request = Small()
        reservation = owner.share(profile, cap=MiB).open()
        module.watch(request, reservation, cap=CAP)
        async for _ in request.stream():
            pass
        assert request.read
        live.append(reservation)
    assert owner.used() == 2 * module.SMALL_REQUEST_BYTES
    refused = Small()
    reservation = owner.share('c', cap=MiB).open()
    module.watch(refused, reservation, cap=CAP)
    with pytest.raises(module.BudgetExceeded) as error:
        async for _ in refused.stream():
            pass
    assert error.value.scope == 'global' and not refused.read
    reservation.close()
    live[0].close()  # the ASGI completion or cancellation path returns the reservation
    assert owner.used() == module.SMALL_REQUEST_BYTES
    later = Small()
    reservation = owner.share('c', cap=MiB).open()
    module.watch(later, reservation, cap=CAP)
    async for _ in later.stream():
        pass
    assert later.read
    reservation.close()
    live[1].close()
    assert owner.used() == 0


def test_more_accounts_or_heavier_children_shrink_the_budget():
    module = rb()
    few = module.default_total_bytes(2048, accounts=2, child_memory_mib=100)
    many = module.default_total_bytes(2048, accounts=6, child_memory_mib=100)
    heavy = module.default_total_bytes(2048, accounts=6, child_memory_mib=300)
    assert few > many > heavy >= 16 * MiB


def test_formula_matches_the_documented_arithmetic():
    module = rb()
    total = module.default_total_bytes(2048, accounts=6, child_memory_mib=100)  # 2 GiB, Odoo switched on
    assert total == int((2048 - 76 - 6 * 100 - 150) * MiB / 20)
    assert module.default_per_profile_bytes(total) == max(16 * MiB, int(total * .5))


def test_a_small_ceiling_is_clamped_to_the_single_request_ceiling():
    module = rb()
    assert module.default_total_bytes(512, accounts=6, child_memory_mib=100) == 16 * MiB
    assert module.default_total_bytes(10 ** 9, accounts=1, child_memory_mib=100) == module.MAX_BUDGET_BYTES


# The PaaS sandbox scenarios (test_gateway_budget_defaults.SCENARIOS): (accounts, policy child MiB, measured child RSS,
# measured amplification). HA has no 1 GiB Pod; the same arithmetic holds for a 1 GiB ceiling (cgroup or MemAvailable).
SCENARIOS = {'odoo-6-accounts': (6, 100, 92, 6.8), 'hermes-4-accounts': (4, 160, 92, 6.8),
             'n8n-2-accounts': (2, 300, 270, 8.3)}


def headroom(memory, accounts, child, total, amplification):
    return memory - (rb().GATEWAY_BASELINE_MIB + accounts * child + total / MiB * amplification)


@pytest.mark.parametrize('name', sorted(SCENARIOS))
def test_a_one_gib_ceiling_keeps_the_sandbox_headroom(name):
    accounts, policy_child, real_child, real_amp = SCENARIOS[name]
    module = rb()
    total = module.default_total_bytes(1024, accounts=accounts, child_memory_mib=policy_child)
    assert headroom(1024, accounts, real_child, total, real_amp) >= 200, name
    assert headroom(1024, accounts, policy_child, total, module.AMPLIFICATION) >= module.SAFETY_MARGIN_MIB - 1 \
        or total == module.MIN_BUDGET_BYTES
    assert total >= 16 * MiB and module.default_per_profile_bytes(total) >= 16 * MiB


def test_the_old_paas_defaults_would_have_failed_the_sandbox_scenarios():
    accounts, _, real_child, real_amp = SCENARIOS['odoo-6-accounts']
    assert headroom(1024, accounts, real_child, int(83.8 * MiB), real_amp) < 100


def test_the_amplification_covers_the_measured_worst_cases():
    """PaaS: one ASCII string 5.5, the guard's worst structure 8.0, one astral character 15.2, both 17.8 (round 3):
    never back under 18."""
    assert rb().AMPLIFICATION >= 18


def test_python_str_really_is_four_bytes_per_character_with_one_astral_character():
    n = 2 * MiB
    ascii_str = json.loads(b'"' + b'a' * n + b'"')
    cjk_str = json.loads(('"' + '你' * (n // 3) + '"').encode())
    astral_str = json.loads(b'"' + b'a' * n + '\U0001F600'.encode() + b'"')
    escaped = json.loads(b'"' + b'a' * n + b'\\ud83d\\ude00"')
    assert sys.getsizeof(ascii_str) < 1.1 * n
    assert 1.9 * (n // 3) < sys.getsizeof(cjk_str) < 2.2 * (n // 3)
    assert sys.getsizeof(astral_str) > 3.9 * n and sys.getsizeof(escaped) > 3.9 * n


def test_a_two_gib_ceiling_holds_the_paas_measured_astral_multiplier():
    """The formula's arithmetic at PaaS's measured multiplier (15.2: PaaS's gateway, which forwards the bytes it read,
    and an MCP SDK child, for a large string with one non-BMP character): six Odoo accounts on 2 GiB keep the margin.
    Not a guarantee for HA: HA's gateway re-serializes, and on its own it peaks at 14 times the charge for that body and
    27.6 times for about 0.8 MiB of the guard's most elements (HM-31 review MF-2, contract 5); HM-19c measures HA's
    gateway and child together (contract 5)."""
    module = rb()
    total = module.default_total_bytes(2048, accounts=6, child_memory_mib=100)
    assert module.GATEWAY_BASELINE_MIB + 6 * 100 + total / MiB * 15.2 <= 2048 - module.SAFETY_MARGIN_MIB + 1


def test_a_one_gib_ceiling_is_at_the_single_request_floor_for_every_switched_on_product():
    module = rb()
    for accounts, child in ((6, 100), (4, 160), (3, 300)):  # Odoo, Hermes, n8n switched on
        assert module.default_total_bytes(1024, accounts=accounts, child_memory_mib=child) == 16 * MiB


# ---- the accounting (PaaS test_gateway_request_budget.py section 2) ----

def test_small_requests_are_never_charged_or_refused():
    owner = budget(16, 16)
    full = share(owner).open()
    full.grow(15 * MiB, cap=CAP)
    notification = share(owner).open()
    notification.grow(2048, cap=CAP)
    notification.grow(64 * 1024, cap=CAP)
    notification.forward(64 * 1024)  # HA: forwarded small too
    assert owner.used() == 15 * MiB
    notification.close()
    full.close()
    assert owner.used() == 0


def test_profile_and_global_limits_are_independent():
    module = rb()
    owner = budget(30, 20)
    a1 = share(owner, 'a').open()
    a1.grow(12 * MiB, cap=CAP)
    a2 = share(owner, 'a').open()
    with pytest.raises(module.BudgetExceeded) as profile_full:
        a2.grow(9 * MiB, cap=CAP)
    assert (profile_full.value.scope, profile_full.value.limit) == ('profile', 20 * MiB)
    b1 = share(owner, 'b').open()
    b1.grow(12 * MiB, cap=CAP)  # isolation: A is full, B goes on
    b2 = share(owner, 'b').open()
    with pytest.raises(module.BudgetExceeded) as total_full:
        b2.grow(8 * MiB, cap=CAP)  # 12 + 12 + 8 > 30
    assert (total_full.value.scope, total_full.value.limit) == ('global', 30 * MiB)
    assert owner.used() == 24 * MiB and owner.used('a') == 12 * MiB
    for reservation in (a1, a2, b1, b2):
        reservation.close()
    assert owner.used() == 0 and owner.used('a') == 0


def test_every_profile_can_always_send_one_maximum_size_request():
    owner = budget(16, 16)
    reservation = share(owner, 'only').open()
    reservation.grow(16 * MiB, cap=CAP)
    assert owner.used('only') == 16 * MiB
    reservation.close()


def test_requests_over_the_single_request_cap_are_not_held():
    owner = budget(32, 32)
    reservation = share(owner).open()
    reservation.grow(10 * MiB, cap=CAP)
    assert owner.used() == 10 * MiB
    reservation.grow(17 * MiB, cap=CAP)  # read past the ceiling: refused as too large, what it held goes back
    assert owner.used() == 0
    reservation.grow(40 * MiB, cap=CAP)
    assert owner.used() == 0
    reservation.close()
    assert owner.used() == 0


def test_a_reservation_is_held_until_its_request_ends():
    """PaaS holds a request's bytes until the proxy is done and every upstream response closed (attach and detach);
    HA's gateway closes the reservation once, when the request ends (its answer sent in full, an event stream's end
    included: gateway.AnyMethod). Closing twice gives nothing back twice."""
    owner = budget()
    reservation = share(owner).open()
    reservation.grow(5 * MiB, cap=CAP)
    assert owner.used() == 5 * MiB
    reservation.close()
    assert owner.used() == 0
    reservation.close()
    reservation.grow(9 * MiB, cap=CAP)  # nothing is charged once closed
    reservation.forward(9 * MiB)
    assert owner.used() == 0


def test_a_refused_grow_does_not_leak_and_close_gives_back():
    module = rb()
    owner = budget(32, 20)
    reservation = share(owner, 'a').open()
    reservation.grow(5 * MiB, cap=CAP)
    with pytest.raises(module.BudgetExceeded):
        reservation.grow(21 * MiB, cap=40 * MiB)
    assert owner.used('a') == 5 * MiB  # what was charged stays until the request ends
    reservation.close()
    assert owner.used() == 0 and owner.used('a') == 0


def test_the_forwarded_size_is_charged_when_it_is_larger():
    """HA stricter than PaaS (HM-08 review S-1; contract 9): the gateway re-serializes a body before forwarding it (a
    CJK character 6 bytes, an emoji 12), so the larger of what was read and what is forwarded is charged, without the
    single-request ceiling (the forwarded copy is what the gateway holds)."""
    module = rb()
    owner = budget(40, 40)
    reservation = share(owner).open()
    reservation.grow(4 * MiB, cap=CAP)
    reservation.forward(12 * MiB)  # 4 MiB of emoji, forwarded with escapes
    assert owner.used() == 12 * MiB
    reservation.forward(3 * MiB)  # smaller: nothing changes
    assert owner.used() == 12 * MiB
    small = share(owner).open()
    small.grow(40 * 1024, cap=CAP)
    small.forward(120 * 1024)  # read small, forwarded large: charged
    assert owner.used() == 12 * MiB + 120 * 1024
    big = share(owner).open()
    big.grow(15 * MiB, cap=CAP)
    with pytest.raises(module.BudgetExceeded) as caught:
        big.forward(45 * MiB)  # 15 MiB of emoji: 45 MiB forwarded does not fit what is left
    assert caught.value.scope == 'profile'
    for reservation_ in (reservation, small, big):
        reservation_.close()
    assert owner.used() == 0


def test_a_thousand_mixed_requests_give_the_budget_back_to_zero():
    module = rb()
    rng = random.Random(7)
    owner = budget(48, 24)
    live = []
    for _ in range(1000):
        reservation = share(owner, rng.choice('abc')).open()
        try:
            reservation.grow(rng.choice([0, 300, 70_000, 3 * MiB, 9 * MiB, 15 * MiB, 17 * MiB]), cap=CAP)
            if rng.random() < .5:
                reservation.grow(reservation.size + rng.choice([0, 2 * MiB, 8 * MiB]), cap=CAP)
            if rng.random() < .3:
                reservation.forward(rng.choice([0, 50_000, 5 * MiB, 20 * MiB]))
        except module.BudgetExceeded:
            pass
        if rng.random() < .7:
            reservation.close()
        else:
            live.append(reservation)
        if len(live) > 12:
            live.pop(rng.randrange(len(live))).close()
        assert 0 <= owner.used() <= 48 * MiB
        assert all(owner.used(p) <= 24 * MiB for p in 'abc')
    for reservation in live:
        reservation.close()
    assert owner.used() == 0 and owner._profiles == {}


def test_an_astral_request_is_charged_and_refused_under_a_small_budget():
    """The charge is the body's bytes (the amplification is in the defaults): two 15 MiB astral requests do not fit a
    16 MiB budget."""
    module = rb()
    owner = budget(16, 16)
    first = share(owner).open()
    first.grow(15 * MiB, cap=CAP)
    second = share(owner).open()
    with pytest.raises(module.BudgetExceeded):
        second.grow(15 * MiB, cap=CAP)
    first.close()
    second.close()
    assert owner.used() == 0


def test_a_budget_and_its_limits_refuse_nonsense():
    module = rb()
    for total, per_profile, idle in ((0, 1, 1), (1, 0, 1), (1.5, 1, 1), (1, 1, 0), (1, 1, True), (1, 1, float('nan'))):
        with pytest.raises(ValueError):
            module.BudgetLimits(total=total, per_profile=per_profile, idle_seconds=idle)
    with pytest.raises(ValueError):
        module.RequestBudget({'total': 1})
    with pytest.raises(ValueError):
        budget().share('default', cap=0)


# ---- reading a body: the declared length, the id of a body that is not parsed ----

def test_the_declared_length_is_one_plain_number_and_never_beside_a_transfer_encoding():
    """declared_length reads the ASGI scope's headers (the gateway's watch and body, the dispatcher's admission-full
    read: one rule). RFC 9112 6.3: a Transfer-Encoding frames the body and its Content-Length is ignored; h11 0.16.0,
    the add-on's parser, reads such a request as chunked and hands content-length on as sent (HM-31 review MF-1, S-6),
    so the body is then counted as it arrives."""
    module = rb()

    def length(*pairs):
        return module.declared_length([(name.encode('latin-1'), value.encode('utf-8')) for name, value in pairs])
    assert length(('content-length', '1024')) == 1024 and length(('content-length', '0')) == 0
    assert length(('Content-Length', '7')) == 7  # ASGI names are lower case; any case is read the same
    for values in ([], ['1', '1'], ['-1'], ['1e3'], ['0x10'], [' '], ['１２'], ['9' * 20]):
        assert length(*(('content-length', value) for value in values)) is None, values
    for pairs in ((('content-length', '10'), ('transfer-encoding', 'chunked')),
                  (('transfer-encoding', 'chunked'), ('content-length', '70000')),
                  (('Transfer-Encoding', 'chunked'), ('content-length', '10')), (('transfer-encoding', 'chunked'),)):
        assert length(*pairs) is None, pairs
    assert not module.registered(64 * 1024) and module.registered(64 * 1024 + 1) and module.registered(None)


class Streamed:
    """What watch reads of a request: its headers and its stream (here size bytes in 256 KiB chunks)."""

    def __init__(self, headers, size):
        from starlette.datastructures import Headers
        self.headers, self.size, self.handed = Headers(raw=headers), size, 0

    async def stream(self):
        chunk = b'{"jsonrpc":"2.0","id":3,"method":"x","params":{"p":"' + b'x' * (256 * 1024 - 52)
        while self.handed < self.size:
            self.handed += len(chunk)
            yield chunk


async def test_the_bytes_that_arrive_are_charged_whatever_was_declared():
    """HM-31 review MF-1: a declared length is charged before the body is read and is no bound on what arrives. A body
    that states 70,000 bytes and sends 10 MiB (framed otherwise: h11 frames by a Transfer-Encoding, which
    declared_length already reads as nothing) is charged by what arrives and cut off once it does not fit, its head
    kept for its id; one that sends what it states adds nothing to what was charged before it was read."""
    module = rb()
    owner = budget(16, 16)
    held = share(owner).open()
    held.grow(10 * MiB, cap=CAP)
    request = Streamed([(b'content-length', b'70000')], 10 * MiB)
    reservation = share(owner).open()
    module.watch(request, reservation, cap=CAP)
    with pytest.raises(module.BudgetExceeded) as refused:
        async for _ in request.stream():
            pass
    assert refused.value.read and module.head_tail_id(refused.value.head) == 3
    assert request.handed < 10 * MiB and owner.used() <= 16 * MiB
    reservation.close()
    honest = Streamed([(b'content-length', str(256 * 1024).encode())], 256 * 1024)
    reservation = share(owner).open()
    module.watch(honest, reservation, cap=CAP)
    async for _ in honest.stream():
        assert owner.used() == 10 * MiB + 256 * 1024  # charged when its read began; what arrived added nothing
    reservation.close()
    held.close()
    assert owner.used() == 0


@pytest.mark.parametrize('head,tail,expected', [
    (b'{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{', b'', 7),
    (b'{ "jsonrpc" : "2.0" , "id" : "a-b" , "method" : "x"}', b'', 'a-b'),
    (b'{"method":"tools/call","params":{"x":"', b'","id":"not-this"},"jsonrpc":"2.0","id":-12}', -12),
    (b'{"method":"tools/call","params":{}', b'"jsonrpc":"2.0","id":3}', None),  # the tail needs a , or { before it
    (b'[{"jsonrpc":"2.0","id":1,"method":"x"}]', b'', None),  # a batch
    (b'{"jsonrpc":"2.0","method":"notifications/initialized"}', b'', None),
    (b'{"id":1,"jsonrpc":"2.0","method":"x"}', b'', None),  # another layout
    (b'{"jsonrpc":"2.0","id":true,"method":"x"}', b'', None),
    (b'{"jsonrpc":"2.0","id":1.5,"method":"x"}', b'', None),
    (b'{"jsonrpc":"2.0","id":"' + b'x' * 257 + b'","method":"x"}', b'', None),
    (b'', b'', None),
])
def test_the_head_and_tail_of_a_body_show_a_single_requests_id(head, tail, expected):
    """PaaS request_body._request_id (d7f5849): only the outer level of one request object, the id first (hand-written
    clients) or last (the MCP SDKs); a string or an integer."""
    module = rb()
    assert module.head_tail_id(head, tail) == expected
    message = module.unread_message(expected)
    assert message == (None if expected is None else {'jsonrpc': '2.0', 'id': expected, 'method': 'unread'})


def test_the_refusal_texts_name_the_layer_and_never_content():
    module = rb()
    profile = module.budget_text(module.BudgetExceeded('profile', 16 * MiB))
    add_on = module.budget_text(module.BudgetExceeded('global', 24 * MiB))
    assert profile.startswith('this MCP URL is already holding 16 MiB of request bodies, the limit')
    assert add_on.startswith('this MCP server (all of its URLs together) is already holding 24 MiB')
    assert '這個 MCP 網址' in profile and '所有網址合計' in add_on
    assert module.idle_text(30).startswith('No request body data arrived for 30 seconds')
    assert 'held 16 MiB of request bodies, its share' in module.budget_note(module.BudgetExceeded('profile', 16 * MiB))
    assert "the add-on's byte budget" in module.budget_note(module.BudgetExceeded('global', 16 * MiB))


# ---- one WARNING per profile and situation a minute (PaaS test_refusal_report_is_throttled_per_profile...) ----

def test_refusal_reports_are_throttled_per_profile_with_a_suppressed_count(log_scan):
    module = rb()
    reports = module.Reports()
    clock = [1000.0]
    reports.clock = lambda: clock[0]
    for _ in range(3):
        reports.warn('default', 'bytes', 'MCP gateway [profile=default]: line')
    reports.warn('b0' * 12, 'bytes', 'MCP gateway [profile=b0b0b0b0]: line')
    clock[0] += module.REPORT_SECONDS + 1
    reports.warn('default', 'bytes', 'MCP gateway [profile=default]: line')
    lines = [record.getMessage() for record in log_scan.records
             if record.name == 'mcp_admin_core.request_budget' and record.levelno == logging.WARNING]
    assert lines == ['MCP gateway [profile=default]: line', 'MCP gateway [profile=b0b0b0b0]: line',
                     'MCP gateway [profile=default]: line suppressed=2']
    from mcp_admin_core import profile_router
    assert profile_router.Reports().log is profile_router.logger  # a switched-on add-on's lines: the router's logger
    assert (profile_router.REPORT_SECONDS, profile_router.MAX_REPORT_KEYS) == (60, 256)


def test_a_switched_off_add_on_has_a_budget_of_its_own(monkeypatch, log_scan):
    """gateway.make_apps without a body_budget: own_share derives the add-on's budget now (startup) for one account of
    the product, and the default profile's share of it (capped at its quota); its WARNINGs name the default profile."""
    module = ceiling(monkeypatch, 4096)
    first, second = module.own_share('odoo'), module.own_share('odoo')
    assert first.budget is not second.budget  # one per add-on (each make_apps)
    assert first.budget.limits.total == int((4096 - 76 - 100 - 150) * MiB / 20)
    assert first.limit == min(64 * MiB, first.budget.limits.per_profile) and first.profile_id == 'default'
    first.warn('bytes', 'its requests in progress held 16 MiB')
    assert [record.getMessage() for record in log_scan.records if record.name == 'mcp_admin_core.request_budget'] == [
        'MCP gateway [profile=default]: its requests in progress held 16 MiB']
