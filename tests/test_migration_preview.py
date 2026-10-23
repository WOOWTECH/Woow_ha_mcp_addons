"""Offline fixtures: no installed state, backend, child process or live upgrade."""
from contextlib import closing
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import get_args

import pytest

from mcp_admin_core.legacy_catalog import LEGACY_TOOLS
from mcp_admin_core.migration import (MigrationError, apply_migration, apply_restore, plan_migration,
                                      plan_restore, read_document, save_recovery)
from mcp_admin_core.policy import Tool
from mcp_admin_core.products import BOUNDED_TOOLS, PRODUCTS, ProductStore, TOOLS, fresh_write_grants
from mcp_admin_core.surface import ChildArguments, full_tools
from n8n_adapter import BOUNDED_TOOLS as N8N_BOUNDED

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / 'fixtures/migration'
ALL = (*PRODUCTS, 'n8n')
CASES = [(1, 'n8n')] + [(version, product) for version in (2, 3) for product in ALL]
CONNECTIONS = {
    'odoo': {'url': 'https://legacy.example.test', 'database': 'fixture', 'username': 'fixture', 'password': 'DUMMY'},
    'odoo-manage': {'url': 'https://legacy.example.test', 'database': 'fixture', 'username': 'fixture', 'api_key': 'DUMMY',
                    'mode': 'module'},
    'hermes': {'gateway_url': 'https://legacy.example.test', 'gateway_api_key': 'DUMMY', 'dashboard_url': None,
               'dashboard_username': None, 'dashboard_password': None},
    'opendesign': {'url': 'https://legacy.example.test'},
    'emqx': {'url': 'https://legacy.example.test', 'api_key': 'DUMMY', 'api_secret': 'DUMMY'},
    'litellm': {'url': 'https://legacy.example.test', 'master_key': 'DUMMY'},
    'nextcloud': {'url': 'https://legacy.example.test', 'username': 'fixture', 'app_password': 'DUMMY'},
}
GRANTS = {'odoo': 'chatter_post', 'odoo-manage': 'create_record', 'hermes': 'hermes_cron:pause',
          'opendesign': 'delete_project', 'emqx': 'emqx_kick_client', 'litellm': 'litellm_create_team',
          'nextcloud': 'create_text_file', 'n8n': 'n8n_manage_folders:create'}


def fixture(version=3, product='n8n'):
    value = json.loads((FIXTURES / f'schema{version}.json').read_text())
    if product != 'n8n':
        value.update(product=product, connection=deepcopy(CONNECTIONS[product]), backend_url=None, backend_key=None,
                     disabled=[next(iter(BOUNDED_TOOLS[product]))])
    if version == 3:
        value['enabled_write_tools'] = [GRANTS[product]]
    return value


def install_fixture(directory, value):
    directory.mkdir(mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    (directory / '.writer.lock').touch(mode=0o600)
    path = directory / 'state.json'
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return path


def test_catalog_matches_retained_legacy_models():
    for product in ALL:
        bounded = N8N_BOUNDED if product == 'n8n' else BOUNDED_TOOLS[product]
        current = full_tools(product) if product == 'n8n' else TOOLS[product]
        assert set(LEGACY_TOOLS[product]) == set(bounded)
        for name, tool in bounded.items():
            entry = LEGACY_TOOLS[product][name]
            selector = tool.selector or current[name].selector
            field = tool.arguments.model_fields.get(selector)
            assert entry == {'write': tool.write, 'legacy_write': tool.legacy_write,
                             'write_operations': list(tool.write_operations),
                             'read_operations': sorted(set(get_args(field.annotation)) - set(tool.write_operations))
                                                if field else []}


@pytest.mark.parametrize('version,product', CASES)
@pytest.mark.parametrize('policy', ['preserve', 'all_on'])
def test_all_schemas_products_and_choices_are_pure_and_reloadable(tmp_path, version, product, policy):
    value = fixture(version, product)
    original = deepcopy(value)
    plan = plan_migration(value, product, policy=policy)
    assert value == original
    assert plan.state.schema_version == 4
    for key in ('token', 'child_token', 'backend_url', 'backend_key', 'endpoint', 'connection'):
        assert plan.state.model_dump()[key] == original.get(key)
    assert plan.state.mcp_access_token is None
    if policy == 'all_on' and product != 'odoo-manage':
        assert plan.state.disabled == []
        assert plan.state.enabled_write_tools == fresh_write_grants(product)
        assert plan.state.writes_enabled is True
    else:
        assert set(original['disabled']) <= set(plan.state.disabled)
        assert set(plan.report['new_tools']) <= set(plan.state.disabled)
        assert set(plan.report['argument_review_tools']) <= set(plan.state.disabled)
        assert not plan.report['effective_writes_added']
    wire = json.dumps({'report': plan.report, 'recovery': plan.recovery})
    for secret in ('LEGACY_FIXTURE_KEY', 'legacy.example.test', 'public.example.test', 'DUMMY', 't' * 43, 'c' * 43):
        assert secret not in wire and secret not in repr(plan)
    install_fixture(tmp_path, original)
    applied = apply_migration(tmp_path, product, policy=policy, expected_sha256=plan.report['source_sha256'])
    assert applied == plan.report
    before = (tmp_path / 'state.json').read_bytes()
    for _ in range(2):
        with closing(ProductStore(tmp_path, product)) as store:
            assert store.load() == plan.state
        assert (tmp_path / 'state.json').read_bytes() == before
    for second_policy in ('preserve', 'all_on'):
        again = plan_migration(plan.state.model_dump(), product, policy=second_policy)
        assert again.state == plan.state and again.recovery is None and not again.report['changed']


@pytest.mark.parametrize('version,product', CASES)
def test_all_on_matches_unchanged_runtime_migration(tmp_path, version, product):
    value = fixture(version, product)
    expected = plan_migration(value, product, policy='all_on').state
    install_fixture(tmp_path, value)
    with closing(ProductStore(tmp_path, product)) as store:
        assert store.load() == expected


@pytest.mark.parametrize('name,arguments', [
    ('search_records', {'model': 'res.users', 'fields': ['id', 'name'], 'domain': [], 'limit': 1}),
    ('chatter_post', {'model': 'sale.order', 'record_id': 1, 'body': 'fixture-only', 'confirm': False}),
])
def test_preserve_refuses_broader_child_arguments_until_review(name, arguments):
    from mcp_admin_core.policy import authorize, ToolCallRefused
    value = fixture(3, 'odoo')
    value['disabled'] = []
    plan = plan_migration(value, 'odoo', policy='preserve')
    message = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
               'params': {'name': name, 'arguments': arguments}}
    legacy_state = plan.state.model_copy(update={'disabled': []})
    with pytest.raises(ToolCallRefused):
        authorize(deepcopy(message), BOUNDED_TOOLS['odoo'], legacy_state)
    with pytest.raises(ToolCallRefused):
        authorize(deepcopy(message), TOOLS['odoo'], plan.state)
    assert name in plan.report['argument_review_tools']


@pytest.mark.parametrize('product,legacy', [('n8n', 'n8n_delete_workflow'), ('opendesign', 'delete_project')])
def test_global_switch_materializes_only_legacy_writer(product, legacy):
    value = fixture(2, product)
    value['disabled'] = [legacy]
    plan = plan_migration(value, product, policy='preserve')
    assert plan.state.enabled_write_tools == [legacy]
    assert legacy in plan.state.disabled
    assert plan.report['effective_writes_added'] == []
    value['writes_enabled'] = False
    assert plan_migration(value, product, policy='preserve').state.enabled_write_tools == []


@pytest.mark.parametrize('version,product', CASES)
@pytest.mark.parametrize('field,bad', [('disabled', 'SECRET_BAD_POLICY'), ('disabled', ['duplicate', 'duplicate']),
                                    ('writes_enabled', 1), ('token', 'SECRET_BAD_TOKEN'), ('child_token', None),
                                    ('backend_key', ''), ('endpoint', 'https://example.test/no_mcp')])
def test_malformed_legacy_fields_are_rejected_before_all_on_overwrites(version, product, field, bad):
    value = fixture(version, product)
    value[field] = bad
    with pytest.raises(MigrationError) as error:
        plan_migration(value, product, policy='all_on')
    assert 'SECRET' not in str(error.value)


@pytest.mark.parametrize('field,bad', [('enabled_write_tools', 'secret'), ('enabled_write_tools', [1]),
                                    ('enabled_write_tools', ['n8n_delete_workflow', 'n8n_delete_workflow']),
                                    ('enabled_write_tools', ['n8n_test_workflow']),
                                    ('enabled_write_tools', ['hermes_chat']), ('schema_version', True),
                                    ('schema_version', 0), ('schema_version', 5), ('schema_version', '3'),
                                    ('schema_version', 3.0), ('product', 'hermes'), ('extra', 'secret')])
def test_incompatible_or_unknown_legacy_data(field, bad):
    value = fixture()
    value[field] = bad
    with pytest.raises(MigrationError):
        plan_migration(value, 'n8n', policy='preserve')


@pytest.mark.parametrize('version', [1, 2, 3])
def test_every_required_legacy_key_is_required(version):
    value = fixture(version)
    for key in value:
        incomplete = {k: v for k, v in value.items() if k != key}
        with pytest.raises(MigrationError):
            plan_migration(incomplete, 'n8n', policy='all_on')


def test_policy_choice_is_required_and_schema1_is_n8n_only():
    with pytest.raises(TypeError):
        plan_migration(fixture(), 'n8n')
    for policy in (None, '', 'default', 'PRESERVE'):
        with pytest.raises(MigrationError):
            plan_migration(fixture(), 'n8n', policy=policy)
    with pytest.raises(MigrationError):
        plan_migration(fixture(1), 'hermes', policy='preserve')


def test_added_unclassified_tools_are_reported_and_preserve_disables_them(monkeypatch):
    monkeypatch.setitem(TOOLS['hermes'], 'future_tool', Tool(ChildArguments, child_schema=True))
    plan = plan_migration(fixture(3, 'hermes'), 'hermes', policy='preserve')
    assert plan.report['unclassified_tools'] == ['future_tool']
    assert 'future_tool' in plan.report['new_tools'] and 'future_tool' in plan.state.disabled
    assert 'hermes_cron:create' in plan.report['new_write_operations']
    assert 'hermes_cron' in plan.report['argument_review_tools']
    for product, name in [('emqx', 'emqx_test_rule_sql'), ('n8n', 'n8n_audit_instance')]:
        preview = plan_migration(fixture(3, product), product, policy='preserve')
        assert name in preview.report['unverified_tools'] and name in preview.state.disabled


def test_added_read_operation_disables_whole_mixed_tool(monkeypatch):
    tool = TOOLS['hermes']['hermes_cron']
    from dataclasses import replace
    monkeypatch.setitem(TOOLS['hermes'], 'hermes_cron', replace(tool, read_operations=('list', 'new_read')))
    plan = plan_migration(fixture(3, 'hermes'), 'hermes', policy='preserve')
    assert plan.report['expanded_read_tools'] == ['hermes_cron', 'hermes_session']
    assert 'hermes_cron' in plan.state.disabled


@pytest.mark.parametrize('version', [2, 3, 4])
def test_optional_mcp_token_preserved_and_schema4_policy_untouched(version):
    value = fixture(min(version, 3))
    value.update(schema_version=version, mcp_access_token='CURRENT_MCP_SECRET')
    if version == 4:
        value.update(enabled_write_tools=['n8n_test_workflow'], disabled=['n8n_list_workflows'])
    for policy in ('preserve', 'all_on'):
        plan = plan_migration(value, 'n8n', policy=policy)
        assert plan.state.mcp_access_token == 'CURRENT_MCP_SECRET'
        if version == 4:
            assert plan.state.model_dump() == value


@pytest.mark.parametrize('token', [None, 'r' * 43])
@pytest.mark.parametrize('product', ALL)
def test_recovery_keeps_current_credentials_and_later_revocations(product, token):
    plan = plan_migration(fixture(3, product), product, policy='all_on')
    current = plan.state.model_dump()
    current.update(token=token, child_token='s' * 43, enabled_write_tools=[], disabled=['later_disabled_tool'],
                   endpoint='https://new.example.test/mcp')
    if product == 'n8n':
        current.update(backend_key='ROTATED', backend_url='https://new.example.test', mcp_access_token='ROTATED_MCP')
    else:
        current['connection'] = None
    restored = plan_restore(current, product, plan.recovery)
    for field in set(current) - {'disabled', 'enabled_write_tools', 'writes_enabled'}:
        assert restored.state.model_dump()[field] == current[field]
    assert restored.state.enabled_write_tools == []
    assert 'later_disabled_tool' in restored.state.disabled
    assert set(fixture(3, product)['disabled']) <= set(restored.state.disabled)
    assert plan_restore(restored.state.model_dump(), product, plan.recovery).state == restored.state


def test_recovery_rejects_secrets_foreign_catalog_and_malformed_policy():
    plan = plan_migration(fixture(), 'n8n', policy='all_on')
    for key, value in [('token', 'old-secret'), ('product', 'hermes'), ('format', True), ('source_schema', 4),
                       ('catalog_sha256', '0' * 64), ('policy', {'token': 'old-secret'})]:
        record = {**plan.recovery, key: value}
        with pytest.raises(MigrationError):
            plan_restore(plan.state.model_dump(), 'n8n', record)


def test_document_reader_rejects_unsafe_or_malformed_files_without_changes(tmp_path):
    path = tmp_path / 'input.json'
    for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e400}', b'x' * 65537, b'\xff', b'[' * 2000):
        path.write_bytes(raw)
        with pytest.raises(MigrationError):
            read_document(path)
        assert path.read_bytes() == raw
    path.write_text('{}')
    linked = tmp_path / 'linked'
    linked.symlink_to(path)
    with pytest.raises(MigrationError):
        read_document(linked)
    linked.unlink()
    os.link(path, linked)
    with pytest.raises(MigrationError):
        read_document(path)
    fifo = tmp_path / 'fifo'
    os.mkfifo(fifo)
    with pytest.raises(MigrationError):
        read_document(fifo)


def test_recovery_persistence_is_private_exclusive_and_secret_free(tmp_path):
    tmp_path.chmod(0o700)
    plan = plan_migration(fixture(), 'n8n', policy='preserve')
    path = tmp_path / 'policy.json'
    save_recovery(path, plan)
    assert path.stat().st_mode & 0o777 == 0o600
    assert read_document(path) == plan.recovery
    before = path.read_bytes()
    with pytest.raises(MigrationError):
        save_recovery(path, plan)
    assert path.read_bytes() == before
    tmp_path.chmod(0o755)
    with pytest.raises(MigrationError):
        save_recovery(tmp_path / 'other.json', plan)


@pytest.mark.parametrize('policy', ['preserve', 'all_on'])
def test_explicit_offline_apply_and_restore_never_resurrect_token(tmp_path, policy):
    value = fixture()
    path = install_fixture(tmp_path, value)
    preview = plan_migration(value, 'n8n', policy=policy)
    report = apply_migration(tmp_path, 'n8n', policy=policy, expected_sha256=preview.report['source_sha256'])
    assert report == preview.report
    record_path = tmp_path / 'migration-policy-recovery.json'
    assert record_path.exists() and record_path.stat().st_mode & 0o777 == 0o600
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        store.update(token=None, child_token='r' * 43, backend_key='ROTATED', enabled_write_tools=[])
    current = read_document(path)
    restore = plan_restore(current, 'n8n', read_document(record_path))
    apply_restore(tmp_path, 'n8n', record_path, expected_sha256=restore.report['source_sha256'])
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        assert store.load().token is None and store.load().child_token == 'r' * 43
        assert store.load().backend_key == 'ROTATED' and store.load().enabled_write_tools == []
    snapshot = path.read_bytes()
    current_plan = plan_migration(read_document(path), 'n8n', policy='all_on')
    apply_migration(tmp_path, 'n8n', policy='all_on', expected_sha256=current_plan.report['source_sha256'])
    assert path.read_bytes() == snapshot


def test_apply_refuses_stale_preview_busy_writer_or_archive_failure(tmp_path, monkeypatch):
    value = fixture()
    path = install_fixture(tmp_path, value)
    preview = plan_migration(value, 'n8n', policy='preserve')
    raw = path.read_bytes()
    with pytest.raises(MigrationError, match='changed since preview'):
        apply_migration(tmp_path, 'n8n', policy='preserve', expected_sha256='0' * 64)
    import fcntl
    with (tmp_path / '.writer.lock').open('r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(MigrationError, match='writer active'):
            apply_migration(tmp_path, 'n8n', policy='preserve', expected_sha256=preview.report['source_sha256'])
    monkeypatch.setattr('mcp_admin_core.migration.os.fsync', lambda *_: (_ for _ in ()).throw(OSError('secret')))
    with pytest.raises(MigrationError, match='not durably saved'):
        apply_migration(tmp_path, 'n8n', policy='preserve', expected_sha256=preview.report['source_sha256'])
    assert path.read_bytes() == raw


def test_failed_state_write_keeps_recovery_and_original_source(tmp_path, monkeypatch):
    value = fixture()
    path = install_fixture(tmp_path, value)
    preview = plan_migration(value, 'n8n', policy='preserve')
    raw = path.read_bytes()
    def failed_replace(*_):
        raise OSError('secret filesystem error')
    monkeypatch.setattr('mcp_admin_core.config.os.replace', failed_replace)
    with pytest.raises(MigrationError, match='recovery record retained'):
        apply_migration(tmp_path, 'n8n', policy='preserve', expected_sha256=preview.report['source_sha256'])
    assert path.read_bytes() == raw
    assert read_document(tmp_path / 'migration-policy-recovery.json') == preview.recovery
    assert not list(tmp_path.glob('.state-*'))


def test_apply_does_not_bootstrap_or_accept_linked_state(tmp_path):
    preview = plan_migration(fixture(), 'n8n', policy='preserve')
    with pytest.raises(MigrationError):
        apply_migration(tmp_path, 'n8n', policy='preserve', expected_sha256=preview.report['source_sha256'])
    assert list(tmp_path.iterdir()) == []
    outside = tmp_path / 'source.json'
    outside.write_text(json.dumps(fixture()))
    directory = tmp_path / 'data'
    directory.mkdir(mode=0o700)
    (directory / '.writer.lock').touch(mode=0o600)
    (directory / 'state.json').symlink_to(outside)
    with pytest.raises(MigrationError):
        apply_migration(directory, 'n8n', policy='preserve', expected_sha256=preview.report['source_sha256'])
    assert list(directory.iterdir()) and not (directory / 'migration-policy-recovery.json').exists()


def test_cli_requires_choice_and_dry_run_does_not_mutate(tmp_path):
    path = install_fixture(tmp_path, fixture())
    before = {p.name: (p.read_bytes(), p.stat().st_mode) for p in tmp_path.iterdir()}
    command = [str(ROOT / '.venv/bin/python'), str(ROOT / 'scripts/migrate_state.py'), str(tmp_path), '--product', 'n8n']
    missing = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert missing.returncode == 2
    preview = subprocess.run(command + ['--policy', 'preserve'], capture_output=True, text=True, timeout=10)
    assert preview.returncode == 0, preview.stderr
    assert json.loads(preview.stdout)['dry_run'] is True
    assert 'LEGACY_FIXTURE_KEY' not in preview.stdout
    assert {p.name: (p.read_bytes(), p.stat().st_mode) for p in tmp_path.iterdir()} == before
    path.write_text('{"schema_version":3,"schema_version":4}')
    invalid = subprocess.run(command + ['--policy', 'all_on'], capture_output=True, text=True, timeout=10)
    assert invalid.returncode == 2 and invalid.stdout == '' and 'Traceback' not in invalid.stderr


def test_cli_apply_and_recovery_round_trip(tmp_path):
    path = install_fixture(tmp_path, fixture())
    command = [str(ROOT / '.venv/bin/python'), str(ROOT / 'scripts/migrate_state.py'), str(tmp_path), '--product', 'n8n']
    def run(*arguments):
        return subprocess.run(command + list(arguments), capture_output=True, text=True, timeout=10)
    preview = run('--policy', 'all_on')
    assert preview.returncode == 0, preview.stderr
    digest = json.loads(preview.stdout)['source_sha256']
    assert run('--policy', 'all_on', '--apply').returncode == 2
    applied = run('--policy', 'all_on', '--apply', '--expected-sha256', digest)
    assert applied.returncode == 0, applied.stderr
    assert json.loads(applied.stdout)['dry_run'] is False
    with closing(ProductStore(tmp_path, 'n8n')) as store:
        store.update(token=None, backend_key='CURRENT', mcp_access_token='CURRENT_MCP')
    record = str(tmp_path / 'migration-policy-recovery.json')
    recovery_preview = run('--restore-policy', record)
    assert recovery_preview.returncode == 0, recovery_preview.stderr
    recovery_digest = json.loads(recovery_preview.stdout)['source_sha256']
    restored = run('--restore-policy', record, '--apply', '--expected-sha256', recovery_digest)
    assert restored.returncode == 0, restored.stderr
    current = read_document(path)
    assert current['token'] is None and current['backend_key'] == 'CURRENT'
    assert current['mcp_access_token'] == 'CURRENT_MCP'
    assert set(fixture()['disabled']) <= set(current['disabled'])


def test_production_module_entrypoint_needs_only_core_closure(tmp_path):
    """Emulate the Python source COPY: no repository scripts or n8n adapter."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('migration_context_closure', ROOT / 'packaging/context_closure.py')
    closure = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(closure)
    patterns = closure.load_ignore((ROOT / '.dockerignore').read_text())
    core = tmp_path / 'core'
    package = core / 'mcp_admin_core'
    package.mkdir(parents=True)
    for path in (ROOT / 'packages/mcp-admin-core/mcp_admin_core').glob('*.py'):
        relative = str(path.relative_to(ROOT))
        if not closure.excluded(patterns, relative):
            shutil.copyfile(path, package / path.name)
    assert (package / 'migration.py').is_file() and (package / 'legacy_catalog.py').is_file()
    env = {**os.environ, 'PYTHONPATH': str(core), 'PYTHONDONTWRITEBYTECODE': '1'}
    for product in ALL:
        assert 'packages/mcp-admin-core' in closure.copy_sources((ROOT / f'apps/{product}/Dockerfile').read_text())
        directory = tmp_path / product
        path = install_fixture(directory, fixture(3, product))
        raw = path.read_bytes()
        result = subprocess.run([str(ROOT / '.venv/bin/python'), '-m', 'mcp_admin_core.migration', str(directory),
                                 '--product', product, '--policy', 'preserve'],
                                cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['dry_run'] is True and path.read_bytes() == raw
