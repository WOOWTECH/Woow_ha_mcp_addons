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
    # The stock client caches an XMLRPC transport: serialize its sync calls.
    workers = BoundedTools(mcp, capacity=1)
    try:
        runpy.run_module('odoo_mcp', run_name='__main__')
    finally:
        workers.close()
