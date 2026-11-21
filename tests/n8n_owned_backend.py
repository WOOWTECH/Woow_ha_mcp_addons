"""Route the strict-policy-approved test origin to the owned fake listener."""
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit


def origin(url):
    parsed = urlsplit(url)
    assert parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port
    return f'http://8.8.8.8:{parsed.port}'


def route(spec, url):
    port = urlsplit(url).port
    preload = Path(__file__).with_name('n8n_strict_owned_backend.cjs').resolve()
    return replace(spec, env={**spec.env, 'OWNED_N8N_BACKEND_PORT': str(port),
                              'NODE_OPTIONS': f'--require={preload}'})
