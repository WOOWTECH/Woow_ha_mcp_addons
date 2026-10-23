"""Review findings 2 and 4: in-memory children/readers and ASGI transports only."""
import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from mcp_admin_core.config import State
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.lifecycle import ChildSpec, Supervisor
from n8n_adapter import TOOLS


@pytest.fixture
async def pipe_holder(tmp_path, monkeypatch):
    # Exercise normal initialization without changing the test process's subreaper.
    monkeypatch.setattr('mcp_admin_core.lifecycle.ctypes.CDLL',
                        lambda *args, **kwargs: SimpleNamespace(prctl=lambda *args: 0))
    manager = Supervisor(ChildSpec(('mock-child',), {}, tmp_path), retries=3, backoff=.001)
    readers, processes, terminated = [], [], asyncio.Event()
    collect = manager.logs.collect

    async def collecting(*args):
        readers.append(asyncio.current_task())
        await collect(*args)

    async def exited():
        return 0

    async def spawn(*args, **kwargs):
        # The leader exits but an escaped descendant still holds both pipe ends.
        process = SimpleNamespace(stdout=asyncio.StreamReader(), stderr=asyncio.StreamReader(), wait=exited)
        processes.append(process)
        return process

    async def terminate(process):
        assert process in processes
        terminated.set()

    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    monkeypatch.setattr(manager.logs, 'collect', collecting)
    monkeypatch.setattr(manager, '_terminate', terminate)
    before = set(asyncio.all_tasks())
    try:
        yield manager, readers, processes, terminated
    finally:
        if manager.task is not None:
            if not manager.task.done():
                manager.task.cancel()
            await asyncio.gather(manager.task, return_exceptions=True)
        assert all(reader.done() for reader in readers)
        assert not (set(asyncio.all_tasks()) - before - {asyncio.current_task()})


async def test_log_drain_timeout_exhausts_retries_and_allows_first_restart(pipe_holder):
    manager, readers, processes, _ = pipe_holder
    await manager.start()
    await asyncio.wait_for(asyncio.shield(manager.task), 6)
    assert manager.health() == {'state': 'failed', 'transport_ready': False, 'starts': 4, 'last_exit': 0}
    assert manager.process is None and len(processes) == 4
    assert len(readers) == 8 and all(reader.cancelled() for reader in readers)
    await manager.restart(None)
    assert manager.status == 'unconfigured' and manager.task is None


@pytest.mark.parametrize('operation', ['stop', 'restart'])
@pytest.mark.parametrize('cancel', [False, True])
async def test_log_drain_timeout_finishes_owned_transition(pipe_holder, operation, cancel):
    manager, readers, processes, terminated = pipe_holder
    await manager.start()
    await asyncio.wait_for(terminated.wait(), 1)
    pending = asyncio.create_task(manager.stop() if operation == 'stop' else manager.restart(None))
    try:
        # Let the transition acquire its lock before cancelling its caller.
        while not manager._lock.locked():
            await asyncio.sleep(0)
        if cancel:
            for _ in range(2):
                pending.cancel()
                await asyncio.sleep(0)
            assert not pending.done() and manager._lock.locked()
            with pytest.raises(asyncio.CancelledError):
                await pending
        else:
            await pending
        assert manager.status == ('stopped' if operation == 'stop' else 'unconfigured')
        assert manager.process is None and manager.task is None and len(processes) == 1
        assert not manager._lock.locked()
        assert len(readers) == 2 and all(reader.cancelled() for reader in readers)
    finally:
        await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.parametrize('failure_type', [TimeoutError, RuntimeError, asyncio.CancelledError])
async def test_log_drain_timeout_preserves_process_cleanup_failure(pipe_holder, monkeypatch, failure_type):
    manager, readers, processes, terminated = pipe_holder
    terminate = manager._terminate
    failure = failure_type('owned process cleanup fault')

    async def fail_cleanup(process):
        terminated.set()
        raise failure

    monkeypatch.setattr(manager, '_terminate', fail_cleanup)
    await manager.start()
    await asyncio.wait_for(terminated.wait(), 1)
    with pytest.raises(failure_type) as raised:
        await manager.stop()
    if failure_type is not asyncio.CancelledError:
        assert raised.value is failure
    assert manager.status == 'failed' and manager.task is None
    assert manager.process is processes[0] and manager.starts == 1
    assert len(readers) == 2 and all(reader.cancelled() for reader in readers)
    with pytest.raises(RuntimeError, match='cleanup required'):
        await manager.start()
    monkeypatch.setattr(manager, '_terminate', terminate)
    await manager.restart(None)
    assert manager.status == 'unconfigured' and manager.process is None


@pytest.mark.parametrize('phase', ['observation', 'final_role'])
@pytest.mark.parametrize('change', ['unchanged', 'exit', 'replacement', 'role_revoked'])
async def test_catalog_revalidates_child_after_final_role(phase, change):
    state = State.model_construct(child_token='mock-child-token', token='mock-public-token', disabled=[],
                                  enabled_write_tools=[], writes_enabled=False, backend_url=None,
                                  backend_key=None, endpoint=None)
    health = {'state': 'running', 'transport_ready': True, 'starts': 1, 'last_exit': None}
    checks, closed = 0, False

    async def change_child():
        await asyncio.sleep(0)
        if change == 'exit':
            health.update(state='failed', transport_ready=False, last_exit=1)
        elif change == 'replacement':
            health['starts'] += 1  # Same health state, different child generation.

    async def verify(user):
        nonlocal checks
        checks += 1
        if checks == 2:
            assert closed  # Discovery and its session cleanup finished first.
            if phase == 'final_role':
                await change_child()
            return change != 'role_revoked'
        return True

    async def reply(request):
        nonlocal closed
        if request.method == 'DELETE':
            closed = True
            return httpx.Response(204)
        message = json.loads(request.content)
        if 'id' not in message:
            return httpx.Response(202)
        if message['method'] == 'initialize':
            result = {'serverInfo': {}, 'protocolVersion': '2025-03-26'}
        else:
            assert message['method'] == 'tools/list'
            if phase == 'observation':
                await change_child()
            result = {'tools': [{'name': 'n8n_list_workflows', 'inputSchema': {'type': 'object'}}]}
        return httpx.Response(200, headers={'mcp-session-id': 'owned-mock-session'},
                              json={'jsonrpc': '2.0', 'id': message['id'], 'result': result})

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as child:
        app, _ = make_apps(SimpleNamespace(load=lambda: state), TOOLS, child, verify_admin=verify,
                          health=lambda: {'management': 'alive', 'child': dict(health), 'backend': 'reachable'})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app, client=('172.30.32.2', 1)),
                                     base_url='http://admin') as client:
            response = await client.get('/api/capabilities', headers={'x-remote-user-id': 'human'})
    assert checks == 2 and closed
    if change == 'role_revoked':
        assert response.status_code == 403 and 'tools' not in response.json()
        return
    assert response.status_code == 200
    result = response.json()
    assert result['health']['child'] == health['state']
    catalog = result['tools']
    item = next(item for item in catalog['items'] if item['name'] == 'n8n_list_workflows')
    if change == 'unchanged':
        assert catalog['status'] == 'observed' and catalog['effective_count'] == 1
        assert item['effective'] is True
    else:
        assert catalog['status'] == 'unknown' and catalog['effective_count'] is None
        assert item['effective'] is None
