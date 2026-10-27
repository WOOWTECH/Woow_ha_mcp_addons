"""Owner decision 2026-10-27: a legacy installation is switched to full defaults once, on its first start.

The HA twin of the PaaS woow-mcp-server owner_defaults (2026-10-25 "every MCP on by default"). Every runtime
(run_product.py, apps/n8n/run.py) calls apply_legacy_upgrade before it constructs ProductStore or starts a child:

- **Legacy state (schema 1/2/3, written by 0.1.x or by the 2026-10-03 prototypes):** under the existing writer lock,
  the state is validated and replaced by exactly the all_on plan the 0.3.0-0.4.1 upgrade review applied (schema 4,
  writes on, every write grant, no disabled tool, no operation deny; token, child token, endpoint and backend kept),
  with the marker ``owner_defaults_20261025 = {applied, at, from_schema}`` in the same atomic state write. Before
  that write, the legacy policy itself is saved once as the format 2 recovery record
  ``owner-defaults-20261025-recovery.json`` (0600, policy only; published complete or not at all, so a failed or
  interrupted attempt never leaves a partial record that blocks the next start). MCP then starts normally: no
  review stage, no 503.
- **Schema 4 (new installations, everything 0.2.0+ wrote, states the review page migrated):** not touched at all.
  What an administrator chose in the panel stays as it is.
- **No state:** ProductStore seeds a new all-on state as before (no marker).
- **Unreadable, invalid or unsafe state, a busy writer, a recovery record that cannot be saved, or an existing record
  that is not this state's:** nothing is migrated or rewritten (fail-safe); the add-on log says which (fixed text).
  The runtime stops with "runtime unavailable; local recovery required".

The panel then shows a notice (view) with the time and the differences, and offers "restore the pre-upgrade limits"
(restore: migration.plan_owner_restore, faithful to the legacy policy) or "keep everything on" (dismiss). Either is
recorded in the marker and ends the notice.
"""
from __future__ import annotations

from pathlib import Path
import sys

from .config import ConfigError
from .migration import (OWNER_RECOVERY, MigrationError, RecordConflict, RecordNotSaved, _existing_writer,
                        owner_legacy_policy, owner_record, owner_upgrade_summary, plan_migration, plan_owner_restore,
                        read_document, save_owner_record, utc_now, POLICY_FIELDS)
from .products import OWNER_DEFAULTS, ProductState

DECISION = '2026-10-25'
LOG_PREFIX = 'owner defaults 2026-10-25'


class Unavailable(Exception):
    """The requested notice action cannot be applied (no marker, already done, or no valid recovery record)."""


def _log(text):
    # The add-on log (stdout/stderr) is what an HA administrator sees: fixed text only, never a value from state.
    print(f'{LOG_PREFIX}: {text}', file=sys.stderr, flush=True)


def apply_legacy_upgrade(directory, product):
    """The one-time all-on migration of a legacy state, before ProductStore. Returns its report, or None.

    Raises ConfigError, having changed nothing, when a present state cannot be validated or migrated safely.
    """
    path = Path(directory) / 'state.json'
    if not path.exists() and not path.is_symlink():
        return None  # new installation: ProductStore seeds the all-on defaults
    try:
        # Validate before any lock or write; a schema 4 state is never opened for writing here.
        if plan_migration(read_document(path), product, policy='all_on').report['source_schema'] >= 4:
            return None
        with _existing_writer(directory) as writer:
            report = migrate_locked(writer, product)
    except RecordConflict:
        # Names the one file to check; nothing from it or from the state is logged.
        _log(f'{OWNER_RECOVERY} already exists but is not the complete recovery record of this state.json '
             '(incomplete, damaged or from another state); nothing was migrated or rewritten. Restore the add-on '
             'backup taken before the update, or check that file and move it out of the data directory')
        raise ConfigError('legacy upgrade unavailable; inspect protected state') from None
    except RecordNotSaved:
        _log(f'{OWNER_RECOVERY} could not be saved (disk full or I/O error); nothing was migrated or rewritten and no '
             'partial record was left; free space and restart the add-on')
        raise ConfigError('legacy upgrade unavailable; inspect protected state') from None
    except MigrationError:
        _log('state.json is unreadable, invalid, linked or in use, or its recovery record cannot be saved; '
             'nothing was migrated or rewritten')
        raise ConfigError('legacy upgrade unavailable; inspect protected state') from None
    if report is not None:
        _log(f'the schema {report["source_schema"]} state was switched once to schema 4 with every tool and write on; '
             f'its previous limits are kept in {OWNER_RECOVERY} and can be restored from the add-on panel')
    return report


def migrate_locked(writer, product, *, at=None):
    """Under the existing writer's lock: record, then one atomic state write with the marker."""
    if writer._lock_fd is None or writer._poisoned:
        raise MigrationError('migration writer unavailable')
    value = read_document(writer.path)
    plan = plan_migration(value, product, policy='all_on')
    version = plan.report['source_schema']
    if version >= 4:
        return None
    # The legacy policy is durable before the state changes; an identical record of an interrupted attempt is reused.
    save_owner_record(writer.directory / OWNER_RECOVERY, owner_record(value, product))
    marker = {'applied': 'migrated', 'at': at or utc_now(), 'from_schema': version}
    try:
        state = ProductState.model_validate({**plan.state.model_dump(), OWNER_DEFAULTS: marker})
    except (ValueError, TypeError):
        # Fixed text only: a validation error would quote the state (tokens, credentials).
        raise MigrationError('migrated state invalid; state unchanged, recovery record retained') from None
    try:
        writer._write(state)
    except ConfigError:
        raise MigrationError('durable migration write failed; recovery record retained; inspect state') from None
    return {**plan.report, 'marker': marker}


def _record(directory, product):
    """(record, status): status 'available', 'missing' or 'invalid'."""
    path = Path(directory) / OWNER_RECOVERY
    if not path.exists() and not path.is_symlink():
        return None, 'missing'
    try:
        record = read_document(path)
        owner_legacy_policy(record, product)
    except MigrationError:
        return None, 'invalid'
    return record, 'available'


def view(state, directory):
    """The panel's notice data (names and times only; no token, backend or digest), or None without a marker."""
    marker = getattr(state, OWNER_DEFAULTS, None)
    if marker is None:
        return None
    pending = marker.restored_at is None and marker.acknowledged_at is None
    result = {'decision': DECISION, 'applied': marker.applied, 'at': marker.at, 'from_schema': marker.from_schema,
              'restored_at': marker.restored_at, 'acknowledged_at': marker.acknowledged_at,
              'recovery': 'missing', 'upgrade': None, 'restore': None}
    record, result['recovery'] = _record(directory, state.product)
    if record is not None:
        try:
            plan = plan_owner_restore(state.model_dump(), state.product, record)
        except MigrationError:
            result['recovery'] = 'invalid'
        else:
            result['upgrade'] = owner_upgrade_summary(state.product, owner_legacy_policy(record, state.product))
            report = plan.report
            result['restore'] = {key: report[key] for key in (
                'disabled_added', 'write_grants_removed', 'operation_denies_added', 'writes_enabled',
                'kept_new_tools', 'kept_new_write_operations', 'policy_changed')}
            result['restore']['available'] = marker.restored_at is None and report['policy_changed']
    # Shown until the administrator restores or keeps the defaults; a migration that changed nothing needs no notice.
    result['notice'] = pending and (result['upgrade'] is None or result['upgrade']['changed'])
    return result


def restore(store, *, at=None):
    """Apply the faithful pre-upgrade limits (restrictive merge) and record restored_at. Returns the new state."""
    state = store.load()
    marker = getattr(state, OWNER_DEFAULTS, None)
    if marker is None or marker.restored_at is not None:
        raise Unavailable()
    record, status = _record(store.directory, state.product)
    if record is None:
        raise Unavailable()
    try:
        plan = plan_owner_restore(state.model_dump(), state.product, record, at=at or utc_now())
    except MigrationError:
        raise Unavailable() from None
    changes = {key: getattr(plan.state, key) for key in POLICY_FIELDS}
    changes[OWNER_DEFAULTS] = getattr(plan.state, OWNER_DEFAULTS)
    return store.update(**changes)


def dismiss(store, *, at=None):
    """Keep everything on: record acknowledged_at (the notice ends; restore stays possible). Returns the new state."""
    state = store.load()
    marker = getattr(state, OWNER_DEFAULTS, None)
    if marker is None or marker.restored_at is not None or marker.acknowledged_at is not None:
        raise Unavailable()
    return store.update(**{OWNER_DEFAULTS: {**marker.model_dump(), 'acknowledged_at': at or utc_now()}})
