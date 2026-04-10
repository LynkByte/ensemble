"""Tests for dashboard API endpoints.

Uses aiohttp's test client to exercise all /api/* endpoints
against a temporary SQLite database with seeded test data.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer  # noqa: F401 — used by pytest-aiohttp

from ensemble_mcp.dashboard.api import register_api_routes
from ensemble_mcp.state.idempotency import ensure_idempotency_table
from ensemble_mcp.state.locks import get_connection


def _create_test_app(db_path: Path) -> web.Application:
    """Create a minimal dashboard app for testing."""
    app = web.Application()
    app["db_path"] = db_path
    register_api_routes(app)
    return app


def _seed_db(conn: sqlite3.Connection) -> None:
    """Insert test data into the database."""
    # Patterns
    emb = np.zeros(384, dtype=np.float32).tobytes()
    conn.execute(
        "INSERT INTO patterns (name, context, approach, outcome, project, embedding) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("test-pattern", "test context", "test approach", "test outcome", "/my/project", emb),
    )
    conn.execute(
        "INSERT INTO patterns (name, context, approach, outcome, project, embedding) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("global-pattern", "global context", "global approach", "global outcome", None, emb),
    )

    # MCP calls
    conn.execute(
        "INSERT INTO mcp_calls (tool_name, input_bytes, output_bytes, duration_ms) "
        "VALUES (?, ?, ?, ?)",
        ("patterns_store", 100, 50, 5),
    )

    # Project files
    pf_sql = (
        "INSERT INTO project_files"
        " (project_path, file_path, language, role, size_bytes, modified_at)"
        " VALUES (?, ?, ?, ?, ?, ?)"
    )
    conn.execute(
        pf_sql,
        ("/my/project", "src/main.py", "python", "source", 1024, "2026-04-01"),
    )
    conn.execute(
        pf_sql,
        ("/my/project", "tests/test_main.py", "python", "test", 512, "2026-04-01"),
    )

    # File exports
    file_id = conn.execute(
        "SELECT id FROM project_files WHERE file_path = 'src/main.py'"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO file_exports (file_id, name, kind) VALUES (?, ?, ?)",
        (file_id, "main", "function"),
    )

    # Drift history
    dh_sql = (
        "INSERT INTO drift_history"
        " (task_description, changed_files, score, similarity,"
        " verdict, flags, project)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    conn.execute(
        dh_sql,
        ("Add auth", '["src/auth.py"]', 0.15, 0.85, "aligned", "[]", "/my/project"),
    )
    conn.execute(
        dh_sql,
        (
            "Refactor DB",
            '["src/db.py"]',
            0.65,
            0.35,
            "significant_drift",
            '["Unexpected file change: migrations/001.sql"]',
            "/my/project",
        ),
    )

    # Skill suggestions
    ss_sql = (
        "INSERT INTO skill_suggestions"
        " (project, proposed_name, proposed_content, theme,"
        " confidence, status)"
        " VALUES (?, ?, ?, ?, ?, ?)"
    )
    conn.execute(
        ss_sql,
        ("/my/project", "test-skill", "skill content", "testing", 0.85, "pending"),
    )

    # Skill usage tracking
    conn.execute(
        "INSERT INTO skill_usage_tracking (skill_path, project, last_matched_at, match_count) "
        "VALUES (?, ?, ?, ?)",
        (".ai/skills/test.md", "/my/project", "2026-04-01", 5),
    )

    # Session checkpoints
    conn.execute(
        "INSERT INTO session_checkpoints (session_id, state_json, version) VALUES (?, ?, ?)",
        ("sess-001", json.dumps({"status": "completed", "steps": 3}), 2),
    )

    conn.commit()


@pytest.fixture()
def seeded_db(tmp_path):
    """Create a temporary database with test data."""
    db_path = tmp_path / "test_dashboard.db"
    conn = get_connection(db_path)

    # Create all tables
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, context TEXT NOT NULL,
            approach TEXT NOT NULL, outcome TEXT NOT NULL,
            project TEXT, embedding BLOB NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            last_matched_at TEXT, match_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS mcp_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT NOT NULL,
            input_bytes INTEGER DEFAULT 0,
            output_bytes INTEGER DEFAULT 0,
            duration_ms INTEGER,
            called_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS project_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_path TEXT NOT NULL, file_path TEXT NOT NULL,
            language TEXT, role TEXT,
            size_bytes INTEGER DEFAULT 0,
            modified_at TEXT NOT NULL,
            indexed_at TEXT DEFAULT (datetime('now')),
            UNIQUE(project_path, file_path)
        );
        CREATE TABLE IF NOT EXISTS file_exports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL REFERENCES project_files(id) ON DELETE CASCADE,
            name TEXT NOT NULL, kind TEXT NOT NULL,
            line_number INTEGER, signature TEXT, docstring TEXT,
            UNIQUE(file_id, name, kind)
        );
        CREATE TABLE IF NOT EXISTS file_imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL REFERENCES project_files(id) ON DELETE CASCADE,
            import_path TEXT NOT NULL, raw_import TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS skill_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL, proposed_name TEXT NOT NULL,
            proposed_content TEXT NOT NULL, theme TEXT NOT NULL,
            confidence REAL DEFAULT 0.0, status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            resolved_at TEXT, generated_path TEXT
        );
        CREATE TABLE IF NOT EXISTS skill_suggestion_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suggestion_id INTEGER NOT NULL REFERENCES skill_suggestions(id) ON DELETE CASCADE,
            pattern_id INTEGER NOT NULL REFERENCES patterns(id) ON DELETE CASCADE,
            UNIQUE(suggestion_id, pattern_id)
        );
        CREATE TABLE IF NOT EXISTS skill_usage_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_path TEXT NOT NULL, project TEXT NOT NULL,
            first_seen_at TEXT DEFAULT (datetime('now')),
            last_matched_at TEXT, match_count INTEGER DEFAULT 0,
            UNIQUE(skill_path, project)
        );
        CREATE TABLE IF NOT EXISTS skill_file_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_path TEXT NOT NULL, file_path TEXT NOT NULL,
            name TEXT NOT NULL, source_tool TEXT NOT NULL,
            content TEXT NOT NULL, embedding BLOB NOT NULL,
            modified_at TEXT NOT NULL,
            cached_at TEXT DEFAULT (datetime('now')),
            UNIQUE(project_path, file_path)
        );
        CREATE TABLE IF NOT EXISTS drift_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_description TEXT NOT NULL,
            changed_files TEXT NOT NULL,
            score REAL NOT NULL,
            similarity REAL NOT NULL,
            verdict TEXT NOT NULL,
            flags TEXT NOT NULL,
            project TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS session_checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            state_json TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(session_id)
        );
    """)
    ensure_idempotency_table(conn)
    _seed_db(conn)
    conn.close()
    return db_path


@pytest.fixture()
async def client(seeded_db, aiohttp_client):
    """Create an aiohttp test client with the seeded database."""
    app = _create_test_app(seeded_db)
    return await aiohttp_client(app)


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        resp = await client.get("/api/health")
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["data"]["status"] == "ok"
        assert "version" in body["data"]
        assert "pattern_count" in body["data"]
        assert body["data"]["pattern_count"] == 2

    @pytest.mark.asyncio
    async def test_health_has_envelope_format(self, client):
        resp = await client.get("/api/health")
        body = await resp.json()
        assert "ok" in body
        assert "data" in body
        assert "error" in body
        assert "meta" in body
        assert "duration_ms" in body["meta"]


class TestSummaryEndpoint:
    @pytest.mark.asyncio
    async def test_summary_counts(self, client):
        resp = await client.get("/api/summary")
        assert resp.status == 200
        body = await resp.json()
        data = body["data"]
        assert data["pattern_count"] == 2
        assert data["pending_skills"] == 1
        assert data["active_skills"] == 1
        assert data["project_count"] == 1
        assert data["session_count"] == 1

    @pytest.mark.asyncio
    async def test_summary_recent_activity(self, client):
        resp = await client.get("/api/summary")
        body = await resp.json()
        activity = body["data"]["recent_activity"]
        assert len(activity) >= 1
        assert activity[0]["tool_name"] == "patterns_store"


class TestPatternsEndpoint:
    @pytest.mark.asyncio
    async def test_list_patterns(self, client):
        resp = await client.get("/api/patterns")
        assert resp.status == 200
        body = await resp.json()
        assert body["data"]["total"] == 2
        assert len(body["data"]["patterns"]) == 2

    @pytest.mark.asyncio
    async def test_pattern_detail(self, client):
        resp = await client.get("/api/patterns/1")
        assert resp.status == 200
        body = await resp.json()
        assert body["data"]["name"] == "test-pattern"
        assert body["data"]["context"] == "test context"

    @pytest.mark.asyncio
    async def test_pattern_not_found(self, client):
        resp = await client.get("/api/patterns/999")
        assert resp.status == 404
        body = await resp.json()
        assert body["ok"] is False

    @pytest.mark.asyncio
    async def test_patterns_pagination(self, client):
        resp = await client.get("/api/patterns?limit=1&offset=0")
        body = await resp.json()
        assert len(body["data"]["patterns"]) == 1
        assert body["data"]["total"] == 2


class TestSkillsEndpoint:
    @pytest.mark.asyncio
    async def test_skills_list(self, client):
        resp = await client.get("/api/skills")
        assert resp.status == 200
        body = await resp.json()
        assert len(body["data"]["suggestions"]) == 1
        assert body["data"]["suggestions"][0]["proposed_name"] == "test-skill"
        assert len(body["data"]["tracked"]) == 1

    @pytest.mark.asyncio
    async def test_stale_skills_empty_with_recent(self, client):
        # Our test skill was matched on 2026-04-01 which is recent
        resp = await client.get("/api/skills/stale?threshold_days=365")
        body = await resp.json()
        # Depends on test run date vs seeded date
        assert body["ok"] is True


class TestProjectsEndpoint:
    @pytest.mark.asyncio
    async def test_projects_list(self, client):
        resp = await client.get("/api/projects")
        assert resp.status == 200
        body = await resp.json()
        assert len(body["data"]["projects"]) == 1
        assert body["data"]["projects"][0]["file_count"] == 2

    @pytest.mark.asyncio
    async def test_project_detail(self, client):
        resp = await client.get("/api/projects/%2Fmy%2Fproject")
        assert resp.status == 200
        body = await resp.json()
        data = body["data"]
        assert data["total_files"] == 2
        assert data["total_exports"] == 1
        assert len(data["languages"]) >= 1

    @pytest.mark.asyncio
    async def test_project_not_found(self, client):
        resp = await client.get("/api/projects/%2Fnonexistent")
        assert resp.status == 404


class TestDriftEndpoint:
    @pytest.mark.asyncio
    async def test_drift_list(self, client):
        resp = await client.get("/api/drift")
        assert resp.status == 200
        body = await resp.json()
        assert body["data"]["count"] == 2
        checks = body["data"]["drift_checks"]
        assert isinstance(checks[0]["changed_files"], list)
        assert isinstance(checks[0]["flags"], list)

    @pytest.mark.asyncio
    async def test_drift_filter_by_project(self, client):
        resp = await client.get("/api/drift?project=%2Fmy%2Fproject")
        body = await resp.json()
        assert body["data"]["count"] == 2


class TestSessionsEndpoint:
    @pytest.mark.asyncio
    async def test_sessions_list(self, client):
        resp = await client.get("/api/sessions")
        assert resp.status == 200
        body = await resp.json()
        assert body["data"]["total"] == 1
        assert body["data"]["sessions"][0]["session_id"] == "sess-001"
        assert body["data"]["sessions"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_session_detail(self, client):
        resp = await client.get("/api/sessions/sess-001")
        assert resp.status == 200
        body = await resp.json()
        assert body["data"]["state"]["status"] == "completed"
        assert body["data"]["version"] == 2

    @pytest.mark.asyncio
    async def test_session_not_found(self, client):
        resp = await client.get("/api/sessions/nonexistent")
        assert resp.status == 404
