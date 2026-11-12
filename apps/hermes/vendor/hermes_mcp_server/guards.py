"""Hermes MCP 的輸入守衛：拼進網址的 id、設定寫入的 deny-list、MCP server 網址。

MCP 工具（server.py）與管理後台的 dashboard 直通（hermes_mcp_admin/routers/dashboard_proxy.py）共用同一套規則。
商用驗收 QA 服務 249 實測（2026-10-16）的四個缺口：

- AI-HMCP-001-1：session_id／job_id／name 用 f-string 拼進 dashboard 網址。httpx 送出前會把 ``..`` 正規化掉，
  ``session_id="../config/raw"`` 實際打到 ``GET /api/config/raw``，讀出含 provider api_key 明文的 yaml。
  → ``path_segment()``：白名單＋拒絕 ``..``，再 ``quote(safe="")``。
- AI-HMCP-001-3：deny-list 只做字串全等，``terminal``（父鍵整棵換成純量）、大小寫、空白、全形、零寬字元都繞得過。
  → ``config_key_denial()``：先正規化（NFKC、去除格式字元、strip、casefold、拆段），再比對前綴與祖先。
- AI-HMCP-002-2：``hermes_mcp add`` 只擋小寫 ``stdio:``／``command:`` 前綴；後台直通可新增 stdio command。
  → ``check_mcp_server_url()``／``check_mcp_server_body()``：只收 http／https，並套用 SSRF 檢查。
"""

from __future__ import annotations

import ipaddress
import re
import socket
import unicodedata
from typing import Any
from urllib.parse import quote, urlsplit

from backend_policy import Destination, resolve_async, connection_deadline


class GuardError(ValueError):
    """輸入被安全規則拒絕。ValueError：MCP 工具回 isError=true（文字由 server.py 的 keep_error_text 保留），後台轉成 HTTP 400。"""


# ---------------------------------------------------------------------------
# 拼進網址的 id／name（AI-HMCP-001-1）
# ---------------------------------------------------------------------------

# Hermes 的 id 實際長相：session 20261016_193839_d56dfbc7、UUID、qa1011-hermes-g56-import-01；cron job 12 位 hex；
# webhook／toolset／MCP server 名稱。只收字母數字（含 Unicode）與 _ . - : @ + ~，中間可以有單一空白。
# 沒有 / \ ? # %，所以一個值永遠只佔一段路徑；再拒絕含 ".." 與單一 "."（httpx 會把這兩種段落正規化掉）。
_SEGMENT = re.compile(r"[\w.:@+~-]+(?: [\w.:@+~-]+)*")
MAX_SEGMENT = 200


def path_segment(value: Any, field: str) -> str:
    """回傳可以安全拼進 dashboard 網址的單一路徑段（已百分比編碼）；不合格丟 GuardError。"""
    if not isinstance(value, str) or not value:
        raise GuardError(f"{field} is required")
    if len(value) > MAX_SEGMENT or value == "." or ".." in value or not _SEGMENT.fullmatch(value):
        raise GuardError(
            f"invalid {field}: only letters, digits, spaces and _ . - : @ + ~ are allowed, "
            f"without '..' or '/'"
        )
    return quote(value, safe="")


# ---------------------------------------------------------------------------
# 設定寫入的 deny-list（AI-HMCP-001-3）
# ---------------------------------------------------------------------------

# 根鍵：本身與底下任何鍵都不能經 MCP 寫入（舊清單的 terminal.backend、api_server.host、dashboard.basic_auth、
# secrets 都含在內）。model 與 MCP server 有專用工具（hermes_model、hermes_mcp），不開放用 hermes_config 繞過驗證；
# security 是指令安全掃描設定；providers／custom_providers 決定模型流量送去哪裡、帶什麼金鑰。
DENIED_CONFIG_KEYS = frozenset({
    "api_server",
    "custom_providers",
    "dashboard",
    "mcp_servers",
    "model",
    "providers",
    "secrets",
    "security",
    "terminal",
})

# 正規化後每一段只能是這些字元；空段（a..b、.a、a.）、括號索引（a[0]）、空白都不收。
_KEY_SEGMENT = re.compile(r"[a-z0-9_-]+")


def normalize_config_key(key: str) -> str:
    """比對用：NFKC（全形→半形）、去掉格式字元（零寬空白、soft hyphen）、strip、casefold。"""
    return _normalized_key_spelling(key).casefold()


def _normalized_key_spelling(key: str) -> str:
    # Keep camel-case boundaries for the credential-name detector.
    text = unicodedata.normalize("NFKC", key)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf").strip()


def config_key_denial(key: Any, secret_key: Any = None) -> str | None:
    """回傳拒絕原因；可以寫入時回 None。``secret_key(name)`` 為 True 的段落也拒絕（不經 MCP 寫憑證）。"""
    if not isinstance(key, str) or not key.strip():
        return "key is required"
    parts = normalize_config_key(key).split(".")
    if not all(_KEY_SEGMENT.fullmatch(part) for part in parts):
        return "key must be dot-separated segments of letters, digits, '_' or '-'"
    if parts[0].startswith("_"):
        return "internal keys (leading '_') cannot be written"
    for denied in DENIED_CONFIG_KEYS:
        d_parts = denied.split(".")
        # 本身或子鍵（terminal.backend）被擋；祖先（寫父鍵會把整棵子樹換掉）也被擋。
        if parts[: len(d_parts)] == d_parts or d_parts[: len(parts)] == parts:
            return f"'{denied}' and the keys under it cannot be changed through MCP"
    if secret_key is not None and any(secret_key(part) for part in _normalized_key_spelling(key).split(".")):
        return "credential keys cannot be changed through MCP"
    return None


def config_value_denial(key: str, value: Any, secret_key: Any = None) -> str | None:
    """Apply the same path policy to every descendant, including objects in lists."""
    denial = config_key_denial(key, secret_key)
    if denial:
        return denial
    if isinstance(value, dict):
        for child, item in value.items():
            denial = config_value_denial(f"{key}.{child}", item, secret_key)
            if denial:
                return denial
    elif isinstance(value, list):
        for item in value:
            denial = config_value_denial(key, item, secret_key)
            if denial:
                return denial
    return None


def config_patch_applied(requested: Any, actual: Any) -> bool:
    """Hermes deep-merges objects; untouched siblings are not failed writes."""
    if isinstance(requested, dict):
        return isinstance(actual, dict) and all(
            key in actual and config_patch_applied(value, actual[key])
            for key, value in requested.items()
        )
    # Arrays and scalar values are replaced, rather than merged.
    return _exact_config_value(requested, actual)


def _exact_config_value(requested: Any, actual: Any) -> bool:
    if type(actual) is not type(requested):
        return False
    if isinstance(requested, dict):
        return requested.keys() == actual.keys() and all(
            _exact_config_value(value, actual[key]) for key, value in requested.items()
        )
    if isinstance(requested, list):
        return len(requested) == len(actual) and all(
            _exact_config_value(value, observed) for value, observed in zip(requested, actual)
        )
    return actual == requested


def clean_config_key(key: str) -> str:
    """實際送給 Hermes 的鍵：NFKC＋strip（大小寫保留）。只在 config_key_denial() 回 None 之後使用。"""
    return unicodedata.normalize("NFKC", key).strip()


# ---------------------------------------------------------------------------
# MCP server 網址（AI-HMCP-002-2）
# ---------------------------------------------------------------------------

# 只有 stdio transport 會用到的欄位：帶了就代表要 Hermes spawn 本機程式。
STDIO_FIELDS = ("command", "args", "env", "cwd")


# One wording for a loopback MCP server URL on PaaS and the HA add-on (PaaS maps its SSRF module's loopback verdict
# to the same sentence).
LOOPBACK_MCP_URL_MESSAGE = "loopback MCP servers (localhost, 127.0.0.0/8, ::1) cannot be added"

# AI-HMCP-002-2 (loopback, restored in 0.3.4): Hermes connects to a registered MCP server from its own host, so a
# loopback URL reaches whatever listens only there (Hermes itself, its dashboard or API server). backend_policy permits
# loopback for the add-on's own configured backends; registration refuses it here, by name and by every resolved address.
LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain"})


def _loopback_name(host: str) -> bool:
    name = host.rstrip(".").lower()
    return name in LOOPBACK_NAMES or name.endswith(".localhost")


def _loopback_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    return ip.is_loopback or (mapped is not None and mapped.is_loopback)


# A cloud-metadata destination reads like the PaaS answer (H7, found by the 2026-11-05 live comparison). The PaaS check
# (util/ssrf.py) refuses a metadata host name or address before it looks at anything else, with "url blocked by SSRF
# protection: Cloud metadata endpoint blocked"; backend_policy refuses the same destinations with the generic
# BACKEND_DESTINATION_DENIED. CLOUD_METADATA is the PaaS list as it is. Two of its entries, fd20:ce::254 and
# fd00:a9fe:a9fe::1, are unique-local (LAN) addresses that backend_policy lets through, so registration refuses them
# here for the first time. Every other class backend_policy refuses (link-local, CGNAT, 0.0.0.0, userinfo) keeps its
# code and text, and so does a host name that only RESOLVES to a metadata address: the resolver reports a refused answer
# set, not the refused address. PaaS words a number form that a resolver turns into a metadata address (2852039166,
# 0xa9fea9fe) one level up, "Hostname resolves to a blocked address (...)", because it reaches the verdict only after
# resolving; so does this check. A trailing dot is ignored, as backend_policy does for its own metadata names.
CLOUD_METADATA = frozenset({
    "169.254.169.254", "169.254.170.2", "metadata.google.internal", "metadata", "100.100.100.200", "192.0.0.192",
    "fd00:ec2::254", "fd20:ce::254", "fe80::a9fe:a9fe", "fd00:a9fe:a9fe::1",
})
CLOUD_METADATA_REASON = "Cloud metadata endpoint blocked"
# A number, or dotted numbers, in decimal, octal or hex: a resolver reads it as an IPv4 address (2852039166, 0xa9fea9fe
# and 169.254.43518 are all 169.254.169.254).
_IPV4_NUMBER = re.compile(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)(?:\.(?:0[xX][0-9a-fA-F]+|[0-9]+)){0,3}")


def _ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return None


def _ipv4_number(host: str) -> ipaddress.IPv4Address | None:
    if not _IPV4_NUMBER.fullmatch(host):
        return None
    try:
        return ipaddress.IPv4Address(socket.inet_aton(host))
    except OSError:
        return None


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """The IPv4 address an IPv6 address carries: compatible (::a.b.c.d), mapped (::ffff:a.b.c.d), translated
    (::ffff:0:a.b.c.d), NAT64 (64:ff9b::/96 and 64:ff9b:1::/48 with a zero middle), 6to4 (2002::/16) and Teredo
    (2001:0::/32, client address inverted): the forms the PaaS check follows from n8n-mcp's tryExtractTunneledIPv4."""
    p = [int.from_bytes(ip.packed[i:i + 2], "big") for i in range(0, 16, 2)]
    if p[0] == p[1] == p[2] == p[3] == 0 and ((p[4] == 0 and p[5] in (0, 0xFFFF)) or (p[4] == 0xFFFF and p[5] == 0)):
        return ipaddress.IPv4Address((p[6] << 16) | p[7])
    if p[0] == 0x64 and p[1] == 0xFF9B and p[3] == p[4] == p[5] == 0 and p[2] in (0, 1):
        return ipaddress.IPv4Address((p[6] << 16) | p[7])
    if p[0] == 0x2002:
        return ipaddress.IPv4Address((p[1] << 16) | p[2])
    if p[0] == 0x2001 and p[1] == 0:
        return ipaddress.IPv4Address(((p[6] ^ 0xFFFF) << 16) | (p[7] ^ 0xFFFF))
    return None


def _metadata_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    embedded = _embedded_ipv4(ip) if isinstance(ip, ipaddress.IPv6Address) else None
    return str(ip) in CLOUD_METADATA or (embedded is not None and str(embedded) in CLOUD_METADATA)


def _cloud_metadata_reason(host: str) -> str | None:
    """The PaaS reason when the URL's host is a metadata name or spells a metadata address, else None. No DNS."""
    name = host.rstrip(".").lower()
    if name in CLOUD_METADATA:
        return CLOUD_METADATA_REASON
    literal = _ip_literal(name)
    if literal is not None:
        return CLOUD_METADATA_REASON if _metadata_address(literal) else None
    number = _ipv4_number(name)
    if number is not None and _metadata_address(number):
        return f"Hostname resolves to a blocked address ({CLOUD_METADATA_REASON})"
    return None


async def check_mcp_server_url(url: Any) -> str:
    """回傳 strip 過的網址；不是 http／https、帶帳密，或指向 loopback／metadata 就丟 GuardError；HA 允許區網服務。"""
    if not isinstance(url, str) or not url.strip():
        raise GuardError("url is required")
    url = url.strip()
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise GuardError("invalid url") from exc
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise GuardError("only http:// or https:// MCP servers can be added (stdio/command transports are blocked)")
    if (reason := _cloud_metadata_reason(parts.hostname)) is not None:
        raise GuardError(f"url blocked by SSRF protection: {reason}")
    # Registration validates the destination now. Hermes owns future connections;
    # its DNS resolution cannot be pinned by this add-on's HTTP client.
    destination = Destination(url)
    if _loopback_name(destination.host):
        raise GuardError(LOOPBACK_MCP_URL_MESSAGE)
    answers = await resolve_async(destination.host, destination.port, connection_deadline(5.0))
    if any(_loopback_address(address[0]) for _, address in answers):
        raise GuardError(LOOPBACK_MCP_URL_MESSAGE)
    return url


async def check_mcp_server_body(body: Any) -> dict[str, Any]:
    """後台直通 POST /api/mcp/servers 的 payload：拒絕 stdio、command 類欄位與不合格網址。"""
    if not isinstance(body, dict):
        raise GuardError("body must be a JSON object")
    for field in ("transport", "type"):
        value = body.get(field)
        if value is not None and (not isinstance(value, str) or value.strip().casefold() == "stdio"):
            raise GuardError("stdio transport is blocked for security")
    present = [field for field in STDIO_FIELDS if body.get(field) not in (None, "", [], {})]
    if present:
        raise GuardError(f"stdio transport is blocked for security ({', '.join(present)} not allowed)")
    path_segment(body.get("name"), "name")
    return {**body, "url": await check_mcp_server_url(body.get("url"))}
