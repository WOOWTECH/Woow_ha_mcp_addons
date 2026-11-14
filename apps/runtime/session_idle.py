"""0.1.8 (0.1.6 RC GATEWAY-3): end the MCP sessions a client leaves idle, in every Python child.

The SDK pinned until 0.3.3 (mcp 1.28.1, also under FastMCP 3.4.5) kept a stateful session until the client sent
DELETE or the child restarted: neither FastMCP passed the session manager's session_idle_timeout. Clients often never
DELETE (the pinned TS SDK's close() only aborts; a crashed or killed client cannot), and each idle session holds its
transport, server task and per-session state. Measured locally (0.1.8, reviews-018/idle-session-measure.md): about
50-100 KiB per session in five children and about 350 KiB in Odoo, i.e. 70-500 MiB a day for a client that leaves
one session a minute.

install() makes every StreamableHTTPSessionManager this process builds end a session after SECONDS without a
request (the SDK cancels it and drops its transport; the client's next request gets 404 and MCP requires the client
to initialize again). A child calls install() before its server builds the manager; stateless managers are left alone.

0.3.4: mcp 1.30.0 (GHSA-84m7-p3x7-pcfv) ends a session itself after DEFAULT_SESSION_IDLE_TIMEOUT (30 minutes) with
no request in flight (a request being served or an open GET stream holds it), forgets a session at its DELETE or when
its opening request fails, and caps the sessions at 10 000. Its own FastMCP (Odoo, Hermes, OpenDesign) passes that
default explicitly, so the limit here replaces the SDK's default as it replaces None; any other explicit value is
kept. The limit is the same 30 minutes unless the environment sets another (tests), and an SDK without the
parameter still refuses to start.

0.3.4: mcp 1.30.0 also answers a request body larger than max_request_body_size (default 4 MiB) with 413 before parsing
it, in both FastMCP flavours (fastmcp 3.4.11 never passes it). The gateway admits bodies up to its MAX_REQUEST (16 MiB,
0.2.0: Nextcloud uploads up to 10 MiB as base64), so the same wrapper sets BODY_BYTES (equal to it, asserted by
tests/test_session_idle.py) for every manager, stateless or not, whose caller passed nothing or the SDK's default; an
explicit other value is kept. An SDK without the parameter has no such limit and is left as it is.

0.4.0 (mcp 2.3.0, FastMCP 4.1.3): StreamableHTTPSessionManager.__init__ has the same parameters and defaults as in
1.30.0 (session_idle_timeout 1800 s, max_request_body_size 4 MiB, max_sessions 10 000, the last left as it is).
MCPServer (mcp 1.x's FastMCP: Odoo, Hermes, OpenDesign) takes the transport settings in run() and passes both defaults
explicitly, which this replaces as before; FastMCP 4's own manager passes neither (its http_session_idle_timeout setting
is 'auto', the SDK default). The manager now enters the server lifespan once per process and ends an idle session by
cancelling its serve loop; a request in flight or an open GET stream still keeps a session. A request whose
MCP-Protocol-Version header is not an initialize-handshake revision goes to the SDK's 2026-07-28 handling instead;
through the gateway none succeeds there, as such a header failed in mcp 1.x (it answers server/discover itself, forwards
no such header with an initialize and removes params._meta, the 2026-07-28 envelope, from every request).

HM-06 (multi-profile plan 8.3; unreleased, in every product version, not behind a product switch): a Python child serves
only the gateway's own child bearer. The gateway, its health check and its catalog probe have always sent
Authorization: Bearer <child_token> (the state's child_token, mcp_admin_core.config.State); until now only n8n's child
checked it (AUTH_TOKEN). products.child_spec gives the seven Python children (Odoo, Hermes, OpenDesign, EMQX, LiteLLM,
Nextcloud, Headscale) the same value as WOOW_MCP_CHILD_TOKEN, and the same __init__ wrapper puts ChildBearer in front of
every manager's asgi_app, stateless or not (mcp 2.3.0 sets asgi_app in __init__; MCPServer's route calls it directly,
FastMCP 4.1.3's through handle_request):

- bearer() reads the variable once, first in install(), before anything is patched: missing, empty or not the
  child_token format ([A-Za-z0-9_-]{43}) is RuntimeError(REFUSED), a fixed message: the child does not start. The value
  is never part of a message, a repr or a log.
- ChildBearer: an HTTP request with exactly one Authorization header whose value is "Bearer <token>" (compared with
  hmac.compare_digest) reaches the SDK; any other gets 401 with no body and no detail (the gateway turns a child's 401
  into its own 502, gateway.py). Anything that is not an HTTP request never reaches it.
- The variable stays in the environment: the same uid reads /proc/<pid>/environ and the state file anyway (plan 8.3,
  DQ-37). A new child token takes effect with a restart (a new process).
The retired Odoo Manage (no image since 0.1.5) runs no session_idle and gets no bearer: unchanged.
"""
import functools
import hmac
import inspect
import os
import re

ENV = 'WOOW_MCP_SESSION_IDLE_SECONDS'
DEFAULT_SECONDS = 1800.0  # 30 minutes (n8n-mcp, the n8n child, reaps after 10)
BOUNDS = (1.0, 86400.0)
BODY_BYTES = 16 * 1024 * 1024  # 0.3.4: = mcp_admin_core.gateway.MAX_REQUEST, the largest body the gateway forwards
BEARER_ENV = 'WOOW_MCP_CHILD_TOKEN'  # HM-06
CHILD_TOKEN = re.compile(r'[A-Za-z0-9_-]{43}')  # config.State's child_token: secrets.token_urlsafe(32)
SCHEME = b'Bearer '
REFUSED = 'child bearer: WOOW_MCP_CHILD_TOKEN is missing or not a child token'
_UNAUTHORIZED = ((b'www-authenticate', b'Bearer'), (b'content-length', b'0'))


def seconds():
    """The limit: DEFAULT_SECONDS unless the environment sets another (tests); anything invalid refuses to start."""
    value = os.environ.get(ENV)
    if value is None:
        return DEFAULT_SECONDS
    number = float(value)  # ValueError for text: the child does not start
    if not BOUNDS[0] <= number <= BOUNDS[1]:
        raise ValueError('session idle limit out of range')
    return number


def bearer():
    """HM-06: b'Bearer <token>' from WOOW_MCP_CHILD_TOKEN, or RuntimeError(REFUSED): the child refuses to start."""
    value = os.environ.get(BEARER_ENV)
    if value is None or not CHILD_TOKEN.fullmatch(value):
        raise RuntimeError(REFUSED)
    return SCHEME + value.encode('ascii')


class ChildBearer:
    """HM-06, ASGI: only an HTTP request with exactly one Authorization: Bearer <child token> reaches app."""
    __slots__ = ('app', '_expected')

    def __init__(self, app, expected):
        if type(expected) is not bytes or not expected.startswith(SCHEME) or not CHILD_TOKEN.fullmatch(
                expected[len(SCHEME):].decode('ascii', 'replace')):
            raise ValueError(REFUSED)
        self.app = app
        self._expected = expected

    def __repr__(self):
        return '<ChildBearer>'

    def allowed(self, scope):
        if scope.get('type') != 'http':
            return False
        values = [value for name, value in scope.get('headers') or () if name.lower() == b'authorization']
        return len(values) == 1 and hmac.compare_digest(values[0], self._expected)

    async def __call__(self, scope, receive, send):
        if self.allowed(scope):
            await self.app(scope, receive, send)
        elif scope.get('type') == 'http':
            await send({'type': 'http.response.start', 'status': 401, 'headers': list(_UNAUTHORIZED)})
            await send({'type': 'http.response.body', 'body': b''})


def install():
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    original = StreamableHTTPSessionManager.__init__
    if getattr(original, 'woow_idle_seconds', None) is not None:
        return original.woow_idle_seconds
    expected = bearer()  # HM-06: RuntimeError without a valid WOOW_MCP_CHILD_TOKEN; nothing is patched yet
    limit = seconds()
    signature = inspect.signature(original)
    if 'session_idle_timeout' not in signature.parameters:
        raise RuntimeError('pinned MCP SDK without session_idle_timeout')
    sdk_default = signature.parameters['session_idle_timeout'].default  # None in mcp 1.28.1, 1800 in 1.30.0
    body = signature.parameters.get('max_request_body_size')  # 0.3.4: mcp 1.30.0 (4 MiB); absent in 1.28.1

    @functools.wraps(original)
    def __init__(self, *args, **kwargs):
        bound = signature.bind(self, *args, **kwargs)
        value = bound.arguments.get('session_idle_timeout')
        if (value is None or value == sdk_default) and not bound.arguments.get('stateless', False):
            bound.arguments['session_idle_timeout'] = limit
        if body is not None and bound.arguments.get('max_request_body_size', body.default) == body.default:
            bound.arguments['max_request_body_size'] = BODY_BYTES
        original(*bound.args, **bound.kwargs)
        self.asgi_app = ChildBearer(self.asgi_app, expected)  # HM-06: every manager, stateless or not

    __init__.woow_idle_seconds = limit
    StreamableHTTPSessionManager.__init__ = __init__
    return limit
