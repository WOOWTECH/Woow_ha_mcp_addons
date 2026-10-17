"""Fetch one pushed image's manifest, config and layer blobs from a private registry for
delivery_receipt.py (n8n-pilot-image-delivery.md steps 1-4). Read-only; never pushes.

usage: registry_fetch.py HOST/REPO:TAG CREDENTIAL_FILE OUTDIR [--metadata-only]

CREDENTIAL_FILE: mode 0600, two lines: username, token (read:package is enough). The token is
only sent to the registry host over HTTPS: to the bearer realm on the same host, then as a
bearer token. Redirects to another host (blob storage) are followed WITHOUT Authorization.
Nothing secret is printed or written. OUTDIR must not exist; it receives manifest.bin,
manifest.digest, config.bin, blobs/<hex> (unless --metadata-only) and fetch.json.
Every digest is recomputed locally; a mismatch fails before anything is reported.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request

ACCEPT = ', '.join(('application/vnd.oci.image.manifest.v1+json',
                    'application/vnd.docker.distribution.manifest.v2+json'))
REF = re.compile(r'(?P<host>[a-z0-9.-]+(?::\d+)?)/(?P<repo>[a-z0-9._/-]+):(?P<tag>[A-Za-z0-9._-]{1,128})')
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
LIMIT = 4 * 1024 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def credentials(path):
    path = Path(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('credential file must be a regular file with mode 0600')
    lines = path.read_text().splitlines()
    if len(lines) < 2 or not lines[0] or not lines[1]:
        raise ValueError('credential file needs username and token lines')
    return lines[0].strip(), lines[1].strip()


def request(url, headers, host, sink=None):
    """GET url; follow up to 5 redirects, keeping Authorization only on the registry host."""
    for _ in range(6):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != 'https':
            raise ValueError('https required')
        sent = dict(headers)
        if parts.netloc != host:
            sent.pop('Authorization', None)
        try:
            response = OPENER.open(urllib.request.Request(url, headers=sent), timeout=120)
        except urllib.error.HTTPError as error:
            if error.code in (301, 302, 303, 307, 308) and error.headers.get('Location'):
                url = urllib.parse.urljoin(url, error.headers['Location'])
                continue
            raise
        with response:
            if sink is None:
                return response.headers, response.read(LIMIT + 1)
            digest, size = hashlib.sha256(), 0
            for chunk in iter(lambda: response.read(1 << 20), b''):
                size += len(chunk)
                if size > LIMIT:
                    raise ValueError('blob too large')
                digest.update(chunk)
                sink.write(chunk)
            return response.headers, ('sha256:' + digest.hexdigest(), size)
    raise ValueError('too many redirects')


def bearer(host, repo, username, token):
    try:
        OPENER.open(urllib.request.Request('https://%s/v2/' % host), timeout=60).close()
        return {}
    except urllib.error.HTTPError as error:
        challenge = error.headers.get('WWW-Authenticate', '')
    fields = dict(re.findall(r'(\w+)="([^"]*)"', challenge))
    realm = fields.get('realm', '')
    if not challenge.lower().startswith('bearer ') or urllib.parse.urlsplit(realm).netloc != host:
        raise ValueError('unexpected auth challenge (realm must be on the registry host)')
    query = urllib.parse.urlencode({'service': fields.get('service', ''), 'scope': 'repository:%s:pull' % repo})
    basic = base64.b64encode(('%s:%s' % (username, token)).encode()).decode()
    _, body = request(realm + ('&' if '?' in realm else '?') + query, {'Authorization': 'Basic ' + basic}, host)
    value = json.loads(body).get('token') or json.loads(body).get('access_token')
    if not value:
        raise ValueError('no bearer token issued')
    return {'Authorization': 'Bearer ' + value}


def fetch(ref, credential_file, outdir, metadata_only=False):
    match = REF.fullmatch(ref)
    if not match:
        raise ValueError('reference must be HOST/REPO:TAG')
    host, repo, tag = match['host'], match['repo'], match['tag']
    username, token = credentials(credential_file)
    out = Path(outdir)
    out.mkdir(mode=0o700)  # fresh only
    auth = bearer(host, repo, username, token)
    base = 'https://%s/v2/%s' % (host, repo)
    headers, raw = request('%s/manifests/%s' % (base, tag), dict(auth, Accept=ACCEPT), host)
    digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
    announced = headers.get('Docker-Content-Digest', digest)
    if announced != digest:
        raise ValueError('manifest bytes do not hash to Docker-Content-Digest')
    manifest = json.loads(raw)
    config = manifest.get('config', {})
    if not DIGEST.fullmatch(config.get('digest', '')):
        raise ValueError('config descriptor digest format')
    (out / 'manifest.bin').write_bytes(raw)
    (out / 'manifest.digest').write_text(digest + '\n')
    with (out / 'config.bin').open('wb') as sink:
        _, (got, size) = request('%s/blobs/%s' % (base, config['digest']), auth, host, sink)
    if got != config['digest'] or size != config.get('size'):
        raise ValueError('config blob digest/size mismatch')
    layers = []
    if not metadata_only:
        (out / 'blobs').mkdir(mode=0o700)
    for layer in manifest.get('layers') or []:
        if not DIGEST.fullmatch(layer.get('digest', '')):
            raise ValueError('layer digest format')
        if metadata_only:
            layers.append({'digest': layer['digest'], 'evidence': 'metadata-only'})
            continue
        target = out / 'blobs' / layer['digest'].split(':', 1)[1]
        with target.open('wb') as sink:
            _, (got, size) = request('%s/blobs/%s' % (base, layer['digest']), auth, host, sink)
        if got != layer['digest'] or size != layer.get('size'):
            raise ValueError('layer blob digest/size mismatch ' + layer['digest'])
        layers.append({'digest': layer['digest'], 'evidence': 'bytes-verified'})
    summary = {'schema': 1, 'ref': ref, 'manifest_digest': digest, 'config_digest': config['digest'],
               'media_type': manifest.get('mediaType'), 'layers': layers}
    (out / 'fetch.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    return summary


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--metadata-only']
    if len(args) != 3:
        raise SystemExit(__doc__)
    result = fetch(*args, metadata_only='--metadata-only' in sys.argv[1:])
    print('FETCHED %s manifest %s config %s layers %d' % (result['ref'], result['manifest_digest'],
          result['config_digest'], len(result['layers'])))
