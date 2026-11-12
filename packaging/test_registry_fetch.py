"""Offline registry_fetch tests with a scripted fake registry. No network."""
import base64
import email.message
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import registry_fetch as r

HOST = 'git-prod.example.invalid'
REPO = 'ha-components/pilot-0123456789ab/amd64-mcp-n8n'
REF = '%s/%s:0.1.0' % (HOST, REPO)


def sha(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def headers(values):
    message = email.message.Message()
    for key, value in values.items():
        message[key] = value
    return message


class Response(io.BytesIO):
    def __init__(self, body, hdrs=None):
        super().__init__(body)
        self.headers = headers(hdrs or {})


class FakeRegistry:
    def __init__(self, tamper=None):
        self.config = json.dumps({'rootfs': {'type': 'layers', 'diff_ids': [sha(b'tar')]}}).encode()
        self.layer = b'compressed-layer'
        self.manifest = json.dumps({'schemaVersion': 2,
            'mediaType': 'application/vnd.docker.distribution.manifest.v2+json',
            'config': {'digest': sha(self.config), 'size': len(self.config)},
            'layers': [{'digest': sha(self.layer), 'size': len(self.layer)}]}).encode()
        self.tamper = tamper
        self.calls = []

    def open(self, request, timeout=None):
        url, sent = request.full_url, dict(request.header_items())
        self.calls.append((url, sent))
        base = 'https://%s/v2/%s' % (HOST, REPO)
        if url == 'https://%s/v2/' % HOST:
            realm = 'https://%s/v2/token' % (HOST if self.tamper != 'realm' else 'evil.invalid')
            raise urllib.error.HTTPError(url, 401, 'auth', headers(
                {'WWW-Authenticate': 'Bearer realm="%s",service="container_registry",scope="*"' % realm}), None)
        if url.startswith('https://%s/v2/token?' % HOST):
            expected = 'Basic ' + base64.b64encode(b'pilot-reader:tok-123').decode()
            assert sent.get('Authorization') == expected, 'basic auth missing'
            return Response(json.dumps({'token': 'BEARER-1'}).encode())
        if url == base + '/manifests/0.1.0':
            assert sent.get('Authorization') == 'Bearer BEARER-1'
            digest = sha(self.manifest) if self.tamper != 'manifest' else sha(b'other')
            return Response(self.manifest, {'Docker-Content-Digest': digest})
        if url == base + '/blobs/' + sha(self.config):
            return Response(self.config if self.tamper != 'config' else b'{}')
        if url == base + '/blobs/' + sha(self.layer):
            raise urllib.error.HTTPError(url, 307, 'redirect', headers(
                {'Location': 'https://storage.example.invalid/blob?sig=x'}), None)
        if url.startswith('https://storage.example.invalid/'):
            return Response(self.layer if self.tamper != 'layer' else b'xx')
        raise AssertionError('unexpected url ' + url)


class RegistryFetchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cred = self.dir / 'cred'
        self.cred.write_text('pilot-reader\ntok-123\n')
        os.chmod(self.cred, 0o600)

    def tearDown(self):
        self.tmp.cleanup()

    def run_fetch(self, fake, out='out', **kw):
        with patch.object(r, 'OPENER', fake):
            return r.fetch(REF, self.cred, self.dir / out, **kw)

    def test_fetch_verifies_everything_and_drops_auth_off_host(self):
        fake = FakeRegistry()
        summary = self.run_fetch(fake)
        self.assertEqual(summary['manifest_digest'], sha(fake.manifest))
        self.assertEqual(summary['layers'], [{'digest': sha(fake.layer), 'evidence': 'bytes-verified'}])
        out = self.dir / 'out'
        self.assertEqual((out / 'manifest.bin').read_bytes(), fake.manifest)
        self.assertEqual((out / 'config.bin').read_bytes(), fake.config)
        self.assertEqual((out / 'blobs' / sha(fake.layer).split(':')[1]).read_bytes(), fake.layer)
        storage = [sent for url, sent in fake.calls if 'storage.example.invalid' in url]
        self.assertTrue(storage and all('Authorization' not in sent for sent in storage))
        text = ''.join(p.read_text(errors='ignore') for p in out.rglob('*') if p.is_file())
        self.assertNotIn('tok-123', text)
        self.assertNotIn('BEARER-1', text)

    def test_metadata_only_skips_blob_bytes(self):
        summary = self.run_fetch(FakeRegistry(), metadata_only=True)
        self.assertEqual(summary['layers'][0]['evidence'], 'metadata-only')
        self.assertFalse((self.dir / 'out' / 'blobs').exists())

    def test_tampering_and_bad_inputs_fail_closed(self):
        for tamper in ('manifest', 'config', 'layer', 'realm'):
            with self.subTest(tamper=tamper), self.assertRaises(ValueError):
                self.run_fetch(FakeRegistry(tamper), out='out-' + tamper)
        self.run_fetch(FakeRegistry(), out='exists')
        with self.assertRaises(FileExistsError):
            self.run_fetch(FakeRegistry(), out='exists')  # never reuse an earlier output
        os.chmod(self.cred, 0o644)
        with self.assertRaisesRegex(ValueError, '0600'):
            self.run_fetch(FakeRegistry(), out='perm')
        os.chmod(self.cred, 0o600)
        with patch.object(r, 'OPENER', FakeRegistry()), self.assertRaises(ValueError):
            r.fetch('http://%s/%s:0.1.0' % (HOST, REPO), self.cred, self.dir / 'bad-ref')
        with self.assertRaises(ValueError):
            r.request('http://%s/v2/' % HOST, {}, HOST)


if __name__ == '__main__':
    unittest.main()
