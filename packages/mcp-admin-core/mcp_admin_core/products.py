"""Pinned W2a child contracts. No arbitrary commands/env or legacy admin imports.

The tool allowlists are intentionally partial; docs/tool-surface.json enumerates
all upstream tools, including those withheld pending W2b review.
"""
from pathlib import Path
import re
import secrets
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, AfterValidator, field_validator, model_validator

from .config import State, Store, http_url
from .lifecycle import ChildSpec
from .policy import Tool

PRODUCTS = ('odoo', 'odoo-manage', 'hermes', 'opendesign', 'emqx', 'litellm')
Product = Literal['n8n', 'odoo', 'odoo-manage', 'hermes', 'opendesign', 'emqx', 'litellm']
ROOT = Path(__file__).resolve().parents[3]
URL = Annotated[str, AfterValidator(http_url)]


def credential(value):
    if not value or len(value) > 8192 or any(not 32 <= ord(c) <= 126 for c in value):
        raise ValueError('invalid credential')
    return value


Credential = Annotated[str, AfterValidator(credential)]
Name = Annotated[str, Field(min_length=1, max_length=256, pattern=r'^[A-Za-z0-9_@. -]+$')]


class Connection(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class OdooConnection(Connection):
    url: URL
    database: Name
    username: Name
    password: Credential = Field(repr=False)


class ManageConnection(Connection):
    url: URL
    database: Name
    username: Name
    api_key: Credential = Field(repr=False)
    # Only the source-backed XML-RPC read mode; no backend module installation.
    mode: Literal['read'] = 'read'


class HermesConnection(Connection):
    gateway_url: URL
    gateway_api_key: Credential = Field(repr=False)
    dashboard_url: URL | None = None
    dashboard_username: Name | None = None
    dashboard_password: Credential | None = Field(default=None, repr=False)

    @model_validator(mode='after')
    def dashboard_complete(self):
        values = (self.dashboard_url, self.dashboard_username, self.dashboard_password)
        if any(v is not None for v in values) and not all(v is not None for v in values):
            raise ValueError('incomplete dashboard connection')
        return self


class OpenDesignConnection(Connection):
    url: URL  # Upstream sends no backend Authorization header.


class EmqxConnection(Connection):
    url: URL
    api_key: Credential = Field(repr=False)
    api_secret: Credential = Field(repr=False)

    @field_validator('url')
    @classmethod
    def base_only(cls, value):
        if value.endswith('/api/v5'):
            raise ValueError('provide broker base without /api/v5')
        return value


class LiteLLMConnection(Connection):
    url: URL
    master_key: Credential = Field(repr=False)


CONNECTIONS = dict(zip(PRODUCTS, (OdooConnection, ManageConnection, HermesConnection,
                                  OpenDesignConnection, EmqxConnection, LiteLLMConnection)))


class ProductState(State):
    schema_version: int = 2
    product: Product
    connection: OdooConnection | ManageConnection | HermesConnection | OpenDesignConnection | EmqxConnection | LiteLLMConnection | None = Field(default=None, repr=False)

    @field_validator('schema_version')
    @classmethod
    def version(cls, value):
        if value != 2:
            raise ValueError('unsupported schema')
        return value

    @model_validator(mode='before')
    @classmethod
    def typed_connection(cls, value):
        if not isinstance(value, dict):
            return value
        product = value.get('product')
        connection = value.get('connection')
        if product == 'n8n':
            if connection is not None:
                raise ValueError('n8n retains v1 backend fields')
        elif product in CONNECTIONS:
            if value.get('backend_url') is not None or value.get('backend_key') is not None:
                raise ValueError('product uses typed connection only')
            if connection is not None:
                value = {**value, 'connection': CONNECTIONS[product].model_validate(connection)}
        return value

    @property
    def configured(self):
        return bool(self.backend_url and self.backend_key) if self.product == 'n8n' else self.connection is not None


class ProductStore(Store):
    """Explicit v1 n8n -> v2 migration; old Store refuses v2 (no lossy rollback).

    Migration only at construction, under the existing exclusive writer lock.
    Full v1 validation precedes durable replacement. Restore a protected v1 backup
    to roll back the executable; never downgrade a v2 file in place.
    """
    def __init__(self, directory, product):
        if product not in (*PRODUCTS, 'n8n'):
            raise ValueError('unknown product')
        self.product = product
        self._migrate = True
        self._migrated = False
        super().__init__(directory)
        try:
            if self._migrated:
                self._write(self.load())
        except Exception:
            self.close()
            raise
        finally:
            self._migrate = False

    def _initial_state(self):
        return ProductState(product=self.product, token=secrets.token_urlsafe(32), child_token=secrets.token_urlsafe(32))

    def _decode(self, value):
        if isinstance(value, dict) and type(value.get('schema_version')) is int and value['schema_version'] == 1:
            if not self._migrate or self.product != 'n8n':
                raise ValueError('wrong product or unexpected downgrade')
            old = super()._decode(value)
            value = {**old.model_dump(), 'schema_version': 2, 'product': 'n8n', 'connection': None}
            self._migrated = True
        if not isinstance(value, dict) or set(value) != set(ProductState.model_fields) or value.get('product') != self.product:
            raise ValueError('wrong product or incomplete schema')
        return ProductState.model_validate(value)


class Arguments(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')


class Models(Arguments):
    instance: Literal['default'] | None = None
    limit: int = Field(default=20, ge=1, le=100)
    query: str | None = Field(default=None, max_length=128)


class Inspect(Arguments):
    target: Literal['capabilities', 'status']


class SkillList(Arguments):
    action: Literal['list']
    name: None = None


class Toolsets(Arguments):
    action: Literal['list'] = 'list'
    toolset: None = None


class Gateway(Arguments):
    action: Literal['status'] = 'status'


class ModelInfo(Arguments):
    action: Literal['info', 'list_providers'] = 'info'
    model: None = None
    provider: None = None


class Project(Arguments):
    project_id: str = Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


class FileInfo(Project):
    file_path: str = Field(min_length=1, max_length=256, pattern=r'^[A-Za-z0-9_. /-]+$')

    @field_validator('file_path')
    @classmethod
    def relative(cls, value):
        if any(part in ('', '.', '..') for part in value.split('/')):
            raise ValueError('relative non-traversing path required')
        return value


TOOLS = {
    'odoo': {'health_check': Tool(Arguments), 'list_models': Tool(Models)},
    'odoo-manage': {'list_models': Tool(Arguments)},
    'hermes': {'hermes_inspect': Tool(Inspect), 'hermes_skill': Tool(SkillList),
               'hermes_tools': Tool(Toolsets), 'hermes_gateway': Tool(Gateway), 'hermes_model': Tool(ModelInfo)},
    'opendesign': {**{name: Tool(Arguments) for name in ('health', 'version', 'list_agents', 'list_projects', 'list_plugins', 'list_skills')},
                   'get_project': Tool(Project), 'list_project_files': Tool(Project), 'get_file_info': Tool(FileInfo),
                   'delete_project': Tool(Project, write=True)},
    'emqx': {name: Tool(Arguments) for name in ('emqx_cluster_status', 'emqx_broker_stats', 'emqx_metrics_current')},
    'litellm': {name: Tool(Arguments) for name in ('litellm_list_models', 'litellm_health_readiness')},
}
PROBES = {'odoo': ('list_models', {'limit': 1}), 'odoo-manage': ('list_models', {}),
          'hermes': ('hermes_inspect', {'target': 'capabilities'}), 'opendesign': ('health', {}),
          'emqx': ('emqx_cluster_status', {}), 'litellm': ('litellm_list_models', {})}


def probe_success(product, payload):
    """Source-backed success shapes, never 'HTTP 200 means backend ready'."""
    if not isinstance(payload, dict) or payload.get('error') is not None:
        return False
    if product == 'odoo':
        return payload.get('success') is True and isinstance(payload.get('result'), list)
    if product == 'odoo-manage':
        return isinstance(payload.get('models'), list) and payload.get('yolo_mode', {}).get('operations', {}).get('read') is True
    if product == 'hermes':
        return isinstance(payload.get('capabilities'), dict) and 'capabilities_error' not in payload
    if product == 'opendesign':
        return payload.get('status') in ('ok', 'healthy')
    if product == 'emqx':
        nodes = payload.get('nodes')
        return (type(payload.get('node_count')) is int and isinstance(nodes, list) and bool(nodes)
                and payload['node_count'] == len(nodes)
                and all(isinstance(n, dict) and n.get('error') is None
                        and isinstance(n.get('node'), str) and re.fullmatch(r'[^@\s]+@[^@\s]+', n['node'])
                        and isinstance(n.get('version'), str) and bool(n['version'].strip()) for n in nodes)
                and len({n['node'] for n in nodes}) == len(nodes))
    if product == 'litellm':
        return isinstance(payload.get('data'), list)
    return False


def child_spec(state: ProductState, directory: Path) -> ChildSpec | None:
    if not state.configured:
        return None  # no fabricated runtime / fallback credentials / restart loops
    product = state.product
    if product not in PRODUCTS:
        raise ValueError('use the n8n adapter for n8n')
    app = ROOT / 'apps' / product
    python = app / '.venv/bin/python'
    if not python.is_file():
        raise RuntimeError('pinned child environment not installed')
    # Dedicated empty working directory, not GUI state, source checkout or HOME.
    cwd = directory / 'child'
    cwd.mkdir(mode=0o700, exist_ok=True)
    if cwd.is_symlink() or any(cwd.iterdir()):
        raise RuntimeError('child working directory must be empty and non-symlink')
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(cwd), 'PYTHONDONTWRITEBYTECODE': '1',
           'PYTHONUNBUFFERED': '1', 'PYTHONPATH': str(app / 'vendor') + ':' + str(ROOT / 'apps/runtime')}
    c = state.connection
    if product == 'odoo':
        env.update(ODOO_URL=c.url, ODOO_DB=c.database, ODOO_USERNAME=c.username, ODOO_PASSWORD=c.password,
                   ODOO_TRANSPORT='xmlrpc', ODOO_VERIFY_SSL='1', ODOO_TIMEOUT='5',
                   ODOO_MCP_ENABLE_WRITES='0', ODOO_MCP_ALLOW_UNKNOWN_METHODS='0', MCP_CHATTER_DIRECT='0')
        argv = (str(python), str(app / 'launch.py'), '--transport', 'streamable-http', '--host', '127.0.0.1', '--port', '3000', '--path', '/mcp')
    elif product == 'odoo-manage':
        env.update(ODOO_URL=c.url, ODOO_DB=c.database, ODOO_USER=c.username, ODOO_API_KEY=c.api_key,
                   ODOO_YOLO='read', ODOO_MCP_ENABLE_METHOD_CALLS='false', ODOO_MCP_TRANSPORT='streamable-http')
        argv = (str(python), str(app / 'launch.py'), '--transport', 'streamable-http', '--host', '127.0.0.1', '--port', '3000')
    elif product in ('hermes', 'opendesign'):
        if product == 'hermes':
            env.update(HERMES_GATEWAY_URL=c.gateway_url, HERMES_GATEWAY_API_KEY=c.gateway_api_key)
            if c.dashboard_url:
                env.update(HERMES_DASHBOARD_URL=c.dashboard_url, HERMES_DASHBOARD_USERNAME=c.dashboard_username,
                           HERMES_DASHBOARD_PASSWORD=c.dashboard_password)
        else:
            env['OD_API_BASE'] = c.url
        argv = (str(python), str(app / 'launch.py'))
    else:
        if product == 'emqx':
            env.update(EMQX_MCP_BASE_URL=c.url, EMQX_MCP_API_KEY=c.api_key, EMQX_MCP_API_SECRET=c.api_secret, EMQX_MCP_READONLY='true')
            module = 'emqx_mcp_server.server'
        else:
            env.update(LITELLM_MCP_BASE_URL=c.url, LITELLM_MCP_MASTER_KEY=c.master_key, LITELLM_MCP_READONLY='true')
            module = 'woow_litellm_mcp_server.server'
        argv = (str(python), '-m', module, '--transport', 'http', '--host', '127.0.0.1', '--port', '3000', '--path', '/mcp')
    return ChildSpec(argv, env, cwd)
