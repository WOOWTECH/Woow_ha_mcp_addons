"""Best-effort procfs listener check. Same UID is not a security boundary."""
import asyncio
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)
_SOCKET = re.compile(r'socket:\[(\d+)\]')


def inspect_listener(pid, port):
    """Return owned, mismatch, absent, or unavailable; never infer ownership from a port alone.

    /proc/net is scoped to this process's network namespace. The caller and child must share it.
    A disappearing process, unreadable fd, malformed table, or unsupported procfs is unavailable.
    """
    try:
        inodes = set()
        for name in ('tcp', 'tcp6'):
            with open('/proc/net/' + name, encoding='ascii') as table:
                next(table)
                for line in table:
                    fields = line.split()
                    if len(fields) < 10:
                        raise ValueError('invalid tcp table')
                    address, state = fields[1], fields[3]
                    if state == '0A' and int(address.rsplit(':', 1)[1], 16) == port:
                        inodes.add(fields[9])
        if not inodes:
            return 'absent'
        owned = set()
        path = f'/proc/{pid}/fd'
        for fd in os.listdir(path):
            try:
                target = os.readlink(f'{path}/{fd}')
            except FileNotFoundError:  # an unrelated descriptor closed during enumeration
                continue
            found = _SOCKET.fullmatch(target)
            if found:
                owned.add(found.group(1))
        # All listeners on this port must be owned: SO_REUSEPORT may create multiple listeners.
        return 'owned' if inodes <= owned else 'mismatch'
    except (OSError, ValueError, IndexError, StopIteration, UnicodeError):
        return 'unavailable'


class ListenerGuard(httpx.AsyncBaseTransport):
    """Check all requests, including probes and session cleanup, before the pooled transport."""
    def __init__(self, process, port, *, limits):
        self.process, self.port = process, port
        self.inner = httpx.AsyncHTTPTransport(trust_env=False, limits=limits)
        self.status = 'unknown'
        self.warned = False

    def _set_unavailable(self):
        self.status = 'unavailable'
        if not self.warned:
            self.warned = True
            logger.warning('child listener identity unavailable; continuing with bearer protection')

    async def probe(self, pid):
        """Probe after exec even if no request or listener exists yet."""
        def check():
            try:
                for table in ('tcp', 'tcp6'):
                    with open('/proc/net/' + table, encoding='ascii') as stream:
                        next(stream)
                directory = f'/proc/{pid}/fd'
                for fd in os.listdir(directory):
                    try:
                        os.readlink(f'{directory}/{fd}')
                    except FileNotFoundError:
                        continue
                return True
            except (OSError, StopIteration, UnicodeError):
                return False
        if not await asyncio.to_thread(check):
            self._set_unavailable()

    async def handle_async_request(self, request):
        process = self.process.process
        pid = getattr(process, 'pid', None)
        generation = self.process.starts
        if pid is None or self.process.status != 'running':
            raise httpx.ConnectError('child not running', request=request)
        result = await asyncio.to_thread(inspect_listener, pid, self.port)
        if process is not self.process.process or generation != self.process.starts or self.process.status != 'running':
            raise httpx.ConnectError('child changed', request=request)
        self.status = result
        if result == 'unavailable':
            self._set_unavailable()
        if result in ('mismatch', 'absent'):
            raise httpx.ConnectError('child listener identity ' + result, request=request)
        return await self.inner.handle_async_request(request)

    async def aclose(self):
        await self.inner.aclose()
