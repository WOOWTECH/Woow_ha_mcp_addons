"""New fixed native SDK HTTP launcher for the vendored real tool handlers."""
from opendesign_mcp_server.od_mcp_server import mcp, _get_client
from bounded_tools import BoundedTools
import session_idle

# 0.2.0: the vendored client uses upstream's 60 s read timeout again (connect 5 s), so GET /api/agents (about 8 s on a
# small HA box, 0.1.1 HA test) needs no per-path override; every call stays within the gateway's 120 s stream lifetime.

if __name__ == '__main__':
    session_idle.install()  # 0.1.8 (GATEWAY-3): before mcp.run builds the session manager
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
