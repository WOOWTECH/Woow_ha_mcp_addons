"""HM-23: a test of one mode of the multi-profile switch names that mode itself (multi-profile plan 7.3, 12.0 point 5).

features.MULTI_PROFILE_PRODUCTS is the repository's switch: empty until a product's version-bump PR adds the product
(DQ-32: switching a product on is a release). A test written for the add-on with its product switched off (HM-01's
golden regression and contract freezes, the child spec snapshots, the single-profile runtime and its stand-ins, a real
child behind a loopback fake backend, which a switched-on product's child refuses: HM-20) must test the same thing once
such a PR switches the product on, so it does not read the repository's switch: it asks for switched_off. A test of the
switched-on add-on switches its product on itself (tests/multi_profile_runtime.py: switched_on, multi_profile_runtime;
a subprocess preamble). Then a version-bump PR changes features.py and the release data only (plan 11.3), and each test
keeps testing what it tested. HM-23 found the tests that read the repository's switch by running the suite with EMQX
switched on (docs/provenance/ha-multiprofile-HM-23-20261119.md).

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
