"""LOCAL/MOCK transport and fault injection; not HA/backend E2E."""
import asyncio
import json
import os

import httpx
import pytest

from mcp_admin_core.config import ConfigError, Store
from mcp_admin_core.gateway import make_apps
from n8n_adapter import TOOLS


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "state")
    yield value
    value.close()


def test_missing_existing_state_cannot_silently_rebootstrap(store):
    directory = store.directory
    store.path.unlink()
    with pytest.raises(ConfigError):
        store.load()
    store.close()
    with pytest.raises(ConfigError):
        Store(directory)
    assert not (directory / "state.json").exists()


@pytest.mark.parametrize("version", [0, 2, True, "1"])
def test_complete_unsupported_schema_is_preserved(store, version):
    value = store.load().model_dump()
    value["schema_version"] = version
    raw = json.dumps(value)
    store.path.write_text(raw)
    directory = store.directory
    store.close()
    with pytest.raises(ConfigError):
        Store(directory)
    assert (directory / "state.json").read_text() == raw


def test_interrupted_atomic_replace_preserves_previous_state(store, monkeypatch):
    original = store.load()
    def fail(*_):
        raise OSError("injected LOCAL storage fault")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(ConfigError):
        store.update(writes_enabled=True)
    with pytest.raises(ConfigError):
        store.load()
    monkeypatch.undo()
    store.close()
    reopened = Store(store.directory)
    assert reopened.load() == original
    assert not list(store.directory.glob(".state-*"))
    reopened.close()


def test_durability_calls_file_then_directory_fsync(store, monkeypatch):
    seen = []
    real = os.fsync
    def record(fd):
        seen.append(os.fstat(fd).st_mode)
        real(fd)
    monkeypatch.setattr(os, "fsync", record)
    store.update(endpoint="http://mcp.example.test:8081/mcp")
    import stat
    assert len(seen) == 2 and stat.S_ISREG(seen[0]) and stat.S_ISDIR(seen[1])


def test_state_symlink_rejected_without_touching_target(store, tmp_path):
    outside = tmp_path / "outside"
    outside.write_text("not state")
    store.path.unlink()
    store.path.symlink_to(outside)
    with pytest.raises(ConfigError):
        store.load()
    assert outside.read_text() == "not state"


class Fragmented(httpx.AsyncByteStream):
    def __init__(self, fragments):
        self.fragments = fragments
        self.closed = False
    async def __aiter__(self):
        for fragment in self.fragments:
            yield fragment
    async def aclose(self):
        self.closed = True


async def test_fragmented_sse_filter_preserves_event_and_session_semantics(store):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": n} for n in [*TOOLS, "unreviewed"]]}}).encode()
    raw = b": heartbeat\r\n\r\nid: event-1\r\nevent: message\r\nretry: 2000\r\ndata: " + payload + b"\r\n\r\n"
    stream = Fragmented([raw[i:i+7] for i in range(0, len(raw), 7)])
    def upstream(_):
        return httpx.Response(200, headers={"content-type": "text/event-stream", "mcp-session-id": "session", "Set-Cookie": "must-not-forward", "Connection": "keep-alive"}, stream=stream)
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            response = await client.post("/mcp", headers={"Authorization": "Bearer " + store.load().token, "Mcp-Session-Id": "session"},
                                         json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response.status_code == 200
    assert response.headers["mcp-session-id"] == "session"
    assert "set-cookie" not in response.headers and "connection" not in response.headers
    assert "id: event-1" in response.text and "retry: 2000" in response.text and ": heartbeat" in response.text
    data = next(line[6:] for line in response.text.splitlines() if line.startswith("data: "))
    tools = json.loads(data)["result"]["tools"]
    assert {t["name"] for t in tools} == {"tools_documentation", "search_nodes", "n8n_list_workflows",
                                         "get_node", "n8n_get_workflow", "n8n_manage_folders", "validate_node", "validate_workflow",
                                         "n8n_list_catalog", "n8n_executions", "n8n_health_check"}
    assert stream.closed


async def test_rotation_closes_idle_authenticated_stream(store):
    opened = asyncio.Event()
    closed = asyncio.Event()
    class Idle(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b": opened\n\n"
            opened.set()
            await asyncio.Event().wait()
        async def aclose(self):
            closed.set()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Idle()))) as child:
        _, app = make_apps(store, TOOLS, child)
        messages = []
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        async def send(message):
            messages.append(message)
        task = asyncio.create_task(app({"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1", "method": "GET", "path": "/mcp", "raw_path": b"/mcp", "query_string": b"",
            "scheme": "http", "server": ("localhost", 8081), "client": ("127.0.0.1", 1),
            "headers": [(b"authorization", ("Bearer " + store.load().token).encode()),
                        (b"mcp-session-id", b"test-session")]}, receive, send))
        await asyncio.wait_for(opened.wait(), 2)
        store.update(token=None)
        await asyncio.wait_for(task, 2)
        assert closed.is_set()
        assert messages[0]["status"] == 200
        assert messages[-1].get("more_body") is False


async def test_upstream_status_and_empty_notification_response_preserved(store):
    for status in (202, 204, 404, 429):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(status))) as child:
            _, app = make_apps(store, TOOLS, child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
                response = await client.delete("/mcp", headers={"Authorization": "Bearer " + store.load().token, "Mcp-Session-Id": "example"})
            assert response.status_code == status and response.content == b""


async def test_corrupt_state_mid_session_denies_before_forwarding(store):
    calls = []
    def upstream(request):
        calls.append(request)
        return httpx.Response(204)
    token = store.load().token
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as child:
        _, app = make_apps(store, TOOLS, child)
        store.path.write_text("broken")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            response = await client.get("/mcp", headers={"Authorization": "Bearer " + token, "Mcp-Session-Id": "cached"})
        assert response.status_code == 503 and not calls
