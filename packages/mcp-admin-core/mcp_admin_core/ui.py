"""Fixed, self-hosted management build. No fixture or configurable document root."""
import html
from pathlib import Path
import os
import re
import stat

from starlette.responses import Response

UI_ROOT = Path(__file__).resolve().parents[2] / "mcp-admin-ui" / "dist"
HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'",
}
PAGES = {"/", "/overview", "/backend", "/tools", "/access", "/diagnostics"}
TYPES = {".js": "text/javascript", ".css": "text/css", ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".eot": "application/vnd.ms-fontobject", ".txt": "text/plain"}


def response(path, base, *, entrypoint="app"):
    if entrypoint not in ("app", "upgrade"):
        raise ValueError("unknown UI entrypoint")
    page = path in PAGES
    relative = "index.html" if page else path.lstrip("/")
    if not page and (not path.startswith(("/assets/", "/licenses/")) or
                     not re.fullmatch(r"(?:[A-Za-z0-9_-]+/)+[A-Za-z0-9_.-]+", relative) or
                     any(p in (".", "..") for p in relative.split("/")) or
                     Path(relative).suffix not in TYPES):
        return Response(status_code=404)
    # Walk directory descriptors: no symlink, including the dist root. No open of
    # arbitrary data paths, and no FileResponse reopen race after authorization.
    fds = []
    try:
        fd = os.open(UI_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(fd)
        parts = relative.split("/")
        for part in parts[:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            fds.append(fd)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        fds.append(fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 8 * 1024 * 1024:
            return Response(status_code=503)
        with os.fdopen(os.dup(fd), "rb") as stream:
            content = stream.read(8 * 1024 * 1024 + 1)
        if len(content) > 8 * 1024 * 1024:
            return Response(status_code=503)
        if page:
            content = content.decode("utf-8")
            if "__MCP_UI_BASE__" not in content:
                return Response(status_code=503)
            if entrypoint == "upgrade":
                content = content.replace("/assets/app.js", "/assets/upgrade.js")
            content = content.replace("__MCP_UI_BASE__", base)
        return Response(content, media_type="text/html" if page else TYPES[Path(relative).suffix])
    except (OSError, UnicodeError):
        return Response(status_code=503 if page else 404)
    finally:
        for fd in reversed(fds):
            os.close(fd)


def unreviewed_core_page(version):
    """The panel page while HA Core advertises a version this release has not reviewed (ha_role.Unreviewed).

    Static text only: no script, style, link or form, so it renders under the panel CSP without any asset (every asset
    is behind the same role check). version is ha_role.shown_version's validated form or None; it is escaped anyway."""
    if version:
        heading = "這個 HA Core 版本尚未審核：" + html.escape(version)
    else:
        heading = "這個 HA Core 版本尚未審核（Supervisor 回報的版本字串無法辨識）"
    lines = (
        "這版 add-on 的管理面板只在審查過的 Home Assistant Core 版本上確認管理員身分。這個 Core 版本還沒有審查，"
        "所以管理面板暫時不能使用，也不能變更任何設定。",
        "MCP 端點（Bearer 權杖或 Claude.ai 連線網址）不經過這項檢查，照常服務。",
        "請更新到支援這個 Core 版本的 add-on 版本；add-on 紀錄裡有同一行說明。",
    )
    page = ('<!doctype html>\n<html lang="zh-Hant">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n<meta name="referrer" content="no-referrer">\n'
            f'<title>Woow MCP · {heading}</title>\n</head>\n<body>\n<main>\n<h1>{heading}</h1>\n'
            + ''.join(f'<p>{html.escape(line)}</p>\n' for line in lines) + '</main>\n</body>\n</html>\n')
    return Response(page, status_code=403, media_type="text/html")


class SecurityHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def secured(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.decode().lower() not in {h.lower() for h in HEADERS}]
                message["headers"] = headers + [(k.lower().encode(), v.encode()) for k, v in HEADERS.items()]
            await send(message)
        await self.app(scope, receive, secured)
