"""Request-scoped shared-token leases; no child restart or persisted schema change."""
from __future__ import annotations

import asyncio
import hmac
from collections.abc import Awaitable, Callable

import anyio
from starlette.requests import ClientDisconnect

from .config import ConfigError


class AccessChanged(Exception):
    """The authenticated credential no longer authorizes this request."""


def masked_token(token):
    """PaaS-compatible display mask for the validated 43-character HA token."""
    return token[:4] + '*' * 20 + token[-4:] if token else ''


class TokenAccess:
    def __init__(self, store):
        self.store = store
        self.changed = asyncio.Event()

    def committed(self):
        """Publish only AFTER the token mutation has durably committed."""
        previous, self.changed = self.changed, asyncio.Event()
        previous.set()

    def lease(self, token):
        return TokenLease(self, token, self.changed)


class TokenLease:
    def __init__(self, access, token, changed):
        self.access, self.token, self.changed = access, token, changed

    def check(self):
        try:
            current = self.access.store.load().token
            valid = not self.changed.is_set() and current is not None and hmac.compare_digest(current, self.token)
        except ConfigError:
            valid = False
        if not valid:
            raise AccessChanged()

    async def invalidated(self, checked=False):
        while True:
            if not checked:
                try:
                    self.check()
                except AccessChanged:
                    return
            checked = False
            # Keep fail-closed detection for damaged/replaced state outside the admin API.
            try:
                await asyncio.wait_for(self.changed.wait(), .2)
            except TimeoutError:
                continue

    async def run(self, operation: Callable[[], Awaitable], *, checked=False):
        """Cancel and join pending I/O; its caller still owns acquired resources.

        HM-30 D3 (contract 6): checked, the caller had this lease checked as its previous operation ended (the gateway:
        the check after the child's headers or after the previous piece of a reply it read), so the token is not
        checked again before the operation starts, and the watcher's first look comes after its first wait (0.2 s).
        Whatever changed since still stops the operation before its result is used: a token changed through the admin
        API sets the lease's event, which ends that wait at once, and any other change (a damaged or replaced state) is
        caught by the check after the operation, which stays. Each check reads the state file (store.load: five system
        calls and a parse), and the gateway reads a reply in pieces of 64 KiB. Left out, as before."""
        if not checked:
            self.check()
        work = asyncio.create_task(operation())
        changed = asyncio.create_task(self.invalidated(checked))
        try:
            await asyncio.wait((work, changed), return_when=asyncio.FIRST_COMPLETED)
            self.check()
            return await work
        finally:
            for task in (work, changed):
                if not task.done():
                    task.cancel()
            # A direct caller cancellation must not detach I/O or its cleanup.
            joined = asyncio.gather(work, changed, return_exceptions=True)
            cancelled = False
            with anyio.CancelScope(shield=True):
                while not joined.done():
                    try:
                        await asyncio.shield(joined)
                    except asyncio.CancelledError:
                        cancelled = True
            if cancelled:
                raise asyncio.CancelledError


class Delivery:
    """HM-14: how far a response got: its start was attempted (started), the server took its headers (accepted: the
    send returned; a send cancelled while the server waited for the client to read took nothing), the last body the
    server took (last_body: the very object sent) and whether that was the response's last message (completed)."""
    __slots__ = ('started', 'accepted', 'completed', 'last_body')

    def __init__(self):
        self.started = self.accepted = self.completed = False
        self.last_body = None

    async def forward(self, send, message):
        await send(message)
        if message['type'] == 'http.response.start':
            self.accepted = True
        elif message['type'] == 'http.response.body':
            self.last_body = message.get('body', b'')
            if not message.get('more_body', False):
                self.completed = True


class LeasedResponse:
    """Guard the whole response and each actual ASGI send, including backpressure.

    HM-14 (multi-profile contract 2.5): ending, given for a switched-on product only (gateway.make_apps: gateway.Ending),
    ends a response whose token changed after its start was attempted: ending(scope, receive, send, delivery) sends the
    gateway's own ending and returns instead of the ClientDisconnect below (which the server logs with a traceback, and
    answers 500 when the headers had not gone out). Left out, nothing changes."""
    def __init__(self, response, lease, refused, ending=None):
        self.response, self.lease, self.refused, self.ending = response, lease, refused, ending

    async def __call__(self, scope, receive, send):
        delivery = Delivery()

        async def guarded_send(message):
            self.lease.check()
            if message['type'] == 'http.response.start':
                delivery.started = True
            await self.lease.run(lambda: delivery.forward(send, message))

        try:
            await self.lease.run(lambda: self.response(scope, receive, guarded_send))
        except AccessChanged:
            if delivery.started and self.ending is not None:
                await self.ending(scope, receive, send, delivery)
                return
            if delivery.started:
                # An already-started HTTP response cannot be changed into a 401/404.
                raise ClientDisconnect() from None
            raise self.refused() from None
        finally:
            # Revocation may precede even the wrapped response's first instruction.
            owner = getattr(self.response, "owner", None)
            if owner is not None:
                await owner.close()
