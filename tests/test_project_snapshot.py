"""Tests for the project_snapshot MCP tool."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ensemble_mcp.tools.indexer import project_index, project_snapshot


class TestProjectSnapshot:
    """Tests for project_snapshot tool — generation, caching, invalidation."""

    @pytest.mark.asyncio
    async def test_snapshot_generation(self, test_conn: sqlite3.Connection, tmp_path: Path):
        """Snapshot generates from indexed project_files data."""
        # Create a small Python project
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "main.py").write_text("class App:\n    pass\n")
        (src / "utils.py").write_text("def helper():\n    pass\n")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.py").write_text("def test_app():\n    pass\n")
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")

        # Index first
        await project_index(test_conn, project_path=str(tmp_path))

        # Generate snapshot
        env = await project_snapshot(test_conn, project_path=str(tmp_path))
        assert env["ok"] is True
        data = env["data"]

        assert data["cached"] is False
        assert data["files_hash"]
        snapshot = data["snapshot"]
        assert snapshot["language"] == "python"
        assert snapshot["project_path"] == str(tmp_path.resolve())
        assert isinstance(snapshot["conventions"], list)
        assert isinstance(snapshot["structure"], dict)
        assert isinstance(snapshot["build_tools"], list)
        assert isinstance(snapshot["key_files"], list)
        assert isinstance(snapshot["test_setup"], dict)

    @pytest.mark.asyncio
    async def test_cache_hit(self, test_conn: sqlite3.Connection, tmp_path: Path):
        """Second call returns cached result when files haven't changed."""
        (tmp_path / "app.py").write_text("class App:\n    pass\n")
        await project_index(test_conn, project_path=str(tmp_path))

        env1 = await project_snapshot(test_conn, project_path=str(tmp_path))
        assert env1["ok"] is True
        assert env1["data"]["cached"] is False

        env2 = await project_snapshot(test_conn, project_path=str(tmp_path))
        assert env2["ok"] is True
        assert env2["data"]["cached"] is True
        assert env2["data"]["files_hash"] == env1["data"]["files_hash"]

    @pytest.mark.asyncio
    async def test_cache_miss_on_hash_mismatch(self, test_conn: sqlite3.Connection, tmp_path: Path):
        """Cache is invalidated when files_hash changes (files re-indexed)."""
        (tmp_path / "app.py").write_text("class App:\n    pass\n")
        await project_index(test_conn, project_path=str(tmp_path))

        env1 = await project_snapshot(test_conn, project_path=str(tmp_path))
        assert env1["ok"] is True
        assert env1["data"]["cached"] is False

        # Modify the file and re-index
        import time

        time.sleep(0.1)  # Ensure mtime changes
        (tmp_path / "app.py").write_text("class App:\n    x = 1\n")
        await project_index(test_conn, project_path=str(tmp_path), force=True)

        env2 = await project_snapshot(test_conn, project_path=str(tmp_path))
        assert env2["ok"] is True
        assert env2["data"]["cached"] is False  # hash changed → regenerated

    @pytest.mark.asyncio
    async def test_cache_miss_on_expired(self, test_conn: sqlite3.Connection, tmp_path: Path):
        """Expired cache entry is regenerated."""
        (tmp_path / "app.py").write_text("x = 1\n")
        await project_index(test_conn, project_path=str(tmp_path))

        # Generate snapshot
        env1 = await project_snapshot(test_conn, project_path=str(tmp_path))
        assert env1["ok"] is True

        # Manually expire the cache entry
        project = str(tmp_path.resolve())
        test_conn.execute(
            "UPDATE project_snapshots SET expires_at = datetime('now', '-1 hour') "
            "WHERE project_path = ?",
            (project,),
        )
        test_conn.commit()

        # Should regenerate
        env2 = await project_snapshot(test_conn, project_path=str(tmp_path))
        assert env2["ok"] is True
        assert env2["data"]["cached"] is False

    @pytest.mark.asyncio
    async def test_force_refresh(self, test_conn: sqlite3.Connection, tmp_path: Path):
        """force=True bypasses cache and regenerates."""
        (tmp_path / "app.py").write_text("class App:\n    pass\n")
        await project_index(test_conn, project_path=str(tmp_path))

        env1 = await project_snapshot(test_conn, project_path=str(tmp_path))
        assert env1["ok"] is True
        assert env1["data"]["cached"] is False

        env2 = await project_snapshot(test_conn, project_path=str(tmp_path), force=True)
        assert env2["ok"] is True
        assert env2["data"]["cached"] is False  # forced → never returns cached

    @pytest.mark.asyncio
    async def test_empty_project_error(self, test_conn: sqlite3.Connection, tmp_path: Path):
        """Project with no indexed files returns NOT_FOUND_PROJECT error."""
        env = await project_snapshot(test_conn, project_path=str(tmp_path))
        assert env["ok"] is False
        assert env["error"]["code"] == "NOT_FOUND_PROJECT"

    @pytest.mark.asyncio
    async def test_snapshot_detects_build_tools(
        self, test_conn: sqlite3.Connection, tmp_path: Path
    ):
        """Build tools are detected from indicator files."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
        (tmp_path / "Makefile").write_text("all:\n\techo hello\n")
        (tmp_path / "Dockerfile").write_text("FROM python:3.11\n")
        (tmp_path / "app.py").write_text("x = 1\n")
        await project_index(test_conn, project_path=str(tmp_path))

        env = await project_snapshot(test_conn, project_path=str(tmp_path))
        assert env["ok"] is True
        build_tools = env["data"]["snapshot"]["build_tools"]
        assert "pyproject.toml" in build_tools
        assert "make" in build_tools
        assert "docker" in build_tools

    @pytest.mark.asyncio
    async def test_snapshot_detects_test_framework(
        self, test_conn: sqlite3.Connection, tmp_path: Path
    ):
        """Test framework is detected from indicator files."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "conftest.py").write_text("import pytest\n")
        (tests_dir / "test_app.py").write_text("def test_x():\n    pass\n")
        (tmp_path / "app.py").write_text("x = 1\n")
        await project_index(test_conn, project_path=str(tmp_path))

        env = await project_snapshot(test_conn, project_path=str(tmp_path))
        assert env["ok"] is True
        test_setup = env["data"]["snapshot"]["test_setup"]
        assert test_setup["framework"] == "pytest"
        assert test_setup["pattern_dir"] == "tests"

    @pytest.mark.asyncio
    async def test_snapshot_key_files_have_exports(
        self, test_conn: sqlite3.Connection, tmp_path: Path
    ):
        """Key files include export names."""
        (tmp_path / "models.py").write_text("class User:\n    pass\n\nclass Order:\n    pass\n")
        await project_index(test_conn, project_path=str(tmp_path))

        env = await project_snapshot(test_conn, project_path=str(tmp_path))
        assert env["ok"] is True
        key_files = env["data"]["snapshot"]["key_files"]
        assert len(key_files) >= 1
        models_file = [kf for kf in key_files if kf["path"] == "models.py"]
        assert len(models_file) == 1
        assert "User" in models_file[0]["exports"]
        assert "Order" in models_file[0]["exports"]

    @pytest.mark.asyncio
    async def test_snapshot_directory_structure(
        self, test_conn: sqlite3.Connection, tmp_path: Path
    ):
        """Directory structure maps top-level dirs to roles."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("x = 1\n")
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "readme.md").write_text("# Docs\n")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_app.py").write_text("def test():\n    pass\n")
        await project_index(test_conn, project_path=str(tmp_path))

        env = await project_snapshot(test_conn, project_path=str(tmp_path))
        assert env["ok"] is True
        structure = env["data"]["snapshot"]["structure"]
        assert structure.get("src") == "source"
        assert structure.get("docs") == "documentation"
        assert structure.get("tests") == "tests"

    @pytest.mark.asyncio
    async def test_envelope_structure(self, test_conn: sqlite3.Connection, tmp_path: Path):
        """Response follows the standard envelope format."""
        (tmp_path / "app.py").write_text("x = 1\n")
        await project_index(test_conn, project_path=str(tmp_path))

        env = await project_snapshot(test_conn, project_path=str(tmp_path))
        assert env["ok"] is True
        assert env["meta"]["source"] == "sqlite"
        assert env["meta"]["confidence"] == "exact"
        assert isinstance(env["meta"]["duration_ms"], int)

    @pytest.mark.asyncio
    async def test_idempotency(self, test_conn: sqlite3.Connection, tmp_path: Path):
        """Idempotency key returns cached result on replay."""
        (tmp_path / "app.py").write_text("x = 1\n")
        await project_index(test_conn, project_path=str(tmp_path))

        key = "snapshot-idem-1"
        env1 = await project_snapshot(test_conn, project_path=str(tmp_path), idempotency_key=key)
        # Second call with same key returns cached result
        env2 = await project_snapshot(test_conn, project_path=str(tmp_path), idempotency_key=key)
        assert env1["data"] == env2["data"]
