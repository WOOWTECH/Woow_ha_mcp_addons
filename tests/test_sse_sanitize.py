"""LOCAL/MOCK: SSE events are rebuilt from lines the gateway understood (0.1.2 security review).

A child could hide unfiltered data from the gateway in a line some clients still read as data (a BOM before
"data:" at stream start, a lone CR line end) or make clients decode differently (a charset parameter).
"""
import json

import httpx
import pytest

from mcp_admin_core.config import Store
from mcp_admin_core.gateway import make_apps
from n8n_adapter import TOOLS

UNFILTERED = {"tools": {"listChanged": True}, "resources": {}, "prompts": {}, "logging": {}}


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "state")
    yield value
    value.close()


def initialize_result(capabilities):
    return {"protocolVersion": "2025-03-26", "serverInfo": {"name": "mock", "version": "0"}, "capabilities": capabilities}


async def post(store, upstream, method="initialize", **headers):
    message = {"jsonrpc": "2.0", "id": 7, "method": method,
               "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {}} if method == "initialize" else {}}
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            return await client.post("/mcp", headers={"Authorization": "Bearer " + store.load().token, **headers},
                                     json=message)


def sse(body, content_type="text/event-stream"):
    return lambda _: httpx.Response(200, headers={"content-type": content_type, "mcp-session-id": "s"}, content=body)


def data_lines(text):
    return [line for line in text.splitlines() if line.startswith("data:")]


async def test_bom_line_cannot_smuggle_unfiltered_initialize(store):
    hidden = json.dumps({"jsonrpc": "2.0", "id": 7, "result": initialize_result(UNFILTERED)}).encode()
    reply = json.dumps({"jsonrpc": "2.0", "id": 7, "result": initialize_result({"tools": {}})}).encode()
    response = await post(store, sse(b"\xef\xbb\xbfdata: " + hidden + b"\ndata: " + reply + b"\n\n"))
    assert response.status_code == 200
    assert data_lines(response.text) == ["data: " + json.dumps(json.loads(reply), separators=(",", ":"))]
    assert "﻿" not in response.text and "resources" not in response.text


async def test_lone_cr_frames_are_refused(store):
    hidden = json.dumps({"jsonrpc": "2.0", "id": 7, "result": initialize_result(UNFILTERED)}).encode()
    reply = json.dumps({"jsonrpc": "2.0", "id": 7, "result": initialize_result({"tools": {}})}).encode()
    # The security review's case: BOM + "\r\r" makes a TS/EventSource client see the hidden event first.
    response = await post(store, sse(b"\xef\xbb\xbfdata: " + hidden + b"\r\rdata: " + reply + b"\n\n"))
    assert response.status_code == 502 and "resources" not in response.text


async def test_child_charset_is_not_forwarded(store):
    reply = json.dumps({"jsonrpc": "2.0", "id": 7, "result": initialize_result(UNFILTERED)}).encode()
    response = await post(store, sse(b"data: " + reply + b"\n\n", "text/event-stream; charset=utf-16-le"))
    assert response.status_code == 200 and response.headers["content-type"] == "text/event-stream"
    assert json.loads(data_lines(response.text)[0][6:])["result"]["capabilities"] == {"tools": {}}
    response = await post(store, lambda _: httpx.Response(200, headers={"content-type": "application/json; charset=utf-16-le"},
                                                         json={"jsonrpc": "2.0", "id": 7, "result": initialize_result(UNFILTERED)}))
    assert response.status_code == 200 and response.headers["content-type"] == "application/json"
    assert response.json()["result"]["capabilities"] == {"tools": {}}


async def test_stream_rebuilds_events_from_understood_lines(store):
    listed = json.dumps({"jsonrpc": "2.0", "id": 7, "result": {"tools": [{"name": n} for n in [*TOOLS, "unreviewed"]]}}).encode()
    body = (b"\xef\xbb\xbfdata: " + listed + b"\n\n"            # BOM line: dropped, never re-emitted as data
            b": ping - 2026-10-06\r\n\r\n"                       # printable comment: kept
            b": \xe4\xb8\xad\n\n"                                 # non-ASCII comment: dropped
            b"id: e-1\nevent: message\nretry: 2000\nfoo: bar\ndata: " + listed + b"\n\n")
    response = await post(store, sse(body), method="tools/list")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream"
    assert "﻿" not in response.text and "foo: bar" not in response.text and "中" not in response.text
    assert ": ping - 2026-10-06" in response.text and "id: e-1\nevent: message\nretry: 2000\ndata: " in response.text
    [line] = data_lines(response.text)
    assert "unreviewed" not in line and {t["name"] for t in json.loads(line[6:])["result"]["tools"]} <= set(TOOLS)


async def test_stream_stops_at_a_lone_cr(store):
    # A CR is JSON whitespace, so the gateway alone would parse this event, while an SSE client ends the line
    # there and reads a different event. The stream stops instead.
    body = b'data: {"jsonrpc":"2.0",\r"id":7,"result":{"tools":[{"name":"n8n_list_workflows"}]}}\n\n'
    response = await post(store, sse(body), method="tools/list")
    assert response.status_code == 200 and data_lines(response.text) == []


@pytest.mark.parametrize("method", ["initialize", "tools/list"])
@pytest.mark.parametrize("status", [201, 203, 206])
async def test_filtered_replies_need_a_plain_200(store, method, status):
    value = {"jsonrpc": "2.0", "id": 7, "result": initialize_result(UNFILTERED) if method == "initialize"
             else {"tools": [{"name": "unreviewed"}]}}
    response = await post(store, lambda _: httpx.Response(status, json=value), method=method)
    assert response.status_code == 502 and "unreviewed" not in response.text and "resources" not in response.text


async def test_lone_surrogate_request_id_is_a_bad_request(store):
    calls = []

    def upstream(request):
        calls.append(request)
        return httpx.Response(200, json={})
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            response = await client.post("/mcp", headers={"Authorization": "Bearer " + store.load().token,
                                                          "Content-Type": "application/json"},
                                         content=b'{"jsonrpc":"2.0","id":"\\ud800x","method":"ping"}')
    assert response.status_code == 400 and not calls


async def call(store, upstream, verb="POST", message=None, capture=None):
    message = message or {"jsonrpc": "2.0", "id": 9, "method": "ping"}
    def handler(request):
        if capture is not None:
            capture.append(request)
        return upstream(request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            headers = {"Authorization": "Bearer " + store.load().token, "Mcp-Session-Id": "s"}
            if verb == "GET":
                return await client.get("/mcp", headers=headers)
            return await client.post("/mcp", headers=headers, json=message)


UNREVIEWED = json.dumps({"jsonrpc": "2.0", "id": 9, "result": {"tools": [{"name": "unreviewed"}]}}).encode()


@pytest.mark.parametrize("verb", ["POST", "GET"])
@pytest.mark.parametrize("content_type", ["Text/Event-Stream", "text/event-stream ;charset=utf-8",
                                          "text/event-stream\t; charset=utf-16-le", "TEXT/EVENT-STREAM"])
async def test_sse_media_type_variants_are_rebuilt(store, verb, content_type):
    response = await call(store, lambda _: httpx.Response(200, headers={"content-type": content_type},
                                                          content=b"\xef\xbb\xbfdata: " + UNREVIEWED + b"\ndata: " + UNREVIEWED + b"\n\n"), verb)
    assert response.status_code == 200 and response.headers["content-type"] == "text/event-stream"
    assert "unreviewed" not in response.text and "﻿" not in response.text


@pytest.mark.parametrize("verb", ["POST", "GET"])
@pytest.mark.parametrize("headers", [{"content-type": "text/plain"}, {}, [("content-type", "text/event-stream"), ("content-type", "text/event-stream")]])
async def test_unknown_or_duplicate_media_types_are_bad_gateway(store, verb, headers):
    response = await call(store, lambda _: httpx.Response(200, headers=headers, content=b"data: " + UNREVIEWED + b"\n\n"), verb)
    assert response.status_code == 502 and "unreviewed" not in response.text


async def test_get_stream_must_be_sse(store):
    response = await call(store, lambda _: httpx.Response(200, json={"jsonrpc": "2.0", "id": 9, "result": {}}), "GET")
    assert response.status_code == 502
    response = await call(store, lambda _: httpx.Response(405), "GET")  # no GET stream: forwarded as is
    assert response.status_code == 405


@pytest.mark.parametrize("value", [{"jsonrpc": "2.0", "id": 8, "result": {"tools": [{"name": "unreviewed"}]}},
                                   [{"jsonrpc": "2.0", "id": 9, "result": {}}], {"jsonrpc": "2.0", "id": True, "result": {}},
                                   {"jsonrpc": "2.0", "method": "notifications/message"}])
async def test_json_reply_must_be_this_requests_object(store, value):
    response = await call(store, lambda _: httpx.Response(200, json=value), message={"jsonrpc": "2.0", "id": 9, "method": "ping"})
    assert response.status_code == 502 and "unreviewed" not in response.text


async def test_json_reply_is_filtered_and_reserialized(store):
    response = await call(store, lambda _: httpx.Response(200, headers={"content-type": "application/json; charset=utf-16-le"},
                                                          content=UNREVIEWED))
    assert response.status_code == 200 and response.headers["content-type"] == "application/json"
    assert response.json() == {"jsonrpc": "2.0", "id": 9, "result": {"tools": []}}


async def test_sse_batch_stops_the_stream_and_fails_initialize(store):
    batch = b"data: [" + UNREVIEWED + b"]\n\n"
    response = await call(store, lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=batch))
    assert response.status_code == 200 and data_lines(response.text) == []
    response = await post(store, sse(b'data: [{"jsonrpc":"2.0","id":7,"result":{}}]\n\n'))
    assert response.status_code == 502


async def test_empty_priming_events_pass(store):
    reply = json.dumps({"jsonrpc": "2.0", "id": 7, "result": initialize_result({"tools": {}})}).encode()
    response = await post(store, sse(b"id: p-0\ndata: \n\n" + b"id: p-1\nevent: message\ndata: " + reply + b"\n\n"))
    assert response.status_code == 200 and json.loads(data_lines(response.text)[0][6:])["id"] == 7
    response = await call(store, lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"},
                                                          content=b"id: p-0\ndata: \n\nid: p-1\ndata: " + UNREVIEWED + b"\n\n"))
    assert response.text.startswith("id: p-0\ndata:\n\nid: p-1\ndata: ")
    assert "unreviewed" not in response.text


async def test_lone_surrogate_in_a_child_reply_is_escaped(store):
    value = {"jsonrpc": "2.0", "id": 7, "result": {**initialize_result({"tools": {}}), "instructions": "\ud800"}}
    raw = json.dumps(value).encode()  # ASCII escape \ud800, valid JSON text
    response = await post(store, lambda _: httpx.Response(200, headers={"content-type": "application/json"}, content=raw))
    assert response.status_code == 200 and "\\ud800" in response.text


async def test_initialize_forwards_no_client_capabilities(store):
    seen = []
    reply = {"jsonrpc": "2.0", "id": 7, "result": initialize_result({"tools": {}})}
    message = {"jsonrpc": "2.0", "id": 7, "method": "initialize",
               "params": {"protocolVersion": "2025-03-26", "clientInfo": {"name": "c", "version": "0"},
                          "capabilities": {"elicitation": {}, "sampling": {}, "roots": {"listChanged": True}}}}
    response = await call(store, lambda _: httpx.Response(200, json=reply), message=message, capture=seen)
    assert response.status_code == 200
    assert json.loads(seen[0].content)["params"] == {**message["params"], "capabilities": {}}


async def test_sse_ids_follow_the_last_event_id_rules(store):
    reply = json.dumps({"jsonrpc": "2.0", "id": 9, "result": {}}).encode()
    response = await call(store, lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"},
                                                          content=b"id: a b\nretry: soon\ndata: " + reply + b"\n\nid: ok-2\nretry: 2000\ndata: " + reply + b"\n\n"))
    assert "id: a b" not in response.text and "retry: soon" not in response.text
    assert "id: ok-2\nretry: 2000\ndata: " in response.text


async def test_reply_ids_compare_with_their_json_type(store):
    message = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    response = await call(store, lambda _: httpx.Response(200, json={"jsonrpc": "2.0", "id": True, "result": {}}), message=message)
    assert response.status_code == 502  # true is not 1
    response = await call(store, lambda _: httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}}), message=message)
    assert response.status_code == 200 and response.json()["id"] == 1


LYING = {"content-length": "0", "transfer-encoding": "chunked"}  # the round-3 smuggling signature


@pytest.mark.parametrize("verb,status,content_type", [("POST", 201, "application/json"), ("GET", 200, "application/json"),
                                                      ("GET", 200, "text/event-streamx"), ("POST", 200, "text/plain")])
async def test_declared_empty_bodies_are_never_relayed(store, verb, status, content_type):
    body = UNREVIEWED if "json" in content_type else b"data: " + UNREVIEWED + b"\n\n"
    response = await call(store, lambda _: httpx.Response(status, headers={**LYING, "content-type": content_type}, content=body), verb)
    assert response.status_code == 502 and "unreviewed" not in response.text


async def test_declared_empty_initialize_is_unavailable_without_relaying(store):
    body = json.dumps({"jsonrpc": "2.0", "id": 7, "result": initialize_result(UNFILTERED)}).encode()
    response = await post(store, lambda _: httpx.Response(200, headers={**LYING, "mcp-session-id": "s"}, content=body))
    assert response.status_code == 503 and "resources" not in response.text and "mcp-session-id" not in response.headers


async def test_notification_replies_carry_no_child_bytes(store):
    message = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    response = await call(store, lambda _: httpx.Response(200, headers={"content-type": "text/event-stream", "mcp-session-id": "s"},
                                                          content=b"data: " + UNREVIEWED + b"\n\n"), message=message)
    assert response.status_code == 200 and response.content == b"" and "content-type" not in response.headers
    assert response.headers["mcp-session-id"] == "s"
    response = await call(store, lambda _: httpx.Response(202), message=message)
    assert response.status_code == 202 and response.content == b""


@pytest.mark.parametrize("verb", ["POST", "GET"])
async def test_stream_drops_server_to_client_requests(store, verb):
    ask = json.dumps({"jsonrpc": "2.0", "id": "e1", "method": "elicitation/create",
                      "params": {"message": "Re-enter your Home Assistant password", "requestedSchema": {}}}).encode()
    note = json.dumps({"jsonrpc": "2.0", "method": "notifications/progress", "params": {"progress": 1}}).encode()
    reply = json.dumps({"jsonrpc": "2.0", "id": 9, "result": {}}).encode()
    response = await call(store, lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"},
                                                          content=b"data: " + ask + b"\n\ndata: " + note + b"\n\ndata: " + reply + b"\n\n"), verb)
    assert response.status_code == 200
    assert "elicitation" not in response.text and "password" not in response.text
    assert [json.loads(line[6:]).get("method") for line in data_lines(response.text)] == ["notifications/progress", None]


@pytest.mark.parametrize("value", [{"jsonrpc": "2.0", "id": 9, "method": "ping", "result": {}},  # a request, not a reply
                                   {"jsonrpc": "2.0", "id": 9}])                                  # neither result nor error
async def test_json_reply_needs_result_or_error_and_no_method(store, value):
    assert (await call(store, lambda _: httpx.Response(200, json=value))).status_code == 502


async def test_oversize_json_reply_is_bad_gateway(store, monkeypatch):
    import mcp_admin_core.gateway as gateway
    monkeypatch.setattr(gateway, "MAX_RESPONSE", 1024)

    class Padded(httpx.AsyncByteStream):  # a complete reply first: only the size bound can refuse it
        async def __aiter__(self):
            yield b'{"jsonrpc":"2.0","id":9,"result":{}}'
            yield b" " * 4000
    response = await call(store, lambda _: httpx.Response(200, headers={"content-type": "application/json"}, stream=Padded()))
    assert response.status_code == 502


async def test_revocation_while_buffering_a_json_reply_is_401(store):
    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"jsonrpc":"2.0","id":9,'
            store.update(token=None)  # revoked while the reply is being read
            yield b'"result":{}}'
    response = await call(store, lambda _: httpx.Response(200, headers={"content-type": "application/json"}, stream=Slow()))
    assert response.status_code == 401


@pytest.mark.parametrize("status", [201, 206])
async def test_sse_needs_a_plain_200(store, status):
    response = await call(store, lambda _: httpx.Response(status, headers={"content-type": "text/event-stream"},
                                                          content=b"data: " + UNREVIEWED + b"\n\n"))
    assert response.status_code == 502 and "unreviewed" not in response.text


async def test_head_never_reaches_the_child(store):
    seen = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200))) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            response = await client.head("/mcp", headers={"Authorization": "Bearer " + store.load().token})
    assert response.status_code == 405 and not seen


async def test_bad_child_header_values_never_leak_slots(store):
    # Round 4: a non-Latin-1 header value made the streaming reply's constructor fail after the hand-off flag
    # was set, so its slot was never released; 32 such replies blocked the endpoint until a restart.
    seen = []
    reply = json.dumps({"jsonrpc": "2.0", "id": 9, "result": {}}).encode()

    def upstream(request):
        seen.append(request)
        return httpx.Response(200, headers=[(b"content-type", b"text/event-stream"), (b"mcp-session-id", "中".encode()),
                                            (b"retry-after", b"soon"), (b"mcp-protocol-version", b"2025-03-26")],
                              content=b"data: " + reply + b"\n\n")
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            for _ in range(40):  # more than the 32 slots
                response = await client.post("/mcp", headers={"Authorization": "Bearer " + store.load().token},
                                             json={"jsonrpc": "2.0", "id": 9, "method": "ping"})
                assert response.status_code == 200, response.status_code
                assert "mcp-session-id" not in response.headers and "retry-after" not in response.headers
                assert response.headers["mcp-protocol-version"] == "2025-03-26"
    assert len(seen) == 40


async def test_delete_replies_carry_no_child_bytes(store):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(
            200, headers={"content-type": "application/json; charset=utf-16"}, content=UNREVIEWED))) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            response = await client.delete("/mcp", headers={"Authorization": "Bearer " + store.load().token, "Mcp-Session-Id": "s"})
    assert response.status_code == 200 and response.content == b"" and "content-type" not in response.headers


async def test_head_405_names_the_allowed_methods(store):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            response = await client.head("/mcp", headers={"Authorization": "Bearer " + store.load().token})
    assert response.status_code == 405 and response.headers["allow"] == "GET, POST, DELETE"


async def test_overflowing_numbers_are_refused_both_ways(store):
    seen = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(
            200, headers={"content-type": "application/json"}, content=b'{"jsonrpc":"2.0","id":9,"result":{"x":1e400}}'))) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            headers = {"Authorization": "Bearer " + store.load().token, "Content-Type": "application/json"}
            request = await client.post("/mcp", headers=headers, content=b'{"jsonrpc":"2.0","id":1e400,"method":"ping"}')
            assert request.status_code == 400 and not seen  # never forwarded as Infinity
            reply = await client.post("/mcp", headers=headers, content=b'{"jsonrpc":"2.0","id":9,"method":"ping"}')
            assert reply.status_code == 502 and "Infinity" not in reply.text


async def test_a_failing_stream_response_constructor_releases_its_slot(store, monkeypatch):
    import mcp_admin_core.gateway as gateway
    failures = {"left": 32}  # as many as there are slots

    class Fragile(gateway.OwnedStreamingResponse):
        def __init__(self, *args, **kwargs):
            if failures["left"]:
                failures["left"] -= 1
                raise RuntimeError("constructor failed")
            super().__init__(*args, **kwargs)
    monkeypatch.setattr(gateway, "OwnedStreamingResponse", Fragile)
    reply = json.dumps({"jsonrpc": "2.0", "id": 9, "result": {}}).encode()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=b"data: " + reply + b"\n\n"))) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                     base_url="http://mcp") as client:
            statuses = []
            for _ in range(34):
                response = await client.post("/mcp", headers={"Authorization": "Bearer " + store.load().token},
                                             json={"jsonrpc": "2.0", "id": 9, "method": "ping"})
                statuses.append(response.status_code)
    assert statuses == [500] * 32 + [200, 200]  # with a leaked slot per failure the last two would be 503


@pytest.mark.parametrize("session", ["中".encode(), b"x" * 300])
async def test_initialize_with_an_unusable_session_id_is_bad_gateway(store, session):
    reply = json.dumps({"jsonrpc": "2.0", "id": 7, "result": initialize_result({"tools": {}})}).encode()
    response = await post(store, lambda _: httpx.Response(200, headers=[(b"content-type", b"application/json"),
                                                                        (b"mcp-session-id", session)], content=reply))
    assert response.status_code == 502


@pytest.mark.parametrize("verb", ["PUT", "PATCH", "OPTIONS"])
async def test_other_methods_authenticate_then_405(store, verb):
    seen = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200))) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            assert (await client.request(verb, "/mcp")).status_code == 401
            response = await client.request(verb, "/mcp", headers={"Authorization": "Bearer " + store.load().token})
    assert response.status_code == 405 and response.headers["allow"] == "GET, POST, DELETE" and not seen


async def test_child_sees_a_fixed_accept_and_odd_statuses_are_bad_gateway(store):
    seen = []
    response = await call(store, lambda _: httpx.Response(200, json={"jsonrpc": "2.0", "id": 9, "result": {}}), capture=seen)
    assert response.status_code == 200 and seen[0].headers["accept"] == "application/json, text/event-stream"
    assert (await call(store, lambda _: httpx.Response(600, json={}))).status_code == 502


async def test_overflowing_numbers_inside_forwarded_values(store):
    seen = []
    message = {"jsonrpc": "2.0", "id": 7, "method": "initialize",
               "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "c", "version": "0"}}}
    raw = json.dumps(message).replace('"version": "0"', '"version": "0", "build": 1e400').encode()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200))) as child:
        _, app = make_apps(store, TOOLS, child)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as client:
            response = await client.post("/mcp", headers={"Authorization": "Bearer " + store.load().token,
                                                          "Content-Type": "application/json"}, content=raw)
    assert response.status_code == 400 and not seen  # never forwarded as Infinity
    listed = b'{"jsonrpc":"2.0","id":9,"result":{"tools":[{"name":"search_nodes","annotations":{"x":1e400}}]}}'
    response = await call(store, lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"},
                                                          content=b"data: " + listed + b"\n\n"),
                          message={"jsonrpc": "2.0", "id": 9, "method": "tools/list"})
    assert response.status_code == 200 and "Infinity" not in response.text and data_lines(response.text) == []
