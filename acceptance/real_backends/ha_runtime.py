"""Shipped run_product lifecycle, with only the declared loopback HA identity seam."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from starlette.responses import Response
sys.path.insert(0, '/opt/woow/packaging')
from management_launcher import guard
from mcp_admin_core import run_product
USER = '04404404404404404404404404404404'
async def role(user):return user == USER
class LocalIngressFixture:
    def __init__(self, app):self.app = app
    async def __call__(self, scope, receive, send):
        if scope.get('client', ('', 0))[0] != '127.0.0.1':
            return await Response(status_code=403)(scope, receive, send)
        scope = dict(scope);scope['client'] = ('172.30.32.2', 43210)
        return await self.app(scope, receive, send)
original = run_product.make_apps
def apps(*args, **kwargs):
    admin, mcp = original(*args, **kwargs)
    return LocalIngressFixture(admin), mcp
run_product.make_apps = apps
run_product.make_ha_admin_verifier = lambda: role
if __name__ == '__main__':
    guard()
    family = json.loads(Path('/run/scratch/fixture.json').read_text())['family']
    asyncio.run(run_product.run(SimpleNamespace(product=family, data=Path('/data/mcp'), host='127.0.0.1', admin_port=8099, mcp_port=8081)))
