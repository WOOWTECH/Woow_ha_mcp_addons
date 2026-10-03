"""CI-only pinned public binaries; no system installation or credential lookup."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import urllib.request

PINS = Path(__file__).with_name('scanner-pins.json')


def install(destination):
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, pin in json.loads(PINS.read_text()).items():
        with urllib.request.urlopen(pin['url'], timeout=120) as response:
            data = response.read(200 * 1024 * 1024 + 1)
        if hashlib.sha256(data).hexdigest() != pin['sha256']:
            raise ValueError('tool integrity mismatch')
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            member = archive.getmember(name)
            if not member.isfile():
                raise ValueError('invalid tool archive')
            target = destination / name
            target.write_bytes(archive.extractfile(member).read())
            target.chmod(0o700)
        # Record executable hash too; candidates recheck before running tools.
        (destination / (name + '.sha256')).write_text(hashlib.sha256(target.read_bytes()).hexdigest())
    print('PASS: checksum-verified pinned scanner binaries installed in isolated directory')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('isolated tool directory required')
        install(Path(sys.argv[1]))
    except Exception:
        raise SystemExit('scanner installation CLOSED (download/integrity failure)') from None
