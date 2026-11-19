"""HM-23 (multi-profile plan 12.3; PaaS #153, woow-mcp-server 5b84b5d: cd1ed89, 4b4fd16, 574c805): the three EMQX
fixes PaaS made after its EMQX 5.8.9 field test of 2026-11-14 (its report mp-emqx-20261114, F-01 to F-03), on the HA
add-on's EMQX child. The vendored code is the same as PaaS's before #153; HA's own outbound layer is
apps/runtime/backend_policy.py (no PaaS BrokerClient), so the transport half of each fix sits in deps.EmqxHttp.request,
the one door every tool's request goes through.

- F-01 emqx_list_subscriptions: match_topic is a wildcard search over the stored subscription filters, not a delivery
  lookup (a concrete topic never finds a wildcard subscription). The tool and parameter descriptions said the opposite;
  they now say what the broker does, word for word as PaaS. The parameter still goes to GET /subscriptions unchanged
  and the rows come back as the broker sent them.
- F-02 emqx_prometheus_stats: EMQX answers GET /prometheus/stats with the Prometheus exposition text only to
  Accept: text/plain (JSON statistics otherwise), so this one request asks for text/plain; every other request keeps
  application/json. Only those two Accept values exist (anything else, and any request option but params, json,
  content and data, is refused before any I/O); an empty text answer (a 204 too) is EMQX_INVALID_RESPONSE.
- F-03 an identifier httpx will not build into a URL (over 65,536 characters once encoded) or one that cannot be encoded
  (a lone surrogate) is refused with the fixed code EMQX_DESTINATION_DENIED before any request, instead of an exception
  that FastMCP masked as "Error calling tool ..." and logged with a traceback. Normal lengths are unchanged.

Not taken over from PaaS's tests (PaaS-only rules of its BrokerClient, not part of #153 and not in HA's transport): the
4 MiB response limit and the refusal of compressed answers.

Not gated by the multi-profile switch (contract 1.2): every EMQX child gets it with the product's next version. The
child runs in-process in its own pinned environment (apps/emqx/.venv, as CI installs it) with the environment
products.child_spec builds for it (fake values: T x 43, C x 43), every tool registered, against a loopback fake broker
the harness starts; the gateway's packaged listing is checked here too, and one test runs the real child process behind
the gateway (its own output must show no traceback). The case-by-case map to PaaS's tests is in
docs/provenance/ha-multiprofile-HM-23-20261119.md.
"""
import asyncio
from contextlib import closing
import json
import subprocess

import httpx
import pytest

import loopback_backends
from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.health import protocol_reply
from mcp_admin_core.products import DENY_LOOPBACK_ENV, ProductState, ProductStore, TOOLS, child_spec
from mcp_admin_core.tool_snapshot import LISTED
from owned_runtime import Endpoint
from test_child_bearer import RawLogs

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan
FAKES = ('T' * 43, 'C' * 43)
CONNECTION = {'url': 'http://broker.invalid', 'api_key': FAKES[0], 'api_secret': FAKES[1]}
CODE = 'EMQX_DESTINATION_DENIED'
# PaaS cd1ed89: the claims in the old descriptions that said the opposite of what the broker does (blanks squashed).
OLD_CLAIMS = (
    'whose filter would match this concrete topic',
    "use this to answer 'who receives messages published here?'",
    'given a concrete topic, it tells you exactly which subscribers would receive a message on it',
)
# PaaS cd1ed89, apps/emqx/emqx_mcp_server/tools/topics.py: the parameter description and the docstring, verbatim.
PAAS_PARAM = (
    "Wildcard SEARCH over the stored subscription filters, not a delivery lookup. The value is used as a topic filter "
    "('+' and '#' allowed) and compared with the filters clients subscribed with: a subscription is returned when its "
    "stored filter is matched by yours (a stored 'sensors/#' is found with 'sensors/#'). A concrete topic such as "
    "'sensors/a/temp' does NOT find a wildcard subscription like 'sensors/#', so an empty result does not mean nobody "
    "would receive that topic.")
PAAS_DOC = (
    "Every subscription in the cluster, with the filter each was stored under.\n\n"
    "Narrow with `clientid` (one device's subscriptions), `topic` (an exact\n"
    "stored filter) or `match_topic` (a wildcard search over the stored\n"
    "filters, see its description; it is not a delivery lookup).\n\n"
    "To answer \"who receives messages published to topic T?\", do not use\n"
    "`match_topic`: list the subscriptions (use `clientid` when you know the\n"
    "device, `page` for more) and compare each row's stored `topic` with T\n"
    "yourself, by the MQTT wildcard rules ('+' = exactly one level, '#' = all\n"
    "remaining levels). An empty `match_topic` result never proves that\n"
    "nobody is subscribed.")

HARNESS = r'''
import asyncio
import base64
import json
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit

KEY, SECRET = os.environ['EMQX_MCP_API_KEY'], os.environ['EMQX_MCP_API_SECRET']
AUTH = 'Basic ' + base64.b64encode((KEY + ':' + SECRET).encode()).decode()
TEXT = 'text/plain; version=0.0.4; charset=utf-8'
PROM = '/api/v5/prometheus/stats'
HEAD = '# HELP emqx_connections_count Number of connections\n# TYPE emqx_connections_count gauge\nemqx_connections_count 7\n'
EXPOSITION = HEAD + ''.join('emqx_messages_received{node="emqx@127.0.0.1",shard="%d"} %d\n' % (i, i * 7)
                            for i in range(3000))
CODE = 'EMQX_DESTINATION_DENIED'


class Broker(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(('127.0.0.1', 0), Handler)
        self.reset()

    def reset(self):
        self.requests, self.routes, self.text_routes, self.headers = [], {}, {}, {}
        self.status, self.response, self.body, self.content_type = 200, None, None, 'application/json'


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def respond(self):
        server = self.server
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else b''
        server.requests.append({'method': self.command, 'path': self.path, 'accept': self.headers.get('Accept'),
                                'body': body.decode('utf-8', 'replace')})
        path = urlsplit(self.path).path
        if self.headers.get('Authorization') != AUTH:
            status, value = 401, {'error': 'bad credentials'}
        else:
            status, value = server.status, server.routes.get(path, server.response)
            if value is None:
                value = ([{'node': 'emqx@owned', 'version': '5.8.9'}] if path.endswith('/nodes') else
                         [{'connections.count': 7}] if path.endswith('/stats') else {'data': [], 'meta': {'count': 0}})
        data = server.body if server.body is not None else json.dumps(value).encode()
        content_type = server.content_type
        text = server.text_routes.get(path)
        if status == 200 and text is not None and server.body is None and 'text/plain' in (self.headers.get('Accept') or ''):
            data, content_type = text.encode(), TEXT
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        for name, value in server.headers.items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_GET = do_POST = do_PUT = do_DELETE = respond


broker = Broker()
threading.Thread(target=broker.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True).start()
assert os.environ['EMQX_MCP_BASE_URL'] == 'http://broker.invalid', 'the saved URL is the test state one'
os.environ['EMQX_MCP_BASE_URL'] = 'http://127.0.0.1:%d' % broker.server_port
# Every tool registered, as PaaS's tests' policy {"tools": {"disabled": []}} (the state's own policy is not under test).
os.environ['EMQX_MCP_READONLY'], os.environ['EMQX_MCP_DISABLED_TOOLS'] = 'false', ''

import backend_policy
import fastmcp
import httpx
from emqx_mcp_server import deps, lifespan
from emqx_mcp_server.errors import EmqxApiError, emqx_request
from emqx_mcp_server.server import build_server
from emqx_mcp_server.tools._common import path_segment


class Records(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def tracebacks(self):
        return sum(1 for r in self.records if r.exc_info or r.exc_text or r.stack_info or 'Traceback' in self.format(r))


records = Records()
for name in ('', 'fastmcp', 'mcp'):
    logging.getLogger(name).addHandler(records)


def text_of(result):
    return ' '.join(getattr(item, 'text', '') for item in result.content)


def failure(exc):
    return {'type': type(exc).__name__, 'message': str(exc)[:200]}


async def outcome(client, name, args):
    """A tool call through MCP: whether it is an error, its text (bounded), its structured result."""
    try:
        result = await client.call_tool(name, args, raise_on_error=False)
    except Exception as exc:  # before the fixes, a few refusals were protocol errors, not tool results
        return {'error': True, 'text': 'raised ' + type(exc).__name__, 'length': 0, 'structured': None}
    text = text_of(result)
    return {'error': result.is_error, 'text': text[:300], 'length': len(text), 'structured': result.structured_content}


async def direct(method, path, **kwargs):
    """EmqxHttp.request (the tools' one door) and then emqx_request, each on a fresh client: what each raised."""
    found = {}
    for name in ('request', 'emqx_request'):
        async with lifespan.make_client() as client:
            http = deps.EmqxHttp(client)
            try:
                if name == 'request':
                    response = await http.request(method, path, **kwargs)
                else:
                    response = await emqx_request(http, method, path, **kwargs)
                found[name] = {'type': 'response', 'status': response.status_code, 'text': response.text[:300]}
            except Exception as exc:
                found[name] = failure(exc)
    return found


VALUES = ['sub/a/#', 'sub/a/+', 'sub/a/deep/x', 'sub/+/x', '$SYS/brokers/+/clients/#', '中文/主題', 'a b/c%d', 'x&y=z#w']


async def f01(client):
    tool = next(t for t in await client.list_tools() if t.name == 'emqx_list_subscriptions')
    out = {'description': tool.description, 'param': tool.input_schema['properties']['match_topic'].get('description'),
           'forwarded': []}
    for value in VALUES:
        broker.reset()
        result = await outcome(client, 'emqx_list_subscriptions', {'match_topic': value})
        request = broker.requests[0] if len(broker.requests) == 1 else None
        split = urlsplit(request['path']) if request else None
        out['forwarded'].append({'error': result['error'], 'requests': len(broker.requests),
                                 'method': request and request['method'], 'path': split and split.path,
                                 'match_topic': split and parse_qs(split.query, keep_blank_values=True).get('match_topic')})
    broker.reset()
    args = {'clientid': 'cli-a', 'topic': 'sub/a/#', 'match_topic': 'sub/a/+', 'qos': 1, 'page': 2, 'limit': 5}
    result = await outcome(client, 'emqx_list_subscriptions', args)
    out['names'] = {'error': result['error'], 'query': parse_qs(urlsplit(broker.requests[0]['path']).query)}
    row = {'clientid': 'cli-a', 'topic': 'sub/a/#', 'qos': 1, 'node': 'emqx@127.0.0.1'}
    broker.reset()
    broker.routes = {'/api/v5/subscriptions': {'data': [row], 'meta': {'count': 1}}}
    found = await outcome(client, 'emqx_list_subscriptions', {'match_topic': 'sub/a/deep/x'})
    broker.routes = {'/api/v5/subscriptions': {'data': [], 'meta': {'count': 0}}}
    empty = await outcome(client, 'emqx_list_subscriptions', {'match_topic': 'sub/a/deep/x'})
    out['rows'] = {'found': found['structured'], 'empty': empty['structured'], 'row': row}
    return out


# (tool, arguments): every tool but emqx_prometheus_stats, as PaaS's test_39_calls CASES.
OTHERS = [
    ('cluster_status', {}), ('node_detail', {'node': 'emqx@owned'}), ('broker_stats', {}), ('metrics_current', {}),
    ('metrics_history', {}), ('list_alarms', {}), ('list_clients', {}), ('get_client', {'clientid': 'owned'}),
    ('client_subscriptions', {'clientid': 'owned'}), ('kick_client', {'clientid': 'owned'}),
    ('client_subscribe', {'clientid': 'owned', 'topic': 'owned/topic'}),
    ('client_unsubscribe', {'clientid': 'owned', 'topic': 'owned/topic'}), ('list_topics', {}),
    ('list_subscriptions', {}), ('publish', {'topic': 'owned/topic', 'payload': 'owned-message'}),
    ('publish_bulk', {'messages': [{'topic': 'owned/topic', 'payload': 'owned-message'}]}), ('list_retained', {}),
    ('get_retained', {'topic': 'owned/topic'}), ('delete_retained', {'topic': 'owned/topic'}), ('list_authn', {}),
    ('manage_authn_users', {'operation': 'read'}), ('list_authz_sources', {}), ('authz_settings', {}),
    ('manage_authz_rules', {'operation': 'read'}), ('list_banned', {}), ('ban', {'subject_type': 'clientid', 'who': 'owned'}),
    ('unban', {'subject_type': 'clientid', 'who': 'owned'}), ('list_traces', {}),
    ('create_trace', {'name': 'owned', 'target_type': 'clientid', 'target': 'owned'}),
    ('get_trace_log', {'name': 'owned'}), ('delete_trace', {'name': 'owned'}), ('list_listeners', {}),
    ('list_rules', {}), ('get_rule_metrics', {'rule_id': 'owned'}), ('toggle_rule', {'rule_id': 'owned', 'enable': False}),
    ('test_rule_sql', {'sql': 'SELECT * FROM "owned/#"'}), ('list_connectors', {}), ('list_actions', {}),
]
ROUTES = {
    '/api/v5/authorization/sources': {'sources': [{'type': 'built_in_database'}]},
    '/api/v5/publish': {'id': 'owned-id', 'reason_code': 0},
    '/api/v5/publish/bulk': [{'id': 'owned-id', 'reason_code': 0}],
    '/api/v5/mqtt/retainer/message/owned%2Ftopic': {'payload': 'b3duZWQ=', 'qos': 0},
    '/api/v5/trace/owned/log_detail': [],
}
BAD_ACCEPT = ['text/html', '*/*', 'text/plain, application/json', 'application/json;q=0.1', 'text/plain\r\nX-Injected: 1',
              '', 'TEXT/PLAIN', None, 1, ['text/plain'], {'a': 1}]
OPTIONS = {'headers': {'headers': {'Accept': 'text/plain'}}, 'any header': {'headers': {'X-Anything': '1'}},
           'cookies': {'cookies': {'a': 'b'}}, 'auth': {'auth': ('a', 'b')}, 'redirects': {'follow_redirects': True}}


async def f02(client):
    out = {}
    broker.reset()
    broker.text_routes = {PROM: EXPOSITION}
    result = await outcome(client, 'emqx_prometheus_stats', {'max_bytes': 262144})
    structured = result['structured'] or {}
    out['text'] = {'error': result['error'], 'accepts': [r['accept'] for r in broker.requests],
                   'paths': [(r['method'], urlsplit(r['path']).path) for r in broker.requests],
                   'whole': structured == {'truncated': False, 'text': EXPOSITION}}
    small = await outcome(client, 'emqx_prometheus_stats', {'max_bytes': 1024})
    default = await outcome(client, 'emqx_prometheus_stats', {})
    out['cut'] = {'small': small['structured'] == {'truncated': True, 'text': EXPOSITION[:1024]},
                  'default': default['structured'] == {'truncated': True, 'text': EXPOSITION[:65536]},
                  'starts': ((small['structured'] or {}).get('text') or '').startswith('# HELP emqx_connections_count'),
                  'longer_than_default': len(EXPOSITION) > 65536}
    broker.reset()
    result = await outcome(client, 'emqx_prometheus_stats', {})
    try:
        parsed = json.loads((result['structured'] or {}).get('text') or 'null')
    except ValueError:
        parsed = 'not JSON'
    out['json_broker'] = {'error': result['error'], 'parsed': parsed}
    broker.reset()
    broker.routes, broker.text_routes = dict(ROUTES), {PROM: EXPOSITION}
    silent = []  # a tool whose call sent no request at all (its Accept would not be seen)
    for short, args in OTHERS:
        before = len(broker.requests)
        await outcome(client, 'emqx_' + short, args)
        if len(broker.requests) == before:
            silent.append(short)
    out['others'] = {'tools': len(OTHERS), 'silent': silent, 'requests': len(broker.requests),
                     'accepts': sorted({str(r['accept']) for r in broker.requests})}
    out['empty'] = []
    for body in (b'', b'\n', b' \r\n \t'):
        broker.reset()
        broker.body, broker.content_type = body, TEXT
        result = await outcome(client, 'emqx_prometheus_stats', {})
        out['empty'].append({'error': result['error'], 'code': 'EMQX_INVALID_RESPONSE' in result['text'],
                             'requests': len(broker.requests)})
    broker.reset()
    broker.status, broker.body, broker.content_type = 204, b'', TEXT
    result = await outcome(client, 'emqx_prometheus_stats', {})
    out['no_content'] = {'error': result['error'], 'code': 'EMQX_INVALID_RESPONSE' in result['text']}
    out['statuses'] = {}
    for status, fragment in ((401, '401'), (404, '404'), (500, 'EMQX_API_ERROR status=500')):
        broker.reset()
        broker.status, broker.response = status, {'message': 'leak-canary-message'}
        result = await outcome(client, 'emqx_prometheus_stats', {})
        out['statuses'][str(status)] = {'error': result['error'], 'fragment': fragment in result['text'],
                                        'echo': 'leak-canary' in result['text']}
    out['other_json'] = []
    for body in (b'', b'<html>login</html>', b'null', b'42'):
        broker.reset()
        broker.body = body
        result = await outcome(client, 'emqx_broker_stats', {})
        out['other_json'].append({'error': result['error'], 'code': 'EMQX_INVALID_RESPONSE' in result['text']})
    broker.reset()
    broker.text_routes = {PROM: EXPOSITION}
    asked = {'text': await direct('GET', '/prometheus/stats', accept='text/plain'),
             'default': await direct('GET', '/prometheus/stats'),
             'json': await direct('GET', '/prometheus/stats', accept='application/json')}
    out['transport'] = {name: {'request_type': value['request']['type'],
                               'text': value['request'].get('text', '') == EXPOSITION[:300],
                               'json': value['request'].get('text', '')[:40]} for name, value in asked.items()}
    out['transport_accepts'] = [r['accept'] for r in broker.requests]
    out['bad_accept'] = []
    for accept in BAD_ACCEPT:
        broker.reset()
        out['bad_accept'].append({'value': repr(accept), **(await direct('GET', '/prometheus/stats', accept=accept)),
                                  'requests': len(broker.requests)})
    out['options'] = {}
    for name, extra in OPTIONS.items():
        broker.reset()
        out['options'][name] = {**(await direct('GET', '/nodes', **extra)), 'requests': len(broker.requests)}
    return out


LONG = 'a' * 400_000
LONG_CASES = [
    ('emqx_get_client', {'clientid': LONG}, 'clientid'),
    ('emqx_client_subscriptions', {'clientid': LONG}, 'clientid'),
    ('emqx_kick_client', {'clientid': LONG}, 'clientid'),
    ('emqx_client_subscribe', {'clientid': LONG, 'topic': 'owned/topic'}, 'clientid'),
    ('emqx_client_unsubscribe', {'clientid': LONG, 'topic': 'owned/topic'}, 'clientid'),
    ('emqx_get_retained', {'topic': LONG}, 'topic'),
    ('emqx_delete_retained', {'topic': LONG}, 'topic'),
    ('emqx_node_detail', {'node': LONG}, 'node'),
    ('emqx_get_trace_log', {'name': LONG}, 'name'),
    ('emqx_delete_trace', {'name': LONG}, 'name'),
    ('emqx_get_rule_metrics', {'rule_id': LONG}, 'rule_id'),
    ('emqx_toggle_rule', {'rule_id': LONG, 'enable': True}, 'rule_id'),
    ('emqx_unban', {'subject_type': 'clientid', 'who': LONG}, 'who'),
    ('emqx_manage_authn_users', {'operation': 'delete', 'user_id': LONG}, 'user_id'),
    ('emqx_manage_authn_users', {'operation': 'read', 'authenticator_id': LONG}, 'authenticator_id'),
    ('emqx_manage_authz_rules', {'operation': 'delete', 'subject_type': 'username', 'subject': LONG}, 'subject'),
    ('emqx_list_clients', {'username': LONG}, 'username(query)'),
    ('emqx_list_subscriptions', {'match_topic': LONG}, 'match_topic(query)'),
]
LOOKUPS = ('/api/v5/authorization/sources',)  # a lookup a tool makes before its own request


async def f03(client):
    out = {'long': []}
    for tool, args, field in LONG_CASES:
        broker.reset()
        broker.routes = {'/api/v5/authorization/sources': {'sources': [{'type': 'built_in_database'}]}}
        before = records.tracebacks()
        result = await outcome(client, tool, args)
        out['long'].append({'case': tool + ':' + field, 'error': result['error'], 'code': CODE in result['text'],
                            'echo': 'aaaaaaaaaaaaaaaa' in result['text'], 'length': result['length'],
                            'url_too_long': 'URL too long' in result['text'], 'httpx': 'httpx' in result['text'].lower(),
                            'requests': len([r for r in broker.requests if urlsplit(r['path']).path not in LOOKUPS]),
                            'tracebacks': records.tracebacks() - before})
    out['made_of'] = {}
    for name, value in (('percent', '%' * 400_000), ('cjk', '毛' * 100_000), ('slash', '/' * 400_000),
                        ('newline', '\n' * 70_000)):
        broker.reset()
        result = await outcome(client, 'emqx_get_client', {'clientid': value})
        out['made_of'][name] = {'error': result['error'], 'code': CODE in result['text'], 'requests': len(broker.requests)}
    try:
        path_segment('a\ud800b', 'clientid')
        out['path_segment'] = {'type': 'returned'}
    except Exception as exc:
        out['path_segment'] = failure(exc)
        out['path_segment']['message'] = str(exc)
    out['cannot_build'] = {}
    for name, (method, path, kwargs) in {
            'query-surrogate': ('GET', '/subscriptions', {'params': {'match_topic': 'a\ud800'}}),
            'json-surrogate': ('POST', '/publish', {'json': {'topic': 'a\ud800', 'payload': 'x'}}),
            'query-too-long': ('GET', '/subscriptions', {'params': {'a': 'x' * 70_000}})}.items():
        broker.reset()
        out['cannot_build'][name] = {**(await direct(method, path, **kwargs)), 'requests': len(broker.requests)}
    broker.reset()
    analysed = []
    original = backend_policy.no_dot_segments

    def watched(url):
        analysed.append(len(str(url)))
        return original(url)
    backend_policy.no_dot_segments = watched
    try:
        out['precheck'] = {**(await direct('GET', '/clients/' + quote('%' * 400_000, safe=''))),
                           'analysed': analysed[:], 'requests': len(broker.requests)}
    finally:
        backend_policy.no_dot_segments = original
    broker.reset()
    out['surrogate_tools'] = []
    for tool, args in (('emqx_get_client', {'clientid': 'a\ud800b'}), ('emqx_list_subscriptions', {'match_topic': 'a\ud800'}),
                       ('emqx_client_subscribe', {'clientid': 'owned', 'topic': 'a\ud800'})):
        result = await outcome(client, tool, args)
        out['surrogate_tools'].append({'tool': tool, 'error': result['error'], 'code': CODE in result['text']})
    out['surrogate_requests'] = len(broker.requests)
    out['normal'] = []
    for value in ('a' * 1000, 'a' * 64_000, '毛' * 5000, 'a/b?c#d' * 3000):
        broker.reset()
        got = await outcome(client, 'emqx_get_client', {'clientid': value})
        match = await outcome(client, 'emqx_list_subscriptions', {'match_topic': value[:60_000]})
        first = urlsplit(broker.requests[0]['path']).path if broker.requests else None
        out['normal'].append({'length': len(value), 'error': got['error'], 'match_error': match['error'],
                              'path': first == '/api/v5/clients/' + quote(value, safe='')})
    broker.reset()
    fits = await outcome(client, 'emqx_get_client', {'clientid': '毛' * 5000})
    over = await outcome(client, 'emqx_get_client', {'clientid': '毛' * 8000})
    out['cjk_limit'] = {'fits': fits['error'], 'over': over['error'], 'code': CODE in over['text'],
                        'requests': len(broker.requests)}
    return out


async def main():
    observed = {}
    async with fastmcp.Client(build_server()) as client:
        for name, scenario in (('f01', f01), ('f02', f02), ('f03', f03)):
            try:
                observed[name] = await scenario(client)
            except Exception as exc:
                observed[name] = {'harness_error': failure(exc)}
    observed['tracebacks'] = records.tracebacks()
    return observed


observed = asyncio.run(main())
broker.shutdown()
broker.server_close()
print(json.dumps(observed, sort_keys=True, ensure_ascii=True, default=str))
'''


@pytest.fixture(scope='module')
def observed(tmp_path_factory):
    """One run of the harness in the EMQX child's pinned environment, the child's environment from products.child_spec
    (the fake broker is on loopback, which a switched-on product's child refuses: loopback_backends lets this test's
    fake through, whatever the repository switch says, HM-20)."""
    state = ProductState(product='emqx', token=FAKES[0], child_token=FAKES[1], connection=CONNECTION)
    with loopback_backends.allowed():
        spec = child_spec(state, tmp_path_factory.mktemp('emqx-field'))
    assert DENY_LOOPBACK_ENV not in spec.env
    result = subprocess.run([spec.argv[0], '-c', HARNESS], env=spec.env, cwd=spec.cwd, capture_output=True,
                            text=True, timeout=300)
    leaked = any(fake in result.stdout + result.stderr for fake in FAKES)
    assert result.returncode == 0, 'harness failed (output withheld: it holds a fake credential)' if leaked else (
        result.stderr[-4000:])
    assert not leaked, 'a credential reached the harness output'
    return json.loads(result.stdout.splitlines()[-1])


@pytest.fixture(autouse=True)
def fake_values_never_logged(log_scan):
    log_scan.watch(*FAKES, kind='secret')


def squash(text):
    return ' '.join((text or '').split())


def scenario(observed, name):
    value = observed[name]
    assert 'harness_error' not in value, value
    return value


# ---- F-01: match_topic says what the broker does (PaaS cd1ed89, test_subscription_match_topic.py) ----

def test_descriptions_no_longer_claim_the_opposite_direction(observed):
    found = scenario(observed, 'f01')
    param, whole = squash(found['param']).lower(), squash(found['description']).lower()
    for claim in OLD_CLAIMS:
        assert claim not in param and claim not in whole, claim


def test_the_descriptions_are_the_paas_text(observed):
    """Word for word PaaS cd1ed89's parameter description and docstring (FastMCP takes the docstring as the tool's
    description), so a client sees the same text from the PaaS server and from the add-on."""
    found = scenario(observed, 'f01')
    assert found['param'] == PAAS_PARAM
    assert found['description'] == PAAS_DOC


def test_match_topic_parameter_states_what_the_broker_really_does(observed):
    param = squash(scenario(observed, 'f01')['param']).lower()
    assert 'filter' in param and 'stored' in param
    assert 'not a delivery lookup' in param
    assert 'concrete topic' in param and 'wildcard subscription' in param
    assert 'sensors/#' in param and 'sensors/a/temp' in param


def test_tool_description_names_the_way_to_answer_who_receives(observed):
    whole = squash(scenario(observed, 'f01')['description']).lower()
    assert 'who receives messages published to topic' in whole
    assert 'list the subscriptions' in whole and 'compare' in whole
    assert "'+' = exactly one level" in whole and "'#' = all remaining levels" in whole
    assert 'never proves that nobody is subscribed' in whole


def test_match_topic_is_forwarded_unchanged_as_a_query_parameter(observed):
    forwarded = scenario(observed, 'f01')['forwarded']
    values = ['sub/a/#', 'sub/a/+', 'sub/a/deep/x', 'sub/+/x', '$SYS/brokers/+/clients/#', '中文/主題', 'a b/c%d',
              'x&y=z#w']
    assert [row['match_topic'] for row in forwarded] == [[value] for value in values]
    assert all(not row['error'] and row['requests'] == 1 for row in forwarded), forwarded
    assert {(row['method'], row['path']) for row in forwarded} == {('GET', '/api/v5/subscriptions')}


def test_other_filters_keep_their_query_names(observed):
    names = scenario(observed, 'f01')['names']
    assert not names['error']
    assert names['query'] == {'clientid': ['cli-a'], 'topic': ['sub/a/#'], 'match_topic': ['sub/a/+'], 'qos': ['1'],
                              'page': ['2'], 'limit': ['5']}


def test_rows_are_returned_as_the_broker_sent_them_without_client_side_matching(observed):
    rows = scenario(observed, 'f01')['rows']
    assert rows['found'] == {'count': 1, 'total': 1, 'subscriptions': [rows['row']]}
    assert rows['empty'] == {'count': 0, 'total': 0, 'subscriptions': []}


def test_the_gateways_packaged_listing_carries_the_same_text(observed):
    """The listing the gateway answers tools/list with while no child answers (tool_snapshot.LISTED, regenerated from
    the real children; tests/test_tool_snapshot.py) has the child's new text too."""
    found = scenario(observed, 'f01')
    [tool] = [tool for tool in LISTED['emqx'] if tool['name'] == 'emqx_list_subscriptions']
    assert tool['description'] == found['description']
    assert tool['inputSchema']['properties']['match_topic']['description'] == found['param']


# ---- F-02: emqx_prometheus_stats asks for text/plain, every other request for JSON (PaaS 4b4fd16) ----

def test_the_prometheus_tool_asks_for_text_and_returns_the_exposition_text(observed):
    text = scenario(observed, 'f02')['text']
    assert not text['error']
    assert text['accepts'] == ['text/plain']
    assert text['paths'] == [['GET', '/api/v5/prometheus/stats']]  # a JSON array: the harness prints JSON
    assert text['whole']


def test_the_exposition_text_is_cut_at_max_bytes_not_in_the_middle_of_json(observed):
    cut = scenario(observed, 'f02')['cut']
    assert cut == {'small': True, 'default': True, 'starts': True, 'longer_than_default': True}


def test_a_broker_that_still_answers_json_is_passed_through_as_before(observed):
    """No text for text/plain (the broker answers JSON): as before the fix, the text comes back as it is, no error."""
    found = scenario(observed, 'f02')['json_broker']
    assert not found['error'] and found['parsed'] == [{'connections.count': 7}]


def test_every_other_tool_keeps_asking_for_json(observed):
    """The other 38 tools, each called once (PaaS's test_39_calls arguments): every one reaches the broker, and every
    request of theirs asks for application/json."""
    others = scenario(observed, 'f02')['others']
    assert others['tools'] == 38 and others['silent'] == []
    assert others['requests'] >= 38
    assert others['accepts'] == ['application/json']


def test_empty_exposition_text_is_refused_not_reported_as_success(observed):
    assert scenario(observed, 'f02')['empty'] == [{'error': True, 'code': True, 'requests': 1}] * 3


def test_a_204_for_the_text_request_is_not_an_empty_success_either(observed):
    assert scenario(observed, 'f02')['no_content'] == {'error': True, 'code': True}


def test_error_statuses_for_the_text_request_are_mapped_like_any_other_tool(observed):
    assert scenario(observed, 'f02')['statuses'] == {
        status: {'error': True, 'fragment': True, 'echo': False} for status in ('401', '404', '500')}


def test_other_tools_still_refuse_empty_and_malformed_200_json(observed):
    assert scenario(observed, 'f02')['other_json'] == [{'error': True, 'code': True}] * 4


def test_the_door_serves_text_only_when_asked_with_the_fixed_value(observed):
    found = scenario(observed, 'f02')
    transport = found['transport']
    assert transport['text'] == {'request_type': 'response', 'text': True, 'json': transport['text']['json']}
    for name in ('default', 'json'):
        assert transport[name]['request_type'] == 'response' and transport[name]['json'].startswith('[{"connections.')
    # EmqxHttp.request, then emqx_request, for each of: text/plain, the default, application/json
    assert found['transport_accepts'] == ['text/plain'] * 2 + ['application/json'] * 4


def test_any_other_accept_value_is_refused_before_io(observed):
    for case in scenario(observed, 'f02')['bad_accept']:
        assert case['request']['type'] == 'BackendDenied', case
        assert case['emqx_request'] == {'type': 'EmqxApiError', 'message': CODE}, case
        assert case['requests'] == 0, case


def test_callers_still_cannot_pass_headers_or_other_request_options(observed):
    for name, case in scenario(observed, 'f02')['options'].items():
        assert case['request']['type'] == 'BackendDenied', name
        assert case['emqx_request'] == {'type': 'EmqxApiError', 'message': CODE}, name
        assert case['requests'] == 0, name


# ---- F-03: an identifier that cannot become a URL gets the fixed code (PaaS 574c805, test_long_identifiers.py) ----

def test_an_overlong_identifier_gets_the_fixed_code_and_never_leaves_the_process(observed):
    for case in scenario(observed, 'f03')['long']:
        assert case['error'] and case['code'], case
        assert not case['echo'] and case['length'] < 300, case  # no echo of the argument, not the masked FastMCP error
        assert not case['url_too_long'] and not case['httpx'], case
        assert case['requests'] == 0, case  # nothing reached the broker
        assert case['tracebacks'] == 0, case
    assert len(scenario(observed, 'f03')['long']) == 18


def test_the_fixed_code_does_not_depend_on_what_the_long_value_is_made_of(observed):
    assert scenario(observed, 'f03')['made_of'] == {
        name: {'error': True, 'code': True, 'requests': 0} for name in ('percent', 'cjk', 'slash', 'newline')}


def test_a_path_value_that_cannot_be_encoded_is_refused_with_the_fixed_code(observed):
    found = scenario(observed, 'f03')['path_segment']
    assert found == {'type': 'EmqxApiError', 'message': CODE}


def test_a_request_that_cannot_be_built_is_denied_before_any_io(observed):
    for name, case in scenario(observed, 'f03')['cannot_build'].items():
        assert case['request']['type'] == 'BackendDenied', name
        assert case['emqx_request'] == {'type': 'EmqxApiError', 'message': CODE}, name
        assert case['requests'] == 0, name


def test_a_path_httpx_would_refuse_is_denied_before_any_path_analysis(observed):
    """'%' x 400,000 encoded is 1.2 million characters: refused before backend_policy looks at the path (PaaS: before
    its path analysis spends linear work on it)."""
    found = scenario(observed, 'f03')['precheck']
    assert found['request']['type'] == 'BackendDenied' and found['emqx_request']['message'] == CODE
    assert found['analysed'] == [] and found['requests'] == 0


def test_a_lone_surrogate_in_a_tool_argument_gets_the_fixed_code(observed):
    found = scenario(observed, 'f03')
    assert [(case['error'], case['code']) for case in found['surrogate_tools']] == [(True, True)] * 3
    assert found['surrogate_requests'] == 0


def test_a_long_but_valid_identifier_still_reaches_the_broker_unchanged(observed):
    assert scenario(observed, 'f03')['normal'] == [
        {'length': length, 'error': False, 'match_error': False, 'path': True}
        for length in (1000, 64_000, 5000, 21_000)]


def test_the_limit_is_on_the_encoded_length_so_a_cjk_value_stops_earlier(observed):
    assert scenario(observed, 'f03')['cjk_limit'] == {'fits': False, 'over': True, 'code': True, 'requests': 1}


def test_no_traceback_was_logged(observed):
    assert observed['tracebacks'] == 0


# ---- the real child behind the gateway: no traceback in its own output (PaaS 574c805) ----

async def test_the_real_child_prints_no_traceback_for_an_overlong_identifier(tmp_path, log_scan):
    """The child process as the add-on starts it (products.child_spec, run_child), behind the gateway: the two calls of
    PaaS's field test with a 400,000-character clientid and topic get the fixed code, and the child's own output (its
    stdout and stderr, read before the Supervisor's scrub) shows no traceback, library path or the argument; a normal
    call still reaches the broker."""
    from test_six_hardening import Quiet, call, serve

    seen = []

    class Broker(Quiet):
        def answer(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0) or 0))
            seen.append((self.command, self.path))
            if self.path.endswith('/nodes'):
                return self.reply([{'node': 'emqx@owned', 'version': '5.8.9'}])
            self.reply({'clientid': 'owned', 'connected': True})
        do_GET = do_POST = do_PUT = do_DELETE = answer

    long = 'a' * 400_000
    with serve(Broker) as url, closing(ProductStore(tmp_path / 'state', 'emqx')) as store:
        store.update(connection={**CONNECTION, 'url': url})
        state = store.load()
        log_scan.watch_state(state)
        with loopback_backends.allowed():  # the fake broker is on loopback (HM-20), whatever the switch says
            spec = child_spec(state, store.directory)
        endpoint = Endpoint('emqx')
        manager = endpoint.supervisor(spec)
        manager.logs = RawLogs()
        try:
            await manager.start()
            async with endpoint.client(timeout=60) as child, httpx.AsyncClient(
                    transport=httpx.ASGITransport(make_apps(store, TOOLS['emqx'], child, child_url=endpoint.url)[1]),
                    base_url='http://boundary', timeout=60) as client:
                headers = {'Authorization': 'Bearer ' + state.token,
                           'Accept': 'application/json, text/event-stream'}
                init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                    'protocolVersion': '2025-06-18', 'capabilities': {},
                    'clientInfo': {'name': 'hm23', 'version': '0'}}}
                for _ in range(200):
                    response = await client.post('/mcp', headers=headers, json=init)
                    if response.status_code == 200 and not response.headers.get('mcp-session-id', '').startswith(
                            'woow-local-'):
                        break
                    await asyncio.sleep(.1)
                else:
                    raise AssertionError('child not ready')
                headers['Mcp-Session-Id'] = response.headers['mcp-session-id']
                headers['MCP-Protocol-Version'] = '2025-06-18'
                await client.post('/mcp', headers=headers,
                                  json={'jsonrpc': '2.0', 'method': 'notifications/initialized'})

                async def tool(name, arguments, id):
                    async with client.stream('POST', '/mcp', headers=headers, json=call(name, arguments, id)) as answer:
                        assert answer.status_code == 200
                        return await protocol_reply(answer, id)

                for number, (name, arguments) in enumerate(
                        (('emqx_get_client', {'clientid': long}), ('emqx_get_retained', {'topic': long})), 2):
                    result = await tool(name, arguments, number)
                    assert result.get('isError') is True and CODE in json.dumps(result), json.dumps(result)[:300]
                assert seen == []  # nothing reached the broker
                result = await tool('emqx_get_client', {'clientid': 'owned'}, 9)
                assert result.get('isError') is not True, json.dumps(result)[:300]
        finally:
            await manager.stop()
            endpoint.close()
    output = '\n'.join(manager.logs.raw)
    assert 'Traceback' not in output, output[-2000:]
    assert 'URL too long' not in output and 'site-packages' not in output
    assert 'aaaaaaaaaaaaaaaa' not in output
    assert seen == [('GET', '/api/v5/clients/owned')]  # only the normal request reached the broker
