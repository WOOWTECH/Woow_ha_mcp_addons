"""HM-01 contract freeze, management API (8099): today's answer shapes, byte for byte.

docs/multi-profile/contract.md (HM-00, section 4.1) says the existing management answers have five body shapes at
bb48449, and that HM-10 adds its new codes in shape A without moving an existing answer to another shape (a product
without multi-profile would then no longer answer as today):

- A {"error":"request denied","detail":{"code":...}}: config_revision_required 428, operation_id_required 428;
- B {"detail":{"code":"config_conflict"}} 409, no "error": a malformed and a stale If-Match;
- C {"error":"owner_defaults_unavailable","detail":{"code":"owner_defaults_unavailable"}} 409;
- D {"saved":true,"detail":{"code":"config_apply_failed"},"configuration":...} 503, no "error": saved, but the child
  did not start (a backend save), or the restored policy was not applied (owner-defaults restore, which also carries
  "owner_defaults", after "configuration" and before "detail");
- E {"error":"<string>"} without "detail": backend_check_failed 503; unsupported and backend_fixed 409.

Also the fixed answers without a code (section 4.1, end): {"error":"request denied"} for 403 (identity, CSRF,
cross-site, not an administrator), 400 (a query, a body where none belongs, a malformed X-Ingress-Path, a '%' in the
path, a value that does not validate), 415 and a page path written to (404); the empty 404 of an unknown operation; and
Starlette's 405.

Every answer is compared whole: status, every header (ui.SecurityHeaders on all of them, the ETag where the action set
it) and the body. The production runtime of each product serves them (tests/test_single_profile_golden.py:
production_runtime, a configured backend, the panel's own headers). D needs a child start that fails (failing_start)
and backend_check_failed a saved-configuration check that raises (HealthMonitor.test_saved, replaced before run() wires
it). unsupported and backend_fixed cannot happen in the add-on runtime (it wires backend_check, restart_child and
diagnostics and lets the panel edit the backend), and the add-on runtime starts a product only after its owner-defaults
step, so D's restore variant needs a migrated legacy state: those are frozen on make_apps, as a builtin deployment and
tests/test_owner_defaults.py wire it.
"""
from contextlib import closing
import json
from pathlib import Path

import httpx
import pytest

from admin_write_headers import reviewed_headers
from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import owner_defaults
from mcp_admin_core.backend_edit import FIELDS
from mcp_admin_core.capabilities import ManagementOptions
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.health import HealthMonitor
from mcp_admin_core.products import ProductStore, TOOLS
from n8n_adapter import TOOLS as N8N_TOOLS
from test_single_profile_golden import (ADMIN, CONNECTIONS, GENUINE_CLIENT, INGRESS, N8N_BACKEND, PRODUCTS,
                                        NoProcessSupervisor, answer, compact, configure, production_runtime,
                                        secrets_of, settle, stored)

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan
FIXTURES = Path(__file__).parent / 'fixtures/owner_defaults'
# ui.SecurityHeaders: on every management answer (bb48449).
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; connect-src 'self'; "
       "img-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'")
SECURITY = (('cache-control', 'no-store'), ('content-security-policy', CSP), ('referrer-policy', 'no-referrer'),
            ('x-content-type-options', 'nosniff'))
DENIED = b'{"error":"request denied"}'
SHAPE_A = {code: compact({'error': 'request denied', 'detail': {'code': code}})
           for code in ('config_revision_required', 'operation_id_required')}
SHAPE_B = b'{"detail":{"code":"config_conflict"}}'
SHAPE_C = b'{"error":"owner_defaults_unavailable","detail":{"code":"owner_defaults_unavailable"}}'
SHAPE_E = {code: compact({'error': code}) for code in ('backend_check_failed', 'unsupported', 'backend_fixed')}
APPLY_FAILED = {'code': 'config_apply_failed'}
POLICY = {'writes_enabled': True, 'disabled': []}  # a valid policy for every product (all tools on)
RESTORE_PRODUCTS = ('emqx', 'litellm', 'nextcloud')  # owner-defaults restore re-applies their children; a legacy state
OUTSIDE = ('127.0.0.1', 1)  # any caller but the HA ingress proxy (172.30.32.2)


def management_answer(status, body, *, etag=None, content_type='application/json'):
    headers = [*SECURITY, ('content-length', str(len(body)))]
    if content_type is not None:
        headers.append(('content-type', content_type))
    if etag is not None:
        headers.append(('etag', etag))
    return status, sorted(headers), body


def failing_start():
    """A NoProcessSupervisor whose next starts fail while refuse is set (run()'s backend_changed then raises)."""
    class FailingStart(NoProcessSupervisor):
        refuse = False

        def _start_child(self):
            if type(self).refuse:
                raise RuntimeError('HM-01: the child does not start')
            super()._start_child()
    return FailingStart


def unchanged_field(product):
    """A partial connection edit that keeps the saved value (no destination check, still a save)."""
    name = FIELDS[product][0]
    return {'changes': {name: N8N_BACKEND['backend_url'] if product == 'n8n' else CONNECTIONS[product][name]}}


def compare(failures, label, response, expected):
    """Collect a difference instead of stopping, so one run names every changed answer."""
    found = answer(response)
    if found != expected:
        failures.append(f'{label}: {found[0]} {found[1]} {found[2][:120]!r} != {expected[0]} {expected[1]} '
                        f'{expected[2][:120]!r}')


@pytest.mark.parametrize('product', PRODUCTS)
async def test_management_answer_shapes(tmp_path, log_scan, product):
    data = tmp_path / 'data'
    configure(data, product)
    log_scan.watch(*secrets_of(product), kind='secret')
    supervisor = failing_start()
    failures = []

    async def check_fails(self, state):
        raise RuntimeError('HM-01: the saved-configuration check fails')

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(HealthMonitor, 'test_saved', check_fails)  # before run() binds it as backend_check
        async with production_runtime(product, data, supervisor=supervisor) as runtime:
            await settle(runtime, 'configured')
            log_scan.watch(stored(data)['token'], stored(data)['child_token'])
            async with runtime.admin() as admin, GENUINE_CLIENT(transport=httpx.ASGITransport(
                    app=runtime.admin_app, client=OUTSIDE), base_url='http://admin') as outside:
                bootstrap = (await admin.get('/api/bootstrap', headers=ADMIN)).json()
                etag = '"' + bootstrap['configuration']['revision'] + '"'
                write = {**ADMIN, 'X-CSRF-Token': bootstrap['csrf']}
                # The fixed answers without a code.
                for label, response in (
                        ('403 no user', await admin.get('/api/bootstrap')),
                        ('403 not through the ingress proxy', await outside.get('/api/bootstrap', headers=ADMIN)),
                        ('403 no CSRF token', await admin.put('/api/policy', headers=ADMIN, json=POLICY)),
                        ('403 cross-site', await admin.put('/api/policy', json=POLICY,
                                                           headers={**write, 'Sec-Fetch-Site': 'cross-site'})),
                        ('403 not an administrator', await admin.get('/api/bootstrap',
                                                                     headers={'X-Remote-User-Id': 'golden-viewer'})),
                        ('400 query', await admin.get('/api/bootstrap?x=1', headers=ADMIN)),
                        ('400 a body where none belongs', await admin.post('/api/backend/test', headers=write,
                                                                           json={})),
                        ('400 malformed X-Ingress-Path', await admin.get('/api/bootstrap',
                                                                         headers={**ADMIN, 'X-Ingress-Path': 'bad'})),
                        ("400 '%' in the path", await admin.get('/api/%62ootstrap', headers=ADMIN)),
                        ('400 a value that does not validate', await admin.put('/api/policy', headers=write,
                                                                               json={'writes_enabled': True})),
                        ('404 a page path written to', await admin.put('/overview', headers=write, json={}))):
                    compare(failures, label, response, management_answer(int(label[:3]), DENIED))
                compare(failures, '415', await admin.put('/api/policy', content=b'{}', headers={
                    **write, 'Content-Type': 'text/plain'}), management_answer(415, DENIED))
                compare(failures, '404 unknown operation', await admin.get('/api/no-such-operation', headers=ADMIN),
                        management_answer(404, b'', content_type=None))
                refused = await admin.delete('/api/bootstrap', headers=ADMIN)
                # Starlette's 405 lists the route's methods from a set: the order of Allow is not fixed.
                assert sorted(refused.headers.get('allow', '').split(', ')) == ['GET', 'HEAD', 'POST', 'PUT']
                status, headers, body = management_answer(405, b'Method Not Allowed',
                                                           content_type='text/plain; charset=utf-8')
                compare(failures, '405', refused, (status, sorted([*headers, ('allow', refused.headers['allow'])]),
                                                   body))
                # Shape A: a save without If-Match; a receipt operation without Idempotency-Key.
                compare(failures, 'A config_revision_required', await admin.put('/api/policy', headers=write,
                                                                                json=POLICY),
                        management_answer(428, SHAPE_A['config_revision_required']))
                compare(failures, 'A operation_id_required', await admin.post('/api/token/rotate', headers={
                    **write, 'If-Match': etag}), management_answer(428, SHAPE_A['operation_id_required']))
                # Shape B: an If-Match that is malformed, or well formed and stale.
                for value in ('"bogus"', '"c1-' + '0' * 64 + '"'):
                    compare(failures, 'B ' + value[:6], await admin.put('/api/policy', json=POLICY, headers={
                        **write, 'If-Match': value}), management_answer(409, SHAPE_B, etag=etag))
                # Shape C: the owner-defaults actions on a state without the migration's marker.
                for action in ('restore', 'dismiss'):
                    compare(failures, 'C ' + action, await admin.post('/api/owner-defaults/' + action, headers={
                        **write, 'If-Match': etag}), management_answer(409, SHAPE_C, etag=etag))
                # Shape E: the saved-configuration check raises.
                compare(failures, 'E backend_check_failed', await admin.post('/api/backend/test', headers=write),
                        management_answer(503, SHAPE_E['backend_check_failed'], etag=etag))
                # Shape D: the save commits, the child does not start (last: the child stays stopped).
                supervisor.refuse = True
                saved = await admin.put('/api/backend/patch', json=unchanged_field(product), headers={
                    **write, 'If-Match': etag})
                supervisor.refuse = False
                configuration = (await admin.get('/api/configuration', headers=ADMIN)).json()['configuration']
                assert (configuration['apply_state'], configuration['last_error_code']) == (
                    'failed', 'child_start_failed')
                compare(failures, 'D config_apply_failed', saved, management_answer(503, compact(
                    {'saved': True, 'detail': APPLY_FAILED, 'configuration': configuration}),
                    etag='"' + configuration['revision'] + '"'))
    assert not failures, f'{product}: {len(failures)} management answer(s) changed:\n' + '\n'.join(failures)


@pytest.mark.parametrize('product', PRODUCTS)
async def test_builtin_only_answer_shapes(tmp_path, log_scan, product):
    """Shape E without a backend check, child restart or diagnostics hook, and with a fixed backend."""
    data = tmp_path / 'data'
    configure(data, product)
    log_scan.watch(*secrets_of(product), kind='secret')
    log_scan.watch(stored(data)['token'], stored(data)['child_token'])

    async def administrator(user):
        return user == ADMIN['X-Remote-User-Id']

    reached = []

    def no_child(request):
        reached.append(request.method)
        return httpx.Response(503)

    with closing(ProductStore(data, product)) as store:
        async with GENUINE_CLIENT(transport=httpx.MockTransport(no_child)) as child:
            admin, _ = make_apps(store, N8N_TOOLS if product == 'n8n' else TOOLS[product], child,
                                 verify_admin=administrator, management=ManagementOptions(
                                     kind='builtin', authority='ha-ingress', backend_mode='fixed',
                                     backend_can_edit=False))
            async with GENUINE_CLIENT(transport=httpx.ASGITransport(app=admin, client=INGRESS),
                                      base_url='http://admin') as client:
                bootstrap = (await client.get('/api/bootstrap', headers=ADMIN)).json()
                etag = '"' + bootstrap['configuration']['revision'] + '"'
                write = {**ADMIN, 'X-CSRF-Token': bootstrap['csrf']}
                before = store.path.read_bytes()
                unsupported = management_answer(409, SHAPE_E['unsupported'], etag=etag)
                assert answer(await client.post('/api/backend/test', headers=write)) == unsupported
                assert answer(await client.get('/api/diagnostics', headers=ADMIN)) == unsupported
                # child/restart: after the If-Match and Idempotency-Key checks.
                assert answer(await client.post('/api/child/restart', headers=reviewed_headers(bootstrap, ADMIN))) == (
                    unsupported)
                # backend_fixed: after the If-Match check.
                assert answer(await client.put('/api/backend/patch', json=unchanged_field(product), headers={
                    **write, 'If-Match': etag})) == management_answer(409, SHAPE_E['backend_fixed'], etag=etag)
                assert store.path.read_bytes() == before and reached == []


@pytest.mark.parametrize('product', RESTORE_PRODUCTS)
async def test_owner_defaults_restore_apply_failure_shape(tmp_path, log_scan, product):
    """Shape D of owner-defaults restore: the restored policy is saved, re-applying the child fails."""
    value = json.loads((FIXTURES / f'schema3-{product}-v0.1.14-max.json').read_text())
    data = tmp_path / 'data'
    data.mkdir(mode=0o700)
    (data / '.writer.lock').touch(mode=0o600)
    (data / 'state.json').write_text(json.dumps(value))
    (data / 'state.json').chmod(0o600)
    owner_defaults.apply_legacy_upgrade(data, product)  # the one-time migration: the marker and the recovery record
    log_scan.watch(value['token'], value['child_token'])

    async def administrator(user):
        return user == ADMIN['X-Remote-User-Id']

    async def apply_fails(state):
        raise RuntimeError('HM-01: the restored policy is not applied')

    with closing(ProductStore(data, product)) as store:
        async with GENUINE_CLIENT(transport=httpx.MockTransport(lambda request: httpx.Response(503))) as child:
            admin, _ = make_apps(store, TOOLS[product], child, verify_admin=administrator,
                                 backend_changed=apply_fails)
            async with GENUINE_CLIENT(transport=httpx.ASGITransport(app=admin, client=INGRESS),
                                      base_url='http://admin') as client:
                bootstrap = (await client.get('/api/bootstrap', headers=ADMIN)).json()
                assert bootstrap['owner_defaults']['restored_at'] is None  # the migration's notice, not yet acted on
                restored = await client.post('/api/owner-defaults/restore', headers={
                    **ADMIN, 'X-CSRF-Token': bootstrap['csrf'],
                    'If-Match': '"' + bootstrap['configuration']['revision'] + '"'})
                after = (await client.get('/api/bootstrap', headers=ADMIN)).json()
                assert after['owner_defaults']['restored_at'] is not None  # saved before the apply failed
                expected = compact({'saved': True, 'configuration': after['configuration'],
                                    'owner_defaults': after['owner_defaults'], 'detail': APPLY_FAILED})
                assert answer(restored) == management_answer(503, expected,
                                                             etag='"' + after['configuration']['revision'] + '"')
