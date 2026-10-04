"""Offline pilot-variant tests against the real public manifests. No network/HA."""
import json
from pathlib import Path
import tempfile
import unittest

import pilot_variant as p
from validate import PRODUCTS, ROOT, load

SHA = 'a' * 40
REG = 'registry.example.invalid/woow'


class PilotVariantTests(unittest.TestCase):
    def test_only_three_fields_change_for_every_product(self):
        for product in PRODUCTS:
            with self.subTest(product=product):
                public = load(ROOT / 'addons' / product / 'config.yaml')
                result = p.variant(public, product, SHA, REG)
                changed = sorted(k for k in public if result[k] != public[k])
                self.assertEqual(changed, sorted(p.CHANGED))
                self.assertEqual(result['version'], public['version'])
                self.assertEqual(result['slug'], public['slug'] + '_pilot')
                self.assertEqual(result['image'], f'{REG}/pilot-aaaaaaaaaaaa/amd64-mcp-{product}')
                self.assertEqual(result['homeassistant_api'], public['homeassistant_api'])

    def test_generate_writes_fresh_tree_and_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'out'
            receipt = p.generate('n8n', SHA, REG, out)
            app = out / 'woow_mcp_n8n_pilot'
            self.assertEqual(receipt['installed_slug'], 'local_woow_mcp_n8n_pilot')
            self.assertEqual(load(app / 'config.yaml')['slug'], 'woow_mcp_n8n_pilot')
            self.assertEqual((app / 'translations' / 'en.yaml').read_bytes(),
                             (ROOT / 'addons/n8n/translations/en.yaml').read_bytes())
            self.assertEqual(set(receipt['files']), {str(f.relative_to(out)) for f in app.rglob('*') if f.is_file()})
            self.assertEqual(json.loads((out / 'variant-receipt.json').read_text()), receipt)
            self.assertEqual((out / 'variant-receipt.json').stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                p.generate('n8n', SHA, REG, out)

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
        tampered = dict(public, hassio_api=True)
        with self.assertRaises(Exception):
            p.variant(tampered, 'n8n', SHA, REG)  # never derive from an invalid public manifest


if __name__ == '__main__':
    unittest.main()
