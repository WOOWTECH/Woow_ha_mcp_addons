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
import uvicorn

from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import Children, create_profile, multi_profile_runtime, stored
from mcp_admin_core import gateway, profiles, run_product
from mcp_admin_core.config import ConfigError, Store
from mcp_admin_core.gateway import make_apps
from n8n_adapter import TOOLS as N8N_TOOLS
from reply_load import (ARGUMENTS, B, C, D, LABELS, LARGE, PRODUCT, STALL_LIMIT, TOOL, LoopLag, bearer, call,
                        percentile, session_of, starved, until, watch)
from test_profile_routing import change_token
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
        # ended is set as the thread ends, from the thread itself (call_soon_threadsafe): the loop may see it before
        # the thread has returned (HM-30 review MF-1: asserting `not alive` at once failed 16% of 200 runs).
        await until(lambda: not worker.alive, 5)
        assert isinstance(worker.failure, RuntimeError)
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


CHECKPOINT_THREAD = 'checkpoint-test'


class Sleeps:
    """reply_worker's time module for a test: the real clock; the sleeps of the checkpoint thread are only recorded
    (none is slept), any other thread's are slept as before."""
    perf_counter = staticmethod(time.perf_counter)

    def __init__(self):
        self.slept = []

    def sleep(self, seconds):
        if threading.current_thread().name == CHECKPOINT_THREAD:
            self.slept.append(seconds)
        else:
            time.sleep(seconds)


def one_checkpoint(module, ran):
    """The sleeps of one checkpoint (breathe) on a thread of its own whose run began `ran` seconds before (the
    worker's _breath is per thread)."""
    def checkpoint():
        module._breath.since = time.perf_counter() - ran
        module.breathe()
    thread = threading.Thread(target=checkpoint, name=CHECKPOINT_THREAD)
    thread.start()
    thread.join(10)
    assert not thread.is_alive()
    return module.time.slept


@pytest.mark.parametrize('busy', [True, False], ids=['loop-busy', 'loop-idle'])
def test_a_checkpoint_gives_way_for_as_long_as_the_loop_is_busy(monkeypatch, busy):
    """Counted, not timed (HM-30 review S-4: a timed test of this missed it): a run past SLICE_SECONDS breathes
    BREATH_SECONDS, then goes on giving way in YIELD_STEP_SECONDS steps while the loop is busy, YIELD_SECONDS in all;
    an idle loop gets the breath only; a run within its slice does not stop at all."""
    module = worker_module()
    monkeypatch.setattr(module, 'time', Sleeps())
    monkeypatch.setattr(module, '_loop_busy', lambda: busy)
    slept = one_checkpoint(module, 1.0)
    assert slept[0] == module.BREATH_SECONDS
    if busy:
        assert set(slept[1:]) == {module.YIELD_STEP_SECONDS}
        assert module.YIELD_SECONDS - 1e-9 <= sum(slept) < module.YIELD_SECONDS + module.YIELD_STEP_SECONDS
    else:
        assert slept == [module.BREATH_SECONDS]
    monkeypatch.setattr(module, 'time', Sleeps())
    assert one_checkpoint(module, 0.0) == []


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


def json_objects(raw):
    """How many JSON objects raw holds (the parser builds each one: object_pairs_hook)."""
    built = []
    json.loads(raw, object_pairs_hook=lambda pairs: built.append(1) or dict(pairs))
    return len(built)


@pytest.mark.parametrize('sse', [False, True], ids=['json', 'event-stream'])
async def test_the_parser_gives_the_worker_a_checkpoint_at_every_object(store, worker, monkeypatch, sse):
    """Counted, not timed (HM-30 review S-4: the injected cost of tests/reply_load.py breathes by itself, so a test of
    the loop's stops cannot see a parser without checkpoints): on the worker the parser calls the checkpoint once for
    every JSON object it builds, the steps once more each; on the loop nothing calls it."""
    calls = []
    real = gateway.breathe

    def counted():
        calls.append(threading.current_thread().name)
        real()
    monkeypatch.setattr(gateway, 'breathe', counted)
    raw = json_cases('T' * 43, 'C' * 43)['records']  # 300 records: over 300 objects
    child = b'data: ' + raw + b'\n\n' if sse else raw
    inline = await relayed(store, child, sse=sse)
    assert calls == []
    assert await relayed(store, child, lane=worker.lane('a'), sse=sse) == inline and inline[0] == 200
    assert set(calls) == {worker_module().THREAD_NAME}
    assert len(calls) >= json_objects(raw) + 2 > 300


# The functions in which the gateway reads the state a reply's processing needs (its masks, the policy): on the loop,
# relayed_reply and relayed_event; for the worker, prepared (gateway.make_apps). The token checks read it elsewhere.
REPLY_STATE_READS = frozenset({'relayed_reply', 'relayed_event', 'prepared'})


@pytest.mark.parametrize('case', ['not-this-requests-reply', 'this-requests-reply', 'list-changed-then-reply'])
async def test_a_state_that_cannot_be_read_fails_the_worker_where_it_fails_the_loop(store, worker, monkeypatch, case):
    """The state cannot be read when a reply is processed (contract 6; HM-30 review S-2): the worker's job raises the
    ConfigError where the loop's own read raises it, after the reply's checks, so both paths answer alike. A reply that
    is not this request's is still the 502 of a reply the gateway does not relay (not the 503 of the state), this
    request's reply is the 503, and an event stream still relays a list_changed event (which needs no state) before it
    ends at the reply. Only the reads for a reply's processing fail here (REPLY_STATE_READS), not the token checks."""
    real = Store.load

    def load(self):
        if sys._getframe(1).f_code.co_name in REPLY_STATE_READS:
            raise ConfigError('state unreadable (test)')
        return real(self)
    monkeypatch.setattr(Store, 'load', load)
    list_changed = b'data: {"jsonrpc":"2.0","method":"notifications/tools/list_changed","params":{}}\n\n'
    child, sse, expected = {
        'not-this-requests-reply': (reply(text_result('answer'), ident=8), False, (502, b'{"error":"request denied"}')),
        'this-requests-reply': (reply(text_result('answer')), False, (503, b'{"error":"state unavailable"}')),
        'list-changed-then-reply': (list_changed + b'data: ' + reply(text_result('answer')) + b'\n\n', True,
                                    (200, gateway.LIST_CHANGED + b'\n\n')),
    }[case]
    inline = await relayed(store, child, sse=sse)
    assert (inline[0], inline[2]) == expected
    assert await relayed(store, child, lane=worker.lane('a'), sse=sse) == inline


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


async def test_the_worker_starts_before_the_listeners_serve_and_stops_once_they_stopped(tmp_path, log_scan,
                                                                                         monkeypatch):
    """contract 6 (HM-30 review S-7): run_product starts the reply worker before either listener serves (a reply
    that comes first never finds no worker, which would be a 502), and stops it only once both listeners stopped."""
    module = worker_module()
    servers, seen = [], {'start': [], 'stop': []}

    def made(self, config):
        uvicorn.Server.__init__(self, config)
        servers.append(self)
    monkeypatch.setattr(run_product.Listener, '__init__', made)
    start, stop = module.ReplyWorker.start, module.ReplyWorker.stop

    def starting(self):
        seen['start'].append([server.started for server in servers])
        return start(self)

    async def stopping(self):
        # Every call: the listeners' serve() still running then (asyncio.all_tasks: the tasks not done yet).
        names = [getattr(task.get_coro(), '__qualname__', '') for task in asyncio.all_tasks()]
        seen['stop'].append([name for name in names if name.endswith('Listener.serve')])
        await stop(self)
    monkeypatch.setattr(module.ReplyWorker, 'start', starting)
    monkeypatch.setattr(module.ReplyWorker, 'stop', stopping)
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    async with multi_profile_runtime(PRODUCT, data) as runtime:
        log_scan.watch(stored(data)['token'], stored(data)['child_token'])
        assert runtime.manager.reply_worker.alive and len(servers) == 2
        assert all(server.started for server in servers)
    assert len(seen['start']) == 1 and not any(seen['start'][0])  # no listener served yet when the worker started
    assert seen['stop'] and all(running == [] for running in seen['stop'])  # nor ran when it was stopped


async def test_a_queued_reply_whose_token_changes_is_withdrawn_at_once(tmp_path, log_scan, monkeypatch):
    """The gateway waits for the worker under the token lease, as for every other wait of a request (HM-30 review
    S-3): while the default profile's reply holds the worker, B's reply waits in B's queue; B's token is rotated: B's
    request is answered 401 at once, not once the worker is free, and B's job is withdrawn, never run (a revoked token
    holds neither the worker nor a slot). The default profile's reply is still answered."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    children = Children()
    children.add(3000, ProfileChild('default', PRODUCT, data))
    for number, profile_id in enumerate((B, C)):
        create_profile(data, PRODUCT, profile_id, label=LABELS[profile_id], port=18000 + number)
        children.add(18000 + number, ProfileChild('p' + profile_id[:4], PRODUCT,
                                                  profiles.Layout(data).profile(profile_id)))
    gate, started = threading.Event(), threading.Event()
    real = gateway.strict_json

    def held(raw, **options):
        if b'"id":81,"result"' in bytes(raw):  # the default profile's reply (the request has "method" there)
            started.set()
            gate.wait(20)
        return real(raw, **options)
    monkeypatch.setattr(gateway, 'strict_json', held)
    try:
        async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
            watch(log_scan, data)
            worker = runtime.manager.reply_worker
            async with runtime.mcp(timeout=30) as client:
                a_token, b_token = runtime.token('default'), runtime.token(B)
                a = {**bearer(a_token), 'Mcp-Session-Id': await session_of(client, a_token)}
                b = {**bearer(b_token), 'Mcp-Session-Id': await session_of(client, b_token)}
                first = asyncio.create_task(client.post('/mcp', headers=a, json=call(81)))
                await until(started.is_set)
                queued = asyncio.create_task(client.post('/mcp', headers=b, json=call(82)))
                await until(lambda: worker.handed[B] >= 1)
                processed = worker.processed
                log_scan.watch(await change_token(runtime, B, 'rotate'))
                done, _ = await asyncio.wait({queued}, timeout=3)
                assert queued in done, "a rotated token's reply still waits for the worker"
                assert queued.result().status_code == 401 and not first.done()
                gate.set()
                assert (await asyncio.wait_for(first, 10)).status_code == 200
                await asyncio.sleep(0.1)
                assert worker.processed == processed + 1  # the default profile's job only: B's never ran
    finally:
        gate.set()


async def test_a_worker_that_stops_by_itself_stops_the_add_on_and_no_request_waits(tmp_path, log_scan, monkeypatch):
    """The worker's thread ends while the add-on serves (a fault of the worker, not of a job): the reply in process is
    still answered (the worker hands it back before it takes the next job), the one queued behind it is answered 502
    at once, and run_product stops the add-on ('runtime component stopped'), so that the Supervisor restarts it.
    The fault waits until the first answer reached its client: the in-process client here bypasses the listener, so
    nothing holds the add-on's stop for it (uvicorn lets a response in progress finish first; HM-30 review fixes: the
    test raced the stop under load)."""
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
            answered = threading.Event()

            def fault():
                answered.wait(10)  # the first answer reached its client: now the thread ends
                raise RuntimeError('DUMMY-fault-text')
            monkeypatch.setattr(worker, '_next', fault)
            gate.set()
            try:
                assert (await asyncio.wait_for(first, 5)).status_code == 200
            finally:
                answered.set()
            second = await asyncio.wait_for(queued, 5)
            assert (second.status_code, second.content) == (502, b'{"error":"request denied"}')
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
    of GIL-holding processing per 8 MiB (d). Meanwhile B calls a tool again and again: over the whole run the event
    loop never stops for more than 50 ms, B's tools/call p99 is at most 2d + 0.2 s (B waits for at most A's one reply
    in process, plus its own), every reply is processed on the worker, one at a time. The whole run (D3 of the HM-30
    review, the user's decision of 2026-11-16: reading counts too): while A's 160 MiB still arrive (A's 32 requests
    start at once, the loop reads the replies in 64 KiB pieces, each under the token lease, while the worker already
    processes the first ones) and while they are processed; both phases are printed."""
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
    print(f'HM-30 starvation: d={D} unit={run.work.unit * 1000:.1f} ms paid={run.work.paid:.2f} s; whole run worst '
          f'{max(run.reading.worst, run.lag.worst) * 1000:.1f} ms; while A\'s replies arrived '
          f'{run.reading.distribution()}; while they were processed {run.lag.distribution()}; B calls={len(latencies)} '
          f'p50={percentile(latencies, 0.5) * 1000:.0f} ms p99={percentile(latencies, 0.99) * 1000:.0f} ms')
    assert run.work.threads == {worker_module().THREAD_NAME}
    assert run.work.paid >= 16 * D * LARGE / (8 * MiB) + 16 * D / 4 - 0.1  # every reply paid its cost
    assert max(run.reading.worst, run.lag.worst) <= STALL_LIMIT, (run.reading.distribution(), run.lag.distribution())
    assert percentile(latencies, 0.99) <= 2 * D + 0.2, latencies


# ---- D3: the loop's own work while A's replies arrive (the user's decision of 2026-11-16, D3 (a); contract 6) ----

class CountingStore:
    """A Store whose loads are counted (the token checks read the state file: five system calls and a parse each)."""

    def __init__(self, store):
        self.store, self.loads = store, 0

    def __getattr__(self, name):
        return getattr(self.store, name)

    def load(self):
        self.loads += 1
        return self.store.load()


async def test_a_lease_checked_just_before_runs_without_reading_the_state_again_first(store):
    """D3: TokenLease.run(checked=True) (a piece of a reply read right after the check that ended the previous one)
    does not read the state before its operation starts, and its watcher's first look comes after its first wait; the
    check after the operation stays, and a token changed through the admin API (TokenAccess.committed) still ends the
    operation at once. A state replaced on disk meanwhile (no event) is caught by the check after it: what the
    operation read is never handed back. Left out (every other lease), as before: a check first, the watcher's at once,
    one after."""
    from mcp_admin_core.access import AccessChanged, TokenAccess
    counting = CountingStore(store)
    access = TokenAccess(counting)
    lease = access.lease(store.load().token)
    held = []

    async def operation():
        held.append(counting.loads)
        await asyncio.sleep(0.05)
        return 'done'
    assert await lease.run(operation) == 'done'
    assert held == [1] and counting.loads == 3  # before it, then the watcher's at once (it starts second), after it
    counting.loads, held = 0, []
    assert await lease.run(operation, checked=True) == 'done'
    assert held == [0] and counting.loads == 1  # after it only (the watcher waits 0.2 s before its first look)

    async def long_operation():
        await asyncio.sleep(10)
    task = asyncio.create_task(lease.run(long_operation, checked=True))
    await asyncio.sleep(0.05)
    begun = time.perf_counter()
    access.committed()  # the admin API changed the token
    with pytest.raises(AccessChanged):
        await asyncio.wait_for(task, 2)
    assert time.perf_counter() - begun < 0.1

    # A change outside the admin API (the state replaced on disk: no event) between the check that ended the previous
    # operation and this one is caught by the check after it: what the operation read is never handed back.
    lease = access.lease(store.load().token)
    read = []

    async def read_after_a_change():
        store.update(token='T' * 43)
        read.append('a piece read after the change')
        return read[-1]
    with pytest.raises(AccessChanged):
        await lease.run(read_after_a_change, checked=True)
    assert read == ['a piece read after the change']


@pytest.mark.parametrize('switched_on', [False, True], ids=['switched-off', 'switched-on'])
async def test_a_switched_on_reply_is_read_with_one_state_read_a_piece(store, worker, switched_on):
    """D3: the gateway reads a child's reply in pieces, each under the token lease. Switched on (reply_worker given) a
    piece reads the state once (the check after it, which is the check before the next one); switched off three times,
    as before. The answer is the same."""
    counting = CountingStore(store)
    raw = reply(text_result('piece ' * 300))  # about 1.9 KiB: 270 or so pieces of 7 bytes
    pieces = -(-len(raw) // 7)
    answer = await relayed(counting, raw, lane=worker.lane('a') if switched_on else None, chunked=True)
    assert answer[0] == 200 and json.loads(answer[2])['result']['content'][0]['text'] == 'piece ' * 300
    print(f'HM-30 D3 state reads: {counting.loads} for {pieces} pieces ({"on" if switched_on else "off"})')
    if switched_on:
        assert pieces <= counting.loads <= pieces + 30
    else:
        assert counting.loads >= 3 * pieces


# ---- D1: the worker serializes in pieces (the user's decision of 2026-11-16, D1 (a); contract 6) ----

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


REAL_LIMIT = 8 * MiB - 4096  # an 8 MiB reply as a child sends it (UTF-8), within MAX_RESPONSE with an event's framing


def filled(build, limit=REAL_LIMIT):
    """build(n) for the largest n that fits limit, for a build whose size grows by the same bytes with every n."""
    one, two = len(build(1)), len(build(2))
    count = (limit - one) // (two - one) + 1
    raw = build(count)
    assert len(raw) <= limit < len(build(count + 1)), (len(raw), limit)
    return raw


def nested_tree(depth=64):
    """A tree as deep as the structure guard lets a request nest (64 levels; a level: a few scalars, a short CJK note, a
    list of the level below and a small dict)."""
    tree = {'leaf': True}
    for level in range(depth):
        tree = {'level': level, 'name': f'node {level:03d}', 'children': [tree, {f'k{n}': 'v' * 12 for n in range(4)}],
                'note': '中文說明'}
    return tree


REAL_SHAPES = {
    # C2's mixed shape: a long JSON text and many records with lists in them
    'mixed': mixed_reply,
    # many small objects (8 MiB of two-member records): json.dumps of the whole value is one C call of 0.1 s or more
    'small-objects': lambda: filled(lambda n: reply({'structuredContent': {'rows': [{'a': 5, 'b': 'x'}] * n},
                                                     **text_result('rows')})),
    # one long string each: Odoo CJK fields, an emoji text (escaped 2 and 3 times as long), plain ASCII
    'cjk': lambda: filled(lambda n: reply(text_result('中文字' * n))),
    'emoji': lambda: filled(lambda n: reply(text_result('\U0001F600' * n))),
    'ascii-string': lambda: filled(lambda n: reply(text_result('a' * n))),
    # a string of what json escapes: controls (6 bytes each), quotes, backslashes, newlines, tabs
    'escapes': lambda: filled(lambda n: reply(text_result('\x01"\\\n\t' * n))),
    # deep trees (64 levels), one after another: hundreds of thousands of objects with lists in them
    'nested': lambda: filled(lambda n: reply({'structuredContent': {'trees': [nested_tree()] * n},
                                              **text_result('nested')})),
}
_REAL = {}


def real_reply(shape):
    if shape not in _REAL:
        _REAL[shape] = REAL_SHAPES[shape]()
    return _REAL[shape]


# Every code point json escapes in its own way: ASCII, controls, the two it backslashes, DEL, Latin-1, a line
# separator, BMP CJK, the replacement character, lone surrogates (strict_json keeps them: \ud800), astral ones.
ALPHABET = 'a Z0"\\/\n\t\r\x00\x1f\x7f\xe9\xff\u2028\u4e2d\ufffd\ud800\udfff\U000103ff\U0001F600\U0010FFFF'


def random_json(rng, depth=0):
    """A random JSON value as strict_json gives one (str keys), with long strings and keys now and then."""
    choice = rng.random()
    if depth < 6 and choice < 0.3:
        return [random_json(rng, depth + 1) for _ in range(rng.randrange(0, 7))]
    if depth < 6 and choice < 0.55:
        return {random_text(rng): random_json(rng, depth + 1) for _ in range(rng.randrange(0, 7))}
    if choice < 0.75:
        return random_text(rng)
    return rng.choice([0, -1, 7, 2 ** 63, -(10 ** 40), 10 ** 300, 0.1, -0.0, 1.5e-7, 1e308, 5e-324, 123.456,
                       True, False, None])


def random_text(rng):
    length = rng.choice([0, 1, 2, 5, 9, 40, 300])
    return ''.join(rng.choice(ALPHABET) for _ in range(length))


def one_shot(value):
    return json.dumps(value, separators=(',', ':')).encode()


@pytest.mark.parametrize(('piece', 'batch'), [(1, 1), (2, 7), (3, 64), (16, 1000)])
def test_in_pieces_the_bytes_are_json_dumps_own(monkeypatch, piece, batch):
    """D1: the worker's serialization (reply_worker.encoded) is byte for byte json.dumps(value, separators=(",", ":"))
    .encode(), the loop's: random values with every kind of code point, number and nesting, and the edge cases, with
    pieces this small (STRING_PIECE code points, PIECE_BYTES bytes) that every value is split at every place it can
    be."""
    module = worker_module()
    monkeypatch.setattr(module, 'STRING_PIECE', piece)
    monkeypatch.setattr(module, 'PIECE_BYTES', batch)
    import random
    rng = random.Random(30 + piece)
    values = [random_json(rng) for _ in range(300)]
    values += ['', [], {}, [[]], {'': {}}, 'x' * 50, ['x' * 50, 'y'], {'k' * 50: 'v' * 50, 'z': ['w' * 50]},
               ALPHABET * 3, [ALPHABET] * 3, {ALPHABET: ALPHABET}, list(range(200)), {str(n): n for n in range(200)},
               [[[[[ALPHABET]]]]], 10 ** 4000, [10 ** 4000, -(10 ** 4000)],
               # what json.dumps converts itself: kept as it does (keys that are not strings, tuples, non-finite)
               {1: 'one', True: 'yes', None: 'none', 1.5: 'half'}, (1, 'two', (3,)), [float('nan'), float('inf')]]
    for value in values:
        assert module.encoded(value) == one_shot(value), value


def test_long_strings_and_large_values_go_out_between_checkpoints(monkeypatch):
    """D1: a long string goes out STRING_PIECE code points at a time and a large list or dict in runs of members of at
    most PIECE_BYTES (counted as the most they can encode to), the checkpoint called between them: one C call never
    encodes a whole large value. A small value is one call."""
    module = worker_module()
    calls = []
    real = module._encode

    def recorded(value):
        text = real(value)
        calls.append(len(text))
        return text
    monkeypatch.setattr(module, '_encode', recorded)
    checkpoints = []
    text = '\U0001F600' * (3 * module.STRING_PIECE + 5)  # each code point 12 bytes once escaped
    assert module.encoded(text, lambda: checkpoints.append(1)) == one_shot(text)
    assert len(calls) == 4 and max(calls) <= 12 * module.STRING_PIECE + 2 and len(checkpoints) == 4
    calls.clear(), checkpoints.clear()
    rows = [{'id': n, 'name': f'Partner {n}', 'tags': [1, 2]} for n in range(20_000)]  # about 0.8 MiB once encoded
    assert module.encoded({'rows': rows}, lambda: checkpoints.append(1)) == one_shot({'rows': rows})
    assert len(calls) >= len(one_shot(rows)) // module.PIECE_BYTES and max(calls) <= module.PIECE_BYTES
    assert len(checkpoints) >= len(calls) - 1
    calls.clear(), checkpoints.clear()
    assert module.encoded({'small': [1, 2]}, lambda: checkpoints.append(1)) == b'{"small":[1,2]}'
    assert len(calls) == 1  # one C call (the checkpoints are the costing pass's, one a container)


async def served_at_once(store, child, *, lane=None, sse=False, piece=64 * 1024):
    """One tools/call answered by make_apps, as relayed() asks it, but straight through ASGI and with the child's bytes
    in pieces of `piece`, the loop running between them (a socket's way; an in-process child handing the gateway 8 MiB
    at one instant would make the loop copy it all in one go, which no network does), and the answer's pieces only
    kept (an in-process HTTP client would join them on the loop: its work, not the gateway's). (status, the headers
    as make_apps sends them, the body's pieces)."""
    async def pieces():
        for start in range(0, len(child), piece):
            yield child[start:start + piece]
            await asyncio.sleep(0)

    def answer(request):
        return httpx.Response(200, headers={'content-type': 'text/event-stream' if sse else 'application/json'},
                              content=pieces())
    options = {'reply_secrets': lambda: set(SECRETS)}
    if lane is not None:
        options['reply_worker'] = lane
    body = json.dumps({'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
                       'params': {'name': list(N8N_TOOLS)[0], 'arguments': {}}}).encode()
    headers = {**bearer(store.load().token), 'Mcp-Session-Id': 's'}
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        _, app = make_apps(store, N8N_TOOLS, client, **options)
        task, taken = asgi_request(app, headers, body)
        await asyncio.wait_for(task, 120)
    start = next(message for message in taken if message['type'] == 'http.response.start')
    return start['status'], sorted(start['headers']), [message.get('body', b'') for message in taken
                                                       if message['type'] == 'http.response.body']


@pytest.mark.parametrize(('shape', 'sse'), [(shape, False) for shape in REAL_SHAPES] + [('mixed', True),
                                                                                        ('emoji', True)])
async def test_a_real_8_mib_reply_is_the_loops_bytes_and_stops_the_loop_briefly(store, worker, shape, sse):
    """D1 (contract 6: the loop's single stop at most 50 ms; no injected cost): a real reply of about 8 MiB in each
    shape, as JSON and two as an event: on the loop it stops every profile for its whole processing; on the worker,
    which serializes in pieces (long strings too) and holds the cyclic collector off while it processes a job, the loop
    stops at most for one short C call (what is left: json.loads scanning one long string, the final join). The answer
    is byte for byte the loop's. The lag's distribution and the request's time are printed (the provenance note)."""
    raw = real_reply(shape)
    child = b'data: ' + raw + b'\n\n' if sse else raw
    assert 7 * MiB < len(child) <= gateway.MAX_RESPONSE

    async def measured(lane):
        gc.collect()  # a full collection of the test process's own objects is not due during the measurement
        lag = LoopLag(0.002).start()
        begun = time.perf_counter()
        status, headers, pieces = await served_at_once(store, child, lane=lane, sse=sse)
        total = time.perf_counter() - begun
        await lag.stop()
        return (status, headers, b''.join(pieces)), total, lag
    inline, inline_total, inline_lag = await measured(None)
    answer, total, lag = await measured(worker.lane('a'))
    assert inline[0] == 200 and answer == inline
    print(f'HM-30 D1 real reply {shape}{" (event)" if sse else ""} ({len(raw) / MiB:.2f} MiB, '
          f'{len(inline[2]) / MiB:.2f} MiB out): on the loop worst stop {inline_lag.worst * 1000:.0f} ms (request '
          f'{inline_total * 1000:.0f} ms); on the worker {lag.distribution()}, request {total * 1000:.0f} ms; '
          f'threshold {STALL_LIMIT * 1000:.0f} ms')
    assert lag.worst <= STALL_LIMIT, lag.distribution()


def test_a_large_value_is_let_go_of_in_pieces_and_nothing_it_does_not_own_is_touched(monkeypatch):
    """D1: once encoded, released() empties a large value's large lists and dicts a run of members at a time (a
    checkpoint between the runs) and its twin's containers of the same place with them; it only drops references, so an
    object held elsewhere too (here a small dict shared with the caller) stays as it was, and a twin of another shape is
    left alone."""
    module = worker_module()
    monkeypatch.setattr(module, 'PIECE_BYTES', 4096)
    shared = {'kept': [1, 2, 3]}
    value = {'rows': [{'id': n, 'name': f'row {n}'} for n in range(2000)], 'shared': shared, 'small': [1]}
    twin = {'rows': [{'id': n, 'name': f'row {n}'} for n in range(2000)], 'shared': {'kept': [1, 2, 3]}, 'small': [1]}
    other = [1, 2, 3]  # not of value's shape
    checkpoints = []
    plans = module._plan(value, module.PIECE_BYTES)
    assert id(value) in plans and id(value['rows']) in plans and id(shared) not in plans
    rows = value['rows']
    module.released(value, plans, lambda: checkpoints.append(1), twin)
    assert value == {} and rows == [] and twin == {} and shared == {'kept': [1, 2, 3]}
    assert len(checkpoints) >= 2000 * 30 // 4096  # a run at a time
    module.released({'rows': list(range(5000))}, module._plan({'rows': list(range(5000))}, 4096), None, other)
    assert other == [1, 2, 3]


async def test_a_large_tool_list_is_relayed_the_same_twice_on_the_worker(store, worker, monkeypatch):
    """D1: filter_list rebuilds a tool list from the policy's own schemas, so the worker never lets go of such a reply in
    pieces (releasable: released is not called for it, as it is for a large tools/call reply): relayed twice, a tool
    list too large for one run of the encoder is the same answer both times, and the loop's."""
    module = worker_module()
    let_go = []
    real = module.released

    def recorded(value, *args):
        let_go.append(type(value).__name__)
        return real(value, *args)
    monkeypatch.setattr(module, 'released', recorded)
    tools = [{'name': name, 'description': 'd' * 4000, 'inputSchema': {'type': 'object'}} for name in list(N8N_TOOLS)]
    raw = reply({'tools': tools * 8})
    inline = await relayed(store, raw, method='tools/list')
    first = await relayed(store, raw, lane=worker.lane('a'), method='tools/list')
    second = await relayed(store, raw, lane=worker.lane('a'), method='tools/list')
    assert inline[0] == 200 and first == inline and second == inline
    assert let_go == []
    large = reply(text_result('x' * (2 * module.PIECE_BYTES)) | {'rows': list(range(20_000))})
    assert (await relayed(store, large, lane=worker.lane('a')))[0] == 200 and let_go == ['dict']


async def test_a_job_runs_with_the_cyclic_collector_held_off(worker, store, monkeypatch):
    """D1: while the worker processes a job the cyclic collector does not run (a full collection walks every object of
    the add-on, the reply's own among them: one stop of the loop of 50 to 75 ms measured on an add-on's heap); it is on
    again once the job ended, however it ended, and stays off when it was off before. The loop's own processing (a
    product not switched on) never touches it."""
    collected = []
    inside = threading.Event()

    def note(phase, info):
        if phase == 'start' and inside.is_set():
            collected.append(info['generation'])
    tracked = 3 * gc.get_threshold()[0]

    def job(fail=False):
        inside.set()
        try:
            enabled = gc.isenabled()
            junk = [[n] for n in range(tracked)]  # tracked objects enough for several collections
            if fail:
                raise ValueError('a failed job')
            return enabled, len(junk)
        finally:
            inside.clear()
    gc.callbacks.append(note)
    try:
        assert gc.isenabled()
        assert await worker.run('a', job) == (False, tracked)
        assert collected == [] and gc.isenabled()
        with pytest.raises(ValueError):
            await worker.run('a', job, True)
        assert collected == [] and gc.isenabled()
        gc.disable()
        try:
            assert await worker.run('a', job) == (False, tracked)
            assert not gc.isenabled()
        finally:
            gc.enable()
        seen = []
        real = gateway.strict_json
        monkeypatch.setattr(gateway, 'strict_json', lambda raw, **options: seen.append(gc.isenabled()) or real(
            raw, **options))
        assert (await relayed(store, reply(text_result('on the loop'))))[0] == 200
        assert seen and all(seen)  # the request's body and the reply, both parsed on the loop with it on
    finally:
        gc.callbacks.remove(note)


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


EMOJI = '\U0001F600'  # 4 bytes as UTF-8; the gateway's json.dumps writes it as a 12-byte escape (\ud83d\ude00)


def exact_reply(ident, size, fill='s'):
    """A compact tools/call reply of exactly size bytes whose text is fill again and again (then 's' up to the size).
    ASCII: the gateway's own serialization of it is the same bytes, so what it hands over is size bytes too; an emoji
    fill: about three times as many (served)."""
    head = b'{"jsonrpc":"2.0","id":%d,"result":{"content":[{"type":"text","text":"' % ident
    tail = b'"}],"isError":false}}'
    room, unit = size - len(head) - len(tail), fill.encode()
    text = unit * (room // len(unit))
    return head + text + b's' * (room - len(text)) + tail


def served(raw):
    """What the gateway hands over for a child's tools/call reply raw that it relays unchanged: its own serialization
    (json.dumps, ASCII escapes, compact)."""
    return json.dumps(json.loads(raw), separators=(',', ':')).encode()


class SizedChild(ProfileChild):
    """One profile's child: a tools/call whose id is in sizes gets an exact_reply of that many bytes (its text fill), as
    JSON, or as an event stream (its headers, then the reply event) for an id in streams; tool_calls counts the
    tools/calls of TOOL it got (the readiness probe is another tool). A request whose id is in held, whatever its
    method, waits until release_held is set (waiting counts them)."""

    def __init__(self, *args, sizes, streams=(), fill='s', held=()):
        super().__init__(*args)
        self.sizes, self.streams, self.fill, self.tool_calls = dict(sizes), set(streams), fill, 0
        self.held, self.waiting, self.release_held = set(held), 0, asyncio.Event()

    async def __call__(self, request):
        message = json.loads(request.content) if request.content else {}
        if message.get('id') in self.held:
            self.waiting += 1
            await self.release_held.wait()
        if message.get('method') == 'tools/call' and message['params']['name'] == TOOL:
            self.tool_calls += 1
            ident = message['id']
            if ident in self.sizes:
                body = exact_reply(ident, self.sizes[ident], self.fill)
                if ident not in self.streams:
                    return httpx.Response(200, headers={'content-type': 'application/json'}, content=body)

                async def events():
                    yield b'data: ' + body + b'\n\n'
                return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=events())
        return await super().__call__(request)


def budget_setup(tmp_path, sized_child, owner=B):
    """The add-on on disk (the default profile, B and C) and its children: owner's is sized_child(its name, its
    directory), the others' a ProfileChild. Returns the data directory, the children and owner's child."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    for number, profile_id in enumerate((B, C)):
        create_profile(data, PRODUCT, profile_id, label=LABELS[profile_id], port=18000 + number)
    children, sized = Children(), None
    for port, profile_id in ((3000, 'default'), (18000, B), (18001, C)):
        name = 'default' if profile_id == 'default' else 'p' + profile_id[:4]
        directory = data if profile_id == 'default' else profiles.Layout(data).profile(profile_id)
        if profile_id == owner:
            sized = children.add(port, sized_child(name, directory))
        else:
            children.add(port, ProfileChild(name, PRODUCT, directory))
    return data, children, sized


def quota_name(profile_id):
    return 'DEFAULT_PROFILE_QUOTA' if profile_id == 'default' else 'EXTRA_PROFILE_QUOTA'


def body_bytes(gate):
    """What the profile's requests hold of the add-on's request body budget now (HM-31: its share of one budget, charged
    by its app; HM-08's own per-profile count is gone)."""
    return gate.budget_share.budget.used(gate.profile_id)


@pytest.mark.parametrize('owner', ['default', B], ids=['default-profile', 'additional-profile'])
async def test_answers_not_received_yet_past_the_budget_refuse_the_profiles_next_tools_call(tmp_path, log_scan,
                                                                                            monkeypatch, owner):
    """The profile's pending-reply budget is 1 MiB here (32 MiB in the add-on), the default profile's as an additional
    profile's (C1-M5: the default profile's holder may be the attacker too; HM-30 review MF-2). Two of its answers of
    600 KiB stay with a client that does not read: they are charged from the moment its app hands them over (in pieces
    of 64 KiB, the bytes on the wire unchanged) until the server took them. Its next tools/call is answered at once,
    200 + -32003 under its id, and never forwarded; a tools/list is still forwarded; the two other profiles are served
    as before; one WARNING a minute. Once the client reads, everything is given back and its tools/call is forwarded
    again."""
    budget = 1 * MiB
    name = quota_name(owner)
    monkeypatch.setattr(profiles, name, replace(getattr(profiles, name), pending_reply_bytes=budget))
    size = 600 * 1024
    data, children, child = budget_setup(tmp_path, lambda child_name, directory: SizedChild(
        child_name, PRODUCT, directory, sizes={21: size, 22: size, 23: size}), owner)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        gate = runtime.gate(owner)
        assert gate.quota.pending_reply_bytes == budget and gate.reply_bytes == 0
        token = runtime.token(owner)
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
            for profile_id in ('default', B, C):
                if profile_id == owner:
                    continue
                other = runtime.token(profile_id)
                response = await client.post('/mcp', headers={**bearer(other), 'Mcp-Session-Id': await session_of(
                    client, other)}, json=call(25))
                assert response.status_code == 200 and response.json()['result']['content'][0]['text'] == (
                    'profile tool result')
            assert (await client.post('/mcp', headers=headers, json=call(26))).json()['error']['code'] == -32003
            warnings = [record.getMessage() for record in log_scan.records
                        if record.name == 'mcp_admin_core.profile_router' and 'not received' in record.getMessage()]
            assert warnings == [f'MCP gateway [profile={profiles.log_id(owner)}]: its answers not received yet held '
                                '1 MiB, its limit; new tools/call requests were answered busy (-32003) and not sent']
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


async def test_a_profile_past_its_pending_reply_budget_is_answered_before_it_waits_for_a_slot(tmp_path, log_scan,
                                                                                              monkeypatch):
    """contract 2.4: the pending-reply check comes before the forwarding slots (HM-30 review S-2). Every one of B's
    slots is taken (its child holds as many pings) and B's answers not received yet hold its budget: B's next
    tools/call is answered 200 + -32003 with the pending-reply text at once, not with the slots' text after waiting
    FORWARD_WAIT_SECONDS for one. (HM-14 puts its queue at the slots: the check stays before it.)"""
    budget = 1 * MiB
    monkeypatch.setattr(profiles, 'EXTRA_PROFILE_QUOTA', replace(profiles.EXTRA_PROFILE_QUOTA,
                                                                 pending_reply_bytes=budget))
    slots = profiles.EXTRA_PROFILE_QUOTA.forward_slots
    size, pings = 600 * 1024, range(60, 60 + slots)
    data, children, child = budget_setup(tmp_path, lambda name, directory: SizedChild(
        name, PRODUCT, directory, sizes={21: size, 22: size}, held=pings))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        gate = runtime.gate(B)
        token = runtime.token(B)
        async with runtime.mcp() as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            reading = asyncio.Event()
            held = []
            for number, ident in enumerate((21, 22), 1):
                held.append(asgi_request(runtime.mcp_app, headers, json.dumps(call(ident)).encode(), hold=reading))
                await until(lambda: gate.reply_bytes >= number * size, 10)
            waiting = [asyncio.create_task(client.post('/mcp', headers=headers, json={
                'jsonrpc': '2.0', 'id': ident, 'method': 'ping'})) for ident in pings]
            try:
                await until(lambda: child.waiting == slots, 10)  # B's slots are all taken now
                loop = asyncio.get_running_loop()
                begun = loop.time()
                refused = await client.post('/mcp', headers=headers, json=call(23))
                assert loop.time() - begun < gateway.FORWARD_WAIT_SECONDS
                assert refused.json() == {'jsonrpc': '2.0', 'id': 23, 'error': {
                    'code': -32003, 'message': router().pending_text(budget)}}
            finally:
                child.release_held.set()
                reading.set()
            for task in waiting:
                response = await asyncio.wait_for(task, 10)
                assert response.status_code == 200 and response.json()['result'] == {}
            for task, _ in held:
                await asyncio.wait_for(task, 10)
            assert gate.reply_bytes == 0


async def test_the_charge_is_given_back_however_a_request_ends(tmp_path, log_scan):
    """An answer handed over and then cut (the client leaves while the server waits: the task is cancelled) gives its
    charge back; a small answer is handed over whole (one message) and charged only until the server took it."""
    data, children, child = budget_setup(tmp_path, lambda name, directory: SizedChild(
        name, PRODUCT, directory, sizes={31: 300 * 1024, 33: 300 * 1024}, streams={33}))
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
                assert (gate.reply_bytes, gate.active, body_bytes(gate)) == (0, 0, 0)
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


# What a slow reader asks for, by content: the answers' text, the answers in turn (an id; whether it is an event stream
# whose request carries 4 MiB of that text as arguments, else a JSON answer), and the least of the byte budget the open
# streams still hold (their forwarded bodies). Emoji (HM-08 review section 9, HM-30 review S-1): the gateway serializes
# with ASCII escapes, so an emoji answer of 8 MiB is charged as about 24 MiB, and 4 MiB of emoji arguments are
# forwarded as about 12 MiB; two answers then pass the 32 MiB (the soft limit: the second one is handed over whole).
SLOW_READS = {
    'ascii': ('s', ((41, False), (42, False), (43, True), (44, True)), 2 * 4 * MiB),
    'emoji': (EMOJI, ((41, False), (43, True)), 3 * 4 * MiB),
}


@pytest.mark.parametrize('content', list(SLOW_READS))
async def test_a_slow_reader_holds_no_more_than_its_pending_reply_budget(tmp_path, log_scan, content):
    """contract 6 (慢讀用戶端), on the real listener (uvicorn, h11): B's client asks for 8 MiB answers one after another
    and never reads them, JSON answers and event streams whose requests carry 4 MiB of arguments (an open stream keeps
    its forwarded body: charged to B's share of the request body budget, HM-08, HM-31): ASCII, four of them; emoji, two
    (each charged as the gateway serializes it). Once they hold B's 32 MiB, B's next tools/call is answered 200 + -32003 at once and never forwarded;
    the default profile and C are served as before. The management process's RSS grows by at most B's pending replies
    32 MiB + one processing's amplification 200 MiB + 64 MiB = 296 MiB. When the client leaves, every byte is given back
    and B is served again."""
    fill, asked, forwarded = SLOW_READS[content]
    streams = {ident for ident, stream in asked if stream}
    eight = 8 * MiB
    # An event stream's reply: 8 MiB with its framing (data: and the blank line), the most a child may send (MAX_RESPONSE).
    sizes = {ident: eight - (8 if ident in streams else 0) for ident in range(41, 50)}

    def charge(ident):
        """What B's gate holds for the answer to ident: the gateway's own bytes for it, framed as an event or not."""
        answer = served(exact_reply(ident, sizes[ident], fill))
        return len(b'data: ' + answer + b'\n\n') if ident in streams else len(answer)
    data, children, child = budget_setup(tmp_path, lambda name, directory: SizedChild(
        name, PRODUCT, directory, sizes=sizes, streams=streams, fill=fill))
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
                assert warm.status_code == 200 and warm.content == served(exact_reply(49, eight, fill))
                del warm
                # The requests (an event stream's with 4 MiB of the text as arguments, sent as UTF-8) and what each
                # answer will hold, made before the RSS baseline: the test's own objects are not the gateway's.
                text = fill * (4 * MiB // len(fill.encode()))
                messages = {ident: json.dumps(call(ident, {**ARGUMENTS, 'filter': text} if stream else None),
                                              ensure_ascii=False).encode() for ident, stream in asked}
                charges = {ident: charge(ident) for ident, _ in asked}
                del text
                gc.collect()
                baseline = rss_bytes()
                charged = 0
                with RssPeak() as rss:
                    for number, (ident, _) in enumerate(asked, 1):
                        assert gate.reply_bytes < 32 * MiB  # B's tools/call is still forwarded
                        _, writer = await asyncio.open_connection('127.0.0.1', port)
                        writer.write(raw_post(port, token, session, messages[ident]))
                        await writer.drain()
                        writers.append(writer)
                        charged += charges[ident]
                        try:
                            await until(lambda: gate.reply_bytes >= charged, 30)
                        except TimeoutError:
                            raise AssertionError(('answer', number, 'charged', gate.reply_bytes, 'calls', child.tool_calls,
                                                  'active', gate.active)) from None
                    assert gate.reply_bytes == charged and charged >= 32 * MiB
                    assert body_bytes(gate) >= forwarded  # the open streams still hold their forwarded bodies
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
                print(f'HM-30 slow reader ({content}): B pending {gate.reply_bytes / MiB:.1f} MiB, byte budget '
                      f'{body_bytes(gate) / MiB:.1f} MiB, RSS growth {growth / MiB:.0f} MiB (contract 6: 296)')
                assert growth <= (32 + 200 + 64) * MiB, growth / MiB
                for writer in writers:
                    writer.close()
                await until(lambda: gate.reply_bytes == 0 and body_bytes(gate) == 0 and gate.active == 0, 20)
                again = await client.post('/mcp', headers=headers, json=call(49))
                assert again.status_code == 200 and again.content == served(exact_reply(49, eight, fill))
    finally:
        for writer in writers:
            writer.close()
