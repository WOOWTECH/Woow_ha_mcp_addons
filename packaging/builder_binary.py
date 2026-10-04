"""Future approved VM only: verify operator-delivered Buildx BEFORE execution.

No downloader and no subprocess. The operator must privately provision the
reviewed release asset at SOURCE. A version string is not byte authentication.
"""
import hashlib
import os
from pathlib import Path
import stat

SOURCE = Path('/opt/woow-builder/buildx-v0.28.0.linux-amd64')
# https://github.com/docker/buildx/releases/download/v0.28.0/checksums.txt
SHA256 = '696bc104bac3bb708eff1af3f8bbc09fda0fd88f5757c1f9b404a35117889224'
MAX_BYTES = 128 * 1024 * 1024


def checked_bytes(path):
    # Refuse links/devices/FIFOs. Hash the same bytes we subsequently write,
    # rather than hashing a pathname then copying a potentially changed file.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES:
            raise ValueError('invalid Buildx asset')
        data = source.read(MAX_BYTES + 1)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('Buildx checksum mismatch; execution denied')
    return data


def install(config):
    data = checked_bytes(SOURCE)
    plugins = config / 'cli-plugins'
    plugins.mkdir(mode=0o700)  # Fresh job only; never replace an existing plugin.
    target = plugins / 'docker-buildx'
    with target.open('xb') as output:
        output.write(data)
    target.chmod(0o500)
    verify(config)


def verify(config):
    plugins = config / 'cli-plugins'
    if not plugins.is_dir() or plugins.is_symlink():
        raise ValueError('missing private plugin directory')
    target = plugins / 'docker-buildx'
    checked_bytes(target)
    if target.stat().st_mode & 0o777 != 0o500:
        raise ValueError('Buildx permissions changed')
