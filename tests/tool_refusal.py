"""0.1.14 test helper: the gateway's own answer to a refused well-formed tools/call inside a session.

Before 0.1.14 these refusals were HTTP 403 {"error":"request denied"}; now they are HTTP 200 application/json with a
JSON-RPC error (-32602 Unknown tool / Invalid params / Operation not permitted, -32603 Backend not configured) and no
result. Callers keep asserting that the child or backend was not reached.
"""
MESSAGES = {-32602: ("Unknown tool", "Invalid params", "Operation not permitted"),
            -32603: ("Backend not configured", "Backend unreachable")}  # 0.2.2: Backend unreachable


def refusal(response):
    """The JSON-RPC error of a gateway refusal, else None (a 403, a child's reply, a result, any other code)."""
    if response.status_code != 200 or response.headers.get("content-type") != "application/json":
        return None
    if response.headers.get("cache-control") != "no-store" or "mcp-session-id" in response.headers:
        return None
    body = response.json()
    if not isinstance(body, dict) or set(body) != {"jsonrpc", "id", "error"} or body["jsonrpc"] != "2.0":
        return None
    error = body["error"]
    if not isinstance(error, dict) or error.get("message") not in MESSAGES.get(error.get("code"), ()):
        return None
    return error


def refused(response, message=None):
    """True for a gateway refusal (optionally with this message)."""
    error = refusal(response)
    return error is not None and (message is None or error["message"] == message)
