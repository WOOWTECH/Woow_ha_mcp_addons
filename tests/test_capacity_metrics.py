"""Focused contract tests for opt-in capacity evidence."""

import asyncio
from dataclasses import FrozenInstanceError
import time

import pytest

from mcp_admin_core.capacity_metrics import CapacityMetrics
from mcp_admin_core.request_budget import BudgetLimits, RequestBudget


@pytest.mark.asyncio
async def test_disabled_probe_is_inert_and_allocates_no_task(monkeypatch):
    probe = CapacityMetrics()
    before = asyncio.all_tasks()
    monkeypatch.setattr(time, 'monotonic_ns', lambda: pytest.fail('disabled probe read clock'))
    probe.start()
    probe.on_charge_change('not even evaluated')
    assert probe.snapshot() is None
    assert await probe.stop() is None
    assert asyncio.all_tasks() == before


@pytest.mark.asyncio
async def test_charge_hook_is_bounded_numeric_and_preserves_peak_after_overflow():
    probe = CapacityMetrics(enabled=True, max_charge_samples=2, max_lag_samples=2)
    probe.start()
    for value in (10, 20, 5, 0):
        probe.on_charge_change(value)
    snap = await probe.stop()
    assert snap is not None
    assert snap.charged_bytes_now == 0
    assert snap.charged_bytes_peak == 20
    assert snap.started_at_monotonic_ns <= snap.charged_peak_at_monotonic_ns <= snap.stopped_at_monotonic_ns
    assert [row.charged_bytes for row in snap.charge_samples] == [5, 0]
    assert snap.dropped_charge_samples == 2
    assert all(snap.started_at_monotonic_ns <= row.at_monotonic_ns <= snap.stopped_at_monotonic_ns
               for row in snap.charge_samples)
    with pytest.raises(FrozenInstanceError):
        snap.charged_bytes_peak = 99
    assert await probe.stop() == snap


@pytest.mark.asyncio
async def test_hook_records_actual_budget_total_across_charge_forward_and_refund():
    budget = RequestBudget(BudgetLimits(total=300_000, per_profile=300_000))
    reservation = budget.share('private-profile-id', cap=300_000).open()
    probe = CapacityMetrics(enabled=True)
    probe.start()
    reservation.grow(100_000, cap=300_000)
    probe.on_charge_change(budget.used())
    reservation.forward(120_000)
    probe.on_charge_change(budget.used())
    reservation.close()
    probe.on_charge_change(budget.used())
    snap = await probe.stop()
    assert snap is not None
    assert [row.charged_bytes for row in snap.charge_samples] == [100_000, 120_000, 0]
    assert snap.charged_bytes_peak == 120_000
    assert 'private-profile-id' not in repr(snap)


@pytest.mark.asyncio
async def test_lag_probe_observes_event_loop_block_and_stops():
    probe = CapacityMetrics(enabled=True, interval_seconds=0.005, max_lag_samples=2)
    probe.start()
    await asyncio.sleep(0.015)
    time.sleep(0.05)  # Deliberately block the loop; the wake-up should be late.
    await asyncio.sleep(0.015)
    snap = await probe.stop()
    assert snap is not None
    assert snap.lag_max_ns >= 20_000_000
    assert snap.lag_max_at_monotonic_ns is not None
    assert 1 <= len(snap.lag_samples) <= 2
    assert snap.dropped_lag_samples > 0
    assert not any(task.get_name() == 'capacity-loop-lag' for task in asyncio.all_tasks())


@pytest.mark.asyncio
async def test_rejects_invalid_or_cross_loop_charge_samples():
    probe = CapacityMetrics(enabled=True)
    with pytest.raises(RuntimeError):
        probe.on_charge_change(1)
    probe.start()
    for value in (-1, True, 1.2, 'secret', 2**63):
        with pytest.raises(ValueError):
            probe.on_charge_change(value)
    with pytest.raises(RuntimeError):
        probe.start()
    assert await asyncio.to_thread(_call_from_new_loop, probe) == 'wrong loop'
    await probe.stop()
    with pytest.raises(RuntimeError):
        probe.on_charge_change(1)


def _call_from_new_loop(probe):
    try:
        asyncio.run(_record(probe))
    except RuntimeError:
        return 'wrong loop'
    return 'incorrectly accepted'


async def _record(probe):
    probe.on_charge_change(1)


@pytest.mark.parametrize('kwargs', [
    {'enabled': 1}, {'interval_seconds': 0}, {'interval_seconds': float('nan')},
    {'interval_seconds': 2}, {'max_charge_samples': 0}, {'max_charge_samples': 65537},
    {'max_lag_samples': True}, {'max_lag_samples': 8193},
])
def test_rejects_unbounded_or_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        CapacityMetrics(**kwargs)
