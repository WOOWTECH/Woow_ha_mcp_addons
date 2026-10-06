"""Pinned child contracts. No arbitrary commands/env or legacy admin imports.

The W2b allowlists are deliberately bounded; docs/tool-surface.json enumerates
all upstream tools and the individually deferred capabilities.
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
    # module requires an ALREADY installed MCP backend module; no full YOLO.
    mode: Literal['read', 'module'] = 'read'


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
    schema_version: int = 3
    enabled_write_tools: list[str] = Field(default_factory=list)
    product: Product
    connection: OdooConnection | ManageConnection | HermesConnection | OpenDesignConnection | EmqxConnection | LiteLLMConnection | None = Field(default=None, repr=False)

    @field_validator('schema_version')
    @classmethod
    def version(cls, value):
        if value != 3:
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

    @model_validator(mode='after')
    def reviewed_grants(self):
        if self.product == 'n8n':
            from .expansion import N8N_GRANTS
            allowed = N8N_GRANTS
        else:
            allowed = {g for name, tool in TOOLS[self.product].items() for g in tool.grants(name)}
        if self.product == 'odoo-manage' and self.enabled_write_tools and (self.connection is None or self.connection.mode != 'module'):
            raise ValueError('Manage writers require existing MCP module mode; never full YOLO')
        if len(set(self.enabled_write_tools)) != len(self.enabled_write_tools) or set(self.enabled_write_tools) - set(allowed):
            raise ValueError('unknown or wrong-product write grant')
        return self

    @property
    def configured(self):
        return bool(self.backend_url and self.backend_key) if self.product == 'n8n' else self.connection is not None


class ProductStore(Store):
    """Explicit v1 n8n / v2 product -> v3 grants migration; never downgrade.

    Construction-only migration under the exclusive writer lock. All legacy
    fields are validated and preserved; new grants are empty. The legacy global
    switch still applies ONLY to n8n_delete_workflow and delete_project. Restore
    a protected compatible backup to roll back, never rewrite version in place.
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
        if isinstance(value, dict) and type(value.get('schema_version')) is int and value['schema_version'] == 2:
            if not self._migrate or set(value) != set(ProductState.model_fields) - {'enabled_write_tools'}:
                raise ValueError('incomplete legacy state or unexpected downgrade')
            # Validate every legacy field before any durable replacement.
            value = {**value, 'schema_version': 3, 'enabled_write_tools': []}
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
                   'delete_project': Tool(Project, write=True, legacy_write=True)},
    'emqx': {name: Tool(Arguments) for name in ('emqx_cluster_status', 'emqx_broker_stats', 'emqx_metrics_current')},
    'litellm': {name: Tool(Arguments) for name in ('litellm_list_models', 'litellm_health_readiness')},
}
from .expansion import expand_tools
expand_tools(TOOLS)
from .batch2 import expand_tools as expand_batch2
expand_batch2(TOOLS)
from .odoo_b2 import TOOLS as ODOO_B2_TOOLS
TOOLS['odoo'].update(ODOO_B2_TOOLS)

# Each product's representative public read (tests, container acceptance). HealthMonitor uses health_probe(): Odoo
# and Odoo Manage have private authentication-only probes instead (RC review notes, 0.1.3 #6 and 0.1.4 #7).
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
        return isinstance(payload.get('models'), list) and (
            (payload.get('yolo_mode') or {}).get('operations', {}).get('read') is True
            or any(isinstance(m, dict) and m.get('model') == 'res.partner'
                   and m.get('operations', {}).get('read') is True for m in payload['models']))
    if product == 'hermes':
        return isinstance(payload.get('capabilities'), dict) and 'capabilities_error' not in payload
    if product == 'opendesign':
        # 0.1.4: OpenDesign 0.21.1 answers {"ok": true, "version": "0.21.1"} (0.1.3 HA regression); older builds used
        # status. A present status or ok must agree (RC review #8: {"ok": true, "status": "unhealthy"} is not healthy).
        if 'status' in payload and payload['status'] not in ('ok', 'healthy'):
            return False
        if 'ok' in payload:
            version = payload.get('version')
            return (payload['ok'] is True and isinstance(version, str)
                    and re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}', version) is not None)
        return 'status' in payload
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


# HealthMonitor's backend probe. Odoo's and (0.1.4) Odoo Manage's are private to the child (apps/odoo*/launch.py,
# not in TOOLS): they run on their own owned thread, never the tool path, and only authenticate (no ir.model access).
ODOO_HEALTH_PROBE = 'woow_backend_probe'
PRIVATE_PROBES = ('odoo', 'odoo-manage')


def health_probe(product):
    return (ODOO_HEALTH_PROBE, {}) if product in PRIVATE_PROBES else PROBES[product]


def health_probe_success(product, payload):
    if product in PRIVATE_PROBES:
        # Odoo's authenticate answer: a positive user id (it answers False for rejected credentials).
        return isinstance(payload, dict) and set(payload) == {'uid'} and type(payload['uid']) is int and payload['uid'] > 0
    return probe_success(product, payload)


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
                   ODOO_YOLO='off' if c.mode == 'module' else 'read', ODOO_MCP_ENABLE_METHOD_CALLS='false', ODOO_MCP_TRANSPORT='streamable-http')
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
        # FastMCP's banner otherwise performs a public PyPI lookup and writes
        # HOME/version-cache state, breaking the intentionally clean restart CWD.
        env.update(FASTMCP_CHECK_FOR_UPDATES='off', FASTMCP_SHOW_SERVER_BANNER='false')
        from .native_inventory import NAMES
        from .policy import enabled
        public_allowed = {name for name in TOOLS[product] if enabled(name, TOOLS[product], state)}
        # Private loopback registration also serves HealthMonitor, independently
        # of public disables. Reserve ONLY the fixed, argument-free read probe:
        # EMQX GET /nodes or LiteLLM GET /v1/models (never provider /health).
        # Parent authorize/filter_list still enforce every public disable; raw
        # child tools/list is intentionally not the public authorization surface.
        native_allowed = public_allowed | {health_probe(product)[0]}  # the probe HealthMonitor actually calls
        prefix = 'EMQX_MCP_' if product == 'emqx' else 'LITELLM_MCP_'
        env[prefix + 'READONLY'] = 'false' if any(TOOLS[product][name].write for name in public_allowed) else 'true'
        env[prefix + 'DISABLED_TOOLS'] = ','.join(sorted(set(NAMES[product]) - native_allowed))
        argv = (str(python), '-m', module, '--transport', 'http', '--host', '127.0.0.1', '--port', '3000', '--path', '/mcp')
    return ChildSpec(argv, env, cwd)
