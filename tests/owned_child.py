"""Private SDK-port interposition, then the ORIGINAL launcher/instrumentation.

Hermes/OpenDesign still own initialization, handlers, bounded workers/finalizers.
The -c branch composes the DNS/late-httpcore wrappers rather than discarding them.
"""
from pathlib import Path
import runpy
import sys

from owned_network import install
install()


def main():
    product, port, *target = sys.argv[1:]
    port = int(port)
    assert product in ('hermes', 'opendesign') and 0 < port <= 65535 and port != 3000
    # 0.4.0 (mcp 2.3.0): FastMCP is MCPServer, and the launchers pass the fixed transport settings to run().
    from mcp.server.mcpserver import MCPServer
    original = MCPServer.run
    calls = 0
    def run(self, *args, **kwargs):
        nonlocal calls
        assert calls == 0
        assert not args and kwargs == {'transport': 'streamable-http', 'host': '127.0.0.1', 'port': 3000,
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
