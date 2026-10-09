"""New fixed native SDK HTTP launcher; no legacy shared wrapper/UI imported."""
import session_idle
from hermes_mcp_server.server import mcp

session_idle.install()  # 0.1.8 (GATEWAY-3): before mcp.run builds the session manager

mcp.settings.host = '127.0.0.1'
mcp.settings.port = 3000
mcp.settings.streamable_http_path = '/mcp'
mcp.run(transport='streamable-http')
