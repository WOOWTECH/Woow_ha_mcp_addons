"""Offline registry-evidence check for the pilot delivery receipt (n8n-pilot-image-delivery.md steps 1-4).

Reads files someone already fetched (no network here): the raw manifest bytes, the config blob, the
tested candidate's subject.json and, optionally, layer blobs. Two hash kinds are never compared with
each other: manifest layers[].digest is the digest of the stored (usually compressed) blob, while
rootfs.diff_ids are digests of UNCOMPRESSED layer tars (OCI image-spec v1.1.0).

usage: delivery_receipt.py MANIFEST_DIGEST MANIFEST_FILE CONFIG_FILE SUBJECT_JSON [BLOB_DIR]
  BLOB_DIR holds layer blobs named by digest hex; a missing blob is graded metadata-only.
Prints the receipt JSON; exits non-zero on any mismatch.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
MANIFEST_TYPES = ('application/vnd.oci.image.manifest.v1+json',
                  'application/vnd.docker.distribution.manifest.v2+json')


def sha(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def check(manifest_digest, manifest_bytes, config_bytes, subject, blob_dir=None):
    def require(ok, message):
        if not ok:
            raise ValueError(message)
    require(bool(DIGEST.fullmatch(manifest_digest)), 'manifest digest format')
    # 1. manifest bytes hash to the digest the registry answered with; single-platform image manifest.
    require(sha(manifest_bytes) == manifest_digest, 'manifest bytes do not hash to manifest digest')
    manifest = json.loads(manifest_bytes)
    require(manifest.get('schemaVersion') == 2, 'schemaVersion')
    require(manifest.get('mediaType') in MANIFEST_TYPES, 'not a single-platform image manifest (index/list rejected)')
    # 2. config blob hashes to its descriptor, which must equal the tested image ID.
    descriptor = manifest.get('config', {})
    require(sha(config_bytes) == descriptor.get('digest'), 'config blob does not hash to its descriptor')
    require(descriptor.get('size') == len(config_bytes), 'config size')
    require(descriptor['digest'] == subject['image_id'], 'config digest is not the tested image ID')
    # 3. diff_ids read from the VERIFIED config equal the tested subject's, in order.
    config = json.loads(config_bytes)
    diff_ids = config.get('rootfs', {}).get('diff_ids')
    require(diff_ids == subject['diff_ids'], 'config rootfs.diff_ids differ from tested subject')
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
    return {'schema': 1, 'manifest_digest': manifest_digest, 'config_digest': descriptor['digest'],
            'image_id_matches_tested': True, 'config_diff_ids_match_subject': True,
            'layers': graded, 'all_layers_bytes_verified': all(g['evidence'] == 'bytes-verified' for g in graded),
            'runtime_identity_in_ha': 'NOT ESTABLISHED (registry reference only)'}


if __name__ == '__main__':
    if len(sys.argv) not in (5, 6):
        raise SystemExit(__doc__)
    receipt = check(sys.argv[1], Path(sys.argv[2]).read_bytes(), Path(sys.argv[3]).read_bytes(),
                    json.loads(Path(sys.argv[4]).read_text()), sys.argv[5] if len(sys.argv) == 6 else None)
    print(json.dumps(receipt, indent=2, sort_keys=True))
