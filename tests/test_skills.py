"""Tests for skills tools (skills_discover, skills_suggest, skills_generate)."""

from __future__ import annotations

import sqlite3
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
