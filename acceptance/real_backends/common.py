"""Owned fixtures only. Credentials stay in cluster Secrets and process memory."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess

if not __debug__:
    raise RuntimeError('acceptance ownership checks require Python without -O')

os.umask(0o077)
ROOT = Path(__file__).resolve().parent
LANE = Path(os.environ.get('BACKEND_EVIDENCE_DIR', '/data/pi-agent/home/work/mcp-parity-finalization-20261030/lanes/backends'))
E = LANE / 'evidence'
K = ['kubectl', '--context', os.environ.get('BACKEND_CONTEXT', 'woow-k3s')]
IMAGES = json.loads((ROOT / 'images.json').read_text())
NS = os.environ.get('BACKEND_NAMESPACE', 'mcp-real-backends-20261030')
NODE = os.environ.get('BACKEND_NODE', 'ubuntuserver-31zix')
PY = '/opt/woow/.venv/bin/python'

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def save(name, value):
    E.mkdir(parents=True, exist_ok=True)
    p = E / name
    with p.open('x') as f: json.dump(value, f, indent=2); f.write('\n')
def command(args, data=None, timeout=90):
    p = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError('command_failed:' + args[0] + ':' + str(p.returncode))
    return p.stdout
def get(kind, name, namespace=None):
    out = command(K + (['-n', namespace] if namespace else []) + ['get', kind, name, '--ignore-not-found', '-o', 'json'])
    return json.loads(out) if out.strip() else None
def config(): return json.loads((LANE/'run.json').read_text())
def guard():
    c = config(); n = get('namespace', NS)
    assert n and n['metadata']['uid'] == c['namespace_uid']
    assert n['metadata']['labels'].get('acceptance.woowtech.io/run') == c['run']
    return c
def apply(items):
    guard()
    return command(K + ['apply', '-f', '-'], json.dumps({'apiVersion':'v1','kind':'List','items':items}).encode())
def exec_code(family, container, code, python=None, timeout=180):
    guard()
    return command(K + ['-n', NS, 'exec', '-i', family, '-c', container, '--', python or (PY if container == 'ha' else 'python3'), '-'], code.encode(), timeout)
def digest(data): return hashlib.sha256(data).hexdigest()
