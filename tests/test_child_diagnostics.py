"""Owned child output, bounds, redaction and cleanup; no live log collection."""
import asyncio
import base64
from pathlib import Path
import sys
from urllib.parse import quote

import pytest

from mcp_admin_core.diagnostics import ChildLogs, MAX_BYTES, MAX_ENTRIES, MAX_LINE, scrub_line
from mcp_admin_core.lifecycle import ChildSpec, Supervisor
from test_lifecycle import until


def test_short_credentials_do_not_expand_masks_or_leak():
    assert scrub_line('A D E', ('A', 'D', 'E')) == '[REDACTED] [REDACTED] [REDACTED]'


async def test_buffer_redacts_split_secrets_before_retention_and_drops_oversize_lines():
    secret = 'DUMMY-secret/+123'
    logs = ChildLogs()
    reader = asyncio.StreamReader()
    task = asyncio.create_task(logs.collect(reader, 'stderr', 1, (secret,)))
    raw = f'raw {secret} encoded {quote(secret, safe="")} base64 {base64.b64encode(secret.encode()).decode()}\n'
    for part in [raw[:11], raw[11:]]:
        reader.feed_data(part.encode())
        await asyncio.sleep(0)
    reader.feed_data(b'x' * (MAX_LINE + 1) + b'Bearer UNLISTED-CANARY\n')
    reader.feed_data(b'Authorization: Bearer OTHER-CANARY\nurl http://user:PASS-CANARY@host/path?token=QUERY-CANARY\n/private_PATH-CANARY/mcp\npassword="SPACED CANARY"\n')
    reader.feed_eof()
    await task
    snapshot = logs.snapshot()
    rendered = str(snapshot)
    assert secret not in rendered and quote(secret, safe='') not in rendered
    assert 'CANARY' not in rendered and '[REDACTED]' in rendered
    assert logs.dropped == 1 and snapshot['redacted'] and snapshot['retention'] == 'memory'
    for index in range(1000): logs.append('stdout', 'safe' * 1000, index)
    assert logs.bytes <= MAX_BYTES and len(logs.entries) <= MAX_ENTRIES and logs.dropped > 1


async def test_output_flood_does_not_block_exit_or_leave_readers(tmp_path):
    before = set(asyncio.all_tasks())
    code = "import os; os.write(1,b'x'*1000000+b'\\n'); os.write(2,b'api_key=CANARY\\nsafe end\\n')"
    manager = Supervisor(ChildSpec((sys.executable, '-c', code), {'PATH':'/usr/bin:/bin'}, tmp_path), retries=0, grace=.1)
    try:
        await manager.start()
        await until(lambda: manager.status == 'failed')
        assert manager.last_exit == 0
        logs = manager.diagnostics()['logs']
        assert logs['dropped'] >= 1 and 'CANARY' not in str(logs)
        assert any(entry['text'] == 'safe end' for entry in logs['entries'])
    finally: await manager.stop()
    assert not (set(asyncio.all_tasks()) - before)


async def test_descendant_holding_pipes_reaped_on_cancelled_restart(tmp_path):
    marker = tmp_path / 'descendant'
    code = f'''import os,signal,time
signal.signal(signal.SIGTERM,signal.SIG_IGN)
pid=os.fork()
if pid:
 open({str(marker)!r},'w').write(str(pid))
 print('backend_key='+os.environ['API_KEY'],flush=True)
while True: time.sleep(.01)
'''
    manager = Supervisor(ChildSpec((sys.executable, '-c', code), {'PATH':'/usr/bin:/bin','API_KEY':'DUMMY-OLD-SECRET'}, tmp_path), grace=.1)
    try:
        await manager.start()
        await until(marker.exists)
        await until(lambda: bool(manager.logs.entries))
        old_pid, descendant = manager.process.pid, int(marker.read_text())
        restart = asyncio.create_task(manager.restart(None))
        await asyncio.sleep(.01)
        restart.cancel()
        with pytest.raises(asyncio.CancelledError): await restart
        assert manager.process is None and manager.status == 'unconfigured'
        assert not Path(f'/proc/{old_pid}').exists() and not Path(f'/proc/{descendant}').exists()
        assert 'DUMMY-OLD-SECRET' not in str(manager.logs.entries)
    finally: await manager.stop()
