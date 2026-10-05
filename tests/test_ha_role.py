"""Owned loopback WS only; never HA. All machine credentials are dummy values."""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
import signal
import socket
import sys

import httpx
import pytest
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from mcp_admin_core import ha_role
from mcp_admin_core.config import Store
from mcp_admin_core.gateway import make_apps
from n8n_adapter import TOOLS, child_spec

DUMMY = "DUMMY-machine-token"
IDENTITY = {"X-Remote-User-Id": "human"}


def user(**changes):
    return {"id": "human", "is_owner": False, "is_active": True,
            "system_generated": False, "group_ids": ["system-admin"], **changes}


def result(users=None, **changes):
    return {"id": 1, "type": "result", "success": True,
            "result": [user()] if users is None else users, **changes}


@asynccontextmanager
async def owned_provider(monkeypatch, *, response=None, first=None, auth=None, stall=None):
    monkeypatch.setenv("SUPERVISOR_TOKEN", DUMMY)
    record = {"frames": [], "connections": 0, "closed": 0, "options": [],
              "response": result() if response is None else response}
    entered = asyncio.Event()

    async def handler(ws):
        record["connections"] += 1
        assert ws.request.path == "/core/websocket"
        assert ws.request.headers["Host"] == "supervisor"
        assert "Authorization" not in ws.request.headers
        assert "Cookie" not in ws.request.headers
        assert not ws.protocol.extensions
        try:
            if stall == "hello":
                entered.set()
                await ws.wait_closed()
                return
            await ws.send(json.dumps(first if first is not None else {"type": "auth_required", "ha_version": "2026.7.2"}))
            record["frames"].append(json.loads(await ws.recv()))
            await ws.send(json.dumps(auth if auth is not None else {"type": "auth_ok", "ha_version": "2026.7.2"}))
            record["frames"].append(json.loads(await ws.recv()))
            entered.set()
            if stall == "result":
                await ws.wait_closed()
                return
            payload = record["response"]
            await ws.send(payload if isinstance(payload, (str, bytes)) else json.dumps(payload))
            await ws.wait_closed()
        except ConnectionClosed:
            pass
        finally:
            record["closed"] += 1

    server_logger = logging.Logger("owned-test-server")
    server_logger.disabled = True
    async with serve(handler, "127.0.0.1", 0, compression=None, logger=server_logger) as server:
        port = record["port"] = server.sockets[0].getsockname()[1]

        def connector(uri, **options):
            assert uri == "ws://supervisor/core/websocket"
            assert options["proxy"] is None and options["compression"] is None
            assert options["max_size"] == 1024 * 1024 and options["max_queue"] == 1
            assert options["logger"].disabled
            record["options"].append(options)
            # Transport-only override, keeps production URI, HTTP Host and path.
            return ha_role._NoRedirectConnect(uri, host="127.0.0.1", port=port, **options)

        provider = ha_role._Verifier(connector)
        yield provider, record, entered
        assert provider._active == 0
    assert record["closed"] == record["connections"]


@pytest.mark.parametrize("record,allowed", [
    (user(), True), (user(is_owner=True, group_ids=[]), True),
    (user(group_ids=[]), False), (user(is_active=False), False),
    (user(is_owner=True, is_active=False), False),
    (user(system_generated=True), False), (user(id="other-admin"), False),
    (user(is_active=1), False), (user(is_owner="true"), False),
    (user(system_generated=0), False), (user(group_ids="system-admin"), False),
    (user(group_ids=[1]), False), (user(local_only="false"), False),
    (user(id=12), False),
])
async def test_actual_protocol_and_current_subject(monkeypatch, record, allowed):
    async with owned_provider(monkeypatch, response=result([record])) as (verify, seen, _):
        assert await verify("human") is allowed
        assert seen["frames"] == [{"type": "auth", "access_token": DUMMY},
                                  {"id": 1, "type": "config/auth/list"}]


@pytest.mark.parametrize("response", [
    result([]), result([user(), user()]), result([user(), user(id="x"), user(id="x")]),
    result([user(), {}]), result([{"id": "human"}]), result(id=2), result(id=True),
    result(type="event"), result(success=1), result(success=False), result(result={}),
    {"id": 1, "type": "result", "success": True}, result(error={}),
    '{"id":1,"id":1,"type":"result","success":true,"result":[]}',
    '{', '[]', 'NaN', b'{"type":"result"}',
    ' ' * (1024 * 1024 + 1), '[' * 2000,
])
async def test_failclosed_result_schema(monkeypatch, response):
    async with owned_provider(monkeypatch, response=response) as (verify, _, __):
        assert await verify("human") is False


@pytest.mark.parametrize("phase,message", [
    ("first", {"type": "auth_ok", "ha_version": "2026.7.2"}),
    ("first", {"type": "auth_required"}),
    ("first", {"type": "auth_required", "ha_version": 2026}),
    ("first", {"type": "auth_required", "ha_version": "unreviewed-version"}),
    ("auth", {"type": "auth_invalid", "message": "DUMMY-revoked-or-flag-disabled"}),
    ("auth", {"type": "result", "id": 1, "success": True, "result": [user()]}),
])
async def test_wrong_sequence_and_revoked_machine_capability(monkeypatch, phase, message):
    async with owned_provider(monkeypatch, **{phase: message}) as (verify, seen, _):
        assert await verify("human") is False
        assert len(seen["frames"]) == (0 if phase == "first" else 1)


async def test_fresh_connection_no_positive_cache_token_reloaded(monkeypatch):
    async with owned_provider(monkeypatch) as (verify, seen, _):
        assert await verify("human") is True
        seen["response"] = result([user(group_ids=[])])
        monkeypatch.setenv("SUPERVISOR_TOKEN", "DUMMY-rotated-machine")
        assert await verify("human") is False
        seen["response"] = result([])  # deletion
        assert await verify("human") is False
        assert seen["connections"] == 3
        assert seen["frames"][2]["access_token"] == "DUMMY-rotated-machine"
        monkeypatch.delenv("SUPERVISOR_TOKEN")
        assert await verify("human") is False
        assert seen["connections"] == 3


@pytest.mark.parametrize("stall", ["hello", "result"])
async def test_timeout_closes_socket(monkeypatch, stall):
    async with owned_provider(monkeypatch, stall=stall) as (verify, seen, _):
        start = asyncio.get_running_loop().time()
        assert await verify("human") is False
        assert asyncio.get_running_loop().time() - start < 2.9
        assert verify._active == 0


async def test_no_queue_and_cancellation_cleanup(monkeypatch):
    async with owned_provider(monkeypatch, stall="result") as (verify, seen, entered):
        before = set(asyncio.all_tasks())
        pending = [asyncio.create_task(verify("human")) for _ in range(8)]
        await entered.wait()
        assert await verify("human") is False
        assert verify._active == 8
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await asyncio.sleep(.05)
        assert verify._active == 0
        assert not (set(asyncio.all_tasks()) - before)


async def test_machine_token_missing_outage_no_leak(monkeypatch, caplog):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    verify = ha_role.make_ha_admin_verifier()
    assert await verify("human") is False
    # Never connect to production: injected failure containing dummy secrets.
    async def fail(*args, **kwargs):
        raise RuntimeError("DUMMY-private-token-directory")
    monkeypatch.setenv("SUPERVISOR_TOKEN", DUMMY)
    with caplog.at_level(logging.DEBUG):
        assert await ha_role._Verifier(fail)("human") is False
        async with owned_provider(monkeypatch) as (verify, _, __):
            assert await verify("human") is True
    assert "DUMMY" not in caplog.text
    # Server debug logging is outside our client; don't enable it here.


@asynccontextmanager
async def gateway(tmp_path, verify, *, changed=None):
    store = Store(tmp_path / "state")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(204))) as child:
        admin, mcp = make_apps(store, TOOLS, child, verify_admin=verify, backend_changed=changed)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=admin, client=("172.30.32.2", 1)), base_url="http://admin") as client:
            yield store, client, admin, mcp
    store.close()


@pytest.mark.parametrize("headers", [
    [], [("X-Remote-User-Id", "human"), ("X-Remote-User-Id", "human")],
    *[[("X-Remote-User-Id", x)] for x in ["", "human,other", " human", "human ", "hu\x7fman", "hu\tman", "x" * 257]],
])
async def test_identity_ambiguity_never_queries(tmp_path, monkeypatch, headers):
    async with owned_provider(monkeypatch) as (verify, seen, _):
        async with gateway(tmp_path, verify) as (store, client, _, __):
            response = await client.get("/api/bootstrap", headers=headers)
            assert response.status_code == 403
            assert seen["connections"] == 0


@pytest.mark.parametrize("operation,method,payload", [
    ("token/reveal", "POST", None), ("token/rotate", "POST", None),
    ("token/revoke", "POST", None),
    ("backend", "PUT", {"url": "http://127.0.0.1:1234", "key": "DUMMY-backend"}),
    ("policy", "PUT", {"writes_enabled": True, "disabled": []}),
    ("endpoint", "PUT", {"endpoint": "http://example.test/mcp"}),
    ("bootstrap", "GET", None),
])
async def test_denied_fresh_action_no_mutation_or_disclosure(tmp_path, monkeypatch, operation, method, payload):
    async with owned_provider(monkeypatch) as (verify, seen, _):
        async with gateway(tmp_path, verify) as (store, client, _, __):
            initial = store.path.read_bytes()
            headers = dict(IDENTITY)
            headers["X-CSRF-Token"] = (await client.get("/api/bootstrap", headers=headers)).json()["csrf"]
            seen["response"] = result([user(is_active=False)])
            response = await client.request(method, "/api/" + operation, headers=headers, json=payload)
            assert response.status_code == 403
            assert response.json() == {"error": "request denied"}
            assert store.path.read_bytes() == initial
            assert seen["connections"] == 2
            assert store.load().token not in response.text


async def test_body_and_validation_precede_fresh_query(tmp_path, monkeypatch):
    async with owned_provider(monkeypatch) as (verify, seen, _):
        async with gateway(tmp_path, verify) as (store, client, _, __):
            headers = dict(IDENTITY)
            headers["X-CSRF-Token"] = (await client.get("/api/bootstrap", headers=headers)).json()["csrf"]
            initial = store.path.read_bytes()
            for data in ({"writes_enabled": "true", "disabled": []}, {"bad": True}):
                assert (await client.put("/api/policy", headers=headers, json=data)).status_code == 400
            assert seen["connections"] == 1
            async def slow_body():
                yield b'{"writes_enabled":'
                # Simulate demotion while waiting for body, not before admission.
                seen["response"] = result([user(group_ids=[])])
                await asyncio.sleep(.01)
                yield b'true,"disabled":[]}'
            response = await client.put("/api/policy", headers={**headers, "Content-Type": "application/json"}, content=slow_body())
            assert response.status_code == 403
            assert seen["connections"] == 2
            assert store.path.read_bytes() == initial


async def test_queued_demotion_checks_after_lock(tmp_path, monkeypatch):
    holding, release = asyncio.Event(), asyncio.Event()
    async def changed(_):
        holding.set()
        await release.wait()
    async with owned_provider(monkeypatch) as (verify, seen, _):
        async with gateway(tmp_path, verify, changed=changed) as (store, client, _, __):
            headers = dict(IDENTITY)
            headers["X-CSRF-Token"] = (await client.get("/api/bootstrap", headers=headers)).json()["csrf"]
            first = asyncio.create_task(client.put("/api/backend", headers=headers, json={"url": None, "key": None}))
            await holding.wait()
            initial = store.path.read_bytes()
            queued = asyncio.create_task(client.post("/api/token/rotate", headers=headers))
            await asyncio.sleep(.03)
            assert seen["connections"] == 2  # bootstrap + holder, NOT queued grant
            seen["response"] = result([user(group_ids=[])])
            release.set()
            assert (await first).status_code == 200
            assert (await queued).status_code == 403
            assert store.path.read_bytes() == initial
            assert seen["connections"] == 3


async def test_credentials_and_peer_listener_separation(tmp_path, monkeypatch):
    async with owned_provider(monkeypatch) as (verify, seen, _):
        async with gateway(tmp_path, verify) as (store, client, admin, mcp):
            store.update(backend_key="DUMMY-backend")
            headers = {**IDENTITY, "Authorization": "Bearer DUMMY-browser", "Cookie": "DUMMY-cookie"}
            bootstrap = await client.get("/api/bootstrap", headers=headers)
            assert bootstrap.status_code == 200
            assert "DUMMY" not in bootstrap.text
            assert DUMMY not in store.path.read_text()
            spec = child_spec(store.load(), store.directory)
            assert "SUPERVISOR_TOKEN" not in spec.env
            assert DUMMY not in repr(spec.argv) and DUMMY not in repr(spec.env)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=admin, client=("127.0.0.1", 1)), base_url="http://admin") as direct:
                assert (await direct.get("/api/bootstrap", headers={**headers, "X-Forwarded-For": "172.30.32.2"})).status_code == 403
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mcp), base_url="http://mcp") as data:
                assert (await data.get("/api/bootstrap", headers=headers)).status_code == 404
                assert (await data.get("/mcp", headers=headers)).status_code == 401
            assert seen["connections"] == 1
            assert seen["frames"][0]["access_token"] == DUMMY


async def test_disconnect_cancels_role_query_without_disclosure(tmp_path, monkeypatch):
    async with owned_provider(monkeypatch, stall="result") as (verify, seen, entered):
        async with gateway(tmp_path, verify) as (store, _, admin, __):
            initial = store.path.read_bytes()
            events = asyncio.Queue()
            await events.put({"type": "http.request", "body": b"", "more_body": False})
            output = []
            async def send(message):
                output.append(message)
            task = asyncio.create_task(admin({"type": "http", "method": "GET", "path": "/api/bootstrap", "query_string": b"", "headers": [(b"x-remote-user-id", b"human")], "client": ("172.30.32.2", 1), "server": ("admin", 80), "scheme": "http", "http_version": "1.1"}, events.get, send))
            await entered.wait()
            await events.put({"type": "http.disconnect"})
            await asyncio.wait_for(task, 1)
            assert verify._active == 0
            assert store.path.read_bytes() == initial
            assert b"csrf" not in b"".join(m.get("body", b"") for m in output)


def test_n8n_and_six_products_share_factory():
    import inspect
    import run
    from mcp_admin_core import run_product
    assert run.make_ha_admin_verifier is ha_role.make_ha_admin_verifier
    assert "verify_admin=make_ha_admin_verifier()" in inspect.getsource(run.run)
    assert run_product.make_ha_admin_verifier is ha_role.make_ha_admin_verifier
    assert "verify_admin=make_ha_admin_verifier()" in inspect.getsource(run_product.run)
    assert not isinstance(ha_role._NoRedirectConnect.process_redirect(None, RuntimeError()), str)


async def test_real_n8n_executable_tcp_uses_production_factory(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    from owned_executable import Executable
    from test_real_n8n import free_port
    admin_port, mcp_port = free_port(), free_port()
    async with owned_provider(monkeypatch) as (_, seen, __):
        # Test-only transport and ingress socket simulation. The real executable,
        # verifier factory, authentication frames and child launcher remain intact.
        code = f'''
from mcp_admin_core import ha_role
import run
connector = ha_role._NoRedirectConnect
def owned_transport(uri, **options):
    assert uri == "ws://supervisor/core/websocket"
    return connector(uri, host="127.0.0.1", port={seen['port']}, **options)
ha_role._NoRedirectConnect = owned_transport
apps = run.make_apps
def ingress_simulation(*args, **kwargs):
    assert isinstance(kwargs["verify_admin"], ha_role._Verifier)
    admin, mcp = apps(*args, **kwargs)
    async def ingress(scope, receive, send):
        await admin({{**scope, "client": ("172.30.32.2", 1)}}, receive, send)
    return ingress, mcp
run.make_apps = ingress_simulation
run.main()
'''
        runner = Executable(tmp_path, 'n8n', [admin_port, mcp_port])
        code = 'import run; ' + runner.code('run') + '\n' + code
        runner.release()
        process = await asyncio.create_subprocess_exec(sys.executable, "-c", code,
            "--data", str(tmp_path / "runtime"), "--host", "127.0.0.1",
            "--admin-port", str(admin_port), "--mcp-port", str(mcp_port), cwd=tmp_path,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(root / "packages/mcp-admin-core") + ":" + str(root / "apps/n8n"), "SUPERVISOR_TOKEN": DUMMY},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            await runner.ready(process)
            async with httpx.AsyncClient(trust_env=False, base_url=f"http://127.0.0.1:{admin_port}", event_hooks={'request': [runner.guard]}) as client:
                async with asyncio.timeout(20):
                    while True:
                        assert process.returncode is None
                        try:
                            response = await client.get("/api/bootstrap", headers=IDENTITY)
                            break
                        except httpx.ConnectError:
                            await asyncio.sleep(.05)
                assert response.status_code == 200
                assert seen["frames"] == [{"type": "auth", "access_token": DUMMY}, {"id": 1, "type": "config/auth/list"}]
                headers = {**IDENTITY, "X-CSRF-Token": response.json()["csrf"]}
                seen["response"] = result([user(group_ids=[])])
                denied = await client.post("/api/token/reveal", headers=headers)
                assert denied.status_code == 403 and denied.json() == {"error": "request denied"}
                assert seen["connections"] == 2
                # Same actual factory/runner: the real backend callback must
                # rebuild Node and refresh its proof, not reuse the old inode.
                previous = await runner.guard_url(runner.child_url)
                seen['response'] = result()
                changed = await client.put('/api/backend', headers=headers, json={'url':None, 'key':None})
                assert changed.status_code == 200
                current = await runner.guard_url(runner.child_url)
                assert current['generation'] == previous['generation'] + 1
                assert current['proof'] != previous['proof']
                assert not Path(f"/proc/{previous['proof'][0]}").exists()
        finally:
            if process.returncode is None:
                process.send_signal(signal.SIGTERM)
            try:
                out, err = await asyncio.wait_for(process.communicate(), 10)
            except TimeoutError:
                process.kill()
                out, err = await process.communicate()
        assert process.returncode == 0
        assert b"DUMMY" not in out + err and b"Traceback" not in err
