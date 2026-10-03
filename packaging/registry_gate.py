"""Future release runner only. Never reads local credential stores/PATs.

unused: ephemeral workflow GITHUB_TOKEN only; registry errors are NOT absence.
public: anonymous registry metadata plus a clean-config anonymous Docker pull.
No remote calls occur during packaging validation/unit tests.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from validate import PRODUCTS, VERSION
from supply_chain import verify_current, verify_bundle, verify_remote, require, write_json


def request(url, headers):
    req = urllib.request.Request(url, headers=headers)
    # All endpoints hardcoded HTTPS; do not replay auth through redirects/proxies.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(req, timeout=30)


def main(mode, app, evidence=None):
    if mode not in ('unused', 'public') or app not in PRODUCTS:
        raise ValueError('invalid release selection')
    subject = verify_current(app, Path(evidence)) if mode == 'public' and evidence else None
    if mode == 'public' and subject is None:
        raise ValueError('bound candidate evidence required')
    repo = 'woowtech/amd64-mcp-' + app
    headers = {}
    if mode == 'unused':
        token = os.environ.get('GHCR_TOKEN')
        actor = os.environ.get('GITHUB_ACTOR')
        if not token or not actor:
            raise ValueError('missing ephemeral publisher identity')
        headers['Authorization'] = 'Basic ' + base64.b64encode((actor + ':' + token).encode()).decode()
    query = urllib.parse.urlencode({'service': 'ghcr.io', 'scope': 'repository:' + repo + ':pull'})
    with request('https://ghcr.io/token?' + query, headers) as response:
        bearer = json.load(response)['token']
    try:
        with request(f'https://ghcr.io/v2/{repo}/manifests/{VERSION}', {
            'Authorization': 'Bearer ' + bearer,
            'Accept': 'application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json',
        }) as response:
            digest = response.headers['Docker-Content-Digest']
            raw_manifest = response.read()
            if digest != 'sha256:' + hashlib.sha256(raw_manifest).hexdigest():
                raise ValueError('invalid immutable manifest digest')
    except urllib.error.HTTPError as exc:
        if mode == 'unused' and exc.code == 404:
            # Only registry's explicit MANIFEST_UNKNOWN means an absent version.
            body = json.loads(exc.read(8192))
            if body.get('errors') and all(e.get('code') == 'MANIFEST_UNKNOWN' for e in body['errors']):
                print('PASS: fixed version absent; protected publisher may continue')
                return
        raise ValueError('registry precondition unavailable') from None
    if mode == 'unused':
        raise ValueError('version exists; immutable tags must never be overwritten')
    manifest = json.loads(raw_manifest)
    require(manifest.get('schemaVersion') == 2 and 'manifests' not in manifest)
    require(manifest['config']['digest'] == subject['image_id'])
    require(len(manifest['layers']) == len(subject['diff_ids']))
    reference = f'ghcr.io/{repo}@{digest}'
    with tempfile.TemporaryDirectory(prefix='anonymous-ghcr-') as config:
        # Docker verifies the registry manifest, compressed blob hashes, config
        # digest AND decompressed diffIDs while pulling by immutable digest.
        subprocess.run(['docker', '--config', config, 'pull', '--platform', 'linux/amd64', reference],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pulled = json.loads(subprocess.check_output(['docker', 'image', 'inspect', reference],
                                                   stderr=subprocess.DEVNULL))[0]
        verify_remote(raw_manifest, digest, pulled, subject)
        require(reference in pulled['RepoDigests'])
    directory = Path(evidence)
    verify_bundle(directory, subject)
    candidate = json.loads((directory / 'provenance.json').read_text())
    # Preserve original local identity, scans and archive hash; add registry
    # manifest subject only AFTER verified config/layer identity. Never replace
    # candidate evidence with a different image or silently substitute a digest.
    candidate['subject'].append({'name': 'ghcr.io/' + repo, 'digest': {'sha256': digest[7:]}})
    candidate['predicate']['registry'] = {'manifest_digest': digest, 'config_digest': subject['image_id'],
                                        'reference': reference, 'anonymous_pull_verified': True}
    write_json(directory / 'published-provenance.json', candidate)
    write_json(directory / 'published-digest.json', {'reference': reference, 'config_digest': subject['image_id']})
    print('PASS: exact published manifest/config/layers anonymously verified; unsigned digest-linked evidence')


if __name__ == '__main__':
    try:
        if len(sys.argv) not in (3, 4):
            raise ValueError('mode/app and public candidate evidence required')
        main(*sys.argv[1:])
    except Exception:
        # No third-party exception/header/body/token dumped to a public build log.
        raise SystemExit('registry gate CLOSED; check namespace, version and visibility with approved publisher') from None
