"""Actual HA gateway authorization before a fake child dispatch."""
import json

import httpx
import pytest

from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS
from tool_refusal import refused


@pytest.mark.parametrize("name,args", [
    ("litellm_health", {"model": "fake"}),
    ("litellm_token_counter", {"model": "fake", "prompt": "hello"}),
    ("litellm_spend_calculate", {"model": "fake/provider", "messages": []}),
])
async def test_existing_exact_grants_still_control_dispatch(tmp_path, name, args):
    tools = TOOLS["litellm"]
    assert len(tools) == 40
    assert sum(tool.write for tool in tools.values()) == 25
    assert tools[name].write is True
    store = ProductStore(tmp_path, "litellm")
    calls = []
    def dispatch(request):
        message = json.loads(request.content)
        calls.append(message)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": message["id"],
                                        "result": {"content": []}})
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": args}}
    try:
        store.update(connection={"url": "http://fake.invalid", "master_key": "fake"},
                     writes_enabled=False, enabled_write_tools=[])
        async with httpx.AsyncClient(transport=httpx.MockTransport(dispatch)) as child:
            _, app = make_apps(store, tools, child)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
                headers = {"Authorization": "Bearer " + store.load().token, "Mcp-Session-Id": "test-session"}
                assert refused(await client.post("/mcp", headers=headers, json=message))
                assert calls == []
                store.update(enabled_write_tools=[name])
                assert (await client.post("/mcp", headers=headers, json=message)).status_code == 200
                assert calls == [message]
                store.update(disabled=[name])
                assert refused(await client.post("/mcp", headers=headers, json=message))
                assert len(calls) == 1
    finally:
        store.close()
