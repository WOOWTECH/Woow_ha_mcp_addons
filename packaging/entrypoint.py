"""Stock-image bootstrap: own only a new dedicated directory, then drop privilege.

No command override, recursive chown, runtime install or bootstrap HA API call.
Each product's management process receives the runtime Supervisor token for the approved HA admin
verifier (n8n 2026-10-04; the other six 2026-10-05, 0.1.1); children are started with allowlisted env.
Existing state must belong to uid/gid 10001. State that Home Assistant restored root-owned (observed in
the 2026-10-05 HA pilot) is re-owned once: plain directories and single-link files only, never following
a link; anything else keeps the fail-closed refusal.
"""
import ctypes
import os
from pathlib import Path
import stat
import sys

PRODUCTS = ('odoo', 'odoo-manage', 'n8n', 'hermes', 'opendesign', 'emqx', 'litellm')
UID = GID = 10001
ROOT = Path('/opt/woow')
RESTORE_OWNER = (0, 0)  # Supervisor extracts a restored app backup as root
MAX_RESTORED_ENTRIES = 4096
MAX_RESTORED_DEPTH = 8


def _check_restored(dir_fd, depth, budget):
    """Pass 1, no changes: only plain dirs and single-link files owned by the restore owner or runtime user."""
    if depth > MAX_RESTORED_DEPTH:
        raise RuntimeError('restored state too deep')
    for name in os.listdir(dir_fd):
        budget[0] -= 1
        if budget[0] < 0:
            raise RuntimeError('restored state too large')
        info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        if (info.st_uid, info.st_gid) not in (RESTORE_OWNER, (UID, GID)):
            raise RuntimeError('foreign restored owner')
        if stat.S_ISDIR(info.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
            try:
                _check_restored(child, depth + 1, budget)
            finally:
                os.close(child)
        elif not (stat.S_ISREG(info.st_mode) and info.st_nlink == 1):
            raise RuntimeError('unsupported restored entry')


def _reown_restored(dir_fd):
    """Pass 2: re-own through descriptors opened without following links, checked against pass-1 types."""
    for name in os.listdir(dir_fd):
        info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        directory = stat.S_ISDIR(info.st_mode)
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | (os.O_DIRECTORY if directory else os.O_NONBLOCK),
                     dir_fd=dir_fd)
        try:
            opened = os.fstat(fd)
            plain = stat.S_ISDIR(opened.st_mode) if directory else (stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1)
            if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino) or not plain:
                raise RuntimeError('restored state changed during bootstrap')
            if directory:
                _reown_restored(fd)
            os.fchown(fd, UID, GID)
            os.fchmod(fd, 0o700 if directory else 0o600)
        finally:
            os.close(fd)


def prepare_data(parent=Path('/data')):
    # Directory fds prevent a substituted symlink from redirecting bootstrap.
    fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            os.mkdir('mcp', mode=0o700, dir_fd=fd)
            created = True
        except FileExistsError:
            created = False
        child = os.open('mcp', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            if created and os.geteuid() == 0:
                os.fchown(child, UID, GID)
            info = os.fstat(child)
            if (not created and os.geteuid() == 0 and (info.st_uid, info.st_gid) == RESTORE_OWNER
                    and RESTORE_OWNER != (UID, GID)):
                _check_restored(child, 0, [MAX_RESTORED_ENTRIES])
                _reown_restored(child)
                os.fchown(child, UID, GID)
                os.fchmod(child, 0o700)
                info = os.fstat(child)
            if (info.st_uid, info.st_gid) != (UID, GID) or stat.S_IMODE(info.st_mode) != 0o700:
                raise RuntimeError('incompatible data ownership')
        finally:
            os.close(child)
    finally:
        os.close(fd)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in PRODUCTS:
        raise RuntimeError('fixed product required')
    product = sys.argv[1]
    os.umask(0o077)
    prepare_data()
    if os.geteuid() == 0:
        os.setgroups([])
        os.setgid(GID)
        os.setuid(UID)
    if (os.getuid(), os.geteuid(), os.getgid()) != (UID, UID, GID):
        raise RuntimeError('runtime privilege drop failed')
    # Linux no_new_privs: later exec cannot gain setuid/file-capability authority.
    if ctypes.CDLL(None, use_errno=True).prctl(38, 1, 0, 0, 0) != 0:
        raise RuntimeError('no_new_privs unavailable')
    python = str(ROOT / '.venv/bin/python')
    # The final interpreter exec MUST enter the trusted post-exec guard.
    args = [str(ROOT / 'packaging/management_launcher.py'), product]
    # Fixed environment; no proxy/Python/provider URL or command injection.
    # The approved management verifier needs the runtime token; it is the only inherited variable.
    # Child env stripping AND post-exec procfs/memory denial are both required.
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/data/mcp',
           'PYTHONPATH': str(ROOT / 'packages/mcp-admin-core') + ':' + str(ROOT / 'apps/n8n'),
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1'}
    token = os.environ.get('SUPERVISOR_TOKEN')
    if token:
        env['SUPERVISOR_TOKEN'] = token
    os.chdir(ROOT)
    os.execve(python, [python, *args], env)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError):
        raise SystemExit('bootstrap unavailable; check protected data ownership and release documentation') from None
