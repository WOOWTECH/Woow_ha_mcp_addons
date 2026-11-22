"""Fail-closed, profile-bound EMQX policy for direct child MCP requests."""
import hmac
import os
from pathlib import Path
import stat

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware
from mcp_admin_core.config import strict_json
from mcp_admin_core.policy import Denied, authorize, policy_enabled
from mcp_admin_core.products import ProductState, STORED_FIELDS, TOOLS

MAX_STATE_BYTES = 65536
PROBE = 'emqx_cluster_status'
OPTIONAL = frozenset(ProductState.model_fields) - STORED_FIELDS


class SavedPolicy:
    def __init__(self, path, settings):
        self.path = Path(path)
        self.settings = settings

    def read(self):
        try:
            path = self.path
            if (not path.is_absolute() or path.name != 'state.json'
                    or any(p.is_symlink() for p in (path.parent, *path.parent.parents))):
                raise ValueError()
            directory = path.parent.lstat()
            if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.geteuid()
                    or stat.S_IMODE(directory.st_mode) != 0o700):
                raise ValueError()
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                before = os.fstat(fd)
                current = path.lstat()
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.geteuid()
                        or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size > MAX_STATE_BYTES
                        or (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)):
                    raise ValueError()
                with os.fdopen(fd, 'rb', closefd=False) as stream:
                    raw = stream.read(MAX_STATE_BYTES + 1)
                after = os.fstat(fd)
                if (len(raw) > MAX_STATE_BYTES or
                        (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size) !=
                        (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size)):
                    raise ValueError()
                value = strict_json(raw)
            finally:
                os.close(fd)
            if (not isinstance(value, dict) or set(value) - OPTIONAL != STORED_FIELDS
                    or any(value[key] is None for key in set(value) & OPTIONAL)):
                raise ValueError()
            state = ProductState.model_validate(value)
            c = state.connection
            if (state.product != 'emqx' or not state.configured
                    or not hmac.compare_digest(c.url.encode(), self.settings.base_url.encode())
                    or not hmac.compare_digest(c.api_key.encode(), self.settings.api_key.encode())
                    or not hmac.compare_digest(c.api_secret.encode(), self.settings.api_secret.encode())
                    or not hmac.compare_digest(state.child_token, os.environ.get('WOOW_MCP_CHILD_TOKEN', ''))):
                raise ValueError()
            return state
        except Exception:
            raise ToolError('EMQX_POLICY_UNAVAILABLE') from None


class PolicyMiddleware(Middleware):
    def __init__(self, path, settings):
        self.policy = SavedPolicy(path, settings)

    async def on_list_tools(self, context, call_next):
        state = self.policy.read()
        tools = await call_next(context)
        return [tool for tool in tools if tool.name == PROBE or policy_enabled(tool.name, TOOLS['emqx'], state)]

    async def on_call_tool(self, context, call_next):
        state = self.policy.read()
        name = context.message.name
        arguments = context.message.arguments or {}
        if name == PROBE and arguments == {}:
            return await call_next(context)
        try:
            tool = TOOLS['emqx'].get(name)
            # The mixed tools require an explicit, audited selector even when
            # every operation is currently granted.
            if tool and tool.selector and tool.operations:
                operation = arguments.get(tool.selector, tool.default_operation)
                if type(operation) is not str or operation not in tool.operations:
                    raise Denied('invalid operation')
            authorize({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                       'params': {'name': name, 'arguments': arguments}}, TOOLS['emqx'], state)
        except (Denied, AttributeError, TypeError):
            raise ToolError('EMQX_POLICY_DENIED') from None
        return await call_next(context)
