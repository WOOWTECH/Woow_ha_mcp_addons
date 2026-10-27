"""Owner decision 2026-10-27: a legacy installation is switched to the full defaults once, at its first start.

Real legacy samples (tests/fixtures/owner_defaults, see its README): schema 1 and 2 written by the code of commit
313ab01, schema 3 by the v0.1.14 tag code and by the real ws97 Hermes add-on 0.1.14, schema 4 by v0.2.2 and by the
real ws97 Hermes add-on 0.4.1 (writes off). Only fake tokens and DUMMY credentials; no backend, child process or HA.
"""
import asyncio
from contextlib import closing
import errno
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace

import httpx
import pytest

from mcp_admin_core import owner_defaults, run_product
from mcp_admin_core.config import ConfigError
from mcp_admin_core.legacy_catalog import LEGACY_TOOLS
from mcp_admin_core.migration import (OWNER_RECOVERY, MigrationError, _effective, _legacy_grants, _validate, main,
                                      owner_record, plan_migration, plan_owner_restore, plan_restore, read_document)
from mcp_admin_core.policy import enabled, policy_enabled
from mcp_admin_core.products import (OWNER_DEFAULTS, STORED_FIELDS, ProductStore, TOOLS, fresh_write_grants,
                                     write_grants)
from mcp_admin_core.surface import full_tools
from mcp_admin_core.gateway import make_apps
from n8n_adapter import TOOLS as N8N_TOOLS
from test_unconfigured_connect import Boundary, NO_CHILD, UP
from test_full_surface import COUNTS

FIXTURES = Path(__file__).parent / 'fixtures/owner_defaults'
LEGACY = sorted(p.name for p in FIXTURES.glob('schema[123]-*.json'))
CURRENT = sorted(p.name for p in FIXTURES.glob('schema4-*.json'))
SEVEN = ('odoo', 'n8n', 'hermes', 'emqx', 'litellm', 'nextcloud', 'opendesign')
TIMESTAMP = re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00$')
SECRETS = ('T' * 43, 'C' * 43, 'DUMMY', '.invalid')
IDENTITY = {'x-remote-user-id': 'owned-administrator'}


def sample(name):
    value = json.loads((FIXTURES / name).read_text())
    return value, value.get('product', 'n8n')


def install(directory, value):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    (directory / '.writer.lock').touch(mode=0o600)
    path = directory / 'state.json'
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return path


def tools_of(product):
    return full_tools('n8n') if product == 'n8n' else TOOLS[product]


def snapshot(directory):
    return {p.name: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in directory.iterdir() if p.is_file()}


def test_the_samples_cover_every_legacy_schema_and_all_seven_add_ons():
    versions = {sample(name)[0]['schema_version'] for name in LEGACY}
    assert versions == {1, 2, 3}
    assert {sample(name)[1] for name in LEGACY if name.startswith('schema3-')} == set(SEVEN)
    assert {sample(name)[1] for name in CURRENT} == set(SEVEN)
    for name in LEGACY + CURRENT:
        text = (FIXTURES / name).read_text()
        assert not re.search(r'[A-Za-z0-9_-]{43}', text.replace('T' * 43, '').replace('C' * 43, '')), name


@pytest.mark.parametrize('name', LEGACY)
def test_a_legacy_state_is_switched_once_to_exactly_the_review_pages_all_on(tmp_path, capsys, name):
    value, product = sample(name)
    expected = plan_migration(value, product, policy='all_on').state
    install(tmp_path, value)
    report = owner_defaults.apply_legacy_upgrade(tmp_path, product)
    assert report['source_schema'] == value['schema_version'] and report['policy'] == 'all_on'
    stored = json.loads((tmp_path / 'state.json').read_text())
    marker = stored[OWNER_DEFAULTS]
    assert marker == {'applied': 'migrated', 'at': marker['at'], 'from_schema': value['schema_version'],
                      'restored_at': None, 'acknowledged_at': None}
    assert TIMESTAMP.match(marker['at']) and report['marker']['at'] == marker['at']
    assert set(stored) == STORED_FIELDS | {OWNER_DEFAULTS}
    with closing(ProductStore(tmp_path, product)) as store:
        state = store.load()
    # The all_on plan of the 0.3.0-0.4.1 review page, plus the marker; schema 4, every write, nothing disabled.
    assert {k: v for k, v in state.model_dump().items() if k != OWNER_DEFAULTS} == expected.model_dump()
    assert state.schema_version == 4 and state.writes_enabled is True and state.disabled == []
    assert state.denied_operations == {} and state.enabled_write_tools == fresh_write_grants(product)
    assert all(enabled(tool, tools_of(product), state) for tool in tools_of(product))
    for key in ('token', 'child_token', 'endpoint', 'backend_url', 'backend_key', 'connection'):
        assert state.model_dump()[key] == ({**value, 'connection': value.get('connection')}).get(key)
    # The recovery record: the legacy policy itself, private, secret-free.
    record_path = tmp_path / OWNER_RECOVERY
    assert record_path.stat().st_mode & 0o777 == 0o600
    record = read_document(record_path)
    assert record == owner_record(value, product)
    assert record['legacy_policy'] == {'writes_enabled': value['writes_enabled'], 'disabled': value['disabled'],
                                       'enabled_write_tools': value.get('enabled_write_tools', []),
                                       'denied_operations': value.get('denied_operations', {})}
    text = record_path.read_text() + capsys.readouterr().err
    assert not any(secret in text for secret in SECRETS)
    assert 'switched once to schema 4' in text and OWNER_RECOVERY in text


@pytest.mark.parametrize('product', SEVEN)
@pytest.mark.parametrize('path', ['bearer', 'secret'])
async def test_mcp_serves_at_once_after_the_migration_never_503(tmp_path, product, path):
    value, _ = sample(f'schema3-{product}-v0.1.14-fresh.json')
    install(tmp_path, value)
    owner_defaults.apply_legacy_upgrade(tmp_path, product)
    with closing(ProductStore(tmp_path, product)) as store:
        async with Boundary(store, product, UP if product == 'n8n' else NO_CHILD, path=path) as boundary:
            response, tools = await boundary.connect()
            assert response.status_code == 200 and response.json()['result']['serverInfo']['name'] == 'woow-mcp-' + product
            assert len(tools) == COUNTS[product]  # every tool listed: all on, no review stage
            assert 'upgrade_review_required' not in response.text


@pytest.mark.parametrize('name', ['schema1-n8n-313ab01.json', 'schema2-hermes-313ab01.json',
                                  'schema3-hermes-ws97-0.1.14.json', 'schema3-odoo-v0.1.14-max.json'])
def test_repeated_starts_are_idempotent(tmp_path, name):
    value, product = sample(name)
    install(tmp_path, value)
    assert owner_defaults.apply_legacy_upgrade(tmp_path, product) is not None
    after = snapshot(tmp_path)
    for _ in range(3):
        assert owner_defaults.apply_legacy_upgrade(tmp_path, product) is None
        with closing(ProductStore(tmp_path, product)) as store:
            assert getattr(store.load(), OWNER_DEFAULTS).from_schema == value['schema_version']
        assert snapshot(tmp_path) == after


def test_an_interrupted_migration_resumes_with_its_own_record(tmp_path, monkeypatch):
    value, product = sample('schema3-hermes-ws97-0.1.14.json')
    path = install(tmp_path, value)
    raw = path.read_bytes()

    def failed_replace(*_):
        raise OSError('secret filesystem error')
    with monkeypatch.context() as patch:
        patch.setattr('mcp_admin_core.config.os.replace', failed_replace)
        with pytest.raises(ConfigError):
            owner_defaults.apply_legacy_upgrade(tmp_path, product)
    assert path.read_bytes() == raw and not list(tmp_path.glob('.state-*'))
    record = (tmp_path / OWNER_RECOVERY).read_bytes()
    assert owner_defaults.apply_legacy_upgrade(tmp_path, product)['source_schema'] == 3
    assert (tmp_path / OWNER_RECOVERY).read_bytes() == record  # reused, not rewritten
    with closing(ProductStore(tmp_path, product)) as store:
        assert store.load().enabled_write_tools == fresh_write_grants(product)


@pytest.mark.parametrize('content', ['another state', 'empty', 'truncated'])
def test_a_foreign_or_incomplete_record_blocks_the_migration_and_nothing_changes(tmp_path, capsys, content):
    value, product = sample('schema3-hermes-ws97-0.1.14.json')
    other, _ = sample('schema3-hermes-v0.1.14-max.json')
    path = install(tmp_path, value)
    own = json.dumps(owner_record(value, product), sort_keys=True, indent=2) + '\n'
    (tmp_path / OWNER_RECOVERY).write_text({'another state': json.dumps(owner_record(other, product)),
                                            'empty': '', 'truncated': own[:40]}[content])
    (tmp_path / OWNER_RECOVERY).chmod(0o600)
    before = snapshot(tmp_path)
    with pytest.raises(ConfigError):
        owner_defaults.apply_legacy_upgrade(tmp_path, product)
    assert snapshot(tmp_path) == before and path.read_bytes() == before['state.json'][0]
    # The add-on log names the one file to check (fixed text; nothing from the record or the state).
    err = capsys.readouterr().err
    assert f'{OWNER_RECOVERY} already exists but is not the complete recovery record of this state.json' in err
    assert 'nothing was migrated or rewritten' in err and not any(secret in err for secret in SECRETS)


TEMPORARY = re.compile(r'\.' + re.escape(OWNER_RECOVERY) + r'\.[0-9a-f]{32}\.tmp')


def temporaries(directory):
    return sorted(p.name for p in directory.iterdir() if TEMPORARY.fullmatch(p.name))


def short_write(patch, written=40):
    """ENOSPC after the first `written` bytes of a recovery record (the only binary-mode os.fdopen writer here)."""
    real_fdopen = os.fdopen

    class Short(io.RawIOBase):
        def __init__(self, fd):
            self.fd = fd

        def writable(self):
            return True

        def write(self, data):
            os.write(self.fd, bytes(data[:written]))
            raise OSError(errno.ENOSPC, 'No space left on device')

        def close(self):
            if not self.closed:
                os.close(self.fd)
            super().close()

    def fdopen(fd, mode='r', *args, **kwargs):
        return Short(fd) if mode == 'wb' else real_fdopen(fd, mode, *args, **kwargs)
    patch.setattr('mcp_admin_core.migration.os.fdopen', fdopen)


@pytest.mark.parametrize('fault', ['short write', 'fsync'])
def test_a_failed_record_write_leaves_nothing_and_the_next_start_migrates(tmp_path, monkeypatch, capsys, fault):
    value, product = sample('schema3-hermes-ws97-0.1.14.json')
    install(tmp_path, value)
    before = snapshot(tmp_path)

    def failed_fsync(_):
        raise OSError(errno.EIO, 'secret I/O error')
    with monkeypatch.context() as patch:
        if fault == 'short write':
            short_write(patch)  # disk full in the middle of the record
        else:
            patch.setattr('mcp_admin_core.migration.os.fsync', failed_fsync)
        for _ in range(2):
            with pytest.raises(ConfigError):
                owner_defaults.apply_legacy_upgrade(tmp_path, product)
    # No record, no temporary copy, the state as it was (bytes, mode, mtime of every file).
    assert snapshot(tmp_path) == before and not temporaries(tmp_path)
    err = capsys.readouterr().err
    assert f'{OWNER_RECOVERY} could not be saved (disk full or I/O error)' in err and 'no partial record' in err
    assert 'secret' not in err and not any(secret in err for secret in SECRETS)
    # Space is back: the next start completes the migration with a complete record.
    assert owner_defaults.apply_legacy_upgrade(tmp_path, product)['source_schema'] == 3
    assert read_document(tmp_path / OWNER_RECOVERY) == owner_record(value, product) and not temporaries(tmp_path)
    with closing(ProductStore(tmp_path, product)) as store:
        assert getattr(store.load(), OWNER_DEFAULTS).from_schema == 3


@pytest.mark.parametrize('crash', ['before the link', 'between the link and the unlink'])
def test_an_interrupted_record_creation_never_blocks_the_next_start(tmp_path, crash):
    """What a kill or power loss during the record's creation can leave: an unpublished, possibly partial temporary
    copy, or a second name of the complete record. The next start removes it and migrates."""
    value, product = sample('schema3-hermes-ws97-0.1.14.json')
    install(tmp_path, value)
    record = owner_record(value, product)
    data = (json.dumps(record, sort_keys=True, indent=2) + '\n').encode()
    temporary = tmp_path / f'.{OWNER_RECOVERY}.{"a" * 32}.tmp'
    if crash == 'before the link':
        temporary.write_bytes(data[:40])
    else:
        (tmp_path / OWNER_RECOVERY).write_bytes(data)
        (tmp_path / OWNER_RECOVERY).chmod(0o600)
        os.link(tmp_path / OWNER_RECOVERY, temporary)
    temporary.chmod(0o600)
    assert owner_defaults.apply_legacy_upgrade(tmp_path, product)['source_schema'] == 3
    assert not temporaries(tmp_path) and (tmp_path / OWNER_RECOVERY).stat().st_nlink == 1
    assert read_document(tmp_path / OWNER_RECOVERY) == record
    with closing(ProductStore(tmp_path, product)) as store:
        assert getattr(store.load(), OWNER_DEFAULTS).from_schema == 3


def _broken(directory, case):
    value, _ = sample('schema3-hermes-ws97-0.1.14.json')
    path = install(directory, value)
    if case == 'not json':
        path.write_text('{"schema_version": 3,')
    elif case == 'duplicate key':
        path.write_text('{"schema_version": 3, "schema_version": 4}')
    elif case == 'nonfinite':
        path.write_text(json.dumps(value).replace('false', 'NaN', 1))
    elif case == 'too large':
        path.write_text(json.dumps({**value, 'disabled': ['x' * 70000]}))
    elif case == 'future schema':
        path.write_text(json.dumps({**value, 'schema_version': 5}))
    elif case == 'string schema':
        path.write_text(json.dumps({**value, 'schema_version': '3'}))
    elif case == 'wrong product':
        path.write_text(json.dumps({**value, 'product': 'odoo'}))
    elif case == 'missing key':
        path.write_text(json.dumps({k: v for k, v in value.items() if k != 'disabled'}))
    elif case == 'extra key':
        path.write_text(json.dumps({**value, 'admin_password': 'SECRET-EXTRA'}))
    elif case == 'marker on legacy':
        path.write_text(json.dumps({**value, OWNER_DEFAULTS: {'applied': 'migrated', 'at': '2026-10-27T00:00:00+00:00',
                                                               'from_schema': 3}}))
    elif case == 'null marker on schema 4':
        current = plan_migration(value, 'hermes', policy='all_on').state.model_dump()
        path.write_text(json.dumps({**current, OWNER_DEFAULTS: None}))
    elif case == 'bad grant':
        path.write_text(json.dumps({**value, 'enabled_write_tools': ['hermes_chat']}))  # not a 0.1.x grant
    elif case == 'symlink':
        target = directory.parent / 'outside.json'
        target.write_text(json.dumps(value))
        path.unlink()
        path.symlink_to(target)
    elif case == 'hard link':
        os.link(path, directory.parent / 'second-name.json')
    elif case == 'no writer lock':
        (directory / '.writer.lock').unlink()
    elif case == 'open directory':
        directory.chmod(0o755)
    return path


BROKEN = ['not json', 'duplicate key', 'nonfinite', 'too large', 'future schema', 'string schema', 'wrong product',
          'missing key', 'extra key', 'marker on legacy', 'null marker on schema 4', 'bad grant', 'symlink',
          'hard link', 'no writer lock', 'open directory']


@pytest.mark.parametrize('case', BROKEN)
def test_a_broken_or_unsafe_state_is_never_migrated_or_rewritten(tmp_path, capsys, case):
    directory = tmp_path / 'mcp'
    path = _broken(directory, case)
    before = snapshot(directory)
    raw = path.read_bytes() if path.exists() else None
    with pytest.raises(ConfigError):
        owner_defaults.apply_legacy_upgrade(directory, 'hermes')
    assert snapshot(directory) == before and (path.read_bytes() if path.exists() else None) == raw
    assert not (directory / OWNER_RECOVERY).exists() and not list(directory.glob('.state-*'))
    err = capsys.readouterr().err
    assert 'nothing was migrated or rewritten' in err and 'SECRET' not in err and 'DUMMY' not in err


def test_a_busy_writer_is_refused_without_changes(tmp_path):
    value, product = sample('schema3-hermes-ws97-0.1.14.json')
    path = install(tmp_path, value)
    raw = path.read_bytes()
    with (tmp_path / '.writer.lock').open('r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ConfigError):
            owner_defaults.apply_legacy_upgrade(tmp_path, product)
    assert path.read_bytes() == raw and not (tmp_path / OWNER_RECOVERY).exists()


@pytest.mark.parametrize('name', CURRENT)
def test_a_schema4_state_is_never_touched(tmp_path, name):
    value, product = sample(name)
    install(tmp_path, value)
    before = snapshot(tmp_path)
    assert owner_defaults.apply_legacy_upgrade(tmp_path, product) is None
    assert snapshot(tmp_path) == before and not (tmp_path / OWNER_RECOVERY).exists()
    with closing(ProductStore(tmp_path, product)) as store:
        state = store.load()
        assert getattr(state, OWNER_DEFAULTS) is None and owner_defaults.view(state, tmp_path) is None
    for key in ('writes_enabled', 'disabled', 'enabled_write_tools'):
        assert getattr(state, key) == value[key]
    if 'denied_operations' in value:  # written by 0.3.0+: also byte-identical after the store opened it
        assert snapshot(tmp_path) == before


def test_the_ws97_hermes_writes_off_state_keeps_writes_off(tmp_path):
    value, product = sample('schema4-hermes-ws97-0.4.1-writes-off.json')
    install(tmp_path, value)
    raw = (tmp_path / 'state.json').read_bytes()
    assert owner_defaults.apply_legacy_upgrade(tmp_path, product) is None
    with closing(ProductStore(tmp_path, product)) as store:
        state = store.load()
    assert state.writes_enabled is False and state.enabled_write_tools == [] and state.disabled == []
    assert not enabled('hermes_chat', TOOLS['hermes'], state)  # the administrator's choice stays
    assert (tmp_path / 'state.json').read_bytes() == raw


@pytest.mark.parametrize('product', SEVEN)
def test_a_new_installation_is_all_on_and_keeps_the_041_keys(tmp_path, product):
    directory = tmp_path / 'mcp'
    assert owner_defaults.apply_legacy_upgrade(directory, product) is None and not directory.exists()
    with closing(ProductStore(directory, product)) as store:
        state = store.load()
    stored = json.loads((directory / 'state.json').read_text())
    assert set(stored) == STORED_FIELDS  # no marker key: a 0.4.1 runtime still reads it
    assert state.writes_enabled is True and state.enabled_write_tools == fresh_write_grants(product)
    before = snapshot(directory)
    assert owner_defaults.apply_legacy_upgrade(directory, product) is None and snapshot(directory) == before


def _migrated(directory, name):
    value, product = sample(name)
    install(directory, value)
    owner_defaults.apply_legacy_upgrade(directory, product)
    return value, product


@pytest.mark.parametrize('name', LEGACY)
def test_restore_is_faithful_to_the_legacy_limits_and_never_disables_everything(tmp_path, name):
    value, product = _migrated(tmp_path, name)
    _, legacy = _validate(value, product)
    tools = tools_of(product)
    with closing(ProductStore(tmp_path, product)) as store:
        restored = owner_defaults.restore(store)
        assert store.load() == restored
        with pytest.raises(owner_defaults.Unavailable):
            owner_defaults.restore(store)
        with pytest.raises(owner_defaults.Unavailable):
            owner_defaults.dismiss(store)
    assert getattr(restored, OWNER_DEFAULTS).restored_at is not None
    # Tools by the legacy deny list: exactly the tools the old state disabled, no more.
    assert set(restored.disabled) == set(legacy.disabled) & set(tools)
    # Writes by the legacy allow list (0.1.x enabled_write_tools; the legacy switch only for its two legacy writers):
    # only the grants the old state held stay, every other one is revoked, one added since 0.1.x included.
    held = set(legacy.enabled_write_tools) | (
        {name for name, tool in LEGACY_TOOLS[product].items() if tool['legacy_write']} if legacy.writes_enabled else set())
    assert set(restored.enabled_write_tools) == held & write_grants(product)
    assert not (write_grants(product) - _legacy_grants(product)) & set(restored.enabled_write_tools)
    # So the restored policy permits exactly the writes the legacy runtime permitted, and nothing else.
    assert _effective(restored, legacy=False) == _effective(legacy, legacy=True)
    # A tool added since 0.1.x is never disabled by the restore; one without any write grant stays usable.
    for tool in set(tools) - set(LEGACY_TOOLS[product]):
        assert tool not in restored.disabled, tool
        if not tools[tool].grants(tool):
            assert policy_enabled(tool, tools, restored), tool
    assert sum(policy_enabled(tool, tools, restored) for tool in tools) > 0  # never "everything disabled"
    # Identity is the current one.
    for key in ('token', 'child_token', 'endpoint', 'backend_url', 'backend_key', 'connection'):
        assert restored.model_dump()[key] == ({**value, 'connection': value.get('connection')}).get(key)


async def test_the_ws97_hermes_sample_restores_to_its_read_only_policy_not_zero_tools(tmp_path):
    """ws97's real Hermes 0.1.14 state: hermes_skill disabled, writes off, no grant. Restored: the same (no write at
    all, as 0.1.14 allowed none), 9 of 11 tools listed (hermes_skill disabled, the write-only hermes_chat ungranted);
    the 0.3.0 preserve choice listed 0."""
    value, product = _migrated(tmp_path, 'schema3-hermes-ws97-0.1.14.json')
    with closing(ProductStore(tmp_path, product)) as store:
        restored = owner_defaults.restore(store)
        assert restored.disabled == ['hermes_skill'] and restored.enabled_write_tools == []
        assert restored.writes_enabled is False
        async with Boundary(store, product, NO_CHILD) as boundary:
            _, tools = await boundary.connect()
        names = {tool['name'] for tool in tools}
        assert len(tools) == 9 and not names & {'hermes_skill', 'hermes_chat'}
        assert names == {name for name in TOOLS['hermes'] if policy_enabled(name, TOOLS['hermes'], restored)}


def test_restore_keeps_what_the_administrator_changed_after_the_upgrade(tmp_path):
    _migrated(tmp_path, 'schema3-hermes-ws97-0.1.14.json')
    with closing(ProductStore(tmp_path, 'hermes')) as store:
        grants = [g for g in store.load().enabled_write_tools if g != 'hermes_chat']
        store.update(token='R' * 43, disabled=['hermes_inspect'], enabled_write_tools=grants,
                     denied_operations={'hermes_cron': ['trigger']})
        restored = owner_defaults.restore(store)
    assert restored.token == 'R' * 43
    assert set(restored.disabled) == {'hermes_inspect', 'hermes_skill'}
    assert 'hermes_chat' not in restored.enabled_write_tools and 'hermes_cron:pause' not in restored.enabled_write_tools
    assert restored.denied_operations == {'hermes_cron': ['trigger']}


def test_restore_refuses_a_missing_or_tampered_record_without_changes(tmp_path):
    _migrated(tmp_path, 'schema3-hermes-ws97-0.1.14.json')
    record = tmp_path / OWNER_RECOVERY
    good = record.read_text()
    with closing(ProductStore(tmp_path, 'hermes')) as store:
        for content in (None, '{', json.dumps({**json.loads(good), 'format': 1}),
                        json.dumps({**json.loads(good), 'product': 'odoo'}),
                        json.dumps({**json.loads(good), 'token': 'T' * 43}),
                        json.dumps({**json.loads(good), 'legacy_policy': {**json.loads(good)['legacy_policy'],
                                                                           'enabled_write_tools': ['hermes_chat']}})):
            record.unlink(missing_ok=True)
            if content is not None:
                record.write_text(content)
                record.chmod(0o600)
            before = store.path.read_bytes()
            with pytest.raises(owner_defaults.Unavailable):
                owner_defaults.restore(store)
            assert store.path.read_bytes() == before
            view = owner_defaults.view(store.load(), tmp_path)
            assert view['recovery'] == ('missing' if content is None else 'invalid') and view['restore'] is None
            assert view['notice'] is True  # the administrator still learns of the migration


@pytest.mark.parametrize('name', LEGACY)
def test_the_notice_view_names_the_differences_and_holds_no_secret(tmp_path, name):
    value, product = _migrated(tmp_path, name)
    with closing(ProductStore(tmp_path, product)) as store:
        state = store.load()
    view = owner_defaults.view(state, tmp_path)
    assert view['applied'] == 'migrated' and view['from_schema'] == value['schema_version'] and view['recovery'] == 'available'
    assert view['upgrade']['enabled_tools'] == sorted(value['disabled'])
    assert view['upgrade']['new_tools'] == sorted(set(tools_of(product)) - set(LEGACY_TOOLS[product]))
    assert view['restore']['disabled_added'] == sorted(set(value['disabled']) & set(tools_of(product)))
    # The preview names every write the restore revokes: all but the legacy state's own grants, newer ones included.
    _, legacy = _validate(value, product)
    held = set(legacy.enabled_write_tools) | (
        {name for name, tool in LEGACY_TOOLS[product].items() if tool['legacy_write']} if legacy.writes_enabled else set())
    assert view['restore']['write_grants_removed'] == sorted(write_grants(product) - held)
    assert set(view['upgrade']['new_write_operations']) <= set(view['restore']['write_grants_removed'])
    assert set(view['restore']) == {'disabled_added', 'write_grants_removed', 'operation_denies_added', 'writes_enabled',
                                    'kept_new_tools', 'policy_changed', 'available'}
    assert view['notice'] is True and view['restore']['available'] is view['restore']['policy_changed']
    wire = json.dumps(view)
    assert not any(secret in wire for secret in SECRETS) and 'sha256' not in wire


def test_the_offline_cli_restores_a_format2_record_and_records_it(tmp_path, capsys):
    _migrated(tmp_path, 'schema3-hermes-ws97-0.1.14.json')
    record = str(tmp_path / OWNER_RECOVERY)
    capsys.readouterr()
    assert main([str(tmp_path), '--product', 'hermes', '--restore-policy', record]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview['dry_run'] is True and preview['disabled_added'] == ['hermes_skill']
    assert main([str(tmp_path), '--product', 'hermes', '--restore-policy', record, '--apply',
                 '--expected-sha256', preview['source_sha256']]) == 0
    with closing(ProductStore(tmp_path, 'hermes')) as store:
        state = store.load()
    assert state.disabled == ['hermes_skill'] and getattr(state, OWNER_DEFAULTS).restored_at is not None
    assert plan_restore(state.model_dump(), 'hermes', read_document(record)).report['policy_changed'] is False


async def _admin(store, product, allowed=True, restarts=None):
    async def verify(_):
        return allowed

    async def changed(state):
        if restarts is not None:
            restarts.append(state)
    child = httpx.AsyncClient(trust_env=False)
    admin, _ = make_apps(store, N8N_TOOLS if product == 'n8n' else TOOLS[product], child, verify_admin=verify,
                         backend_changed=changed)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(admin, client=('172.30.32.2', 1)), base_url='http://admin')
    return client, child


async def test_the_panel_restores_once_with_csrf_role_and_the_reviewed_revision(tmp_path):
    _migrated(tmp_path, 'schema3-hermes-ws97-0.1.14.json')
    with closing(ProductStore(tmp_path, 'hermes')) as store:
        client, child = await _admin(store, 'hermes')
        async with client, child:
            boot = await client.get('/api/bootstrap', headers=IDENTITY)
            view = boot.json()['owner_defaults']
            assert view['notice'] is True and view['restore']['available'] is True
            assert not any(secret in boot.text for secret in SECRETS[2:])
            csrf = {**IDENTITY, 'x-csrf-token': boot.json()['csrf']}
            before = store.path.read_bytes()
            assert (await client.post('/api/owner-defaults/restore', headers=IDENTITY)).status_code == 403
            missing = await client.post('/api/owner-defaults/restore', headers=csrf)
            assert missing.status_code == 428 and missing.json()['detail']['code'] == 'precondition_required'
            stale = await client.post('/api/owner-defaults/restore', headers={**csrf, 'if-match': '"c1-' + '0' * 64 + '"'})
            assert stale.status_code == 409 and stale.json()['detail']['code'] == 'config_conflict'
            body = await client.post('/api/owner-defaults/restore', headers={**csrf, 'if-match': boot.headers['etag']},
                                     content=b'{}')
            assert body.status_code == 400
            assert store.path.read_bytes() == before
            done = await client.post('/api/owner-defaults/restore', headers={**csrf, 'if-match': boot.headers['etag']})
            assert done.status_code == 200 and done.json()['saved'] is True
            assert done.json()['owner_defaults']['notice'] is False and done.json()['owner_defaults']['restored_at']
            assert done.headers['etag'] != boot.headers['etag']
            assert store.load().disabled == ['hermes_skill']
            again = await client.post('/api/owner-defaults/restore', headers={**csrf, 'if-match': done.headers['etag']})
            assert again.status_code == 409 and again.json()['detail']['code'] == 'owner_defaults_unavailable'


async def test_a_denied_role_never_restores_or_dismisses(tmp_path):
    _migrated(tmp_path, 'schema3-hermes-ws97-0.1.14.json')
    with closing(ProductStore(tmp_path, 'hermes')) as store:
        allowed, allowed_child = await _admin(store, 'hermes')
        async with allowed, allowed_child:
            boot = await allowed.get('/api/bootstrap', headers=IDENTITY)
        denied, child = await _admin(store, 'hermes', allowed=False)
        async with denied, child:
            before = store.path.read_bytes()
            for action in ('restore', 'dismiss'):
                response = await denied.post(f'/api/owner-defaults/{action}', headers={
                    **IDENTITY, 'x-csrf-token': boot.json()['csrf'], 'if-match': boot.headers['etag']})
                assert response.status_code == 403
            assert (await denied.get('/api/bootstrap', headers=IDENTITY)).status_code == 403
            assert store.path.read_bytes() == before


async def test_keep_everything_on_ends_the_notice_and_restore_stays_possible(tmp_path):
    restarts = []
    _migrated(tmp_path, 'schema3-emqx-v0.1.14-fresh.json')
    with closing(ProductStore(tmp_path, 'emqx')) as store:
        client, child = await _admin(store, 'emqx', restarts=restarts)
        async with client, child:
            boot = await client.get('/api/bootstrap', headers=IDENTITY)
            headers = {**IDENTITY, 'x-csrf-token': boot.json()['csrf']}
            kept = await client.post('/api/owner-defaults/dismiss', headers={**headers, 'if-match': boot.headers['etag']})
            assert kept.status_code == 200 and kept.json()['owner_defaults']['acknowledged_at']
            assert kept.json()['owner_defaults']['notice'] is False and restarts == []
            assert store.load().enabled_write_tools == fresh_write_grants('emqx')
            boot = await client.get('/api/bootstrap', headers=IDENTITY)
            assert boot.json()['owner_defaults']['restore']['available'] is True
            done = await client.post('/api/owner-defaults/restore', headers={
                **IDENTITY, 'x-csrf-token': boot.json()['csrf'], 'if-match': boot.headers['etag']})
            assert done.status_code == 200
            # EMQX's child is launched with the policy: a restore restarts it, as a saved policy does.
            assert len(restarts) == 1 and restarts[0] == store.load()
            # The 0.1.14 default granted no write: none is granted again, a write added since 0.1.x included.
            assert store.load().enabled_write_tools == [] and 'emqx_kick_client' not in store.load().enabled_write_tools


async def test_a_state_without_the_marker_has_no_notice_and_no_actions(tmp_path):
    with closing(ProductStore(tmp_path / 'mcp', 'odoo')) as store:
        client, child = await _admin(store, 'odoo')
        async with client, child:
            boot = await client.get('/api/bootstrap', headers=IDENTITY)
            assert 'owner_defaults' not in boot.json()
            for action in ('restore', 'dismiss'):
                response = await client.post(f'/api/owner-defaults/{action}', headers={
                    **IDENTITY, 'x-csrf-token': boot.json()['csrf'], 'if-match': boot.headers['etag']})
                assert response.status_code == 409 and response.json()['detail']['code'] == 'owner_defaults_unavailable'


def test_the_retired_odoo_manage_keeps_its_policy_and_shows_no_notice(tmp_path):
    value = {**sample('schema3-odoo-v0.1.14-max.json')[0], 'product': 'odoo-manage',
             'connection': {'url': 'http://odoo.invalid:8069', 'database': 'dummy', 'username': 'dummy',
                            'api_key': 'DUMMY-api-key', 'mode': 'module'},
             'disabled': ['get_record'], 'enabled_write_tools': ['create_record']}
    install(tmp_path, value)
    owner_defaults.apply_legacy_upgrade(tmp_path, 'odoo-manage')
    with closing(ProductStore(tmp_path, 'odoo-manage')) as store:
        state = store.load()
    assert state.disabled == ['get_record'] and state.enabled_write_tools == ['create_record']
    view = owner_defaults.view(state, tmp_path)
    assert view['upgrade']['changed'] is False and view['notice'] is False and view['restore']['available'] is False


@pytest.mark.parametrize('kind', ['product', 'n8n'])
async def test_both_runtimes_migrate_before_the_store_and_stop_on_failure(tmp_path, monkeypatch, kind):
    if kind == 'product':
        module = run_product
    else:
        spec = importlib.util.spec_from_file_location(
            'owner_defaults_n8n_runtime', Path(__file__).resolve().parents[1] / 'apps/n8n/run.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    seen = []

    def migrate(directory, product):
        seen.append(('migrate', product))
        raise ConfigError('fixed')

    def store(*_):
        seen.append('store')
        raise AssertionError('ProductStore constructed after a failed migration')
    monkeypatch.setattr(owner_defaults, 'apply_legacy_upgrade', migrate)
    monkeypatch.setattr(module, 'ProductStore', store)
    with pytest.raises(ConfigError):
        await module.run(SimpleNamespace(data=tmp_path / 'state', product='hermes'))
    assert seen == [('migrate', 'hermes' if kind == 'product' else 'n8n')]


async def test_the_real_runtime_order_reaches_the_store_with_the_migrated_state(tmp_path, monkeypatch):
    """run_product.run with the real migration: the first store it constructs already sees schema 4 + marker."""
    value, _ = sample('schema3-litellm-v0.1.14-max.json')
    install(tmp_path, value)
    loaded = []

    class Stop(Exception):
        pass

    def store(directory, product):
        with closing(ProductStore(directory, product)) as real:
            loaded.append(real.load())
        raise Stop()
    monkeypatch.setattr(run_product, 'ProductStore', store)
    with pytest.raises(Stop):
        await run_product.run(SimpleNamespace(data=tmp_path, product='litellm'))
    assert getattr(loaded[0], OWNER_DEFAULTS).from_schema == 3 and loaded[0].disabled == []


def test_plan_owner_restore_refuses_legacy_or_foreign_input():
    value, product = sample('schema3-hermes-ws97-0.1.14.json')
    record = owner_record(value, product)
    with pytest.raises(MigrationError):
        plan_owner_restore(value, product, record)  # the current state must be schema 4
    current = plan_migration(value, product, policy='all_on').state.model_dump()
    for bad in ({**record, 'source_schema': 4}, {**record, 'format': True}, {**record, 'decision': 'other'},
                {**record, 'legacy_catalog_sha256': '0' * 64}, {**record, 'source_sha256': 'x'},
                {**record, 'extra': 1}, [record]):
        with pytest.raises(MigrationError):
            plan_owner_restore(current, product, bad)
    assert plan_owner_restore(current, product, record).report['disabled_added'] == ['hermes_skill']
