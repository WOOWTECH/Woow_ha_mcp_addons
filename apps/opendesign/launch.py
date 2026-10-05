"""New fixed native SDK HTTP launcher for the vendored real tool handlers."""
import httpx
import opendesign_mcp_server.od_mcp_server as od
from opendesign_mcp_server.od_mcp_server import mcp, _get_client
from bounded_tools import BoundedTools

# GET /api/agents makes OpenDesign probe every agent CLI it knows: about 8 s on a small HA box (0.1.1 HA test),
# past the upstream client's fixed 5 s read timeout. Only that read waits longer; connecting still gets 5 s and
# the gateway's 30 s upstream limit bounds the call. Every other request keeps the upstream behavior.
SLOW_READS = {'/api/agents': httpx.Timeout(20.0, connect=5.0)}
upstream_api_get = od._api_get


def api_get(path):
    timeout = SLOW_READS.get(path)
    if timeout is None:
        return upstream_api_get(path)
    resp = _get_client().get(path, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


od._api_get = api_get  # the vendored tools look the helper up at call time

if __name__ == '__main__':
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
