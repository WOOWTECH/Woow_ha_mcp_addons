"""Offline strict project subset of Supervisor 2026.09.3 store schemas.

Pinned source: 64ea3be4322537fd5dcfbf620c4dc25490c1f56d
supervisor/apps/validate.py:454-557,589-606; store/validate.py:10-17.
Supervisor REMOVE_EXTRA is deliberately replaced with rejection. This is NOT a
vendored/full Supervisor implementation; new fields require explicit review.
"""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess

import yaml

from builder_contract import RUNNER

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ('odoo', 'n8n', 'hermes', 'opendesign', 'emqx', 'litellm', 'nextcloud')  # CI/release build allowlist; nextcloud is first released with 0.1.7 (no image for earlier versions)
# Owner decision 2026-10-06: Odoo Manage is archived. It left the store and no image is built or released again
# (0.1.4 was the last); its source stays in apps/odoo-manage and the shared core, and is still tested.
RETIRED = ('odoo-manage',)
URL = 'https://github.com/WOOWTECH/Woow_ha_mcp_addons'
VERSION = '0.1.8'
TITLES = dict(zip(PRODUCTS, ('Odoo', 'n8n', 'Hermes', 'OpenDesign', 'EMQX', 'LiteLLM', 'Nextcloud')))


class Invalid(ValueError):
    pass


class StrictLoader(yaml.SafeLoader):
    pass


# YAML 1.2 booleans: workflow `on` is a string, never silently boolean True.
StrictLoader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != 'tag:yaml.org,2002:bool']
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
StrictLoader.add_implicit_resolver('tag:yaml.org,2002:bool', re.compile(r'^(?:true|false)$'), list('tf'))


def mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise Invalid('nonstring/duplicate YAML key')
        result[key] = loader.construct_object(value_node)
    return result


StrictLoader.add_constructor('tag:yaml.org,2002:map', mapping)


def load(path):
    text = path.read_text()
    try:
        if any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(text)):
            raise Invalid('YAML aliases are not permitted')
        result = yaml.load(text, Loader=StrictLoader)
    except yaml.YAMLError as exc:
        raise Invalid('invalid YAML') from exc
    if not isinstance(result, dict):
        raise Invalid('expected mapping')
    return result


def require(condition, message):
    if not condition:
        raise Invalid(message)


def exact(value, expected, context):
    # Equality alone accepts true == 1. Compare types recursively as well.
    require(type(value) is type(expected), context + ': wrong type')
    if isinstance(expected, dict):
        require(set(value) == set(expected), context + ': unknown/missing keys')
        for key in expected:
            exact(value[key], expected[key], context + '.' + key)
    elif isinstance(expected, list):
        require(len(value) == len(expected), context + ': wrong length')
        for a, b in zip(value, expected):
            exact(a, b, context)
    else:
        require(value == expected, context + ': unsupported value')


def manifest(value, product):
    require(product in PRODUCTS, 'unsupported product')
    require(isinstance(value.get('ports_description'), dict), 'ports_description mapping required')
    expected = dict(name=f'Woow {TITLES[product]} MCP Server', version=VERSION,
        slug='woow_mcp_' + product.replace('-', '_'), description=value.get('description'),
        url=URL, arch=['amd64'], startup='application', boot='manual', init=True,
        stage='experimental', image=f'ghcr.io/woowtech/{{arch}}-mcp-{product}',
        ingress=True, ingress_port=8099, ingress_entry='/', ingress_stream=True,
        panel_admin=True, panel_icon='mdi:connection', ports={'8081/tcp': None},
        ports_description={'8081/tcp': value.get('ports_description', {}).get('8081/tcp')},
        timeout=30, backup='cold', apparmor=True, options={}, schema={})
    for key in ('host_network', 'host_pid', 'host_ipc', 'host_uts', 'host_dbus',
                'full_access', 'docker_api', 'hassio_api', 'auth_api'):
        expected[key] = False
    # Approved broad-Core capability exception: n8n pilot (2026-10-04) and the other six (owner decision
    # 2026-10-05, 0.1.1) and Nextcloud (owner decision 2026-10-08, 0.1.7). hassio_role remains omitted/default; all
    # other privileges stay closed.
    expected['homeassistant_api'] = True
    for text in (expected['description'], expected['ports_description']['8081/tcp']):
        require(isinstance(text, str) and 1 <= len(text) <= 512, 'missing description')
    exact(value, expected, product)


def translation(value):
    require(set(value) == {'configuration', 'network'}, 'translation unknown/missing scope')
    exact(value['configuration'], {}, 'no deployment options implemented')
    require(isinstance(value['network'], dict) and set(value['network']) == {'8081/tcp'}, 'translation port scope')
    require(isinstance(value['network']['8081/tcp'], str) and bool(value['network']['8081/tcp']), 'translation text')


def clearance_shape(value):
    require(set(value) == {'schema_version', 'approved_commit', 'source', 'license', 'secret', 'publisher', 'products'}, 'clearance keys')
    exact(value['schema_version'], 1, 'clearance schema')
    require(value['approved_commit'] is None or (isinstance(value['approved_commit'], str) and re.fullmatch(r'[0-9a-f]{40}', value['approved_commit'])), 'approved commit')
    require(isinstance(value['products'], dict) and set(value['products']) == set(PRODUCTS), 'clearance product scope')
    gates = [value[k] for k in ('source', 'license', 'secret', 'publisher')]
    for app in PRODUCTS:
        require(set(value['products'][app]) == {'image', 'ha'}, 'per-product clearance keys')
        gates.extend(value['products'][app].values())
    for gate in gates:
        require(isinstance(gate, dict) and set(gate) == {'cleared', 'evidence'}, 'clearance fields')
        require(type(gate['cleared']) is bool, 'clearance boolean')
        require(gate['evidence'] is None or isinstance(gate['evidence'], str), 'evidence type')
        if gate['cleared']:
            require(isinstance(gate['evidence'], str) and bool(re.fullmatch(r'docs/operations/evidence/[a-zA-Z0-9_./-]+\.md', gate['evidence'])) and '..' not in gate['evidence'], 'reviewed checked-in evidence required')


def source_paths(root):
    # Match the store's checkout, not local ignored dependency installations.
    return subprocess.check_output(['git', '-C', str(root), 'ls-files', '--cached', '--others', '--exclude-standard', '-z']).decode().split('\0')[:-1]


def runtime_version(text):
    """0.1.8 (F6): mcp_admin_core.VERSION, the add-on version initialize reports, is bound exactly once, to the release
    VERSION (an annotated, augmented or imported VERSION would rebind it)."""
    bindings = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Assign):
            bindings += [node for target in node.targets for name in ast.walk(target)
                         if isinstance(name, ast.Name) and name.id == 'VERSION']
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name) and node.target.id == 'VERSION':
            bindings.append(node)
        elif isinstance(node, (ast.Import, ast.ImportFrom)) and any((a.asname or a.name) == 'VERSION' for a in node.names):
            bindings.append(node)
    require(len(bindings) == 1 and isinstance(bindings[0], ast.Assign) and len(bindings[0].targets) == 1
            and isinstance(bindings[0].targets[0], ast.Name) and isinstance(bindings[0].value, ast.Constant)
            and bindings[0].value.value == VERSION, 'initialize serverInfo version')


def image_labels(dockerfile, value):
    """0.1.8: exactly one io.hass.name and one io.hass.description in the Dockerfile, equal to the add-on manifest. Docker
    keeps the last value of a repeated label, so a second LABEL (or any other mention) fails (review F-5d)."""
    require(dockerfile.count('io.hass.name') == 1 and dockerfile.count('io.hass.description') == 1
            and f'io.hass.name="{value["name"]}" io.hass.description="{value["description"]}"' in dockerfile,
            'image name/description labels differ from the add-on manifest')


def builder_workflow(value, workflow):
    """Strict builder recipe; runner labels/approval markers are not a sandbox."""
    require('env' not in value and 'defaults' not in value, 'no workflow environment/default injection')
    candidate = value['jobs']['images' if workflow == 'ci' else 'publish']
    exact(candidate['runs-on'], RUNNER, 'dedicated externally approved VM runner')
    require(not any(k in candidate for k in ('container', 'services', 'continue-on-error', 'defaults')),
            'nested runner or bypass denied')
    wanted_env = {'BLD2_APPROVAL': '${{ vars.BLD2_APPROVAL }}',
                  'DOCKER_BUILD_SUMMARY': 'false', 'DOCKER_BUILD_RECORD_UPLOAD': 'false'}
    if workflow == 'release':
        wanted_env['APP'] = '${{ inputs.app }}'
    exact(candidate['env'], wanted_env, 'no ambient builder overrides')
    steps = candidate['steps']

    def action(prefix):
        found = [i for i, step in enumerate(steps) if step.get('uses', '').startswith(prefix + '@')]
        require(len(found) == 1, 'one ' + prefix + ' required')
        index = found[0]
        require(set(steps[index]) <= {'name', 'uses', 'with'}, 'conditional/permissive builder action')
        return index

    def guard(job, phase):
        command = 'python3 packaging/builder_contract.py ' + phase
        found = [i for i, step in enumerate(job['steps']) if step.get('run') == command]
        require(len(found) == 1, 'mandatory builder ' + phase + ' gate')
        require(set(job['steps'][found[0]]) <= {'name', 'run'}, 'builder gate bypass')
        return found[0]

    prepare, verify = guard(candidate, 'prepare'), guard(candidate, 'verify')
    setup = guard(candidate, 'setup --driver docker')
    build = action('docker/build-push-action')
    require(prepare < setup < verify < build, 'builder gates must precede setup/build')
    # Reject later run/action/env injection, not just overrides at setup/build.
    # This list deliberately covers the WHOLE candidate path and late login.
    runs = ['python3 packaging/builder_contract.py prepare',
            'python3 packaging/builder_contract.py setup --driver docker',
            'python3 packaging/builder_contract.py verify']
    python = 'python3' if workflow == 'ci' else 'python'
    runs += [python + ' packaging/install_scanners.py "$RUNNER_TEMP/scanners"',
             python + ' packaging/supply_chain.py candidate "$APP" "$RUNNER_TEMP/scanners" "$RUNNER_TEMP/candidate"']
    uses = ['actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
            'docker/build-push-action@10e90e3645eae34f1e60eeb005ba3a3d33f178e8']
    if workflow == 'release':
        runs = ['python -m pip install --require-hashes --only-binary=:all: -r packaging/requirements-ci.txt',
                'python packaging/validate.py && python packaging/check_release.py "$APP"', *runs,
                'python packaging/registry_gate.py unused "$APP"',
                '\n'.join(['set -eu',
                    'python packaging/supply_chain.py verify "$APP" "$RUNNER_TEMP/candidate"',
                    f'IMAGE="ghcr.io/woowtech/amd64-mcp-$APP:{VERSION}"',
                    'TESTED_ID="$(python -c \'import json,sys; print(json.load(open(sys.argv[1]))["image_id"])\' "$RUNNER_TEMP/candidate/subject.json")"',
                    'docker tag "$TESTED_ID" "$IMAGE"',
                    'test "$(docker image inspect "$IMAGE" --format \'{{.Id}}\')" = "$TESTED_ID"',
                    'docker push "$IMAGE"']),
                'python packaging/registry_gate.py public "$APP" "$RUNNER_TEMP/candidate"']
        uses.insert(1, 'actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1')
        uses += ['docker/login-action@c94ce9fb468520275223c153574b00df6fe4bcc9',
                 'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02']
    exact([s['run'].strip() for s in steps if 'run' in s], runs,
          'reviewed run sequence only; no GITHUB_ENV/PATH or shell overrides')
    exact([s['uses'] for s in steps if 'uses' in s], uses,
          'reviewed actions only; no Buildx downloader/overwrite')
    for step in steps:
        require(set(step) <= ({'name', 'run', 'env'} if 'run' in step else {'name', 'uses', 'with'}),
                'step environment/default/bypass injection')
        wanted = {}
        if workflow == 'ci' and 'supply_chain.py candidate' in step.get('run', ''):
            wanted = {'APP': '${{ matrix.app }}'}
        if workflow == 'release' and 'registry_gate.py unused' in step.get('run', ''):
            wanted = {'GHCR_TOKEN': '${{ secrets.GITHUB_TOKEN }}'}
        exact(step.get('env', {}), wanted, 'step environment cannot override isolation')
    if workflow == 'release':
        login = action('docker/login-action')
        candidate_scan = next(i for i, s in enumerate(steps) if 'supply_chain.py candidate' in s.get('run', ''))
        unused = next(i for i, s in enumerate(steps) if 'registry_gate.py unused' in s.get('run', ''))
        push = next(i for i, s in enumerate(steps) if 'docker push' in s.get('run', ''))
        require(build < candidate_scan < unused < login < push, 'credentials only after candidate acceptance')
        exact(steps[login]['with'], {'registry': 'ghcr.io', 'username': '${{ github.actor }}',
              'password': '${{ secrets.GITHUB_TOKEN }}'}, 'late GHCR login only')
    app = '${{ matrix.app }}' if workflow == 'ci' else '${{ inputs.app }}'
    exact(steps[build]['with'], {'builder': 'default', 'provenance': False, 'sbom': False,
          'context': '.', 'file': 'apps/' + app + '/Dockerfile', 'platforms': 'linux/amd64',
          'push': False, 'load': True, 'tags': 'local/mcp-' + app + ':' + VERSION,
          'build-args': 'BUILD_VERSION=' + VERSION,
          'labels': 'org.opencontainers.image.revision=${{ github.sha }}'}, 'fixed local candidate build')
    admission = value['jobs']['builder-admission' if workflow == 'ci' else 'gate']
    guard(admission, 'admit')
    exact(admission['runs-on'], 'ubuntu-24.04', 'admit before external scheduling')
    exact(admission['env'], {'BLD2_APPROVAL': '${{ vars.BLD2_APPROVAL }}'}, 'operator approval input')
    require('continue-on-error' not in admission and 'container' not in admission
            and 'services' not in admission, 'admission bypass/nesting')
    if workflow == 'ci':
        require('if' not in admission and 'if' not in candidate, 'CI denial must not be a skipped PASS')
        exact(candidate['needs'], ['unit', 'builder-admission'], 'mandatory admission dependency')
        exact(candidate['environment'], 'builder-candidate', 'protected candidate environment')
        exact(candidate['strategy']['max-parallel'], 1, 'bounded runner allocation')
        require('needs' not in value['jobs']['unit'], 'local unit job independent of builder approval')
    else:
        exact(candidate['needs'], 'gate', 'release admission dependency')


def validate(root=ROOT):
    exact(load(root / 'repository.yaml'), {'name': 'WOOW MCP Add-ons (experimental)', 'url': URL, 'maintainer': 'WOOWTECH'}, 'repository')
    paths = source_paths(root)
    app_scopes = {Path(p).parts[1] for p in paths if p.startswith('apps/') and len(Path(p).parts) > 1}
    require(app_scopes == set(PRODUCTS) | set(RETIRED) | {'runtime'}, 'application source scope')
    inputs = load(root / 'packaging/inputs.json')
    exact(inputs['products'], list(PRODUCTS), 'build allowlist')
    exact(inputs['version'], VERSION, 'build version')
    runtime_version((root / 'packages/mcp-admin-core/mcp_admin_core/__init__.py').read_text())
    exact(inputs['supervisor'], {'version': '2026.09.3', 'commit': '64ea3be4322537fd5dcfbf620c4dc25490c1f56d'}, 'Supervisor schema pin')
    require(set(inputs['bases']) == {'python', 'node', 'uv'}, 'base allowlist')
    for image in inputs['bases'].values():
        require(bool(re.fullmatch(r'[a-z0-9/.-]+:[a-z0-9.-]+@sha256:[0-9a-f]{64}', image)), 'base must be exact version plus digest')
    discovered = {p for p in paths if Path(p).name in ('config.yaml', 'config.yml', 'config.json') and not any(x.startswith('.') or x == 'rootfs' for x in Path(p).parts)}
    require(discovered == {f'addons/{p}/config.yaml' for p in PRODUCTS}, 'accidental/missing Supervisor config discovery')
    require({p.name for p in (root / 'addons').iterdir()} == set(PRODUCTS), 'addon directory allowlist')
    slugs = set()
    for product in PRODUCTS:
        path = root / 'addons' / product
        value = load(path / 'config.yaml')
        manifest(value, product)
        require(value['slug'] not in slugs, 'duplicate slug')
        slugs.add(value['slug'])
        require({p.name for p in (path / 'translations').iterdir()} == {'en.yaml', 'zh-Hant.yaml'}, 'translation language allowlist')
        for lang in ('en', 'zh-Hant'):
            translation(load(path / 'translations' / (lang + '.yaml')))
        for doc in ('README.md', 'DOCS.md', 'CHANGELOG.md'):
            require((path / doc).is_file() and (path / doc).stat().st_size > 150, 'missing product document')
        dockerfile = (root / 'apps' / product / 'Dockerfile').read_text()
        bases = json.loads((root / 'packaging/inputs.json').read_text())['bases']
        for line in dockerfile.splitlines():
            if line.startswith('FROM '):
                require(line.split()[1] in bases.values(), 'unreviewed FROM')
        require('COPY apps/runtime ./apps/runtime' in dockerfile, 'missing scoped runtime helpers')
        require(f"FROM {bases['node']} AS ui" in dockerfile
                and 'COPY packages/mcp-admin-ui/package.json packages/mcp-admin-ui/package-lock.json ./' in dockerfile
                and 'RUN npm ci --ignore-scripts --no-audit --no-fund' in dockerfile
                and 'RUN npm run build' in dockerfile
                and 'COPY --from=ui /ui/dist ./packages/mcp-admin-ui/dist' in dockerfile,
                'pinned complete UI build/runtime closure missing')
        require('COPY packages/mcp-admin-ui ./packages/mcp-admin-ui' not in dockerfile, 'UI test/source runtime copy')
        require('COPY packaging/entrypoint.py packaging/management_launcher.py ./packaging/' in dockerfile,
                'post-exec management credential guard missing')
        require('EXPOSE 8081\n' in dockerfile and 'EXPOSE 3000' not in dockerfile and 'EXPOSE 8099' not in dockerfile, 'port scope')
        require('COPY apps/ ./apps/' not in dockerfile and 'COPY . .' not in dockerfile, 'broad app copy')
        require('io.hass.type="app"' in dockerfile and 'io.hass.arch="amd64"' in dockerfile, 'HA labels')
        image_labels(dockerfile, value)
        require('uv sync --frozen --no-dev' in dockerfile, 'unlocked core')
        if product == 'n8n':
            require('npm ci --ignore-scripts --no-audit --no-fund' in dockerfile, 'unlocked/scripted npm')
        else:
            require(f'uv sync --project apps/{product} --frozen --no-dev' in dockerfile, 'missing isolated child lock')
    require('!packaging/management_launcher.py' in (root / '.dockerignore').read_text(), 'guard excluded from context')
    context = (root / '.dockerignore').read_text()
    for path in ('package.json', 'package-lock.json', 'NOTICE.txt', 'src/*.js', 'src/*.css', 'src/*.html', 'scripts/build.mjs'):
        require('!packages/mcp-admin-ui/' + path in context, 'UI input excluded')
    require('!packages/mcp-admin-ui/**' not in context, 'broad UI context')
    scanner_pins = load(root / 'packaging/scanner-pins.json')
    require(set(scanner_pins) == {'gitleaks', 'syft', 'grype'}, 'scanner set drift')
    for pin in scanner_pins.values():
        require(bool(re.fullmatch(r'[0-9a-f]{64}', pin['sha256'])), 'scanner archive hash')
        require(pin['url'].startswith('https://github.com/') and '/v' + pin['version'] + '/' in pin['url'], 'scanner immutable release URL')
    gates = load(root / 'RELEASE-GATES.json')
    clearance_shape(gates)
    for workflow in ('ci', 'release'):
        value = load(root / '.github/workflows' / (workflow + '.yaml'))
        builder_workflow(value, workflow)
        for name, job in value['jobs'].items():
            if name not in ('images', 'publish'):
                exact(job['runs-on'], 'ubuntu-24.04', 'isolated hosted unit/admission runner')
            require(type(job['timeout-minutes']) is int and 1 <= job['timeout-minutes'] <= 40, 'bounded job')
            for step in job['steps']:
                if step.get('uses', '').startswith('actions/checkout@'):
                    exact(step['with']['persist-credentials'], False, 'checkout credential persistence')
                if step.get('uses', '').startswith('docker/build-push-action@'):
                    for key, wanted in {'context': '.', 'platforms': 'linux/amd64', 'push': False, 'load': True, 'build-args': 'BUILD_VERSION=' + VERSION}.items():
                        exact(step['with'][key], wanted, 'build ' + key)
        exact(value['permissions'], {'contents': 'read'}, workflow + ' default permissions')
        require('pull_request_target' not in value['on'], 'unsafe event')
        text = (root / '.github/workflows' / (workflow + '.yaml')).read_text()
        for use in re.findall(r'uses:\s*([^\s]+)', text):
            require(bool(re.fullmatch(r'[\w-]+/[\w-]+@[0-9a-f]{40}', use)), 'unpinned action')
        candidate_job = value['jobs']['images' if workflow == 'ci' else 'publish']
        candidate_steps = candidate_job['steps']
        require(sum(step.get('uses', '').startswith('docker/build-push-action@') for step in candidate_steps) == 1,
                'candidate must build once')
        require(any('supply_chain.py candidate' in step.get('run', '') for step in candidate_steps), 'missing exact-candidate scan/test gate')
        require(any('install_scanners.py' in step.get('run', '') for step in candidate_steps), 'missing pinned tools')
        require(candidate_job['env']['DOCKER_BUILD_RECORD_UPLOAD'] == 'false'
                and candidate_job['env']['DOCKER_BUILD_SUMMARY'] == 'false', 'unscanned build artifacts enabled')
        for step in candidate_steps:
            if step.get('uses', '').startswith('actions/checkout@'):
                exact(step['with']['fetch-depth'], 0, 'complete publishable history required')
        if workflow == 'ci':
            require('secrets.' not in text and 'packages: write' not in text and 'push: true' not in text, 'CI publication authority')
            exact(value['jobs']['images']['strategy']['matrix']['app'], list(PRODUCTS), 'CI matrix')
        else:
            require(set(value['on']) == {'workflow_dispatch'}, 'release must be manual')
            require('supply_chain.py verify' in text and 'registry_gate.py public' in text
                    and 'published-provenance.json' in text and 'sbom.spdx.json' in text,
                    'missing exact-artifact prepush/postpush/persistence enforcement')
            exact(value['jobs']['publish']['environment'], 'public-release', 'protected environment name')
            exact(value['on']['workflow_dispatch']['inputs']['app']['options'], list(PRODUCTS), 'release allowlist')
            exact(value['jobs']['publish']['permissions'], {'contents': 'read', 'packages': 'write'}, 'minimal publisher authority')
            for job in value['jobs'].values():
                exact(job['if'], "github.ref == 'refs/heads/main'", 'main-only release')
                for step in job['steps']:
                    if step.get('uses', '').startswith('actions/checkout@'):
                        exact(step['with']['ref'], '${{ github.sha }}', 'no arbitrary release checkout')
    print('PASS: seven strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    try:
        validate(parser.parse_args().root)
    except (Invalid, KeyError, TypeError) as exc:
        raise SystemExit('packaging validation failed: ' + str(exc)) from None
