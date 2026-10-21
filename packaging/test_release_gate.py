"""Offline release_gate tests with a scripted fake GHCR/GitHub. No network."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error

import release_gate as g


def sha(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def http_error(code):
    return urllib.error.HTTPError('https://example.invalid', code, 'error', {}, io.BytesIO(b''))


def registry(*entries):
    return {'providers': {g.REPOSITORY: {'components': [
        dict({'source_path': 'addons/' + name, 'config_file': 'config.yaml', 'channel': 'stable'}, id='woow_mcp_' + name, enabled=enabled)
        for name, enabled in entries]}}}


class FakeRegistry:
    """GHCR with one image index per reference; GitHub with a set of stable Release tags."""

    def __init__(self, images=(), released=(), arch='amd64'):
        self.objects = {}
        self.tags = {}
        self.released = set(released)
        for reference in images:
            config = json.dumps({'os': 'linux', 'architecture': arch}).encode()
            manifest = json.dumps({'config': {'digest': sha(config)}}).encode()
            index = json.dumps({'manifests': [{'digest': sha(manifest), 'platform': {'os': 'linux', 'architecture': arch}}]}).encode()
            repo, tag = reference[len('ghcr.io/'):].rsplit(':', 1)
            self.tags[(repo, tag)] = index
            self.objects[(repo, sha(manifest))] = manifest
            self.objects[(repo, sha(config))] = config

    def __call__(self, url, headers=None):
        if url.startswith('https://ghcr.io/token'):
            return b'{"token": "anonymous"}'
        if url.startswith('https://api.github.com/'):
            tag = url.rsplit('/', 1)[1]
            if tag not in self.released:
                raise http_error(404)
            return json.dumps({'tag_name': tag, 'draft': False, 'prerelease': False}).encode()
        assert headers['Authorization'] == 'Bearer anonymous'
        repo, kind, ref = url[len('https://ghcr.io/v2/'):].rsplit('/', 2)
        data = self.tags.get((repo, ref)) if kind == 'manifests' and not ref.startswith('sha256:') else self.objects.get((repo, ref))
        if data is None:
            raise http_error(404)
        return data


class ReleaseGateTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        for name in ('n8n', 'opendesign'):
            path = self.root / 'addons' / name
            path.mkdir(parents=True)
            (path / 'config.yaml').write_text(
                f'slug: woow_mcp_{name}\nversion: 0.3.0\narch: [amd64]\nimage: ghcr.io/woowtech/{{arch}}-mcp-{name}\n')
        (self.root / 'docs/operations').mkdir(parents=True)

    def tearDown(self):
        self.directory.cleanup()

    def found(self):
        return g.components(registry(('n8n', True), ('opendesign', False)), self.root)

    def test_disabled_components_are_ignored(self):
        self.assertEqual([slug for slug, _, _ in self.found()], ['woow_mcp_n8n'])

    def test_slug_mismatch_fails(self):
        (self.root / 'addons/n8n/config.yaml').write_text('slug: other\nversion: 0.3.0\n')
        with self.assertRaises(g.Failed):
            self.found()

    def test_image_present_passes_missing_fails(self):
        self.assertEqual(g.check_images(self.found(), fetch=FakeRegistry(['ghcr.io/woowtech/amd64-mcp-n8n:0.3.0'])), [])
        failures = g.check_images(self.found(), fetch=FakeRegistry(['ghcr.io/woowtech/amd64-mcp-n8n:0.2.9']))
        self.assertEqual(len(failures), 1)
        self.assertIn('HTTP 404', failures[0])

    def test_wrong_architecture_fails(self):
        fake = FakeRegistry(['ghcr.io/woowtech/amd64-mcp-n8n:0.3.0'], arch='arm64')
        self.assertIn('no linux/amd64', g.check_images(self.found(), fetch=fake)[0])

    def test_unreleased_version_needs_a_decision_record(self):
        fake = FakeRegistry()
        self.assertEqual(len(g.check_decisions(self.found(), self.root, fetch=fake)), 1)
        (self.root / 'docs/operations/release-decision-0.3.0.md').write_text('# 0.3.0 release record\n')
        self.assertEqual(g.check_decisions(self.found(), self.root, fetch=fake), [])

    def test_released_version_needs_no_record(self):
        self.assertEqual(g.check_decisions(self.found(), self.root, fetch=FakeRegistry(released=['woow_mcp_n8n-v0.3.0'])), [])

    def test_record_must_name_the_exact_version(self):
        (self.root / 'docs/operations/release-decision-0.3.01.md').write_text('0.3.01 and 10.3.0 and 0.3.0.1\n')
        self.assertEqual(g.decision_records('0.3.0', self.root), [])
        (self.root / 'docs/operations/release-decision-x.md').write_text('upgrade to 0.3.0.\n')
        self.assertEqual(g.decision_records('0.3.0', self.root), ['release-decision-x.md'])


if __name__ == '__main__':
    unittest.main()
