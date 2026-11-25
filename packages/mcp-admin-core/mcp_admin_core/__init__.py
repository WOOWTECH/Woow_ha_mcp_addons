"""New HA boundary adaptation. Publication/license clearance remains pending."""

# The default release version; packaging/validate.py binds each fixed per-product
# override (every store product but the disabled OpenDesign, which keeps this default) to its manifest, Docker label and
# build/publish tag.
VERSION = '0.4.15'
PRODUCT_VERSIONS = {'odoo': '0.5.2', 'emqx': '0.5.1', 'litellm': '0.5.1', 'nextcloud': '0.5.1', 'headscale': '0.5.0',
                    'hermes': '0.5.0', 'n8n': '0.5.0'}


def version_for_product(product: str) -> str:
    return PRODUCT_VERSIONS.get(product, VERSION)
