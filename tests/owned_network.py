"""Test-process-only fail-before-syscall sentinel. Not an OS sandbox."""
import os
from pathlib import Path
import subprocess
import sys

from batch2_owned_port import OwnershipError

HERE = Path(__file__).resolve().parent
_installed = False
_spawn_installed = False
forbidden_operations = 0


def check_address(address):
    # Port-only denial also covers IPv6, mapped addresses and unresolved names.
    # Unix socket paths do not have a TCP/UDP port.
    global forbidden_operations
    if isinstance(address, tuple) and len(address) >= 2 and str(address[1]) == '3000':
        forbidden_operations += 1
        raise OwnershipError('test network operation on production port forbidden')


def audit(event, args):
    if event in ('socket.bind', 'socket.connect'):
        check_address(args[1])
    elif event == 'socket.getaddrinfo':
        check_address((args[0], args[1]))
    elif event == 'socket.sendto':
        check_address(args[-1])


def install():
    global _installed
    if not _installed:
        sys.addaudithook(audit)
        _installed = True


def guarded_env(env):
    value = dict(env)
    bootstrap = str(HERE / 'owned_bootstrap')
    paths = value.get('PYTHONPATH', '').split(os.pathsep)
    if bootstrap not in paths:
        value['PYTHONPATH'] = os.pathsep.join([bootstrap, *filter(None, paths)])
    preload = '--require=' + str(HERE / 'owned_network.cjs')
    options = value.get('NODE_OPTIONS', '')
    if preload not in options.split():
        value['NODE_OPTIONS'] = (preload + ' ' + options).strip()
    value['PYTHONDONTWRITEBYTECODE'] = '1'
    return value


def install_subprocess_guard():
    """Carry the sentinel across exec even where real ChildSpecs scrub env.

    Does not change argv/handlers or production specs. Python's sitecustomize and
    Node's preload execute before the actual target. OpenSSL here only generates
    owned test certificates; Chromium is separately origin/IPC guarded.
    """
    global _spawn_installed
    if _spawn_installed:
        return
    original = subprocess.Popen.__init__
    def spawn(self, *args, **kwargs):
        kwargs['env'] = guarded_env(os.environ if kwargs.get('env') is None else kwargs['env'])
        return original(self, *args, **kwargs)
    subprocess.Popen.__init__ = spawn
    _spawn_installed = True
