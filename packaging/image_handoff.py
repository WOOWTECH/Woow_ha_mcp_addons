"""Hands the tested candidate image from the candidate job to the approved publish job, unchanged (no rebuild).

    python packaging/image_handoff.py save APP CANDIDATE_DIR HANDOFF_DIR   candidate job, after the J1900 check
    python packaging/image_handoff.py load APP HANDOFF_DIR EVIDENCE_DIR    publish job; EXPECTED_IMAGE_ID is the
                                                                          candidate job's output image_id; EVIDENCE_DIR
                                                                          holds the downloaded candidate/ and
                                                                          release-evidence/

save: binds the local tag to the tested evidence (supply_chain.verify_current), saves that tag with
`docker image save`, checks that the archive holds exactly that one image (config digest = the tested image ID, the tag,
the tested diffIDs), and writes HANDOFF_DIR/handoff.json (app, version, tag, image ID, diffIDs, source, archive
SHA-256 and size) and the job output image_id (GITHUB_OUTPUT; the value is a checked sha256 ID, nothing else). The
archive travels as a three-day artifact.
load: the expected ID (the candidate job's output, a channel apart from the artifacts) must equal handoff.json's, the
candidate evidence's subject.json's and the J1900 record's (which must say passed); the archive must have the recorded
SHA-256 and the same single image; the tag must not exist yet on this fresh runner; `docker load` must add exactly that
image ID under that tag and nothing else, with the tested diffIDs. Docker keeps the image ID across save and load only
in the classic overlay2 store, which hosted_runner.py ensures first in both jobs. supply_chain.py verify then checks the
image against the whole candidate evidence.

An archive member is accepted only under the names `docker image save` writes (Docker 28.0.4 is the GitHub-hosted
ubuntu-24.04 image's engine, 2026-11-17): moby v28.0.4 image/tarexport/save.go writes manifest.json, repositories (for
tagged images), oci-layout, index.json and blobs/sha256/<digest> files and no links, and pkg/archive adds the
directories blobs/ and blobs/sha256/ but no entry for the root. Any other name, a link or device, a name that is not in
that canonical form (./manifest.json) or a repeated name is refused: Docker and this check must read the same members.
"""
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import subprocess
import sys
import tarfile

import supply_chain
from supply_chain import PRODUCTS, fixed_image, inspect_image, sha, verify_current
from validate import version_for

SHA256_ID = re.compile(r'sha256:[0-9a-f]{64}')
ARCHIVE = 'image.tar'
RECORD = 'handoff.json'
RECORD_KEYS = {'app', 'version', 'tag', 'image_id', 'diff_ids', 'source', 'archive_sha256', 'archive_bytes'}
ARCHIVE_FILES = re.compile(r'manifest\.json|index\.json|oci-layout|repositories|blobs/sha256/[0-9a-f]{64}')
ARCHIVE_DIRECTORIES = ('blobs', 'blobs/sha256')


class Closed(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Closed(message)


def docker(argv, timeout=1800):
    """Runs docker; output is captured and never printed (image metadata only)."""
    try:
        return subprocess.run(['docker', *argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        raise Closed('docker %s could not run' % argv[0]) from None


def read_record(path, what):
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        raise Closed(what + ' missing or not JSON') from None
    require(isinstance(value, dict), what + ' is not an object')
    return value


def check_members(members):
    """Only the canonical docker save names (see the module notes), each once; returns {name: member} of the files."""
    files, seen = {}, set()
    for member in members:
        name = member.name
        normal = posixpath.normpath(name.lstrip('/')).lstrip('./') if name not in ('', '.') else ''
        require(normal not in seen, 'the image archive repeats the member ' + normal)
        seen.add(normal)
        if member.isdir():
            require(name.rstrip('/') in ARCHIVE_DIRECTORIES, 'unexpected directory in the image archive: ' + name[:80])
        else:
            require(member.isfile() and ARCHIVE_FILES.fullmatch(name) is not None,
                    'unexpected member in the image archive: ' + name[:80])
            files[name] = member
    return files


def check_archive(archive, image_id, tag, diff_ids):
    """The archive holds exactly one image: tagged `tag`, config digest `image_id`, diffIDs `diff_ids`."""
    try:
        with tarfile.open(archive) as tar:
            files = check_members(tar.getmembers())
            require('manifest.json' in files, 'the image archive has no manifest.json')
            manifest = json.load(tar.extractfile(files['manifest.json']))
            require(isinstance(manifest, list) and len(manifest) == 1, 'the image archive must hold exactly one image')
            entry = manifest[0]
            require(entry.get('RepoTags') == [tag], 'the image in the archive is not tagged ' + tag)
            require(entry.get('Config') in files and all(layer in files for layer in entry.get('Layers') or []),
                    'the archive manifest names a member the archive does not hold')
            config = tar.extractfile(files[entry['Config']]).read()
            require('sha256:' + hashlib.sha256(config).hexdigest() == image_id,
                    'the archive config digest is not the tested image ID')
            require(json.loads(config)['rootfs']['diff_ids'] == diff_ids, 'the archive diffIDs are not the tested ones')
            require(isinstance(entry.get('Layers'), list) and len(entry['Layers']) == len(diff_ids),
                    'the archive layer count is not the tested one')
    except (tarfile.TarError, KeyError, TypeError, ValueError, AttributeError, OSError):
        raise Closed('the image archive is not a docker save archive of one image') from None


def write_once(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def save(app, candidate, handoff, env=None):
    env = os.environ if env is None else env
    require(app in PRODUCTS, 'product not allowed')
    output = env.get('GITHUB_OUTPUT', '')
    require(bool(output), 'GITHUB_OUTPUT missing: the candidate job outputs the tested image ID')
    subject = verify_current(app, candidate)  # the local tag is the tested, scanned image and its source is HEAD
    image_id, tag = subject['image_id'], fixed_image(app)
    require(SHA256_ID.fullmatch(image_id) is not None, 'the tested image ID is not a sha256 ID')
    require(not handoff.exists(), 'handoff directory already exists')
    handoff.mkdir(mode=0o700)
    archive = handoff / ARCHIVE
    result = docker(['image', 'save', '--output', str(archive), tag])
    require(result.returncode == 0, 'docker image save failed (exit %d)' % result.returncode)
    require(inspect_image(app)['Id'] == image_id, 'the local tag no longer names the tested image')
    check_archive(archive, image_id, tag, subject['diff_ids'])
    record = {'app': app, 'version': version_for(app), 'tag': tag, 'image_id': image_id, 'diff_ids': subject['diff_ids'],
              'source': subject['source'], 'archive_sha256': sha(archive), 'archive_bytes': archive.stat().st_size}
    write_once(handoff / RECORD, record)
    with open(output, 'a') as stream:
        stream.write('image_id=%s\n' % image_id)
    return record


def images():
    """'<image ID> <repository>:<tag>' of every image on this runner."""
    result = docker(['image', 'ls', '--all', '--no-trunc', '--format', '{{.ID}} {{.Repository}}:{{.Tag}}'], timeout=60)
    require(result.returncode == 0, 'docker image ls failed (exit %d)' % result.returncode)
    return {line.strip() for line in result.stdout.decode(errors='replace').splitlines() if line.strip()}


def load(app, handoff, evidence, env=None):
    env = os.environ if env is None else env
    candidate = evidence / 'candidate'
    require(app in PRODUCTS, 'product not allowed')
    expected = env.get('EXPECTED_IMAGE_ID', '')
    require(SHA256_ID.fullmatch(expected) is not None, 'EXPECTED_IMAGE_ID (the candidate job output) is not an image ID')
    tag = fixed_image(app)
    record = read_record(handoff / RECORD, 'handoff.json')
    require(set(record) == RECORD_KEYS and record['app'] == app and record['version'] == version_for(app)
            and record['tag'] == tag and record['image_id'] == expected,
            'handoff.json does not name the candidate job output for ' + tag)
    subject = read_record(candidate / 'subject.json', 'candidate subject.json')
    require(subject.get('app') == app and subject.get('image_id') == expected
            and subject.get('diff_ids') == record['diff_ids'] and subject.get('source') == record['source'],
            'the handed-over image is not the tested candidate (subject.json)')
    j1900 = read_record(evidence / 'release-evidence' / ('j1900-%s.json' % app), 'J1900 record')
    require(j1900.get('passed') is True and j1900.get('image_id') == expected and j1900.get('app') == app
            and j1900.get('version') == version_for(app) and j1900.get('source') == record['source'],
            'the J1900 record did not pass for this image ID')
    archive = handoff / ARCHIVE
    require(archive.is_file() and not archive.is_symlink(), 'image archive missing')
    require(sha(archive) == record['archive_sha256'], 'the image archive SHA-256 differs from handoff.json')
    check_archive(archive, expected, tag, subject['diff_ids'])
    require(docker(['image', 'inspect', tag], timeout=60).returncode != 0, tag + ' already exists on this runner')
    before = images()
    result = docker(['load', '--quiet', '--input', str(archive)])
    require(result.returncode == 0, 'docker load failed (exit %d)' % result.returncode)
    after = images()
    require(before <= after and after - before == {expected + ' ' + tag},
            'docker load added something other than exactly the tested image ID under ' + tag)
    metadata = inspect_image(app)
    require(metadata['Id'] == expected and metadata['RootFS']['Layers'] == subject['diff_ids'],
            'the loaded image is not the tested image ID (Docker must use the classic store)')
    return {'tag': tag, 'image_id': expected}


def main(argv):
    require(len(argv) == 4 and argv[0] in ('save', 'load'), 'usage: image_handoff.py save APP CANDIDATE_DIR HANDOFF_DIR | '
            'load APP HANDOFF_DIR EVIDENCE_DIR')
    if argv[0] == 'save':
        record = save(argv[1], Path(argv[2]), Path(argv[3]))
        print('PASS: saved the tested %s %s (%d bytes) for the publish job' % (record['tag'], record['image_id'],
                                                                               record['archive_bytes']))
    else:
        loaded = load(argv[1], Path(argv[2]), Path(argv[3]))
        print('PASS: loaded %s as the tested %s' % (loaded['tag'], loaded['image_id']))


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except Closed as exc:
        raise SystemExit('image handoff CLOSED: ' + str(exc)) from None
    except (supply_chain.Closed, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise SystemExit('image handoff CLOSED: ' + type(exc).__name__ + ' (candidate evidence or Docker)') from None
