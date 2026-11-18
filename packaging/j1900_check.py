"""J1900 instruction-set check of the tested candidate image, before it can be handed to publication (DQ-42: every release).

    python packaging/j1900_check.py APP CANDIDATE_DIR EVIDENCE_DIR

The J1900 the add-ons ship on has no AVX, AVX2 or AVX-512. QEMU user mode with -cpu Nehalem is stricter: Nehalem also
lacks MOVBE and AES-NI (docs/operations/release-decision-0.1.7.md). The image is first bound to its candidate evidence
(supply_chain.verify_current: the local tag is the tested image ID, its source is HEAD and its scans are unchanged);
every check then runs on that image ID, in a container with --network none --read-only --user 10001:10001
--cap-drop ALL and no-new-privileges, with only j1900_probe.py and the QEMU binary mounted read-only:
  1. each Python environment the image runs, the core venv /opt/woow/.venv and the child venv
     /opt/woow/apps/<app>/.venv (n8n has none: its child is Node): j1900_probe.py lists every native extension module
     (the interpreter's own lib-dynload ones and the installed packages' site-packages ones) and imports each natively.
     At least one site-packages module must import natively, and a module that fails natively fails the check unless
     packaging/j1900-allowlist.json lists it for this product with a reviewed reason and its native error contains the
     entry's error_contains text, the one known cause (review M1: a third-party module that cannot even load natively
     would otherwise never reach QEMU). A listed module that does import natively is checked under QEMU like any other.
     The natively importable ones are imported again under `qemu-x86_64-static -cpu Nehalem` and must all import, with
     no SIGILL; a small smoke through C code (hashlib, ssl, zlib, sqlite3, decimal, re) must give the same result both
     ways. The one exception is the other kind of entry, qemu_error_contains, for a module that imports natively but
     not under QEMU because the emulator lacks a system call it needs at import (caio.linux_aio calls io_setup, which
     QEMU's linux-user mode does not implement): it is set aside from the comparison only when it imported natively,
     failed under QEMU and its QEMU error contains that text; every other module is compared as before, and a SIGILL
     still fails whatever the list says;
  2. n8n: Node loads better-sqlite3, builds an FTS5 table, hashes and compresses, natively and under QEMU, with the
     same result.
Both import runs must answer for exactly the modules they were sent, each once, imported or failed, the QEMU run in the
order they were sent (review round 2: a module missing from both would otherwise never reach QEMU and never be
reported), and every module name the image reports must be a dotted Python name (review round 3, low-1: nothing else
can reach a log line). A SIGILL (exit 132, or QEMU's "uncaught target signal 4") fails the release at once and names
the last module tried; so does a run that fails, an answer that is not JSON or does not account for its modules, no
module or no third-party module importing natively, and a smoke that fails or differs. Native import failures and QEMU
differences that the allowlist does not cover are collected instead and reported together, with each module's error
text, after every environment ran (review round 3, medium-1: one real run shows all of them); an immediate failure
also lists what was collected before it.
QEMU is the runner's own apt package qemu-user-static (its version, version line and binary SHA-256 are recorded). The
whole check has a 60-minute budget; every container run gets at most what is left of it. The result is
EVIDENCE_DIR/j1900-<app>.json. Limit: QEMU checks only the code that actually runs (the imports and the smokes), not
every path of the program.

Ported from artifacts/ha-multiprofile-parity-20261114/wave4/release-0.4.14-builder/inpod_0414.py (docker_run_argv,
j1900_exec, j1900_env, j1900; written for the dropped k3s builder and never run there): the same container flags,
verdicts and record. Changed: the image is bound through supply_chain.verify_current instead of builder records,
qemu-user-static comes from the hosted runner's apt, the work directory is private to the run (under RUNNER_TEMP), a
failure names the step, its exit status, the last module tried and a short stderr tail, the collected failures name
each module's error text, and the review M1 rules above.
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
ALLOWLIST = HERE / 'j1900-allowlist.json'
QEMU = Path('/usr/bin/qemu-x86_64-static')
QEMU_PACKAGE = 'qemu-user-static'
CPU = 'Nehalem'
MOUNT = '/j1900'
CORE_PYTHON = '/opt/woow/.venv/bin/python'
NODE = '/usr/local/bin/node'
KINDS = ('lib-dynload', 'site-packages')
ISOLATION = ('--network', 'none', '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,size=256m,mode=1777',
             '--user', '10001:10001', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
             '--pids-limit', '512', '--memory', '4g', '-e', 'HOME=/tmp')
# Caps per container run; the whole check never exceeds BUDGET seconds (review L5).
TIMEOUTS = {'list': 300, 'native': 600, 'qemu': 1800, 'smoke': 300, 'smoke-qemu': 600, 'node': 300, 'node-qemu': 900}
BUDGET = 3600
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


ENTRY_KINDS = ({'reason', 'review', 'error_contains'}, {'reason', 'review', 'qemu_error_contains'})
DETAIL = 300  # characters of one module's error text, on one line (as j1900_probe.DETAIL)
LIST_MAX = 1500  # characters of the module list in each part of the collected failures' message


def module_name(name):
    """A dotted Python module name, the only kind of name accepted from the image or the allowlist, so that a name can
    neither break a log line nor start a workflow command there (review round 3, low-1)."""
    return isinstance(name, str) and bool(name) and all(part.isidentifier() for part in name.split('.'))


def load_allowlist(path=ALLOWLIST):
    """{product: {module: entry}} from packaging/j1900-allowlist.json. An entry is either native (error_contains: the
    known cause of its native import failure) or QEMU-only (qemu_error_contains: the known cause of its failure under
    QEMU alone), never both, with a reason and a review; a malformed file fails closed."""
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        raise Closed('J1900 allowlist missing or not JSON') from None
    require(isinstance(value, dict) and value.get('schema') == 1 and isinstance(value.get('products'), dict)
            and set(value['products']) == set(PRODUCTS), 'J1900 allowlist shape')
    for product, entries in value['products'].items():
        require(isinstance(entries, dict), 'J1900 allowlist entries of ' + product)
        for module, entry in entries.items():
            require(module_name(module) and isinstance(entry, dict) and set(entry) in ENTRY_KINDS
                    and all(isinstance(text, str) and text.strip() for text in entry.values()),
                    'J1900 allowlist entry of %s needs a module name, a reason, a review and the error text it excuses '
                    '(error_contains or qemu_error_contains, not both)' % product)
    return value['products']


class Deadline:
    """What is left of the check's budget; every container run gets at most that."""

    def __init__(self, seconds=BUDGET, clock=time.monotonic):
        self.seconds, self.clock, self.end = seconds, clock, clock() + seconds

    def timeout(self, step, cap):
        left = int(self.end - self.clock())
        require(left > 0, 'J1900 check exceeded its %d-second budget before %s' % (self.seconds, step))
        return min(cap, left)


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
    passed the all-layer secret scan, and the probe's TRY/OK/ERR lines carry module and exception type names only."""
    tried = [name for name in (line[4:].strip() for line in result.stdout.decode(errors='replace').splitlines()
                               if line.startswith('TRY ')) if module_name(name)]
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


def names_of(value, what):
    require(isinstance(value, list) and all(module_name(name) for name in value), what)
    return value


def keyed(value, what):
    """An object of the probe's answer keyed by module name (its 'err' and 'detail')."""
    require(isinstance(value, dict) and all(module_name(name) for name in value), what)
    return value


def accounted(label, ok, err, sent):
    """The probe answered for exactly the modules it was sent: each one once, either imported or failed."""
    require(len(ok) == len(set(ok)) and not set(ok) & set(err) and set(ok) | set(err) == set(sent),
            '%s import result does not account for every module it was sent exactly once (missing: %s)'
            % (label, ', '.join(sorted(set(sent) - set(ok) - set(err))[:8]) or 'none'))


def one_line(text):
    """An error text from the image on one line of at most DETAIL characters, whatever the probe printed."""
    return ' '.join(str(text).split())[:DETAIL]


def report(app, found):
    """The collected failures of every environment on one line: each native import failure and each QEMU difference
    that the allowlist does not cover, as 'scope module (error text)', at most LIST_MAX characters per kind so that
    both kinds always show."""
    parts = []
    for kind, what in (('native', 'native modules fail to import natively and packaging/j1900-allowlist.json does not '
                                  'list them for %s' % app),
                       ('qemu', 'modules differ under -cpu %s and no QEMU-only entry of packaging/j1900-allowlist.json '
                                'covers them for %s' % (CPU, app))):
        items = ['%s %s (%s)' % (scope, name, text) for each, scope, name, text in found if each == kind]
        listed = ', '.join(items)
        if items:
            parts.append('%s: %s' % (what, listed if len(listed) <= LIST_MAX
                                     else '%s … (%d in all)' % (listed[:LIST_MAX], len(items))))
    return '; '.join(parts)


def check_python(image_id, app, scope, python, work, run=run_in_image, allowed=None, deadline=None, found=None):
    """One Python environment; returns its record. A native import failure that the allowlist does not cover and a
    module that differs under QEMU without a QEMU-only entry for its error do not raise here: they are returned in
    'disallowed' and 'qemu_differ' and appended to found as (kind, scope, module, error text), and check() fails on
    them after every environment ran. Everything else that is wrong raises at once. The smoke keeps failing at once:
    it imports hashlib, ssl, sqlite3, zlib, decimal and re itself, so it relies on those importing the same way under
    QEMU, which a module difference may already have broken; check() then also names the differences found before."""
    allowed = {} if allowed is None else allowed
    found = [] if found is None else found
    deadline = Deadline() if deadline is None else deadline
    label = '%s-%s' % (app, scope)
    qemu, probe = MOUNT + '/bin/qemu-x86_64-static', MOUNT + '/j1900_probe.py'

    def step(entrypoint, args, suffix, cap):
        return run(image_id, entrypoint, args, label + suffix, deadline.timeout(label + suffix, TIMEOUTS[cap]), work)
    listed = step(python, ['-I', '-B', probe, 'list'], '-list', 'list')
    require(listed.returncode == 0, failure(label + '-list', listed, 'native module listing failed'))
    by_kind = last_json(listed.stdout)
    require(isinstance(by_kind, dict) and set(by_kind) == set(KINDS), label + ': native module listing is not '
            '{"lib-dynload": [...], "site-packages": [...]}')
    kinds = {kind: set(names_of(by_kind[kind], label + ': module names')) for kind in KINDS}
    modules = sorted(kinds['lib-dynload'] | kinds['site-packages'])
    require(bool(modules), label + ': no native extension modules found')
    write_public(work / (label + '-modules.json'), modules)
    native = step(python, ['-I', '-B', probe, 'import', '%s/%s-modules.json' % (MOUNT, label)], '-native', 'native')
    require(native.returncode == 0, failure(label + '-native', native, 'native import run failed'))
    natively = last_json(native.stdout)
    require(isinstance(natively, dict), label + ': native import result')
    native_ok = names_of(natively.get('ok'), label + ': native import result')
    native_err = keyed(natively.get('err'), label + ': native import result')
    details = {name: one_line(text) for name, text in keyed(natively.get('detail', {}),
                                                             label + ': native import result').items()}
    # Every listed module is accounted for exactly once: imported or failed (review round 2: a module missing from both
    # would otherwise never reach QEMU and never be reported).
    accounted(label + ' native', native_ok, native_err, modules)
    errors = {name: details.get(name) or one_line(kind) for name, kind in native_err.items()}
    excused = {name for name in errors if 'error_contains' in allowed.get(name, {})
               and allowed[name]['error_contains'] in details.get(name, '')}
    disallowed = {name: text for name, text in sorted(errors.items()) if name not in excused}
    found.extend(('native', scope, name, text) for name, text in disallowed.items())
    require(bool(native_ok), label + ': no native module imports natively')
    require(bool(set(native_ok) & kinds['site-packages']),
            label + ': no third-party (site-packages) native module imports natively')
    write_public(work / (label + '-native-ok.json'), native_ok)
    emulated = step(qemu, ['-cpu', CPU, python, '-I', '-B', probe, 'import', '%s/%s-native-ok.json' % (MOUNT, label)],
                    '-qemu', 'qemu')
    require(not illegal_instruction(emulated), failure(label + '-qemu', emulated, 'ILLEGAL INSTRUCTION under -cpu ' + CPU))
    require(emulated.returncode == 0, failure(label + '-qemu', emulated, 'emulated import run failed'))
    result = last_json(emulated.stdout)
    require(isinstance(result, dict), label + ': emulated import result')
    qemu_ok = names_of(result.get('ok'), label + ': emulated import result')
    qemu_err = keyed(result.get('err', {}), label + ': emulated import result')
    qemu_details = {name: one_line(text) for name, text in keyed(result.get('detail', {}),
                                                                  label + ': emulated import result').items()}
    accounted(label + ' QEMU', qemu_ok, qemu_err, native_ok)
    require(qemu_ok == [name for name in native_ok if name not in qemu_err],
            label + ' QEMU import result is not in the order the modules were sent')
    # Set aside only a QEMU-only entry's module that imported natively and failed under QEMU for its known cause; every
    # other module that failed under QEMU is a difference, and a SIGILL has already failed above whatever the list says.
    qemu_excused = {name: qemu_details[name] for name in sorted(qemu_err)
                    if name in native_ok and 'qemu_error_contains' in allowed.get(name, {})
                    and allowed[name]['qemu_error_contains'] in qemu_details.get(name, '')}
    differ = {name: qemu_details.get(name) or one_line(kind) for name, kind in sorted(qemu_err.items())
              if name not in qemu_excused}
    found.extend(('qemu', scope, name, text) for name, text in differ.items())
    smoke = step(python, ['-I', '-B', probe, 'smoke'], '-smoke', 'smoke')
    require(smoke.returncode == 0, failure(label + '-smoke', smoke, 'native smoke failed'))
    smoke_qemu = step(qemu, ['-cpu', CPU, python, '-I', '-B', probe, 'smoke'], '-smoke-qemu', 'smoke-qemu')
    require(not illegal_instruction(smoke_qemu),
            failure(label + '-smoke-qemu', smoke_qemu, 'ILLEGAL INSTRUCTION in the smoke under -cpu ' + CPU))
    require(smoke_qemu.returncode == 0, failure(label + '-smoke-qemu', smoke_qemu, 'emulated smoke failed'))
    require(last_json(smoke.stdout) == last_json(smoke_qemu.stdout), label + ': smoke differs under -cpu ' + CPU)
    ok = set(native_ok)
    return {'python': python, 'modules_listed': len(modules),
            'lib_dynload': {'listed': len(kinds['lib-dynload']), 'native_ok': len(kinds['lib-dynload'] & ok)},
            'site_packages': {'listed': len(kinds['site-packages']), 'native_ok': len(kinds['site-packages'] & ok)},
            'native_ok': len(native_ok), 'native_errors': errors,
            'allowlisted': sorted(excused), 'disallowed': disallowed,
            'qemu_ok': len(qemu_ok), 'qemu_allowlisted': qemu_excused, 'qemu_differ': differ,
            'modules_sha256': hashlib.sha256(json.dumps(native_ok).encode()).hexdigest(), 'smoke': True}


def check_node(image_id, work, run=run_in_image, deadline=None):
    deadline = Deadline() if deadline is None else deadline
    qemu = MOUNT + '/bin/qemu-x86_64-static'
    native = run(image_id, NODE, ['-e', NODE_SMOKE], 'n8n-node', deadline.timeout('n8n-node', TIMEOUTS['node']), work)
    require(native.returncode == 0, failure('n8n-node', native, 'native node smoke failed'))
    emulated = run(image_id, qemu, ['-cpu', CPU, NODE, '-e', NODE_SMOKE], 'n8n-node-qemu',
                   deadline.timeout('n8n-node-qemu', TIMEOUTS['node-qemu']), work)
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


def check(app, candidate, evidence, run=run_in_image, qemu_installer=install_qemu, allowlist=None, deadline=None):
    require(app in PRODUCTS, 'product not allowed')
    allowed = (load_allowlist() if allowlist is None else allowlist)[app]
    require(evidence.is_dir() and not evidence.is_symlink(), 'evidence directory missing (hosted runner preflight)')
    record_path = evidence / ('j1900-%s.json' % app)
    require(not record_path.exists(), 'J1900 already recorded for ' + app)
    subject = verify_current(app, candidate)  # the local tag is the tested, scanned image and its source is HEAD
    image_id = subject['image_id']
    qemu = qemu_installer()
    deadline = Deadline() if deadline is None else deadline
    found = []  # (kind, scope, module, error text) from every environment, reported together (review round 3)
    try:
        with tempfile.TemporaryDirectory(prefix='woow-j1900-', dir=os.environ.get('RUNNER_TEMP') or None) as directory:
            work = Path(directory)
            prepare(work, Path(qemu['path']))
            envs = {'core': check_python(image_id, app, 'core', CORE_PYTHON, work, run, allowed, deadline, found)}
            if app != 'n8n':
                envs['child'] = check_python(image_id, app, 'child', child_python(app), work, run, allowed, deadline,
                                             found)
            node = check_node(image_id, work, run, deadline) if app == 'n8n' else None
            probe_sha256 = sha_file(work / 'j1900_probe.py')
    except Closed as exc:
        if not found:
            raise
        raise Closed('%s; found before it: %s' % (exc, report(app, found))) from None
    require(not found, report(app, found))
    require(inspect_image(app)['Id'] == image_id, 'the local image changed during the J1900 check')
    for env in envs.values():
        del env['disallowed'], env['qemu_differ']
    record = {'app': app, 'version': version_for(app), 'source': subject['source'], 'image_id': image_id,
              'passed': True, 'cpu': CPU, 'mode': 'qemu-user', 'qemu': qemu, 'probe_sha256': probe_sha256,
              'allowlist_sha256': sha_file(ALLOWLIST), 'container': list(ISOLATION), 'envs': envs, 'node': node,
              'scope': SCOPE}
    write_once(record_path, record)
    return record


def summary(record):
    parts = []
    for scope, env in record['envs'].items():
        parts.append('%s: lib-dynload %d/%d, site-packages %d/%d natively, %d allowlisted native errors, %d/%d under '
                     'QEMU, %d QEMU-only allowlisted' % (
                         scope, env['lib_dynload']['native_ok'], env['lib_dynload']['listed'],
                         env['site_packages']['native_ok'], env['site_packages']['listed'], len(env['allowlisted']),
                         env['qemu_ok'], env['native_ok'], len(env['qemu_allowlisted'])))
    return 'PASS: J1900 (-cpu %s, %s) %s %s; %s%s' % (
        CPU, record['qemu']['version_line'], record['app'], record['image_id'], '; '.join(parts),
        '; node smoke with FTS5' if record['node'] else '')


def main(argv):
    require(len(argv) == 3, 'usage: j1900_check.py APP CANDIDATE_DIR EVIDENCE_DIR')
    print(summary(check(argv[0], Path(argv[1]), Path(argv[2]))))


def cli(argv):
    try:
        main(argv)
    except Closed as exc:
        raise SystemExit('J1900 check CLOSED: ' + str(exc)) from None
    except (supply_chain.Closed, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise SystemExit('J1900 check CLOSED: ' + type(exc).__name__ + ' (candidate evidence, Docker or QEMU)') from None


if __name__ == '__main__':
    cli(sys.argv[1:])
