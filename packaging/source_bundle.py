"""Private source transfer for an approved operator builder VM. No network/push.

create: bundle the complete reachable history of ONE reviewed commit from a
throwaway bare clone (the shared repository gets no new refs), plus a receipt.
Relative paths are accepted and resolved against the caller's working
directory before git runs. verify: on the VM, before any build, prove the bundle holds exactly that commit
under one fixed ref, passes fsck, and matches the receipt hash.

Git runs with no system/global config, no hooks and a fresh HOME so credential
helpers, aliases or hooks of the operator account are never consulted. A bundle
carries objects and refs only: no config, hooks, remotes or credentials.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

REF = 'refs/heads/candidate'
SHA = re.compile(r'[0-9a-f]{40}')


def git(args, cwd, home):
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_TERMINAL_PROMPT': '0', 'LC_ALL': 'C'}
    result = subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, *args], cwd=cwd, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
    if result.returncode:
        raise RuntimeError('git ' + args[0] + ' failed: ' + result.stderr.strip()[-300:])
    return result.stdout


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def require_sha(sha):
    if not SHA.fullmatch(sha or ''):
        raise ValueError('full lowercase 40-character commit SHA required')


def create(repo, sha, output):
    require_sha(sha)
    # Absolute before any git call: git runs with cwd set to temporary repositories.
    repo, output = Path(repo).resolve(strict=True), Path(output).absolute()
    output.mkdir(mode=0o700)  # fresh directory only; never reuse earlier evidence
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if git(['cat-file', '-t', sha], repo, tmp).strip() != 'commit':
            raise ValueError('not a commit')
        bare = tmp / 'clone.git'
        git(['clone', '--quiet', '--bare', '--no-local', '--no-tags', str(repo), str(bare)], tmp, tmp)
        git(['update-ref', REF, sha], bare, tmp)
        name = 'woow-mcp-' + sha[:12] + '.bundle'
        bundle = output / name
        git(['bundle', 'create', '--quiet', str(bundle), REF], bare, tmp)
        os.chmod(bundle, 0o600)
        commits = int(git(['rev-list', '--count', sha], bare, tmp))
        tree = git(['rev-parse', sha + '^{tree}'], bare, tmp).strip()
    receipt = {'schema': 1, 'commit': sha, 'tree': tree, 'ref': REF, 'commits': commits,
               'bundle': name, 'sha256': digest(bundle), 'bytes': bundle.stat().st_size}
    path = output / 'source-receipt.json'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write('\n')
    return receipt


def verify(bundle, sha, receipt_path, checkout):
    require_sha(sha)
    bundle, checkout = Path(bundle).resolve(strict=True), Path(checkout).absolute()
    receipt = json.loads(Path(receipt_path).read_text())
    if receipt.get('commit') != sha or receipt.get('ref') != REF or receipt.get('bundle') != bundle.name:
        raise ValueError('receipt does not bind this commit/bundle')
    if digest(bundle) != receipt.get('sha256'):
        raise ValueError('bundle hash mismatch')
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        heads = git(['bundle', 'list-heads', str(bundle)], tmp, tmp).split('\n')
        if [line for line in heads if line] != [sha + ' ' + REF]:
            raise ValueError('bundle must contain exactly the reviewed commit under ' + REF)
        checkout.mkdir(mode=0o700)  # fresh checkout; the build context is this tree only
        git(['init', '--quiet', str(checkout)], tmp, tmp)
        git(['fetch', '--quiet', '--no-tags', str(bundle), REF + ':' + REF], checkout, tmp)
        git(['fsck', '--full', '--strict', '--no-dangling'], checkout, tmp)
        git(['checkout', '--quiet', '--detach', sha], checkout, tmp)
        if git(['rev-parse', 'HEAD'], checkout, tmp).strip() != sha:
            raise ValueError('checkout HEAD differs from reviewed commit')
        if git(['rev-parse', 'HEAD^{tree}'], checkout, tmp).strip() != receipt.get('tree'):
            raise ValueError('tree differs from receipt')
        if git(['status', '--porcelain', '--untracked-files=all'], checkout, tmp).strip():
            raise ValueError('checkout is not clean')
    return receipt


def main(argv):
    if len(argv) == 4 and argv[0] == 'create':
        receipt = create(argv[1], argv[2], argv[3])
    elif len(argv) == 5 and argv[0] == 'verify':
        receipt = verify(argv[1], argv[2], argv[3], argv[4])
    else:
        raise SystemExit('usage: source_bundle.py create REPO SHA OUTDIR | verify BUNDLE SHA RECEIPT CHECKOUT')
    print(argv[0].upper() + ' PASS: ' + receipt['commit'] + ' sha256=' + receipt['sha256'])


if __name__ == '__main__':
    main(sys.argv[1:])
