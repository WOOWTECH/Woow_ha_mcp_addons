"""EMQX MCP server entry point."""

from __future__ import annotations

import json
import os

from fastmcp import FastMCP

from .gating import ToolGate
from .lifespan import emqx_lifespan
from .settings import settings
from .tools import (
    clients,
    cluster,
    diagnostics,
    integration,
    messaging,
    security,
    topics,
)

INSTRUCTIONS = """\
Tools for inspecting and operating an EMQX MQTT broker through its REST API v5.

Read-only tools are safe to call freely. Tools whose description starts with
[DESTRUCTIVE] disconnect clients, delete credentials, or drop stored state —
confirm with the user before calling them.
"""

_MODULES = (cluster, clients, topics, messaging, security, diagnostics, integration)


def gate_from_settings() -> ToolGate:
    """Build the gate from EMQX_MCP_* environment variables."""
    categories = [c.strip() for c in settings.disabled_categories.split(",") if c.strip()]
    tools = [t.strip() for t in settings.disabled_tools.split(",") if t.strip()]
    try:
        operations = json.loads(settings.disabled_operations or "{}")
    except json.JSONDecodeError:
        operations = {}
    return ToolGate(
        disabled_categories=categories,
        disabled_tools=tools,
        disabled_operations=operations,
        readonly=settings.readonly,
    )


def build_server(gate: ToolGate | None = None) -> FastMCP:
    """Assemble a server exposing exactly the tools the gate allows."""
    # Defense in depth (train A review F-1): the environment gate (READONLY, DISABLED_TOOLS) stays active in every
    # mode, with or without a state path; PolicyMiddleware below is a second, live layer on top of it, never a
    # replacement. The gateway is the first layer.
    gate = gate if gate is not None else gate_from_settings()

    mcp = FastMCP(
        name="EMQX MCP",
        instructions=INSTRUCTIONS,
        lifespan=emqx_lifespan,
        mask_error_details=True,
    )
    for module in _MODULES:
        module.register(mcp, gate)
    # Only the HA launcher supplies a profile-bound state path. Standalone
    # upstream use retains its environment gate.
    if os.environ.get("EMQX_MCP_STATE_PATH"):
        from emqx_child_policy import PolicyMiddleware
        mcp.add_middleware(PolicyMiddleware(os.environ["EMQX_MCP_STATE_PATH"], settings))
    return mcp


mcp = build_server()


def main() -> None:
    """CLI entry point.

    Defaults to stdio for desktop clients; the Admin bundle spawns this with
    `--transport http --host 127.0.0.1 --port 3000` so only its proxy can
    reach it.
    """
    import argparse

    parser = argparse.ArgumentParser(prog="emqx-mcp-server")
    parser.add_argument(
        "--transport", default="stdio", choices=["stdio", "http", "sse"]
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--path", default="/mcp/")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(
            transport=args.transport, host=args.host, port=args.port, path=args.path
        )


if __name__ == "__main__":
    main()
