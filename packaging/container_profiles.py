"""The container probe's multi-profile stage (multi-profile HM-16; plan 12.3 HM-16, 10.1; FM-101, FM-147; T-05, T-13,
T-14, T-21, T-23).

Run ONLY by packaging/container_probe.py, inside the disposable candidate container of container_acceptance, and ONLY
for a product whose multi-profile switch is on (features.enabled: a switched-on candidate, first HM-19a's throwaway
flag-on builder dry run). A product that is not switched on never gets here, and its probe path is the one before
HM-16 statement for statement (packaging/test_container_probe.py compares it with the reviewed one).

stage() runs after the probe's single-profile path, with the runtime stopped and the default profile configured on the
probe's own mock backend (for a switched-on product on the container's private address, as Headscale's: HM-20's
loopback rule):

1. Fixture, while stopped (the probe's rule: fixture state changes only while stopped). The single-profile path handled
   its restore already: the boot guard of that stage's start (HM-13b) removed the entrypoint's marker, and the instance
   sentinel and its record are the runtime's own (made by the guard's restore_detect.detect at the product's first
   switched-on start, before any profile data existed; rebuilt by the guard after that restore): detect, run as the
   runtime user, finds no marker and them CONSISTENT, and makes nothing. Then two additional profiles are created with
   the library calls of the panel's creation (HM-10: profile_initial_state, ProductStore(create=...), the index; ports
   from 18000), configured on the default profile's mock backend, and given to the runtime user (the probe writes as
   root, as fixture_update does). The probe sends no management request: the
   container has no trusted Ingress and no HA role verifier, and the probe never bypasses them (the management API is
   tests/test_profile_admin_api.py's and, on HAOS, the P9 kit's temporary-profile mode's).
2. One start: every profile's child runs and listens on its own port (3000, 18000, 18001), on IPv4 loopback only.
3. Routing (T-05): each profile's token opens a session with its own child on both connection methods: a child's
   session, not the gateway's own, and asked straight with each child's own child token, only that profile's child
   knows it (the gateway hands out the child's own session id; every other child answers 404: a consistent swap of two
   profiles' children is seen, HM-16 review SF-1). Both methods list the same tools, and so do the three profiles (the
   policy a creation copies, DQ-02); a session of one profile is unknown (404) with any other profile's token, on both
   methods; an unknown token gets 401 (Bearer) and 404 (secret URL).
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
   the start after it, whose stderr is read back once it stopped (container_probe.check_restore_log). With profile data
   on disk the boot guard revokes every profile, the default profile's included (DQ-03 (b) A2; plan 8.4 A-F; HM-13b):
   the entrypoint gave every restored entry back to the runtime user and said so once; the guard removed the marker and
   the single-profile stage's restore notice (no longer true, HM-13c), wrote restore-record.json (both signals, every
   profile revoked) and said REVOKED once for each profile and REVOKED_NOTICE once, and none of its other lines (HM-16's
   second review); every profile's token is None with one more history entry and its child token new, nothing else of
   a state changed, nor the index; every profile's child started again; no credential from before the restore is
   served (each token on both connection methods, each child token by its child). Stopped: the sentinel was rebuilt
   (detect: no marker, CONSISTENT), and what the guard left is still a tree the repair takes (tree_snapshot: the
   record, new journals, the Origin policy's included (HM-27), archived receipts).

Fixed messages only: no token, child token, label, state or backend value is ever printed; a profile is named by its
log id (profiles.log_id).

Not for n8n yet (HM-25, review SF-2): its child names its port only in its environment (PORT, beside its tokens), never
on its command line, so the children cannot be told apart by their command lines; stage() refuses n8n before it
changes anything. Reading another user's /proc/<pid>/fd links as root takes CAP_SYS_PTRACE, which docker gives no
container by default (not measured here). n8n's switch-on slice gives its child a port the probe can read without its
environment, and checks tree_snapshot's names against what n8n-mcp leaves in its directory (its HOME).
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
import tempfile
import time

import httpx

import entrypoint  # the restore repair's limits: packaging/entrypoint.py, the file every image copies
from mcp_admin_core import operations, profiles, restore_detect, restore_lock
from mcp_admin_core.config import ConfigError
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
# ran and the boot guard handled a restore (HM-13b, HM-13c, HM-27). A profile directory holds its state, writer lock,
# operation journal (and the journal a restore archived) and the child's empty working directory.
JOURNAL = operations.journal_path(Path('state.json')).name  # operations.OperationJournal beside state.json
# The receipts a restore archived (operations.archive_for_restore; HM-13b): beside every profile's state.json, the
# default profile's included, and beside the index; HM-27: beside the add-on's Origin policy too.
JOURNAL_ARCHIVE, INDEX_JOURNAL_ARCHIVE, ORIGIN_JOURNAL_ARCHIVE = profiles.RECEIPT_ARCHIVE_NAMES
PROFILE_NAMES = frozenset({'state.json', '.writer.lock', JOURNAL, JOURNAL_ARCHIVE, 'child'})
TOP_NAMES = PROFILE_NAMES | {OWNER_RECOVERY, profiles.INDEX_NAME, profiles.INDEX_OPERATIONS_NAME, INDEX_JOURNAL_ARCHIVE,
                             profiles.PROFILES_NAME, profiles.SENTINEL_NAME, profiles.INSTANCE_RECORD_NAME,
                             profiles.INSTANCE_RECORD_TEMPORARY_NAME, profiles.RESTORE_MARKER_NAME,
                             profiles.REVOKE_ALL_MARKER_NAME, profiles.RESTORE_RECORD_NAME,
                             profiles.RESTORE_NOTICE_NAME,  # HM-13c: a restore that kept the token (single profile)
                             # HM-27: the add-on's Origin policy of the secret path (only the panel saves it; a restore
                             # leaves it as the backup had it) and the receipts of its saves, which the boot guard
                             # archives as the index's and writes anew at every restore it handles, also where the
                             # backup had none
                             profiles.ORIGIN_POLICY_NAME, profiles.ORIGIN_POLICY_OPERATIONS_NAME,
                             ORIGIN_JOURNAL_ARCHIVE}
# What the guard's revocation writes in a state (ProductStore.change_token, then a new child token): nothing else.
REVOKED_FIELDS = ('token', 'child_token', 'token_history')
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

def check_marker_ended(data):
    """The marker of the single-profile restore stage is gone: the boot guard of that stage's start removed it as its
    last step (HM-13b; container_probe.check_restored_start saw that), and nothing made one since. Nothing is removed
    here (before HM-13b the probe removed it itself)."""
    assert not os.path.lexists(Path(data) / profiles.RESTORE_MARKER_NAME), 'a restore marker left before the stage'


def _child_environment():
    """What the runtime user's detection needs to import mcp_admin_core (the image's, or the checkout's)."""
    return {'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONPATH': str(Path(restore_detect.__file__).resolve().parents[1])}


def detect_as_runtime(data, *, user=RUNTIME):
    """restore_detect.detect(data, enabled=True) as the add-on's management process runs it: as the runtime user (the
    sentinel and its record are its files: a chown afterwards would change the sentinel's ctime), while stopped. Where
    there are none yet it makes the two files (ESTABLISHED), as the runtime's first switched-on start does; the stage
    expects the runtime to have made them (CONSISTENT), so the files it would make here only come with a failure.
    Returns the verdict only: {"marker", "active", "sentinel"}. user None: as this process (the packaging tests)."""
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


def restore_picture(data, created):
    """What the start after the multi-profile restore is checked against (check_revoked_restore): ({every profile's
    state.json, relative to /data/mcp: its content}, the default profile's first; the index's bytes). Read only from
    this disposable fixture; never printed."""
    layout = profiles.Layout(Path(data))
    paths = [layout.root / 'state.json', *(layout.profile(profile_id) / 'state.json' for profile_id, _ in created)]
    return ({str(path.relative_to(layout.root)): json.loads(path.read_bytes()) for path in paths},
            layout.index.read_bytes())


# ---- the start after the multi-profile restore (DQ-03 (b) A2; plan 8.4 A-F; HM-13b, HM-13c) ----

def check_restore_files(data, restored, created):
    """Its files, as container_probe.check_restored_start checks the single-profile ones: the boot guard removed the
    marker; the entrypoint gave every restored entry back to the runtime user (directories 0700, files 0600), and the
    restore notice of the single-profile stage is the one restored entry the guard removed (the default profile's token
    was revoked: the notice would not be true, HM-13c); the sentinel, its record and restore-record.json are single-link
    files of the runtime user, 0600, and the record is as the guard writes it (restore_lock.check_record), with both
    restore signals and every profile revoked."""
    data = Path(data)
    assert not os.path.lexists(data / profiles.RESTORE_MARKER_NAME), \
        'restore marker left: the boot guard did not handle the restore'
    for name in restored:
        if not os.path.lexists(data / name):
            assert name == profiles.RESTORE_NOTICE_NAME, 'a restored entry gone'
            continue
        info = os.lstat(data / name)
        mode = 0o700 if stat.S_ISDIR(info.st_mode) else 0o600
        assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (*RUNTIME, mode), 'restore not repaired'
    assert not os.path.lexists(data / profiles.RESTORE_NOTICE_NAME), 'a restore notice although every token was revoked'
    for name in (profiles.SENTINEL_NAME, profiles.INSTANCE_RECORD_NAME, profiles.RESTORE_RECORD_NAME):
        assert os.path.lexists(data / name), 'restore files missing'
        info = os.lstat(data / name)
        assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'restore files not files'
        assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (*RUNTIME, 0o600), 'restore files not private'
    try:
        record = restore_lock.check_record(json.loads((data / profiles.RESTORE_RECORD_NAME).read_bytes()))
    except (ValueError, ConfigError):
        raise AssertionError('restore record not as the boot guard writes it') from None
    assert (record['restore'] is not None and record['restore']['marker'] is True
            and record['restore']['sentinel'] == restore_detect.MISMATCH), 'restore record without both signals'
    ids = [profiles.DEFAULT_PROFILE, *(profile_id for profile_id, _ in created)]
    assert sorted((row['id'], row['token']) for row in record['profiles']) == sorted((i, 'revoked') for i in ids), \
        'restore record without every profile revoked'


def check_revoked(before, after):
    """DQ-03 (b) A2 for every profile's state, the default profile's included ({state.json path: content} before the
    restore and after its start, restore_picture's): each token None, with one history entry (revoke) before the ones
    it had; each child token new, none that any profile had before and none shared; nothing else changed."""
    assert sorted(after) == sorted(before), 'a profile state missing after the restore'
    held = {state.get(name) for state in before.values() for name in ('token', 'child_token')}
    renewed = [state.get('child_token') for state in after.values()]
    for path, old in before.items():
        new = after[path]
        assert new.get('token') is None, 'a token not revoked by the restore'
        history = new.get('token_history') or []
        assert (len(history) >= 1 and history[0].get('action') == 'revoke'
                and history[1:] == (old.get('token_history') or [])[:4]), 'token history not one revocation more'
        assert ({name: value for name, value in new.items() if name not in REVOKED_FIELDS}
                == {name: value for name, value in old.items() if name not in REVOKED_FIELDS}), \
            'restored profile data rewritten'
    assert (all(isinstance(value, str) and value not in held for value in renewed)
            and len(set(renewed)) == len(renewed)), 'a child token not renewed'


def check_revoked_restore(data, restored, before, created):
    """Step 9's files once the runtime serves (check_restore_files), every profile's state against *before*
    (restore_picture before the restore; check_revoked), and the index as restored (the guard never writes it)."""
    check_restore_files(data, restored, created)
    states, index = restore_picture(data, created)
    check_revoked(before[0], states)
    assert index == before[1], 'restored profile index rewritten'


# ---- the running children ----

def child_port(argv):
    """The port a child's command line names (--port N or --port=N), or None (the default child of Hermes and
    OpenDesign runs on its launcher's own default, CHILD_PORT; an additional child's exec wrapper carries the real
    command line, so it names the port too). n8n's child names none (its port is in its environment: module
    docstring)."""
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
    found, listening = {}, {}
    try:
        async with asyncio.timeout(timeout):
            while True:
                assert process.poll() is None, 'packaged entrypoint exited'
                found = child_ports(probe, process, proc)
                listening = listeners(proc)
                if sorted(found) == wanted and all(listening.get(port) == ['0100007F'] for port in wanted):
                    return found
                await asyncio.sleep(pause)
    except TimeoutError:
        # Ports only (a profile's child that never starts: e.g. an open file limit below open_file_budget's, or a
        # child that refuses its backend). The runtime's own lines are not shown: the probe never prints them.
        up = [port for port in wanted if found.get(port) and listening.get(port) == ['0100007F']]
        raise AssertionError(f'children up on {up} of {wanted}') from None


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
    try:
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
    except TimeoutError:
        raise AssertionError(f'the child on {port} did not start again') from None


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


async def ping_child(client, port, child_token, session, version):
    """ping straight to the child on *port* in *session*, with that child's own child bearer: its status (the reply read
    and dropped). A child knows only the sessions it opened: any other id is 404 (the MCP SDK's unknown session)."""
    message = {'jsonrpc': '2.0', 'id': 3, 'method': 'ping'}
    headers = {**ACCEPT, 'Authorization': 'Bearer ' + child_token, 'Mcp-Session-Id': session,
               'MCP-Protocol-Version': version}
    async with client.stream('POST', f'http://127.0.0.1:{port}/mcp', headers=headers, json=message) as response:
        if response.status_code == 200:
            await protocol_reply(response, message['id'])
        else:
            await response.aread()
        return response.status_code


async def check_routing(client, found, message, base=MCP):
    """T-05 on the real 8081 (see the module docstring). found: [(log id, child port, token, child token)], as
    credentials() returns them. Every session it opens is ended, also when a check fails. Fixed messages only, a profile
    named by its log id."""
    def methods(token):
        return ((base + '/mcp', {'Authorization': 'Bearer ' + token}), (f'{base}/private_{token}/mcp', {}))
    opened, listings, ended = [], {}, []
    try:
        for label, _, token, _ in found:
            for url, headers in methods(token):
                status, session, version = await initialize_on(client, url, headers, message)
                assert status == 200 and session, f'{label}: its token opened no session'
                opened.append((label, token, url, headers, session, version))
                assert not session.startswith(LOCAL_SESSION), f"{label}: no child answered its initialize"
                status, names = await tools_on(client, url, headers, session, version)
                assert status == 200 and names, f'{label}: tools/list unanswered'
                listings.setdefault(label, names)
                assert listings[label] == names, f'{label}: its two connection methods list differently'
        first = listings[found[0][0]]
        assert all(names == first for names in listings.values()), "a profile's policy differs from the default's"
        for label, _, _, _, session, version in opened:
            # The gateway hands out the child's own session id: only the child of the profile whose token opened the
            # session knows it (review SF-1: a consistent swap of two profiles' children passes every check above).
            for other, port, _, child_token in found:
                status = await ping_child(client, port, child_token, session, version)
                if other == label:
                    assert status == 200, f"{label}: its session is not its own child's"
                else:
                    assert status == 404, f'{label}: the child of {other} knows its session'
        for label, _, _, _, session, version in opened:
            for other, _, token, _ in found:
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


async def check_refused(client, found, message, base=MCP):
    """After the multi-profile restore (DQ-03 (b) A2; PaaS restore_inplace._verify: nothing that authenticated against
    the backup authenticates now): found, the credentials from before the restore ([(log id, child port, token, child
    token)], credentials()'s). Each token gets 401 as a Bearer and 404 in its secret URL (a session one opened all the
    same is ended), and each child token 401 and no session from its profile's child. Fixed messages, a profile named
    by its log id."""
    for label, port, token, child_token in found:
        for url, headers, refusal in ((base + '/mcp', {'Authorization': 'Bearer ' + token}, 401),
                                      (f'{base}/private_{token}/mcp', {}, 404)):
            status, session, version = await initialize_on(client, url, headers, message)
            if session:
                await end_session(client, url, headers, session, version)
            assert status == refusal, f'{label}: its token from before the restore is served'
        response = await client.post(f'http://127.0.0.1:{port}/mcp', json=message,
                                     headers={**ACCEPT, 'Authorization': 'Bearer ' + child_token})
        assert response.status_code == 401 and 'mcp-session-id' not in response.headers, \
            f'{label}: its child token from before the restore is served'


async def stage(probe, client):
    """The multi-profile stage (the module docstring's steps 1 to 9); prints one line of numbers, no secret."""
    assert probe.APP != 'n8n', "n8n's children name their port in their environment only (HM-25)"
    data = Path(probe.DATA)
    message = initialize_message()
    check_marker_ended(data)
    assert detect_as_runtime(data) == detected(False, restore_detect.CONSISTENT), 'sentinel not made by the runtime'
    created = create_profiles(probe)
    found = credentials(data, created)
    ports = [port for _, port, _, _ in found]
    process = probe.start()
    try:
        await probe.ready_listener(client, process)
        began = time.monotonic()
        pids = await profiles_up(probe, process, ports)
        up = time.monotonic() - began
        await check_routing(client, found, message)
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
    before = restore_picture(data, created)
    restored, _ = probe.restore_as_supervisor()
    with tempfile.TemporaryFile() as log:  # the start's stderr: unnamed, gone once closed, never shown
        process = probe.start(log)
        try:
            await probe.ready_listener(client, process)
            check_revoked_restore(data, restored, before, created)
            await profiles_up(probe, process, ports)
            await check_refused(client, found, message)
            stop_within(probe, process)
            process = None
        finally:
            if process is not None and process.poll() is None:
                probe.stop(process)
        probe.check_restore_log(log, len(restored) + 1, revoked=[label for label, _, _, _ in found])
    assert detect_as_runtime(data) == detected(False, restore_detect.CONSISTENT), \
        'restore not finished by the boot guard'
    tree_snapshot(data)  # what the guard left (the record, new journals, archived receipts) still restores
    print(f'PASS multi-profile: default + {len(created)} profiles up in {up:.1f} s; routing, child bearer, resources, '
          f'SIGKILL, stop in {stopped:.1f} s; {entries} entries; restore tree: every profile revoked and its old '
          f'credentials refused, sentinel rebuilt')


# Metadata only, recorded by the owned backend after it chooses a real HTTP 503.
# Odoo's private probe makes a fresh XML-RPC client; an offline /common request
# fails that check before authentication or any object read can follow.
ODOO_OUTAGE_CHECKS = []


def record_odoo_outage(path):
    assert path == '/xmlrpc/2/common', 'unexpected Odoo outage request'
    ODOO_OUTAGE_CHECKS.append(time.monotonic())


# The wait for readiness to turn 503 once a switched-on product's backend is offline. Its monitor has tolerance 2 (HM-09,
# DQ-25): two failed checks in a row, HEALTH_INTERVAL (15 s) apart, so the verdict comes 15 to 30 s after the outage, and
# a 503 seen while the first check runs is only a snapshot of that check, not the verdict. A product that is not
# switched on keeps the probe's own 22 s and one 503 (tolerance 1). Owner decision 2026-11-24 (train A candidate
# failure: litellm, nextcloud and emqx timed out at the 22 s wait): up to 40 s, and three 503 in a row, .25 s apart.
# Odoo's stage (odoo_outage) runs before this one and is unchanged: afterwards the 503 is already stable.
OUTAGE_SWITCHED_SECONDS = 40
OUTAGE_SWITCHED_STABLE = 3


async def wait_unready(probe, client, ready_url=MCP + '/health/ready'):
    stable = 0
    try:
        async with asyncio.timeout(OUTAGE_SWITCHED_SECONDS):
            while stable < OUTAGE_SWITCHED_STABLE:
                stable = stable + 1 if (await client.get(ready_url)).status_code == 503 else 0
                await asyncio.sleep(.25)
    except TimeoutError:
        raise AssertionError(f'{probe.APP}: expected {OUTAGE_SWITCHED_STABLE} HTTP 503 in a row within '
                             f'{OUTAGE_SWITCHED_SECONDS} s of the backend going offline') from None


async def odoo_outage(probe, client, ready_url=MCP + '/health/ready'):
    """Check HM-09's two-failure contract, not an arbitrary phase of its 15 s clock.

    Each failed backend observation has the original 22 s deadline. The first
    must still leave readiness healthy; the second must make it unavailable.
    Count actual failed HTTP requests, so a transient 503 while the monitor is
    checking cannot pass for the second verdict. No runtime clock or health
    state is altered. Caller still checks PID stability, ping and shutdown.
    """
    baseline = len(ODOO_OUTAGE_CHECKS)
    started = time.monotonic()
    probe.OFFLINE.set()
    for number, expected in ((1, 200), (2, 503)):
        try:
            async with asyncio.timeout(22):
                while len(ODOO_OUTAGE_CHECKS) < baseline + number:
                    await asyncio.sleep(.05)
                # Require a stable public result, not the check-in-progress
                # snapshot. The second backend check must not rescue the first.
                stable = 0
                while stable < 3:
                    assert len(ODOO_OUTAGE_CHECKS) == baseline + number, 'extra outage check before verdict'
                    status = (await client.get(ready_url)).status_code
                    stable = stable + 1 if status == expected else 0
                    await asyncio.sleep(.25)
        except TimeoutError:
            raise AssertionError(f'Odoo outage check {number}: expected stable HTTP {expected} within 22 s') from None
        print(f'container/mock Odoo outage check {number}: HTTP {expected} '
              f'after {time.monotonic() - started:.2f}s; NOT HA E2E')
