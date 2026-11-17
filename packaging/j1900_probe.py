#!/usr/bin/env python3
"""J1900 instruction-set probe. Runs INSIDE a candidate image, natively and under
`qemu-x86_64-static -cpu Nehalem` (QEMU user mode; the 0.1.7 record calls Nehalem stricter than the J1900: Nehalem has
no AVX, AVX2, MOVBE or AES-NI), started by packaging/j1900_check.py. Standard library only: it runs on the image's own
Python, never on the runner's.

  list              print every native extension module this interpreter can see as one JSON object:
                    {"lib-dynload": [...], "site-packages": [...]} (the interpreter's own C modules, and the
                    installed packages' ones from site-packages and dist-packages)
  import FILE       import every module named in FILE (JSON list), one by one; print TRY/OK/ERR
                    lines and finally {"ok": [...], "err": {name: exception type}, "detail": {name:
                    "Type: message", at most 300 characters on one line}}; a SIGILL kills the process, so
                    the last TRY line names the culprit
  smoke             a few deterministic computations through C code (hashlib, ssl, zlib, sqlite3,
                    json, decimal, re) printed as one JSON object

Provenance: ported from artifacts/ha-multiprofile-parity-20261114/wave4/release-0.4.14-builder/j1900_probe.py
(written for the dropped k3s builder, never run there); changed: `list` groups the modules by where they live, so the
check can require a third-party one (review M1). docs/operations/release-decision-0.1.7.md (0.1.8 to-do) records
that the 0.1.7 images passed "QEMU user-mode -cpu Nehalem" in the Claude delivery lane j1900-isa-check-1009/ and that
every release should repeat it (DQ-42, owner 2026-11-17: every release); that lane's script is not available, so this
re-implements the described method. Limit: QEMU checks only the code that actually runs (the imports and the smoke).
"""
import importlib
import json
from pathlib import Path
import sys

SUFFIXES = ('.so',)
SKIP_PARTS = ('tests', 'test', '__pycache__')


def module_name(root, path, suffixes=SUFFIXES):
    rel = Path(path).relative_to(root)
    parts = list(rel.parts)
    stem = parts[-1]
    for suffix in suffixes:
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]
            break
    else:
        return None
    stem = stem.split('.')[0]  # drop .cpython-313-x86_64-linux-gnu / .abi3 tags
    parts[-1] = stem
    if any(p in SKIP_PARTS for p in parts[:-1]):
        return None
    if not all(p.isidentifier() for p in parts):  # vendored libs (*.libs/libfoo-1.so.1), not modules
        return None
    if parts[-1] == '__init__':
        parts = parts[:-1]
    return '.'.join(parts) if parts else None


def roots(paths=None):
    found = []
    for entry in (paths if paths is not None else sys.path):
        p = Path(entry)
        if p.is_dir() and (p.name in ('site-packages', 'dist-packages', 'lib-dynload')):
            found.append(p)
    return found


def native_modules(paths=None, suffixes=SUFFIXES):
    names = set()
    for found in modules_by_root(paths, suffixes).values():
        names.update(found)
    return sorted(names)


def modules_by_root(paths=None, suffixes=SUFFIXES):
    """{'lib-dynload': [...], 'site-packages': [...]}: dist-packages counts as site-packages (installed packages)."""
    found = {'lib-dynload': set(), 'site-packages': set()}
    for root in roots(paths):
        kind = 'lib-dynload' if root.name == 'lib-dynload' else 'site-packages'
        for path in root.rglob('*'):
            if path.is_file():
                name = module_name(root, path, suffixes)
                if name:
                    found[kind].add(name)
    return {kind: sorted(names) for kind, names in found.items()}


DETAIL = 300


def import_all(names, emit=print):
    ok, err, detail = [], {}, {}
    for name in names:
        emit('TRY ' + name)
        sys.stdout.flush()
        try:
            importlib.import_module(name)
        except BaseException as e:  # noqa: B036 - SystemExit from a module is an error here, not an exit
            err[name] = type(e).__name__
            # The allowlist can require a known cause (packaging/j1900-allowlist.json error_contains).
            detail[name] = ' '.join(('%s: %s' % (type(e).__name__, e)).split())[:DETAIL]
            emit('ERR %s %s' % (name, type(e).__name__))
        else:
            ok.append(name)
            emit('OK ' + name)
    return {'ok': ok, 'err': err, 'detail': detail}


def smoke():
    import decimal
    import hashlib
    import re
    import sqlite3
    import ssl
    import zlib
    data = b'j1900-nehalem' * 4096
    db = sqlite3.connect(':memory:')
    db.execute('create table t (a text)')
    db.executemany('insert into t values (?)', [('row %d' % i,) for i in range(200)])
    count = db.execute("select count(*) from t where a like 'row 1%'").fetchone()[0]
    ctx = ssl.create_default_context()
    decimal.getcontext().prec = 50
    return {'sha256': hashlib.sha256(data).hexdigest(), 'blake2b': hashlib.blake2b(data).hexdigest(),
            'sha3': hashlib.sha3_256(data).hexdigest(), 'zlib': zlib.crc32(zlib.compress(data, 9)),
            'sqlite': count, 'ssl_verify': ctx.verify_mode == ssl.CERT_REQUIRED,
            'decimal': str(decimal.Decimal(2).sqrt()), 'json': json.dumps({'a': [1, 2.5, None]}),
            're': len(re.findall(rb'nehalem', data))}


def main(argv):
    if argv == ['list']:
        print(json.dumps(modules_by_root()))
        return 0
    if len(argv) == 2 and argv[0] == 'import':
        names = json.loads(Path(argv[1]).read_text())
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise SystemExit('module list must be a JSON list of names')
        print(json.dumps(import_all(names)), flush=True)
        return 0
    if argv == ['smoke']:
        print(json.dumps(smoke(), sort_keys=True))
        return 0
    raise SystemExit('usage: j1900_probe.py list | import FILE | smoke')


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
