"""HM-07 mode/owner probe, run as uid 10001 (the add-on user) by tests/test_profile_store.py (root only, the CI).

Root (euid 0) passes every mode and owner check on any file, so the proof that the profile data layer writes 0700
directories and 0600 files owned by the add-on user, tightens widened ones and refuses entries another uid owns runs
here, after a real privilege drop (multi-profile plan §10.1, C4-SF-6; FM-97). The parent prepares the root-owned
entries a restore leaves behind; this probe only reports what it found as JSON on stdout (never a token).

Every module is imported here, at module level, while the process is still root: after the drop the checkout may not
be readable by uid 10001 (a CI runner's home directory need not be open to other users).
"""
import json
import os
from pathlib import Path
import secrets
import stat
import sys

from mcp_admin_core import profiles
from mcp_admin_core.config import State, Store


def facts(path):
    info = os.lstat(path)
    return {'mode': oct(stat.S_IMODE(info.st_mode)), 'uid': info.st_uid, 'gid': info.st_gid, 'nlink': info.st_nlink,
            'type': 'dir' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) else 'other'}


def outcome(action):
    try:
        action()
    except Exception as exc:  # the type only: messages could name paths
        return 'refused:' + type(exc).__name__
    return 'ok'


def watch_chmod():
    """List every chmod of an entry another uid owns (HM-07 review S-03). The kernel refuses such a chmod anyway
    (EPERM), so a refusal alone cannot tell the owner check from the kernel: the owner check refuses before any chmod
    exactly when this list stays empty. Only the kind of call is kept, never a path."""
    tried = []
    real_fchmod, real_chmod = os.fchmod, os.chmod

    def fchmod(fd, mode):
        if os.fstat(fd).st_uid != os.geteuid():
            tried.append('fchmod')
        return real_fchmod(fd, mode)

    def chmod(path, mode, *, dir_fd=None, follow_symlinks=True):
        try:
            owner = os.stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks).st_uid
        except OSError:
            owner = None
        if owner is not None and owner != os.geteuid():
            tried.append('chmod')
        return real_chmod(path, mode, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    os.fchmod, os.chmod = fchmod, chmod
    return tried


def main(config):
    report = {'uid': os.getuid(), 'euid': os.geteuid(), 'gid': os.getgid()}
    foreign_chmod = watch_chmod()
    layout = profiles.Layout(Path(config['data']))
    first = config['first']
    profiles.ensure_profiles_directory(layout)
    report['profiles_dir'] = facts(layout.profiles)
    state = State(token=secrets.token_urlsafe(32), child_token=secrets.token_urlsafe(32))
    store = Store(layout.profile(first), create=state)
    store.close()
    directory = layout.profile(first)
    report['created'] = {name: facts(path) for name, path in (
        ('dir', directory), ('lock', directory / '.writer.lock'), ('state', directory / 'state.json'))}
    report['created_names'] = sorted(os.listdir(directory))
    view = profiles.write_index(layout.index, [profiles.IndexEntry(first, 'probe', profiles.FIRST_PROFILE_PORT)],
                                expected=profiles.read_index(layout.index))
    report['index'] = facts(layout.index)
    report['index_read'] = profiles.read_index(layout.index).state
    report['index_baseline'] = profiles.recheck_index(layout.index, view).state
    # Widened as an fsGroup-style permission change would leave them; an existing-only open tightens them again.
    os.chmod(directory, 0o755)
    os.chmod(directory / 'state.json', 0o644)
    os.chmod(directory / '.writer.lock', 0o644)
    reopened = Store(directory, existing_only=True)
    report['reopened_equal'] = reopened.load() == state
    reopened.close()
    report['tightened'] = {name: facts(path)['mode'] for name, path in (
        ('dir', directory), ('lock', directory / '.writer.lock'), ('state', directory / 'state.json'))}
    foreign = profiles.Layout(Path(config['foreign']))
    report['foreign'] = {name: outcome(lambda name=name: Store(foreign.profile(name), existing_only=True).close())
                         for name in config['foreign_profiles']}
    report['foreign_state_mode_after'] = {name: facts(foreign.profile(name) / 'state.json')['mode']
                                          for name in config['foreign_profiles']}
    report['foreign_index'] = profiles.read_index(foreign.index).state
    report['foreign_scan'] = sorted(profiles.scan_profiles(foreign).profiles)
    rooted = profiles.Layout(Path(config['rooted']))
    report['rooted_ensure'] = outcome(lambda: profiles.ensure_profiles_directory(rooted))
    report['rooted_scan'] = outcome(lambda: profiles.scan_profiles(rooted))
    report['foreign_chmod'] = list(foreign_chmod)
    return report


if __name__ == '__main__':
    settings = json.loads(sys.argv[1])
    os.setgroups([])
    os.setgid(settings['gid'])
    os.setuid(settings['uid'])
    os.umask(0o077)  # as packaging/entrypoint.py runs the add-on
    if (os.getuid(), os.geteuid(), os.getgid()) != (settings['uid'], settings['uid'], settings['gid']):
        raise SystemExit('privilege drop failed')
    print(json.dumps(main(settings), sort_keys=True), flush=True)
