"""HM-20 test double: lets a test's loopback fake backend through the loopback rule of a switched-on product.

What it replaces: products.loopback_refused, the one place that decides whether a product's backend URL may be
loopback, for the admin API's save check (products.check_saved_destinations) and for the child's environment
(products.child_spec and n8n_adapter.child_spec, which give a switched-on product's child WOOW_MCP_DENY_LOOPBACK=1). In
production it is features.enabled(product) and nothing else.

While it is on, a switched-on product saves a loopback URL and its child gets no WOOW_MCP_DENY_LOOPBACK: both behave as
for a product that is not switched on. The child's own refusal (apps/runtime/backend_policy.py,
apps/n8n/backend_policy.cjs) has no switch of its own: only that variable turns it on.

Who can turn it on: only code running inside the process that imported mcp_admin_core: a test (allowed() as a context
manager) or the preamble of a subprocess a test starts (install()). This file is in tests/, which no image copies
(apps/*/Dockerfile copy packages/mcp-admin-core, apps/ and two packaging files), and no runtime file imports it
(tests/test_backend_loopback.py checks both). No option, request, file or environment variable reaches it.
"""
from contextlib import contextmanager

from mcp_admin_core import features, products


def _double(product):
    features.enabled(product)  # an unknown product stays an error
    return False


def install():
    """For a subprocess preamble: on for the rest of that process."""
    products.loopback_refused = _double


@contextmanager
def allowed():
    """On inside the block; the production rule again after it, also when the block raises."""
    before = products.loopback_refused
    products.loopback_refused = _double
    try:
        yield
    finally:
        products.loopback_refused = before
