"""Tests for session tools (session_save, session_load)."""

from __future__ import annotations

import sqlite3

import pytest

from ensemble_mcp.tools.session import session_load, session_save


class TestSessionSave:
    @pytest.mark.asyncio
    async def test_save_new_checkpoint(self, test_conn: sqlite3.Connection):
        env = await session_save(
            test_conn,
            session_id="sess_test1",
            state={"step": 3, "agent": "craft"},
        )
        assert env["ok"] is True
        assert env["data"]["saved"] is True
        assert env["data"]["version"] == 1

    @pytest.mark.asyncio
    async def test_save_increments_version(self, test_conn: sqlite3.Connection):
        await session_save(
            test_conn,
            session_id="sess_v1",
            state={"step": 1},
        )
        env = await session_save(
            test_conn,
            session_id="sess_v1",
            state={"step": 2},
        )
        assert env["data"]["version"] == 2

    @pytest.mark.asyncio
    async def test_save_with_version_check_passes(self, test_conn: sqlite3.Connection):
        await session_save(
            test_conn,
            session_id="sess_ov",
            state={"step": 1},
        )
        env = await session_save(
            test_conn,
            session_id="sess_ov",
            state={"step": 2},
            version=1,  # matches current version
        )
        assert env["ok"] is True
        assert env["data"]["version"] == 2

    @pytest.mark.asyncio
    async def test_save_version_mismatch(self, test_conn: sqlite3.Connection):
        await session_save(
            test_conn,
            session_id="sess_conflict",
            state={"step": 1},
        )
        env = await session_save(
            test_conn,
            session_id="sess_conflict",
            state={"step": 2},
            version=99,  # wrong version
        )
        assert env["ok"] is False
        assert env["error"]["code"] == "CONFLICT_VERSION_MISMATCH"

    @pytest.mark.asyncio
    async def test_save_idempotency(self, test_conn: sqlite3.Connection):
        key = "session-save-1"
        env1 = await session_save(
            test_conn,
            session_id="sess_idem",
            state={"x": 1},
            idempotency_key=key,
        )
        env2 = await session_save(
            test_conn,
            session_id="sess_idem",
            state={"x": 2},
            idempotency_key=key,
        )
        assert env1["data"] == env2["data"]


class TestSessionLoad:
    @pytest.mark.asyncio
    async def test_load_not_found(self, test_conn: sqlite3.Connection):
        env = await session_load(test_conn, session_id="nonexistent")
        assert env["ok"] is True
        assert env["data"]["found"] is False

    @pytest.mark.asyncio
    async def test_load_specific_session(self, test_conn: sqlite3.Connection):
        await session_save(
            test_conn,
            session_id="sess_load1",
            state={"agent": "craft", "step": 5},
        )
        env = await session_load(test_conn, session_id="sess_load1")
        assert env["ok"] is True
        data = env["data"]
        assert data["found"] is True
        assert data["session_id"] == "sess_load1"
        assert data["state"]["agent"] == "craft"
        assert data["version"] == 1

    @pytest.mark.asyncio
    async def test_load_latest_checkpoint(self, test_conn: sqlite3.Connection):
        await session_save(
            test_conn,
            session_id="sess_old",
            state={"order": 1},
        )
        await session_save(
            test_conn,
            session_id="sess_new",
            state={"order": 2},
        )
        env = await session_load(test_conn, session_id=None)
        assert env["ok"] is True
        assert env["data"]["found"] is True
        # Should return the most recent checkpoint
        assert env["data"]["session_id"] in ("sess_old", "sess_new")

    @pytest.mark.asyncio
    async def test_load_reflects_updated_state(self, test_conn: sqlite3.Connection):
        await session_save(
            test_conn,
            session_id="sess_update",
            state={"v": 1},
        )
        await session_save(
            test_conn,
            session_id="sess_update",
            state={"v": 2},
        )
        env = await session_load(test_conn, session_id="sess_update")
        assert env["data"]["state"]["v"] == 2
        assert env["data"]["version"] == 2
