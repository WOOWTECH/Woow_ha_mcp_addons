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
PRODUCTS = ('odoo', 'n8n', 'hermes', 'opendesign', 'emqx', 'litellm', 'nextcloud', 'headscale')
# Owner decision 2026-10-06: Odoo Manage is archived. It left the store and no image is built or released again
# (0.1.4 was the last); its source stays in apps/odoo-manage and the shared core, and is still tested.
RETIRED = ('odoo-manage',)
URL = 'https://github.com/WOOWTECH/Woow_ha_mcp_addons'
VERSION = '0.4.15'
# Products on a version line of their own; every other product ships VERSION. A version bump changes this data and the
# files validate() binds to it (manifest, Dockerfile default, inputs.json, core PRODUCT_VERSIONS). The workflows'
# version expressions are generated from it (version_expression) and compared verbatim (HM-17).
VERSION_OVERRIDES = {'odoo': '0.5.2', 'emqx': '0.5.1', 'litellm': '0.5.1', 'nextcloud': '0.5.1', 'headscale': '0.5.0', 'hermes': '0.5.0', 'n8n': '0.5.0'}
TITLES = dict(zip(PRODUCTS, ('Odoo', 'n8n', 'Hermes', 'OpenDesign', 'EMQX', 'LiteLLM', 'Nextcloud', 'Headscale')))
# The app a builder workflow builds: ci.yaml's matrix, release.yaml's dispatch input.
SELECTORS = {'ci': 'matrix.app', 'release': 'inputs.app'}


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def version_for(product):
    require(product in PRODUCTS, 'unsupported product version')
    return VERSION_OVERRIDES.get(product, VERSION)


def version_expression(selector, overrides=None, default=None):
    """HM-17: the GitHub Actions value of the version that `selector` (SELECTORS) builds, generated from the release data
    (default: VERSION_OVERRIDES and VERSION). One `<selector> == '<product>' && '<version>'` arm per override, in
    PRODUCTS order, joined by `||`, then the default: `&&` binds tighter than `||` and a version is never empty, so
    the product's arm gives its version and every other app falls through to the default. That is the two-way form the
    workflows carry since 0.4.14, chained; no fromJSON or other syntax these workflows never ran (C4-SF-1). Without an
    override it is the bare default, the form before 0.4.14."""
    overrides = VERSION_OVERRIDES if overrides is None else overrides
    default = VERSION if default is None else default
    require(selector in SELECTORS.values(), 'unsupported version selector')
    require(isinstance(overrides, dict) and set(overrides) <= set(PRODUCTS), 'version override outside the products')
    for version in (default, *overrides.values()):
        require(isinstance(version, str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version) is not None,
                'release version is not x.y.z')
    require(default not in overrides.values(), 'version override equal to the default version')
    if not overrides:
        return default
    arms = [f"{selector} == '{product}' && '{overrides[product]}'" for product in PRODUCTS if product in overrides]
    return '${{ ' + ' || '.join([*arms, f"'{default}'"]) + ' }}'


# Generated when the module loads, so release data a version expression cannot carry stops every packaging tool that
# imports this module (check_release, supply_chain, registry_gate, container_acceptance, pilot_variant, j1900_check) with
# the validator's one-line message instead of a traceback.
try:
    CI_VERSION = version_expression(SELECTORS['ci'])
    RELEASE_VERSION = version_expression(SELECTORS['release'])
except Invalid as error:
    raise SystemExit('packaging validation failed: ' + str(error)) from None


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
    expected = dict(name=f'Woow {TITLES[product]} MCP Server', version=version_for(product),
        slug='woow_mcp_' + product.replace('-', '_'), description=value.get('description'),
        url=URL, arch=['amd64'], startup='application', boot='auto', init=True,
        stage='stable', image=f'ghcr.io/woowtech/{{arch}}-mcp-{product}',
        ingress=True, ingress_port=8099, ingress_stream=True,
        panel_admin=True, panel_icon='mdi:connection', ports={'8081/tcp': None},
        ports_description={'8081/tcp': value.get('ports_description', {}).get('8081/tcp')},
        timeout=30, backup='cold', apparmor=True, options={}, schema={})
    for key in ('host_network', 'host_pid', 'host_ipc', 'host_uts', 'host_dbus',
                'full_access', 'docker_api', 'hassio_api', 'auth_api'):
        expected[key] = False
    # Approved broad-Core capability exception: n8n pilot (2026-10-04), the other original products
    # (owner decision 2026-10-05, 0.1.1), and Nextcloud (2026-10-08, 0.1.7). Headscale follows the
    # same admin verifier contract, with independent image/HA gates. hassio_role stays omitted/default;
    # every other privilege remains closed.
    expected['homeassistant_api'] = True
    for text in (expected['description'], expected['ports_description']['8081/tcp']):
        require(isinstance(text, str) and 1 <= len(text) <= 512, 'missing description')
    # 0.1.12: no ingress_entry. Supervisor 2026.09 builds ingress_url as f"/api/hassio_ingress/{token}/{ingress_entry}", so
    # the former ingress_entry '/' made the HA sidebar open .../<token>// (404 in every MCP admin UI). The default
    # (key absent) is the root; exact() rejects the key if it ever comes back.
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
    overrides = [node for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'PRODUCT_VERSIONS' for target in node.targets)]
    require(len(overrides) == 1 and ast.literal_eval(overrides[0].value) == VERSION_OVERRIDES,
            'fixed per-product runtime version')


def image_labels(dockerfile, value):
    """0.1.8: exactly one io.hass.name and one io.hass.description in the Dockerfile, equal to the add-on manifest. Docker
    keeps the last value of a repeated label, so a second LABEL (or any other mention) fails (review F-5d)."""
    require(dockerfile.count('io.hass.name') == 1 and dockerfile.count('io.hass.description') == 1
            and f'io.hass.name="{value["name"]}" io.hass.description="{value["description"]}"' in dockerfile,
            'image name/description labels differ from the add-on manifest')


def build_version_default(dockerfile, product):
    """HM-17 (C4-SF-2): one ARG BUILD_VERSION whose default is the product's release version, and one io.hass.version
    label that uses it. The default is the image's version whenever no build-arg sets it, every release bumps it with
    the other bindings (release-decision-0.4.4.md), and container acceptance requires io.hass.version ==
    version_for(app) (container_acceptance.py): a stale default fails here instead of on the out-of-repo builder."""
    require(dockerfile.count('ARG BUILD_VERSION') == 1 and f'\nARG BUILD_VERSION={version_for(product)}\n' in dockerfile
            and dockerfile.count('io.hass.version=') == 1 and 'io.hass.version="${BUILD_VERSION}"' in dockerfile,
            'Dockerfile build version default differs from the release version')


def unit_child_sync(text):
    """The standalone source gate must install every isolated Python child."""
    loops = re.findall(r'^for app in ([a-z0-9 -]+); do\n  uv sync --project "apps/\$app" '
                       r'--frozen --no-dev --python python3\.13\ndone$', text, re.M)
    require(len(loops) == 1, 'one frozen child sync loop required in unit.sh')
    apps = loops[0].split()
    require(len(apps) == len(set(apps)) and set(apps) == (set(PRODUCTS) | set(RETIRED)) - {'n8n'},
            'unit.sh isolated child scope')


def workflow_strings(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from workflow_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from workflow_strings(item)
    elif isinstance(value, str):
        yield value


def workflow_versions(value, workflow):
    """HM-17: every expression of a builder workflow that reads the app, other than the app itself, is exactly the
    version expression generated from VERSION_OVERRIDES, wherever it is (a stale, hand-written or second selection
    fails), and release.yaml's published evidence is named with it. The other places (candidate tags and build-args,
    the pushed IMAGE) are part of the fixed recipe below."""
    selector, wanted = SELECTORS[workflow], CI_VERSION if workflow == 'ci' else RELEASE_VERSION
    # matrix.app, inputs.app, github.event.inputs.app, and the same with ['app']; GitHub ignores case in names.
    reads = re.compile(r"(?<![\w.-])(?:github\.event\.)?(?:matrix|inputs)(?:\.app|\[\s*'app'\s*\])(?![\w-])", re.I)
    for text in workflow_strings(value):
        for match in re.finditer(r'\$\{\{(.*?)\}\}', text, re.S):
            if match.group(1).strip() != selector and reads.search(match.group(1)):
                require(match.group(0) == wanted, workflow + '.yaml: the version expression generated from '
                        'VERSION_OVERRIDES is ' + wanted)
    if workflow == 'release':
        uploads = [step for step in value['jobs']['publish']['steps']
                   if step.get('uses', '').startswith('actions/upload-artifact@')]
        require(len(uploads) == 1, 'one published evidence upload')
        exact(uploads[0]['with']['name'], 'published-evidence-${{ inputs.app }}-' + RELEASE_VERSION + '-${{ github.sha }}',
              'published evidence named with the release version')


# release.yaml, the GitHub-hosted route (owner decision 2026-11-17; docs/operations/release.md): gate, then candidate,
# then publish, compared with this recipe step by step; the workflow name and the step names are free text without
# expressions or secrets. Its only environment variables: candidate's APP and Docker build-record switches, publish's
# APP, SOURCE_SHA on the three check_release steps (gate's also has APP), GH_TOKEN on the two environment_gate steps,
# RUNNER_KIND on the two runner preflights, EXPECTED_IMAGE_ID on the image load and GHCR_TOKEN on the registry
# precondition. Its only secret is the run's own GITHUB_TOKEN, as exactly those GH_TOKEN and GHCR_TOKEN values and the
# registry login password.
RELEASE_RUN_NAME = 'Publish ${{ inputs.app }} from ${{ github.ref_name }} at ${{ inputs.source_sha }}'
RELEASE_BRANCHES = "startsWith(github.ref, 'refs/heads/release/')"
# gate: the PR checks job's source gate window (DQ-43); candidate: cold build, candidate gate, the J1900 check (its own
# 60-minute budget) and the handover; publish: load, registry checks and the push.
RELEASE_MINUTES = {'gate': 60, 'candidate': 150, 'publish': 60}
# actions read: environment_gate.py reads the public-release settings (gate, publish) and this run's approvals (publish).
RELEASE_PERMISSIONS = {'gate': {'contents': 'read', 'actions': 'read'}, 'candidate': {'contents': 'read'},
                       'publish': {'contents': 'read', 'packages': 'write', 'actions': 'read'}}
RELEASE_JOB_KEYS = {'gate': {'runs-on', 'permissions', 'timeout-minutes', 'steps'},
                    'candidate': {'needs', 'if', 'permissions', 'runs-on', 'timeout-minutes', 'outputs', 'env', 'steps'},
                    'publish': {'needs', 'if', 'environment', 'permissions', 'runs-on', 'timeout-minutes', 'env', 'steps'}}
RELEASE_TOKEN = '${{ secrets.GITHUB_TOKEN }}'
# Any secret or the run token, in any spelling GitHub expressions accept (contexts are case-insensitive).
SECRETISH = re.compile(r'secrets|github\s*(?:\.\s*token\b|\[\s*[\'"]token[\'"]\s*\])', re.I)
CANDIDATE_EVIDENCE = ('candidate/subject.json', 'candidate/sbom.syft.json', 'candidate/sbom.spdx.json',
                      'candidate/scan-summary.json', 'candidate/provenance.json')
RUNNER_EVIDENCE = ('release-evidence/hosted-runner.json', 'release-evidence/j1900-${{ inputs.app }}.json')
# In the publish job the candidate evidence artifact is downloaded into its own directory, RUNNER_TEMP/candidate-evidence
# (review round 2: never next to the runner's own files in RUNNER_TEMP).
DOWNLOADED = 'candidate-evidence/'
PUBLISHED_EVIDENCE = (*(DOWNLOADED + name for name in CANDIDATE_EVIDENCE),
                      DOWNLOADED + 'candidate/published-provenance.json', DOWNLOADED + 'candidate/published-digest.json',
                      *(DOWNLOADED + name for name in RUNNER_EVIDENCE), 'handoff/handoff.json',
                      'publish-evidence/approval.json', 'publish-evidence/hosted-runner.json')
# The gate's Node pin, the same script as ci.yaml's unit job and the PR checks job (release.md, "PR/main CI", item 3).
NODE_PATH_PIN = '\n'.join([
    'test "$(node --version)" = v26.13.1',
    'NODE_BIN="$(readlink -f "$(command -v node)")"',
    'if [ "$NODE_BIN" != /usr/bin/node ]; then sudo ln -sfn "$NODE_BIN" /usr/bin/node; fi',
    'test "$(/usr/bin/node --version)" = v26.13.1',
    "# 0.4.0: unit.sh runs pytest under sudo, whose secure PATH finds the runner's own /usr/local/bin/node (v22) first,",
    '# and the n8n child takes node from that PATH (as in the image, /usr/local/bin/node): pin it to the same binary.',
    'if [ "$NODE_BIN" != /usr/local/bin/node ]; then sudo ln -sfn "$NODE_BIN" /usr/local/bin/node; fi',
    'test "$(sudo -n -- node --version)" = v26.13.1'])


def runner_paths(names):
    return ''.join('${{ runner.temp }}/' + name + '\n' for name in names)


def release_recipe():
    """{job: its steps without names} of release.yaml, generated when called: the version expression is RELEASE_VERSION
    (VERSION_OVERRIDES). Run scripts are compared without their surrounding whitespace."""
    checkout = {'uses': 'actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
                'with': {'persist-credentials': False, 'ref': '${{ github.sha }}', 'fetch-depth': 0}}
    python = {'uses': 'actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1', 'with': {'python-version': '3.13.16'}}
    pip = {'run': 'python -m pip install --require-hashes --only-binary=:all: -r packaging/requirements-ci.txt'}
    source_sha = {'SOURCE_SHA': '${{ inputs.source_sha }}'}
    admission = {'env': source_sha, 'run': 'python packaging/validate.py && python packaging/check_release.py "$APP"'}
    upload = 'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02'
    # download-artifact v4.3.0 (formal release, lightweight tag -> this commit), the pair of upload-artifact v4.6.2.
    download = 'actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093'
    image = 'candidate-image-${{ inputs.app }}-${{ github.sha }}'
    evidence = 'candidate-evidence-${{ inputs.app }}-${{ github.sha }}'
    version = RELEASE_VERSION
    gate = [checkout, python, pip,
            {'env': {'APP': '${{ inputs.app }}', **source_sha}, 'run': 'python packaging/check_release.py "$APP"'},
            {'env': {'GH_TOKEN': RELEASE_TOKEN}, 'run': 'python packaging/environment_gate.py gate'},
            {'run': 'python packaging/validate.py'},
            {'uses': 'actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020', 'with': {'node-version': '26.13.1'}},
            {'uses': 'astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78',
             'with': {'version': '0.12.10', 'enable-cache': False}},
            {'run': '\n'.join(['uv sync --frozen --no-dev --python python3.13',
                               'uv pip install --python .venv/bin/python --require-hashes --only-binary=:all: '
                               '-r packaging/requirements-ci.txt',
                               ".venv/bin/python -m unittest discover -s packaging -p 'test_*.py' -v"])},
            {'run': NODE_PATH_PIN},
            {'run': 'sh packaging/unit.sh'}]
    candidate = [checkout, python, pip, admission,
                 {'env': {'RUNNER_KIND': '${{ runner.environment }}'},
                  'run': 'python packaging/hosted_runner.py "$RUNNER_KIND" "$RUNNER_TEMP/release-evidence/hosted-runner.json"'},
                 {'uses': 'docker/build-push-action@10e90e3645eae34f1e60eeb005ba3a3d33f178e8',
                  'with': {'builder': 'default', 'provenance': False, 'sbom': False, 'context': '.',
                           'file': 'apps/${{ inputs.app }}/Dockerfile', 'platforms': 'linux/amd64', 'push': False,
                           'load': True, 'tags': 'local/mcp-${{ inputs.app }}:' + version,
                           'build-args': 'BUILD_VERSION=' + version,
                           'labels': 'org.opencontainers.image.revision=${{ github.sha }}'}},
                 {'run': 'python packaging/install_scanners.py "$RUNNER_TEMP/scanners"'},
                 {'run': 'python packaging/supply_chain.py candidate "$APP" "$RUNNER_TEMP/scanners" "$RUNNER_TEMP/candidate"'},
                 {'run': 'python packaging/j1900_check.py "$APP" "$RUNNER_TEMP/candidate" "$RUNNER_TEMP/release-evidence"'},
                 {'id': 'handoff',
                  'run': 'python packaging/image_handoff.py save "$APP" "$RUNNER_TEMP/candidate" "$RUNNER_TEMP/handoff"'},
                 {'uses': upload, 'with': {'name': image, 'path': runner_paths(('handoff/image.tar', 'handoff/handoff.json')),
                                           'if-no-files-found': 'error', 'retention-days': 3}},
                 {'uses': upload, 'with': {'name': evidence, 'path': runner_paths(CANDIDATE_EVIDENCE + RUNNER_EVIDENCE),
                                           'if-no-files-found': 'error', 'retention-days': 90}}]
    publish = [checkout, python, pip, admission,
               {'env': {'GH_TOKEN': RELEASE_TOKEN},
                'run': 'python packaging/environment_gate.py publish "$RUNNER_TEMP/publish-evidence/approval.json"'},
               {'env': {'RUNNER_KIND': '${{ runner.environment }}'},
                'run': 'python packaging/hosted_runner.py "$RUNNER_KIND" "$RUNNER_TEMP/publish-evidence/hosted-runner.json"'},
               {'uses': download, 'with': {'name': image, 'path': '${{ runner.temp }}/handoff'}},
               {'uses': download, 'with': {'name': evidence, 'path': '${{ runner.temp }}/candidate-evidence'}},
               {'env': {'EXPECTED_IMAGE_ID': '${{ needs.candidate.outputs.image_id }}'},
                'run': 'python packaging/image_handoff.py load "$APP" "$RUNNER_TEMP/handoff" "$RUNNER_TEMP/candidate-evidence"'},
               {'run': 'python packaging/supply_chain.py verify "$APP" "$RUNNER_TEMP/candidate-evidence/candidate"'},
               {'env': {'GHCR_TOKEN': RELEASE_TOKEN}, 'run': 'python packaging/registry_gate.py unused "$APP"'},
               {'uses': 'docker/login-action@c94ce9fb468520275223c153574b00df6fe4bcc9',
                'with': {'registry': 'ghcr.io', 'username': '${{ github.actor }}', 'password': RELEASE_TOKEN}},
               {'run': '\n'.join(['set -eu',
                                  'python packaging/supply_chain.py verify "$APP" "$RUNNER_TEMP/candidate-evidence/candidate"',
                                  f'IMAGE="ghcr.io/woowtech/amd64-mcp-$APP:{version}"',
                                  'TESTED_ID="$(python -c \'import json,sys; print(json.load(open(sys.argv[1]))["image_id"])\' '
                                  '"$RUNNER_TEMP/candidate-evidence/candidate/subject.json")"',
                                  'docker tag "$TESTED_ID" "$IMAGE"',
                                  'test "$(docker image inspect "$IMAGE" --format \'{{.Id}}\')" = "$TESTED_ID"',
                                  'docker push "$IMAGE"'])},
               {'run': 'python packaging/registry_gate.py public "$APP" "$RUNNER_TEMP/candidate-evidence/candidate"'},
               {'uses': upload,
                'with': {'name': 'published-evidence-${{ inputs.app }}-' + version + '-${{ github.sha }}',
                         'path': runner_paths(PUBLISHED_EVIDENCE), 'if-no-files-found': 'error', 'retention-days': 90}}]
    return {'gate': gate, 'candidate': candidate, 'publish': publish}


def field(value, *keys):
    for key in keys:
        require(isinstance(value, dict) and key in value, 'release.yaml: missing ' + '.'.join(keys))
        value = value[key]
    return value


def free_text(text, what):
    """Step names and input descriptions are shown, not run: no expression, secret or token in them (review L3)."""
    require(isinstance(text, str) and 1 <= len(text) <= 200 and '${{' not in text and not SECRETISH.search(text),
            what + ': free text without ${{ }}, secrets or the token')


def hosted_release(value):
    """release.yaml is exactly the GitHub-hosted route: a manual dispatch with app and source_sha; gate (contents and
    actions read, no condition: check_release.py refuses every other ref) checks the dispatch, the public-release
    environment and the source; candidate (contents read only, no environment) builds, accepts, J1900-checks and hands
    over the tested image ID; publish (public-release, contents read, packages write, actions read) loads exactly that
    image ID after the owner's approval and pushes it. All three run on GitHub-hosted ubuntu-24.04, on release/* only,
    with the reviewed steps in order. The environment's reviewers and branch rule are repository settings: this checks
    the file, environment_gate.py checks the settings when the run starts (docs/operations/release.md)."""
    workflow_versions(value, 'release')
    require(isinstance(value, dict) and set(value) == {'name', 'run-name', 'on', 'permissions', 'concurrency', 'jobs'},
            'release.yaml keys (no workflow environment/default injection)')
    free_text(value['name'], 'release workflow name')
    exact(value['run-name'], RELEASE_RUN_NAME, 'release run name')
    inputs = field(value, 'on', 'workflow_dispatch', 'inputs')
    described = {name: field(inputs, name, 'description') for name in ('app', 'source_sha')}
    for name, text in described.items():
        free_text(text, 'release input description ' + name)
    exact(value['on'], {'workflow_dispatch': {'inputs': {
        'app': {'description': described['app'], 'type': 'choice', 'required': True, 'options': list(PRODUCTS)},
        'source_sha': {'description': described['source_sha'], 'type': 'string', 'required': True}}}},
        'release must be a manual dispatch with app and source_sha only')
    exact(value['permissions'], {'contents': 'read'}, 'release default permissions')
    exact(value['concurrency'], {'group': 'public-release-${{ inputs.app }}', 'cancel-in-progress': False},
          'one release group per product; a run in progress is never cancelled')
    jobs = value['jobs']
    require(isinstance(jobs, dict) and set(jobs) == set(RELEASE_JOB_KEYS), 'release jobs are gate, candidate, publish')
    for name, keys in RELEASE_JOB_KEYS.items():
        require(isinstance(jobs[name], dict) and set(jobs[name]) == keys,
                name + ' job keys (no other condition, environment, container, services, strategy, defaults or bypass)')
        exact(jobs[name]['runs-on'], 'ubuntu-24.04', 'GitHub-hosted ' + name + ' runner')
        exact(jobs[name]['permissions'], RELEASE_PERMISSIONS[name], name + ' authority')
        exact(jobs[name]['timeout-minutes'], RELEASE_MINUTES[name], name + ' time limit')
    candidate, publish = jobs['candidate'], jobs['publish']
    exact(candidate['needs'], 'gate', 'candidate after the gate')
    exact(candidate['if'], RELEASE_BRANCHES, 'candidate from release/* branches only')
    exact(candidate['outputs'], {'image_id': '${{ steps.handoff.outputs.image_id }}'}, 'candidate hands over the image ID')
    exact(candidate['env'], {'APP': '${{ inputs.app }}', 'DOCKER_BUILD_SUMMARY': 'false', 'DOCKER_BUILD_RECORD_UPLOAD': 'false'},
          'candidate job environment')
    exact(publish['needs'], ['gate', 'candidate'], 'publish after the gate and the candidate')
    exact(publish['if'], RELEASE_BRANCHES, 'publish from release/* branches only')
    exact(publish['environment'], 'public-release', 'protected environment name')
    exact(publish['env'], {'APP': '${{ inputs.app }}'}, 'publish job environment')
    recipe = release_recipe()
    for name in RELEASE_JOB_KEYS:
        steps = jobs[name]['steps']
        require(isinstance(steps, list) and all(isinstance(step, dict) for step in steps), 'release steps')
        for step in steps:
            require(set(step) <= ({'name', 'run', 'env', 'id'} if 'run' in step else {'name', 'uses', 'with'}),
                    'release step keys (no condition, shell, working directory or bypass)')
            if 'name' in step:
                free_text(step['name'], 'release step name')
        exact([{key: (item.strip() if key == 'run' and isinstance(item, str) else item)
                for key, item in step.items() if key != 'name'} for step in steps], recipe[name],
              'reviewed ' + name + ' steps only; no added run, action, environment or GITHUB_ENV/GITHUB_PATH write')
    for text in workflow_strings(value):
        require(not SECRETISH.search(text) or text == RELEASE_TOKEN, 'no secret but the run\'s own GITHUB_TOKEN, and '
                'only where the recipe puts it')
        require(not re.search(r'\bvars\s*[.\[]', text, re.I) and 'GITHUB_ENV' not in text and 'GITHUB_PATH' not in text,
                'no repository variable or GITHUB_ENV/GITHUB_PATH write')


def builder_workflow(value, workflow):
    """Strict builder recipe; runner labels/approval markers are not a sandbox. release.yaml is the GitHub-hosted route
    (hosted_release); ci.yaml's images job keeps the blocked BLD2 contract below."""
    if workflow == 'release':
        hosted_release(value)
        return
    workflow_versions(value, workflow)
    require('env' not in value and 'defaults' not in value, 'no workflow environment/default injection')
    candidate = value['jobs']['images']
    exact(candidate['runs-on'], RUNNER, 'dedicated externally approved VM runner')
    require(not any(k in candidate for k in ('container', 'services', 'continue-on-error', 'defaults')),
            'nested runner or bypass denied')
    wanted_env = {'BLD2_APPROVAL': '${{ vars.BLD2_APPROVAL }}',
                  'DOCKER_BUILD_SUMMARY': 'false', 'DOCKER_BUILD_RECORD_UPLOAD': 'false'}
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
    # This list deliberately covers the WHOLE candidate path.
    runs = ['python3 packaging/builder_contract.py prepare',
            'python3 packaging/builder_contract.py setup --driver docker',
            'python3 packaging/builder_contract.py verify',
            'python3 packaging/install_scanners.py "$RUNNER_TEMP/scanners"',
            'python3 packaging/supply_chain.py candidate "$APP" "$RUNNER_TEMP/scanners" "$RUNNER_TEMP/candidate"']
    uses = ['actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
            'docker/build-push-action@10e90e3645eae34f1e60eeb005ba3a3d33f178e8']
    exact([s['run'].strip() for s in steps if 'run' in s], runs,
          'reviewed run sequence only; no GITHUB_ENV/PATH or shell overrides')
    exact([s['uses'] for s in steps if 'uses' in s], uses,
          'reviewed actions only; no Buildx downloader/overwrite')
    for step in steps:
        require(set(step) <= ({'name', 'run', 'env'} if 'run' in step else {'name', 'uses', 'with'}),
                'step environment/default/bypass injection')
        wanted = {}
        if 'supply_chain.py candidate' in step.get('run', ''):
            wanted = {'APP': '${{ matrix.app }}'}
        exact(step.get('env', {}), wanted, 'step environment cannot override isolation')
    app = '${{ matrix.app }}'
    exact(steps[build]['with'], {'builder': 'default', 'provenance': False, 'sbom': False,
          'context': '.', 'file': 'apps/' + app + '/Dockerfile', 'platforms': 'linux/amd64',
          'push': False, 'load': True, 'tags': 'local/mcp-' + app + ':' + CI_VERSION,
          'build-args': 'BUILD_VERSION=' + CI_VERSION,
          'labels': 'org.opencontainers.image.revision=${{ github.sha }}'}, 'fixed local candidate build')
    admission = value['jobs']['builder-admission']
    guard(admission, 'admit')
    exact(admission['runs-on'], 'ubuntu-24.04', 'admit before external scheduling')
    exact(admission['env'], {'BLD2_APPROVAL': '${{ vars.BLD2_APPROVAL }}'}, 'operator approval input')
    require('continue-on-error' not in admission and 'container' not in admission
            and 'services' not in admission, 'admission bypass/nesting')
    require('if' not in admission and 'if' not in candidate, 'CI denial must not be a skipped PASS')
    exact(candidate['needs'], ['unit', 'builder-admission'], 'mandatory admission dependency')
    exact(candidate['environment'], 'builder-candidate', 'protected candidate environment')
    exact(candidate['strategy']['max-parallel'], 1, 'bounded runner allocation')
    require('needs' not in value['jobs']['unit'], 'local unit job independent of builder approval')


NATIVE_ADDON_KEYS = {'package', 'version', 'node', 'node_abi', 'platform', 'url', 'sha256', 'size', 'member', 'member_size',
                     'member_sha256', 'evidence'}


def native_addons(inputs, dockerfiles, files):
    """Unreleased (0.4.12 line): the n8n image has exactly one native addon, better-sqlite3's prebuilt binary, and it enters
    only through packaging/native_addon.mjs from the release asset pinned in inputs.json native_addons. The npm tree
    stays hash-locked (`npm ci --ignore-scripts`); no Dockerfile may download anything else. Checked here: the pin's
    shape and immutable URL, that the lock and the override hold the same better-sqlite3 version, that the n8n Dockerfile
    carries every pinned literal in the npm stage (and no other Dockerfile mentions the addon), and that the CI unit
    environment and the build context install/reach the same script. files: lock, package, unit, dockerignore (texts)."""
    addons = inputs.get('native_addons')
    require(isinstance(addons, dict) and set(addons) == {'better-sqlite3'}, 'native addon allowlist')
    pin = addons['better-sqlite3']
    require(set(pin) == NATIVE_ADDON_KEYS, 'native addon pin shape')
    version, abi, platform = pin['version'], pin['node_abi'], pin['platform']
    require(pin['package'] == 'better-sqlite3' and re.fullmatch(r'\d+\.\d+\.\d+', version), 'native addon version')
    require(pin['node'] == inputs['bases']['node'].split(':')[1].split('-')[0], 'native addon is for the base image Node')
    require(re.fullmatch(r'v\d+', abi) and platform == 'linux-x64', 'native addon target')
    require(pin['url'] == f'https://github.com/WiseLibs/better-sqlite3/releases/download/v{version}/'
                          f'better-sqlite3-v{version}-node-{abi}-{platform}.tar.gz', 'native addon immutable release URL')
    require(all(re.fullmatch(r'[0-9a-f]{64}', pin[key]) for key in ('sha256', 'member_sha256')), 'native addon digests')
    require(all(type(pin[key]) is int and pin[key] > 0 for key in ('size', 'member_size')), 'native addon sizes')
    require(pin['member'] == 'build/Release/better_sqlite3.node', 'native addon member')
    require(json.loads(files['lock'])['packages']['node_modules/better-sqlite3']['version'] == version,
            'lock holds another better-sqlite3 than the pinned addon')
    require(json.loads(files['package']).get('overrides', {}).get('better-sqlite3') == version, 'package.json override of better-sqlite3')
    n8n = dockerfiles['n8n']
    for literal in ('COPY packaging/native_addon.mjs ./native_addon.mjs', 'RUN node native_addon.mjs install --version ' + version,
                    '--into node_modules/better-sqlite3', '--url ' + pin['url'], '--sha256 ' + pin['sha256'],
                    '--size ' + str(pin['size']), '--member ' + pin['member'], '--member-size ' + str(pin['member_size']),
                    '--member-sha256 ' + pin['member_sha256']):
        require(literal in n8n, 'n8n Dockerfile does not carry the pinned addon: ' + literal[:48])
    require(n8n.count('native_addon.mjs install') == 1, 'one addon installation')
    locked = 'RUN npm ci --ignore-scripts --no-audit --no-fund && npm cache clean --force'  # the npm stage's own line, not the UI stage's
    require(locked in n8n and n8n.index(locked) < n8n.index('native_addon.mjs install') < n8n.index('COPY --from=npm /npm/node_modules'),
            'the addon is installed in the npm stage, after the locked tree and before it is copied')
    for product, text in dockerfiles.items():
        require(not re.search(r'(?im)^\s*ADD\b|\b(curl|wget)\b', text), 'a Dockerfile downloads something: ' + product)
        require(product == 'n8n' or 'native_addon' not in text, 'native addon outside the n8n image: ' + product)
    unit = files['unit']
    command = 'node packaging/native_addon.mjs install --inputs packaging/inputs.json --addon better-sqlite3 --node-modules apps/n8n/node_modules'
    require(command in unit and unit.index('npm ci --prefix apps/n8n --ignore-scripts') < unit.index(command),
            'CI unit environment does not install the pinned addon after the locked tree')
    require('!packaging/native_addon.mjs' in files['dockerignore'], 'addon installer does not reach the build context')


def validate(root=ROOT):
    exact(load(root / 'repository.yaml'), {'name': 'WOOW MCP Add-ons', 'url': URL, 'maintainer': 'WOOWTECH'}, 'repository')
    paths = source_paths(root)
    app_scopes = {Path(p).parts[1] for p in paths if p.startswith('apps/') and len(Path(p).parts) > 1}
    require(app_scopes == set(PRODUCTS) | set(RETIRED) | {'runtime'}, 'application source scope')
    inputs = load(root / 'packaging/inputs.json')
    exact(inputs['products'], list(PRODUCTS), 'build allowlist')
    exact(inputs['version'], VERSION, 'build version')
    exact(inputs['version_overrides'], VERSION_OVERRIDES, 'per-product version overrides')
    runtime_version((root / 'packages/mcp-admin-core/mcp_admin_core/__init__.py').read_text())
    exact(inputs['supervisor'], {'version': '2026.09.3', 'commit': '64ea3be4322537fd5dcfbf620c4dc25490c1f56d'}, 'Supervisor schema pin')
    require(set(inputs['bases']) == {'python', 'node', 'uv'}, 'base allowlist')
    for image in inputs['bases'].values():
        require(bool(re.fullmatch(r'[a-z0-9/.-]+:[a-z0-9.-]+@sha256:[0-9a-f]{64}', image)), 'base must be exact version plus digest')
    discovered = {p for p in paths if Path(p).name in ('config.yaml', 'config.yml', 'config.json') and not any(x.startswith('.') or x == 'rootfs' for x in Path(p).parts)}
    require(discovered == {f'addons/{p}/config.yaml' for p in PRODUCTS}, 'accidental/missing Supervisor config discovery')
    require({p.name for p in (root / 'addons').iterdir()} == set(PRODUCTS), 'addon directory allowlist')
    slugs = set()
    dockerfiles = {}
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
        dockerfiles[product] = dockerfile
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
        build_version_default(dockerfile, product)
        require('uv sync --frozen --no-dev' in dockerfile, 'unlocked core')
        if product == 'n8n':
            require('npm ci --ignore-scripts --no-audit --no-fund' in dockerfile, 'unlocked/scripted npm')
        else:
            require(f'uv sync --project apps/{product} --frozen --no-dev' in dockerfile, 'missing isolated child lock')
    unit = (root / 'packaging/unit.sh').read_text()
    unit_child_sync(unit)
    native_addons(inputs, dockerfiles, {'lock': (root / 'apps/n8n/package-lock.json').read_text(), 'package': (root / 'apps/n8n/package.json').read_text(),
                                         'unit': unit, 'dockerignore': (root / '.dockerignore').read_text()})
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
            if workflow == 'release' or name != 'images':  # only ci.yaml's blocked BLD2 images job is not GitHub-hosted
                exact(job['runs-on'], 'ubuntu-24.04', 'isolated hosted unit/admission runner')
            limit = 40 if workflow == 'ci' else RELEASE_MINUTES[name]  # release: exact per job (hosted_release)
            require(type(job['timeout-minutes']) is int and 1 <= job['timeout-minutes'] <= limit, 'bounded job')
            for step in job['steps']:
                if step.get('uses', '').startswith('actions/checkout@'):
                    exact(step['with']['persist-credentials'], False, 'checkout credential persistence')
                if step.get('uses', '').startswith('docker/build-push-action@'):
                    for key, wanted in {'context': '.', 'platforms': 'linux/amd64', 'push': False,
                                        'load': True, 'build-args': 'BUILD_VERSION=' +
                                        (CI_VERSION if workflow == 'ci' else RELEASE_VERSION)}.items():
                        exact(step['with'][key], wanted, 'build ' + key)
        exact(value['permissions'], {'contents': 'read'}, workflow + ' default permissions')
        require('pull_request_target' not in value['on'], 'unsafe event')
        text = (root / '.github/workflows' / (workflow + '.yaml')).read_text()
        for use in re.findall(r'uses:\s*([^\s]+)', text):
            require(bool(re.fullmatch(r'[\w-]+/[\w-]+@[0-9a-f]{40}', use)), 'unpinned action')
        candidate_job = value['jobs']['images' if workflow == 'ci' else 'candidate']
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
            exact(value['jobs']['publish']['permissions'], RELEASE_PERMISSIONS['publish'], 'minimal publisher authority')
            require('packages' not in value['jobs']['candidate']['permissions'] and 'environment' not in value['jobs']['candidate'],
                    'the candidate job has no registry authority')
            for job in ('candidate', 'publish'):
                exact(value['jobs'][job]['if'], RELEASE_BRANCHES, job + ' from release/* branches only')
            require('if' not in value['jobs']['gate'], 'the gate refuses other refs itself, never a skipped pass')
            for job in value['jobs'].values():
                for step in job['steps']:
                    if step.get('uses', '').startswith('actions/checkout@'):
                        exact(step['with']['ref'], '${{ github.sha }}', 'no arbitrary release checkout')
    print(f'PASS: {len(PRODUCTS)} strict Supervisor-subset manifests, translations, pins, workflow policy and clearance shape')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    try:
        validate(parser.parse_args().root)
    except (Invalid, KeyError, TypeError) as exc:
        raise SystemExit('packaging validation failed: ' + str(exc)) from None
