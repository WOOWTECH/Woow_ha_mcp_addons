"""0.1.8 (RR-03): read_record answers "Record not found" for a missing record also when it reads only 'id'.

Odoo's read() of no field but 'id' fetches nothing from the database, so it answers [{'id': n}] for any n, a deleted
record included, and the pinned read_record (odoo_mcp.tools_read, source-guarded by launch.py) then reports success
(woowtech-ha M2a, 2026-10-10: ODOO-RR-03 and RR-03b). Any other field makes Odoo fetch the row and read() leaves a
missing record out, which the handler reports as not found; so only after a successful read of no field but 'id' this
asks Odoo whether the record exists: search_count on its id with active_test off (read() does not hide archived
records), with the caller's own credential and record rules (a record they hide is not found, as a read of any other
field reports it). A missing record gets the handler's own not-found answer; a failed or malformed count fails the call
with one of the transport's fixed codes only (public_failure), never exception text.
"""
import functools
import hashlib
from pathlib import Path
import re

# Fixed codes the pinned transport raises (backend_policy); native handlers report them as str(exc). (0.2.0: moved here
# from the removed odoo_b2_scope, which bounded the B2 tools to res.partner.)
PUBLIC_FAILURES = frozenset({'BACKEND_RPC_FAULT', 'BACKEND_TIMEOUT', 'BACKEND_UNAVAILABLE', 'BACKEND_BUSY',
                             'BACKEND_DESTINATION_DENIED', 'BACKEND_STREAM_ERROR', 'BACKEND_INVALID_RESPONSE'})


def public_failure(report):
    """The error of a native failure report when it is exactly one fixed transport code, else None.

    Anything else (exception text, partial data) stays hidden behind BACKEND_RESPONSE_INVALID.
    """
    if type(report) is dict and report.get('success') is False:
        error = report.get('error')
        if type(error) is str and (error in PUBLIC_FAILURES
                                   or re.fullmatch(r'BACKEND_HTTP_ERROR status=[1-5][0-9]{2}', error)):
            return error
    return None

ID_ONLY = frozenset({'id'})
# The pinned sources this depends on: the handler it wraps and the client resolution it repeats.
SOURCES = {
    'tools_read': '4c8bf33b35c54757b93f0cc367b4f5027488ca8fbf63f68c1241f1a4be784de0',
    'server_core': '7b4e2a03a25447f151f7459883af7721814da310afeb5b55e5aa94b9b8c78641',  # 0.2.0: PaaS-patched
}


def needs_check(report):
    """True for a successful native read whose fields were only 'id' (once or more)."""
    if type(report) is not dict or report.get('success') is not True:
        return False
    used = report.get('fields_used')
    return type(used) is list and bool(used) and set(used) <= ID_ONLY


def checked(original):
    @functools.wraps(original)
    def read_record(**kwargs):
        report = original(**kwargs)
        if not needs_check(report):
            return report
        model, record_id = kwargs['model'], kwargs['record_id']
        try:
            from odoo_mcp.server_core import _resolve_odoo
            _, odoo = _resolve_odoo(kwargs['ctx'], kwargs.get('instance'))
            count = odoo.execute_method(model, 'search_count', [['id', '=', record_id]],
                                        context={'active_test': False})
        except Exception as e:  # a fixed transport code (e.g. BACKEND_RPC_FAULT), never the exception text
            failure = {'success': False, 'error': str(e)}
            return {'success': False, 'error': public_failure(failure) or 'BACKEND_RESPONSE_INVALID'}
        if type(count) is not int or count not in (0, 1):
            return {'success': False, 'error': 'BACKEND_RESPONSE_INVALID'}
        if count == 0:
            return {'success': False, 'error': f'Record not found: {model} ID {record_id}'}
        return report
    return read_record


def guard_sources():
    import odoo_mcp
    root = Path(odoo_mcp.__file__).parent
    for module, digest in SOURCES.items():
        if hashlib.sha256((root / (module + '.py')).read_bytes()).hexdigest() != digest:
            raise RuntimeError('read_record requires source review')


def install(mcp):
    """Wrap the registered read_record; before BoundedTools, which moves sync handlers to its worker."""
    guard_sources()
    from odoo_mcp import tools_read
    tool = mcp._tool_manager.get_tool('read_record')
    if tool is None or tool.is_async or tool.fn is not tools_read.read_record:
        raise RuntimeError('read_record requires source review')
    tool.fn = checked(tool.fn)
