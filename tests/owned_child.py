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
    from mcp.server.fastmcp import FastMCP
    original = FastMCP.run
    calls = 0
    def run(self, *args, **kwargs):
        nonlocal calls
        assert calls == 0
        assert (self.settings.host, self.settings.port, self.settings.streamable_http_path) == ('127.0.0.1', 3000, '/mcp')
        assert kwargs == {'transport': 'streamable-http'} and not args
        calls += 1
        self.settings.port = port
        return original(self, *args, **kwargs)
    FastMCP.run = run
    if target[0] == '-c':
        sys.argv = ['-c', *target[2:]]
        exec(compile(target[1], '<owned instrumentation>', 'exec'), {'__name__': '__main__'})
    else:
        assert Path(target[0]).resolve().parts[-3:] == ('apps', product, 'launch.py')
        sys.argv = target
        runpy.run_path(target[0], run_name='__main__')


if __name__ == '__main__':
    main()
