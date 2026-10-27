"""Migration planning and policy recovery records. Never invoked by ProductStore construction.

Owner decision 2026-10-27: the runtimes migrate a legacy (schema 1/2/3) state
once, before starting, to exactly this module's all_on plan
(owner_defaults.apply_legacy_upgrade) and keep a format 2 recovery record: the
legacy policy itself, which plan_owner_restore restores faithfully (tools by the
legacy deny list, writes by the legacy allow list). The offline
CLI keeps both explicit choices (preserve, all_on) and format 1 records.
Reports and recovery records contain policy only. A returned state is
private operational data and must not be logged or used as a rollback backup.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import ConfigError, State, Store, strict_json
from .legacy_catalog import LEGACY_TOOLS
from .policy import policy_enabled
from .products import (OWNER_DEFAULTS, PRODUCTS, STORED_FIELDS, ProductState, TOOLS,
                       fresh_write_grants, write_grants)
from .surface import full_tools, names

POLICIES = ('preserve', 'all_on')
POLICY_FIELDS = ('writes_enabled', 'disabled', 'enabled_write_tools', 'denied_operations')
MAX_BYTES = 65536
# Format 2 (owner decision 2026-10-27): written next to state.json by the one-time all-on migration.
OWNER_RECOVERY = 'owner-defaults-20261025-recovery.json'
OWNER_RECORD_FIELDS = frozenset({'format', 'decision', 'product', 'source_schema', 'source_sha256',
                                 'legacy_catalog_sha256', 'legacy_policy'})


class MigrationError(ValueError):
    """Fixed public error; never expose validation input or credentials."""


class RecordNotSaved(MigrationError):
    """A recovery record could not be created durably (disk full, I/O error, unsafe directory); none was left behind."""


class RecordConflict(MigrationError):
    """An owner-defaults recovery record already exists that is not this state's complete record."""


@dataclass(frozen=True)
class MigrationPlan:
    state: ProductState = field(repr=False)
    report: dict
    recovery: dict | None


class _RecoveryPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    writes_enabled: bool
    disabled: list[str]
    enabled_write_tools: list[str]
    denied_operations: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator('denied_operations')
    @classmethod
    def valid_denies(cls, value):
        return ProductState.operation_denies(value)

    @field_validator('disabled')
    @classmethod
    def valid_disabled(cls, value):
        return State.names(value)


def _tools(product):
    return full_tools(product) if product == 'n8n' else TOOLS[product]


def _policy(state):
    return {key: deepcopy(getattr(state, key)) for key in POLICY_FIELDS}


def _legacy_grants(product):
    return {grant for name, tool in LEGACY_TOOLS[product].items()
            for grant in ([name] if tool['write'] else []) +
            [f'{name}:{op}' for op in tool['write_operations']]}


def _validate(value, product):
    """Validate the original policy before replacing any field or version."""
    try:
        if product not in (*PRODUCTS, 'n8n') or not isinstance(value, dict):
            raise ValueError
        version = value.get('schema_version')
        if type(version) is not int or version not in (1, 2, 3, 4):
            raise ValueError
        value = deepcopy(value)
        if version == 1:
            if product != 'n8n' or set(value) != set(State.model_fields):
                raise ValueError
            value = {**State.model_validate(value).model_dump(), 'product': product, 'connection': None}
        else:
            expected = set(STORED_FIELDS) - {'mcp_access_token', 'denied_operations'}
            if version == 2:
                expected -= {'enabled_write_tools'}
            # Only a schema 4 state may carry the owner-defaults marker (and then never null).
            optional = {'mcp_access_token', 'denied_operations'} | ({OWNER_DEFAULTS} if version == 4 else set())
            if (set(value) - optional != expected or value.get('product') != product
                    or (OWNER_DEFAULTS in value and value[OWNER_DEFAULTS] is None)):
                raise ValueError
        if version < 3:
            value['enabled_write_tools'] = []
        value.setdefault('mcp_access_token', None)
        value.setdefault('denied_operations', {})
        value['schema_version'] = 4
        state = ProductState.model_validate(value)
        if version < 4 and set(state.enabled_write_tools) - _legacy_grants(product):
            raise ValueError
        return version, state
    except (ValueError, TypeError, RecursionError):
        raise MigrationError('invalid, incompatible or wrong-product migration source') from None


def _effective(state, *, legacy):
    grants = set(state.enabled_write_tools)
    if legacy and state.writes_enabled:
        grants.update(name for name, tool in LEGACY_TOOLS[state.product].items() if tool['legacy_write'])
    return {g for g in grants if g.split(':', 1)[0] not in state.disabled
            and (':' not in g or g.split(':', 1)[1] not in state.denied_operations.get(g.split(':', 1)[0], ()))}


def _preserve(state):
    tools = _tools(state.product)
    old = LEGACY_TOOLS[state.product]
    # Keep the conservative batch2 migration boundary: expanded argument validation
    # also needs review before the tool is enabled, even with operation denies.
    expanded_reads = {name for name, tool in tools.items() if name in old
                      and set(tool.read_operations) - set(old[name]['read_operations'])}
    # The full child validates a broader argument surface than the old bounded
    # models (e.g. Odoo model allowlists). Grant names alone cannot preserve
    # that boundary. Hold these tools disabled until the owner reviews them.
    argument_review = {name for name, tool in tools.items() if name in old and tool.child_schema}
    disabled = sorted(set(state.disabled) | (set(tools) - set(old)) | expanded_reads | argument_review)
    grants = set(state.enabled_write_tools)
    if state.writes_enabled:
        grants.update(name for name, tool in old.items() if tool['legacy_write'])
    return ProductState.model_validate({**state.model_dump(), 'disabled': disabled,
                                        'enabled_write_tools': sorted(grants)})


def _catalog_digest(product):
    current = {name: {'write': t.write, 'legacy_write': t.legacy_write,
                      'read_operations': t.read_operations, 'write_operations': t.write_operations}
               for name, t in _tools(product).items()}
    raw = json.dumps([LEGACY_TOOLS[product], current], sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def source_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def plan_migration(value, product, *, policy):
    """Pure explicit-choice plan. Schema 4 policy/identity/backend are unchanged.

    Comparisons use the final 0.1.x catalog, not an inferred installation date.
    Argument constraints formerly enforced by bounded models are not restored.
    """
    if policy not in POLICIES:
        raise MigrationError('choose preserve or all_on explicitly')
    version, before = _validate(value, product)
    tools = _tools(product)
    old = LEGACY_TOOLS[product]
    after = before
    recovery = None
    if version < 4:
        preserved = _preserve(before)
        after = preserved
        if policy == 'all_on' and product != 'odoo-manage':
            after = ProductState.model_validate({**before.model_dump(), 'writes_enabled': True,
                                                 'disabled': [], 'denied_operations': {}, 'enabled_write_tools': fresh_write_grants(product)})
        recovery = {'format': 1, 'product': product, 'source_schema': version,
                    'catalog_sha256': _catalog_digest(product), 'policy': _policy(preserved)}
    before_grants, after_grants = _effective(before, legacy=version < 4), _effective(after, legacy=False)
    groups = names(product)
    classified = {name for group in groups.values() for name in group}
    # Retired Manage uses its bounded catalog, not surface.py's broader inventory.
    if product == 'odoo-manage':
        classified = set(old)
    report = {
        'product': product, 'source_schema': version, 'target_schema': 4, 'policy': policy,
        'source_sha256': source_digest(value),
        'changed': before.model_dump() != after.model_dump() or version < 4,
        'source_catalog': 'final-0.1.x-bounded' if version < 4 else 'current-schema-4',
        'before': _policy(before), 'after': _policy(after),
        'disabled_added': sorted(set(after.disabled) - set(before.disabled)),
        'disabled_removed': sorted(set(before.disabled) - set(after.disabled)),
        'write_grants_added': sorted(set(after.enabled_write_tools) - set(before.enabled_write_tools)),
        'write_grants_removed': sorted(set(before.enabled_write_tools) - set(after.enabled_write_tools)),
        'effective_writes_added': sorted(after_grants - before_grants),
        'effective_writes_removed': sorted(before_grants - after_grants),
        'new_tools': sorted(set(tools) - set(old)) if version < 4 else [],
        'new_write_operations': sorted({g for n, t in tools.items() for g in t.grants(n)} - _legacy_grants(product))
                                if version < 4 else [],
        'unclassified_tools': sorted(set(tools) - classified),
        'unverified_tools': sorted(set(groups['unverified']) & set(tools)),
        'expanded_read_tools': sorted(n for n, t in tools.items() if n in old
                                     and set(t.read_operations) - set(old[n]['read_operations'])) if version < 4 else [],
        'argument_review_tools': sorted(n for n, t in tools.items() if n in old and t.child_schema) if version < 4 else [],
    }
    return MigrationPlan(after, report, recovery)


def utc_now():
    """The owner-defaults timestamp format (the PaaS marker's): ISO 8601, seconds, UTC as +00:00."""
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _legacy_catalog_digest(product):
    raw = json.dumps(LEGACY_TOOLS[product], sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def owner_record(value, product):
    """Format 2 recovery record of a legacy state: its policy exactly as the old format expressed it.

    writes_enabled, disabled, enabled_write_tools and denied_operations as validated (schema 1/2 had no exact
    grants), the digest of the source document and of the frozen 0.1.x catalog it is read against. Never a token,
    endpoint, connection or backend field. Deterministic: an interrupted migration rebuilds the same record.
    """
    version, before = _validate(value, product)
    if version >= 4:
        raise MigrationError('schema 4 has no legacy policy to record')
    return {'format': 2, 'decision': OWNER_DEFAULTS, 'product': product, 'source_schema': version,
            'source_sha256': source_digest(value), 'legacy_catalog_sha256': _legacy_catalog_digest(product),
            'legacy_policy': _policy(before)}


def owner_legacy_policy(record, product):
    """The validated legacy policy of a format 2 record; MigrationError for anything else."""
    try:
        if (not isinstance(record, dict) or set(record) != OWNER_RECORD_FIELDS
                or type(record['format']) is not int or record['format'] != 2
                or record['decision'] != OWNER_DEFAULTS or record['product'] != product
                or type(record['source_schema']) is not int or record['source_schema'] not in (1, 2, 3)
                or (record['source_schema'] == 1 and product != 'n8n')
                or not isinstance(record['source_sha256'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', record['source_sha256'])
                or record['legacy_catalog_sha256'] != _legacy_catalog_digest(product)
                or not isinstance(record['legacy_policy'], dict)
                or set(record['legacy_policy']) != set(POLICY_FIELDS)):
            raise ValueError
        legacy = _RecoveryPolicy.model_validate(record['legacy_policy'])
        if (len(set(legacy.enabled_write_tools)) != len(legacy.enabled_write_tools)
                or set(legacy.enabled_write_tools) - _legacy_grants(product)
                or (record['source_schema'] < 3 and legacy.enabled_write_tools)):
            raise ValueError
    except (ValueError, TypeError, KeyError, RecursionError):
        raise MigrationError('invalid or incompatible owner-defaults recovery record') from None
    return legacy


def _legacy_held(product, legacy):
    """The write grants the legacy state held. 0.1.x enabled_write_tools was an allow list (policy.has_grant then as
    now): an exact entry, or, with the legacy global switch on, one of the two legacy writers (n8n_delete_workflow,
    OpenDesign delete_project). No other write was permitted, including any write the catalog did not have yet."""
    held = set(legacy.enabled_write_tools)
    if legacy.writes_enabled:
        held |= {name for name, tool in LEGACY_TOOLS[product].items() if tool['legacy_write']}
    return held


def _legacy_revoked(product, legacy):
    """The final 0.1.x write grants the legacy state did not hold (what the migration granted within that catalog)."""
    return _legacy_grants(product) - _legacy_held(product, legacy)


def owner_upgrade_summary(product, legacy):
    """What the one-time all-on migration changed for this legacy policy (names only)."""
    tools = _tools(product)
    if product == 'odoo-manage':  # retired: its all_on plan keeps the legacy policy
        return {'enabled_tools': [], 'granted_writes': [], 'cleared_operation_denies': [], 'new_tools': [],
                'new_write_operations': [], 'writes_enabled': [legacy.writes_enabled, legacy.writes_enabled],
                'changed': False}
    summary = {
        'enabled_tools': sorted(legacy.disabled),
        'granted_writes': sorted(_legacy_revoked(product, legacy)),
        'cleared_operation_denies': sorted(f'{name}:{op}' for name, ops in legacy.denied_operations.items() for op in ops),
        'new_tools': sorted(set(tools) - set(LEGACY_TOOLS[product])),
        'new_write_operations': sorted(write_grants(product) - _legacy_grants(product)),
        'writes_enabled': [legacy.writes_enabled, True],
    }
    summary['changed'] = (any(summary[key] for key in ('enabled_tools', 'granted_writes', 'cleared_operation_denies',
                                                       'new_tools', 'new_write_operations'))
                          or not legacy.writes_enabled)
    return summary


def plan_owner_restore(value, product, record, *, at=None):
    """Faithful restore of the pre-upgrade limits into CURRENT schema 4, from a format 2 record.

    Each list is read the way the legacy runtime enforced it. Tools: a deny list, so the tools the legacy state
    disabled are disabled again and a tool added since 0.1.x stays enabled (never "everything disabled", unlike
    preserve). Writes: an allow list, so only the write grants the legacy state held stay granted (_legacy_held);
    every other one is revoked, a write operation added since 0.1.x included, as the legacy runtime refused it. Its
    legacy write switch and operation denies come back. Restrictive merge: what the administrator disabled, revoked or
    denied after the upgrade stays so, and nothing is enabled or granted. Token, child token, endpoint and backend are
    the current ones. With at, the marker records restored_at.
    """
    version, current = _validate(value, product)
    if version != 4:
        raise MigrationError('recovery requires current schema 4 state')
    legacy = owner_legacy_policy(record, product)
    tools = _tools(product)
    held = _legacy_held(product, legacy)
    marker = getattr(current, OWNER_DEFAULTS)
    if marker is not None and at is not None and marker.restored_at is None:
        marker = {**marker.model_dump(), 'restored_at': at}

    def merged(old, new):  # an unchanged set keeps the administrator's saved order
        return old if set(new) == set(old) else sorted(new)

    denies = dict(current.denied_operations)
    for name, operations in legacy.denied_operations.items():
        denies[name] = merged(denies.get(name, []), set(denies.get(name, ())) | set(operations))
    try:
        restored = ProductState.model_validate({
            **current.model_dump(),
            'disabled': merged(current.disabled, set(current.disabled) | (set(legacy.disabled) & set(tools))),
            'enabled_write_tools': merged(current.enabled_write_tools, set(current.enabled_write_tools) & held),
            'writes_enabled': current.writes_enabled and legacy.writes_enabled,
            'denied_operations': denies,
            **({OWNER_DEFAULTS: marker} if marker is not None else {}),
        })
    except (ValueError, TypeError, RecursionError):
        raise MigrationError('invalid or incompatible owner-defaults recovery record') from None
    added_denies = sorted(f'{name}:{op}' for name, ops in restored.denied_operations.items() for op in ops
                          if op not in current.denied_operations.get(name, ()))
    report = {
        'product': product, 'source_schema': 4, 'target_schema': 4, 'policy': 'owner_restore',
        'legacy_schema': record['source_schema'], 'source_sha256': source_digest(value),
        'before': _policy(current), 'after': _policy(restored),
        'disabled_added': sorted(set(restored.disabled) - set(current.disabled)),
        'write_grants_removed': sorted(set(current.enabled_write_tools) - set(restored.enabled_write_tools)),
        'operation_denies_added': added_denies,
        'writes_enabled': [current.writes_enabled, restored.writes_enabled],
        # The tools added since 0.1.x that the restored policy still lets a client call (a write-only one needs its
        # grant, which the legacy allow list did not hold).
        'kept_new_tools': sorted(name for name in set(tools) - set(LEGACY_TOOLS[product])
                                 if policy_enabled(name, tools, restored)),
        'ignored_disabled': sorted(set(legacy.disabled) - set(tools)),
        'policy_changed': _policy(current) != _policy(restored),
        'changed': current.model_dump() != restored.model_dump(),
    }
    return MigrationPlan(restored, report, None)


def save_owner_record(path, record):
    """Create the format 2 record once (0600, exclusive, durable) in an existing owner-only directory.

    Called under the runtime's writer lock (owner_defaults.migrate_locked), so a temporary copy next to the record can
    only be an interrupted earlier attempt's: it is removed first. An identical record (an earlier attempt stopped
    before its state write) is reused: True when created, False when reused. Any other existing file (incomplete,
    damaged, another state's, not a regular file) is refused and kept (RecordConflict): the caller must not migrate
    without its own record. RecordNotSaved when it cannot be created; then no partial record is left behind.
    """
    owner_legacy_policy(record, record.get('product') if isinstance(record, dict) else None)
    data = json.dumps(record, sort_keys=True, indent=2).encode() + b'\n'
    if len(data) > MAX_BYTES:
        raise MigrationError('policy recovery record too large')
    path = Path(os.path.abspath(path))
    _discard_temporaries(path)
    if path.exists() or path.is_symlink():
        try:
            existing = read_document(path)
        except MigrationError:
            existing = None
        if existing != record:
            raise RecordConflict('a different or incomplete owner-defaults recovery record exists; inspect protected state')
        return False
    _create_private(path, data)
    return True


def plan_restore(value, product, recovery):
    """Restrictive policy recovery into CURRENT schema 4; never restore identity.

    Newer disabled tools and revoked grants stay revoked. This is neither a
    binary downgrade nor a full-state backup restore. A format 2 record (the
    one-time all-on migration's) is restored faithfully by plan_owner_restore.
    """
    if isinstance(recovery, dict) and recovery.get('format') == 2:
        return plan_owner_restore(value, product, recovery, at=utc_now())
    version, current = _validate(value, product)
    if version != 4:
        raise MigrationError('recovery requires current schema 4 state')
    try:
        if (not isinstance(recovery, dict) or set(recovery) !=
                {'format', 'product', 'source_schema', 'catalog_sha256', 'policy'}
                or type(recovery['format']) is not int or recovery['format'] != 1
                or type(recovery['source_schema']) is not int or recovery['source_schema'] not in (1, 2, 3)
                or recovery['product'] != product or (recovery['source_schema'] == 1 and product != 'n8n')
                or recovery['catalog_sha256'] != _catalog_digest(product)
                or not isinstance(recovery['policy'], dict)
                or set(recovery['policy']) not in (set(POLICY_FIELDS), set(POLICY_FIELDS) - {'denied_operations'})):
            raise ValueError
        baseline = _RecoveryPolicy.model_validate(recovery['policy'])
        if (len(set(baseline.enabled_write_tools)) != len(baseline.enabled_write_tools)
                or set(baseline.enabled_write_tools) - write_grants(product)):
            raise ValueError
        restored = ProductState.model_validate({
            **current.model_dump(),
            'disabled': sorted(set(current.disabled) | set(baseline.disabled)),
            'enabled_write_tools': sorted(set(current.enabled_write_tools) & set(baseline.enabled_write_tools)),
            'writes_enabled': current.writes_enabled and baseline.writes_enabled,
            'denied_operations': {name: sorted(set(current.denied_operations.get(name, ()))
                                                | set(baseline.denied_operations.get(name, ())))
                                  for name in current.denied_operations.keys() | baseline.denied_operations.keys()},
        })
    except (ValueError, TypeError, RecursionError):
        raise MigrationError('invalid or incompatible policy recovery record') from None
    return MigrationPlan(restored, {'product': product, 'source_schema': 4, 'target_schema': 4,
                                    'source_sha256': source_digest(value),
                                    'policy': 'recovery', 'before': _policy(current), 'after': _policy(restored),
                                    'changed': current.model_dump() != restored.model_dump()}, None)


def read_document(path):
    """Read without Store construction, chmod, migration, links or unbounded IO."""
    try:
        path = Path(os.path.abspath(path))
        if any(p.is_symlink() for p in (*path.parents, path)):
            raise ValueError
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES:
                raise ValueError
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError
        return strict_json(raw)
    except (OSError, ValueError, RecursionError):
        raise MigrationError('migration document unavailable or invalid') from None


def save_recovery(path, plan):
    """Create one secret-free 0600 record in an existing owner-only directory.

    Never overwrite a record. Interrupted writes cannot authorize recovery:
    readers reject incomplete JSON. The caller must stop if durability fails.
    """
    if plan.recovery is None:
        raise MigrationError('no legacy policy recovery record for this plan')
    # Revalidate the public mutable record before persisting any caller data.
    plan_restore(plan.state.model_dump(), plan.state.product, plan.recovery)
    data = json.dumps(plan.recovery, sort_keys=True, indent=2).encode() + b'\n'
    if len(data) > MAX_BYTES:
        raise MigrationError('policy recovery record too large')
    _create_private(path, data)


def _temporaries(name):
    """The temporary names _create_private uses next to the record name: .<name>.<32 hex>.tmp"""
    return re.compile(rf'\.{re.escape(name)}\.[0-9a-f]{{32}}\.tmp')


def _create_private(path, data):
    """Exclusive 0600 creation in an existing owner-only directory: the final name only ever holds the complete data.

    The data is written and fsynced under a random temporary name in the same directory, then hard-linked to the final
    name (which never replaces an existing file), the temporary name is removed and the directory fsynced. A failed
    write (ENOSPC, EIO) removes the temporary file. A crash leaves at most a temporary name next to it (unpublished
    data, or a second name of the complete record), never a partial record under the final name.
    """
    directory_fd = None
    temporary = None
    try:
        path = Path(os.path.abspath(path))
        if any(p.is_symlink() for p in (*path.parents, path)):
            raise ValueError
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(directory_fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError
        name = f'.{path.name}.{secrets.token_hex(16)}.tmp'
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
        temporary = name
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
        os.unlink(temporary, dir_fd=directory_fd)
        temporary = None
        os.fsync(directory_fd)
    except (OSError, ValueError):
        raise RecordNotSaved('policy recovery record not durably saved; source unchanged') from None
    finally:
        if temporary is not None:
            with suppress(OSError):
                os.unlink(temporary, dir_fd=directory_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _discard_temporaries(path):
    """Under the writer lock only: remove the temporary names an interrupted _create_private left next to path.

    Each is unpublished data or a second name of the complete record (a crash between its link and unlink); either way
    the record itself is untouched, and a second name would make read_document refuse it (two links)."""
    directory_fd = None
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        pattern = _temporaries(path.name)
        for name in os.listdir(directory_fd):
            if pattern.fullmatch(name):
                os.unlink(name, dir_fd=directory_fd)
    except OSError:
        raise RecordNotSaved('policy recovery record not durably saved; source unchanged') from None
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


@contextmanager
def _existing_writer(directory):
    """Use the runtime's lock and atomic writer without starting its migration."""
    writer = object.__new__(Store)
    writer.directory = Path(os.path.abspath(directory))
    writer.path = writer.directory / 'state.json'
    writer._lock_fd = None
    writer._poisoned = False
    try:
        if any(p.is_symlink() for p in (*writer.directory.parents, writer.directory)):
            raise ValueError
        info = writer.directory.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError
        # Never bootstrap an empty directory or replace the existing lock inode.
        writer._lock_fd = os.open(writer.directory / '.writer.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(writer._lock_fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise ValueError
        fcntl.flock(writer._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, ValueError):
        writer.close()
        raise MigrationError('existing state unavailable or writer active; stop runtime before applying') from None
    try:
        yield writer
    finally:
        writer.close()


def apply_migration(directory, product, *, policy, expected_sha256):
    """Explicit offline apply; recoverable policy saved before atomic replacement.

    The caller must supply the digest from its reviewed dry run. A changed state
    or existing recovery record is refused, never overwritten.
    """
    with _existing_writer(directory) as writer:
        return apply_migration_locked(writer, product, policy=policy, expected_sha256=expected_sha256)


def apply_migration_locked(writer, product, *, policy, expected_sha256):
    """Apply under the existing writer's lock, shared by CLI and startup review."""
    if writer._lock_fd is None or writer._poisoned:
        raise MigrationError('migration writer unavailable')
    value = read_document(writer.path)
    plan = plan_migration(value, product, policy=policy)
    if plan.report['source_sha256'] != expected_sha256:
        raise MigrationError('state changed since preview; run preview again')
    if plan.recovery is not None:
        save_recovery(writer.directory / 'migration-policy-recovery.json', plan)
        try:
            writer._write(plan.state)
        except ConfigError:
            raise MigrationError('durable migration write failed; recovery record retained; inspect state') from None
    return plan.report


def apply_restore(directory, product, recovery_path, *, expected_sha256):
    """Apply only the restrictive policy plan; current credentials stay current."""
    with _existing_writer(directory) as writer:
        plan = plan_restore(read_document(writer.path), product, read_document(recovery_path))
        if plan.report['source_sha256'] != expected_sha256:
            raise MigrationError('state changed since preview; run preview again')
        if plan.report['changed']:
            try:
                writer._write(plan.state)
            except ConfigError:
                raise MigrationError('durable recovery write failed; inspect current state') from None
        return plan.report


def main(argv=None):
    """CLI also available inside product images: python -m mcp_admin_core.migration."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='Existing data directory containing state.json')
    parser.add_argument('--product', required=True, choices=(*PRODUCTS, 'n8n'))
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--policy', choices=POLICIES, help='Explicit migration choice (no default)')
    choice.add_argument('--restore-policy', type=Path, help='Restrictive recovery record (migration-policy-recovery.json, '
                        'or the one-time all-on migration\'s owner-defaults-20261025-recovery.json), never a full state backup')
    parser.add_argument('--apply', action='store_true', help='Write offline under the existing runtime lock')
    parser.add_argument('--expected-sha256', help='Required with --apply: source_sha256 from reviewed dry run')
    parser.add_argument('--save-recovery', type=Path, help='Dry run only: save policy in an existing protected directory')
    args = parser.parse_args(argv)
    if args.apply and (not args.expected_sha256 or args.save_recovery):
        parser.error('--apply requires --expected-sha256 and cannot use --save-recovery')
    if not args.apply and args.expected_sha256:
        parser.error('--expected-sha256 is only used with --apply')
    if args.restore_policy and args.save_recovery:
        parser.error('--save-recovery requires --policy')
    try:
        if args.apply:
            if args.restore_policy:
                report = apply_restore(args.directory, args.product, args.restore_policy,
                                       expected_sha256=args.expected_sha256)
            else:
                report = apply_migration(args.directory, args.product, policy=args.policy,
                                         expected_sha256=args.expected_sha256)
        else:
            source = read_document(args.directory / 'state.json')
            plan = (plan_restore(source, args.product, read_document(args.restore_policy)) if args.restore_policy else
                    plan_migration(source, args.product, policy=args.policy))
            if args.save_recovery:
                save_recovery(args.save_recovery, plan)
            report = plan.report
    except MigrationError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({'dry_run': not args.apply, **report}, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
