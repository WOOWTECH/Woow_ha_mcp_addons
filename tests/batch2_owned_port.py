"""Linux-only B1 test seam; no production port or lifecycle changes.

The reservation closes immediately before spawn (the stock CLIs cannot inherit
it). A competing bind therefore FAILS ownership verification, never triggers an
HTTP readiness probe. Only the Supervisor's own live PID/fds are inspected.
"""
import asyncio
from dataclasses import replace
from pathlib import Path
import socket


class OwnershipError(RuntimeError):
    pass


def reserve_port():
    reservation = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        reservation.bind(('127.0.0.1', 0))
        if reservation.getsockname()[1] == 3000:
            raise OwnershipError('production port must not be used')
        return reservation
    except BaseException:
        reservation.close()
        raise


def private_spec(spec, product, port):
    """Replace ONLY the exact port in the actual fixed production ChildSpec."""
    assert 0 < port <= 65535 and port != 3000
    if product == 'n8n':
        assert spec.env['PORT'] == '3000' and '--port' not in spec.argv
        return replace(spec, env={**spec.env, 'PORT': str(port)})
    assert product in ('odoo', 'odoo-manage')
    assert spec.argv.count('--port') == 1
    index = spec.argv.index('--port') + 1
    assert spec.argv[index] == '3000'
    argv = list(spec.argv)
    argv[index] = str(port)
    return replace(spec, argv=tuple(argv))


def owned_listener(supervisor, port):
    """Return (PID, inode), None while starting; reject any unowned listener."""
    if port == 3000:
        raise OwnershipError('production port must not be inspected')
    process = supervisor.process
    if process is None or process.returncode is not None:
        if supervisor.status == 'failed' or (process is not None and process.returncode is not None):
            raise OwnershipError('owned child exited before listener verification')
        return None
    try:
        # Read the kernel table, not other PIDs. Retain only this private port.
        listeners = [row.split() for row in Path('/proc/net/tcp').read_text().splitlines()[1:]
                     if row.split()[3] == '0A' and int(row.split()[1].split(':')[1], 16) == port]
        if not listeners:
            return None
        if len(listeners) != 1 or listeners[0][1] != f'0100007F:{port:04X}':
            raise OwnershipError('private port is not an exclusive loopback listener')
        inode = listeners[0][9]
        owned = False
        for fd in Path(f'/proc/{process.pid}/fd').iterdir():
            try:
                if str(fd.readlink()) == f'socket:[{inode}]':
                    owned = True
                    break
            except FileNotFoundError:  # another fd may close during enumeration
                continue
        if not owned:
            raise OwnershipError('private listener is not owned by spawned child')
    except OSError as exc:
        raise OwnershipError('cannot prove owned child listener') from exc
    if supervisor.process is not process or process.returncode is not None:
        raise OwnershipError('owned child changed during verification')
    return process.pid, inode


async def wait_owned_listener(supervisor, port, *, timeout=25):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        proof = owned_listener(supervisor, port)
        if proof is not None:
            return proof
        if supervisor.task is not None and supervisor.task.done():
            raise OwnershipError('owned child stopped before listener verification')
        if asyncio.get_running_loop().time() >= deadline:
            raise OwnershipError('owned child listener verification timed out')
        await asyncio.sleep(.02)


def request_guard(supervisor, port, proof):
    """Recheck ownership and exact destination before EVERY child HTTP send."""
    async def guard(request):
        if (request.url.scheme, request.url.host, request.url.port, request.url.path) != (
                'http', '127.0.0.1', port, '/mcp'):
            raise OwnershipError('unexpected child destination')
        if owned_listener(supervisor, port) != proof:
            raise OwnershipError('owned child listener proof no longer valid')
    return guard
