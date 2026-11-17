"""Dispatch gate of the GitHub-hosted publication route (.github/workflows/release.yaml): no token, HTTP or checkout.

Owner decision 2026-11-17: the HA add-on line builds, accepts and pushes its images in this repository's own GitHub
Actions on GitHub-hosted runners, not on PaaS infrastructure. Every job of the route (gate, candidate, publish) admits
a product only when
  - the run is a manual workflow_dispatch of a refs/heads/release/<name> branch: the open version-bump PR's branch,
    whose readiness check needs the image first. A pull request, a tag or any other branch is refused, and <name> is
    one path segment, as the public-release environment's deployment-branch rule release/* matches;
  - it is the run's first attempt: a re-run reuses the original commit and inputs, and an approval binds one attempt,
    so starting again means a new dispatch;
  - the checkout HEAD, GITHUB_SHA and the owner's source_sha input (SOURCE_SHA) are one full lowercase 40-hex commit.
    GITHUB_SHA is the branch head at the moment of the dispatch; nothing here proves it is still the head, or that it
    is the PR head the owner reviewed: the owner checks that on the run page before approving;
  - the product is a store product with an image: OpenDesign is store-disabled and source-version-only, so none is
    built or published;
  - validate.version_for(product) is the version of addons/<product>/config.yaml.
This runs from the dispatched branch, like the workflow itself, so it holds only if that branch carries the reviewed
packaging code (docs/operations/release.md, "限制"). The owner's approval is the protected public-release environment,
whose settings environment_gate.py checks. RELEASE-GATES.json, the clearance file of the blocked BLD2 route, is not
read here any more; validate.py still checks its shape.
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
    attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '')
    require(attempt == '1', 'a re-run (attempt %r) is refused: dispatch a new run instead' % attempt)
    dispatched = os.environ.get('GITHUB_SHA', '')
    require(COMMIT.fullmatch(dispatched) is not None, 'dispatched SHA is not a full commit')
    source = os.environ.get('SOURCE_SHA', '')
    require(COMMIT.fullmatch(source) is not None, 'source_sha must be a full lowercase 40-hex commit')
    require(source == dispatched, 'source_sha is not the commit this run was dispatched at (GITHUB_SHA)')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    require(head == dispatched, 'checkout differs from the dispatched SHA')
    manifest = load(ROOT / 'addons' / product / 'config.yaml')
    require(manifest.get('version') == version_for(product), 'add-on manifest version is not the release version')
    print(f'PASS: {product} {version_for(product)} from {ref}, dispatched at the owner-given source_sha {source}')


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 2, 'product required')
        check(sys.argv[1])
    except Invalid as exc:
        raise SystemExit(str(exc)) from None
