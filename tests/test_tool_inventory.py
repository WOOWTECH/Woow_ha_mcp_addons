"""All seven source inventories must stay synchronized; unknown remains denied."""
import ast
import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

from mcp_admin_core.config import State
from mcp_admin_core.policy import Denied, authorize

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('inventory', ROOT / 'scripts/tool_inventory.py')
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


def test_inventory_names_hashes_schema_and_documentation_do_not_drift():
    actual = inventory.build()
    expected = json.loads((ROOT / 'docs/tool-surface.json').read_text())
    assert actual == expected
    assert inventory.markdown(actual) == (ROOT / 'docs/tool-surface.md').read_text()
    assert {p: d['upstream_count'] for p, d in actual['products'].items()} == {
        'n8n': 28, 'odoo': 41, 'odoo-manage': 10, 'hermes': 11, 'opendesign': 15, 'emqx': 39, 'litellm': 40}


def test_all_withheld_tools_deny_even_when_writes_enabled():
    data = json.loads((ROOT / 'docs/tool-surface.json').read_text())
    state = State(token='a' * 43, child_token='b' * 43, writes_enabled=True)
    count = 0
    for product, group in data['products'].items():
        for tool in group['tools']:
            if tool['status'] == 'temporarily-unsupported':
                with pytest.raises(Denied):
                    authorize({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                               'params': {'name': tool['name'], 'arguments': {}}}, inventory.POLICIES[product], state)
                assert tool['reason'] and tool['enable'] and tool['source']
                count += 1
    assert count == 108  # 184 exact pinned tools, 76 bounded supported (+5 LiteLLM metadata reads).


def test_vendored_content_hashes_and_license_notices():
    import hashlib
    records = json.loads((ROOT / 'docs/provenance/runtime-sources.json').read_text())
    for record in records:
        path = ROOT / 'apps' / record['product'] / 'vendor' / record['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record.get('local_sha256', record['upstream_sha256'])
        if record.get('local_sha256'):
            assert record.get('modification')
    for product in ('hermes', 'opendesign', 'emqx', 'litellm'):
        assert 'MIT License' in (ROOT / 'apps' / product / 'vendor/LICENSE').read_text()


DIGEST = re.compile(r"""['"]([0-9a-f]{64})['"]""")


def digests(path):
    """Source-guard digests a patched file writes: Python string constants (adjacent literals already joined), or
    quoted 64-hex strings in other languages."""
    if path.suffix != '.py':
        return set(DIGEST.findall(path.read_text()))
    return {node.value for node in ast.walk(ast.parse(path.read_text())) if isinstance(node, ast.Constant)
            and isinstance(node.value, str) and re.fullmatch('[0-9a-f]{64}', node.value)}


# Dynamic loading this test resolves: argument index of a module name or of a file path (its stem is the module).
BY_NAME = {'import_module': 0, '__import__': 0, 'run_module': 0, 'find_spec': 0}
BY_PATH = {'run_path': 0, 'spec_from_file_location': 1, 'SourceFileLoader': 1}
REFUSED = {'exec', 'eval', 'compile', 'load_module', 'spec_from_loader', 'ModuleSpec'}  # nothing to resolve
FOLLOWS = {'exec_module'}  # runs a spec created by one of the resolved calls above
BUILTINS = {'__import__', 'exec', 'eval', 'compile'}  # only as bare names (re.compile is not a loader)
LOADERS = set(BY_NAME) | set(BY_PATH) | REFUSED | FOLLOWS


def imports(tree, where):
    """Top-level names a module imports: every import statement form in any block, and dynamic loads whose target
    is a constant (a module name, or a file path whose stem is the module). A load this cannot resolve fails the
    test (R2 #1): a non-constant target, exec/eval/compile and other loaders with nothing to resolve, a loader used
    without being called (aliasing), imported under another name, or named in a string (getattr)."""
    names = set()
    calls = {id(node.func): node for node in ast.walk(tree) if isinstance(node, ast.Call)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split('.')[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            if not node.level:
                names.add(node.module.split('.')[0])
            assert not any(a.name in LOADERS and a.asname for a in node.names), (where, node.lineno, 'renamed loader')
        elif isinstance(node, ast.Constant):
            assert node.value not in LOADERS, (where, node.lineno, 'loader named in a string')
        elif isinstance(node, (ast.Name, ast.Attribute)):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if name not in LOADERS or name in BUILTINS and not isinstance(node, ast.Name):
                continue
            call = calls.get(id(node))
            assert call is not None and name not in REFUSED, (where, node.lineno, 'unresolvable load: ' + name)
            if name in FOLLOWS:
                continue
            index = BY_NAME.get(name, BY_PATH.get(name))
            assert len(call.args) > index and isinstance(call.args[index], ast.Constant), (where, node.lineno, 'unresolvable load: ' + name)
            target = str(call.args[index].value)
            names.add(target.split('.')[0] if name in BY_NAME else Path(target).stem)
    return names


def app_sources(app):
    """Every Python file an app ships (launch.py, vendor/ and any other package), not venvs or node_modules."""
    for top, dirs, files in os.walk(app):
        dirs[:] = sorted(d for d in dirs if d not in ('.venv', 'node_modules', '__pycache__'))
        yield from (Path(top) / f for f in sorted(files) if f.endswith('.py'))


def guard_apps(patch, root=ROOT):
    """Apps whose processes run a patch's source guard. A shared apps/runtime module's guard runs in every app that
    imports it, directly or through another runtime module (R1 #4); bounded_tools' guard only where BoundedTools is
    built, which holds while its digests sit in BoundedTools.__init__ (asserted)."""
    if not patch.startswith('apps/runtime/'):
        return {patch.split('/')[1]}
    runtime = {p.stem: ast.parse(p.read_text()) for p in (root / 'apps/runtime').glob('*.py')}
    name = Path(patch).stem
    if name == 'bounded_tools':
        [init] = [f for c in runtime[name].body if isinstance(c, ast.ClassDef) and c.name == 'BoundedTools'
                  for f in c.body if isinstance(f, ast.FunctionDef) and f.name == '__init__']
        assert {n.value for n in ast.walk(init) if isinstance(n, ast.Constant)} >= digests(root / patch)
    apps = set()
    for app in (root / 'apps').iterdir():
        if app.name == 'runtime' or not app.is_dir():
            continue
        trees = [(f, ast.parse(f.read_text())) for f in app_sources(app)]
        loaded, todo = set(), [n for f, t in trees for n in imports(t, f) if n in runtime]
        while todo:
            if (module := todo.pop()) not in loaded:
                loaded.add(module)
                todo += [n for n in imports(runtime[module], module) if n in runtime]
        if name == 'bounded_tools':
            used = [t for _, t in trees] + [runtime[m] for m in loaded if m != name]
            if any(getattr(n, 'id', getattr(n, 'attr', getattr(n, 'name', getattr(n, 'value', None)))) == 'BoundedTools'
                   for t in used for n in ast.walk(t)):  # names, attributes, import aliases and getattr strings
                apps.add(app.name)
        elif name in loaded:
            apps.add(app.name)
    return apps


def test_runtime_patch_ledger_and_guarded_wheel_sources():
    import hashlib
    ledger = json.loads((ROOT / 'docs/provenance/runtime-patches.json').read_text())
    for patch in ledger['patches']:
        assert hashlib.sha256((ROOT / patch['path']).read_bytes()).hexdigest() == patch['sha256']
        assert patch['change']
        for path, expected in patch['guarded_sources'].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
        # 0.1.5 (0.1.4 re-review #5): every source-guard digest written in a patched file is listed for review,
        # in every app where that guard runs (the same file has the same digest in each venv).
        written = digests(ROOT / patch['path'])
        if written:
            apps = guard_apps(patch['path'])
            assert {path.split('/')[1] for path in patch['guarded_sources']} == apps, patch['path']
            for app in apps:
                listed = {digest for path, digest in patch['guarded_sources'].items() if path.startswith(f'apps/{app}/')}
                assert written <= listed, (patch['path'], app, sorted(written - listed))


def test_guard_apps_follow_imports_in_any_form(tmp_path):
    # R1 #4: the cases a text search missed: several names per import, odd spacing, imports inside blocks or after
    # a semicolon, constant dynamic imports and runtime modules importing each other.
    digest = "'" + 'a' * 64 + "'"
    files = {'apps/runtime/shared.py': 'CHECK = ' + digest + '\n', 'apps/runtime/via.py': 'import shared\n',
             'apps/runtime/bounded_tools.py': 'class OwnedWorkers:\n    pass\n\n\nclass BoundedTools(OwnedWorkers):\n'
                                              '    def __init__(self):\n        self.check = ' + digest + '\n',
             'apps/a/launch.py': 'import os, shared\n', 'apps/b/launch.py': 'try:\n    import  shared\nexcept ImportError:\n    pass\n',
             'apps/c/vendor/pkg/mod.py': 'x = 1; from via import y\n', 'apps/d/launch.py': 'import importlib\nimportlib.import_module("shared")\n',
             'apps/e/launch.py': 'import json  # shared, BoundedTools\n', 'apps/f/launch.py': 'from bounded_tools import OwnedWorkers\n',
             'apps/g/launch.py': 'import bounded_tools\nbounded_tools.BoundedTools()\n',
             'apps/i/launch.py': 'from bounded_tools import BoundedTools as Bounded\nBounded()\n'}
    for path, text in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    assert guard_apps('apps/runtime/shared.py', tmp_path) == {'a', 'b', 'c', 'd'}
    assert guard_apps('apps/runtime/bounded_tools.py', tmp_path) == {'g', 'i'}
    (tmp_path / 'apps/h/launch.py').parent.mkdir()
    (tmp_path / 'apps/h/launch.py').write_text('import importlib\nname = "shared"\nimportlib.import_module(name)\n')
    with pytest.raises(AssertionError, match='unresolvable load'):
        guard_apps('apps/runtime/shared.py', tmp_path)
    (tmp_path / 'apps/h/launch.py').unlink()
    (tmp_path / 'apps/runtime/bounded_tools.py').write_text('CHECK = ' + digest + '\n\n\nclass BoundedTools:\n    def __init__(self):\n        pass\n')
    with pytest.raises(AssertionError):  # the guard moved out of BoundedTools.__init__: the use rule no longer holds
        guard_apps('apps/runtime/bounded_tools.py', tmp_path)
    # R2 #1: constant path loads, any package directory, getattr of BoundedTools; unresolvable forms fail.
    more = {'apps/j/pkg/mod.py': 'import shared\n',
            'apps/k/launch.py': 'import runpy\nrunpy.run_path("/opt/woow/apps/runtime/shared.py")\n',
            'apps/l/launch.py': ('import importlib.util\nspec = importlib.util.spec_from_file_location("x", "/opt/woow/apps/runtime/shared.py")\n'
                                 'module = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\n'),
            'apps/m/launch.py': 'import bounded_tools\ngetattr(bounded_tools, "BoundedTools")()\n'}
    for path, text in more.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    for path, text in {'apps/runtime/shared.py': 'CHECK = ' + digest + '\n',
                       'apps/runtime/bounded_tools.py': 'class BoundedTools:\n    def __init__(self):\n        self.check = ' + digest + '\n'}.items():
        (tmp_path / path).write_text(text)
    assert guard_apps('apps/runtime/shared.py', tmp_path) == {'a', 'b', 'c', 'd', 'j', 'k', 'l'}
    assert guard_apps('apps/runtime/bounded_tools.py', tmp_path) == {'g', 'i', 'm'}
    for text, reason in (('from importlib import import_module as load\nload("shared")\n', 'renamed loader'),
                         ('import importlib\ngetattr(importlib, "import_module")("shared")\n', 'loader named in a string'),
                         ('import importlib\nload = importlib.import_module\nload("shared")\n', 'unresolvable load'),
                         ('exec("import shared")\n', 'unresolvable load'),
                         ('import runpy\nrunpy.run_path(PATH)\n', 'unresolvable load')):
        (tmp_path / 'apps/h/launch.py').write_text(text)
        with pytest.raises(AssertionError, match=reason):
            guard_apps('apps/runtime/shared.py', tmp_path)
    (tmp_path / 'apps/h/launch.py').unlink()
    split = tmp_path / 'split.py'
    split.write_text("CHECK = ('" + 'a' * 32 + "'\n         '" + 'a' * 32 + "')\n")
    assert digests(split) == {'a' * 64}  # adjacent literals, which a text search misses
