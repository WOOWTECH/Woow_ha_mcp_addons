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
    subject = {'image_id': sha(config), 'diff_ids': [sha(r) for r in raws]}
    return manifest, config, subject, blobs


class DeliveryReceiptTests(unittest.TestCase):
    def test_bytes_verified_and_metadata_only_grading(self):
        manifest, config, subject, blobs = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / sha(blobs[0]).split(':')[1]).write_bytes(blobs[0])  # only first blob fetched
            r = d.check(sha(manifest), manifest, config, subject, tmp)
        self.assertEqual([l['evidence'] for l in r['layers']], ['bytes-verified', 'metadata-only'])
        self.assertFalse(r['all_layers_bytes_verified'])
        self.assertIn('NOT ESTABLISHED', r['runtime_identity_in_ha'])
        # The two hash kinds really differ, and the tool never equates them.
        self.assertNotEqual([l['digest'] for l in r['layers']], subject['diff_ids'])

    def test_identity_binding_is_explicit_for_both_image_stores(self):
        manifest, config, subject, _ = fixture()
        classic = d.check(sha(manifest), manifest, config, subject)
        self.assertIn('classic', classic['tested_identity_binding'])
        # Docker 29 containerd image store: inspect .Id is the manifest digest (observed on the builder VM).
        containerd = d.check(sha(manifest), manifest, config, dict(subject, image_id=sha(manifest)))
        self.assertIn('containerd', containerd['tested_identity_binding'])
        explicit = d.check(sha(manifest), manifest, config, dict(subject, image_id=sha(manifest), config_digest=sha(config)))
        self.assertEqual(explicit['tested_identity_binding'], 'config_digest')

    def test_mismatches_fail_closed(self):
        manifest, config, subject, blobs = fixture()
        good = sha(manifest)
        cases = {
            'manifest digest': (sha(b'x'), manifest, config, subject),
            'tested id': (good, manifest, config, dict(subject, image_id=sha(b'other'))),
            'diff ids': (good, manifest, config, dict(subject, diff_ids=subject['diff_ids'][::-1])),
            'diff ids vs layer digests': (good, manifest, config,
                                          dict(subject, diff_ids=[l['digest'] for l in json.loads(manifest)['layers']])),
            'config blob': (good, manifest, config + b' ', subject),
        }
        for name, args in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                d.check(*args)
        with self.assertRaises(ValueError):
            d.check(good, manifest, config, dict(subject, config_digest=sha(b'other')))
        index = json.dumps({'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.index.v1+json',
                            'manifests': []}).encode()
        with self.assertRaisesRegex(ValueError, 'single-platform'):
            d.check(sha(index), index, config, subject)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / sha(blobs[1]).split(':')[1]).write_bytes(blobs[0])  # wrong bytes under the name
            with self.assertRaisesRegex(ValueError, 'blob bytes'):
                d.check(good, manifest, config, subject, tmp)


if __name__ == '__main__':
    unittest.main()
