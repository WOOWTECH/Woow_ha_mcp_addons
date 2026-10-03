"""New fixed native SDK HTTP launcher; no legacy shared wrapper/UI imported."""
from hermes_mcp_server.server import mcp

mcp.settings.host = '127.0.0.1'
mcp.settings.port = 3000
mcp.settings.streamable_http_path = '/mcp'
mcp.run(transport='streamable-http')
