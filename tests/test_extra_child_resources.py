"""HM-09: what an additional profile's child gets beside its own state (multi-profile plan 5.2, 5.4, 10.3; contract 5,
7; C2-SF-3, C2-SF-5, C2-SF-10; C4-SF-6; DQ-07 (a); FM-25, 134).

- oom_score_adj 500 (absolute: the add-on's container is at 200, HA Core at -300) and nice +5, written by the child
  itself before it execs (a fresh single-threaded interpreter, -I -S, between the fork and the real command: no
  preexec_fn in a process with threads), so the kernel prefers to kill and to slow an additional profile's child, not
  the default profile's. Its argv, environment, working directory and signal dispositions are the real command's.
  The default profile's child is spawned as before. What the platform refuses is not assumed: the child starts
  anyway and one WARNING names what was not applied (HM-03a writes the HAOS values once).
- The proof runs as an unprivileged user: as uid 10001 after a real drop when the test runs as root (the CI), on a
  baseline of 200 as Docker gives an add-on; as the test's own user otherwise.
- Memory (contract 5): a save or the panel's restart of an additional profile reads MemAvailable; below the product's
  MiB per child plus the 256 MiB reserve, the state is saved but the child is not started (blocked, memory_capacity).
  The boot and the watchdog never check. Unreadable: the child starts and one WARNING says so. With a readable cgroup
  memory.max the PaaS formula decides at open instead (disabled memory_capacity, with required_memory_mib).
- File descriptors: spawning and reaping children (through the wrapper too) leaves none open; without the open-file
  budget (HM-08) no additional profile is served, so start_all starts the default profile only.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

import pytest

from admin_write_headers import reviewed_headers
from lifecycle_runtime import lifecycle_lines, manager_rig, open_fds, proc_cmdline, until, watch
from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import lifecycle, profile_runtime, profiles
from mcp_admin_core.lifecycle import ChildSpec, Supervisor
from multi_profile_runtime import stored
from test_router_passthrough import FakeResource
from test_single_profile_golden import ADMIN

pytestmark = pytest.mark.usefixtures('log_scan')
ROOT = Path(__file__).resolve().parents[1]


# ---- the wrapper ----

async def test_only_an_additional_profiles_child_goes_through_the_wrapper(tmp_path, log_scan):
    async with manager_rig(tmp_path, extras=1) as rig:
        watch(log_scan, rig)
        b, = rig.extras
        await rig.manager.launch()
        await rig.manager.start_all()
        await until(lambda: rig.pid('default') and rig.pid(b) and rig.supervisor(b).resource_state is not None)
        for profile_id in ('default', b):
            argv = list(rig.supervisor(profile_id).spec.argv)
            assert proc_cmdline(rig.pid(profile_id)) == argv  # the real command, whatever ran before its exec
        assert rig.supervisor('default').resources is None and rig.supervisor('default').resource_state is None
        state = rig.supervisor(b).resource_state
        assert set(state) == {'oom_score_adj', 'nice'}
        if state['oom_score_adj']:
            assert int(Path(f'/proc/{rig.pid(b)}/oom_score_adj').read_text()) == 500


SHOW = ('printf "%s\\n" "$@" > "$OUT_DIR/args"; env | sort > "$OUT_DIR/env"; pwd > "$OUT_DIR/cwd"; '
        'grep -E "^Sig(Ign|Blk)" /proc/self/status > "$OUT_DIR/signals"; touch "$OUT_DIR/done"; '
        'exec sleep 30')


async def test_the_wrapper_hands_the_child_its_argv_environment_directory_and_signals(tmp_path, log_scan):
    """The same /bin/sh child spawned plainly and through the wrapper sees the same arguments, environment (no
    LC_CTYPE the wrapper's interpreter would add: PEP 538), working directory and ignored or blocked signals."""
    seen = {}
    for name, resources in (('plain', None), ('wrapped', lifecycle.ChildResources())):
        out = tmp_path / name
        out.mkdir()
        cwd = tmp_path / 'cwd'
        cwd.mkdir(exist_ok=True)
        spec = ChildSpec(('/bin/sh', '-c', SHOW.replace('$OUT_DIR', str(out)), 'sh', 'one', 'two words'),
                         {'PATH': '/usr/bin:/bin', 'HOME': str(cwd)}, cwd)
        supervisor = Supervisor(spec, grace=0.2, delays=(30,), resources=resources)
        await supervisor.start()
        try:
            await until(lambda: (out / 'done').exists())
        finally:
            await supervisor.stop()
        seen[name] = {part: (out / part).read_text() for part in ('args', 'env', 'cwd', 'signals')}
    assert seen['wrapped'] == seen['plain']
    assert seen['plain']['args'] == 'one\ntwo words\n' and 'LC_CTYPE' not in seen['plain']['env']


def test_child_resources_are_bounded():
    assert lifecycle.ChildResources() == lifecycle.EXTRA_CHILD_RESOURCES == lifecycle.ChildResources(500, 5)
    for bad in (dict(oom_score_adj=1001), dict(oom_score_adj=-1001), dict(oom_score_adj=True), dict(nice=40),
                dict(nice=-40), dict(nice=1.5)):
        with pytest.raises(ValueError):
            lifecycle.ChildResources(**bad)


# ---- as an unprivileged user (uid 10001 when the test runs as root) ----

@pytest.fixture(scope='module')
def probe_python():
    """The interpreter the probe runs on: a copy readable by uid 10001 when the test runs as root (never chmod an
    existing private interpreter), the test's own otherwise."""
    if os.geteuid() != 0:
        yield sys.executable
        return
    with tempfile.TemporaryDirectory(prefix='hm09-uid-') as directory:
        temp = Path(directory)
        temp.chmod(0o755)
        interpreter = Path(sys.executable).resolve().parents[1]
        shutil.copytree(interpreter, temp / 'python', symlinks=True)
        shutil.copytree(ROOT / '.venv', temp / '.venv', symlinks=True)
        for path in (temp / '.venv/bin').glob('python*'):
            path.unlink()
        (temp / '.venv/bin/python').symlink_to(temp / 'python/bin/python3.13')
        (temp / '.venv/pyvenv.cfg').write_text(
            f'home = {temp}/python/bin\ninclude-system-site-packages = false\nversion = 3.13.2\n')
        yield str(temp / '.venv/bin/python')


def probe(python, resources, baseline=200):
    """Run tests/child_resources_probe.py in a fresh directory of the system's temporary directory (pytest's own is
    private to its user: uid 10001 could not reach a child's working directory there)."""
    with tempfile.TemporaryDirectory(prefix='hm09-probe-') as directory:
        temp = Path(directory)
        work = temp / 'work'
        work.mkdir(mode=0o700)
        if os.geteuid() == 0:
            temp.chmod(0o755)
            os.chown(work, 10001, 10001)
        config = {'baseline': baseline, 'resources': resources, 'work': str(work)}
        result = subprocess.run([python, str(ROOT / 'tests/child_resources_probe.py'), json.dumps(config)],
                                capture_output=True, text=True, timeout=90, cwd=temp,
                                env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'packages/mcp-admin-core'),
                                     'PYTHONDONTWRITEBYTECODE': '1'})
    assert result.returncode == 0, result.stderr[-4000:]
    return json.loads(result.stdout)


def test_an_unprivileged_child_gets_oom_score_adj_500_and_nice_5(probe_python):
    report = probe(probe_python, {'oom_score_adj': 500, 'nice': 5})
    expected_uid = 10001 if os.geteuid() == 0 else os.getuid()
    assert report['probe']['uid'] == report['child']['uid'] == expected_uid
    if os.geteuid() == 0:
        assert report['probe']['oom_score_adj'] == 200  # the add-on's baseline, as Docker sets it
    assert report['child']['oom_score_adj'] == 500
    assert report['child']['nice'] == min(19, report['probe']['nice'] + 5)
    assert report['resource_state'] == {'oom_score_adj': True, 'nice': True} and report['status'] == 'running'
    assert not [line for line in report['warnings'] if 'not applied' in line]


def test_resources_an_unprivileged_child_cannot_have_degrade_to_one_warning(probe_python):
    """What an unprivileged process can never do (an oom_score_adj below its floor, a lower nice value): the child
    starts anyway with its parent's values, and one WARNING names both (never assumed done)."""
    report = probe(probe_python, {'oom_score_adj': -1000, 'nice': -5})
    assert report['child']['oom_score_adj'] == report['probe']['oom_score_adj']
    assert report['child']['nice'] == report['probe']['nice']
    assert report['resource_state'] == {'oom_score_adj': False, 'nice': False} and report['status'] == 'running'
    lines = [line for line in report['warnings'] if 'not applied' in line]
    assert len(lines) == 1 and lines[0].startswith('MCP child [profile=aaaaaaaa port=18000 pid=')
    assert lines[0].endswith(']: child resources not applied (oom_score_adj -1000, nice -5); it runs without them')


# ---- memory (contract 5) ----

async def save(rig, profile_id):
    """The panel saves the profile's connection unchanged (a save starts the child again)."""
    state = stored(rig.directory(profile_id))
    async with rig.admin(profile_id) as admin:
        boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
        return await admin.put('/api/backend/patch', json={'changes': {'url': state['connection']['url']}},
                               headers=reviewed_headers(boot, ADMIN))


async def restart(rig, profile_id):
    async with rig.admin(profile_id) as admin:
        boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
        return await admin.post('/api/child/restart', headers=reviewed_headers(boot, ADMIN))


async def test_low_memory_holds_a_save_or_restart_but_never_the_boot(tmp_path, log_scan, monkeypatch):
    """Odoo needs 100 + 256 MiB per additional child: with 300 MiB available the boot still starts B (no check at
    boot), but the panel's save is saved and its child not started (blocked, memory_capacity) and so is its restart
    (202 with blocked_reason); the default profile is never checked; with 400 MiB the restart starts B again."""
    available = {'mib': 300}
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: None)
    monkeypatch.setattr(profiles, 'available_memory_mib', lambda: available['mib'])
    async with manager_rig(tmp_path, extras=1) as rig:
        watch(log_scan, rig)
        b, = rig.extras
        await rig.manager.launch()
        await rig.manager.start_all()
        await until(lambda: rig.pid(b) is not None)
        saved = await save(rig, b)
        assert saved.status_code == 200, saved.text
        supervisor = rig.supervisor(b)
        assert (supervisor.status, supervisor.blocked_reason, rig.pid(b)) == ('blocked', 'memory_capacity', None)
        answered = await restart(rig, b)
        assert answered.status_code == 202 and answered.json()['blocked_reason'] == 'memory_capacity'
        assert any(f'[profile={profiles.log_id(b)} port={rig.ports[b]}]: not started (memory_capacity): 300 MiB of '
                   'memory available, 356 MiB needed' in line for line in lifecycle_lines(log_scan))
        default = await restart(rig, 'default')
        assert default.status_code == 202 and default.json()['blocked_reason'] is None
        await until(lambda: rig.pid('default') is not None)
        available['mib'] = 400
        answered = await restart(rig, b)
        assert answered.status_code == 202 and answered.json()['blocked_reason'] is None
        await until(lambda: rig.pid(b) is not None)
        os.kill(rig.pid(b), signal.SIGKILL)  # the watchdog's restarts do not check either
        available['mib'] = 10
        await until(lambda: supervisor.retry_in is not None)
        supervisor.retry_now()
        await until(lambda: supervisor.status == 'running' and rig.pid(b) is not None)


async def test_unreadable_memory_starts_the_child_and_says_so(tmp_path, log_scan, monkeypatch):
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: None)
    monkeypatch.setattr(profiles, 'available_memory_mib', lambda: None)
    async with manager_rig(tmp_path, extras=1) as rig:
        watch(log_scan, rig)
        b, = rig.extras
        await rig.manager.launch()
        await rig.manager.start_all()
        answered = await restart(rig, b)
        assert answered.status_code == 202 and answered.json()['blocked_reason'] is None
        await until(lambda: rig.pid(b) is not None)
        assert any(f'[profile={profiles.log_id(b)} port={rig.ports[b]}]: MemAvailable cannot be read' in line
                   for line in lifecycle_lines(log_scan))


async def test_a_cgroup_memory_limit_disables_the_profiles_past_the_paas_formula(tmp_path, log_scan, monkeypatch):
    """memory.max of 256 + 3 x 100 MiB runs three Odoo children: the default and two additional ones (PaaS: max(1,
    (556 - 256) // 100) - 1 = 2). The third is disabled memory_capacity (required_memory_mib 656), never started; with
    the cgroup limit MemAvailable is not read."""
    def forbidden():
        raise AssertionError('MemAvailable read although the cgroup limit decides')
    monkeypatch.setattr(profiles, 'memory_limit_mib', lambda: 556)
    monkeypatch.setattr(profiles, 'available_memory_mib', forbidden)
    async with manager_rig(tmp_path, extras=3) as rig:
        watch(log_scan, rig)
        b, c, d = rig.extras
        assert rig.manager.capacity == profiles.capacity('odoo', 556)
        assert rig.entry(d).disabled == {'disabled_reason': 'memory_capacity', 'required_memory_mib': 656}
        await rig.manager.launch()
        await rig.manager.start_all()
        assert rig.pid(b) and rig.pid(c) and rig.supervisor(d).status == 'blocked'
        assert rig.supervisor(d).blocked_reason == 'memory_capacity' and rig.supervisor(d).starts == 0
        answered = await restart(rig, b)
        assert answered.status_code == 202 and answered.json()['blocked_reason'] is None


def test_memory_readings_follow_the_kernels_files(tmp_path, monkeypatch):
    meminfo = tmp_path / 'meminfo'
    meminfo.write_text('MemTotal:        4000000 kB\nMemFree:          200000 kB\nMemAvailable:     524288 kB\n')
    monkeypatch.setattr(profiles, 'MEMINFO', meminfo)
    assert profiles.available_memory_mib() == 512
    meminfo.write_text('MemTotal: 4000000 kB\n')
    assert profiles.available_memory_mib() is None
    monkeypatch.setattr(profiles, 'MEMINFO', tmp_path / 'missing')
    assert profiles.available_memory_mib() is None
    v2, v1 = tmp_path / 'memory.max', tmp_path / 'memory.limit_in_bytes'
    monkeypatch.setattr(profiles, 'CGROUP_MEMORY_LIMITS', (v2, v1))
    assert profiles.memory_limit_mib() is None
    v2.write_text('max\n')
    assert profiles.memory_limit_mib() is None
    v2.write_text(f'{1024 * 1024 * 1024}\n')
    assert profiles.memory_limit_mib() == 1024
    v2.unlink()
    v1.write_text(f'{(1 << 63) - 4096}\n')  # cgroup v1's "no limit"
    assert profiles.memory_limit_mib() is None
    v1.write_text(f'{512 * 1024 * 1024}\n')
    assert profiles.memory_limit_mib() == 512


# ---- file descriptors ----

async def test_spawning_and_reaping_children_leaves_no_descriptor_open(tmp_path, log_scan):
    supervisor = Supervisor(ChildSpec((sys.executable, '-c', 'raise SystemExit(3)'), {'PATH': '/usr/bin:/bin'},
                                      tmp_path), grace=0.05, delays=(30,), resources=lifecycle.ChildResources())
    await supervisor.start()
    await until(lambda: supervisor.retry_in is not None)
    before = open_fds()
    for _ in range(12):
        starts = supervisor.starts
        supervisor.retry_now()
        await until(lambda: supervisor.starts == starts + 1 and supervisor.retry_in is not None)
    assert open_fds() == before
    await supervisor.stop()


async def test_without_the_file_budget_start_all_starts_the_default_profile_only(tmp_path, log_scan, monkeypatch):
    needed, _ = profile_runtime.open_file_budget('odoo')
    monkeypatch.setattr(profile_runtime, 'resource', FakeResource(256, needed - 1))
    async with manager_rig(tmp_path, extras=2) as rig:
        watch(log_scan, rig)
        assert [entry.profile_id for entry in rig.manager.profiles()] == ['default']
        await rig.manager.launch()
        await rig.manager.start_all()
        await until(lambda: rig.pid('default') is not None)
        assert rig.sleepers.ports() == [rig.default_port]
