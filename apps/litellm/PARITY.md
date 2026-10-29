# LiteLLM product contract alignment

## Gateway base URL

Normalize trailing slashes and only an exact origin-root `/v1` API suffix.
`https://host/v1/` becomes `https://host`; `/v1/models` is then requested once.
`https://host/proxy/v1/` becomes `https://host/proxy/v1`; the model route is
`/proxy/v1/v1/models` because `/proxy/v1` is the reverse-proxy mount. `/V1` and
percent-encoded mount names are preserved. Do not guess which part of a longer
path belongs to a proxy. Existing generic URL guards remain in force.

The HA change in shared `products.py` is limited to `LiteLLMConnection.url`'s
product validator. It normalizes the model used by persistence, child environment
and connection probes. The vendored child Settings independently applies the
same rule to standalone environment configuration. No shared URL helper, other
product, state schema or version changes.

Main's UI/connection integration should use the model-returned value and explain
the exact-root rule; it must not strip every path ending in `/v1`. Existing
persisted bytes are not rewritten at startup by this patch. The standalone
child now rejects credential-bearing/query/fragment URLs before HTTP, matching
HA's existing connection boundary. Prefixed mounts need to be configured as
the actual gateway root, not as an OpenAI endpoint URL.

Tests use source models and actual HTTPX request composition with MockTransport;
they do not prove a deployed reverse proxy or live LiteLLM service.
