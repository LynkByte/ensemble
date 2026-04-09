"""MCP call tracking — records tool invocations in the ``mcp_calls`` table.

This module provides a lightweight helper that wraps around the tool
dispatch to track each call's input/output byte sizes and duration.
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
    """Insert a record into the ``mcp_calls`` table."""
    input_bytes = len(json.dumps(arguments, default=str).encode("utf-8"))
    output_bytes = len(json.dumps(result, default=str).encode("utf-8"))

    conn.execute(
        "INSERT INTO mcp_calls (tool_name, input_bytes, output_bytes, duration_ms) "
        "VALUES (?, ?, ?, ?)",
        (tool_name, input_bytes, output_bytes, duration_ms),
    )
    conn.commit()
