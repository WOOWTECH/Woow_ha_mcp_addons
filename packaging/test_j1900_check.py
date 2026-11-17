"""J1900 check: the in-image probe (module discovery, import loop, smoke, CLI) and the host-side verdicts with an owned
fake Docker and fake apt; no container, QEMU or package manager runs here.
Ported from artifacts/ha-multiprofile-parity-20261114/wave4/release-0.4.14-builder/tests/test_j1900_probe.py (probe
tests) and tests/test_inpod.py (J1900Test, CliTest.test_docker_run_is_isolated), adapted to j1900_check.py; review M1,
L4 and L5 cases added.
"""
import copy
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
import supply_chain
import validate as v

IMAGE = 'sha256:' + 'e' * 64
PROBE = Path(probe.__file__).resolve()
STDLIB = ['_ssl', 'zlib', '_tkinter']
SITE = ['pydantic_core._pydantic_core', 'yaml._yaml']
TK_ERROR = 'ImportError: libtk8.6.so: cannot open shared object file: No such file or directory'
TK_ENTRY = {'reason': 'invented for the test', 'review': 'test',
            'error_contains': 'ImportError: libtk8.6.so: cannot open shared object file'}


def detail(names):
    """The probe's detail text for natively failing modules: the real Tk one for _tkinter, an invented one otherwise."""
    return {name: TK_ERROR if name == '_tkinter' else 'ImportError: invented failure of ' + name for name in names}


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

    def test_native_modules_are_grouped_by_where_they_live(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / 'lib/python3.13/site-packages'
            dist = Path(d) / 'usr/lib/python3/dist-packages'
            dyn = Path(d) / 'lib/python3.13/lib-dynload'
            other = Path(d) / 'apps/n8n'
            for path in (sp / 'a/_x.cpython-313-x86_64-linux-gnu.so', sp / 'b.abi3.so', dist / 'c/_d.abi3.so',
                         dyn / '_ssl.cpython-313-x86_64-linux-gnu.so', other / 'e.so'):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'')
            roots = [str(sp), str(dist), str(dyn), str(other)]
            self.assertEqual(probe.modules_by_root(roots), {'lib-dynload': ['_ssl'], 'site-packages': ['a._x', 'b', 'c._d']})
            self.assertEqual(probe.native_modules(roots), ['_ssl', 'a._x', 'b', 'c._d'])

    def test_import_all_reports_ok_and_errors(self):
        lines = []
        found = probe.import_all(['json', 'zlib', 'no_such_module_j1900'], emit=lines.append)
        self.assertEqual(found, {'ok': ['json', 'zlib'], 'err': {'no_such_module_j1900': 'ModuleNotFoundError'},
                                 'detail': {'no_such_module_j1900': "ModuleNotFoundError: No module named 'no_such_module_j1900'"}})
        self.assertEqual(lines[0], 'TRY json')
        self.assertIn('ERR no_such_module_j1900 ModuleNotFoundError', lines)  # the TRY/OK/ERR lines carry type names only
        with tempfile.TemporaryDirectory() as d:  # a long, multi-line message is kept on one bounded line
            (Path(d) / 'noisy_j1900.py').write_text('raise ImportError("line one\\n" + "x" * 1000)\n')
            with mock.patch.object(sys, 'path', [d, *sys.path]):
                noisy = probe.import_all(['noisy_j1900'], emit=lines.append)
            sys.modules.pop('noisy_j1900', None)
        self.assertEqual(len(noisy['detail']['noisy_j1900']), probe.DETAIL)
        self.assertTrue(noisy['detail']['noisy_j1900'].startswith('ImportError: line one xxx'))

    def test_smoke_is_deterministic(self):
        self.assertEqual(probe.smoke(), probe.smoke())

    def test_cli(self):
        r = subprocess.run([sys.executable, '-I', '-B', str(PROBE), 'list'], stdout=subprocess.PIPE, timeout=120)
        self.assertEqual(r.returncode, 0)
        listed = json.loads(r.stdout)
        self.assertEqual(set(listed), {'lib-dynload', 'site-packages'})
        self.assertTrue(all(isinstance(n, str) for names in listed.values() for n in names))
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
    """Fake run_in_image: answers by step label; records (image, entrypoint, args, label, timeout)."""

    def __init__(self, stdlib=None, site=None, native_err=None, qemu_rc=0, qemu_stderr=b'', qemu_ok=None, qemu_err=None,
                 smoke_qemu=None, smoke_qemu_rc=0, smoke_qemu_stderr=b'', node_qemu=None, node_rc=0, list_rc=0,
                 native_rc=0, listing=None, native_stdout=None, native_detail=None):
        self.calls = []
        self.native_detail = native_detail or {}
        self.stdlib = list(STDLIB if stdlib is None else stdlib)
        self.site = list(SITE if site is None else site)
        self.native_err = {'_tkinter': 'ImportError'} if native_err is None else native_err
        self.listing = listing
        self.native_ok = [m for m in sorted(set(self.stdlib) | set(self.site)) if m not in self.native_err]
        self.qemu_rc, self.qemu_stderr, self.qemu_ok, self.qemu_err = qemu_rc, qemu_stderr, qemu_ok, qemu_err
        self.smoke_qemu, self.smoke_qemu_rc, self.smoke_qemu_stderr = smoke_qemu, smoke_qemu_rc, smoke_qemu_stderr
        self.node_qemu, self.node_rc, self.list_rc, self.native_rc = node_qemu, node_rc, list_rc, native_rc
        self.native_stdout = native_stdout
        self.node = {'node': 'v26.12.1', 'fts5': 1, 'sha256': 'a' * 64, 'zlib': 5000}

    def __call__(self, image_id, entrypoint, args, label, timeout, work):
        self.calls.append((image_id, entrypoint, list(args), label, timeout))
        if label.endswith('-list'):
            listing = self.listing if self.listing is not None else {'lib-dynload': self.stdlib, 'site-packages': self.site}
            return result(self.list_rc, listing, lines=())
        if label.endswith('-native'):
            if self.native_stdout is not None:
                return types.SimpleNamespace(returncode=self.native_rc, stdout=self.native_stdout, stderr=b'')
            return result(self.native_rc, {'ok': self.native_ok, 'err': self.native_err,
                                           'detail': {**detail(self.native_err), **self.native_detail}})
        if label.endswith('-smoke-qemu'):
            return result(self.smoke_qemu_rc, self.smoke_qemu or {'sha256': 'a'}, self.smoke_qemu_stderr, lines=())
        if label.endswith('-smoke'):
            return result(0, {'sha256': 'a'}, lines=())
        if label == 'n8n-node':
            return result(self.node_rc, self.node, lines=())
        if label == 'n8n-node-qemu':
            return result(self.qemu_rc, self.node_qemu or self.node, self.qemu_stderr, lines=())
        if label.endswith('-qemu'):
            ok = self.qemu_ok if self.qemu_ok is not None else self.native_ok
            return result(self.qemu_rc, {'ok': ok, 'err': self.qemu_err or {}}, self.qemu_stderr,
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

    def env(self, fake, app='odoo', scope='core', allowed=None, deadline=None):
        return j.check_python(IMAGE, app, scope, j.CORE_PYTHON, self.work, fake, allowed or {}, deadline)

    def test_pass_records_counts_by_kind(self):
        r = self.env(FakeImage())
        self.assertEqual((r['modules_listed'], r['native_ok'], r['qemu_ok']), (5, 4, 4))
        self.assertEqual((r['lib_dynload'], r['site_packages']), ({'listed': 3, 'native_ok': 2}, {'listed': 2, 'native_ok': 2}))
        self.assertEqual((r['native_errors'], r['allowlisted'], r['disallowed']),
                         ({'_tkinter': TK_ERROR}, [], {'_tkinter': TK_ERROR}))
        ok = sorted(['_ssl', 'zlib', 'pydantic_core._pydantic_core', 'yaml._yaml'])
        self.assertEqual(r['modules_sha256'], hashlib.sha256(json.dumps(ok).encode()).hexdigest())
        self.assertEqual(json.loads((self.work / 'odoo-core-native-ok.json').read_text()), ok)
        self.assertEqual(json.loads((self.work / 'odoo-core-modules.json').read_text()), sorted(STDLIB + SITE))
        self.assertEqual(oct((self.work / 'odoo-core-modules.json').stat().st_mode & 0o777), '0o644')
        allowed = self.env(FakeImage(), allowed={'_tkinter': TK_ENTRY})
        self.assertEqual((allowed['allowlisted'], allowed['disallowed']), (['_tkinter'], {}))

    def test_an_allowlisted_module_is_excused_only_for_its_known_cause(self):
        # The coordinator's 2026-11-17 decision: _tkinter may fail natively only because Tcl/Tk is missing.
        for text in ('ImportError: /usr/local/lib/python3.13/lib-dynload/_tkinter.cpython-313-x86_64-linux-gnu.so: '
                     'undefined symbol: Tk_Init', 'ImportError: libtcl8.6.so: cannot open shared object file',
                     'SystemExit: 1', 'ImportError: libtk8.6.so: file too short'):
            with self.subTest(text=text):
                r = self.env(FakeImage(native_detail={'_tkinter': text}), allowed={'_tkinter': TK_ENTRY})
                self.assertEqual((r['allowlisted'], r['disallowed']), ([], {'_tkinter': text}))
        # A failure without any detail (an older probe) is never excused.
        r = self.env(FakeImage(native_stdout=b'{"ok": ["_ssl", "pydantic_core._pydantic_core", "yaml._yaml", "zlib"], '
                                             b'"err": {"_tkinter": "ImportError"}}\n'), allowed={'_tkinter': TK_ENTRY})
        self.assertEqual((r['allowlisted'], r['disallowed']), ([], {'_tkinter': 'ImportError'}))
        # Another module failing natively is not covered by the _tkinter entry.
        r = self.env(FakeImage(native_err={'_tkinter': 'ImportError', 'yaml._yaml': 'ImportError'}),
                     allowed={'_tkinter': TK_ENTRY})
        self.assertEqual((r['allowlisted'], r['disallowed']), (['_tkinter'], {'yaml._yaml': 'ImportError: invented failure of yaml._yaml'}))

    def test_an_allowlisted_module_that_imports_natively_still_goes_through_qemu(self):
        fake = FakeImage(native_err={})
        r = self.env(fake, allowed={'_tkinter': TK_ENTRY})
        self.assertEqual((r['allowlisted'], r['disallowed'], r['qemu_ok']), ([], {}, 5))
        self.assertIn('_tkinter', json.loads((self.work / 'odoo-core-native-ok.json').read_text()))
        qemu = next(call for call in fake.calls if call[3] == 'odoo-core-qemu')
        self.assertEqual(qemu[2][-1], '/j1900/odoo-core-native-ok.json')
        # Being listed does not excuse a difference under QEMU.
        with self.assertRaisesRegex(j.Closed, 'modules differ under -cpu Nehalem: _tkinter'):
            self.env(FakeImage(native_err={}, qemu_ok=['_ssl', 'pydantic_core._pydantic_core', 'yaml._yaml', 'zlib']),
                     allowed={'_tkinter': TK_ENTRY})
        with self.assertRaisesRegex(j.Closed, 'ILLEGAL INSTRUCTION'):
            self.env(FakeImage(native_err={}, qemu_rc=132), allowed={'_tkinter': TK_ENTRY})

    def test_the_emulated_runs_use_qemu_nehalem_on_the_same_interpreter(self):
        fake = FakeImage()
        self.env(fake)
        emulated = [call for call in fake.calls if call[3].endswith('-qemu')]
        self.assertEqual([call[3] for call in emulated], ['odoo-core-qemu', 'odoo-core-smoke-qemu'])
        for _, entrypoint, args, _, _ in emulated:
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
                self.assertIn('last TRY zlib', str(caught.exception))
        for rc, err in ((132, b''), (1, b'qemu: uncaught target signal 4 (Illegal instruction)')):
            with self.subTest(smoke=rc), self.assertRaisesRegex(j.Closed, 'ILLEGAL INSTRUCTION in the smoke'):
                self.env(FakeImage(smoke_qemu_rc=rc, smoke_qemu_stderr=err))

    def test_module_or_smoke_difference_fails(self):
        with self.assertRaisesRegex(j.Closed, 'modules differ under -cpu Nehalem: pydantic_core._pydantic_core'):
            self.env(FakeImage(qemu_ok=['_ssl', 'yaml._yaml', 'zlib']))
        # The same modules import, but QEMU reports an error for one of them: still a difference.
        with self.assertRaisesRegex(j.Closed, 'modules differ under -cpu Nehalem: zlib'):
            self.env(FakeImage(qemu_err={'zlib': 'ImportError'}))
        with self.assertRaisesRegex(j.Closed, 'smoke differs'):
            self.env(FakeImage(smoke_qemu={'sha256': 'b'}))
        with self.assertRaisesRegex(j.Closed, 'emulated smoke failed'):
            self.env(FakeImage(smoke_qemu_rc=1))
        with self.assertRaisesRegex(j.Closed, 'emulated import run failed'):
            self.env(FakeImage(qemu_rc=1, qemu_stderr=b'qemu-x86_64-static: Unable to reserve address space'))

    def test_listing_and_native_runs_must_succeed_and_answer(self):
        cases = [(FakeImage(list_rc=1), 'native module listing failed'),
                 (FakeImage(native_rc=1), 'native import run failed'),
                 (FakeImage(listing=['_ssl', 'pydantic_core._pydantic_core']), 'listing is not'),
                 (FakeImage(listing={'lib-dynload': ['_ssl']}), 'listing is not'),
                 (FakeImage(listing={'lib-dynload': [1], 'site-packages': []}), 'module names'),
                 (FakeImage(stdlib=[], site=[]), 'no native extension modules'),
                 (FakeImage(native_stdout=b'TRY _ssl\n'), 'no JSON result'),
                 (FakeImage(native_stdout=b'TRY _ssl\n{broken\n'), 'no JSON result'),
                 (FakeImage(native_stdout=b'["not", "a", "dict"]\n'), 'native import result')]
        for fake, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(j.Closed, message):
                self.env(fake)

    def test_review_m1_third_party_modules_must_import_natively(self):
        # The review's probes/j1900_gap.py scenario: every site-packages module fails natively, only the interpreter's own
        # modules import. Before the fix this passed; now it fails twice over.
        gap = FakeImage(stdlib=['_ssl', '_hashlib', 'zlib'],
                        site=['pydantic_core._pydantic_core', 'cryptography.hazmat.bindings._rust', 'orjson.orjson'],
                        native_err={m: 'ImportError' for m in ['pydantic_core._pydantic_core',
                                                               'cryptography.hazmat.bindings._rust', 'orjson.orjson']})
        with self.assertRaisesRegex(j.Closed, 'no third-party \\(site-packages\\) native module imports natively'):
            self.env(gap)
        # One third-party module still loading does not excuse the others: they fail the whole check (below).
        partial = FakeImage(native_err={'yaml._yaml': 'ImportError'})
        self.assertEqual(self.env(partial)['disallowed'], {'yaml._yaml': 'ImportError: invented failure of yaml._yaml'})
        with self.assertRaisesRegex(j.Closed, 'no third-party'):
            self.env(FakeImage(site=[], native_err={}))
        with self.assertRaisesRegex(j.Closed, 'no native module imports natively'):
            self.env(FakeImage(native_err={m: 'ImportError' for m in STDLIB + SITE}))

    def test_n8n_node_smoke_natively_and_under_qemu(self):
        self.assertEqual(j.check_node(IMAGE, self.work, FakeImage())['fts5'], 1)
        for fake, message in ((FakeImage(qemu_rc=132), 'ILLEGAL INSTRUCTION'),
                              (FakeImage(node_qemu={'node': 'v26.12.1', 'fts5': 0, 'sha256': 'a' * 64, 'zlib': 5000}),
                               'node smoke differs'),
                              (FakeImage(node_rc=1), 'native node smoke failed')):
            with self.subTest(message=message), self.assertRaisesRegex(j.Closed, message):
                j.check_node(IMAGE, self.work, fake)

    def test_the_whole_check_keeps_its_budget(self):
        now = [0.0]
        deadline = j.Deadline(seconds=1000, clock=lambda: now[0])
        self.assertEqual(deadline.timeout('a', 300), 300)
        now[0] = 900.0
        self.assertEqual(deadline.timeout('b', 300), 100)  # never past the budget
        now[0] = 1000.0
        with self.assertRaisesRegex(j.Closed, 'exceeded its 1000-second budget before c'):
            deadline.timeout('c', 300)
        fake = FakeImage()
        self.env(fake, deadline=j.Deadline(seconds=50, clock=lambda: 0.0))
        self.assertTrue(all(call[4] <= 50 for call in fake.calls))
        caps = sum(j.TIMEOUTS[key] for key in ('list', 'native', 'qemu', 'smoke', 'smoke-qemu'))
        self.assertGreater(2 * caps, j.BUDGET)  # the caps alone could exceed it; the deadline is what bounds the check
        self.assertLessEqual(j.BUDGET / 60, v.RELEASE_MINUTES['candidate'] - 60)  # room for build, scans, handover

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


class AllowlistTest(unittest.TestCase):
    def test_the_reviewed_allowlist_excuses_only_the_missing_tk_for_the_imaged_products(self):
        # Started empty (review M1); _tkinter added for the seven products with an image (coordinator 2026-11-17).
        allowlist = j.load_allowlist()
        self.assertEqual({product: sorted(entries) for product, entries in allowlist.items()},
                         {product: [] if product == 'opendesign' else ['_tkinter'] for product in v.PRODUCTS})
        for product, entries in allowlist.items():
            for entry in entries.values():
                with self.subTest(product=product):
                    self.assertEqual(entry['error_contains'], 'ImportError: libtk8.6.so: cannot open shared object file')
                    self.assertIn('deliberately ships without Tcl/Tk', entry['reason'])
                    self.assertIn('sbom.syft.json', entry['reason'])
                    self.assertIn('2026-11-17', entry['review'])
        # With the real list, every imaged product passes on the real failure text and fails on any other module.
        for product in v.PRODUCTS:
            if product == 'opendesign':
                continue
            with self.subTest(product=product):
                with tempfile.TemporaryDirectory() as d:
                    r = j.check_python(IMAGE, product, 'core', j.CORE_PYTHON, Path(d), FakeImage(), allowlist[product])
                    self.assertEqual((r['allowlisted'], r['disallowed']), (['_tkinter'], {}))
                with tempfile.TemporaryDirectory() as d:
                    r = j.check_python(IMAGE, product, 'core', j.CORE_PYTHON, Path(d),
                                       FakeImage(native_err={'_tkinter': 'ImportError', 'yaml._yaml': 'ImportError'}),
                                       allowlist[product])
                    self.assertEqual(sorted(r['disallowed']), ['yaml._yaml'])

    def test_a_malformed_allowlist_fails_closed(self):
        good = json.loads(j.ALLOWLIST.read_text())
        entry = {'reason': 'Tk is not in the slim base image', 'review': 'owner 2026-11-18, release record',
                 'error_contains': 'ImportError: libtk8.6.so: cannot open shared object file'}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'allowlist.json'
            path.write_text(json.dumps({**good, 'products': {**good['products'], 'odoo': {'_tkinter': entry}}}))
            self.assertEqual(j.load_allowlist(path)['odoo'], {'_tkinter': entry})
            bad = [{**good, 'schema': 2}, {**good, 'products': {**good['products'], 'unknown': {}}},
                   {**good, 'products': {k: x for k, x in good['products'].items() if k != 'odoo'}},
                   {**good, 'products': {**good['products'], 'odoo': []}},
                   {**good, 'products': {**good['products'], 'odoo': {'_tkinter': {'reason': 'r'}}}},
                   {**good, 'products': {**good['products'], 'odoo': {'_tkinter': {'reason': 'r', 'review': 'x'}}}},
                   {**good, 'products': {**good['products'], 'odoo': {'_tkinter': {**entry, 'error_contains': ' '}}}},
                   {**good, 'products': {**good['products'], 'odoo': {'_tkinter': {**entry, 'reason': ' '}}}},
                   {**good, 'products': {**good['products'], 'odoo': {'_tkinter': {**entry, 'extra': 'x'}}}},
                   {**good, 'products': {**good['products'], 'odoo': {'not a module': entry}}}, []]
            for value in bad:
                path.write_text(json.dumps(value))
                with self.subTest(value=str(value)[:80]), self.assertRaises(j.Closed):
                    j.load_allowlist(path)
            path.write_text('{not json')
            with self.assertRaisesRegex(j.Closed, 'not JSON'):
                j.load_allowlist(path)


class InstallAndRecordTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.qemu = self.base / 'qemu-x86_64-static'
        self.qemu.write_bytes(b'invented static qemu bytes')
        self.evidence = self.base / 'release-evidence'
        self.evidence.mkdir(mode=0o700)
        self.allowed = {product: {} for product in v.PRODUCTS}
        for product in self.allowed:
            self.allowed[product]['_tkinter'] = TK_ENTRY

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

    def check(self, app, fake, image_after=IMAGE, allowed=None, verify=None, installer=None):
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
        with mock.patch.object(j, 'verify_current', side_effect=verify or (lambda a, c: subject)) as verified, \
             mock.patch.object(j, 'inspect_image', return_value={'Id': image_after}), \
             mock.patch.object(j, 'prepare', side_effect=prepare), \
             mock.patch.dict(os.environ, {'RUNNER_TEMP': str(self.base)}):
            record = j.check(app, self.base / 'candidate', self.evidence, run=fake,
                             qemu_installer=installer or (lambda: qemu), allowlist=self.allowed if allowed is None else allowed)
        verified.assert_called_once_with(app, self.base / 'candidate')
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
        self.assertEqual(record['envs']['core']['allowlisted'], ['_tkinter'])
        self.assertNotIn('disallowed', record['envs']['core'])
        self.assertIsNone(record['node'])
        self.assertEqual(record['probe_sha256'], hashlib.sha256(PROBE.read_bytes()).hexdigest())
        self.assertEqual(record['allowlist_sha256'], hashlib.sha256(j.ALLOWLIST.read_bytes()).hexdigest())
        self.assertEqual(record['qemu']['package'], 'qemu-user-static')
        for flag in ('--network', 'none', '--read-only', '--user', '10001:10001', '--cap-drop', 'ALL'):
            self.assertIn(flag, record['container'])
        self.assertFalse(any(call[3].startswith('n8n-node') for call in fake.calls))
        line = j.summary(record)
        self.assertIn('core: lib-dynload 2/3, site-packages 2/2 natively, 1 allowlisted native errors, 4/4 under QEMU', line)
        self.assertIn('child: lib-dynload 2/3', line)

    def test_n8n_has_no_child_venv_and_runs_the_node_check(self):
        fake = FakeImage()
        record = self.check('n8n', fake)
        self.assertEqual(set(record['envs']), {'core'})
        self.assertEqual(record['node']['fts5'], 1)
        self.assertIn('n8n-node-qemu', [call[3] for call in fake.calls])
        self.assertFalse(any('/opt/woow/apps/n8n/.venv' in entry for call in fake.calls for entry in [call[1], *call[2]]))
        self.assertIn('node smoke with FTS5', j.summary(record))

    def test_native_errors_outside_the_allowlist_fail_after_every_environment_ran(self):
        empty = {product: {} for product in v.PRODUCTS}
        fake = FakeImage(native_err={'_tkinter': 'ImportError', 'yaml._yaml': 'ImportError'})
        with self.assertRaises(j.Closed) as caught:
            self.check('hermes', fake, allowed=empty)
        message = str(caught.exception)
        for part in ('core _tkinter (%s)' % TK_ERROR, 'core yaml._yaml (ImportError: invented failure of yaml._yaml)',
                     'child _tkinter (%s)' % TK_ERROR, 'child yaml._yaml (ImportError: invented failure of yaml._yaml)',
                     'packaging/j1900-allowlist.json', 'hermes'):
            self.assertIn(part, message)
        self.assertIn('hermes-child-smoke-qemu', [call[3] for call in fake.calls])  # QEMU still ran everywhere
        self.assertFalse((self.evidence / 'j1900-hermes.json').exists())
        # The allowlist is per product: an entry for another product does not help.
        other = {product: {} for product in v.PRODUCTS}
        other['emqx'] = {'_tkinter': TK_ENTRY, 'yaml._yaml': {'reason': 'r', 'review': 'x',
                                                               'error_contains': 'invented failure of yaml._yaml'}}
        with self.assertRaisesRegex(j.Closed, 'does not list them for hermes'):
            self.check('hermes', FakeImage(native_err={'_tkinter': 'ImportError', 'yaml._yaml': 'ImportError'}), allowed=other)
        self.check('emqx', FakeImage(native_err={'_tkinter': 'ImportError', 'yaml._yaml': 'ImportError'}), allowed=other)

    def test_refusals_and_order(self):
        with self.assertRaisesRegex(j.Closed, 'not allowed'):
            j.check('odoo-manage', self.base / 'candidate', self.evidence, run=FakeImage(), qemu_installer=dict,
                    allowlist=self.allowed)
        with self.assertRaisesRegex(j.Closed, 'evidence directory missing'):
            j.check('odoo', self.base / 'candidate', self.base / 'absent', run=FakeImage(), qemu_installer=dict,
                    allowlist=self.allowed)
        installs = []

        def broken(app, candidate):
            raise supply_chain.Closed('supply-chain precondition failed')
        with self.assertRaises(supply_chain.Closed):
            self.check('odoo', FakeImage(), verify=broken, installer=lambda: installs.append(1))
        self.assertEqual(installs, [])  # an image that does not match its evidence stops before QEMU is installed
        with self.assertRaisesRegex(j.Closed, 'image changed during the J1900 check'):
            self.check('hermes', FakeImage(), image_after='sha256:' + 'f' * 64)
        self.assertFalse((self.evidence / 'j1900-hermes.json').exists())
        self.check('emqx', FakeImage())
        with self.assertRaisesRegex(j.Closed, 'already recorded'):
            self.check('emqx', FakeImage())
        with self.assertRaisesRegex(j.Closed, 'ILLEGAL INSTRUCTION'):
            self.check('litellm', FakeImage(qemu_rc=132))
        self.assertFalse((self.evidence / 'j1900-litellm.json').exists())

    def test_cli_maps_every_failure_to_one_closed_line(self):
        for error, message in ((j.Closed('invented reason'), 'J1900 check CLOSED: invented reason'),
                               (supply_chain.Closed('supply-chain precondition failed'),
                                'J1900 check CLOSED: Closed (candidate evidence, Docker or QEMU)'),
                               (OSError('x'), 'J1900 check CLOSED: OSError (candidate evidence, Docker or QEMU)'),
                               (KeyError('x'), 'J1900 check CLOSED: KeyError (candidate evidence, Docker or QEMU)')):
            with self.subTest(error=type(error).__name__), mock.patch.object(j, 'main', side_effect=error), \
                 self.assertRaises(SystemExit) as caught:
                j.cli(['odoo', 'c', 'e'])
            self.assertEqual(str(caught.exception), message)
        with self.assertRaisesRegex(j.Closed, 'usage'):
            j.main(['odoo'])

    def test_the_check_writes_no_workflow_environment_and_reads_no_secret(self):
        source = Path(j.__file__).read_text()
        for absent in ('GITHUB_ENV', 'GITHUB_PATH', 'GITHUB_OUTPUT', 'GITHUB_TOKEN', 'GHCR_TOKEN', 'docker login',
                       "'login'", 'push'):
            self.assertNotIn(absent, source)


if __name__ == '__main__':
    unittest.main()
