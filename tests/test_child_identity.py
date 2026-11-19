import os
import socket
from types import SimpleNamespace

import httpx
import pytest

from mcp_admin_core import child_identity


def test_real_listener_and_foreign_process():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert child_identity.inspect_listener(os.getpid(), port) == 'owned'
        # PID 1 is not the owner; if procfs denies access, that must not be called a mismatch.
        assert child_identity.inspect_listener(1, port) in ('mismatch', 'unavailable')
    assert child_identity.inspect_listener(os.getpid(), port) == 'absent'


@pytest.mark.asyncio
@pytest.mark.parametrize('result,forwarded', [('owned', True), ('unavailable', True),
                                               ('mismatch', False), ('absent', False)])
async def test_transport_checks_every_request(monkeypatch, result, forwarded, caplog):
    supervisor = SimpleNamespace(process=SimpleNamespace(pid=123), starts=1, status='running')
    guard = child_identity.ListenerGuard(supervisor, 12345, limits=httpx.Limits())
    sent = []
    async def send(request):
        sent.append(request)
        return httpx.Response(200, request=request)
    monkeypatch.setattr(guard.inner, 'handle_async_request', send)
    monkeypatch.setattr(child_identity, 'inspect_listener', lambda pid, port: result)
    request = httpx.Request('POST', 'http://127.0.0.1:12345/mcp', headers={'Authorization': 'Bearer secret'})
    if forwarded:
        await guard.handle_async_request(request)
        await guard.handle_async_request(request)
        assert len(sent) == 2
    else:
        with pytest.raises(httpx.ConnectError):
            await guard.handle_async_request(request)
        assert not sent
    assert guard.status == result
    assert 'secret' not in caplog.text
    if result == 'unavailable':
        assert caplog.text.count('identity unavailable') == 1
    await guard.aclose()


@pytest.mark.asyncio
async def test_replacement_during_check_is_not_forwarded(monkeypatch):
    supervisor = SimpleNamespace(process=SimpleNamespace(pid=123), starts=1, status='running')
    guard = child_identity.ListenerGuard(supervisor, 12345, limits=httpx.Limits())
    def inspect(pid, port):
        supervisor.starts += 1
        return 'owned'
    monkeypatch.setattr(child_identity, 'inspect_listener', inspect)
    with pytest.raises(httpx.ConnectError, match='changed'):
        await guard.handle_async_request(httpx.Request('GET', 'http://127.0.0.1:12345/mcp'))
    await guard.aclose()



@pytest.mark.asyncio
async def test_actual_http_listener_is_checked_before_request(monkeypatch):
    import asyncio

    received = []
    async def serve(reader, writer):
        received.append(await reader.readuntil(b'\r\n\r\n'))
        writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    server = await asyncio.start_server(serve, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    supervisor = SimpleNamespace(process=SimpleNamespace(pid=os.getpid()), starts=1, status='running')
    guard = child_identity.ListenerGuard(supervisor, port, limits=httpx.Limits())
    try:
        async with httpx.AsyncClient(transport=guard) as client:
            response = await client.get(f'http://127.0.0.1:{port}/mcp')
            assert response.status_code == 200
            assert guard.status == 'owned'
            monkeypatch.setattr(child_identity, 'inspect_listener', lambda pid, port: 'mismatch')
            with pytest.raises(httpx.ConnectError):
                await client.get(f'http://127.0.0.1:{port}/mcp', headers={'Authorization': 'Bearer secret'})
            assert len(received) == 1
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_startup_probe_reports_unavailable_without_a_request(monkeypatch, caplog):
    supervisor = SimpleNamespace(process=SimpleNamespace(pid=123), starts=1, status='running')
    guard = child_identity.ListenerGuard(supervisor, 12345, limits=httpx.Limits())
    def denied(path):
        raise PermissionError('denied')
    monkeypatch.setattr(child_identity.os, 'listdir', denied)
    await guard.probe(123)
    await guard.probe(123)
    assert guard.status == 'unavailable'
    assert caplog.text.count('identity unavailable') == 1
    await guard.aclose()


def test_multiple_listeners_must_all_be_owned(monkeypatch):
    import io

    def table(path, **kwargs):
        rows = ('header\n 0: 00000000:3039 00000000:0000 0A 0:0 0:0 0 0 0 111\n'
                if path.endswith('/tcp') else
                'header\n 0: 00000000000000000000000000000000:3039 00000000:0000 0A 0:0 0:0 0 0 0 222\n')
        return io.StringIO(rows)
    monkeypatch.setattr(child_identity, 'open', table, raising=False)
    monkeypatch.setattr(child_identity.os, 'listdir', lambda _: ['3'])
    monkeypatch.setattr(child_identity.os, 'readlink', lambda _: 'socket:[111]')
    assert child_identity.inspect_listener(999, 12345) == 'mismatch'
    monkeypatch.setattr(child_identity.os, 'listdir', lambda _: ['3', '4'])
    monkeypatch.setattr(child_identity.os, 'readlink', lambda path: 'socket:[111]' if path.endswith('/3') else 'socket:[222]')
    assert child_identity.inspect_listener(999, 12345) == 'owned'
