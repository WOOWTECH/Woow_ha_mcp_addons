"""HM-07: an additional profile's store (open existing only, one-write creation, owner checks) and its first state.

Multi-profile plan §4.1, §4.3, §8.2 (I2, I5, I6), §10.1; DQ-02 (a) (2026-11-14): a new profile copies the default
profile's current policy, gets new tokens and no backend, never the n8n session settings, and creation records no
token history. Not wired yet: nothing in the add-on creates or opens an additional profile.

Mode and owner: asserted directly (stat), with a foreign owner simulated by a different effective uid, and once more
for real in a uid 10001 process (test_mode_and_owner_as_the_add_on_user; it needs root, so only the CI runs it).
"""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import features, products, profiles
from mcp_admin_core.config import ConfigError, State, Store
from mcp_admin_core.products import (
    N8nSession, OdooWriteSwitches, ProductState, ProductStore, TOOLS, profile_initial_state, write_grants,
)
from mcp_admin_core.surface import full_tools

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan

ROOT = Path(__file__).resolve().parents[1]
A, B, C, D, E = ('a' * 24, 'b' * 24, 'c' * 24, 'd' * 24, 'e' * 24)
SUPPORTED = ('odoo', 'n8n', 'hermes', 'emqx', 'litellm', 'nextcloud', 'headscale')
# tests/fixtures/owner_defaults/README.md rules: DUMMY- credentials, .invalid hosts, tokens made while the test runs.
CONNECTIONS = {
    'odoo': {'url': 'https://odoo.invalid', 'database': 'DUMMY-db', 'username': 'DUMMY-user',
             'password': 'DUMMY-store-odoo-password'},
    'hermes': {'gateway_url': 'https://hermes.invalid', 'gateway_api_key': 'DUMMY-store-hermes-key',
               'dashboard_url': 'https://dashboard.invalid', 'dashboard_username': 'DUMMY-admin',
               'dashboard_password': 'DUMMY-store-dashboard-password'},
    'emqx': {'url': 'https://emqx.invalid', 'api_key': 'DUMMY-store-emqx-key', 'api_secret': 'DUMMY-store-emqx-secret'},
    'litellm': {'url': 'https://litellm.invalid', 'master_key': 'DUMMY-store-litellm-key'},
    'nextcloud': {'url': 'https://nextcloud.invalid', 'username': 'DUMMY-user',
                  'app_password': 'DUMMY-store-nextcloud-app-password'},
    'headscale': {'url': 'https://headscale.invalid', 'api_key': 'DUMMY-store-headscale-key'},
}


def tools(product):
    return full_tools('n8n') if product == 'n8n' else TOOLS[product]


def configured_default(directory, product):
    """The default profile of an installed add-on: backend saved, a policy the administrator changed, an endpoint,
    one token rotation, and (Odoo, n8n) the product's own settings."""
    store = ProductStore(directory, product)
    names = sorted(tools(product))
    grants = sorted(write_grants(product))
    changes = dict(writes_enabled=False, disabled=names[:2], enabled_write_tools=grants[1:4],
                   denied_operations={names[-1]: ['DUMMY.operation']}, endpoint='https://ha.invalid/mcp')
    if product == 'n8n':
        changes.update(backend_url='https://n8n.invalid', backend_key='DUMMY-store-n8n-key',
                       mcp_access_token='DUMMY-store-n8n-mcp-token',
                       n8n_session=N8nSession(timeout_seconds=900, max_sessions=5))
    else:
        changes['connection'] = CONNECTIONS[product]
    if product == 'odoo':
        changes.update(odoo_write_switches=OdooWriteSwitches(enable_writes=False, allow_direct_writes=True,
                                                             allow_unknown_methods=False, chatter_direct=True),
                       odoo_allowed_methods=['res.partner.message_post', 'sale.order.action_confirm'])
    store.update(**changes)
    store.change_token(secrets.token_urlsafe(32), action='rotate')
    return store


def snapshot(path):
    info = os.lstat(path)
    return hashlib.sha256(path.read_bytes()).hexdigest(), info.st_ino, info.st_mtime_ns, stat.S_IMODE(info.st_mode)


def mode(path):
    return stat.S_IMODE(os.lstat(path).st_mode)


def plain_state():
    return State(token=secrets.token_urlsafe(32), child_token=secrets.token_urlsafe(32))


def watch(log_scan, *states):
    for state in states:
        log_scan.watch_state(state)


# ---------------------------------------------------------------------------------------------------------------
# DQ-02: the first state of an additional profile
# ---------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('product', SUPPORTED)
def test_new_profile_copies_the_current_policy_and_nothing_else(tmp_path, log_scan, product):
    store = configured_default(tmp_path / 'mcp', product)
    default = store.load()
    before = snapshot(store.path)
    taken = {secrets.token_urlsafe(32) for _ in range(4)}
    new = profile_initial_state(default, taken=taken)
    watch(log_scan, default, new)
    assert type(new) is ProductState and new.schema_version == 4 and new.product == product
    # New credentials: the 43-character format, distinct from each other, the default's and every taken value (I2).
    for value in (new.token, new.child_token):
        assert len(value) == 43 and value not in taken | {default.token, default.child_token}
    assert new.token != new.child_token
    # No backend identity of its own yet, and none borrowed (I5): the connection is empty, the endpoint is not stored.
    assert (new.connection, new.backend_url, new.backend_key, new.mcp_access_token, new.endpoint) == (None,) * 5
    assert not new.configured
    # The default profile's policy as it is now.
    assert (new.writes_enabled, new.disabled, new.enabled_write_tools, new.denied_operations) == (
        default.writes_enabled, default.disabled, default.enabled_write_tools, default.denied_operations)
    assert new.disabled is not default.disabled and new.denied_operations is not default.denied_operations
    if product == 'odoo':
        assert new.odoo_write_switches == default.odoo_write_switches
        assert new.odoo_allowed_methods == default.odoo_allowed_methods
    else:
        assert (new.odoo_write_switches, new.odoo_allowed_methods) == (None, None)
    # Never copied: the n8n session settings (DQ-02), the owner-defaults marker; creation is no token change.
    assert (new.n8n_session, new.owner_defaults_20261025, new.token_history) == (None, None, None)
    assert default.token_history and default.endpoint and default.configured
    assert snapshot(store.path) == before  # the default state on disk is untouched
    store.close()


def test_odoo_switches_are_written_as_saved_and_absent_methods_stay_absent(tmp_path, log_scan):
    store = ProductStore(tmp_path / 'mcp', 'odoo')  # a new installation: legacy (absent) switches, no method list
    default = store.load()
    assert default.odoo_write_switches is None and default.odoo_allowed_methods is None
    new = profile_initial_state(default)
    watch(log_scan, default, new)
    # The legacy default runs the four child switches on; the new profile stores that choice, so the panel shows it
    # as saved (odoo_write_switches_source 'saved'), not as the legacy all-on.
    assert new.odoo_write_switches == OdooWriteSwitches(enable_writes=True, allow_direct_writes=True,
                                                        allow_unknown_methods=True, chatter_direct=True)
    assert new.odoo_allowed_methods is None
    assert (new.writes_enabled, new.enabled_write_tools) == (default.writes_enabled, default.enabled_write_tools)
    store.close()


def test_new_tokens_avoid_the_taken_values(monkeypatch, log_scan):
    default = ProductState(product='litellm', token='T' * 43, child_token='C' * 43)
    values = iter(['T' * 43, 'C' * 43, 'X' * 43, 'X' * 43, 'Y' * 43, 'Z' * 43])
    monkeypatch.setattr(products.secrets, 'token_urlsafe', lambda size: next(values))
    new = profile_initial_state(default, taken={'Y' * 43})
    assert (new.token, new.child_token) == ('X' * 43, 'Z' * 43)


def test_only_products_with_profiles_get_a_first_state(log_scan):
    # DQ-28 (2026-11-14): OpenDesign and Odoo Manage are not opened (profiles.capacity 0; HM-10 answers 409
    # profile_product_unsupported). The data layer refuses them as well: no first state here, and no creation in
    # ProductStore (test_the_store_creates_no_profile_of_a_product_without_profiles).
    assert products.NO_PROFILE_PRODUCTS == {p for p in features.KNOWN_PRODUCTS if not profiles.supports_profiles(p)}
    for product in sorted(features.KNOWN_PRODUCTS):
        default = ProductState(product=product, token='T' * 43, child_token='C' * 43)
        if profiles.supports_profiles(product):
            new = profile_initial_state(default)
            log_scan.watch_state(new)
            assert new.product == product
        else:
            with pytest.raises(ValueError, match='no additional profiles'):
                profile_initial_state(default)


def test_the_store_creates_no_profile_of_a_product_without_profiles(tmp_path, log_scan):
    # HM-07 review S-06: ProductStore(create=...) refuses OpenDesign and Odoo Manage before it makes anything, whatever
    # state it is given. Opening an existing directory stays possible: HM-13b revokes what a restore may have left.
    for product in sorted(products.NO_PROFILE_PRODUCTS):
        state = ProductState(product=product, token='T' * 43, child_token='C' * 43)
        log_scan.watch_state(state)
        root = tmp_path / product
        root.mkdir()
        with pytest.raises(ValueError, match='no additional profiles'):
            ProductStore(root / A, product, create=state)
        assert os.listdir(root) == []
        legacy_tree(root / B, state.model_dump_json().encode())
        store = ProductStore(root / B, product, existing_only=True)
        assert store.load() == state
        store.close()
    for product in SUPPORTED:  # the products with profiles still create theirs
        ProductStore(tmp_path / ('ok-' + product), product,
                     create=ProductState(product=product, token='T' * 43, child_token='C' * 43)).close()


def test_the_first_state_is_written_once_and_reopens_equal(tmp_path, monkeypatch, log_scan):
    default_store = configured_default(tmp_path / 'mcp', 'odoo')
    new = profile_initial_state(default_store.load())
    watch(log_scan, default_store.load(), new)
    layout = profiles.Layout(default_store.directory)
    profiles.ensure_profiles_directory(layout)
    writes = []
    real = Store._write

    def counted(self, value):
        writes.append(value)
        return real(self, value)

    with monkeypatch.context() as patch:
        patch.setattr(Store, '_write', counted)
        created = ProductStore(layout.profile(A), 'odoo', create=new)
    assert writes == [new] and created.load() == new  # one durable write: no all-on seed rewritten afterwards
    assert (layout.profile(A) / 'state.json').read_text() == new.model_dump_json()
    created.close()
    reopened = ProductStore(layout.profile(A), 'odoo', existing_only=True)
    assert reopened.load() == new
    reopened.close()
    default_store.close()


def test_five_profiles_have_private_independent_stores(tmp_path, log_scan):
    # PaaS test_profiles.py:28: five profiles, each its own files, tokens and port; the default keeps its own.
    default_store = configured_default(tmp_path / 'mcp', 'odoo')
    default = default_store.load()
    layout = profiles.Layout(default_store.directory)
    profiles.ensure_profiles_directory(layout)
    taken, entries, made = {default.token, default.child_token}, [], {}
    for profile_id, label in zip((A, B, C, D, E), ('一', '二', '三', '四', '五')):
        state = profile_initial_state(default, taken=taken)
        taken |= {state.token, state.child_token}
        ProductStore(layout.profile(profile_id), 'odoo', create=state).close()
        entries.append(profiles.IndexEntry(profile_id, label, profiles.allocate_port(e.port for e in entries)))
        made[profile_id] = state
    watch(log_scan, default, *made.values())
    view = profiles.write_index(layout.index, entries)
    assert [e.port for e in view.entries] == [18000, 18001, 18002, 18003, 18004]
    assert len(taken) == 12
    for profile_id, state in made.items():
        store = ProductStore(layout.profile(profile_id), 'odoo', existing_only=True)
        assert store.load() == state and store.directory == layout.profile(profile_id)
        store.close()
    assert default_store.load() == default
    default_store.close()


# ---------------------------------------------------------------------------------------------------------------
# Creation: the directory must not exist, the lock is new (O_EXCL), the final state is written once
# ---------------------------------------------------------------------------------------------------------------

def test_create_writes_exactly_the_given_state_with_private_modes(tmp_path, log_scan):
    state = plain_state()
    watch(log_scan, state)
    store = Store(tmp_path / A, create=state)
    assert store.load() == state
    directory = tmp_path / A
    assert sorted(os.listdir(directory)) == ['.writer.lock', 'state.json']
    assert (mode(directory), mode(directory / '.writer.lock'), mode(directory / 'state.json')) == (0o700, 0o600, 0o600)
    for path in (directory, directory / '.writer.lock', directory / 'state.json'):
        assert os.lstat(path).st_uid == os.geteuid()
    assert os.lstat(directory / 'state.json').st_nlink == 1
    assert (directory / 'state.json').read_text() == state.model_dump_json()
    with pytest.raises(ConfigError):
        Store(directory, existing_only=True)  # the writer lock is held: one writer per profile
    store.close()


def test_create_under_a_restrictive_umask_still_ends_0700_and_0600(tmp_path, log_scan):
    state = plain_state()
    watch(log_scan, state)
    previous = os.umask(0o277)
    try:
        store = Store(tmp_path / A, create=state)
    finally:
        os.umask(previous)
    directory = tmp_path / A
    assert (mode(directory), mode(directory / '.writer.lock'), mode(directory / 'state.json')) == (0o700, 0o600, 0o600)
    store.close()


def test_create_never_reuses_an_existing_name(tmp_path, log_scan):
    state = plain_state()
    watch(log_scan, state)
    existing = tmp_path / 'existing'
    existing.mkdir(mode=0o700)
    (existing / 'keep').write_text('x')
    (tmp_path / 'empty').mkdir(mode=0o700)
    (tmp_path / 'link').symlink_to('nowhere')
    (tmp_path / 'file').write_text('x')
    for name in ('existing', 'empty', 'link', 'file'):
        before = sorted(os.listdir(tmp_path))
        with pytest.raises(ConfigError):
            Store(tmp_path / name, create=state)
        assert sorted(os.listdir(tmp_path)) == before, name
    assert sorted(os.listdir(existing)) == ['keep'] and os.listdir(tmp_path / 'empty') == []
    assert os.readlink(tmp_path / 'link') == 'nowhere'
    with pytest.raises(ConfigError):
        Store(tmp_path / 'missing-parent' / A, create=state)
    assert not (tmp_path / 'missing-parent').exists()
    (tmp_path / 'real').mkdir()
    (tmp_path / 'linked-parent').symlink_to('real')
    with pytest.raises(ConfigError):
        Store(tmp_path / 'linked-parent' / A, create=state)
    assert os.listdir(tmp_path / 'real') == []


def test_create_refuses_an_invalid_state_and_leaves_nothing(tmp_path, log_scan):
    wrong = ProductState(product='emqx', token=secrets.token_urlsafe(32), child_token=secrets.token_urlsafe(32))
    watch(log_scan, wrong)
    with pytest.raises(ConfigError):
        ProductStore(tmp_path / A, 'litellm', create=wrong)
    assert os.listdir(tmp_path) == []
    with pytest.raises(ValueError):
        Store(tmp_path / A, create=plain_state(), existing_only=True)
    assert os.listdir(tmp_path) == []


def open_descriptors():
    return sorted(os.listdir('/proc/self/fd'))


STEPS = ['mkdir', 'directory-open', 'directory-fstat', 'lock-open', 'flock', 'temporary-open', 'fsync-file',
         'replace', 'fsync-directory', 'load']


@pytest.mark.parametrize('step', STEPS)
def test_a_failure_at_any_creation_step_leaves_no_profile_behind(tmp_path, monkeypatch, log_scan, step):
    import fcntl
    from mcp_admin_core import config
    state = plain_state()
    watch(log_scan, state)
    target = tmp_path / A
    seen = {'open': 0, 'fsync': 0}
    real_open, real_fsync, real_fstat = os.open, os.fsync, os.fstat

    def fail():
        raise OSError('injected LOCAL storage fault')

    def opened(path, flags, *args, **kwargs):
        name = os.path.basename(path)
        if ((step == 'directory-open' and Path(path) == target)
                or (step == 'lock-open' and name == '.writer.lock')
                or (step == 'temporary-open' and name.startswith('.state-'))):
            fail()
        return real_open(path, flags, *args, **kwargs)

    def synced(fd):
        kind = stat.S_IFMT(real_fstat(fd).st_mode)
        if (step == 'fsync-file' and kind == stat.S_IFREG) or (step == 'fsync-directory' and kind == stat.S_IFDIR):
            fail()
        return real_fsync(fd)

    def stat_fd(fd):
        if step == 'directory-fstat' and stat.S_ISDIR(real_fstat(fd).st_mode):
            fail()
        return real_fstat(fd)

    with monkeypatch.context() as patch:
        patch.setattr(config.os, 'open', opened)
        patch.setattr(config.os, 'fsync', synced)
        patch.setattr(config.os, 'fstat', stat_fd)
        if step == 'mkdir':
            patch.setattr(config.os, 'mkdir', lambda *a, **k: fail())
        if step == 'flock':
            patch.setattr(config.fcntl, 'flock', lambda *a, **k: fail())
        if step == 'replace':
            patch.setattr(config.os, 'replace', lambda *a, **k: fail())
        if step == 'load':
            patch.setattr(config.Store, 'load', lambda self: fail())
        before = open_descriptors()
        with pytest.raises(ConfigError):
            Store(target, create=state)
        assert open_descriptors() == before, step  # the lock descriptor is closed again
    assert os.listdir(tmp_path) == [], step  # no directory, lock, state or temporary file stays
    store = Store(target, create=state)  # and the same profile can be created afterwards
    assert store.load() == state
    fcntl.flock(store._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # this store holds the only writer lock
    store.close()


def test_a_failed_creation_keeps_what_it_did_not_create(tmp_path, monkeypatch, log_scan):
    # Something else appeared in the new directory before the failure (same uid): its files are not removed, so the
    # directory stays, as an orphan the consistency check lists (never opened or routed).
    from mcp_admin_core import config
    state = plain_state()
    watch(log_scan, state)

    def intruded(self, value):
        (self.directory / 'stranger').write_text('x')
        raise ConfigError('injected')

    monkeypatch.setattr(config.Store, '_write', intruded)
    with pytest.raises(ConfigError):
        Store(tmp_path / A, create=state)
    assert os.listdir(tmp_path / A) == ['stranger']


# ---------------------------------------------------------------------------------------------------------------
# Open existing only: never seeds, never makes a directory or lock, refuses foreign entries
# ---------------------------------------------------------------------------------------------------------------

def created(tmp_path, name=A, state=None):
    state = state or plain_state()
    Store(tmp_path / name, create=state).close()
    return tmp_path / name, state


def test_existing_only_opens_what_was_created(tmp_path, log_scan):
    directory, state = created(tmp_path)
    watch(log_scan, state)
    store = Store(directory, existing_only=True)
    assert store.load() == state
    updated = store.update(writes_enabled=True)
    assert store.load() == updated and updated.writes_enabled
    store.close()


def test_existing_only_never_makes_anything(tmp_path, log_scan):
    # PaaS test_restore_marker.py:198/:208: a missing profile state is never replaced by factory defaults.
    with pytest.raises(ConfigError):
        Store(tmp_path / 'missing', existing_only=True)
    assert os.listdir(tmp_path) == []
    empty = tmp_path / 'empty'
    empty.mkdir(mode=0o700)
    with pytest.raises(ConfigError):
        Store(empty, existing_only=True)
    assert os.listdir(empty) == []  # the default profile's Store would seed a new all-on state here
    directory, state = created(tmp_path, B)
    watch(log_scan, state)
    (directory / 'state.json').unlink()
    with pytest.raises(ConfigError):
        Store(directory, existing_only=True)
    assert os.listdir(directory) == ['.writer.lock']
    directory, state = created(tmp_path, C)
    watch(log_scan, state)
    (directory / '.writer.lock').unlink()
    with pytest.raises(ConfigError):
        Store(directory, existing_only=True)
    assert os.listdir(directory) == ['state.json']


def test_existing_only_refuses_links_and_oversized_state(tmp_path, log_scan):
    directory, state = created(tmp_path)
    watch(log_scan, state)
    (tmp_path / 'linked').symlink_to(directory)
    with pytest.raises(ConfigError):
        Store(tmp_path / 'linked', existing_only=True)
    cases = {}
    for name, damage in (
            ('state-symlink', lambda d: ((d / 'real.json').write_bytes((d / 'state.json').read_bytes()),
                                         (d / 'state.json').unlink(), (d / 'state.json').symlink_to('real.json'))),
            ('lock-symlink', lambda d: ((d / '.writer.lock').unlink(), (d / 'other').write_text(''),
                                        (d / '.writer.lock').symlink_to('other'))),
            ('state-hard-link', lambda d: os.link(d / 'state.json', d / 'second')),
            ('lock-hard-link', lambda d: os.link(d / '.writer.lock', d / 'second')),
            ('state-too-large', lambda d: (d / 'state.json').write_bytes(b' ' * 70000)),
            ('state-directory', lambda d: ((d / 'state.json').unlink(), (d / 'state.json').mkdir())),
            ('lock-directory', lambda d: ((d / '.writer.lock').unlink(), (d / '.writer.lock').mkdir()))):
        path, value = created(tmp_path, name)
        watch(log_scan, value)
        damage(path)
        cases[name] = path
    for name, path in cases.items():
        with pytest.raises(ConfigError):
            Store(path, existing_only=True)


def test_existing_only_tightens_widened_modes(tmp_path, log_scan):
    # PaaS test_profiles.py:226 (fsGroup-widened directories are tightened on reload); also as uid 10001 below.
    directory, state = created(tmp_path)
    watch(log_scan, state)
    os.chmod(directory, 0o755)
    os.chmod(directory / '.writer.lock', 0o644)
    os.chmod(directory / 'state.json', 0o644)
    store = Store(directory, existing_only=True)
    assert (mode(directory), mode(directory / '.writer.lock'), mode(directory / 'state.json')) == (0o700, 0o600, 0o600)
    store.close()


@pytest.mark.parametrize('entry', ['directory', 'lock', 'state'])
def test_existing_only_refuses_an_entry_another_uid_owns_before_touching_it(tmp_path, monkeypatch, log_scan, entry):
    # The owner is compared with the effective uid before any chmod: a foreign state is refused, not tightened.
    from mcp_admin_core import config
    directory, state = created(tmp_path)
    watch(log_scan, state)
    path = {'directory': directory, 'lock': directory / '.writer.lock', 'state': directory / 'state.json'}[entry]
    os.chmod(directory / 'state.json', 0o644)
    owner = os.lstat(path).st_uid
    real_fstat = os.fstat
    real_lstat = os.lstat

    def foreign(result, inode):
        if (result.st_dev, result.st_ino) != inode:
            return result
        fields = list(result)
        fields[stat.ST_UID] = owner + 1
        return os.stat_result(fields)

    inode = (os.lstat(path).st_dev, os.lstat(path).st_ino)
    monkeypatch.setattr(config.os, 'fstat', lambda fd: foreign(real_fstat(fd), inode))
    monkeypatch.setattr(config.os, 'lstat', lambda p, *a, **k: foreign(real_lstat(p, *a, **k), inode))
    with pytest.raises(ConfigError):
        Store(directory, existing_only=True)
    monkeypatch.undo()
    assert mode(directory / 'state.json') == 0o644  # refused before the tightening chmod
    assert mode(directory) == 0o700


def test_the_default_profile_store_keeps_its_behavior(tmp_path, monkeypatch, log_scan):
    # No owner check and the first-boot seeding stay as they were for /data/mcp itself (HM-01 freezes the rest).
    from mcp_admin_core import config
    store = Store(tmp_path / 'mcp')
    state = store.load()
    watch(log_scan, state)
    store.close()
    real_fstat = os.fstat

    def other_owner(fd):
        fields = list(real_fstat(fd))
        fields[stat.ST_UID] += 1
        return os.stat_result(fields)

    monkeypatch.setattr(config.os, 'fstat', other_owner)
    reopened = Store(tmp_path / 'mcp')
    assert reopened.load() == state
    reopened.close()


def legacy_tree(directory, raw):
    directory.mkdir(mode=0o700)
    (directory / '.writer.lock').write_bytes(b'')
    os.chmod(directory / '.writer.lock', 0o600)
    (directory / 'state.json').write_bytes(raw)
    os.chmod(directory / 'state.json', 0o600)


@pytest.mark.parametrize('fixture', sorted(p.name for p in (ROOT / 'tests/fixtures/owner_defaults').glob('schema*.json')))
def test_an_additional_profile_is_never_migrated(tmp_path, fixture, log_scan):
    # Only the default profile carries legacy states (schema 1-3, or schema 4 without a later key): an additional
    # profile is born complete at schema 4, so a state the default profile's store would migrate is refused as it
    # is, never rewritten; a complete schema 4 state opens unchanged.
    raw = (ROOT / 'tests/fixtures/owner_defaults' / fixture).read_bytes()
    product = json.loads(raw).get('product', 'n8n')
    legacy_tree(tmp_path / 'default', raw)
    ProductStore(tmp_path / 'default', product).close()
    migrated = (tmp_path / 'default' / 'state.json').read_bytes() != raw  # what the default profile's store does
    directory = tmp_path / A
    legacy_tree(directory, raw)
    if migrated:
        with pytest.raises(ConfigError):
            ProductStore(directory, product, existing_only=True)
    else:
        store = ProductStore(directory, product, existing_only=True)
        assert store.load() == ProductState.model_validate_json(raw)
        store.close()
    assert (directory / 'state.json').read_bytes() == raw
    assert sorted(os.listdir(directory)) == ['.writer.lock', 'state.json']


def test_most_legacy_fixtures_are_ones_the_default_store_migrates(tmp_path):
    # The case above must exercise both branches: only the 0.4.1 Hermes sample is a complete schema 4 state.
    complete = []
    for path in sorted((ROOT / 'tests/fixtures/owner_defaults').glob('schema*.json')):
        raw = path.read_bytes()
        legacy_tree(tmp_path / path.stem, raw)
        ProductStore(tmp_path / path.stem, json.loads(raw).get('product', 'n8n')).close()
        if (tmp_path / path.stem / 'state.json').read_bytes() == raw:
            complete.append(path.name)
    assert complete == ['schema4-hermes-ws97-0.4.1-writes-off.json']


def test_profiles_directory_is_private_and_owned(tmp_path, monkeypatch, log_scan):
    layout = profiles.Layout(tmp_path)
    profiles.ensure_profiles_directory(layout)
    assert mode(layout.profiles) == 0o700 and os.lstat(layout.profiles).st_uid == os.geteuid()
    os.chmod(layout.profiles, 0o755)
    profiles.ensure_profiles_directory(layout)
    assert mode(layout.profiles) == 0o700
    other = profiles.Layout(tmp_path / 'other')
    (tmp_path / 'other').mkdir()
    previous = os.umask(0o277)
    try:
        profiles.ensure_profiles_directory(other)
    finally:
        os.umask(previous)
    assert mode(other.profiles) == 0o700
    for name, setup in (('symlink', lambda p: (p.with_name('real').mkdir(), p.symlink_to('real'))),
                        ('file', lambda p: p.write_text('x'))):
        root = tmp_path / name
        root.mkdir()
        setup(root / 'profiles')
        with pytest.raises(profiles.ProfileDataError):
            profiles.ensure_profiles_directory(profiles.Layout(root))
    with monkeypatch.context() as patch:
        real_fstat = os.fstat

        def other_owner(fd):
            fields = list(real_fstat(fd))
            fields[stat.ST_UID] += 1
            return os.stat_result(fields)

        patch.setattr(profiles.os, 'fstat', other_owner)
        with pytest.raises(profiles.ProfileDataError):
            profiles.ensure_profiles_directory(layout)


# ---------------------------------------------------------------------------------------------------------------
# The whole tree stays within the entrypoint's restore repair (FM-16; plan §4.1 "項目預算")
# ---------------------------------------------------------------------------------------------------------------

def test_a_full_multi_profile_tree_fits_the_restore_repair(tmp_path, log_scan):
    spec = importlib.util.spec_from_file_location('hm07_entrypoint', ROOT / 'packaging/entrypoint.py')
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    entry.UID, entry.GID = os.getuid(), os.getgid()  # the repair accepts the runtime user; here that is this user
    root = tmp_path / 'mcp'
    store = configured_default(root, 'odoo')
    default = store.load()
    layout = profiles.Layout(root)
    for name in ('.state.json.operations.json', '.state.json.operations.json.restored',
                 'owner-defaults-20261025-recovery.json', layout.sentinel.name, layout.instance_record.name,
                 layout.restore_marker.name, layout.revoke_all_marker.name, layout.restore_record.name,
                 layout.index_operations.name):
        (root / name).write_text('{}')
    (root / 'child').mkdir(mode=0o700)
    profiles.ensure_profiles_directory(layout)
    taken, entries, states = {default.token, default.child_token}, [], [default]
    for profile_id in (A, B, C, D, E):
        state = profile_initial_state(default, taken=taken)
        taken |= {state.token, state.child_token}
        states.append(state)
        ProductStore(layout.profile(profile_id), 'odoo', create=state).close()
        for name in ('.state.json.operations.json', '.state.json.operations.json.restored'):
            (layout.profile(profile_id) / name).write_text('{}')
        layout.child(profile_id).mkdir(mode=0o700)
        entries.append(profiles.IndexEntry(profile_id, profile_id[:1], profiles.allocate_port(e.port for e in entries)))
    profiles.write_index(layout.index, entries)
    from datetime import datetime, timezone
    for number, profile_id in enumerate(('1' * 24, '2' * 24)):
        quarantined = layout.profiles / profiles.quarantine_name(profile_id, datetime(2026, 11, 14, 13, number,
                                                                                       tzinfo=timezone.utc))
        shutil.copytree(layout.profile(A), quarantined)
    watch(log_scan, *states)
    store.close()
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    pinned = []
    try:
        entry._approve_restored(fd, os.fstat(fd).st_dev, 0, [entry.MAX_RESTORED_ENTRIES], pinned)
        count = len(pinned)
    finally:
        for descriptor in pinned:
            os.close(descriptor)
        os.close(fd)
    # About 50 entries, 4 levels deep (plan §4.1); the panel warns past 400 (C2-SF-8), the repair refuses past 512.
    assert 50 <= count <= 64 and count < 400 < entry.MAX_RESTORED_ENTRIES
    depth = max(len(path.relative_to(root).parts) for path in root.rglob('*'))
    assert depth <= 4 < entry.MAX_RESTORED_DEPTH


# ---------------------------------------------------------------------------------------------------------------
# For real as uid 10001 (root only: the CI runs pytest as root; locally this one test fails like the existing
# tests/test_owned_executable.py::test_uid10001_nondumpable_self_and_own_child_proof)
# ---------------------------------------------------------------------------------------------------------------

def _write_owned(path, data, mode_bits, uid, gid):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode_bits)
    try:
        os.write(fd, data)
        os.fchmod(fd, mode_bits)
        os.fchown(fd, uid, gid)
    finally:
        os.close(fd)


def _directory_owned(path, mode_bits, uid, gid):
    os.mkdir(path, mode_bits)
    os.chmod(path, mode_bits)
    os.chown(path, uid, gid)


def test_the_probe_loads_everything_before_it_drops_privileges():
    # Runs everywhere (the probe itself needs root). After the drop the probe may not be able to read the checkout
    # (a CI runner's home directory need not be open to other users): every module it uses is imported at module
    # level, while it is still root, and nothing is imported later.
    tree = ast.parse((ROOT / 'tests/profile_owner_probe.py').read_text())
    loaded = {f'{node.module}.{alias.name}' for node in tree.body if isinstance(node, ast.ImportFrom)
              for alias in node.names}
    assert {'mcp_admin_core.profiles', 'mcp_admin_core.config.State', 'mcp_admin_core.config.Store'} <= loaded
    later = [node.lineno for node in ast.walk(tree)
             if isinstance(node, (ast.Import, ast.ImportFrom)) and node not in tree.body]
    assert later == []


def test_mode_and_owner_as_the_add_on_user(log_scan):
    assert os.geteuid() == 0, 'the uid 10001 mode/owner proof needs root (the CI); HM-07 provenance, section 6'
    user = group = 10001
    with tempfile.TemporaryDirectory(prefix='hm07-uid-') as directory:
        temp = Path(directory)
        temp.chmod(0o755)
        # An interpreter and venv the add-on user can read; never chmod an existing private one.
        interpreter = Path(sys.executable).resolve().parents[1]
        shutil.copytree(interpreter, temp / 'python', symlinks=True)
        shutil.copytree(ROOT / '.venv', temp / '.venv', symlinks=True)
        for path in (temp / '.venv/bin').glob('python*'):
            path.unlink()
        (temp / '.venv/bin/python').symlink_to(temp / 'python/bin/python3.13')
        (temp / '.venv/pyvenv.cfg').write_text(
            f'home = {temp}/python/bin\ninclude-system-site-packages = false\nversion = 3.13.2\n')
        data, foreign, rooted = temp / 'data', temp / 'foreign', temp / 'rooted'
        for path in (data, foreign, rooted):
            _directory_owned(path, 0o700, user, group)
        _directory_owned(foreign / 'profiles', 0o700, user, group)
        _directory_owned(rooted / 'profiles', 0o755, 0, 0)  # left by a restore as root
        states = {}
        # What a restore leaves: root-owned entries the add-on user can still read (so only the owner check refuses).
        layout = {
            B: {'dir': (0o700, user), 'lock': (0o600, user), 'state': (0o644, 0)},
            C: {'dir': (0o755, 0), 'lock': (0o600, user), 'state': (0o600, user)},
            D: {'dir': (0o700, user), 'lock': (0o666, 0), 'state': (0o600, user)},
            E: {'dir': (0o700, user), 'lock': (0o600, user), 'state': (0o600, user)},  # control: all its own
        }
        for profile_id, owners in layout.items():
            state = plain_state()
            states[profile_id] = state
            path = foreign / 'profiles' / profile_id
            _directory_owned(path, owners['dir'][0], owners['dir'][1], owners['dir'][1])
            _write_owned(path / '.writer.lock', b'', owners['lock'][0], owners['lock'][1], owners['lock'][1])
            _write_owned(path / 'state.json', state.model_dump_json().encode(), owners['state'][0],
                         owners['state'][1], owners['state'][1])
        _write_owned(foreign / 'profiles.json', profiles.encode_index([profiles.IndexEntry(E, 'x', 18000)]), 0o644, 0, 0)
        watch(log_scan, *states.values())
        settings = {'uid': user, 'gid': group, 'data': str(data), 'first': A, 'foreign': str(foreign),
                    'foreign_profiles': [B, C, D, E], 'rooted': str(rooted)}
        result = subprocess.run([str(temp / '.venv/bin/python'), str(ROOT / 'tests/profile_owner_probe.py'),
                                 json.dumps(settings)], capture_output=True, text=True, timeout=60, cwd=temp,
                                env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'packages/mcp-admin-core'),
                                     'PYTHONDONTWRITEBYTECODE': '1'})
        assert result.returncode == 0, result.stderr[-4000:]
        report = json.loads(result.stdout)

    def own(mode_text, kind):
        return {'mode': mode_text, 'uid': user, 'gid': group, 'nlink': report['created'][kind]['nlink'],
                'type': 'dir' if kind == 'dir' else 'file'}

    assert (report['uid'], report['euid'], report['gid']) == (user, user, group)
    # A directory's link count depends on the file system: never compared.
    assert {k: v for k, v in report['profiles_dir'].items() if k != 'nlink'} == {
        'mode': '0o700', 'uid': user, 'gid': group, 'type': 'dir'}
    assert report['created'] == {'dir': own('0o700', 'dir'), 'lock': own('0o600', 'lock'),
                                 'state': own('0o600', 'state')}
    assert report['created']['state']['nlink'] == 1 and report['created']['lock']['nlink'] == 1
    assert report['created_names'] == ['.writer.lock', 'state.json']
    assert report['index'] == {'mode': '0o600', 'uid': user, 'gid': group, 'nlink': 1, 'type': 'file'}
    assert (report['index_read'], report['index_baseline']) == ('ok', 'ok')
    assert report['reopened_equal'] is True
    assert report['tightened'] == {'dir': '0o700', 'lock': '0o600', 'state': '0o600'}
    assert report['foreign'] == {B: 'refused:ConfigError', C: 'refused:ConfigError', D: 'refused:ConfigError',
                                 E: 'ok'}
    assert report['foreign_state_mode_after'] == {B: '0o644', C: '0o600', D: '0o600', E: '0o600'}
    assert report['foreign_index'] == 'corrupt'
    assert report['foreign_scan'] == [B, C, D, E]
    assert (report['rooted_ensure'], report['rooted_scan']) == ('refused:ProfileDataError', 'refused:ProfileDataError')
