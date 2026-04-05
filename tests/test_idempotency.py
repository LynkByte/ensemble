"""Tests for idempotency key store."""

from __future__ import annotations

import sqlite3

from ensemble_mcp.state.idempotency import (
    check_idempotency,
    store_idempotency,
)


class TestIdempotency:
    def test_ensure_table_creates_table(self, test_conn: sqlite3.Connection):
        # Table already created by fixture, verify it exists
        row = test_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='idempotency_keys'"
        ).fetchone()
        assert row is not None

    def test_check_returns_none_for_no_key(self, test_conn: sqlite3.Connection):
        result = check_idempotency(test_conn, None)
        assert result is None

    def test_check_returns_none_for_missing_key(self, test_conn: sqlite3.Connection):
        result = check_idempotency(test_conn, "nonexistent-key")
        assert result is None

    def test_store_and_check(self, test_conn: sqlite3.Connection):
        data = {"stored": True, "id": 42}
        store_idempotency(test_conn, "test-key-1", data)

        result = check_idempotency(test_conn, "test-key-1")
        assert result == data

    def test_store_none_key_is_noop(self, test_conn: sqlite3.Connection):
        store_idempotency(test_conn, None, {"x": 1})
        # No error should occur; key is silently skipped

    def test_replace_existing_key(self, test_conn: sqlite3.Connection):
        store_idempotency(test_conn, "replace-me", {"v": 1})
        store_idempotency(test_conn, "replace-me", {"v": 2})
        result = check_idempotency(test_conn, "replace-me")
        assert result == {"v": 2}

    def test_expired_key_returns_none(self, test_conn: sqlite3.Connection):
        # Store with TTL of 0 hours (effectively expired immediately)
        test_conn.execute(
            "INSERT OR REPLACE INTO idempotency_keys (key, result_json, expires_at) "
            "VALUES (?, ?, datetime('now', '-1 hours'))",
            ("expired-key", '{"old": true}'),
        )
        test_conn.commit()

        result = check_idempotency(test_conn, "expired-key")
        assert result is None

    def test_multiple_keys_independent(self, test_conn: sqlite3.Connection):
        store_idempotency(test_conn, "key-a", {"value": "a"})
        store_idempotency(test_conn, "key-b", {"value": "b"})

        assert check_idempotency(test_conn, "key-a") == {"value": "a"}
        assert check_idempotency(test_conn, "key-b") == {"value": "b"}
