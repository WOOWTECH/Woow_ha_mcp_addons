"""Opt-in runtime evidence wiring without a host or network service."""

import asyncio
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from types import SimpleNamespace

import httpx
import pytest

from mcp_admin_core.capacity_metrics import (
    CapacityMetrics, LagSample, activate, deactivate, write_evidence,
)
from mcp_admin_core.health import HealthMonitor
from mcp_admin_core.reply_worker import ReplyWorker
from mcp_admin_core import request_budget, run_product


@pytest.mark.asyncio
async def test_shared_budget_records_actual_charge_and_refund_not_failed_admission():
    probe = CapacityMetrics(enabled=True)
    probe.start()
    token = activate(probe)
    try:
        budget = request_budget.RequestBudget(request_budget.BudgetLimits(
            total=128 * 1024, per_profile=128 * 1024, small_minimum=64 * 1024))
    finally:
        deactivate(token)
    reservation = budget.share('default', cap=128 * 1024).open()
    assert probe.snapshot().charge_hook_calls == 1
    reservation.reserve_small()
    assert budget.used() == 64 * 1024
    assert probe.snapshot().charged_bytes_peak == 64 * 1024
    with pytest.raises(request_budget.BudgetExceeded):
        reservation.grow(256 * 1024, cap=16 * 1024 * 1024)
    assert budget.used() == 64 * 1024 and probe.snapshot().charge_hook_calls == 2
    reservation.close()
    snap = await probe.stop()
    assert budget.used() == 0
    assert snap.charge_hook_calls == 3
    assert [row.charged_bytes for row in snap.charge_samples] == [0, 64 * 1024, 0]


def test_environment_requires_exact_opt_in(monkeypatch):
    monkeypatch.delenv('WOOW_CAPACITY_METRICS', raising=False)
    assert not run_product.capacity_opted_in()
    for value in ('', '0', 'true', 'yes', '2'):
        monkeypatch.setenv('WOOW_CAPACITY_METRICS', value)
        assert not run_product.capacity_opted_in()
    monkeypatch.setenv('WOOW_CAPACITY_METRICS', '1')
    assert run_product.capacity_opted_in()


@pytest.mark.asyncio
async def test_scheduled_health_check_and_registered_zero_check_slot(monkeypatch):
    probe = CapacityMetrics(enabled=True)
    probe.start()
    token = activate(probe)
    try:
        first = HealthMonitor(None, SimpleNamespace(), None)
        second = HealthMonitor(None, SimpleNamespace(), None)
    finally:
        deactivate(token)

    called = asyncio.Event()

    async def checked():
        first._capacity_phase = 2
        first.backend = 'reachable'
        called.set()
        return (0, True, 'reachable', None)

    monkeypatch.setattr(first, '_check_saved', checked)
    task = asyncio.create_task(first.run())
    await asyncio.wait_for(called.wait(), 1)
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    snap = await probe.stop()
    assert snap.health_monitors_registered == 2
    assert not hasattr(snap, 'health_monitor_child_ports')
    assert snap.health_checks_by_slot == (1, 0)
    assert snap.health_inflight_by_slot == (0, 0)
    assert snap.health_checks_scheduled == 1
    row = snap.health_samples[0]
    assert row.slot == first._capacity_slot
    assert row.phase == 2 and row.outcome == 0
    assert snap.started_at_monotonic_ns <= row.scheduled_at_monotonic_ns <= row.started_at_monotonic_ns <= row.ended_at_monotonic_ns
    assert row.duration_ns == row.ended_at_monotonic_ns - row.scheduled_at_monotonic_ns
    assert row.execution_ns == row.ended_at_monotonic_ns - row.started_at_monotonic_ns
    assert second._capacity_slot == 1
    assert 'health_monitor_child_ports' not in asdict(snap)


@pytest.mark.asyncio
async def test_inflight_health_check_is_counted_before_it_completes(monkeypatch):
    probe = CapacityMetrics(enabled=True)
    probe.start()
    token = activate(probe)
    try:
        monitor = HealthMonitor(None, SimpleNamespace(), None)
    finally:
        deactivate(token)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def checked():
        entered.set()
        await release.wait()

    monkeypatch.setattr(monitor, '_check_saved', checked)
    task = asyncio.create_task(monitor.run())
    await asyncio.wait_for(entered.wait(), 1)
    during = probe.snapshot()
    assert during.health_checks_by_slot == (1,)
    assert during.health_inflight_by_slot == (1,)
    assert during.health_samples == ()
    release.set()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    after = await probe.stop()
    assert after.health_inflight_by_slot == (0,)
    assert len(after.health_samples) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('error_type', [TimeoutError, httpx.ConnectTimeout, httpx.ReadTimeout])
async def test_scheduled_health_timeout_records_initialization_phase(monkeypatch, error_type):
    class TimedOutClient:
        def stream(self, *args, **kwargs):
            raise error_type('transport timed out')

    probe = CapacityMetrics(enabled=True)
    probe.start()
    token = activate(probe)
    try:
        monitor = HealthMonitor(None, SimpleNamespace(), TimedOutClient())
    finally:
        deactivate(token)
    called = asyncio.Event()

    async def checked():
        await monitor._check(SimpleNamespace(child_token='unused'), True, 'odoo')
        called.set()

    monkeypatch.setattr(monitor, '_check_saved', checked)
    task = asyncio.create_task(monitor.run())
    await asyncio.wait_for(called.wait(), 1)
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    snap = await probe.stop()
    assert snap.health_samples[0].phase == 1
    assert snap.health_samples[0].outcome == 2


@pytest.mark.asyncio
async def test_lag_bound_and_50ms_gate_include_sampling_interval():
    probe = CapacityMetrics(enabled=True, interval_seconds=0.01)
    probe.start()
    assert probe.snapshot().lag_50ms_gate_pass is None
    at = time.monotonic_ns()
    probe._lag_max = 45_000_000
    probe._lag_max_at = at
    probe._lag_samples.append(LagSample(at, 45_000_000))
    snap = probe.snapshot()
    assert snap.lag_max_ns == 45_000_000
    assert snap.lag_pause_bound_ns == 55_000_000
    assert snap.lag_50ms_gate_pass == 0
    path = Path('/tmp') / f'hm19c-capacity-metrics-test-{os.getpid()}-{time.monotonic_ns()}.json'
    try:
        write_evidence(snap, path)
        data = json.loads(path.read_text())
        assert data['lag_pause_bound_ns'] == 55_000_000
        assert data['lag_50ms_gate_pass'] == 0
        assert 'health_monitor_child_ports' not in data
    finally:
        path.unlink(missing_ok=True)
    probe._lag_max = 39_000_000
    probe._lag_samples.clear()
    probe._lag_samples.append(LagSample(at, 39_000_000))
    assert probe.snapshot().lag_50ms_gate_pass == 1
    await probe.stop()


@pytest.mark.asyncio
async def test_health_outcome_uses_raw_check_when_tolerance_keeps_ready(monkeypatch):
    probe = CapacityMetrics(enabled=True)
    probe.start()
    token = activate(probe)
    try:
        monitor = HealthMonitor(None, SimpleNamespace(), None)
    finally:
        deactivate(token)

    async def checked():
        monitor._capacity_phase = 2
        monitor.backend = 'reachable'  # A tolerated previous verdict.
        return (0, True, 'unreachable', None)

    monkeypatch.setattr(monitor, '_check_saved', checked)
    await monitor._scheduled_check()
    snap = await probe.stop()
    assert snap.health_samples[0].outcome == 1
    assert snap.health_samples[0].phase == 2


@pytest.mark.asyncio
async def test_worker_records_actual_job_duration_and_failure():
    probe = CapacityMetrics(enabled=True)
    probe.start()
    worker = ReplyWorker(capacity_metrics=probe)
    worker.start()

    def succeeds():
        time.sleep(0.01)
        return 7

    def fails():
        raise ValueError('private text must not be recorded')

    try:
        assert await worker.run('private-profile', succeeds) == 7
        with pytest.raises(ValueError):
            await worker.run('private-profile', fails)
    finally:
        await worker.stop()
    snap = await probe.stop()
    assert snap.reply_jobs_observed == 2
    assert [row.outcome for row in snap.reply_samples] == [0, 1]
    assert snap.reply_d_max_ns >= 10_000_000
    assert all(row.duration_ns == row.ended_at_monotonic_ns - row.started_at_monotonic_ns
               for row in snap.reply_samples)
    assert 'private-profile' not in repr(snap)
    assert 'private text' not in repr(snap)


@pytest.mark.asyncio
async def test_signal_dump_freezes_metrics_before_write(monkeypatch):
    probe = CapacityMetrics(enabled=True)
    probe.start()
    requested = asyncio.Event()
    saved = []
    monkeypatch.setattr(run_product, 'write_evidence', saved.append)
    task = asyncio.create_task(run_product.dump_capacity_on_signal(probe, requested))
    await asyncio.sleep(0)
    assert not task.done() and saved == []
    requested.set()
    await asyncio.wait_for(task, 1)
    assert len(saved) == 1
    assert saved[0].stopped_at_monotonic_ns is not None
    assert saved[0] == probe.snapshot()
    probe.on_charge_change(1)
    assert probe.snapshot().charged_bytes_now == 0


@pytest.mark.asyncio
async def test_numeric_json_is_private_tmp_only_and_replaces_symlink_itself(tmp_path):
    probe = CapacityMetrics(enabled=True)
    probe.start()
    probe.on_charge_change(123456)
    snap = await probe.stop()
    assert snap is not None
    with tempfile.TemporaryDirectory(prefix='hm19c-capacity-test-', dir='/tmp') as scratch:
        path = Path('/tmp') / f'hm19c-capacity-metrics-test-{os.getpid()}-{time.monotonic_ns()}.json'
        target = Path(scratch) / 'untouched'
        target.write_text('private sentinel')
        try:
            path.symlink_to(target)
            write_evidence(snap, path)
            assert target.read_text() == 'private sentinel'
            assert path.is_file() and not path.is_symlink()
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            data = json.loads(path.read_text())
            assert data['charged_bytes_peak'] == 123456
            assert data['health_checks_scheduled'] == 0
            assert data['health_monitors_registered'] == 0
            assert _numeric_tree(data)
            assert 'private' not in json.dumps(data)
            with pytest.raises(ValueError):
                write_evidence(snap, tmp_path / 'hm19c-capacity-metrics.json')
            with pytest.raises(ValueError):
                write_evidence(snap, Path('/data/mcp/hm19c-capacity-metrics.json'))
            with pytest.raises(ValueError):
                write_evidence(replace(snap, charged_bytes_now='secret'), path)
            assert 'secret' not in path.read_text()
        finally:
            path.unlink(missing_ok=True)


def _numeric_tree(value):
    if isinstance(value, dict):
        return all(isinstance(key, str) and _numeric_tree(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_numeric_tree(item) for item in value)
    return value is None or type(value) is int
