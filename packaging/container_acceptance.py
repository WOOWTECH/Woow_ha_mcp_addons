"""Host-side Docker gate. This command MUST fail when Docker/build is unavailable."""
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys

from validate import version_for

INPUTS = json.loads((Path(__file__).resolve().parent / 'inputs.json').read_text())
PRODUCTS = tuple(INPUTS['products'])  # 0.1.5: the store products; the retired odoo-manage is refused
# Multi-profile HM-16: the product switch of the source the candidate is built from (supply_chain.candidate checks the
# image's revision label against this checkout's HEAD), read as the probe reads the image's own copy.
CORE = Path(__file__).resolve().parents[1] / 'packages/mcp-admin-core'
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))
from mcp_admin_core import features  # noqa: E402
PROBE_SECONDS = 180
# A switched-on candidate also runs the probe's multi-profile stage (container_profiles.stage: two more starts, three
# children, a watchdog restart and a restore), after the single-profile path every candidate runs.
MULTI_PROFILE_PROBE_SECONDS = 360


def main(app, image, expected_id=None):
    if app not in PRODUCTS or image != f'local/mcp-{app}:{version_for(app)}':
        raise SystemExit('fixed image/app allowlist required')
    metadata = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image]))[0]
    assert metadata['Architecture'] == 'amd64' and metadata['Os'] == 'linux'
    if expected_id is not None:
        assert metadata['Id'] == expected_id, 'image changed before acceptance'
    labels = metadata['Config']['Labels']
    for key, value in {'io.hass.type': 'app', 'io.hass.arch': 'amd64',
                       'io.hass.version': version_for(app)}.items():
        assert labels.get(key) == value, key
    assert set(metadata['Config'].get('ExposedPorts', {})) == {'8081/tcp'}
    assert metadata['Config']['Entrypoint'] == ['/usr/local/bin/python', '/opt/woow/packaging/entrypoint.py', app]
    probe = Path(__file__).resolve().parent
    network = 'none'
    created_network = None
    switched = features.enabled(app)
    try:
        if app == 'headscale' or switched:
            # The Headscale child deliberately rejects loopback upstreams, and
            # so does every child of a switched-on product (multi-profile HM-20;
            # HM-16). Give its owned mock a non-loopback address, with no
            # external route and no other container on this one-use internal
            # bridge (container_probe.mock_bind_host).
            created_network = subprocess.check_output(
                ['docker', 'network', 'create', '--internal', '--driver', 'bridge',
                 f'woow-{app}-candidate-' + secrets.token_hex(8)], text=True, timeout=30).strip()
            assert re.fullmatch(r'[0-9a-f]{64}', created_network), 'invalid private network ID'
            private = json.loads(subprocess.check_output(
                ['docker', 'network', 'inspect', created_network], timeout=30))[0]
            assert (private['Id'] == created_network and private['Internal'] is True
                    and private['Driver'] == 'bridge' and not private['Containers']), 'mock network not isolated'
            network = created_network
        subprocess.run(['docker', 'run', '--rm', '--init', '--network', network, '--read-only',
            '--tmpfs', '/data:rw,nosuid,nodev,mode=0755', '--tmpfs', '/tmp:rw,nosuid,nodev,mode=1777',
            '--mount', f'type=bind,source={probe},target=/probe-package,readonly',
            '--entrypoint', '/opt/woow/.venv/bin/python', metadata['Id'], '/probe-package/container_probe.py', app], check=True,
            timeout=MULTI_PROFILE_PROBE_SECONDS if switched else PROBE_SECONDS)
    finally:
        if created_network:
            subprocess.run(['docker', 'network', 'rm', created_network], check=True, timeout=30)
    checked = 'labels/isolation/bootstrap/uid/protocol/auth/policy/outage/persistence/shutdown' + ('/multi-profile' if switched else '')
    print(f'PASS container/mock {app}: {checked}; NOT HA E2E')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('usage: container_acceptance.py APP local/mcp-APP:<reviewed version>')
    main(*sys.argv[1:])
