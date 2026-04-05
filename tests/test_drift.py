"""Tests for drift detection tool (drift_check)."""

from __future__ import annotations

import sqlite3

import pytest

from ensemble_mcp.tools.drift import drift_check


class TestDriftCheck:
    @pytest.mark.asyncio
    async def test_aligned_task_and_diff(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
    ):
        env = await drift_check(
            mock_embedding_model,
            test_conn,
            task_description="Add user authentication",
            changed_files=["src/auth.py", "tests/test_auth.py"],
            diff_summary="Add user authentication module with login and logout",
        )
        assert env["ok"] is True
        data = env["data"]
        assert "score" in data
        assert "similarity" in data
        assert "flags" in data
        assert "verdict" in data
        assert isinstance(data["score"], float)
        assert data["verdict"] in ("aligned", "minor_drift", "significant_drift")

    @pytest.mark.asyncio
    async def test_empty_changed_files(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
    ):
        env = await drift_check(
            mock_embedding_model,
            test_conn,
            task_description="Fix login bug",
            changed_files=[],
            diff_summary="Fixed the login validation",
        )
        assert env["ok"] is True
        assert env["data"]["flags"] == []

    @pytest.mark.asyncio
    async def test_suspicious_file_may_flag(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
    ):
        env = await drift_check(
            mock_embedding_model,
            test_conn,
            task_description="Fix login bug",
            changed_files=["migrations/002_add_column.sql", "src/auth.py"],
            diff_summary="Fixed the login validation",
        )
        assert env["ok"] is True
        # The mock model is hash-based, so flags depend on hash similarity
        assert isinstance(env["data"]["flags"], list)

    @pytest.mark.asyncio
    async def test_drift_score_structure(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
    ):
        env = await drift_check(
            mock_embedding_model,
            test_conn,
            task_description="task A",
            changed_files=[],
            diff_summary="completely unrelated topic B",
        )
        assert env["ok"] is True
        data = env["data"]
        # score + similarity should approximately equal 1.0
        assert abs(data["score"] + data["similarity"] - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_idempotency(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
    ):
        key = "drift-idem-1"
        env1 = await drift_check(
            mock_embedding_model,
            test_conn,
            task_description="task",
            changed_files=[],
            diff_summary="diff",
            idempotency_key=key,
        )
        env2 = await drift_check(
            mock_embedding_model,
            test_conn,
            task_description="DIFFERENT task",
            changed_files=[],
            diff_summary="DIFFERENT diff",
            idempotency_key=key,
        )
        assert env1["data"] == env2["data"]
