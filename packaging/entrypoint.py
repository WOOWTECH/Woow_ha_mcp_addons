"""Stock-image bootstrap: own only a new dedicated directory, then drop privilege.

No command override, recursive chown, runtime install or bootstrap HA API call.
Only n8n management receives the runtime Supervisor token (approved pilot).
Existing restored state must already belong to uid/gid 10001.
"""
import ctypes
import os
from pathlib import Path
import stat
import sys

PRODUCTS = ('odoo', 'odoo-manage', 'n8n', 'hermes', 'opendesign', 'emqx', 'litellm')
UID = GID = 10001
ROOT = Path('/opt/woow')


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
