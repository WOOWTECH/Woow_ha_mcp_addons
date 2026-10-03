"""Packaging-only regression fixtures: never use a config.* fixture basename."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import validate as v


class PackagingTests(unittest.TestCase):
    def test_all_manifests(self):
        for product in v.PRODUCTS:
            with self.subTest(product=product):
                v.manifest(v.load(v.ROOT / 'addons' / product / 'config.yaml'), product)

    def test_security_and_schema_mutations(self):
        original = v.load(v.ROOT / 'addons/n8n/config.yaml')
        mutations = [('image', 'ghcr.io/woowtech/amd64-mcp-n8n:0.1.0'),
            ('image', 'ghcr.io/other/{arch}-mcp-n8n'), ('slug', 'woow_mcp_emqx'),
            ('arch', ['amd64', 'aarch64']), ('arch', ['aarch64']), ('version', 'latest'),
            ('version', 0.1), ('ingress_port', 8081), ('ports', {'8099/tcp': 8099}),
            ('ports', {'3000/tcp': None}), ('ports', {'8081/tcp': 8081}),
            ('init', False), ('init', 1), ('homeassistant_api', False),
            ('hassio_api', True), ('hassio_role', 'admin'), ('auth_api', True),
            ('docker_api', True), ('host_network', True), ('host_pid', True),
            ('full_access', True), ('apparmor', False), ('map', ['config:rw']),
            ('privileged', ['SYS_ADMIN']), ('watchdog', 'http://[HOST]:8081/health/ready'),
            ('protected', True), ('auto_update', False), ('homeassistant', '2026.09.3'),
            ('options', {'backend_url': 'http://example.invalid'}), ('schema', False),
            ('boot', 'auto'), ('unknown_typo', False)]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                doc = copy.deepcopy(original)
                doc[key] = value
                with self.assertRaises(v.Invalid):
                    v.manifest(doc, 'n8n')

    def test_n8n_only_approved_permission_exception(self):
        for product in v.PRODUCTS:
            original = v.load(v.ROOT / 'addons' / product / 'config.yaml')
            self.assertIs(original['homeassistant_api'], product == 'n8n')
            v.manifest(original, product)
            # Exact booleans; no new API, Supervisor role or host privileges.
            mutations = [('homeassistant_api', value) for value in
                         (product != 'n8n', 0, 1, 'true', 'false', None)]
            mutations += [(key, True) for key in ('hassio_api', 'auth_api',
                          'docker_api', 'full_access', 'host_network', 'host_pid',
                          'host_ipc', 'host_uts', 'host_dbus')]
            mutations += [('hassio_role', role) for role in
                          ('admin', 'manager', 'homeassistant', 'default')]
            mutations += [('privileged', ['SYS_ADMIN']), ('devices', ['/dev/test']),
                          ('map', ['config:rw']), ('apparmor', False),
                          ('options', {'SUPERVISOR_TOKEN': 'INVENTED-ONLY'}),
                          ('environment', {'HA_ROLE_URL': 'ws://example.invalid'})]
            for key, value in mutations:
                with self.subTest(product=product, key=key, value=value):
                    doc = copy.deepcopy(original)
                    doc[key] = value
                    with self.assertRaises(v.Invalid):
                        v.manifest(doc, product)

    def test_accidental_discovery_and_excluded_scope(self):
        paths = v.source_paths(v.ROOT)
        for extra in ('packaging/fixture/config.yaml', 'apps/kubernetes/runtime.py'):
            with self.subTest(extra=extra), patch.object(v, 'source_paths', return_value=[*paths, extra]), self.assertRaises(v.Invalid):
                v.validate()

    def test_missing_key(self):
        doc = v.load(v.ROOT / 'addons/n8n/config.yaml')
        del doc['homeassistant_api']
        with self.assertRaises(v.Invalid):
            v.manifest(doc, 'n8n')

    def test_translations_scope(self):
        for doc in ({'configuration': {}, 'network': {'8099/tcp': 'admin'}},
                    {'configuration': {'token': {'name': 'secret'}}, 'network': {'8081/tcp': 'MCP'}},
                    {'configuration': {}, 'network': {'8081/tcp': 1}},
                    {'configuration': {}, 'network': {'8081/tcp': 'MCP'}, 'unknown': {}}):
            with self.subTest(doc=doc), self.assertRaises(v.Invalid):
                v.translation(doc)

    def test_duplicate_alias_and_unsafe_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.yaml'
            for text in ('a: 1\na: 2', 'a: &a {}\nb: *a', 'x: !!python/object:danger {}', 'true: x'):
                path.write_text(text)
                with self.subTest(text=text), self.assertRaises(v.Invalid):
                    v.load(path)

    def test_workflow_on_not_boolean(self):
        self.assertIn('on', v.load(v.ROOT / '.github/workflows/ci.yaml'))

    def test_release_defaults_closed(self):
        gates = v.load(v.ROOT / 'RELEASE-GATES.json')
        v.clearance_shape(gates)
        if gates['approved_commit'] is None:
            for key in ('source', 'license', 'secret', 'publisher'):
                self.assertIs(gates[key]['cleared'], False)
            for product in v.PRODUCTS:
                for gate in gates['products'][product].values():
                    self.assertIs(gate['cleared'], False)

    def test_clearance_evidence_and_types(self):
        for cleared, evidence in [('true', None), (True, None), (True, 'https://example.invalid'),
                                  (True, 'docs/operations/evidence/../private.md')]:
            gates = v.load(v.ROOT / 'RELEASE-GATES.json')
            gates['source'] = {'cleared': cleared, 'evidence': evidence}
            with self.subTest(cleared=cleared, evidence=evidence), self.assertRaises(v.Invalid):
                v.clearance_shape(gates)


if __name__ == '__main__':
    unittest.main()
