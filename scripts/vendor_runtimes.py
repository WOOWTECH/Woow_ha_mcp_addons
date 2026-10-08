"""Explicit runtime-only acquisition. No repository checkout or deployment/config reads."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
LEGACY = Path('/data/pi-agent/home/woow-repos/WOOW/woow-mcp-server')
SOURCES = {
    'hermes': ('local:614ae663fadd91c76972f60017a76d2627bea87e', ['hermes_mcp_server/server.py']),
    'opendesign': ('local:614ae663fadd91c76972f60017a76d2627bea87e', ['opendesign_mcp_server/od_mcp_server.py']),
    'emqx': ('WOOWTECH/Woow_emqx_mcp_server/1be17bad5aef6c7b7519686ccbfe1d80762bc10e', [
        'emqx_mcp_server/' + p + '.py' for p in ['__init__', 'server', 'settings', 'lifespan', 'gating', 'registry', 'errors', 'deps', 'models', 'tools/__init__', 'tools/_common', 'tools/cluster', 'tools/clients', 'tools/topics', 'tools/messaging', 'tools/security', 'tools/diagnostics', 'tools/integration']]),
    'litellm': ('WOOWTECH/Woow_litellm_mcp_server/4d4190369216a2d068d1100d53406a67a1d81609', [
        'woow_litellm_mcp_server/' + p + '.py' for p in ['__init__', 'server', 'settings', 'lifespan', 'gating', 'registry', 'errors', 'deps', 'middleware', 'tools/__init__', 'tools/_common', 'tools/models', 'tools/chat', 'tools/keys', 'tools/teams', 'tools/users', 'tools/spend', 'tools/health', 'tools/plugins']]),
    # Tag v0.1.0. The package lives under src/ upstream (SOURCE_PREFIX); LICENSE is at the repository root.
    'nextcloud': ('WOOWTECH/Woow_nextcloud_mcp_server/1f94258bbfaa92f2693c60e7905c86ef2efb711a', [
        'nextcloud_mcp_server/' + p + '.py' for p in ['__init__', 'server', 'settings', 'client', 'errors', 'paths', 'webdav', 'caldav', 'ical', 'tools']]),
}
SOURCE_PREFIX = {'nextcloud': 'src/'}

def fetch(product, path):
    source, _ = SOURCES[product]
    upstream = path if path == 'LICENSE' else SOURCE_PREFIX.get(product, '') + path
    with urlopen('https://raw.githubusercontent.com/' + source + '/' + upstream, timeout=30) as response:
        return response.read()


def stage(product, directory):
    """Re-acquisition of ONE public product into an empty staging directory (never apps/ or provenance): the
    reviewer ports the recorded local changes onto the staged upstream files, then replaces the vendor tree and
    the product's runtime-sources.json records. Prints the new upstream records."""
    source, paths = SOURCES[product]
    assert not source.startswith('local:'), 'staging is for public sources only'
    directory = Path(directory)
    if directory.exists() and any(directory.iterdir()):
        raise SystemExit('staging directory must be empty')
    records = []
    for path in [*paths, 'LICENSE']:
        data = fetch(product, path)
        dest = directory / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        records.append({'product': product, 'source': source, 'path': path, 'upstream_sha256': hashlib.sha256(data).hexdigest()})
    print(json.dumps(records, indent=2))


if __name__ == '__main__':
    import sys
    if sys.argv[1:2] == ['--stage']:
        # python scripts/vendor_runtimes.py --stage <product> <empty directory>
        stage(sys.argv[2], sys.argv[3])
        raise SystemExit(0)
    # Never overwrite reviewed local hardening or provenance during re-acquisition.
    if any((ROOT / 'apps' / product / 'vendor').exists() for product in SOURCES):
        raise SystemExit('vendor directories already exist; review updates in a separate staging tree')
    import subprocess
    assert subprocess.check_output(['git', '-C', str(LEGACY), 'rev-parse', 'HEAD'], text=True).strip() == '614ae663fadd91c76972f60017a76d2627bea87e'
    records = []
    for product, (source, paths) in SOURCES.items():
        for path in [*paths, 'LICENSE']:
            if source.startswith('local:'):
                data = (LEGACY / 'apps' / product / path).read_bytes()
            else:
                data = fetch(product, path)
            dest = ROOT / 'apps' / product / 'vendor' / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            records.append({'product': product, 'source': source, 'path': path, 'upstream_sha256': hashlib.sha256(data).hexdigest()})
    (ROOT / 'docs/provenance/runtime-sources.json').write_text(json.dumps(records, indent=2) + '\n')
