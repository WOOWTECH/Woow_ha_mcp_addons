"""Offline strict project subset of Supervisor 2026.09.3 store schemas.

Pinned source: 64ea3be4322537fd5dcfbf620c4dc25490c1f56d
supervisor/apps/validate.py:454-557,589-606; store/validate.py:10-17.
Supervisor REMOVE_EXTRA is deliberately replaced with rejection. This is NOT a
vendored/full Supervisor implementation; new fields require explicit review.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ('odoo', 'odoo-manage', 'n8n', 'hermes', 'opendesign', 'emqx', 'litellm')
URL = 'https://github.com/WOOWTECH/Woow_ha_mcp_addons'
VERSION = '0.1.0'
TITLES = dict(zip(PRODUCTS, ('Odoo', 'Odoo Manage', 'n8n', 'Hermes', 'OpenDesign', 'EMQX', 'LiteLLM')))


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
    expected = dict(name=f'WOOW {TITLES[product]} MCP (experimental)', version=VERSION,
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
    # Approved broad-Core capability exception: new n8n pilot ONLY.
    # hassio_role remains omitted/default; all other privileges stay closed.
    expected['homeassistant_api'] = product == 'n8n'
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


def validate(root=ROOT):
    exact(load(root / 'repository.yaml'), {'name': 'WOOW MCP Add-ons (experimental / blocked)', 'url': URL, 'maintainer': 'WOOWTECH'}, 'repository')
    paths = source_paths(root)
    app_scopes = {Path(p).parts[1] for p in paths if p.startswith('apps/') and len(Path(p).parts) > 1}
    require(app_scopes == set(PRODUCTS) | {'runtime'}, 'application source scope')
    inputs = load(root / 'packaging/inputs.json')
    exact(inputs['products'], list(PRODUCTS), 'build allowlist')
    exact(inputs['version'], VERSION, 'build version')
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
        for job in value['jobs'].values():
            exact(job['runs-on'], 'ubuntu-24.04', 'isolated hosted runner')
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
