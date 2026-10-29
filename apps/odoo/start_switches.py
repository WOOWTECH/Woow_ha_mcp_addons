"""Install the reviewed Odoo write switch overlay, then run the existing source-guarded HA launcher."""
import runpy

import session_idle
session_idle.install()  # Before odoo_mcp.server constructs its session manager; launch.py repeats idempotently.

from odoo_mcp.server import mcp
from odoo_switch_overlay import install

install(mcp)
runpy.run_module('launch', run_name='__main__')
