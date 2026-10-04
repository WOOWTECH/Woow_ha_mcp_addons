"""Offline registry evidence for the pilot delivery (n8n-pilot-image-delivery.md steps 1-4) and its assembly.

Two commands, both offline (they read files someone already fetched; no network/registry/HA):

  check MANIFEST_DIGEST MANIFEST_FILE CONFIG_FILE SUBJECT_JSON [BLOB_DIR]
      -> "registry digest sub-evidence" (kind registry-digest-subevidence). NOT a complete delivery
         receipt: it proves only that one manifest/config/layer set is self-consistent and matches the
         tested subject's identity. Prints JSON; exits non-zero on any mismatch.
  assemble SOURCE_RECEIPT VARIANT_RECEIPT SUBJECT_JSON SUBEVIDENCE_JSON REF
      -> the delivery receipt: binds source commit/tree, pilot variant (and its config hash), tested
         subject (image identity + DiffIDs), the registry ref and the sub-evidence, refusing any
         cross-round mix. HA install observations are NOT included (they do not exist offline).

Hash kinds are never compared with each other: manifest layers[].digest is the stored (usually
compressed) blob digest; rootfs.diff_ids are digests of UNCOMPRESSED layer tars (OCI image-spec v1.1.0).

Identity contract (subject fields):
  image_store  "classic" | "containerd"  - which Engine store produced subject.image_id (recommended)
  image_id     docker inspect .Id: classic store = config digest; containerd store = image MANIFEST digest
  config_digest optional explicit config digest
Every field that is present must agree with the evidence; any contradiction fails. Without image_store
the store is inferred from which digest image_id equals, and the receipt says it was inferred.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
COMMIT = re.compile(r'[0-9a-f]{40}')
MANIFEST_TYPES = ('application/vnd.oci.image.manifest.v1+json',
                  'application/vnd.docker.distribution.manifest.v2+json')


def sha(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def identity(subject, manifest_digest, config_digest):
    store = subject.get('image_store')
    require(store in (None, 'classic', 'containerd'), 'unknown image_store')
    image_id = subject.get('image_id')
    require(isinstance(image_id, str) and bool(DIGEST.fullmatch(image_id)), 'subject image_id format')
    if subject.get('config_digest') is not None:
        require(subject['config_digest'] == config_digest, 'config digest differs from tested config digest')
    expected = {'classic': config_digest, 'containerd': manifest_digest}
    if store is not None:
        require(image_id == expected[store], 'image_id contradicts the declared %s image store' % store)
        return {'image_store': store, 'store_source': 'declared'}
    matches = [k for k, v in expected.items() if v == image_id]
    require(len(matches) == 1, 'image_id equals neither the config nor the manifest digest')
    return {'image_store': matches[0], 'store_source': 'inferred'}


def check(manifest_digest, manifest_bytes, config_bytes, subject, blob_dir=None):
    require(bool(DIGEST.fullmatch(manifest_digest)), 'manifest digest format')
    # 1. manifest bytes hash to the digest the registry answered with; single-platform image manifest.
    require(sha(manifest_bytes) == manifest_digest, 'manifest bytes do not hash to manifest digest')
    manifest = json.loads(manifest_bytes)
    require(manifest.get('schemaVersion') == 2, 'schemaVersion')
    require(manifest.get('mediaType') in MANIFEST_TYPES, 'not a single-platform image manifest (index/list rejected)')
    # 2. config blob hashes to its descriptor; identity fields of the subject all agree with it.
    descriptor = manifest.get('config', {})
    require(sha(config_bytes) == descriptor.get('digest'), 'config blob does not hash to its descriptor')
    require(descriptor.get('size') == len(config_bytes), 'config size')
    binding = identity(subject, manifest_digest, descriptor['digest'])
    # 3. diff_ids read from the VERIFIED config equal the tested subject's, in order.
    diff_ids = json.loads(config_bytes).get('rootfs', {}).get('diff_ids')
    require(diff_ids == subject.get('diff_ids'), 'config rootfs.diff_ids differ from tested subject')
    # 4. layer descriptors: only registry self-consistency; never compared with diff_ids.
    layers = manifest.get('layers') or []
    require(len(layers) == len(diff_ids) and len(layers) > 0, 'layer count')
    graded = []
    for layer in layers:
        digest = layer.get('digest', '')
        require(bool(DIGEST.fullmatch(digest)), 'layer digest format')
        blob = Path(blob_dir) / digest.split(':', 1)[1] if blob_dir else None
        if blob is not None and blob.is_file():
            data = blob.read_bytes()
            require(sha(data) == digest and len(data) == layer.get('size'), 'layer blob bytes mismatch ' + digest)
            graded.append({'digest': digest, 'size': layer.get('size'), 'evidence': 'bytes-verified'})
        else:
            graded.append({'digest': digest, 'size': layer.get('size'), 'evidence': 'metadata-only'})
    return {'schema': 2, 'kind': 'registry-digest-subevidence', 'complete_delivery_receipt': False,
            'manifest_digest': manifest_digest, 'config_digest': descriptor['digest'],
            'subject_image_id': subject['image_id'], 'subject_diff_ids': diff_ids, **binding,
            'layers': graded, 'all_layers_bytes_verified': all(g['evidence'] == 'bytes-verified' for g in graded),
            'runtime_identity_in_ha': 'NOT ESTABLISHED (registry reference only)'}


def assemble(source, variant, subject, sub, ref):
    """Bind one round: source -> variant -> tested subject -> registry ref -> digest sub-evidence."""
    commit = source.get('commit')
    require(isinstance(commit, str) and bool(COMMIT.fullmatch(commit)), 'source receipt commit')
    require(variant.get('commit') == commit and variant.get('tree') == source.get('tree'),
            'variant was not generated from this source commit/tree')
    require(subject.get('source') == commit, 'tested subject was built from a different commit')
    require(subject.get('app') == variant.get('product'), 'subject product differs from variant product')
    require(ref == '%s:%s' % (variant.get('image'), variant.get('version')), 'ref is not the variant image:version')
    require(sub.get('kind') == 'registry-digest-subevidence', 'sub-evidence kind')
    require(sub.get('subject_image_id') == subject.get('image_id') and sub.get('subject_diff_ids') == subject.get('diff_ids'),
            'sub-evidence was produced for a different tested subject')
    config_files = [k for k in variant.get('files', {}) if k.endswith('/config.yaml')]
    require(len(config_files) == 1, 'variant receipt must list exactly one config.yaml')
    return {'schema': 1, 'kind': 'pilot-delivery-receipt', 'complete_delivery_receipt': True,
            'commit': commit, 'tree': source['tree'], 'source_bundle_sha256': source.get('sha256'),
            'product': variant['product'], 'installed_slug': variant.get('installed_slug'),
            'variant_config_sha256': variant['files'][config_files[0]], 'ref': ref,
            'image_id': subject['image_id'], 'diff_ids': subject['diff_ids'],
            'image_store': sub['image_store'], 'store_source': sub['store_source'],
            'manifest_digest': sub['manifest_digest'], 'config_digest': sub['config_digest'],
            'all_layers_bytes_verified': sub['all_layers_bytes_verified'],
            'not_included': ['HA/Supervisor/Core versions', 'manifest digests read before/after install',
                             'HA runtime image identity (NOT ESTABLISHED)']}


def main(argv):
    load = lambda p: json.loads(Path(p).read_text())
    if argv[:1] == ['check'] and len(argv) in (5, 6):
        result = check(argv[1], Path(argv[2]).read_bytes(), Path(argv[3]).read_bytes(), load(argv[4]),
                       argv[5] if len(argv) == 6 else None)
    elif argv[:1] == ['assemble'] and len(argv) == 6:
        result = assemble(load(argv[1]), load(argv[2]), load(argv[3]), load(argv[4]), argv[5])
    else:
        raise SystemExit(__doc__)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main(sys.argv[1:])
