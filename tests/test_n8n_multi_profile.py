"""HM-25: n8n's additional profiles (multi-profile plan 9 n8n row, 12.3 HM-21～HM-26 n8n; DQ-04, DQ-22, UC-01, UC-09;
contract section 9 #4, #28, #47, #62, #90 and HM-25's rows; FM-15, FM-84, FM-140; T-05, T-07, T-22, T-23).

The repository switches no product on: every switched-on case here monkeypatches features.MULTI_PROFILE_PRODUCTS for
the test (tests/multi_profile_runtime.py, as the Odoo tests do); n8n's upgrade PR is the only one that switches it on.

- The runtime: apps/n8n/run.py runs run_product's runtime with the n8n adapter. Switched off, the default profile's
  lone ProfileRuntime (HM-01's golden regression and both contract freezes prove its bytes; tests/test_router_passthrough.py
  runs them switched on too); switched on, the ProfileManager every other product has.
- The child spec: the default profile's is the one before (tests/contract/child_spec_default.json). An additional
  profile's child starts only with a backend (DQ-22), works in its own empty profiles/<id>/child/ (HOME and cwd; never
  a link, never the profile directory), reads its own catalog copy (DQ-04, UC-09; never the default profile's or the
  packaged file) and names its port on its command line (HM-16 review SF-2: the P9 kit and the container probe read
  it there).
- The catalog copies: /tmp/woow-n8n-mcp/profiles/<id>/nodes.db (here under the test's own directory), 0700 directories
  and a 0600 file, never through a link (each directory opened and checked, the next one made and the file written
  through its descriptor: a directory swapped after its check is never written through; HM-25 security review S-6),
  made once per management process in a worker thread before the child's first start and again for another backend
  (security review S-8), removed with the profile: a deleted profile's, an orphan's and a quarantine directory's whose
  id is no longer served; a cleanup that fails is one WARNING and the deletion stands (correctness review S-2).
- The gateway: each profile's token reaches only its own child (Bearer 401 and secret URL 404 for every other token);
  no x-n8n-* header ever reaches a child (§8.8 #4), switched on or off; an additional profile without a backend has no
  child and every one of its tools, the seven documentation tools too, is refused as unconfigured, never "try again
  shortly"; saving one profile's policy restarts no child (n8n's policy is the gateway's), saving its session or
  backend restarts its child only (a profile born without a backend gets its child when its backend is saved, and
  loses it when the backend is cleared: correctness review S-1), and each profile's child gets its own session limits
  (20 by default: a new profile never copies another's settings, DQ-02); a reply is masked with every token the add-on
  holds once switched on, the profile's own credentials only when switched off (security review S-3).
- UC-01: the real n8n-mcp child of an additional profile leaves its HOME empty.

Every test runs under the HM-01 log scan (tokens, child tokens, the synthetic backend keys and the labels watched).
"""
import asyncio
import json
import logging
import os
from pathlib import Path
import secrets
import shutil
import stat
import time

import httpx
import pytest

import n8n_adapter
import run as n8n_run
from admin_write_headers import reviewed_headers
from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import (Children, CATALOG_STAND_IN, all_tokens, create_profile, ids, multi_profile_runtime,
                                   stored)
from mcp_admin_core import features, products, profile_runtime, profiles, redact
from mcp_admin_core.products import ProductState, ProductStore
from mcp_admin_core.surface import BACKEND_FREE, OPERATION_READS, SELECTORS, listing
from test_reply_mask_union import UNHELD, EchoChild, masked
from test_single_profile_golden import (ACCEPT, ADMIN, BEARER_REQUIRED, CHILD_HEADERS, GENUINE_CLIENT, INGRESS,
                                        NOT_FOUND, answer, configure, initialize_message, settle)

pytestmark = pytest.mark.usefixtures('log_scan')
PRODUCT = 'n8n'
B, C = ids(2)
D, O = ids(5)[3:]  # a quarantined profile and an orphan (HM-25 review S-2)
RUNTIME_LOGGER = 'mcp_admin_core.profile_runtime'
LABELS = {B: 'Beta Flows', C: 'Gamma Flows'}
DOCUMENTATION = BACKEND_FREE['n8n'].split()  # the seven tools n8n-mcp serves without a backend
# The headers n8n-mcp reads to switch its backend or instance (dist/http-server-single-session.js
# extractMultiTenantHeaders; G5-13) and one more of the family: a client never gets them to a child (§8.8 #4).
N8N_HEADERS = {'x-n8n-url': 'https://elsewhere.n8n.invalid', 'x-n8n-key': 'DUMMY-header-workflow-key',
               'x-n8n-mcp-token': 'DUMMY-header-access-token', 'x-instance-id': 'header-instance',
               'x-session-id': 'header-session', 'x-n8n-anything': '1'}


def watch(log_scan, data):
    """Every token, child token and backend key stored under data, and the labels."""
    for path in [Path(data) / 'state.json', *sorted((Path(data) / 'profiles').glob('*/state.json'))]:
        if path.exists():
            value = json.loads(path.read_text())
            log_scan.watch(*(v for v in (value['token'], value['child_token']) if v))
            log_scan.watch(*(v for v in (value.get('backend_key'), value.get('mcp_access_token')) if v), kind='secret')
    log_scan.watch(*LABELS.values(), kind='name')


def setup_profiles(tmp_path, *, configured=(B, C), extras=(B, C), default=True):
    """The default profile (configured as the golden one unless default is False) and the additional profiles extras
    (ports 18000 and up), each with its own synthetic backend when it is in configured."""
    data = tmp_path / 'data'
    if default:
        configure(data, PRODUCT)
    else:
        ProductStore(data, PRODUCT).close()
    for number, profile_id in enumerate(extras):
        create_profile(data, PRODUCT, profile_id, label=LABELS[profile_id], port=18000 + number,
                       configured=profile_id in configured)
    return data


def children_of(data, extras=(B, C)):
    children = Children()
    children.profile_child(3000, 'default', PRODUCT, data)
    for number, profile_id in enumerate(extras):
        children.profile_child(18000 + number, 'p' + profile_id[:4], PRODUCT, profiles.Layout(data).profile(profile_id))
    return children


def bearer(token, **headers):
    return {**ACCEPT, 'Authorization': 'Bearer ' + token, **headers}


def call(ident, name, arguments=None):
    return {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments or {}}}


def well_formed(name):
    """Arguments the add-on's policy lets through for the tool: a selector tool's first read operation (a strict
    selector refuses a call without one before anything else)."""
    if name not in SELECTORS:
        return {}
    selector, values = SELECTORS[name]
    return {selector: (OPERATION_READS[name] or values.split())[0]}


async def panel_write(runtime, method, path):
    """One of the panel's global management calls (the profile list's ETag, its CSRF token, a new Idempotency-Key)."""
    async with GENUINE_CLIENT(transport=httpx.ASGITransport(app=runtime.admin_app, client=INGRESS),
                              base_url='http://admin') as admin:
        boot = (await admin.get('/api/bootstrap', headers={**ADMIN, 'X-MCP-Profile': 'default'})).json()
        listed = await admin.get('/api/profiles', headers=ADMIN)
        return await admin.request(method, path, headers={
            **ADMIN, 'X-CSRF-Token': boot['csrf'], 'If-Match': listed.headers['etag'],
            'Idempotency-Key': f'{int(time.time() * 1000) - 1000}.{secrets.token_hex(16)}'})


def cleanup_warnings(log_scan):
    """The WARNINGs of ProfileManager.removed (a product's cleanup after a deletion that failed)."""
    return [record.getMessage() for record in log_scan.records
            if record.name == RUNTIME_LOGGER and record.levelno == logging.WARNING
            and record.getMessage().startswith('multi-profile: the cleanup after deleting profile ')]


def current(directory):
    """A profile's state as it is on disk now, read without opening its store (the runtime holds it)."""
    return ProductState.model_validate(stored(directory))


@pytest.fixture
def catalogs(tmp_path, monkeypatch):
    """n8n's catalog copies made from a small stand-in under the test's directory (never /tmp/woow-n8n-mcp)."""
    root = tmp_path / 'catalogs'
    root.mkdir(mode=0o700)
    source = root / 'source.db'
    source.write_bytes(CATALOG_STAND_IN)
    monkeypatch.setattr(n8n_adapter, 'PACKAGED_CATALOG', source)
    monkeypatch.setattr(n8n_adapter, 'CATALOG_DIR', root / 'copies')
    monkeypatch.setattr(n8n_adapter, '_profile_catalogs', {})
    monkeypatch.setattr(n8n_adapter, '_catalog', None)
    return root / 'copies'


@pytest.fixture
def switched(monkeypatch):
    monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset({PRODUCT}))


def state_of(data, profile_id='default'):
    directory = Path(data) if profile_id == 'default' else profiles.Layout(Path(data)).profile(profile_id)
    store = ProductStore(directory, PRODUCT) if profile_id == 'default' else ProductStore(directory, PRODUCT,
                                                                                       existing_only=True)
    try:
        return store.load(), Path(store.directory)
    finally:
        store.close()


# ---- the runtime ----

@pytest.mark.parametrize('switch', [False, True])
async def test_n8n_runs_run_products_runtime(tmp_path, log_scan, catalogs, switch):
    """apps/n8n/run.py runs run_product's runtime with the n8n adapter: switched off the default profile's lone runtime
    (8081 its own MCP app), switched on the ProfileManager (8081 its token dispatcher) with n8n's tools, child spec and
    catalog hooks."""
    data = setup_profiles(tmp_path, extras=())
    async with multi_profile_runtime(PRODUCT, data, switch=switch) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        if not switch:
            assert runtime.manager is None
            assert any(getattr(route, 'path', None) == '/mcp' for route in runtime.mcp_app.routes)
        else:
            manager = runtime.manager
            assert isinstance(manager, profile_runtime.ProfileManager) and manager.product == PRODUCT
            assert manager.tools is n8n_adapter.TOOLS and manager.child_spec is n8n_adapter.child_spec
            assert manager.prepare_child is n8n_adapter.prepare_child
            assert manager.profile_removed is n8n_adapter.remove_profile_catalog
            assert runtime.limits() == {'admin': 64, 'mcp': 64 + 32 * 2}  # n8n: two additional profiles at most


# ---- the child spec ----

def test_an_additional_profiles_child_works_in_its_own_directory(tmp_path, log_scan, catalogs, switched):
    """Its HOME and cwd are profiles/<id>/child/ (made 0700, empty), its catalog its own copy, its port on its command
    line too; everything else is the default profile's spec with its own state's values."""
    data = setup_profiles(tmp_path, extras=(B,))
    default_copy = n8n_adapter.prepare_catalog(tmp_path / 'default-catalog', catalogs.parent / 'source.db')
    own = n8n_adapter.prepare_profile_catalog(B)
    default_state, default_directory = state_of(data)
    state, directory = state_of(data, B)
    log_scan.watch_state(default_state)
    log_scan.watch_state(state)
    default = n8n_adapter.child_spec(default_state, default_directory)
    spec = n8n_adapter.child_spec(state, directory, port=18000)
    home = profiles.Layout(data).child(B)
    assert spec.cwd == home and spec.env['HOME'] == str(home)
    assert home.is_dir() and not home.is_symlink() and stat.S_IMODE(home.stat().st_mode) & 0o777 == 0o700
    assert list(home.iterdir()) == [] and sorted(path.name for path in directory.iterdir()) == [
        '.writer.lock', 'child', 'state.json']
    assert default.cwd == default_directory and default.env['HOME'] == str(default_directory)  # unchanged (/data/mcp)
    assert spec.argv == (*default.argv, '--port', '18000') and '--port' not in default.argv
    assert list(spec.env) == list(default.env)  # the same variables, in the same order
    different = {name for name in spec.env if spec.env[name] != default.env[name]}
    assert different == {'HOME', 'PORT', 'AUTH_TOKEN', 'N8N_API_URL', 'N8N_API_KEY', 'NODE_DB_PATH'}
    assert (spec.env['PORT'], spec.env['AUTH_TOKEN']) == ('18000', state.child_token)
    assert (spec.env['N8N_API_URL'], spec.env['N8N_API_KEY']) == (state.backend_url, state.backend_key)
    assert spec.env['NODE_DB_PATH'] == str(own) == str(catalogs / 'profiles' / B / 'nodes.db')
    assert default.env['NODE_DB_PATH'] == str(default_copy) != str(own)
    assert spec.env[products.DENY_LOOPBACK_ENV] == '1' and spec.env['WEBHOOK_SECURITY_MODE'] == 'permissive'
    assert spec.env['N8N_MCP_MAX_SESSIONS'] == '20' and spec.env['SESSION_TIMEOUT_MINUTES'] == '10'
    # Another start keeps the directory (it stays empty) and gives the same spec.
    assert n8n_adapter.child_spec(state, directory, port=18000) == spec


def test_an_additional_profile_without_a_backend_has_no_child(tmp_path, log_scan, catalogs, switched):
    """DQ-22: no child (no directory made, no catalog needed); the default profile's child still runs without one, for
    its documentation tools."""
    data = setup_profiles(tmp_path, configured=(), extras=(B,), default=False)
    default_state, default_directory = state_of(data)
    state, directory = state_of(data, B)
    log_scan.watch_state(state)
    assert not state.configured and not default_state.configured
    assert n8n_adapter.child_spec(state, directory, port=18000) is None
    assert not profiles.Layout(data).child(B).exists() and n8n_adapter.profile_catalog(B) is None
    assert n8n_adapter.child_spec(default_state, default_directory) is not None
    assert profiles.documentation_child(PRODUCT) and profiles.documentation_child(PRODUCT, 'default')
    assert not profiles.documentation_child(PRODUCT, B)
    assert not any(profiles.documentation_child(product, 'default') for product in products.PRODUCTS)


@pytest.mark.parametrize('case', ['link', 'link to a file', 'file', 'not empty'])
def test_the_child_directory_is_its_own_empty_directory(tmp_path, log_scan, catalogs, switched, case):
    """Checked whenever the spec is built (a start, a save, the panel's restart, a re-evaluation; the watchdog's
    restarts reuse the spec): a link (to a directory or a file), a file or a directory with anything in it is refused
    and nothing is followed or written there."""
    data = setup_profiles(tmp_path, extras=(B,))
    n8n_adapter.prepare_profile_catalog(B)
    state, directory = state_of(data, B)
    log_scan.watch_state(state)
    home = directory / 'child'
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    if case == 'link':
        home.symlink_to(elsewhere)
    elif case == 'link to a file':
        (elsewhere / 'file').write_text('x')
        home.symlink_to(elsewhere / 'file')
    elif case == 'file':
        home.write_text('x')
    else:
        home.mkdir(mode=0o700)
        (home / '.n8n-mcp').mkdir()
    with pytest.raises((RuntimeError, FileExistsError)):
        n8n_adapter.child_spec(state, directory, port=18000)
    assert sorted(path.name for path in elsewhere.iterdir()) == ([] if case == 'link' else
                                                                 ['file'] if case == 'link to a file' else [])


def test_an_additional_profile_never_reads_another_catalog(tmp_path, log_scan, catalogs, switched):
    """UC-09: no copy of its own (none made, or gone), no child: never the default profile's copy or the packaged file,
    which another profile's child could be writing."""
    data = setup_profiles(tmp_path, extras=(B, C))
    n8n_adapter.prepare_catalog(tmp_path / 'default-catalog', catalogs.parent / 'source.db')
    n8n_adapter.prepare_profile_catalog(C)
    state, directory = state_of(data, B)
    log_scan.watch_state(state)
    with pytest.raises(RuntimeError, match='catalog'):
        n8n_adapter.child_spec(state, directory, port=18000)
    own = n8n_adapter.prepare_profile_catalog(B)
    own.unlink()
    with pytest.raises(RuntimeError, match='catalog'):
        n8n_adapter.child_spec(state, directory, port=18000)


def test_switched_off_no_additional_profile_has_a_child(tmp_path, log_scan, catalogs, monkeypatch):
    """Switched off, profile data is dormant (HM-13b): an additional profile's spec is refused, never built."""
    monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset({PRODUCT}))
    data = setup_profiles(tmp_path, extras=(B,))
    n8n_adapter.prepare_profile_catalog(B)
    monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset())
    state, directory = state_of(data, B)
    log_scan.watch_state(state)
    with pytest.raises(RuntimeError, match='no additional profile'):
        n8n_adapter.child_spec(state, directory, port=18000)
    assert n8n_adapter.profile_of(directory) == B and n8n_adapter.profile_of(data) == 'default'
    assert n8n_adapter.profile_of(tmp_path / 'profiles') == 'default'
    assert n8n_adapter.profile_of(tmp_path / 'other' / B) == 'default'  # only <data>/profiles/<id> is a profile's


# ---- the catalog copies ----

def test_each_profile_gets_its_own_catalog_copy(tmp_path, catalogs):
    """profiles/<id>/nodes.db under the catalog directory: every directory 0700, the file 0600, the bytes the package's;
    a second copy replaces the first atomically and leaves nothing else; the default profile's copy is another file."""
    source = catalogs.parent / 'source.db'
    default = n8n_adapter.prepare_catalog(catalogs, source)
    made = {profile_id: n8n_adapter.prepare_profile_catalog(profile_id) for profile_id in (B, C)}
    assert made == {profile_id: catalogs / 'profiles' / profile_id / 'nodes.db' for profile_id in (B, C)}
    for path in (*made.values(), default):
        assert path.read_bytes() == CATALOG_STAND_IN and stat.S_IMODE(path.stat().st_mode) == 0o600
    for directory in (catalogs, catalogs / 'profiles', *(path.parent for path in made.values())):
        assert stat.S_IMODE(directory.stat().st_mode) & 0o777 == 0o700  # (a setgid parent adds 0o2000)
    assert {n8n_adapter.profile_catalog(B), n8n_adapter.profile_catalog(C)} == set(made.values())
    source.write_bytes(CATALOG_STAND_IN + b'a newer image')
    assert n8n_adapter.prepare_profile_catalog(B).read_bytes() == source.read_bytes()
    assert sorted(path.name for path in (catalogs / 'profiles' / B).iterdir()) == ['nodes.db']
    assert made[C].read_bytes() == CATALOG_STAND_IN and default.read_bytes() == CATALOG_STAND_IN
    with pytest.raises(ValueError):
        n8n_adapter.prepare_profile_catalog('default')
    with pytest.raises(ValueError):
        n8n_adapter.prepare_profile_catalog('../' + B)


@pytest.mark.parametrize('case', ['profiles link', 'profile link', 'open root', 'open profiles', 'source link',
                                  'no source'])
def test_a_catalog_copy_never_follows_a_link(tmp_path, catalogs, case):
    source = catalogs.parent / 'source.db'
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir(mode=0o700)
    catalogs.mkdir(mode=0o700)
    if case == 'profiles link':
        (catalogs / 'profiles').symlink_to(elsewhere)
    elif case == 'profile link':
        (catalogs / 'profiles').mkdir(mode=0o700)
        (catalogs / 'profiles' / B).symlink_to(elsewhere)
    elif case == 'open root':
        os.chmod(catalogs, 0o755)
    elif case == 'open profiles':
        (catalogs / 'profiles').mkdir(mode=0o700)
        os.chmod(catalogs / 'profiles', 0o755)
    elif case == 'source link':
        (tmp_path / 'link.db').symlink_to(source)
        source = tmp_path / 'link.db'
    else:
        source = tmp_path / 'missing.db'
    assert n8n_adapter.prepare_profile_catalog(B, source=source) is None
    assert n8n_adapter.profile_catalog(B) is None and list(elsewhere.iterdir()) == []


def test_a_deleted_profiles_copy_is_removed_without_following_a_link(tmp_path, catalogs):
    made = n8n_adapter.prepare_profile_catalog(B)
    kept = n8n_adapter.prepare_profile_catalog(C)
    assert n8n_adapter.remove_profile_catalog(B) is True
    assert not made.parent.exists() and n8n_adapter.profile_catalog(B) is None
    assert n8n_adapter.remove_profile_catalog(B) is True  # nothing left: done
    assert kept.read_bytes() == CATALOG_STAND_IN and n8n_adapter.profile_catalog(C) == kept
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    (elsewhere / 'nodes.db').write_bytes(b'not ours')
    (catalogs / 'profiles' / B).symlink_to(elsewhere)
    assert n8n_adapter.remove_profile_catalog(B) is False  # a link at the profile's name: not followed
    assert (elsewhere / 'nodes.db').read_bytes() == b'not ours'
    (catalogs / 'profiles' / B).unlink()
    shutil.move(catalogs / 'profiles', tmp_path / 'moved')
    (catalogs / 'profiles').symlink_to(tmp_path / 'moved')
    assert n8n_adapter.remove_profile_catalog(C) is False  # the profiles directory a link: not followed
    assert kept.resolve().read_bytes() == CATALOG_STAND_IN
    assert n8n_adapter.remove_profile_catalog(B, root=tmp_path / 'nothing-here') is True
    with pytest.raises(ValueError):
        n8n_adapter.remove_profile_catalog('default')


async def test_a_profiles_copy_is_made_once_off_the_event_loop(tmp_path, log_scan, catalogs, monkeypatch, caplog):
    """prepare_child: nothing without a backend; with one, the copy in a worker thread (asyncio.to_thread), once per
    management process; again only when it is gone. A copy that cannot be made is one WARNING (the id's first 8
    characters, never a path or a label)."""
    data = setup_profiles(tmp_path, configured=(C,), extras=(B, C))
    unconfigured, _ = state_of(data, B)
    configured, _ = state_of(data, C)
    threads = []
    original = asyncio.to_thread

    async def recorded(function, *args, **kwargs):
        threads.append(function.__name__)
        return await original(function, *args, **kwargs)
    monkeypatch.setattr(n8n_adapter.asyncio, 'to_thread', recorded)
    await n8n_adapter.prepare_child(B, unconfigured)
    assert threads == [] and n8n_adapter.profile_catalog(B) is None
    await n8n_adapter.prepare_child(C, configured)
    assert threads == ['prepare_profile_catalog'] and n8n_adapter.profile_catalog(C) is not None
    await n8n_adapter.prepare_child(C, configured)
    assert threads == ['prepare_profile_catalog']  # kept across the child's restarts
    n8n_adapter.remove_profile_catalog(C)
    monkeypatch.setattr(n8n_adapter, 'PACKAGED_CATALOG', tmp_path / 'missing.db')
    with caplog.at_level(logging.WARNING, logger='n8n_adapter'):
        await n8n_adapter.prepare_child(C, configured)
    assert threads == ['prepare_profile_catalog'] * 2 and n8n_adapter.profile_catalog(C) is None
    assert [record.getMessage() for record in caplog.records if record.name == 'n8n_adapter'] == [
        f'n8n: profile {C[:8]}: no catalog copy could be made; its child does not start']


async def test_a_profiles_copy_belongs_to_the_backend_it_was_made_for(tmp_path, log_scan, catalogs, monkeypatch):
    """HM-25 security review S-8: n8n_workflow_versions reads a snapshot by its number, whatever workflow and backend
    it was taken from, so a profile handed to another backend's holder (another URL, or another key: another n8n user)
    must not read the snapshots taken from the one before. The same backend keeps its copy and the history in it
    across starts; another URL or another key gets a new copy before the child starts; without a backend nothing is
    made (and the copy is left as it is)."""
    data = setup_profiles(tmp_path, configured=(C,), extras=(C,))
    state, _ = state_of(data, C)
    log_scan.watch_state(state)
    made = []
    original = asyncio.to_thread

    async def recorded(function, *args, **kwargs):
        made.append(function.__name__)
        return await original(function, *args, **kwargs)
    monkeypatch.setattr(n8n_adapter.asyncio, 'to_thread', recorded)
    history = b'version snapshots taken from this backend'
    await n8n_adapter.prepare_child(C, state)
    copy = n8n_adapter.profile_catalog(C)
    copy.write_bytes(copy.read_bytes() + history)
    await n8n_adapter.prepare_child(C, state)
    assert made == ['prepare_profile_catalog'] and copy.read_bytes().endswith(history)
    for changes in ({'backend_url': 'https://elsewhere.n8n.invalid'}, {'backend_key': 'DUMMY-another-workflow-key'}):
        await n8n_adapter.prepare_child(C, state.model_copy(update=changes))
        assert n8n_adapter.profile_catalog(C) == copy and copy.read_bytes() == CATALOG_STAND_IN, sorted(changes)
        copy.write_bytes(copy.read_bytes() + history)
        await n8n_adapter.prepare_child(C, state)  # the first backend again: not the copy the other one used
        assert copy.read_bytes() == CATALOG_STAND_IN, sorted(changes)
        copy.write_bytes(copy.read_bytes() + history)
    assert made == ['prepare_profile_catalog'] * 5
    await n8n_adapter.prepare_child(C, state.model_copy(update={'backend_url': None, 'backend_key': None}))
    assert len(made) == 5 and copy.read_bytes().endswith(history)


def test_a_catalog_copy_is_never_written_through_a_directory_swapped_after_its_check(tmp_path, catalogs, monkeypatch):
    """HM-25 security review S-6: every directory is opened without following a link and checked, the next one is made
    in it and the file is written and renamed through the last one's descriptor (as remove_profile_catalog removes
    it). The profiles directory swapped for a link right after its check (here: as the profile's directory is made in
    it) is never written through: the copy lands in the directory that was checked, its path no longer leads to it, so
    nothing is recorded and the profile's child does not start."""
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir(mode=0o700)
    real_mkdir, swapped = os.mkdir, []

    def mkdir(path, mode=0o777, *, dir_fd=None):
        if os.path.basename(os.fspath(path)) == B and not swapped:
            os.rename(catalogs / 'profiles', tmp_path / 'moved')
            (catalogs / 'profiles').symlink_to(elsewhere)
            swapped.append(B)
        return real_mkdir(path, mode, dir_fd=dir_fd)
    monkeypatch.setattr(os, 'mkdir', mkdir)
    assert n8n_adapter.prepare_profile_catalog(B) is None
    assert swapped == [B] and list(elsewhere.iterdir()) == []
    assert (tmp_path / 'moved' / B / 'nodes.db').read_bytes() == CATALOG_STAND_IN
    assert n8n_adapter.profile_catalog(B) is None


# ---- the gateway, switched on ----

async def test_every_profile_reaches_only_its_own_child(tmp_path, log_scan):
    """T-05, T-23: each profile's token, on both connection paths, opens a session with its own child only and its
    tools/call goes there; every other token gets 401 (Bearer) or 404 (secret URL) and reaches no child; one profile's
    session is unknown with another profile's token; each child only ever gets its own child bearer."""
    data = setup_profiles(tmp_path)
    children = children_of(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        mock = {'default': children.by_port[3000], B: children.by_port[18000], C: children.by_port[18001]}
        names = {'default': 'default', B: 'p' + B[:4], C: 'p' + C[:4]}
        sessions = {}
        async with runtime.mcp() as client:
            for profile_id in ('default', B, C):
                token = runtime.token(profile_id)
                for path, headers in (('/mcp', bearer(token)), (f'/private_{token}/mcp', dict(ACCEPT))):
                    since = {key: len(child.requests) for key, child in mock.items()}
                    opened = await client.post(path, headers=headers, json=initialize_message())
                    session = opened.headers['mcp-session-id']
                    assert opened.status_code == 200 and session.startswith(names[profile_id] + '-session-'), path
                    called = await client.post(path, headers={**headers, 'Mcp-Session-Id': session},
                                               json=call(2, 'tools_documentation'))
                    assert called.json()['result']['content'][0]['text'] == mock[profile_id].text
                    reached = {key for key, child in mock.items() if len(child.requests) > since[key]}
                    assert reached == {profile_id}, (profile_id, path[:8])
                    sessions[profile_id] = session
            wrong = secrets.token_urlsafe(32)
            log_scan.watch(wrong)
            since = {key: len(child.requests) for key, child in mock.items()}
            assert answer(await client.post('/mcp', headers=bearer(wrong), json=initialize_message())) == (
                BEARER_REQUIRED)
            assert answer(await client.post(f'/private_{wrong}/mcp', headers=ACCEPT,
                                            json=initialize_message())) == NOT_FOUND
            assert all(len(child.requests) == since[key] for key, child in mock.items())
            # B's session with C's token: C's child does not know it (404), and B's child is never asked.
            crossed = await client.post('/mcp', headers=bearer(runtime.token(C), **{'Mcp-Session-Id': sessions[B]}),
                                        json=call(3, 'tools_documentation'))
            assert crossed.status_code == 404 and len(mock[B].requests) == since[B]
        for profile_id, child in mock.items():
            own = stored(runtime.directory(profile_id))['child_token']
            assert {tuple(request.headers.get_list('authorization')) for request in child.requests} == {
                ('Bearer ' + own,)}


@pytest.mark.parametrize('switch', [False, True])
async def test_no_x_n8n_header_reaches_a_child(tmp_path, log_scan, switch):
    """§8.8 #4 (G5-13): n8n-mcp would switch its backend or instance by x-n8n-url, x-n8n-key, x-n8n-mcp-token,
    x-instance-id and x-session-id. The gateway forwards only its own headers and the three session headers, on both
    paths, for every profile, switched on or off: the headers a child gets are HM-01's CHILD_HEADERS."""
    extras = (B,) if switch else ()
    data = setup_profiles(tmp_path, extras=extras)
    children = children_of(data, extras)
    async with multi_profile_runtime(PRODUCT, data, children=children, switch=switch) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        log_scan.watch(N8N_HEADERS['x-n8n-key'], N8N_HEADERS['x-n8n-mcp-token'], kind='secret')
        async with runtime.mcp() as client:
            for profile_id in ('default', *extras):
                token = runtime.token(profile_id)
                for path, headers in (('/mcp', bearer(token, **N8N_HEADERS)),
                                      (f'/private_{token}/mcp', {**ACCEPT, **N8N_HEADERS})):
                    opened = await client.post(path, headers=headers, json=initialize_message())
                    assert opened.status_code == 200
                    session = {**headers, 'Mcp-Session-Id': opened.headers['mcp-session-id']}
                    for message in ({'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
                                    call(3, 'n8n_list_workflows', {'limit': 1})):
                        assert (await client.post(path, headers=session, json=message)).status_code in (200, 202)
                    assert (await client.delete(path, headers=session)).status_code == 200
    seen = [request for child in children.by_port.values() for request in child.requests]
    assert len(seen) > 10
    for request in seen:
        assert set(request.headers) <= CHILD_HEADERS, sorted(set(request.headers) - CHILD_HEADERS)
        assert not any(name.startswith('x-') for name in request.headers)
        assert not any(value in request.headers.values() for value in N8N_HEADERS.values())


async def test_an_additional_profile_without_a_backend_refuses_every_tool(tmp_path, log_scan):
    """DQ-22, T-22: B has no backend: no child is started for it (no request ever reaches its port), the gateway answers
    its initialize and tools/list itself (the whole listing, through its policy), and every tool, the seven
    documentation tools too, is refused as unconfigured (-32603 Backend not configured), never "try again shortly". Its
    panel says unconfigured (health, apply state, the profile list). The default profile, without a backend too, keeps
    its documentation child (its documentation tools are answered by it). C, configured, is served by its child."""
    data = setup_profiles(tmp_path, configured=(C,), default=False)
    children = children_of(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'fresh')  # n8n's default profile: its documentation child is applied
        watch(log_scan, data)
        manager = runtime.manager
        supervisor = manager.get(B).runtime.supervisor
        assert (supervisor.status, supervisor.spec) == ('unconfigured', None)
        assert not profiles.Layout(data).child(B).exists() and n8n_adapter.profile_catalog(B) is None
        assert manager.get(C).runtime.supervisor.status == 'running' and n8n_adapter.profile_catalog(C) is not None
        token = runtime.token(B)
        async with runtime.mcp() as client:
            for path, headers in (('/mcp', bearer(token)), (f'/private_{token}/mcp', dict(ACCEPT))):
                opened = await client.post(path, headers=headers, json=initialize_message())
                assert opened.status_code == 200 and opened.headers['mcp-session-id'].startswith('woow-local-')
                session = {**headers, 'Mcp-Session-Id': opened.headers['mcp-session-id']}
                listed = await client.post(path, headers=session, json={'jsonrpc': '2.0', 'id': 2,
                                                                        'method': 'tools/list'})
                names = [tool['name'] for tool in listed.json()['result']['tools']]
                assert names == [tool['name'] for tool in listing(PRODUCT)] and set(DOCUMENTATION) <= set(names)
                for number, name in enumerate(names):
                    refused = await client.post(path, headers=session, json=call(10 + number, name, well_formed(name)))
                    assert refused.status_code == 200 and refused.json() == {
                        'jsonrpc': '2.0', 'id': 10 + number,
                        'error': {'code': -32603, 'message': 'Backend not configured', 'data': {'tool': name}}}, name
                    assert b'try again' not in refused.content
            default = runtime.token('default')
            opened = await client.post('/mcp', headers=bearer(default), json=initialize_message())
            assert opened.headers['mcp-session-id'].startswith('default-session-')
            documented = await client.post('/mcp', headers=bearer(default, **{
                'Mcp-Session-Id': opened.headers['mcp-session-id']}), json=call(3, 'tools_documentation'))
            assert documented.json()['result']['content'][0]['text'] == children.by_port[3000].text
        assert children.by_port[18000].requests == []
        # Its health check (the monitor's, run now: an additional profile's first one is staggered by 15 s and more)
        # sends nothing and finds it unconfigured, as every other product's profile without a backend.
        await manager.get(B).runtime.health.check()
        assert children.by_port[18000].requests == []
        async with runtime.admin(B) as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
        assert boot['health']['child']['state'] == 'unconfigured' and boot['health']['backend'] == 'unconfigured'
        assert boot['configuration']['apply_state'] == 'unconfigured' and boot['connection_configured'] is False
        async with GENUINE_CLIENT(transport=httpx.ASGITransport(app=runtime.admin_app, client=INGRESS),
                                  base_url='http://admin') as admin:
            rows = (await admin.get('/api/profiles', headers=ADMIN)).json()['profiles']
        assert {row['id']: row['status'] for row in rows} == {'default': 'running', B: 'unconfigured', C: 'running'}


async def test_saving_a_profiles_settings_restarts_only_its_own_child(tmp_path, log_scan):
    """T-07, T-22: B's policy save restarts no child (n8n's policy is the gateway's) and changes B's answers only;
    B's session save restarts B's child only, with B's limits; every profile starts with the 20 sessions and 10 minutes
    of its own state (a new profile never copies another's settings, DQ-02)."""
    data = setup_profiles(tmp_path)
    children = children_of(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        manager = runtime.manager
        supervisors = {profile_id: manager.get(profile_id).runtime.supervisor for profile_id in ('default', B, C)}
        for supervisor in supervisors.values():
            assert (supervisor.spec.env['N8N_MCP_MAX_SESSIONS'], supervisor.spec.env['SESSION_TIMEOUT_MINUTES']) == (
                '20', '10')
        assert all('n8n_session' not in stored(runtime.directory(profile_id)) for profile_id in (B, C))
        starts = {profile_id: supervisor.starts for profile_id, supervisor in supervisors.items()}
        async with runtime.admin(B) as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            policy = {'writes_enabled': boot['writes_enabled'], 'disabled': ['search_nodes'],
                      'enabled_write_tools': boot['enabled_write_tools']}
            saved = await admin.put('/api/policy', json=policy, headers=reviewed_headers(boot, ADMIN))
            assert saved.status_code == 200 and saved.json()['profile'] == {'id': B}
        assert {profile_id: supervisor.starts for profile_id, supervisor in supervisors.items()} == starts
        async with runtime.mcp() as client:
            for profile_id, expected in ((B, 'refused'), (C, 'served'), ('default', 'served')):
                token = runtime.token(profile_id)
                opened = await client.post('/mcp', headers=bearer(token), json=initialize_message())
                answered = await client.post('/mcp', headers=bearer(token, **{
                    'Mcp-Session-Id': opened.headers['mcp-session-id']}), json=call(2, 'search_nodes', {'query': 'x'}))
                body = answered.json()
                assert ('error' in body and body['error']['message'] == 'Unknown tool') == (expected == 'refused')
        async with runtime.admin(B) as admin:
            boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
            session = {'n8n_session': {'timeout_seconds': 900, 'max_sessions': 5}}
            saved = await admin.put('/api/n8n/session', json=session, headers=reviewed_headers(boot, ADMIN))
            assert saved.status_code == 200 and saved.json()['profile'] == {'id': B}
        assert {profile_id: supervisor.starts for profile_id, supervisor in supervisors.items()} == {
            **starts, B: starts[B] + 1}
        assert (supervisors[B].spec.env['N8N_MCP_MAX_SESSIONS'], supervisors[B].spec.env['SESSION_TIMEOUT_MINUTES']) == (
            '5', '15')
        for profile_id in ('default', C):
            assert supervisors[profile_id].spec.env['N8N_MCP_MAX_SESSIONS'] == '20'
        assert 'n8n_session' not in stored(data) and 'n8n_session' not in stored(runtime.directory(C))


async def test_each_profile_runs_on_its_own_catalog_and_its_copy_goes_with_it(tmp_path, log_scan, monkeypatch):
    """DQ-04: B's and C's children read their own copies (the default profile keeps its own, made at start, and its
    HOME, the data directory); deleting B through the panel removes B's copy and B's directory, C's stays."""
    monkeypatch.setattr(profiles, 'port_occupied', lambda port: None)  # tests/owned_network.py: no test bind here
    data = setup_profiles(tmp_path)
    children = children_of(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        manager = runtime.manager
        copies = Path(n8n_adapter.CATALOG_DIR) / 'profiles'
        specs = {profile_id: manager.get(profile_id).runtime.supervisor.spec for profile_id in ('default', B, C)}
        assert {profile_id: spec.env.get('NODE_DB_PATH') for profile_id, spec in specs.items()} == {
            'default': None,  # the harness skips the default profile's 70 MB copy, as HM-01's does
            B: str(copies / B / 'nodes.db'), C: str(copies / C / 'nodes.db')}
        assert {profile_id: spec.env['HOME'] for profile_id, spec in specs.items()} == {
            'default': str(data), B: str(profiles.Layout(data).child(B)), C: str(profiles.Layout(data).child(C))}
        async with GENUINE_CLIENT(transport=httpx.ASGITransport(app=runtime.admin_app, client=INGRESS),
                                  base_url='http://admin') as admin:
            boot = (await admin.get('/api/bootstrap', headers={**ADMIN, 'X-MCP-Profile': 'default'})).json()
            listed = await admin.get('/api/profiles', headers=ADMIN)
            deleted = await admin.delete(f'/api/profiles/{B}', headers={
                **ADMIN, 'X-CSRF-Token': boot['csrf'], 'If-Match': listed.headers['etag'],
                'Idempotency-Key': f'{int(time.time() * 1000) - 1000}.{secrets.token_hex(16)}'})
        assert deleted.status_code == 200 and deleted.json()['deleted'] == B
        assert not (copies / B).exists() and not profiles.Layout(data).profile(B).exists()
        assert (copies / C / 'nodes.db').read_bytes() == CATALOG_STAND_IN and n8n_adapter.profile_catalog(B) is None


async def test_a_profiles_backend_saved_starts_its_child_and_cleared_stops_it(tmp_path, log_scan, monkeypatch):
    """HM-25 correctness review S-1 (T-07, T-22; the usual path: the panel creates a profile without a backend, plan
    4.3) and security review S-8. B is served without a backend: no child, no copy, no child directory. Its backend
    saved through the panel restarts B's runtime only: B's catalog copy made once, in a worker thread, then B's child
    started on its own HOME, copy, backend and --port, and B's token served by it; the default profile's and C's
    children are not restarted. A session save keeps B's copy and the version history in it; another backend (another
    URL and key) gets a new copy before B's child starts again, so nothing taken from the first backend is read through
    the second. The backend cleared stops B's child (no spec) and every tool of B is refused as unconfigured again."""
    data = setup_profiles(tmp_path, configured=(C,))
    children = children_of(data)
    copied = []
    original = asyncio.to_thread

    async def recorded(function, *args, **kwargs):
        if getattr(function, '__name__', None) == 'prepare_profile_catalog':
            copied.append(args[0])
        return await original(function, *args, **kwargs)
    monkeypatch.setattr(n8n_adapter.asyncio, 'to_thread', recorded)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        manager = runtime.manager
        supervisors = {profile_id: manager.get(profile_id).runtime.supervisor for profile_id in ('default', B, C)}
        assert (supervisors[B].status, supervisors[B].spec) == ('unconfigured', None) and copied == [C]
        assert not profiles.Layout(data).child(B).exists() and n8n_adapter.profile_catalog(B) is None
        starts = {profile_id: supervisor.starts for profile_id, supervisor in supervisors.items()}
        copy = Path(n8n_adapter.CATALOG_DIR) / 'profiles' / B / 'nodes.db'
        token = runtime.token(B)

        async def save(path, body):
            async with runtime.admin(B) as admin:
                boot = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
                saved = await admin.put(path, json=body, headers=reviewed_headers(boot, ADMIN))
            assert saved.status_code == 200 and saved.json()['profile'] == {'id': B}, saved.content[:300]

        def restarted(times):
            return {profile_id: supervisor.starts for profile_id, supervisor in supervisors.items()} == {
                **starts, B: starts[B] + times}

        first = {'url': 'https://beta.n8n.invalid', 'key': 'DUMMY-beta-workflow-key'}
        second = {'url': 'https://beta-next.n8n.invalid', 'key': 'DUMMY-beta-next-workflow-key'}
        log_scan.watch(first['key'], second['key'], kind='secret')
        await save('/api/backend', first)
        spec = supervisors[B].spec
        assert copied == [C, B] and supervisors[B].status == 'running' and restarted(1)
        assert spec.cwd == profiles.Layout(data).child(B) and spec.env['HOME'] == str(spec.cwd)
        assert spec.env['NODE_DB_PATH'] == str(copy) and spec.argv[-2:] == ('--port', '18000')
        assert (spec.env['N8N_API_URL'], spec.env['N8N_API_KEY']) == (first['url'], first['key'])
        async with runtime.mcp() as client:
            opened = await client.post('/mcp', headers=bearer(token), json=initialize_message())
        assert opened.status_code == 200 and opened.headers['mcp-session-id'].startswith('p' + B[:4] + '-session-')
        history = b'version snapshots taken from the first backend'  # what n8n-mcp keeps in the copy
        copy.write_bytes(copy.read_bytes() + history)
        await save('/api/n8n/session', {'n8n_session': {'timeout_seconds': 900, 'max_sessions': 5}})
        assert copied == [C, B] and restarted(2) and copy.read_bytes().endswith(history)
        await save('/api/backend', second)
        assert copied == [C, B, B] and restarted(3) and copy.read_bytes() == CATALOG_STAND_IN
        assert supervisors[B].spec.env['NODE_DB_PATH'] == str(copy)
        assert supervisors[B].spec.env['N8N_API_URL'] == second['url']
        await save('/api/backend', {'url': None, 'key': None})
        assert (supervisors[B].status, supervisors[B].spec) == ('unconfigured', None) and restarted(3)
        since = len(children.by_port[18000].requests)
        async with runtime.mcp() as client:
            opened = await client.post('/mcp', headers=bearer(token), json=initialize_message())
            assert opened.headers['mcp-session-id'].startswith('woow-local-')
            session = bearer(token, **{'Mcp-Session-Id': opened.headers['mcp-session-id']})
            for number, name in enumerate(('tools_documentation', 'n8n_list_workflows')):
                refused = await client.post('/mcp', headers=session, json=call(10 + number, name, well_formed(name)))
                assert refused.json()['error'] == {'code': -32603, 'message': 'Backend not configured',
                                                   'data': {'tool': name}}, name
        assert len(children.by_port[18000].requests) == since and copied == [C, B, B]


async def test_a_cleanup_that_leaves_a_copy_is_one_warning_and_the_deletion_stands(tmp_path, log_scan, monkeypatch):
    """HM-25 correctness review S-2, security review S-4 (plan 4.4: a cleanup that fails is one WARNING; PaaS #159
    likewise for the K8s files it keeps in /tmp): the copies' profiles directory is no longer private, so B's copy
    cannot be removed (remove_profile_catalog answers False). Deleting B through the panel still answers 200 and
    removes B's directory; one WARNING names B by its first 8 characters, never a path; C keeps its copy and child."""
    monkeypatch.setattr(profiles, 'port_occupied', lambda port: None)  # tests/owned_network.py: no test bind here
    data = setup_profiles(tmp_path)
    children = children_of(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        copies = Path(n8n_adapter.CATALOG_DIR) / 'profiles'
        starts = runtime.manager.get(C).runtime.supervisor.starts
        os.chmod(copies, 0o755)
        try:
            deleted = await panel_write(runtime, 'DELETE', f'/api/profiles/{B}')
        finally:
            os.chmod(copies, 0o700)
        assert deleted.status_code == 200 and deleted.json()['deleted'] == B
        assert not profiles.Layout(data).profile(B).exists() and (copies / B / 'nodes.db').is_file()
        assert n8n_adapter.profile_catalog(C) == copies / C / 'nodes.db'
        assert runtime.manager.get(C).runtime.supervisor.starts == starts
    assert cleanup_warnings(log_scan) == [
        f'multi-profile: the cleanup after deleting profile {B[:8]} could not remove everything']


async def test_an_orphans_deletion_removes_its_catalog_copy(tmp_path, log_scan, monkeypatch):
    """HM-25 correctness review S-2, security review S-4: an orphan (a profile directory the index does not list, here
    with a copy as if this management process had served it before) deleted through the panel goes with its copy too:
    profile_admin's one delete() runs the product's cleanup after the directory; B is not touched."""
    monkeypatch.setattr(profiles, 'port_occupied', lambda port: None)
    data = setup_profiles(tmp_path, extras=(B,))
    log_scan.watch_state(create_profile(data, PRODUCT, O, label='Orphan Flows', port=18001, indexed=False))
    children = children_of(data, (B,))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        made = n8n_adapter.prepare_profile_catalog(O)
        async with GENUINE_CLIENT(transport=httpx.ASGITransport(app=runtime.admin_app, client=INGRESS),
                                  base_url='http://admin') as admin:
            assert (await admin.get('/api/profiles', headers=ADMIN)).json()['orphans'] == [{'id': O}]
        deleted = await panel_write(runtime, 'DELETE', f'/api/profiles/{O}')
        assert deleted.status_code == 200 and deleted.json()['deleted'] == O
        assert not made.parent.exists() and not profiles.Layout(data).profile(O).exists()
        assert n8n_adapter.profile_catalog(O) is None and n8n_adapter.profile_catalog(B) is not None
    assert cleanup_warnings(log_scan) == []


async def test_a_quarantine_directorys_deletion_removes_the_copy_of_an_id_no_longer_served(tmp_path, log_scan,
                                                                                        monkeypatch):
    """HM-25 correctness review S-2, security review S-4 (profile_admin.delete_quarantined): D's quarantine directory
    deleted through the panel goes with D's copy; a quarantine directory named with B's id while B is served leaves B's
    copy and child alone (the cleanup runs only for an id that is no longer served)."""
    monkeypatch.setattr(profiles, 'port_occupied', lambda port: None)
    data = setup_profiles(tmp_path, extras=(B,))
    log_scan.watch_state(create_profile(data, PRODUCT, D, label='Delta Flows', port=18001, indexed=False))
    layout = profiles.Layout(data)
    names = {D: f'{D}-20261116T093015Z', B: f'{B}-20261116T093016Z'}
    os.rename(layout.profile(D), layout.profiles / (profiles.QUARANTINE_PREFIX + names[D]))
    os.mkdir(layout.profiles / (profiles.QUARANTINE_PREFIX + names[B]), 0o700)
    children = children_of(data, (B,))
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        made = n8n_adapter.prepare_profile_catalog(D)  # as if this management process had served D before
        served = n8n_adapter.profile_catalog(B)
        starts = runtime.manager.get(B).runtime.supervisor.starts
        for profile_id in (D, B):
            deleted = await panel_write(runtime, 'POST', f'/api/profiles/quarantine/{names[profile_id]}/delete')
            assert deleted.status_code == 200 and deleted.json()['deleted'] == names[profile_id], profile_id
        assert not made.parent.exists() and n8n_adapter.profile_catalog(D) is None
        assert served is not None and n8n_adapter.profile_catalog(B) == served
        assert served.read_bytes() == CATALOG_STAND_IN
        assert runtime.manager.get(B).runtime.supervisor.starts == starts
    assert cleanup_warnings(log_scan) == []


# ---- the reply mask (HM-25 security review S-3; plan 5.1 point 8, 8.6; contract 2.7) ----

def echo_children(data, extras=(B, C)):
    children = Children()
    children.add(3000, EchoChild('default', PRODUCT, data))
    for number, profile_id in enumerate(extras):
        children.add(18000 + number, EchoChild('p' + profile_id[:4], PRODUCT,
                                               profiles.Layout(data).profile(profile_id)))
    return children


async def documentation_reply(client, token, ident=5):
    """tools_documentation on the Bearer path: the reply's JSON (an SSE event's data when it comes as one)."""
    opened = await client.post('/mcp', headers=bearer(token), json=initialize_message())
    response = await client.post('/mcp', headers=bearer(token, **{'Mcp-Session-Id': opened.headers['mcp-session-id']}),
                                 json=call(ident, 'tools_documentation'))
    assert response.status_code == 200, response.content[:300]
    if response.headers['content-type'] == 'text/event-stream':
        data, = [line[6:] for line in response.text.splitlines() if line.startswith('data: ')]
        return json.loads(data)
    return response.json()


@pytest.mark.parametrize('framing', ['json', 'sse'])
async def test_an_n8n_reply_never_carries_a_token_the_add_on_holds(tmp_path, log_scan, framing):
    """n8n is served by the ProfileManager from HM-25 on, so its replies get the union mask (the plan's own example: A's
    n8n workflow holding B's secret URL): B's child relays a workflow that holds every token and child token the add-on
    holds (the default profile's, B's, C's), C's secret URL, C's and B's n8n API keys and a value nobody holds. Every
    token is [REDACTED] and so is B's own key (redact.secret_values of B's state, as today); C's key is not in B's mask
    (a backend secret a person chose, plan 5.1 point 8); the value nobody holds is shown. JSON replies and SSE events
    alike."""
    data = setup_profiles(tmp_path)
    children = echo_children(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        layout = profiles.Layout(data)
        b_state, c_state = current(layout.profile(B)), current(layout.profile(C))
        held = all_tokens(data)
        child = children.by_port[18000]
        child.sse = framing == 'sse'
        child.text = (f'workflow note: {" ".join(held)} url=https://ha.invalid/private_{c_state.token}/mcp'
                      f' c_key={c_state.backend_key} b_key={b_state.backend_key} other={UNHELD}')
        async with runtime.mcp() as client:
            shown = (await documentation_reply(client, runtime.token(B)))['result']['content'][0]['text']
        assert shown == masked(child.text, [*held, *redact.secret_values(b_state)])
        assert all(token not in shown for token in held) and len(held) == 6
        assert c_state.backend_key in shown and UNHELD in shown and b_state.backend_key not in shown


async def test_switched_off_an_n8n_reply_is_masked_with_the_profiles_own_credentials(tmp_path, log_scan):
    """Switched off (the repository), the default profile's reply is masked with its own credentials only, as before:
    its token and API key [REDACTED]; a dormant profile's child token on disk and a value nobody holds are shown."""
    data = setup_profiles(tmp_path, extras=(B,))
    children = echo_children(data, extras=())
    async with multi_profile_runtime(PRODUCT, data, children=children, switch=False) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        own = current(data)
        other = stored(profiles.Layout(data).profile(B))['child_token']
        children.by_port[3000].text = f'own {own.token} key {own.backend_key} other {other} unheld {UNHELD}'
        async with runtime.mcp() as client:
            shown = (await documentation_reply(client, runtime.token('default')))['result']['content'][0]['text']
        assert shown == f'own [REDACTED] key [REDACTED] other {other} unheld {UNHELD}'


def test_the_n8n_profile_count_follows_the_memory_limit():
    """PaaS apps/n8n/tests/test_profile_capacity.py (test_n8n_profile_count_tracks_container_limit; §8.8 #19): 2
    additional n8n profiles at most, 300 MiB a child and 256 MiB reserved, so a 512 MiB limit runs none, 1 GiB one
    additional n8n profile and 2 GiB both; the third is the product limit's (profile_limit), the second at 1 GiB the
    memory's."""
    assert profiles.capacity(PRODUCT).limit == 2 and profiles.capacity(PRODUCT).child_memory_mib == 300
    assert [profiles.capacity(PRODUCT, memory).limit for memory in (512, 1024, 2048)] == [0, 1, 2]
    small = profiles.capacity(PRODUCT, 1024)
    assert [small.disabled_reason(position) for position in range(3)] == [None, 'memory_capacity', 'profile_limit']
    assert small.required_memory_mib(2) == 256 + 3 * 300


async def test_a_restore_revokes_every_n8n_profile_and_their_children_start_apart(tmp_path, log_scan):
    """PaaS test_restore_guard_n8n_integration (two n8n profiles restored): a restore of an add-on with n8n profile data
    (the entrypoint's marker) revokes every profile's token, the default profile's included (DQ-03 (b) A2; HM-13b), and
    gives each a new child token; every child then starts again on its own new child token and, for an additional
    profile, its own catalog copy and HOME; no token from before the restore is served."""
    data = setup_profiles(tmp_path)
    before = {profile_id: stored(data if profile_id == 'default' else profiles.Layout(data).profile(profile_id))
              for profile_id in ('default', B, C)}
    watch(log_scan, data)
    os.close(os.open(data / profiles.RESTORE_MARKER_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))
    children = children_of(data)
    async with multi_profile_runtime(PRODUCT, data, children=children) as runtime:
        await settle(runtime, 'configured')
        watch(log_scan, data)
        manager = runtime.manager
        homes, catalogs = set(), set()
        for profile_id in ('default', B, C):
            now = stored(runtime.directory(profile_id))
            assert now['token'] is None and now['child_token'] != before[profile_id]['child_token'], profile_id
            spec = manager.get(profile_id).runtime.supervisor.spec
            assert spec.env['AUTH_TOKEN'] == now['child_token'], profile_id
            homes.add(spec.env['HOME'])
            catalogs.add(spec.env.get('NODE_DB_PATH'))
        assert len(homes) == 3 and len(catalogs) == 3  # the default profile's catalog: None (the harness skips it)
        async with runtime.mcp() as client:
            for profile_id in ('default', B, C):
                token = before[profile_id]['token']
                assert answer(await client.post('/mcp', headers=bearer(token), json=initialize_message())) == (
                    BEARER_REQUIRED)
                assert answer(await client.post(f'/private_{token}/mcp', headers=ACCEPT,
                                                json=initialize_message())) == NOT_FOUND
    assert not (data / profiles.RESTORE_MARKER_NAME).exists()


# ---- UC-01: the real child leaves its HOME empty ----

async def test_the_real_child_of_an_additional_profile_leaves_its_home_empty(tmp_path, log_scan, monkeypatch):
    """The pinned n8n-mcp child of an additional profile, started from its real spec (only its port moved to a private
    one; the loopback fake backend allowed for this test, as tests/loopback_backends.py allows it): a session with the
    documentation tools, a search, a workflow listing on the fake backend and its end. Its HOME and cwd, profiles/<id>/
    child/, are still empty when it stopped (UC-01: so every start may require an empty directory); its argv's --port
    is harmless (it serves on PORT)."""
    from batch2_owned_port import reserve_port
    from owned_network import guarded_env
    from mcp_admin_core.lifecycle import Supervisor
    calls = []

    async def serve(reader, writer):
        try:
            calls.append(await reader.readuntil(b'\r\n\r\n'))
            body = b'{"data":[],"nextCursor":null}'
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n'
                         b'Content-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
            await writer.drain()
        finally:
            writer.close()
    backend = await asyncio.start_server(serve, '127.0.0.1', 0)
    monkeypatch.setattr(features, 'MULTI_PROFILE_PRODUCTS', frozenset({PRODUCT}))
    monkeypatch.setattr(products, 'loopback_refused', lambda product: False)
    monkeypatch.setattr(n8n_adapter, 'CATALOG_DIR', tmp_path / 'catalogs')
    monkeypatch.setattr(n8n_adapter, '_profile_catalogs', {})
    data = tmp_path / 'data'
    ProductStore(data, PRODUCT).close()
    create_profile(data, PRODUCT, B, label=LABELS[B], port=18000, configured=False)
    store = ProductStore(profiles.Layout(data).profile(B), PRODUCT, existing_only=True)
    try:
        state = store.update(backend_url=f'http://127.0.0.1:{backend.sockets[0].getsockname()[1]}',
                             backend_key='DUMMY-uc01-workflow-key')
        directory = Path(store.directory)
    finally:
        store.close()
    log_scan.watch_state(state)
    await n8n_adapter.prepare_child(B, state)
    spec = n8n_adapter.child_spec(state, directory, port=18000)
    with reserve_port() as reservation:
        port = reservation.getsockname()[1]
    assert port not in range(18000, 18100) and port != 3000
    argv = (*spec.argv[:-1], str(port))
    spec = type(spec)(argv, guarded_env({**spec.env, 'PORT': str(port)}), spec.cwd)
    home = profiles.Layout(data).child(B)
    assert spec.cwd == home and spec.env['HOME'] == str(home) and list(home.iterdir()) == []
    manager = Supervisor(spec, retries=0)
    url = f'http://127.0.0.1:{port}/mcp'
    headers = {'Authorization': 'Bearer ' + state.child_token, **ACCEPT}
    try:
        await manager.start()
        async with httpx.AsyncClient(trust_env=False, timeout=30) as client:
            started = time.monotonic()
            while True:
                try:
                    opened = await client.post(url, headers=headers, json=initialize_message())
                    if opened.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert time.monotonic() - started < 60 and manager.status in ('starting', 'running')
                await asyncio.sleep(.25)
            session = {**headers, 'Mcp-Session-Id': opened.headers['mcp-session-id']}
            await client.post(url, headers=session, json={'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            for number, (name, arguments) in enumerate((
                    ('tools_documentation', {}), ('search_nodes', {'query': 'webhook', 'limit': 2}),
                    ('n8n_list_workflows', {'limit': 1}))):
                answered = await client.post(url, headers=session, json=call(2 + number, name, arguments))
                assert answered.status_code == 200, name
            assert (await client.delete(url, headers=session)).status_code in (200, 204)
    finally:
        await manager.stop()
        backend.close()
        await backend.wait_closed()
    assert calls, 'the child never asked its backend'
    assert list(home.iterdir()) == [], sorted(path.name for path in home.rglob('*'))
    assert sorted(path.name for path in directory.iterdir()) == ['.writer.lock', 'child', 'state.json']
