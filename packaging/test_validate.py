"""Packaging-only regression fixtures: never use a config.* fixture basename."""
import copy
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import validate as v

# HM-17: the workflows' version expressions are checked by what GitHub Actions would make of them, with an evaluator of
# their own, not by re-reading the generator's text.
TOKEN = re.compile(r"\s*('(?:[^']|'')*'|==|&&|\|\||[A-Za-z_][A-Za-z0-9_.]*)")
EXPRESSION = re.compile(r'\$\{\{.*?\}\}', re.S)


def evaluate(expression, selector, app):
    """The value GitHub Actions gives `expression` when `selector` (matrix.app or inputs.app) is `app`, for the grammar
    the version expressions use: string literals, that one property, ==, && and || (&& binds tighter than ||, both
    return an operand, == compares strings ignoring case). A bare value (no ${{ }}) is itself."""
    if not expression.startswith('${{'):
        return expression
    if not (expression.startswith('${{ ') and expression.endswith(' }}')):
        raise AssertionError('not one whole expression: ' + expression)
    body, tokens, position = expression[3:-3], [], 0
    while body[position:].strip():
        match = TOKEN.match(body, position)
        if match is None:
            raise AssertionError('unexpected text: ' + body[position:])
        tokens.append(match.group(1))
        position = match.end()
    tokens.append(None)

    def truthy(value):
        return value not in (False, None, '', 0)

    def primary():
        token = tokens.pop(0)
        if token is not None and token.startswith("'"):
            return token[1:-1].replace("''", "'")
        if token == selector:
            return app
        raise AssertionError(f'unexpected token {token!r}')

    def comparison():
        left = primary()
        if tokens[0] == '==':
            tokens.pop(0)
            right = primary()
            left = isinstance(left, str) and isinstance(right, str) and left.casefold() == right.casefold()
        return left

    def conjunction():
        left = comparison()
        while tokens[0] == '&&':
            tokens.pop(0)
            right = comparison()
            left = right if truthy(left) else left
        return left

    def disjunction():
        left = conjunction()
        while tokens[0] == '||':
            tokens.pop(0)
            right = conjunction()
            left = left if truthy(left) else right
        return left

    value = disjunction()
    if tokens != [None]:
        raise AssertionError('trailing tokens: ' + repr(tokens))
    return value


def substitute(text, selector, app):
    """`text` with every expression that reads the app replaced by its value; the others (${{ github.sha }}) stay."""
    def value(match):
        if selector not in match.group(0):
            return match.group(0)
        result = evaluate(match.group(0), selector, app)
        if not isinstance(result, str):
            raise AssertionError('not a string value: ' + match.group(0))
        return result
    return EXPRESSION.sub(value, text)


def strings(value, path=()):
    """(path, text) of every string in a loaded workflow."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from strings(item, path + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from strings(item, path + (index,))
    elif isinstance(value, str):
        yield path, value


def at(document, path):
    for key in path:
        document = document[key]
    return document


def replaced(document, path, text):
    document = copy.deepcopy(document)
    at(document, path[:-1])[path[-1]] = text
    return document


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
            ('boot', 'manual'), ('ingress_entry', '/'), ('ingress_entry', '/access'), ('unknown_typo', False)]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                doc = copy.deepcopy(original)
                doc[key] = value
                with self.assertRaises(v.Invalid):
                    v.manifest(doc, 'n8n')

    def test_approved_permission_exception_is_homeassistant_api_only(self):
        # n8n approved 2026-10-04; the other six by owner decision 2026-10-05 (0.1.1); Nextcloud 2026-10-08 (0.1.7).
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

    def test_initialize_version_is_the_release_version(self):
        # 0.1.8 review F-5a: mcp_admin_core.VERSION (initialize serverInfo) is bound once, to the release version.
        good = "VERSION = '%s'\nPRODUCT_VERSIONS = %r\n" % (v.VERSION, v.VERSION_OVERRIDES)
        v.runtime_version(good)
        v.runtime_version((v.ROOT / 'packages/mcp-admin-core/mcp_admin_core/__init__.py').read_text())
        for text in ("VERSION = '0.1.6'\n", '', "VERSION = None\n", "VERSION = VERSION_TEXT\n",
                     "VERSION, OTHER = '%s', 1\n" % v.VERSION, good + "VERSION = '0.1.6'\n",
                     good + "VERSION: str = '0.1.6'\n", good + "VERSION += '-dirty'\n",
                     good + "from os import sep as VERSION\n", good + "def f():\n    VERSION = '0.1.6'\n"):
            with self.subTest(text=text), self.assertRaisesRegex(v.Invalid, 'initialize serverInfo version'):
                v.runtime_version(text)
        # validate() runs this check on the real tree.
        with patch.object(v, 'runtime_version', side_effect=v.Invalid('initialize serverInfo version')):
            with self.assertRaisesRegex(v.Invalid, 'initialize serverInfo version'):
                v.validate(v.ROOT)
        with self.assertRaisesRegex(v.Invalid, 'fixed per-product runtime version'):
            v.runtime_version("VERSION = '%s'\nPRODUCT_VERSIONS = {}\n" % v.VERSION)

    def test_every_release_version_is_bound_at_every_boundary(self):
        # HM-17 (C4-SF-2): read from version_for(), so a version bump changes data only (VERSION, VERSION_OVERRIDES and
        # what validate() binds to them), never this test. Headscale has its own line today; the others ship VERSION.
        self.assertEqual({product: v.version_for(product) for product in v.PRODUCTS},
                         {product: v.VERSION_OVERRIDES.get(product, v.VERSION) for product in v.PRODUCTS})
        for unknown in ('unknown', *v.RETIRED):
            with self.subTest(product=unknown), self.assertRaises(v.Invalid):
                v.version_for(unknown)
        inputs = v.load(v.ROOT / 'packaging/inputs.json')
        self.assertEqual({product: inputs['version_overrides'].get(product, inputs['version']) for product in v.PRODUCTS},
                         {product: v.version_for(product) for product in v.PRODUCTS})
        lines = {v.VERSION, *v.VERSION_OVERRIDES.values(), '99.0.0'}  # 99.0.0: a version no product line uses
        for product in v.PRODUCTS:
            own = v.version_for(product)
            manifest = v.load(v.ROOT / 'addons' / product / 'config.yaml')
            dockerfile = (v.ROOT / 'apps' / product / 'Dockerfile').read_text()
            with self.subTest(product=product):
                self.assertEqual(manifest['version'], own)
                v.manifest(manifest, product)
                v.build_version_default(dockerfile, product)
            for other in sorted(lines - {own}):  # another product line's version, or a new one
                with self.subTest(product=product, other=other):
                    with self.assertRaises(v.Invalid):
                        v.manifest({**manifest, 'version': other}, product)
                    with self.assertRaisesRegex(v.Invalid, 'build version default'):
                        v.build_version_default(dockerfile.replace(f'\nARG BUILD_VERSION={own}\n',
                                                                   f'\nARG BUILD_VERSION={other}\n'), product)
            # One default, used by the version label: it is the image's version whenever no build-arg sets it, and
            # container acceptance requires io.hass.version == version_for(app) (container_acceptance.py).
            for mutated in (dockerfile + f'ARG BUILD_VERSION={own}\n',
                            dockerfile.replace(f'\nARG BUILD_VERSION={own}\n', '\nARG BUILD_VERSION\n'),
                            dockerfile.replace('io.hass.version="${BUILD_VERSION}"', f'io.hass.version="{own}"'),
                            dockerfile + f'LABEL io.hass.version="{own}"\n'):
                with self.subTest(product=product, mutated=mutated[-80:]), self.assertRaisesRegex(v.Invalid, 'build version default'):
                    v.build_version_default(mutated, product)
        with patch.object(v, 'build_version_default', side_effect=v.Invalid('Dockerfile build version default')):
            with self.assertRaisesRegex(v.Invalid, 'build version default'):
                v.validate(v.ROOT)

    def test_version_expressions_are_generated_from_the_overrides(self):
        # HM-17 (plan 11.2, C4-SF-1): one `<selector> == '<product>' && '<version>'` arm per override in PRODUCTS order,
        # joined by ||, then the default: the two-way form the workflows carry since 0.4.14, chained (no fromJSON).
        # Without an override it is the bare default, the form before 0.4.14.
        self.assertEqual(v.CI_VERSION, v.version_expression('matrix.app'))
        self.assertEqual(v.RELEASE_VERSION, v.version_expression('inputs.app'))
        self.assertEqual(v.version_expression('matrix.app', {}, '1.2.3'), '1.2.3')
        self.assertEqual(v.version_expression('matrix.app', {'headscale': '1.2.4'}, '1.2.3'),
                         "${{ matrix.app == 'headscale' && '1.2.4' || '1.2.3' }}")
        self.assertEqual(v.version_expression('inputs.app', {'headscale': '1.2.4', 'odoo': '2.0.0'}, '1.2.3'),
                         "${{ inputs.app == 'odoo' && '2.0.0' || inputs.app == 'headscale' && '1.2.4' || '1.2.3' }}")
        every = {product: f'2.0.{index}' for index, product in enumerate(v.PRODUCTS)}
        for overrides in ({}, {'headscale': '1.2.4'}, {'headscale': '1.2.4', 'odoo': '2.0.0'},
                          {'nextcloud': '2.0.0', 'n8n': '2.0.1', 'emqx': '2.0.0'}, every):
            for selector in ('matrix.app', 'inputs.app'):
                expression = v.version_expression(selector, overrides, '1.2.3')
                for product in (*v.PRODUCTS, *v.RETIRED):  # a product outside the list gets the default
                    with self.subTest(overrides=overrides, selector=selector, product=product):
                        self.assertEqual(evaluate(expression, selector, product), overrides.get(product, '1.2.3'))
        for selector, expression in (('matrix.app', v.CI_VERSION), ('inputs.app', v.RELEASE_VERSION)):
            for product in v.PRODUCTS:
                with self.subTest(selector=selector, product=product):
                    self.assertEqual(evaluate(expression, selector, product), v.version_for(product))

    def test_version_expression_refuses_data_it_cannot_express(self):
        for selector, overrides, default in (
                ('github.ref', {}, '1.2.3'), ('matrix.app', {'unknown': '1.2.4'}, '1.2.3'),
                ('matrix.app', {'odoo-manage': '1.2.4'}, '1.2.3'), ('matrix.app', {'odoo': '1.2.3'}, '1.2.3'),
                ('matrix.app', {'odoo': "1.2.4' || '9.9.9"}, '1.2.3'), ('matrix.app', {'odoo': ''}, '1.2.3'),
                ('matrix.app', {'odoo': 1.2}, '1.2.3'), ('matrix.app', {'odoo': '1.2'}, '1.2.3'),
                ('matrix.app', {'odoo': 'latest'}, '1.2.3'), ('matrix.app', {}, 'latest'), ('matrix.app', {}, ''),
                ('matrix.app', [('odoo', '1.2.4')], '1.2.3')):
            with self.subTest(selector=selector, overrides=overrides, default=default), self.assertRaises(v.Invalid):
                v.version_expression(selector, overrides, default)

    def test_every_app_dependent_workflow_value_is_the_release_version(self):
        # HM-17: ci.yaml and release.yaml do not run on a PR; validate.py compares them (C4-SF-1). Evaluated as GitHub
        # would, for every app they build, each place carries version_for(app).
        for workflow, selector in (('ci', 'matrix.app'), ('release', 'inputs.app')):
            document = v.load(v.ROOT / '.github/workflows' / (workflow + '.yaml'))
            v.workflow_versions(document, workflow)  # the repository as it is
            job = document['jobs']['images' if workflow == 'ci' else 'publish']
            build = next(s for s in job['steps'] if s.get('uses', '').startswith('docker/build-push-action@'))
            apps = (job['strategy']['matrix']['app'] if workflow == 'ci'
                    else document['on']['workflow_dispatch']['inputs']['app']['options'])
            self.assertEqual(apps, list(v.PRODUCTS))
            for app in apps:
                version = v.version_for(app)
                with self.subTest(workflow=workflow, app=app):
                    self.assertEqual(substitute(build['with']['build-args'], selector, app), 'BUILD_VERSION=' + version)
                    self.assertEqual(substitute(build['with']['tags'], selector, app), f'local/mcp-{app}:{version}')
                    if workflow == 'release':
                        push = next(s for s in job['steps'] if 'docker push' in s.get('run', ''))
                        self.assertIn(f'IMAGE="ghcr.io/woowtech/amd64-mcp-$APP:{version}"',
                                      substitute(push['run'], selector, app).splitlines())
                        upload = next(s for s in job['steps'] if s.get('uses', '').startswith('actions/upload-artifact@'))
                        self.assertEqual(substitute(upload['with']['name'], selector, app),
                                         'published-evidence-%s-%s-${{ github.sha }}' % (app, version))

    def test_a_stale_or_hand_written_version_expression_is_refused(self):
        # A version bump changes VERSION_OVERRIDES; until every place is regenerated the workflow is refused, place by
        # place (the published evidence name too), and so is a fixed version or any other expression that reads the app.
        changed = {**v.VERSION_OVERRIDES, v.PRODUCTS[0]: '99.0.0'}
        bump = {'VERSION_OVERRIDES': changed, 'CI_VERSION': v.version_expression('matrix.app', changed),
                'RELEASE_VERSION': v.version_expression('inputs.app', changed)}
        for workflow, selector, key, group in (('ci', 'matrix.app', 'CI_VERSION', 'ci-${{ github.workflow }}-'),
                                               ('release', 'inputs.app', 'RELEASE_VERSION', 'public-release-')):
            original = v.load(v.ROOT / '.github/workflows' / (workflow + '.yaml'))
            current, new = getattr(v, key), bump[key]
            places = [path for path, text in strings(original) if current in text]
            self.assertEqual(len(places), 2 if workflow == 'ci' else 4)  # tags, build-args; release: IMAGE, evidence name
            regenerated = original
            for path in places:
                regenerated = replaced(regenerated, path, at(regenerated, path).replace(current, new))
            with patch.multiple(v, **bump):
                with self.subTest(workflow=workflow, state='stale'), self.assertRaises(v.Invalid):
                    v.builder_workflow(original, workflow)
                v.builder_workflow(regenerated, workflow)  # every place regenerated
                for path in places:
                    for text in (at(original, path), at(regenerated, path).replace(new, v.VERSION)):
                        with self.subTest(workflow=workflow, place=path, text=text), self.assertRaises(v.Invalid):
                            v.builder_workflow(replaced(regenerated, path, text), workflow)
            inner = current[4:-3] if current.startswith('${{ ') else f"'{current}'"
            for hand in (f"${{{{ {selector} == 'odoo-manage' && '99.0.0' || {inner} }}}}",
                         f"${{{{ fromJSON('{{}}')[{selector}] || {inner} }}}}", f'${{{{  {inner} }}}}'):
                for path in places:
                    with self.subTest(workflow=workflow, place=path, hand=hand), self.assertRaises(v.Invalid):
                        v.builder_workflow(replaced(original, path, at(original, path).replace(current, hand)), workflow)
            context, name = selector.split('.')
            for reads in (selector, f"{context}['{name}']", f'github.event.{selector}', selector.upper()):
                elsewhere = replaced(original, ('concurrency', 'group'), group + f"${{{{ {reads} == 'odoo' && 'a' || 'b' }}}}")
                with self.subTest(workflow=workflow, place='concurrency', reads=reads), self.assertRaises(v.Invalid):
                    v.builder_workflow(elsewhere, workflow)
            for unrelated in (f'${{{{ {selector} }}}}', "${{ github.ref == 'refs/heads/main' && 'a' || 'b' }}",
                              '${{ github.event.inputs.application }}'):
                with self.subTest(workflow=workflow, place='concurrency', unrelated=unrelated):
                    v.builder_workflow(replaced(original, ('concurrency', 'group'), group + unrelated), workflow)

    def test_unit_script_installs_headscale_without_workflow_precondition(self):
        unit = (v.ROOT / 'packaging/unit.sh').read_text()
        v.unit_child_sync(unit)
        with self.assertRaisesRegex(v.Invalid, 'unit.sh isolated child scope'):
            v.unit_child_sync(unit.replace(' nextcloud headscale; do', ' nextcloud; do'))
        for workflow in ('ci.yaml', 'release.yaml', 'woow-addon-release.yml'):
            text = (v.ROOT / '.github/workflows' / workflow).read_text()
            self.assertIn('sh packaging/unit.sh', text)
            self.assertNotIn('run: uv sync --project apps/headscale', text)

    def test_the_native_addon_is_pinned_everywhere_and_is_the_only_download(self):
        # Unreleased (0.4.12 line): better-sqlite3's prebuilt binary is the n8n image's one native addon; it enters only
        # through packaging/native_addon.mjs from the pinned release asset, next to the hash-locked, script-free npm tree.
        inputs = v.load(v.ROOT / 'packaging/inputs.json')
        dockerfiles = {product: (v.ROOT / 'apps' / product / 'Dockerfile').read_text() for product in v.PRODUCTS}
        files = {'lock': (v.ROOT / 'apps/n8n/package-lock.json').read_text(), 'package': (v.ROOT / 'apps/n8n/package.json').read_text(),
                 'unit': (v.ROOT / 'packaging/unit.sh').read_text(), 'dockerignore': (v.ROOT / '.dockerignore').read_text()}
        v.native_addons(inputs, dockerfiles, files)  # the repository as it is
        pin = inputs['native_addons']['better-sqlite3']
        n8n = dockerfiles['n8n']

        def with_pin(**changes):
            value = copy.deepcopy(inputs)
            value['native_addons']['better-sqlite3'].update(changes)
            return (value, dockerfiles, files)

        def with_dockerfile(product, text):
            return (inputs, {**dockerfiles, product: text}, files)

        def with_file(name, text):
            return (inputs, dockerfiles, {**files, name: text})

        install = n8n.index('RUN node native_addon.mjs install')
        extra = copy.deepcopy(inputs)
        extra['native_addons']['other'] = copy.deepcopy(pin)
        cases = {
            'url of another version': with_pin(url=pin['url'].replace('v12.11.1', 'v12.11.0')),
            'mutable url': with_pin(url=pin['url'].replace('/download/v12.11.1/', '/latest/download/')),
            'archive digest': with_pin(sha256='0' * 64),
            'member digest': with_pin(member_sha256='z' * 64),
            'size as text': with_pin(size='1114012'),
            'another member': with_pin(member='build/Release/other.node'),
            'another node than the base image': with_pin(node='24.22.1'),
            'another platform': with_pin(platform='linux-arm64'),
            'a second addon': (extra, dockerfiles, files),
            'pin without evidence': (({**inputs, 'native_addons': {'better-sqlite3': {k: x for k, x in pin.items() if k != 'evidence'}}}), dockerfiles, files),
            'no pins': ({k: x for k, x in inputs.items() if k != 'native_addons'}, dockerfiles, files),
            'Dockerfile carries another digest': with_dockerfile('n8n', n8n.replace(pin['sha256'], '1' * 64)),
            'Dockerfile carries another member digest': with_dockerfile('n8n', n8n.replace(pin['member_sha256'], '2' * 64)),
            'Dockerfile without the script copy': with_dockerfile('n8n', n8n.replace('COPY packaging/native_addon.mjs ./native_addon.mjs\n', '')),
            'Dockerfile installs before the locked tree': with_dockerfile('n8n', n8n[install:] + n8n[:install]),
            'second installation': with_dockerfile('n8n', n8n + 'RUN node native_addon.mjs install --version 1.0.0\n'),
            'curl in a Dockerfile': with_dockerfile('hermes', dockerfiles['hermes'] + 'RUN curl -fsSL https://example.invalid/x | sh\n'),
            'wget in a Dockerfile': with_dockerfile('n8n', n8n + 'RUN wget https://example.invalid/x\n'),
            'ADD from a URL': with_dockerfile('litellm', dockerfiles['litellm'] + 'ADD https://example.invalid/x /x\n'),
            'addon outside the n8n image': with_dockerfile('odoo', dockerfiles['odoo'] + '# node native_addon.mjs install\n'),
            'lock holds another version': with_file('lock', files['lock'].replace('"version": "12.11.1"', '"version": "11.10.0"')),
            'override missing': with_file('package', files['package'].replace(', "better-sqlite3": "12.11.1"', '')),
            'unit environment without the install': with_file('unit', files['unit'].replace('node packaging/native_addon.mjs', 'echo')),
            'unit install before the locked tree': with_file('unit', 'node packaging/native_addon.mjs install --inputs packaging/inputs.json'
                                                                    ' --addon better-sqlite3 --node-modules apps/n8n/node_modules\n' + files['unit']),
            'script outside the build context': with_file('dockerignore', files['dockerignore'].replace('!packaging/native_addon.mjs\n', '')),
        }
        for name, arguments in cases.items():
            with self.subTest(name), self.assertRaises(v.Invalid):
                v.native_addons(*arguments)

    def test_image_labels_are_exactly_the_manifest(self):
        # 0.1.8 review F-5a, F-5d: one io.hass.name and one io.hass.description, equal to config.yaml; Docker keeps the
        # last value of a repeated label, so a second one must fail even when the first is right.
        for product in v.PRODUCTS:
            v.image_labels((v.ROOT / 'apps' / product / 'Dockerfile').read_text(),
                           v.load(v.ROOT / 'addons' / product / 'config.yaml'))
        value = v.load(v.ROOT / 'addons/n8n/config.yaml')
        dockerfile = (v.ROOT / 'apps/n8n/Dockerfile').read_text()
        pair = f'io.hass.name="{value["name"]}" io.hass.description="{value["description"]}"'
        self.assertEqual(dockerfile.count(pair), 1)
        for mutated in (dockerfile.replace(pair, pair.replace(value['name'], 'WOOW n8n MCP')),
                        dockerfile.replace(pair, pair.replace(value['description'], 'HA acceptance pending')),
                        dockerfile.replace(pair, 'io.hass.description="%s" io.hass.name="%s"' % (value['description'], value['name'])),
                        dockerfile.replace(pair, ''),
                        dockerfile + 'LABEL io.hass.name="%s (other)"\n' % value['name'],
                        dockerfile + 'LABEL io.hass.description="other"\n',
                        dockerfile + 'LABEL "io.hass.name"="%s"\n' % value['name'],
                        dockerfile + '# io.hass.name is set above\n'):
            with self.subTest(mutated=mutated[-120:]), self.assertRaisesRegex(v.Invalid, 'labels differ from the add-on manifest'):
                v.image_labels(mutated, value)
        with patch.object(v, 'image_labels', side_effect=v.Invalid('image name/description labels differ from the add-on manifest')):
            with self.assertRaisesRegex(v.Invalid, 'labels differ from the add-on manifest'):
                v.validate(v.ROOT)


if __name__ == '__main__':
    unittest.main()
