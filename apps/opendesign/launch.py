"""New fixed native SDK HTTP launcher for the vendored real tool handlers."""
import argparse

from opendesign_mcp_server.od_mcp_server import mcp, _get_client
from bounded_tools import BoundedTools
import session_idle
from tool_error_text import keep_error_text

# 0.2.0: the vendored client uses upstream's 60 s read timeout again (connect 5 s), so GET /api/agents (about 8 s on a
# small HA box, 0.1.1 HA test) needs no per-path override; every call stays within the gateway's 120 s stream lifetime.


def child_port():
    """HM-04 (multi-profile plan 5.4): --port is the child's loopback port. Without it 3000, the default profile's
    child, started as before (no option); an extra profile's child gets its own. Positional arguments are ignored, as
    this launcher always ignored its arguments; an unknown option (a mistyped --port) is refused, never read as 3000."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument('--port', type=int, default=3000)
    args, extra = parser.parse_known_args()
    if any(value.startswith('-') for value in extra):
        parser.error('unrecognized option')
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    return args.port


if __name__ == '__main__':
    port = child_port()
    session_idle.install()  # 0.1.8 (GATEWAY-3): before mcp.run builds the session manager
    # Initialize once before workers start, avoiding the upstream lazy-client race.
    client = _get_client()
    workers = BoundedTools(mcp, capacity=4)
    # 0.4.0 (mcp 2.3.0): mcp 2 hides an exception's text unless it is a ToolError; keep 1.x's text (backend errors,
    # BACKEND_BUSY) for every tool. Last, around the bounded workers.
    keep_error_text(mcp)
    try:
        # 0.4.0: MCPServer takes the transport settings in run() (mcp 1.x's FastMCP read mcp.settings).
        mcp.run(transport='streamable-http', host='127.0.0.1', port=port, streamable_http_path='/mcp')
    finally:
        workers.close()
        client.close()
