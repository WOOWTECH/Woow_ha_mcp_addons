"""Source-guarded PaaS #89 Odoo child decisions, installed before the existing HA launcher.

This keeps apps/odoo/launch.py (owned by the independent isError PR) and the pinned wheel bytes unchanged. The
underlying odoo-mcp 1.3.0 handlers still do their own validation, approval-token checks and backend calls. The
pre-call refusals only narrow access, except that they correct the all-on descriptions and runtime posture.
"""
from __future__ import annotations

import functools
import hashlib
import os
from pathlib import Path

from mcp_admin_core import odoo_write_gates as gates


SOURCES = {
    'tools_write': '353fbc5a11497a1b969105d3d58760b8df376df86d30008c875c83477efcad93',
    'tools_read': 'c477b2a8a6276004b8bd55f51d7a0e5119096a68f0b81fc3dac43a916f906200',
    'server_core': '4866870f36f905122f2a6fbdb105591268b51d26848a38b99cf25efb498bee1d',
    'diagnostics': '1fb1632cc711a7dfa4d5f6700472abeaffb897a094a4c399c21ce045aebb0dc7',
}


def switches():
    from odoo_mcp.tool_helpers import truthy_env
    from odoo_mcp.write_policy import chatter_direct_enabled, writes_enabled
    return gates.Switches(
        enable=writes_enabled(),
        direct=os.environ.get('ODOO_MCP_ALLOW_DIRECT_WRITES', '').strip().lower() in ('1', 'true', 'yes'),
        unknown=truthy_env('ODOO_MCP_ALLOW_UNKNOWN_METHODS'),
        chatter=chatter_direct_enabled(),
    )


def _verified_tools(mcp):
    from odoo_mcp import diagnostics, tools_read, tools_write
    root = Path(tools_write.__file__).parent
    for name, expected in SOURCES.items():
        if hashlib.sha256((root / (name + '.py')).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Odoo write switch overlay requires source review')
    expected = {'execute_method': tools_write.execute_method, 'chatter_post': tools_write.chatter_post,
                'validate_write': tools_write.validate_write, 'health_check': tools_read.health_check}
    found = {name: mcp._tool_manager.get_tool(name) for name in
             (*expected, 'preview_write', 'execute_approved_write')}
    if (any(tool is None for tool in found.values()) or
            any(found[name].fn is not fn or found[name].is_async for name, fn in expected.items()) or
            any(found[name].fn is not getattr(tools_write, name) for name in ('preview_write',)) or
            found['execute_approved_write'].fn is not tools_write.execute_approved_write_tool):
        raise RuntimeError('Odoo write tools require source review')
    return found, diagnostics, tools_write


def install(mcp):
    """Verify every source/tool first, then install all four decisions and their matching descriptions."""
    found, diagnostics, tools_write = _verified_tools(mcp)
    current = switches()  # one child generation has one immutable launch configuration
    original_execute = found['execute_method'].fn
    original_chatter = found['chatter_post'].fn
    original_validate = found['validate_write'].fn
    original_health = found['health_check'].fn

    @functools.wraps(original_execute)
    def execute_method(ctx, model, method, args=None, kwargs=None, instance=None):
        try:
            tools_write.validate_model_name(model)
            tools_write.validate_method_name(method)
            refusal = gates.execute_method_refusal(
                model, method, diagnostics.classify_method_safety(method),
                lambda: tools_write.side_effect_method_allowed(model, method), current)
        except Exception as exc:
            return {'success': False, 'error': str(exc)}
        if refusal is not None:
            return refusal
        return original_execute(ctx=ctx, model=model, method=method, args=args, kwargs=kwargs, instance=instance)

    @functools.wraps(original_chatter)
    def chatter_post(*args, **kwargs):
        refusal = gates.chatter_post_refusal(current)
        return refusal if refusal is not None else original_chatter(*args, **kwargs)

    @functools.wraps(original_validate)
    def validate_write(*args, **kwargs):
        result = original_validate(*args, **kwargs)
        return {**result, 'valid': result.get('success') is True} if type(result) is dict else result

    @functools.wraps(original_health)
    def health_check(*args, **kwargs):
        result = original_health(*args, **kwargs)
        runtime = result['runtime']
        notes = list(runtime['notes'])
        if notes[2] != gates.UPSTREAM_STATIC_NOTE:
            raise RuntimeError('Odoo health posture requires source review')
        notes[2] = gates.runtime_note(current)
        broad = dict(runtime['broad_unknown_method_mode'])
        broad.update(enabled=gates.unknown_methods_run(current), risk='broad' if gates.unknown_methods_run(current) else 'off')
        return {**result, 'runtime': {**runtime, 'direct_writes_enabled': current.direct,
                                      'broad_unknown_method_mode': broad, 'notes': notes}}

    found['execute_method'].fn = execute_method
    found['chatter_post'].fn = chatter_post
    found['validate_write'].fn = validate_write
    found['health_check'].fn = health_check
    found['execute_method'].parameters['properties']['method']['description'] = gates.execute_method_text(current)
    for name, description in (
        ('chatter_post', gates.chatter_post_text(current)),
        ('preview_write', gates.preview_write_text(current)),
        ('validate_write', gates.validate_write_text(current)),
        ('execute_approved_write', gates.execute_approved_write_text(current)),
    ):
        found[name].description = description
