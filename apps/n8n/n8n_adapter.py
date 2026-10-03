"""n8n-mcp 2.91.0: intentionally narrow, source-audited policy and fixed launcher."""
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
    "n8n_delete_workflow": Tool(DeleteWorkflow, write=True),
}
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
        "LOG_LEVEL": "error", "DISABLE_CONSOLE_OUTPUT": "true",
        "N8N_MCP_MAX_SESSIONS": "20", "SESSION_TIMEOUT_MINUTES": "10",
    }
    if state.backend_url and state.backend_key:
        env.update(N8N_API_URL=state.backend_url, N8N_API_KEY=state.backend_key)
    policy = Path(__file__).with_name("backend_policy.cjs").resolve()
    return ChildSpec((node, "--require", str(policy), str(entry.resolve())), env, directory)
