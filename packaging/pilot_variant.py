"""Generate a HA *local app* pilot variant of one product (design: docs/operations/n8n-pilot-image-delivery.md).

Offline only: reads the public manifest + translations, writes a NEW directory outside the store
tree, and a receipt. Derives only from a manifest that passes validate.manifest(); exactly three
fields differ from it (name, slug, image). version stays equal to the image label io.hass.version
(pinned Supervisor restore compares them), so candidates are told apart by a per-commit registry path.
No network, registry, credential or HA access.

usage: pilot_variant.py PRODUCT COMMIT REGISTRY_PREFIX OUTDIR
  REGISTRY_PREFIX: host[:port]/namespace, lowercase, no scheme/tag/digest
  writes OUTDIR/<pilot slug>/{config.yaml,translations/*,README.md} and OUTDIR/variant-receipt.json
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys

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


def write_new(path, data, mode=0o644):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)


def generate(product, commit, registry, output, root=ROOT):
    root, output = Path(root), Path(output).absolute()
    source = root / 'addons' / product
    public = load(source / 'config.yaml')
    result = variant(public, product, commit, registry)
    output.mkdir(mode=0o700)  # fresh only
    app = output / result['slug']
    (app / 'translations').mkdir(parents=True)
    text = yaml.safe_dump(result, sort_keys=False, allow_unicode=True, default_flow_style=False).encode()
    write_new(app / 'config.yaml', text)
    if load(app / 'config.yaml') != result:  # strict loader round trip
        raise ValueError('generated config.yaml does not round-trip')
    for item in sorted((source / 'translations').iterdir()):
        translation(load(item))
        write_new(app / 'translations' / item.name, item.read_bytes())
    write_new(app / 'README.md', (
        f'# {result["name"]}\n\nLocal pilot variant generated from commit `{commit}`. '
        f'Not a store release. Image `{result["image"]}:{result["version"]}`. '
        'Data in this app does not migrate to the store version.\n').encode())
    files = sorted(p for p in app.rglob('*') if p.is_file())
    receipt = {'schema': 1, 'product': product, 'commit': commit, 'slug': result['slug'],
               'installed_slug': 'local_' + result['slug'], 'image': result['image'], 'version': result['version'],
               'changed_fields': list(CHANGED), 'public_config_sha256': digest(source / 'config.yaml'),
               'files': {str(p.relative_to(output)): digest(p) for p in files}}
    write_new(output / 'variant-receipt.json', (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode(), 0o600)
    return receipt


if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    r = generate(*sys.argv[1:])
    print('PASS: pilot variant', r['installed_slug'], r['image'] + ':' + r['version'])
