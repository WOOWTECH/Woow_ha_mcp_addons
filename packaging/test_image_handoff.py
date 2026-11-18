"""image_handoff.py with owned fake docker save archives and a fake Docker: no daemon, image or registry."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch

import image_handoff as m
import supply_chain
import validate as v

APP = 'odoo'
TAG = 'local/mcp-%s:%s' % (APP, v.version_for(APP))


class Kind:
    """A tar member type other than a regular file (tarfile's type constants are bytes, like file contents)."""

    def __init__(self, type_):
        self.type = type_


DIRECTORY, SYMLINK, HARDLINK, DEVICE = Kind(tarfile.DIRTYPE), Kind(tarfile.SYMTYPE), Kind(tarfile.LNKTYPE), Kind(tarfile.CHRTYPE)


def archive_bytes(tag=TAG, layers=(b'layer one', b'layer two'), images=1, config_extra=None, extra_members=(),
                  directories=True, rename=None):
    """A docker-save-shaped archive (moby v28: blobs/sha256 files, index.json, manifest.json, oci-layout, repositories,
    the blobs directories); returns (bytes, image_id, diff_ids). extra_members: (name, bytes or a Kind)."""
    diff_ids = ['sha256:' + hashlib.sha256(layer).hexdigest() for layer in layers]
    config = json.dumps({'architecture': 'amd64', 'os': 'linux', 'rootfs': {'type': 'layers', 'diff_ids': diff_ids},
                         **(config_extra or {})}).encode()
    image_id = 'sha256:' + hashlib.sha256(config).hexdigest()
    entry = {'Config': 'blobs/sha256/' + image_id[7:], 'RepoTags': [tag],
             'Layers': ['blobs/sha256/' + d[7:] for d in diff_ids]}
    members = [('blobs', DIRECTORY), ('blobs/sha256', DIRECTORY)] if directories else []
    members += [(entry['Config'], config), *zip(entry['Layers'], layers),
                ('index.json', b'{"schemaVersion": 2}'), ('manifest.json', json.dumps([entry] * images).encode()),
                ('oci-layout', b'{"imageLayoutVersion": "1.0.0"}'), ('repositories', b'{}'), *extra_members]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as tar:
        for name, data in members:
            info = tarfile.TarInfo((rename or {}).get(name, name))
            if isinstance(data, Kind):
                info.type = data.type
                if data.type in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                    info.linkname = 'manifest.json'
                tar.addfile(info)
            else:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue(), image_id, diff_ids


class FakeDocker:
    """`image save` writes the owned archive; `load` adds `loaded` (default: the tested ID under the tag) to the image
    list that `image ls` reports."""

    def __init__(self, archive, present=False, load_rc=0, save_rc=0, loaded=None, existing=()):
        self.archive, self.present, self.load_rc, self.save_rc = archive, present, load_rc, save_rc
        self.loaded, self.images, self.calls = loaded, set(existing), []

    def __call__(self, argv, timeout=1800):
        self.calls.append(list(argv))
        if argv[:2] == ['image', 'save']:
            Path(argv[3]).write_bytes(self.archive)
            return types.SimpleNamespace(returncode=self.save_rc, stdout=b'')
        if argv[:2] == ['image', 'inspect']:
            return types.SimpleNamespace(returncode=0 if self.present else 1, stdout=b'')
        if argv[:2] == ['image', 'ls']:
            return types.SimpleNamespace(returncode=0, stdout=''.join(line + '\n' for line in sorted(self.images)).encode())
        if argv[0] == 'load':
            if self.load_rc == 0:
                self.present = True
                self.images |= set(self.loaded)
            return types.SimpleNamespace(returncode=self.load_rc, stdout=b'')
        raise AssertionError(argv)


class ImageHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.archive, self.image_id, self.diff_ids = archive_bytes()
        self.subject = {'app': APP, 'source': 'a' * 40, 'image_id': self.image_id, 'diff_ids': self.diff_ids,
                        'archive_sha256': '0' * 64}
        self.evidence = self.base / 'candidate-evidence'
        self.candidate = self.evidence / 'candidate'
        self.candidate.mkdir(parents=True)
        (self.candidate / 'subject.json').write_text(json.dumps(self.subject))
        self.j1900 = {'app': APP, 'version': v.version_for(APP), 'source': 'a' * 40, 'image_id': self.image_id,
                      'passed': True}
        (self.evidence / 'release-evidence').mkdir()
        self.j1900_path = self.evidence / 'release-evidence' / ('j1900-%s.json' % APP)
        self.j1900_path.write_text(json.dumps(self.j1900))
        self.handoff = self.base / 'handoff'
        self.output = self.base / 'github-output'
        self.output.write_text('')

    def tearDown(self):
        self.temporary.cleanup()

    def fake(self, archive=None, **kwargs):
        kwargs.setdefault('loaded', {self.image_id + ' ' + TAG})
        return FakeDocker(self.archive if archive is None else archive, **kwargs)

    def save(self, docker=None, inspect_id=None, env=None, verify=None):
        docker = docker or self.fake()
        metadata = {'Id': inspect_id or self.image_id, 'RootFS': {'Layers': self.diff_ids}}
        with patch.object(m, 'docker', side_effect=docker), patch.object(m, 'inspect_image', return_value=metadata), \
             patch.object(m, 'verify_current', side_effect=verify or (lambda app, candidate: self.subject)):
            return m.save(APP, self.candidate, self.handoff, env={'GITHUB_OUTPUT': str(self.output)} if env is None else env)

    def load(self, docker=None, expected=None, loaded_id=None, loaded_layers=None):
        docker = docker or self.fake()
        metadata = {'Id': loaded_id or self.image_id, 'RootFS': {'Layers': loaded_layers or self.diff_ids}}
        with patch.object(m, 'docker', side_effect=docker), patch.object(m, 'inspect_image', return_value=metadata):
            return m.load(APP, self.handoff, self.evidence, env={'EXPECTED_IMAGE_ID': expected or self.image_id})

    def test_save_hands_over_exactly_the_tested_image_and_outputs_its_id(self):
        docker = self.fake()
        record = self.save(docker)
        self.assertEqual(docker.calls, [['image', 'save', '--output', str(self.handoff / 'image.tar'), TAG]])
        self.assertEqual(record, json.loads((self.handoff / 'handoff.json').read_text()))
        self.assertEqual(record, {'app': APP, 'version': v.version_for(APP), 'tag': TAG, 'image_id': self.image_id,
                                  'diff_ids': self.diff_ids, 'source': 'a' * 40,
                                  'archive_sha256': hashlib.sha256(self.archive).hexdigest(),
                                  'archive_bytes': len(self.archive)})
        self.assertEqual(self.output.read_text(), 'image_id=%s\n' % self.image_id)
        self.assertEqual(self.handoff.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.handoff / 'handoff.json').stat().st_mode & 0o777, 0o600)

    def test_save_refusals(self):
        other, _, _ = archive_bytes(config_extra={'invented': 'another image'})
        two, _, _ = archive_bytes(images=2)
        retagged, _, _ = archive_bytes(tag='local/mcp-odoo:latest')
        cases = [({'env': {}}, 'GITHUB_OUTPUT'),
                 ({'docker': self.fake(save_rc=1)}, 'docker image save failed'),
                 ({'inspect_id': 'sha256:' + 'f' * 64}, 'no longer names the tested image'),
                 ({'docker': self.fake(other)}, 'config digest is not the tested image ID'),
                 ({'docker': self.fake(two)}, 'exactly one image'),
                 ({'docker': self.fake(retagged)}, 'not tagged ' + TAG),
                 ({'docker': self.fake(b'not a tar archive')}, 'not a docker save archive')]
        for kwargs, message in cases:
            shutil.rmtree(self.handoff, ignore_errors=True)
            self.output.write_text('')
            with self.subTest(message=message), self.assertRaisesRegex(m.Closed, message):
                self.save(**kwargs)
            self.assertEqual(self.output.read_text(), '')  # no job output for a refused handover
        shutil.rmtree(self.handoff, ignore_errors=True)
        docker = self.fake()

        def broken(app, candidate):
            raise supply_chain.Closed('supply-chain precondition failed')
        with self.assertRaises(supply_chain.Closed):
            self.save(docker, verify=broken)
        self.assertEqual(docker.calls, [])  # nothing is saved for an image that does not match its evidence
        self.handoff.mkdir()
        with self.assertRaisesRegex(m.Closed, 'already exists'):
            self.save()
        with self.assertRaisesRegex(m.Closed, 'not allowed'):
            m.save('odoo-manage', self.candidate, self.base / 'x', env={'GITHUB_OUTPUT': str(self.output)})

    def test_the_archive_holds_only_the_names_docker_save_writes_each_once(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'image.tar'

            def check(archive):
                path.write_bytes(archive)
                m.check_archive(path, self.image_id, TAG, self.diff_ids)
            check(self.archive)
            check(archive_bytes(directories=False)[0])  # directory entries are optional
            # Review round 2: Docker reads the last './manifest.json'; this check must never read another member.
            second = json.dumps([{'Config': 'blobs/sha256/' + self.image_id[7:], 'RepoTags': [TAG, 'x:y'], 'Layers': []}])
            cases = {
                'manifest.json twice through ./': archive_bytes(extra_members=[('./manifest.json', second.encode())])[0],
                'the same name twice': archive_bytes(extra_members=[('manifest.json', second.encode())])[0],
                'only ./manifest.json': archive_bytes(rename={'manifest.json': './manifest.json'})[0],
                'an absolute name': archive_bytes(extra_members=[('/etc/passwd', b'x')])[0],
                'a parent name': archive_bytes(extra_members=[('../manifest.json', b'[]')])[0],
                'a legacy layer directory': archive_bytes(extra_members=[('0123/layer.tar', b'x')])[0],
                'another directory': archive_bytes(extra_members=[('blobs/sha512', DIRECTORY)])[0],
                'a short blob name': archive_bytes(extra_members=[('blobs/sha256/abc', b'x')])[0],
                'a symlink': archive_bytes(extra_members=[('index.json.link', SYMLINK)])[0],
                'a link named like a blob': archive_bytes(extra_members=[('blobs/sha256/' + 'b' * 64, HARDLINK)])[0],
                'a symlink named like a blob': archive_bytes(extra_members=[('blobs/sha256/' + 'e' * 64, SYMLINK)])[0],
                'a device': archive_bytes(extra_members=[('oci-layout2', DEVICE)])[0],
                'a directory named like a file': archive_bytes(extra_members=[('index.json', DIRECTORY)])[0],
                'no manifest': archive_bytes(rename={'manifest.json': 'manifest.json.bak'})[0],
            }
            for name, archive in cases.items():
                with self.subTest(name), self.assertRaises(m.Closed):
                    check(archive)
            missing = archive_bytes(rename={'blobs/sha256/' + self.diff_ids[0][7:]: 'blobs/sha256/' + 'c' * 64})[0]
            with self.assertRaisesRegex(m.Closed, 'names a member the archive does not hold'):
                check(missing)
            with self.assertRaisesRegex(m.Closed, 'repeats the member manifest.json'):
                check(cases['manifest.json twice through ./'])

    def test_load_accepts_only_the_output_image_id(self):
        self.save()
        docker = self.fake(existing={'sha256:' + '9' * 64 + ' <none>:<none>'})
        self.assertEqual(self.load(docker), {'tag': TAG, 'image_id': self.image_id})
        image_ls = ['image', 'ls', '--all', '--no-trunc', '--format', '{{.ID}} {{.Repository}}:{{.Tag}}']
        self.assertEqual(docker.calls, [['image', 'inspect', TAG], image_ls,
                                        ['load', '--quiet', '--input', str(self.handoff / 'image.tar')], image_ls])

    def test_load_refusals(self):
        self.save()
        record = json.loads((self.handoff / 'handoff.json').read_text())
        other_id = 'sha256:' + 'c' * 64
        cases = [({'expected': 'sha256:short'}, 'EXPECTED_IMAGE_ID'), ({'expected': other_id}, 'handoff.json'),
                 ({'docker': self.fake(present=True)}, 'already exists'),
                 ({'docker': self.fake(load_rc=1)}, 'docker load failed'),
                 ({'docker': self.fake(loaded={self.image_id + ' ' + TAG, other_id + ' ' + TAG.replace(':', ':x')})},
                  'added something other'),
                 ({'docker': self.fake(loaded={self.image_id + ' local/mcp-odoo:latest'})}, 'added something other'),
                 ({'docker': self.fake(loaded={other_id + ' ' + TAG})}, 'added something other'),
                 ({'docker': self.fake(loaded=set())}, 'added something other'),
                 ({'loaded_id': other_id}, 'not the tested image ID'),
                 ({'loaded_layers': ['sha256:' + 'd' * 64]}, 'not the tested image ID')]
        for kwargs, message in cases:
            with self.subTest(message=message, kwargs=str(kwargs)[:60]), self.assertRaisesRegex(m.Closed, message):
                self.load(**kwargs)
        with self.assertRaisesRegex(m.Closed, 'EXPECTED_IMAGE_ID'):
            with patch.object(m, 'docker', side_effect=self.fake()):
                m.load(APP, self.handoff, self.evidence, env={})
        for change in ({'tag': 'local/mcp-odoo:latest'}, {'app': 'n8n'}, {'version': '9.9.9'}, {'extra': 1}):
            (self.handoff / 'handoff.json').write_text(json.dumps({**record, **change}))
            with self.subTest(record=change), self.assertRaisesRegex(m.Closed, 'handoff.json'):
                self.load()
        (self.handoff / 'handoff.json').write_text(json.dumps(record))
        for change in ({'image_id': other_id}, {'diff_ids': []}, {'source': 'b' * 40}, {'app': 'n8n'}):
            (self.candidate / 'subject.json').write_text(json.dumps({**self.subject, **change}))
            with self.subTest(subject=change), self.assertRaisesRegex(m.Closed, 'not the tested candidate'):
                self.load()
        (self.candidate / 'subject.json').write_text(json.dumps(self.subject))
        # Suggestion 4 of the review: the J1900 record must have passed for exactly this image ID before the push.
        for change in ({'passed': False}, {'passed': 'true'}, {'image_id': other_id}, {'app': 'n8n'}, {'version': '9.9.9'},
                       {'source': 'b' * 40}):
            self.j1900_path.write_text(json.dumps({**self.j1900, **change}))
            with self.subTest(j1900=change), self.assertRaisesRegex(m.Closed, 'J1900 record did not pass'):
                self.load()
        self.j1900_path.unlink()
        with self.assertRaisesRegex(m.Closed, 'J1900 record missing'):
            self.load()
        self.j1900_path.write_text(json.dumps(self.j1900))
        (self.handoff / 'image.tar').write_bytes(self.archive + b'\0' * 512)
        with self.assertRaisesRegex(m.Closed, 'SHA-256 differs'):
            self.load()
        other, _, _ = archive_bytes(config_extra={'invented': 'another image'})
        (self.handoff / 'image.tar').write_bytes(other)
        (self.handoff / 'handoff.json').write_text(json.dumps({**record, 'archive_sha256': hashlib.sha256(other).hexdigest()}))
        with self.assertRaisesRegex(m.Closed, 'config digest'):
            self.load()
        (self.handoff / 'image.tar').unlink()
        with self.assertRaisesRegex(m.Closed, 'archive missing'):
            self.load()
        (self.handoff / 'handoff.json').unlink()
        with self.assertRaisesRegex(m.Closed, 'handoff.json missing'):
            self.load()

    def test_the_handoff_writes_only_the_image_id_output(self):
        source = Path(m.__file__).read_text()
        for absent in ('GITHUB_ENV', 'GITHUB_PATH', 'GITHUB_TOKEN', 'GHCR_TOKEN', 'docker push', 'login'):
            self.assertNotIn(absent, source)
        self.assertEqual(source.count("stream.write('image_id=%s\\n' % image_id)"), 1)

    def test_main_usage(self):
        for argv in ([], ['save'], ['push', 'odoo', 'a', 'b'], ['load', 'odoo', 'a']):
            with self.subTest(argv=argv), self.assertRaisesRegex(m.Closed, 'usage'):
                m.main(argv)


if __name__ == '__main__':
    unittest.main()
