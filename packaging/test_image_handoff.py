"""image_handoff.py with owned fake docker save archives and a fake Docker: no daemon, image or registry."""
import hashlib
import io
import json
import os
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


def archive_bytes(tag=TAG, layers=(b'layer one', b'layer two'), images=1, config_extra=None):
    """A docker-save-shaped archive; returns (bytes, image_id, diff_ids)."""
    diff_ids = ['sha256:' + hashlib.sha256(layer).hexdigest() for layer in layers]
    config = json.dumps({'architecture': 'amd64', 'os': 'linux', 'rootfs': {'type': 'layers', 'diff_ids': diff_ids},
                         **(config_extra or {})}).encode()
    image_id = 'sha256:' + hashlib.sha256(config).hexdigest()
    entry = {'Config': 'blobs/sha256/' + image_id[7:], 'RepoTags': [tag],
             'Layers': ['blobs/sha256/' + d[7:] for d in diff_ids]}
    members = [('manifest.json', json.dumps([entry] * images).encode()), (entry['Config'], config)]
    members += [(name, layer) for name, layer in zip(entry['Layers'], layers)]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as tar:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue(), image_id, diff_ids


class FakeDocker:
    """`image save` writes the owned archive, `load` marks the tag as present with `loaded` (Id, Layers)."""

    def __init__(self, archive, present=False, load_rc=0, save_rc=0, loaded=None):
        self.archive, self.present, self.load_rc, self.save_rc = archive, present, load_rc, save_rc
        self.loaded, self.calls = loaded, []

    def __call__(self, argv, timeout=1800):
        self.calls.append(list(argv))
        if argv[:2] == ['image', 'save']:
            Path(argv[3]).write_bytes(self.archive)
            return types.SimpleNamespace(returncode=self.save_rc)
        if argv[:2] == ['image', 'inspect']:
            return types.SimpleNamespace(returncode=0 if self.present else 1)
        if argv[0] == 'load':
            self.present = self.load_rc == 0
            return types.SimpleNamespace(returncode=self.load_rc)
        raise AssertionError(argv)


class ImageHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.archive, self.image_id, self.diff_ids = archive_bytes()
        self.subject = {'app': APP, 'source': 'a' * 40, 'image_id': self.image_id, 'diff_ids': self.diff_ids,
                        'archive_sha256': '0' * 64}
        self.candidate = self.base / 'candidate'
        self.candidate.mkdir()
        (self.candidate / 'subject.json').write_text(json.dumps(self.subject))
        self.handoff = self.base / 'handoff'
        self.output = self.base / 'github-output'
        self.output.write_text('')

    def tearDown(self):
        self.temporary.cleanup()

    def save(self, docker=None, inspect_id=None, env=None, verify=None):
        docker = docker or FakeDocker(self.archive)
        metadata = {'Id': inspect_id or self.image_id, 'RootFS': {'Layers': self.diff_ids}}
        with patch.object(m, 'docker', side_effect=docker), patch.object(m, 'inspect_image', return_value=metadata), \
             patch.object(m, 'verify_current', side_effect=verify or (lambda app, candidate: self.subject)):
            return m.save(APP, self.candidate, self.handoff, env={'GITHUB_OUTPUT': str(self.output)} if env is None else env)

    def load(self, docker=None, expected=None, loaded_id=None, loaded_layers=None):
        docker = docker or FakeDocker(self.archive)
        metadata = {'Id': loaded_id or self.image_id, 'RootFS': {'Layers': loaded_layers or self.diff_ids}}
        with patch.object(m, 'docker', side_effect=docker), patch.object(m, 'inspect_image', return_value=metadata):
            return m.load(APP, self.handoff, self.candidate, env={'EXPECTED_IMAGE_ID': expected or self.image_id})

    def test_save_hands_over_exactly_the_tested_image_and_outputs_its_id(self):
        docker = FakeDocker(self.archive)
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
        other, other_id, _ = archive_bytes(config_extra={'invented': 'another image'})
        two, _, _ = archive_bytes(images=2)
        retagged, _, _ = archive_bytes(tag='local/mcp-odoo:latest')
        cases = [({'env': {}}, 'GITHUB_OUTPUT'),
                 ({'docker': FakeDocker(self.archive, save_rc=1)}, 'docker image save failed'),
                 ({'inspect_id': 'sha256:' + 'f' * 64}, 'no longer names the tested image'),
                 ({'docker': FakeDocker(other)}, 'config digest is not the tested image ID'),
                 ({'docker': FakeDocker(two)}, 'exactly one image'),
                 ({'docker': FakeDocker(retagged)}, 'not tagged ' + TAG),
                 ({'docker': FakeDocker(b'not a tar archive')}, 'not a docker save archive')]
        for kwargs, message in cases:
            shutil.rmtree(self.handoff, ignore_errors=True)
            self.output.write_text('')
            with self.subTest(message=message), self.assertRaisesRegex(m.Closed, message):
                self.save(**kwargs)
            self.assertEqual(self.output.read_text(), '')  # no job output for a refused handover
        shutil.rmtree(self.handoff, ignore_errors=True)
        docker = FakeDocker(self.archive)

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

    def test_load_accepts_only_the_output_image_id(self):
        self.save()
        docker = FakeDocker(self.archive)
        self.assertEqual(self.load(docker), {'tag': TAG, 'image_id': self.image_id})
        self.assertEqual(docker.calls, [['image', 'inspect', TAG], ['load', '--quiet', '--input', str(self.handoff / 'image.tar')]])

    def test_load_refusals(self):
        self.save()
        record = json.loads((self.handoff / 'handoff.json').read_text())
        other_id = 'sha256:' + 'c' * 64
        cases = [({'expected': 'sha256:short'}, 'EXPECTED_IMAGE_ID'), ({'expected': other_id}, 'handoff.json'),
                 ({'docker': FakeDocker(self.archive, present=True)}, 'already exists'),
                 ({'docker': FakeDocker(self.archive, load_rc=1)}, 'docker load failed'),
                 ({'loaded_id': other_id}, 'not the tested image ID'),
                 ({'loaded_layers': ['sha256:' + 'd' * 64]}, 'not the tested image ID')]
        for kwargs, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(m.Closed, message):
                self.load(**kwargs)
        with self.assertRaisesRegex(m.Closed, 'EXPECTED_IMAGE_ID'):
            with patch.object(m, 'docker', side_effect=FakeDocker(self.archive)):
                m.load(APP, self.handoff, self.candidate, env={})
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
