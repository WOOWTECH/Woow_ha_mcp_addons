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

    def test_approved_permission_exception_is_homeassistant_api_only(self):
        # n8n approved 2026-10-04; the other six by owner decision 2026-10-05 (0.1.1).
        for product in v.PRODUCTS:
            original = v.load(v.ROOT / 'addons' / product / 'config.yaml')
            self.assertIs(original['homeassistant_api'], True)
            v.manifest(original, product)
            # Exact booleans; no new API, Supervisor role or host privileges.
            mutations = [('homeassistant_api', value) for value in
                         (False, 0, 1, 'true', 'false', None)]
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

    def test_builder_workflow_contract(self):
        for workflow in ('ci', 'release'):
            original = v.load(v.ROOT / '.github/workflows' / (workflow + '.yaml'))
            v.builder_workflow(original, workflow)
            job_name = 'images' if workflow == 'ci' else 'publish'
            job = original['jobs'][job_name]
            setup = next(i for i, step in enumerate(job['steps'])
                         if step.get('run') == 'python3 packaging/builder_contract.py setup --driver docker')
            build = next(i for i, step in enumerate(job['steps'])
                         if step.get('uses', '').startswith('docker/build-push-action@'))
            for replacement in ('docker-container', 'remote', 'docker --version latest',
                                'docker --driver-opts network=host',
                                'docker --buildkitd-flags --oci-worker-no-process-sandbox'):
                doc = copy.deepcopy(original)
                doc['jobs'][job_name]['steps'][setup]['run'] = (
                    'python3 packaging/builder_contract.py setup --driver ' + replacement)
                with self.subTest(workflow=workflow, driver=replacement), self.assertRaises(v.Invalid):
                    v.builder_workflow(doc, workflow)
            mutations = [(build, 'allow', 'security.insecure'), (build, 'network', 'host'),
                         (build, 'platforms', 'linux/arm64'), (build, 'builder', 'remote')]
            for index, key, value in mutations:
                doc = copy.deepcopy(original)
                doc['jobs'][job_name]['steps'][index]['with'][key] = value
                with self.subTest(workflow=workflow, key=key), self.assertRaises(v.Invalid):
                    v.builder_workflow(doc, workflow)
            for command in ('prepare', 'setup --driver docker', 'verify'):
                for bypass in ('if', 'continue-on-error', 'remove'):
                    doc = copy.deepcopy(original)
                    steps = doc['jobs'][job_name]['steps']
                    step = next(s for s in steps if s.get('run') == 'python3 packaging/builder_contract.py ' + command)
                    if bypass == 'remove':
                        steps.remove(step)
                    else:
                        step[bypass] = True
                    with self.subTest(workflow=workflow, command=command, bypass=bypass), self.assertRaises(v.Invalid):
                        v.builder_workflow(doc, workflow)

    def test_no_later_proxy_home_helper_or_github_env_reintroduction(self):
        for workflow in ('ci', 'release'):
            original = v.load(v.ROOT / '.github/workflows' / (workflow + '.yaml'))
            candidate = 'images' if workflow == 'ci' else 'publish'
            for key in ('HTTPS_PROXY', 'no_proxy', 'PASSWORD_STORE_DIR', 'HOME', 'DOCKER_CONFIG'):
                for scope in ('workflow', 'candidate-step'):
                    doc = copy.deepcopy(original)
                    target = doc if scope == 'workflow' else doc['jobs'][candidate]['steps'][-1]
                    target.setdefault('env', {})[key] = 'INVENTED-ONLY'
                    with self.subTest(workflow=workflow, key=key, scope=scope), self.assertRaises(v.Invalid):
                        v.builder_workflow(doc, workflow)
            for script in ('echo HOME=/invented >> "$GITHUB_ENV"',
                           'export HTTPS_PROXY=http://invented.invalid',
                           'echo /invented >> "$GITHUB_PATH"'):
                doc = copy.deepcopy(original)
                doc['jobs'][candidate]['steps'].insert(-1, {'run': script})
                with self.subTest(workflow=workflow, script=script), self.assertRaises(v.Invalid):
                    v.builder_workflow(doc, workflow)

    def test_setup_cannot_download_or_overwrite_verified_buildx(self):
        for workflow in ('ci', 'release'):
            doc = v.load(v.ROOT / '.github/workflows' / (workflow + '.yaml'))
            job = doc['jobs']['images' if workflow == 'ci' else 'publish']
            self.assertFalse(any(s.get('uses', '').startswith('docker/setup-buildx-action@')
                                 for s in job['steps']))
            self.assertTrue(any(s.get('run') == 'python3 packaging/builder_contract.py setup --driver docker'
                                for s in job['steps']))

    def test_builder_admission_and_runner_mutations(self):
        for workflow in ('ci', 'release'):
            original = v.load(v.ROOT / '.github/workflows' / (workflow + '.yaml'))
            candidate = 'images' if workflow == 'ci' else 'publish'
            admission = 'builder-admission' if workflow == 'ci' else 'gate'
            mutations = [(candidate, 'runs-on', 'ubuntu-24.04'),
                         (candidate, 'container', {'image': 'docker:latest'}),
                         (candidate, 'services', {'docker': {'image': 'docker:dind'}}),
                         (candidate, 'continue-on-error', True),
                         (candidate, 'needs', []), (admission, 'continue-on-error', True),
                         (admission, 'env', {})]
            if workflow == 'ci':
                mutations += [(admission, 'if', 'false'), (candidate, 'if', 'false'),
                              ('unit', 'needs', ['builder-admission'])]
            for job, key, value in mutations:
                doc = copy.deepcopy(original)
                doc['jobs'][job][key] = value
                with self.subTest(workflow=workflow, job=job, key=key), self.assertRaises(v.Invalid):
                    v.builder_workflow(doc, workflow)
            doc = copy.deepcopy(original)
            steps = doc['jobs'][candidate]['steps']
            guard = next(s for s in steps if s.get('run') == 'python3 packaging/builder_contract.py verify')
            steps.remove(guard)
            steps.append(guard)
            with self.subTest(workflow=workflow, mutation='verify-after-build'), self.assertRaises(v.Invalid):
                v.builder_workflow(doc, workflow)

    def test_odoo_manage_is_retired_from_store_build_and_release(self):
        # Owner decision 2026-10-06: off the store, never built or released again; the source stays (archived).
        self.assertEqual(v.RETIRED, ('odoo-manage',))
        self.assertNotIn('odoo-manage', v.PRODUCTS)
        self.assertFalse((v.ROOT / 'addons/odoo-manage').exists())
        self.assertNotIn('odoo-manage', v.load(v.ROOT / 'packaging/inputs.json')['products'])
        self.assertNotIn('odoo-manage', v.load(v.ROOT / 'RELEASE-GATES.json')['products'])
        for workflow in ('ci.yaml', 'release.yaml'):
            self.assertNotIn('odoo-manage', (v.ROOT / '.github/workflows' / workflow).read_text())
        self.assertTrue((v.ROOT / 'apps/odoo-manage/launch.py').is_file())
        # RC review F2: the builder-side gate tools refuse it too, so no odoo-manage 0.1.5 image can pass the gate.
        import container_acceptance
        import context_closure
        import supply_chain
        for products in (container_acceptance.PRODUCTS, supply_chain.PRODUCTS, tuple(context_closure.products(v.ROOT))):
            self.assertEqual(tuple(products), v.PRODUCTS)

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
