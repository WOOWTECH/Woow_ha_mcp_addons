"""HM-13a: restore detection. Signal 1 is the restore marker the entrypoint saves; signal 2 the instance sentinel.

Multi-profile plan §8.4 (detection, marker) and §12.3 HM-13a. Neither is behind the multi-profile switch (§3.3): the
marker comes with every product's next release; the sentinel is read and written only for a product whose switch is
on or that has profile data on disk, so a product that is not enabled and has no profile data changes nothing unless
it is restored (the zero-change tests below). Acting on a detection is the boot gate's (HM-13b), not tested here.

Signal 1 runs in packaging/entrypoint.py as root, before pass 1 of the ownership repair. Most tests run that boot
unprivileged through VirtualRoot: the entrypoint's own os module with geteuid() 0 and file owners kept per inode (an
inode this test user owns reads as root's until it is chowned; chown and fchown only change that map). Modes, names,
contents, fsync and the order of the calls are real. The tests named test_root_* run the same boots with real owners
and check what the runtime user (uid 10001) can do afterwards in a forked child: the CI runs pytest as root
(packaging/unit.sh); an unprivileged run fails them on purpose, it never skips them. The restore stage every release's
container acceptance runs (packaging/container_probe.py) is checked here against the same entrypoint, both ways.
"""
from contextlib import contextmanager, redirect_stderr
import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import stat
import sys
import tempfile
import time

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import restore_detect as rd
from mcp_admin_core.config import ConfigError
from mcp_admin_core.products import ProductStore

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan
ROOT = Path(__file__).resolve().parents[1]
RESTORE_OWNER = (0, 0)  # Supervisor restores as root and does not chown
RUNTIME = (10001, 10001)
REOWNED = 'bootstrap: re-owned %d restored entries in /data/mcp\n'
# %s: why the marker could not be saved, an errno name or 'name in use' (nothing else: no path, no value)
WARNING = ('bootstrap: WARNING: /data/mcp was restored but its restore marker (.restore-detected) could not be '
           'saved (%s); starting (no profile data)\n')
REFUSED = ('bootstrap: /data/mcp was restored with profile data but its restore marker (.restore-detected) could '
           'not be saved (%s); not starting (retried at the next start)\n')
IN_USE = 'name in use'


def inode(path):
    info = os.lstat(path)
    return info.st_dev, info.st_ino


def entrypoint(os_module=None):
    """A fresh copy of packaging/entrypoint.py for one boot; os_module, when given, is its os."""
    spec = importlib.util.spec_from_file_location('entrypoint_under_test', ROOT / 'packaging/entrypoint.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if os_module is not None:
        module.os = os_module
    return module


def container_probe(monkeypatch, data, os_module=None):
    """packaging/container_probe.py, for its restore stage: its DATA is data and os_module (when given) its os."""
    monkeypatch.syspath_prepend(str(ROOT / 'packaging'))  # its own import of denial_probe
    monkeypatch.setattr(sys, 'argv', ['container_probe.py', 'odoo'])
    spec = importlib.util.spec_from_file_location('container_probe_under_test', ROOT / 'packaging/container_probe.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.DATA = data
    if os_module is not None:
        module.os = os_module
    return module


class Crash(BaseException):
    """The boot stops at this call (killed, or the power went once the page cache was written): nothing after it
    runs and what reached the disk stays. Not an OSError or RuntimeError: nothing in the code under test handles it."""


class Stuck(BaseException):
    """A call blocked past its deadline. Not an OSError (TimeoutError is one): the code under test cannot take it for
    an unreadable file."""


@contextmanager
def deadline(seconds):
    """Fail the test with Stuck when the block takes longer than seconds, instead of hanging the whole run."""
    def expire(signum, frame):
        raise Stuck(f'blocked for more than {seconds} s')
    previous = signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class Seen:
    """A stat result with the owner the virtual disk records."""

    def __init__(self, info, owner):
        self._info = info
        self.st_uid, self.st_gid = owner

    def __getattr__(self, name):
        return getattr(self._info, name)


class VirtualRoot:
    """packaging/entrypoint.py's os module as root sees it, for a test user that cannot chown (module text).

    owners is the disk's ownership, (st_dev, st_ino) -> (uid, gid): give the same dict to the next boot. events lists
    (kind, subject) in call order: open and stat by name; fsync, scandir, mode (fchmod, chmod) and owner (fchown,
    chown) by inode. opens keeps (name, flags, mode, inode of the directory descriptor).
    """

    def __init__(self, owners=None, euid=0):
        self.owners = {} if owners is None else owners
        self.euid = euid
        self.events = []
        self.opens = []
        self._faults = []

    def __getattr__(self, name):
        return getattr(os, name)

    def fault(self, kind, error, *, subject=None, nth=1, after=False):
        """Raise error at the nth call of kind (on subject, when given): before it runs, or right after it."""
        self._faults.append({'kind': kind, 'subject': subject, 'left': nth, 'error': error, 'after': after})

    def owner(self, info):
        key = (info.st_dev, info.st_ino)
        if key in self.owners:
            return self.owners[key]
        return RESTORE_OWNER if info.st_uid == os.getuid() else (info.st_uid, info.st_gid)

    def own(self, directory, owner):
        for path in [directory, *directory.rglob('*')]:
            self.owners[inode(path)] = owner

    def _call(self, kind, subject, perform):
        due = []
        for rule in self._faults:
            if rule['kind'] == kind and rule['subject'] in (None, subject) and rule['left'] > 0:
                rule['left'] -= 1
                if rule['left'] == 0:
                    due.append(rule)
        for rule in due:
            if not rule['after']:
                raise rule['error']
        result = perform()
        self.events.append((kind, subject))
        for rule in due:
            raise rule['error']
        return result

    @staticmethod
    def _held(fd):
        info = os.fstat(fd)
        return info.st_dev, info.st_ino

    def geteuid(self):
        return self.euid

    def fstat(self, fd):
        info = os.fstat(fd)
        return Seen(info, self.owner(info))

    def lstat(self, path):  # for packaging/container_probe.py's restore stage (the entrypoint never calls it)
        info = os.lstat(path)
        return Seen(info, self.owner(info))

    def stat(self, path, *, dir_fd=None, follow_symlinks=True):
        info = self._call('stat', os.fspath(path),
                          lambda: os.stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks))
        return Seen(info, self.owner(info))

    def open(self, path, flags, mode=0o777, *, dir_fd=None):
        self.opens.append((os.fspath(path), flags, mode, None if dir_fd is None else self._held(dir_fd)))
        return self._call('open', os.fspath(path), lambda: os.open(path, flags, mode, dir_fd=dir_fd))

    def fsync(self, fd):
        return self._call('fsync', self._held(fd), lambda: os.fsync(fd))

    def scandir(self, fd):
        return self._call('scandir', self._held(fd), lambda: os.scandir(fd))

    def fchmod(self, fd, mode):
        return self._call('mode', self._held(fd), lambda: os.fchmod(fd, mode))

    @staticmethod
    def _named(path):  # pass 2 names a pinned file as /proc/self/fd/<n>: stat follows it to that inode
        info = os.stat(path)
        return info.st_dev, info.st_ino

    def chmod(self, path, mode):
        return self._call('mode', self._named(path), lambda: os.chmod(path, mode))

    def fchown(self, fd, uid, gid):
        key = self._held(fd)
        return self._call('owner', key, lambda: self.owners.__setitem__(key, (uid, gid)))

    def chown(self, path, uid, gid):
        key = self._named(path)
        return self._call('owner', key, lambda: self.owners.__setitem__(key, (uid, gid)))


class Calls:
    """restore_detect's os module: records each call as (name, subject), the subject being its first argument when
    that is a name or a path (else None); fail() raises before the nth matching call; override() swaps one function."""

    def __init__(self):
        self.made = []
        self._faults = []
        self._overrides = {}

    def fail(self, name, subject, error, nth=1):
        self._faults.append([name, subject, nth, error])

    def override(self, name, function):
        self._overrides[name] = function

    def __getattr__(self, name):
        real = self._overrides.get(name) or getattr(os, name)
        if not callable(real) or isinstance(real, type):
            return real

        def call(*args, **kwargs):
            subject = os.fspath(args[0]) if args and isinstance(args[0], (str, os.PathLike)) else None
            for fault in self._faults:
                if fault[0] == name and fault[1] == subject and fault[2] > 0:
                    fault[2] -= 1
                    if fault[2] == 0:
                        raise fault[3]
            self.made.append((name, subject))
            return real(*args, **kwargs)
        return call


def boot(parent, vroot):
    """One start of the real prepare_data on parent/mcp, as root under vroot. Returns what it printed to stderr; an
    exception carries that as .stderr."""
    module = entrypoint(vroot)
    log = io.StringIO()
    try:
        with redirect_stderr(log):
            module.prepare_data(parent)
    except BaseException as error:
        error.stderr = log.getvalue()
        raise
    return log.getvalue()


def add_profile_data(data, kind):
    if kind == 'index':
        (data / 'profiles.json').write_bytes(b'{"version": 1, "profile_index": {}}')
    elif kind == 'directory':
        (data / 'profiles' / ('0' * 24)).mkdir(parents=True)
    elif kind == 'dangling link':
        (data / 'profiles').symlink_to(data / 'nowhere')
    else:
        assert kind is None, kind


def restored_tree(parent, profile_data=None):
    """/data/mcp as a restore leaves it (root-owned: under VirtualRoot, owned by this test user): the default
    profile's files with the modes the 2026-10-05 HA pilot saw (files 0644, a directory 0755)."""
    data = parent / 'mcp'
    data.mkdir(mode=0o700)
    data.chmod(0o700)
    (data / 'state.json').write_bytes(b'{"restored": true}')  # the entrypoint never parses a state
    (data / '.writer.lock').write_bytes(b'')
    (data / 'child').mkdir()
    (data / 'child').chmod(0o755)
    (data / 'child' / 'leftover').write_bytes(b'x')
    for name in ('state.json', '.writer.lock', 'child/leftover'):
        (data / name).chmod(0o644)
    add_profile_data(data, profile_data)
    return data


def runtime_tree(parent, log_scan, product='odoo'):
    """/data/mcp as the runtime keeps it: a real default state (tokens generated, watched by the log scan)."""
    data = parent / 'mcp'
    store = ProductStore(data, product)
    try:
        log_scan.watch_state(store.load())
    finally:
        store.close()
    return data


def snapshot(directory):
    """directory and each entry under it: inode, mode, links, size, mtime, ctime and a regular file's bytes. A chmod
    (even to the same mode), a write, a new link or a new file in an old name each change this."""
    entries = {}
    for path in [directory, *sorted(directory.rglob('*'))]:
        info = path.lstat()
        content = path.read_bytes() if stat.S_ISREG(info.st_mode) else None
        entries[str(path.relative_to(directory))] = (info.st_ino, info.st_mode, info.st_nlink, info.st_size,
                                                     info.st_mtime_ns, info.st_ctime_ns, content)
    return entries


def after_tick(clock, since_ns):
    """Wait until a new file in clock gets a ctime past since_ns. File times come from a coarse clock (one tick is up
    to 10 ms): a real restore comes long after the sentinel it copies; the tests make sure of it instead of assuming."""
    deadline = time.monotonic() + 5
    probe = clock / 'clock-tick'
    while True:
        probe.write_bytes(b'')
        now = probe.lstat().st_ctime_ns
        probe.unlink()
        if now > since_ns:
            return
        assert time.monotonic() < deadline, 'the file clock did not move for 5 s'
        time.sleep(0.001)


def supervisor_restore(backup, data):
    """What Supervisor's restore does to the data (supervisor/apps/app.py): remove it, then copytree the backup's
    copy back, links kept, no chown (copy2 keeps modes and mtimes; no call keeps a ctime)."""
    shutil.rmtree(data)
    shutil.copytree(backup, data, symlinks=True)


def establish(data):
    """The first start of a product with its switch on (no profile data yet): both files appear."""
    assert rd.detect(data, enabled=True) == rd.Detection(marker=False, active=True, sentinel=rd.ESTABLISHED)
    return (data / rd.SENTINEL).lstat()


def record_of(data):
    return json.loads((data / rd.RECORD).read_bytes())


# ---- signal 1: the restore marker (packaging/entrypoint.py) ----------------------------------------------------

def test_the_entrypoint_and_the_detection_use_the_same_names():
    # The entrypoint runs as root with the standard library only, so it keeps its own copy of the names.
    module = entrypoint()
    assert module.MARKER == rd.MARKER == '.restore-detected'
    assert module.PROFILE_DATA == rd.PROFILE_DATA == ('profiles.json', 'profiles')


def test_a_restore_saves_the_marker_durably_before_pass_1(tmp_path):
    data = restored_tree(tmp_path)
    state = (data / 'state.json').read_bytes()
    directory = inode(data)
    vroot = VirtualRoot()
    out = boot(tmp_path, vroot)
    marker = data / rd.MARKER
    info = marker.lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size == 0
    assert stat.S_IMODE(info.st_mode) == 0o600 and vroot.owners[inode(marker)] == RUNTIME
    # Through the /data/mcp descriptor, never following a link, never over an existing name, owner-only: the one
    # creating open of a restore start (pass 1 opens every name again, the marker's too, with O_PATH).
    [(name, flags, mode, where)] = [opened for opened in vroot.opens if opened[1] & os.O_CREAT]
    assert name == rd.MARKER and flags & (os.O_EXCL | os.O_NOFOLLOW) == os.O_EXCL | os.O_NOFOLLOW
    assert mode == 0o600 and where == directory
    # Created, then the marker and /data/mcp fsynced, and only then pass 1 lists /data/mcp; nothing changed before.
    events = vroot.events
    created = events.index(('open', rd.MARKER))
    assert events[:created] == [('open', str(tmp_path)), ('open', 'mcp')]
    assert events[created + 1:created + 4] == [('fsync', inode(marker)), ('fsync', directory), ('scandir', directory)]
    # Pass 2 re-owns the marker with the rest; /data/mcp itself is re-owned last (a stop before that repeats both).
    assert ('owner', inode(marker)) in events
    assert events[-2:] == [('mode', directory), ('owner', directory)]
    entries = [data, *data.rglob('*')]
    assert {vroot.owner(path.lstat()) for path in entries} == {RUNTIME}
    assert all(stat.S_IMODE(path.lstat().st_mode) == (0o700 if path.is_dir() else 0o600) for path in entries)
    assert out == REOWNED % (len(entries) - 1)  # the count includes the marker
    assert (data / 'state.json').read_bytes() == state


def test_a_marker_already_there_is_kept_as_it_is(tmp_path):
    # A restore whose marker the management process had not handled yet, or a backup that carried one.
    data = restored_tree(tmp_path)
    marker = data / rd.MARKER
    marker.write_bytes(b'')
    marker.chmod(0o644)
    kept, written = inode(marker), marker.lstat().st_mtime_ns
    vroot = VirtualRoot()
    out = boot(tmp_path, vroot)
    assert inode(marker) == kept and marker.lstat().st_mtime_ns == written and marker.read_bytes() == b''
    assert stat.S_IMODE(marker.lstat().st_mode) == 0o600 and vroot.owners[kept] == RUNTIME
    assert [name for name, flags, *_ in vroot.opens if flags & os.O_CREAT] == [rd.MARKER]  # it found the marker
    assert vroot.events.index(('fsync', inode(data))) < vroot.events.index(('scandir', inode(data)))
    assert out == REOWNED % len(list(data.rglob('*')))


@pytest.mark.parametrize('case', ['new installation', 'runtime-owned', 'foreign owner', 'not root'])
def test_only_data_that_comes_back_root_owned_is_marked(tmp_path, case):
    # Signal 1 is exactly the restore repair's condition (PaaS test_volume_root_owner_rule): an existing /data/mcp
    # owned by the restore owner, seen by root. Every other start keeps today's behaviour.
    vroot = VirtualRoot(euid=4242 if case == 'not root' else 0)
    data = tmp_path / 'mcp'
    if case != 'new installation':
        restored_tree(tmp_path)
    if case == 'runtime-owned':
        vroot.own(data, RUNTIME)
    if case == 'foreign owner':
        vroot.owners[inode(data)] = (4242, 4242)
    before = snapshot(data) if data.exists() else None
    if case in ('foreign owner', 'not root'):
        with pytest.raises(RuntimeError, match='incompatible data ownership'):
            boot(tmp_path, vroot)
    else:
        assert boot(tmp_path, vroot) == ''
    assert not (data / rd.MARKER).exists()
    assert not [event for event in vroot.events if event[0] in ('mode', 'fsync', 'scandir')]
    if before is None:
        assert list(data.iterdir()) == []
    else:
        assert snapshot(data) == before


def test_a_refused_restore_keeps_its_marker(tmp_path):
    # Pass 1 refuses a foreign owner inside the tree; the marker was saved before it, so the restore stays marked
    # until a start completes the repair.
    data = restored_tree(tmp_path)
    vroot = VirtualRoot()
    vroot.owners[inode(data / 'child' / 'leftover')] = (4242, 4242)
    with pytest.raises(RuntimeError, match='foreign restored owner'):
        boot(tmp_path, vroot)
    assert (data / rd.MARKER).is_file()
    assert not [event for event in vroot.events if event[0] in ('mode', 'owner')]


CRASHES = {  # where the first start stops: the VirtualRoot.fault() arguments; DATA stands for /data/mcp's inode
    'after the marker was created': dict(kind='fsync', nth=1),
    'after the marker was fsynced': dict(kind='fsync', nth=2),
    'when pass 1 starts': dict(kind='scandir', subject='DATA', nth=1),
    'when pass 2 starts': dict(kind='scandir', subject='DATA', nth=2),
    'in pass 2, after two entries': dict(kind='owner', nth=3),
    'before the mode of /data/mcp': dict(kind='mode', subject='DATA'),
    'before the owner of /data/mcp': dict(kind='owner', subject='DATA'),
    'after the owner of /data/mcp': dict(kind='owner', subject='DATA', after=True),
}


@pytest.mark.parametrize('crash', list(CRASHES))
def test_an_interrupted_restore_start_is_redone_until_it_completes(tmp_path, crash):
    data = restored_tree(tmp_path)
    contents = {path: path.read_bytes() for path in data.rglob('*') if path.is_file()}
    owners = {}
    first = VirtualRoot(owners)
    point = dict(CRASHES[crash])
    if point.get('subject') == 'DATA':
        point['subject'] = inode(data)
    first.fault(error=Crash(crash), **point)
    with pytest.raises(Crash):
        boot(tmp_path, first)
    marker = data / rd.MARKER
    assert marker.is_file()  # every stop comes after the marker was created
    again = VirtualRoot(owners)  # the next start: the same disk
    out = boot(tmp_path, again)
    entries = [data, *data.rglob('*')]
    if crash == 'after the owner of /data/mcp':
        # /data/mcp is the runtime user's already: an ordinary start, nothing left to repair; the marker stays.
        assert out == '' and not [event for event in again.events if event[0] in ('mode', 'owner', 'fsync')]
    else:
        assert out == REOWNED % (len(entries) - 1)
    assert {again.owner(path.lstat()) for path in entries} == {RUNTIME}
    assert all(stat.S_IMODE(path.lstat().st_mode) == (0o700 if path.is_dir() else 0o600) for path in entries)
    assert {path: path.read_bytes() for path in contents} == contents
    info = marker.lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_size == 0 and stat.S_IMODE(info.st_mode) == 0o600


def marker_failures():
    """The calls that can fail while the marker is saved, and the reason the log line names."""
    def failed(code):  # as the kernel reports it, with the file name: the line must name only the errno
        return OSError(code, os.strerror(code), rd.MARKER)
    return {
        'no space left': (dict(kind='open', subject=rd.MARKER, error=failed(errno.ENOSPC)), 'ENOSPC'),
        'read-only file system': (dict(kind='open', subject=rd.MARKER, error=failed(errno.EROFS)), 'EROFS'),
        'the marker fsync fails': (dict(kind='fsync', nth=1, error=failed(errno.EIO)), 'EIO'),
        'the /data/mcp fsync fails': (dict(kind='fsync', nth=2, error=failed(errno.EIO)), 'EIO'),
    }


def take_the_markers_name(data, kind):
    """Something that is not a marker holds its name: a directory, a link, or a file with a second link."""
    marker = data / rd.MARKER
    if kind == 'name taken by a directory':
        marker.mkdir()
    elif kind == 'name taken by a link':
        marker.symlink_to('state.json')
    else:
        assert kind == 'name taken by a second link', kind
        os.link(data / 'state.json', marker)


@pytest.mark.parametrize('profile_data', ['index', 'directory'])
@pytest.mark.parametrize('failure', [*marker_failures(), 'name taken by a directory', 'name taken by a link',
                                     'name taken by a second link'])
def test_with_profile_data_a_restore_without_its_marker_does_not_start(tmp_path, failure, profile_data):
    # PaaS test_marker_detection_fails_closed; plan §8.4: profile data on disk, no durable marker -> refuse the start
    # (bootstrap unavailable) before any change; the next start tries again.
    data = restored_tree(tmp_path, profile_data)
    vroot = VirtualRoot()
    marker = data / rd.MARKER
    if failure in marker_failures():
        fault, reason = marker_failures()[failure]
        vroot.fault(**fault)
    else:
        take_the_markers_name(data, failure)
        reason = IN_USE
    before = snapshot(data)
    with pytest.raises(RuntimeError, match='restore marker unavailable') as refused:
        boot(tmp_path, vroot)
    assert refused.value.stderr == REFUSED % reason
    assert not [event for event in vroot.events if event[0] in ('mode', 'owner', 'scandir')] and vroot.owners == {}
    after = snapshot(data)
    made = {rd.MARKER} if 'fsync' in failure else set()  # created, but not known to be durable
    assert set(after) == set(before) | made
    assert {name: entry for name, entry in after.items() if name not in ('.', *made)} == \
        {name: entry for name, entry in before.items() if name != '.'}
    if failure in marker_failures():
        assert boot(tmp_path, VirtualRoot(vroot.owners)) == REOWNED % len(list(data.rglob('*')))
        assert marker.is_file()


@pytest.mark.parametrize('failure', [*marker_failures(), 'name taken by a directory'])
def test_without_profile_data_a_restore_without_its_marker_warns_and_starts(tmp_path, failure):
    # Plan §8.4: no profile data, nothing to revoke: one WARNING line and the repair goes on as today.
    data = restored_tree(tmp_path)
    vroot = VirtualRoot()
    if failure in marker_failures():
        fault, reason = marker_failures()[failure]
        vroot.fault(**fault)
    else:
        take_the_markers_name(data, failure)  # a directory: pass 1 approves it like any plain directory
        reason = IN_USE
    out = boot(tmp_path, vroot)
    entries = [data, *data.rglob('*')]
    assert out == WARNING % reason + REOWNED % (len(entries) - 1)
    assert {vroot.owner(path.lstat()) for path in entries} == {RUNTIME}


@pytest.mark.parametrize('taken', ['name taken by a link', 'name taken by a second link'])
def test_a_link_in_the_markers_name_never_starts(tmp_path, taken):
    # Without profile data the WARNING comes first; then pass 1 refuses the link, as it refuses any link and any file
    # with a second link. Never a marker accepted (review HM-13a E20).
    data = restored_tree(tmp_path)
    take_the_markers_name(data, taken)
    before = snapshot(data)
    vroot = VirtualRoot()
    with pytest.raises(RuntimeError, match='unsupported restored entry') as refused:
        boot(tmp_path, vroot)
    assert refused.value.stderr == WARNING % IN_USE
    assert snapshot(data) == before and vroot.owners == {}


@pytest.mark.parametrize('lookup', [pytest.param(errno.EIO, id='EIO'), pytest.param(errno.EACCES, id='EACCES'),
                                    pytest.param(None, id='a dangling profiles link')])
def test_a_profile_data_check_that_cannot_rule_it_out_counts_as_profile_data(tmp_path, lookup):
    # A lookup that cannot answer counts, and the check never follows a link: a profiles link to nowhere is profile
    # data too (review HM-13a E19).
    data = restored_tree(tmp_path, 'dangling link' if lookup is None else None)
    vroot = VirtualRoot()
    vroot.fault('open', OSError(errno.ENOSPC, os.strerror(errno.ENOSPC)), subject=rd.MARKER)
    if lookup is not None:
        vroot.fault('stat', OSError(lookup, os.strerror(lookup)), subject='profiles.json')
    before = snapshot(data)
    with pytest.raises(RuntimeError, match='restore marker unavailable') as refused:
        boot(tmp_path, vroot)
    assert refused.value.stderr == REFUSED % 'ENOSPC' and snapshot(data) == before and vroot.owners == {}


def test_a_start_without_a_restore_changes_nothing(tmp_path, log_scan):
    data = runtime_tree(tmp_path, log_scan)
    vroot = VirtualRoot()
    vroot.own(data, RUNTIME)
    before, owners = snapshot(data), dict(vroot.owners)
    for _ in range(2):
        assert boot(tmp_path, vroot) == ''
    assert snapshot(data) == before and vroot.owners == owners
    assert vroot.events == [('open', str(tmp_path)), ('open', 'mcp')] * 2  # nothing looked up, synced or changed


# ---- signal 2: the instance sentinel (mcp_admin_core.restore_detect) -------------------------------------------

def test_the_verdicts():
    assert rd.RESTORED == {rd.MISMATCH, rd.SENTINEL_MISSING, rd.SENTINEL_INVALID, rd.RECORD_MISSING,
                           rd.RECORD_INVALID}
    assert not {rd.INACTIVE, rd.ESTABLISHED, rd.REBUILT, rd.CONSISTENT} & rd.RESTORED
    assert rd.Detection(marker=True, active=False, sentinel=rd.INACTIVE).restored
    assert rd.Detection(marker=False, active=True, sentinel=rd.MISMATCH).restored
    assert not rd.Detection(marker=False, active=True, sentinel=rd.CONSISTENT).restored


@pytest.mark.parametrize('leftover', [None, 'a stale sentinel and record', 'a marker'])
def test_a_product_that_is_not_enabled_and_has_no_profile_data_is_left_alone(tmp_path, log_scan, monkeypatch,
                                                                             leftover):
    # The zero change of plan §12.3 HM-13a: no file opened (no state, no index, no sentinel), nothing written.
    data = runtime_tree(tmp_path, log_scan)
    if leftover == 'a stale sentinel and record':  # from an earlier release with the switch on; a check would object
        sentinel = establish(data)
        after_tick(tmp_path, sentinel.st_ctime_ns)
        (data / rd.SENTINEL).chmod(0o600)
    if leftover == 'a marker':
        (data / rd.MARKER).write_bytes(b'')
    before = snapshot(data)
    calls = Calls()
    monkeypatch.setattr(rd, 'os', calls)
    for _ in range(3):
        detection = rd.detect(data, enabled=False)
        assert detection == rd.Detection(marker=leftover == 'a marker', active=False, sentinel=rd.INACTIVE)
        assert detection.restored == (leftover == 'a marker')  # the boot gate (HM-13b) only warns and clears it
    assert snapshot(data) == before
    looked_up = [('open', str(data)), ('stat', rd.MARKER), ('stat', 'profiles.json'), ('stat', 'profiles'),
                 ('close', None)]
    assert calls.made == looked_up * 3


def test_the_first_start_with_the_switch_on_makes_the_sentinel_and_its_record(tmp_path, log_scan):
    data = runtime_tree(tmp_path, log_scan)
    state = snapshot(data)['state.json']
    entries = {path.name for path in data.iterdir()}
    detection = rd.detect(data, enabled=True)
    assert detection == rd.Detection(marker=False, active=True, sentinel=rd.ESTABLISHED) and not detection.restored
    assert {path.name for path in data.iterdir()} == entries | {rd.SENTINEL, rd.RECORD}  # no temporary left
    sentinel = (data / rd.SENTINEL).lstat()
    assert stat.S_ISREG(sentinel.st_mode) and sentinel.st_size == 0 and sentinel.st_nlink == 1
    assert stat.S_IMODE(sentinel.st_mode) == 0o600
    record = (data / rd.RECORD).lstat()
    assert stat.S_ISREG(record.st_mode) and record.st_nlink == 1 and stat.S_IMODE(record.st_mode) == 0o600
    # Two integers and a version, nothing else (no secret, no st_dev).
    assert record_of(data) == {'version': 1, 'st_ino': sentinel.st_ino, 'st_ctime_ns': sentinel.st_ctime_ns}
    settled = snapshot(data)
    for _ in range(3):
        assert rd.detect(data, enabled=True) == rd.Detection(marker=False, active=True, sentinel=rd.CONSISTENT)
    assert snapshot(data) == settled and settled['state.json'] == state


@pytest.mark.parametrize('profile_data', ['index', 'directory', 'dangling link'])
def test_profile_data_turns_the_sentinel_on_without_the_switch(tmp_path, log_scan, profile_data):
    # A release with the switch off again (dormant profiles), or a restore of that period's backup.
    data = runtime_tree(tmp_path, log_scan)
    establish(data)
    add_profile_data(data, profile_data)
    assert rd.detect(data, enabled=False) == rd.Detection(marker=False, active=True, sentinel=rd.CONSISTENT)
    (data / rd.SENTINEL).unlink()
    (data / rd.RECORD).unlink()
    before = snapshot(data)
    assert rd.detect(data, enabled=False) == rd.Detection(marker=False, active=True, sentinel=rd.RECORD_MISSING)
    assert snapshot(data) == before


@pytest.mark.parametrize('kind', ['a file', 'a directory', 'a dangling link', 'an unanswerable lookup'])
@pytest.mark.parametrize('name', [rd.MARKER, *rd.PROFILE_DATA])
def test_any_entry_under_those_names_counts(tmp_path, log_scan, monkeypatch, name, kind):
    # Fails closed like PaaS restore_marker: any kind of entry counts, and so does one a lookup cannot rule out.
    data = runtime_tree(tmp_path, log_scan)
    path = data / name
    if kind == 'a file':
        path.write_bytes(b'')
    elif kind == 'a directory':
        path.mkdir()
    elif kind == 'a dangling link':
        path.symlink_to(data / 'nowhere')
    else:
        calls = Calls()
        calls.fail('stat', name, OSError(errno.EIO, os.strerror(errno.EIO)))
        monkeypatch.setattr(rd, 'os', calls)
    if name == rd.MARKER:
        expected = rd.Detection(marker=True, active=False, sentinel=rd.INACTIVE)
    else:  # profile data with neither file: a restore (the record must exist once profiles do)
        expected = rd.Detection(marker=False, active=True, sentinel=rd.RECORD_MISSING)
    assert rd.detect(data, enabled=False) == expected


@pytest.mark.parametrize('missing, profile_data, verdict', [
    ('both', None, rd.ESTABLISHED),
    ('both', 'index', rd.RECORD_MISSING),
    ('record', None, rd.REBUILT),             # the first start stopped between the two files
    ('record', 'index', rd.RECORD_MISSING),
    ('sentinel', None, rd.SENTINEL_MISSING),
    ('sentinel', 'directory', rd.SENTINEL_MISSING),
])
def test_a_missing_sentinel_or_record(tmp_path, log_scan, missing, profile_data, verdict):
    data = runtime_tree(tmp_path, log_scan)
    old = establish(data)
    if missing in ('record', 'both'):
        (data / rd.RECORD).unlink()
    if missing in ('sentinel', 'both'):
        (data / rd.SENTINEL).unlink()
    add_profile_data(data, profile_data)
    after_tick(tmp_path, old.st_ctime_ns)
    before = snapshot(data)
    detection = rd.detect(data, enabled=True)
    assert detection == rd.Detection(marker=False, active=True, sentinel=verdict)
    assert detection.restored == (verdict in rd.RESTORED)
    if verdict in rd.RESTORED:
        assert snapshot(data) == before  # nothing written while a restore is detected
    else:
        new = (data / rd.SENTINEL).lstat()
        assert new.st_ctime_ns > old.st_ctime_ns  # a new file, never the old one adopted
        assert record_of(data) == {'version': 1, 'st_ino': new.st_ino, 'st_ctime_ns': new.st_ctime_ns}
        assert rd.detect(data, enabled=True).sentinel == rd.CONSISTENT


def test_every_file_level_restore_is_seen_even_when_the_inode_number_comes_back(tmp_path, log_scan):
    # The plan's experiment (20 Supervisor-style restores: inode alone missed 20/20, ctime 0/20), as a test.
    data = runtime_tree(tmp_path, log_scan)
    establish(data)
    add_profile_data(data, 'index')
    backup = tmp_path / 'backup'
    shutil.copytree(data, backup, symlinks=True)
    recorded = record_of(data)
    after_tick(tmp_path, recorded['st_ctime_ns'])
    for _ in range(20):
        supervisor_restore(backup, data)
        assert rd.detect(data, enabled=True).sentinel == rd.MISMATCH


CHANGES = {
    'chmod to the same mode': lambda path: path.chmod(0o600),
    'chown to the same owner': lambda path: os.chown(path, path.lstat().st_uid, path.lstat().st_gid),
    'new timestamps': lambda path: os.utime(path),
    'a write': lambda path: path.write_bytes(b'x'),
    'a second link': lambda path: os.link(path, path.with_name('sentinel-link')),
    'a new file in its name': lambda path: (path.unlink(), path.write_bytes(b'')),
}


@pytest.mark.parametrize('change', sorted(CHANGES))
def test_any_change_to_the_sentinel_reads_as_a_restore(tmp_path, log_scan, change):
    # Why nothing but the entrypoint's restore repair may touch it (HM-13b scans every chmod and chown).
    data = runtime_tree(tmp_path, log_scan)
    sentinel = establish(data)
    after_tick(tmp_path, sentinel.st_ctime_ns)
    CHANGES[change](data / rd.SENTINEL)
    assert rd.detect(data, enabled=True).sentinel == rd.MISMATCH


def test_another_device_number_alone_is_not_a_restore(tmp_path, log_scan, monkeypatch):
    # A host that numbers its disks differently (one more USB disk at boot): st_dev changes, the file does not.
    data = runtime_tree(tmp_path, log_scan)
    establish(data)

    class Renumbered(Seen):
        def __init__(self, info):
            super().__init__(info, (info.st_uid, info.st_gid))
            self.st_dev = info.st_dev + 1
    calls = Calls()
    calls.override('stat', lambda *args, **kwargs: Renumbered(os.stat(*args, **kwargs)))
    calls.override('fstat', lambda fd: Renumbered(os.fstat(fd)))
    monkeypatch.setattr(rd, 'os', calls)
    assert rd.detect(data, enabled=True) == rd.Detection(marker=False, active=True, sentinel=rd.CONSISTENT)


def test_ordinary_runtime_work_never_reads_as_a_restore(tmp_path, log_scan):
    # Store reads (which fchmod state.json), token changes, the management process's directory chmod and ordinary
    # entrypoint starts leave the sentinel as it was.
    data = runtime_tree(tmp_path, log_scan)
    establish(data)
    vroot = VirtualRoot()
    vroot.owners[inode(data)] = RUNTIME
    for _ in range(3):
        store = ProductStore(data, 'odoo')
        try:
            state, _ = store.change_token(secrets.token_urlsafe(32), action='rotate')
            log_scan.watch_state(state)
            store.load()
        finally:
            store.close()
        assert boot(tmp_path, vroot) == ''
        assert rd.detect(data, enabled=True) == rd.Detection(marker=False, active=True, sentinel=rd.CONSISTENT)


def test_a_backup_restored_by_supervisor_shows_both_signals(tmp_path, log_scan):
    parent = tmp_path / 'data'
    parent.mkdir()
    data = runtime_tree(parent, log_scan)
    sentinel = establish(data)
    backup = tmp_path / 'backup'
    shutil.copytree(data, backup, symlinks=True)
    store = ProductStore(data, 'odoo')
    try:  # after the backup, the token is rotated (the backup's token is the one a restore brings back)
        state, _ = store.change_token(secrets.token_urlsafe(32), action='rotate')
        log_scan.watch_state(state)
    finally:
        store.close()
    after_tick(tmp_path, sentinel.st_ctime_ns)
    supervisor_restore(backup, data)
    restored = (data / 'state.json').read_bytes()
    assert boot(parent, VirtualRoot()) == REOWNED % len(list(data.rglob('*')))
    switch_off = rd.detect(data, enabled=False)
    assert switch_off == rd.Detection(marker=True, active=False, sentinel=rd.INACTIVE) and switch_off.restored
    switch_on = rd.detect(data, enabled=True)
    assert switch_on == rd.Detection(marker=True, active=True, sentinel=rd.MISMATCH) and switch_on.restored
    assert (data / 'state.json').read_bytes() == restored  # detection reads no state and writes none
    # The boot gate's last step (HM-13b): a new sentinel and record; the marker stays until the gate removes it.
    rd.rebuild(data, enabled=True)
    assert rd.detect(data, enabled=True) == rd.Detection(marker=True, active=True, sentinel=rd.CONSISTENT)


def test_a_first_start_that_finds_the_marker_still_reads_as_a_restore(tmp_path, log_scan):
    # A backup from before the switch was on (no sentinel yet), restored onto a release with it on: the first start
    # makes the two files as any first start does, and the marker alone keeps the restore detected, also at the next
    # start when the boot gate (HM-13b) stopped before it removed the marker.
    parent = tmp_path / 'data'
    parent.mkdir()
    data = runtime_tree(parent, log_scan)
    backup = tmp_path / 'backup'
    shutil.copytree(data, backup, symlinks=True)
    supervisor_restore(backup, data)
    assert boot(parent, VirtualRoot()) == REOWNED % len(list(data.rglob('*')))
    first = rd.detect(data, enabled=True)
    assert first == rd.Detection(marker=True, active=True, sentinel=rd.ESTABLISHED) and first.restored
    again = rd.detect(data, enabled=True)
    assert again == rd.Detection(marker=True, active=True, sentinel=rd.CONSISTENT) and again.restored


MALFORMED = {
    'not JSON': lambda real: b'{"version": 1',
    'not an object': lambda real: json.dumps([1, real['st_ino'], real['st_ctime_ns']]).encode(),
    'a duplicated key': lambda real: ('{"version": 1, "st_ino": %d, "st_ino": %d, "st_ctime_ns": %d}' % (
        real['st_ino'], real['st_ino'], real['st_ctime_ns'])).encode(),
    'a key too many': lambda real: json.dumps({**real, 'st_dev': 1}).encode(),
    'a key missing': lambda real: json.dumps({'version': 1, 'st_ino': real['st_ino']}).encode(),
    'another version': lambda real: json.dumps({**real, 'version': 2}).encode(),
    'a boolean': lambda real: json.dumps({**real, 'version': True}).encode(),
    'a boolean inode': lambda real: json.dumps({**real, 'st_ino': True}).encode(),
    'a boolean ctime': lambda real: json.dumps({**real, 'st_ctime_ns': False}).encode(),
    'a float': lambda real: json.dumps({**real, 'st_ctime_ns': float(real['st_ctime_ns'])}).encode(),
    'a string': lambda real: json.dumps({**real, 'st_ino': str(real['st_ino'])}).encode(),
    'a negative number': lambda real: json.dumps({**real, 'st_ino': -1}).encode(),
    'NaN': lambda real: ('{"version": 1, "st_ino": NaN, "st_ctime_ns": %d}' % real['st_ctime_ns']).encode(),
    'too large': lambda real: json.dumps(real).encode() + b' ' * rd.RECORD_LIMIT,
    'nested too deep': lambda real: b'[' * 4000,
    'not UTF-8': lambda real: b'\xff\xff',
    'empty': lambda real: b'',
}


@pytest.mark.parametrize('name', sorted(MALFORMED))
def test_a_malformed_record_reads_as_a_restore(tmp_path, log_scan, name):
    data = runtime_tree(tmp_path, log_scan)
    establish(data)
    (data / rd.RECORD).write_bytes(MALFORMED[name](record_of(data)))
    before = snapshot(data)
    detection = rd.detect(data, enabled=True)
    assert detection == rd.Detection(marker=False, active=True, sentinel=rd.RECORD_INVALID) and detection.restored
    assert snapshot(data) == before


@pytest.mark.parametrize('kind', ['a link to a good copy', 'a second name', 'a directory', 'a FIFO', 'unreadable',
                                  'another owner', 'reported larger than the limit'])
def test_an_unsafe_record_reads_as_a_restore(tmp_path, log_scan, monkeypatch, kind):
    data = runtime_tree(tmp_path, log_scan)
    establish(data)
    record = data / rd.RECORD
    if kind == 'a link to a good copy':
        record.rename(data / 'record-copy')
        record.symlink_to('record-copy')
    elif kind == 'a second name':
        os.link(record, data / 'record-copy')
    elif kind == 'a directory':
        record.unlink()
        record.mkdir()
    elif kind == 'a FIFO':
        record.unlink()
        os.mkfifo(record)
    elif kind == 'unreadable':
        calls = Calls()
        calls.fail('open', rd.RECORD, PermissionError(errno.EACCES, os.strerror(errno.EACCES)))
        monkeypatch.setattr(rd, 'os', calls)
    else:  # what fstat says about the record: another owner, or a size past the limit (its bytes still a good record)
        held = inode(record)

        def fstat(fd):
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) != held:
                return info
            owner = (info.st_uid + 1, info.st_gid) if kind == 'another owner' else (info.st_uid, info.st_gid)
            seen = Seen(info, owner)
            if kind == 'reported larger than the limit':
                seen.st_size = rd.RECORD_LIMIT + 1
            return seen
        calls = Calls()
        calls.override('fstat', fstat)
        monkeypatch.setattr(rd, 'os', calls)
    before = snapshot(data)
    with deadline(5):  # a record opened without O_NONBLOCK would block on the FIFO: fail fast, never hang the run
        detection = rd.detect(data, enabled=True)
    assert detection == rd.Detection(marker=False, active=True, sentinel=rd.RECORD_INVALID)
    assert snapshot(data) == before


@pytest.mark.parametrize('moved', ['st_ino', 'st_ctime_ns'])
def test_the_record_names_the_sentinel_by_inode_and_ctime_together(tmp_path, log_scan, monkeypatch, moved):
    # Either number alone differing is another file (review HM-13a X4: the same ctime with another inode too).
    data = runtime_tree(tmp_path, log_scan)
    establish(data)

    def stat(name, **kwargs):
        info = os.stat(name, **kwargs)
        if name != rd.SENTINEL:
            return info
        seen = Seen(info, (info.st_uid, info.st_gid))
        setattr(seen, moved, getattr(info, moved) + 1)
        return seen
    calls = Calls()
    calls.override('stat', stat)
    monkeypatch.setattr(rd, 'os', calls)
    assert rd.detect(data, enabled=True) == rd.Detection(marker=False, active=True, sentinel=rd.MISMATCH)


@pytest.mark.parametrize('record', ['kept', 'missing'])
@pytest.mark.parametrize('kind', ['a directory', 'a link', 'an unanswerable lookup'])
def test_a_sentinel_that_is_not_a_plain_file_reads_as_a_restore(tmp_path, log_scan, monkeypatch, kind, record):
    # Never what an interrupted first start leaves: a restore even without a record or profile data (not rebuilt).
    data = runtime_tree(tmp_path, log_scan)
    establish(data)
    if record == 'missing':
        (data / rd.RECORD).unlink()
    sentinel = data / rd.SENTINEL
    if kind == 'a directory':
        sentinel.unlink()
        sentinel.mkdir()
    elif kind == 'a link':
        sentinel.unlink()
        sentinel.symlink_to(rd.RECORD)
    else:
        calls = Calls()
        calls.fail('stat', rd.SENTINEL, OSError(errno.EIO, os.strerror(errno.EIO)))
        monkeypatch.setattr(rd, 'os', calls)
    before = snapshot(data)
    assert rd.detect(data, enabled=True) == rd.Detection(marker=False, active=True, sentinel=rd.SENTINEL_INVALID)
    assert snapshot(data) == before


def restored_with_profile_data(tmp_path, log_scan):
    """A product with profile data whose sentinel was replaced (a restore, signal 2): what rebuild() repairs."""
    data = runtime_tree(tmp_path, log_scan)
    sentinel = establish(data)
    add_profile_data(data, 'index')
    after_tick(tmp_path, sentinel.st_ctime_ns)
    CHANGES['a new file in its name'](data / rd.SENTINEL)
    assert rd.detect(data, enabled=True).sentinel == rd.MISMATCH
    return data


REBUILD_STEPS = {  # rebuild()'s calls in order: (os function, name, nth such call, the verdict after a stop there)
    'removing the old sentinel': ('unlink', rd.SENTINEL, 1, rd.MISMATCH),
    'creating the sentinel': ('open', rd.SENTINEL, 1, rd.SENTINEL_MISSING),
    'syncing the sentinel': ('fsync', None, 1, rd.MISMATCH),
    'syncing the directory': ('fsync', None, 2, rd.MISMATCH),
    'clearing a leftover record': ('unlink', rd.TEMPORARY, 1, rd.MISMATCH),
    'creating the new record': ('open', rd.TEMPORARY, 1, rd.MISMATCH),
    'syncing the new record': ('fsync', None, 3, rd.MISMATCH),
    'replacing the record': ('replace', rd.TEMPORARY, 1, rd.MISMATCH),
    'syncing the directory again': ('fsync', None, 4, rd.CONSISTENT),
}


@pytest.mark.parametrize('stop', ['crash', 'error'])
@pytest.mark.parametrize('step', list(REBUILD_STEPS))
def test_an_interrupted_or_failed_rebuild_leaves_the_restore_visible(tmp_path, log_scan, monkeypatch, step, stop):
    # rebuild() is the boot gate's last step before the marker goes (HM-13b step F). A stop anywhere before the new
    # record is in place still reads as a restore, so the next start runs the gate again; then rebuild() completes.
    data = restored_with_profile_data(tmp_path, log_scan)
    name, subject, nth, verdict = REBUILD_STEPS[step]
    calls = Calls()
    calls.fail(name, subject, Crash(step) if stop == 'crash' else OSError(errno.EIO, os.strerror(errno.EIO)), nth)
    monkeypatch.setattr(rd, 'os', calls)
    with pytest.raises(Crash if stop == 'crash' else ConfigError):
        rd.rebuild(data, enabled=True)
    monkeypatch.setattr(rd, 'os', os)
    assert rd.detect(data, enabled=True).sentinel == verdict
    if stop == 'error':
        assert not (data / rd.TEMPORARY).exists()  # a failure cleans up after itself; a crash leaves it to the next
    rd.rebuild(data, enabled=True)
    assert rd.detect(data, enabled=True).sentinel == rd.CONSISTENT
    assert not (data / rd.TEMPORARY).exists()


def test_a_rebuild_checks_what_it_wrote(tmp_path, log_scan, monkeypatch):
    data = restored_with_profile_data(tmp_path, log_scan)

    class Shifted(Seen):
        def __init__(self, info):
            super().__init__(info, (info.st_uid, info.st_gid))
            self.st_ctime_ns = info.st_ctime_ns + 1
    calls = Calls()
    calls.override('fstat', lambda fd: Shifted(os.fstat(fd)))
    monkeypatch.setattr(rd, 'os', calls)
    with pytest.raises(ConfigError):  # the record names a file that is not the sentinel: refused, not left consistent
        rd.rebuild(data, enabled=True)


@pytest.mark.parametrize('profile_data', [None, 'index'])
def test_a_rebuild_is_only_for_an_active_product(tmp_path, log_scan, monkeypatch, profile_data):
    # The boot gate calls rebuild() only when detect() was active; rebuild() also refuses on its own (review HM-13a
    # SF-10), so a product that is not enabled and has no profile data never gets the two files.
    data = runtime_tree(tmp_path, log_scan)
    add_profile_data(data, profile_data)
    if profile_data is None:
        before = snapshot(data)
        calls = Calls()
        monkeypatch.setattr(rd, 'os', calls)
        with pytest.raises(ConfigError):
            rd.rebuild(data, enabled=False)
        assert calls.made == [('open', str(data)), ('stat', 'profiles.json'), ('stat', 'profiles'), ('close', None)]
        assert snapshot(data) == before
    else:  # dormant profiles: the sentinel is on without the switch
        rd.rebuild(data, enabled=False)
        assert rd.detect(data, enabled=False) == rd.Detection(marker=False, active=True, sentinel=rd.CONSISTENT)


def test_a_sentinel_that_cannot_be_made_stops_the_start(tmp_path, log_scan, monkeypatch):
    data = runtime_tree(tmp_path, log_scan)
    calls = Calls()
    calls.fail('open', rd.SENTINEL, OSError(errno.ENOSPC, os.strerror(errno.ENOSPC)))
    monkeypatch.setattr(rd, 'os', calls)
    with pytest.raises(ConfigError):
        rd.detect(data, enabled=True)
    monkeypatch.setattr(rd, 'os', os)
    assert not (data / rd.SENTINEL).exists() and not (data / rd.RECORD).exists()
    assert rd.detect(data, enabled=True).sentinel == rd.ESTABLISHED  # the next start tries again


def test_detection_needs_its_directory(tmp_path):
    with pytest.raises(ConfigError):
        rd.detect(tmp_path / 'absent', enabled=False)
    (tmp_path / 'link').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ConfigError):
        rd.detect(tmp_path / 'link', enabled=True)
    with pytest.raises(ConfigError):
        rd.rebuild(tmp_path / 'absent', enabled=True)


# ---- the container acceptance's restore stage (packaging/container_probe.py) --------------------------------------

def test_the_container_probes_restore_stage_meets_the_entrypoint(tmp_path, log_scan, monkeypatch):
    # Every release's container acceptance restores /data/mcp as Supervisor does, starts the real image and checks what
    # the entrypoint left (review HM-13a MF-1). Its two steps here, with the real entrypoint between them.
    parent = tmp_path / 'data'
    parent.mkdir()
    data = runtime_tree(parent, log_scan)
    vroot = VirtualRoot()
    vroot.own(data, RUNTIME)
    probe = container_probe(monkeypatch, data, vroot)
    restored, state = probe.restore_as_supervisor()
    assert {vroot.owner(path.lstat()) for path in [data, *data.rglob('*')]} == {RESTORE_OWNER}
    assert boot(parent, vroot) == REOWNED % (len(restored) + 1)  # the restored entries and the marker
    probe.check_restored_start(restored, state)


# ---- as root (the CI): real owners, and what the runtime user can do afterwards -----------------------------------

def require_root():
    assert os.geteuid() == 0, ('needs root: the CI runs pytest as root (packaging/unit.sh); an unprivileged run '
                               'fails here on purpose (docs/provenance/ha-multiprofile-HM-13a-20261114.md)')


def as_runtime_user(function, *args):
    """function(*args) in a forked child that is uid and gid 10001, as the management process is; its JSON result.
    Root may read and write anything: what the runtime user cannot do would pass unseen as root."""
    reader, writer = os.pipe()
    pid = os.fork()
    if pid == 0:  # the child never returns
        code = 1
        try:
            try:
                os.close(reader)
                os.setgroups([])
                os.setgid(RUNTIME[1])
                os.setuid(RUNTIME[0])
                os.umask(0o077)
                answer = json.dumps({'result': function(*args)})
                code = 0
            except BaseException as error:
                answer = json.dumps({'error': f'{type(error).__name__}: {error}'})
            os.write(writer, answer.encode())
        finally:
            os._exit(code)
    os.close(writer)
    with os.fdopen(reader, 'rb') as stream:
        raw = stream.read()
    _, status = os.waitpid(pid, 0)
    answer = json.loads(raw)
    assert os.waitstatus_to_exitcode(status) == 0 and 'result' in answer, answer
    return answer['result']


def start_runtime(directory):
    """The management process's start with the switch on: the default state, then the sentinel."""
    directory = Path(directory)
    ProductStore(directory, 'odoo').close()
    detection = rd.detect(directory, enabled=True)
    return [detection.marker, detection.active, detection.sentinel]


def detect_and_rebuild(directory):
    directory = Path(directory)
    before = rd.detect(directory, enabled=True)
    rd.rebuild(directory, enabled=True)
    after = rd.detect(directory, enabled=True)
    store = ProductStore(directory, 'odoo')
    try:
        loaded = store.load().product
    finally:
        store.close()
    return {'before': [before.marker, before.active, before.sentinel],
            'after': [after.marker, after.active, after.sentinel], 'state': loaded}


@pytest.fixture
def reachable():
    """A directory the runtime user can reach: pytest's own temporary directories are private to root."""
    path = Path(tempfile.mkdtemp(prefix='hm13a-'))
    path.chmod(0o755)
    parent = path / 'data'
    parent.mkdir()
    parent.chmod(0o755)
    try:
        yield parent
    finally:
        shutil.rmtree(path)


def owners_of(data):
    return {(path.lstat().st_uid, path.lstat().st_gid) for path in [data, *data.rglob('*')]}


def test_root_backup_restore_and_repair(reachable):
    require_root()
    data = reachable / 'mcp'
    data.mkdir(mode=0o700)
    os.chown(data, *RUNTIME)
    assert as_runtime_user(start_runtime, str(data)) == [False, True, rd.ESTABLISHED]
    backup = reachable.parent / 'backup'
    shutil.copytree(data, backup, symlinks=True)
    after_tick(reachable.parent, (data / rd.SENTINEL).lstat().st_ctime_ns)
    supervisor_restore(backup, data)
    assert owners_of(data) == {RESTORE_OWNER}
    log = io.StringIO()
    with redirect_stderr(log):
        entrypoint().prepare_data(reachable)
    entries = [data, *data.rglob('*')]
    assert log.getvalue() == REOWNED % (len(entries) - 1)
    assert owners_of(data) == {RUNTIME}
    assert all(stat.S_IMODE(path.lstat().st_mode) == (0o700 if path.is_dir() else 0o600) for path in entries)
    marker = (data / rd.MARKER).lstat()
    assert stat.S_ISREG(marker.st_mode) and marker.st_size == 0
    # The management process (uid 10001) sees both signals, reads the record, rebuilds the sentinel, loads its state.
    assert as_runtime_user(detect_and_rebuild, str(data)) == {
        'before': [True, True, rd.MISMATCH], 'after': [True, True, rd.CONSISTENT], 'state': 'odoo'}


def test_root_start_without_a_restore_changes_nothing(reachable):
    require_root()
    data = reachable / 'mcp'
    data.mkdir(mode=0o700)
    os.chown(data, *RUNTIME)
    assert as_runtime_user(start_runtime, str(data)) == [False, True, rd.ESTABLISHED]
    before, owners = snapshot(data), owners_of(data)
    for _ in range(2):
        log = io.StringIO()
        with redirect_stderr(log):
            entrypoint().prepare_data(reachable)
        assert log.getvalue() == ''
    assert snapshot(data) == before and owners_of(data) == owners == {RUNTIME}
    assert as_runtime_user(start_runtime, str(data)) == [False, True, rd.CONSISTENT]


@pytest.mark.parametrize('profile_data', [None, 'index'])
def test_root_marker_name_taken_by_a_directory(reachable, profile_data):
    require_root()
    data = restored_tree(reachable, profile_data)  # made by root: root-owned for real
    (data / rd.MARKER).mkdir()
    before = snapshot(data)
    log = io.StringIO()
    if profile_data:
        with redirect_stderr(log), pytest.raises(RuntimeError, match='restore marker unavailable'):
            entrypoint().prepare_data(reachable)
        assert log.getvalue() == REFUSED % IN_USE
        assert snapshot(data) == before and owners_of(data) == {RESTORE_OWNER}
    else:
        with redirect_stderr(log):
            entrypoint().prepare_data(reachable)
        assert log.getvalue() == WARNING % IN_USE + REOWNED % len(list(data.rglob('*')))
        assert owners_of(data) == {RUNTIME}


def test_root_the_container_probes_restore_stage_meets_the_entrypoint(reachable, log_scan, monkeypatch):
    require_root()
    data = runtime_tree(reachable, log_scan)
    for path in [data, *data.rglob('*')]:
        os.chown(path, *RUNTIME)  # as the runtime keeps it
    probe = container_probe(monkeypatch, data)
    restored, state = probe.restore_as_supervisor()
    assert owners_of(data) == {RESTORE_OWNER}
    log = io.StringIO()
    with redirect_stderr(log):
        entrypoint().prepare_data(reachable)
    assert log.getvalue() == REOWNED % (len(restored) + 1)
    probe.check_restored_start(restored, state)
