"""Reusable Linux/IPv4 PRIVATE test endpoint; no production seam or defaults.

Reservation release/bind and proof/send are NOT atomic FD activation. Reuse B1's
own-live-PID/fd/inode proof read-only. No foreign PID lookup, environ or memory.
"""
from dataclasses import replace
from pathlib import Path

import httpx

from batch2_owned_port import (OwnershipError, owned_listener, reserve_port,
                              wait_owned_listener, private_spec as b1_private_spec)
from mcp_admin_core.lifecycle import Supervisor
from owned_network import guarded_env

HERE = Path(__file__).resolve().parent


def private_spec(spec, product, port):
    assert 0 < port <= 65535 and port != 3000
    if spec is None:
        return None
    if product in ('n8n', 'odoo', 'odoo-manage'):
        return b1_private_spec(spec, product, port)
    if product in ('emqx', 'litellm'):
        assert spec.argv.count('--port') == 1
        index = spec.argv.index('--port') + 1
        assert spec.argv[index] == '3000'
        argv = list(spec.argv)
        argv[index] = str(port)
        return replace(spec, argv=tuple(argv))
    assert product in ('hermes', 'opendesign')
    # The two existing instrumentation wrappers deliberately pass -c and then
    # run the genuine launcher. Outer interposition preserves their exact argv.
    if spec.argv[1] == '-c':
        assert sum(Path(arg).parts[-3:] == ('apps', product, 'launch.py') for arg in spec.argv[3:]) == 1
    else:
        assert Path(spec.argv[1]).parts[-3:] == ('apps', product, 'launch.py')
    return replace(spec, argv=(spec.argv[0], str(HERE / 'owned_child.py'), product,
                               str(port), *spec.argv[1:]))


class ChildUnavailable(OwnershipError, httpx.ConnectError):
    """Fail-before-send ownership denial during a legitimate child transition.

    Also a transport failure so the REAL health monitor handles a stopped child
    just as it handles a refused connection. Bad destinations/unowned listeners
    remain hard OwnershipErrors; no request is dispatched on either failure.
    """


class Endpoint:
    def __init__(self, product=None, *, port=None):
        self.product = product
        self.reservation = reserve_port() if port is None else None
        self.port = self.reservation.getsockname()[1] if self.reservation else port
        if not 0 < self.port <= 65535 or self.port == 3000:
            raise OwnershipError('invalid private port')
        self.url = f'http://127.0.0.1:{self.port}/mcp'
        self.manager = None
        self.proof = None
        self.generation = 0
        self.dispatches = 0

    def prepare(self, spec):
        value = private_spec(spec, self.product, self.port)
        return replace(value, env=guarded_env(value.env)) if value is not None else None

    def close(self):
        if self.reservation is not None:
            self.reservation.close()
            self.reservation = None

    def invalidate(self):
        self.proof = None

    async def refresh(self):
        if self.manager.spec is not None:
            self.proof = await wait_owned_listener(self.manager, self.port)
            self.generation += 1

    def supervisor(self, spec, *, prepared=False, **kwargs):
        assert self.manager is None
        endpoint = self
        class OwnedSupervisor(Supervisor):
            async def start(self):
                endpoint.invalidate()
                endpoint.close()
                await super().start()
                await endpoint.refresh()

            async def stop(self):
                endpoint.invalidate()  # before any signal/await
                await super().stop()

            async def restart(self, spec):
                endpoint.invalidate()
                await super().restart(spec)
                await endpoint.refresh()
        self.manager = OwnedSupervisor(spec if prepared else self.prepare(spec), retries=0, **kwargs)
        self.manager.endpoint = self
        return self.manager

    async def guard(self, request):
        if (request.url.scheme, request.url.host, request.url.port, request.url.path) != (
                'http', '127.0.0.1', self.port, '/mcp') or request.url.raw_path != b'/mcp' or request.url.username or request.url.password or request.url.fragment:
            raise OwnershipError('unexpected child destination')
        if self.proof is None or owned_listener(self.manager, self.port) != self.proof:
            raise ChildUnavailable('owned child listener proof no longer valid')
        self.dispatches += 1

    def attach(self, client):
        hooks = client.event_hooks['request']
        if self.guard not in hooks:
            hooks.insert(0, self.guard)  # before all counters/dispatch hooks
        return client

    def client(self, **kwargs):
        assert 'transport' not in kwargs and 'event_hooks' not in kwargs
        return self.attach(httpx.AsyncClient(trust_env=False, follow_redirects=False, **kwargs))


def forbidden_transport():
    def forbidden(request):
        raise OwnershipError('admin-only fixture attempted child I/O')
    return httpx.MockTransport(forbidden)
