"""Keep the gateway's offline Odoo tools/list snapshot truthful for the saved child switches."""
from __future__ import annotations

import copy

from . import odoo_write_gates as gates


def for_state(pinned, state):
    tools = copy.deepcopy(pinned)
    if getattr(state, 'product', None) != 'odoo' or tools is None:
        return tools
    saved = state.effective_odoo_write_switches
    switches = gates.Switches(saved.enable_writes, saved.allow_direct_writes,
                              saved.allow_unknown_methods, saved.chatter_direct)
    by_name = {tool['name']: tool for tool in tools}
    by_name['execute_method']['inputSchema']['properties']['method']['description'] = gates.execute_method_text(switches)
    for name, text in (
        ('chatter_post', gates.chatter_post_text(switches)),
        ('preview_write', gates.preview_write_text(switches)),
        ('validate_write', gates.validate_write_text(switches)),
        ('execute_approved_write', gates.execute_approved_write_text(switches)),
    ):
        by_name[name]['description'] = text
    return tools
