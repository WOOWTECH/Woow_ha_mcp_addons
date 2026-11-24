"""由產品明確啟用的 MCP 輸入界線；在驗證 token 後、轉發／SDK 驗證前執行。

HM-31（多帳號計畫 §12.3；契約第 2.4 節；PaaS #155，woow-mcp-server d7f5849 request_limits.py、request_body.py）：每個產品的
JSON 結構守門（structure_violation：深度與元素個數，在 json.loads 之前、只掃描不建立物件）與 UTF-16／32 拒收（not_utf8），
不受開關管（契約第 1.2 節）。n8n 的 McpRequestLimits.parse_and_check 先跑同一道守門；其他產品由 gateway 的 json_body 跑
（gateway.STRUCTURE_LIMITS）。拒收的回應照 PaaS：認得出請求 id 就 200＋該 id 的 -32602，否則 413（too_complex）。
"""
from __future__ import annotations

import codecs
from dataclasses import dataclass
import json
import re
from typing import Any

from starlette.requests import Request


#: 結構守門的預設上限（PaaS d7f5849 DEFAULT_MAX_TOTAL_ELEMENTS、DEFAULT_MAX_DEPTH）。元素個數＝逗號數＋容器（``[``、``{``）數
#: （字串內的不算）。16 MiB 的 ``[[],[],…]``、``[{},{},…]`` 解析後多出約 390 MiB（24 倍），純字串只有 1 倍；20 萬個元素的上限讓
#: 結構造成的放大有界。Odoo ``execute_method`` 批次 create 3,000 筆 × 30 欄位約 93,000 個元素；Nextcloud 13.3 MiB 的 base64
#: 檔案是單一字串，元素數 0。
DEFAULT_MAX_TOTAL_ELEMENTS = 200_000
DEFAULT_MAX_DEPTH = 64

# Remove complete JSON strings in C before the Python structural loop. The
# possessive repeat keeps an unterminated long string from backtracking.
_COMPLETE_STRING = re.compile(rb'"(?:[^"\\]|\\.)*+"', re.DOTALL)
# Keep only structural bytes outside strings. Removing other bytes in C avoids
# creating one Python match object for each of ~200,000 tiny JSON elements.
_STRUCTURE_BYTES = bytes.maketrans(bytes(range(256)),
                                   bytes(char if char in b'[]{},' else 0 for char in range(256)))
_EARLY_STRUCTURE_WINDOW = 4096
_COMMA = ord(",")
#: 檢查「整段是合法 UTF-8」時每次解碼的區塊大小：不把整份內容解成 str（astral 字元會讓 str 變成 4 倍），暫存只有區塊大小。
_UTF8_CHUNK = 1024 * 1024
NOT_UTF8_REASON = "the body is not UTF-8 text (UTF-16 and UTF-32 are not accepted)"
#: 沒解析的請求只看頭尾各這麼多位元組找 id（PaaS request_body._WINDOW；request_budget.ID_WINDOW 同值）。
ID_WINDOW = 4096


def not_utf8(body: bytes) -> bool:
    """body 不是 UTF-8 就回 True（PaaS 第三輪 P1-A）。``json.loads(bytes)`` 依 RFC 4627 看前 4 個位元組有沒有 NUL（或 BOM）
    自動改用 UTF-16／32 解碼；結構掃描卻逐位元組當 UTF-8 掃，UTF-16 的 ``"`` 是 ``00 22``，引號奇偶全亂。所以掃描之前先拒收：
    前 4 個位元組含 NUL，或整段不是合法 UTF-8（所有 BOM：``ff fe``、``fe ff`` 都不是合法 UTF-8）。合法的 UTF-8（中文、日文、
    emoji、UTF-8 BOM）一律放行：純 ASCII 用 ``isascii()``；其餘以增量解碼器每次一個區塊驗證（線性、暫存常數）。"""
    if b"\x00" in body[:4]:
        return True
    if body.isascii():
        return False
    decoder = codecs.getincrementaldecoder("utf-8")()
    view = memoryview(body)
    try:
        for start in range(0, len(body), _UTF8_CHUNK):
            decoder.decode(view[start:start + _UTF8_CHUNK])
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return True
    return False


def _scan_structure(data: bytes, max_depth: int, max_elements: int) -> str | None:
    outside_strings = _COMPLETE_STRING.sub(b'', data)
    # The original scanner still counted structure before an unterminated
    # string. Stop at its opening quote, but retain any earlier violation.
    outside_strings = outside_strings.split(b'"', 1)[0]
    structural = outside_strings.translate(_STRUCTURE_BYTES).replace(b'\x00', b'')
    # Collapse balanced empty pairs in C before walking structural bytes in
    # Python. A near-limit body can have ~100,000 flat objects; the Python
    # walk otherwise holds the GIL for every bracket and comma. Removing commas
    # does not change nesting, and a sequence reduced to empty within
    # max_depth passes is balanced and cannot exceed that depth. Count the
    # original structural bytes so the element limit stays exact. Malformed or
    # deeper sequences still take the original ordered scanner below. Each
    # replacement pass removes at most one nesting level: replacing [] and {}
    # in the same pass could remove two nested levels and bypass max_depth.
    elements_total = structural.count(_COMMA) + structural.count(ord('[')) + structural.count(ord('{'))
    brackets = structural.replace(b',', b'')
    if not brackets:
        return f"more than {max_elements} JSON elements" if elements_total > max_elements else None
    unchanged_passes = 0
    for step in range(max_depth):
        collapsed = brackets.replace(b'[]' if step % 2 == 0 else b'{}', b'')
        if not collapsed:
            return f"more than {max_elements} JSON elements" if elements_total > max_elements else None
        unchanged_passes = unchanged_passes + 1 if len(collapsed) == len(brackets) else 0
        if unchanged_passes == 2:
            break
        brackets = collapsed
    depth = elements = 0
    for char in structural:
        if char == _COMMA:
            elements += 1
        elif char == ord('[') or char == ord('{'):
            elements += 1
            depth += 1
            if depth > max_depth:
                return f"more than {max_depth} levels of nesting"
        else:
            depth -= 1
            if depth < 0:
                return None  # 閉括號比開括號多：不是合法 JSON；繼續掃只會被灌閉括號拖慢
        if elements > max_elements:
            return f"more than {max_elements} JSON elements"
    return None


def structure_violation(body: bytes, *, max_depth: int, max_elements: int) -> str | None:
    """body（JSON 原始位元組）的容器巢狀深度或元素個數超過上限就回原因（英文短句，不含內容），否則 None（PaaS d7f5849）。

    The short prefix scan returns an already certain violation before copying a large
    malformed body. A later closing bracket or string cannot undo an earlier limit.
    The complete scan still counts only structure outside strings and retains the
    original early stop on an unmatched quote or excess closing bracket.
    """
    if not_utf8(body):
        return NOT_UTF8_REASON
    if len(body) > _EARLY_STRUCTURE_WINDOW:
        early = _scan_structure(body[:_EARLY_STRUCTURE_WINDOW], max_depth, max_elements)
        if early is not None:
            return early
    openers = body.count(b"[") + body.count(b"{")
    if openers + body.count(b",") <= max_elements and openers <= max_depth:
        return None
    return _scan_structure(body, max_depth, max_elements)


# 沒解析的請求只看頭尾找 id（PaaS request_body._request_id；只認整個 JSON 物件最外層的兩種寫法，不撿參數裡的 "id"）。
_ID = rb'(-?[0-9]{1,19}|"(?:[^"\\\x00-\x1f]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4}){0,256}")'
_HEAD_METHOD = re.compile(rb'\s*\{\s*"method"\s*:\s*"')
_HEAD_ID = re.compile(rb'\s*\{\s*"jsonrpc"\s*:\s*"2\.0"\s*,\s*"id"\s*:\s*' + _ID + rb'\s*,\s*"method"\s*:')
_TAIL_ID = re.compile(rb'[{,]\s*"jsonrpc"\s*:\s*"2\.0"\s*,\s*"id"\s*:\s*' + _ID + rb'\s*\}\s*\Z')


def head_tail_id(head: bytes, tail: bytes = b""):
    """沒讀完（或沒解析）的單一請求的 id：MCP SDK 的 ``{"method":…,"jsonrpc":"2.0","id":…}`` 從結尾找，
    ``{"jsonrpc":"2.0","id":…,"method":…}`` 從開頭找；認不出來（batch、通知、其他寫法）回 None。只回字串或整數。"""
    match = _HEAD_ID.match(head)
    if match is None and _HEAD_METHOD.match(head):
        match = _TAIL_ID.search(tail)
    if match is None:
        return None
    try:
        value = json.loads(match.group(1))
    except ValueError:
        return None
    return value if type(value) in (str, int) else None


class RequestLimitError(Exception):
    """可直接回傳且不含輸入內容的 HTTP／JSON-RPC 錯誤。"""

    def __init__(self, message: str, *, status: int = 413, code: int = -32602, rpc_id=None, kind: str = "rejected",
                 log_reason: str | None = None):
        """保留已解析的請求 ID，讀取／解析前的拒絕使用 null。HM-31：``kind``、``log_reason`` 只給閘道的節流 WARNING 用
        （情況名稱與不含請求內容的短原因；PaaS P2-D）。"""
        self.status = status
        self.kind = kind
        self.log_reason = log_reason or message
        self.payload = {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}
        super().__init__(message)


def too_complex(body: bytes, reason: str) -> RequestLimitError:
    """拒收結構過深、元素過多或不是 UTF-8 的請求（PaaS request_body.too_complex，d7f5849）：認得出 id（頭尾）就 200＋帶該
    id 的 -32602（MCP SDK 對非 2xx 會讓整個 session 失敗，這樣只有這次呼叫失敗），否則 413、id null。訊息只含上限與處理方式，
    不含內容；編碼不是 UTF-8 用編碼專用的訊息。"""
    if reason == NOT_UTF8_REASON:
        message = ("MCP request body was refused because it is not UTF-8 text (UTF-16 and UTF-32 are not accepted) and "
                   "was not processed. Send the request as UTF-8. (MCP 請求內容不是 UTF-8 文字（不接受 UTF-16、UTF-32），"
                   "未處理；請改用 UTF-8 傳送。)")
    else:
        message = (f"MCP request body was refused because its JSON structure is too complex ({reason}) and was not "
                   "processed. Send fewer or flatter items per call: split the work into several calls, and send file "
                   "contents as one string. (MCP 請求內容的 JSON 結構過於複雜，未處理；請減少每次呼叫的項目數或巢狀層數，"
                   "拆成多次呼叫，檔案內容請以單一字串傳送。)")
    ident = head_tail_id(body[:ID_WINDOW], body[-ID_WINDOW:])
    return RequestLimitError(message, status=413 if ident is None else 200, code=-32602, rpc_id=ident,
                             kind="encoding" if reason == NOT_UTF8_REASON else "structure", log_reason=reason)


@dataclass(frozen=True)
class McpRequestLimits:
    """每個 app 固定啟用的請求位元組、工具參數元素與深度上限；HM-31 起另有整個請求的元素個數上限（結構守門）。"""
    max_bytes: int
    max_argument_elements: int
    max_depth: int = DEFAULT_MAX_DEPTH
    #: 整個請求（不只工具參數）的元素個數上限，見 :data:`DEFAULT_MAX_TOTAL_ELEMENTS`、:func:`structure_violation`。
    max_total_elements: int = DEFAULT_MAX_TOTAL_ELEMENTS

    def structure_reason(self, body: bytes) -> str | None:
        """整個請求的容器深度或元素個數（見 :func:`structure_violation`）超過上限的原因，沒超過回 None。"""
        return structure_violation(body, max_depth=self.max_depth, max_elements=self.max_total_elements)

    def check_structure(self, body: bytes) -> None:
        """同 :meth:`structure_reason`，超過就拋 :func:`too_complex`（不含內容）。"""
        reason = self.structure_reason(body)
        if reason is not None:
            raise too_complex(body, reason)

    def _check_depth(self, value: str | bytes) -> None:
        """在建立 JSON 物件前，忽略字串內容計算容器巢狀深度。"""
        # 在 json.loads 建立物件前先掃描結構；字串中的括號、跳脫引號不計入深度。
        text = value.decode("utf-8") if isinstance(value, bytes) else value
        depth = 0
        in_string = escaped = False
        for char in text:
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char in "[{":
                depth += 1
                if depth > self.max_depth:
                    raise RequestLimitError(f"MCP JSON exceeds {self.max_depth} levels of nesting")
            elif char in "]}":
                depth -= 1

    async def read_body(self, request: Request) -> bytes:
        """同時限制宣告與實際大小，超限時不再讀取後續分塊。"""
        # 轉發壓縮內容會讓上游解壓後繞過這裡的位元組界線。
        if request.headers.get("content-encoding", "identity").lower() != "identity":
            raise RequestLimitError("Compressed MCP requests are not supported", status=415)
        length = request.headers.get("content-length")
        if length is not None:
            try:
                size = int(length)
                if size < 0:
                    raise ValueError
            except ValueError:
                raise RequestLimitError("Invalid Content-Length", status=400, code=-32600)
            if size > self.max_bytes:
                raise RequestLimitError(f"MCP request exceeds {self.max_bytes} bytes")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > self.max_bytes:
                raise RequestLimitError(f"MCP request exceeds {self.max_bytes} bytes")
            body.extend(chunk)
        return bytes(body)

    def parse_and_check(self, body: bytes) -> Any:
        """以迭代器計算 batch 共用預算；回傳未修改的原始訊息。"""
        if not body:
            return None
        self.check_structure(body)  # HM-31：先於 _check_depth：不是 UTF-8 的內容不能進後面的解碼與解析
        try:
            self._check_depth(body)
            rpc = json.loads(body)
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise RequestLimitError("Invalid or excessively nested JSON", status=400, code=-32700)
        messages = rpc if isinstance(rpc, list) else [rpc]
        remaining = self.max_argument_elements
        # n8n 會把部分字串參數 JSON.parse 後當結構使用，預算也涵蓋這些解碼後的結構。
        decoded_bytes = 0
        for message in messages:
            if not isinstance(message, dict) or message.get("method") != "tools/call":
                continue
            params = message.get("params")
            if not isinstance(params, dict):
                continue
            stack = [iter((params.get("arguments"),))]
            while stack:
                try:
                    value = next(stack[-1])
                except StopIteration:
                    stack.pop()
                    continue
                if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
                    decoded_bytes += len(value.encode("utf-8", errors="surrogatepass"))
                    if decoded_bytes > self.max_bytes:
                        raise RequestLimitError("Encoded MCP arguments exceed decoding budget", rpc_id=message.get("id"))
                    try:
                        self._check_depth(value)
                        value = json.loads(value)
                    except RequestLimitError as error:
                        raise RequestLimitError(
                            error.payload["error"]["message"],
                            status=error.status,
                            code=error.payload["error"]["code"],
                            rpc_id=message.get("id"),
                        ) from None
                    except RecursionError:
                        raise RequestLimitError("Excessively nested MCP arguments", rpc_id=message.get("id"))
                    except ValueError:
                        continue
                if isinstance(value, (dict, list)):
                    if len(stack) > self.max_depth:
                        raise RequestLimitError("Excessively nested MCP arguments", rpc_id=message.get("id"))
                    remaining -= len(value)
                    if remaining < 0:
                        raise RequestLimitError(
                            f"MCP tool arguments exceed {self.max_argument_elements} elements",
                            rpc_id=message.get("id"),
                        )
                    stack.append(iter(value.values() if isinstance(value, dict) else value))
        return rpc
