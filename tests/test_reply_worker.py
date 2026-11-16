"""HM-30: a switched-on product's replies are processed on the add-on's one reply worker, the profiles taking turns,
and each profile's answers not received yet are bounded (multi-profile plan 5.5; contract 2.4, 5, 6; §8.8 #17;
invariant I8; DQ-07 (a); C2-MF-4, C1-M5; FM-129, FM-149).

- One worker thread for the whole add-on; the gateway hands it only pure functions of the reply's bytes and what it
  read on the loop first (the profile's state and masks): strict_json, redact_secrets, filter_list, json.dumps, for a
  JSON reply and for every SSE event with data alike. Jobs wait per profile and the profiles take turns; a profile
  with a job in process is out of turn, so at most one job per profile (and, one thread, one in all) is in process.
- What a client gets is byte for byte what the gateway answered on the loop (both paths of the same make_apps, every
  case below); HM-01's golden regression and contract freezes run switched on too (tests/test_router_passthrough.py).
- A job's exception is its caller's, re-raised on the loop as before; a cancelled caller withdraws its queued job. If
  the worker's thread ends by itself, every job gets WorkerStopped at once (a 502 for the request, never a request
  that waits forever) and run_product stops the add-on; at shutdown queued jobs end at once and the one in process is
  waited for at most STOP_SECONDS.
- CPU starvation (contract 6, controllable injection, tests/reply_load.py): while the default profile's 16 replies of
  8 MiB and 16 of 2 MiB cost 0.25 s each per 8 MiB of GIL-holding work, the loop never stops for more than 50 ms and
  another profile's tools/call p99 is at most 2d + 0.2 s. A real 8 MiB reply's own C calls are measured apart.
- Each profile's answers not received yet (handed to the server, not taken by it: its pending replies; 32 MiB) are
  charged from the moment its app hands them over until the server took them; at or over the limit, the profile's next
  tools/call is answered 200 + -32003 before it is forwarded. A slow reader then holds no more than contract 6 allows
  (RSS, with an event stream's forwarded body included).
- Switched off: no worker, no gate; every reply is processed on the loop as before.
"""
import asyncio
from dataclasses import replace
import gc
import json
from pathlib import Path
import subprocess
import sys
import textwrap
import threading
import time
import weakref

import httpx
import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import Children, create_profile, multi_profile_runtime, stored
from mcp_admin_core import gateway, profiles
from mcp_admin_core.config import Store
from mcp_admin_core.gateway import make_apps
from n8n_adapter import TOOLS as N8N_TOOLS
from reply_load import (ARGUMENTS, B, C, D, LABELS, LARGE, PRODUCT, STALL_LIMIT, TOOL, LoopLag, bearer, call,
                        percentile, session_of, starved, until, watch)
from test_profile_runtime import ProfileChild
from test_single_profile_golden import ACCEPT, GENUINE_CLIENT, configure, header_pairs

pytestmark = pytest.mark.usefixtures('log_scan')
MiB = 1024 * 1024


def worker_module():
    import mcp_admin_core.reply_worker as module  # imported when a test runs (the red half of red-green)
    return module


def router():
    import mcp_admin_core.profile_router as module
    return module


@pytest.fixture
async def worker():
    module = worker_module()
    value = module.ReplyWorker()
    value.start()
    yield value
    await value.stop()


# ---- the worker itself ----

async def test_one_thread_takes_the_profiles_in_turn_one_job_of_each_at_a_time(worker):
    """A's first job is in process, A's next two and B's and C's are queued: B and C go before A's next ones (a profile
    with a job in process is out of turn), every job runs on the one worker thread, never two at once."""
    module = worker_module()
    order, threads = [], set()
    first = threading.Event()

    def job(name):
        threads.add(threading.current_thread().name)
        order.append(name)
        if name == 'a1':
            assert first.wait(10)
        return name
    a = [asyncio.create_task(worker.run('a', job, f'a{number}')) for number in (1, 2, 3)]
    await until(lambda: order == ['a1'])
    b = asyncio.create_task(worker.run('b', job, 'b1'))
    c = asyncio.create_task(worker.run('c', job, 'c1'))
    await asyncio.sleep(0.05)
    assert order == ['a1']
    first.set()
    assert await asyncio.wait_for(asyncio.gather(*a, b, c), 10) == ['a1', 'a2', 'a3', 'b1', 'c1']
    assert order == ['a1', 'b1', 'c1', 'a2', 'a3']
    assert threads == {module.THREAD_NAME} and worker.peak == 1 and worker.processed == 5
    assert [thread.name for thread in threading.enumerate()].count(module.THREAD_NAME) == 1


async def test_a_lane_is_one_profiles_turn(worker):
    lane = worker.lane('a')
    assert (lane.worker, lane.profile) == (worker, 'a')
    assert await asyncio.wait_for(lane.run(lambda *values: values, 1, 2), 10) == (1, 2)


async def test_a_jobs_exception_is_its_callers_and_the_worker_goes_on(worker):
    """Any BaseException a job raises is re-raised for its caller (the gateway then answers as it did on the loop;
    StopIteration, which a future refuses, as a RuntimeError); its frames are cleared, so nothing the job held stays
    alive with it; the next job runs."""
    class Severe(BaseException):
        pass

    class Held:
        pass
    alive = []

    def fail(kind):
        held = Held()
        alive.append(weakref.ref(held))
        raise kind('refused reply')
    with pytest.raises(ValueError, match='refused reply') as caught:
        await asyncio.wait_for(worker.run('a', fail, ValueError), 10)
    gc.collect()
    assert alive[0]() is None and caught.value.__traceback__ is not None
    with pytest.raises(Severe):
        await asyncio.wait_for(worker.run('b', fail, Severe), 10)
    with pytest.raises(RuntimeError, match='StopIteration'):  # a future refuses StopIteration: asyncio's own rule
        await asyncio.wait_for(worker.run('b', fail, StopIteration), 10)
    assert await asyncio.wait_for(worker.run('a', lambda: 'still'), 10) == 'still'
    assert worker.alive and worker.failure is None


async def test_a_cancelled_caller_withdraws_its_queued_job(worker):
    started, gate, ran = threading.Event(), threading.Event(), []

    def hold():
        started.set()
        return gate.wait(10)
    holding = asyncio.create_task(worker.run('a', hold))
    await until(started.is_set)
    queued = asyncio.create_task(worker.run('b', ran.append, 'b'))
    await asyncio.sleep(0.02)
    queued.cancel()
    with pytest.raises(asyncio.CancelledError):
        await queued
    gate.set()
    assert await asyncio.wait_for(holding, 10) is True
    assert await asyncio.wait_for(worker.run('c', lambda: 'c'), 10) == 'c' and ran == []


async def test_stop_ends_queued_jobs_at_once_and_waits_for_the_one_in_process():
    module = worker_module()
    worker = module.ReplyWorker()
    worker.start()
    started, gate = threading.Event(), threading.Event()

    def slow():
        started.set()
        gate.wait(10)
        return 'done'
    running = asyncio.create_task(worker.run('a', slow))
    await until(started.is_set)
    queued = [asyncio.create_task(worker.run(profile, lambda: 'never')) for profile in ('a', 'b')]
    await asyncio.sleep(0.02)
    stopping = asyncio.create_task(worker.stop())
    for task in queued:
        with pytest.raises(module.WorkerStopped):
            await asyncio.wait_for(task, 1)
    await asyncio.sleep(0.05)
    assert not stopping.done()  # the job in process is waited for
    gate.set()
    await asyncio.wait_for(stopping, 5)
    assert await asyncio.wait_for(running, 10) == 'done'
    assert not worker.alive and worker.ended.is_set() and worker.failure is None
    with pytest.raises(module.WorkerStopped):
        await worker.run('a', lambda: 'late')


async def test_stop_waits_no_longer_than_its_bound_for_a_job_that_does_not_end(monkeypatch):
    module = worker_module()
    monkeypatch.setattr(module, 'STOP_SECONDS', 0.2)
    worker = module.ReplyWorker()
    worker.start()
    started, gate = threading.Event(), threading.Event()

    def stuck():
        started.set()
        gate.wait(10)
        return 'late'
    running = asyncio.create_task(worker.run('a', stuck))
    await until(started.is_set)
    loop = asyncio.get_running_loop()
    begun = loop.time()
    await asyncio.wait_for(worker.stop(), 10)
    assert 0.15 <= loop.time() - begun < 2 and worker.alive and worker._thread.daemon
    gate.set()
    assert await asyncio.wait_for(running, 5) == 'late'
    await until(lambda: not worker.alive)


async def test_a_worker_whose_thread_ended_answers_every_job_at_once(monkeypatch, log_scan):
    """A fault of the worker itself (here: taking the next job raises) ends its thread: the queued job and every later
    one get WorkerStopped at once, ended is set and failure says why; one WARNING names the exception's class only."""
    module = worker_module()
    worker = module.ReplyWorker()
    worker.start()
    try:
        started, gate = threading.Event(), threading.Event()

        def slow():
            started.set()
            gate.wait(10)
            return 'done'
        running = asyncio.create_task(worker.run('a', slow))
        await until(started.is_set)
        queued = asyncio.create_task(worker.run('b', lambda: 'never'))
        await asyncio.sleep(0.02)

        def fault():
            raise RuntimeError('DUMMY-fault-text')
        monkeypatch.setattr(worker, '_next', fault)
        gate.set()
        assert await asyncio.wait_for(running, 5) == 'done'
        with pytest.raises(module.WorkerStopped):
            await asyncio.wait_for(queued, 5)
        await asyncio.wait_for(worker.ended.wait(), 5)
        assert isinstance(worker.failure, RuntimeError) and not worker.alive
        with pytest.raises(module.WorkerStopped):
            await worker.run('a', lambda: 'late')
    finally:
        await worker.stop()
    lines = [record.getMessage() for record in log_scan.records if record.name == 'mcp_admin_core.reply_worker']
    assert lines == ['MCP reply worker: its thread stopped (RuntimeError); replies cannot be processed and the add-on '
                     'stops']


async def test_a_busy_worker_lets_the_loop_have_the_gil_at_its_checkpoints(worker, tmp_path):
    """The GIL convoy (reply_worker's module docstring): while the worker runs back-to-back C calls of about 10 ms, each
    system call of the loop (here a small file read, as store.load makes five) waits for the GIL again, so the loop
    crawls. With a checkpoint between the calls (breathe: a 1 ms sleep once the worker ran 5 ms; the parser calls it
    once per JSON object) the loop has the GIL to itself during the breaths, and its reads are about as fast as with an
    idle worker. Off the worker thread a checkpoint does nothing."""
    module = worker_module()
    path = tmp_path / 'state.json'
    path.write_text('{"x": 1}')
    document = '"' + 'a' * (5 * MiB) + '"'  # one json.loads of it: one C call of about 10 ms

    def busy(units, checkpoint):
        for _ in range(units):
            json.loads(document)
            if checkpoint:
                module.breathe()

    async def reads_while(checkpoint):
        job = asyncio.create_task(worker.run('a', busy, 20, checkpoint))
        latencies = []
        while not job.done():
            begun = time.perf_counter()
            path.read_bytes()
            await asyncio.sleep(0)
            latencies.append(time.perf_counter() - begun)
        await asyncio.wait_for(job, 30)
        return sorted(latencies)
    convoy = await reads_while(False)
    breathing = await reads_while(True)
    begun = time.perf_counter()
    module.breathe()
    assert time.perf_counter() - begun < 0.001  # not on the worker thread: no sleep
    print(f'HM-30 convoy: {len(convoy)} reads during the job, median {convoy[len(convoy) // 2] * 1000:.2f} ms; '
          f'with checkpoints {len(breathing)} reads, median {breathing[len(breathing) // 2] * 1000:.3f} ms')
    assert breathing[len(breathing) // 2] < 0.001
    assert len(breathing) >= 5 * len(convoy)


def test_the_worker_thread_has_a_stack_of_its_own_for_deeply_nested_replies():
    """A reply nested just inside CPython's C recursion limit is parsed on the worker, one nested past it raises
    RecursionError (the gateway's 502), even where threads get a small stack by default. Here both defaults are small:
    the platform's, 512 KiB (glibc sizes a thread's stack by the RLIMIT_STACK soft limit the process started with, 2 MiB
    when it is unlimited; the child starts under 512 KiB), and the process's own setting, 256 KiB (threading.stack_size
    before the worker starts); either one crashes json.loads 9,000 levels deep (measured: 1 MiB already does). The
    worker starts its thread with STACK_BYTES and gives the process's setting back. In a child interpreter, where a
    crash cannot take the test run with it."""
    code = textwrap.dedent("""
        import asyncio, json, resource, sys, threading
        sys.path.insert(0, sys.argv[1])
        from mcp_admin_core import reply_worker
        assert resource.getrlimit(resource.RLIMIT_STACK)[0] == 512 * 1024  # the platform's default for threads
        threading.stack_size(256 * 1024)  # the process's own setting

        def parse(depth):
            try:
                json.loads('[' * depth + ']' * depth)
                return 'parsed'
            except RecursionError:
                return 'RecursionError'

        async def main():
            worker = reply_worker.ReplyWorker().start()
            assert threading.stack_size() == 256 * 1024
            print(await worker.run('a', parse, 9000), await worker.run('a', parse, 100000), flush=True)
            await worker.stop()
        asyncio.run(main())
    """)
    package = Path(gateway.__file__).resolve().parents[1]  # the mcp_admin_core this test run imports
    # The soft limit is lowered (always allowed) by the shell that then becomes the child interpreter: glibc reads it
    # when the process starts.
    result = subprocess.run(['/bin/sh', '-c', 'ulimit -S -s 512 && exec "$@"', 'sh', sys.executable, '-I', '-c', code,
                             str(package)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, (result.returncode, result.stderr[-2000:])
    assert result.stdout.split() == ['parsed', 'RecursionError']


# ---- byte for byte what the loop answered ----

SECRETS = ('O' * 43, 'P' * 43)  # other profiles' tokens (reply_secrets), synthetic


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / 'state')
    value.update(backend_url='https://n8n.invalid', backend_key='DUMMY-reply-worker-key')
    yield value
    value.close()


def reply(result=None, *, error=None, ident=7):
    value = {'jsonrpc': '2.0', 'id': ident}
    value.update({'error': error} if error is not None else {'result': result})
    return json.dumps(value, ensure_ascii=False).encode()


def text_result(text):
    return {'content': [{'type': 'text', 'text': text}], 'isError': False}


def json_cases(token, child_token):
    deep = b'{"jsonrpc":"2.0","id":7,"result":' + b'[' * 100_000 + b']' * 100_000 + b'}'
    tools = [{'name': name, 'description': 'child text', 'inputSchema': {'type': 'object'}} for name in
             list(N8N_TOOLS)[:3]] + [{'name': 'not_a_tool'}, {'name': list(N8N_TOOLS)[0]}]
    return {
        'ascii': reply(text_result('plain answer ' * 100)),
        'cjk-emoji': reply(text_result('中文回覆 \U0001F600 ' * 50)),
        'escaped-surrogate': b'{"jsonrpc":"2.0","id":7,"result":{"content":[{"type":"text","text":"\\ud800 \\udfff"}]}}',
        'numbers': (b'{"jsonrpc":"2.0","id":7,"result":{"n":[1e15,-0,0.1,1.5e-7,123456789012345678901234567890,'
                    b'-1,2.50,1E3]}}'),
        'records': reply({'structuredContent': {'records': [{'id': n, 'name': f'Partner {n}', 'amount': n * 1.5,
                                                             'tags': [1, 2], 'active': True, 'note': None}
                                                            for n in range(300)]}, **text_result('records')}),
        'secrets': reply(text_result(f'token {token} child {child_token} key DUMMY-reply-worker-key others '
                                     f'{SECRETS[0]} and {SECRETS[1]}') | {token: 'a key that is a token'}),
        'tools': reply({'tools': tools, 'nextCursor': 'next', 'other': 1}),
        'capabilities': reply({'capabilities': {'tools': {'listChanged': True}, 'resources': {}}}),
        'error-with-data': reply(error={'code': -32001, 'message': f'backend said {token}', 'data': {'k': [1, 2]}}),
        'error-float-code': reply(error={'code': 1000.0, 'message': 'float code'}),
        'error-elicitation': reply(error={'code': -32042, 'message': 'open this', 'data': {'url': 'https://x.invalid'}}),
        'error-bad-message': reply(error={'code': -1, 'message': 5}),
        'not-json': b'{"jsonrpc":',
        'duplicate-key': b'{"jsonrpc":"2.0","id":7,"id":7,"result":{}}',
        'nan': b'{"jsonrpc":"2.0","id":7,"result":{"n":NaN}}',
        'too-large-number': b'{"jsonrpc":"2.0","id":7,"result":{"n":1e400}}',
        'other-id': reply(text_result('x'), ident=8),
        'id-type': b'{"jsonrpc":"2.0","id":"7","result":{}}',
        'batch': b'[' + reply(text_result('x')) + b']',
        'both': b'{"jsonrpc":"2.0","id":7,"result":{},"error":{"code":1,"message":"m"}}',
        'neither': b'{"jsonrpc":"2.0","id":7}',
        'empty': b'',
        'too-deep': deep,
        'oversize': reply(text_result('x' * (gateway.MAX_RESPONSE + 10))),
    }


def sse_cases(token):
    good = reply(text_result('streamed answer'))
    return {
        'reply': b'data: ' + good + b'\n\n',
        'priming-comments-fields': b': hello\n\nid: 1\nevent: message\nretry: 10\ndata:\n\nid: 2\ndata: ' + good + b'\n\n',
        'list-changed-then-reply': (b'data: {"jsonrpc":"2.0","method":"notifications/tools/list_changed","params":{}}\n\n'
                                    b'data: ' + good + b'\n\n'),
        'progress-and-request-skipped': (b'data: {"jsonrpc":"2.0","method":"notifications/progress","params":{}}\n\n'
                                         b'data: {"jsonrpc":"2.0","id":99,"method":"sampling/createMessage"}\n\n'
                                         b'data: ' + good + b'\n\n'),
        'other-id-then-reply': b'data: ' + reply(text_result('not yours'), ident=8) + b'\n\ndata: ' + good + b'\n\n',
        'reply-then-more': b'data: ' + good + b'\n\ndata: ' + reply(text_result('second')) + b'\n\n',
        'batch-ends': b'data: [' + good + b']\n\ndata: ' + good + b'\n\n',
        'malformed-ends': b'data: {"jsonrpc"\n\ndata: ' + good + b'\n\n',
        'both-ends': b'data: {"jsonrpc":"2.0","id":7,"result":{},"error":{"code":1,"message":"m"}}\n\n',
        'lone-cr-ends': b'data: ' + good + b'\r\r\n\n',
        'multi-line-data': b'data: {"jsonrpc":"2.0",\ndata: "id":7,"result":{"content":[]}}\n\n',
        'secrets-and-tools': b'data: ' + reply({'tools': [{'name': list(N8N_TOOLS)[1], 'description': token},
                                                          {'name': 'unknown'}]}) + b'\n\n',
        'neither-skipped': b'data: {"jsonrpc":"2.0","id":7}\n\ndata: ' + good + b'\n\n',
        'truncated': b'data: ' + good,
    }


class Recording:
    """Which threads parsed the replies (gateway.strict_json on a body that names MARK)."""
    MARK = b'answer'

    def __init__(self, real):
        self.real, self.threads = real, []

    def __call__(self, raw, **options):
        if self.MARK in bytes(raw):
            self.threads.append(threading.current_thread().name)
        return self.real(raw, **options)


async def relayed(store, child, *, lane=None, method='tools/call', http='POST', chunked=False, sse=False):
    """One request answered by make_apps (reply_secrets given, as a switched-on product's apps get it; lane: the reply
    worker's) whose child answers `child` bytes, JSON or (sse) an event stream (chunked: in pieces of 7 bytes):
    (status, headers, body), or (the exception's class, its text) when the app raised one."""

    def answer(request):
        content = child
        if chunked:
            async def pieces():
                for start in range(0, len(child), 7):
                    yield child[start:start + 7]
            content = pieces()
        return httpx.Response(200, headers={'content-type': 'text/event-stream' if sse else 'application/json'},
                              content=content)
    options = {'reply_secrets': lambda: set(SECRETS)}
    if lane is not None:
        options['reply_worker'] = lane
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        _, app = make_apps(store, N8N_TOOLS, client, **options)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://mcp') as mcp:
            headers = {**bearer(store.load().token), 'Mcp-Session-Id': 's'}
            try:
                if http == 'GET':
                    response = await mcp.get('/mcp', headers=headers)
                else:
                    response = await mcp.post('/mcp', headers=headers, json={
                        'jsonrpc': '2.0', 'id': 7, 'method': method,
                        'params': {'name': list(N8N_TOOLS)[0], 'arguments': {}} if method == 'tools/call' else {}})
            except Exception as error:  # an unexpected error reaches the client as the app raised it
                return type(error), str(error)
            return response.status_code, header_pairs(response), response.content


@pytest.mark.parametrize('case', list(json_cases('T' * 43, 'C' * 43)))
async def test_a_json_reply_is_byte_for_byte_what_the_loop_answered(store, worker, monkeypatch, case):
    state = store.load()
    child = json_cases(state.token, state.child_token)[case]
    method = 'tools/list' if case in ('tools', 'capabilities') else 'tools/call'
    recording = Recording(gateway.strict_json)
    monkeypatch.setattr(gateway, 'strict_json', recording)
    inline = await relayed(store, child, method=method)
    assert recording.threads in ([], ['MainThread'])
    recording.threads.clear()
    assert await relayed(store, child, lane=worker.lane('a'), method=method) == inline
    assert recording.threads in ([], [worker_module().THREAD_NAME])
    if case in ('ascii', 'secrets', 'error-with-data', 'tools'):
        assert inline[0] == 200
        for secret in (state.token, state.child_token, 'DUMMY-reply-worker-key', *SECRETS):
            assert secret.encode() not in inline[2]
    if case in ('not-json', 'duplicate-key', 'nan', 'too-large-number', 'other-id', 'id-type', 'batch', 'both',
                'neither', 'empty', 'too-deep', 'oversize'):
        assert inline[:1] == (502,) and inline[2] == b'{"error":"request denied"}'


@pytest.mark.parametrize('chunked', [False, True], ids=['whole', 'pieces'])
@pytest.mark.parametrize('case', list(sse_cases('T' * 43)))
async def test_an_event_stream_is_byte_for_byte_what_the_loop_answered(store, worker, monkeypatch, case, chunked):
    state = store.load()
    child = sse_cases(state.token)[case]
    method = 'tools/list' if case == 'secrets-and-tools' else 'tools/call'
    recording = Recording(gateway.strict_json)
    monkeypatch.setattr(gateway, 'strict_json', recording)
    inline = await relayed(store, child, method=method, chunked=chunked, sse=True)
    assert set(recording.threads) <= {'MainThread'}
    recording.threads.clear()
    assert await relayed(store, child, lane=worker.lane('a'), method=method, chunked=chunked, sse=True) == inline
    assert set(recording.threads) <= {worker_module().THREAD_NAME}
    assert state.token.encode() not in inline[2]


async def test_a_get_streams_events_are_byte_for_byte_what_the_loop_answered(store, worker):
    child = (b'data: {"jsonrpc":"2.0","method":"notifications/tools/list_changed"}\n\n'
             b'data: ' + reply(text_result('no reply on a GET stream')) + b'\n\n'
             b'data: {"jsonrpc":"2.0","method":"notifications/message","params":{}}\n\n')
    inline = await relayed(store, child, http='GET', sse=True)
    assert inline[0] == 200 and inline[2] == b'data: {"jsonrpc":"2.0","method":"notifications/tools/list_changed"}\n\n'
    assert await relayed(store, child, lane=worker.lane('a'), http='GET', sse=True) == inline


async def test_an_unexpected_error_while_processing_reaches_the_client_as_it_did(store, worker, monkeypatch):
    def broken(*args):
        raise KeyError('DUMMY-processing-fault')
    monkeypatch.setattr(gateway, 'filter_list', broken)
    child = reply(text_result('answer'))
    inline = await relayed(store, child)
    assert inline[0] is KeyError
    assert await relayed(store, child, lane=worker.lane('a')) == inline
    sse_child = b'data: ' + child + b'\n\n'
    assert await relayed(store, sse_child, lane=worker.lane('a'), sse=True) == await relayed(store, sse_child, sse=True)


async def test_a_stopped_worker_is_answered_as_a_reply_the_gateway_cannot_process(store):
    """A job the worker can no longer take (stopped, or its thread ended): the JSON reply's request gets the 502 of a
    reply the gateway does not relay, an event stream ends there, as for an event it cannot parse."""
    module = worker_module()
    stopped = module.ReplyWorker()
    stopped.start()
    await stopped.stop()
    status, _, body = await relayed(store, reply(text_result('answer')), lane=stopped.lane('a'))
    assert (status, body) == (502, b'{"error":"request denied"}')
    status, headers, body = await relayed(store, b': before\n\ndata: ' + reply(text_result('answer')) + b'\n\n',
                                          lane=stopped.lane('a'), sse=True)
    assert status == 200 and body == b': before\n\n'


async def test_the_state_is_read_on_the_loop_never_on_the_worker(store, worker, monkeypatch):
    """The worker never reads the store: what a job needs of it (the state, the masks) is read on the loop when the job
    is handed over, for a JSON reply and for an event stream's events alike."""
    loads = []
    real = Store.load

    def load(self):
        loads.append(threading.current_thread().name)
        return real(self)
    monkeypatch.setattr(Store, 'load', load)
    assert (await relayed(store, reply(text_result('answer')), lane=worker.lane('a')))[0] == 200
    assert (await relayed(store, b'data: ' + reply(text_result('answer')) + b'\n\n', lane=worker.lane('a'),
                          sse=True))[0] == 200
    assert loads and set(loads) == {'MainThread'}


# ---- switched on and off: the runtime ----

def worker_threads():
    return [thread for thread in threading.enumerate() if thread.name == worker_module().THREAD_NAME]


async def test_switched_on_every_profile_has_its_turn_on_the_add_ons_one_worker(tmp_path, log_scan):
    module = worker_module()
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    children = Children()
    children.add(3000, ProfileChild('default', PRODUCT, data))
    for number, profile_id in enumerate((B, C)):
        create_profile(data, PRODUCT, profile_id, label=LABELS[profile_id], port=18000 + number)
        children.add(18000 + number, ProfileChild('p' + profile_id[:4], PRODUCT,
                                                  profiles.Layout(data).profile(profile_id)))
    before = len(worker_threads())
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        worker = runtime.manager.reply_worker
        assert isinstance(worker, module.ReplyWorker) and worker.alive
        assert len(worker_threads()) == before + 1
        for entry in runtime.manager.profiles():
            lane = entry.runtime.reply_worker
            assert isinstance(lane, module.Lane) and lane.worker is worker and lane.profile == entry.profile_id
        async with runtime.mcp() as client:
            for profile_id in ('default', B, C):
                token = runtime.token(profile_id)
                headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
                response = await client.post('/mcp', headers=headers, json=call(5))
                assert response.status_code == 200 and 'result' in response.json()
        assert worker.processed >= 3 and worker.peak == 1
    assert not worker.alive and len(worker_threads()) == before


async def test_switched_off_there_is_no_worker_and_replies_are_processed_on_the_loop(tmp_path, log_scan, monkeypatch):
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    recording = Recording(gateway.strict_json)
    recording.MARK = b'golden tool result'
    monkeypatch.setattr(gateway, 'strict_json', recording)
    before = len(worker_threads())
    async with multi_profile_runtime(PRODUCT, data, switch=False) as runtime:
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        assert runtime.manager is None and len(worker_threads()) == before
        async with runtime.mcp() as client:
            token = runtime.token('default')
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            response = await client.post('/mcp', headers=headers, json=call(5))
            assert response.status_code == 200 and 'result' in response.json()
    assert recording.threads == ['MainThread']


async def test_a_worker_that_stops_by_itself_stops_the_add_on_and_no_request_waits(tmp_path, log_scan, monkeypatch):
    """The worker's thread ends while the add-on serves (a fault of the worker, not of a job): the reply in process is
    still answered, the one queued behind it is answered 502 at once, and run_product stops the add-on ('runtime
    component stopped'), so that the Supervisor restarts it."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    gate, started = threading.Event(), threading.Event()
    real = gateway.strict_json

    def held(raw, **options):
        if b'"id":61,"result"' in bytes(raw):  # its reply (the request has "method" there)
            started.set()
            gate.wait(10)
        return real(raw, **options)
    monkeypatch.setattr(gateway, 'strict_json', held)
    async with multi_profile_runtime(PRODUCT, data, may_stop=True) as runtime:
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        worker = runtime.manager.reply_worker
        async with runtime.mcp() as client:
            token = runtime.token('default')
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            first = asyncio.create_task(client.post('/mcp', headers=headers, json=call(61)))
            await until(started.is_set)
            queued = asyncio.create_task(client.post('/mcp', headers=headers, json=call(62)))
            await asyncio.sleep(0.05)

            def fault():
                raise RuntimeError('DUMMY-fault-text')
            monkeypatch.setattr(worker, '_next', fault)
            gate.set()
            second = await asyncio.wait_for(queued, 5)
            assert (second.status_code, second.content) == (502, b'{"error":"request denied"}')
            assert (await asyncio.wait_for(first, 5)).status_code == 200
        done, _ = await asyncio.wait({runtime.task}, timeout=10)
        assert runtime.task in done
    error = runtime.task.exception()
    assert isinstance(error, RuntimeError) and str(error) == 'runtime component stopped'
    assert not worker.alive and isinstance(worker.failure, RuntimeError)


async def test_stopping_the_add_on_ends_the_queued_replies_at_once(tmp_path, log_scan, monkeypatch):
    """At shutdown the worker stops after the listeners: a reply still queued is answered 502 at once (or its client
    is gone by then), the one in process is waited for at most STOP_SECONDS, and the add-on stops well within HA's
    30 s (the listeners' own 5 s bound, then the worker's)."""
    module = worker_module()
    monkeypatch.setattr(module, 'STOP_SECONDS', 0.5)
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    gate, started = threading.Event(), threading.Event()
    real = gateway.strict_json

    def held(raw, **options):
        if b'"id":71,"result"' in bytes(raw):  # its reply (the request has "method" there)
            started.set()
            gate.wait(20)
        return real(raw, **options)
    monkeypatch.setattr(gateway, 'strict_json', held)
    loop = asyncio.get_running_loop()
    tasks = []
    try:
        async with multi_profile_runtime(PRODUCT, data) as runtime:
            log_scan.watch(stored(data)['token'], stored(data)['child_token'])
            worker = runtime.manager.reply_worker
            async with runtime.mcp(timeout=30) as client:
                token = runtime.token('default')
                headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
                tasks.append(asyncio.create_task(client.post('/mcp', headers=headers, json=call(71))))
                await until(started.is_set)
                tasks += [asyncio.create_task(client.post('/mcp', headers=headers, json=call(n))) for n in (72, 73)]
                await asyncio.sleep(0.05)
            begun = loop.time()
        stopped_in = loop.time() - begun
        assert stopped_in < 5 + 0.5 + 2, stopped_in
        assert not worker._accepting and worker._thread.daemon
        results = await asyncio.wait_for(asyncio.gather(*tasks[1:], return_exceptions=True), 5)
        for result in results:
            assert isinstance(result, BaseException) or (result.status_code, result.content) == (
                502, b'{"error":"request denied"}'), result
    finally:
        gate.set()
        await asyncio.gather(*tasks, return_exceptions=True)


# ---- CPU starvation (contract 6: controllable injection, tests/reply_load.py) ----

async def test_another_profiles_large_replies_leave_the_loop_and_this_profile_their_pace(tmp_path, log_scan,
                                                                                         monkeypatch):
    """The default profile (A) sends 16 tools/calls answered with 8 MiB and 16 with 2 MiB at once; each costs 0.25 s
    of GIL-holding processing per 8 MiB (d). Meanwhile B calls a tool again and again: while A's replies are processed
    the event loop never stops for more than 50 ms, B's tools/call p99 is at most 2d + 0.2 s (B waits for at most A's one
    reply in process, plus its own), every reply is processed on the worker, one at a time. The loop's lag while A's
    160 MiB still arrive (its own work of reading them in 64 KiB pieces, each under the token lease: no processing) is
    printed, not held to the threshold (the provenance note compares it with the loop's processing before HM-30)."""
    loop = asyncio.get_running_loop()
    latencies = []
    async with starved(tmp_path, log_scan, monkeypatch) as run:
        runtime = run.runtime
        token = runtime.token(B)
        async with runtime.mcp(timeout=60) as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            ident = 1000
            while not all(task.done() for task in run.a_tasks):
                ident += 1
                begun = loop.time()
                response = await client.post('/mcp', headers=headers, json=call(ident))
                latencies.append(loop.time() - begun)
                assert response.status_code == 200, response.content[:200]
                assert response.json()['result']['content'][0]['text'] == 'profile tool result'
                await asyncio.sleep(0.05)
        worker = runtime.manager.reply_worker
        assert worker.peak == 1
    assert len(latencies) >= 8, latencies
    print(f'HM-30 starvation: d={D} unit={run.work.unit * 1000:.1f} ms paid={run.work.paid:.2f} s; loop worst '
          f'while A\'s replies arrived {run.reading.worst * 1000:.1f} ms ({run.reading.samples} samples), while they '
          f'were processed {run.lag.worst * 1000:.1f} ms ({run.lag.samples} samples); B calls={len(latencies)} '
          f'p50={percentile(latencies, 0.5) * 1000:.0f} ms p99={percentile(latencies, 0.99) * 1000:.0f} ms')
    assert run.work.threads == {worker_module().THREAD_NAME}
    assert run.work.paid >= 16 * D * LARGE / (8 * MiB) + 16 * D / 4 - 0.1  # every reply paid its cost
    assert run.lag.worst <= STALL_LIMIT, run.lag.worst
    assert percentile(latencies, 0.99) <= 2 * D + 0.2, latencies


def mixed_reply(limit=8 * MiB - 4096):
    """C2's "mixed" shape (loop_block_bench.py): records as a JSON text and the same records as structuredContent,
    as many as fit in limit bytes."""
    def record(i):
        return {'id': i, 'name': f'Partner {i:06d}', 'email': f'p{i}@example.invalid', 'active': True,
                'street': 'No. %d, Example Rd.' % i, 'city': 'Taipei', 'zip': '100', 'credit': i * 1.5,
                'write_date': '2026-11-14 12:00:00', 'tags': [1, 2, 3], 'company_id': [1, 'Example Co.']}

    def build(count):
        rows = [record(i) for i in range(count)]
        text = json.dumps({'records': rows}, separators=(',', ':'))
        result = {'content': [{'type': 'text', 'text': text}], 'structuredContent': {'records': rows}, 'isError': False}
        return json.dumps({'jsonrpc': '2.0', 'id': 7, 'result': result}, separators=(',', ':')).encode()
    count = int(limit / (len(build(1000)) / 1000))
    while len(raw := build(count)) > limit:
        count -= 50
    return raw


async def test_a_real_8_mib_reply_stops_the_loop_for_its_longest_c_call_only(store, worker):
    """A real reply (C2's mixed shape, about 8 MiB; no injected cost): on the loop it stops every profile for its whole
    processing; on the worker the loop stops only while one C call of it holds the GIL (json.dumps of the whole value
    is the longest: one call). Measured here, against the processing on the loop: the provenance note gives the
    numbers of contract 6's 50 ms threshold, which a real reply of this shape does not meet on the EPYC 7713 (HM-30
    reports it: the user decides on processing in pieces or a subprocess)."""
    raw = mixed_reply()
    assert 7 * MiB < len(raw) <= gateway.MAX_RESPONSE
    value = gateway.strict_json(raw)
    begun = time.perf_counter()
    json.dumps(value, separators=(',', ':'))
    dumps = time.perf_counter() - begun

    async def measured(lane):
        gc.collect()  # the test process's own full collection is not due during the measurement (reply_load.starved)
        lag = LoopLag(0.002).start()
        begun = time.perf_counter()
        answer = await relayed(store, raw, lane=lane)
        total = time.perf_counter() - begun
        await lag.stop()
        return answer, total, lag.worst
    inline, inline_total, inline_worst = await measured(None)
    answer, total, worst = await measured(worker.lane('a'))
    assert answer == inline and inline[0] == 200
    print(f'HM-30 real 8 MiB reply ({len(raw) / MiB:.2f} MiB): on the loop worst stop {inline_worst * 1000:.0f} ms '
          f'(request {inline_total * 1000:.0f} ms); on the worker worst stop {worst * 1000:.1f} ms (request '
          f'{total * 1000:.0f} ms); one json.dumps of it {dumps * 1000:.1f} ms; contract 6 threshold '
          f'{STALL_LIMIT * 1000:.0f} ms')
    assert worst < inline_worst / 2


# ---- each profile's answers not received yet (contract 2.4, 5, 6) ----



# ---- each profile's answers not received yet (contract 2.4, 5, 6) ----

def asgi_request(app, headers, body, *, hold=None):
    """One HTTP/1.1 POST /mcp handed to an ASGI app as uvicorn hands it over. hold: an asyncio.Event the server waits
    for before it takes each body message (a client that does not read: h11 waits for its buffer to drain before it
    takes the next message). Returns the app's task and the messages the server took."""
    taken, received = [], False

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        await asyncio.Event().wait()

    async def send(message):
        if message['type'] == 'http.response.body' and hold is not None:
            await hold.wait()
        taken.append(message)
    scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.3'}, 'http_version': '1.1',
             'method': 'POST', 'scheme': 'http', 'path': '/mcp', 'raw_path': b'/mcp', 'query_string': b'',
             'root_path': '', 'client': ('127.0.0.1', 50000), 'server': ('127.0.0.1', 8081),
             'headers': [(name.lower().encode(), value.encode()) for name, value in headers.items()]
             + [(b'content-type', b'application/json'), (b'content-length', str(len(body)).encode())]}
    return asyncio.create_task(app(scope, receive, send)), taken


def answer_of(taken):
    status = next(message['status'] for message in taken if message['type'] == 'http.response.start')
    return status, b''.join(message.get('body', b'') for message in taken if message['type'] == 'http.response.body')


def exact_reply(ident, size):
    """A compact tools/call reply of exactly size bytes (an ASCII text): the gateway's own serialization of it is the
    same bytes, so what it hands over is size bytes too."""
    head = b'{"jsonrpc":"2.0","id":%d,"result":{"content":[{"type":"text","text":"' % ident
    tail = b'"}],"isError":false}}'
    return head + b's' * (size - len(head) - len(tail)) + tail


class SizedChild(ProfileChild):
    """B's child: a tools/call whose id is in sizes gets an exact_reply of that many bytes, as JSON, or as an event
    stream (its headers, then the reply event) for an id in streams; tool_calls counts the tools/calls of TOOL it got
    (the readiness probe is another tool)."""

    def __init__(self, *args, sizes, streams=()):
        super().__init__(*args)
        self.sizes, self.streams, self.tool_calls = dict(sizes), set(streams), 0

    async def __call__(self, request):
        message = json.loads(request.content) if request.content else {}
        if message.get('method') == 'tools/call' and message['params']['name'] == TOOL:
            self.tool_calls += 1
            ident = message['id']
            if ident in self.sizes:
                body = exact_reply(ident, self.sizes[ident])
                if ident not in self.streams:
                    return httpx.Response(200, headers={'content-type': 'application/json'}, content=body)

                async def events():
                    yield b'data: ' + body + b'\n\n'
                return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=events())
        return await super().__call__(request)


def budget_setup(tmp_path, b_child):
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    children = Children()
    children.add(3000, ProfileChild('default', PRODUCT, data))
    for number, profile_id in enumerate((B, C)):
        create_profile(data, PRODUCT, profile_id, label=LABELS[profile_id], port=18000 + number)
    child = children.add(18000, b_child(profiles.Layout(data).profile(B)))
    children.add(18001, ProfileChild('pcccc', PRODUCT, profiles.Layout(data).profile(C)))
    return data, children, child


async def test_answers_not_received_yet_past_the_budget_refuse_the_profiles_next_tools_call(tmp_path, log_scan,
                                                                                            monkeypatch):
    """B's pending-reply budget is 1 MiB here (32 MiB in the add-on). Two of B's answers of 600 KiB stay with a client
    that does not read: they are charged from the moment B's app hands them over (in pieces of 64 KiB, the bytes on the
    wire unchanged) until the server took them. B's next tools/call is answered at once, 200 + -32003 under its id,
    and never forwarded; a tools/list is still forwarded; the default profile and C are served as before; one WARNING
    a minute. Once the client reads, everything is given back and B's tools/call is forwarded again."""
    budget = 1 * MiB
    monkeypatch.setattr(profiles, 'EXTRA_PROFILE_QUOTA', replace(profiles.EXTRA_PROFILE_QUOTA,
                                                                 pending_reply_bytes=budget))
    size = 600 * 1024
    data, children, child = budget_setup(tmp_path, lambda directory: SizedChild(
        'pbbbb', PRODUCT, directory, sizes={21: size, 22: size, 23: size}))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        gate = runtime.gate(B)
        assert gate.quota.pending_reply_bytes == budget and gate.reply_bytes == 0
        token = runtime.token(B)
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            reading = asyncio.Event()
            held = []
            for number, ident in enumerate((21, 22), 1):
                held.append(asgi_request(runtime.mcp_app, headers, json.dumps(call(ident)).encode(), hold=reading))
                await until(lambda: gate.reply_bytes >= number * size, 10)
            assert gate.reply_bytes == 2 * size
            sent = child.tool_calls
            loop = asyncio.get_running_loop()
            begun = loop.time()
            refused = await client.post('/mcp', headers=headers, json=call(23))
            assert loop.time() - begun < 1
            assert refused.status_code == 200 and refused.headers['retry-after'] == '5'
            assert refused.headers['cache-control'] == 'no-store'
            assert refused.json() == {'jsonrpc': '2.0', 'id': 23, 'error': {
                'code': -32003, 'message': router().pending_text(budget)}}
            assert child.tool_calls == sent  # never forwarded
            listed = await client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 24, 'method': 'tools/list'})
            assert listed.status_code == 200 and 'tools' in listed.json()['result']
            for profile_id in ('default', C):
                other = runtime.token(profile_id)
                response = await client.post('/mcp', headers={**bearer(other), 'Mcp-Session-Id': await session_of(
                    client, other)}, json=call(25))
                assert response.status_code == 200 and response.json()['result']['content'][0]['text'] == (
                    'profile tool result')
            assert (await client.post('/mcp', headers=headers, json=call(26))).json()['error']['code'] == -32003
            warnings = [record.getMessage() for record in log_scan.records
                        if record.name == 'mcp_admin_core.profile_router' and 'not received' in record.getMessage()]
            assert warnings == [f'MCP gateway [profile={B[:8]}]: its answers not received yet held 1 MiB, its limit; '
                                'new tools/call requests were answered busy (-32003) and not sent']
            reading.set()
            for task, taken in held:
                await asyncio.wait_for(task, 10)
                status, answer = answer_of(taken)
                assert (status, answer) == (200, exact_reply(int(json.loads(answer)['id']), size))
                bodies = [message for message in taken if message['type'] == 'http.response.body']
                assert len(bodies) == -(-size // router().REPLY_PIECE) + 1  # the pieces, then the end
                assert all(len(message['body']) <= router().REPLY_PIECE for message in bodies)
                assert bodies[-1] == {'type': 'http.response.body', 'body': b'', 'more_body': False}
            assert gate.reply_bytes == 0
            again = await client.post('/mcp', headers=headers, json=call(23))
            assert again.status_code == 200 and again.content == exact_reply(23, size)


async def test_the_charge_is_given_back_however_a_request_ends(tmp_path, log_scan):
    """An answer handed over and then cut (the client leaves while the server waits: the task is cancelled) gives its
    charge back; a small answer is handed over whole (one message) and charged only until the server took it."""
    data, children, child = budget_setup(tmp_path, lambda directory: SizedChild(
        'pbbbb', PRODUCT, directory, sizes={31: 300 * 1024, 33: 300 * 1024}, streams={33}))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        gate = runtime.gate(B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            for ident in (31, 33):  # JSON, then an event stream
                task, taken = asgi_request(runtime.mcp_app, headers, json.dumps(call(ident)).encode(),
                                           hold=asyncio.Event())
                await until(lambda: gate.reply_bytes >= 300 * 1024, 10)
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                assert (gate.reply_bytes, gate.active, gate.body_bytes) == (0, 0, 0)
            small, small_taken = asgi_request(runtime.mcp_app, headers, json.dumps(call(32)).encode())
            await asyncio.wait_for(small, 10)
            assert gate.reply_bytes == 0
            bodies = [message for message in small_taken if message['type'] == 'http.response.body']
            assert len(bodies) == 1 and answer_of(small_taken)[0] == 200


def rss_bytes():
    with open('/proc/self/statm') as file:
        return int(file.read().split()[1]) * 4096


class RssPeak:
    """The process's resident memory, sampled every 2 ms on a thread of its own: peak is the largest seen."""

    def __init__(self):
        self.peak, self._stop = rss_bytes(), threading.Event()
        self._thread = threading.Thread(target=self._run, name='rss-sampler', daemon=True)

    def _run(self):
        while not self._stop.wait(0.002):
            self.peak = max(self.peak, rss_bytes())

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc_info):
        self._stop.set()
        self._thread.join(5)
        self.peak = max(self.peak, rss_bytes())


def raw_post(port, token, session, message):
    return (f'POST /mcp HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAccept: {ACCEPT["Accept"]}\r\n'
            f'Authorization: Bearer {token}\r\nMcp-Session-Id: {session}\r\nContent-Type: application/json\r\n'
            f'Content-Length: {len(message)}\r\n\r\n').encode() + message


async def test_a_slow_reader_holds_no_more_than_its_pending_reply_budget(tmp_path, log_scan):
    """contract 6 (慢讀用戶端), on the real listener (uvicorn, h11): B's client asks for four 8 MiB answers and never
    reads them, two as JSON and two as event streams whose requests carry 4 MiB of arguments (an open stream keeps its
    forwarded body: charged to B's byte budget, HM-08). They fill B's 32 MiB; B's next tools/call is answered
    200 + -32003 at once and never forwarded; the default profile and C are served as before. The management process's
    RSS grows by at most B's pending replies 32 MiB + one processing's amplification 200 MiB + 64 MiB = 296 MiB. When
    the client leaves, every byte is given back and B is served again."""
    eight = 8 * MiB
    # An event stream's reply: 8 MiB with its framing (data: and the blank line), the most a child may send (MAX_RESPONSE).
    sizes = {ident: eight - (8 if ident in (43, 44) else 0) for ident in range(41, 50)}
    data, children, child = budget_setup(tmp_path, lambda directory: SizedChild(
        'pbbbb', PRODUCT, directory, sizes=sizes, streams={43, 44}))
    writers = []
    try:
        async with multi_profile_runtime(PRODUCT, data, sockets=True, children=children) as runtime:
            watch(log_scan, data)
            gate = runtime.gate(B)
            assert gate.quota.pending_reply_bytes == 32 * MiB
            port, token = runtime.mcp_port, runtime.token(B)
            async with GENUINE_CLIENT(base_url=f'http://127.0.0.1:{port}', timeout=60) as client:
                session = await session_of(client, token)
                headers = {**bearer(token), 'Mcp-Session-Id': session}
                warm = await client.post('/mcp', headers=headers, json=call(49))  # read whole: warms the allocator
                assert warm.status_code == 200 and warm.content == exact_reply(49, eight)
                del warm
                gc.collect()
                baseline = rss_bytes()
                with RssPeak() as rss:
                    for number, ident in enumerate((41, 42, 43, 44), 1):
                        arguments = {**ARGUMENTS, 'filter': 'f' * (4 * MiB)} if ident in (43, 44) else None
                        message = json.dumps(call(ident, arguments)).encode()
                        _, writer = await asyncio.open_connection('127.0.0.1', port)
                        writer.write(raw_post(port, token, session, message))
                        await writer.drain()
                        writers.append(writer)
                        try:
                            await until(lambda: gate.reply_bytes >= number * eight, 30)
                        except TimeoutError:
                            raise AssertionError(('answer', number, 'charged', gate.reply_bytes, 'calls', child.tool_calls,
                                                  'active', gate.active)) from None
                    assert 32 * MiB <= gate.reply_bytes < 32 * MiB + 64
                    assert gate.body_bytes >= 8 * MiB  # the two open streams still hold their forwarded bodies
                    sent = child.tool_calls
                    loop = asyncio.get_running_loop()
                    begun = loop.time()
                    refused = await client.post('/mcp', headers=headers, json=call(45))
                    assert loop.time() - begun < 1 and refused.status_code == 200
                    assert refused.json()['error'] == {'code': -32003, 'message': router().pending_text(32 * MiB)}
                    assert child.tool_calls == sent
                    for profile_id in ('default', C):
                        other = runtime.token(profile_id)
                        response = await client.post('/mcp', headers={**bearer(other), 'Mcp-Session-Id': await
                                                                      session_of(client, other)}, json=call(46))
                        assert response.status_code == 200 and 'result' in response.json()
                    await asyncio.sleep(0.2)
                growth = rss.peak - baseline
                print(f'HM-30 slow reader: B pending {gate.reply_bytes / MiB:.1f} MiB, byte budget '
                      f'{gate.body_bytes / MiB:.1f} MiB, RSS growth {growth / MiB:.0f} MiB (contract 6: 296)')
                assert growth <= (32 + 200 + 64) * MiB, growth / MiB
                for writer in writers:
                    writer.close()
                await until(lambda: gate.reply_bytes == 0 and gate.body_bytes == 0 and gate.active == 0, 20)
                again = await client.post('/mcp', headers=headers, json=call(49))
                assert again.status_code == 200 and again.content == exact_reply(49, eight)
    finally:
        for writer in writers:
            writer.close()
