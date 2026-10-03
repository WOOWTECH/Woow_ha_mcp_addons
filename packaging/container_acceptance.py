"""Host-side Docker gate. This command MUST fail when Docker/build is unavailable."""
import json
from pathlib import Path
import subprocess
import sys

PRODUCTS = ('odoo', 'odoo-manage', 'n8n', 'hermes', 'opendesign', 'emqx', 'litellm')


def main(app, image, expected_id=None):
    if app not in PRODUCTS or image != f'local/mcp-{app}:0.1.0':
        raise SystemExit('fixed image/app allowlist required')
    metadata = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image]))[0]
    assert metadata['Architecture'] == 'amd64' and metadata['Os'] == 'linux'
    if expected_id is not None:
        assert metadata['Id'] == expected_id, 'image changed before acceptance'
    labels = metadata['Config']['Labels']
    for key, value in {'io.hass.type': 'app', 'io.hass.arch': 'amd64', 'io.hass.version': '0.1.0'}.items():
        assert labels.get(key) == value, key
    assert set(metadata['Config'].get('ExposedPorts', {})) == {'8081/tcp'}
    assert metadata['Config']['Entrypoint'] == ['/usr/local/bin/python', '/opt/woow/packaging/entrypoint.py', app]
    probe = Path(__file__).resolve().parent
    subprocess.run(['docker', 'run', '--rm', '--init', '--network', 'none', '--read-only',
        '--tmpfs', '/data:rw,nosuid,nodev,mode=0755', '--tmpfs', '/tmp:rw,nosuid,nodev,mode=1777',
        '--mount', f'type=bind,source={probe},target=/probe-package,readonly',
        '--entrypoint', '/opt/woow/.venv/bin/python', metadata['Id'], '/probe-package/container_probe.py', app], check=True, timeout=180)
    print(f'PASS container/mock {app}: labels/isolation/bootstrap/uid/protocol/auth/policy/outage/persistence/shutdown; NOT HA E2E')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('usage: container_acceptance.py APP local/mcp-APP:0.1.0')
    main(*sys.argv[1:])
