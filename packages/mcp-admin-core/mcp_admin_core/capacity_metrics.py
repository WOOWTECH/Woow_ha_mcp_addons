"""Opt-in in-process capacity evidence; no endpoint, logger, or file output.

Integrate on the gateway event loop. Call start before load, pass the exact
RequestBudget.used() total to on_charge_change after successful changes,
then await stop. The interface accepts numbers only, never profile identity,
token, body, URL, or response data.

The lag value is the largest observed late timer wake-up at the configured
interval; it is not a continuous proof that no shorter pause occurred.
"""

import asyncio
from collections import deque
from contextvars import ContextVar
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time


_active: ContextVar['CapacityMetrics | None'] = ContextVar('capacity_metrics', default=None)
EVIDENCE_PATH = Path('/tmp/hm19c-capacity-metrics.json')


def active_metrics():
    """The opt-in probe in this gateway task's context, if any."""
    return _active.get()


def activate(metrics):
    return _active.set(metrics)


def deactivate(token):
    _active.reset(token)


@dataclass(frozen=True, slots=True)
class ChargeSample:
    at_monotonic_ns: int
    charged_bytes: int


@dataclass(frozen=True, slots=True)
class LagSample:
    at_monotonic_ns: int
    lag_ns: int


@dataclass(frozen=True, slots=True)
class HealthSample:
    slot: int  # ephemeral registration order, never a profile ID
    scheduled_at_monotonic_ns: int
    started_at_monotonic_ns: int | None
    ended_at_monotonic_ns: int
    duration_ns: int
    execution_ns: int | None
    phase: int  # 0 skipped/before check, 1 MCP initialize/ping, 2 backend tool
    outcome: int  # 0 reachable, 1 not reachable, 2 timeout, 3 cancelled, 4 exception


@dataclass(frozen=True, slots=True)
class ReplySample:
    started_at_monotonic_ns: int
    ended_at_monotonic_ns: int
    duration_ns: int
    outcome: int  # 0 returned, 1 raised


@dataclass(frozen=True, slots=True)
class CapacitySnapshot:
    started_at_monotonic_ns: int
    stopped_at_monotonic_ns: int | None
    interval_ns: int
    charged_bytes_now: int
    charged_bytes_peak: int
    charged_peak_at_monotonic_ns: int
    charge_hook_calls: int
    charge_samples: tuple[ChargeSample, ...]
    dropped_charge_samples: int
    lag_max_ns: int
    lag_max_at_monotonic_ns: int | None
    lag_samples: tuple[LagSample, ...]
    dropped_lag_samples: int
    health_monitors_registered: int
    health_monitors_untracked: int
    health_monitor_child_ports: tuple[int | None, ...]
    health_checks_scheduled: int
    health_checks_by_slot: tuple[int, ...]
    health_inflight_by_slot: tuple[int, ...]
    health_samples: tuple[HealthSample, ...]
    dropped_health_samples: int
    reply_jobs_observed: int
    reply_d_max_ns: int
    reply_samples: tuple[ReplySample, ...]
    dropped_reply_samples: int


class CapacityMetrics:
    """Single-loop bounded probe; constructed and started explicitly.

    The charge hook receives the exact current add-on budget total after a
    successful transition. Offered and client-uploaded bytes are invalid.
    History overflow is counted so truncated evidence is visible.
    """

    def __init__(self, *, enabled: bool = False, interval_seconds: float = 0.01,
                 max_charge_samples: int = 32768, max_lag_samples: int = 4096,
                 max_health_samples: int = 2048, max_reply_samples: int = 8192) -> None:
        if not isinstance(enabled, bool):
            raise ValueError('enabled must be bool')
        if (isinstance(interval_seconds, bool) or
                not isinstance(interval_seconds, (float, int)) or
                not math.isfinite(interval_seconds) or
                not 0.001 <= interval_seconds <= 1.0):
            raise ValueError('interval_seconds must be finite and within [0.001, 1]')
        for name, count, limit in (('max_charge_samples', max_charge_samples, 65536),
                                   ('max_lag_samples', max_lag_samples, 8192),
                                   ('max_health_samples', max_health_samples, 8192),
                                   ('max_reply_samples', max_reply_samples, 32768)):
            if type(count) is not int or not 1 <= count <= limit:
                raise ValueError(f'{name} must be in [1, {limit}]')
        self.enabled = enabled
        self._interval_ns = round(interval_seconds * 1_000_000_000)
        self._charge_samples: deque[ChargeSample] = deque(maxlen=max_charge_samples)
        self._lag_samples: deque[LagSample] = deque(maxlen=max_lag_samples)
        self._health_samples: deque[HealthSample] = deque(maxlen=max_health_samples)
        self._reply_samples: deque[ReplySample] = deque(maxlen=max_reply_samples)
        self._dropped_charge_samples = 0
        self._dropped_lag_samples = 0
        self._dropped_health_samples = 0
        self._dropped_reply_samples = 0
        self._health_counts: list[int] = []
        self._health_inflight: list[int] = []
        self._health_ports: list[int | None] = []
        self._health_checks = 0
        self._health_untracked = 0
        self._reply_jobs = 0
        self._reply_d_max = 0
        self._reply_lock = threading.Lock()
        self._charged_now = 0
        self._charged_peak = 0
        self._charged_peak_at = 0
        self._charge_hook_calls = 0
        self._lag_max = 0
        self._lag_max_at: int | None = None
        self._started_at = 0
        self._stopped_at: int | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start the lag probe on the running gateway loop; one run per instance."""
        if not self.enabled:
            return
        if self._started_at:
            raise RuntimeError('capacity metrics already started')
        loop = asyncio.get_running_loop()
        self._loop = loop
        self._started_at = time.monotonic_ns()
        self._charged_peak_at = self._started_at
        self._task = loop.create_task(self._probe(), name='capacity-loop-lag')

    def on_charge_change(self, total_charged_bytes: int) -> None:
        """Record a successful budget accounting transition, numeric only."""
        if not self.enabled:
            return
        if self._stopped_at is not None:
            return
        if self._loop is None:
            raise RuntimeError('capacity metrics must be running')
        if asyncio.get_running_loop() is not self._loop:
            raise RuntimeError('capacity metrics hook called outside gateway loop')
        if type(total_charged_bytes) is not int or not 0 <= total_charged_bytes <= 2**63 - 1:
            raise ValueError('total_charged_bytes must be a nonnegative integer')
        at = time.monotonic_ns()
        self._charge_hook_calls += 1
        self._charged_now = total_charged_bytes
        if total_charged_bytes > self._charged_peak:
            self._charged_peak = total_charged_bytes
            self._charged_peak_at = at
        if len(self._charge_samples) == self._charge_samples.maxlen:
            self._dropped_charge_samples += 1
        self._charge_samples.append(ChargeSample(at, total_charged_bytes))

    def register_health_monitor(self, child_port: int | None = None) -> int | None:
        """Assign an ephemeral numeric slot, including monitors with zero checks."""
        if self._stopped_at is not None:
            return None
        if not self.enabled or self._loop is None or asyncio.get_running_loop() is not self._loop:
            raise RuntimeError('capacity metrics must run on the gateway loop')
        if len(self._health_counts) >= 256:
            self._health_untracked += 1
            return None
        if child_port is not None and (type(child_port) is not int or not 1 <= child_port <= 65535):
            raise ValueError('invalid numeric child port')
        slot = len(self._health_counts)
        self._health_counts.append(0)
        self._health_inflight.append(0)
        self._health_ports.append(child_port)
        return slot

    def on_health_check_scheduled(self, slot: int, scheduled_at_ns: int) -> None:
        """Count the schedule immediately, so zero means no check was started."""
        if self._stopped_at is not None or slot is None:
            return
        if (self._loop is None or asyncio.get_running_loop() is not self._loop or
                type(slot) is not int or not 0 <= slot < len(self._health_counts) or
                type(scheduled_at_ns) is not int or scheduled_at_ns < self._started_at):
            raise ValueError('invalid numeric health schedule')
        self._health_counts[slot] += 1
        self._health_inflight[slot] += 1
        self._health_checks += 1

    def on_scheduled_health_check(self, slot: int, scheduled_at_ns: int,
                                  started_at_ns: int | None, phase: int, outcome: int) -> None:
        """Record a scheduled check with bounded numeric phase and outcome."""
        if self._stopped_at is not None or slot is None:
            return
        if not self.enabled or self._loop is None or asyncio.get_running_loop() is not self._loop:
            raise RuntimeError('capacity metrics must run on the gateway loop')
        if (type(slot) is not int or not 0 <= slot < len(self._health_counts) or
                type(scheduled_at_ns) is not int or scheduled_at_ns < self._started_at or
                (started_at_ns is not None and (type(started_at_ns) is not int or started_at_ns < scheduled_at_ns)) or
                type(phase) is not int or phase not in (0, 1, 2) or
                type(outcome) is not int or outcome not in (0, 1, 2, 3, 4)):
            raise ValueError('invalid numeric health sample')
        ended = time.monotonic_ns()
        if self._health_inflight[slot] < 1:
            raise ValueError('health completion without schedule')
        self._health_inflight[slot] -= 1
        if len(self._health_samples) == self._health_samples.maxlen:
            self._dropped_health_samples += 1
        self._health_samples.append(HealthSample(slot, scheduled_at_ns, started_at_ns,
                                                 ended, ended - scheduled_at_ns,
                                                 ended - started_at_ns if started_at_ns is not None else None,
                                                 phase, outcome))

    def on_reply_job(self, started_at_ns: int, ended_at_ns: int, outcome: int) -> None:
        """Record the worker's actual function span; safe from its thread."""
        if not self.enabled or self._stopped_at is not None:
            return
        if (type(started_at_ns) is not int or type(ended_at_ns) is not int or
                started_at_ns < self._started_at or ended_at_ns < started_at_ns or
                type(outcome) is not int or outcome not in (0, 1)):
            raise ValueError('invalid numeric reply sample')
        duration = ended_at_ns - started_at_ns
        with self._reply_lock:
            if self._stopped_at is not None:
                return
            self._reply_jobs += 1
            self._reply_d_max = max(self._reply_d_max, duration)
            if len(self._reply_samples) == self._reply_samples.maxlen:
                self._dropped_reply_samples += 1
            self._reply_samples.append(ReplySample(started_at_ns, ended_at_ns, duration, outcome))

    async def _probe(self) -> None:
        expected = time.monotonic_ns() + self._interval_ns
        while True:
            await asyncio.sleep(max(0, (expected - time.monotonic_ns()) / 1_000_000_000))
            at = time.monotonic_ns()
            lag = max(0, at - expected)
            if lag > self._lag_max:
                self._lag_max = lag
                self._lag_max_at = at
            if len(self._lag_samples) == self._lag_samples.maxlen:
                self._dropped_lag_samples += 1
            self._lag_samples.append(LagSample(at, lag))
            expected = at + self._interval_ns

    async def stop(self) -> CapacitySnapshot | None:
        """Cancel the probe and return an immutable body-free snapshot."""
        if not self.enabled:
            return None
        if self._loop is None:
            raise RuntimeError('capacity metrics were not started')
        if asyncio.get_running_loop() is not self._loop:
            raise RuntimeError('capacity metrics stopped outside gateway loop')
        if self._stopped_at is None:
            with self._reply_lock:
                self._stopped_at = time.monotonic_ns()
            assert self._task is not None
            self._task.cancel()
        assert self._task is not None
        try:
            await self._task
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
        return self.snapshot()

    def snapshot(self) -> CapacitySnapshot | None:
        """Return current in-memory evidence; no serialization or I/O."""
        if not self.enabled:
            return None
        if self._loop is None:
            raise RuntimeError('capacity metrics were not started')
        with self._reply_lock:
            reply_jobs = self._reply_jobs
            reply_d_max = self._reply_d_max
            reply_samples = tuple(self._reply_samples)
            dropped_reply = self._dropped_reply_samples
        return CapacitySnapshot(
            self._started_at, self._stopped_at, self._interval_ns,
            self._charged_now, self._charged_peak, self._charged_peak_at, self._charge_hook_calls,
            tuple(self._charge_samples), self._dropped_charge_samples,
            self._lag_max, self._lag_max_at, tuple(self._lag_samples),
            self._dropped_lag_samples,
            len(self._health_counts), self._health_untracked,
            tuple(self._health_ports), self._health_checks,
            tuple(self._health_counts), tuple(self._health_inflight), tuple(self._health_samples),
            self._dropped_health_samples, reply_jobs, reply_d_max,
            reply_samples, dropped_reply,
        )


def write_evidence(snapshot: CapacitySnapshot, path: Path = EVIDENCE_PATH) -> None:
    """Atomically write numeric-only JSON directly in /tmp, mode 0600.

    Only the fixed /tmp filename or a same-prefix test filename is accepted.
    No endpoint, /data write, or arbitrary environment-selected path exists.
    """
    path = Path(path)
    if path.parent != Path('/tmp') or not path.name.startswith('hm19c-capacity-metrics') or path.suffix != '.json':
        raise ValueError('capacity evidence path must be directly in /tmp')
    if type(snapshot) is not CapacitySnapshot:
        raise TypeError('capacity evidence must be a CapacitySnapshot')
    data = asdict(snapshot)

    def numeric_only(value):
        if isinstance(value, dict):
            return all(type(key) is str and numeric_only(item) for key, item in value.items())
        if isinstance(value, (list, tuple)):
            return all(numeric_only(item) for item in value)
        return value is None or type(value) is int

    if not numeric_only(data):
        raise ValueError('capacity evidence contains a nonnumeric value')
    payload = json.dumps(data, separators=(',', ':'), allow_nan=False).encode('ascii')
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', prefix='.hm19c-capacity-', dir='/tmp',
                                         delete=False) as handle:
            name = handle.name
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
        os.replace(name, path)  # Replaces a symlink itself; never follows it.
    finally:
        if name is not None and os.path.exists(name):
            os.unlink(name)
