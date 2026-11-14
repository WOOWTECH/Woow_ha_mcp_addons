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
        for name in ('n8n', 'opendesign', 'headscale'):
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

    def test_unreleased_version_needs_its_own_decision_record(self):
        # HM-17: only the product's own record counts; a shared release-decision-<version>.md no longer does.
        fake = FakeRegistry()
        failures = g.check_decisions(self.found(), self.root, fetch=fake)
        self.assertEqual(len(failures), 1)
        self.assertIn('woow_mcp_n8n 0.3.0', failures[0])
        self.assertIn('release-decision-n8n-0.3.0.md', failures[0])
        (self.root / 'docs/operations/release-decision-0.3.0.md').write_text('# 0.3.0 release record\n')
        self.assertEqual(len(g.check_decisions(self.found(), self.root, fetch=fake)), 1)
        (self.root / 'docs/operations/release-decision-n8n-0.3.0.md').write_text('# woow_mcp_n8n 0.3.0 image decision\n')
        self.assertEqual(g.check_decisions(self.found(), self.root, fetch=fake), [])

    def test_another_products_record_never_counts(self):
        # R10 RG-12: Headscale's own line reused 0.4.14-0.4.18, so a record naming only the version let another product
        # pass with Headscale's record; and every product moves to 0.5.0 in its own release (DQ-32).
        both = g.components(registry(('n8n', True), ('headscale', True)), self.root)
        records = self.root / 'docs/operations'
        (records / 'release-decision-headscale-0.3.0.md').write_text(
            '# woow_mcp_headscale 0.3.0 image decision\n\nwoow_mcp_n8n follows at 0.3.0 in its own release.\n')
        failures = g.check_decisions(both, self.root, fetch=FakeRegistry())
        self.assertEqual(len(failures), 1)
        self.assertIn('woow_mcp_n8n 0.3.0', failures[0])
        # One shared record naming both slugs releases neither.
        (records / 'release-decision-headscale-0.3.0.md').unlink()
        (records / 'release-decision-0.3.0.md').write_text('# woow_mcp_n8n and woow_mcp_headscale 0.3.0 image decision\n')
        self.assertEqual(len(g.check_decisions(both, self.root, fetch=FakeRegistry())), 2)
        # A record under another product's name is not this product's, whatever it says.
        (records / 'release-decision-headscale-0.3.0.md').write_text('# woow_mcp_n8n 0.3.0 image decision\n')
        failures = g.check_decisions(both, self.root, fetch=FakeRegistry())
        self.assertEqual(len(failures), 2)

    def test_new_headscale_needs_its_own_decision_record(self):
        headscale = g.components(registry(('headscale', True)), self.root)
        other_record = self.root / 'docs/operations/release-decision-0.3.0.md'
        other_record.write_text('# 0.3.0: existing six images only\n')
        self.assertIn('woow_mcp_headscale 0.3.0',
                      g.check_decisions(headscale, self.root, fetch=FakeRegistry())[0])
        headscale_record = self.root / 'docs/operations/release-decision-headscale-0.3.0.md'
        headscale_record.write_text('# woow_mcp_headscale 0.3.0: accepted candidate image\n')
        self.assertEqual(g.check_decisions(headscale, self.root, fetch=FakeRegistry()), [])

    def test_released_version_needs_no_record(self):
        self.assertEqual(g.check_decisions(self.found(), self.root, fetch=FakeRegistry(released=['woow_mcp_n8n-v0.3.0'])), [])

    def test_record_must_name_the_slug_and_the_exact_version(self):
        record = self.root / 'docs/operations/release-decision-n8n-0.3.0.md'
        for text in ('woow_mcp_n8n 0.3.01 and 10.3.0 and 0.3.0.1\n', '# 0.3.0 image decision\n',
                     '# woow_mcp_n8n_pilot 0.3.0\n', '# xwoow_mcp_n8n 0.3.0\n', '# woow_mcp_headscale 0.3.0\n'):
            record.write_text(text)
            with self.subTest(text=text):
                self.assertIsNone(g.own_record('woow_mcp_n8n', '0.3.0', self.root))
        record.write_text('woow_mcp_n8n: upgrade to 0.3.0.\n')
        self.assertEqual(g.own_record('woow_mcp_n8n', '0.3.0', self.root), 'release-decision-n8n-0.3.0.md')
        record.unlink()
        record.mkdir()  # not a file
        self.assertIsNone(g.own_record('woow_mcp_n8n', '0.3.0', self.root))

    def test_the_record_is_named_after_the_add_on_directory(self):
        self.assertEqual(g.record_name('woow_mcp_headscale', '0.4.18'), 'release-decision-headscale-0.4.18.md')
        self.assertEqual(g.record_name('woow_mcp_odoo', '0.5.0'), 'release-decision-odoo-0.5.0.md')
        self.assertEqual(g.record_name('woow_mcp_odoo_manage', '0.1.5'), 'release-decision-odoo-manage-0.1.5.md')
        for slug, version in (('woow_mcp_n8n', '0.3'), ('woow_mcp_n8n', '0.3.0.1'), ('woow_mcp_n8n', '../0.3.0'),
                              ('woow_mcp_n8n', 'latest'), ('woow_mcp_n8n', ''), ('n8n', '0.3.0'), ('woow_mcp_', '0.3.0'),
                              ('woow_mcp_N8N', '0.3.0'), ('woow_mcp_n8n/../x', '0.3.0')):
            with self.subTest(slug=slug, version=version), self.assertRaises(g.Failed):
                g.record_name(slug, version)
        # The gate reports it instead of stopping: the other add-ons are still checked.
        (self.root / 'addons/n8n/config.yaml').write_text(
            'slug: woow_mcp_n8n\nversion: latest\narch: [amd64]\nimage: ghcr.io/woowtech/{arch}-mcp-n8n\n')
        both = g.components(registry(('n8n', True), ('headscale', True)), self.root)
        failures = g.check_decisions(both, self.root, fetch=FakeRegistry())
        self.assertEqual(len(failures), 2)
        self.assertIn('woow_mcp_n8n latest', failures[0])

    def test_the_repository_records_follow_the_rule(self):
        # Headscale's records already have the product's own form; the versions they name release no other product.
        records = sorted((g.ROOT / 'docs/operations').glob('release-decision-headscale-*.md'))
        self.assertTrue(records)
        others = ('woow_mcp_odoo', 'woow_mcp_n8n', 'woow_mcp_hermes', 'woow_mcp_opendesign', 'woow_mcp_emqx',
                  'woow_mcp_litellm', 'woow_mcp_nextcloud')
        for path in records:
            version = path.name[len('release-decision-headscale-'):-len('.md')]
            with self.subTest(record=path.name):
                self.assertEqual(g.own_record('woow_mcp_headscale', version, g.ROOT), path.name)
                self.assertEqual([slug for slug in others if g.own_record(slug, version, g.ROOT)], [])


if __name__ == '__main__':
    unittest.main()
