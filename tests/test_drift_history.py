"""Tests for drift history persistence."""

from __future__ import annotations

import json
import sqlite3

import pytest

from ensemble_mcp.tools.drift import drift_check


class TestDriftHistoryPersistence:
    """Verify that drift_check writes results to drift_history table."""

    @pytest.mark.asyncio
    async def test_drift_check_persists_history(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
    ):
        """drift_check should insert a row into drift_history."""
        env = await drift_check(
            mock_embedding_model,
            test_conn,
            task_description="Add user authentication",
            changed_files=["src/auth.py", "tests/test_auth.py"],
            diff_summary="Add user authentication module with login and logout",
            project="/my/project",
        )
        assert env["ok"] is True

        # Verify row was persisted
        rows = test_conn.execute("SELECT * FROM drift_history").fetchall()
        assert len(rows) == 1

        row = rows[0]
        assert row["task_description"] == "Add user authentication"
        assert row["score"] == env["data"]["score"]
        assert row["similarity"] == env["data"]["similarity"]
        assert row["verdict"] == env["data"]["verdict"]
        assert row["project"] == "/my/project"

        # changed_files and flags are JSON-encoded
        changed_files = json.loads(row["changed_files"])
        assert changed_files == ["src/auth.py", "tests/test_auth.py"]

        flags = json.loads(row["flags"])
        assert isinstance(flags, list)

    @pytest.mark.asyncio
    async def test_multiple_drift_checks_accumulate(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
    ):
        """Multiple drift_check calls should create multiple history rows."""
        for i in range(3):
            await drift_check(
                mock_embedding_model,
                test_conn,
                task_description=f"Task {i}",
                changed_files=[f"file_{i}.py"],
                diff_summary=f"Diff for task {i}",
            )

        count = test_conn.execute("SELECT COUNT(*) FROM drift_history").fetchone()[0]
        assert count == 3

    @pytest.mark.asyncio
    async def test_drift_history_without_project(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
    ):
        """drift_check without project should persist with NULL project."""
        await drift_check(
            mock_embedding_model,
            test_conn,
            task_description="Fix bug",
            changed_files=[],
            diff_summary="Fixed the bug",
        )

        row = test_conn.execute("SELECT project FROM drift_history").fetchone()
        assert row["project"] is None

    @pytest.mark.asyncio
    async def test_drift_history_has_created_at(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
    ):
        """drift_history rows should have a created_at timestamp."""
        await drift_check(
            mock_embedding_model,
            test_conn,
            task_description="Task",
            changed_files=[],
            diff_summary="Diff",
        )

        row = test_conn.execute("SELECT created_at FROM drift_history").fetchone()
        assert row["created_at"] is not None
        # Should look like a datetime string
        assert "20" in row["created_at"]  # starts with year

    @pytest.mark.asyncio
    async def test_drift_history_filterable_by_project(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
    ):
        """drift_history should support filtering by project."""
        await drift_check(
            mock_embedding_model,
            test_conn,
            task_description="Task A",
            changed_files=[],
            diff_summary="Diff A",
            project="/project/a",
        )
        await drift_check(
            mock_embedding_model,
            test_conn,
            task_description="Task B",
            changed_files=[],
            diff_summary="Diff B",
            project="/project/b",
        )

        rows_a = test_conn.execute(
            "SELECT * FROM drift_history WHERE project = ?", ("/project/a",)
        ).fetchall()
        assert len(rows_a) == 1
        assert rows_a[0]["task_description"] == "Task A"

    @pytest.mark.asyncio
    async def test_idempotent_call_still_persists_once(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
    ):
        """Idempotent drift_check should only persist history on first call."""
        key = "drift-hist-idem-1"
        await drift_check(
            mock_embedding_model,
            test_conn,
            task_description="Task",
            changed_files=[],
            diff_summary="Diff",
            idempotency_key=key,
        )
        # Second call with same key — should return cached result
        await drift_check(
            mock_embedding_model,
            test_conn,
            task_description="DIFFERENT",
            changed_files=[],
            diff_summary="DIFFERENT",
            idempotency_key=key,
        )

        count = test_conn.execute("SELECT COUNT(*) FROM drift_history").fetchone()[0]
        # Only one row because the second call returns the cached result
        assert count == 1
