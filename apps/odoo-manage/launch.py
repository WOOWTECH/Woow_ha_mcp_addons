"""Scoped, source-guarded XMLRPC transport replacement; wheel stays unmodified."""
import hashlib
import os
from pathlib import Path
import runpy

from backend_policy import XMLTransport, sync_client, public_backend_error
import mcp_server_odoo.access_control as access
import re

if hashlib.sha256(Path(access.__file__).read_bytes()).hexdigest() != '6001ec627491f1e1c6fa04e2eeddf126d92d4b811c8f9603676e021dbe92359a':
    raise RuntimeError('Manage access transport requires source review')


def module_request(self, endpoint, timeout, allow_session_retry):
    # API-key mode only. No urllib, redirects, session/password fallback or
    # arbitrary endpoint. Existing module/ACLs remain authoritative.
    if not self.config.api_key or self.auth_method == 'password':
        raise access.AccessControlUnavailableError('BACKEND_AUTH_REQUIRED')
    if not re.fullmatch(r'/mcp/models(?:/res\.partner/access)?', endpoint):
        raise access.AccessControlUnavailableError('BACKEND_PATH_DENIED')
    try:
        with sync_client(base_url=self.base_url, timeout=5, headers={
            'X-API-Key': self.config.api_key, 'X-Odoo-Database': self.database,
        }) as client:
            data = client.get(endpoint).json()
        if not isinstance(data, dict) or data.get('success') is not True or not isinstance(data.get('data'), dict):
            raise ValueError()
        if endpoint.endswith('/access'):
            detail = data['data']
            if detail.get('model') != 'res.partner' or type(detail.get('enabled')) is not bool:
                raise ValueError()
            operations = detail.get('operations')
            if not isinstance(operations, dict) or any(type(operations.get(op)) is not bool for op in ('read', 'create', 'write', 'unlink')):
                raise ValueError()
        return data
    except Exception as exc:
        raise access.AccessControlUnavailableError(public_backend_error(exc)) from None


access.AccessController._do_request = module_request

import mcp_server_odoo.odoo_connection as connection
if hashlib.sha256(Path(connection.__file__).read_bytes()).hexdigest() != 'ebf31be7f21390beff402f267a30110ec3af9071b0e41bb1c453620a399d7a75':
    raise RuntimeError('Manage authentication transport requires source review')


def module_authenticate(self, database):
    try:
        with sync_client(base_url=self.config.url, timeout=5, headers={
            'X-API-Key': self.config.api_key, 'X-Odoo-Database': database,
        }) as client:
            data = client.get('/mcp/auth/validate').json()
        detail = data.get('data', {})
        if data.get('success') is not True or detail.get('valid') is not True or type(detail.get('user_id')) is not int or detail['user_id'] < 1:
            return False
        self._uid = detail['user_id']
        self._database = database
        self._auth_method = 'api_key'
        self._authenticated = True
        return True
    except Exception as exc:
        raise connection.OdooConnectionError(public_backend_error(exc)) from None


connection.OdooConnection._authenticate_api_key_mcp = module_authenticate
import mcp_server_odoo.performance as performance

if hashlib.sha256(Path(performance.__file__).read_bytes()).hexdigest() != '34f476a3c41de0daa653c3bb35b6d95468c8ef7e4a12b4d912222e0987df7b19':
    raise RuntimeError('Manage transport requires source review')


class BackendTransport(XMLTransport):
    def __init__(self, database=None, timeout=None, context=None, **kwargs):
        super().__init__(os.environ['ODOO_URL'], timeout=min(timeout or 5, 5), database=database)


performance.OdooTransport = BackendTransport
performance.OdooSafeTransport = BackendTransport

# Narrow the real handler results before their declared output models serialize.
import functools
import mcp_server_odoo.tools as tools
from batch2_outputs import manage_counts, resource_templates

if hashlib.sha256(Path(tools.__file__).read_bytes()).hexdigest() != '5569568a6c86306d19bc4194ef7aeb504a238c4b8dba4d7fc809002104737249':
    raise RuntimeError('Manage B1 handlers require source review')


def projected_handler(original, projection):
    @functools.wraps(original)
    async def projected(self, *args, **kwargs):
        return projection(await original(self, *args, **kwargs))
    return projected


for name, projection in (('_handle_aggregate_records_tool', manage_counts),
                         ('_handle_list_resource_templates_tool', resource_templates)):
    setattr(tools.OdooToolHandler, name, projected_handler(getattr(tools.OdooToolHandler, name), projection))

class MessageResponseError(ValueError):
    """Decoded message_post result cannot identify one genuine message."""


def message_id(raw):
    # Pinned handler accepts int or a list, but would silently use the first
    # element (even bool). Validate BEFORE that coercion, never invent an ID.
    value = raw[0] if type(raw) is list and len(raw) == 1 else raw
    if type(value) is not int or not 1 <= value <= 2147483647:
        raise MessageResponseError('BACKEND_INVALID_RESPONSE')
    return value


execute_kw = connection.OdooConnection.execute_kw


@functools.wraps(execute_kw)
def checked_execute_kw(self, model, method, args, kwargs):
    raw = execute_kw(self, model, method, args, kwargs)
    if model == 'res.partner' and method == 'message_post':
        message_id(raw)
    return raw


connection.OdooConnection.execute_kw = checked_execute_kw
post_message = tools.OdooToolHandler._handle_post_message_tool


@functools.wraps(post_message)
async def bounded_post_message(self, *args, **kwargs):
    try:
        result = await post_message(self, *args, **kwargs)
        if type(result) is not dict or result.get('success') is not True:
            raise MessageResponseError('BACKEND_INVALID_RESPONSE')
        return {'success': True, 'message_id': message_id(result.get('message_id'))}
    except Exception as exc:
        # Pinned handler wraps typed ACL/connection errors with explicit causes.
        # Walk only that bounded cause chain; no text matching or repr/str of it.
        code = 'BACKEND_UNAVAILABLE'
        cause = exc
        for _ in range(4):
            if isinstance(cause, MessageResponseError):
                code = public_backend_error(cause)
                break
            if isinstance(cause, access.AccessControlUnavailableError):
                break
            if isinstance(cause, access.AccessControlError):
                code = 'BACKEND_ACCESS_DENIED'
                break
            cause = cause.__cause__
            if cause is None:
                break
        raise tools.ValidationError(code) from None
    # CancelledError/GeneratorExit/process signals are BaseException, not caught.


tools.OdooToolHandler._handle_post_message_tool = bounded_post_message

if __name__ == '__main__':
    import mcp_server_odoo.server as server
    if hashlib.sha256(Path(server.__file__).read_bytes()).hexdigest() != '4dec3375d722e2eb6af054949be31e66ca35f1713bbc1908398d46f35c09b4fe':
        raise RuntimeError('Manage server requires source review')
    from bounded_tools import OwnedWorkers
    # HealthMonitor's private probe (0.1.4), as for Odoo: not in TOOLS, so the gateway neither lists nor authorizes
    # it. A fresh connection (own transport and pool, never the shared session connection) connects and
    # authenticates on its own owned thread; the uid is the only result. list_models needed ir.model read access,
    # so a least-privilege account always read as unreachable (0.1.3 HA regression).
    probe_worker = OwnedWorkers(1, 'backend-probe')
    server_init = server.OdooMCPServer.__init__

    @functools.wraps(server_init)
    def init_with_probe(self, *args, **kwargs):
        server_init(self, *args, **kwargs)
        config = self.config

        def authenticate():
            odoo = connection.OdooConnection(config, performance_manager=performance.PerformanceManager(config))
            try:
                odoo.connect()
                odoo.authenticate()
                return odoo.uid
            finally:
                odoo.disconnect(suppress_logging=True)

        async def woow_backend_probe():
            try:
                uid = await probe_worker.run(authenticate)
            except Exception:
                raise ValueError('BACKEND_UNAVAILABLE') from None
            return {'uid': uid}

        self.app.add_tool(woow_backend_probe, name='woow_backend_probe', description='Add-on readiness probe (private).')
        if self.app._tool_manager.get_tool('woow_backend_probe').fn is not woow_backend_probe:
            raise RuntimeError('readiness probe name taken')  # add_tool keeps an existing tool of the same name

    server.OdooMCPServer.__init__ = init_with_probe
    try:
        runpy.run_module('mcp_server_odoo', run_name='__main__')
    finally:
        probe_worker.close()
