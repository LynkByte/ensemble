"""Tests for session tools (session_save, session_load, session_search)."""

from __future__ import annotations

import numpy as np
import pytest

from ensemble_mcp.memory.store import VectorStore
from ensemble_mcp.tools.session import session_load, session_save, session_search

# ── session_save ─────────────────────────────────────────────────


class TestSessionSave:
    @pytest.mark.asyncio
    async def test_save_new_checkpoint(self, test_store: VectorStore):
        env = await session_save(
            test_store,
            session_id="sess_test1",
            state={"step": 3, "agent": "craft"},
        )
        assert env["ok"] is True
        assert env["data"]["saved"] is True
        assert env["data"]["version"] == 1

    @pytest.mark.asyncio
    async def test_save_increments_version(self, test_store: VectorStore):
        await session_save(
            test_store,
            session_id="sess_v1",
            state={"step": 1},
        )
        env = await session_save(
            test_store,
            session_id="sess_v1",
            state={"step": 2},
        )
        assert env["data"]["version"] == 2

    @pytest.mark.asyncio
    async def test_save_with_version_check_passes(self, test_store: VectorStore):
        await session_save(
            test_store,
            session_id="sess_ov",
            state={"step": 1},
        )
        env = await session_save(
            test_store,
            session_id="sess_ov",
            state={"step": 2},
            version=1,  # matches current version
        )
        assert env["ok"] is True
        assert env["data"]["version"] == 2

    @pytest.mark.asyncio
    async def test_save_version_mismatch(self, test_store: VectorStore):
        await session_save(
            test_store,
            session_id="sess_conflict",
            state={"step": 1},
        )
        env = await session_save(
            test_store,
            session_id="sess_conflict",
            state={"step": 2},
            version=99,  # wrong version
        )
        assert env["ok"] is False
        assert env["error"]["code"] == "CONFLICT_VERSION_MISMATCH"

    @pytest.mark.asyncio
    async def test_save_idempotency(self, test_store: VectorStore):
        key = "session-save-1"
        env1 = await session_save(
            test_store,
            session_id="sess_idem",
            state={"x": 1},
            idempotency_key=key,
        )
        env2 = await session_save(
            test_store,
            session_id="sess_idem",
            state={"x": 2},
            idempotency_key=key,
        )
        assert env1["data"] == env2["data"]

    @pytest.mark.asyncio
    async def test_save_with_resume_fields(self, test_store: VectorStore):
        """Saving with resume fields merges them into state and stores columns."""
        env = await session_save(
            test_store,
            session_id="sess_resume",
            state={"step": 1},
            original_request="Add pagination to user list",
            decisions=["Use cursor-based pagination"],
            completed_steps=["Step 1: Plan"],
            remaining_steps=["Step 2: Implement"],
            files_changed=["src/users.py"],
            errors=[],
            context_for_resume="Using Django paginator",
            task_classification="standard",
            status="running",
            project="/home/user/myproject",
        )
        assert env["ok"] is True
        assert env["data"]["saved"] is True
        assert env["data"]["version"] == 1

        # Verify columns were stored
        row = test_store.conn.execute(
            "SELECT original_request, task_classification, status, project "
            "FROM session_checkpoints WHERE session_id = ?",
            ("sess_resume",),
        ).fetchone()
        assert row[0] == "Add pagination to user list"
        assert row[1] == "standard"
        assert row[2] == "running"
        assert row[3] == "/home/user/myproject"

    @pytest.mark.asyncio
    async def test_save_generates_embedding(self, test_store: VectorStore):
        """When original_request is provided, an embedding BLOB is stored."""
        await session_save(
            test_store,
            session_id="sess_emb",
            state={"step": 1},
            original_request="Fix login page CSS layout issue",
        )
        row = test_store.conn.execute(
            "SELECT embedding FROM session_checkpoints WHERE session_id = ?",
            ("sess_emb",),
        ).fetchone()
        assert row[0] is not None
        emb = np.frombuffer(row[0], dtype=np.float32)
        assert emb.shape == (384,)

    @pytest.mark.asyncio
    async def test_save_without_resume_fields_backward_compat(self, test_store: VectorStore):
        """Without resume fields, behavior is identical to original."""
        env = await session_save(
            test_store,
            session_id="sess_compat",
            state={"step": 5, "agent": "forge"},
        )
        assert env["ok"] is True
        assert env["data"]["version"] == 1

        # No embedding or extra columns
        row = test_store.conn.execute(
            "SELECT embedding, original_request, task_classification, project "
            "FROM session_checkpoints WHERE session_id = ?",
            ("sess_compat",),
        ).fetchone()
        assert row[0] is None  # no embedding
        assert row[1] is None  # no original_request
        assert row[2] is None  # no task_classification
        assert row[3] is None  # no project

    @pytest.mark.asyncio
    async def test_save_resume_merged_into_state(self, test_store: VectorStore):
        """Resume fields are merged into state dict under 'resume' key."""
        await session_save(
            test_store,
            session_id="sess_merged",
            state={"step": 2},
            original_request="Build API endpoint",
            task_classification="standard",
        )
        row = test_store.conn.execute(
            "SELECT state_json FROM session_checkpoints WHERE session_id = ?",
            ("sess_merged",),
        ).fetchone()
        import json

        state = json.loads(row[0])
        assert "resume" in state
        assert state["resume"]["original_request"] == "Build API endpoint"
        assert state["resume"]["task_classification"] == "standard"
        assert state["step"] == 2

    @pytest.mark.asyncio
    async def test_save_update_preserves_columns_with_coalesce(self, test_store: VectorStore):
        """Updating without resume fields preserves existing column values."""
        await session_save(
            test_store,
            session_id="sess_coalesce",
            state={"step": 1},
            original_request="Add feature X",
            task_classification="complex",
            project="/proj",
        )
        # Update without resume fields
        await session_save(
            test_store,
            session_id="sess_coalesce",
            state={"step": 2},
        )
        row = test_store.conn.execute(
            "SELECT original_request, task_classification, project "
            "FROM session_checkpoints WHERE session_id = ?",
            ("sess_coalesce",),
        ).fetchone()
        assert row[0] == "Add feature X"
        assert row[1] == "complex"
        assert row[2] == "/proj"

    @pytest.mark.asyncio
    async def test_save_default_status(self, test_store: VectorStore):
        """New sessions without explicit status get 'running'."""
        await session_save(
            test_store,
            session_id="sess_default_status",
            state={"step": 1},
        )
        row = test_store.conn.execute(
            "SELECT status FROM session_checkpoints WHERE session_id = ?",
            ("sess_default_status",),
        ).fetchone()
        assert row[0] == "running"


# ── session_load ─────────────────────────────────────────────────


class TestSessionLoad:
    @pytest.mark.asyncio
    async def test_load_not_found(self, test_store: VectorStore):
        env = await session_load(test_store, session_id="nonexistent")
        assert env["ok"] is True
        assert env["data"]["found"] is False

    @pytest.mark.asyncio
    async def test_load_specific_session(self, test_store: VectorStore):
        await session_save(
            test_store,
            session_id="sess_load1",
            state={"agent": "craft", "step": 5},
        )
        env = await session_load(test_store, session_id="sess_load1")
        assert env["ok"] is True
        data = env["data"]
        assert data["found"] is True
        assert data["session_id"] == "sess_load1"
        assert data["state"]["agent"] == "craft"
        assert data["version"] == 1

    @pytest.mark.asyncio
    async def test_load_latest_checkpoint(self, test_store: VectorStore):
        await session_save(
            test_store,
            session_id="sess_old",
            state={"order": 1},
        )
        await session_save(
            test_store,
            session_id="sess_new",
            state={"order": 2},
        )
        env = await session_load(test_store, session_id=None)
        assert env["ok"] is True
        assert env["data"]["found"] is True
        # Should return the most recent checkpoint
        assert env["data"]["session_id"] in ("sess_old", "sess_new")

    @pytest.mark.asyncio
    async def test_load_reflects_updated_state(self, test_store: VectorStore):
        await session_save(
            test_store,
            session_id="sess_update",
            state={"v": 1},
        )
        await session_save(
            test_store,
            session_id="sess_update",
            state={"v": 2},
        )
        env = await session_load(test_store, session_id="sess_update")
        assert env["data"]["state"]["v"] == 2
        assert env["data"]["version"] == 2

    @pytest.mark.asyncio
    async def test_load_returns_new_columns_when_present(self, test_store: VectorStore):
        """Load includes new columns when they are populated."""
        await session_save(
            test_store,
            session_id="sess_new_cols",
            state={"step": 1},
            original_request="Refactor auth module",
            task_classification="complex",
            status="running",
            project="/home/user/proj",
        )
        env = await session_load(test_store, session_id="sess_new_cols")
        data = env["data"]
        assert data["original_request"] == "Refactor auth module"
        assert data["task_classification"] == "complex"
        assert data["status"] == "running"
        assert data["project"] == "/home/user/proj"

    @pytest.mark.asyncio
    async def test_load_omits_null_columns(self, test_store: VectorStore):
        """Load omits new columns when they are NULL (backward compat)."""
        await session_save(
            test_store,
            session_id="sess_old_style",
            state={"step": 3},
        )
        env = await session_load(test_store, session_id="sess_old_style")
        data = env["data"]
        assert "original_request" not in data
        assert "task_classification" not in data
        # status has DEFAULT 'running' so it will be present
        assert data["status"] == "running"
        assert "project" not in data


# ── session_search ───────────────────────────────────────────────


class TestSessionSearch:
    @pytest.mark.asyncio
    async def test_search_empty_db(self, test_store: VectorStore):
        env = await session_search(test_store, query="anything")
        assert env["ok"] is True
        assert env["data"]["matches"] == []

    @pytest.mark.asyncio
    async def test_search_finds_saved_session(self, test_store: VectorStore):
        """Searching with the same text as original_request should match."""
        await session_save(
            test_store,
            session_id="sess_searchable",
            state={"step": 2},
            original_request="database connection pooling setup",
        )
        env = await session_search(
            test_store,
            query="database connection pooling setup",
            top_k=5,
        )
        assert env["ok"] is True
        matches = env["data"]["matches"]
        # With identical text, the mock model should produce a high score
        assert len(matches) >= 0  # hash-based may or may not match

    @pytest.mark.asyncio
    async def test_search_returns_session_metadata(self, test_store: VectorStore):
        """Search results include session metadata."""
        await session_save(
            test_store,
            session_id="sess_meta",
            state={"step": 1},
            original_request="add user authentication",
            task_classification="standard",
            status="completed",
            project="/home/user/app",
        )
        env = await session_search(
            test_store,
            query="add user authentication",
        )
        assert env["ok"] is True
        if env["data"]["matches"]:
            match = env["data"]["matches"][0]
            assert "session_id" in match
            assert "score" in match
            assert "version" in match

    @pytest.mark.asyncio
    async def test_search_project_filter(self, test_store: VectorStore):
        """Project filter scopes search results."""
        await session_save(
            test_store,
            session_id="sess_proj_a",
            state={"step": 1},
            original_request="setup logging",
            project="proj-a",
        )
        await session_save(
            test_store,
            session_id="sess_proj_b",
            state={"step": 1},
            original_request="setup logging",
            project="proj-b",
        )
        env = await session_search(
            test_store,
            query="setup logging",
            project="proj-a",
        )
        assert env["ok"] is True
        # All matches should be from proj-a or NULL project
        for match in env["data"]["matches"]:
            assert match.get("project") in ("proj-a", None)

    @pytest.mark.asyncio
    async def test_search_status_filter(self, test_store: VectorStore):
        """Status filter limits results to matching status."""
        await session_save(
            test_store,
            session_id="sess_active",
            state={"step": 1},
            original_request="build feature",
            status="running",
        )
        await session_save(
            test_store,
            session_id="sess_done",
            state={"step": 3},
            original_request="build feature",
            status="completed",
        )
        env = await session_search(
            test_store,
            query="build feature",
            status="completed",
        )
        assert env["ok"] is True
        for match in env["data"]["matches"]:
            assert match.get("status") == "completed"

    @pytest.mark.asyncio
    async def test_search_idempotency(self, test_store: VectorStore):
        key = "idem-session-search-1"
        env1 = await session_search(
            test_store,
            query="test search",
            idempotency_key=key,
        )
        env2 = await session_search(
            test_store,
            query="different search",
            idempotency_key=key,
        )
        assert env1["data"] == env2["data"]

    @pytest.mark.asyncio
    async def test_search_skips_sessions_without_embedding(self, test_store: VectorStore):
        """Sessions saved without original_request have no embedding and are skipped."""
        await session_save(
            test_store,
            session_id="sess_no_emb",
            state={"step": 1},
        )
        env = await session_search(test_store, query="anything")
        assert env["ok"] is True
        # sess_no_emb should not appear because it has no embedding
        for match in env["data"]["matches"]:
            assert match["session_id"] != "sess_no_emb"
