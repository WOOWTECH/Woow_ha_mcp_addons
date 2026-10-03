"""Review regressions: disposable processes/state and loopback sockets only."""
import asyncio
import json
import os
from pathlib import Path
import signal
import sys

import httpx
import pytest

from mcp_admin_core.config import ConfigError, Store
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.lifecycle import ChildSpec, Supervisor
from mcp_admin_core.policy import authorize
from n8n_adapter import TOOLS


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "state")
    yield value
    value.close()


@pytest.mark.parametrize("restart", [False, True])
async def test_stop_during_natural_exit_cleanup_reaps_group(tmp_path, restart):
    pidfile = tmp_path / "pid"
    code = f'''
import os, signal, time
pid = os.fork()
if pid == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    open({str(pidfile)!r}, 'w').write(str(os.getpid()))
    while True: time.sleep(.01)
while not os.path.exists({str(pidfile)!r}): time.sleep(.01)
os._exit(7)
'''
    manager = Supervisor(ChildSpec((sys.executable, "-c", code), {}, tmp_path), retries=0, grace=.05)
    term = asyncio.Event()
    original = manager._signal
    def observe(pid, sig):
        original(pid, sig)
        if sig == signal.SIGTERM:
            term.set()
    manager._signal = observe
    descendant = None
    try:
        await manager.start()
        await asyncio.wait_for(term.wait(), 3)
        descendant = int(pidfile.read_text())
        leader = manager.process.pid
        if restart:
            await manager.restart(ChildSpec((sys.executable, "-c", "import time; time.sleep(60)"), {}, tmp_path))
        else:
            await manager.stop()
            assert manager.process is None
        assert not Path(f"/proc/{leader}").exists()
        assert not Path(f"/proc/{descendant}").exists()
    finally:
        await manager.stop()
        if descendant and Path(f"/proc/{descendant}").exists():
            os.kill(descendant, signal.SIGKILL)
            await asyncio.to_thread(os.waitpid, descendant, 0)


@pytest.mark.parametrize("sse", [False, True])
@pytest.mark.parametrize("method", ["initialize", "tools/list"])
async def test_advertisements_match_local_contract(store, sse, method):
    # Include the explicitly enabled writer schema, without executing a write.
    store.update(writes_enabled=True)
    result = ({"protocolVersion": "2025-03-26", "serverInfo": {"name": "mock", "version": "0"},
               "capabilities": {"tools": {"listChanged": True}, "resources": {}, "prompts": {}, "logging": {}}}
              if method == "initialize" else {"tools": [
                  {"name": name, "description": "upstream description", "inputSchema": {"type": "object"}}
                  for name in TOOLS]})
    payload = {"jsonrpc": "2.0", "id": 1, "result": result}
    def handler(_):
        if sse:
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  content="id: 123\ndata: " + json.dumps(payload) + "\n\n")
        return httpx.Response(200, json=payload)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://local") as client:
            params = {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {}} if method == "initialize" else {}
            response = await client.post("/mcp", headers={"Authorization": "Bearer " + store.load().token},
                                         json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    assert response.status_code == 200
    reply = json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith("data: "))) if sse else response.json()
    if method == "initialize":
        assert reply["result"]["capabilities"] == {"tools": {}}
    else:
        for tool in reply["result"]["tools"]:
            assert tool["inputSchema"] == TOOLS[tool["name"]].arguments.model_json_schema()
            assert tool["description"] == "upstream description"
        schemas = {tool["name"]: tool["inputSchema"] for tool in reply["result"]["tools"]}
        workflow = schemas["n8n_list_workflows"]
        assert workflow["properties"]["active"]["type"] == "boolean"
        assert "anyOf" not in workflow["properties"]["active"]
        assert "default" not in workflow["properties"]["active"]
        assert "active" not in workflow.get("required", [])
        assert workflow["properties"]["limit"]["default"] == 20
        assert schemas["search_nodes"]["properties"]["limit"]["default"] == 20
        assert schemas["tools_documentation"]["properties"]["topic"]["default"] == "overview"
        assert schemas["tools_documentation"]["properties"]["depth"]["default"] == "essentials"
        assert schemas["n8n_delete_workflow"]["required"] == ["id"]
        for name, args in [("tools_documentation", {}), ("search_nodes", {"query": "webhook", "limit": 100}),
                           ("n8n_list_workflows", {"active": True, "limit": 1}),
                           ("n8n_delete_workflow", {"id": "LOCAL-validation-only"})]:
            assert authorize({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": name, "arguments": args}}, TOOLS, store.load()) == "tools/call"


async def disconnect_request(app, token, phase="body"):
    delivered = asyncio.Event()
    sent = []
    initial = True
    async def receive():
        nonlocal initial
        if initial:
            initial = False
            return {"type": "http.request", "body": b"", "more_body": False}
        await delivered.wait()
        return {"type": "http.disconnect"}
    async def send(message):
        sent.append(message)
        if (phase == "headers" and message["type"] == "http.response.start" or
                phase == "body" and message["type"] == "http.response.body"):
            delivered.set()
    await asyncio.wait_for(app({"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "method": "GET", "path": "/mcp", "raw_path": b"/mcp", "query_string": b"",
        "scheme": "http", "server": ("localhost", 8081), "client": ("127.0.0.1", 1),
        "headers": [(b"authorization", ("Bearer " + token).encode())]}, receive, send), 6)
    return sent[0]["status"]


@pytest.mark.parametrize("phase", ["body", "headers"])
async def test_asgi23_real_socket_disconnects_release_pool(store, phase):
    counts = {"opened": 0, "closed": 0}
    handlers = set()
    async def serve(reader, writer):
        task = asyncio.current_task()
        handlers.add(task)
        try:
            await reader.readuntil(b"\r\n\r\n")
            counts["opened"] += 1
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\n: opened\n\n")
            await writer.drain()
            await reader.read()
        finally:
            counts["closed"] += 1
            writer.close()
            await writer.wait_closed()
            handlers.discard(task)
    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    baseline = len(os.listdir("/proc/self/fd"))
    try:
        async with httpx.AsyncClient(trust_env=False, limits=httpx.Limits(max_connections=40)) as child:
            _, app = make_apps(store, TOOLS, child, child_url=f"http://127.0.0.1:{port}/mcp")
            statuses = [await disconnect_request(app, store.load().token, phase) for _ in range(45)]
            assert statuses == [200] * 45
            async with asyncio.timeout(2):
                while counts["closed"] != 45:
                    await asyncio.sleep(.01)
            assert child._transport._pool.connections == []
            assert len(os.listdir("/proc/self/fd")) <= baseline + 2
    finally:
        server.close()
        await server.wait_closed()
        if handlers:
            await asyncio.wait_for(asyncio.gather(*handlers), 3)


async def test_asgi23_async_close_checkpoints_do_not_leak_slots_or_readers(store):
    counts = {"closed": 0, "readers": 0}
    class Idle(httpx.AsyncByteStream):
        async def __aiter__(self):
            counts["readers"] += 1
            try:
                yield b": opened\n\n"
                await asyncio.Event().wait()
            finally:
                counts["readers"] -= 1
        async def aclose(self):
            await asyncio.sleep(.001)  # cancellation checkpoint inside close
            counts["closed"] += 1
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=Idle()))) as child:
        _, app = make_apps(store, TOOLS, child)
        for _ in range(45):
            assert await disconnect_request(app, store.load().token) == 200
        assert counts == {"closed": 45, "readers": 0}


async def test_direct_cancellation_during_cleanup_is_joined_and_slot_released():
    from mcp_admin_core.gateway import UpstreamOwner
    started, finish = asyncio.Event(), asyncio.Event()
    slots = asyncio.Semaphore(1)
    await slots.acquire()
    class Closing:
        async def aclose(self):
            started.set()
            await finish.wait()
    owner = UpstreamOwner(slots)
    owner.response = Closing()
    task = asyncio.create_task(owner.close())
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done() and slots.locked()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not slots.locked()


@pytest.mark.parametrize("key", ["DUMMY\u00a0", "DUMMY\u007f", "DUMMY\u4e2d"])
async def test_invalid_header_secret_rejected_before_persistence(store, key):
    before = store.path.read_bytes()
    async def role(_): return True
    async with httpx.AsyncClient() as child:
        admin, _ = make_apps(store, TOOLS, child, verify_admin=role)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=("172.30.32.2", 1)), base_url="http://admin") as client:
            headers = {"X-Remote-User-Id": "test"}
            headers["X-CSRF-Token"] = (await client.get("/api/bootstrap", headers=headers)).json()["csrf"]
            response = await client.put("/api/backend", headers=headers, json={"url": "http://127.0.0.1:5678", "key": key})
    assert response.status_code == 400
    assert key not in response.text
    assert store.path.read_bytes() == before


def test_invalid_persisted_header_secret_fails_closed(store):
    value = store.load().model_dump()
    value["backend_key"] = "DUMMY\u00a0"
    store.path.write_text(json.dumps(value))
    with pytest.raises(ConfigError, match="manual recovery required"):
        store.load()
