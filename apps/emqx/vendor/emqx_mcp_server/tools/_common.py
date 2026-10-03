"""Shared helpers for tool modules."""

from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations


def read_only(title: str) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )


def destructive(title: str, idempotent: bool = True) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=idempotent,
        openWorldHint=True,
    )


def writing(title: str) -> ToolAnnotations:
    """Changes state but destroys nothing (e.g. publishing a message)."""
    return ToolAnnotations(
        title=title,
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )


def page_of(body: Any) -> tuple[list[dict], dict]:
    """Split an EMQX paged response into (rows, meta)."""
    if isinstance(body, dict):
        rows = body.get("data", [])
        return (rows if isinstance(rows, list) else []), body.get("meta", {}) or {}
    if isinstance(body, list):
        return body, {}
    return [], {}
