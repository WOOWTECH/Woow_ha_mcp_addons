"""Synthetic DNS/intercepted sockets: never send packets to denied destinations."""
from pathlib import Path
import subprocess

import pytest

from mcp_admin_core.products import PRODUCTS, ProductState, child_spec
from test_real_products import connection

PROGRAM = r'''
import socket, os, asyncio, json, runpy
attempts=[]
mode=os.environ['CASE']
def resolve(host, port, *a, **k):
    host=host.decode() if isinstance(host,bytes) else host
    addresses = ['127.0.0.1', '169.254.169.254'] if mode=='mixed' else ['169.254.169.254']
    return [(socket.AF_INET,socket.SOCK_STREAM,socket.IPPROTO_TCP,'',(ip,int(port))) for ip in addresses]
def stop(self,address):
    attempts.append(address);raise OSError(111,'intercepted before connect')
socket.getaddrinfo=resolve;socket.socket.connect=stop;socket.socket.connect_ex=stop
p=os.environ['PRODUCT']
async def main():
    outcome=''
    try:
        if p=='odoo':
            if os.environ.get('POLICY_LAUNCH'):
                runpy.run_path(os.environ['POLICY_LAUNCH'],run_name='policy_test')
            from odoo_mcp.odoo_client import get_odoo_client
            get_odoo_client()
        elif p=='odoo-manage':
            if os.environ.get('POLICY_LAUNCH'):
                runpy.run_path(os.environ['POLICY_LAUNCH'],run_name='policy_test')
            from mcp_server_odoo.config import OdooConfig
            from mcp_server_odoo.odoo_connection import OdooConnection
            OdooConnection(OdooConfig.from_env()).connect()
        elif p=='hermes':
            from hermes_mcp_server.server import hermes_inspect, _dashboard_login, _dashboard_client
            if mode=='dashboard-login': await _dashboard_login(os.environ['HERMES_DASHBOARD_URL'],'tester','DUMMY')
            elif mode=='dashboard-cookie':
                async with _dashboard_client(os.environ['HERMES_DASHBOARD_URL'],'DUMMY-COOKIE') as c: await c.get('/api/status')
            else: outcome = await hermes_inspect(target='capabilities')
        elif p=='opendesign':
            from opendesign_mcp_server.od_mcp_server import health
            health()
        elif p=='emqx':
            from emqx_mcp_server.lifespan import make_client
            async with make_client() as c:await c.get('/nodes')
        elif p=='nextcloud':
            from nextcloud_mcp_server.client import NextcloudClient
            from nextcloud_mcp_server.settings import load_settings
            nc=NextcloudClient(load_settings())
            try: await nc.probe()
            finally: await nc.aclose()
        else:
            from woow_litellm_mcp_server.lifespan import build_client
            async with build_client() as c:await c.get('/v1/models')
    except Exception as exc: outcome=str(exc)
    assert 'BACKEND_DESTINATION_DENIED' in outcome, (p, outcome)
    assert not attempts, (p,mode,attempts)
asyncio.run(main())
'''


@pytest.mark.parametrize('product', PRODUCTS)
@pytest.mark.parametrize('case', ['literal', 'dns', 'mixed'])
def test_actual_backend_denied_before_connect(tmp_path, product, case):
    url = 'http://169.254.169.254' if case == 'literal' else 'http://rebind.invalid'
    run_case(tmp_path, product, case, url)


@pytest.mark.parametrize('case', ['dashboard-login', 'dashboard-cookie'])
def test_hermes_dashboard_denied_before_connect(tmp_path, case):
    run_case(tmp_path, 'hermes', case, 'http://rebind.invalid')


def run_case(tmp_path, product, case, url):
    state = ProductState(product=product, token='a'*43, child_token='b'*43, connection=connection(product, url))
    spec = child_spec(state, tmp_path)
    launcher = spec.argv[1] if product in ('odoo','odoo-manage') and spec.argv[1].endswith('launch.py') else ''
    result = subprocess.run([spec.argv[0], '-c', PROGRAM], env={**spec.env, 'PRODUCT': product,
        'CASE': case, 'POLICY_LAUNCH': launcher}, cwd=spec.cwd, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_cancelled_sdk_call_retains_worker_until_function_finishes(tmp_path):
    state = ProductState(product='opendesign', token='a'*43, child_token='b'*43,
                         connection={'url': 'http://127.0.0.1:9999'})
    spec = child_spec(state, tmp_path)
    program = r'''
import asyncio, threading
from mcp.server.fastmcp import FastMCP
from bounded_tools import BoundedTools
entered, release = threading.Event(), threading.Event()
mcp=FastMCP('owned-cancel-regression')
@mcp.tool()
def blocked() -> dict:
    entered.set(); release.wait(5); return {'done': True}
workers=BoundedTools(mcp,1)
async def main():
    task=asyncio.create_task(mcp.call_tool('blocked',{}))
    assert await asyncio.to_thread(entered.wait,2)
    task.cancel()
    await asyncio.gather(task,return_exceptions=True)
    try:
        await mcp.call_tool('blocked',{})
    except Exception as exc:
        assert 'BACKEND_BUSY' in str(exc)
    else: raise AssertionError('cancel released still-running worker')
    release.set()
    for _ in range(100):
        try:
            await mcp.call_tool('blocked',{}); break
        except Exception as exc:
            assert 'BACKEND_BUSY' in str(exc)
            await asyncio.sleep(.01)
    else: raise AssertionError('worker slot leaked')
try: asyncio.run(main())
finally: release.set(); workers.close()
'''
    result = subprocess.run([spec.argv[0], '-c', program], env=spec.env, cwd=spec.cwd,
                            text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
