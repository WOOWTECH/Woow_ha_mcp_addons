"""HA Headscale child: one fixed origin, one saved state, loopback MCP only."""
import argparse
import os


def main(argv=None):
    parser = argparse.ArgumentParser(description="Headscale MCP child")
    parser.add_argument("--host", choices=("127.0.0.1",), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    os.environ.setdefault("FASTMCP_CHECK_FOR_UPDATES", "off")
    os.environ.setdefault("FASTMCP_SHOW_SERVER_BANNER", "false")
    from headscale_mcp_server.log_redaction import install, set_secrets
    install()
    key = os.environ.get("HEADSCALE_MCP_API_KEY", "")
    set_secrets(key)

    import session_idle
    session_idle.install()  # before FastMCP creates its session manager
    from headscale_mcp_server.client import HeadscaleClient
    from headscale_mcp_server.server import build_server

    client = HeadscaleClient(os.environ.get("HEADSCALE_MCP_BASE_URL", ""), key)
    server = build_server(client, os.environ.get("HEADSCALE_MCP_STATE_PATH"))
    server.run(transport="streamable-http", host=args.host, port=args.port,
               path="/mcp", show_banner=False)


if __name__ == "__main__":
    main()
