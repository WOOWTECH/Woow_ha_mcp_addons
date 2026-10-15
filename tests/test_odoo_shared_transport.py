"""0.2.1 (B4): Odoo async tasks and foreground calls share one XML-RPC transport.

odoo-mcp's submit_async_task captures the session's OdooClient (app_context.odoo) and runs the job on its own
task_queue thread, outside the add-on's one-worker dispatch (BoundedTools capacity 1). Both threads then drove the same
xmlrpc transport, whose single cached http.client connection is closed after every request
(backend_policy.XMLTransport.request -> finally close()); one thread's close or request broke the other's exchange
("BACKEND_UNAVAILABLE: Idle", http.client's ResponseNotReady/CannotSendRequest state 'Idle'), seen on the test VM as
a foreground execute_method create and a chatter_post each failing once while a cancelled async task still ran.
The transport now serializes its requests (one exchange on the connection at a time).
"""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from pathlib import Path
import threading
import time
import xmlrpc.client

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('backend_policy_shared', ROOT / 'apps/runtime/backend_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def test_one_transport_used_by_a_task_thread_and_the_foreground_never_breaks():
    class Odoo(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            params, method = xmlrpc.client.loads(self.rfile.read(int(self.headers['Content-Length'])))
            time.sleep(0.01)  # a slow Odoo: requests overlap unless serialized
            body = xmlrpc.client.dumps((params[0],), methodresponse=True).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/xml')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Odoo)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}'
        proxy = xmlrpc.client.ServerProxy(url + '/xmlrpc/2/object', transport=policy.XMLTransport(url, timeout=5),
                                          allow_none=True)

        def calls(worker):
            return [proxy.echo(f'{worker}-{n}') for n in range(15)]

        with ThreadPoolExecutor(4) as pool:  # an async task worker and foreground calls on one client
            results = list(pool.map(calls, range(4)))
        assert results == [[f'{w}-{n}' for n in range(15)] for w in range(4)]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
