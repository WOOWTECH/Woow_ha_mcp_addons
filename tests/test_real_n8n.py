"""REAL local pinned n8n subprocess, NOT HA/production backend E2E.

Two real TCP listeners, bundled documentation and (one parameterized case) a
loopback fake workflow API with an invented key. No real n8n backend is contacted.
"""
import asyncio
import json
import os
from pathlib import Path
import signal
import socket
import sys
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from mcp_admin_core import VERSION
from mcp_admin_core.config import Store
from mcp_admin_core.health import protocol_reply

from owned_executable import Executable
from batch2_owned_port import reserve_port

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with reserve_port() as sock:
        return sock.getsockname()[1]


@pytest.fixture
async def fake_backend():
    calls = []
    handlers = set()
    async def serve(reader, writer):
        handlers.add(asyncio.current_task())
        try:
            request = await reader.readuntil(b"\r\n\r\n")
            calls.append(request)
            body = b'{"data":[],"nextCursor":null}'
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                         + str(len(body)).encode() + b"\r\n\r\n" + body)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            handlers.discard(asyncio.current_task())
    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    try:
        yield f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}", calls
    finally:
        server.close()
        await server.wait_closed()
        if handlers:
            await asyncio.gather(*handlers)


@pytest.mark.parametrize("configured_backend,check_defaults", [
    (False, None), (True, "omission"), (True, "null"),
])
async def test_real_tcp_runtime_documentation_session_and_shutdown(tmp_path, fake_backend, configured_backend, check_defaults):
    if not (ROOT / "apps/n8n/node_modules/n8n-mcp/dist/mcp/index.js").exists():
        pytest.skip("EXTERNAL GATE: run npm ci --ignore-scripts --prefix apps/n8n")
    data = tmp_path / "state"
    store = Store(data)
    if configured_backend:
        store.update(backend_url=fake_backend[0], backend_key="DUMMY-local-only")
    token = store.load().token
    store.close()
    admin_port, mcp_port = free_port(), free_port()
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "packages/mcp-admin-core") + ":" + str(ROOT / "apps/n8n")}
    runner = Executable(tmp_path, 'n8n', [admin_port, mcp_port])
    code = 'import run; ' + runner.code('run') + 'run.main()'
    runner.release()
    process = await asyncio.create_subprocess_exec(sys.executable, '-c', code,
        "--data", str(data), "--host", "127.0.0.1", "--admin-port", str(admin_port), "--mcp-port", str(mcp_port),
        cwd=tmp_path, env=env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    children = []
    started = time.monotonic()
    try:
        await runner.ready(process)
        async with httpx.AsyncClient(trust_env=False, timeout=15, event_hooks={'request': [runner.guard]}) as client:
            url = f"http://127.0.0.1:{mcp_port}/mcp"
            headers = {"Authorization": "Bearer " + token, "Accept": "application/json, text/event-stream"}
            initialized = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "local-no-backend-smoke", "version": "0"}}}
            async with asyncio.timeout(35):
                while True:
                    assert process.returncode is None
                    try:
                        async with client.stream("POST", url, headers=headers, json=initialized) as response:
                            if response.status_code == 200:
                                session = response.headers.get("mcp-session-id")
                                result = await protocol_reply(response, 1)
                                break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.2)
            # 0.1.8 (F6): the add-on's identity, not n8n-mcp's ("n8n-documentation-mcp" 2.91.0); no instructions.
            assert result["serverInfo"] == {"name": "woow-mcp-n8n", "version": VERSION} and "instructions" not in result
            assert result["capabilities"] == {"tools": {}}
            assert session
            headers["Mcp-Session-Id"] = session
            headers["MCP-Protocol-Version"] = result["protocolVersion"]
            r = await client.post(url, headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
            assert r.status_code in (200, 202, 204)
            async with client.stream("POST", url, headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) as response:
                tools = await protocol_reply(response, 2)
            names = {tool["name"] for tool in tools["tools"]}
            assert {"tools_documentation", "search_nodes"} <= names
            assert names <= {"tools_documentation", "search_nodes", "n8n_list_workflows",
                             "get_node", "n8n_get_workflow", "n8n_manage_folders", "validate_node", "validate_workflow",
                             "n8n_list_catalog", "n8n_executions", "n8n_health_check"}
            assert 'get_node' in names
            from n8n_adapter import TOOLS
            from mcp_admin_core.policy import declared_schema
            for tool in tools["tools"]:
                assert tool["inputSchema"] == declared_schema(TOOLS[tool["name"]].arguments)  # 0.1.6 declared form
            if configured_backend:
                # Forged instance headers must not redirect the real Node API path.
                async with client.stream("POST", url, headers={**headers,
                    "x-n8n-url": "http://127.0.0.1:1", "x-n8n-key": "WRONG"}, json={
                        "jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {
                            "name": "n8n_list_workflows", "arguments": {"limit": 1}}}) as response:
                    backend_result = await protocol_reply(response, 9)
                assert json.loads(backend_result["content"][0]["text"])["success"] is True
                assert fake_backend[1]
                assert all(b"X-N8N-API-KEY: DUMMY-local-only" in call for call in fake_backend[1])
                assert all(b"WRONG" not in call for call in fake_backend[1])
                async def workflow_call(arguments):
                    return await client.post(url, headers=headers, json={
                        "jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {
                            "name": "n8n_list_workflows", "arguments": arguments}})

                def workflow_queries():
                    return [parse_qs(urlsplit(call.split(b" ")[1].decode()).query)
                            for call in fake_backend[1]]

                if check_defaults == "omission":
                    # The health monitor uses limit=1; assert the *actual* Node API
                    # query for each client call, not the advertised/local model.
                    for arguments, expected in [({}, {"limit": ["20"], "excludePinnedData": ["true"]}),
                            ({"active": False}, {"limit": ["20"], "active": ["false"], "excludePinnedData": ["true"]}),
                            ({"active": True, "limit": 7}, {"limit": ["7"], "active": ["true"], "excludePinnedData": ["true"]})]:
                        before = len(fake_backend[1])
                        response = await workflow_call(arguments)
                        assert response.status_code == 200
                        result = await protocol_reply(response, 10)
                        assert json.loads(result["content"][0]["text"])["success"] is True
                        queries = workflow_queries()[before:]
                        assert expected in queries, queries
                else:
                    for arguments in ({"active": None}, {"limit": None}):
                        before = len(fake_backend[1])
                        response = await workflow_call(arguments)
                        assert response.status_code == 403
                        # Any concurrent automatic health read has its own limit=1.
                        assert all(query["limit"] == ["1"] for query in workflow_queries()[before:])
                assert all(call.startswith(b"GET /api/v1/workflows?") for call in fake_backend[1])
            latencies = []
            for name, args in [("tools_documentation", {}), ("search_nodes", {"query": "webhook", "limit": 1})]:
                now = time.monotonic()
                async with client.stream("POST", url, headers=headers, json={"jsonrpc": "2.0", "id": 3,
                    "method": "tools/call", "params": {"name": name, "arguments": args}}) as response:
                    result = await protocol_reply(response, 3)
                latencies.append(round((time.monotonic() - now) * 1000))
                assert not result.get("isError", False)
                assert result["content"] and result["content"][0]["type"] == "text"
                if name == "search_nodes":
                    assert "webhook" in result["content"][0]["text"].lower()
            if not configured_backend:
                # Check the other read-only defaults against the real handler,
                # not just schemas. Both tools use bundled data, not a backend.
                for name, omitted, explicit in [
                    ("tools_documentation", {}, {"topic": "overview", "depth": "essentials"}),
                    ("search_nodes", {"query": "http"}, {"query": "http", "limit": 20}),
                ]:
                    replies = []
                    for args in (omitted, explicit):
                        response = await client.post(url, headers=headers, json={
                            "jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {
                                "name": name, "arguments": args}})
                        assert response.status_code == 200
                        replies.append(await protocol_reply(response, 11))
                    assert replies[0] == replies[1]
                    assert not replies[0].get("isError", False)
                    if name == "search_nodes":
                        search = json.loads(replies[0]["content"][0]["text"])
                        assert 0 < len(search["results"]) <= 20
            for method in ("GET", "POST", "DELETE"):
                assert (await client.request(method, url, headers={"Mcp-Session-Id": session})).status_code == 401
            # GET attaches a real Streamable HTTP SSE channel for this session.
            async with client.stream("GET", url, headers={**headers, "Accept": "text/event-stream"}) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
            # Real Uvicorn ASGI 2.3 disconnect must detach the upstream SSE session.
            await asyncio.sleep(.3)
            async with client.stream("GET", url, headers={**headers, "Accept": "text/event-stream"}) as response:
                assert response.status_code == 200
            await asyncio.sleep(.3)
            assert (await client.delete(url, headers=headers)).status_code == 204
            assert (await client.get(f"http://127.0.0.1:{admin_port}/api/bootstrap", headers={"X-Remote-User-Id": "forged", "X-Forwarded-For": "172.30.32.2"})).status_code == 403
            if configured_backend:
                async with asyncio.timeout(20):
                    while (await client.get(url.replace("/mcp", "/health/ready"))).status_code != 200:
                        await asyncio.sleep(.1)
            else:
                assert (await client.get(url.replace("/mcp", "/health/ready"))).status_code == 503
            children = [int(v) for v in Path(f"/proc/{process.pid}/task/{process.pid}/children").read_text().split()]
            assert len(children) == 1
            rss = next(line.split()[1] for line in Path(f"/proc/{children[0]}/status").read_text().splitlines() if line.startswith("VmRSS:"))
            print(f"REAL LOCAL n8n 2.91.0: elapsed={time.monotonic()-started:.2f}s tool_latency_ms={latencies} child_rss_kib={rss}; fake_backend={configured_backend}, NOT production/HA E2E")
    finally:
        if process.returncode is None:
            process.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), 12)
        except TimeoutError:
            process.kill()
            await process.wait()
            pytest.fail("runtime did not terminate within deadline")
    assert process.returncode == 0
    for pid in children:
        assert not Path(f"/proc/{pid}").exists()
