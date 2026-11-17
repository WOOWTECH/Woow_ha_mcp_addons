"""Dispatch gate of the GitHub-hosted publication route (.github/workflows/release.yaml): no token, HTTP or checkout.

Owner decision 2026-11-17: the HA add-on line builds, accepts and pushes its images in this repository's own GitHub
Actions on GitHub-hosted runners, not on PaaS infrastructure. A product is admitted only when
  - the run is a manual workflow_dispatch of a refs/heads/release/<name> branch: the open version-bump PR's branch,
    whose readiness check needs the image first. A pull request, a tag or any other branch is refused, and <name> is
    one path segment, as the public-release environment's deployment-branch rule release/* matches;
  - the checkout HEAD, the dispatched GITHUB_SHA and the owner's source_sha input (SOURCE_SHA) are one full lowercase
    40-hex commit, so the owner's approval of the run binds exactly that commit;
  - the product is a store product with an image: OpenDesign is store-disabled and source-version-only, so none is
    built or published;
  - validate.version_for(product) is the version of addons/<product>/config.yaml.
The approval itself is the protected public-release environment (required reviewers, release/* only), a repository
setting this workflow can neither create nor prove (docs/operations/release.md). RELEASE-GATES.json, the clearance file
of the blocked BLD2 route, is not read here any more; validate.py still checks its shape.
"""
import os
import re
import subprocess
import sys

from validate import ROOT, PRODUCTS, Invalid, load, require, version_for

# Store-disabled and source-version-only (0.4.10 on): no OpenDesign image is built, accepted or published.
IMAGELESS = ('opendesign',)
RELEASE_BRANCH = re.compile(r'refs/heads/release/[A-Za-z0-9][A-Za-z0-9._-]*')
COMMIT = re.compile(r'[0-9a-f]{40}')


def check(product):
    require(product in PRODUCTS, 'product not allowed')
    require(product not in IMAGELESS, 'product has no image to publish')
    require(os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch', 'manual event required')
    ref = os.environ.get('GITHUB_REF', '')
    require(RELEASE_BRANCH.fullmatch(ref) is not None, 'release must run from a release/* branch')
    dispatched = os.environ.get('GITHUB_SHA', '')
    require(COMMIT.fullmatch(dispatched) is not None, 'dispatched SHA is not a full commit')
    source = os.environ.get('SOURCE_SHA', '')
    require(COMMIT.fullmatch(source) is not None, 'source_sha must be a full lowercase 40-hex commit')
    require(source == dispatched, 'source_sha is not the head of the dispatched release branch')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    require(head == dispatched, 'checkout differs from the dispatched SHA')
    manifest = load(ROOT / 'addons' / product / 'config.yaml')
    require(manifest.get('version') == version_for(product), 'add-on manifest version is not the release version')
    print(f'PASS: {product} {version_for(product)} from {ref} at the owner-approved source_sha {source}')


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 2, 'product required')
        check(sys.argv[1])
    except Invalid as exc:
        raise SystemExit(str(exc)) from None
