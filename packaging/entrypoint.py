"""Stock-image bootstrap: own only a new dedicated directory, then drop privilege.

No command override, recursive chown, runtime install or bootstrap HA API call.
Only n8n management receives the runtime Supervisor token (approved pilot).
Existing state must belong to uid/gid 10001. State that Home Assistant restored root-owned (observed in
the 2026-10-05 HA pilot) is re-owned once: pass 1 approves a bounded tree of plain directories and
single-link files by identity, pass 2 changes exactly those inodes after re-verifying each one; any
addition, removal, replacement, link or foreign owner keeps the fail-closed refusal.
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


def _owner(info):
    return (info.st_uid, info.st_gid)


def _identity(info):
    # dev+inode alone is not enough: a replaced file may reuse the freed inode number. ctime_ns is set
    # when an inode is created or changed, and nothing changes the restored tree before the app starts.
    return (info.st_dev, info.st_ino, info.st_ctime_ns)


def _approve_restored(dir_fd, depth, budget):
    """Pass 1, no changes: return the approved tree {name: (identity, children or None)}.

    Only plain directories and single-link regular files owned by the restore owner or the runtime user,
    within the entry and depth limits. A directory is opened without following links and must be the
    same inode and owner that was just checked.
    """
    if depth > MAX_RESTORED_DEPTH:
        raise RuntimeError('restored state too deep')
    approved = {}
    for name in os.listdir(dir_fd):
        budget[0] -= 1
        if budget[0] < 0:
            raise RuntimeError('restored state too large')
        info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        if _owner(info) not in (RESTORE_OWNER, (UID, GID)):
            raise RuntimeError('foreign restored owner')
        if stat.S_ISDIR(info.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
            try:
                opened = os.fstat(child)
                if _identity(opened) != _identity(info) or _owner(opened) != _owner(info):
                    raise RuntimeError('restored state changed during bootstrap')
                approved[name] = (_identity(info), _approve_restored(child, depth + 1, budget))
            finally:
                os.close(child)
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            approved[name] = (_identity(info), None)
        else:
            raise RuntimeError('unsupported restored entry')
    return approved


def _reown_restored(dir_fd, approved):
    """Pass 2: change only the approved entries, each re-verified by identity on its own descriptor.

    The directory must hold exactly the approved names (no additions, removals or renames). Each entry is
    opened without following links (regular files with O_PATH, so nothing is read or triggered) and must
    still be the approved identity (dev, inode, ctime) and type, owned by the restore owner or runtime user,
    with one link; only
    then is that descriptor's inode re-owned. Bootstrap runs before the app as root on a tree only the
    Supervisor wrote, so nothing should change between the passes; if anything does, bootstrap stops.
    Approved entries handled before a change is found keep their new owner: they were approved.
    """
    if sorted(os.listdir(dir_fd)) != sorted(approved):
        raise RuntimeError('restored state changed during bootstrap')
    for name, (identity, children) in approved.items():
        directory = children is not None
        flags = os.O_NOFOLLOW | (os.O_RDONLY | os.O_DIRECTORY if directory else os.O_PATH)
        fd = os.open(name, flags, dir_fd=dir_fd)
        try:
            opened = os.fstat(fd)
            plain = stat.S_ISDIR(opened.st_mode) if directory else (stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1)
            if (_identity(opened) != identity or not plain
                    or _owner(opened) not in (RESTORE_OWNER, (UID, GID))):
                raise RuntimeError('restored state changed during bootstrap')
            if directory:
                _reown_restored(fd, children)
                os.fchown(fd, UID, GID)
                os.fchmod(fd, 0o700)
            else:
                # O_PATH descriptors cannot fchown/fchmod; the magic link names exactly this inode.
                target = '/proc/self/fd/%d' % fd
                os.chown(target, UID, GID)
                os.chmod(target, 0o600)
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
                _reown_restored(child, _approve_restored(child, 0, [MAX_RESTORED_ENTRIES]))
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
    # The approved n8n management verifier alone needs the runtime token.
    # Child env stripping AND post-exec procfs/memory denial are both required.
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/data/mcp',
           'PYTHONPATH': str(ROOT / 'packages/mcp-admin-core') + ':' + str(ROOT / 'apps/n8n'),
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1'}
    if product == 'n8n':
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
