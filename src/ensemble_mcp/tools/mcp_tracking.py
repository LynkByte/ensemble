"""MCP call tracking — records tool invocations in the ``mcp_calls`` table.

This module provides a lightweight helper that wraps around the tool
dispatch to track each call's input/output byte sizes and duration.

Session association is optional: if a session_id is provided in the tool
arguments (for metrics-related tools), the call is linked to that session.
Otherwise ``session_id`` is left NULL.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def record_mcp_call(
    conn: sqlite3.Connection,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
    duration_ms: int,
) -> None:
    """Insert a record into the ``mcp_calls`` table.

    Attempts to associate the call with a session via ``session_id``
    in the arguments (if present and the session exists).
    """
    # Try to infer session_id from arguments
    session_id: str | None = arguments.get("session_id")

    # Verify session actually exists (avoid FK violation on NULL-safe insert)
    if session_id:
        row = conn.execute(
            "SELECT id FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            session_id = None  # Don't link to non-existent session

    input_bytes = len(json.dumps(arguments, default=str).encode("utf-8"))
    output_bytes = len(json.dumps(result, default=str).encode("utf-8"))

    conn.execute(
        "INSERT INTO mcp_calls (session_id, tool_name, input_bytes, output_bytes, duration_ms) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, tool_name, input_bytes, output_bytes, duration_ms),
    )
    conn.commit()
