"""Offline delivery-receipt tests with synthetic gzip layers (compressed digest != DiffID)."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import delivery_receipt as d


def sha(b):
    return 'sha256:' + hashlib.sha256(b).hexdigest()


def fixture(layer_count=2):
    raws, blobs = [], []
    for i in range(layer_count):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w') as tar:
            info = tarfile.TarInfo('f%d' % i)
            data = ('layer %d' % i).encode()
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        raws.append(buf.getvalue())
        blobs.append(gzip.compress(buf.getvalue(), mtime=0))
    config = json.dumps({'architecture': 'amd64', 'os': 'linux',
                         'rootfs': {'type': 'layers', 'diff_ids': [sha(r) for r in raws]}}).encode()
    manifest = json.dumps({'schemaVersion': 2, 'mediaType': d.MANIFEST_TYPES[0],
                           'config': {'mediaType': 'application/vnd.oci.image.config.v1+json',
                                      'digest': sha(config), 'size': len(config)},
                           'layers': [{'mediaType': 'application/vnd.oci.image.layer.v1.tar+gzip',
                                       'digest': sha(b), 'size': len(b)} for b in blobs]}).encode()
    subject = {'app': 'n8n', 'source': 'c' * 40, 'image_id': sha(config), 'diff_ids': [sha(r) for r in raws]}
    return manifest, config, subject, blobs


class DeliveryReceiptTests(unittest.TestCase):
    def test_bytes_verified_and_metadata_only_grading(self):
        manifest, config, subject, blobs = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / sha(blobs[0]).split(':')[1]).write_bytes(blobs[0])  # only first blob fetched
            r = d.check(sha(manifest), manifest, config, subject, tmp)
        self.assertEqual([l['evidence'] for l in r['layers']], ['bytes-verified', 'metadata-only'])
        self.assertFalse(r['all_layers_bytes_verified'])
        self.assertEqual((r['kind'], r['complete_delivery_receipt']), ('registry-digest-subevidence', False))
        self.assertIn('NOT ESTABLISHED', r['runtime_identity_in_ha'])
        self.assertNotEqual([l['digest'] for l in r['layers']], subject['diff_ids'])

    def test_identity_contract_per_image_store(self):
        manifest, config, subject, _ = fixture()
        m, c = sha(manifest), sha(config)
        self.assertEqual(d.check(m, manifest, config, subject)['store_source'], 'inferred')
        ok = [dict(subject, image_store='classic'), dict(subject, image_store='containerd', image_id=m),
              dict(subject, image_store='containerd', image_id=m, config_digest=c),
              dict(subject, image_store='classic', config_digest=c)]
        for s in ok:
            with self.subTest(ok=s.get('image_store')):
                r = d.check(m, manifest, config, s)
                self.assertEqual(r['store_source'], 'declared' if 'image_store' in s else 'inferred')
        # Review F3: a correct config_digest must NOT short-circuit a contradicting image_id.
        bad = [dict(subject, config_digest=c, image_id=sha(b'other round')),
               dict(subject, image_store='classic', image_id=m),
               dict(subject, image_store='containerd'),
               dict(subject, image_store='containerd', image_id=m, config_digest=sha(b'x')),
               dict(subject, image_store='podman'),
               dict(subject, image_id='not-a-digest')]
        for s in bad:
            with self.subTest(bad=str(s)[:80]), self.assertRaises(ValueError):
                d.check(m, manifest, config, s)

    def test_mismatches_fail_closed(self):
        manifest, config, subject, blobs = fixture()
        good = sha(manifest)
        cases = {
            'manifest digest': (sha(b'x'), manifest, config, subject),
            'diff ids': (good, manifest, config, dict(subject, diff_ids=subject['diff_ids'][::-1])),
            'diff ids vs layer digests': (good, manifest, config,
                                          dict(subject, diff_ids=[l['digest'] for l in json.loads(manifest)['layers']])),
            'config blob': (good, manifest, config + b' ', subject),
        }
        for name, args in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                d.check(*args)
        index = json.dumps({'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.index.v1+json',
                            'manifests': []}).encode()
        with self.assertRaisesRegex(ValueError, 'single-platform'):
            d.check(sha(index), index, config, subject)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / sha(blobs[1]).split(':')[1]).write_bytes(blobs[0])
            with self.assertRaisesRegex(ValueError, 'blob bytes'):
                d.check(good, manifest, config, subject, tmp)

    def test_assemble_binds_one_round_and_rejects_mixing(self):
        # Review F4: the complete receipt binds source/variant/subject/ref/sub-evidence of ONE round.
        manifest, config, subject, _ = fixture()
        sub = d.check(sha(manifest), manifest, config, dict(subject, image_store='classic'))
        source = {'commit': 'c' * 40, 'tree': 't' * 40, 'sha256': 'f' * 64}
        variant = {'commit': 'c' * 40, 'tree': 't' * 40, 'product': 'n8n', 'image': 'r.example/w/pilot-cccccccccccc/amd64-mcp-n8n',
                   'version': '0.1.0', 'installed_slug': 'local_woow_mcp_n8n_pilot',
                   'files': {'woow_mcp_n8n_pilot/config.yaml': '1' * 64, 'woow_mcp_n8n_pilot/README.md': '2' * 64}}
        ref = variant['image'] + ':0.1.0'
        r = d.assemble(source, variant, subject, sub, ref)
        self.assertTrue(r['complete_delivery_receipt'])
        self.assertEqual((r['commit'], r['variant_config_sha256'], r['image_store']), ('c' * 40, '1' * 64, 'classic'))
        other_manifest, other_config, other_subject, _ = fixture(3)
        other_sub = d.check(sha(other_manifest), other_manifest, other_config, other_subject)
        mixes = {
            'variant from other commit': (source, dict(variant, commit='d' * 40), subject, sub, ref),
            'variant from other tree': (source, dict(variant, tree='e' * 40), subject, sub, ref),
            'subject from other commit': (source, variant, dict(subject, source='d' * 40), sub, ref),
            'subject other product': (source, variant, dict(subject, app='odoo'), sub, ref),
            'ref not variant image': (source, variant, subject, sub, 'r.example/w/other/amd64-mcp-n8n:0.1.0'),
            'sub-evidence of other round': (source, variant, subject, other_sub, ref),
            'not sub-evidence': (source, variant, subject, dict(sub, kind='pilot-delivery-receipt'), ref),
            # Review N3: same image_id/DiffIDs but contradicting explicit identity fields.
            'subject config_digest conflicts': (source, variant, dict(subject, config_digest=sha(b'other')), sub, ref),
            'subject declares containerd': (source, variant, dict(subject, image_store='containerd'), sub, ref),
        }
        for name, args in mixes.items():
            with self.subTest(name), self.assertRaises(ValueError):
                d.assemble(*args)


if __name__ == '__main__':
    unittest.main()
