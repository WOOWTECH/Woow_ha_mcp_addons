"""The container probe's multi-profile stage (multi-profile HM-16; plan 12.3 HM-16, 10.1; FM-101, FM-147; T-05, T-13,
T-14, T-21, T-23).

Run ONLY by packaging/container_probe.py, inside the disposable candidate container of container_acceptance, and ONLY
for a product whose multi-profile switch is on (features.enabled: a switched-on candidate, first HM-19a's throwaway
flag-on builder dry run). A product that is not switched on never gets here, and its probe path is the one before
HM-16 statement for statement (packaging/test_container_probe.py compares it with the reviewed one).

stage() runs after the probe's single-profile path, with the runtime stopped and the default profile configured on the
probe's own mock backend (for a switched-on product on the container's private address, as Headscale's: HM-20's
loopback rule):

1. Fixture, while stopped (the probe's rule: fixture state changes only while stopped). The restore marker that the
   single-profile restore stage left is removed, as the boot gate's last step removes it (HM-13a saves it, nothing
   removes it until HM-13b). The instance sentinel and its record are made as the runtime user by restore_detect.detect,
   which is what HM-13b's boot does at the first switched-on start (ESTABLISHED; before any profile data exists). Then
   two additional profiles are created with the library calls of the panel's creation (HM-10: profile_initial_state,
   ProductStore(create=...), the index; ports from 18000), configured on the default profile's mock backend, and given
   to the runtime user (the probe writes as root, as fixture_update does). The probe sends no management request: the
   container has no trusted Ingress and no HA role verifier, and the probe never bypasses them (the management API is
   tests/test_profile_admin_api.py's and, on HAOS, the P9 kit's temporary-profile mode's).
2. One start: every profile's child runs and listens on its own port (3000, 18000, 18001), on IPv4 loopback only.
3. Routing (T-05): each profile's token opens a session with its own child (a child's session, not the gateway's own)
   on both connection methods, and lists the same tools (the policy a creation copies, DQ-02); a session of one
   profile is unknown (404) with any other profile's token, on both methods; an unknown token gets 401 (Bearer) and 404
   (secret URL).
4. Child bearer (T-23, HM-06): each child serves its own child token only; none, a random one and every other
   profile's get 401 and no session.
5. Child resources (HM-09): an additional child's oom_score_adj is 500 and its nice value 5 above the management
   process's; the default child's are the management process's own.
6. A SIGKILL of one additional profile's child (T-13): the watchdog starts it again with a new PID; every other child
   keeps its PID and the killed profile serves again.
7. A stop: every child stopped at once and the management process exited 0 within HA's 30 s (measured, printed).
8. Nothing of it touched the sentinel (detect: CONSISTENT, no marker), and /data/mcp after the children ran is a tree
   the restore repair takes, within the layout's names and the repair's entry and depth budget (tree_snapshot).
9. A Supervisor-style restore of the whole multi-profile tree (the single-profile stage's restore_as_supervisor) and
   the start after it: the entrypoint saved its marker and gave every entry back to the runtime user, every state, the
   index and the instance record kept their bytes, and every profile's child started again; stopped, both restore
   signals are seen (detect: the marker and MISMATCH).

What HM-13b's boot gate changes in steps 1 and 9 (it removes the marker itself, makes the sentinel itself, and revokes
on the start after a restore) is listed in docs/provenance/ha-multiprofile-HM-16-20261116.md. Fixed messages only: no
token, child token, label, state or backend value is ever printed; a profile is named by its log id (profiles.log_id).
"""
import asyncio
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import stat
import subprocess
import sys
import time

import httpx

import entrypoint  # the restore repair's limits: packaging/entrypoint.py, the file every image copies
from mcp_admin_core import profiles, restore_detect
from mcp_admin_core.health import protocol_reply
from mcp_admin_core.lifecycle import CHILD_PORT, EXTRA_CHILD_RESOURCES
from mcp_admin_core.migration import OWNER_RECOVERY
from mcp_admin_core.products import ProductStore, allowed_address, profile_initial_state

RUNTIME = (entrypoint.UID, entrypoint.GID)
EXTRA_PROFILES = 2  # plan 12.3 HM-16: the default profile and two additional ones
LABELS = ('Probe B', 'Probe C')  # synthetic, never printed (I7)
MCP = 'http://127.0.0.1:8081'
ACCEPT = {'Accept': 'application/json, text/event-stream'}
LOCAL_SESSION = 'woow-local-'  # the gateway's own sessions (gateway.local_initialize): no child answered
STOP_SECONDS = 30  # HA's stop timeout: Supervisor kills the add-on after it (plan 5.4; contract 7)
UP_SECONDS = 60  # the default child, then the additional ones (start_all: at most two starting at once)
RESTART_SECONDS = 40  # the watchdog's first delay is 2 s (lifecycle.WATCHDOG), then the child's own start
BACKEND_FIELDS = ('connection', 'backend_url', 'backend_key')  # what a profile's backend is (n8n: url and key)

# The layout's names (plan 4.1; profiles.py, operations.py, migration.py): what /data/mcp may hold once the children
# ran. A profile directory holds its state, writer lock, operation journal and the child's empty working directory.
JOURNAL = '.state.json.operations.json'  # operations.OperationJournal beside state.json
PROFILE_NAMES = frozenset({'state.json', '.writer.lock', JOURNAL, 'child'})
TOP_NAMES = PROFILE_NAMES | {OWNER_RECOVERY, profiles.INDEX_NAME, profiles.INDEX_OPERATIONS_NAME, profiles.PROFILES_NAME,
                             profiles.SENTINEL_NAME, profiles.INSTANCE_RECORD_NAME,
                             profiles.INSTANCE_RECORD_TEMPORARY_NAME, profiles.RESTORE_MARKER_NAME,
                             profiles.REVOKE_ALL_MARKER_NAME, profiles.RESTORE_RECORD_NAME}
DIRECTORIES = frozenset({'child', profiles.PROFILES_NAME})
INDEX_QUARANTINE = re.compile(re.escape(profiles.INDEX_NAME) + r'\.quarantine-[0-9]{8}T[0-9]{6}Z(?:-[0-9]{1,3})?')
MAX_FILE_BYTES = 1024 * 1024  # as the single-profile fixture_snapshot

DETECT = '''import json, sys
from pathlib import Path
from mcp_admin_core import restore_detect
found = restore_detect.detect(Path(sys.argv[1]), enabled=True)
print(json.dumps({"marker": found.marker, "active": found.active, "sentinel": found.sentinel}))
'''


def private_mock_host():
    """The address a switched-on product's mock backend listens on: this container's private address on
    container_acceptance's one-use internal bridge (HM-20 review MF-2: the product's every child refuses a loopback
    backend; tests/loopback_backends.py, the test double, is in no image). The rule of Headscale's mock address."""
    host = socket.gethostbyname(socket.gethostname())
    address = ipaddress.ip_address(host)
    assert (address.version == 4 and address.is_private and not address.is_loopback
            and not address.is_link_local and allowed_address(host)), 'switched-on mock needs private bridge IP'
    return host


# ---- /data/mcp as a switched-on product leaves it ----

def _designed(parts, directory):
    """Whether a name at this place of the tree is the layout's (plan 4.1), as the kind of entry it is."""
    name = parts[-1]
    if len(parts) == 1:
        if INDEX_QUARANTINE.fullmatch(name):
            return not directory
        return name in TOP_NAMES and (name in DIRECTORIES) == directory
    if parts[0] != profiles.PROFILES_NAME:
        return False
    if len(parts) == 2:
        return directory and (profiles.is_profile_id(name) or profiles.parse_quarantine_name(name) is not None)
    if len(parts) == 3:
        return name in PROFILE_NAMES and (name == 'child') == directory
    return False


def tree_snapshot(data):
    """fixture_snapshot for a switched-on product (C4-SF-5; FM-16, FM-101): the single-profile rule (a bounded, private
    synthetic fixture of regular files) widened to the multi-profile layout, and nothing more.

    Every entry is a plain directory or a single-link regular file (at most 1 MiB) on /data/mcp's filesystem, the
    runtime user's and private (0700, 0600), at a name the layout gives it; every child working directory is empty (a
    child that leaves a file there does not start again: products.child_spec); the whole tree is within the restore
    repair's entry and depth limits (packaging/entrypoint.py: a backup of it restores). Returns {relative path: (inode,
    uid, gid, mode, size, mtime_ns, ctime_ns, sha256 of a file's bytes or None)}. Never log its contents or hashes."""
    data = Path(data)
    device = os.lstat(data).st_dev
    found = {}
    walk = [((), 0)]
    while walk:
        parts, depth = walk.pop()
        listed = []
        with os.scandir(data.joinpath(*parts)) as entries:
            for entry in entries:
                listed.append(entry.name)
                assert len(found) + len(listed) <= entrypoint.MAX_RESTORED_ENTRIES, 'tree over the repair budget'
        for name in sorted(listed):
            path = (*parts, name)
            info = os.lstat(data.joinpath(*path))
            directory = stat.S_ISDIR(info.st_mode)
            assert depth <= entrypoint.MAX_RESTORED_DEPTH, 'tree deeper than the repair goes'
            assert info.st_dev == device, 'tree crosses a filesystem'
            assert directory or (stat.S_ISREG(info.st_mode) and info.st_nlink == 1), 'not a plain entry'
            assert (info.st_uid, info.st_gid) == RUNTIME, "not the runtime user's"
            assert stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600), 'not private'
            assert _designed(path, directory), 'not a name of the layout'
            if directory:
                if name == 'child':
                    with os.scandir(data.joinpath(*path)) as inside:
                        assert next(inside, None) is None, 'child working directory not empty'
                walk.append((path, depth + 1))
                digest = None
            else:
                assert info.st_size <= MAX_FILE_BYTES, 'oversize entry'
                digest = hashlib.sha256(data.joinpath(*path).read_bytes()).hexdigest()
            found['/'.join(path)] = (info.st_ino, info.st_uid, info.st_gid, info.st_mode, info.st_size,
                                     info.st_mtime_ns, info.st_ctime_ns, digest)
    return found


# ---- the fixture (only while stopped) ----

def end_restore_marker(data):
    """The marker the single-profile restore stage left goes, as the boot gate's last step removes it (HM-13a: nothing
    removes it yet). Once HM-13b's gate is merged it is gone already, and this check fails on purpose."""
    marker = Path(data) / profiles.RESTORE_MARKER_NAME
    assert os.path.lexists(marker), 'the single-profile restore stage left no marker'
    os.unlink(marker)


def _child_environment():
    """What the runtime user's detection needs to import mcp_admin_core (the image's, or the checkout's)."""
    return {'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONPATH': str(Path(restore_detect.__file__).resolve().parents[1])}


def detect_as_runtime(data, *, user=RUNTIME):
    """restore_detect.detect(data, enabled=True) as the add-on's management process runs it: as the runtime user (the
    sentinel and its record are its files: a chown afterwards would change the sentinel's ctime), while stopped. It
    makes the two files the first time. Returns the verdict only: {"marker", "active", "sentinel"}. user None: as this
    process (the packaging tests)."""
    options = {} if user is None else {'user': user[0], 'group': user[1], 'extra_groups': []}
    result = subprocess.run([sys.executable, '-c', DETECT, str(data)], capture_output=True, text=True, timeout=60,
                            cwd='/', env=_child_environment(), check=False, **options)
    assert result.returncode == 0, 'restore detection failed'
    return json.loads(result.stdout)


def detected(marker, sentinel):
    return {'marker': marker, 'active': True, 'sentinel': sentinel}


def create_profiles(probe, count=EXTRA_PROFILES):
    """*count* additional profiles as the panel's creation makes them (HM-10; plan 4.3): each born complete with
    profile_initial_state (new tokens no other profile has, the default profile's policy now, no backend), then given
    the default profile's backend, then appended to the index, ports from 18000. The probe writes as root, so every
    entry it made is given to the runtime user afterwards (fixture_update's rule). Returns [(profile id, port)]."""
    data = Path(probe.DATA)
    layout = profiles.Layout(data)
    default = probe.fixture_update()
    backend = {name: value for name, value in default.model_dump().items() if name in BACKEND_FIELDS and value}
    assert backend, 'the default profile has no backend to share'
    created, taken = [], {default.token, default.child_token}
    profiles.ensure_profiles_directory(layout)
    for number in range(count):
        view = profiles.read_index(layout.index)
        assert view.state in (profiles.INDEX_ABSENT, profiles.INDEX_OK), 'profile index unavailable'
        profile_id = profiles.new_profile_id({entry.id for entry in view.entries})
        port = profiles.allocate_port({entry.port for entry in view.entries})
        state = profile_initial_state(default, taken=taken)
        taken |= {state.token, state.child_token}
        ProductStore(layout.profile(profile_id), default.product, create=state).close()
        store = ProductStore(layout.profile(profile_id), default.product, existing_only=True)
        try:
            store.update(**backend)
        finally:
            store.close()
        profiles.write_index(layout.index, [*view.entries, profiles.IndexEntry(profile_id, LABELS[number], port)],
                             expected=view)
        created.append((profile_id, port))
    for path in (layout.index, layout.profiles, *sorted(layout.profiles.rglob('*'))):
        os.chown(path, *RUNTIME)
    return created


def credentials(data, created):
    """[(log id, child port, token, child token)]: the default profile first, then the created ones in index order. Read
    only from this disposable fixture; never printed."""
    layout = profiles.Layout(Path(data))
    found = []
    for profile_id, port in [(profiles.DEFAULT_PROFILE, CHILD_PORT), *created]:
        directory = layout.root if profile_id == profiles.DEFAULT_PROFILE else layout.profile(profile_id)
        state = json.loads((directory / 'state.json').read_text())
        found.append((profiles.log_id(profile_id), port, state['token'], state['child_token']))
    return found


def kept_bytes(data, created):
    """The bytes a restore must give back as they were: every profile's state, the index and the instance record."""
    layout = profiles.Layout(Path(data))
    paths = [layout.root / 'state.json', *(layout.profile(profile_id) / 'state.json' for profile_id, _ in created),
             layout.index, layout.instance_record]
    return {str(path.relative_to(layout.root)): path.read_bytes() for path in paths}


# ---- the running children ----

def child_port(argv):
    """The port a child's command line names (--port N or --port=N), or None (the default child of Hermes and
    OpenDesign runs on its launcher's own default, CHILD_PORT; an additional child's exec wrapper carries the real
    command line, so it names the port too)."""
    for index, value in enumerate(argv):
        if value == '--port' and index + 1 < len(argv) and argv[index + 1].isdigit():
            return int(argv[index + 1])
        if value.startswith('--port=') and value[7:].isdigit():
            return int(value[7:])
    return None


def child_ports(probe, process, proc=Path('/proc')):
    """{port: PID} of the management process's children, by their command lines (world-readable, as the P9 kit's).
    A child that is gone, or exited and not reaped yet (a zombie's command line is empty), is left out. Two children
    naming the same port fail."""
    found = {}
    for pid in probe.children(process):
        try:
            raw = (proc / pid / 'cmdline').read_bytes()
        except OSError:
            continue  # gone already (a watchdog restart in between)
        if not raw:
            continue  # exited, not reaped yet
        port = child_port(raw.decode('utf-8', 'replace').split('\0'))
        port = CHILD_PORT if port is None else port
        assert port not in found, 'two children on one port'
        found[port] = int(pid)
    return found


def listeners(proc=Path('/proc')):
    """{port: [local address hex]} of every listening TCP socket of this network namespace (/proc/net/tcp, tcp6)."""
    found = {}
    for name in ('tcp', 'tcp6'):
        try:
            rows = (proc / 'net' / name).read_text().splitlines()[1:]
        except OSError:
            continue  # no IPv6
        for row in rows:
            fields = row.split()
            if len(fields) > 3 and fields[3] == '0A':
                address, _, port = fields[1].rpartition(':')
                found.setdefault(int(port, 16), []).append(address)
    return found


async def profiles_up(probe, process, ports, *, timeout=UP_SECONDS, proc=Path('/proc'), pause=.25):
    """Wait until exactly the children of *ports* run, each listening on its own port on IPv4 loopback only (as the
    default child's 3000, container_probe); {port: PID}."""
    wanted = sorted(ports)
    async with asyncio.timeout(timeout):
        while True:
            assert process.poll() is None, 'packaged entrypoint exited'
            found = child_ports(probe, process, proc)
            listening = listeners(proc)
            if sorted(found) == wanted and all(listening.get(port) == ['0100007F'] for port in wanted):
                return found
            await asyncio.sleep(pause)


def stat_fields(pid, proc=Path('/proc')):
    """(oom_score_adj, nice) of a process (world-readable)."""
    adj = int((proc / str(pid) / 'oom_score_adj').read_text())
    fields = (proc / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
    return adj, int(fields[16])  # field 19 of proc(5), the 17th after the command name


def check_resources(process, pids, proc=Path('/proc')):
    """HM-09 in the real container: an additional child (any port but CHILD_PORT) has oom_score_adj 500 and its nice
    value raised by 5 from the management process's; the default child keeps the management process's own."""
    adj, nice = stat_fields(process.pid, proc)
    for port, pid in pids.items():
        if port == CHILD_PORT:
            assert stat_fields(pid, proc) == (adj, nice), 'default child resources changed'
        else:
            assert stat_fields(pid, proc) == (EXTRA_CHILD_RESOURCES.oom_score_adj, nice + EXTRA_CHILD_RESOURCES.nice), \
                'additional child resources not applied'


async def kill_one(probe, process, port, *, timeout=RESTART_SECONDS, proc=Path('/proc'), kill=os.kill, pause=.25):
    """SIGKILL the child on *port* (T-13): the watchdog starts it again with a new PID, listening again; every other
    child keeps its PID throughout. Returns the children after it {port: PID}."""
    before = child_ports(probe, process, proc)
    target = before[port]
    kill(target, signal.SIGKILL)
    async with asyncio.timeout(timeout):
        while True:
            assert process.poll() is None, 'packaged entrypoint exited'
            now = child_ports(probe, process, proc)
            assert all(now.get(other) in (None, pid) for other, pid in before.items() if other != port), \
                "another profile's child was restarted"
            if now.get(port) not in (None, target) and listeners(proc).get(port) == ['0100007F'] \
                    and all(now.get(other) == pid for other, pid in before.items() if other != port):
                return now
            await asyncio.sleep(pause)


def stop_within(probe, process, *, seconds=STOP_SECONDS, clock=time.monotonic, proc=Path('/proc')):
    """Stop the add-on as HA does (SIGTERM, then a kill after 30 s): it must exit 0 within the 30 s with every child
    reaped (stop_all stops them at once). Returns the seconds it took."""
    owned = probe.children(process)
    begin = clock()
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise AssertionError("multi-profile shutdown over HA's 30 s") from None
    elapsed = clock() - begin
    assert elapsed < seconds, "multi-profile shutdown over HA's 30 s"
    assert process.returncode == 0, 'multi-profile shutdown failed'
    assert all(not (proc / pid).exists() for pid in owned), 'orphan child'
    return elapsed


# ---- requests ----

def initialize_message():
    return {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
        'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'container-mock', 'version': '1'}}}


async def initialize_on(client, url, headers, message):
    """initialize; (status, session id, protocol version): the latter two None unless it was answered."""
    async with client.stream('POST', url, headers={**ACCEPT, **headers}, json=message) as response:
        if response.status_code != 200:
            await response.aread()
            return response.status_code, None, None
        session = response.headers.get('mcp-session-id')
        result = await protocol_reply(response, message['id'])
    return 200, session, result['protocolVersion']


async def tools_on(client, url, headers, session, version):
    """tools/list in a session: (status, sorted tool names, or None unless it was answered)."""
    message = {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}
    headers = {**ACCEPT, **headers, 'Mcp-Session-Id': session, 'MCP-Protocol-Version': version}
    async with client.stream('POST', url, headers=headers, json=message) as response:
        if response.status_code != 200:
            await response.aread()
            return response.status_code, None
        result = await protocol_reply(response, message['id'])
    return 200, sorted(tool['name'] for tool in result['tools'])


async def end_session(client, url, headers, session, version):
    """DELETE the session; its status, 0 when there was no answer."""
    try:
        response = await client.delete(url, headers={**headers, 'Mcp-Session-Id': session,
                                                     'MCP-Protocol-Version': version})
    except httpx.HTTPError:
        return 0
    return response.status_code


async def check_routing(client, profiles_tokens, message, base=MCP):
    """T-05 on the real 8081 (see the module docstring). profiles_tokens: [(log id, token)]. Every session it opens is
    ended, also when a check fails. Fixed messages only, a profile named by its log id."""
    def methods(token):
        return ((base + '/mcp', {'Authorization': 'Bearer ' + token}), (f'{base}/private_{token}/mcp', {}))
    opened, listings, ended = [], {}, []
    try:
        for label, token in profiles_tokens:
            for url, headers in methods(token):
                status, session, version = await initialize_on(client, url, headers, message)
                assert status == 200 and session, f'{label}: its token opened no session'
                opened.append((label, token, url, headers, session, version))
                assert not session.startswith(LOCAL_SESSION), f"{label}: no child answered its initialize"
                status, names = await tools_on(client, url, headers, session, version)
                assert status == 200 and names, f'{label}: tools/list unanswered'
                listings.setdefault(label, names)
                assert listings[label] == names, f'{label}: its two connection methods list differently'
        first = listings[profiles_tokens[0][0]]
        assert all(names == first for names in listings.values()), "a profile's policy differs from the default's"
        for label, _, _, _, session, version in opened:
            for other, token in profiles_tokens:
                if other == label:
                    continue
                for url, headers in methods(token):
                    status, _ = await tools_on(client, url, headers, session, version)
                    assert status == 404, f'{label} session served with the token of {other}'
        unknown = secrets.token_urlsafe(32)
        for (url, headers), refusal, failure in zip(methods(unknown), (401, 404),
                                                    ('unknown Bearer token served', 'unknown secret URL served')):
            status, session, version = await initialize_on(client, url, headers, message)
            if session:
                opened.append(('unknown token', unknown, url, headers, session, version))  # ended below all the same
            assert status == refusal, failure
    finally:
        for label, _, url, headers, session, version in opened:
            ended.append((label, await end_session(client, url, headers, session, version)))
    for label, status in ended:
        assert status in (200, 204), f'{label}: its session was not ended'


async def check_child_bearers(probe, client, children, message):
    """T-23 on every profile's real child (HM-06's assert_child_bearer: none and a random token get 401, the own one a
    session, ended), and each other profile's child token gets 401 and no session too. children: [(log id, port, child
    token)]."""
    for label, port, own in children:
        url = f'http://127.0.0.1:{port}/mcp'
        await probe.assert_child_bearer(client, own, message, url=url)
        for other, _, token in children:
            if other == label:
                continue
            response = await client.post(url, headers={**ACCEPT, 'Authorization': 'Bearer ' + token}, json=message)
            assert response.status_code == 401 and 'mcp-session-id' not in response.headers, \
                f"{label}: child served the child token of {other}"


async def stage(probe, client):
    """The multi-profile stage (the module docstring's steps 1 to 9); prints one line of numbers, no secret."""
    data = Path(probe.DATA)
    message = initialize_message()
    end_restore_marker(data)
    assert detect_as_runtime(data) == detected(False, restore_detect.ESTABLISHED), 'sentinel not established'
    created = create_profiles(probe)
    found = credentials(data, created)
    ports = [port for _, port, _, _ in found]
    process = probe.start()
    try:
        await probe.ready_listener(client, process)
        began = time.monotonic()
        pids = await profiles_up(probe, process, ports)
        up = time.monotonic() - began
        await check_routing(client, [(label, token) for label, _, token, _ in found], message)
        await check_child_bearers(probe, client, [(label, port, child) for label, port, _, child in found], message)
        check_resources(process, pids)
        label, port, token, _ = found[1]
        await kill_one(probe, process, port)
        status, session, version = await initialize_on(client, MCP + '/mcp', {'Authorization': 'Bearer ' + token},
                                                       message)
        assert status == 200 and session and not session.startswith(LOCAL_SESSION), f'{label}: not served again'
        await end_session(client, MCP + '/mcp', {'Authorization': 'Bearer ' + token}, session, version)
        stopped = stop_within(probe, process)
        process = None
    finally:
        if process is not None and process.poll() is None:
            probe.stop(process)
    assert detect_as_runtime(data) == detected(False, restore_detect.CONSISTENT), 'sentinel touched by the runtime'
    entries = len(tree_snapshot(data))
    kept = kept_bytes(data, created)
    restored, state = probe.restore_as_supervisor()
    process = probe.start()
    try:
        await probe.ready_listener(client, process)
        probe.check_restored_start(restored, state)
        assert kept_bytes(data, created) == kept, 'restored profile data rewritten'
        await profiles_up(probe, process, ports)
        stop_within(probe, process)
        process = None
    finally:
        if process is not None and process.poll() is None:
            probe.stop(process)
    assert detect_as_runtime(data) == detected(True, restore_detect.MISMATCH), 'restore not seen by both signals'
    print(f'PASS multi-profile: default + {len(created)} profiles up in {up:.1f} s; routing, child bearer, resources, '
          f'SIGKILL, stop in {stopped:.1f} s; {entries} entries; restore tree and both signals')
