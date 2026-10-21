"""Release gate for the WOOW App Store (.github/workflows/woow-addon-release.yml).

The Store's registry decides which add-ons ship; for each add-on it enables:

  images     the manifest version's amd64 image on GHCR can be pulled anonymously
             (manifest and image config resolve, and the config is linux/amd64).
  decisions  a version that has no stable Release yet (tag <slug>-v<version>, the
             Store's tag scheme for a multi-add-on repository) is named in a
             docs/operations/release-decision-*.md record: the record is the evidence
             that the builder VM accepted the images, which GitHub Actions cannot see.

Usage: python packaging/release_gate.py {images,decisions,all} <store registry.json>
Network: GHCR anonymous token/manifests; GitHub API releases (GITHUB_TOKEN if set).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'WOOWTECH/Woow_ha_mcp_addons'
ACCEPT = ', '.join(['application/vnd.oci.image.index.v1+json', 'application/vnd.oci.image.manifest.v1+json',
                    'application/vnd.docker.distribution.manifest.list.v2+json',
                    'application/vnd.docker.distribution.manifest.v2+json'])


class Failed(Exception):
    pass


def components(registry, root=ROOT):
    """Enabled stable components of this repository: (slug, version, manifest) read from the checkout."""
    provider = registry['providers'][REPOSITORY]
    found = []
    for component in provider['components']:
        if not component.get('enabled', True) or component.get('channel', 'stable') != 'stable':
            continue
        manifest = yaml.safe_load((root / component['source_path'] / component['config_file']).read_text(encoding='utf-8'))
        if manifest.get('slug') != component['id']:
            raise Failed(f"{component['source_path']}: slug {manifest.get('slug')!r} is not {component['id']!r}")
        found.append((component['id'], str(manifest['version']), manifest))
    if not found:
        raise Failed('the Store registry enables no add-on of ' + REPOSITORY)
    return found


def fetch(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def image_pullable(reference, arch='amd64', fetch=fetch):
    """Anonymous pull check of ghcr.io/<repo>:<tag> for one architecture; returns the platform manifest digest."""
    if not reference.startswith('ghcr.io/'):
        raise Failed(reference + ': not a GHCR image')
    repo, tag = reference[len('ghcr.io/'):].rsplit(':', 1)
    if not re.fullmatch(r'[a-z0-9._/-]+', repo) or not re.fullmatch(r'[A-Za-z0-9_.-]+', tag):
        raise Failed(reference + ': invalid image reference')
    try:
        token = json.loads(fetch('https://ghcr.io/token?scope=' + urllib.parse.quote('repository:' + repo + ':pull')))['token']
        headers = {'Authorization': 'Bearer ' + token, 'Accept': ACCEPT}

        def read(path):
            return fetch('https://ghcr.io/v2/' + repo + '/' + path, headers)

        raw = read('manifests/' + tag)
        manifest = json.loads(raw)
        if 'manifests' in manifest:
            entry = next((m for m in manifest['manifests'] if m.get('platform', {}).get('os') == 'linux'
                          and m['platform'].get('architecture') == arch), None)
            if entry is None:
                raise Failed(reference + ': no linux/' + arch + ' image')
            raw = read('manifests/' + entry['digest'])
            if 'sha256:' + hashlib.sha256(raw).hexdigest() != entry['digest']:
                raise Failed(reference + ': manifest digest mismatch')
            manifest = json.loads(raw)
        config_raw = read('blobs/' + manifest['config']['digest'])
        if 'sha256:' + hashlib.sha256(config_raw).hexdigest() != manifest['config']['digest']:
            raise Failed(reference + ': image config digest mismatch')
        config = json.loads(config_raw)
    except urllib.error.HTTPError as error:
        raise Failed(f'{reference}: not pullable anonymously (HTTP {error.code})') from None
    if config.get('os') != 'linux' or config.get('architecture') != arch:
        raise Failed(reference + ': image is not linux/' + arch)
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def check_images(found, fetch=fetch):
    failures = []
    for slug, version, manifest in found:
        if 'amd64' not in manifest.get('arch', []):
            failures.append(slug + ': amd64 is not an advertised architecture')
            continue
        if not manifest.get('image'):
            failures.append(slug + ': manifest has no prebuilt image')
            continue
        reference = manifest['image'].replace('{arch}', 'amd64') + ':' + version
        try:
            print(f'{slug} {version}: {reference} pullable ({image_pullable(reference, fetch=fetch)})')
        except Failed as error:
            failures.append(f'{slug} {version}: {error}')
    return failures


def stable_release_exists(tag, fetch=fetch):
    headers = {'Accept': 'application/vnd.github+json'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    try:
        release = json.loads(fetch(f'https://api.github.com/repos/{REPOSITORY}/releases/tags/'
                                   + urllib.parse.quote(tag, safe=''), headers))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise Failed(f'{tag}: GitHub API HTTP {error.code}') from None
    return not release.get('draft') and not release.get('prerelease')


def decision_records(version, root=ROOT):
    """release-decision-*.md files that name this exact version (0.2.2 does not match 0.2.20 or 10.2.2)."""
    pattern = re.compile(r'(?<![0-9.])' + re.escape(version) + r'(?![0-9]|\.[0-9])')
    return sorted(p.name for p in (root / 'docs/operations').glob('release-decision-*.md')
                  if pattern.search(p.read_text(encoding='utf-8')))


def check_decisions(found, root=ROOT, fetch=fetch):
    failures = []
    for slug, version, _ in found:
        tag = f'{slug}-v{version}'
        if stable_release_exists(tag, fetch=fetch):
            print(f'{slug} {version}: already released as {tag}')
            continue
        records = decision_records(version, root)
        if records:
            print(f'{slug} {version}: release record {", ".join(records)}')
        else:
            failures.append(f'{slug} {version}: no docs/operations/release-decision-*.md names {version}; '
                            'record the builder VM acceptance before releasing')
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('check', choices=['images', 'decisions', 'all'])
    parser.add_argument('registry', type=Path)
    args = parser.parse_args(argv)
    try:
        found = components(json.loads(args.registry.read_text(encoding='utf-8')))
        failures = []
        if args.check in ('images', 'all'):
            failures += check_images(found)
        if args.check in ('decisions', 'all'):
            failures += check_decisions(found)
    except Failed as error:
        failures = [str(error)]
    for failure in failures:
        print('::error title=Release gate::' + failure)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
