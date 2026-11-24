"""LiteLLM's actual pinned transport has 50 tool slots and an independent probe."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_real_pool_saturation_and_independent_probe():
    script = r'''
import asyncio
import json
import os

async def main():
    active = 0
    peak = 0
    release = asyncio.Event()
    async def serve(reader, writer):
        nonlocal active, peak
        try:
            request = await reader.readuntil(b'\r\n\r\n')
            if b'GET /hold ' in request:
                active += 1
                peak = max(peak, active)
                await release.wait()
                active -= 1
            body = b'{"data":[]}'
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: ' + str(len(body)).encode() + b'\r\nConnection: close\r\n\r\n' + body)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
    server = await asyncio.start_server(serve, '127.0.0.1', 0)
    os.environ['LITELLM_MCP_BASE_URL'] = 'http://127.0.0.1:' + str(server.sockets[0].getsockname()[1])
    os.environ['LITELLM_MCP_MASTER_KEY'] = 'DUMMY-test-key'
    from woow_litellm_mcp_server.lifespan import build_client
    async with server, build_client() as tools:
        tasks = [asyncio.create_task(tools.get('/hold')) for _ in range(51)]
        try:
            async with asyncio.timeout(20):
                while active < 50:
                    await asyncio.sleep(.01)
            await asyncio.sleep(.2)
            assert active == peak == 50 and not any(t.done() for t in tasks)
            async with build_client() as probe:
                response = await asyncio.wait_for(probe.get('/v1/models'), 3)
                assert response.json() == {'data': []}
            assert active == 50
        finally:
            release.set()
            await asyncio.gather(*tasks)
        assert peak == 50
    print('ok')
asyncio.run(main())
'''
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(ROOT / 'apps/runtime'), str(ROOT / 'apps/litellm/vendor'))))
    result = subprocess.run([str(ROOT / 'apps/litellm/.venv/bin/python'), '-c', script], env=env,
                            capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'ok'


def test_resolver_wait_is_bounded_and_other_clients_still_fail_fast():
    script = r'''
import asyncio
import socket
import threading
from backend_policy import async_client
import backend_policy

release = threading.Event()
entered = 0
lock = threading.Lock()
def slow(host, port):
    global entered
    with lock: entered += 1
    release.wait(10)
    return [(socket.AF_INET, ('127.0.0.1', port))]
backend_policy.checked_answers = slow
async def main():
    async with async_client(base_url='http://example.invalid', timeout=.15,
                            max_backend_connections=50, wait_for_resolver=True) as litellm:
        tasks = [asyncio.create_task(litellm.get('/')) for _ in range(4)]
        try:
            async with asyncio.timeout(2):
                while entered != 4: await asyncio.sleep(.01)
            async with async_client(base_url='http://example.invalid', timeout=.15) as other:
                try: await other.get('/')
                except backend_policy.BackendBusy: pass
                else: raise AssertionError('default resolver must fail fast')
            try: await litellm.get('/')
            except Exception as exc:
                assert 'BACKEND_TIMEOUT' in str(exc), repr(exc)
            else: raise AssertionError('waiting resolver must respect deadline')
            assert entered == 4
        finally:
            release.set()
            await asyncio.gather(*tasks, return_exceptions=True)
    print('ok')
asyncio.run(main())
'''
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'apps/runtime'))
    result = subprocess.run([str(ROOT / 'apps/litellm/.venv/bin/python'), '-c', script], env=env,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'ok'
