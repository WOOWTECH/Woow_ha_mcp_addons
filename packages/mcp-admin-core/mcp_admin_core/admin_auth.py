"""Shared HA Ingress identity, CSRF and fresh administrator-role checks."""
import asyncio
import hashlib
import hmac
import re
import secrets

from .ha_role import Unreviewed, valid_user_id

class BadRequest(Exception):
    def __init__(self, status=400, detail=None):
        self.status = status
        # Fixed reviewed codes, public operation receipts, or a validated Core
        # version only. Never include credentials or raw exception messages.
        self.detail = detail


def denial_detail(allowed):
    """The one refusal an administrator can act on: HA Core advertised a version this release has not reviewed."""
    if isinstance(allowed, Unreviewed):
        return {"code": "core_version_unreviewed", "ha_version": allowed.ha_version}
    return None


def prefix(request):
    values = request.headers.getlist("x-ingress-path")
    if len(values) > 1:
        raise BadRequest()
    value = values[0] if values else ""
    if value and (not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)+", value) or len(value) > 512):
        raise BadRequest()
    return value


class AdminAuthority:
    def __init__(self, verifier):
        self.verifier = verifier
        self.csrf_key = secrets.token_bytes(32)

    def identity(self, request):
        # Both normal and pre-upgrade Uvicorn listeners disable proxy_headers.
        if not request.client or request.client.host != "172.30.32.2" or self.verifier is None:
            raise BadRequest(403)
        identities = request.headers.getlist("x-remote-user-id")
        if len(identities) != 1 or not valid_user_id(identities[0]):
            raise BadRequest(403)
        user = identities[0]
        base = prefix(request)
        csrf = hmac.new(self.csrf_key, (user + "\0" + base).encode(), hashlib.sha256).hexdigest()
        if request.method not in ("GET", "HEAD"):
            values = request.headers.getlist("x-csrf-token")
            if len(values) != 1 or not hmac.compare_digest(values[0].encode(), csrf.encode()):
                raise BadRequest(403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                raise BadRequest(403)
        return user, base, csrf

    async def verify(self, user):
        try:
            async with asyncio.timeout(3):
                allowed = await self.verifier(user)
        except Exception:
            allowed = False
        if allowed is not True:
            raise BadRequest(403, detail=denial_detail(allowed))
