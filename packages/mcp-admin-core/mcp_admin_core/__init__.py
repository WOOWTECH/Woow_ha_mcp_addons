"""New HA boundary adaptation. Publication/license clearance remains pending."""

# The default release version; packaging/validate.py binds each fixed per-product
# override (Odoo, Headscale) to its manifest, Docker label and build/publish tag.
VERSION = '0.4.14'
PRODUCT_VERSIONS = {'odoo': '0.5.0', 'headscale': '0.4.19'}


def version_for_product(product: str) -> str:
    return PRODUCT_VERSIONS.get(product, VERSION)
