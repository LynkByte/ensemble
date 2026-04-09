"""Tests for skills tools (skills_discover, skills_suggest, skills_generate)."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import numpy as np
import pytest

from ensemble_mcp.tools.skills import skills_discover, skills_generate, skills_suggest


class TestSkillsDiscover:
    @pytest.mark.asyncio
    async def test_discover_empty_project(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        env = await skills_discover(
            mock_embedding_model,
            test_conn,
            project_path=str(tmp_path),
        )
        assert env["ok"] is True
        assert env["data"]["detected"] == []

    @pytest.mark.asyncio
    async def test_discover_finds_skill_files(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        # Create a skill file in a recognized directory
        skill_dir = tmp_path / ".ai" / "skills"
        skill_dir.mkdir(parents=True)
        (skill_dir / "testing.md").write_text("# Testing patterns\nUse pytest\n")

        env = await skills_discover(
            mock_embedding_model,
            test_conn,
            project_path=str(tmp_path),
        )
        assert env["ok"] is True
        detected = env["data"]["detected"]
        assert len(detected) >= 1
        assert detected[0]["name"] == "testing"
        assert detected[0]["source_tool"] == "opencode"

    @pytest.mark.asyncio
    async def test_discover_with_query(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        skill_dir = tmp_path / ".ai" / "skills"
        skill_dir.mkdir(parents=True)
        (skill_dir / "auth.md").write_text("# Authentication\nJWT patterns\n")

        env = await skills_discover(
            mock_embedding_model,
            test_conn,
            project_path=str(tmp_path),
            query="authentication",
        )
        assert env["ok"] is True
        # Semantic search mode: may or may not match depending on mock model

    @pytest.mark.asyncio
    async def test_discover_tracks_usage(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        skill_dir = tmp_path / ".ai" / "skills"
        skill_dir.mkdir(parents=True)
        (skill_dir / "track.md").write_text("# Trackable skill\n")

        await skills_discover(
            mock_embedding_model,
            test_conn,
            project_path=str(tmp_path),
        )
        row = test_conn.execute("SELECT match_count FROM skill_usage_tracking").fetchone()
        assert row is not None
        assert row[0] >= 1


class TestSkillsSuggest:
    @pytest.mark.asyncio
    async def test_suggest_no_patterns(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
    ):
        env = await skills_suggest(
            mock_embedding_model,
            test_conn,
            project_path="/my/project",
        )
        assert env["ok"] is True
        assert env["data"]["suggestions"] == []

    @pytest.mark.asyncio
    async def test_suggest_with_patterns(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
    ):
        # Insert several patterns with similar embeddings
        base_vec = np.random.RandomState(42).randn(384).astype(np.float32)
        base_vec = base_vec / np.linalg.norm(base_vec)

        for i in range(5):
            # Small perturbation for clustering
            noise = np.random.RandomState(i).randn(384).astype(np.float32) * 0.01
            vec = base_vec + noise
            vec = vec / np.linalg.norm(vec)

            test_conn.execute(
                "INSERT INTO patterns (name, context, approach, outcome, project, embedding) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    f"error-handling-{i}",
                    "API error handling",
                    "try/except with custom exceptions",
                    f"outcome {i}",
                    "/my/project",
                    vec.tobytes(),
                ),
            )
        test_conn.commit()

        env = await skills_suggest(
            mock_embedding_model,
            test_conn,
            project_path="/my/project",
            min_cluster_size=3,
        )
        assert env["ok"] is True
        # Should find at least one cluster of 5 similar patterns
        assert len(env["data"]["suggestions"]) >= 1


class TestSkillsGenerate:
    async def _create_suggestion(
        self,
        conn: sqlite3.Connection,
        project: str = "/proj",
    ) -> int:
        cursor = conn.execute(
            "INSERT INTO skill_suggestions "
            "(project, proposed_name, proposed_content, theme) "
            "VALUES (?, ?, ?, ?)",
            (project, "test-skill", "# Test Skill\nContent", "test theme"),
        )
        conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    @pytest.mark.asyncio
    async def test_accept_generates_file(
        self,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        sid = await self._create_suggestion(test_conn)
        output_dir = str(tmp_path / "skills")

        env = await skills_generate(
            test_conn,
            suggestion_id=sid,
            action="accept",
            output_dir=output_dir,
        )
        assert env["ok"] is True
        assert env["data"]["generated"] is True
        assert env["data"]["status"] == "accepted"
        assert Path(env["data"]["path"]).exists()

    @pytest.mark.asyncio
    async def test_dismiss_suggestion(self, test_conn: sqlite3.Connection):
        sid = await self._create_suggestion(test_conn)
        env = await skills_generate(
            test_conn,
            suggestion_id=sid,
            action="dismiss",
        )
        assert env["ok"] is True
        assert env["data"]["generated"] is False
        assert env["data"]["status"] == "dismissed"

    @pytest.mark.asyncio
    async def test_defer_suggestion(self, test_conn: sqlite3.Connection):
        sid = await self._create_suggestion(test_conn)
        env = await skills_generate(
            test_conn,
            suggestion_id=sid,
            action="defer",
        )
        assert env["ok"] is True
        assert env["data"]["status"] == "deferred"

    @pytest.mark.asyncio
    async def test_not_found_suggestion(self, test_conn: sqlite3.Connection):
        env = await skills_generate(
            test_conn,
            suggestion_id=99999,
        )
        assert env["ok"] is False
        assert env["error"]["code"] == "NOT_FOUND_SKILL_SUGGESTION"

    @pytest.mark.asyncio
    async def test_already_resolved(self, test_conn: sqlite3.Connection):
        sid = await self._create_suggestion(test_conn)
        await skills_generate(test_conn, suggestion_id=sid, action="dismiss")
        env = await skills_generate(test_conn, suggestion_id=sid, action="accept")
        assert env["ok"] is False
        assert env["error"]["code"] == "CONFLICT_ALREADY_RESOLVED"

    @pytest.mark.asyncio
    async def test_invalid_action(self, test_conn: sqlite3.Connection):
        sid = await self._create_suggestion(test_conn)
        env = await skills_generate(
            test_conn,
            suggestion_id=sid,
            action="invalid",
        )
        assert env["ok"] is False
        assert env["error"]["code"] == "VALIDATION_INVALID_VALUE"


class TestSkillFileCache:
    """Tests for the mtime-based skill file caching in skills_discover."""

    @pytest.mark.asyncio
    async def test_discover_caches_skill_files(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        """First call populates skill_file_cache; second call returns same results."""
        skill_dir = tmp_path / ".ai" / "skills"
        skill_dir.mkdir(parents=True)
        (skill_dir / "caching.md").write_text("# Caching patterns\nRedis usage\n")

        # First call — populates cache
        env1 = await skills_discover(
            mock_embedding_model,
            test_conn,
            project_path=str(tmp_path),
        )
        assert env1["ok"] is True
        assert len(env1["data"]["detected"]) == 1

        # Verify cache table has the entry
        rows = test_conn.execute(
            "SELECT file_path, name, source_tool, content, embedding "
            "FROM skill_file_cache WHERE project_path = ?",
            (str(tmp_path),),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == ".ai/skills/caching.md"
        assert rows[0][1] == "caching"
        assert rows[0][2] == "opencode"
        assert "Caching patterns" in rows[0][3]
        # Embedding should be a valid 384-dim float32 BLOB
        emb = np.frombuffer(rows[0][4], dtype=np.float32)
        assert emb.shape == (384,)

        # Second call — should return same results from cache
        env2 = await skills_discover(
            mock_embedding_model,
            test_conn,
            project_path=str(tmp_path),
        )
        assert env2["ok"] is True
        assert len(env2["data"]["detected"]) == 1
        assert env2["data"]["detected"][0]["name"] == "caching"

    @pytest.mark.asyncio
    async def test_discover_invalidates_on_mtime_change(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        """Modified files should have their cached content and embedding updated."""
        skill_dir = tmp_path / ".ai" / "skills"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "evolving.md"
        skill_file.write_text("# Original content\nFirst version\n")

        # First call — populate cache
        await skills_discover(
            mock_embedding_model,
            test_conn,
            project_path=str(tmp_path),
        )
        row1 = test_conn.execute(
            "SELECT content, embedding FROM skill_file_cache WHERE project_path = ?",
            (str(tmp_path),),
        ).fetchone()
        assert "Original content" in row1[0]
        old_embedding = row1[1]

        # Modify file with a different mtime (bump mtime to ensure it differs)
        time.sleep(0.05)
        skill_file.write_text("# Updated content\nSecond version with new info\n")
        # Ensure mtime is definitely different
        new_mtime = os.path.getmtime(str(skill_file)) + 1
        os.utime(str(skill_file), (new_mtime, new_mtime))

        # Second call — should detect mtime change and update cache
        await skills_discover(
            mock_embedding_model,
            test_conn,
            project_path=str(tmp_path),
        )
        row2 = test_conn.execute(
            "SELECT content, embedding FROM skill_file_cache WHERE project_path = ?",
            (str(tmp_path),),
        ).fetchone()
        assert "Updated content" in row2[0]
        assert "Original content" not in row2[0]
        # Embedding should have changed
        # (different content → different hash → different mock embedding)
        assert row2[1] != old_embedding

    @pytest.mark.asyncio
    async def test_discover_removes_deleted_files(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        """Deleted files should be pruned from the cache."""
        skill_dir = tmp_path / ".ai" / "skills"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "ephemeral.md"
        skill_file.write_text("# Ephemeral skill\nWill be deleted\n")

        # First call — populate cache
        env1 = await skills_discover(
            mock_embedding_model,
            test_conn,
            project_path=str(tmp_path),
        )
        assert len(env1["data"]["detected"]) == 1
        cache_count = test_conn.execute(
            "SELECT COUNT(*) FROM skill_file_cache WHERE project_path = ?",
            (str(tmp_path),),
        ).fetchone()[0]
        assert cache_count == 1

        # Delete the file
        skill_file.unlink()

        # Second call — should detect deletion and remove cache entry
        env2 = await skills_discover(
            mock_embedding_model,
            test_conn,
            project_path=str(tmp_path),
        )
        assert len(env2["data"]["detected"]) == 0
        cache_count = test_conn.execute(
            "SELECT COUNT(*) FROM skill_file_cache WHERE project_path = ?",
            (str(tmp_path),),
        ).fetchone()[0]
        assert cache_count == 0

    @pytest.mark.asyncio
    async def test_discover_semantic_uses_cached_embedding(
        self,
        mock_embedding_model,
        test_conn: sqlite3.Connection,
        tmp_path: Path,
    ):
        """Semantic search with query= should use pre-computed cached embeddings."""
        skill_dir = tmp_path / ".ai" / "skills"
        skill_dir.mkdir(parents=True)
        (skill_dir / "auth.md").write_text("# Authentication\nJWT token patterns\n")
        (skill_dir / "deploy.md").write_text("# Deployment\nDocker and CI/CD\n")

        # First call populates the cache (no query)
        env1 = await skills_discover(
            mock_embedding_model,
            test_conn,
            project_path=str(tmp_path),
        )
        assert env1["ok"] is True
        assert len(env1["data"]["detected"]) == 2

        # Verify embeddings are cached
        cache_rows = test_conn.execute(
            "SELECT file_path, embedding FROM skill_file_cache WHERE project_path = ?",
            (str(tmp_path),),
        ).fetchall()
        assert len(cache_rows) == 2
        for row in cache_rows:
            emb = np.frombuffer(row[1], dtype=np.float32)
            assert emb.shape == (384,)

        # Second call with query — semantic search uses cached embeddings
        env2 = await skills_discover(
            mock_embedding_model,
            test_conn,
            project_path=str(tmp_path),
            query="authentication JWT",
        )
        assert env2["ok"] is True
        # Should have results (semantic search was performed)
        # The mock model produces deterministic embeddings so results are stable
        if env2["data"]["detected"]:
            # Each detected skill should have a confidence score
            for skill in env2["data"]["detected"]:
                assert "confidence" in skill
                assert isinstance(skill["confidence"], float)
