"""Fail-closed candidate gate. Private raw reports; only bound, sanitized evidence exits.

No signing claim: provenance is an unsigned CI-generated in-toto Statement.
Trust is the protected workflow/runner and independently reviewed approvals.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ('source-secrets', 'history-secrets', 'image-secrets', 'vulnerabilities', 'licenses', 'container')
EVIDENCE = ('sbom.syft.json', 'sbom.spdx.json', 'scan-summary.json')
PRODUCTS = ('odoo', 'odoo-manage', 'n8n', 'hermes', 'opendesign', 'emqx', 'litellm')


class Closed(ValueError):
    pass


def require(condition):
    if not condition:
        raise Closed('supply-chain precondition failed')


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        raise Closed('missing or malformed evidence') from None


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pins():
    return read_json(ROOT / 'packaging/scanner-pins.json')


def policy_hash():
    return sha(ROOT / 'packaging/supply-chain-policy.json')


def run(command, *, cwd=ROOT, env=None, reject_stderr=False):
    # Never print raw scanner output/exceptions: even stderr can contain secrets.
    try:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True, timeout=900)
        if reject_stderr:
            require(not result.stderr)
        return result.stdout
    except (OSError, subprocess.SubprocessError):
        raise Closed('tool failed; raw diagnostics suppressed') from None


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def grype_db(report):
    # Normalise the DB descriptor: grype <=0.89 reports db.{schemaVersion,checksum,built};
    # grype 0.120 reports db.status.{schemaVersion 'v6.x', built, valid, from=...?checksum=sha256:...}.
    db = report.get('descriptor', {}).get('db', {})
    if isinstance(db.get('status'), dict):
        status = db['status']
        require(status.get('valid') is True and not status.get('error'))
        match = re.search(r'[?&]checksum=sha256(?::|%3A)([0-9a-f]{64})(?:&|$)', str(status.get('from', '')))
        return {'schemaVersion': str(status.get('schemaVersion', '')).removeprefix('v'), 'built': status.get('built'),
                'checksum': match.group(1) if match else ''}
    require(not db.get('error'))
    return {'schemaVersion': str(db.get('schemaVersion', '')), 'built': db.get('built'), 'checksum': db.get('checksum', '')}


def enforce_policy(sbom, vulnerabilities):
    policy = read_json(ROOT / 'packaging/supply-chain-policy.json')
    require(policy['schema'] == 1 and policy['id'] == 'woow-conservative-v1'
            and policy['unknown_or_missing_license'] == 'deny'
            and policy['unfixed_vulnerabilities'] in ('include', 'exclude'))
    require(isinstance(sbom.get('artifacts'), list) and bool(sbom['artifacts']))
    for package in sbom['artifacts']:
        licenses = package.get('licenses')
        require(isinstance(licenses, list) and bool(licenses))
        for license_ in licenses:
            # Expressions are NOT guessed/split: unreviewed AND/OR/custom licenses deny.
            require(license_.get('value') in policy['allowed_licenses'])
    descriptor = vulnerabilities.get('descriptor', {})
    require(descriptor.get('name') == 'grype' and descriptor.get('version') == pins()['grype']['version'])
    db = grype_db(vulnerabilities)
    require(db['schemaVersion'].startswith('6.'))
    require(bool(re.fullmatch(r'[0-9a-f]{64}', db.get('checksum', '').removeprefix('sha256:'))))
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(db['built'].replace('Z', '+00:00'))).total_seconds()
    except (KeyError, ValueError, TypeError):
        raise Closed('missing database freshness') from None
    require(0 <= age <= policy['grype_database_max_age_hours'] * 3600)
    require(isinstance(vulnerabilities.get('matches'), list))
    require(not vulnerabilities.get('ignoredMatches'))
    # 'include' (default): every blocked-severity match fails. 'exclude' (owner decision): matches whose
    # fix.state is not 'fixed' (upstream not-fixed/wont-fix/unknown) are still reported in the scan
    # evidence but do not block; any blocked-severity match WITH an available fix still fails.
    for match in vulnerabilities['matches']:
        vulnerability = match.get('vulnerability', {})
        severity = vulnerability.get('severity')
        require(severity in policy['known_severities'])
        if severity in policy['blocked_severities']:
            fixable = vulnerability.get('fix', {}).get('state') == 'fixed'
            require(policy['unfixed_vulnerabilities'] == 'exclude' and not fixable)


def validate_sbom(sbom, spdx, subject):
    require(sbom['descriptor']['name'] == 'syft' and sbom['descriptor']['version'] == pins()['syft']['version'])
    require(sbom['source']['type'] == 'image' and sbom['source']['metadata']['imageID'] == subject['image_id'])
    require(len(sbom['source']['metadata']['layers']) == len(subject['diff_ids']))
    require(sbom['descriptor']['configuration']['search']['scope'] == 'all-layers')
    kinds = {package['type'] for package in sbom['artifacts']}
    require({'deb', 'python'} <= kinds and (subject['app'] != 'n8n' or 'npm' in kinds))
    require(bool(sbom.get('files')) and sbom['descriptor']['configuration']['files']['selection'] == 'all')
    require(spdx['spdxVersion'] == 'SPDX-2.3' and spdx['SPDXID'] == 'SPDXRef-DOCUMENT' and bool(spdx['packages']))


def provenance(subject, directory):
    return {'_type': 'https://in-toto.io/Statement/v1',
            'subject': [{'name': 'local/mcp-' + subject['app'],
                         'digest': {'sha256': subject['image_id'].removeprefix('sha256:')}}],
            'predicateType': 'urn:woow:mcp:unsigned-candidate:v1',
            'predicate': {'trust': 'unsigned protected-workflow receipt; NOT SLSA certification',
                          'recipe': 'packaging/supply_chain.py candidate (source commit below)',
                          'subject': subject, 'evidence': {n: sha(directory / n) for n in EVIDENCE}}}


def verify_bundle(directory, subject):
    try:
        summary = read_json(directory / 'scan-summary.json')
        require(summary['subject'] == subject)
        require(summary['policy_sha256'] == policy_hash() and summary['tools'] == pins())
        require(summary['checks'] == dict.fromkeys(CHECKS, 'pass'))
        require(read_json(directory / 'provenance.json') == provenance(subject, directory))
        validate_sbom(read_json(directory / 'sbom.syft.json'), read_json(directory / 'sbom.spdx.json'), subject)
    except (OSError, KeyError, TypeError):
        raise Closed('incomplete evidence') from None


def verify_remote(raw_manifest, digest, pulled, subject):
    require(digest == 'sha256:' + hashlib.sha256(raw_manifest).hexdigest())
    manifest = json.loads(raw_manifest)
    require(manifest.get('schemaVersion') == 2 and 'manifests' not in manifest)
    require(manifest['config']['digest'] == subject['image_id'])
    # Docker's successful immutable anonymous pull verifies blob/config hashes
    # and uncompressed diffIDs; check its result against the tested image too.
    require(pulled['Id'] == subject['image_id'])
    require(pulled['RootFS']['Layers'] == subject['diff_ids'])
    require(len(manifest['layers']) == len(subject['diff_ids']) and bool(manifest['layers']))
    for layer in manifest['layers']:
        require(bool(re.fullmatch(r'sha256:[0-9a-f]{64}', layer['digest'])))


def fixed_image(app):
    require(app in PRODUCTS)
    return f'local/mcp-{app}:0.1.0'


def inspect_image(app):
    metadata = json.loads(run(['docker', 'image', 'inspect', fixed_image(app)]))[0]
    require(metadata['Architecture'] == 'amd64' and metadata['Os'] == 'linux')
    require(bool(re.fullmatch(r'sha256:[0-9a-f]{64}', metadata['Id'])))
    return metadata


def verify_current(app, directory):
    subject = read_json(directory / 'subject.json')
    metadata = inspect_image(app)
    require(subject['image_id'] == metadata['Id'] and subject['diff_ids'] == metadata['RootFS']['Layers'])
    require(subject['source'] == run(['git', 'rev-parse', 'HEAD']).decode().strip() and subject['app'] == app)
    verify_bundle(directory, subject)
    return subject


def regular_files(archive, destination):
    # Do not extract tar names, links, devices, permissions, owners or traversal.
    destination.mkdir(mode=0o700)
    for index, member in enumerate(archive):
        if member.isfile():
            suffix = Path(member.name).suffix[:16]
            with archive.extractfile(member) as source, (destination / (str(index) + suffix)).open('wb') as target:
                shutil.copyfileobj(source, target)


def unpack_image(archive_path, metadata, directory):
    scan = directory / 'image-files'
    scan.mkdir(mode=0o700)
    with tarfile.open(archive_path) as archive:
        manifest = json.load(archive.extractfile('manifest.json'))
        require(len(manifest) == 1)
        config = archive.extractfile(manifest[0]['Config']).read()
        require('sha256:' + hashlib.sha256(config).hexdigest() == metadata['Id'])
        require(json.loads(config)['rootfs']['diff_ids'] == metadata['RootFS']['Layers'])
        (scan / 'config.json').write_bytes(config)
        require(len(manifest[0]['Layers']) == len(metadata['RootFS']['Layers']))
        for index, (name, diff_id) in enumerate(zip(manifest[0]['Layers'], metadata['RootFS']['Layers'])):
            layer_path = directory / 'layer.tar'
            with archive.extractfile(name) as source, layer_path.open('wb') as target:
                shutil.copyfileobj(source, target)
            require('sha256:' + sha(layer_path) == diff_id)
            with tarfile.open(layer_path) as layer:
                regular_files(layer, scan / str(index))
            layer_path.unlink()
    return scan


def scanner_env(private):
    # Do not give scanners workflow credentials, user config, proxies or plugins.
    return {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(private),
            'XDG_CACHE_HOME': str(private / 'cache'), 'GRYPE_DB_VALIDATE_AGE': 'true',
            'GRYPE_DB_MAX_ALLOWED_BUILT_AGE': '120h', 'GRYPE_CHECK_FOR_APP_UPDATE': 'false',
            'SYFT_CHECK_FOR_APP_UPDATE': 'false'}


def triaged_pins():
    # Only exact public sha256 file pins already triaged as false positives (packaging/secret-triage.json).
    triage = read_json(ROOT / 'packaging/secret-triage.json')
    require(triage.get('schema') == 1 and triage.get('requires_security_review') is True)
    values = [entry.get('sha256_pin') for entry in triage.get('values', [])]
    require(bool(values) and all(isinstance(v, str) and re.fullmatch(r'[0-9a-f]{64}', v) for v in values))
    require(len(set(values)) == len(values) and all(entry.get('seen_in') for entry in triage['values']))
    return sorted(values)


def gitleaks_config():
    # Default rules unchanged. Allowlist matches the WHOLE secret against exact 64-hex values only,
    # so any other finding (or any other value) still fails closed. Reports stay --redact=100.
    return ('[extend]\nuseDefault = true\n\n[[allowlists]]\n'
            'description = "triaged sha256 file pins (packaging/secret-triage.json)"\n'
            "regexes = ['''^(?:" + '|'.join(triaged_pins()) + ")$''']\n")


def approved_image_findings():
    # Third-party image-layer hits approved by owner/security review: (gitleaks rule, sha256 of value).
    # Values are never stored; entries still PENDING approval do not count.
    section = read_json(ROOT / 'packaging/secret-triage.json').get('image_findings', {})
    approved = set()
    for entry in section.get('entries', []):
        rule, digest = entry.get('rule'), entry.get('secret_sha256')
        require(isinstance(rule, str) and bool(rule) and isinstance(digest, str)
                and bool(re.fullmatch(r'[0-9a-f]{64}', digest)) and bool(entry.get('seen')))
        if entry.get('approved') is True:
            approved.add((rule, digest))
    return approved


def secret_scan(tool, mode, target, private, label, env):
    config = private / 'gitleaks.toml'
    config.write_text(gitleaks_config())
    ignore = private / 'empty-ignore'
    ignore.write_text('')
    report = private / (label + '.json')
    # Image layers hold third-party files whose hits are triaged by value hash, so only that scan reads
    # unredacted values -- inside this private temporary directory, scrubbed right after hashing.
    hashed = label == 'image'
    command = [str(tool), mode, str(target), '--config', str(config),
               '--gitleaks-ignore-path', str(ignore), '--ignore-gitleaks-allow',
               '--max-decode-depth', '5', '--max-archive-depth', '5', '--max-target-megabytes', '0',
               '--log-level', 'warn', '--redact=0' if hashed else '--redact=100', '--no-banner',
               '--report-format', 'json', '--report-path', str(report)]
    if hashed:
        command += ['--exit-code', '0']
    if mode == 'git':
        command += ['--log-opts=--all --full-history -m']
    run(command, cwd=private, env=env, reject_stderr=not hashed)
    findings = read_json(report)
    if not hashed:
        require(findings == [])
        return
    try:
        allowed = approved_image_findings()
        keys = [(f.get('RuleID'), hashlib.sha256(str(f.get('Secret', '')).encode()).hexdigest()) for f in findings]
    finally:
        report.write_text('[]\n')  # never leave raw values behind, even on failure
        findings = None
    require(isinstance(keys, list) and all(key in allowed for key in keys))


def source_scans(tool, private, env):
    require(run(['git', 'rev-parse', '--is-shallow-repository']).strip() == b'false')
    require(run(['git', 'status', '--porcelain', '--untracked-files=all']) == b'')
    require(b'160000 commit' not in run(['git', 'ls-tree', '-r', 'HEAD']))
    exported = private / 'source.tar'
    run(['git', 'archive', '--format=tar', '--output=' + str(exported), 'HEAD'])
    with tarfile.open(exported) as archive:
        regular_files(archive, private / 'source-files')
    secret_scan(tool, 'dir', private / 'source-files', private, 'source', env)
    secret_scan(tool, 'git', ROOT, private, 'history', env)


def candidate(app, tools, output):
    from container_acceptance import main as container_test
    os.umask(0o077)
    require(not output.exists())
    # Test exact ID, not a mutable tag. No rebuild anywhere in this gate.
    metadata = inspect_image(app)
    source = run(['git', 'rev-parse', 'HEAD']).decode().strip()
    require(metadata['Config']['Labels'].get('org.opencontainers.image.revision') == source)
    container_test(app, fixed_image(app), expected_id=metadata['Id'])
    with tempfile.TemporaryDirectory(prefix='private-supply-chain-') as temporary:
        private = Path(temporary)
        env = scanner_env(private)
        for name in pins():
            require(sha(tools / name) == (tools / (name + '.sha256')).read_text())
        require(run([str(tools / 'gitleaks'), 'version'], cwd=private, env=env).decode().strip()
                == pins()['gitleaks']['version'])
        source_scans(tools / 'gitleaks', private, env)
        image = private / 'image.tar'
        run(['docker', 'image', 'save', '--output', str(image), metadata['Id']])
        image_files = unpack_image(image, metadata, private)
        secret_scan(tools / 'gitleaks', 'dir', image_files, private, 'image', env)
        syft = private / 'sbom.syft.json'
        spdx = private / 'sbom.spdx.json'
        syft_config = private / 'syft.yaml'
        syft_config.write_text('check-for-app-update: false\nfile:\n  metadata:\n    selection: all\n'
                               'package:\n  search-unindexed-archives: true\n'
                               'javascript:\n  include-dev-dependencies: true\n')
        run([str(tools / 'syft'), 'scan', 'docker-archive:' + str(image), '--scope', 'all-layers',
             '--config', str(syft_config), '-o', 'syft-json=' + str(syft),
             '-o', 'spdx-json=' + str(spdx)], cwd=private, env=env)
        sbom = read_json(syft)
        subject = {'app': app, 'source': source, 'image_id': metadata['Id'],
                   'diff_ids': metadata['RootFS']['Layers'], 'archive_sha256': sha(image)}
        validate_sbom(sbom, read_json(spdx), subject)
        grype_config = private / 'grype.yaml'
        grype_config.write_text('check-for-app-update: false\ndb:\n  validate-age: true\n  max-allowed-built-age: 120h\n')
        vulnerabilities = private / 'vulnerabilities.json'
        # Fetch and validate the DB first, alone; then scan the SBOM against it.
        run([str(tools / 'grype'), 'db', 'update', '--config', str(grype_config)], cwd=private, env=env)
        raw = run([str(tools / 'grype'), 'sbom:' + str(syft), '--config', str(grype_config),
                   '-o', 'json'], cwd=private, env=env)
        vulnerabilities.write_bytes(raw)
        vulnerability_report = read_json(vulnerabilities)
        enforce_policy(sbom, vulnerability_report)
        # SBOM fields can themselves contain a secret; gate retained evidence too.
        evidence = private / 'evidence'
        evidence.mkdir(mode=0o700)
        shutil.copyfile(syft, evidence / syft.name)
        shutil.copyfile(spdx, evidence / spdx.name)
        write_json(evidence / 'subject.json', subject)
        write_json(evidence / 'scan-summary.json', {'subject': subject, 'policy_sha256': policy_hash(),
                   'tools': pins(), 'checks': dict.fromkeys(CHECKS, 'pass'),
                   'vulnerability_database': grype_db(vulnerability_report),
                   'package_count': len(sbom['artifacts']),
                   'vulnerability_count': len(vulnerability_report['matches'])})
        write_json(evidence / 'provenance.json', provenance(subject, evidence))
        verify_bundle(evidence, subject)
        secret_scan(tools / 'gitleaks', 'dir', evidence, private, 'evidence', env)
        require(inspect_image(app)['Id'] == metadata['Id'])
        shutil.copytree(evidence, output)
    print('PASS: exact tested candidate; source/history/all-layer secrets, SBOM, CVE/license policy; unsigned evidence')


if __name__ == '__main__':
    try:
        if len(sys.argv) == 5 and sys.argv[1] == 'candidate':
            candidate(sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]))
        elif len(sys.argv) == 4 and sys.argv[1] == 'verify':
            verify_current(sys.argv[2], Path(sys.argv[3]))
            print('PASS: current local image matches tested/scanned evidence')
        else:
            raise Closed('invalid command')
    except Exception:
        raise SystemExit('supply-chain gate CLOSED; missing/mismatched evidence, scanner or policy failure; raw output suppressed') from None
