"""Idempotency key dedup store.

Each mutating tool call supports idempotency_key (optional but recommended).
If the same key is replayed within a session, the server returns the
previously committed result instead of applying changes twice.

Storage is SQLite-backed and keys auto-expire after a configurable TTL.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..config.defaults import IDEMPOTENCY_KEY_TTL_HOURS


def ensure_idempotency_table(conn: sqlite3.Connection) -> None:
    """Create the idempotency_keys table if it does not exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            key TEXT PRIMARY KEY,
            result_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT DEFAULT (datetime('now', '+24 hours'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_idempotency_expires ON idempotency_keys(expires_at)"
    )
    conn.commit()


def check_idempotency(
    conn: sqlite3.Connection,
    key: str | None,
) -> dict[str, Any] | None:
    """Return the cached result for *key*, or ``None`` if not found / expired.

    Expired keys are cleaned up lazily.
    """
    if key is None:
        return None

    # Lazy cleanup of expired keys
    conn.execute("DELETE FROM idempotency_keys WHERE expires_at < datetime('now')")

    row = conn.execute(
        "SELECT result_json FROM idempotency_keys WHERE key = ? AND expires_at >= datetime('now')",
        (key,),
    ).fetchone()

    if row is not None:
        result: dict[str, Any] = json.loads(row[0])
        return result
    return None


def store_idempotency(
    conn: sqlite3.Connection,
    key: str | None,
    result: dict[str, Any],
    ttl_hours: int = IDEMPOTENCY_KEY_TTL_HOURS,
) -> None:
    """Persist *result* under *key* so replayed calls return the same value."""
    if key is None:
        return

    conn.execute(
        "INSERT OR REPLACE INTO idempotency_keys (key, result_json, expires_at) "
        "VALUES (?, ?, datetime('now', ? || ' hours'))",
        (key, json.dumps(result), str(ttl_hours)),
    )
    conn.commit()
