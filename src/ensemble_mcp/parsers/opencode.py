"""Parse OpenCode session data.

OpenCode stores all session data in a single monolithic SQLite database
at ``~/.local/share/opencode/opencode.db``.  Token usage is embedded as
JSON inside the ``message.data`` column for assistant-role messages.

Schema (relevant tables)::

    session(id, project_id, title, time_created, time_updated, ...)
    message(id, session_id, time_created, time_updated, data TEXT)
    project(id, worktree, name, ...)

The ``message.data`` JSON for assistant messages contains::

    {
      "role": "assistant",
      "mode": "build",            // or "plan", "explore", "team-*", ...
      "agent": "build",
      "modelID": "claude-opus-4.6",
      "providerID": "github-copilot",
      "tokens": {
        "input": 6791,
        "output": 1569,
        "reasoning": 0,
        "total": 60570,
        "cache": { "read": 52210, "write": 0 }
      },
      "time": { "created": 1775411378179, "completed": 1775411401265 },
      "finish": "tool-calls"
    }

The database is opened in **read-only** mode to avoid interfering with
a running OpenCode instance.
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config.defaults import (
    CONFIDENCE_EXACT,
    CONFIDENCE_PARTIAL,
    OPENCODE_DB_PATH,
    SOURCE_PARSER,
)
from . import ParsedSession, ParsedStep

__all__ = [
    "find_opencode_db",
    "list_sessions",
    "parse_session",
    "parse_latest_session",
]

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────


def _epoch_ms_to_iso(epoch_ms: int | None) -> str | None:
    """Convert epoch milliseconds to ISO-8601 UTC string."""
    if epoch_ms is None or epoch_ms == 0:
        return None
    try:
        dt = datetime.fromtimestamp(epoch_ms / 1000.0, tz=UTC)
        return dt.isoformat()
    except (OSError, ValueError, OverflowError):
        return None


def _safe_json_load(raw: str | None) -> dict[str, Any] | None:
    """Safely parse a JSON string, returning *None* on failure."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    """Open the OpenCode database in read-only mode.

    Uses the ``file:`` URI with ``?mode=ro`` to prevent any writes.
    Sets a busy timeout for the case where OpenCode holds a WAL lock.
    """
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2.0)
    conn.row_factory = sqlite3.Row
    # Safety: enforce read-only at the SQLite level too
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("PRAGMA query_only = ON")
    return conn


def _extract_step(data: dict[str, Any]) -> ParsedStep | None:
    """Extract a :class:`ParsedStep` from a message ``data`` dict.

    Returns *None* if the message has no usable token data.
    """
    role = data.get("role")
    if role != "assistant":
        return None

    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        return None

    input_tok = int(tokens.get("input", 0) or 0)
    output_tok = int(tokens.get("output", 0) or 0)
    reasoning = int(tokens.get("reasoning", 0) or 0)

    cache = tokens.get("cache") or {}
    cache_read = int(cache.get("read", 0) or 0)
    cache_write = int(cache.get("write", 0) or 0)

    # Skip messages with zero useful data
    if input_tok == 0 and output_tok == 0:
        return None

    # Timestamp from data.time.created (epoch ms)
    time_info = data.get("time") or {}
    ts = _epoch_ms_to_iso(time_info.get("created"))

    return ParsedStep(
        model=data.get("modelID"),
        input_tokens=input_tok,
        output_tokens=output_tok,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        reasoning_tokens=reasoning,
        timestamp=ts,
        agent=data.get("mode") or data.get("agent"),
        finish_reason=data.get("finish"),
    )


# ── Public API ───────────────────────────────────────────────────


def find_opencode_db(custom_path: Path | None = None) -> Path | None:
    """Locate the OpenCode database file.

    Parameters
    ----------
    custom_path:
        Override the default path (useful for testing).

    Returns
    -------
    Path | None
        Path to the database, or *None* if it does not exist.
    """
    path = custom_path or OPENCODE_DB_PATH
    return path if path.is_file() else None


def list_sessions(
    db_path: Path,
    *,
    project_path: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List available sessions, most recent first.

    Parameters
    ----------
    db_path:
        Path to the OpenCode SQLite database.
    project_path:
        If provided, restrict to sessions whose project ``worktree``
        matches this path.
    limit:
        Maximum number of sessions to return.

    Returns
    -------
    list[dict]
        Session summaries with ``session_id``, ``title``, ``project``,
        ``time_created``, ``message_count``.
    """
    conn = _connect_readonly(db_path)
    try:
        if project_path:
            rows = conn.execute(
                "SELECT s.id, s.title, s.time_created, s.time_updated, "
                "p.worktree, "
                "(SELECT COUNT(*) FROM message m WHERE m.session_id = s.id) as msg_count "
                "FROM session s "
                "JOIN project p ON s.project_id = p.id "
                "WHERE p.worktree = ? "
                "ORDER BY s.time_updated DESC LIMIT ?",
                (project_path, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT s.id, s.title, s.time_created, s.time_updated, "
                "p.worktree, "
                "(SELECT COUNT(*) FROM message m WHERE m.session_id = s.id) as msg_count "
                "FROM session s "
                "JOIN project p ON s.project_id = p.id "
                "ORDER BY s.time_updated DESC LIMIT ?",
                (limit,),
            ).fetchall()

        sessions = []
        for r in rows:
            sessions.append(
                {
                    "session_id": r["id"],
                    "title": r["title"],
                    "project": r["worktree"],
                    "time_created": _epoch_ms_to_iso(r["time_created"]),
                    "time_updated": _epoch_ms_to_iso(r["time_updated"]),
                    "message_count": r["msg_count"],
                }
            )
        return sessions
    except sqlite3.OperationalError as exc:
        logger.warning("Failed to list OpenCode sessions: %s", exc)
        return []
    finally:
        conn.close()


def parse_session(
    db_path: Path,
    session_id: str,
) -> ParsedSession | None:
    """Parse a specific OpenCode session by ID.

    Parameters
    ----------
    db_path:
        Path to the OpenCode SQLite database.
    session_id:
        The OpenCode session UUID.

    Returns
    -------
    ParsedSession | None
        Parsed session with token totals, or *None* on error.
    """
    conn = _connect_readonly(db_path)
    try:
        # Get session metadata
        session_row = conn.execute(
            "SELECT s.id, s.title, s.time_created, s.time_updated, "
            "p.worktree "
            "FROM session s "
            "LEFT JOIN project p ON s.project_id = p.id "
            "WHERE s.id = ?",
            (session_id,),
        ).fetchone()

        if not session_row:
            logger.debug("OpenCode session %s not found", session_id)
            return None

        # Get all messages for this session, ordered by time
        msg_rows = conn.execute(
            "SELECT data FROM message "
            "WHERE session_id = ? "
            "ORDER BY time_created ASC",
            (session_id,),
        ).fetchall()

        result = ParsedSession(
            session_id=session_id,
            ai_tool="opencode",
            project=session_row["worktree"],
            source=SOURCE_PARSER,
            confidence=CONFIDENCE_EXACT,
            started_at=_epoch_ms_to_iso(session_row["time_created"]),
            ended_at=_epoch_ms_to_iso(session_row["time_updated"]),
        )

        for msg_row in msg_rows:
            data = _safe_json_load(msg_row["data"])
            if data is None:
                result.errors.append("Unparseable message data JSON")
                continue

            step = _extract_step(data)
            if step is not None:
                result.steps.append(step)

        # Degrade confidence if we had parse errors
        if result.errors and result.steps or not result.steps:
            result.confidence = CONFIDENCE_PARTIAL

        result.compute_totals()
        return result

    except sqlite3.OperationalError as exc:
        logger.warning("Failed to parse OpenCode session %s: %s", session_id, exc)
        return None
    finally:
        conn.close()


def parse_latest_session(
    *,
    db_path: Path | None = None,
    project_path: str | None = None,
) -> ParsedSession | None:
    """Find and parse the most recent OpenCode session.

    Parameters
    ----------
    db_path:
        Override the default database path (for testing).
    project_path:
        If provided, restrict to sessions in this project directory.

    Returns
    -------
    ParsedSession | None
        Parsed session, or *None* if no sessions found.
    """
    resolved_path = find_opencode_db(db_path)
    if resolved_path is None:
        logger.debug("OpenCode database not found")
        return None

    sessions = list_sessions(resolved_path, project_path=project_path, limit=1)
    if not sessions:
        logger.debug("No OpenCode sessions found")
        return None

    latest = sessions[0]
    return parse_session(resolved_path, latest["session_id"])
