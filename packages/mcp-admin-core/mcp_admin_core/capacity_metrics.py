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
from dataclasses import dataclass
import math
import time


@dataclass(frozen=True, slots=True)
class ChargeSample:
    at_monotonic_ns: int
    charged_bytes: int


@dataclass(frozen=True, slots=True)
class LagSample:
    at_monotonic_ns: int
    lag_ns: int


@dataclass(frozen=True, slots=True)
class CapacitySnapshot:
    started_at_monotonic_ns: int
    stopped_at_monotonic_ns: int | None
    interval_ns: int
    charged_bytes_now: int
    charged_bytes_peak: int
    charged_peak_at_monotonic_ns: int
    charge_samples: tuple[ChargeSample, ...]
    dropped_charge_samples: int
    lag_max_ns: int
    lag_max_at_monotonic_ns: int | None
    lag_samples: tuple[LagSample, ...]
    dropped_lag_samples: int


class CapacityMetrics:
    """Single-loop bounded probe; constructed and started explicitly.

    The charge hook receives the exact current add-on budget total after a
    successful transition. Offered and client-uploaded bytes are invalid.
    History overflow is counted so truncated evidence is visible.
    """

    def __init__(self, *, enabled: bool = False, interval_seconds: float = 0.01,
                 max_charge_samples: int = 32768, max_lag_samples: int = 4096) -> None:
        if not isinstance(enabled, bool):
            raise ValueError('enabled must be bool')
        if (isinstance(interval_seconds, bool) or
                not isinstance(interval_seconds, (float, int)) or
                not math.isfinite(interval_seconds) or
                not 0.001 <= interval_seconds <= 1.0):
            raise ValueError('interval_seconds must be finite and within [0.001, 1]')
        for name, count, limit in (('max_charge_samples', max_charge_samples, 65536),
                                   ('max_lag_samples', max_lag_samples, 8192)):
            if type(count) is not int or not 1 <= count <= limit:
                raise ValueError(f'{name} must be in [1, {limit}]')
        self.enabled = enabled
        self._interval_ns = round(interval_seconds * 1_000_000_000)
        self._charge_samples: deque[ChargeSample] = deque(maxlen=max_charge_samples)
        self._lag_samples: deque[LagSample] = deque(maxlen=max_lag_samples)
        self._dropped_charge_samples = 0
        self._dropped_lag_samples = 0
        self._charged_now = 0
        self._charged_peak = 0
        self._charged_peak_at = 0
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
        if self._loop is None or self._stopped_at is not None:
            raise RuntimeError('capacity metrics must be running')
        if asyncio.get_running_loop() is not self._loop:
            raise RuntimeError('capacity metrics hook called outside gateway loop')
        if type(total_charged_bytes) is not int or not 0 <= total_charged_bytes <= 2**63 - 1:
            raise ValueError('total_charged_bytes must be a nonnegative integer')
        at = time.monotonic_ns()
        self._charged_now = total_charged_bytes
        if total_charged_bytes > self._charged_peak:
            self._charged_peak = total_charged_bytes
            self._charged_peak_at = at
        if len(self._charge_samples) == self._charge_samples.maxlen:
            self._dropped_charge_samples += 1
        self._charge_samples.append(ChargeSample(at, total_charged_bytes))

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
        return CapacitySnapshot(
            self._started_at, self._stopped_at, self._interval_ns,
            self._charged_now, self._charged_peak, self._charged_peak_at,
            tuple(self._charge_samples), self._dropped_charge_samples,
            self._lag_max, self._lag_max_at, tuple(self._lag_samples),
            self._dropped_lag_samples,
        )
