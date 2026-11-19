"""HM-07: the profile data layer is not wired and an upgrade rewrites nothing (plan §3.3, §7.1; I6).

- Wired since: HM-08 wired features.py and profiles.py: run_product asks features.enabled() at every start, the gateway
  takes the profile id grammar from profiles.py, and only a switched-on product's dispatcher reads the index
  (tests/test_router_passthrough.py: switched off, no index or profile directory is read). HM-20's loopback rule reads
  features.enabled() too (products.loopback_refused; switched off, it changes no answer). HM-12 wired identity_fields.py
  (products.identity_rebound, backend_edit.new_origin_refused: data the gateway reads only for a switched-on product;
  switched off, it changes no answer). HM-13b wired HM-13a's restore_detect.py and reads HM-07's identity_fields.py too:
  both entry points run the boot guard (restore_lock) at every start, which detects a restore, and its restore record
  shows identity fields. UNWIRED is empty now; the scans stay for the next module that is not wired yet. The 8081 and
  8099 answers stay those HM-01 froze (tests/test_single_profile_golden.py, tests/test_mcp_contract_freeze.py,
  tests/test_admin_contract_freeze.py).
- The switch: MULTI_PROFILE_PRODUCTS is empty; features.enabled() reads it at every call (never bound at import), so
  an integration test can switch a product on with a subprocess preamble (tests/test_real_products.py style).
- Zero rewrite: a state.json bb48449 wrote (one installed add-on per product, tests/fixtures/upgrade_zero_rewrite)
  starts the production runtime without a single changed byte and without any new multi-profile file (plan §7.3);
  on a single-profile installation every read of the data layer leaves /data/mcp exactly as it was; creating profiles
  never writes the default profile's state.json (SHA-256, inode, mtime, mode, ctime).
- The restore check (HM-13a) on the same bytes: nothing changes while the product is switched off; once it is on, the
  first check adds the instance sentinel and its record and nothing else. HM-13b runs it at every start (the boot
  guard): the production runtime's start of these bytes switched on adds only those two besides the child's directory.
"""
import ast
import contextlib
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import typing

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import features, products, profiles, restore_detect
from mcp_admin_core.products import ProductState, ProductStore, profile_initial_state
from multi_profile_runtime import multi_profile_runtime
from product_switch import off
from test_restore_detection import after_tick
from test_single_profile_golden import PRODUCTS as GOLDEN_PRODUCTS, production_runtime, settle

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'packages/mcp-admin-core/mcp_admin_core'
ZERO_REWRITE = ROOT / 'tests/fixtures/upgrade_zero_rewrite'
# Modules no runtime file may import yet. HM-08 wired HM-07's features and profiles (HM-20's loopback rule reads
# features too); HM-12 wired HM-07's identity_fields; HM-13b wired HM-13a's restore_detect (the boot guard,
# restore_lock, which reads identity_fields too).
UNWIRED = ()
A, B = 'a' * 24, 'b' * 24


def runtime_sources():
    """Every Python file of the image: the core package, apps/ (no venvs or installs) and the two packaging files
    every Dockerfile copies (scripts/ledger_precheck.py's runtime files)."""
    yield from sorted(CORE.glob('*.py'))
    for top, dirs, files in os.walk(ROOT / 'apps'):
        dirs[:] = sorted(d for d in dirs if d not in ('.venv', 'node_modules', '__pycache__'))
        yield from (Path(top) / name for name in sorted(files) if name.endswith('.py'))
    yield ROOT / 'packaging/entrypoint.py'
    yield ROOT / 'packaging/management_launcher.py'


def references(path, module):
    """Lines of *path* that import *module*: an import statement (absolute or relative, in any block), a call of
    import_module / __import__ with its name, or a string naming the module (mcp_admin_core.<module>) or its file
    (.../<module>.py, as spec_from_file_location and runpy take it). The bare word is no import: a dict key or a tool
    argument called "profiles" or "features" is a product's own data. A name computed at run time is out of reach
    here; test_no_entry_point_imports_the_unwired_modules sees what the entry points import when they load."""
    full = 'mcp_admin_core.' + module
    lines = []
    for node in ast.walk(ast.parse(path.read_text(), str(path))):
        if isinstance(node, ast.Import):
            if any(alias.name in (full, module) for alias in node.names):
                lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            target = node.module or ''
            if (target in (full, module) or target.endswith('.' + module)
                    or (target in ('mcp_admin_core', '') and any(alias.name == module for alias in node.names))):
                lines.append(node.lineno)
        elif isinstance(node, ast.Call):
            callee = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', None)
            name = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
            if (callee in ('import_module', '__import__') and isinstance(name, str)
                    and (name in (full, module, '.' + module) or name.endswith('.' + module))):
                lines.append(node.lineno)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and (
                node.value == full or node.value.endswith('/' + module + '.py')):
            lines.append(node.lineno)
    return lines


def test_no_runtime_file_imports_the_unwired_modules():
    found = {}
    for path in runtime_sources():
        if path.parent == CORE and path.stem in UNWIRED:
            continue
        for module in UNWIRED:
            if lines := references(path, module):
                found.setdefault(str(path.relative_to(ROOT)), {})[module] = lines
    # The unwired modules may name each other (restore_detect takes its file names from profiles); nothing else knows
    # them.
    assert found == {}


def test_references_sees_every_import_form(tmp_path):
    forms = ['from .profiles import Layout\n', 'from . import profiles\n', 'import mcp_admin_core.profiles\n',
             'from mcp_admin_core import profiles as p\n', 'def f():\n    from .profiles import scan_profiles\n',
             'import importlib\nimportlib.import_module("mcp_admin_core.profiles")\n',
             'import importlib\nimportlib.import_module(".profiles", "mcp_admin_core")\n',
             'from importlib import import_module\nimport_module("profiles")\n',
             '__import__("mcp_admin_core.profiles")\n',
             'import importlib.util\nimportlib.util.spec_from_file_location(\n'
             '    "p", "/opt/woow/packages/mcp-admin-core/mcp_admin_core/profiles.py")\n',
             'try:\n    from mcp_admin_core.profiles import Layout\nexcept ImportError:\n    pass\n']
    for number, text in enumerate(forms):
        path = tmp_path / f'case{number}.py'
        path.write_text(text)
        assert references(path, 'profiles'), text
    # The word alone is no import: a dict key, a JSON field or a tool argument called "profiles" or "features"
    # (a product's own data) is not this module.
    (tmp_path / 'clean.py').write_text('import profile_runtime\nfrom .products import ProductStore\nprofiles_seen = 1\n'
                                       'KEYS = ("profiles", "features")\nschema = {"features": {"type": "array"}}\n'
                                       'label = "mcp_admin_core.profiles is not imported here"\n')
    assert references(tmp_path / 'clean.py', 'profiles') == []
    assert references(tmp_path / 'clean.py', 'features') == []


def imported_core_modules(code):
    result = subprocess.run([sys.executable, '-c', code + '\nimport sys, json; print(json.dumps(sorted('
                             'm for m in sys.modules if m.startswith("mcp_admin_core"))))'],
                            capture_output=True, text=True, cwd=ROOT, timeout=120,
                            env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1',
                                 'PYTHONPATH': str(ROOT / 'packages/mcp-admin-core') + ':' + str(ROOT / 'apps/n8n')})
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.splitlines()[-1])


@pytest.mark.parametrize('entry', ['run_product', 'n8n', 'management_launcher', 'entrypoint'])
def test_no_entry_point_imports_the_unwired_modules(entry):
    code = {
        'run_product': 'import mcp_admin_core.run_product',
        # apps/n8n/run.py as the launcher runs it, without starting it (main() is behind __name__ == "__main__").
        'n8n': ('import importlib.util; s = importlib.util.spec_from_file_location("n8n_run", "apps/n8n/run.py"); '
                'm = importlib.util.module_from_spec(s); s.loader.exec_module(m)'),
        'management_launcher': ('import importlib.util; s = importlib.util.spec_from_file_location("launcher", '
                                '"packaging/management_launcher.py"); m = importlib.util.module_from_spec(s); '
                                's.loader.exec_module(m)'),
        'entrypoint': ('import importlib.util; s = importlib.util.spec_from_file_location("entry", '
                       '"packaging/entrypoint.py"); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)'),
    }[entry]
    loaded = imported_core_modules(code)
    assert not {'mcp_admin_core.' + name for name in UNWIRED} & set(loaded), loaded
    if entry in ('run_product', 'n8n'):
        assert 'mcp_admin_core.products' in loaded and 'mcp_admin_core.config' in loaded  # the probe saw imports
        # HM-13b: both runtimes run the boot guard at every start
        assert {'mcp_admin_core.restore_lock', 'mcp_admin_core.restore_detect'} <= set(loaded), loaded


def test_multi_profile_is_switched_off_for_every_product():
    assert features.MULTI_PROFILE_PRODUCTS == frozenset() and type(features.MULTI_PROFILE_PRODUCTS) is frozenset
    assert features.KNOWN_PRODUCTS == frozenset(typing.get_args(products.Product))
    assert not any(features.enabled(product) for product in features.KNOWN_PRODUCTS)
    # Only an upgrade PR (the owner approves and merges it) adds a product, and only one that can have profiles.
    assert all(profiles.supports_profiles(p) for p in features.MULTI_PROFILE_PRODUCTS)
    for value in ('bogus', 'Odoo', '', None):
        with pytest.raises(ValueError):
            features.enabled(value)


def test_the_switch_is_read_at_every_call(monkeypatch):
    monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset({'odoo'}))
    assert features.enabled('odoo') and not features.enabled('n8n')
    monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset())
    assert not features.enabled('odoo')


def test_a_subprocess_preamble_switches_a_product_on():
    code = ('from mcp_admin_core import features; features.MULTI_PROFILE_PRODUCTS = frozenset({"odoo"}); '
            'import mcp_admin_core.run_product; '
            'print("ENABLED", features.enabled("odoo"), features.enabled("n8n"))')
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, cwd=ROOT, timeout=120,
                            env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1',
                                 'PYTHONPATH': str(ROOT / 'packages/mcp-admin-core')})
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.splitlines()[-1] == 'ENABLED True False'


def test_nothing_binds_the_switch_at_import():
    # Plan §3.3: always features.enabled(product), never a copy of MULTI_PROFILE_PRODUCTS taken at import time.
    found = []
    for path in runtime_sources():
        if path == CORE / 'features.py':
            continue
        tree = ast.parse(path.read_text(), str(path))
        for node in ast.walk(tree):
            if ((isinstance(node, ast.ImportFrom) and any(a.name == 'MULTI_PROFILE_PRODUCTS' for a in node.names))
                    or (isinstance(node, ast.Attribute) and node.attr == 'MULTI_PROFILE_PRODUCTS')
                    or (isinstance(node, ast.Name) and node.id == 'MULTI_PROFILE_PRODUCTS')):
                found.append((str(path.relative_to(ROOT)), node.lineno))
    assert found == []
    tree = ast.parse((CORE / 'features.py').read_text())
    [enabled] = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'enabled']
    assert any(isinstance(n, ast.Name) and n.id == 'MULTI_PROFILE_PRODUCTS' for n in ast.walk(enabled))


def tree_facts(root):
    """Every entry under root: kind, mode, inode, link count, size, mtime and ctime (ns), and a file's SHA-256."""
    facts = {}
    for path in sorted([root, *root.rglob('*')]):
        info = os.lstat(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(info.st_mode) else None
        facts[str(path.relative_to(root))] = (stat.S_IFMT(info.st_mode), stat.S_IMODE(info.st_mode), info.st_ino,
                                              info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns, digest)
    return facts


def start_facts(root):
    """tree_facts without the ctime: ProductStore.load() fchmods state.json to 0600 at every read (config.py), so its
    ctime changes on every start; bytes, inode, links, size, mode and mtime do not."""
    return {name: facts[:6] + facts[7:] for name, facts in tree_facts(root).items()}


def test_the_samples_are_the_bytes_the_store_writes():
    # One sample per product, none hand-edited: each is exactly what Store._write writes for its state
    # (model_dump_json), and this code still writes the bytes bb48449 wrote. When this changes, an older image reads
    # back a state this code saved: check FM-09 (rollback) before changing the samples.
    assert sorted(path.stem for path in ZERO_REWRITE.glob('*.json')) == sorted(GOLDEN_PRODUCTS)
    for product in GOLDEN_PRODUCTS:
        raw = (ZERO_REWRITE / f'{product}.json').read_bytes()
        assert ProductState.model_validate_json(raw).model_dump_json().encode() == raw, product


def installed(tmp_path, raw):
    """/data/mcp of an installed add-on of today: the runtime's lock and the state bytes bb48449 wrote, both 0600."""
    data = tmp_path / 'mcp'
    data.mkdir(mode=0o700)
    for name, content in (('.writer.lock', b''), ('state.json', raw)):
        fd = os.open(data / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, content)
        finally:
            os.close(fd)
    return data


@pytest.mark.parametrize('switched_on', [False, True])
@pytest.mark.parametrize('product', GOLDEN_PRODUCTS)
async def test_a_state_bb48449_wrote_starts_without_any_rewrite(tmp_path, log_scan, product, switched_on):
    # Plan §7.1, §7.3: an installed add-on of today upgrades to this code. The state is the bytes bb48449 wrote
    # (tests/fixtures/upgrade_zero_rewrite/README.md); the runtime is the production one with only its outside
    # replaced (tests/test_single_profile_golden.py: production_runtime; switched on, tests/multi_profile_runtime.py:
    # the same with the product's switch on). HM-13b runs the restore check at every start (the boot guard): switched
    # off nothing new appears; switched on, the only new entries are the sentinel and its record (HM-13a pins the check
    # itself: test_the_restore_check_on_a_state_bb48449_wrote_adds_only_the_sentinel). n8n has no profiles until HM-25,
    # but its guard reads the switch as well. Every slice keeps it passing.
    raw = (ZERO_REWRITE / f'{product}.json').read_bytes()
    state = ProductState.model_validate_json(raw)
    assert state.product == product and state.configured and state.token_history
    log_scan.watch_state(state)
    data = installed(tmp_path, raw)
    before = start_facts(data)
    if not switched_on:
        running = switched_off_runtime(product, data)  # HM-26: whatever the repository's switch says
    elif product == 'n8n':
        running = n8n_switched_on(data)
    else:
        running = multi_profile_runtime(product, data)
    async with running as runtime:
        await settle(runtime, 'configured')
    after = start_facts(data)
    assert (data / 'state.json').read_bytes() == raw
    assert {name: after[name] for name in before if name != '.'} == {n: f for n, f in before.items() if n != '.'}
    # The child's own working directory, as today (products.child_spec; n8n works in /data/mcp); switched on, the
    # instance sentinel and its record.
    expected = (set() if product == 'n8n' else {'child'})
    if switched_on:
        expected |= {profiles.SENTINEL_NAME, profiles.INSTANCE_RECORD_NAME}
    assert set(after) - set(before) == expected
    assert not profiles.has_profile_data(data)


@contextlib.asynccontextmanager
async def switched_off_runtime(product, data):
    with off(product):
        async with production_runtime(product, data) as runtime:
            yield runtime


@contextlib.asynccontextmanager
async def n8n_switched_on(data):
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset({'n8n'}))
        async with production_runtime('n8n', data) as runtime:
            yield runtime


@pytest.mark.parametrize('product', GOLDEN_PRODUCTS)
def test_the_restore_check_on_a_state_bb48449_wrote_adds_only_the_sentinel(tmp_path, log_scan, product):
    # HM-13a (plan §7.1, §7.2, §8.4): the same installed add-on before and after its product is switched on. The
    # check is not wired yet (HM-13b runs it at every start, before any listener). Switched off, it changes nothing,
    # not even a ctime. The first check switched on adds the instance sentinel and its record and nothing else; later
    # checks, switched on or off, change nothing. Before each look the file clock moves past every ctime in /data/mcp
    # (after_tick, outside it): a chmod or a new file in the same coarse tick would keep the old ctime.
    Detection, raw = restore_detect.Detection, (ZERO_REWRITE / f'{product}.json').read_bytes()
    log_scan.watch_state(ProductState.model_validate_json(raw))
    data = installed(tmp_path, raw)
    after_tick(tmp_path, max(facts[6] for facts in tree_facts(data).values()))
    before = tree_facts(data)
    for _ in range(2):
        assert restore_detect.detect(data, enabled=False) == Detection(False, False, restore_detect.INACTIVE)
    assert tree_facts(data) == before
    first = restore_detect.detect(data, enabled=True)
    assert first == Detection(False, True, restore_detect.ESTABLISHED) and not first.restored
    after = tree_facts(data)
    assert set(after) - set(before) == {profiles.SENTINEL_NAME, profiles.INSTANCE_RECORD_NAME}
    assert {name: after[name] for name in before if name != '.'} == {n: f for n, f in before.items() if n != '.'}
    after_tick(tmp_path, max(facts[6] for facts in after.values()))
    for enabled, verdict in ((True, restore_detect.CONSISTENT), (False, restore_detect.INACTIVE),
                             (True, restore_detect.CONSISTENT)):
        assert restore_detect.detect(data, enabled=enabled) == Detection(False, enabled, verdict)
    assert tree_facts(data) == after
    assert (data / 'state.json').read_bytes() == raw and not profiles.has_profile_data(data)


@pytest.mark.parametrize('product', sorted(features.KNOWN_PRODUCTS))
def test_reading_a_single_profile_installation_changes_nothing(tmp_path, log_scan, product):
    store = ProductStore(tmp_path / 'mcp', product)  # an installed add-on of today: no profile data
    log_scan.watch_state(store.load())
    store.close()
    root = tmp_path / 'mcp'
    before = tree_facts(root)
    layout = profiles.Layout(root)
    view = profiles.read_index(layout.index)
    assert view.state == profiles.INDEX_ABSENT and view.serves_mcp
    assert profiles.recheck_index(layout.index, view) is view
    scan = profiles.scan_profiles(layout)
    assert scan == profiles.ProfilesScan((), (), 0)
    assert not profiles.has_profile_data(root)
    assert profiles.check_consistency(view.entries, scan, {}).unavailable == ()
    profiles.capacity(product)
    profiles.allocate_port()
    assert tree_facts(root) == before  # nothing created, written, chmod'ed or touched (ctime included)


def test_profiles_never_write_the_default_state(tmp_path, log_scan):
    # I6: the index and the profile directories sit next to the default profile's files; creating profiles, writing
    # the index, opening and checking them leave state.json bit for bit (and its inode, mtime, mode and ctime).
    store = ProductStore(tmp_path / 'mcp', 'odoo')
    default = store.load()
    log_scan.watch_state(default)
    root = tmp_path / 'mcp'
    before = tree_facts(root)
    layout = profiles.Layout(root)
    profiles.ensure_profiles_directory(layout)
    taken, entries, made = {default.token, default.child_token}, [], {}
    for profile_id in (A, B):
        state = profile_initial_state(default, taken=taken)
        taken |= {state.token, state.child_token}
        log_scan.watch_state(state)
        ProductStore(layout.profile(profile_id), 'odoo', create=state).close()
        entries.append(profiles.IndexEntry(profile_id, profile_id[:4], profiles.allocate_port(e.port for e in entries)))
        made[profile_id] = state
    view = profiles.write_index(layout.index, entries, expected=profiles.read_index(layout.index))
    read = {'default': (default.token, default.child_token)}
    for profile_id in made:
        opened = ProductStore(layout.profile(profile_id), 'odoo', existing_only=True)
        read[profile_id] = (opened.load().token, opened.load().child_token)
        opened.close()
    result = profiles.check_consistency(view.entries, profiles.scan_profiles(layout), read)
    assert result.unavailable == () and result.shared_secrets == () and result.orphans == ()
    after = tree_facts(root)
    for name in ('.', 'state.json', '.writer.lock'):
        if name == '.':
            continue  # the directory itself gained two entries
        assert after[name] == before[name], name
    assert set(after) - set(before) == {'profiles.json', 'profiles', *(
        f'profiles/{i}{suffix}' for i in made for suffix in ('', '/.writer.lock', '/state.json'))}
    store.close()
