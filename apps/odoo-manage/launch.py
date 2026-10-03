"""Scoped, source-guarded XMLRPC transport replacement; wheel stays unmodified."""
import hashlib
import os
from pathlib import Path
import runpy

from backend_policy import XMLTransport
import mcp_server_odoo.performance as performance

if hashlib.sha256(Path(performance.__file__).read_bytes()).hexdigest() != '34f476a3c41de0daa653c3bb35b6d95468c8ef7e4a12b4d912222e0987df7b19':
    raise RuntimeError('Manage transport requires source review')


class BackendTransport(XMLTransport):
    def __init__(self, database=None, timeout=None, context=None, **kwargs):
        super().__init__(os.environ['ODOO_URL'], timeout=min(timeout or 5, 5), database=database)


performance.OdooTransport = BackendTransport
performance.OdooSafeTransport = BackendTransport

if __name__ == '__main__':
    runpy.run_module('mcp_server_odoo', run_name='__main__')
