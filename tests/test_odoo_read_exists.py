"""0.1.8 (RR-03): read_record of only 'id' reports a missing record as not found (genuine pinned handler).

Odoo's read() of no field but 'id' answers [{'id': n}] for any n (it fetches nothing), so the pinned read_record
reported a deleted partner as found (woowtech-ha M2a: ODOO-RR-03, RR-03b). The fakes below answer the same way.
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import xmlrpc.client

import httpx

from owned_runtime import Endpoint
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS, child_spec
from test_real_products import connection, rpc
from test_expansion_policy import call
from test_b2_odoo_runtime import initialize
from test_b2_odoo_scope import probe

MISSING = 2147483647
NOT_FOUND = {'success': False, 'error': f'Record not found: res.partner ID {MISSING}'}


def test_genuine_handler_counts_only_after_an_id_only_success():
    out = json.loads(probe('''
import json
from types import SimpleNamespace as NS
from odoo_mcp import tools_read
import odoo_read_exists as r

class Client:
    def __init__(self, count=0, fail=None):
        self.count, self.fail, self.calls = count, fail, []
    def read_records(self, model, ids, fields=None):
        self.calls.append(['read', model, ids, fields])
        if fields == ['id']:
            return [{'id': i} for i in ids]   # Odoo fetches nothing for 'id' only
        return [{'id': i, 'name': 'Owned'} for i in ids] if self.count == 1 else []
    def execute_method(self, model, method, *args, **kwargs):
        self.calls.append(['execute', model, method, list(args), kwargs])
        if self.fail:
            raise ValueError(self.fail)
        return self.count

def run(client, **args):
    app = NS(odoo=client, _default_instance_name='default', schema_cache={})
    ctx = NS(request_context=NS(lifespan_context=app))
    return r.checked(tools_read.read_record)(ctx=ctx, **{'model': 'res.partner', 'fields': ['id'], 'instance': None, **args})

out = {}
for name, count, args in (('missing', 0, {'record_id': 2147483647}), ('present', 1, {'record_id': 1}),
                          ('named', 1, {'record_id': 1, 'fields': ['id', 'name']}),
                          ('named_missing', 0, {'record_id': 7, 'fields': ['name']}),
                          ('invalid_id', 0, {'record_id': 0})):
    client = Client(count)
    out[name] = [run(client, **args), client.calls]
for bad in (True, 2, '1', None, -1):
    client = Client(bad)
    out['bad %r' % (bad,)] = [run(client, record_id=1), len(client.calls)]
client = Client(fail='BACKEND_RPC_FAULT')
out['fault'] = [run(client, record_id=1), len(client.calls)]
print(json.dumps(out))
'''))
    count = ['execute', 'res.partner', 'search_count', [[['id', '=', MISSING]]], {'context': {'active_test': False}}]
    assert out['missing'] == [NOT_FOUND, [['read', 'res.partner', [MISSING], ['id']], count]]
    report, calls = out['present']
    assert report['success'] is True and report['result'] == {'id': 1} and report['fields_used'] == ['id']
    assert [c[0] for c in calls] == ['read', 'execute'] and calls[1][3] == [[['id', '=', 1]]]
    report, calls = out['named']   # any other field makes Odoo fetch the row: no count
    assert report['success'] is True and report['result'] == {'id': 1, 'name': 'Owned'}
    assert [c[0] for c in calls] == ['read']
    assert out['named_missing'] == [{'success': False, 'error': 'Record not found: res.partner ID 7'},
                                    [['read', 'res.partner', [7], ['name']]]]
    report, calls = out['invalid_id']   # the native refusal, before any RPC
    assert report['success'] is False and calls == []
    for bad in (True, 2, '1', None, -1):
        assert out['bad %r' % (bad,)] == [{'success': False, 'error': 'BACKEND_RESPONSE_INVALID'}, 2]
    assert out['fault'] == [{'success': False, 'error': 'BACKEND_RPC_FAULT'}, 2]


def test_install_wraps_the_registered_sync_handler_only():
    probe('''
from types import SimpleNamespace as NS
from odoo_mcp import server, tools_read
import odoo_read_exists as r
tool = server.mcp._tool_manager.get_tool('read_record')
assert tool.fn is tools_read.read_record and tool.is_async is False
r.install(server.mcp)
assert tool.fn is not tools_read.read_record and tool.fn.__wrapped__ is tools_read.read_record
for found in (None, NS(is_async=True, fn=None)):
    try:
        r.install(NS(_tool_manager=NS(get_tool=lambda name, found=found: found)))
    except RuntimeError:
        pass
    else:
        raise AssertionError(found)
for module in r.SOURCES:   # a source that differs from the reviewed one stops the install before any wrapping
    pinned = r.SOURCES[module]
    r.SOURCES[module] = '0' * 64
    try:
        r.install(NS(_tool_manager=NS(get_tool=lambda name: 1 / 0)))
    except RuntimeError as e:
        assert 'source review' in str(e)
    else:
        raise AssertionError(module)
    r.SOURCES[module] = pinned
''')


PRESENT = {1, 5}   # 5 is archived: read() returns it, search_count finds it only with active_test off


@contextmanager
def fake_odoo():
    events, failures, state = [], [], {'fault': False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def do_POST(self):
            try:
                params, method = xmlrpc.client.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if method == 'version':
                    value = {'server_version': '18.0', 'server_version_info': [18, 0, 0, 'final', 0]}
                elif method == 'authenticate':
                    value = 7
                else:
                    assert method == 'execute_kw'
                    model, op, args = params[3:6]
                    kw = params[6] if len(params) > 6 else {}
                    events.append([op, args, kw])
                    assert model == 'res.partner'
                    if op == 'read':
                        (ids,) = args
                        if kw.get('fields') == ['id']:
                            value = [{'id': i} for i in ids]
                        else:
                            value = [{'id': i, 'name': 'Owned'} for i in ids if i in PRESENT]
                    else:
                        assert op == 'search_count' and kw == {'context': {'active_test': False}}, (op, args, kw)
                        if state['fault']:
                            raise xmlrpc.client.Fault(1, 'raw backend fault text')
                        ((field, operator, record_id),) = args[0]
                        assert (field, operator) == ('id', '=')
                        value = 1 if record_id in PRESENT else 0
                data = xmlrpc.client.dumps((value,), methodresponse=True, allow_none=True).encode()
            except xmlrpc.client.Fault as exc:
                data = xmlrpc.client.dumps(exc).encode()
            except Exception as exc:
                failures.append(repr(exc))
                data = xmlrpc.client.dumps(xmlrpc.client.Fault(1, 'fake assertion')).encode()
            self.send_response(200); self.send_header('Content-Type', 'text/xml')
            self.send_header('Content-Length', str(len(data))); self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', events, failures, state
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


async def test_genuine_child_reports_a_missing_id_only_read_as_not_found(tmp_path):
    with fake_odoo() as (url, events, failures, state):
        store = ProductStore(tmp_path / 'state', 'odoo')
        store.update(connection=connection('odoo', url))
        endpoint = Endpoint('odoo')
        process = endpoint.supervisor(child_spec(store.load(), store.directory))
        try:
            await process.start()
            async with endpoint.client() as child:
                _, app = make_apps(store, TOOLS['odoo'], child, child_url=endpoint.url)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://boundary') as client:
                    headers = {'Authorization': 'Bearer ' + store.load().token,
                               'Accept': 'application/json, text/event-stream'}
                    await initialize(client, headers)

                    async def read(record_id, fields):
                        before = len(events)
                        reply = await rpc(client, '/mcp', headers, call(
                            'read_record', {'model': 'res.partner', 'record_id': record_id, 'fields': fields}))
                        assert reply.get('isError') is not True, reply
                        return json.loads(reply['content'][0]['text']), [e[0] for e in events[before:]]

                    assert await read(MISSING, ['id']) == (NOT_FOUND, ['read', 'search_count'])
                    for present in sorted(PRESENT):
                        value, ops = await read(present, ['id'])
                        assert value['success'] is True and value['result'] == {'id': present}, value
                        assert ops == ['read', 'search_count']
                    value, ops = await read(1, ['id', 'name'])
                    assert value['success'] is True and value['result'] == {'id': 1, 'name': 'Owned'} and ops == ['read']
                    assert await read(9, ['name']) == ({'success': False, 'error': 'Record not found: res.partner ID 9'},
                                                       ['read'])
                    state['fault'] = True
                    value, ops = await read(1, ['id'])
                    assert value == {'success': False, 'error': 'BACKEND_RPC_FAULT'} and ops == ['read', 'search_count']
                    assert 'raw backend fault text' not in json.dumps(value)
                    assert not failures, failures
                    await client.delete('/mcp', headers=headers)
        finally:
            await process.stop(); store.close()
