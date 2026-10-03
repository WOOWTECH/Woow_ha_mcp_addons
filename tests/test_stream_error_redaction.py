"""Late failures through real pinned children/gateway and owned HTTP backends."""
import asyncio
import json
import threading

import httpcore
import httpx
import pytest

from test_backend_policy_python import policy

from mcp_admin_core.lifecycle import ChildSpec
from mcp_admin_core.products import PROBES, TOOLS
import test_six_hardening
from test_six_hardening import Quiet, call, runtime, serve

CANARY = 'DUMMY-LATE-RESPONSE-SECRET'


def broken_response(handler, mode, credential):
    handler.send_response(200)
    if mode == 'chunk':
        handler.send_header('Transfer-Encoding', 'chunked')
        body = credential.encode() + b'\r\n'
    elif mode == 'disconnect':
        handler.send_header('Content-Length', '10000')
        body = credential.encode()
    else:
        body = (credential.encode() if mode == 'gzip' else
                b'\xff\xfe' + credential.encode('utf-16-le') + b'\x00' if mode == 'encoding' else
                b'{"' + credential.encode())
        handler.send_header('Content-Length', str(len(body)))
        if mode == 'gzip':
            handler.send_header('Content-Encoding', 'gzip')
    handler.end_headers()
    handler.wfile.write(body)
    handler.wfile.flush()
    handler.close_connection = True


@pytest.mark.parametrize('product,json_response', [
    ('hermes', False), ('opendesign', False), ('emqx', False),
    ('litellm', False), ('litellm', True)])
async def test_actual_child_late_response_errors(tmp_path, product, json_response):
    mode = {'value': 'chunk'}
    seen = []

    class Backend(Quiet):
        def do_GET(self):
            credential = self.headers.get('Authorization', CANARY)
            if product == 'hermes':
                assert credential == 'Bearer ' + CANARY
            seen.append(credential)
            broken_response(self, mode['value'], credential)

    with serve(Backend) as url:
        async with runtime(tmp_path, product, url, canary=CANARY,
                           json_response=json_response) as (client, headers, *_):
            name, args = PROBES[product]
            for failure in ('chunk', 'disconnect', 'gzip', 'encoding', 'json'):
                mode['value'] = failure
                before = len(seen)
                response = await client.post('/mcp', headers=headers, json=call(name, args))
                assert len(seen) > before
                # Whole raw wire payload includes content, structuredContent, notifications.
                assert CANARY not in response.text, (product, failure, response.text)
                code = 'BACKEND_STREAM_ERROR' if failure in ('chunk', 'disconnect') else 'BACKEND_INVALID_RESPONSE'
                assert code in response.text, (product, failure, response.text)
                assert len(response.content) < 4096
                assert response.headers['content-type'].startswith(
                    'application/json' if json_response else 'text/event-stream')


@pytest.mark.parametrize('phase', ['login', 'cookie'])
async def test_actual_dashboard_late_response_errors(tmp_path, phase):
    mode = {'value': 'chunk'}
    seen = []

    class Dashboard(Quiet):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert body['password'] == CANARY
            if phase == 'login':
                seen.append('login')
                return broken_response(self, mode['value'], body['password'])
            self.send_response(200)
            self.send_header('Set-Cookie', f'hermes_session_at={CANARY}')
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'{}')

        def do_GET(self):
            credential = self.headers['Cookie']
            assert CANARY in credential
            seen.append('cookie')
            broken_response(self, mode['value'], credential)

    with serve(Dashboard) as url:
        async with runtime(tmp_path, 'hermes', url, canary=CANARY) as (client, headers, *_):
            # Login does not parse JSON; malformed JSON is only meaningful for cookie GET.
            failures = ('chunk', 'disconnect', 'gzip') if phase == 'login' else ('chunk', 'disconnect', 'gzip', 'encoding', 'json')
            for failure in failures:
                mode['value'] = failure
                response = await client.post('/mcp', headers=headers,
                    json=call('hermes_inspect', {'target': 'status'}))
                assert seen and seen[-1] == phase
                assert CANARY not in response.text, (phase, failure, response.text)
                code = 'BACKEND_STREAM_ERROR' if failure in ('chunk', 'disconnect') else 'BACKEND_INVALID_RESPONSE'
                assert code in response.text, (phase, failure, response.text)
                assert len(response.content) < 4096


@pytest.mark.parametrize('kind', ['sync', 'async'])
@pytest.mark.parametrize('failure', ['chunk', 'disconnect', 'read', 'timeout', 'close', 'status-close'])
async def test_actual_httpcore_lazy_stream_and_close(monkeypatch, kind, failure):
    """Real HTTPX transport + core pool, including core (not HTTPX) close errors."""
    from httpcore._sync.connection_pool import PoolByteStream as SyncPoolStream
    from httpcore._async.connection_pool import PoolByteStream as AsyncPoolStream

    class Backend(Quiet):
        def do_GET(self):
            if failure in ('chunk', 'disconnect'):
                broken_response(self, failure, CANARY)
            else:
                self.reply({'ok': True}, 503 if failure == 'status-close' else 200)

    expected = ('BACKEND_TIMEOUT' if failure == 'timeout' else
                'BACKEND_HTTP_ERROR status=503' if failure == 'status-close' else
                'BACKEND_STREAM_ERROR')
    with serve(Backend) as url:
        if kind == 'sync':
            with policy.sync_client(base_url=url, timeout=1) as client:
                with monkeypatch.context() as patch:
                    if failure in ('read', 'timeout'):
                        def fail_read(self):
                            yield b''
                            raise (httpcore.ReadTimeout if failure == 'timeout' else httpcore.ReadError)(CANARY)
                        patch.setattr(SyncPoolStream, '__iter__', fail_read)
                    if failure in ('close', 'status-close'):
                        original = SyncPoolStream.close
                        def fail_close(self):
                            original(self)
                            raise httpcore.ReadError(CANARY)
                        patch.setattr(SyncPoolStream, 'close', fail_close)
                    for _ in range(6):
                        with pytest.raises(httpx.HTTPError) as caught:
                            with client.stream('GET', '/') as response:
                                assert response.status_code == 200  # lazy: no eager body read
                                list(response.iter_bytes())
                        assert str(caught.value) == expected
                        assert not client._transport._pool._requests
                        assert not client._transport._pool.connections
                # Broken wire cases remain broken; other cases prove same-pool reuse.
                if failure not in ('chunk', 'disconnect', 'status-close'):
                    assert client.get('/').json() == {'ok': True}
        else:
            async with policy.async_client(base_url=url, timeout=1) as client:
                with monkeypatch.context() as patch:
                    if failure in ('read', 'timeout'):
                        async def fail_read(self):
                            yield b''
                            raise (httpcore.ReadTimeout if failure == 'timeout' else httpcore.ReadError)(CANARY)
                        patch.setattr(AsyncPoolStream, '__aiter__', fail_read)
                    if failure in ('close', 'status-close'):
                        original = AsyncPoolStream.aclose
                        async def fail_close(self):
                            await original(self)
                            raise httpcore.ReadError(CANARY)
                        patch.setattr(AsyncPoolStream, 'aclose', fail_close)
                    for _ in range(6):
                        with pytest.raises(httpx.HTTPError) as caught:
                            async with client.stream('GET', '/') as response:
                                assert response.status_code == 200
                                [chunk async for chunk in response.aiter_bytes()]
                        assert str(caught.value) == expected
                        assert not client._transport._pool._requests
                        assert not client._transport._pool.connections
                if failure not in ('chunk', 'disconnect', 'status-close'):
                    assert (await client.get('/')).json() == {'ok': True}


async def test_cancel_actual_lazy_stream_releases_pool_not_resolver_ownership():
    entered, release = threading.Event(), threading.Event()

    class Slow(Quiet):
        def do_GET(self):
            if self.path == '/ok':
                return self.reply({'ok': True})
            self.send_response(200)
            self.send_header('Content-Length', '100')
            self.end_headers()
            self.wfile.flush()
            entered.set()
            release.wait(5)

    with serve(Slow) as url:
        try:
            async with policy.async_client(base_url=url, timeout=2) as client:
                async def consume():
                    async with client.stream('GET', '/') as response:
                        await response.aread()
                for _ in range(6):
                    entered.clear()
                    task = asyncio.create_task(consume())
                    assert await asyncio.to_thread(entered.wait, 2)
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await asyncio.wait_for(task, .5)
                    assert not client._transport._pool._requests
                    assert not client._transport._pool.connections
                assert (await client.get('/ok')).json() == {'ok': True}
                # Resolution is complete here: all four slots must be reusable.
                futures = [policy.resolve_future('127.0.0.1', 80) for _ in range(4)]
                assert all(f.result(1) for f in futures)
        finally:
            release.set()


@pytest.mark.parametrize('product,json_response', [
    ('hermes', False), ('opendesign', False), ('emqx', False),
    ('litellm', False), ('emqx', True), ('litellm', True)])
async def test_every_enabled_http_handler_has_safe_body_errors(tmp_path, product, json_response):
    mode = {'value': 'chunk'}
    seen = []

    class Backend(Quiet):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert body['password'] == CANARY
            self.send_response(200)
            self.send_header('Set-Cookie', f'hermes_session_at={CANARY}')
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'{}')

        def do_GET(self):
            seen.append(self.path)
            if mode['value'] == 'success':
                return self.reply({'note': CANARY, 'data': []})
            broken_response(self, mode['value'], CANARY)

        do_DELETE = do_GET

    project = {'project_id': '12345678-1234-1234-1234-123456789abc'}
    with serve(Backend) as url:
        async with runtime(tmp_path, product, url, canary=CANARY,
                           json_response=json_response) as (client, headers, store, *_):
            store.update(writes_enabled=True)  # Only owned fake OpenDesign DELETE.
            calls = []
            for name in TOOLS[product]:
                if name == 'hermes_inspect':
                    calls.extend((name, {'target': target}) for target in ('capabilities', 'status'))
                    continue
                arguments = ({'action': 'list'} if name in ('hermes_skill', 'hermes_tools') else
                             {'action': 'status'} if name == 'hermes_gateway' else
                             {'action': 'info'} if name == 'hermes_model' else
                             dict(project, file_path='test.txt') if name == 'get_file_info' else
                             project if name in ('get_project', 'list_project_files', 'delete_project') else {})
                calls.append((name, arguments))
            for failure in ('chunk', 'gzip', 'encoding', 'json'):
                mode['value'] = failure
                for name, arguments in calls:
                    before = len(seen)
                    response = await client.post('/mcp', headers=headers, json=call(name, arguments))
                    assert len(seen) > before, (product, name, response.text)
                    assert CANARY not in response.text, (product, name, failure, response.text)
                    code = 'BACKEND_STREAM_ERROR' if failure == 'chunk' else 'BACKEND_INVALID_RESPONSE'
                    assert code in response.text, (product, name, failure, response.text)
                    assert len(response.content) < 4096
            if product in ('hermes', 'opendesign', 'litellm'):
                # Explicit non-goal: do not filter arbitrary valid business output.
                mode['value'] = 'success'
                name, arguments = PROBES[product]
                response = await client.post('/mcp', headers=headers, json=call(name, arguments))
                assert CANARY in response.text


def test_public_error_mapping_never_reads_exception_text():
    class Poison(ValueError):
        def __str__(self):
            raise AssertionError('raw exception text must not be inspected')

    @policy.backend_errors
    def parse():
        raise Poison(CANARY)

    with pytest.raises(policy.BackendFailure, match='^BACKEND_INVALID_RESPONSE$'):
        parse()
    assert policy.public_backend_error(RuntimeError(CANARY)) == 'BACKEND_UNAVAILABLE'
    assert policy.public_backend_error(httpx.DecodingError(CANARY)) == 'BACKEND_INVALID_RESPONSE'
    assert policy.public_backend_error(UnicodeDecodeError('utf-8', CANARY.encode(), 0, 1, CANARY)) == 'BACKEND_INVALID_RESPONSE'
    assert policy.public_backend_error(policy.BackendBusy()) == 'BACKEND_BUSY'
    assert policy.public_backend_error(policy.BackendDenied()) == 'BACKEND_DESTINATION_DENIED'


async def test_public_handler_and_stream_boundaries_preserve_cancellation():
    @policy.backend_errors
    async def cancelled():
        raise asyncio.CancelledError()

    class CancelledStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise asyncio.CancelledError()
            yield b''
        async def aclose(self):
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await cancelled()
    stream = policy.AsyncResponseStream(CancelledStream())
    with pytest.raises(asyncio.CancelledError):
        await anext(stream.__aiter__())
    with pytest.raises(asyncio.CancelledError):
        await stream.aclose()


# Test-only entrypoint: keep actual launcher/handler/HTTPX/core pool and wire
# exchange. Inject only late core read/close faults, never real credentials.
CHILD_LATE_FAULT = r'''
import runpy, sys
import httpcore
from httpcore._sync.connection_pool import PoolByteStream as SyncStream
from httpcore._async.connection_pool import PoolByteStream as AsyncStream
mode, phase = sys.argv[2:4]
canary = 'DUMMY-LATE-RESPONSE-SECRET'
def selected(stream):
    path = stream._pool_request.request.url.target.decode()
    return (phase == 'gateway' and path == '/v1/capabilities' or
            phase == 'login' and path == '/auth/password-login' or
            phase == 'cookie' and path == '/api/status' or
            phase == 'sync' and path == '/api/health')
sync_iter, async_iter = SyncStream.__iter__, AsyncStream.__aiter__
sync_close, async_close = SyncStream.close, AsyncStream.aclose
if mode == 'close':
    def close(self):
        sync_close(self)
        if selected(self): raise httpcore.ReadError(canary)
    async def aclose(self):
        await async_close(self)
        if selected(self): raise httpcore.ReadError(canary)
    SyncStream.close, AsyncStream.aclose = close, aclose
else:
    def iterate(self):
        for part in sync_iter(self):
            yield part
            if selected(self):
                raise (httpcore.ReadTimeout if mode == 'timeout' else httpcore.ReadError)(canary)
    async def aiterate(self):
        async for part in async_iter(self):
            yield part
            if selected(self):
                raise (httpcore.ReadTimeout if mode == 'timeout' else httpcore.ReadError)(canary)
    SyncStream.__iter__, AsyncStream.__aiter__ = iterate, aiterate
runpy.run_path(sys.argv[1], run_name='__main__')
'''


@pytest.mark.parametrize('phase', ['gateway', 'login', 'cookie', 'sync'])
@pytest.mark.parametrize('failure', ['read', 'timeout', 'close'])
async def test_actual_gateway_late_core_faults(tmp_path, monkeypatch, phase, failure):
    original = test_six_hardening.child_spec

    def instrumented(*args, **kwargs):
        spec = original(*args, **kwargs)
        return ChildSpec((spec.argv[0], '-c', CHILD_LATE_FAULT, spec.argv[1], failure, phase),
                         spec.env, spec.cwd)

    monkeypatch.setattr(test_six_hardening, 'child_spec', instrumented)
    seen = []

    class Backend(Quiet):
        def do_GET(self):
            seen.append(self.path)
            self.reply({'ok': True})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert body['password'] == CANARY
            seen.append(self.path)
            self.send_response(200)
            self.send_header('Set-Cookie', f'hermes_session_at={CANARY}')
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'{}')

    product = 'opendesign' if phase == 'sync' else 'hermes'
    name, arguments = ('health', {}) if phase == 'sync' else (
        'hermes_inspect', {'target': 'capabilities' if phase == 'gateway' else 'status'})
    with serve(Backend) as url:
        async with runtime(tmp_path, product, url, canary=CANARY) as (client, headers, *_):
            for _ in range(6):  # More than transport/resolver capacity; same child.
                before = len(seen)
                response = await client.post('/mcp', headers=headers, json=call(name, arguments))
                assert len(seen) > before
                assert CANARY not in response.text
                assert ('BACKEND_TIMEOUT' if failure == 'timeout' else 'BACKEND_STREAM_ERROR') in response.text
                assert len(response.content) < 4096
