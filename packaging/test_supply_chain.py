"""Offline evidence validator negatives, NOT scanner/image success fixtures."""
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import supply_chain as s


class SupplyChainTests(unittest.TestCase):
    def test_policy_unknown_missing_and_high_vulnerabilities_deny(self):
        sbom = {'artifacts': [{'name': 'fixture', 'licenses': [{'value': 'MIT'}]}]}
        report = {'matches': [], 'descriptor': {'name': 'grype', 'version': s.pins()['grype']['version'],
                  'db': {'schemaVersion': '6.0.2', 'checksum': 'a' * 64, 'error': '',
                         'built': datetime.now(timezone.utc).isoformat()}}}
        s.enforce_policy(sbom, report)
        for severity in ('High', 'Critical', 'Unknown', '', 'invented'):
            bad = copy.deepcopy(report)
            bad['matches'] = [{'vulnerability': {'severity': severity, 'fix': {'state': 'fixed'}}}]
            with self.subTest(severity=severity), self.assertRaises(s.Closed):
                s.enforce_policy(sbom, bad)
        for value in ('NOASSERTION', 'UNKNOWN', 'invented', ''):
            with self.subTest(license=value), self.assertRaises(s.Closed):
                s.enforce_policy({'artifacts': [{'licenses': [{'value': value}]}]}, report)
        for bad in ({}, {'artifacts': []}, {'artifacts': [{'licenses': []}]}):
            with self.assertRaises(s.Closed):
                s.enforce_policy(bad, report)
        for bad in ({}, {'matches': []}, {**report, 'descriptor': {'db': {'error': 'invalid'}}}):
            with self.assertRaises(s.Closed):
                s.enforce_policy(sbom, bad)

    def test_unfixed_vulnerability_policy_switch(self):
        sbom = {'artifacts': [{'name': 'fixture', 'licenses': [{'value': 'MIT'}]}]}
        report = {'matches': [], 'descriptor': {'name': 'grype', 'version': s.pins()['grype']['version'],
                  'db': {'schemaVersion': '6.0.2', 'checksum': 'a' * 64, 'error': '',
                         'built': datetime.now(timezone.utc).isoformat()}}}
        policy = json.loads((s.ROOT / 'packaging/supply-chain-policy.json').read_text())
        self.assertEqual(policy['unfixed_vulnerabilities'], 'exclude')  # owner decision 2026-10-05
        match = lambda sev, state: {'vulnerability': {'severity': sev, 'fix': {'state': state}}}
        real = s.read_json
        for mode, matches, ok in (
                ('include', [match('High', 'not-fixed')], False),
                ('exclude', [match('High', 'not-fixed'), match('Critical', 'wont-fix'), match('Unknown', 'unknown')], True),
                ('exclude', [match('Critical', 'fixed')], False),
                ('exclude', [match('High', 'fixed'), match('High', 'not-fixed')], False),
                ('exclude', [match('Medium', 'fixed')], True),
                ('exclude', [match('invented', 'not-fixed')], False),
                ('maybe', [], False)):
            doc = dict(policy, unfixed_vulnerabilities=mode)
            with self.subTest(mode=mode, matches=str(matches)[:60]), patch.object(
                    s, 'read_json', side_effect=lambda path: doc if path.name == 'supply-chain-policy.json' else real(path)):
                if ok:
                    s.enforce_policy(sbom, dict(report, matches=matches))
                else:
                    with self.assertRaises(s.Closed):
                        s.enforce_policy(sbom, dict(report, matches=matches))

    def test_optional_license_extensions_default_off(self):
        repo = json.loads((s.ROOT / 'packaging/supply-chain-policy.json').read_text())
        self.assertEqual((repo['debian_main_licenses'], repo['or_expressions']), ('accept', 'accept-if-any-allowed'))
        self.assertEqual(repo['known_binary_licenses'], {'python': 'PSF-2.0', 'node': 'MIT', 'Simple Launcher': 'PSF-2.0'})
        policy = {k: v for k, v in repo.items()
                  if k not in ('debian_main_licenses', 'or_expressions', 'known_binary_licenses', 'non_package_fixtures')}
        deb = {'type': 'deb', 'name': 'libc6'}
        npm = {'type': 'npm', 'name': 'x'}
        self.assertFalse(s.license_allowed(policy, deb, 'BSD-3-clause'))
        self.assertFalse(s.license_allowed(policy, npm, '(MIT OR WTFPL)'))
        self.assertEqual(s.known_binary_license(policy, {'type': 'binary', 'name': 'python'}), [])
        on = dict(policy, debian_main_licenses='accept', or_expressions='accept-if-any-allowed',
                  known_binary_licenses={'python': 'PSF-2.0'})
        self.assertTrue(s.license_allowed(on, deb, 'BSD-3-clause'))
        self.assertFalse(s.license_allowed(on, npm, 'BSD-3-clause'))  # deb rule never covers npm
        self.assertFalse(s.license_allowed(on, deb, ''))
        for value, ok in (('(MIT OR WTFPL)', True), ('(BSD-2-Clause OR MIT OR Apache-2.0)', True), ('MIT OR GPL-3.0', True),
                          ('(GPL-3.0 OR WTFPL)', False), ('(MIT AND GPL-3.0)', False), ('MIT WITH x', False),
                          ('(MIT OR (GPL-3.0 AND x))', False), ('OR', False)):
            with self.subTest(value=value):
                self.assertEqual(s.license_allowed(on, npm, value), ok)
        self.assertEqual(s.known_binary_license(on, {'type': 'binary', 'name': 'python'}), [{'value': 'PSF-2.0'}])
        self.assertEqual(s.known_binary_license(on, {'type': 'npm', 'name': 'python'}), [])
        real = s.read_json
        sbom = {'artifacts': [{'type': 'binary', 'name': 'python', 'licenses': []}]}
        report = {'matches': [], 'descriptor': {'name': 'grype', 'version': s.pins()['grype']['version'],
                  'db': {'schemaVersion': '6.0.2', 'checksum': 'a' * 64, 'error': '',
                         'built': datetime.now(timezone.utc).isoformat()}}}
        for doc, ok in ((policy, False), (on, True), (dict(on, known_binary_licenses={'python': 'GPL-3.0'}), False),
                        (dict(on, debian_main_licenses='maybe'), False)):
            with self.subTest(doc=str({k: doc.get(k) for k in ('debian_main_licenses', 'known_binary_licenses')})), patch.object(
                    s, 'read_json', side_effect=lambda path: doc if path.name == 'supply-chain-policy.json' else real(path)):
                if ok:
                    s.enforce_policy(sbom, report)
                else:
                    with self.assertRaises(s.Closed):
                        s.enforce_policy(sbom, report)

    def test_non_package_fixtures_are_exact_paths_only(self):
        fx = ['/opt/x/node_modules/a/example/package.json']
        self.assertTrue(s.is_listed_fixture(fx, {'locations': [{'path': fx[0]}]}))
        self.assertFalse(s.is_listed_fixture(fx, {'locations': [{'path': fx[0]}, {'path': '/opt/x/other/package.json'}]}))
        self.assertFalse(s.is_listed_fixture(fx, {'locations': []}))
        self.assertFalse(s.is_listed_fixture(fx, {}))
        self.assertFalse(s.is_listed_fixture([], {'locations': [{'path': fx[0]}]}))
        policy = json.loads((s.ROOT / 'packaging/supply-chain-policy.json').read_text())
        real = s.read_json
        sbom = {'artifacts': [{'type': 'npm', 'name': 'beep-boop', 'licenses': [], 'locations': [{'path': fx[0]}]},
                              {'type': 'npm', 'name': 'ok', 'licenses': [{'value': 'MIT'}]}]}
        report = {'matches': [], 'descriptor': {'name': 'grype', 'version': s.pins()['grype']['version'],
                  'db': {'schemaVersion': '6.0.2', 'checksum': 'a' * 64, 'error': '',
                         'built': datetime.now(timezone.utc).isoformat()}}}
        for doc, ok in ((dict(policy, non_package_fixtures=[]), False), (dict(policy, non_package_fixtures=fx), True),
                        (dict(policy, non_package_fixtures=['/opt/x/*']), False),
                        (dict(policy, non_package_fixtures=['relative/package.json']), False)):
            with self.subTest(fixtures=doc['non_package_fixtures']), patch.object(
                    s, 'read_json', side_effect=lambda path: doc if path.name == 'supply-chain-policy.json' else real(path)):
                if ok:
                    s.enforce_policy(sbom, report)
                else:
                    with self.assertRaises(s.Closed):
                        s.enforce_policy(sbom, report)

    def test_grype_0120_status_descriptor_is_normalised(self):
        sbom = {'artifacts': [{'name': 'fixture', 'licenses': [{'value': 'MIT'}]}]}
        built = datetime.now(timezone.utc).isoformat()
        status = {'schemaVersion': 'v6.1.10', 'built': built, 'valid': True,
                  'from': 'https://grype.anchore.io/databases/v6/db.tar.zst?checksum=sha256%3A' + 'b' * 64}
        report = {'matches': [], 'descriptor': {'name': 'grype', 'version': s.pins()['grype']['version'],
                  'db': {'status': status, 'providers': {}}}}
        s.enforce_policy(sbom, report)
        self.assertEqual(s.grype_db(report), {'schemaVersion': '6.1.10', 'built': built, 'checksum': 'b' * 64})
        for bad_status in (dict(status, valid=False), dict(status, schemaVersion='v5.0.0'),
                           dict(status, built='2000-01-01T00:00:00Z'), dict(status, error='x'),
                           dict(status, **{'from': 'https://x/db?checksum=sha256%3Azz'})):
            bad = copy.deepcopy(report)
            bad['descriptor']['db']['status'] = bad_status
            with self.subTest(status=str(bad_status)[:50]), self.assertRaises(s.Closed):
                s.enforce_policy(sbom, bad)

    def test_scanner_nonzero_and_missing_executable_deny_without_output(self):
        with self.assertRaises(s.Closed):
            s.run(['/bin/sh', '-c', 'echo INVENTED-SENSITIVE >&2; exit 2'])
        with self.assertRaises(s.Closed):
            s.run(['/does-not-exist'])

    def fixture(self, directory):
        root = Path(directory)
        subject = {'image_id': 'sha256:' + 'a' * 64, 'diff_ids': ['sha256:' + 'b' * 64],
                   'source': 'c' * 40, 'app': 'n8n', 'archive_sha256': 'd' * 64}
        sbom = {'descriptor': {'name': 'syft', 'version': s.pins()['syft']['version'],
                 'configuration': {'search': {'scope': 'all-layers'}, 'files': {'selection': 'all'}}},
                'source': {'type': 'image', 'metadata': {'imageID': subject['image_id'], 'layers': [{}]}},
                'files': [{'id': 'offline-fixture-only'}],
                'artifacts': [{'type': kind, 'name': 'offline-fixture-only', 'licenses': [{'value': 'MIT'}]}
                              for kind in ('deb', 'python', 'npm')]}
        s.write_json(root / 'sbom.syft.json', sbom)
        s.write_json(root / 'sbom.spdx.json', {'spdxVersion': 'SPDX-2.3', 'SPDXID': 'SPDXRef-DOCUMENT',
                                            'packages': [{'name': 'offline-fixture-only'}]})
        summary = {'subject': subject, 'policy_sha256': s.policy_hash(),
                   'tools': s.pins(), 'checks': dict.fromkeys(s.CHECKS, 'pass')}
        (root / 'scan-summary.json').write_text(json.dumps(summary))
        provenance = s.provenance(subject, root)
        (root / 'provenance.json').write_text(json.dumps(provenance))
        return root, subject

    def test_missing_or_wrong_scan_subject_sbom_provenance_deny(self):
        for name in ('scan-summary.json', 'sbom.syft.json', 'sbom.spdx.json', 'provenance.json'):
            with tempfile.TemporaryDirectory() as d:
                root, subject = self.fixture(d)
                (root / name).unlink()
                with self.subTest(missing=name), self.assertRaises(s.Closed):
                    s.verify_bundle(root, subject)
        for field in ('source', 'image_id', 'app', 'diff_ids'):
            with tempfile.TemporaryDirectory() as d:
                root, subject = self.fixture(d)
                bad = dict(subject, **{field: 'WRONG'})
                with self.subTest(subject=field), self.assertRaises(s.Closed):
                    s.verify_bundle(root, bad)
        for file in ('sbom.syft.json', 'sbom.spdx.json', 'provenance.json', 'scan-summary.json'):
            with tempfile.TemporaryDirectory() as d:
                root, subject = self.fixture(d)
                (root / file).write_text('{}')
                with self.subTest(changed=file), self.assertRaises(s.Closed):
                    s.verify_bundle(root, subject)

    def test_wrong_sbom_subject_or_scope_denies_even_rehashed(self):
        for field in ('image', 'scope', 'packages'):
            with tempfile.TemporaryDirectory() as d:
                root, subject = self.fixture(d)
                sbom = s.read_json(root / 'sbom.syft.json')
                if field == 'image':
                    sbom['source']['metadata']['imageID'] = 'sha256:' + 'f' * 64
                elif field == 'scope':
                    sbom['descriptor']['configuration']['search']['scope'] = 'squashed'
                else:
                    sbom['artifacts'] = []
                s.write_json(root / 'sbom.syft.json', sbom)
                s.write_json(root / 'provenance.json', s.provenance(subject, root))
                with self.subTest(field=field), self.assertRaises(s.Closed):
                    s.verify_bundle(root, subject)

    def test_failed_missing_unknown_policy_scan_denies_even_rehashed(self):
        for key, value in (('policy_sha256', 'wrong'), ('tools', {}), ('checks', {}),
                           ('checks', dict.fromkeys(s.CHECKS, 'error'))):
            with tempfile.TemporaryDirectory() as d:
                root, subject = self.fixture(d)
                summary = json.loads((root / 'scan-summary.json').read_text())
                summary[key] = value
                (root / 'scan-summary.json').write_text(json.dumps(summary))
                (root / 'provenance.json').write_text(json.dumps(s.provenance(subject, root)))
                with self.assertRaises(s.Closed):
                    s.verify_bundle(root, subject)

    def test_remote_manifest_config_and_layer_mismatch_denies(self):
        config = json.dumps({'rootfs': {'diff_ids': ['sha256:' + 'b' * 64]}}).encode()
        image_id = 'sha256:' + hashlib.sha256(config).hexdigest()
        subject = {'image_id': image_id, 'diff_ids': ['sha256:' + 'b' * 64]}
        manifest = {'schemaVersion': 2, 'config': {'digest': image_id},
                    'layers': [{'digest': 'sha256:' + 'c' * 64}]}
        raw = json.dumps(manifest).encode()
        digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
        pulled = {'Id': image_id, 'RootFS': {'Layers': subject['diff_ids']}}
        s.verify_remote(raw, digest, pulled, subject)
        for changed in ({**subject, 'image_id': 'sha256:' + 'f' * 64},
                        {**subject, 'diff_ids': []}):
            with self.assertRaises(s.Closed):
                s.verify_remote(raw, digest, pulled, changed)
        with self.assertRaises(s.Closed):
            s.verify_remote(raw, 'sha256:' + 'f' * 64, pulled, subject)
        with self.assertRaises(s.Closed):
            s.verify_remote(raw, digest, dict(pulled, Id='sha256:' + 'f' * 64), subject)

    def test_saved_image_config_and_every_layer_bound_before_scanning(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            layer = io.BytesIO()
            with tarfile.open(fileobj=layer, mode='w') as tar:
                info = tarfile.TarInfo('../../must-not-escape.txt')
                data = b'owned layer fixture only'
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            layer_bytes = layer.getvalue()
            diff_id = 'sha256:' + hashlib.sha256(layer_bytes).hexdigest()
            config = json.dumps({'rootfs': {'diff_ids': [diff_id]}}).encode()
            metadata = {'Id': 'sha256:' + hashlib.sha256(config).hexdigest(), 'RootFS': {'Layers': [diff_id]}}
            archive = root / 'image.tar'
            with tarfile.open(archive, 'w') as tar:
                for name, data in [('manifest.json', json.dumps([{'Config': 'config.json', 'Layers': ['layer.tar']}]).encode()),
                                   ('config.json', config), ('layer.tar', layer_bytes)]:
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
            scan = s.unpack_image(archive, metadata, root)
            self.assertEqual((scan / '0/0.txt').read_bytes(), b'owned layer fixture only')
            self.assertFalse((root / 'must-not-escape.txt').exists())
            shutil.rmtree(scan)
            with self.assertRaises(s.Closed):
                s.unpack_image(archive, dict(metadata, Id='sha256:' + 'f' * 64), root)
            shutil.rmtree(scan)
            with self.assertRaises(s.Closed):
                s.unpack_image(archive, dict(metadata, RootFS={'Layers': ['sha256:' + 'f' * 64]}), root)

    def test_workflow_enforces_candidate_before_login_push_and_persists_evidence(self):
        from validate import ROOT, load
        for workflow, job in (('release', 'publish'), ('ci', 'images')):
            value = load(ROOT / '.github/workflows' / (workflow + '.yaml'))
            steps = value['jobs'][job]['steps']
            text = '\n'.join(x.get('run', '') for x in steps)
            self.assertIn('supply_chain.py candidate', text)
            self.assertEqual(sum('docker/build-push-action@' in x.get('uses', '') for x in steps), 1)
            self.assertTrue(any(x.get('with', {}).get('fetch-depth') == 0 for x in steps))
            if workflow == 'release':
                self.assertIn('supply_chain.py verify', text)
                self.assertIn('registry_gate.py public', text)
                candidate = next(i for i,x in enumerate(steps) if 'supply_chain.py candidate' in x.get('run', ''))
                login = next(i for i,x in enumerate(steps) if 'docker/login-action@' in x.get('uses', ''))
                self.assertLess(candidate, login)
