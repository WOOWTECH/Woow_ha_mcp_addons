"""Install the reviewed Odoo write switch overlay, then run the existing source-guarded HA launcher."""
import runpy

from odoo_mcp.server import mcp
from odoo_switch_overlay import install

install(mcp)
runpy.run_module('launch', run_name='__main__')
