"""New fixed native SDK HTTP launcher; no legacy shared wrapper/UI imported."""
import argparse

import session_idle
from hermes_mcp_server.server import mcp

# HM-04 (multi-profile plan 5.4): --port is the child's loopback port. Without it 3000, the default profile's child,
# started as before (no option); an extra profile's child gets its own. Positional arguments are ignored, as this
# launcher always ignored its arguments; an unknown option (a mistyped --port) is refused, never read as 3000.
parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
parser.add_argument('--port', type=int, default=3000)
args, extra = parser.parse_known_args()
if any(value.startswith('-') for value in extra):
    parser.error('unrecognized option')
if not 1 <= args.port <= 65535:
    parser.error('port must be between 1 and 65535')

session_idle.install()  # 0.1.8 (GATEWAY-3): before mcp.run builds the session manager

# 0.4.0 (mcp 2.3.0): MCPServer takes the transport settings in run() (mcp 1.x's FastMCP read mcp.settings); the
# vendored server.py already keeps the 1.x error text of every tool (tool_error_text.keep_error_text).
mcp.run(transport='streamable-http', host='127.0.0.1', port=args.port, streamable_http_path='/mcp')
