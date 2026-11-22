"""Train A review F-1: the EMQX child keeps both policy layers when the launcher gives it a state path.

The environment gate (EMQX_MCP_READONLY, EMQX_MCP_DISABLED_TOOLS) decides which tools the child registers at all;
PolicyMiddleware (EMQX_MCP_STATE_PATH) is a second, live layer on top. A state path must not switch the first one off.
The child runs in the EMQX app's own venv with the PYTHONPATH products.child_spec builds, as in the image, so this also
shows that venv can import mcp_admin_core (apps/emqx/Dockerfile copies packages/mcp-admin-core and puts it on PYTHONPATH).
"""
import json
import os
from pathlib import Path
import subprocess

import pytest

from mcp_admin_core import products

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / 'apps/emqx/.venv/bin/python'
LISTING = (
    "import asyncio, json\n"
    "import mcp_admin_core.products, emqx_child_policy\n"  # the imports PolicyMiddleware needs, in the child's venv
    "from emqx_mcp_server import server\n"
    "async def main():\n"
    "    print(json.dumps(sorted(t.name for t in await server.mcp.list_tools(run_middleware=False))))\n"
    "asyncio.run(main())\n")
WRITE_TOOLS = {'emqx_publish', 'emqx_kick_client', 'emqx_ban', 'emqx_manage_authn_users', 'emqx_toggle_rule'}


def registered(tmp_path, state_path, **policy):
    env = {'PATH': os.environ['PATH'], 'HOME': str(tmp_path), 'PYTHONDONTWRITEBYTECODE': '1',
           'PYTHONPATH': f'{ROOT / "apps/emqx/vendor"}:{ROOT / "apps/runtime"}:{ROOT / "packages/mcp-admin-core"}',
           'EMQX_MCP_BASE_URL': 'http://10.0.0.5:18083', 'EMQX_MCP_API_KEY': 'DUMMY', 'EMQX_MCP_API_SECRET': 'DUMMY',
           'FASTMCP_CHECK_FOR_UPDATES': 'off', 'FASTMCP_SHOW_SERVER_BANNER': 'false', **policy}
    if state_path:
        env['EMQX_MCP_STATE_PATH'] = str(tmp_path / 'profile' / 'state.json')  # never read: only registration is listed
    done = subprocess.run([str(PYTHON), '-c', LISTING], env=env, cwd=tmp_path, capture_output=True, text=True,
                          timeout=120, stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stderr[-2000:]
    return set(json.loads(done.stdout.strip().splitlines()[-1]))


@pytest.mark.parametrize('state_path', [False, True], ids=['standalone', 'with a state path'])
def test_readonly_and_disabled_tools_still_block_registration(tmp_path, state_path):
    everything = registered(tmp_path, state_path, EMQX_MCP_READONLY='false')
    assert WRITE_TOOLS <= everything and 'emqx_list_clients' in everything
    readonly = registered(tmp_path, state_path, EMQX_MCP_READONLY='true')
    assert not readonly & WRITE_TOOLS and 'emqx_list_clients' in readonly
    disabled = registered(tmp_path, state_path, EMQX_MCP_READONLY='false',
                          EMQX_MCP_DISABLED_TOOLS='emqx_list_clients,emqx_publish')
    assert disabled == everything - {'emqx_list_clients', 'emqx_publish'}


def test_a_state_path_changes_nothing_about_which_tools_the_environment_registers(tmp_path):
    policy = {'EMQX_MCP_READONLY': 'true', 'EMQX_MCP_DISABLED_TOOLS': 'emqx_list_topics'}
    assert registered(tmp_path, True, **policy) == registered(tmp_path, False, **policy)

