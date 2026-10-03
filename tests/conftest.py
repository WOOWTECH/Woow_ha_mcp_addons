"""LOCAL TEST coordination only; never terminate another listener or test run."""
import fcntl
import os
from pathlib import Path
import time

import pytest


@pytest.fixture(scope="session", autouse=True)
def local_test_lock():
    # Stable across worktrees/processes for this Unix user. Never unlink a flock
    # file: waiters must keep referring to the same inode. Children do not inherit.
    path = Path(f"/tmp/woow-ha-mcp-local-tests-{os.getuid()}.lock")
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    pytest.fail(f"LOCAL TEST lock busy after 120s: {path}; no tests skipped or processes stopped")
                time.sleep(.1)
        yield path
    finally:
        os.close(fd)
