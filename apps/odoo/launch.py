"""Pinned wheel launcher: fail closed on source drift before runtime adaptation."""
import hashlib
from pathlib import Path
import runpy
import os

from backend_policy import XMLTransport

import odoo_mcp.odoo_client as client

# 0.4.0 (odoo-mcp 1.3.0): only get_model_fields changed (fields_get asks for a bounded attribute list); the XML-RPC
# client still builds its ServerProxy transport through RedirectTransport(timeout=, use_https=, verify_ssl=), which the
# BackendTransport below replaces, and ODOO_TRANSPORT=xmlrpc keeps the urllib JSON-2 path unused.
if hashlib.sha256(Path(client.__file__).read_bytes()).hexdigest() != '3cb7796965772bbea02fa1fda5c4de1fdcb36055ae1dcf9db396fd22559ff6c7':
    raise RuntimeError('Odoo transport requires source review')

class BackendTransport(XMLTransport):
    def __init__(self, timeout=5, use_https=True, verify_ssl=True, **kwargs):
        if not verify_ssl:
            raise ValueError('TLS verification required')
        super().__init__(os.environ['ODOO_URL'], timeout=min(timeout, 5))


# Replace the actual wheel transport before any client construction.
client.RedirectTransport = BackendTransport

if __name__ == '__main__':
    import session_idle
    session_idle.install()  # 0.1.8 (GATEWAY-3): before odoo_mcp builds the session manager
    from odoo_mcp.server import mcp
    from bounded_tools import BoundedTools
    from odoo_mcp import tools_read, tools_diagnostics, agent_tools, diagnostics, tools_write, server_core
    # 0.2.0 (owner decision 2026-10-15, the full add-on): the complete odoo-mcp surface as the PaaS
    # woow-mcp-server serves it. tools_write and server_core carry the two PaaS build patches (apps/odoo/patches:
    # fix_cross_session_token_store, fix_direct_writes; applied to the venv by the Dockerfile and packaging/unit.sh):
    # these digests are the patched files, so an unpatched or altered wheel fails closed here. 0.4.0: odoo-mcp 1.3.0
    # (MCP SDK 2), the PaaS pin since woow-mcp-server #82; both patches apply at their anchors (reviewed in
    # docs/provenance/runtime-patches.json) and the 41 tools keep their names, annotations and write gating. The HA copy of
    # fix_direct_writes also makes the descriptions of execute_method's method and of chatter_post follow the switches
    # this add-on sets (direct writes and direct chatter on): 1.3.0 told the model those calls were blocked or gated.
    for module, digest in (
        (tools_read, 'c477b2a8a6276004b8bd55f51d7a0e5119096a68f0b81fc3dac43a916f906200'),
        (tools_diagnostics, '1355ad597fbe67cf4222c5c2295e229265c6654ebbfd83cebb62a7f291346bd5'),
        (agent_tools, '1e467c6e2871ace8ca935b028124630767968cd08c632875f99435434b2795ee'),
        (diagnostics, '1fb1632cc711a7dfa4d5f6700472abeaffb897a094a4c399c21ce045aebb0dc7'),
        (tools_write, '353fbc5a11497a1b969105d3d58760b8df376df86d30008c875c83477efcad93'),
        (server_core, '4866870f36f905122f2a6fbdb105591268b51d26848a38b99cf25efb498bee1d'),
    ):
        if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Odoo handlers require source review (patched odoo-mcp 1.3.0 expected)')
    from odoo_read_exists import install as install_read_exists
    install_read_exists(mcp)  # 0.1.8 (RR-03): a missing record read by 'id' only is not found
    from bounded_tools import OwnedWorkers
    from odoo_mcp.odoo_client import get_odoo_client
    # HealthMonitor's private probe: not in TOOLS, so the gateway neither lists nor authorizes it. It only
    # authenticates a fresh client (as every session does on its first live call), on its own owned thread:
    # it never takes the single tool worker below (0.1.2 HA: a probe held it while Odoo was slow and user
    # calls got BACKEND_BUSY), and an account without ir.model access still reads as reachable.
    probe_worker = OwnedWorkers(1, 'backend-probe')

    async def woow_backend_probe():
        try:
            odoo = await probe_worker.run(get_odoo_client)
        except Exception:
            raise ValueError('BACKEND_UNAVAILABLE') from None
        return {'uid': odoo.uid}

    mcp.add_tool(woow_backend_probe, name='woow_backend_probe', description='Add-on readiness probe (private).')
    if mcp._tool_manager.get_tool('woow_backend_probe').fn is not woow_backend_probe:
        raise RuntimeError('readiness probe name taken')  # add_tool keeps an existing tool of the same name
    # The upstream Odoo tools return {"success": false, "error": ...} as a normal value. Convert those results to
    # MCP isError=true before the worker wrapper, while preserving each published outputSchema's result envelope.
    # This is the same source-backed contract as the PaaS Odoo launcher; fake-backend tests cover both shapes.
    import odoo_tool_errors
    odoo_tool_errors.install(mcp)
    # The stock client caches an XMLRPC transport: serialize its sync calls. 0.4.0: mcp 2 runs a sync tool on an anyio
    # worker thread, in parallel; BoundedTools turns every sync tool (the writes execute_method and chatter_post as
    # well as the reads) into an async one on its single owned worker, so they still run one at a time.
    workers = BoundedTools(mcp, capacity=1)
    # 0.4.0: mcp 2 hides an exception's text from the client unless it is a ToolError; keep 1.x's text for every tool
    # (BACKEND_BUSY above, the probe's BACKEND_UNAVAILABLE, odoo-mcp's own errors). Last, around everything else.
    from tool_error_text import keep_error_text
    keep_error_text(mcp)
    try:
        runpy.run_module('odoo_mcp', run_name='__main__')
    finally:
        workers.close()
        probe_worker.close()
