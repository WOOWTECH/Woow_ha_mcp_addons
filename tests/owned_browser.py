"""Parent-owned, inherited Unix socket challenge broker for Chromium/Node fetch."""
import asyncio
from contextlib import asynccontextmanager
import json
import secrets
import socket
from urllib.parse import urlsplit

from batch2_owned_port import OwnershipError
from owned_executable import self_listener, live


@asynccontextmanager
async def browser_proofs(runner, control_port):
    parent, child = socket.socketpair()
    parent.setblocking(False)
    reader, writer = await asyncio.open_connection(sock=parent)
    control_proof = self_listener(control_port)
    assert control_proof is not None
    instance = secrets.token_hex(32)
    handle = {'process': None}
    async def serve():
        try:
            while True:
                line = await reader.readline()
                if not line:
                    return
                if len(line) > 4096:
                    raise OwnershipError('oversize browser proof challenge')
                request = json.loads(line)
                assert set(request) == {'instance', 'nonce', 'url'}
                assert request['instance'] == instance and len(request['nonce']) == 64
                assert handle['process'] is not None and live(handle['process'])
                url = urlsplit(request['url'])
                if (url.scheme, url.hostname, url.port) == ('http', '127.0.0.1', control_port) and not url.username and not url.password:
                    assert self_listener(control_port) == control_proof
                    proof = {'proof': control_proof, 'generation': 1}
                else:
                    assert url.port in runner.config['public_ports']
                    proof = await runner.guard_url(request['url'])
                writer.write(json.dumps({'nonce': request['nonce'], 'instance': instance,
                                         'proof': proof['proof'], 'generation': proof['generation']}).encode() + b'\n')
                await writer.drain()
        finally:
            writer.close()
    task = asyncio.create_task(serve())
    try:
        yield child.fileno(), instance, handle
    finally:
        child.close()
        task.cancel()
        results = await asyncio.gather(task, return_exceptions=True)
        writer.close()
        await writer.wait_closed()
        if isinstance(results[0], Exception):
            raise results[0]
