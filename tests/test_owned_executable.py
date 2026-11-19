"""Fresh-challenge proof failures and guarded UID visibility on OWN processes."""
from admin_write_headers import reviewed_headers
import asyncio
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import httpx
import pytest

from batch2_owned_port import OwnershipError, reserve_port
from log_scan import log_scan  # noqa: F401  (fixture; HM-16's test)
from owned_executable import Executable, draw_public_ports

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
                boot = (await admin.get('/api/bootstrap')).json()
                health_task = asyncio.create_task(monitor.check())
                tasks.append(health_task)
                await asyncio.wait_for(health_entered.wait(), 2)
                save = asyncio.create_task(admin.put('/api/backend', headers=reviewed_headers(boot),
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


def test_the_child_port_is_never_a_public_port(tmp_path, monkeypatch):
    """PR #109's first CI run (test_unconfigured_connect_runtime[hermes]): launch() drew its two public ports by binding
    port 0 and closing the socket again (free_port), and the kernel gave one of them to the child port's reservation.
    Here the first two reservations land on the public ports, as the kernel may hand them out: Executable reserves again
    and keeps each colliding reservation bound until it holds one outside the public ports, then closes them."""
    import owned_executable
    held = [reserve_port(), reserve_port()]  # what the kernel hands back first: the public ports
    public = [sock.getsockname()[1] for sock in held]
    real, returned = owned_executable.reserve_port, []

    def kernel_hands_back_the_public_ports():
        assert all(sock.fileno() != -1 for sock in returned), 'a colliding reservation stays bound while reserving again'
        returned.append(held[len(returned)] if len(returned) < len(held) else real())
        return returned[-1]
    monkeypatch.setattr(owned_executable, 'reserve_port', kernel_hands_back_the_public_ports)
    try:
        runner = Executable(tmp_path, 'n8n', public)
        assert len(returned) == 3 and runner.reservation is returned[-1]
        assert runner.config['child_port'] == runner.reservation.getsockname()[1] not in public
        assert all(sock.fileno() == -1 for sock in held), 'the colliding reservations are closed'
    finally:
        for sock in returned + held:
            sock.close()


def test_a_reservation_that_keeps_colliding_is_refused(tmp_path, monkeypatch):
    """A kernel cannot hand back a port that is still bound, so at most one collision per public port can happen; a
    reserve_port that keeps colliding anyway is refused, not retried forever, and nothing it handed out stays open."""
    import owned_executable

    class Collision:
        def __init__(self):
            self.closed = False

        def getsockname(self):
            return ('127.0.0.1', 43210)

        def close(self):
            self.closed = True
    made = []
    monkeypatch.setattr(owned_executable, 'reserve_port', lambda: made.append(Collision()) or made[-1])
    with pytest.raises(OwnershipError, match='outside the public ports'):
        Executable(tmp_path, 'n8n', [43210])
    assert len(made) == 2 and all(collision.closed for collision in made)


def test_the_guard_still_refuses_a_public_child_port(tmp_path, monkeypatch):
    """The assertion stays as a guard behind the reservation: a child port among the public ones never gets a config."""
    import owned_executable
    with reserve_port() as public:
        monkeypatch.setattr(owned_executable, 'reserve_child_port', lambda ports: public)
        with pytest.raises(AssertionError):
            Executable(tmp_path, 'n8n', [public.getsockname()[1]])


def test_the_public_ports_are_distinct_and_never_the_childs(tmp_path, monkeypatch):
    """This follow-up's review: two free_port() calls in a row (each binds port 0 and closes the socket again) could
    draw the same port, 8 in 100,000 launches on one machine, and Executable refuses a repeated public port. Here the
    kernel always hands a bind of port 0 the lowest port nothing holds, so a port closed a moment ago goes to the very
    next bind: draw_public_ports holds every reservation until all are drawn, then releases them together, and the
    child port's reservation still lands outside them."""
    import owned_executable
    held = set()

    class Reservation:
        def __init__(self):
            self.port = 40000
            while self.port in held:
                self.port += 1
            held.add(self.port)
            self.bound = True

        def getsockname(self):
            return ('127.0.0.1', self.port)

        def close(self):
            if self.bound:
                self.bound = False
                held.discard(self.port)
    monkeypatch.setattr(owned_executable, 'reserve_port', Reservation)

    def one_at_a_time():  # what the free_port helpers did
        reservation = owned_executable.reserve_port()
        reservation.close()
        return reservation.getsockname()[1]
    assert one_at_a_time() == one_at_a_time()  # the repeated public port Executable refused
    public = owned_executable.draw_public_ports(2)
    assert public == [40000, 40001] and not held  # distinct, and released together
    runner = Executable(tmp_path, 'n8n', public)
    assert runner.config['child_port'] == 40002 and held == {40002}
    runner.release()
    assert not held


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


async def test_a_switched_on_product_s_default_profile_runs_through_the_owned_executable(tmp_path, log_scan):
    """Multi-profile HM-16 (HM-20's handoff; HM-01's installer): from HM-08 on, a switched-on product's run_product
    builds a ProfileManager whose Supervisor and health monitor take options (the watchdog, the spawn check, the lifecycle
    log, the monitor's pacing) the installer refused, so no switched-on product started through it. Now the default
    profile does: its real child behind the private port (the spawn check binds that port, never 3000), the gateway
    forwards initialize to it (a child's session, not the gateway's own), and 8081 is the switched-on dispatcher (an
    index that appears behind the add-on's back stops every token: DQ-12)."""
    from mcp_admin_core.products import ProductStore
    from test_real_products import connection
    product = 'emqx'
    store = ProductStore(tmp_path / 'state', product)
    # A loopback backend nobody serves: switched on, the child refuses loopback (HM-20) and still answers initialize.
    state = store.update(connection=connection(product, 'http://127.0.0.1:9'))
    store.close()
    log_scan.watch(state.token, state.child_token)
    port, admin_port = draw_public_ports(2)
    endpoint = f'http://127.0.0.1:{port}/mcp'
    runner = Executable(tmp_path, product, [port, admin_port])
    code = (f'from mcp_admin_core import features, run_product; features.MULTI_PROFILE_PRODUCTS = frozenset({{{product!r}}}); '
            + runner.code('run_product') + 'run_product.main()')
    runner.release()
    log_path = tmp_path / 'owned-runtime.log'
    with log_path.open('wb') as log:
        process = subprocess.Popen([str(ROOT / '.venv/bin/python'), '-c', code, product, '--data', str(tmp_path / 'state'),
                                    '--host', '127.0.0.1', '--mcp-port', str(port), '--admin-port', str(admin_port)],
                                   cwd=ROOT, env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1',
                                                  'PYTHONPATH': str(ROOT / 'packages/mcp-admin-core')},
                                   stdout=log, stderr=log)
        try:
            await runner.ready(process)
            headers = {'Authorization': 'Bearer ' + state.token, 'Accept': 'application/json, text/event-stream'}
            message = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'local-test', 'version': '0'}}}
            async with httpx.AsyncClient(trust_env=False, timeout=10, event_hooks={'request': [runner.guard]}) as client:
                session = None
                async with asyncio.timeout(30):
                    while session is None or session.startswith('woow-local-'):
                        assert process.poll() is None, log_path.read_text()
                        response = await client.post(endpoint, headers=headers, json=message)
                        assert response.status_code == 200
                        session = response.headers['mcp-session-id']
                        if session.startswith('woow-local-'):
                            await asyncio.sleep(.25)  # the child is not up yet: the gateway answered itself
                (tmp_path / 'state' / 'profiles.json').write_text('{}')
                response = await client.post(endpoint, headers=headers, json=message)
                assert (response.status_code, response.content) == (503, b'{"error":"state unavailable"}')
        finally:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                pytest.fail('switched-on owned runtime did not stop')
    assert process.returncode == 0, log_path.read_text()
    output = log_path.read_text()
    assert state.token not in output and state.child_token not in output
