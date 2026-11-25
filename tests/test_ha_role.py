"""Owned loopback WS only; never HA. All machine credentials are dummy values."""
from admin_write_headers import reviewed_headers
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

from mcp_admin_core import ha_role, ui
from mcp_admin_core.config import Store
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.products import ProductStore, TOOLS as PRODUCT_TOOLS
from mcp_admin_core.surface import listing
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
    ("first", {"type": "auth_required", "ha_version": "2026.7.1"}),
    ("first", {"type": "auth_required", "ha_version": "2026.12.0"}),
    ("first", {"type": "auth_required", "ha_version": "2026.9.4 "}),
    ("first", {"type": "auth_required", "ha_version": ["2026.7.2"]}),
    ("first", {"type": "auth_required", "ha_version": {"v": "2026.7.2"}}),
    ("auth", {"type": "auth_ok", "ha_version": "2026.9.4"}),  # auth_required said 2026.7.2: versions must agree
    ("auth", {"type": "auth_ok", "ha_version": "2026.10.0"}),  # listed, but auth_required said 2026.7.2
    ("auth", {"type": "auth_invalid", "message": "DUMMY-revoked-or-flag-disabled"}),
    ("auth", {"type": "result", "id": 1, "success": True, "result": [user()]}),
])
async def test_wrong_sequence_and_revoked_machine_capability(monkeypatch, phase, message):
    async with owned_provider(monkeypatch, **{phase: message}) as (verify, seen, _):
        denied = await verify("human")
        # An unreviewed version in a well-formed auth_required is the explained denial (Unreviewed, falsy); every
        # other malformed or out-of-sequence frame is a plain False.
        assert denied is False or isinstance(denied, ha_role.Unreviewed)
        assert not denied
        assert len(seen["frames"]) == (0 if phase == "first" else 1)


@pytest.mark.parametrize("version", sorted(ha_role._HA_VERSIONS))
async def test_every_reviewed_core_version_is_accepted(monkeypatch, version):
    # 0.1.6: the reviewed Core releases keep the consumed contract (docs/ha-role-core-contract.md).
    hello = {"type": "auth_required", "ha_version": version}
    async with owned_provider(monkeypatch, first=hello, auth={"type": "auth_ok", "ha_version": version}) as (verify, _, __):
        assert await verify("human") is True


@pytest.mark.parametrize("version", [["2026.7.2"], {"v": "2026.7.2"}, 2026, None, True, 2026.11, ["2026.11.4"], {"v": "2026.11.4"}])
def test_a_non_string_version_is_refused_explicitly(version):
    # The refusal is the check's own ValueError, not an accidental TypeError from hashing a list or dict.
    with pytest.raises(ValueError):
        ha_role._auth_message(json.dumps({"type": "auth_required", "ha_version": version}), "auth_required")


# Refused before the machine token is sent. Since 2026-11-25 a later patch release of a reviewed month is accepted by rule
# (LATER_PATCHES below), so what stays here is a month this release has not reviewed, a patch release before the first
# reviewed one of its month, and every form other than year.month.patch in ASCII digits without padding (pre-releases too).
NEAR_MISSES = ["2026.7.0", "2026.09.4", "2026.9.04", "02026.9.4", "2026.9.0b9",
               "2026.10.0b2", "2026.9.4.dev0", "v2026.9.4", "", "2026.9", "2026.9.4.0",
               "2026.10.1b1", "2026.10.0b4", "2026.10.0b7", "2026.10", "2026.10.0.0", "2026.10.00", "2026.10.01",
               "2026.10.1.0", "2026.10.1 ", " 2026.10.1",
               # next after the 2026-10-27 review (2026.10.2-2026.10.4 added): betas, other formats
               "2026.10.4b0", "2026.10.4.0", "2026.10.04", "2026.10.4 ", " 2026.10.4",
               "2026.11.0b0", "2026.11.0.dev0", "2026.11.1rc1", "2026.11.2rc1", "2026.12.0",
               # 2026-11-25: 2026.11.3 reviewed, later patch releases of a reviewed month accepted by rule. Still refused:
               # a month that is not reviewed (the first release of the next month included), a patch before the first
               # reviewed one of its month, and any other form of the string
               "2026.12.1", "2026.6.9", "2026.6.0", "2027.1.0", "2025.11.4", "2026.1.0", "2026.13.0", "2026.0.1", "2026.7.1",
               "2026.11.3b0", "2026.11.4b0", "2026.11.4b1", "2026.11.4rc1", "2026.11.4.dev0", "2026.11.4.0", "2026.11.4-1",
               "2026.11.4+1", "2026.11.4_1", "2026.12.0b0", "2026.12.0rc1", "2026.12.0.dev20261125",
               "2026.09.5", "2026.9.05", "2026.11.04", "2026.11.00", "2026.011.4", "02026.11.4", "20260.11.4", "2026.11",
               "2026.11.", "2026..4", ".11.4", "2026.11.-1", "2026.11.4.", "2026.11.1000", "2026.11.99999999999999999999",
               "2026.11.4 ", " 2026.11.4", "2026.11.4\n", "\n2026.11.4", "2026.11.4\x00", "\t2026.11.4", "2026.11.4\u00a0",
               "2026.11.4\u200b", "v2026.11.4", "V2026.11.4", "2026.11.4,2026.11.5", "2026.11.4;", "2026.11.4/", "2026.11.4%20",
               "２０２６.１１.４", "2026.11.٤", "٢٠٢٦.11.4", "2026.١١.4", "2026.11.4 (patch)", "HomeAssistant 2026.11.4",
               "2026\uff0e11\uff0e4", "2026\u202411\u20244", "2026.11.4\u2028", "2026.11.4\r\n", "2026.11.4" + " " * 2000,
               "2026.11." + "9" * 5000, "2026." + "1" * 4000 + ".4"]

# A later patch release of a reviewed month (every month in _HA_VERSIONS, above the newest reviewed patch of that month):
# accepted by rule without a review of its own.
LATER_PATCHES = ["2026.7.5", "2026.7.99", "2026.8.4", "2026.9.5", "2026.10.5", "2026.10.10", "2026.10.40", "2026.11.4",
                 "2026.11.9", "2026.11.10", "2026.11.999"]


@pytest.mark.parametrize("version", NEAR_MISSES)
def test_near_miss_versions_are_refused(version):
    # 0.1.6 review L3: later patches, other formats and pre-releases are not reviewed releases.
    with pytest.raises(ValueError):
        ha_role._auth_message(json.dumps({"type": "auth_required", "ha_version": version}), "auth_required")


@pytest.mark.parametrize("version", NEAR_MISSES)
async def test_near_miss_versions_deny_before_the_token_is_sent(monkeypatch, version):
    hello, ok = {"type": "auth_required", "ha_version": version}, {"type": "auth_ok", "ha_version": version}
    async with owned_provider(monkeypatch, first=hello, auth=ok) as (verify, seen, _):
        denied = await verify("human")
        assert isinstance(denied, ha_role.Unreviewed) and not denied and denied is not True
        assert denied.ha_version == ha_role.shown_version(version)
        assert seen["frames"] == []


@pytest.mark.parametrize("phase", ["first", "auth"])
async def test_an_extra_key_in_an_auth_frame_denies(monkeypatch, phase):
    message = {"type": "auth_required" if phase == "first" else "auth_ok", "ha_version": "2026.7.2", "x": 1}
    async with owned_provider(monkeypatch, **{phase: message}) as (verify, _, __):
        assert await verify("human") is False


def test_the_review_table_lists_exactly_the_reviewed_versions():
    # docs/ha-role-core-contract.md has one column per reviewed release (short form, e.g. `10.1` for 2026.10.1). Later patch
    # releases of those months are accepted by rule and have no column until a release reviews them.
    from pathlib import Path
    doc = (Path(__file__).resolve().parents[1] / 'docs/ha-role-core-contract.md').read_text()
    header = next(line for line in doc.splitlines() if line.startswith('| file (`homeassistant/`) |'))
    columns = [cell.strip() for cell in header.strip('|').split('|')[1:]]
    assert {'2026.' + column for column in columns} == ha_role._HA_VERSIONS


def test_the_reviewed_versions_are_exactly_these():
    # A new Core release is added only after its contract files are reviewed; this list changes with that review.
    assert ha_role._HA_VERSIONS == {"2026.7.2", "2026.7.3", "2026.7.4", "2026.8.0", "2026.8.1", "2026.8.2", "2026.8.3",
                                    "2026.9.0", "2026.9.1", "2026.9.2", "2026.9.3", "2026.9.4", "2026.10.0",
                                    "2026.10.1", "2026.10.2", "2026.10.3", "2026.10.4",
                                    "2026.11.0", "2026.11.1", "2026.11.2", "2026.11.3"}


@pytest.mark.parametrize("version", ["2026.10.2", "2026.10.3", "2026.10.4"])
async def test_core_2026_10_2_to_10_4_are_reviewed_and_still_check_the_role(monkeypatch, version):
    # Reviewed 2026-10-27 (docs/ha-role-core-contract.md): of the 21 contract files only auth/__init__.py changed
    # (async_remove_user), outside config/auth/list. The machine token is sent and the role is still checked.
    hello, ok = {"type": "auth_required", "ha_version": version}, {"type": "auth_ok", "ha_version": version}
    async with owned_provider(monkeypatch, first=hello, auth=ok) as (verify, seen, _):
        assert await verify("human") is True
        assert seen["frames"] == [{"type": "auth", "access_token": DUMMY}, {"id": 1, "type": "config/auth/list"}]
        seen["response"] = result([user(group_ids=[])])
        assert await verify("human") is False


@pytest.mark.parametrize("version", ["2026.11.0", "2026.11.1", "2026.11.2", "2026.11.3"])
async def test_core_2026_11_releases_keep_fresh_admin_check(monkeypatch, version):
    hello, ok = {"type": "auth_required", "ha_version": version}, {"type": "auth_ok", "ha_version": version}
    async with owned_provider(monkeypatch, first=hello, auth=ok) as (verify, seen, _):
        assert await verify("human") is True
        assert seen["frames"] == [{"type": "auth", "access_token": DUMMY}, {"id": 1, "type": "config/auth/list"}]
        seen["response"] = result([user(group_ids=[])])
        assert await verify("human") is False


# Shown to the administrator by their own form (shown_version): a new month, a patch before the first reviewed one of its
# month, and pre-releases. (2026.10.5 and 2026.11.3 left this list on 2026-11-25: a later patch, and a reviewed release.)
UNREVIEWED = ["2026.12.0", "2026.6.9", "2026.7.1", "2026.11.0b0", "2026.11.0rc1", "2026.11.0.dev20261027", "2027.1.0"]


@pytest.mark.parametrize("version", UNREVIEWED)
async def test_an_unreviewed_core_version_denies_with_its_reason_and_one_log_line(monkeypatch, capsys, version):
    hello, ok = {"type": "auth_required", "ha_version": version}, {"type": "auth_ok", "ha_version": version}
    async with owned_provider(monkeypatch, first=hello, auth=ok) as (verify, seen, _):
        for _ in range(3):
            denied = await verify("human")
            assert isinstance(denied, ha_role.Unreviewed) and not denied and denied.ha_version == version
        assert seen["frames"] == []  # the machine token never goes to an unreviewed version
        assert seen["connections"] == 3  # fresh query each time: no cached denial either
    err = capsys.readouterr().err
    lines = [line for line in err.splitlines() if line]
    assert len(lines) == 1, err  # one add-on log line per version and process
    assert lines[0].startswith(f"management: Home Assistant Core {version} has not been reviewed")
    assert "(reviewed: 2026.7.2 to 2026.11.3)" in lines[0] and "MCP endpoints do not use this check." in lines[0]
    # What would have been accepted without a review is said too, so the administrator can tell why this one was not.
    assert "only a later patch release of a reviewed month is accepted without a review" in lines[0]
    assert DUMMY not in err


@pytest.mark.parametrize("advertised", ["unreviewed-version", "2026.9.4 ", "v2026.11.0", "x" * 300, "2026.10.5<script>"])
async def test_an_unrecognized_version_string_is_reported_but_never_echoed(monkeypatch, capsys, advertised):
    async with owned_provider(monkeypatch, first={"type": "auth_required", "ha_version": advertised}) as (verify, seen, _):
        denied = await verify("human")
        assert isinstance(denied, ha_role.Unreviewed) and denied.ha_version is None
        assert seen["frames"] == []
    err = capsys.readouterr().err
    assert "Home Assistant Core (an unrecognized version string) has not been reviewed" in err
    assert advertised.strip() not in err and "<script>" not in err and DUMMY not in err


def test_the_log_is_bounded_per_process(capsys):
    verify = ha_role._Verifier(None)
    for minor in range(ha_role._MAX_REPORTED + 8):
        verify._report_unreviewed(f"2027.{minor}.0")
        verify._report_unreviewed(f"2027.{minor}.0")
    assert len(capsys.readouterr().err.splitlines()) == ha_role._MAX_REPORTED


# ---- 2026-11-25 (owner decision, DQ-35): a later patch release of a reviewed month is accepted by rule ----


@pytest.mark.parametrize("version", LATER_PATCHES)
async def test_a_later_patch_release_sends_the_token_and_still_checks_the_role(monkeypatch, version):
    # docs/ha-role-core-contract.md "Later patch releases": nothing else relaxes. The token goes out only after the version
    # check, the role is queried on a fresh connection for every decision, and a user who is not an active, human
    # owner or administrator is refused exactly as on a reviewed release.
    hello, ok = {"type": "auth_required", "ha_version": version}, {"type": "auth_ok", "ha_version": version}
    async with owned_provider(monkeypatch, first=hello, auth=ok) as (verify, seen, _):
        assert await verify("human") is True
        assert seen["frames"] == [{"type": "auth", "access_token": DUMMY}, {"id": 1, "type": "config/auth/list"}]
        for refused in (user(group_ids=[]), user(is_active=False), user(system_generated=True), user(id="other-admin"),
                        user(is_owner="true"), user(group_ids="system-admin"), user(local_only="false")):
            seen["response"] = result([refused])
            assert await verify("human") is False
        seen["response"] = result([])  # deleted
        assert await verify("human") is False
        seen["response"] = result([user(is_owner=True, group_ids=[])])  # the owner is an administrator
        assert await verify("human") is True
        assert seen["connections"] == 10  # a fresh connection for every decision, no cache


@pytest.mark.parametrize("first,second", [
    ("2026.11.4", "2026.11.5"), ("2026.11.4", "2026.11.3"), ("2026.11.3", "2026.11.4"), ("2026.11.4", "2026.12.0"),
    ("2026.11.4", "2026.11.4 "), ("2026.11.4", "2026.11.04"), ("2026.7.5", "2026.7.6"), ("2026.11.4", "2026.7.2"),
    ("2026.11.4", "2026.11.4b0"),
])
async def test_a_later_patch_release_must_be_the_same_in_both_frames(monkeypatch, first, second):
    # As for a reviewed release: auth_required and auth_ok agree (a difference only happens in an update race), else deny.
    hello, ok = {"type": "auth_required", "ha_version": first}, {"type": "auth_ok", "ha_version": second}
    async with owned_provider(monkeypatch, first=hello, auth=ok) as (verify, seen, _):
        assert await verify("human") is False  # a plain denial, not the explained one
        assert seen["frames"] == [{"type": "auth", "access_token": DUMMY}]  # and no role query follows


def _accepted(version):
    try:
        ha_role._auth_message(json.dumps({"type": "auth_required", "ha_version": version}), "auth_required")
    except ValueError:
        return False
    return True


def test_exactly_the_reviewed_versions_and_the_later_patches_of_reviewed_months_are_accepted():
    # An oracle written apart from the rule, over every year.month.patch of 2025-2027 with months 0-13 and patches 0-129
    # (padding, other shapes and pre-releases are the near-miss list above).
    newest = {}
    for version in ha_role._HA_VERSIONS:
        year, month, patch = map(int, version.split("."))
        newest[(year, month)] = max(patch, newest.get((year, month), -1))
    assert newest == {(2026, 7): 4, (2026, 8): 3, (2026, 9): 4, (2026, 10): 4, (2026, 11): 3}
    expected = set(ha_role._HA_VERSIONS)
    for (year, month), top in newest.items():
        expected |= {f"{year}.{month}.{patch}" for patch in range(top + 1, 130)}
    universe = [f"{year}.{month}.{patch}" for year in (2025, 2026, 2027) for month in range(14) for patch in range(130)]
    assert {version for version in universe if _accepted(version)} == expected
    assert all(_accepted(version) for version in LATER_PATCHES)
    assert not any(_accepted(version) for version in NEAR_MISSES)


def test_the_rule_table_is_computed_from_the_reviewed_list_and_cannot_be_changed_at_run_time():
    assert dict(ha_role._REVIEWED_MONTHS) == {(2026, 7): (2, 4), (2026, 8): (0, 3), (2026, 9): (0, 4), (2026, 10): (0, 4),
                                              (2026, 11): (0, 3)}
    with pytest.raises(TypeError):
        ha_role._REVIEWED_MONTHS[(2026, 12)] = (0, 0)
    with pytest.raises(AttributeError):
        ha_role._HA_VERSIONS.add("2026.12.0")


def test_the_rule_needs_a_patch_above_the_newest_reviewed_one_of_its_month():
    # _auth_message accepts a listed version before it asks the rule, so `>` against `>=` cannot be seen through the verifier
    # (an equivalent mutation there): pin it on the function itself (independent review 2026-11-25, S3). The newest reviewed
    # patch of a month is listed, not a "later" patch; the next one is.
    assert ha_role._later_patch("2026.11.3") is False and ha_role._later_patch("2026.7.4") is False
    assert ha_role._REVIEWED_MONTHS
    for (year, month), (first, last) in ha_role._REVIEWED_MONTHS.items():
        assert ha_role._later_patch(f"{year}.{month}.{last}") is False
        assert ha_role._later_patch(f"{year}.{month}.{last + 1}") is True


def test_every_reviewed_version_has_the_year_month_patch_form():
    # ha_role._reviewed_months() int()s every element of _HA_VERSIONS when the module loads, so a pre-release string in the
    # list would break the import with a ValueError. The list holds only year.month.patch releases
    # (docs/ha-role-core-contract.md "Adding a release", step 3): the form the rule accepts for a later patch.
    assert ha_role._HA_VERSIONS
    for version in ha_role._HA_VERSIONS:
        assert ha_role._PATCH_RELEASE.fullmatch(version), version


@pytest.mark.parametrize("version,month,span", [
    ("2026.11.4", "2026.11", "2026.11.0 to 2026.11.3"), ("2026.7.5", "2026.7", "2026.7.2 to 2026.7.4"),
    ("2026.10.40", "2026.10", "2026.10.0 to 2026.10.4"),
])
async def test_a_later_patch_release_is_logged_once_per_version_and_process(monkeypatch, capsys, version, month, span):
    hello, ok = {"type": "auth_required", "ha_version": version}, {"type": "auth_ok", "ha_version": version}
    async with owned_provider(monkeypatch, first=hello, auth=ok) as (verify, seen, _):
        for _ in range(3):
            assert await verify("human") is True
        assert seen["connections"] == 3
    err = capsys.readouterr().err
    lines = [line for line in err.splitlines() if line]
    assert len(lines) == 1, err  # one add-on log line per version and process
    assert lines[0].startswith(f"management: Home Assistant Core {version} is accepted as a later patch release of {month}")
    assert f"({span})" in lines[0] and "the version itself was not reviewed" in lines[0]
    assert "has not been reviewed" not in lines[0]  # the refusal's line is another one
    assert DUMMY not in err and "human" not in err and "config/auth/list" not in err


async def test_each_later_patch_release_has_its_own_log_line_and_a_reviewed_release_has_none(monkeypatch, capsys):
    hello, ok = {"type": "auth_required", "ha_version": "2026.11.3"}, {"type": "auth_ok", "ha_version": "2026.11.3"}
    async with owned_provider(monkeypatch, first=hello, auth=ok) as (verify, seen, _):
        for version in ("2026.11.3", "2026.7.2", "2026.11.4", "2026.11.5", "2026.11.4", "2026.11.3"):
            hello["ha_version"] = ok["ha_version"] = version
            assert await verify("human") is True
    lines = [line for line in capsys.readouterr().err.splitlines() if line]
    assert [line.split()[4] for line in lines] == ["2026.11.4", "2026.11.5"]


def test_the_later_patch_log_is_bounded_per_process_and_apart_from_the_refusal_log(capsys):
    verify = ha_role._Verifier(None)
    for patch in range(5, 5 + ha_role._MAX_REPORTED + 8):
        verify._report_later_patch(f"2026.7.{patch}")
        verify._report_later_patch(f"2026.7.{patch}")
    assert len(capsys.readouterr().err.splitlines()) == ha_role._MAX_REPORTED
    # Its budget is spent, but a refusal is still explained once (the two kinds of line are counted apart).
    verify._report_unreviewed("2026.12.0")
    verify._report_unreviewed("2026.12.0")
    assert capsys.readouterr().err.count("Home Assistant Core 2026.12.0 has not been reviewed") == 1


async def test_the_panel_follows_core_to_a_later_patch_release_and_stops_at_a_new_month(tmp_path, monkeypatch, capsys):
    hello, ok = {"type": "auth_required", "ha_version": "2026.11.3"}, {"type": "auth_ok", "ha_version": "2026.11.3"}
    async with owned_provider(monkeypatch, first=hello, auth=ok) as (verify, seen, _):
        async with product_gateway(tmp_path, verify) as (store, panel, client):
            assert (await panel.get("/api/bootstrap", headers=IDENTITY)).status_code == 200
            hello["ha_version"] = ok["ha_version"] = "2026.11.4"  # Core updated to a later patch release
            assert (await panel.get("/api/bootstrap", headers=IDENTITY)).status_code == 200
            hello["ha_version"] = ok["ha_version"] = "2026.12.0"  # Core updated to the first release of the next month
            denied = await panel.get("/api/bootstrap", headers=IDENTITY)
            assert denied.status_code == 403
            assert denied.json() == {"error": "request denied", "detail": {"code": "core_version_unreviewed", "ha_version": "2026.12.0"}}
            hello["ha_version"] = ok["ha_version"] = "2026.11.4"
            seen["response"] = result([user(group_ids=[])])  # a later patch release does not make a non-administrator one
            plain = await panel.get("/api/bootstrap", headers=IDENTITY)
            assert plain.status_code == 403 and plain.json() == {"error": "request denied"}
            assert seen["frames"].count({"type": "auth", "access_token": DUMMY}) == 3  # 11.3, 11.4 and 11.4 again; never 12.0
    err = capsys.readouterr().err
    assert err.count("is accepted as a later patch release") == 1 and err.count("has not been reviewed") == 1


NO_CHILD = {"child": "unconfigured", "ready": False, "backend": "unknown", "reason": None}
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "claude-ai", "version": "0"}}}


@asynccontextmanager
async def product_gateway(tmp_path, verify):
    """A Hermes add-on as it starts after a fresh install (every tool and write on), without a backend: the gateway
    itself answers initialize and tools/list from the packaged listing, as for Claude.ai before setup."""
    store = ProductStore(tmp_path / "hermes", "hermes")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(502))) as child:
        admin, mcp = make_apps(store, PRODUCT_TOOLS["hermes"], child, verify_admin=verify, listing=listing("hermes"),
                               availability=lambda: dict(NO_CHILD), server_name="woow-mcp-hermes")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=admin, client=("172.30.32.2", 1)),
                                     base_url="http://admin") as panel:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mcp), base_url="http://mcp") as client:
                yield store, panel, client
    store.close()


async def listed_tools(client, token, secret_path):
    url = f"/private_{token}/mcp" if secret_path else "/mcp"
    headers = {"Accept": "application/json, text/event-stream"}
    if not secret_path:
        headers["Authorization"] = "Bearer " + token
    initialized = await client.post(url, headers=headers, json=INIT)
    assert initialized.status_code == 200, initialized.text
    headers["Mcp-Session-Id"] = initialized.headers["mcp-session-id"]
    assert (await client.post(url, headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})).status_code == 202
    listed = await client.post(url, headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listed.status_code == 200, listed.text
    return {tool["name"] for tool in listed.json()["result"]["tools"]}


async def test_on_an_unreviewed_core_mcp_serves_and_only_the_panel_refuses_with_the_reason(tmp_path, monkeypatch, capsys):
    hello, ok = {"type": "auth_required", "ha_version": "2026.10.4"}, {"type": "auth_ok", "ha_version": "2026.10.4"}
    async with owned_provider(monkeypatch, first=hello, auth=ok) as (verify, seen, _):
        async with product_gateway(tmp_path, verify) as (store, panel, client):
            bootstrap = await panel.get("/api/bootstrap", headers=IDENTITY)
            assert bootstrap.status_code == 200  # a reviewed Core: the panel works
            headers = {**IDENTITY, "X-CSRF-Token": bootstrap.json()["csrf"]}
            # Core is updated to a release this add-on has not reviewed (the frames are read per connection).
            hello["ha_version"] = ok["ha_version"] = "2026.12.0"
            token, before = store.load().token, store.path.read_bytes()
            reason = {"error": "request denied", "detail": {"code": "core_version_unreviewed", "ha_version": "2026.12.0"}}
            policy = {"writes_enabled": False, "disabled": ["hermes_inspect"], "enabled_write_tools": []}
            for method, path, payload in [("GET", "/api/bootstrap", None), ("PUT", "/api/policy", policy),
                                          ("POST", "/api/token/reveal", None), ("POST", "/api/token/rotate", None),
                                          ("PUT", "/api/endpoint", {"endpoint": "https://mcp.example.test/mcp"})]:
                response = await panel.request(method, path, headers=headers, json=payload)
                assert response.status_code == 403 and response.json() == reason, (path, response.text)
                assert token not in response.text and "csrf" not in response.text
            assert store.path.read_bytes() == before  # no setting changed
            page = await panel.get("/", headers=IDENTITY)
            assert page.status_code == 403 and page.headers["content-type"].startswith("text/html")
            assert "<h1>這個 HA Core 版本尚未審核：2026.12.0</h1>" in page.text and "照常服務" in page.text
            assert not any(tag in page.text for tag in ("<script", "<style", "<link", "<form", " style="))
            assert "default-src 'self'" in page.headers["content-security-policy"]
            asset = await panel.get("/assets/app.js", headers=IDENTITY)
            assert asset.status_code == 403 and asset.json() == reason  # assets stay behind the role check
            # MCP never uses the role check: Bearer and the Claude.ai secret path serve the full all-on catalog.
            for secret_path in (False, True):
                assert await listed_tools(client, token, secret_path) == set(PRODUCT_TOOLS["hermes"])
            assert store.path.read_bytes() == before
            assert seen["frames"].count({"type": "auth", "access_token": DUMMY}) == 1  # only the reviewed bootstrap
            hello["ha_version"] = ok["ha_version"] = "2026.10.4"  # back on a reviewed Core: the panel works again
            assert (await panel.get("/api/bootstrap", headers=IDENTITY)).status_code == 200
    err = capsys.readouterr().err
    assert err.count("has not been reviewed") == 1 and "Core 2026.12.0 " in err
    assert DUMMY not in err and token not in err


async def test_a_plain_denial_keeps_its_fixed_answer_and_page(tmp_path, monkeypatch):
    async with owned_provider(monkeypatch, response=result([user(group_ids=[])])) as (verify, _, __):
        async with product_gateway(tmp_path, verify) as (_, panel, __):
            for path in ("/api/bootstrap", "/"):
                response = await panel.get(path, headers=IDENTITY)
                assert response.status_code == 403 and response.json() == {"error": "request denied"}


@pytest.mark.parametrize("version,heading", [
    ("2026.12.0", "<h1>這個 HA Core 版本尚未審核：2026.12.0</h1>"),
    (None, "<h1>這個 HA Core 版本尚未審核（Supervisor 回報的版本字串無法辨識）</h1>"),
    ('<img src=x onerror="1">', "<h1>這個 HA Core 版本尚未審核：&lt;img src=x onerror=&quot;1&quot;&gt;</h1>"),
])
def test_the_unreviewed_core_page_is_static_text(version, heading):
    response = ui.unreviewed_core_page(version)
    body = response.body.decode()
    assert response.status_code == 403 and response.media_type == "text/html" and heading in body
    # What is accepted without a review is on the page too, so a later patch release is not expected to be refused.
    assert "自動放行" in body and "修補版" in body
    # The sentence is about the visitor's own version: it is NOT in the two accepted groups. It once said the reverse
    # ("這個 Core 版本不是（新的月份、…）"), the very list this page is shown for (independent review 2026-11-25, M2).
    assert "不在這兩類之內" in body and "版本不是（" not in body
    assert "<img" not in body and not any(tag in body for tag in ("<script", "<style", "<link", "<form", " style="))


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
            headers = reviewed_headers((await client.get("/api/bootstrap", headers=headers)).json(), headers)
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
            headers = reviewed_headers((await client.get("/api/bootstrap", headers=headers)).json(), headers)
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
            headers = reviewed_headers((await client.get("/api/bootstrap", headers=headers)).json(), headers)
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
    # HM-25: n8n's runtime is run_product's (run.run hands it the n8n adapter), so it takes run_product's factory.
    assert "run_product.run(" in inspect.getsource(run.run) and not hasattr(run, "make_ha_admin_verifier")
    assert run_product.make_ha_admin_verifier is ha_role.make_ha_admin_verifier
    assert "verify_admin=make_ha_admin_verifier()" in inspect.getsource(run_product.run)
    assert not isinstance(ha_role._NoRedirectConnect.process_redirect(None, RuntimeError()), str)


async def test_real_n8n_executable_tcp_uses_production_factory(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    from owned_executable import Executable, draw_public_ports
    async with owned_provider(monkeypatch) as (_, seen, __):
        # Drawn once the fake Supervisor listens: its bind of port 0 could take a port drawn (and closed) before it.
        admin_port, mcp_port = draw_public_ports(2)
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
from mcp_admin_core import profile_runtime  # HM-25: n8n's runtime is run_product's; its profile makes the apps
apps = profile_runtime.make_apps
def ingress_simulation(*args, **kwargs):
    assert isinstance(kwargs["verify_admin"], ha_role._Verifier)
    admin, mcp = apps(*args, **kwargs)
    async def ingress(scope, receive, send):
        await admin({{**scope, "client": ("172.30.32.2", 1)}}, receive, send)
    return ingress, mcp
profile_runtime.make_apps = ingress_simulation
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
                headers = reviewed_headers(response.json(), IDENTITY)
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
