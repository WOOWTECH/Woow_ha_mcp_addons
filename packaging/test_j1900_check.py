"""J1900 check: the in-image probe (module discovery, import loop, smoke, CLI) and the host-side verdicts with an owned
fake Docker and fake apt; no container, QEMU or package manager runs here.
Ported from artifacts/ha-multiprofile-parity-20261114/wave4/release-0.4.14-builder/tests/test_j1900_probe.py (probe
tests, unchanged) and tests/test_inpod.py (J1900Test, CliTest.test_docker_run_is_isolated), adapted to j1900_check.py.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

import j1900_check as j
import j1900_probe as probe
import validate as v

IMAGE = 'sha256:' + 'e' * 64
PROBE = Path(probe.__file__).resolve()


def result(returncode, payload=None, stderr=b'', lines=(b'TRY x',)):
    stdout = b'\n'.join([*lines, json.dumps(payload).encode()]) + b'\n' if payload is not None else b'\n'.join(lines)
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class ProbeTest(unittest.TestCase):
    def test_module_names(self):
        root = Path('/x/site-packages')
        cases = {
            'pydantic_core/_pydantic_core.cpython-313-x86_64-linux-gnu.so': 'pydantic_core._pydantic_core',
            'cryptography/hazmat/bindings/_rust.abi3.so': 'cryptography.hazmat.bindings._rust',
            '_cffi_backend.cpython-313-x86_64-linux-gnu.so': '_cffi_backend',
            'pkg/__init__.cpython-313-x86_64-linux-gnu.so': 'pkg',
            'plain.so': 'plain',
            'numpy.libs/libopenblas64_p-r0-0cf96a72.3.23.dev.so': None,
            'pkg/tests/_t.cpython-313-x86_64-linux-gnu.so': None,
            'pkg/module.py': None,
            'tokenizers/tokenizers.abi3.so': 'tokenizers.tokenizers',
        }
        for rel, want in cases.items():
            with self.subTest(rel=rel):
                self.assertEqual(probe.module_name(root, root / rel), want)

    def test_native_modules_scans_only_package_roots(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / 'lib/python3.13/site-packages'
            dyn = Path(d) / 'lib/python3.13/lib-dynload'
            other = Path(d) / 'apps/n8n'
            for path in (sp / 'a/_x.cpython-313-x86_64-linux-gnu.so', sp / 'b.abi3.so',
                         dyn / '_ssl.cpython-313-x86_64-linux-gnu.so', other / 'c.so'):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'')
            self.assertEqual(probe.native_modules([str(sp), str(dyn), str(other)]), ['_ssl', 'a._x', 'b'])

    def test_import_all_reports_ok_and_errors(self):
        lines = []
        found = probe.import_all(['json', 'zlib', 'no_such_module_j1900'], emit=lines.append)
        self.assertEqual(found, {'ok': ['json', 'zlib'], 'err': {'no_such_module_j1900': 'ModuleNotFoundError'}})
        self.assertEqual(lines[0], 'TRY json')

    def test_smoke_is_deterministic(self):
        self.assertEqual(probe.smoke(), probe.smoke())

    def test_cli(self):
        r = subprocess.run([sys.executable, '-I', '-B', str(PROBE), 'list'], stdout=subprocess.PIPE, timeout=120)
        self.assertEqual(r.returncode, 0)
        names = json.loads(r.stdout)
        self.assertTrue(isinstance(names, list) and all(isinstance(n, str) for n in names))
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'm.json'
            f.write_text(json.dumps(['json', 'not_a_module_x']))
            r = subprocess.run([sys.executable, '-I', '-B', str(PROBE), 'import', str(f)], stdout=subprocess.PIPE,
                               timeout=120)
            self.assertEqual(r.returncode, 0)
            last = json.loads(r.stdout.decode().strip().splitlines()[-1])
            self.assertEqual(last['ok'], ['json'])
        r = subprocess.run([sys.executable, '-I', '-B', str(PROBE), 'smoke'], stdout=subprocess.PIPE, timeout=120)
        self.assertEqual(json.loads(r.stdout), probe.smoke())
        r = subprocess.run([sys.executable, '-I', '-B', str(PROBE), 'bogus'], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=60)
        self.assertNotEqual(r.returncode, 0)

    def test_the_probe_uses_the_standard_library_only(self):
        # It runs on the image's own Python, which has neither PyYAML nor the packaging modules.
        source = PROBE.read_text()
        self.assertNotIn('import yaml', source)
        for module in ('validate', 'supply_chain', 'j1900_check'):
            self.assertNotIn('import ' + module, source)


class FakeImage:
    """Fake run_in_image: answers by step label; records (entrypoint, args, label)."""

    def __init__(self, qemu_rc=0, qemu_stderr=b'', qemu_ok=None, smoke_qemu=None, node_qemu=None, node_rc=0):
        self.calls = []
        self.modules = ['_ssl', 'pydantic_core._pydantic_core', 'yaml._yaml']
        self.native_ok = self.modules[:2]
        self.qemu_rc, self.qemu_stderr, self.qemu_ok = qemu_rc, qemu_stderr, qemu_ok
        self.smoke_qemu, self.node_qemu, self.node_rc = smoke_qemu, node_qemu, node_rc
        self.node = {'node': 'v26.12.1', 'fts5': 1, 'sha256': 'a' * 64, 'zlib': 5000}

    def __call__(self, image_id, entrypoint, args, label, timeout, work):
        self.calls.append((image_id, entrypoint, list(args), label))
        if label.endswith('-list'):
            return result(0, self.modules, lines=())
        if label.endswith('-native'):
            return result(0, {'ok': self.native_ok, 'err': {'yaml._yaml': 'ImportError'}})
        if label.endswith('-smoke-qemu'):
            return result(0, self.smoke_qemu or {'sha256': 'a'}, lines=())
        if label.endswith('-smoke'):
            return result(0, {'sha256': 'a'}, lines=())
        if label == 'n8n-node':
            return result(self.node_rc, self.node, lines=())
        if label == 'n8n-node-qemu':
            return result(self.qemu_rc, self.node_qemu or self.node, self.qemu_stderr, lines=())
        if label.endswith('-qemu'):
            ok = self.qemu_ok if self.qemu_ok is not None else self.native_ok
            return result(self.qemu_rc, {'ok': ok, 'err': {}}, self.qemu_stderr,
                          lines=[b'TRY ' + name.encode() for name in self.native_ok])
        raise AssertionError(label)


class J1900Test(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.work = self.base / 'work'
        self.work.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def env(self, fake, app='odoo', scope='core'):
        return j.check_python(IMAGE, app, scope, j.CORE_PYTHON, self.work, fake)

    def test_pass_records_counts(self):
        r = self.env(FakeImage())
        self.assertEqual((r['modules_listed'], r['native_ok'], r['qemu_ok']), (3, 2, 2))
        self.assertEqual(r['native_errors'], {'yaml._yaml': 'ImportError'})
        self.assertEqual(r['modules_sha256'], hashlib.sha256(json.dumps(['_ssl', 'pydantic_core._pydantic_core']).encode()).hexdigest())
        self.assertEqual(json.loads((self.work / 'odoo-core-native-ok.json').read_text()),
                         ['_ssl', 'pydantic_core._pydantic_core'])
        self.assertEqual(oct((self.work / 'odoo-core-modules.json').stat().st_mode & 0o777), '0o644')

    def test_the_emulated_runs_use_qemu_nehalem_on_the_same_interpreter(self):
        fake = FakeImage()
        self.env(fake)
        emulated = [call for call in fake.calls if call[3].endswith('-qemu')]
        self.assertEqual([call[3] for call in emulated], ['odoo-core-qemu', 'odoo-core-smoke-qemu'])
        for _, entrypoint, args, _ in emulated:
            self.assertEqual(entrypoint, '/j1900/bin/qemu-x86_64-static')
            self.assertEqual(args[:3], ['-cpu', 'Nehalem', j.CORE_PYTHON])
        self.assertEqual(fake.calls[2][2][-1], '/j1900/odoo-core-native-ok.json')  # only the natively importable ones
        self.assertTrue(all(call[0] == IMAGE for call in fake.calls))

    def test_sigill_is_a_named_failure(self):
        for rc, err in ((132, b''), (-4, b''), (1, b'qemu: uncaught target signal 4 (Illegal instruction) - core dumped')):
            with self.subTest(rc=rc):
                with self.assertRaises(j.Closed) as caught:
                    self.env(FakeImage(qemu_rc=rc, qemu_stderr=err))
                self.assertIn('ILLEGAL INSTRUCTION', str(caught.exception))
                self.assertIn('last TRY pydantic_core._pydantic_core', str(caught.exception))

    def test_module_or_smoke_difference_fails(self):
        with self.assertRaisesRegex(j.Closed, 'modules differ under -cpu Nehalem: pydantic_core._pydantic_core'):
            self.env(FakeImage(qemu_ok=['_ssl']))
        with self.assertRaisesRegex(j.Closed, 'smoke differs'):
            self.env(FakeImage(smoke_qemu={'sha256': 'b'}))
        with self.assertRaisesRegex(j.Closed, 'emulated import run failed'):
            self.env(FakeImage(qemu_rc=1, qemu_stderr=b'qemu-x86_64-static: Unable to reserve address space'))

    def test_no_native_module_is_not_a_pass(self):
        fake = FakeImage()
        fake.modules = []
        with self.assertRaisesRegex(j.Closed, 'no native extension modules'):
            self.env(fake)
        fake = FakeImage()
        fake.native_ok = []
        with self.assertRaisesRegex(j.Closed, 'no native module imports natively'):
            self.env(fake)

    def test_n8n_node_smoke_natively_and_under_qemu(self):
        self.assertEqual(j.check_node(IMAGE, self.work, FakeImage())['fts5'], 1)
        for fake, message in ((FakeImage(qemu_rc=132), 'ILLEGAL INSTRUCTION'),
                              (FakeImage(node_qemu={'node': 'v26.12.1', 'fts5': 0, 'sha256': 'a' * 64, 'zlib': 5000}),
                               'node smoke differs'),
                              (FakeImage(node_rc=1), 'native node smoke failed')):
            with self.subTest(message=message), self.assertRaisesRegex(j.Closed, message):
                j.check_node(IMAGE, self.work, fake)

    def test_docker_run_is_isolated(self):
        argv = j.docker_run_argv(IMAGE, '/j1900/bin/qemu-x86_64-static', ['-cpu', 'Nehalem'], 'n', Path('/w/j1900'))
        for needle in ('--network', 'none', '--read-only', '--cap-drop', 'ALL', '--user', '10001:10001',
                       'no-new-privileges', 'type=bind,source=/w/j1900,target=/j1900,readonly', '--rm'):
            self.assertIn(needle, argv)
        for absent in ('--privileged', '--cap-add', '--network=host', 'host', '--pid', '-v'):
            self.assertNotIn(absent, argv)
        self.assertEqual(argv[argv.index('--network') + 1], 'none')
        self.assertEqual(argv[-3:], [IMAGE, '-cpu', 'Nehalem'])

    def test_timeout_removes_the_container_and_fails(self):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(argv)
            if argv[:2] == ['docker', 'run']:
                raise subprocess.TimeoutExpired(argv, kwargs.get('timeout'))
            return types.SimpleNamespace(returncode=0)
        with mock.patch.object(j.subprocess, 'run', side_effect=fake_run), \
             self.assertRaisesRegex(j.Closed, 'odoo-core-qemu timed out after 5 s'):
            j.run_in_image(IMAGE, j.CORE_PYTHON, ['-V'], 'odoo-core-qemu', 5, self.work)
        name = calls[0][calls[0].index('--name') + 1]
        self.assertTrue(name.startswith('woow-j1900-odoo-core-qemu-'))
        self.assertEqual(calls[1], ['docker', 'rm', '-f', name])


class InstallAndRecordTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.qemu = self.base / 'qemu-x86_64-static'
        self.qemu.write_bytes(b'invented static qemu bytes')
        self.evidence = self.base / 'release-evidence'
        self.evidence.mkdir(mode=0o700)

    def tearDown(self):
        self.temporary.cleanup()

    def apt(self, fail=None, version='1:8.2.2+ds-0ubuntu1.18', line='qemu-x86_64 version 8.2.2 (Debian 1:8.2.2+ds-0ubuntu1.18)',
            failures=99):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            if fail and fail in argv and sum(fail in call for call in calls) <= failures:
                return types.SimpleNamespace(returncode=100, stdout=b'', stderr=b'')
            if argv[0] == 'dpkg-query':
                return types.SimpleNamespace(returncode=0, stdout=version.encode(), stderr=b'')
            if argv[-1] == '--version':
                return types.SimpleNamespace(returncode=0, stdout=(line + '\nCopyright\n').encode(), stderr=b'')
            return types.SimpleNamespace(returncode=0, stdout=b'', stderr=b'')
        return calls, fake_run

    def test_qemu_user_static_comes_from_apt_and_is_recorded(self):
        calls, fake_run = self.apt()
        with mock.patch.object(j, 'QEMU', self.qemu):
            qemu = j.install_qemu(fake_run)
        self.assertEqual(calls[0], ['sudo', '-n', 'env', 'DEBIAN_FRONTEND=noninteractive', 'apt-get', 'update', '-q'])
        self.assertEqual(calls[1], ['sudo', '-n', 'env', 'DEBIAN_FRONTEND=noninteractive', 'apt-get', 'install', '-y', '-q',
                                    '--no-install-recommends', 'qemu-user-static'])
        self.assertEqual(qemu, {'package': 'qemu-user-static', 'version': '1:8.2.2+ds-0ubuntu1.18',
                                'version_line': 'qemu-x86_64 version 8.2.2 (Debian 1:8.2.2+ds-0ubuntu1.18)',
                                'path': str(self.qemu.resolve()),
                                'sha256': hashlib.sha256(b'invented static qemu bytes').hexdigest()})
        for fail, kwargs in (('update', {}), ('install', {}), (None, {'version': ''}), (None, {'line': 'qemu-aarch64 version 8.2.2'})):
            calls, fake_run = self.apt(fail, **kwargs)
            with self.subTest(fail=fail, kwargs=kwargs), mock.patch.object(j, 'QEMU', self.qemu), \
                 mock.patch.object(j.time, 'sleep'), self.assertRaises(j.Closed):
                j.install_qemu(fake_run)
            if fail:
                self.assertEqual(sum(fail in call for call in calls), 3)  # three attempts, then closed
        # A mirror hiccup is retried; the package that does get installed is what the record names.
        calls, fake_run = self.apt('update', failures=2)
        with mock.patch.object(j, 'QEMU', self.qemu), mock.patch.object(j.time, 'sleep') as sleep:
            self.assertEqual(j.install_qemu(fake_run)['version'], '1:8.2.2+ds-0ubuntu1.18')
        self.assertEqual(sum('update' in call for call in calls), 3)
        self.assertEqual(sleep.call_count, 2)

    def check(self, app, fake, image_after=IMAGE):
        qemu = {'package': 'qemu-user-static', 'version': '1:8.2.2+ds-0ubuntu1.18', 'path': str(self.qemu),
                'version_line': 'qemu-x86_64 version 8.2.2', 'sha256': hashlib.sha256(self.qemu.read_bytes()).hexdigest()}
        subject = {'app': app, 'source': 'a' * 40, 'image_id': IMAGE}
        works = []
        real_prepare = j.prepare

        def prepare(work, binary):
            works.append(work)
            real_prepare(work, binary)
            self.assertEqual(oct(work.stat().st_mode & 0o777), '0o755')
            self.assertEqual(oct((work / 'bin/qemu-x86_64-static').stat().st_mode & 0o777), '0o755')
            self.assertEqual((work / 'j1900_probe.py').read_bytes(), PROBE.read_bytes())
        with mock.patch.object(j, 'verify_current', return_value=subject) as verify, \
             mock.patch.object(j, 'inspect_image', return_value={'Id': image_after}), \
             mock.patch.object(j, 'prepare', side_effect=prepare), \
             mock.patch.dict(os.environ, {'RUNNER_TEMP': str(self.base)}):
            record = j.check(app, self.base / 'candidate', self.evidence, run=fake, qemu_installer=lambda: qemu)
        verify.assert_called_once_with(app, self.base / 'candidate')
        self.assertFalse(works[0].exists())  # the private work directory is removed afterwards
        self.assertEqual(works[0].parent, self.base)
        return record

    def test_record_for_a_python_child_product(self):
        fake = FakeImage()
        record = self.check('odoo', fake)
        self.assertEqual(json.loads((self.evidence / 'j1900-odoo.json').read_text()), record)
        self.assertEqual(oct((self.evidence / 'j1900-odoo.json').stat().st_mode & 0o777), '0o600')
        self.assertEqual((record['app'], record['version'], record['image_id'], record['passed'], record['cpu']),
                         ('odoo', v.version_for('odoo'), IMAGE, True, 'Nehalem'))
        self.assertEqual(set(record['envs']), {'core', 'child'})
        self.assertEqual(record['envs']['child']['python'], '/opt/woow/apps/odoo/.venv/bin/python')
        self.assertIsNone(record['node'])
        self.assertEqual(record['probe_sha256'], hashlib.sha256(PROBE.read_bytes()).hexdigest())
        self.assertEqual(record['qemu']['package'], 'qemu-user-static')
        for flag in ('--network', 'none', '--read-only', '--user', '10001:10001', '--cap-drop', 'ALL'):
            self.assertIn(flag, record['container'])
        self.assertFalse(any(label.startswith('n8n-node') for *_, label in fake.calls))

    def test_n8n_has_no_child_venv_and_runs_the_node_check(self):
        fake = FakeImage()
        record = self.check('n8n', fake)
        self.assertEqual(set(record['envs']), {'core'})
        self.assertEqual(record['node']['fts5'], 1)
        self.assertIn('n8n-node-qemu', [label for *_, label in fake.calls])
        self.assertFalse(any('/opt/woow/apps/n8n/.venv' in entry for call in fake.calls for entry in [call[1], *call[2]]))

    def test_refusals(self):
        with self.assertRaisesRegex(j.Closed, 'not allowed'):
            j.check('odoo-manage', self.base / 'candidate', self.evidence, run=FakeImage(), qemu_installer=dict)
        with self.assertRaisesRegex(j.Closed, 'evidence directory missing'):
            j.check('odoo', self.base / 'candidate', self.base / 'absent', run=FakeImage(), qemu_installer=dict)
        with self.assertRaisesRegex(j.Closed, 'image changed during the J1900 check'):
            self.check('hermes', FakeImage(), image_after='sha256:' + 'f' * 64)
        self.assertFalse((self.evidence / 'j1900-hermes.json').exists())
        self.check('emqx', FakeImage())
        with self.assertRaisesRegex(j.Closed, 'already recorded'):
            self.check('emqx', FakeImage())
        with self.assertRaisesRegex(j.Closed, 'ILLEGAL INSTRUCTION'):
            self.check('litellm', FakeImage(qemu_rc=132))
        self.assertFalse((self.evidence / 'j1900-litellm.json').exists())

    def test_the_check_writes_no_workflow_environment_and_reads_no_secret(self):
        source = Path(j.__file__).read_text()
        for absent in ('GITHUB_ENV', 'GITHUB_PATH', 'GITHUB_TOKEN', 'GHCR_TOKEN', 'docker login', "'login'", 'push'):
            self.assertNotIn(absent, source)


if __name__ == '__main__':
    unittest.main()
