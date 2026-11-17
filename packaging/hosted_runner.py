"""Preflight of the GitHub-hosted publish job (.github/workflows/release.yaml), before anything is built.

    python packaging/hosted_runner.py RUNNER_KIND RECORD

Runs before the candidate job builds and before the publish job loads the handed-over image (docker load keeps the
image ID only in the classic store).

RUNNER_KIND is the job's ${{ runner.environment }}. The job stops unless
  - the runner is GitHub-hosted: RUNNER_KIND is 'github-hosted' (and so is RUNNER_ENVIRONMENT when the runner sets
    it) on Linux X64. A self-hosted runner never builds or pushes here;
  - Docker keeps images in the classic overlay2 store. The gates rely on "image ID = config digest" (supply_chain.py,
    registry_gate.py); the containerd image store gives manifest or index digests instead. The runner is a disposable
    VM, so when the containerd snapshotter is on, /etc/docker/daemon.json is rewritten with
    features.containerd-snapshotter false (every other key kept), Docker is restarted, and `docker info` must then
    report overlay2 without the containerd snapshotter;
  - the build reaches that same daemon: no ambient variable selects another daemon, context, configuration, builder or
    platform, and the current context is the default one on the local socket;
  - the checked-out build inputs are readable by everyone: the image runs as UID 10001 and Docker copies the
    checkout's modes into it (0.4.17: a private umask made copied runtime files unreadable).
RECORD (a new file; its directory is created 0700 when missing) receives the runner image, the Docker client, server,
API and component versions, the Buildx version, the storage driver and whether this preflight switched the store.
Nothing secret is read or recorded, and nothing is written into the checkout (the supply-chain gate requires a clean
tree).
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
DAEMON_JSON = Path('/etc/docker/daemon.json')
SOCKET = 'unix:///var/run/docker.sock'
# Variables that would send the build, scans or push to another daemon, context, configuration, builder or platform
# than the one checked here. The job itself sets only DOCKER_BUILD_SUMMARY and DOCKER_BUILD_RECORD_UPLOAD ('false').
REDIRECTS = ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH',
             'DOCKER_API_VERSION', 'DOCKER_DEFAULT_PLATFORM', 'BUILDX_BUILDER', 'BUILDX_CONFIG', 'BUILDKIT_HOST')
READABLE = ('pyproject.toml', 'uv.lock', 'packaging/entrypoint.py', 'packaging/management_launcher.py',
            'packaging/container_probe.py', 'packages/mcp-admin-core/mcp_admin_core/__init__.py')
TRAVERSABLE = ('apps', 'packages', 'packaging', 'packages/mcp-admin-core/mcp_admin_core')
BUILDX = re.compile(r'github\.com/docker/buildx v?\d+\.\d+\.\d+\S*( \S+)?')  # recorded, not pinned


class Closed(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Closed(message)


def run(argv, timeout=120):
    """stdout of argv; a failure names the command and its exit status only."""
    try:
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        raise Closed(' '.join(argv[:3]) + ' could not run') from None
    require(result.returncode == 0, '%s failed (exit %d)' % (' '.join(argv[:3]), result.returncode))
    return result.stdout


def decode(text, what):
    try:
        return json.loads(text)
    except ValueError:
        raise Closed(what + ' is not JSON') from None


def docker_info():
    return decode(run(['docker', 'info', '--format', '{{json .}}']), 'docker info')


def containerd_store(info):
    """True when Docker keeps images in the containerd image store (its snapshotter shows in DriverStatus)."""
    return 'containerd.snapshotter' in json.dumps(info.get('DriverStatus'))


def classic_store(info):
    return info.get('Driver') == 'overlay2' and not containerd_store(info)


def without_containerd_store(text):
    """daemon.json text -> the same settings with features.containerd-snapshotter false. Refuses what it cannot read as
    one JSON object, a features value that is not an object, or another storage driver: it never guesses."""
    value = decode(text, '/etc/docker/daemon.json') if text.strip() else {}
    require(isinstance(value, dict), '/etc/docker/daemon.json is not a JSON object')
    features = value.get('features', {})
    require(isinstance(features, dict), '/etc/docker/daemon.json features is not an object')
    require(value.get('storage-driver', 'overlay2') == 'overlay2', '/etc/docker/daemon.json selects another storage driver')
    return dict(value, features=dict(features, **{'containerd-snapshotter': False}))


def wait_for_docker(attempts=60, pause=2.0):
    for _ in range(attempts):
        try:
            return docker_info()
        except Closed:
            time.sleep(pause)
    raise Closed('Docker did not come back after the restart')


def use_classic_store(daemon_json, scratch):
    try:
        text = daemon_json.read_text() if daemon_json.exists() else ''
    except OSError:
        raise Closed('cannot read ' + str(daemon_json)) from None
    staged = scratch / 'daemon.json'
    staged.write_text(json.dumps(without_containerd_store(text), indent=2, sort_keys=True) + '\n')
    run(['sudo', '-n', 'install', '-o', 'root', '-g', 'root', '-m', '0644', str(staged), str(daemon_json)])
    run(['sudo', '-n', 'systemctl', 'restart', 'docker.service'], timeout=180)
    return wait_for_docker()


def world_readable(root):
    for rel in READABLE:
        mode = (root / rel).stat().st_mode
        require(mode & 0o044 == 0o044, 'build input not readable by every user: ' + rel)
    for rel in TRAVERSABLE:
        mode = (root / rel).stat().st_mode
        require(mode & 0o055 == 0o055, 'build input directory not readable by every user: ' + rel)


def write_once(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def preflight(kind, record_path, env=None, root=ROOT, daemon_json=DAEMON_JSON):
    env = os.environ if env is None else env
    require(kind == 'github-hosted' and env.get('RUNNER_ENVIRONMENT', kind) == 'github-hosted',
            'not a GitHub-hosted runner (runner.environment is %r)' % kind)
    require(env.get('RUNNER_OS') == 'Linux' and env.get('RUNNER_ARCH') == 'X64' and platform.machine() == 'x86_64',
            'not a Linux X64 runner')
    found = sorted(name for name in REDIRECTS if name in env)
    require(not found, 'ambient Docker/Buildx target override: ' + ', '.join(found))
    world_readable(root)
    directory = record_path.parent
    if not directory.exists():
        directory.mkdir(mode=0o700, parents=True)
    require(directory.is_dir() and not directory.is_symlink(), 'evidence directory is not a plain directory')
    require(not record_path.exists() and not record_path.is_symlink(), 'runner record already exists')
    require(run(['docker', 'context', 'show']).strip() == 'default', 'Docker context is not the default one')
    contexts = decode(run(['docker', 'context', 'inspect', 'default']), 'docker context inspect')
    require(isinstance(contexts, list) and len(contexts) == 1
            and contexts[0].get('Endpoints', {}).get('docker', {}).get('Host') == SOCKET,
            'the default Docker context is not the local socket')
    info = docker_info()
    switched = False
    if not classic_store(info):
        require(containerd_store(info), 'Docker storage driver %r is not overlay2' % info.get('Driver'))
        with tempfile.TemporaryDirectory(prefix='woow-daemon-json-', dir=env.get('RUNNER_TEMP') or None) as scratch:
            info = use_classic_store(daemon_json, Path(scratch))
        switched = True
        require(classic_store(info), 'Docker still uses the containerd image store after the restart')
    require(info.get('OSType') == 'linux' and info.get('Architecture') in ('x86_64', 'amd64'), 'Docker engine platform')
    versions = decode(run(['docker', 'version', '--format', '{{json .}}']), 'docker version')
    client, server = versions.get('Client') or {}, versions.get('Server') or {}
    require(server.get('Os') == 'linux' and server.get('Arch') == 'amd64', 'Docker server platform')
    buildx = (run(['docker', 'buildx', 'version']).strip().splitlines() or [''])[0]
    require(BUILDX.fullmatch(buildx) is not None, 'unexpected Buildx version output')
    record = {
        'runner': {'environment': kind, 'os': env.get('RUNNER_OS'), 'arch': env.get('RUNNER_ARCH'),
                   'image_os': env.get('ImageOS'), 'image_version': env.get('ImageVersion'),
                   'kernel': platform.release()},
        'docker': {'client': client.get('Version'), 'server': server.get('Version'), 'api': server.get('ApiVersion'),
                   'components': {c.get('Name'): c.get('Version') for c in server.get('Components') or []
                                  if isinstance(c, dict)},
                   'operating_system': info.get('OperatingSystem'), 'storage_driver': info.get('Driver'),
                   'driver_status': info.get('DriverStatus'), 'image_store': 'classic',
                   'switched_from_containerd_store': switched},
        'buildx': buildx,
        'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    write_once(record_path, record)
    return record


def main(argv):
    require(len(argv) == 2, 'usage: hosted_runner.py RUNNER_KIND RECORD')
    record = preflight(argv[0], Path(argv[1]))
    print('PASS: GitHub-hosted runner %s; Docker %s with the classic overlay2 store%s; %s' % (
        record['runner']['image_version'], record['docker']['server'],
        ' (switched from the containerd store)' if record['docker']['switched_from_containerd_store'] else '',
        record['buildx']))


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (Closed, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        detail = str(exc) if isinstance(exc, Closed) else type(exc).__name__
        raise SystemExit('hosted runner preflight CLOSED: ' + detail) from None
