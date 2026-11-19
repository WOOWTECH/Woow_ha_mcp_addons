"""The multi-profile switch of one test's product, pinned off (multi-profile plan 3.3, 7.4; HM-26).

A test of the add-on as it serves a product that is not switched on (HM-01's golden regression and both contract
freezes, the switched-off runtime, a child spec snapshot, the single-profile real runtime) relied on the repository's
switch leaving its product out. Once a product's release adds it to features.MULTI_PROFILE_PRODUCTS, such a test would
run that product switched on and fail for what it does not test (X-MCP-Profile and the profile echo on 8099,
WOOW_MCP_DENY_LOOPBACK, the health tolerance), or pass for another reason than its own. Pinning the product off keeps
these tests proving the switched-off add-on after that release: switching a product off again is a release too (plan
7.4), and its answers are these.

- switched_off: a fixture for a test with a 'product' parameter; the switch without that product for the test (every
  other product as the repository has it). It acts only for the test pytest runs: a test that calls such a test function
  itself (tests/test_router_passthrough.py runs them again inside multi_profile_runtime.switched_on) gets the switch it
  set there.
- off(product): the same as a context manager, for a test whose parameters differ or that needs it for one block.
- preamble(product): the same for a subprocess, as code to run first (features.enabled is read at every call:
  tests/test_upgrade_zero_rewrite.py).
"""
from contextlib import contextmanager

import pytest

from mcp_admin_core import features


def without(product):
    """The switch with *product* left out (an unknown product is an error, as for features.enabled)."""
    features.enabled(product)
    return features.MULTI_PROFILE_PRODUCTS - {product}


@contextmanager
def off(product):
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(features, 'MULTI_PROFILE_PRODUCTS', without(product))
        yield


@pytest.fixture
def switched_off(request):
    """The test's product (its 'product' parameter) switched off for the test."""
    product = request.getfixturevalue('product')
    with off(product):
        yield product


def preamble(product):
    """Code that switches *product* off in a subprocess before anything else runs."""
    features.enabled(product)
    return ('from mcp_admin_core import features; '
            f'features.MULTI_PROFILE_PRODUCTS = features.MULTI_PROFILE_PRODUCTS - {{{product!r}}}; ')
