"""Private real-main installer and fresh owner-side proof IPC.

Management stays nondumpable/UID10001. The parent authenticates the Unix peer's
kernel PID against its exact launched handle; only the owner inspects child fds.
No production route, token, environment/memory discovery, or port override flag.
"""
import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import threading
import time
from types import SimpleNamespace

from batch2_owned_port import OwnershipError, owned_listener, reserve_port
from owned_network import install, install_subprocess_guard
from owned_runtime import Endpoint


def live(process):
    return process.poll() is None if hasattr(process, 'poll') else process.returncode is None


def self_listener(port):
    owner = SimpleNamespace(process=SimpleNamespace(pid=os.getpid(), returncode=None), status='running')
    return owned_listener(owner, port)


def _read_line(sock):
    data = b''
    while not data.endswith(b'\n'):
        chunk = sock.recv(4096 - len(data))
        if not chunk:
            raise OwnershipError('proof IPC closed')
        data += chunk
        if len(data) >= 4096:
            raise OwnershipError('oversize proof IPC')
    return json.loads(data)


def serve_proofs(config, endpoint):
    """Bounded, metadata-only owner-side checks, after real management guard."""
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(config['ipc'])  # private owned directory; never unlink/reuse
    os.chmod(config['ipc'], 0o600)
    server.listen(8)
    def serve():
        while True:
            conn, _ = server.accept()
            with conn:
                conn.settimeout(2)
                try:
                    request = _read_line(conn)
                    assert set(request) == {'nonce', 'instance', 'port'}
                    assert request['instance'] == config['instance']
                    assert isinstance(request['nonce'], str) and len(request['nonce']) == 64
                    port = request['port']
                    assert port in config['public_ports'] or port == endpoint.port
                    if port == endpoint.port:
                        proof = endpoint.proof
                        if proof is not None and owned_listener(endpoint.manager, port) != proof:
                            raise OwnershipError('stale child generation')
                        generation = endpoint.generation
                    else:
                        proof = self_listener(port)
                        generation = 1
                    response = {**request, 'pid': os.getpid(), 'proof': proof, 'generation': generation}
                except Exception:
                    response = {'error': 'ownership unavailable'}
                try:
                    conn.sendall(json.dumps(response).encode() + b'\n')
                except OSError:
                    pass
    threading.Thread(target=serve, name='owned-proof-ipc', daemon=True).start()
    return server


def install_runner(module, config):
    """Bind real runner aliases BEFORE its real main (including runpy callers)."""
    install()
    install_subprocess_guard()
    endpoint = Endpoint(config['product'], port=config['child_port'])
    original_spec, original_monitor, original_apps = module.child_spec, module.HealthMonitor, module.make_apps
    def trace(operation, phase, reason=None):
        if 'trace' not in config:
            return
        manager = endpoint.manager
        event = {'operation': operation, 'phase': phase, 'time': time.monotonic(),
                 'generation': endpoint.generation, 'proof': endpoint.proof,
                 'child_state': manager.status if manager else None,
                 'child_pid': manager.process.pid if manager and manager.process else None,
                 'reason': reason}
        with open(config['trace'], 'a') as output:
            output.write(json.dumps(event)+'\n')
    def spec(*args, **kwargs):
        return endpoint.prepare(original_spec(*args, **kwargs))
    def supervisor(value, **kwargs):
        assert not kwargs
        return endpoint.supervisor(value, prepared=True)
    class Monitor(original_monitor):
        def __init__(self, store, manager, client):
            super().__init__(store, manager, endpoint.attach(client), child_url=endpoint.url)

        async def check(self):
            # Do not serialize production health and callback scheduling. An
            # invalidated child proof denies I/O as a transport failure instead.
            trace('health', 'entered')
            try:
                return await super().check()
            finally:
                trace('health', 'finished')

    def apps(store, tools, client, **kwargs):
        assert 'child_url' not in kwargs
        changed = kwargs['backend_changed']
        async def joined_change(state):
            trace('callback', 'entered')
            try:
                return await changed(state)
            except BaseException as error:
                trace('callback', 'failed', type(error).__name__)
                raise
            finally:
                trace('callback', 'finished')
        kwargs['backend_changed'] = joined_change
        return original_apps(store, tools, endpoint.attach(client), child_url=endpoint.url, **kwargs)
    module.child_spec, module.Supervisor = spec, supervisor
    module.HealthMonitor, module.make_apps = Monitor, apps
    module._owned_test_endpoint = endpoint
    module._owned_test_ipc = serve_proofs(config, endpoint)
    return endpoint


class Executable:
    """Parent-held reservations + exact launched handle; never readiness HTTP."""
    def __init__(self, directory, product, public_ports):
        self.reservation = reserve_port()
        self.config = {'product': product, 'child_port': self.reservation.getsockname()[1],
                       'public_ports': list(public_ports), 'instance': secrets.token_hex(32),
                       'ipc': str(Path(directory) / 'owned-proof.sock')}
        assert len(set(public_ports)) == len(public_ports)
        assert all(0 < p <= 65535 and p != 3000 for p in public_ports)
        assert self.config['child_port'] not in public_ports
        self.process = None
        self.public_proofs = {}
        self.dispatches = 0

    @property
    def child_url(self):
        return f"http://127.0.0.1:{self.config['child_port']}/mcp"

    def code(self, module):
        return f'from owned_executable import install_runner; install_runner({module}, {self.config!r}); '

    def release(self):
        self.reservation.close()

    def _proof(self, port):
        if self.process is None or not live(self.process):
            raise OwnershipError('owned executable is not live')
        nonce = secrets.token_hex(32)
        request = {'nonce': nonce, 'instance': self.config['instance'], 'port': port}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(2)
            conn.connect(self.config['ipc'])
            pid, uid, gid = struct.unpack('3i', conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if pid != self.process.pid:
                raise OwnershipError('proof IPC peer is not launched executable')
            conn.sendall(json.dumps(request).encode() + b'\n')
            response = _read_line(conn)
        if not live(self.process) or any(response.get(k) != v for k, v in request.items()) or response.get('pid') != self.process.pid:
            raise OwnershipError('proof IPC challenge mismatch')
        proof = response.get('proof')
        if proof is not None:
            if not (isinstance(proof, list) and len(proof) == 2 and type(proof[0]) is int and proof[0] > 0
                    and isinstance(proof[1], str) and proof[1].isascii() and proof[1].isdigit()
                    and int(proof[1]) > 0 and type(response.get('generation')) is int and response['generation'] > 0):
                raise OwnershipError('invalid listener proof')
            if port in self.config['public_ports']:
                if proof[0] != self.process.pid:
                    raise OwnershipError('public proof is not self-owned')
                previous = self.public_proofs.setdefault(port, proof)
                if previous != proof:
                    raise OwnershipError('public listener replaced')
        return response

    async def ready(self, process, *, timeout=25):
        self.process = process
        async with asyncio.timeout(timeout):
            while True:
                try:
                    proofs = [await asyncio.to_thread(self._proof, port) for port in self.config['public_ports']]
                    if all(p['proof'] is not None for p in proofs):
                        return
                except (FileNotFoundError, ConnectionRefusedError):
                    pass  # IPC not yet created; no TCP probe has occurred
                await asyncio.sleep(.02)

    async def guard(self, request):
        await self.guard_url(str(request.url))

    async def guard_url(self, url):
        from urllib.parse import urlsplit
        value = urlsplit(url)
        port = value.port
        if value.scheme != 'http' or value.hostname != '127.0.0.1' or value.username or value.password:
            raise OwnershipError('unexpected executable destination')
        if port not in self.config['public_ports']:
            if port != self.config['child_port'] or value.path != '/mcp' or value.query:
                raise OwnershipError('unexpected executable port/path')
        response = await asyncio.to_thread(self._proof, port)
        if response['proof'] is None:
            raise OwnershipError('executable listener not proved')
        self.dispatches += 1
        return response
