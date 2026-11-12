"""Read HA ProductState on every call; a raw loopback MCP caller gets no bypass."""
from __future__ import annotations

from dataclasses import dataclass
import hmac
import json
import os
from pathlib import Path
import re
import stat
from typing import get_args

from mcp_admin_core.config import strict_json
from mcp_admin_core.products import Product, ProductState, STORED_FIELDS

from .errors import HeadscaleError
from .http_policy import normalize_base_url
from .native import NATIVE_OPERATIONS
from .registry import OPERATION_POLICIES, TASK_NATIVE, TOOL_REGISTRY, normalize_arguments

MAX_STATE_BYTES = 65536  # HA Store.load's limit
OPTIONAL_FIELDS = frozenset(ProductState.model_fields) - STORED_FIELDS
WRITE_GRANTS = frozenset(
    name if OPERATION_POLICIES[name].parameter is None else f"{name}:{operation}"
    for spec in TOOL_REGISTRY for name in (spec.name,)
    for operation in spec.operations
    if (native := TASK_NATIVE[name, operation]) is not None and not NATIVE_OPERATIONS[native].read_only
)
_NAME = re.compile(r"[A-Za-z0-9_]{1,128}\Z")
_OPERATION = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")


@dataclass(frozen=True)
class PolicySnapshot:
    disabled: frozenset[str]
    grants: frozenset[str]
    denied: dict[str, frozenset[str]]


class SavedPolicy:
    def __init__(self, path, client):
        self.path = Path(path) if path else None
        self.client = client
        if (self.path is None or not self.path.is_absolute() or self.path.name != "state.json"
                or any(parent.is_symlink() for parent in (self.path.parent, *self.path.parent.parents))):
            raise HeadscaleError("HEADSCALE_POLICY_UNAVAILABLE")

    def read(self) -> PolicySnapshot:
        try:
            directory = self.path.parent
            directory_info = directory.lstat()
            if (not stat.S_ISDIR(directory_info.st_mode)
                    or directory_info.st_uid != os.geteuid()
                    or stat.S_IMODE(directory_info.st_mode) != 0o700):
                raise ValueError()
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                before = os.fstat(fd)
                current = self.path.lstat()
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                        or before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) != 0o600
                        or before.st_size > MAX_STATE_BYTES
                        or (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)):
                    raise ValueError()
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    raw = stream.read(MAX_STATE_BYTES + 1)
                after = os.fstat(fd)
                if (len(raw) > MAX_STATE_BYTES or
                        (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size) !=
                        (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size)):
                    raise ValueError()
                value = strict_json(raw)
            finally:
                os.close(fd)
            if (not isinstance(value, dict) or set(value) - OPTIONAL_FIELDS != STORED_FIELDS
                    or any(value[key] is None for key in set(value) & OPTIONAL_FIELDS)
                    or type(value.get("schema_version")) is not int or value["schema_version"] != 4
                    or value.get("product") != "headscale"):
                raise ValueError()
            # Once HA core registers Headscale, use its full ProductState
            # validation too. The projection below remains explicit so this
            # child can be verified independently before that core lands.
            if "headscale" in get_args(Product):
                ProductState.model_validate(value)
            connection = value["connection"]
            if (not isinstance(connection, dict) or set(connection) != {"url", "api_key"}
                    or not isinstance(connection["url"], str)
                    or not isinstance(connection["api_key"], str)
                    or not hmac.compare_digest(normalize_base_url(connection["url"]), self.client.base_url)
                    or not hmac.compare_digest(connection["api_key"], self.client._api_key)
                    or value["backend_url"] is not None or value["backend_key"] is not None
                    or value["mcp_access_token"] is not None
                    or type(value["writes_enabled"]) is not bool
                    or (value["token"] is not None and not isinstance(value["token"], str))
                    or (value["token"] is not None and not _TOKEN.fullmatch(value["token"]))
                    or not isinstance(value["child_token"], str)
                    or not _TOKEN.fullmatch(value["child_token"])):
                raise ValueError()
            disabled, grants, denied = value["disabled"], value["enabled_write_tools"], value["denied_operations"]
            if (not isinstance(disabled, list) or len(disabled) > 256
                    or any(type(name) is not str or not _NAME.fullmatch(name) for name in disabled)
                    or len(disabled) != len(set(disabled))
                    or not isinstance(grants, list) or len(grants) > 256
                    or any(type(grant) is not str or grant not in WRITE_GRANTS for grant in grants)
                    or len(grants) != len(set(grants))
                    or not isinstance(denied, dict) or len(denied) > 256
                    or len(json.dumps(denied, separators=(",", ":"))) > 16384):
                raise ValueError()
            for name, operations in denied.items():
                if (type(name) is not str or not _NAME.fullmatch(name)
                        or not isinstance(operations, list) or not 1 <= len(operations) <= 128
                        or any(type(op) is not str or not _OPERATION.fullmatch(op) for op in operations)
                        or len(operations) != len(set(operations))):
                    raise ValueError()
            return PolicySnapshot(frozenset(disabled), frozenset(grants),
                                  {name: frozenset(ops) for name, ops in denied.items()})
        except Exception:
            # Never return a permissive default, a file path, a URL or a key.
            raise HeadscaleError("HEADSCALE_POLICY_UNAVAILABLE") from None

    def allows_operation(self, name, operation, snapshot=None):
        snapshot = self.read() if snapshot is None else snapshot
        spec = OPERATION_POLICIES.get(name)
        if spec is None or operation not in spec.operations:
            return False
        # The parent has a private, fixed, read-only health probe. It may be
        # publicly disabled, but the child must keep it callable for probing.
        if name == "headscale_health":
            return True
        if name in snapshot.disabled or spec.requirements(operation) & snapshot.denied.get(name, frozenset()):
            return False
        native = TASK_NATIVE[name, operation]
        if native is None or NATIVE_OPERATIONS[native].read_only:
            return True
        grant = name if spec.parameter is None else f"{name}:{operation}"
        return grant in snapshot.grants

    def require(self, name, arguments):
        args = normalize_arguments(name, arguments)
        spec = OPERATION_POLICIES[name]
        operation = args.get("operation", spec.default)
        if not self.allows_operation(name, operation):
            raise HeadscaleError("HEADSCALE_POLICY_DENIED")
