"""Per-product multi-profile switch (multi-profile plan §3.3, DQ-32 (a); HM-07: defined, not wired yet).

A product is switched on only by its own upgrade PR, which the owner approves and merges: switching one off again
is a release too (a higher version), never a runtime toggle. Code asks enabled(product) every time it decides,
and never keeps a copy of MULTI_PROFILE_PRODUCTS taken at import time, so a test can switch a product on in a
subprocess preamble (tests/test_upgrade_zero_rewrite.py).

What the switch governs (the dispatcher on 8081, the profile management API, the panel) and what runs whatever it
says (log redaction, the child bearer, the restore marker and guard, the dormant-profile revocation) is listed in
the plan §3.3 and docs/multi-profile/contract.md §1.2.
"""
from __future__ import annotations

# The products of products.Product (the n8n adapter included).
KNOWN_PRODUCTS = frozenset({'n8n', 'odoo', 'odoo-manage', 'hermes', 'opendesign', 'emqx', 'litellm', 'nextcloud',
                            'headscale'})

# No product has additional profiles yet. OpenDesign and Odoo Manage never will (DQ-28; profiles.supports_profiles).
MULTI_PROFILE_PRODUCTS: frozenset[str] = frozenset()


def enabled(product: str) -> bool:
    """Whether *product* serves additional profiles; reads the switch at every call. An unknown name is an error,
    never a silent "off"."""
    if product not in KNOWN_PRODUCTS:
        raise ValueError('unknown product')
    return product in MULTI_PROFILE_PRODUCTS
