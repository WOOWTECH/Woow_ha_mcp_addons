"""New fixed native SDK HTTP launcher for the vendored real tool handlers."""
from opendesign_mcp_server.od_mcp_server import mcp, _get_client
from bounded_tools import BoundedTools

mcp.settings.host = '127.0.0.1'
mcp.settings.port = 3000
mcp.settings.streamable_http_path = '/mcp'
# Initialize once before workers start, avoiding the upstream lazy-client race.
client = _get_client()
workers = BoundedTools(mcp, capacity=4)
try:
    mcp.run(transport='streamable-http')
finally:
    workers.close()
    client.close()
