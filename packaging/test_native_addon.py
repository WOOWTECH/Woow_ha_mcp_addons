"""packaging/native_addon.mjs: the one way a native addon (better-sqlite3's prebuilt binary) reaches the n8n image.

Unreleased (0.4.12 line). The script runs under Node with synthetic archives and an injected request function: nothing here
touches the network. It must refuse every archive that is not exactly the pinned one, and must write the single pinned file
as 0644 under the installed package of the pinned version, whatever the archive or the umask said.
"""
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'packaging/native_addon.mjs'
MEMBER = 'build/Release/better_sqlite3.node'
BODY = b'\x7fELF synthetic native addon ' * 100
VERSION = '12.11.1'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive(entries, fmt=tarfile.USTAR_FORMAT, mode=0o777):
    """A .tar.gz of (name, bytes, type) entries; the member's mode is the world-writable one the real archive has."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w', format=fmt) as tar:
        for name, data, kind in entries:
            info = tarfile.TarInfo(name)
            info.type, info.mode = kind, mode
            if kind == tarfile.SYMTYPE:
                info.linkname = '/etc/passwd'
            info.size = len(data) if kind == tarfile.REGTYPE else 0
            tar.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
    return gzip.compress(buffer.getvalue(), mtime=0), buffer.getvalue()


def pin_for(packed, body=BODY, **changes):
    value = {'package': 'better-sqlite3', 'version': VERSION, 'url': 'https://github.com/WiseLibs/better-sqlite3/releases/download/x',
             'sha256': sha(packed), 'size': len(packed), 'member': MEMBER, 'memberSize': len(body), 'memberSha256': sha(body)}
    value.update(changes)
    return value


def node(code, **case):
    """Run code (an ES module) with `m` = native_addon.mjs and `case` = the JSON given; its last stdout line is JSON."""
    prelude = f"import * as m from {json.dumps(SCRIPT.as_uri())}; import fs from 'node:fs'; import {{ EventEmitter }} from 'node:events'; " \
              f"const c = JSON.parse(process.env.CASE); const out = (v) => console.log(JSON.stringify(v));\n"
    finished = subprocess.run([shutil.which('node'), '--input-type=module', '-e', prelude + code], capture_output=True, text=True,
                              env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'CASE': json.dumps(case)}, timeout=60, check=False)
    assert finished.returncode == 0, finished.stderr
    return json.loads(finished.stdout.strip().splitlines()[-1])


VERIFY = ("const r = (() => { try { const e = m.verifiedMember(fs.readFileSync(c.file), c.pin); return { ok: true, size: e.length, sha: m.sha256(e) }; }"
          " catch (e) { return { ok: false, message: e.message }; } })(); out(r);")


class NativeAddonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert shutil.which('node'), 'node is required (the n8n image runs the same script on its Node 26 build stage)'

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix='native-addon-'))
        self.addCleanup(shutil.rmtree, self.dir, True)

    def verify(self, packed, pin=None):
        file = self.dir / 'a.tar.gz'
        file.write_bytes(packed)
        return node(VERIFY, file=str(file), pin=pin or pin_for(packed))

    def refused(self, packed, message, pin=None):
        result = self.verify(packed, pin)
        self.assertFalse(result['ok'], result)
        self.assertIn(message, result['message'])

    def test_the_pinned_archive_gives_the_pinned_file(self):
        packed, _ = archive([(MEMBER, BODY, tarfile.REGTYPE)])
        self.assertEqual(self.verify(packed), {'ok': True, 'size': len(BODY), 'sha': sha(BODY)})

    def test_size_and_digests_are_checked_before_the_archive_is_opened(self):
        packed, _ = archive([(MEMBER, BODY, tarfile.REGTYPE)])
        self.refused(packed, 'archive is', pin_for(packed, size=len(packed) + 1))
        self.refused(packed, 'archive sha256 is not the pinned value', pin_for(packed, sha256='0' * 64))
        # An archive whose own digest is pinned but whose content is not what the member pin says.
        self.refused(packed, 'sha256 is not the pinned value', pin_for(packed, memberSha256='0' * 64))
        self.refused(packed, 'the pin says', pin_for(packed, memberSize=len(BODY) + 1))
        tampered, _ = archive([(MEMBER, BODY + b'!', tarfile.REGTYPE)])
        self.refused(tampered, 'archive sha256 is not the pinned value', pin_for(tampered, sha256=sha(packed)))  # right size, other bytes

    def test_the_archive_must_hold_exactly_the_one_pinned_plain_file(self):
        extra, _ = archive([(MEMBER, BODY, tarfile.REGTYPE), ('build/Release/other.node', b'x', tarfile.REGTYPE)])
        self.refused(extra, 'more than the one pinned entry')
        elsewhere, _ = archive([('../../etc/cron.d/x', BODY, tarfile.REGTYPE)])
        self.refused(elsewhere, 'not the pinned')
        absolute, _ = archive([('/usr/local/bin/node', BODY, tarfile.REGTYPE)])
        self.refused(absolute, 'not the pinned')
        link, _ = archive([(MEMBER, b'', tarfile.SYMTYPE)])
        self.refused(link, 'not a plain file')
        directory, _ = archive([('build', b'', tarfile.DIRTYPE), (MEMBER, BODY, tarfile.REGTYPE)])
        self.refused(directory, 'not a plain file')
        extended, _ = archive([(MEMBER, BODY, tarfile.REGTYPE)], fmt=tarfile.PAX_FORMAT)
        # PAX writes a header only when it has to; a long name forces an 'x' record in front of the entry.
        long_name = 'build/' + 'd' * 150 + '/Release/better_sqlite3.node'
        pax, _ = archive([(long_name, BODY, tarfile.REGTYPE)], fmt=tarfile.PAX_FORMAT)
        self.refused(pax, 'not a plain file')
        prefixed, _ = archive([('build/' + 'd' * 120 + '/better_sqlite3.node', BODY, tarfile.REGTYPE)])
        self.refused(prefixed, 'path prefix')
        self.assertTrue(self.verify(extended)['ok'])  # the same format is fine when no extension record is needed

    def test_a_broken_or_hostile_container_is_refused_not_crashed_on(self):
        packed, raw = archive([(MEMBER, BODY, tarfile.REGTYPE)])
        flipped = bytearray(raw)
        flipped[0] ^= 0x01  # a header byte changes, its checksum does not
        self.refused(gzip.compress(bytes(flipped), mtime=0), 'checksum does not match')
        self.refused(gzip.compress(raw[:1024], mtime=0), 'cut short')
        self.refused(gzip.compress(raw[:300], mtime=0), 'too short')
        self.refused(gzip.compress(raw + b'trailing', mtime=0), 'more than the one pinned entry')
        junk = b'this is not gzip data at all'
        self.refused(junk, 'not a gzip file', pin_for(junk))
        bomb = gzip.compress(b'\0' * (40 * 1024 * 1024), mtime=0)  # a few KB that unpack to 40 MiB
        self.refused(bomb, 'not a gzip file within', pin_for(bomb))

    def install(self, pin, entry=BODY, version=VERSION, umask=0o022, package=True):
        directory = self.dir / 'node_modules' / 'better-sqlite3'
        if package:
            directory.mkdir(parents=True, exist_ok=True)
            (directory / 'package.json').write_text(json.dumps({'name': 'better-sqlite3', 'version': version}))
        (self.dir / 'entry.bin').write_bytes(entry)
        code = ("process.umask(c.umask); const r = (() => { try { const t = m.installMember(fs.readFileSync(c.entry), c.pin, c.dir);"
                " return { ok: true, target: t }; } catch (e) { return { ok: false, message: e.message }; } })(); out(r);")
        return node(code, entry=str(self.dir / 'entry.bin'), pin=pin, dir=str(directory), umask=umask), directory

    def test_the_file_is_installed_as_0644_whatever_the_archive_and_the_umask_say(self):
        packed, _ = archive([(MEMBER, BODY, tarfile.REGTYPE)])  # the archive's own mode is 0777
        for umask in (0o022, 0o000, 0o077):
            with self.subTest(umask=oct(umask)):
                shutil.rmtree(self.dir / 'node_modules', ignore_errors=True)
                result, directory = self.install(pin_for(packed), umask=umask)
                self.assertTrue(result['ok'], result)
                target = directory / MEMBER
                self.assertEqual(Path(result['target']), target)
                self.assertEqual(target.read_bytes(), BODY)
                self.assertEqual(target.stat().st_mode & 0o7777, 0o644)
                self.assertEqual([(directory / d).stat().st_mode & 0o7777 for d in ('build', 'build/Release')], [0o755, 0o755])
                self.assertEqual(sorted(p.name for p in target.parent.iterdir()), ['better_sqlite3.node'])  # no temporary left

    def test_only_the_installed_package_of_the_pinned_version_gets_the_file(self):
        packed, _ = archive([(MEMBER, BODY, tarfile.REGTYPE)])
        result, _ = self.install(pin_for(packed), version='11.10.0')
        self.assertFalse(result['ok'])
        self.assertIn('installed better-sqlite3 is 11.10.0, the pinned addon is for 12.11.1', result['message'])
        shutil.rmtree(self.dir / 'node_modules', ignore_errors=True)
        result, _ = self.install(pin_for(packed), package=False)
        self.assertFalse(result['ok'])
        self.assertIn('is not an installed package', result['message'])
        self.assertFalse((self.dir / 'node_modules/better-sqlite3/build').exists())

    def test_odd_package_paths_and_members_cannot_loop_escape_or_follow_a_link(self):
        packed, _ = archive([(MEMBER, BODY, tarfile.REGTYPE)])
        code = ("const r = (() => { try { const t = m.installMember(fs.readFileSync(c.entry), c.pin, c.dir); return { ok: true, target: t }; }"
                " catch (e) { return { ok: false, message: e.message }; } })(); out(r);")
        directory = self.dir / 'node_modules' / 'better-sqlite3'
        directory.mkdir(parents=True)
        (directory / 'package.json').write_text(json.dumps({'version': VERSION}))
        (self.dir / 'entry.bin').write_bytes(BODY)
        entry = str(self.dir / 'entry.bin')
        # A package directory written with a trailing slash or dots resolves to the same place (and cannot loop).
        for spelled in (str(directory) + '/', str(directory / '.'), str(self.dir / 'node_modules' / '..' / 'node_modules' / 'better-sqlite3')):
            shutil.rmtree(directory / 'build', ignore_errors=True)
            result = node(code, entry=entry, pin=pin_for(packed), dir=spelled)
            self.assertTrue(result['ok'], (spelled, result))
            self.assertEqual((directory / MEMBER).read_bytes(), BODY)
        # A member that could leave the package is refused before anything is written.
        shutil.rmtree(directory / 'build')
        for member in ('../outside.node', '/tmp/outside.node', 'build/../../outside.node'):
            result = node(code, entry=entry, pin=pin_for(packed, member=member), dir=str(directory))
            self.assertEqual(result, {'ok': False, 'message': 'native addon pin is incomplete or malformed'}, member)
        self.assertEqual(sorted(p.name for p in (self.dir / 'node_modules').iterdir()), ['better-sqlite3'])
        self.assertFalse((directory / 'build').exists())
        # An existing link at the target is never followed or replaced.
        (directory / 'build/Release').mkdir(parents=True)
        (self.dir / 'elsewhere.node').write_bytes(BODY)
        (directory / MEMBER).symlink_to(self.dir / 'elsewhere.node')
        result = node(code, entry=entry, pin=pin_for(packed), dir=str(directory))
        self.assertEqual((result['ok'], result['message'].endswith('is a link')), (False, True))
        self.assertTrue((directory / MEMBER).is_symlink())

    def test_an_existing_file_is_kept_when_identical_and_never_replaced_otherwise(self):
        packed, _ = archive([(MEMBER, BODY, tarfile.REGTYPE)])
        result, directory = self.install(pin_for(packed))
        self.assertTrue(result['ok'])
        (directory / MEMBER).chmod(0o755)
        again, _ = self.install(pin_for(packed))
        self.assertTrue(again['ok'])
        self.assertEqual((directory / MEMBER).stat().st_mode & 0o7777, 0o644)  # normalised, content untouched
        (directory / MEMBER).write_bytes(b'another binary')
        refused, _ = self.install(pin_for(packed))
        self.assertFalse(refused['ok'])
        self.assertIn('exists with other content', refused['message'])
        self.assertEqual((directory / MEMBER).read_bytes(), b'another binary')

    DOWNLOAD = ("const script = c.script; const calls = []; const request = (url, options, cb) => { calls.push(url.href); const step = script.shift();"
                " const req = new EventEmitter(); req.destroy = (e) => req.emit('error', e);"
                " queueMicrotask(() => { const res = new EventEmitter(); res.statusCode = step.status; res.headers = step.headers ?? {};"
                " res.resume = () => {}; res.destroy = () => {}; cb(res); for (const chunk of step.body ?? []) res.emit('data', Buffer.from(chunk)); res.emit('end'); });"
                " return req; };")

    def download(self, script, retry=False, **options):
        code = self.DOWNLOAD + ("const fn = c.retry ? (u, o) => m.downloadWithRetry(u, o, { attempts: 3, pause: 1 }) : (u, o) => m.download(u, o);"
                                " const r = await fn(c.url, { request, ...c.options }).then((b) => ({ ok: true, body: b.toString() }),"
                                " (e) => ({ ok: false, message: e.message, status: e.status ?? null })); out({ ...r, calls });")
        return node(code, script=script, retry=retry, options=options, url='https://github.com/WiseLibs/x.tar.gz')

    def test_download_follows_https_redirects_and_nothing_else(self):
        ok = {'status': 200, 'body': ['pay', 'load']}
        moved = {'status': 302, 'headers': {'location': 'https://release-assets.githubusercontent.com/a?sig=1'}}
        result = self.download([moved, ok])
        self.assertEqual((result['ok'], result['body'], result['calls']),
                         (True, 'payload', ['https://github.com/WiseLibs/x.tar.gz', 'https://release-assets.githubusercontent.com/a?sig=1']))
        relative = self.download([{'status': 301, 'headers': {'location': '/other/place.tar.gz'}}, ok])
        self.assertEqual(relative['calls'][1], 'https://github.com/other/place.tar.gz')
        downgrade = self.download([{'status': 302, 'headers': {'location': 'http://example.invalid/x'}}, ok])
        self.assertFalse(downgrade['ok'])
        self.assertIn('over http: refused', downgrade['message'])
        self.assertFalse(self.download([moved] * 7)['ok'])  # more than 5 redirects
        self.assertIn('too many redirects', self.download([moved] * 7)['message'])
        self.assertIn('not a URL', self.download([{'status': 302, 'headers': {'location': 'https://[bad'}}])['message'])  # no crash in the callback

    def test_download_is_capped_and_a_missing_asset_is_not_retried(self):
        big = self.download([{'status': 200, 'body': ['x' * 10, 'y' * 10]}], maxBytes=15)
        self.assertFalse(big['ok'])
        self.assertIn('over 15 bytes', big['message'])
        missing = self.download([{'status': 404}, {'status': 200, 'body': ['late']}], retry=True)
        self.assertEqual((missing['ok'], missing['status'], len(missing['calls'])), (False, 404, 1))
        flaky = self.download([{'status': 503}, {'status': 502}, {'status': 200, 'body': ['fine']}], retry=True)
        self.assertEqual((flaky['ok'], flaky['body'], len(flaky['calls'])), (True, 'fine', 3))
        down = self.download([{'status': 503}] * 3, retry=True)
        self.assertEqual((down['ok'], down['status'], len(down['calls'])), (False, 503, 3))

    def test_the_command_line_installs_from_inputs_or_from_flags_and_fails_closed(self):
        packed, _ = archive([(MEMBER, BODY, tarfile.REGTYPE)])
        (self.dir / 'a.tar.gz').write_bytes(packed)
        pin = pin_for(packed)
        inputs = {'native_addons': {'better-sqlite3': {
            'package': 'better-sqlite3', 'version': VERSION, 'url': pin['url'], 'sha256': pin['sha256'], 'size': pin['size'],
            'member': MEMBER, 'member_size': pin['memberSize'], 'member_sha256': pin['memberSha256']}}}
        (self.dir / 'inputs.json').write_text(json.dumps(inputs))
        modules = self.dir / 'node_modules'
        package = modules / 'better-sqlite3'
        package.mkdir(parents=True)
        (package / 'package.json').write_text(json.dumps({'version': VERSION}))

        def cli(*arguments):
            return subprocess.run([shutil.which('node'), str(SCRIPT), *arguments], capture_output=True, text=True, timeout=60,
                                  env={'PATH': '/usr/local/bin:/usr/bin:/bin'}, check=False)

        done = cli('install', '--inputs', str(self.dir / 'inputs.json'), '--addon', 'better-sqlite3', '--node-modules', str(modules),
                   '--from-file', str(self.dir / 'a.tar.gz'))
        self.assertEqual((done.returncode, done.stderr), (0, ''), done.stdout)
        self.assertIn(pin['memberSha256'], done.stdout)
        self.assertEqual((package / MEMBER).read_bytes(), BODY)
        shutil.rmtree(package / 'build')
        flags = ['install', '--version', VERSION, '--into', str(package), '--url', pin['url'], '--sha256', pin['sha256'],
                 '--size', str(pin['size']), '--member', MEMBER, '--member-size', str(pin['memberSize']),
                 '--member-sha256', pin['memberSha256'], '--from-file', str(self.dir / 'a.tar.gz')]
        self.assertEqual(cli(*flags).returncode, 0)
        shutil.rmtree(package / 'build')
        wrong = cli(*flags[:flags.index('--sha256') + 1], '1' * 64, *flags[flags.index('--sha256') + 2:])
        self.assertEqual(wrong.returncode, 1)
        self.assertIn('native addon install failed: archive sha256 is not the pinned value', wrong.stderr)
        self.assertFalse((package / 'build').exists())  # nothing was written
        self.assertEqual(cli('install', '--inputs', str(self.dir / 'inputs.json'), '--addon', 'unknown', '--node-modules', str(modules)).returncode, 1)
        self.assertEqual(cli('uninstall').returncode, 1)
        self.assertEqual(cli('install', '--version').returncode, 1)
        self.assertEqual(cli('install', '--url', 'http://example.invalid/x', '--version', VERSION).returncode, 1)

    def test_the_pin_in_inputs_is_complete_and_what_the_script_reads(self):
        inputs = json.loads((ROOT / 'packaging/inputs.json').read_text())
        code = "const p = m.checkPin(m.pinFrom(c.inputs, 'better-sqlite3')); out(p);"
        pin = node(code, inputs=inputs)
        entry = inputs['native_addons']['better-sqlite3']
        self.assertEqual(pin, {'package': 'better-sqlite3', 'version': entry['version'], 'url': entry['url'], 'sha256': entry['sha256'],
                               'size': entry['size'], 'member': entry['member'], 'memberSize': entry['member_size'],
                               'memberSha256': entry['member_sha256']})
        for field, value in (('sha256', 'abc'), ('member', '../x.node'), ('url', 'http://github.com/x'), ('size', 0)):
            with self.subTest(field=field):
                broken = json.loads(json.dumps(inputs))
                broken['native_addons']['better-sqlite3'][field] = value
                bad = node("try { m.checkPin(m.pinFrom(c.inputs, 'better-sqlite3')); out('accepted'); } catch (e) { out(e.message); }", inputs=broken)
                self.assertEqual(bad, 'native addon pin is incomplete or malformed')


if __name__ == '__main__':
    unittest.main()
