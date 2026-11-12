"""Offline pilot-variant tests: real public manifests, owned throwaway candidate repos. No network/HA."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import pilot_variant as p
from validate import PRODUCTS, ROOT, load

SHA = 'a' * 40
REG = 'registry.example.invalid/woow'


def candidate(base):
    """A clean git checkout holding a copy of the real addons/ tree; returns (root, head, tree)."""
    root = Path(base) / 'candidate'
    shutil.copytree(ROOT / 'addons', root / 'addons')
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(base), 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
           'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.invalid',
           'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.invalid'}
    run = lambda *a: subprocess.run(['git', *a], cwd=root, env=env, check=True, capture_output=True, text=True).stdout
    run('init', '-q')
    run('add', '-A')
    run('commit', '-qm', 'c')
    return root, run('rev-parse', 'HEAD').strip(), run('rev-parse', 'HEAD^{tree}').strip()


class PilotVariantTests(unittest.TestCase):
    def test_only_three_fields_change_for_every_product(self):
        for product in PRODUCTS:
            with self.subTest(product=product):
                public = load(ROOT / 'addons' / product / 'config.yaml')
                result = p.variant(public, product, SHA, REG)
                self.assertEqual(sorted(k for k in public if result[k] != public[k]), sorted(p.CHANGED))
                self.assertEqual(result['version'], public['version'])
                self.assertEqual(result['slug'], public['slug'] + '_pilot')
                self.assertEqual(result['image'], f'{REG}/pilot-aaaaaaaaaaaa/amd64-mcp-{product}')
                self.assertEqual(result['homeassistant_api'], public['homeassistant_api'])

    def test_generate_binds_verified_candidate_and_writes_fresh_tree(self):
        with tempfile.TemporaryDirectory() as d:
            root, head, tree = candidate(d)
            rec = Path(d) / 'source-receipt.json'
            rec.write_text(json.dumps({'commit': head, 'tree': tree}))
            out = Path(d) / 'out'
            receipt = p.generate(root, 'n8n', head, REG, out, rec)
            app = out / 'woow_mcp_n8n_pilot'
            self.assertEqual((receipt['commit'], receipt['tree'], receipt['source_receipt_bound']), (head, tree, True))
            self.assertEqual(receipt['installed_slug'], 'local_woow_mcp_n8n_pilot')
            self.assertEqual(receipt['source_files']['addons/n8n/config.yaml'], p.digest(root / 'addons/n8n/config.yaml'))
            self.assertEqual(load(app / 'config.yaml')['slug'], 'woow_mcp_n8n_pilot')
            self.assertEqual(set(receipt['files']), {str(f.relative_to(out)) for f in app.rglob('*') if f.is_file()})
            self.assertEqual((out / 'variant-receipt.json').stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                p.generate(root, 'n8n', head, REG, out)

    def test_candidate_binding_is_enforced(self):
        # Review F2: the commit must be the checkout actually read, clean, and match the receipt.
        with tempfile.TemporaryDirectory() as d:
            root, head, tree = candidate(d)
            with self.assertRaisesRegex(ValueError, 'HEAD differs'):
                p.generate(root, 'n8n', SHA, REG, Path(d) / 'o1')
            bad = Path(d) / 'bad-receipt.json'
            bad.write_text(json.dumps({'commit': head, 'tree': '0' * 40}))
            with self.assertRaisesRegex(ValueError, 'source receipt'):
                p.generate(root, 'n8n', head, REG, Path(d) / 'o2', bad)
            (root / 'addons/n8n/config.yaml').write_text((root / 'addons/n8n/config.yaml').read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'not clean'):
                p.generate(root, 'n8n', head, REG, Path(d) / 'o3')
            for name in ('o1', 'o2', 'o3'):
                self.assertFalse((Path(d) / name).exists())

    def test_root_must_be_worktree_top_level(self):
        # Review N1: a subdirectory holding another valid addons/ tree must not be accepted as the root.
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / 'base'
            base.mkdir()
            shutil.copytree(ROOT / 'addons', base / 'export' / 'addons')
            root, head, _ = candidate(base)  # base/candidate is the repo; put export inside it and commit
            shutil.copytree(base / 'export', root / 'export')
            env = {'PATH': '/usr/bin:/bin', 'HOME': d, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
                   'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@x.invalid', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@x.invalid'}
            subprocess.run(['git', 'add', '-A'], cwd=root, env=env, check=True)
            subprocess.run(['git', 'commit', '-qm', 'export'], cwd=root, env=env, check=True)
            head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, env=env, check=True, capture_output=True, text=True).stdout.strip()
            with self.assertRaisesRegex(ValueError, 'top level'):
                p.generate(root / 'export', 'n8n', head, REG, Path(d) / 'out-sub')
            with self.assertRaisesRegex(ValueError, 'outside'):
                p.generate(root, 'n8n', head, REG, root / 'evidence')
            self.assertFalse((Path(d) / 'out-sub').exists())

    def test_ignored_files_are_never_consumed(self):
        # Review N2: sources are the commit's blobs; an ignored extra translation beside them is not read.
        with tempfile.TemporaryDirectory() as d:
            root, head, _ = candidate(d)
            (root / '.git' / 'info' / 'exclude').write_text('extra.yaml\n')
            extra = root / 'addons/n8n/translations/extra.yaml'
            extra.write_text((root / 'addons/n8n/translations/en.yaml').read_text())
            receipt = p.generate(root, 'n8n', head, REG, Path(d) / 'out')
            self.assertNotIn('addons/n8n/translations/extra.yaml', receipt['source_files'])
            self.assertFalse((Path(d) / 'out/woow_mcp_n8n_pilot/translations/extra.yaml').exists())
            self.assertEqual(sorted(receipt['source_files']),
                             ['addons/n8n/config.yaml', 'addons/n8n/translations/en.yaml', 'addons/n8n/translations/zh-Hant.yaml'])

    def test_output_must_be_outside_candidate_and_tool_repo(self):
        # Review F1: including via a parent symlink that points back into the checkout.
        with tempfile.TemporaryDirectory() as d:
            root, head, _ = candidate(d)
            link = Path(d) / 'sneaky'
            link.symlink_to(root / 'addons')
            for out in (root / 'addons' / 'pilot-evidence', root / 'evidence', link / 'x', ROOT / 'pilot-evidence-test'):
                with self.subTest(out=str(out)), self.assertRaisesRegex(ValueError, 'outside'):
                    p.generate(root, 'n8n', head, REG, out)
            self.assertFalse((root / 'addons' / 'pilot-evidence').exists())
            self.assertFalse((root / 'addons' / 'x').exists())
            self.assertFalse((ROOT / 'pilot-evidence-test').exists())

    def test_rejections(self):
        public = load(ROOT / 'addons/n8n/config.yaml')
        for registry in ('', 'Registry.example/woow', 'https://r.example/woow', 'r.example/woow:1',
                         'r.example/woow@sha256:' + 'a' * 64, 'r.example', 'r.example/woow/', '../x/y'):
            with self.subTest(registry=registry), self.assertRaises(ValueError):
                p.variant(public, 'n8n', SHA, registry)
        for commit in ('', 'a' * 12, 'A' * 40, 'g' * 40):
            with self.subTest(commit=commit), self.assertRaises(ValueError):
                p.variant(public, 'n8n', commit, REG)
        with self.assertRaises(ValueError):
            p.variant(public, 'kubernetes', SHA, REG)
        with self.assertRaises(Exception):
            p.variant(dict(public, hassio_api=True), 'n8n', SHA, REG)  # never derive from an invalid manifest


if __name__ == '__main__':
    unittest.main()
