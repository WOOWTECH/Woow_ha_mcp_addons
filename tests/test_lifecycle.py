"""LOCAL process fault injection; only subprocesses created by these tests."""
import asyncio
import os
from pathlib import Path
import signal
import sys
import time

import pytest

from mcp_admin_core.lifecycle import ChildSpec, Supervisor


async def until(predicate, timeout=4):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


def spec(code, tmp_path):
    return ChildSpec((sys.executable, "-c", code), {"PATH": "/usr/bin:/bin"}, tmp_path)


async def test_crash_budget_backoff_and_liveness(tmp_path):
    manager = Supervisor(spec("raise SystemExit(7)", tmp_path), retries=2, backoff=0.04, grace=0.05)
    start = time.monotonic()
    await manager.start()
    await until(lambda: manager.status == "failed")
    assert manager.starts == 3 and manager.last_exit == 7
    assert time.monotonic() - start >= 0.12
    assert not manager.ready
    await manager.stop()


async def test_spawn_failure_bounded(tmp_path):
    manager = Supervisor(ChildSpec(("/nonexistent-executable",), {}, tmp_path), retries=1, backoff=0.01)
    await manager.start()
    await until(lambda: manager.status == "failed")
    assert manager.starts == 2
    await manager.stop()


async def test_sigterm_and_forced_kill_entire_process_group(tmp_path):
    # Parent handles SIGTERM and reaps child; child ignores TERM so KILL is required.
    pidfile = tmp_path / "descendant.pid"
    code = f'''
import os, signal, time
pid = os.fork()
if pid == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True: time.sleep(.01)
def term(*args):
    os.waitpid(pid, 0)
    raise SystemExit(0)
signal.signal(signal.SIGTERM, term)
open({str(pidfile)!r}, 'w').write(str(pid))
while True: time.sleep(.01)
'''
    manager = Supervisor(spec(code, tmp_path), grace=0.1)
    await manager.start()
    await until(pidfile.exists)
    descendant = int(pidfile.read_text())
    leader = manager.process.pid
    await manager.stop()
    assert manager.process is None
    assert manager.status == "stopped"
    assert not Path(f"/proc/{leader}").exists()
    # No live descendants OR orphan zombies are accepted.
    assert not Path(f"/proc/{descendant}").exists()


async def test_crashed_leader_leaves_no_orphan_before_budget_exhaustion(tmp_path):
    pidfile = tmp_path / "orphan.pid"
    code = f'''
import os, signal, time
pid = os.fork()
if pid == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True: time.sleep(.01)
open({str(pidfile)!r}, 'w').write(str(pid))
time.sleep(.05)
os._exit(7)
'''
    manager = Supervisor(spec(code, tmp_path), retries=0, grace=0.05)
    await manager.start()
    await until(lambda: manager.status == "failed")
    descendant = int(pidfile.read_text())
    assert not Path(f"/proc/{descendant}").exists()
    await manager.stop()


async def test_graceful_term_is_observed(tmp_path):
    marker = tmp_path / "term"
    ready = tmp_path / "ready"
    code = f'''
import signal, time
from pathlib import Path
def term(*args):
    Path({str(marker)!r}).write_text('term')
    raise SystemExit(0)
signal.signal(signal.SIGTERM, term)
Path({str(ready)!r}).touch()
while True: time.sleep(.01)
'''
    manager = Supervisor(spec(code, tmp_path), grace=0.2)
    await manager.start()
    await until(ready.exists)
    await manager.stop()
    assert marker.read_text() == "term"
    assert manager.starts == 1
