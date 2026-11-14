"""Reusable Linux/IPv4 PRIVATE test endpoint; no production seam or defaults.

Reservation release/bind and proof/send are NOT atomic FD activation. Reuse B1's
own-live-PID/fd/inode proof read-only. No foreign PID lookup, environ or memory.

HM-01: the port the production spec carries is a parameter (production_port: 3000, the default profile's child; an
extra profile's child is on 18000-18099 in the multi-profile plan), and the shared client (Endpoint.client) sends the
child bearer (Endpoint.bearer) on every request that names no Authorization itself, so that direct tests keep working
once HM-06 makes every child check it.
"""
from dataclasses import replace
from pathlib import Path
import secrets

import httpx

from batch2_owned_port import OwnershipError, owned_listener, reserve_port, wait_owned_listener
from mcp_admin_core.lifecycle import Supervisor
from owned_network import PRODUCTION_PORT, PROFILE_CHILD_PORTS, forbidden_port, guarded_env

HERE = Path(__file__).resolve().parent
# HM-06 (multi-profile plan 8.3): the Python children's bearer; n8n's child has always checked AUTH_TOKEN.
CHILD_TOKEN_ENV = 'WOOW_MCP_CHILD_TOKEN'


def production_port_valid(port):
    return type(port) is int and (port == PRODUCTION_PORT or port in PROFILE_CHILD_PORTS)


def private_spec(spec, product, port, *, production_port=PRODUCTION_PORT):
    """Replace ONLY production_port in the actual production ChildSpec with the private port."""
    assert 0 < port <= 65535 and not forbidden_port(port)
    assert production_port_valid(production_port)
    if spec is None:
        return None
    expected = str(production_port)
    if product == 'n8n':
        assert spec.env['PORT'] == expected and '--port' not in spec.argv
        return replace(spec, env={**spec.env, 'PORT': str(port)})
    if product in ('odoo', 'odoo-manage', 'emqx', 'litellm', 'nextcloud', 'headscale'):
        assert spec.argv.count('--port') == 1
        index = spec.argv.index('--port') + 1
        assert spec.argv[index] == expected
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
    # The launcher passes its port to run() (owned_child checks it); the default keeps the exact former argv.
    moved = () if production_port == PRODUCTION_PORT else ('--production-port=' + expected,)
    return replace(spec, argv=(spec.argv[0], str(HERE / 'owned_child.py'), product,
                               str(port), *moved, *spec.argv[1:]))


def spec_bearer(spec, product):
    """The bearer this spec's child checks: HM-06's WOOW_MCP_CHILD_TOKEN, n8n's AUTH_TOKEN; None without one."""
    if spec is None:
        return None
    return spec.env.get(CHILD_TOKEN_ENV) or (spec.env.get('AUTH_TOKEN') if product == 'n8n' else None)


class ChildUnavailable(OwnershipError, httpx.ConnectError):
    """Fail-before-send ownership denial during a legitimate child transition.

    Also a transport failure so the REAL health monitor handles a stopped child
    just as it handles a refused connection. Bad destinations/unowned listeners
    remain hard OwnershipErrors; no request is dispatched on either failure.
    """


class Endpoint:
    def __init__(self, product=None, *, port=None, production_port=PRODUCTION_PORT):
        if not production_port_valid(production_port):
            raise OwnershipError('invalid production port')
        self.product = product
        self.production_port = production_port
        self.reservation = self._reserve() if port is None else None
        self.port = self.reservation.getsockname()[1] if self.reservation else port
        if not 0 < self.port <= 65535 or forbidden_port(self.port):
            self.close()
            raise OwnershipError('invalid private port')
        self.url = f'http://127.0.0.1:{self.port}/mcp'
        self.manager = None
        self.proof = None
        self.generation = 0
        self.dispatches = 0
        self._synthetic_bearer = None

    @staticmethod
    def _reserve():
        for _ in range(16):  # an ephemeral port is never 3000 or 18000-18099 unless the kernel range is unusual
            reservation = reserve_port()
            if not forbidden_port(reservation.getsockname()[1]):
                return reservation
            reservation.close()
        raise OwnershipError('no private port outside the production ports')

    def prepare(self, spec):
        value = private_spec(spec, self.product, self.port, production_port=self.production_port)
        return replace(value, env=guarded_env(value.env)) if value is not None else None

    def bearer(self):
        """The child bearer the shared client sends: the one the supervised spec's child checks now (n8n AUTH_TOKEN;
        the Python children's WOOW_MCP_CHILD_TOKEN from HM-06; read at each send, so it follows a restart with a new
        spec), else one synthetic value for this endpoint, which a child before HM-06 ignores."""
        found = spec_bearer(self.manager.spec, self.product) if self.manager is not None else None
        if found is not None:
            return found
        if self._synthetic_bearer is None:
            self._synthetic_bearer = secrets.token_urlsafe(32)
        return self._synthetic_bearer

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

    def client(self, *, bearer=True, **kwargs):
        """The shared client of this child: the ownership guard first, then (by default) the child bearer on every
        request that names no Authorization itself. The add-on's own requests always name the child token, so they are
        sent as before; a test's direct request gets bearer() (bearer=False: none; a str: that value)."""
        assert 'transport' not in kwargs and 'event_hooks' not in kwargs
        if not (isinstance(bearer, bool) or isinstance(bearer, str) and bearer):
            raise TypeError('bearer is True, False or the value to send')
        client = self.attach(httpx.AsyncClient(trust_env=False, follow_redirects=False, **kwargs))
        if bearer:
            async def authorize(request):
                if 'authorization' not in request.headers:
                    request.headers['Authorization'] = 'Bearer ' + (self.bearer() if bearer is True else bearer)
            client.event_hooks['request'].insert(client.event_hooks['request'].index(self.guard) + 1, authorize)
        return client


def forbidden_transport():
    def forbidden(request):
        raise OwnershipError('admin-only fixture attempted child I/O')
    return httpx.MockTransport(forbidden)
