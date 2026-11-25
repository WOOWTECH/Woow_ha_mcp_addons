"""n8n-mcp 2.96.2 (0.3.4; 2.91.0 before): the full tool surface (0.2.0) and the fixed launcher.

2.96.2 lists the same 28 tools with the same descriptions, schemas and annotations as 2.91.0 (tools.js and
tools-n8n-manager.js are byte-identical). Of its new switches child_spec sets only N8N_MCP_VERSION_CHECK_DISABLED=true
(no npm registry query from n8n_health_check, as the PaaS); N8N_MCP_DISABLE_UI_APPS and the per-context
instanceArgument are not set.

HM-25 (multi-profile plan 9 n8n row, 12.3 HM-25; DQ-04, DQ-22, UC-01, UC-09; contract section 9 #28, #47 and HM-25's
rows; unreleased, behind the product switch): an additional profile's child. Which profile a child spec is for is read
from its directory (profile_of: profiles.Layout puts an additional profile at <data>/profiles/<id>); the default
profile's spec is the one before, byte for byte (tests/contract/child_spec_default.json). An additional profile's child
(only while n8n is switched on, features.enabled read at each call):
- starts only with a backend (DQ-22): without one child_spec answers None, as the other products' do, and the gateway
  refuses each of its tools as unconfigured (profiles.documentation_child);
- works in <data>/profiles/<id>/child/ (its HOME and cwd: never the profile directory with its state.json), made 0700
  when missing and required to be an empty directory, not a link, whenever its spec is built (a start, a save, the
  panel's restart, a re-evaluation; the watchdog's automatic restarts reuse the spec, as for the Python children)
  (UC-01: n8n-mcp 2.96.2 writes nothing there with N8N_MCP_TELEMETRY_DISABLED=true, its only HOME writer being the
  telemetry config; tests/test_n8n_multi_profile.py runs the real child);
- reads its own copy of the node catalog, <CATALOG_DIR>/profiles/<id>/nodes.db (DQ-04: outside /data, not in backups;
  UC-09: with one shared file every profile would see, roll back and delete the others' workflow version backups, which
  n8n-mcp scopes by instance_id '' in this single-tenant mode). prepare_child makes it in a worker thread before the
  child's first start (run_product's ProfileManager awaits it), and again once the profile's backend changed (another
  URL or key: the snapshots taken from one backend are never read by the holder of the next; HM-25 security review
  S-8); remove_profile_catalog removes it with the profile. Without its own copy when its spec is built, the child does
  not start (never the default profile's copy or the packaged file);
- names its port on its command line as well (--port N after the entry, which n8n-mcp does not read: it listens on
  PORT), so the P9 kit and the container probe tell the children apart without reading their environment (HM-16
  review SF-2). The default profile's child keeps its argv (no --port: port 3000, as the Hermes and OpenDesign
  launchers' default).
"""
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import stat
from typing import Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.json_schema import SkipJsonSchema

from mcp_admin_core import features, products, profiles
from mcp_admin_core.config import State
from mcp_admin_core.lifecycle import CHILD_PORT, ChildSpec, child_port_text, child_url
from mcp_admin_core.policy import Tool


class Arguments(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Documentation(Arguments):
    topic: str = Field(default="overview", min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_]+$")
    depth: Literal["essentials", "full"] = "essentials"


class Search(Arguments):
    query: str = Field(min_length=1, max_length=256)
    limit: int = Field(default=20, ge=1, le=100)


class ListWorkflows(Arguments):
    limit: int = Field(default=20, ge=1, le=100)
    # None is an internal omission sentinel, not accepted client input. Keep it
    # out of both the public schema and serialized calls to the pinned handler.
    active: bool | SkipJsonSchema[None] = Field(
        default=None, exclude_if=lambda value: value is None,
        json_schema_extra=lambda schema: schema.pop("default", None),
        description="Optional boolean filter; omit for all workflows. Null is invalid.",
    )

    @field_validator("active")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("active must be a boolean when supplied")
        return value


class DeleteWorkflow(Arguments):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")


# All other upstream tools/arguments (including mixed-action tools) are denied.
TOOLS = {
    "tools_documentation": Tool(Documentation),
    "search_nodes": Tool(Search),
    "n8n_list_workflows": Tool(ListWorkflows),
    "n8n_delete_workflow": Tool(DeleteWorkflow, write=True, legacy_write=True),
}
from mcp_admin_core.expansion import N8N_TOOLS
TOOLS.update(N8N_TOOLS)
from mcp_admin_core.batch2 import N8N_TOOLS as BATCH2_TOOLS
TOOLS.update(BATCH2_TOOLS)
from mcp_admin_core.n8n_b3 import N8N_TOOLS as B3_TOOLS
TOOLS.update(B3_TOOLS)
# The 0.1.x bounded surface above stays importable (its models are still tested); since 0.2.0 the add-on serves the
# pinned n8n-mcp's complete surface: all 28 tools, the child's own schemas and validation (surface.full_tools).
BOUNDED_TOOLS = TOOLS
from mcp_admin_core.surface import full_tools
TOOLS = full_tools("n8n")
CHILD_URL = child_url()  # HM-04: the default profile's child; child_url(port) is another profile's

# Unreleased (0.4.12 line). n8n-mcp keeps its local workflow version history (table workflow_versions: the backups taken before
# an update or autofix, n8n_workflow_versions) in the same SQLite file as its node catalog, nodes.db. In the image that file is
# root-owned and the child runs as uid 10001. sql.js loaded it into memory, so writes worked (and were lost with the process; its
# attempt to save them back failed unseen). Native better-sqlite3 opens an unwritable file read-only, and the first INSERT into
# workflow_versions fails with "attempt to write a readonly database". So the child gets a private working copy, as the PaaS
# image does (NODE_DB_PATH): made once when the management process starts (run.py), kept across child restarts, outside /data so
# it is not part of backups, gone with the container like the in-memory history was, and always the catalog of the running image.
# HM-25 (DQ-04): an additional profile's copy is <CATALOG_DIR>/profiles/<id>/nodes.db, made the same way before its child's
# first start in this management process (prepare_child), again for another backend, and removed with the profile
# (remove_profile_catalog).
CATALOG_DIR = Path("/tmp/woow-n8n-mcp")
PACKAGED_CATALOG = Path(__file__).parent / "node_modules/n8n-mcp/data/nodes.db"
PROFILE_CATALOGS = "profiles"
_catalog = None
logger = logging.getLogger(__name__)


class _Copy(NamedTuple):
    """HM-25: what this management process made for an additional profile."""
    path: Path  # <CATALOG_DIR>/profiles/<id>/nodes.db
    backend: str | None  # backend_of() of the state it was made for (None: made without one)
    identity: tuple  # the file's (st_dev, st_ino): its path must still lead to it (profile_catalog)


_profile_catalogs = {}  # additional profile id -> its _Copy


def _copy(source, directory):
    """source copied to <directory>/nodes.db (0600, replaced atomically, fsynced); the path, or None when the copy is
    short. OSError when it cannot be made. directory is checked by the caller."""
    target, temporary = directory / "nodes.db", directory / f".nodes.db.{os.getpid()}.tmp"
    try:
        with open(source, "rb") as origin, os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as copy:
            shutil.copyfileobj(origin, copy, 1024 * 1024)
            copy.flush()
            os.fsync(copy.fileno())
        if temporary.stat().st_size != source.stat().st_size:
            return None
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def prepare_catalog(directory=CATALOG_DIR, source=None):
    """Copy the packaged nodes.db to <directory>/nodes.db (directory 0700, file 0600, replaced atomically) and make the next
    child_spec() hand it to n8n-mcp. Returns the path, or None when the package has no database or the copy cannot be made
    (the child then reads the packaged file: search works, version history writes fail). Never follows a link."""
    global _catalog
    _catalog = None
    source = Path(source) if source is not None else PACKAGED_CATALOG
    directory = Path(directory)
    try:
        if source.is_symlink() or not source.is_file():
            return None
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = os.lstat(directory)
        if directory.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
            return None  # not our private directory
        target = _copy(source, directory)
        if target is None:
            return None
    except OSError:
        return None
    _catalog = target
    return target


def profile_of(directory) -> str:
    """HM-25: whose child a spec is for: the id of the additional profile whose store directory this is (profiles.Layout:
    <data>/profiles/<id>), else the default profile."""
    directory = Path(directory)
    if directory.parent.name == profiles.PROFILES_NAME and profiles.is_profile_id(directory.name):
        return directory.name
    return profiles.DEFAULT_PROFILE


def _private_directory(name, directory=None):
    """HM-25: name (in the directory open as the descriptor directory; a path when None) opened without following a
    link: its descriptor when it is a directory of this uid that no one else may enter, else None (closed again).
    OSError when it cannot be opened (a link, not a directory, missing)."""
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        os.close(fd)
        return None
    return fd


def _copy_into(source, directory):
    """HM-25: source copied to nodes.db in the directory open as the descriptor directory, never through a path: 0600,
    fsynced, replaced atomically. The copy's (st_dev, st_ino), or None when it is short. OSError when it cannot be
    made."""
    temporary = f".nodes.db.{os.getpid()}.tmp"
    try:
        with open(source, "rb") as origin, os.fdopen(os.open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600,
                dir_fd=directory), "wb") as copy:
            shutil.copyfileobj(origin, copy, 1024 * 1024)
            copy.flush()
            os.fsync(copy.fileno())
            made = os.fstat(copy.fileno())
            if made.st_size != os.fstat(origin.fileno()).st_size:
                return None
        os.replace(temporary, "nodes.db", src_dir_fd=directory, dst_dir_fd=directory)
        return made.st_dev, made.st_ino
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def _identity(path):
    """(st_dev, st_ino) of the regular file path leads to, its last name not a link; else None."""
    try:
        info = os.stat(path)
        if Path(path).is_symlink() or not stat.S_ISREG(info.st_mode):
            return None
    except OSError:
        return None
    return info.st_dev, info.st_ino


def backend_of(state):
    """HM-25 security review S-8: which backend a copy's version history comes from, a digest of the configured URL and
    key (the key is never kept as text): another URL or another key (another n8n user) is another backend."""
    return hashlib.sha256(json.dumps([state.backend_url, state.backend_key]).encode()).hexdigest()


def prepare_profile_catalog(profile_id, *, root=None, source=None, backend=None):
    """HM-25 (DQ-04): the packaged nodes.db copied to <root>/profiles/<profile_id>/nodes.db (root: CATALOG_DIR), as
    prepare_catalog copies the default profile's: every directory 0700 and this uid's, never a link, the file 0600,
    replaced atomically. Each directory is opened without following a link and checked, the next one is made and opened
    in it, and the file is written and renamed in the last one through its descriptor (HM-25 security review S-6: the
    way remove_profile_catalog removes it), so a directory changed after its check is never written through. Recorded
    for this process with the backend it is made for (backend: backend_of(state); profile_catalog). Returns the path, or
    None when it cannot be made or its path no longer leads to it (the profile's child then does not start)."""
    if not profiles.is_profile_id(profile_id):
        raise ValueError('not an additional profile id')
    _profile_catalogs.pop(profile_id, None)
    root = Path(CATALOG_DIR if root is None else root)
    source = Path(PACKAGED_CATALOG if source is None else source)
    opened = []
    try:
        if source.is_symlink() or not source.is_file():
            return None
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory = None
        for name in (root, PROFILE_CATALOGS, profile_id):
            if directory is not None:
                try:
                    os.mkdir(name, 0o700, dir_fd=directory)
                except FileExistsError:
                    pass
            directory = _private_directory(name, directory)
            if directory is None:
                return None  # not our private directory
            opened.append(directory)
        identity = _copy_into(source, directory)
        target = root / PROFILE_CATALOGS / profile_id / "nodes.db"
        if identity is None or _identity(target) != identity:
            return None  # short, or its path leads elsewhere now
    except OSError:
        return None
    finally:
        for fd in opened:
            os.close(fd)
    _profile_catalogs[profile_id] = _Copy(target, backend, identity)
    return target


def profile_catalog(profile_id):
    """The copy this process made for an additional profile (prepare_profile_catalog), while its path still leads to
    that file (a regular file, its last name not a link); else None."""
    made = _profile_catalogs.get(profile_id)
    if made is None or _identity(made.path) != made.identity:
        return None
    return made.path


async def prepare_child(profile_id, state):
    """HM-25: before an additional profile's child spec is built (run_product's ProfileManager awaits it whenever it
    builds one: a start, a save, the panel's restart, a re-evaluation): its catalog copy, made once in this management
    process for the backend it serves (later starts keep it and its version history, as the default profile's), in a
    worker thread so that the 67 MiB copy and its fsync never stall the event loop every profile shares. Made again
    when the profile's backend changed (another URL or key; HM-25 security review S-8): the version snapshots taken from
    one backend are never read through the next (a profile handed over to another backend's holder). Nothing without a
    backend (no child starts, DQ-22). A copy that cannot be made is named once (the id's first 8 characters); the spec
    then refuses to start the child."""
    if not state.configured:
        return
    backend = backend_of(state)
    made = _profile_catalogs.get(profile_id)
    if made is not None and made.backend == backend and profile_catalog(profile_id) is not None:
        return
    if await asyncio.to_thread(prepare_profile_catalog, profile_id, backend=backend) is None:
        logger.warning('n8n: profile %s: no catalog copy could be made; its child does not start',
                       profiles.log_id(profile_id))


def remove_profile_catalog(profile_id, *, root=None):
    """HM-25: a deleted profile's catalog copy and its directory removed (run_product's profile_removed), never following a
    link: <root>/profiles opened without following one and checked as this uid's private directory, shutil.rmtree's
    descriptor-based walk below it. True when nothing of it is left, False when something could not be removed (it is
    outside /data and goes with the container; ProfileManager.removed names it in one WARNING)."""
    if not profiles.is_profile_id(profile_id):
        raise ValueError('not an additional profile id')
    _profile_catalogs.pop(profile_id, None)
    root = Path(CATALOG_DIR if root is None else root)
    try:
        top = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    try:
        try:
            fd = os.open(PROFILE_CATALOGS, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=top)
        except FileNotFoundError:
            return True
        try:
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                return False
            try:
                entry = os.lstat(profile_id, dir_fd=fd)
            except FileNotFoundError:
                return True
            if not stat.S_ISDIR(entry.st_mode) or not shutil.rmtree.avoids_symlink_attacks:
                return False
            shutil.rmtree(profile_id, dir_fd=fd)
            return True
        finally:
            os.close(fd)
    except OSError:
        return False
    finally:
        os.close(top)


def child_spec(state: State, directory: Path, port: int = CHILD_PORT) -> ChildSpec | None:
    # HM-04: port is the child's loopback port, its PORT (the default profile's child: CHILD_PORT, the former spec).
    listen = child_port_text(port)
    # HM-25: an additional profile's child (see the module docstring); the default profile's spec is the former one.
    profile = profile_of(directory)
    additional = profile != profiles.DEFAULT_PROFILE
    if additional:
        if not features.enabled("n8n"):
            raise RuntimeError("n8n serves no additional profile")
        if not state.configured and not profiles.documentation_child("n8n", profile):
            return None  # DQ-22: no backend, no child (no fabricated runtime, no restart loop)
    entry = Path(__file__).parent / "node_modules/n8n-mcp/dist/mcp/index.js"
    node = shutil.which("node")
    if node is None or not entry.is_file():
        raise RuntimeError("pinned n8n runtime not installed")
    home, catalog = directory, (_catalog if _catalog is not None and _catalog.is_file() else None)
    if additional:
        # Its own empty working directory (HOME and cwd), never the profile directory with its state.json (C2-SF-8).
        # Checked here, when the spec is built; the watchdog's automatic restarts reuse the spec (as the Python
        # children's: products.child_spec).
        home = Path(directory) / "child"
        home.mkdir(mode=0o700, exist_ok=True)
        if home.is_symlink() or not home.is_dir() or any(home.iterdir()):
            raise RuntimeError("child working directory must be empty and non-symlink")
        catalog = profile_catalog(profile)
        if catalog is None:
            raise RuntimeError("no catalog copy of the profile's own")  # never another profile's (UC-09)
    # Never inherit parent secrets/proxy variables/NODE_OPTIONS or user env.
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(home),
        "NODE_ENV": "production", "MCP_MODE": "http", "HOST": "127.0.0.1", "PORT": listen,
        "AUTH_TOKEN": state.child_token, "N8N_MCP_TELEMETRY_DISABLED": "true",
        # 0.3.4 (n8n-mcp 2.96.2, as the PaaS): n8n_health_check reports the version check as "disabled" instead of querying
        # the npm registry. The environment is built here, never inherited, so nothing outside can turn it back on.
        "N8N_MCP_VERSION_CHECK_DISABLED": "true",
        "LOG_LEVEL": "error", "DISABLE_CONSOLE_OUTPUT": "true",
        "N8N_MCP_MAX_SESSIONS": "20", "SESSION_TIMEOUT_MINUTES": "10",
    }
    if hasattr(state, 'effective_n8n_session'):
        session = state.effective_n8n_session
        env.update(N8N_MCP_MAX_SESSIONS=str(session.max_sessions),
                   SESSION_TIMEOUT_MINUTES=str(session.timeout_minutes))
    if state.backend_url and state.backend_key:
        env.update(N8N_API_URL=state.backend_url, N8N_API_KEY=state.backend_key)
        # 0.2.1: n8n's instance-level MCP key, optional; without it the official-MCP features are NOT_CONFIGURED.
        if getattr(state, "mcp_access_token", None):
            env["N8N_MCP_ACCESS_TOKEN"] = state.mcp_access_token
    if products.loopback_refused("n8n"):
        # HM-20 (multi-profile plan 8.7, DQ-10; unreleased, behind the product switch): backend_policy.cjs refuses
        # every loopback answer for the configured instance (its API and its official MCP endpoint) and, since the
        # HM-25 security review S-1 (owner decision 2026-11-25), for the connections of n8n_test_workflow's webhook, chat
        # and form clients too (their agents come from SSRFProtection.createPinnedAgents); the mode below stays.
        env[products.DENY_LOOPBACK_ENV] = "1"
    # 0.2.1 (owner decision 2026-10-15): n8n-mcp's widest webhook/URL mode (dist/utils/ssrf-protection.js): any
    # address, private and loopback included (only cloud metadata names stay blocked), so n8n_test_workflow can reach
    # an n8n on the HA network. The configured API backend keeps its own DNS-pinned agents (backend_policy.cjs).
    # Kept as it is by the owner on 2026-11-15 (DQ-10) and again on 2026-11-25 after the independent security review
    # (HM-25 S-1): the validators stay permissive, and only once n8n is switched on the connection to this add-on itself
    # (loopback) is refused, as above; the LAN stays reachable.
    env["WEBHOOK_SECURITY_MODE"] = "permissive"
    if catalog is not None:
        # the private writable copy made at start-up (prepare_catalog), or the additional profile's own (prepare_child)
        env["NODE_DB_PATH"] = str(catalog)
    policy = Path(__file__).with_name("backend_policy.cjs").resolve()
    argv = (node, "--require", str(policy), str(entry.resolve()))
    if not additional:
        return ChildSpec(argv, env, directory)
    return ChildSpec((*argv, "--port", listen), env, home)
