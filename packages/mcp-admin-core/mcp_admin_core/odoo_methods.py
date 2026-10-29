"""Bounded exact Odoo model.method settings; no execution-policy overrides."""
import json
import re
from typing import Annotated

from pydantic import BeforeValidator


FIELD = 'odoo_allowed_methods'
ROUTE = 'odoo/allowed-methods'
MAX_METHODS = 128
MAX_ENTRY_LENGTH = 256
MAX_BYTES = 16384
# Match the pinned child's technical model grammar; methods must be public.
EXACT_METHOD = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\.[A-Za-z][A-Za-z0-9_]*')


def validate_methods(value):
    """Reject malformed/duplicate entries without silently normalizing names."""
    if (not isinstance(value, list) or len(value) > MAX_METHODS
            or any(not isinstance(item, str) or len(item) > MAX_ENTRY_LENGTH
                   or not EXACT_METHOD.fullmatch(item) for item in value)
            or len(set(value)) != len(value)
            or len(json.dumps(value, separators=(',', ':'))) > MAX_BYTES):
        raise ValueError('invalid Odoo allowed methods')
    return list(value)


AllowedMethods = Annotated[list[str], BeforeValidator(validate_methods)]


def changes(state, value):
    """Validate only this Odoo setting before the gateway's final role check."""
    if getattr(state, 'product', None) != 'odoo' or not isinstance(value, dict) or set(value) != {FIELD}:
        raise ValueError('invalid Odoo allowed methods update')
    return {FIELD: validate_methods(value[FIELD])}


def bootstrap(state):
    """Expose the effective list only; no connection or child credentials."""
    if getattr(state, 'product', None) != 'odoo':
        return {}
    return {FIELD: list(state.odoo_allowed_methods or []),
            FIELD + '_source': 'saved' if state.odoo_allowed_methods is not None else 'legacy_empty'}
