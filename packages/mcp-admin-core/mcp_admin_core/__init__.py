"""New HA boundary adaptation. Publication/license clearance remains pending."""

# The default release version; packaging/validate.py binds the fixed Headscale
# override to its manifest, Docker label and build/publish tag.
VERSION = '0.4.13'
PRODUCT_VERSIONS = {'headscale': '0.4.14'}


def version_for_product(product: str) -> str:
    return PRODUCT_VERSIONS.get(product, VERSION)
