"""Patch odoo-mcp-server to allow direct create/write/unlink via execute_method.

Problem
-------
The upstream ``execute_method`` tool unconditionally blocks ``create``,
``write``, and ``unlink`` calls, forcing a three-step approval flow
(``preview_write`` -> ``validate_write`` -> ``execute_approved_write``).

Claude.ai frequently drops write-approval tokens across sessions, making
this three-step flow unreliable in practice.

Fix
---
When the environment variable ``ODOO_MCP_ALLOW_DIRECT_WRITES`` is set to
``1`` (or ``true`` / ``yes``), the ``DESTRUCTIVE_METHODS`` guard in
``execute_method`` is bypassed, allowing direct ORM calls.

This patch is **opt-in** and safe to apply unconditionally — the guard is
only lifted when the env var is explicitly set.

Usage
-----
Run once after ``pip install odoo-mcp-server``::

    python patches/fix_direct_writes.py

The script is idempotent — re-running it on an already-patched file is safe.

WOOW HA add-on (0.4.0, odoo-mcp 1.3.0)
--------------------------------------
The add-on always starts the child with ``ODOO_MCP_ALLOW_DIRECT_WRITES=1`` and ``MCP_CHATTER_DIRECT=1``
(``mcp_admin_core.products.child_spec``), but odoo-mcp 1.3.0 tells the model the opposite: the ``method`` parameter
of ``execute_method`` says "direct create, write, and unlink are blocked", and ``chatter_post`` says its default mode
needs an approval token from a preview call. A model then falls back to the three-step approval flow, or expects a
preview from ``chatter_post`` that never comes (it posts at once). This HA copy therefore also makes both descriptions
follow the same switches the code reads (the guard below and ``write_policy.chatter_direct_enabled``): switch on, the
text says the call runs directly; switch off, it is upstream's text. The description is computed when the tool is
registered, from the child's fixed environment. The WOOW PaaS keeps the original patch: there the switch defaults to
off and upstream's text is accurate.

Exact digests (0.4.0): the patch accepts only the published odoo-mcp 1.3.0 ``tools_write.py`` (PINNED) and writes
exactly PATCHED, the digest ``apps/odoo/launch.py`` checks; an already patched file is left as it is and any other
content is refused (exit 1).
"""

from __future__ import annotations

import glob
import hashlib
import os
import sys

MARKER = "ODOO_MCP_ALLOW_DIRECT_WRITES"

OLD_BLOCK = (
    '        if method in DESTRUCTIVE_METHODS:\n'
    '            return {\n'
    '                "success": False,\n'
    '                "error": (\n'
    '                    "Direct execute_method blocks create/write/unlink. Use "\n'
    '                    "preview_write -> validate_write -> execute_approved_write."\n'
    '                ),\n'
    '            }'
)

NEW_BLOCK = (
    '        if method in DESTRUCTIVE_METHODS:\n'
    '            # PATCH(woowtech): allow direct writes when opt-in env var is set.\n'
    '            if not os.environ.get("ODOO_MCP_ALLOW_DIRECT_WRITES", "").strip().lower() in ("1", "true", "yes"):\n'
    '                return {\n'
    '                    "success": False,\n'
    '                    "error": (\n'
    '                        "Direct execute_method blocks create/write/unlink. Use "\n'
    '                        "preview_write -> validate_write -> execute_approved_write, "\n'
    '                        "or set ODOO_MCP_ALLOW_DIRECT_WRITES=1."\n'
    '                    ),\n'
    '                }'
)


PINNED = "d02045c6c268c664f4f58036c7cf1862e7fcb602ec84d9f43630e7bf7b1e749b"  # odoo-mcp 1.3.0 tools_write.py as published
PATCHED = "353fbc5a11497a1b969105d3d58760b8df376df86d30008c875c83477efcad93"  # the digest apps/odoo/launch.py checks

# The direct-writes switch, read exactly as the guard above reads it, so the text and the behaviour cannot disagree.
DIRECT_WRITES = 'os.environ.get("ODOO_MCP_ALLOW_DIRECT_WRITES", "").strip().lower() in ("1", "true", "yes")'

OLD_METHOD_DESCRIPTION = (
    '            description=(\n'
    '                "Odoo model method to call; direct create, write, and unlink are blocked."\n'
    '            )\n'
)

NEW_METHOD_DESCRIPTION = (
    '            description=(\n'
    '                # PATCH(woowtech HA 0.4.0): the text follows the direct-writes switch the guard below reads.\n'
    '                "Odoo model method to call; create, write and unlink run directly in this deployment "\n'
    '                "(ODOO_MCP_ALLOW_DIRECT_WRITES is set), without the preview_write -> validate_write -> "\n'
    '                "execute_approved_write flow; the Odoo user\'s own access rights still apply."\n'
    '                if ' + DIRECT_WRITES + '\n'
    '                else "Odoo model method to call; direct create, write, and unlink are blocked."\n'
    '            )\n'
)

OLD_CHATTER_DESCRIPTION = (
    '    description=(\n'
    '        "Post a chatter message on a mail.thread record. Default mode requires "\n'
    '        "an approval token returned from a preview call; set MCP_CHATTER_DIRECT=1 "\n'
    '        "to bypass and post immediately."\n'
    '    ),\n'
)

NEW_CHATTER_DESCRIPTION = (
    '    description=(\n'
    '        # PATCH(woowtech HA 0.4.0): the text follows MCP_CHATTER_DIRECT, which chatter_post itself reads.\n'
    '        "Post a chatter message on a mail.thread record. Direct mode is on in this deployment "\n'
    '        "(MCP_CHATTER_DIRECT): the first call posts the message at once; there is no preview and "\n'
    '        "no approval token."\n'
    '        if chatter_direct_enabled()\n'
    '        else "Post a chatter message on a mail.thread record. Default mode requires "\n'
    '        "an approval token returned from a preview call; set MCP_CHATTER_DIRECT=1 "\n'
    '        "to bypass and post immediately."\n'
    '    ),\n'
)


def find_tools_write() -> list[str]:
    """Locate tools_write.py inside the installed odoo_mcp package."""
    paths: list[str] = []
    # Try importlib first (most reliable)
    try:
        import importlib.util
        spec = importlib.util.find_spec("odoo_mcp.tools_write")
        if spec and spec.origin:
            paths.append(spec.origin)
    except (ImportError, ModuleNotFoundError, ValueError):
        pass
    # Fallback to glob patterns
    patterns = [
        os.path.join(sys.prefix, "lib", "python*", "site-packages", "odoo_mcp", "tools_write.py"),
        os.path.join(os.path.dirname(__file__), "..", "src", "odoo_mcp", "tools_write.py"),
    ]
    for pattern in patterns:
        for match in glob.glob(pattern):
            if match not in paths:
                paths.append(match)
    return paths


def patch(filepath: str) -> bool:
    """Apply the direct-writes patch.  Returns True if patched; raises on any unexpected content."""
    with open(filepath, "rb") as f:
        data = f.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest == PATCHED:
        print(f"[patch-direct-writes] Already applied to {filepath}")
        return False
    if digest != PINNED:
        raise ValueError(f"unexpected tools_write.py (sha256 {digest}); review the new odoo-mcp before patching")

    content = data.decode("utf-8")
    for old, new in ((OLD_BLOCK, NEW_BLOCK), (OLD_METHOD_DESCRIPTION, NEW_METHOD_DESCRIPTION),
                     (OLD_CHATTER_DESCRIPTION, NEW_CHATTER_DESCRIPTION)):
        if content.count(old) != 1:
            raise ValueError(f"target block not found exactly once in {filepath}")
        content = content.replace(old, new, 1)
    patched = content.encode("utf-8")
    if hashlib.sha256(patched).hexdigest() != PATCHED:
        raise ValueError("patched tools_write.py does not have the reviewed digest")

    with open(filepath, "wb") as f:
        f.write(patched)

    # Clear .pyc cache
    cache_dir = os.path.join(os.path.dirname(filepath), "__pycache__")
    if os.path.isdir(cache_dir):
        for pyc in glob.glob(os.path.join(cache_dir, "tools_write*.pyc")):
            os.remove(pyc)
            print(f"[patch-direct-writes] Removed cache: {pyc}")

    # Verify
    with open(filepath) as f:
        assert MARKER in f.read(), "Marker not found after patch"

    print(f"[patch-direct-writes] Applied to {filepath}")
    return True


def main() -> int:
    paths = find_tools_write()
    if not paths:
        print("[patch-direct-writes] ERROR: could not locate odoo_mcp/tools_write.py", file=sys.stderr)
        return 1
    ok = True
    for filepath in paths:
        try:
            patch(filepath)
        except Exception as exc:
            print(f"[patch-direct-writes] ERROR: {exc}", file=sys.stderr)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
