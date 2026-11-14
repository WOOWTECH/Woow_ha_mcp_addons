"""Private SDK-port interposition, then the ORIGINAL launcher/instrumentation.

Hermes/OpenDesign still own initialization, handlers, bounded workers/finalizers.
The -c branch composes the DNS/late-httpcore wrappers rather than discarding them.
HM-01: the launcher's production port is a parameter, --production-port=N right after the private port (default 3000;
an extra profile's child is on 18000-18099 in the multi-profile plan).
"""
from pathlib import Path
import runpy
import sys

from owned_network import PRODUCTION_PORT, PROFILE_CHILD_PORTS, forbidden_port, install
install()

OPTION = '--production-port='


def main():
    product, port, *target = sys.argv[1:]
    port = int(port)
    production_port = PRODUCTION_PORT
    if target and target[0].startswith(OPTION):
        production_port = int(target.pop(0)[len(OPTION):])
    assert product in ('hermes', 'opendesign') and 0 < port <= 65535 and not forbidden_port(port)
    assert production_port == PRODUCTION_PORT or production_port in PROFILE_CHILD_PORTS
    # 0.4.0 (mcp 2.3.0): FastMCP is MCPServer, and the launchers pass the fixed transport settings to run().
    from mcp.server.mcpserver import MCPServer
    original = MCPServer.run
    calls = 0
    def run(self, *args, **kwargs):
        nonlocal calls
        assert calls == 0
        assert not args and kwargs == {'transport': 'streamable-http', 'host': '127.0.0.1', 'port': production_port,
                                       'streamable_http_path': '/mcp'}
        calls += 1
        return original(self, **dict(kwargs, port=port))
    MCPServer.run = run
    if target[0] == '-c':
        sys.argv = ['-c', *target[2:]]
        exec(compile(target[1], '<owned instrumentation>', 'exec'), {'__name__': '__main__'})
    else:
        assert Path(target[0]).resolve().parts[-3:] == ('apps', product, 'launch.py')
        sys.argv = target
        runpy.run_path(target[0], run_name='__main__')


if __name__ == '__main__':
    main()
