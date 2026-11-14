"""HM-07: what is under /data/mcp/profiles and whether it agrees with the index (not wired yet).

Multi-profile plan §4.1, §4.4, §8.2 I2; FM-13, FM-30. An indexed profile without its directory or a readable state is
`unavailable` (never re-created, only deletable); a profile directory the index does not list is an orphan (never
opened or routed); `.quarantine-*` directories can only be deleted; tokens and child tokens must be unique across
profiles (a copied directory shares both: 撞號, refused by HM-08 with 503). HM-07 only reports these facts and deletes
nothing; acting on them (logging, 503, refusing a start, deleting: the deletion rules are DQ-14's, not decided yet)
belongs to HM-08, HM-09, HM-10 and HM-13b.
"""
from datetime import datetime, timedelta, timezone
import os
import secrets
import shutil

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import profiles
from mcp_admin_core.config import State, Store
from mcp_admin_core.profiles import IndexEntry, ProfilesScan

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan

A, B, C, D = ('a' * 24, 'b' * 24, 'c' * 24, 'd' * 24)
WHEN = datetime(2026, 11, 14, 13, 55, 1, tzinfo=timezone.utc)


def state():
    return State(token=secrets.token_urlsafe(32), child_token=secrets.token_urlsafe(32))


def credentials(value):
    return (value.token, value.child_token)


def test_layout_paths(tmp_path):
    layout = profiles.Layout(tmp_path)
    assert layout.root == tmp_path
    assert layout.index == tmp_path / 'profiles.json'
    assert layout.index_operations == tmp_path / '.profiles.json.operations.json'
    assert layout.profiles == tmp_path / 'profiles'
    assert layout.profile(A) == tmp_path / 'profiles' / A
    assert layout.child(A) == tmp_path / 'profiles' / A / 'child'
    assert (layout.sentinel.name, layout.instance_record.name, layout.restore_marker.name,
            layout.revoke_all_marker.name, layout.restore_record.name) == (
        '.instance-sentinel', '.instance-record', '.restore-detected', '.revoke-all-pending', 'restore-record.json')
    for value in ('default', '../' + A[3:], A.upper(), A + '/x', '', '.', '..'):
        with pytest.raises(ValueError):
            layout.profile(value)


def test_quarantine_names():
    name = profiles.quarantine_name(A, WHEN)
    assert name == '.quarantine-' + A + '-20261114T135501Z'
    assert profiles.parse_quarantine_name(name) == (A, '20261114T135501Z')
    local = WHEN.astimezone(timezone(timedelta(hours=8)))
    assert profiles.quarantine_name(A, local) == name  # always written in UTC
    assert profiles.index_quarantine_name(WHEN) == 'profiles.json.quarantine-20261114T135501Z'
    for value in ('.quarantine-' + A, '.quarantine-' + A + '-20261114T135501', '.quarantine-' + A.upper()
                  + '-20261114T135501Z', 'quarantine-' + A + '-20261114T135501Z', A, '.quarantine-x-20261114T135501Z',
                  '.quarantine-' + A + '-20261114T135501Z/', name + '\n'):
        assert profiles.parse_quarantine_name(value) is None
    with pytest.raises(ValueError):
        profiles.quarantine_name(A, datetime(2026, 11, 14, 13, 55, 1))  # naive: no time zone
    with pytest.raises(ValueError):
        profiles.quarantine_name('default', WHEN)


def test_scan_of_a_single_profile_installation_is_empty(tmp_path):
    assert profiles.scan_profiles(profiles.Layout(tmp_path)) == ProfilesScan((), (), 0)
    assert os.listdir(tmp_path) == []


def test_scan_sorts_entries_by_kind_without_following_links(tmp_path):
    layout = profiles.Layout(tmp_path)
    profiles.ensure_profiles_directory(layout)
    base = layout.profiles
    for name in (A, B):
        (base / name).mkdir(mode=0o700)
    quarantined = profiles.quarantine_name(C, WHEN)
    (base / quarantined).mkdir(mode=0o700)
    (base / D).write_text('x')                                  # an id-named file is no profile
    (tmp_path / 'elsewhere').mkdir()
    (base / ('e' * 24)).symlink_to(tmp_path / 'elsewhere')       # nor an id-named link to a directory
    (base / 'tmp').mkdir()
    (base / '.quarantine-bad').mkdir()
    (base / (profiles.quarantine_name('f' * 24, WHEN))).write_text('x')  # a quarantine name, but a file
    scan = profiles.scan_profiles(layout)
    assert scan == ProfilesScan((A, B), (quarantined,), 5)


def test_scan_refuses_a_profiles_entry_it_cannot_trust(tmp_path, monkeypatch):
    for name, setup in (('symlink', lambda p: (p.with_name('real').mkdir(), p.symlink_to('real'))),
                        ('file', lambda p: p.write_text('x'))):
        root = tmp_path / name
        root.mkdir()
        setup(root / 'profiles')
        with pytest.raises(profiles.ProfileDataError):
            profiles.scan_profiles(profiles.Layout(root))
    layout = profiles.Layout(tmp_path / 'owned')
    (tmp_path / 'owned').mkdir()
    profiles.ensure_profiles_directory(layout)
    real_fstat = os.fstat

    def other_owner(fd):
        fields = list(real_fstat(fd))
        fields[4] += 1  # st_uid
        return os.stat_result(fields)

    monkeypatch.setattr(profiles.os, 'fstat', other_owner)
    with pytest.raises(profiles.ProfileDataError):
        profiles.scan_profiles(layout)


def test_everything_consistent(tmp_path):
    default, first, second = state(), state(), state()
    entries = (IndexEntry(A, 'One', 18000), IndexEntry(B, 'Two', 18001))
    result = profiles.check_consistency(entries, ProfilesScan((A, B), (), 0),
                                        {'default': credentials(default), A: credentials(first),
                                         B: credentials(second)})
    assert result == profiles.Consistency(unavailable=(), orphans=(), quarantined=(), other_entries=0,
                                          port_conflicts={}, shared_secrets=())


def test_a_missing_or_unreadable_profile_affects_only_itself(tmp_path, log_scan):
    # PaaS test_profiles.py:192: the other profiles and the start are unaffected; HA marks it profile_unavailable,
    # never re-creates it (an existing-only open refuses), and it can still be deleted (HM-10).
    layout = profiles.Layout(tmp_path)
    profiles.ensure_profiles_directory(layout)
    values = {}
    for name in (A, B, C):
        values[name] = state()
        Store(layout.profile(name), create=values[name]).close()
    for value in values.values():
        log_scan.watch_state(value)
    shutil.rmtree(layout.profile(A))                       # gone
    (layout.profile(B) / 'state.json').write_text('{')     # unreadable
    entries = (IndexEntry(A, 'One', 18000), IndexEntry(B, 'Two', 18001), IndexEntry(C, 'Three', 18002))
    read = {}
    for entry in entries:
        try:
            store = Store(layout.profile(entry.id), existing_only=True)
        except Exception:
            read[entry.id] = None
            continue
        read[entry.id] = credentials(store.load())
        store.close()
    result = profiles.check_consistency(entries, profiles.scan_profiles(layout), read)
    assert result.unavailable == (A, B) and result.orphans == () and result.shared_secrets == ()
    assert not layout.profile(A).exists()  # nothing was re-created
    assert read[C] == credentials(values[C])


def test_orphans_quarantine_and_other_entries_are_reported(tmp_path):
    scan = ProfilesScan((A, B, C), (profiles.quarantine_name(D, WHEN),), 2)
    result = profiles.check_consistency((IndexEntry(B, 'Two', 18001),), scan, {B: credentials(state())})
    assert (result.orphans, result.quarantined, result.other_entries, result.unavailable) == (
        (A, C), (profiles.quarantine_name(D, WHEN),), 2, ())


def test_a_copied_profile_directory_shares_its_tokens(tmp_path, log_scan):
    # I2: creation always makes new tokens (profile_initial_state); a copy (by hand, or a restore mixing trees) is
    # the only way two profiles share a token. Both are reported; HM-08 answers 503 and routes to neither (DQ-09).
    layout = profiles.Layout(tmp_path)
    profiles.ensure_profiles_directory(layout)
    original = state()
    log_scan.watch_state(original)
    Store(layout.profile(A), create=original).close()
    shutil.copytree(layout.profile(A), layout.profile(B))
    read = {}
    for name in (A, B):
        store = Store(layout.profile(name), existing_only=True)
        read[name] = credentials(store.load())
        store.close()
    entries = (IndexEntry(A, 'One', 18000), IndexEntry(B, 'Two', 18001))
    result = profiles.check_consistency(entries, profiles.scan_profiles(layout), read)
    assert result.shared_secrets == ((A, B),)
    copied_default = profiles.check_consistency(entries, profiles.scan_profiles(layout),
                                                {'default': read[A], A: credentials(state()), B: read[B]})
    assert copied_default.shared_secrets == (('default', B),)  # the default profile first, then index order


def test_shared_secrets_compare_every_token_kind_and_ignore_revoked_tokens():
    one, two, three = state(), state(), state()
    entries = (IndexEntry(A, 'One', 18000), IndexEntry(B, 'Two', 18001), IndexEntry(C, 'Three', 18002))
    scan = ProfilesScan((A, B, C), (), 0)
    # A's MCP token is B's child token: one credential that would authenticate as two profiles.
    crossed = profiles.check_consistency(entries, scan, {A: (one.token, one.child_token),
                                                         B: (two.token, one.token), C: credentials(three)})
    assert crossed.shared_secrets == ((A, B),)
    revoked = profiles.check_consistency(entries, scan, {A: (None, one.child_token), B: (None, two.child_token),
                                                         C: credentials(three)})
    assert revoked.shared_secrets == ()  # a revoked token (None) is no credential
    groups = profiles.check_consistency(entries, scan, {A: credentials(one), B: credentials(one),
                                                        C: (three.token, one.child_token)})
    assert groups.shared_secrets == ((A, B, C),)
    ordered = profiles.check_consistency((IndexEntry(C, 'Three', 18002), IndexEntry(A, 'One', 18000)),
                                         ProfilesScan((A, C), (), 0),
                                         {A: credentials(one), C: credentials(one), D: credentials(one)})
    assert ordered.shared_secrets == ((C, A, D),)  # index order, then any other profile given (an orphan) by id


def test_port_conflicts_are_part_of_the_check():
    entries = (IndexEntry(A, 'One', 18000), IndexEntry(B, 'Two', 18000), IndexEntry(C, 'Three', 3000),
               IndexEntry(D, 'Four', 8099))
    result = profiles.check_consistency(entries, ProfilesScan((A, B, C, D), (), 0),
                                        {A: credentials(state()), B: credentials(state()), C: credentials(state()),
                                         D: credentials(state())})
    assert result.port_conflicts == {18000: (A, B), 3000: (C,), 8099: (D,)}
    assert result.unavailable == ()  # a conflicting port stops the child, it does not make the profile unavailable


def test_profile_data_presence(tmp_path, monkeypatch):
    # Plan §3.3: "磁碟上有帳號資料" = profiles.json or profiles/ exists (any kind of entry, links included). A check that
    # cannot tell answers yes: that direction only revokes more (HM-13b) or refuses a start (HM-13a).
    assert not profiles.has_profile_data(tmp_path)
    assert not profiles.has_profile_data(tmp_path / 'missing')
    Store(tmp_path / 'mcp').close()
    assert not profiles.has_profile_data(tmp_path / 'mcp')
    for name, make in (('profiles.json', lambda p: p.write_text('{}')), ('profiles', lambda p: p.mkdir()),
                       ('profiles.json', lambda p: p.symlink_to('nowhere'))):
        root = tmp_path / ('case-' + str(len(list(tmp_path.iterdir()))))
        root.mkdir()
        make(root / name)
        assert profiles.has_profile_data(root), name
    listed = sorted(os.listdir(tmp_path / 'mcp'))
    real_lstat = os.lstat

    def denied(path, *args, **kwargs):
        if os.path.basename(path) in ('profiles.json', 'profiles'):
            raise PermissionError('injected')
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(profiles.os, 'lstat', denied)
    assert profiles.has_profile_data(tmp_path / 'mcp')
    monkeypatch.undo()
    assert sorted(os.listdir(tmp_path / 'mcp')) == listed  # only looked
