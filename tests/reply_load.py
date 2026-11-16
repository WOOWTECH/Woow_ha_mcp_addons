"""HM-30 test rig: one switched-on Odoo add-on whose default profile (A) gets many large replies while two additional
profiles (B, C) stay idle, with a controllable processing cost that holds the GIL as reply processing does
(multi-profile plan 5.5; contract 6; C2-MF-4).

- A's replies are 8 MiB and 2 MiB as received (contract 6: "A 並行 16 個 8 MiB 與 16 個 2 MiB 回覆"), sent in pieces of
  64 KiB with the loop running between them, as a socket delivers them (an in-process child handing the gateway 160 MiB
  at one instant would make the loop copy it all in one go, which no network does). Their content is padding the JSON
  scanner skips in short C calls, so what processing them costs is the injected cost alone:
  D (0.25 s) per 8 MiB, in proportion for any other size (contract 6: d = 0.25 s, against EPYC 7713's 0.28-0.47 s
  for one real 8 MiB reply). The runner's speed decides neither the cost nor the outcome. What a real reply's own
  C calls cost is measured apart (tests/test_reply_worker.py: the real 8 MiB reply).
- The injected cost is GilWork: single C calls of about UNIT_SECONDS each (json.loads of one long string, calibrated
  on the runner at the start), repeated until D of the thread's CPU time went by. sleep would give the GIL away and a
  pure Python loop gives it up every 5 ms (sys.getswitchinterval()): neither would stop the loop the way a reply does.
  Between its C calls it calls the parser's checkpoint when there is one (config.strict_json checkpoint: the reply
  worker's breathe, once per JSON object), as a real reply's parsing does between the objects it builds.
  It runs where the gateway parses a reply (gateway.strict_json, monkeypatched): on the event loop before HM-30 (the
  red phase), on the reply worker after it. Requests and B's and C's small replies carry none (INJECT_FROM).
- LoopLag samples the event loop's lateness (a 5 ms sleep, again and again): its largest value is the loop's
  longest stop while it runs.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import gc
import json
import math
import threading
import time

import httpx

from multi_profile_runtime import Children, create_profile, ids, multi_profile_runtime, stored
from mcp_admin_core import gateway, profiles
from test_profile_runtime import ProfileChild
from test_single_profile_golden import ACCEPT, configure, initialize_message

PRODUCT = 'odoo'
MiB = 1024 * 1024
D = 0.25                    # contract 6: the processing time of one 8 MiB reply, injected
UNIT_SECONDS = 0.01         # one GIL-holding C call of the injected cost
LARGE = 8 * MiB - 4096      # "8 MiB": within gateway.MAX_RESPONSE with its envelope
SMALL = 2 * MiB
INJECT_FROM = 64 * 1024     # only what is at least this large carries the injected cost
STALL_LIMIT = 0.050         # contract 6: the event loop's longest stop
B, C = ids(2)
LABELS = {B: 'Beta Ops', C: 'Gamma Ops'}
# A read tool the default policy allows and whose arguments the child validates (any object passes the gateway); not
# the readiness probe (list_models), which ProfileChild answers with the probe's own text.
TOOL, ARGUMENTS = 'search_records', {'model': 'res.partner', 'limit': 1}


class GilWork:
    """A processing cost that holds the GIL in single C calls of about `unit` seconds, until `seconds` of the calling
    thread's CPU time went by (time.thread_time: a thread that waits for the GIL spends none)."""

    def __init__(self, unit=UNIT_SECONDS):
        sample = '"' + 'a' * MiB + '"'
        per_mib = min(self._time(sample) for _ in range(5))
        size = int(min(max(unit / per_mib * MiB, 16 * 1024), 64 * MiB))
        self.document = '"' + 'a' * size + '"'
        self.unit = min(self._time(self.document) for _ in range(3))
        self.threads = set()  # the names of the threads that paid it
        self.paid = 0.0

    @staticmethod
    def _time(document):
        start = time.perf_counter()
        json.loads(document)
        return time.perf_counter() - start

    def __call__(self, seconds, checkpoint=None):
        self.threads.add(threading.current_thread().name)
        start = time.thread_time()
        deadline = start + seconds
        while time.thread_time() < deadline:
            json.loads(self.document)
            if checkpoint is not None:
                checkpoint()  # where the parser calls it too: between the C calls (reply_worker.breathe)
        self.paid += time.thread_time() - start


def injected(work, real):
    """gateway.strict_json with the injected cost first: D per 8 MiB of what it parses, when that is INJECT_FROM or
    more (a reply of A), else nothing. The parser's checkpoint (the reply worker gives one; the loop none) is also the
    injected cost's: it is called between its C calls, as the parser calls it between the objects it builds."""
    def strict_json(raw, **options):
        if len(raw) >= INJECT_FROM:
            work(D * len(raw) / (8 * MiB), options.get('checkpoint'))
        return real(raw, **options)
    return strict_json


PIECE = 64 * 1024  # how A's child sends a large reply: in pieces, the loop running between them (as a socket delivers)


def padded_reply(ident, size):
    """The pieces of a tools/call reply of exactly size bytes: a short result, then spaces up to its closing brace."""
    head = json.dumps({'jsonrpc': '2.0', 'id': ident, 'result': {
        'content': [{'type': 'text', 'text': 'a large answer'}], 'isError': False}}, separators=(',', ':')).encode()
    head = head[:-1]
    padding = size - len(head) - 1
    blank = b' ' * PIECE

    async def pieces():
        yield head
        for start in range(0, padding, PIECE):
            await asyncio.sleep(0)
            yield blank[:min(PIECE, padding - start)]
        yield b'}'
    return pieces()


class LargeChild(ProfileChild):
    """A's child: a tools/call whose id is in sizes gets a padded reply of that many bytes (JSON, sent in pieces), any
    other request as ProfileChild answers it. started is set when the first large reply was asked for; answered counts
    them."""

    def __init__(self, *args, sizes=None):
        super().__init__(*args)
        self.sizes = dict(sizes or {})
        self.started = asyncio.Event()
        self.answered = 0

    async def __call__(self, request):
        message = json.loads(request.content) if request.content else {}
        if message.get('method') == 'tools/call' and message.get('id') in self.sizes:
            token = json.loads(self.state.read_text())['child_token']
            assert request.headers.get_list('authorization') == ['Bearer ' + token]
            self.started.set()
            self.answered += 1
            return httpx.Response(200, headers={'content-type': 'application/json'},
                                  content=padded_reply(message['id'], self.sizes[message['id']]))
        return await super().__call__(request)


class LoopLag:
    """The event loop's lateness, sampled every `step` seconds while it runs: worst is its longest stop seen; lags every
    sample (HM-30 D1: the distribution the tests print, distribution())."""

    def __init__(self, step=0.005):
        self.step, self.worst, self.samples = step, 0.0, 0
        self.lags = []
        self._task = None

    async def _run(self):
        loop = asyncio.get_running_loop()
        while True:
            before = loop.time()
            await asyncio.sleep(self.step)
            lag = loop.time() - before - self.step
            self.worst = max(self.worst, lag)
            self.samples += 1
            self.lags.append(lag)

    def distribution(self):
        """p50, p90, p99 and the worst of the samples, in ms (text for a test's print)."""
        if not self.lags:
            return 'no samples'
        return (f'p50 {percentile(self.lags, 0.5) * 1000:.2f} p90 {percentile(self.lags, 0.9) * 1000:.2f} '
                f'p99 {percentile(self.lags, 0.99) * 1000:.2f} max {self.worst * 1000:.2f} ms ({self.samples} samples)')

    def start(self):
        self._task = asyncio.create_task(self._run())
        return self

    async def stop(self):
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)


def bearer(token):
    return {**ACCEPT, 'Authorization': 'Bearer ' + token}


def call(ident, arguments=None):
    return {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
            'params': {'name': TOOL, 'arguments': ARGUMENTS if arguments is None else arguments}}


async def session_of(client, token):
    response = await client.post('/mcp', headers=bearer(token), json=initialize_message())
    assert response.status_code == 200, response.status_code
    return response.headers['mcp-session-id']


async def until(condition, seconds=10, step=0.005):
    async with asyncio.timeout(seconds):
        while not condition():
            await asyncio.sleep(step)


def percentile(values, share):
    """The nearest-rank percentile (share 0.99: p99)."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def starvation_sizes(large=16, small=16):
    """A's request ids and their reply sizes: `large` replies of 8 MiB, then `small` of 2 MiB."""
    sizes = {ident: LARGE for ident in range(1, large + 1)}
    sizes.update({ident: SMALL for ident in range(large + 1, large + small + 1)})
    return sizes


def setup(tmp_path, sizes, child=ProfileChild):
    """An Odoo add-on on disk: the default profile (A) and B, C configured; children: A's LargeChild on 3000, B's and C's
    `child` (ProfileChild unless given) on 18000 and 18001."""
    data = tmp_path / 'data'
    configure(data, PRODUCT)
    for number, profile_id in enumerate((B, C)):
        create_profile(data, PRODUCT, profile_id, label=LABELS[profile_id], port=18000 + number)
    children = Children()
    children.add(3000, LargeChild('default', PRODUCT, data, sizes=sizes))
    for number, profile_id in enumerate((B, C)):
        children.add(18000 + number, child('p' + profile_id[:4], PRODUCT, profiles.Layout(data).profile(profile_id)))
    return data, children


def watch(log_scan, data):
    for directory in [data, *(profiles.Layout(data).profile(p) for p in (B, C))]:
        value = stored(directory)
        log_scan.watch(*(v for v in (value['token'], value['child_token']) if v))
    log_scan.watch(*LABELS.values(), kind='name')


@dataclass
class Starved:
    """What a starvation run saw: the injected cost; the loop's lag while A's replies were still arriving (reading: the
    loop takes 160 MiB in 64 KiB pieces, each read under the token lease, while the worker processes the first ones)
    and once every one of them was read and handed to the worker (lag: while they are processed). The tests hold lag to
    contract 6's threshold; whether reading is held to it too is the user's decision (HM-30 review D3), so they print
    it. The tasks of A's requests."""
    runtime: object
    work: GilWork
    reading: LoopLag
    lag: LoopLag
    a_tasks: list = field(default_factory=list)


async def _phases(run, child, total):
    """Ends the reading phase once every one of A's replies is read: handed to the worker (switched on with HM-30), or,
    before HM-30 (the red phase), answered by A's child (the loop then processes them itself)."""
    worker = getattr(run.runtime.manager, 'reply_worker', None)
    if worker is not None:
        await until(lambda: worker.handed['default'] >= total, 60)
    else:
        await until(lambda: child.answered >= total, 60)
    await run.reading.stop()
    run.lag.start()


@asynccontextmanager
async def starved(tmp_path, log_scan, monkeypatch, *, large=16, small=16, child=ProfileChild):
    """The runtime, switched on, with A's `large` 8 MiB and `small` 2 MiB requests sent at once once it serves; yields
    while they are answered (the caller drives B and C meanwhile; `child`: their children's class) and waits for them
    before it ends."""
    sizes = starvation_sizes(large, small)
    data, children = setup(tmp_path, sizes, child)
    work = GilWork()
    monkeypatch.setattr(gateway, 'strict_json', injected(work, gateway.strict_json))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        watch(log_scan, data)
        token = runtime.token('default')
        async with runtime.mcp(timeout=120) as client:
            headers = {**bearer(token), 'Mcp-Session-Id': await session_of(client, token)}
            # A full collection now, so that one of the test process's own (millions of objects in a full pytest run, far
            # more than an add-on holds) is not due while A's replies are processed: it holds the GIL however long it takes.
            gc.collect()
            run = Starved(runtime, work, LoopLag().start(), LoopLag())
            phases = None
            try:
                run.a_tasks = [asyncio.create_task(client.post('/mcp', headers=headers, json=call(ident)))
                               for ident in sizes]
                phases = asyncio.create_task(_phases(run, children.by_port[3000], len(sizes)))
                await until(lambda: children.by_port[3000].started.is_set(), 30)
                yield run
                answers = await asyncio.gather(*run.a_tasks)
                await asyncio.wait_for(phases, 30)
            finally:
                if phases is not None:
                    phases.cancel()
                    await asyncio.gather(phases, return_exceptions=True)
                await run.reading.stop()
                if run.lag._task is not None:
                    await run.lag.stop()
                for task in run.a_tasks:
                    task.cancel()
                await asyncio.gather(*run.a_tasks, return_exceptions=True)
        for response in answers:
            assert response.status_code == 200 and response.json()['result']['content'][0]['text'] == 'a large answer'
