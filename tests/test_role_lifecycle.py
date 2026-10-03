"""Post-commit cancellation: real runtimes/supervisors, owned dummy children only."""
import asyncio
import json
import os
from pathlib import Path
import signal
import sys
from types import SimpleNamespace

import anyio
import httpx
import pytest

import run as n8n_run
from mcp_admin_core import run_product
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.lifecycle import ChildSpec, Supervisor
from mcp_admin_core.products import PRODUCTS
from test_ha_role import gateway
from test_lifecycle import until
from test_real_products import connection


def owned_spec(tmp_path, name):
    # Both leader and descendant ignore TERM; the marker proves handlers exist.
    marker = tmp_path / name
    code = f'''
import os, signal, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
pid = os.fork()
if pid:
    with open({str(marker) + '.tmp'!r}, 'w') as output: output.write(str(pid))
    os.replace({str(marker) + '.tmp'!r}, {str(marker)!r})
while True: time.sleep(.01)
'''
    return ChildSpec((sys.executable, '-c', code), {'PATH': '/usr/bin:/bin'}, tmp_path)


def group_gone(pid):
    with pytest.raises(ProcessLookupError):
        os.killpg(pid, 0)


async def emergency_cleanup(manager, processes):
    # Also cleans the known-broken RED implementation, never unrelated children.
    for process in processes:
        Supervisor._signal(process.pid, signal.SIGKILL)
        await process.wait()
        async with asyncio.timeout(2):
            while True:
                try:
                    pid, _ = os.waitpid(-process.pid, os.WNOHANG)
                except ChildProcessError:
                    break
                if pid == 0:
                    await asyncio.sleep(.01)
    if manager.task is not None and manager.task.cancelled():
        manager.task = None
        manager.process = None
    await manager.stop()


@pytest.mark.parametrize('product', ('n8n', *PRODUCTS))
@pytest.mark.parametrize('cancel', ('disconnect', 'direct', 'scope'))
async def test_committed_runtime_backend_transition_is_joined(tmp_path, monkeypatch, product, cancel):
    module = n8n_run if product == 'n8n' else run_product
    captured, servers, processes = {}, [], []
    terminating = asyncio.Event()
    roles = {'allow': True, 'calls': 0}
    before = set(asyncio.all_tasks())

    def child_spec(state, directory):
        return owned_spec(tmp_path, 'replacement' if state.configured else 'original')

    class Manager(Supervisor):
        def __init__(self, spec):
            super().__init__(spec, grace=.25)
            captured['manager'] = self

        async def _terminate(self, process):
            processes.append(process)
            terminating.set()
            await super()._terminate(process)

    async def verify(_):
        roles['calls'] += 1
        return roles['allow']

    def apps(store, tools, child, **kwargs):
        captured['store'] = store
        # Deliberately isolate lifecycle from HA; no capability change to six apps.
        kwargs['verify_admin'] = verify
        admin, mcp = make_apps(store, tools, child, **kwargs)
        captured['admin'] = admin

        async def ingress(scope, receive, send):
            await admin({**scope, 'client': ('172.30.32.2', 1)}, receive, send)
        return ingress, mcp

    class Listener(module.Listener):
        def __init__(self, config):
            super().__init__(config)
            servers.append(self)

    class Monitor:
        def __init__(self, *args): pass
        def snapshot(self): return {}
        async def run(self): await asyncio.Event().wait()

    monkeypatch.setattr(module, 'Supervisor', Manager)
    monkeypatch.setattr(module, 'child_spec', child_spec)
    monkeypatch.setattr(module, 'make_apps', apps)
    monkeypatch.setattr(module, 'Listener', Listener)
    monkeypatch.setattr(module, 'HealthMonitor', Monitor)
    args = SimpleNamespace(data=tmp_path / 'state', product=product,
                           host='127.0.0.1', admin_port=0, mcp_port=0)
    runtime = asyncio.create_task(module.run(args))
    request = queued = None
    try:
        await until(lambda: len(servers) == 2 and all(s.started for s in servers))
        await until((tmp_path / 'original').exists)
        manager, store = captured['manager'], captured['store']
        old = manager.process
        processes.append(old)
        descendant = int((tmp_path / 'original').read_text())
        port = servers[0].servers[0].sockets[0].getsockname()[1]
        async with httpx.AsyncClient(trust_env=False, base_url=f'http://127.0.0.1:{port}') as client:
            headers = {'x-remote-user-id': 'human'}
            response = await client.get('/api/bootstrap', headers=headers)
            assert response.status_code == 200
            headers['x-csrf-token'] = response.json()['csrf']
            payload = ({'url': 'http://127.0.0.1:1', 'key': 'DUMMY-backend'} if product == 'n8n'
                       else {'connection': connection(product, 'http://127.0.0.1:1')})
            events, output = asyncio.Queue(), []
            events.put_nowait({'type': 'http.request', 'body': json.dumps(payload).encode(), 'more_body': False})
            async def send(message): output.append(message)
            scope = {'type': 'http', 'method': 'PUT', 'path': '/api/backend', 'query_string': b'',
                     'headers': [(k.encode(), v.encode()) for k, v in headers.items()] + [(b'content-type', b'application/json')],
                     'client': ('172.30.32.2', 1), 'server': ('admin', 80), 'scheme': 'http', 'http_version': '1.1'}
            async def invoke():
                with anyio.CancelScope() as cancel_scope:
                    captured['cancel_scope'] = cancel_scope
                    await captured['admin'](scope, events.get, send)
            request = asyncio.create_task(invoke())
            await asyncio.wait_for(terminating.wait(), 2)
            assert store.load().configured  # exact reviewer cut: committed, graceful stop pending
            committed = store.path.read_bytes()
            assert old.returncode is None
            if cancel == 'disconnect':
                events.put_nowait({'type': 'http.disconnect'})
            elif cancel == 'scope':
                captured['cancel_scope'].cancel()
            else:
                request.cancel()
            await asyncio.sleep(.02)
            if cancel == 'direct':
                request.cancel()  # repeated cancellation must not detach cleanup
            assert not request.done(), {
                'released_lifecycle_ownership': True,
                'backend_state_committed': store.load().configured,
                'old_child_still_running': old.returncode is None,
                'old_spec_retained': manager.spec == owned_spec(tmp_path, 'original'),
                'supervisor_task_cancelled': manager.task.cancelled(),
            }
            roles['allow'] = False
            calls = roles['calls']
            queued = asyncio.create_task(client.post('/api/token/rotate', headers=headers))
            await asyncio.sleep(.02)
            assert not queued.done() and roles['calls'] == calls, 'mutation lock released early'
            if cancel == 'direct':
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(request, 2)
            else:
                await asyncio.wait_for(request, 2)
                if cancel == 'disconnect':
                    assert output[0]['status'] == 403
            assert (await queued).status_code == 403  # fresh role, never a queued grant
            assert store.path.read_bytes() == committed
            group_gone(old.pid)
            assert not Path(f'/proc/{descendant}').exists()
            assert manager.spec == child_spec(store.load(), store.directory)
            await until((tmp_path / 'replacement').exists)
            assert manager.process is not old and manager.process.returncode is None
            assert not manager.task.done() and manager.status == 'running'
            replacement = manager.process
            processes.append(replacement)
            await manager.restart(manager.spec)
            group_gone(replacement.pid)
            await until(lambda: manager.process is not None and manager.status == 'running')
            processes.append(manager.process)
            await manager.stop()
            assert manager.task is None and manager.process is None and manager.status == 'stopped'
            for process in processes:
                group_gone(process.pid)
    finally:
        for pending in (request, queued):
            if pending is not None and not pending.done(): pending.cancel()
        await asyncio.gather(*(p for p in (request, queued) if p is not None), return_exceptions=True)
        if 'manager' in captured:
            manager = captured['manager']
            if manager.process is not None: processes.append(manager.process)
            await emergency_cleanup(manager, processes)
        runtime.cancel()
        await asyncio.gather(runtime, return_exceptions=True)
    await asyncio.sleep(0)
    assert not (set(asyncio.all_tasks()) - before), 'unjoined request/runtime cleanup task'


@pytest.mark.parametrize('phase', ('body', 'queue', 'verifier'))
@pytest.mark.parametrize('cancel', ('disconnect', 'direct'))
async def test_precommit_cancellation_has_no_effects(tmp_path, phase, cancel):
    entered, holding, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    checks, changes = [], []
    stall = False

    async def verify(user):
        checks.append(user)
        if stall:
            entered.set()
            await asyncio.Event().wait()
        return True

    async def changed(state):
        changes.append(state)
        holding.set()
        await release.wait()

    async with gateway(tmp_path, verify, changed=changed) as (store, client, admin, _):
        headers = {'x-remote-user-id': 'human'}
        headers['x-csrf-token'] = (await client.get('/api/bootstrap', headers=headers)).json()['csrf']
        holder = pending = None
        before = set(asyncio.all_tasks())
        try:
            if phase == 'queue':
                holder = asyncio.create_task(client.put('/api/backend', headers=headers, json={'url': None, 'key': None}))
                await holding.wait()
            stall = phase == 'verifier'
            baseline, check_count, change_count = store.path.read_bytes(), len(checks), len(changes)
            events, output = asyncio.Queue(), []
            payload = b'{"writes_enabled":true,"disabled":[]}'
            events.put_nowait({'type': 'http.request', 'body': payload, 'more_body': phase == 'body'})
            async def receive():
                if events.empty() and phase != 'verifier': entered.set()
                return await events.get()
            async def send(message): output.append(message)
            scope = {'type': 'http', 'method': 'PUT', 'path': '/api/policy', 'query_string': b'',
                     'headers': [(k.encode(), v.encode()) for k, v in headers.items()] + [(b'content-type', b'application/json')],
                     'client': ('172.30.32.2', 1), 'server': ('admin', 80), 'scheme': 'http', 'http_version': '1.1'}
            pending = asyncio.create_task(admin(scope, receive, send))
            await asyncio.wait_for(entered.wait(), 1)
            if cancel == 'disconnect':
                events.put_nowait({'type': 'http.disconnect'})
                await asyncio.wait_for(pending, 1)
                assert output[0]['status'] == 403
            else:
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(pending, 1)
            assert store.path.read_bytes() == baseline and len(changes) == change_count
            assert len(checks) == check_count + (phase == 'verifier')
            assert b'token' not in b''.join(m.get('body', b'') for m in output)
        finally:
            release.set()
            if pending is not None and not pending.done(): pending.cancel()
            await asyncio.gather(*(p for p in (holder, pending) if p is not None), return_exceptions=True)
        assert not (set(asyncio.all_tasks()) - before)


async def test_failed_cleanup_retains_process_for_explicit_retry(tmp_path):
    manager = Supervisor(owned_spec(tmp_path, 'original'), grace=.1)
    original_terminate = manager._terminate
    calls = 0

    async def fail_once(process):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError('owned cleanup fault')
        await original_terminate(process)

    manager._terminate = fail_once
    processes = []
    try:
        await manager.start()
        await until((tmp_path / 'original').exists)
        old = manager.process
        processes.append(old)
        with pytest.raises(TimeoutError):
            await manager.stop()
        assert manager.status == 'failed' and manager.task is None
        assert manager.process is old  # retained ownership, never silently orphaned
        with pytest.raises(RuntimeError):
            await manager.start()  # cannot launch over an unreaped group
        replacement = owned_spec(tmp_path, 'replacement')
        await manager.restart(replacement)
        group_gone(old.pid)
        await until((tmp_path / 'replacement').exists)
        processes.append(manager.process)
        assert manager.spec == replacement and not manager.task.done()
        await manager.stop()
    finally:
        if manager.process is not None: processes.append(manager.process)
        await emergency_cleanup(manager, processes)


@pytest.mark.parametrize('operation', ('stop', 'restart'))
async def test_direct_supervisor_cancellation_joins_transition(tmp_path, operation):
    manager = Supervisor(owned_spec(tmp_path, 'original'), grace=.2)
    processes = []
    terminating = asyncio.Event()
    original_terminate = manager._terminate
    async def terminate(process):
        terminating.set()
        await original_terminate(process)
    manager._terminate = terminate
    pending = None
    try:
        await manager.start()
        await until((tmp_path / 'original').exists)
        old = manager.process
        processes.append(old)
        replacement = owned_spec(tmp_path, 'replacement')
        pending = asyncio.create_task(manager.stop() if operation == 'stop' else manager.restart(replacement))
        await terminating.wait()
        pending.cancel()
        await asyncio.sleep(.02)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        group_gone(old.pid)
        if operation == 'restart':
            assert manager.spec == replacement
            await until((tmp_path / 'replacement').exists)
            assert not manager.task.done()
            processes.append(manager.process)
        else:
            assert manager.task is None and manager.process is None and manager.status == 'stopped'
        await manager.restart(replacement)
        await until(lambda: manager.process is not None and manager.status == 'running')
        processes.append(manager.process)
        await manager.stop()
        for process in processes: group_gone(process.pid)
    finally:
        if pending is not None:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        if manager.process is not None: processes.append(manager.process)
        await emergency_cleanup(manager, processes)
