"""Actual executable failure paths; generated dummy state, no external requests."""
import asyncio
import json
import os
from pathlib import Path
import socket
import sys

import pytest

from mcp_admin_core.config import Store

from owned_executable import Executable
from batch2_owned_port import reserve_port

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with reserve_port() as sock:
        return sock.getsockname()[1]


@pytest.mark.parametrize("fault", ["monitor", "monitor_return", "persisted_key"])
async def test_runtime_failure_is_sanitized_and_nonzero(tmp_path, fault):
    store = Store(tmp_path / "data")
    if fault == "persisted_key":
        value = store.load().model_dump()
        value.update(backend_url="http://127.0.0.1:1", backend_key="DUMMY\u00a0")
        store.path.write_text(json.dumps(value))
    store.close()
    code = "import run; run.main()"
    if fault == "monitor":
        code = '''
import run
async def fail(self):
    raise RuntimeError('DUMMY-private-exception')
run.HealthMonitor.run = fail
run.main()
'''
    if fault == "monitor_return":
        code = '''
import run
async def finish(self):
    return
run.HealthMonitor.run = finish
run.main()
'''
    admin_port, mcp_port = free_port(), free_port()
    runner = Executable(tmp_path, 'n8n', [admin_port, mcp_port])
    code = 'import run; ' + runner.code('run') + '\n' + code
    runner.release()
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", code,
        "--data", str(store.directory), "--host", "127.0.0.1", "--admin-port", str(admin_port), "--mcp-port", str(mcp_port),
        cwd=tmp_path, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "packages/mcp-admin-core") + os.pathsep + str(ROOT / "apps/n8n")},
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(process.communicate(), 12)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    assert process.returncode != 0
    assert b"runtime unavailable; local recovery required" in err
    assert b"DUMMY" not in out + err
    assert b"Traceback" not in err
