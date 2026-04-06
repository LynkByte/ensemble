"""Session tools: session_save, session_load.

Pipeline checkpoint state with optimistic versioning.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..contracts.envelope import tool_handler
from ..contracts.errors import ErrorCode, ToolError
from ..state.idempotency import check_idempotency, store_idempotency


@tool_handler(source="sqlite", confidence="exact")
async def session_save(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    state: dict[str, Any],
    version: int | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Save pipeline checkpoint state with optimistic versioning.

    If ``version`` is provided, it must match the current version in the
    database — otherwise a ``CONFLICT_VERSION_MISMATCH`` is raised.
    """
    cached = check_idempotency(conn, idempotency_key)
    if cached is not None:
        return cached

    state_json = json.dumps(state)

    # Check for existing checkpoint
    existing = conn.execute(
        "SELECT version FROM session_checkpoints WHERE session_id = ?",
        (session_id,),
    ).fetchone()

    if existing is not None:
        current_version = existing[0]
        if version is not None and version != current_version:
            raise ToolError(
                code=ErrorCode.CONFLICT_VERSION_MISMATCH,
                message=(
                    f"Version mismatch for session {session_id}: "
                    f"expected {version}, current is {current_version}"
                ),
                details={
                    "session_id": session_id,
                    "expected_version": version,
                    "current_version": current_version,
                },
            )
        new_version = current_version + 1
        conn.execute(
            "UPDATE session_checkpoints SET state_json = ?, version = ?, "
            "created_at = datetime('now') WHERE session_id = ?",
            (state_json, new_version, session_id),
        )
    else:
        new_version = 1
        conn.execute(
            "INSERT INTO session_checkpoints (session_id, state_json, version) VALUES (?, ?, ?)",
            (session_id, state_json, new_version),
        )

    conn.commit()
    result = {"saved": True, "version": new_version}
    store_idempotency(conn, idempotency_key, result)
    return result


@tool_handler(source="sqlite", confidence="exact")
async def session_load(
    conn: sqlite3.Connection,
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Load latest checkpoint, or a specific session's checkpoint.

    If ``session_id`` is ``None``, returns the most recent checkpoint.
    """
    if session_id:
        row = conn.execute(
            "SELECT session_id, state_json, version FROM session_checkpoints WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT session_id, state_json, version FROM session_checkpoints "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

    if not row:
        return {"found": False}

    return {
        "found": True,
        "session_id": row[0],
        "state": json.loads(row[1]),
        "version": row[2],
    }
