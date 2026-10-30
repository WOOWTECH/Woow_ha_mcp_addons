"""Real Nextcloud child/gateway, owned fake backend, configured fake credentials only."""
import base64
import json
from urllib.parse import quote
from xml.sax.saxutils import escape

import pytest

from nextcloud_fixtures import NextcloudFake, OCS_PATH, respond
from test_six_hardening import Quiet, call, runtime, serve

PASSWORD = 'FAKE-nc-pass/+"quoted-4917'
DIAGNOSTIC = 'FAKE storage temporarily unavailable'
# 0.4.7 (vendored upstream v0.1.6, errors.mask_credentials): forms the 0.4.4 HA routine did not mask. A password
# whose Basic value contains '/', and a periodic password whose occurrences overlap.
SLASHED = 'FAKE-nc-basic??~-4917'
PERIODIC = 'FAKE-nc-overlap-' * 2


def error_result(response):
    if response.headers['content-type'].startswith('application/json'):
        return response.json()['result']
    return next(json.loads(line[6:])['result'] for line in response.text.splitlines()
                if line.startswith('data: ') and '"result"' in line)


@pytest.mark.parametrize('json_response', [False, True], ids=['sse', 'json'])
@pytest.mark.parametrize('form', ['raw', 'basic', 'url', 'json', 'base64', 'folded', 'cut',
                                  'json-slash', 'basic-slash', 'overlap'])
async def test_configured_secret_in_backend_detail(tmp_path, caplog, capfd, json_response, form):
    password = {'folded': 'FAKE-nc-pass  spaced-4917', 'basic-slash': SLASHED, 'overlap': PERIODIC}.get(form, PASSWORD)
    fake = NextcloudFake(password=password)
    encoded = {
        'raw': PASSWORD,
        'basic': base64.b64encode(f'tester:{PASSWORD}'.encode()).decode(),
        'url': quote(PASSWORD, safe=''),
        'json': json.dumps(PASSWORD)[1:-1],
        'base64': base64.b64encode(PASSWORD.encode()).decode(),
        'folded': ' '.join(password.split()),
        'cut': password[:16],
        # JSON may write '/' as '\/' (PHP json_encode does by default; Nextcloud is PHP).
        'json-slash': json.dumps(PASSWORD)[1:-1].replace('/', '\\/'),
        'basic-slash': base64.b64encode(f'tester:{SLASHED}'.encode()).decode().replace('/', '\\/'),
        # Echoed as password + its first half: the part a non-overlapping replacement leaves.
        'overlap': PERIODIC[:16],
    }[form]
    mode = {'status': 500, 'shape': 'json'}
    seen = []

    class Backend(Quiet):
        def answer(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            seen.append((self.command, self.path))
            if self.path == OCS_PATH:
                return respond(self, *fake.handle(self.command, self.path, self.headers, body))
            detail = f'{DIAGNOSTIC}; credential echo {encoded}; end diagnostic'
            if form == 'folded':
                detail = f'{DIAGNOSTIC}; credential echo {password}; end diagnostic'
            elif form == 'cut':
                detail = DIAGNOSTIC + 'x' * (984 - len(DIAGNOSTIC)) + password
            elif form == 'overlap':
                detail = f'{DIAGNOSTIC}; credential echo {password}{encoded}; end diagnostic'
            if mode['shape'] == 'sabre':
                body = ('<d:error xmlns:d="DAV:" xmlns:s="http://sabredav.org/ns">'
                        f'<s:message>{escape(detail)}</s:message></d:error>').encode()
            elif mode['shape'] == 'ocs':
                body = json.dumps({'ocs': {'meta': {'message': detail}}}).encode()
            elif mode['shape'] == 'text':
                body = detail.encode()
            else:
                body = json.dumps({'message': detail}).encode()
            respond(self, mode['status'], {'Content-Type': 'text/plain'}, body)

        do_GET = do_PROPFIND = answer

    failures = []
    with serve(Backend) as url:
        async with runtime(tmp_path, 'nextcloud', url, canary=password,
                           json_response=json_response) as (client, headers, store, manager, _):
            assert store.load().connection.app_password == password
            for status, shape in ((403, 'json'), (422, 'json'), (500, 'json'),
                                  (500, 'sabre'), (500, 'ocs'), (500, 'text')):
                mode.update(status=status, shape=shape)
                response = await client.post('/mcp', headers=headers, json=call('get_file_tree', {'path': 'x'}))
                result = error_result(response)
                text = '\n'.join(block.get('text', '') for block in result['content'])
                assert response.status_code == 200 and result['isError'] is True
                assert f'BACKEND_HTTP_ERROR status={status}' in text
                assert DIAGNOSTIC in text
                if form != 'cut':
                    assert 'end diagnostic' in text
                if encoded in text or password in text:
                    failures.append((status, shape, form, 'tool response'))
            # Stop joins the genuine output readers before inspecting retained diagnostics.
            await manager.stop()
            snapshot = manager.logs.snapshot()
            assert snapshot['entries'] and snapshot['retention'] == 'memory'
            retained = json.dumps(snapshot, ensure_ascii=False)
            captured = capfd.readouterr()
            logs = caplog.text + captured.out + captured.err + retained
            assert password not in logs and encoded not in logs
    assert seen and not fake.mutations
    assert not failures, failures
