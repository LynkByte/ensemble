"""Tests for MCP call tracking."""

from __future__ import annotations

import json
import sqlite3

from ensemble_mcp.tools.mcp_tracking import record_mcp_call


class TestRecordMcpCall:
    def test_record_without_session(self, test_conn: sqlite3.Connection) -> None:
        """Record a call that is not linked to any session."""
        record_mcp_call(
            test_conn,
            tool_name="patterns_search",
            arguments={"query": "test", "top_k": 3},
            result={"ok": True, "data": {"matches": []}},
            duration_ms=5,
        )
        row = test_conn.execute(
            "SELECT tool_name, session_id, duration_ms FROM mcp_calls"
        ).fetchone()
        assert row is not None
        assert row[0] == "patterns_search"
        assert row[1] is None  # no session
        assert row[2] == 5

    def test_record_with_valid_session(self, test_conn: sqlite3.Connection) -> None:
        """Record a call linked to an existing session."""
        test_conn.execute(
            "INSERT INTO sessions (id, task, classification, state) "
            "VALUES ('sess_test1', 'test', 'simple', 'running')"
        )
        test_conn.commit()

        record_mcp_call(
            test_conn,
            tool_name="metrics_record_step",
            arguments={"session_id": "sess_test1", "agent": "craft"},
            result={"ok": True, "data": {"recorded": True}},
            duration_ms=10,
        )
        row = test_conn.execute("SELECT tool_name, session_id FROM mcp_calls").fetchone()
        assert row[0] == "metrics_record_step"
        assert row[1] == "sess_test1"

    def test_record_with_nonexistent_session(self, test_conn: sqlite3.Connection) -> None:
        """Session ID in args but session doesn't exist -> session_id is NULL."""
        record_mcp_call(
            test_conn,
            tool_name="metrics_record_step",
            arguments={"session_id": "nonexistent", "agent": "craft"},
            result={"ok": False},
            duration_ms=3,
        )
        row = test_conn.execute("SELECT tool_name, session_id FROM mcp_calls").fetchone()
        assert row[0] == "metrics_record_step"
        assert row[1] is None  # non-existent session -> NULL

    def test_input_output_bytes_calculated(self, test_conn: sqlite3.Connection) -> None:
        """Input and output bytes should reflect JSON serialization sizes."""
        args = {"query": "hello", "top_k": 5}
        result = {"ok": True, "data": {"matches": [{"name": "test"}]}}

        record_mcp_call(
            test_conn,
            tool_name="patterns_search",
            arguments=args,
            result=result,
            duration_ms=2,
        )

        row = test_conn.execute("SELECT input_bytes, output_bytes FROM mcp_calls").fetchone()

        expected_input = len(json.dumps(args).encode("utf-8"))
        expected_output = len(json.dumps(result).encode("utf-8"))
        assert row[0] == expected_input
        assert row[1] == expected_output

    def test_multiple_calls_tracked(self, test_conn: sqlite3.Connection) -> None:
        """Multiple calls should all be recorded."""
        for i in range(5):
            record_mcp_call(
                test_conn,
                tool_name=f"tool_{i}",
                arguments={},
                result={"ok": True},
                duration_ms=i,
            )

        count = test_conn.execute("SELECT COUNT(*) FROM mcp_calls").fetchone()[0]
        assert count == 5
