"""n8n-mcp 2.96.2 (0.3.4; 2.91.0 before): the full tool surface (0.2.0) and the fixed launcher.

2.96.2 lists the same 28 tools with the same descriptions, schemas and annotations as 2.91.0 (tools.js and
tools-n8n-manager.js are byte-identical). Of its new switches child_spec sets only N8N_MCP_VERSION_CHECK_DISABLED=true
(no npm registry query from n8n_health_check, as the PaaS); N8N_MCP_DISABLE_UI_APPS and the per-context
instanceArgument are not set.
"""
from pathlib import Path
import shutil
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.json_schema import SkipJsonSchema

from mcp_admin_core.config import State
from mcp_admin_core.lifecycle import ChildSpec
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
CHILD_URL = "http://127.0.0.1:3000/mcp"


def child_spec(state: State, directory: Path) -> ChildSpec:
    entry = Path(__file__).parent / "node_modules/n8n-mcp/dist/mcp/index.js"
    node = shutil.which("node")
    if node is None or not entry.is_file():
        raise RuntimeError("pinned n8n runtime not installed")
    # Never inherit parent secrets/proxy variables/NODE_OPTIONS or user env.
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(directory),
        "NODE_ENV": "production", "MCP_MODE": "http", "HOST": "127.0.0.1", "PORT": "3000",
        "AUTH_TOKEN": state.child_token, "N8N_MCP_TELEMETRY_DISABLED": "true",
        # 0.3.4 (n8n-mcp 2.96.2, as the PaaS): n8n_health_check reports the version check as "disabled" instead of querying
        # the npm registry. The environment is built here, never inherited, so nothing outside can turn it back on.
        "N8N_MCP_VERSION_CHECK_DISABLED": "true",
        "LOG_LEVEL": "error", "DISABLE_CONSOLE_OUTPUT": "true",
        "N8N_MCP_MAX_SESSIONS": "20", "SESSION_TIMEOUT_MINUTES": "10",
    }
    if state.backend_url and state.backend_key:
        env.update(N8N_API_URL=state.backend_url, N8N_API_KEY=state.backend_key)
        # 0.2.1: n8n's instance-level MCP key, optional; without it the official-MCP features are NOT_CONFIGURED.
        if getattr(state, "mcp_access_token", None):
            env["N8N_MCP_ACCESS_TOKEN"] = state.mcp_access_token
    # 0.2.1 (owner decision 2026-10-15): n8n-mcp's widest webhook/URL mode (dist/utils/ssrf-protection.js): any
    # address, private and loopback included (only cloud metadata names stay blocked), so n8n_test_workflow can reach
    # an n8n on the HA network. The configured API backend keeps its own DNS-pinned agents (backend_policy.cjs).
    env["WEBHOOK_SECURITY_MODE"] = "permissive"
    policy = Path(__file__).with_name("backend_policy.cjs").resolve()
    return ChildSpec((node, "--require", str(policy), str(entry.resolve())), env, directory)
