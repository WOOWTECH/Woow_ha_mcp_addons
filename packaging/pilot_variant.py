"""Generate a HA *local app* pilot variant of one product (design: docs/operations/n8n-pilot-image-delivery.md).

Offline only. Reads the public manifest + translations AS BLOBS OF THE GIVEN COMMIT from an explicit
candidate checkout that must be the git worktree top level, whose HEAD must equal the commit and whose
tree is clean (optionally also bound to a verified
source-receipt.json), writes a NEW directory that must lie outside both the candidate checkout and this
tool's repository (parent symlinks resolved first), and a receipt. Derives only from a manifest that
passes validate.manifest(); exactly three fields differ (name, slug, image). version stays equal to the
image label io.hass.version (pinned Supervisor restore compares them), so candidates are told apart by a
per-commit registry path. No network, registry, credential or HA access.

usage: pilot_variant.py CANDIDATE_ROOT PRODUCT COMMIT REGISTRY_PREFIX OUTDIR [SOURCE_RECEIPT]
  REGISTRY_PREFIX: host[:port]/namespace, lowercase, no scheme/tag/digest
  writes OUTDIR/<pilot slug>/{config.yaml,translations/*,README.md} and OUTDIR/variant-receipt.json
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import yaml

from validate import PRODUCTS, ROOT, exact, load, manifest, translation

REGISTRY = re.compile(r'[a-z0-9]([a-z0-9.-]*[a-z0-9])?(:[0-9]{1,5})?(/[a-z0-9]+([._-][a-z0-9]+)*)+')
COMMIT = re.compile(r'[0-9a-f]{40}')
CHANGED = ('name', 'slug', 'image')


def variant(public, product, commit, registry):
    if product not in PRODUCTS:
        raise ValueError('unsupported product')
    if not COMMIT.fullmatch(commit or ''):
        raise ValueError('full lowercase 40-character commit SHA required')
    if not REGISTRY.fullmatch(registry or '') or '/' not in registry:
        raise ValueError('registry prefix must be host[:port]/namespace, lowercase, without scheme/tag/digest')
    manifest(public, product)  # only a valid public manifest may be derived from
    short = commit[:12]
    result = copy.deepcopy(public)
    result['name'] = public['name'] + f' (pilot {short})'
    result['slug'] = public['slug'] + '_pilot'
    result['image'] = f'{registry}/pilot-{short}/amd64-mcp-{product}'
    # Self-check: restoring the three changed fields must give back the public manifest exactly.
    restored = copy.deepcopy(result)
    for key in CHANGED:
        restored[key] = public[key]
    exact(restored, public, product + ' pilot variant')
    if [k for k in result if result[k] != public[k]] != [k for k in public if k in CHANGED]:
        raise ValueError('variant changed fields other than ' + ', '.join(CHANGED))
    return result


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root, *args, binary=False):
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_CONFIG_GLOBAL': os.devnull, 'LC_ALL': 'C'}
    result = subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, *args], cwd=root, env=env,
                            capture_output=True, text=not binary, timeout=60)
    if result.returncode:
        raise ValueError('candidate root is not a usable git checkout')
    return result.stdout


def verify_candidate(root, commit, source_receipt=None):
    """root IS the worktree top level of the named, clean commit; optionally bound to a bundle receipt."""
    if Path(git(root, 'rev-parse', '--show-toplevel').strip()).resolve() != Path(root).resolve():
        raise ValueError('candidate root must be the git worktree top level')
    if git(root, 'rev-parse', 'HEAD').strip() != commit:
        raise ValueError('candidate checkout HEAD differs from the given commit')
    if git(root, 'status', '--porcelain', '--untracked-files=all').strip():
        raise ValueError('candidate checkout is not clean')
    tree = git(root, 'rev-parse', 'HEAD^{tree}').strip()
    if source_receipt is not None:
        receipt = json.loads(Path(source_receipt).read_text())
        if receipt.get('commit') != commit or receipt.get('tree') != tree:
            raise ValueError('source receipt does not bind this commit/tree')
    return tree


def outside(path, *roots):
    """Resolve the parent (symlinks included) and refuse any location inside the given roots."""
    target = Path(path).absolute()
    resolved = target.parent.resolve(strict=True) / target.name
    for root in roots:
        real = Path(root).resolve(strict=True)
        if resolved == real or real in resolved.parents:
            raise ValueError('output must be outside the candidate checkout and the tool repository')
    return resolved


def commit_sources(root, commit, product):
    """Read config.yaml and translations/*.yaml as blobs of the named commit (never the working tree),
    so ignored or untracked files beside them cannot be consumed. Only regular files (mode 100644)."""
    prefix = 'addons/%s/' % product
    listing = git(root, 'ls-tree', '-r', '-z', commit, '--', prefix).split('\0')
    blobs = {}
    for entry in filter(None, listing):
        meta, path = entry.split('\t', 1)
        mode, kind, oid = meta.split()
        rel = path[len(prefix):]
        if rel == 'config.yaml' or (rel.startswith('translations/') and rel.count('/') == 1 and rel.endswith('.yaml')):
            if kind != 'blob' or mode != '100644':
                raise ValueError('source must be a regular committed file: ' + path)
            blobs[rel] = git(root, 'cat-file', 'blob', oid, binary=True)
    if 'config.yaml' not in blobs or not any(k.startswith('translations/') for k in blobs):
        raise ValueError('commit lacks the product manifest or translations')
    return blobs


def write_new(path, data, mode=0o644):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)


def generate(root, product, commit, registry, output, source_receipt=None):
    if product not in PRODUCTS:
        raise ValueError('unsupported product')
    root = Path(root).resolve(strict=True)
    tree = verify_candidate(root, commit, source_receipt)
    output = outside(output, root, ROOT)
    blobs = commit_sources(root, commit, product)
    with tempfile.TemporaryDirectory() as staging:  # parse committed bytes with the strict loader
        staged = Path(staging) / 'config.yaml'
        staged.write_bytes(blobs['config.yaml'])
        public = load(staged)
        for name, data in blobs.items():
            if name.startswith('translations/'):
                (Path(staging) / 'translation.yaml').write_bytes(data)
                translation(load(Path(staging) / 'translation.yaml'))
    result = variant(public, product, commit, registry)
    output.mkdir(mode=0o700)  # fresh only
    app = output / result['slug']
    (app / 'translations').mkdir(parents=True)
    text = yaml.safe_dump(result, sort_keys=False, allow_unicode=True, default_flow_style=False).encode()
    write_new(app / 'config.yaml', text)
    if load(app / 'config.yaml') != result:  # strict loader round trip
        raise ValueError('generated config.yaml does not round-trip')
    sources = {}
    for name, data in sorted(blobs.items()):
        sources['addons/%s/%s' % (product, name)] = hashlib.sha256(data).hexdigest()
        if name.startswith('translations/'):
            write_new(app / name, data)
    write_new(app / 'README.md', (
        f'# {result["name"]}\n\nLocal pilot variant generated from verified clean checkout of commit `{commit}` '
        f'(tree `{tree}`). Not a store release. Image `{result["image"]}:{result["version"]}`. '
        'Data in this app does not migrate to the store version.\n').encode())
    files = sorted(p for p in app.rglob('*') if p.is_file())
    receipt = {'schema': 2, 'product': product, 'commit': commit, 'tree': tree,
               'source_receipt_bound': source_receipt is not None, 'source_files': sources,
               'slug': result['slug'], 'installed_slug': 'local_' + result['slug'], 'image': result['image'],
               'version': result['version'], 'changed_fields': list(CHANGED),
               'files': {str(p.relative_to(output)): digest(p) for p in files}}
    write_new(output / 'variant-receipt.json', (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode(), 0o600)
    return receipt


if __name__ == '__main__':
    if len(sys.argv) not in (6, 7):
        raise SystemExit(__doc__)
    r = generate(*sys.argv[1:])
    print('PASS: pilot variant', r['installed_slug'], r['image'] + ':' + r['version'], 'from', r['commit'])
