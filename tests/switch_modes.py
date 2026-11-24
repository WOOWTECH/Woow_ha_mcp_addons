"""A test of one mode of the multi-profile switch names that mode itself (multi-profile plan 7.3, 12.0 point 5).

features.MULTI_PROFILE_PRODUCTS is the repository's switch: a product's version-bump PR adds it (DQ-32: switching a
product on is a release; Odoo from 0.5.0, HM-19a). A test written for the add-on with its product switched off (HM-01's
golden regression and contract freezes, the child spec snapshots, the single-profile runtime and its stand-ins, a real
child behind a loopback fake backend, which a switched-on product's child refuses: HM-20) keeps testing the same thing
once such a PR switches the product on, so it does not read the repository's switch: it asks for switched_off. A test of
the switched-on add-on switches its product on itself (tests/multi_profile_runtime.py: switched_on,
multi_profile_runtime; a subprocess preamble). The switched-off add-on is still what every other product ships, and what
a switched-on product goes back to with an emergency switch-off release (docs/operations/update-backup-rollback.md).

HM-19a found the tests that read the repository's switch by running the whole suite with Odoo switched on; the
same-named module of the EMQX and Headscale feature PRs (HM-23, HM-26) has the same fixture with the same meaning.

A subprocess a test starts reads the repository's switch, not this fixture's: its own preamble sets the switch it needs
(code a test runs with python -c), as tests/test_upgrade_zero_rewrite.py's preamble switches one on.
"""
import pytest

from mcp_admin_core import features


@pytest.fixture
def switched_off():
    """Every product switched off while the test runs, whatever the repository switches on. A test that switches a
    product on inside (switched_on, multi_profile_runtime, its own monkeypatch) still does: that comes after this."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset())
        yield
