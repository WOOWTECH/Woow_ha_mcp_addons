"""Audited dispatch allowlist. Tool advertisements are not authorization."""
from dataclasses import dataclass
from typing import Mapping

from pydantic import BaseModel, ValidationError

from .config import State


class Denied(ValueError):
    pass


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    write: bool = False
    # Only the two W2a writers retain the historical global-switch semantics.
    legacy_write: bool = False
    selector: str | None = None
    write_operations: tuple[str, ...] = ()

    def grants(self, name):
        return ([name] if self.write else []) + [f'{name}:{op}' for op in self.write_operations]


def has_grant(name, tool, state):
    return name in getattr(state, 'enabled_write_tools', ()) or (tool.legacy_write and state.writes_enabled)


def enabled(name: str, tools: Mapping[str, Tool], state: State) -> bool:
    return name in tools and name not in state.disabled and (not tools[name].write or has_grant(name, tools[name], state))


def authorize(message, tools: Mapping[str, Tool], state: State) -> str:
    """Authorize, replacing tool arguments with the reviewed model's wire values.

    Defaults and field-specific omission rules are applied before dispatch;
    repeated authorization is idempotent. Invalid calls are never normalized.
    """
    if not isinstance(message, dict) or set(message) - {"jsonrpc", "id", "method", "params"}:
        raise Denied("single JSON-RPC request required")
    if message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        raise Denied("invalid JSON-RPC")
    method = message["method"]
    params = message.get("params", {})
    if not isinstance(params, dict):
        raise Denied("params must be object")
    if method == "notifications/initialized":
        if "id" in message or params:
            raise Denied("invalid initialized notification")
        return method
    if type(message.get("id")) not in (str, int):
        raise Denied("request id required; tool notifications are forbidden")
    if method == "initialize":
        if set(params) != {"protocolVersion", "capabilities", "clientInfo"}:
            raise Denied("invalid initialization")
        if (not isinstance(params["protocolVersion"], str) or not isinstance(params["capabilities"], dict)
                or not isinstance(params["clientInfo"], dict)):
            raise Denied("invalid initialization")
    elif method == "ping":
        if params:
            raise Denied("invalid ping")
    elif method == "tools/list":
        if set(params) - {"cursor"} or ("cursor" in params and not isinstance(params["cursor"], str)):
            raise Denied("invalid list")
    elif method == "tools/call":
        name = params.get("name")
        if set(params) - {"name", "arguments"} or not isinstance(name, str) or not enabled(name, tools, state):
            raise Denied("tool not permitted")
        try:
            arguments = tools[name].arguments.model_validate(params.get("arguments", {}))
        except ValidationError:
            raise Denied("invalid tool arguments") from None
        normalized = arguments.model_dump(mode="json")
        tool = tools[name]
        if tool.selector and normalized.get(tool.selector) in tool.write_operations:
            if f'{name}:{normalized[tool.selector]}' not in getattr(state, 'enabled_write_tools', ()):
                raise Denied('operation not permitted')
        params["arguments"] = normalized
    else:
        raise Denied("method not permitted")
    return method


def filter_list(message, tools: Mapping[str, Tool], state: State):
    if not isinstance(message, dict):
        raise ValueError("invalid list response")
    result = message.get("result")
    if isinstance(result, dict) and "tools" in result:
        if not isinstance(result["tools"], list):
            raise ValueError("invalid tools response")
        result["tools"] = [{**tool, "inputSchema": tools[tool["name"]].arguments.model_json_schema()}
                           for tool in result["tools"] if isinstance(tool, dict)
                           and isinstance(tool.get("name"), str) and enabled(tool["name"], tools, state)]
    # Also applies to resumed SSE replies: no unsupported capabilities or
    # listChanged promise may escape the method allowlist at the boundary.
    if isinstance(result, dict) and "capabilities" in result:
        result["capabilities"] = {"tools": {}}
    return message
