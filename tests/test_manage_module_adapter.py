"""New module-only REST paths must use the existing audited transport."""
import json
from pathlib import Path
import subprocess

import pytest

from test_six_hardening import Quiet, serve

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('mode', ['valid', 'denied', 'redirect', 'nonbool', 'invalid_json'])
@pytest.mark.parametrize('operation', ['auth', 'access'])
def test_actual_source_guarded_module_rest_helpers(mode, operation):
    seen = []
    class Backend(Quiet):
        def do_GET(self):
            seen.append(self.path)
            assert self.headers['X-API-Key'] == 'DUMMY'
            if mode == 'redirect':
                self.send_response(307); self.send_header('Location', '/capture'); self.send_header('Content-Length', '0'); self.end_headers(); return
            if mode == 'denied': return self.reply({'error': 'MUST_NOT_ESCAPE'}, 403)
            if mode == 'invalid_json': return self.reply(b'MUST_NOT_ESCAPE')
            detail = ({'valid': True, 'user_id': 7} if operation == 'auth' else
                      {'model': 'res.partner', 'enabled': True, 'operations': {k: True for k in ('read', 'create', 'write', 'unlink')}})
            if mode == 'nonbool':
                if operation == 'auth': detail['valid'] = 'true'
                else: detail['operations']['create'] = 'true'
            self.reply({'success': True, 'data': detail, 'private_key': 'MUST_NOT_ESCAPE'})
    with serve(Backend) as url:
        code = '''
import runpy, sys
runpy.run_path(sys.argv[1], run_name='adapter_probe')
from mcp_server_odoo.config import OdooConfig
from mcp_server_odoo.odoo_connection import OdooConnection
from mcp_server_odoo.access_control import AccessController
c = OdooConfig(url=sys.argv[2], username='tester', database='test', api_key='DUMMY', yolo_mode='off')
try:
    if sys.argv[3] == 'auth':
        ok = OdooConnection(c)._authenticate_api_key_mcp('test')
    else:
        result = AccessController(c, database='test', auth_method='api_key')._make_request('/mcp/models/res.partner/access')
        ok = result['data']['operations']['create'] is True
    print('ALLOWED' if ok else 'DENIED')
except Exception as exc:
    print('DENIED', str(exc))
'''
        result = subprocess.run([str(ROOT/'apps/odoo-manage/.venv/bin/python'), '-c', code,
            str(ROOT/'apps/odoo-manage/launch.py'), url, operation],
            env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT/'apps/runtime'),
                 'PYTHONDONTWRITEBYTECODE': '1', 'ODOO_URL': url},
            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert len(seen) == 1 and seen[0] != '/capture'
    assert ('ALLOWED' if mode == 'valid' else 'DENIED') in result.stdout
    assert 'MUST_NOT_ESCAPE' not in result.stdout + result.stderr
