"""Pinned wheel launcher: fail closed on source drift before runtime adaptation."""
import hashlib
from pathlib import Path
import runpy
import os

from backend_policy import XMLTransport

import odoo_mcp.odoo_client as client

if hashlib.sha256(Path(client.__file__).read_bytes()).hexdigest() != '8bd06a523cb8049f14f54d06d9b73c3d7787108e7e78cf58bfb725ec9a97f74d':
    raise RuntimeError('Odoo transport requires source review')

class BackendTransport(XMLTransport):
    def __init__(self, timeout=5, use_https=True, verify_ssl=True, **kwargs):
        if not verify_ssl:
            raise ValueError('TLS verification required')
        super().__init__(os.environ['ODOO_URL'], timeout=min(timeout, 5))


# Replace the actual wheel transport before any client construction.
client.RedirectTransport = BackendTransport

if __name__ == '__main__':
    from odoo_mcp.server import mcp
    from bounded_tools import BoundedTools
    from batch2_outputs import odoo_counts
    import functools
    from odoo_mcp import tools_read, tools_diagnostics, agent_tools, diagnostics
    for module, digest in (
        (tools_read, '4c8bf33b35c54757b93f0cc367b4f5027488ca8fbf63f68c1241f1a4be784de0'),
        (tools_diagnostics, '957f3affa479cb079350de8874064d89594ab0661cfbfd7675b7f26930d32772'),
        (agent_tools, '5004b28b00e59efd903ae8d48240922a0bdb43fb9b0051e77dbcd919e3c434fd'),
        (diagnostics, '1fb1632cc711a7dfa4d5f6700472abeaffb897a094a4c399c21ce045aebb0dc7'),
    ):
        if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Odoo B1 handlers require source review')
    aggregate = mcp._tool_manager.get_tool('aggregate_records')
    original_aggregate = aggregate.fn

    @functools.wraps(original_aggregate)
    def bounded_counts(**kwargs):
        return odoo_counts(original_aggregate(**kwargs))

    aggregate.fn = bounded_counts
    from odoo_b2_scope import install as install_b2
    install_b2(mcp)
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
    # The stock client caches an XMLRPC transport: serialize its sync calls.
    workers = BoundedTools(mcp, capacity=1)
    try:
        runpy.run_module('odoo_mcp', run_name='__main__')
    finally:
        workers.close()
        probe_worker.close()
