"""Unreleased (0.4.12 line): the n8n child writes its workflow version history to a private copy of the catalog database.

n8n-mcp keeps `workflow_versions` (the backup taken before an update or autofix, n8n_workflow_versions) in nodes.db, the same
SQLite file as its node catalog. In the image that file is root-owned and the child runs as uid 10001. sql.js worked on an in-memory
copy; native better-sqlite3 opens an unwritable file read-only, so the first INSERT would fail. prepare_catalog() makes a private
working copy (0700 directory, 0600 file) and child_spec() hands it over as NODE_DB_PATH, as the PaaS image does.
"""
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

import pytest

import n8n_adapter
from mcp_admin_core.config import Store

PACKAGED = Path(__file__).resolve().parents[1] / "apps/n8n/node_modules/n8n-mcp/data/nodes.db"


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "state")
    yield value
    value.close()


@pytest.fixture(autouse=True)
def no_catalog_left_behind(monkeypatch):
    monkeypatch.setattr(n8n_adapter, "_catalog", None)


def test_child_spec_names_the_copy_only_after_it_was_made(tmp_path, store):
    source = tmp_path / "packaged.db"
    source.write_bytes(b"SQLite format 3\0" + b"x" * 5000)
    assert "NODE_DB_PATH" not in n8n_adapter.child_spec(store.load(), store.path.parent).env  # nothing prepared: the packaged file
    target = n8n_adapter.prepare_catalog(tmp_path / "work", source)
    assert target == tmp_path / "work/nodes.db" and target.read_bytes() == source.read_bytes()
    assert (tmp_path / "work").stat().st_mode & 0o777 == 0o700 and target.stat().st_mode & 0o777 == 0o600  # (a setgid parent adds 0o2000)
    assert n8n_adapter.child_spec(store.load(), store.path.parent).env["NODE_DB_PATH"] == str(target)


def test_the_copy_is_replaced_atomically_and_leaves_nothing_behind(tmp_path):
    source = tmp_path / "packaged.db"
    source.write_bytes(b"first" * 1000)
    n8n_adapter.prepare_catalog(tmp_path / "work", source)
    source.write_bytes(b"second image's catalog" * 1000)
    target = n8n_adapter.prepare_catalog(tmp_path / "work", source)
    assert target.read_bytes() == source.read_bytes()  # a new image always starts from its own catalog
    assert sorted(path.name for path in (tmp_path / "work").iterdir()) == ["nodes.db"]


def test_nothing_unsafe_is_copied_or_followed(tmp_path, store):
    real = tmp_path / "real.db"
    real.write_bytes(b"data" * 100)
    (tmp_path / "link.db").symlink_to(real)
    assert n8n_adapter.prepare_catalog(tmp_path / "w1", tmp_path / "link.db") is None  # a link as the source
    assert n8n_adapter.prepare_catalog(tmp_path / "w2", tmp_path / "missing.db") is None  # no database in the package
    (tmp_path / "open").mkdir(mode=0o755)
    os.chmod(tmp_path / "open", 0o755)
    assert n8n_adapter.prepare_catalog(tmp_path / "open", real) is None  # a directory others can enter is not ours
    (tmp_path / "elsewhere").mkdir(mode=0o700)
    (tmp_path / "dirlink").symlink_to(tmp_path / "elsewhere")
    assert n8n_adapter.prepare_catalog(tmp_path / "dirlink", real) is None
    assert list((tmp_path / "elsewhere").iterdir()) == []
    assert "NODE_DB_PATH" not in n8n_adapter.child_spec(store.load(), store.path.parent).env  # a failed copy never names a path


VERSIONS = r"""
const path = require('path');
const [pkg] = process.argv.slice(1);
const { createDatabaseAdapter } = require(path.join(pkg, 'dist/database/database-adapter.js'));
const { NodeRepository } = require(path.join(pkg, 'dist/database/node-repository.js'));
(async () => {
  const out = {};
  try {
    const db = await createDatabaseAdapter(process.env.NODE_DB_PATH || path.join(pkg, 'data/nodes.db'));
    out.adapter = db.constructor.name;
    const repo = new NodeRepository(db);
    const make = (n) => ({ instanceId: 'i', workflowId: 'w', versionNumber: n, workflowName: 'v' + n, workflowSnapshot: { n }, trigger: 'partial_update' });
    out.ids = [1, 2, 3].map((n) => Number(repo.createWorkflowVersion(make(n))));
    out.pruned = repo.pruneWorkflowVersions('w', 1, 'i');
    out.missing = repo.deleteWorkflowVersion(2147483000, 'i');
    out.one = repo.deleteWorkflowVersion(Number(repo.createWorkflowVersion(make(9))), 'i');
    out.all = repo.deleteWorkflowVersionsByWorkflowId('w', 'i');
    db.close();
  } catch (error) { out.error = String(error).slice(0, 200); }
  process.stdout.write(JSON.stringify(out));
})();
"""


def versions_flow(spec, env):
    package = Path(spec.argv[-1]).parents[2]  # …/node_modules/n8n-mcp
    result = subprocess.run([spec.argv[0], "-e", VERSIONS, str(package)], env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_version_history_is_written_natively_on_the_copy_of_a_database_the_child_cannot_write(tmp_path, store):
    image = tmp_path / "image-nodes.db"
    shutil.copyfile(PACKAGED, image)
    image.chmod(0o444)  # root-owned and read-only for the child, as in the image
    spec = n8n_adapter.child_spec(store.load(), store.path.parent)
    no_copy = {key: value for key, value in spec.env.items() if key != "NODE_DB_PATH"}
    # Why the copy exists: without it the native engine opens the unwritable file read-only and the first write fails.
    # Only an unprivileged user can be shown that: root writes through a 0444 file (CI runs this suite as root), so the
    # premise is checked when the suite runs as the child would (any non-root uid) and the rest of the test runs for both.
    if os.geteuid() != 0:
        unwritable = versions_flow(spec, {**no_copy, "NODE_DB_PATH": str(image)})
        assert unwritable["adapter"] == "BetterSQLiteAdapter" and "readonly database" in unwritable["error"]
    # With the private copy the flow works and the counters are the real ones (sql.js reported ids 0 and one change per DELETE).
    n8n_adapter.prepare_catalog(tmp_path / "work", image)
    flow = versions_flow(spec, n8n_adapter.child_spec(store.load(), store.path.parent).env)
    assert flow["adapter"] == "BetterSQLiteAdapter" and "error" not in flow, flow
    assert flow["ids"] == sorted(set(flow["ids"])) and flow["ids"][0] > 0
    assert (flow["pruned"], flow["missing"], flow["one"], flow["all"]) == (2, 0, 1, 1)
    assert stat.S_IMODE(image.stat().st_mode) == 0o444  # the packaged file is never touched
