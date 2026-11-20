"""The EMQX client uses backend_policy's pool, not the discarded client limits."""
import os
from pathlib import Path
import subprocess


def test_emqx_lifespan_uses_bounded_pool():
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=f'{root}/apps/emqx/vendor:{root}/apps/runtime',
               EMQX_MCP_BASE_URL='http://127.0.0.1:18083',
               EMQX_MCP_API_KEY='DUMMY', EMQX_MCP_API_SECRET='DUMMY')
    script = '''
import asyncio
from emqx_mcp_server.lifespan import make_client

async def main():
    client = make_client()
    try:
        pool = client._transport._pool
        assert pool._max_connections == 4
        assert pool._max_keepalive_connections == 0
    finally:
        await client.aclose()
    assert client.is_closed

asyncio.run(main())
'''
    subprocess.run([str(root / 'apps/emqx/.venv/bin/python'), '-c', script], env=env, check=True)
