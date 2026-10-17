"""Hermes MCP Server — FastMCP server with 9 tools bridging Gateway + Dashboard APIs.

Gateway API  (:8642) — OpenAI-compatible API with Bearer auth  [A]
Dashboard API (:9119) — Management REST API with cookie auth   [B]

Environment variables for connection config:
  HERMES_GATEWAY_URL, HERMES_GATEWAY_API_KEY
  HERMES_DASHBOARD_URL, HERMES_DASHBOARD_USERNAME, HERMES_DASHBOARD_PASSWORD
"""

from __future__ import annotations

import asyncio
import email.utils
import hashlib
import json
import math
import os
import re
import time
from typing import Any, Awaitable, Callable

import httpx
from backend_policy import async_client, backend_errors, backend_error_text
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("hermes-mcp-server")

# ---------------------------------------------------------------------------
# Deny-list for config writes
# ---------------------------------------------------------------------------

DENIED_CONFIG_KEYS = {
    "terminal.backend",
    "api_server.cors_origins",
    "api_server.host",
    "dashboard.basic_auth",
    "secrets",
}

# ---------------------------------------------------------------------------
# Credential redaction for config reads (Woow 0.2.2)
# ---------------------------------------------------------------------------

# Hermes keeps the credentials it uses in its config (e.g. custom_providers[].api_key for a custom OpenAI-compatible
# endpoint) and GET /api/config returns them in plain text. A config read keeps every field name and shows whether a
# secret is set, never its value. A key is secret when one of its words (split at non-alphanumerics and camelCase) is in
# SECRET_WORDS, or its last word is in SECRET_LAST_WORDS (api_key, OPENAI_API_KEY, access_token, basic_auth; not
# max_tokens or auth_mode). Every non-empty value under such a key (nested objects and lists included) becomes
# [REDACTED]; empty strings, null and booleans stay, so "not set" remains visible. A URL's userinfo password is
# redacted in every string. Writes (action=set) are unchanged.
REDACTED = "[REDACTED]"
SECRET_WORDS = frozenset({"password", "passwd", "passphrase", "secret", "secrets", "authorization", "credential",
                          "credentials", "apikey", "cookie", "cookies"})
SECRET_LAST_WORDS = frozenset({"key", "token", "auth", "pat", "bearer"})
_KEY_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")
_URL_PASSWORD = re.compile(r"(://[^/\s:@]*:)[^/\s@]+@")


def _secret_key(name: Any) -> bool:
    words = [word.lower() for word in _KEY_WORD.findall(str(name))]
    return bool(words) and (any(word in SECRET_WORDS for word in words) or words[-1] in SECRET_LAST_WORDS)


def _redact_all(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _redact_all(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_all(v) for v in value]
    if value is None or isinstance(value, bool) or value == "":
        return value
    return REDACTED


def redact_config(value: Any) -> Any:
    """A config value with the value of every secret field replaced by [REDACTED] (field names kept)."""
    if isinstance(value, dict):
        return {k: _redact_all(v) if _secret_key(k) else redact_config(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_config(v) for v in value]
    if isinstance(value, str):
        return _URL_PASSWORD.sub(r"\1" + REDACTED + "@", value)
    return value


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


class ConnectionNotConfiguredError(RuntimeError):
    """連線設定缺漏（或形狀不對）時丟出，訊息直接指向 admin GUI 的修正動作。

    存在的理由：把 ``base_url=""`` 交給 httpx 只會得到
    ``Request URL is missing an 'http://' or 'https://' protocol.``——那句會把人帶去查
    「哪個 URL 少了 http:// 前綴」，而真因是租戶根本沒填。admin REST 面
    （routers/config.py、routers/health.py、routers/dashboard_proxy.py）本來就會回
    「not configured」，MCP 工具面必須講同一句話。
    """


# 每個連線欄位對應 admin GUI 的哪個區塊（訊息要能直接指向動作）
_ADMIN_HINTS = {
    "gateway_url": "Connection > Gateway API Server",
    "gateway_api_key": "Connection > Gateway API Server",
    "dashboard_url": "Connection > Dashboard REST API",
    "dashboard_username": "Connection > Dashboard REST API",
    "dashboard_password": "Connection > Dashboard REST API",
}


def _get_connection() -> dict[str, str]:
    """Read connection config from environment variables."""
    return {
        "gateway_url": os.environ.get("HERMES_GATEWAY_URL", ""),
        "gateway_api_key": os.environ.get("HERMES_GATEWAY_API_KEY", ""),
        "dashboard_url": os.environ.get("HERMES_DASHBOARD_URL", ""),
        "dashboard_username": os.environ.get("HERMES_DASHBOARD_USERNAME", ""),
        "dashboard_password": os.environ.get("HERMES_DASHBOARD_PASSWORD", ""),
    }


def _require_url(value: str, field: str) -> str:
    """回傳正規化後的 base URL；缺值或缺 scheme 時丟講人話的錯誤。

    兩種形狀都會讓 httpx 丟出同一句誤導訊息，所以兩種都在這裡攔下來：
    空字串（沒設定）與 ``host:port``（有值但沒有 scheme）。
    """
    url = (value or "").strip()
    where = _ADMIN_HINTS[field]
    if not url:
        raise ConnectionNotConfiguredError(
            f"{field} is not configured - set it in the admin GUI under {where}"
        )
    if not url.startswith(("http://", "https://")):
        raise ConnectionNotConfiguredError(
            f"{field} must start with http:// or https:// (got {url!r}) - "
            f"fix it in the admin GUI under {where}"
        )
    return url.rstrip("/")


def _check_gateway_response(resp: httpx.Response, api_key: str) -> None:
    """Gateway 回 401/403 而 api key 根本沒設定時，講「沒設定」而不是「認證失敗」。

    只在 key 為空時改寫：key 有填卻被拒＝真的認證失敗，必須原樣回報。
    """
    if resp.status_code in (401, 403) and not api_key:
        raise ConnectionNotConfiguredError(
            f"gateway_api_key is not configured - set it in the admin GUI under "
            f"{_ADMIN_HINTS['gateway_api_key']} (Hermes Gateway returned HTTP {resp.status_code})"
        )


# Woow 0.2.2 (test VM 2026-10-16, G2): one Hermes agent turn (POST /v1/responses, ~14.5k prompt tokens) routinely took
# 28-30 s with free models, so hermes_chat's former 30 s limit failed 2 of 3 turns with BACKEND_TIMEOUT although Hermes
# finished them. A chat turn may take CHAT_TIMEOUT seconds (HERMES_MCP_CHAT_TIMEOUT, 1-3600, default 300; the add-on's
# gateway allows a tools/call reply up to 330 s); connecting, and every other Gateway/Dashboard call, keep 30 s.
CHAT_TIMEOUT = 300.0


def _chat_timeout() -> float:
    try:
        value = float(os.environ.get("HERMES_MCP_CHAT_TIMEOUT", CHAT_TIMEOUT))
    except ValueError:
        return CHAT_TIMEOUT
    return min(max(value, 1.0), 3600.0) if math.isfinite(value) else CHAT_TIMEOUT


def _gateway_client(url: str, api_key: str, timeout: float | httpx.Timeout = 30.0) -> httpx.AsyncClient:
    """Create an httpx client for the Hermes Gateway API with Bearer auth."""
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return async_client(
        base_url=_require_url(url, "gateway_url"),
        headers=headers,
        timeout=timeout,
    )


# Dashboard cookie cache: {url#credential fingerprint: (cookie, expiry)}
# Woow (commercial acceptance AI-HMCP-003-1): the key carries a fingerprint of the credentials (changed credentials never
# reuse an old cookie), and a 401 drops the cookie and logs in once more (see _get_dashboard_client).
_cookie_cache: dict[str, tuple[str, float]] = {}

# Single-flight login locks: {cache key: asyncio.Lock} (commercial acceptance AI-HER-PERF-1). The Hermes dashboard allows 10
# POST /auth/password-login per client IP per 60 s (successful logins count too) and its 429 has no Retry-After. One
# child serves every MCP session, so when 10+ calls start cold (or the cookie expires) and each logs in, the 11th gets
# 429. Only one caller per dashboard_url logs in; the others wait for its cookie in the cache and share it.
_login_locks: dict[str, asyncio.Lock] = {}

# A 429 login is retried up to LOGIN_MAX_RETRIES times: after Retry-After (seconds or an HTTP date) capped at
# LOGIN_RETRY_AFTER_CAP, otherwise (Hermes 0.21.6 sends none) after 1 s, then 2 s. Other statuses are not retried.
LOGIN_MAX_RETRIES = 2
LOGIN_BACKOFF_BASE = 1.0
LOGIN_RETRY_AFTER_CAP = 10.0

# list_providers lists at most this many models per provider (aggregators such as OpenRouter have hundreds)
MODEL_LIST_LIMIT = 30


def _login_retry_delay(resp: httpx.Response, attempt: int) -> float:
    """Seconds to wait after the attempt-th (0-based) 429: Retry-After first, else exponential backoff."""
    value = (resp.headers.get("retry-after") or "").strip()
    delay: float | None = None
    if value:
        try:
            delay = float(value)
        except ValueError:
            try:
                delay = email.utils.parsedate_to_datetime(value).timestamp() - time.time()
            except (TypeError, ValueError, IndexError, OverflowError):
                delay = None
    if delay is None or not math.isfinite(delay):
        delay = LOGIN_BACKOFF_BASE * (2 ** attempt)
    return min(max(delay, 0.0), LOGIN_RETRY_AFTER_CAP)


def _cookie_key(url: str, username: str, password: str) -> str:
    """Cache key: the dashboard URL plus a sha256 fingerprint of the credentials (never the credentials)."""
    digest = hashlib.sha256(f"{username}\0{password}".encode()).hexdigest()[:16]
    return f"{url}#{digest}"


def _cached_cookie(key: str) -> str | None:
    cached = _cookie_cache.get(key)
    if cached and cached[1] > time.time():
        return cached[0]
    return None


async def _dashboard_login(url: str, username: str, password: str) -> str:
    """Login to Hermes Dashboard and return session cookie (cached 10 min).

    Concurrent logins for one dashboard_url are coalesced into one; a 429 login is retried (AI-HER-PERF-1).
    """
    url = _require_url(url, "dashboard_url")
    key = _cookie_key(url, username, password)
    cached = _cached_cookie(key)
    if cached is not None:
        return cached
    async with _login_locks.setdefault(key, asyncio.Lock()):
        # The previous holder may have logged in while this caller waited.
        cached = _cached_cookie(key)
        if cached is not None:
            return cached
        return await _password_login(url, username, password)


async def _password_login(url: str, username: str, password: str) -> str:
    """POST /auth/password-login; the caller holds this url's login lock."""
    async with async_client(base_url=url, timeout=5.0) as client:
        for attempt in range(LOGIN_MAX_RETRIES + 1):
            resp = await client.post(
                "/auth/password-login",
                json={"provider": "basic", "username": username, "password": password},
            )
            if resp.status_code != 429 or attempt == LOGIN_MAX_RETRIES:
                break
            await asyncio.sleep(_login_retry_delay(resp, attempt))
        # 帳密沒設定又被拒 ⇒ 講「沒設定」；有填卻被拒才是真的認證失敗（維持原樣拋出）。
        if resp.status_code in (401, 403) and not (username and password):
            missing = " / ".join(
                name for name, value in (
                    ("dashboard_username", username), ("dashboard_password", password),
                ) if not value
            )
            raise ConnectionNotConfiguredError(
                f"{missing} is not configured - set it in the admin GUI under "
                f"{_ADMIN_HINTS['dashboard_password']} "
                f"(Hermes Dashboard login returned HTTP {resp.status_code})"
            )
        resp.raise_for_status()
        for h in resp.headers.get_list("set-cookie"):
            if "hermes_session_at=" in h:
                token = h.split("hermes_session_at=")[1].split(";")[0].strip('"')
                _cookie_cache[_cookie_key(url, username, password)] = (token, time.time() + 600)
                return token
        return ""


def _cookie_header(cookie: str) -> str:
    return f'hermes_session_at="{cookie}"'


def _dashboard_client(url: str, cookie: str) -> httpx.AsyncClient:
    """Create an httpx client for the Hermes Dashboard API with cookie auth."""
    return async_client(
        base_url=_require_url(url, "dashboard_url"),
        headers={"Content-Type": "application/json", "Cookie": _cookie_header(cookie)},
        timeout=30.0,
    )


def _relogin_on_401(client: httpx.AsyncClient, relogin: Callable[[], Awaitable[str]]) -> httpx.AsyncClient:
    """A dashboard 401 (Hermes restarted or rotated, the cookie is stale): drop it, log in once, resend the request.

    Once only: a second 401 (or a 401 login: the password changed) goes to the caller. A 401 means the request was not
    processed, so resending a POST/PUT/DELETE is safe. Wraps the instance's send (the transport stays), which get, post
    and request all use.
    """
    send = client.send
    pending = [relogin]

    async def send_with_relogin(request: httpx.Request, **kwargs: Any) -> httpx.Response:
        response = await send(request, **kwargs)
        if response.status_code != 401 or not pending:
            return response
        retry = pending.pop()
        await response.aclose()
        header = _cookie_header(await retry())
        client.headers["Cookie"] = header
        request.headers["Cookie"] = header
        return await send(request, **kwargs)

    client.send = send_with_relogin  # type: ignore[method-assign]
    return client


async def _get_dashboard_client(conn: dict) -> httpx.AsyncClient:
    """Get authenticated dashboard client.

    守衛前置：先驗 dashboard_url（缺值 / 缺 scheme 都在這裡擋下），再 login。
    server.py 的 dashboard 系工具全部走這條，所以這裡是唯一的把關點。
    """
    url = _require_url(conn.get("dashboard_url", ""), "dashboard_url")
    username, password = conn.get("dashboard_username", ""), conn.get("dashboard_password", "")
    cookie = await _dashboard_login(url, username, password)

    async def relogin() -> str:
        # Drop only the cookie this client used: when several sessions get a 401 at once, a late one must not drop the
        # fresh cookie another just got; the login itself is single-flight (AI-HER-PERF-1).
        key = _cookie_key(url, username, password)
        if _cookie_cache.get(key, ("",))[0] == cookie:
            _cookie_cache.pop(key, None)
        return await _dashboard_login(url, username, password)

    return _relogin_on_401(_dashboard_client(url, cookie), relogin)


# ---------------------------------------------------------------------------
# Tool 1: hermes_inspect
# ---------------------------------------------------------------------------


@mcp.tool()
async def hermes_inspect(target: str = "all") -> str:
    """Inspect Hermes Agent. target: all, capabilities, config, model, status"""
    conn = _get_connection()
    result: dict[str, Any] = {}

    if target in ("all", "capabilities"):
        try:
            async with _gateway_client(conn["gateway_url"], conn["gateway_api_key"]) as client:
                resp = await client.get("/v1/capabilities")
                _check_gateway_response(resp, conn["gateway_api_key"])
                resp.raise_for_status()
                result["capabilities"] = resp.json()
        except Exception as exc:
            result["capabilities_error"] = backend_error_text(exc)

    if target in ("all", "config"):
        try:
            async with await _get_dashboard_client(conn) as client:
                resp = await client.get("/api/config")
                resp.raise_for_status()
                cfg = resp.json()
                result["config_summary"] = redact_config({
                    "model": cfg.get("model", ""),
                    "toolsets": cfg.get("toolsets", []),
                    "max_live_sessions": cfg.get("max_live_sessions"),
                })
        except Exception as exc:
            result["config_error"] = backend_error_text(exc)

    if target in ("all", "model"):
        try:
            async with await _get_dashboard_client(conn) as client:
                resp = await client.get("/api/model/info")
                resp.raise_for_status()
                result["model_info"] = resp.json()
        except Exception as exc:
            result["model_info_error"] = backend_error_text(exc)

    if target in ("all", "status"):
        try:
            async with await _get_dashboard_client(conn) as client:
                resp = await client.get("/api/status")
                resp.raise_for_status()
                st = resp.json()
                result["status"] = {
                    "version": st.get("version"),
                    "gateway_running": st.get("gateway_running"),
                    "active_sessions": st.get("active_sessions"),
                }
        except Exception as exc:
            result["status_error"] = backend_error_text(exc)

    return json.dumps(result, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool 2: hermes_skill
# ---------------------------------------------------------------------------


@mcp.tool()
@backend_errors
async def hermes_skill(action: str, name: str | None = None) -> str:
    """Manage Hermes skills. Actions: list, enable, disable"""
    conn = _get_connection()

    async with await _get_dashboard_client(conn) as client:
        if action == "list":
            resp = await client.get("/api/skills")
            resp.raise_for_status()
            skills = resp.json()
            if isinstance(skills, list):
                summary = [{"name": s.get("name"), "enabled": s.get("enabled"), "category": s.get("category")} for s in skills if isinstance(s, dict)]
                return json.dumps({"total": len(summary), "skills": summary}, indent=2)
            return json.dumps(skills, indent=2)

        if action in ("enable", "disable"):
            if not name:
                return json.dumps({"error": f"Skill name required for '{action}'"})
            enabled = action == "enable"
            resp = await client.put("/api/skills/toggle", json={"name": name, "enabled": enabled})
            resp.raise_for_status()
            return json.dumps({"ok": True, "name": name, "enabled": enabled})

        return json.dumps({"error": f"Unknown action: {action}. Valid: list, enable, disable"})


# ---------------------------------------------------------------------------
# Tool 3: hermes_mcp (MCP server management)
# ---------------------------------------------------------------------------


@mcp.tool()
@backend_errors
async def hermes_mcp(action: str, name: str | None = None, url: str | None = None) -> str:
    """Manage Hermes MCP server connections. Actions: list, add, remove"""
    conn = _get_connection()

    async with await _get_dashboard_client(conn) as client:
        if action == "list":
            resp = await client.get("/api/mcp/servers")
            resp.raise_for_status()
            return json.dumps(resp.json(), indent=2)

        if action == "add":
            if not name or not url:
                return json.dumps({"error": "Both 'name' and 'url' required"})
            if url.startswith("stdio:") or url.startswith("command:"):
                return json.dumps({"error": "stdio transport is blocked for security"})
            resp = await client.post("/api/mcp/servers", json={
                "name": name, "transport": "streamable-http", "url": url,
            })
            resp.raise_for_status()
            return json.dumps({"ok": True, "name": name, "added": True})

        if action == "remove":
            if not name:
                return json.dumps({"error": "Name required for 'remove'"})
            resp = await client.delete(f"/api/mcp/servers/{name}")
            resp.raise_for_status()
            return json.dumps({"ok": True, "name": name, "removed": True})

        return json.dumps({"error": f"Unknown action: {action}. Valid: list, add, remove"})


# ---------------------------------------------------------------------------
# Tool 4: hermes_model
# ---------------------------------------------------------------------------


@mcp.tool()
@backend_errors
async def hermes_model(
    action: str = "info",
    model: str | None = None,
    provider: str | None = None,
    confirm_expensive: bool = False,
) -> str:
    """Manage Hermes model. Actions: info, set, list_providers

    - info: the configured main model and provider
    - list_providers: providers Hermes can use (from Hermes itself), each with its models
    - set: switch the main model for new sessions (requires model; provider defaults to the current one).
      If Hermes asks to confirm an expensive model, call again with confirm_expensive=true.
    """
    conn = _get_connection()

    async with await _get_dashboard_client(conn) as client:
        if action == "info":
            resp = await client.get("/api/model/info")
            resp.raise_for_status()
            return json.dumps(resp.json(), indent=2)

        if action == "list_providers":
            # Woow (AI-HMCP-001-2): Hermes' own GET /api/model/options (the fixed list lacked e.g. custom).
            resp = await client.get("/api/model/options")
            resp.raise_for_status()
            data = resp.json()
            providers = []
            for row in data.get("providers", []) if isinstance(data, dict) else []:
                if not isinstance(row, dict):
                    continue
                models = [str(m) for m in row.get("models") or []]
                providers.append({
                    "slug": row.get("slug"), "name": row.get("name"), "is_current": bool(row.get("is_current")),
                    "total_models": len(models), "models": models[:MODEL_LIST_LIMIT],
                })
            current = {"model": data.get("model"), "provider": data.get("provider")} if isinstance(data, dict) else {}
            return json.dumps({"current": current, "providers": providers}, indent=2)

        if action == "set":
            # Woow (AI-HMCP-001-2): Hermes 0.21.6's POST /api/model/set requires {scope, provider, model}; model alone
            # was always 422.
            if not model:
                return json.dumps({"error": "Specify 'model' (provider is optional and defaults to the current one)"})
            if not provider:
                info = await client.get("/api/model/info")
                info.raise_for_status()
                provider = (info.json() or {}).get("provider") or ""
                if not provider:
                    return json.dumps({"error": "Hermes has no current provider; specify 'provider' "
                                                "(see hermes_model action=list_providers)"})
            payload: dict[str, Any] = {"scope": "main", "provider": provider, "model": model}
            if confirm_expensive:
                payload["confirm_expensive_model"] = True
            resp = await client.post("/api/model/set", json=payload)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and data.get("confirm_required"):
                # Hermes' own answer (nothing changed), plus how to go ahead.
                data = {**data, "hint": "Hermes did not switch the model. Call hermes_model again with "
                                        "confirm_expensive=true to switch anyway."}
            return json.dumps(data, indent=2)

        return json.dumps({"error": f"Unknown action: {action}. Valid: info, set, list_providers"})


# ---------------------------------------------------------------------------
# Tool 5: hermes_config
# ---------------------------------------------------------------------------


@mcp.tool()
@backend_errors
async def hermes_config(action: str = "get", key: str | None = None, value: str | None = None, dry_run: bool = False) -> str:
    """Read or update Hermes config. Actions: get, set"""
    conn = _get_connection()

    async with await _get_dashboard_client(conn) as client:
        if action == "get":
            resp = await client.get("/api/config")
            resp.raise_for_status()
            data = resp.json()
            if key and isinstance(data, dict):
                parts = key.split(".")
                current = data
                for part in parts:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        return json.dumps({"error": f"Key '{key}' not found"})
                # A secret anywhere on the path (model.api_key, secrets.x) hides the whole value.
                current = _redact_all(current) if any(_secret_key(part) for part in parts) else redact_config(current)
                return json.dumps({"key": key, "value": current}, indent=2, default=str)
            return json.dumps(redact_config(data), indent=2, default=str)

        if action == "set":
            if not key or value is None:
                return json.dumps({"error": "Both 'key' and 'value' required"})
            if key in DENIED_CONFIG_KEYS:
                return json.dumps({"error": f"Key '{key}' is denied", "denied_keys": sorted(DENIED_CONFIG_KEYS)})
            if dry_run:
                return json.dumps({"dry_run": True, "key": key, "value": value, "message": "No changes made"}, indent=2)
            # Parse value as JSON if possible
            try:
                parsed_value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                parsed_value = value
            # Woow (AI-HMCP-001-4): PUT /api/config deep-merges the body, so a dotted key sent as is became a literal
            # top-level key ("display.compact: true") and display.compact did not change. Nest it, then read it back.
            parts = key.split(".")
            if any(not part.strip() for part in parts):
                return json.dumps({"error": f"Invalid key '{key}': empty path segment"})
            nested: Any = parsed_value
            for part in reversed(parts):
                nested = {part: nested}
            resp = await client.put("/api/config", json={"config": nested})
            resp.raise_for_status()

            check = await client.get("/api/config")
            check.raise_for_status()
            found, actual = True, check.json()
            for part in parts:
                if isinstance(actual, dict) and part in actual:
                    actual = actual[part]
                else:
                    found = False
                    break
            if not found or actual != parsed_value:
                shown = (_redact_all(actual) if any(_secret_key(part) for part in parts) else redact_config(actual))
                raise ValueError(
                    f"Hermes accepted the write but '{key}' reads back as "
                    f"{json.dumps(shown, default=str) if found else '(missing)'}, not "
                    f"{json.dumps(parsed_value, default=str)}. The key may not exist in this Hermes version "
                    f"(check with hermes_config action=get) or Hermes normalized the value."
                )
            return json.dumps({"ok": True, "key": key, "value": parsed_value}, indent=2, default=str)

        return json.dumps({"error": f"Unknown action: {action}. Valid: get, set"})


# ---------------------------------------------------------------------------
# Tool 6: hermes_tools
# ---------------------------------------------------------------------------


@mcp.tool()
@backend_errors
async def hermes_tools(action: str = "list", toolset: str | None = None) -> str:
    """Manage Hermes toolsets. Actions: list, enable, disable"""
    conn = _get_connection()

    async with await _get_dashboard_client(conn) as client:
        if action == "list":
            resp = await client.get("/api/tools/toolsets")
            resp.raise_for_status()
            return json.dumps(resp.json(), indent=2)

        if action in ("enable", "disable"):
            if not toolset:
                return json.dumps({"error": f"Toolset name required for '{action}'"})
            enabled = action == "enable"
            resp = await client.put(f"/api/tools/toolsets/{toolset}", json={"enabled": enabled})
            resp.raise_for_status()
            return json.dumps({"ok": True, "toolset": toolset, "enabled": enabled})

        return json.dumps({"error": f"Unknown action: {action}. Valid: list, enable, disable"})


# ---------------------------------------------------------------------------
# Tool 7: hermes_gateway
# ---------------------------------------------------------------------------


@mcp.tool()
@backend_errors
async def hermes_gateway(action: str = "status") -> str:
    """Manage Hermes Gateway. Actions: status, restart"""
    conn = _get_connection()

    async with await _get_dashboard_client(conn) as client:
        if action == "status":
            resp = await client.get("/api/status")
            resp.raise_for_status()
            data = resp.json()
            return json.dumps({
                "running": data.get("gateway_running", False),
                "state": data.get("gateway_state", "unknown"),
                "version": data.get("version"),
                "active_sessions": data.get("active_sessions", 0),
            }, indent=2)

        if action == "restart":
            resp = await client.post("/api/gateway/restart")
            resp.raise_for_status()
            return json.dumps({"ok": True, "message": "Gateway restart initiated"})

        return json.dumps({"error": f"Unknown action: {action}. Valid: status, restart"})


# ---------------------------------------------------------------------------
# Tool 8: hermes_chat
# ---------------------------------------------------------------------------


@mcp.tool()
@backend_errors
async def hermes_chat(message: str, session_id: str | None = None) -> str:
    """Send a chat message to Hermes and receive a response.

    session_id: optional conversation name. Reuse the same value to continue a multi-turn conversation
    (Hermes keeps the history under that conversation name; an unknown name starts a new one). A value
    starting with "resp_" continues from that Hermes response id. Omit it for a one-off turn.
    A turn may take up to HERMES_MCP_CHAT_TIMEOUT seconds (default 300); on timeout the turn is stopped.
    """
    conn = _get_connection()
    payload: dict[str, Any] = {"model": "default", "input": message, "stream": True}
    # Woow (AI-HMCP-001-5): session_id was never sent, so every turn was a new session. It maps to /v1/responses'
    # conversation (a named conversation whose history Hermes continues); a resp_ id is previous_response_id.
    sid = (session_id or "").strip()
    if sid.startswith("resp_"):
        payload["previous_response_id"] = sid
    elif sid:
        payload["conversation"] = sid

    limit = _chat_timeout()
    timeout = httpx.Timeout(limit, connect=30.0)  # a whole agent turn (see CHAT_TIMEOUT); wait_for bounds the turn
    async with _gateway_client(conn["gateway_url"], conn["gateway_api_key"], timeout) as client:
        try:
            data = await asyncio.wait_for(_chat_turn(client, payload, conn["gateway_api_key"]), timeout=limit)
        except asyncio.TimeoutError:
            # Woow (AI-HMCP-001-6): cancelling the streamed request closes it, and Hermes stops the turn when its client
            # goes away (api_server_openai_routes._write_sse_responses: disconnect -> _abandon_agent_task).
            raise httpx.TimeoutException(
                f"Hermes Gateway timed out: the turn did not finish within {limit:g} seconds and was stopped. "
                f"Tools Hermes already ran in this turn are not undone. Ask for a smaller step, or raise "
                f"HERMES_MCP_CHAT_TIMEOUT (now {limit:g} s)."
            ) from None
    if data.get("status") == "failed" or data.get("error"):
        error = data.get("error")
        detail = error.get("message") if isinstance(error, dict) else error
        raise RuntimeError(f"Hermes could not complete the turn: {detail or 'response failed'}")
    # Extract text from response
    output = data.get("output", [])
    texts = []
    for item in output if isinstance(output, list) else []:
        if isinstance(item, dict) and item.get("type") == "message":
            for c in item.get("content", []):
                if isinstance(c, dict) and c.get("type") == "output_text":
                    texts.append(c.get("text", ""))
    if texts:
        return "\n".join(texts)
    return json.dumps(data, indent=2, default=str)


async def _chat_turn(client: httpx.AsyncClient, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    """One /v1/responses turn with stream=true; returns the final response object (the completed/failed envelope).

    Streamed so that a timeout can close the connection and Hermes stops the turn; Hermes does not stop a non-streamed
    turn when its client leaves. A backend answering plain JSON is parsed as before.
    """
    async with client.stream("POST", "/v1/responses", json=payload) as resp:
        if resp.status_code >= 400:
            await resp.aread()
            _check_gateway_response(resp, api_key)
            resp.raise_for_status()
        if "text/event-stream" not in resp.headers.get("content-type", ""):
            await resp.aread()
            return resp.json()
        event, data_lines = "", []
        async for line in resp.aiter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
            elif not line and data_lines:
                if event in ("response.completed", "response.failed", "response.incomplete"):
                    body = json.loads("\n".join(data_lines))
                    envelope = body.get("response") if isinstance(body, dict) else None
                    return envelope if isinstance(envelope, dict) else {}
                event, data_lines = "", []
    raise RuntimeError("Hermes Gateway ended the reply without a result (stream closed early); retry.")


# ---------------------------------------------------------------------------
# Tool 9: hermes_session
# ---------------------------------------------------------------------------


@mcp.tool()
@backend_errors
async def hermes_session(action: str = "list", session_id: str | None = None) -> str:
    """Manage Hermes sessions. Actions: list, get, delete"""
    conn = _get_connection()

    # Sessions go via Dashboard API (has the session data)
    async with await _get_dashboard_client(conn) as client:
        if action == "list":
            resp = await client.get("/api/sessions")
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                sessions = data.get("sessions", [])
                return json.dumps({"total": data.get("total", len(sessions)), "sessions": sessions[:20]}, indent=2, default=str)
            return json.dumps(data, indent=2, default=str)

        if action == "get":
            if not session_id:
                return json.dumps({"error": "session_id required"})
            resp = await client.get(f"/api/sessions/{session_id}")
            resp.raise_for_status()
            return json.dumps(resp.json(), indent=2, default=str)

        if action == "delete":
            if not session_id:
                return json.dumps({"error": "session_id required"})
            resp = await client.delete(f"/api/sessions/{session_id}")
            resp.raise_for_status()
            # Woow (AI-HMCP-001-8): Hermes answers a missing session with 200 {"ok": true, "already_absent": true} (the
            # desktop's idempotent delete); it was reported as deleted. Report it like the other missing resources (404).
            data = resp.json() if resp.content else {}
            if isinstance(data, dict) and data.get("already_absent"):
                missing = httpx.Response(404, json={"detail": f"Session '{session_id}' not found; nothing was deleted"},
                                         request=resp.request)
                raise httpx.HTTPStatusError("session not found", request=resp.request, response=missing)
            return json.dumps({"ok": True, "deleted": session_id})

        return json.dumps({"error": f"Unknown action: {action}. Valid: list, get, delete"})


# ---------------------------------------------------------------------------
# Tool 10: hermes_cron
# ---------------------------------------------------------------------------


@mcp.tool()
@backend_errors
async def hermes_cron(
    action: str = "list",
    name: str | None = None,
    schedule: str | None = None,
    prompt: str | None = None,
    enabled: bool = True,
    job_id: str | None = None,
) -> str:
    """Manage Hermes cron/scheduled jobs.

    Actions: list, create, update, delete, trigger, pause, resume
    - list: show all cron jobs
    - create: new job (requires name, schedule, prompt)
    - update: modify job (requires job_id, plus fields to change)
    - delete: remove job (requires job_id)
    - trigger: run job now (requires job_id)
    - pause / resume: toggle job state (requires job_id)

    schedule uses cron syntax: '0 9 * * 1-5' = weekdays at 9am
    """
    conn = _get_connection()

    async with await _get_dashboard_client(conn) as client:
        if action == "list":
            resp = await client.get("/api/cron/jobs")
            resp.raise_for_status()
            jobs = resp.json()
            if isinstance(jobs, list):
                summary = []
                for j in jobs:
                    if isinstance(j, dict):
                        summary.append({
                            "id": j.get("id"),
                            "name": j.get("name"),
                            "schedule": j.get("schedule", {}).get("expr") if isinstance(j.get("schedule"), dict) else j.get("schedule"),
                            "prompt": (j.get("prompt") or "")[:80],
                            "enabled": j.get("enabled"),
                            "state": j.get("state"),
                            "next_run": j.get("next_run_at"),
                        })
                return json.dumps({"total": len(summary), "jobs": summary}, indent=2, default=str)
            return json.dumps(jobs, indent=2, default=str)

        if action == "create":
            if not name or not schedule or not prompt:
                return json.dumps({"error": "name, schedule, and prompt are all required"})
            resp = await client.post("/api/cron/jobs", json={
                "name": name, "schedule": schedule, "prompt": prompt, "enabled": enabled,
            })
            resp.raise_for_status()
            data = resp.json()
            return json.dumps({
                "ok": True, "id": data.get("id"), "name": data.get("name"),
                "schedule": data.get("schedule", {}).get("expr") if isinstance(data.get("schedule"), dict) else schedule,
                "next_run": data.get("next_run_at"),
            }, indent=2, default=str)

        if action == "update":
            if not job_id:
                return json.dumps({"error": "job_id required for update"})
            updates: dict[str, Any] = {}
            if prompt is not None:
                updates["prompt"] = prompt
            if schedule is not None:
                updates["schedule"] = schedule
            if name is not None:
                updates["name"] = name
            if not updates:
                return json.dumps({"error": "provide at least one field to update (prompt, schedule, name)"})
            resp = await client.put(f"/api/cron/jobs/{job_id}", json={"updates": updates})
            resp.raise_for_status()
            return json.dumps({"ok": True, "updated": job_id}, indent=2)

        if action == "delete":
            if not job_id:
                return json.dumps({"error": "job_id required"})
            resp = await client.delete(f"/api/cron/jobs/{job_id}")
            resp.raise_for_status()
            return json.dumps({"ok": True, "deleted": job_id})

        if action == "trigger":
            if not job_id:
                return json.dumps({"error": "job_id required"})
            resp = await client.post(f"/api/cron/jobs/{job_id}/trigger")
            resp.raise_for_status()
            return json.dumps({"ok": True, "triggered": job_id})

        if action == "pause":
            if not job_id:
                return json.dumps({"error": "job_id required"})
            resp = await client.post(f"/api/cron/jobs/{job_id}/pause")
            resp.raise_for_status()
            return json.dumps({"ok": True, "paused": job_id})

        if action == "resume":
            if not job_id:
                return json.dumps({"error": "job_id required"})
            resp = await client.post(f"/api/cron/jobs/{job_id}/resume")
            resp.raise_for_status()
            return json.dumps({"ok": True, "resumed": job_id})

        return json.dumps({"error": f"Unknown action: {action}. Valid: list, create, update, delete, trigger, pause, resume"})


# ---------------------------------------------------------------------------
# Tool 11: hermes_webhook
# ---------------------------------------------------------------------------

_LEGACY_PAYLOAD = re.compile(r"\{\{\s*payload\s*\}\}")


@mcp.tool()
@backend_errors
async def hermes_webhook(
    action: str = "list",
    name: str | None = None,
    prompt: str | None = None,
    enabled: bool = True,
) -> str:
    """Manage Hermes webhooks.

    Actions: list, enable_platform, create, delete, toggle
    - list: show webhook platform status and subscriptions
    - enable_platform: enable the webhook listener (triggers gateway restart)
    - create: new webhook (requires name, prompt). In the prompt, {__raw__} is the whole incoming JSON
      payload and {field.path} is one field of it (e.g. {order.id}); {event_type} is the event name
    - delete: remove webhook (requires name)
    - toggle: enable/disable webhook (requires name, set enabled=true/false)

    Example prompt: 'New order {order.id} received: {__raw__}. Summarize the order details.'
    """
    conn = _get_connection()

    async with await _get_dashboard_client(conn) as client:
        if action == "list":
            resp = await client.get("/api/webhooks")
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                subs = data.get("subscriptions", [])
                return json.dumps({
                    "platform_enabled": data.get("enabled", False),
                    "base_url": data.get("base_url", ""),
                    "total": len(subs),
                    "webhooks": [{"name": w.get("name"), "enabled": w.get("enabled"), "prompt": (w.get("prompt") or "")[:80]} for w in subs if isinstance(w, dict)],
                }, indent=2)
            return json.dumps(data, indent=2, default=str)

        if action == "enable_platform":
            resp = await client.post("/api/webhooks/enable", json={})
            resp.raise_for_status()
            return json.dumps({"ok": True, "message": "Webhook platform enabled. Gateway will restart."})

        if action == "create":
            if not name or not prompt:
                return json.dumps({"error": "name and prompt are required. Use {__raw__} for the incoming payload."})
            # Woow (AI-HMCP-001-7): the {{payload}} the old description taught is no Hermes placeholder (Hermes renders
            # {field.path} / {__raw__}), so the payload never reached the agent. Such a prompt gets {__raw__}.
            rendered = _LEGACY_PAYLOAD.sub("{__raw__}", prompt)
            resp = await client.post("/api/webhooks", json={
                "name": name, "prompt": rendered, "enabled": enabled,
            })
            resp.raise_for_status()
            result: dict[str, Any] = {"ok": True, "name": name, "created": True}
            if rendered != prompt:
                result["prompt"] = rendered
                result["note"] = "{{payload}} is not a Hermes placeholder; it was replaced with {__raw__}"
            return json.dumps(result)

        if action == "delete":
            if not name:
                return json.dumps({"error": "name required"})
            resp = await client.delete(f"/api/webhooks/{name}")
            resp.raise_for_status()
            return json.dumps({"ok": True, "deleted": name})

        if action == "toggle":
            if not name:
                return json.dumps({"error": "name required"})
            resp = await client.put(f"/api/webhooks/{name}/enabled", json={"enabled": enabled})
            resp.raise_for_status()
            return json.dumps({"ok": True, "name": name, "enabled": enabled})

        return json.dumps({"error": f"Unknown action: {action}. Valid: list, enable_platform, create, delete, toggle"})


# ---------------------------------------------------------------------------
# Low-level server（供雙 transport wrapper 掛 SSE + StreamableHTTP）
# ---------------------------------------------------------------------------

# core 的 DualTransportApp 需要底層 low-level ``Server``（用 StreamableHTTPSessionManager
# 與 ``server.run`` 的 API），FastMCP 內部即持有一個。以 module-level 名稱 ``server``
# 暴露，對齊 odoo 的 ``mcp_server_odoo.server:server`` 命名，供 launcher 掛雙 transport。
server = mcp._mcp_server
