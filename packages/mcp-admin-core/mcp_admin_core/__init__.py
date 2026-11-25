"""New HA boundary adaptation. Publication/license clearance remains pending."""

# The default release version; packaging/validate.py binds each fixed per-product
# override (Odoo, EMQX, LiteLLM, Nextcloud, Headscale) to its manifest, Docker label and build/publish tag.
VERSION = '0.4.15'
PRODUCT_VERSIONS = {'odoo': '0.5.2', 'emqx': '0.5.1', 'litellm': '0.5.1', 'nextcloud': '0.5.1', 'headscale': '0.4.20'}


def version_for_product(product: str) -> str:
    return PRODUCT_VERSIONS.get(product, VERSION)
