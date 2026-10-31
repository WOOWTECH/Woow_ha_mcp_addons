"""N14-C2: both HA backend entry points validate through the real typed store."""
from contextlib import closing

import httpx
import pytest

from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS


IDENTITY = {"x-remote-user-id": "synthetic-owner"}
CONNECTION = {"url": "http://old.test", "database": "original-db",
              "username": "synthetic-user", "password": "synthetic-password"}


@pytest.fixture
async def odoo_admin(tmp_path):
    applied = []

    async def verify(_):
        return True

    async def backend_changed(state):
        applied.append(state)

    def no_backend_request(_):
        raise AssertionError("This connection-validation test must not call the backend")

    with closing(ProductStore(tmp_path, "odoo")) as store:
        store.update(connection=CONNECTION)
        async with httpx.AsyncClient(transport=httpx.MockTransport(no_backend_request)) as child:
            admin, _ = make_apps(store, TOOLS["odoo"], child, verify_admin=verify,
                                 backend_changed=backend_changed)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(admin, client=("172.30.32.2", 1)),
                base_url="http://admin",
            ) as client:
                yield client, store, applied


def payload(route, changes):
    return {"connection": {**CONNECTION, **changes}} if route == "/api/backend" else {"changes": changes}


@pytest.mark.parametrize("route", ["/api/backend", "/api/backend/patch"])
@pytest.mark.parametrize("change", [{"database": ["tracker43_admin_probe"]},
                                    {"database": None}, {"unexpected": "value"}],
                         ids=["list", "null", "unknown-key"])
async def test_invalid_connection_is_rejected_before_state_or_apply(odoo_admin, route, change):
    client, store, applied = odoo_admin
    before = await client.get("/api/bootstrap", headers=IDENTITY)
    assert before.status_code == 200
    raw = store.path.read_bytes()
    response = await client.put(route, json=payload(route, change), headers={
        **IDENTITY, "x-csrf-token": before.json()["csrf"], "If-Match": before.headers["etag"]})
    assert response.status_code == 400
    assert store.path.read_bytes() == raw
    after = await client.get("/api/bootstrap", headers=IDENTITY)
    assert after.headers["etag"] == before.headers["etag"]
    assert not applied


async def test_partial_edit_preserves_secret_and_revision_guards(odoo_admin):
    client, store, applied = odoo_admin
    before = await client.get("/api/bootstrap", headers=IDENTITY)
    headers = {**IDENTITY, "x-csrf-token": before.json()["csrf"]}
    raw = store.path.read_bytes()
    body = {"changes": {"database": "next-db"}}
    missing = await client.put("/api/backend/patch", json=body, headers=headers)
    assert missing.status_code == 428
    assert store.path.read_bytes() == raw and not applied
    headers["If-Match"] = before.headers["etag"]
    response = await client.put("/api/backend/patch", json=body, headers=headers)
    assert response.status_code == 200
    assert store.load().connection.model_dump() == {**CONNECTION, "database": "next-db"}
    assert len(applied) == 1
    after = await client.get("/api/bootstrap", headers=IDENTITY)
    assert after.headers["etag"] != before.headers["etag"]
    raw = store.path.read_bytes()
    stale = await client.put("/api/backend/patch", json=body, headers=headers)
    assert stale.status_code == 409
    assert store.path.read_bytes() == raw and len(applied) == 1
