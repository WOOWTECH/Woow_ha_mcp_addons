"""Direct LiteLLM entry points never expose the add-on's private probe."""
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / 'apps/litellm/.venv/bin/python'


@pytest.mark.parametrize('transport', ['stdio', 'http'])
def test_direct_entry_rejects_private_probe_without_backend_io(transport):
    script = r'''
import asyncio, os, socket, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import MCPError, ToolError

hits = []
class Backend(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        hits.append(self.path)
        data = b'{"data":[{"id":"dummy"}]}'
        self.send_response(200); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
backend = ThreadingHTTPServer(('127.0.0.1', 0), Backend)
threading.Thread(target=backend.serve_forever, daemon=True).start()
env = dict(os.environ, LITELLM_MCP_BASE_URL='http://127.0.0.1:%s' % backend.server_port,
           LITELLM_MCP_MASTER_KEY='DUMMY-test-key', WOOW_MCP_CHILD_TOKEN='C'*43,
           FASTMCP_CHECK_FOR_UPDATES='off', FASTMCP_SHOW_SERVER_BANNER='false')
module = 'woow_litellm_mcp_server.server'
proc = None
async def main():
    global proc
    if sys.argv[1] == 'stdio':
        target = StdioTransport(sys.executable, ['-m', module, '--transport', 'stdio'], env=env)
    else:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        proc = subprocess.Popen([sys.executable, '-m', module, '--transport', 'http', '--host', '127.0.0.1',
                                 '--port', str(port), '--path', '/mcp'], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(200):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.1): break
            except OSError:
                if proc.poll() is not None: raise AssertionError('HTTP server exited')
                await asyncio.sleep(.05)
        else: raise AssertionError('HTTP server did not start')
        target = 'http://127.0.0.1:%s/mcp' % port
    async with Client(target) as client:
        names = {tool.name for tool in await client.list_tools()}
        assert 'litellm_list_models' in names
        assert 'woow_backend_probe' not in names, 'private probe listed'
        try:
            answer = await client.call_tool('woow_backend_probe', {})
        except (MCPError, ToolError) as exc:
            assert "woow_backend_probe" in str(exc), str(exc)
        else:
            assert answer.is_error, 'private probe callable'
        assert hits == [], hits
try: asyncio.run(main())
finally:
    if proc:
        proc.terminate(); proc.wait(timeout=10)
    backend.shutdown(); backend.server_close()
'''
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(ROOT / 'apps/runtime'), str(ROOT / 'apps/litellm/vendor'))))
    result = subprocess.run([str(PYTHON), '-c', script, transport], env=env, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('args', [
    ['--transport', 'stdio', '--host', '127.0.0.1'],
    ['--transport', 'http', '--host', '0.0.0.0'],
    ['--transport', 'sse', '--host', '127.0.0.1'],
    ['--transport', 'http', '--host', '127.0.0.1', '--host', '0.0.0.0'],
])
def test_controlled_child_refuses_unsafe_transports(args):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(ROOT / 'apps/runtime'), str(ROOT / 'apps/litellm/vendor'))),
               WOOW_MCP_CHILD_TOKEN='C' * 43)
    result = subprocess.run([str(PYTHON), '-m', 'run_child', 'woow_litellm_mcp_server.server', *args], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0 and 'LiteLLM requires loopback HTTP' in result.stderr


@pytest.mark.parametrize('help_flag', ['--help', '--hel', '--he', '-h'])
def test_child_help_matches_direct_cli_without_starting_or_registering_probe(help_flag):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(ROOT / 'apps/runtime'), str(ROOT / 'apps/litellm/vendor'))),
               FASTMCP_CHECK_FOR_UPDATES='off', FASTMCP_SHOW_SERVER_BANNER='false')
    env.pop('WOOW_MCP_CHILD_TOKEN', None)
    module = 'woow_litellm_mcp_server.server'
    direct = subprocess.run([str(PYTHON), '-m', module, help_flag], env=env, capture_output=True, text=True, timeout=15)
    assert direct.returncode == 0
    # Fail if help ever installs the bearer, registers the probe, or runs the server.
    script = r'''
import runpy, sys
import session_idle
from fastmcp import FastMCP
session_idle.install = lambda: (_ for _ in ()).throw(AssertionError('bearer installed'))
original = FastMCP.add_tool
def add_tool(self, tool, *args, **kwargs):
    assert getattr(tool, 'name', None) != 'woow_backend_probe', 'probe registered'
    return original(self, tool, *args, **kwargs)
FastMCP.add_tool = add_tool
FastMCP.run = lambda *a, **k: (_ for _ in ()).throw(AssertionError('server started'))
sys.argv = ['run_child', 'woow_litellm_mcp_server.server', sys.argv[1]]
runpy.run_module('run_child', run_name='__main__')
'''
    child = subprocess.run([str(PYTHON), '-c', script, help_flag], env=env, capture_output=True, text=True, timeout=15)
    assert child.returncode == 0, child.stderr
    assert child.stdout == direct.stdout


@pytest.mark.parametrize('args,allowed', [
    (['--transport', 'http', '--transport', 'stdio', '--host', '127.0.0.1'], False),
    (['--transport', 'stdio', '--transport', 'http', '--host', '127.0.0.1'], True),
    (['--trans', 'stdio', '--host', '127.0.0.1'], False),
    (['--trans', 'http', '--hos', '127.0.0.1'], True),
    (['--trans', 'http', '--hos', '0.0.0.0'], False),
])
def test_controlled_child_validates_final_and_abbreviated_options(args, allowed):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(ROOT / 'apps/runtime'), str(ROOT / 'apps/litellm/vendor'))))
    env.pop('WOOW_MCP_CHILD_TOKEN', None)
    result = subprocess.run([str(PYTHON), '-m', 'run_child', 'woow_litellm_mcp_server.server', *args], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    if allowed:
        assert 'child bearer: WOOW_MCP_CHILD_TOKEN is missing' in result.stderr
    else:
        assert 'LiteLLM requires loopback HTTP' in result.stderr
