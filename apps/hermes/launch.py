"""New fixed native SDK HTTP launcher; no legacy shared wrapper/UI imported."""
import session_idle
from hermes_mcp_server.server import mcp

session_idle.install()  # 0.1.8 (GATEWAY-3): before mcp.run builds the session manager

# 0.4.0 (mcp 2.3.0): MCPServer takes the transport settings in run() (mcp 1.x's FastMCP read mcp.settings); the
# vendored server.py already keeps the 1.x error text of every tool (tool_error_text.keep_error_text).
mcp.run(transport='streamable-http', host='127.0.0.1', port=3000, streamable_http_path='/mcp')
