"""J1900 instruction-set check of the tested candidate image, before any registry credential (DQ-42: every release).

    python packaging/j1900_check.py APP CANDIDATE_DIR EVIDENCE_DIR

The J1900 the add-ons ship on has no AVX, AVX2 or AVX-512. QEMU user mode with -cpu Nehalem is stricter: Nehalem also
lacks MOVBE and AES-NI (docs/operations/release-decision-0.1.7.md). The image is first bound to its candidate evidence
(supply_chain.verify_current: the local tag is the tested image ID, its source is HEAD and its scans are unchanged);
every check then runs on that image ID, in a container with --network none --read-only --user 10001:10001
--cap-drop ALL and no-new-privileges, with only j1900_probe.py and the QEMU binary mounted read-only:
  1. each Python environment the image runs, the core venv /opt/woow/.venv and the child venv
     /opt/woow/apps/<app>/.venv (n8n has none: its child is Node): j1900_probe.py lists every native extension module
     and imports each natively; the natively importable ones are imported again under
     `qemu-x86_64-static -cpu Nehalem` and must all import, with no SIGILL; a small smoke through C code (hashlib, ssl,
     zlib, sqlite3, decimal, re) must give the same result both ways;
  2. n8n: Node loads better-sqlite3, builds an FTS5 table, hashes and compresses, natively and under QEMU, with the
     same result.
A SIGILL (exit 132, or QEMU's "uncaught target signal 4") fails the release and names the last module tried. QEMU is
the runner's own apt package qemu-user-static (its version, version line and binary SHA-256 are recorded). The result
is EVIDENCE_DIR/j1900-<app>.json. Limit: QEMU checks only the code that actually runs (the imports and the smokes), not
every path of the program.

Ported from artifacts/ha-multiprofile-parity-20261114/wave4/release-0.4.14-builder/inpod_0414.py (docker_run_argv,
j1900_exec, j1900_env, j1900; written for the dropped k3s builder and never run there): the same container flags,
verdicts and record. Changed: the image is bound through supply_chain.verify_current instead of builder records,
qemu-user-static comes from the hosted runner's apt, the work directory is private to the run (under RUNNER_TEMP), and a
failure names the step, its exit status, the last module tried and a short stderr tail.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

import supply_chain
from supply_chain import PRODUCTS, inspect_image, verify_current
from validate import version_for

HERE = Path(__file__).resolve().parent
PROBE = HERE / 'j1900_probe.py'
QEMU = Path('/usr/bin/qemu-x86_64-static')
QEMU_PACKAGE = 'qemu-user-static'
CPU = 'Nehalem'
MOUNT = '/j1900'
CORE_PYTHON = '/opt/woow/.venv/bin/python'
NODE = '/usr/local/bin/node'
ISOLATION = ('--network', 'none', '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,size=256m,mode=1777',
             '--user', '10001:10001', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
             '--pids-limit', '512', '--memory', '4g', '-e', 'HOME=/tmp')
TIMEOUTS = {'list': 300, 'native': 900, 'qemu': 2400, 'smoke': 300, 'smoke-qemu': 900, 'node': 300,
            'node-qemu': 1200}
NODE_SMOKE = (
    "const db=require('/opt/woow/apps/n8n/node_modules/better-sqlite3')(':memory:');"
    "db.exec('create virtual table t using fts5(a)');db.prepare('insert into t values (?)').run('hello j1900');"
    "const c=db.prepare(\"select count(*) c from t where t match 'hello'\").get().c;"
    "const h=require('crypto').createHash('sha256').update('j1900').digest('hex');"
    "const z=require('zlib');const n=z.gunzipSync(z.gzipSync(Buffer.from('j1900'.repeat(1000)))).length;"
    "process.stdout.write(JSON.stringify({node:process.version,fts5:c,sha256:h,zlib:n})+'\\n');")
SCOPE = 'imports every natively importable extension module plus a smoke run; not a full runtime trace'


class Closed(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Closed(message)


def sha_file(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def child_python(app):
    return '/opt/woow/apps/%s/.venv/bin/python' % app


def docker_run_argv(image_id, entrypoint, args, name, work):
    return ['docker', 'run', '--rm', '--name', name, *ISOLATION,
            '--mount', 'type=bind,source=%s,target=%s,readonly' % (work, MOUNT),
            '--entrypoint', entrypoint, image_id, *args]


def run_in_image(image_id, entrypoint, args, label, timeout, work):
    name = 'woow-j1900-%s-%s' % (label, secrets.token_hex(4))
    try:
        return subprocess.run(docker_run_argv(image_id, entrypoint, args, name, work), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        raise Closed('%s timed out after %d s' % (label, timeout)) from None


def last_json(raw):
    for line in reversed(raw.decode(errors='replace').splitlines()):
        line = line.strip()
        if line.startswith(('{', '[')):
            try:
                return json.loads(line)
            except ValueError:
                break
    raise Closed('no JSON result')


def illegal_instruction(result):
    return result.returncode in (132, -4) or b'uncaught target signal 4' in result.stderr


def failure(label, result, why):
    """Names the step, its exit status, the last module the probe tried and a short stderr tail. The image already
    passed the all-layer secret scan, and the probe prints module and exception type names only."""
    tried = [line[4:].strip() for line in result.stdout.decode(errors='replace').splitlines() if line.startswith('TRY ')]
    tail = ' | '.join(line[:200] for line in result.stderr.decode(errors='replace').splitlines()[-6:])
    return '%s: %s (exit %d%s)%s' % (label, why, result.returncode, ', last TRY ' + tried[-1] if tried else '',
                                     '; stderr: ' + tail if tail else '')


def write_public(path, value):
    """A module list the container (UID 10001) reads through the read-only mount."""
    path.write_text(json.dumps(value))
    os.chmod(path, 0o644)


def install_qemu(run=subprocess.run, attempts=3, pause=10.0):
    """qemu-user-static from the runner's apt (Ubuntu 24.04 ships /usr/bin/qemu-x86_64-static); returns what the record
    keeps. Installing it registers binfmt handlers for foreign architectures only, on this disposable runner. A mirror
    hiccup is retried; whatever gets installed is what the record names."""
    apt = ['sudo', '-n', 'env', 'DEBIAN_FRONTEND=noninteractive', 'apt-get']
    for argv in ([*apt, 'update', '-q'], [*apt, 'install', '-y', '-q', '--no-install-recommends', QEMU_PACKAGE]):
        for attempt in range(attempts):
            result = run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
            if result.returncode == 0:
                break
            if attempt + 1 < attempts:
                time.sleep(pause)
        require(result.returncode == 0, 'apt-get %s failed (exit %d)' % (argv[5], result.returncode))
    query = run(['dpkg-query', '-W', '-f=${Version}', QEMU_PACKAGE], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=60)
    version = query.stdout.decode().strip()
    require(query.returncode == 0 and version, QEMU_PACKAGE + ' is not installed')
    binary = Path(os.path.realpath(QEMU))
    require(binary.is_file(), str(QEMU) + ' is missing')
    shown = run([str(binary), '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    line = (shown.stdout.decode(errors='replace').splitlines() or [''])[0].strip()
    require(shown.returncode == 0 and line.startswith('qemu-x86_64 version '), 'unexpected qemu-x86_64-static --version')
    return {'package': QEMU_PACKAGE, 'version': version, 'version_line': line, 'path': str(binary),
            'sha256': sha_file(binary)}


def prepare(work, qemu):
    """The read-only mount: work/bin/qemu-x86_64-static (0755) and work/j1900_probe.py (0644), copies checked."""
    os.chmod(work, 0o755)
    tools = work / 'bin'
    tools.mkdir()
    os.chmod(tools, 0o755)
    shutil.copyfile(qemu, tools / 'qemu-x86_64-static')
    os.chmod(tools / 'qemu-x86_64-static', 0o755)
    shutil.copyfile(PROBE, work / 'j1900_probe.py')
    os.chmod(work / 'j1900_probe.py', 0o644)
    require(sha_file(tools / 'qemu-x86_64-static') == sha_file(qemu)
            and sha_file(work / 'j1900_probe.py') == sha_file(PROBE), 'J1900 tool copies differ')


def check_python(image_id, app, scope, python, work, run=run_in_image):
    label = '%s-%s' % (app, scope)
    qemu, probe = MOUNT + '/bin/qemu-x86_64-static', MOUNT + '/j1900_probe.py'
    listed = run(image_id, python, ['-I', '-B', probe, 'list'], label + '-list', TIMEOUTS['list'], work)
    require(listed.returncode == 0, failure(label + '-list', listed, 'native module listing failed'))
    modules = last_json(listed.stdout)
    require(isinstance(modules, list) and bool(modules) and all(isinstance(m, str) for m in modules),
            label + ': no native extension modules found')
    write_public(work / (label + '-modules.json'), modules)
    native = run(image_id, python, ['-I', '-B', probe, 'import', '%s/%s-modules.json' % (MOUNT, label)],
                 label + '-native', TIMEOUTS['native'], work)
    require(native.returncode == 0, failure(label + '-native', native, 'native import run failed'))
    natively = last_json(native.stdout)
    native_ok = natively.get('ok') if isinstance(natively, dict) else None
    require(isinstance(native_ok, list) and bool(native_ok), label + ': no native module imports natively')
    write_public(work / (label + '-native-ok.json'), native_ok)
    emulated = run(image_id, qemu, ['-cpu', CPU, python, '-I', '-B', probe, 'import',
                                    '%s/%s-native-ok.json' % (MOUNT, label)], label + '-qemu', TIMEOUTS['qemu'], work)
    require(not illegal_instruction(emulated), failure(label + '-qemu', emulated, 'ILLEGAL INSTRUCTION under -cpu ' + CPU))
    require(emulated.returncode == 0, failure(label + '-qemu', emulated, 'emulated import run failed'))
    result = last_json(emulated.stdout)
    differ = sorted(set(native_ok) ^ set(result.get('ok') or [])) + sorted(result.get('err') or {})
    require(result.get('ok') == native_ok and not result.get('err'),
            '%s: modules differ under -cpu %s: %s' % (label, CPU, ', '.join(differ[:8])))
    smoke = run(image_id, python, ['-I', '-B', probe, 'smoke'], label + '-smoke', TIMEOUTS['smoke'], work)
    require(smoke.returncode == 0, failure(label + '-smoke', smoke, 'native smoke failed'))
    smoke_qemu = run(image_id, qemu, ['-cpu', CPU, python, '-I', '-B', probe, 'smoke'], label + '-smoke-qemu',
                     TIMEOUTS['smoke-qemu'], work)
    require(not illegal_instruction(smoke_qemu),
            failure(label + '-smoke-qemu', smoke_qemu, 'ILLEGAL INSTRUCTION in the smoke under -cpu ' + CPU))
    require(smoke_qemu.returncode == 0, failure(label + '-smoke-qemu', smoke_qemu, 'emulated smoke failed'))
    require(last_json(smoke.stdout) == last_json(smoke_qemu.stdout), label + ': smoke differs under -cpu ' + CPU)
    return {'python': python, 'modules_listed': len(modules), 'native_ok': len(native_ok),
            'native_errors': natively.get('err') or {}, 'qemu_ok': len(result['ok']),
            'modules_sha256': hashlib.sha256(json.dumps(native_ok).encode()).hexdigest(), 'smoke': True}


def check_node(image_id, work, run=run_in_image):
    qemu = MOUNT + '/bin/qemu-x86_64-static'
    native = run(image_id, NODE, ['-e', NODE_SMOKE], 'n8n-node', TIMEOUTS['node'], work)
    require(native.returncode == 0, failure('n8n-node', native, 'native node smoke failed'))
    emulated = run(image_id, qemu, ['-cpu', CPU, NODE, '-e', NODE_SMOKE], 'n8n-node-qemu', TIMEOUTS['node-qemu'], work)
    require(not illegal_instruction(emulated), failure('n8n-node-qemu', emulated, 'ILLEGAL INSTRUCTION under -cpu ' + CPU))
    require(emulated.returncode == 0, failure('n8n-node-qemu', emulated, 'emulated node smoke failed'))
    result = last_json(emulated.stdout)
    require(isinstance(result, dict) and result == last_json(native.stdout) and result.get('fts5') == 1,
            'n8n node smoke differs under -cpu ' + CPU)
    return result


def write_once(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def check(app, candidate, evidence, run=run_in_image, qemu_installer=install_qemu):
    require(app in PRODUCTS, 'product not allowed')
    require(evidence.is_dir() and not evidence.is_symlink(), 'evidence directory missing (hosted runner preflight)')
    record_path = evidence / ('j1900-%s.json' % app)
    require(not record_path.exists(), 'J1900 already recorded for ' + app)
    subject = verify_current(app, candidate)  # the local tag is the tested, scanned image and its source is HEAD
    image_id = subject['image_id']
    qemu = qemu_installer()
    with tempfile.TemporaryDirectory(prefix='woow-j1900-', dir=os.environ.get('RUNNER_TEMP') or None) as directory:
        work = Path(directory)
        prepare(work, Path(qemu['path']))
        envs = {'core': check_python(image_id, app, 'core', CORE_PYTHON, work, run)}
        if app != 'n8n':
            envs['child'] = check_python(image_id, app, 'child', child_python(app), work, run)
        node = check_node(image_id, work, run) if app == 'n8n' else None
        probe_sha256 = sha_file(work / 'j1900_probe.py')
    require(inspect_image(app)['Id'] == image_id, 'the local image changed during the J1900 check')
    record = {'app': app, 'version': version_for(app), 'source': subject['source'], 'image_id': image_id,
              'passed': True, 'cpu': CPU, 'mode': 'qemu-user', 'qemu': qemu, 'probe_sha256': probe_sha256,
              'container': list(ISOLATION), 'envs': envs, 'node': node, 'scope': SCOPE}
    write_once(record_path, record)
    return record


def main(argv):
    require(len(argv) == 3, 'usage: j1900_check.py APP CANDIDATE_DIR EVIDENCE_DIR')
    record = check(argv[0], Path(argv[1]), Path(argv[2]))
    print('PASS: J1900 (-cpu %s, %s) %s %s: %s%s' % (
        CPU, record['qemu']['version_line'], record['app'], record['image_id'],
        ', '.join('%s %d/%d modules' % (scope, value['qemu_ok'], value['modules_listed'])
                  for scope, value in record['envs'].items()),
        '; node smoke with FTS5' if record['node'] else ''))


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except Closed as exc:
        raise SystemExit('J1900 check CLOSED: ' + str(exc)) from None
    except (supply_chain.Closed, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise SystemExit('J1900 check CLOSED: ' + type(exc).__name__ + ' (candidate evidence, Docker or QEMU)') from None
