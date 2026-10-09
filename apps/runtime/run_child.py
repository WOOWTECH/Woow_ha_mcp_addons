"""Start a vendored FastMCP child (EMQX, LiteLLM, Nextcloud) with the add-on's session idle limit (0.1.8 GATEWAY-3).

python -m run_child <module> [the module's own arguments]: installs session_idle before the module builds its
server, then runs the module as __main__ with the remaining arguments, exactly as `python -m <module>` would.
"""
import runpy
import sys

import session_idle

MODULES = ('emqx_mcp_server.server', 'woow_litellm_mcp_server.server', 'nextcloud_mcp_server.server')


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in MODULES:
        raise SystemExit('run_child: unknown child module')
    module = sys.argv.pop(1)
    session_idle.install()
    runpy.run_module(module, run_name='__main__', alter_sys=True)


if __name__ == '__main__':
    main()
