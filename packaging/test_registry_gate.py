"""Offline registry trust-chain tests. No network/auth/pull is performed."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import registry_gate as r


class RegistryTests(unittest.TestCase):
    def test_missing_evidence_denies_before_network(self):
        with patch.object(r, 'request') as request:
            with self.assertRaises(ValueError):
                r.main('public', 'n8n')
            request.assert_not_called()

    def test_remote_config_diffids_manifest_or_pull_failure_never_emits_receipt(self):
        subject = {'image_id': 'sha256:' + 'a' * 64, 'diff_ids': ['sha256:' + 'b' * 64]}
        for problem in ('manifest', 'config', 'diffids', 'pulled_id', 'pull_error'):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as d:
                directory = Path(d)
                manifest = {'schemaVersion': 2, 'config': {'digest': subject['image_id']},
                            'layers': [{'digest': 'sha256:' + 'c' * 64}]}
                if problem == 'config':
                    manifest['config']['digest'] = 'sha256:' + 'f' * 64
                raw = json.dumps(manifest).encode()
                digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
                if problem == 'manifest':
                    digest = 'sha256:' + 'f' * 64
                response = io.BytesIO(raw)
                response.headers = {'Docker-Content-Digest': digest}
                reference = 'ghcr.io/woowtech/amd64-mcp-n8n@' + digest
                pulled = {'Id': subject['image_id'], 'RootFS': {'Layers': subject['diff_ids']},
                          'RepoDigests': [reference]}
                if problem == 'diffids':
                    pulled['RootFS'] = {'Layers': []}
                if problem == 'pulled_id':
                    pulled['Id'] = 'sha256:' + 'f' * 64
                def pull(*args, **kwargs):
                    if problem == 'pull_error':
                        raise OSError('invented offline pull failure')
                with patch.object(r, 'verify_current', return_value=subject), \
                     patch.object(r, 'request', side_effect=[io.BytesIO(b'{"token":"INVENTED-PUBLIC-CHALLENGE"}'), response]), \
                     patch.object(r.subprocess, 'run', side_effect=pull), \
                     patch.object(r.subprocess, 'check_output', return_value=json.dumps([pulled]).encode()):
                    with self.assertRaises((ValueError, OSError)):
                        r.main('public', 'n8n', directory)
                self.assertFalse((directory / 'published-provenance.json').exists())
                self.assertFalse((directory / 'published-digest.json').exists())
