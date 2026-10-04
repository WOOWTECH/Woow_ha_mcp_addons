"""Fail-closed runner admission and runtime facts, NOT an isolation attestation.

No download/build/bootstrap/run here. Only a future reviewed hosting route and
external operator approval may enable VM queries. See builder-runner.md.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess

import builder_binary

# Known WOOWTECH USER repository cannot provide required runner-group controls.
# No environment/label/approval JSON can change this. A future hosting decision
# requires a reviewed source change, account/plan evidence and NEW SECURITY.
HOSTING_ROUTE = 'BLOCKED_PERSONAL_REPOSITORY'
ANONYMOUS_CONFIG = {'auths': {'bld2-anonymous.invalid': {}}}
PRIVATE_DIRS = {'HOME': 'home', 'XDG_CONFIG_HOME': 'xdg-config',
                'XDG_DATA_HOME': 'xdg-data', 'XDG_CACHE_HOME': 'xdg-cache',
                'XDG_STATE_HOME': 'xdg-state', 'XDG_RUNTIME_DIR': 'xdg-runtime',
                'DOCKER_CONFIG': 'docker'}

BUILDX_VERSION = 'v0.28.0'
ENDPOINT = 'unix:///var/run/docker.sock'
RUNNER = {'group': 'woow-disposable-builder', 'labels': ['self-hosted', 'linux', 'x64']}
APPROVAL_KEYS = {'schema', 'status', 'source', 'expires', 'review', 'buildx',
                 'client', 'engine', 'api', 'buildkit', 'runners'}


class Denied(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Denied(message)


def decode(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(text, object_pairs_hook=unique)
    except (ValueError, TypeError):
        raise Denied('missing/malformed JSON; raw data suppressed') from None


def approval(env):
    require(HOSTING_ROUTE == 'REVIEWED_ORGANIZATION',
            'BLOCKED: current WOOWTECH personal repository lacks required hosting controls')
    value = decode(env.get('BLD2_APPROVAL', '{"status":"NOT_APPROVED"}') or '{}')
    require(isinstance(value, dict) and value.get('status') == 'APPROVED',
            'NOT_APPROVED: operator runner/source authorization missing')
    require(set(value) == APPROVAL_KEYS and type(value['schema']) is int and value['schema'] == 1,
            'approval schema mismatch')
    require(env.get('GITHUB_EVENT_NAME') in ('push', 'workflow_dispatch')
            and env.get('GITHUB_REF') == 'refs/heads/main', 'no PR or non-main builder admission')
    require(isinstance(value['source'], str) and re.fullmatch('[0-9a-f]{40}', value['source'])
            and value['source'] == env.get('GITHUB_SHA'), 'unreviewed source SHA')
    require(isinstance(value['review'], str) and re.fullmatch(r'[A-Za-z0-9._/-]{1,160}', value['review']),
            'external review reference required')
    require(value['buildx'] == BUILDX_VERSION, 'unapproved Buildx software version')
    for key, pattern in [('client', r'\d+\.\d+\.\d+'), ('engine', r'\d+\.\d+\.\d+'),
                         ('api', r'\d+\.\d+'), ('buildkit', r'v?\d+\.\d+\.\d+')]:
        require(isinstance(value[key], str) and re.fullmatch(pattern, value[key]),
                'unknown/unpinned ' + key + ' version')
    try:
        remaining = (datetime.fromisoformat(value['expires'].replace('Z', '+00:00'))
                     - datetime.now(timezone.utc)).total_seconds()
    except (AttributeError, ValueError, TypeError):
        raise Denied('invalid approval expiry') from None
    require(0 < remaining <= 4 * 3600, 'approval expired or exceeds four-hour authorization')
    require(isinstance(value['runners'], dict) and bool(value['runners']), 'no enrolled VM engines')
    for name, identity in value['runners'].items():
        require(re.fullmatch(r'[A-Za-z0-9._-]{1,128}', name) and isinstance(identity, dict)
                and set(identity) == {'engine_id', 'daemon_name'}, 'invalid runner enrollment')
        for field in identity.values():
            require(isinstance(field, str) and re.fullmatch(r'[A-Za-z0-9:._-]{1,160}', field),
                    'unknown engine identity')
    return value


def private_paths(env):
    temp = Path(env.get('RUNNER_TEMP', ''))
    require(temp.is_absolute() and temp.is_dir() and not temp.is_symlink()
            and '\n' not in str(temp) and '\r' not in str(temp), 'private runner temp required')
    root = temp / 'woow-builder'
    return root, root / 'docker'


def exports(env):
    root, _ = private_paths(env)
    return {key: str(root / directory) for key, directory in PRIVATE_DIRS.items()}


def environment(env, *, prepared=False):
    allowed = {'DOCKER_BUILD_SUMMARY': 'false', 'DOCKER_BUILD_RECORD_UPLOAD': 'false'}
    for key, value in env.items():
        upper = key.upper()
        require(not upper.endswith('_PROXY'), 'ambient proxy denied (including empty values)')
        require(not upper.startswith('XDG_') or key in PRIVATE_DIRS,
                'unreviewed XDG search/session override denied')
        require(not upper.startswith(('PASSWORD_STORE_', 'GPG_', 'GNUPG', 'DBUS_',
                    'KEYRING_', 'GCM_', 'SSH_AUTH_', 'SSH_AGENT_', 'DOCKER_CREDENTIAL_'))
                and upper not in ('GIT_ASKPASS', 'SSH_ASKPASS', 'CREDENTIALS_DIRECTORY'),
                'ambient helper store/session denied')
    # Discover names only; NEVER execute a helper or inspect any real store.
    # Refuse all helper names, including Linux auto-detection's pass/secretservice.
    for directory in env.get('PATH', '').split(os.pathsep):
        path = Path(directory)
        require(path.is_absolute(), 'absolute helper-free PATH required')
        require(not any(path.glob('docker-credential-*')), 'credential helper on PATH denied')
    if prepared:
        root, config = private_paths(env)
        require(root.is_dir() and not root.is_symlink() and root.stat().st_mode & 0o777 == 0o700,
                'missing private builder root')
        for key, path in exports(env).items():
            target = Path(path)
            require(env.get(key) == path and target.is_dir() and not target.is_symlink()
                    and target.stat().st_mode & 0o777 == 0o700,
                    'not the job-created HOME/XDG/Docker environment')
        allowed['DOCKER_CONFIG'] = str(config)
        config_file = config / 'config.json'
        require(config_file.is_file() and not config_file.is_symlink(), 'missing private config')
        require(decode(config_file.read_text()) == ANONYMOUS_CONFIG,
                'candidate config changed or contains auth/helper/proxy settings')
        builder_binary.verify(config)
    for key, value in env.items():
        if key.upper().startswith(('DOCKER_', 'BUILDX_', 'BUILDKIT_', 'BUILDKITD_', 'BUILDER_NODE_')):
            require(key in allowed and value == allowed[key], 'ambient Docker/builder override denied')


def runner(value, env):
    require(env.get('RUNNER_OS') == 'Linux' and env.get('RUNNER_ARCH') == 'X64'
            and platform.machine() == 'x86_64', 'native Linux amd64 runner required')
    require(env.get('RUNNER_NAME') in value['runners'], 'runner not enrolled by operator')


def command(args, env):
    # No raw output/error logging, no shell, and no daemon start/bootstrap flags.
    try:
        result = subprocess.run(['docker', *args], env=env, text=True,
                                capture_output=True, check=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise Denied('Docker fact query failed; raw diagnostics suppressed') from None
    require(not result.stderr.strip(), 'Docker fact query diagnostics; deny')
    return result.stdout.strip()


def engine_facts(value, env, docker_env):
    require(command(['context', 'show'], docker_env) == 'default', 'non-default context denied')
    contexts = decode(command(['context', 'inspect', 'default'], docker_env))
    require(isinstance(contexts, list) and len(contexts) == 1, 'ambiguous context')
    context = contexts[0]
    require(context['Name'] == 'default' and not context.get('TLSMaterial')
            and set(context['Endpoints']) == {'docker'}, 'remote/TLS context denied')
    endpoint = context['Endpoints']['docker']
    require(endpoint['Host'] == ENDPOINT and endpoint.get('SkipTLSVerify') is False
            and not endpoint.get('TLSData'), 'only the enrolled VM-local engine endpoint is allowed')
    # The local pathname is NOT proof of ownership: exact enrollment plus the
    # external VM/no-forwarded-sockets boundary remain mandatory.
    versions = decode(command(['version', '--format', '{{json .}}'], docker_env))
    client, server = versions['Client'], versions['Server']
    require(client['Version'] == value['client'] and server['Version'] == value['engine']
            and server['ApiVersion'] == value['api'], 'Docker version not approved')
    require(all(x['Os'] == 'linux' and x['Arch'] == 'amd64' for x in (client, server)),
            'Docker client/server architecture mismatch')
    info = decode(command(['info', '--format', '{{json .}}'], docker_env))
    identity = value['runners'][env['RUNNER_NAME']]
    require(info['ID'] == identity['engine_id'] and info['Name'] == identity['daemon_name'],
            'daemon identity not enrolled')
    require(info['OSType'] == 'linux' and info['Architecture'] in ('x86_64', 'amd64'),
            'engine architecture mismatch')
    return {'client': client['Version'], 'engine': server['Version'], 'api': server['ApiVersion'],
            'engine_id': info['ID'], 'daemon_name': info['Name'], 'endpoint': ENDPOINT,
            'os': 'linux', 'arch': 'amd64', 'runner': env['RUNNER_NAME']}


def prepare(env):
    value = approval(env)
    environment(env)
    runner(value, env)
    root, config = private_paths(env)
    require(not root.exists(), 'runner reused or builder directory already exists')
    root.mkdir(mode=0o700)
    for path in exports(env).values():
        Path(path).mkdir(mode=0o700)
    # Pinned CLI LoadDefaultConfigFile calls DetectDefaultStore iff !ContainsAuth.
    # ContainsAuth counts auths entries, even this reserved, credential-free one.
    # No credsStore/credHelpers => GetCredentialsStore uses only this file.
    config_file = config / 'config.json'
    config_file.write_text(json.dumps(ANONYMOUS_CONFIG) + '\n')
    config_file.chmod(0o600)
    builder_binary.install(config)  # Hash/copy bytes BEFORE any Docker invocation.
    docker_env = dict(env, **exports(env))
    environment(docker_env, prepared=True)
    engine_facts(value, env, docker_env)
    return config


def setup(env, driver):
    require(driver == 'docker', 'only embedded docker driver allowed')
    # No downloader, create, bootstrap or alternate driver. Embedded docker
    # Bootstrap is a no-op in v0.28.0; verification is the entire setup needed.
    return verify(env)


def verify(env):
    value = approval(env)
    environment(env, prepared=True)
    runner(value, env)
    facts = engine_facts(value, env, env)
    version = command(['buildx', 'version'], env)
    require(re.fullmatch(r'github\.com/docker/buildx ' + re.escape(BUILDX_VERSION)
                         + r' [A-Za-z0-9._-]+', version), 'Buildx runtime version mismatch')
    # v0.28.0 supports JSON-lines ls, NOT inspect --format. Fresh config has
    # exactly one local default builder; no other context/node is admissible.
    builders = [decode(line) for line in command(['buildx', 'ls', '--format', 'json'], env).splitlines()]
    require(len(builders) == 1, 'extra builders/contexts denied')
    builder = builders[0]
    require(builder['Name'] == 'default' and builder['Driver'] == 'docker'
            and builder['Current'] is True and builder['Dynamic'] is False
            and not builder.get('Err'), 'only current embedded docker driver allowed')
    require(len(builder['Nodes']) == 1, 'exactly one local builder node required')
    node = builder['Nodes'][0]
    require(node['Endpoint'] == 'default' and node['Status'] == 'running'
            and not node.get('Err'), 'remote/unavailable builder node')
    require(node['Version'] == value['buildkit'], 'unknown/unapproved embedded BuildKit version')
    require(isinstance(node['Platforms'], list) and 'linux/amd64' in node['Platforms'],
            'native amd64 build support missing')
    for key in ('Flags', 'DriverOpts', 'Files', 'ProxyConfig'):
        require(not node.get(key), 'builder options/config/entitlements denied')
    facts.update(source=value['source'], buildx=version, buildkit=node['Version'], driver='docker',
                 review=value['review'], approval_sha256=hashlib.sha256(
                     json.dumps(value, sort_keys=True).encode()).hexdigest())
    root, _ = private_paths(env)
    (root / 'identity.json').write_text(json.dumps(facts, sort_keys=True, indent=2) + '\n')
    return facts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('admit', 'prepare', 'setup', 'verify'))
    parser.add_argument('--driver', choices=('docker',))
    args = parser.parse_args()
    phase = args.phase
    env = dict(os.environ)
    try:
        value = approval(env)  # Fail BEFORE even git/Docker when approval is absent.
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
        require(head == value['source'], 'checkout not the approved source')
        if phase == 'prepare':
            prepare(env)
            with Path(env['GITHUB_ENV']).open('a') as output:
                for key, path in exports(env).items():
                    output.write(key + '=' + path + '\n')
        elif phase == 'setup':
            print(json.dumps(setup(env, args.driver), sort_keys=True))
        elif phase == 'verify':
            print(json.dumps(verify(env), sort_keys=True))
        print('Builder ' + phase + ': contract matched; NOT image acceptance or isolation proof')
    except (Denied, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        raise SystemExit('Builder gate DENIED: current WOOWTECH personal-repository route BLOCKED; '
                         'hosting/approval/environment/software/runner contract not satisfied; '
                         'no image acceptance. See docs/operations/builder-runner.md') from None


if __name__ == '__main__':
    main()
