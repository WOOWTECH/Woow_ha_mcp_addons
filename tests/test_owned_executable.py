"""Fresh-challenge proof failures and guarded UID visibility on OWN processes."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace

import httpx
import pytest

from batch2_owned_port import OwnershipError, reserve_port
from owned_executable import Executable

ROOT = Path(__file__).resolve().parents[1]


async def test_uid10001_nondumpable_self_and_own_child_proof(monkeypatch):
    assert os.getuid() == 0, 'owned UID10001 visibility requires local root'
    with tempfile.TemporaryDirectory(prefix='bt1-uid-') as directory:
        temp = Path(directory)
        temp.chmod(0o755)
        # Independent readable copy, never chmod an existing private interpreter.
        interpreter = Path(sys.executable).resolve().parents[1]
        shutil.copytree(interpreter, temp/'python', symlinks=True)
        shutil.copytree(ROOT/'.venv', temp/'.venv', symlinks=True)
        for path in (temp/'.venv/bin').glob('python*'):
            path.unlink()
        (temp/'.venv/bin/python').symlink_to(temp/'python/bin/python3.13')
        (temp/'.venv/pyvenv.cfg').write_text(f'home = {temp}/python/bin\ninclude-system-site-packages = false\nversion = 3.13.2\n')
        data = temp/'data'
        data.mkdir(mode=0o700)
        os.chown(data, 10001, 10001)
        with reserve_port() as reservation:
            port = reservation.getsockname()[1]
        runner = Executable(data, 'n8n', [port])
        runner.release()
        process = await asyncio.create_subprocess_exec(str(temp/'.venv/bin/python'), str(ROOT/'tests/owned_uid_probe.py'),
            json.dumps(runner.config), env={'PATH':'/usr/bin:/bin', 'PYTHONPATH':str(ROOT/'packages/mcp-admin-core')},
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            ready = await asyncio.wait_for(process.stdout.readline(), 15)
            assert ready == b'OWNED_UID_PROOF_READY\n', ready
            await runner.ready(process, timeout=5)
            public = await runner.guard_url(f'http://127.0.0.1:{port}/admin')
            child = await runner.guard_url(runner.child_url)
            assert public['proof'][0] == process.pid
            assert child['proof'][0] != process.pid and child['generation'] == 1
            assert public['nonce'] != child['nonce']
            again = await runner.guard_url(runner.child_url)
            assert again['nonce'] != child['nonce'] and again['proof'] == child['proof']
            import owned_executable
            with monkeypatch.context() as patch:
                patch.setattr(owned_executable, '_read_line', lambda socket: child)
                with pytest.raises(OwnershipError, match='challenge mismatch'):
                    await runner.guard_url(runner.child_url)
            read_line = owned_executable._read_line
            for field, value in [('generation', True), ('generation', 0),
                                 ('proof', [True, '12345']), ('proof', [-1, '12345']),
                                 ('proof', [process.pid, ''])]:
                def malformed(sock):
                    response = read_line(sock)
                    response[field] = value
                    return response
                with monkeypatch.context() as patch:
                    patch.setattr(owned_executable, '_read_line', malformed)
                    with pytest.raises(OwnershipError, match='invalid listener proof'):
                        await runner.guard_url(runner.child_url)
            with pytest.raises(OwnershipError, match='port/path'):
                await runner.guard(httpx.Request('GET', 'http://127.0.0.1:3000/mcp'))
            # Known OWN child's PID is metadata only; parent never reads its fds.
            own_child = child['proof'][0]
            process.stdin.write(b'quit\n')
            await process.stdin.drain()
            out, err = await asyncio.wait_for(process.communicate(), 10)
            assert process.returncode == 0, err.decode()
            assert not Path(f'/proc/{own_child}').exists()
            with pytest.raises(OwnershipError, match='not live'):
                await runner.guard_url(f'http://127.0.0.1:{port}/admin')
        finally:
            if process.returncode is None:
                # Negative assertions must still let the manager reap its group.
                process.stdin.write(b'quit\n')
                await asyncio.wait_for(process.stdin.drain(), 3)
                try:
                    await asyncio.wait_for(process.communicate(), 10)
                except TimeoutError:
                    process.kill()
                    await asyncio.wait_for(process.wait(), 3)
                    pytest.fail('owned UID probe did not join child cleanup')


async def test_callback_is_not_serialized_behind_health(tmp_path, monkeypatch):
    """Actual Core callback runs during health I/O, without a harness-only lock."""
    import owned_executable
    from mcp_admin_core.config import Store
    from mcp_admin_core.gateway import make_apps
    from mcp_admin_core.health import HealthMonitor
    from n8n_adapter import TOOLS, child_spec
    from test_owned_runtime import dummy
    # This in-process alias test has no public listener/IPC; the joined test
    # separately exercises the actual executable proof server and OS guard.
    monkeypatch.setattr(owned_executable, 'serve_proofs', lambda *_: None)
    module = SimpleNamespace(child_spec=child_spec, HealthMonitor=HealthMonitor, make_apps=make_apps)
    with reserve_port() as reservation:
        port = reservation.getsockname()[1]
    endpoint = owned_executable.install_runner(module, {'product':'n8n', 'child_port':port})
    manager = endpoint.supervisor(dummy(port), prepared=True)
    store = Store(tmp_path)
    health_entered, callback_entered = asyncio.Event(), asyncio.Event()
    release_health, release_callback = asyncio.Event(), asyncio.Event()
    async def transport(request):
        health_entered.set()
        await asyncio.wait_for(release_health.wait(), 5)
        return httpx.Response(200, headers={'mcp-session-id':'owned-session'}, json={
            'jsonrpc':'2.0', 'id':1, 'result':{'serverInfo':{}, 'protocolVersion':'2025-03-26'}})
    async def changed(state):
        endpoint.invalidate()
        callback_entered.set()
        await asyncio.wait_for(release_callback.wait(), 5)
        await manager.restart(dummy(port))
    async def role(_): return True
    tasks = []
    try:
        await manager.start()
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as child:
            monitor = module.HealthMonitor(store, manager, child)
            app, _ = module.make_apps(store, TOOLS, child, verify_admin=role, backend_changed=changed)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app, client=('172.30.32.2', 1)),
                base_url='http://owned', headers={'x-remote-user-id':'owner'}) as admin:
                csrf = (await admin.get('/api/bootstrap')).json()['csrf']
                health_task = asyncio.create_task(monitor.check())
                tasks.append(health_task)
                await asyncio.wait_for(health_entered.wait(), 2)
                save = asyncio.create_task(admin.put('/api/backend', headers={'x-csrf-token':csrf},
                    json={'url':None, 'key':None}))
                tasks.append(save)
                await asyncio.wait_for(callback_entered.wait(), 2)
                assert not health_task.done(), 'callback must overlap the real health check'
                release_health.set()
                await asyncio.wait_for(health_task, 2)
                release_callback.set()
                assert (await asyncio.wait_for(save, 5)).status_code == 200
                assert endpoint.generation == 2 and endpoint.proof is not None
    finally:
        release_health.set()
        release_callback.set()
        async with asyncio.timeout(10):
            await asyncio.gather(*tasks, return_exceptions=True)
            await manager.stop()
        endpoint.close()
        store.close()


async def test_ipc_rejects_other_own_process_before_tcp(tmp_path):
    with reserve_port() as port:
        runner = Executable(tmp_path, 'n8n', [port.getsockname()[1]])
    runner.release()
    code = ('import socket,sys,time; s=socket.socket(socket.AF_UNIX); '
            's.bind(sys.argv[1]); s.listen(); print("ready",flush=True); '
            'c,_=s.accept(); time.sleep(10)')
    decoy = await asyncio.create_subprocess_exec(sys.executable, '-c', code, runner.config['ipc'],
        stdout=asyncio.subprocess.PIPE, env={'PATH':'/usr/bin:/bin'})
    owner = await asyncio.create_subprocess_exec(sys.executable, '-c', 'import time; time.sleep(10)',
        env={'PATH':'/usr/bin:/bin'})
    try:
        assert await asyncio.wait_for(decoy.stdout.readline(), 5) == b'ready\n'
        runner.process = owner
        with pytest.raises(OwnershipError, match='peer is not launched'):
            await asyncio.to_thread(runner._proof, runner.config['public_ports'][0])
    finally:
        for process in (owner, decoy):
            if process.returncode is None:
                process.terminate()
            await asyncio.wait_for(process.wait(), 3)
