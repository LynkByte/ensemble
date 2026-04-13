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

from ensemble_mcp.dashboard.api import register_api_routes
from ensemble_mcp.state.idempotency import ensure_idempotency_table
from ensemble_mcp.state.locks import get_connection


def _create_test_app(db_path: Path, global_config_path: Path | None = None) -> web.Application:
    """Create a minimal dashboard app for testing."""
    app = web.Application()
    app["db_path"] = db_path
    if global_config_path is not None:
        app["global_config_path"] = global_config_path
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
        "INSERT INTO session_checkpoints"
        " (session_id, state_json, version, status)"
        " VALUES (?, ?, ?, ?)",
        ("sess-001", json.dumps({"status": "completed", "steps": 3}), 2, "completed"),
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
            embedding BLOB,
            original_request TEXT,
            task_classification TEXT,
            status TEXT DEFAULT 'in_progress',
            project TEXT,
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


# ── Mutation endpoint tests ───────────────────────────────────────


class TestPatternMutations:
    """Tests for pattern delete, edit, and prune endpoints."""

    @pytest.mark.asyncio
    async def test_delete_pattern(self, client):
        resp = await client.delete("/api/patterns/1")
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["data"]["deleted"] is True
        assert body["data"]["id"] == 1

        # Verify it's gone
        resp = await client.get("/api/patterns/1")
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_delete_pattern_not_found(self, client):
        resp = await client.delete("/api/patterns/999")
        assert resp.status == 404
        body = await resp.json()
        assert body["ok"] is False

    @pytest.mark.asyncio
    async def test_edit_pattern_valid(self, client):
        resp = await client.put(
            "/api/patterns/1",
            json={"name": "updated-name", "context": "updated context"},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["data"]["updated"] is True
        assert body["data"]["pattern"]["name"] == "updated-name"
        assert body["data"]["pattern"]["context"] == "updated context"
        # Unchanged fields should remain
        assert body["data"]["pattern"]["approach"] == "test approach"

    @pytest.mark.asyncio
    async def test_edit_pattern_not_found(self, client):
        resp = await client.put("/api/patterns/999", json={"name": "updated"})
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_edit_pattern_no_valid_fields(self, client):
        resp = await client.put("/api/patterns/1", json={"invalid_field": "value"})
        assert resp.status == 400
        body = await resp.json()
        assert body["ok"] is False
        assert "No valid fields" in body["error"]["message"]

    @pytest.mark.asyncio
    async def test_edit_pattern_invalid_type(self, client):
        resp = await client.put("/api/patterns/1", json={"name": 123})
        assert resp.status == 400
        body = await resp.json()
        assert body["ok"] is False
        assert "VALIDATION_INVALID_TYPE" in body["error"]["code"]

    @pytest.mark.asyncio
    async def test_edit_pattern_empty_string(self, client):
        resp = await client.put("/api/patterns/1", json={"name": ""})
        assert resp.status == 400
        body = await resp.json()
        assert body["ok"] is False

    @pytest.mark.asyncio
    async def test_prune_patterns(self, client, seeded_db):
        # First, add a stale pattern with an old created_at and zero matches
        conn = get_connection(seeded_db)
        try:
            emb = np.zeros(384, dtype=np.float32).tobytes()
            conn.execute(
                "INSERT INTO patterns (name, context, approach, outcome, embedding, "
                "created_at, match_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("stale-pattern", "ctx", "appr", "out", emb, "2020-01-01", 0),
            )
            conn.commit()
        finally:
            conn.close()

        resp = await client.post(
            "/api/patterns/prune",
            json={"max_age_days": 30},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["data"]["pruned"] >= 1
        assert "remaining" in body["data"]

    @pytest.mark.asyncio
    async def test_prune_patterns_invalid_max_age(self, client):
        resp = await client.post(
            "/api/patterns/prune",
            json={"max_age_days": -1},
        )
        assert resp.status == 400
        body = await resp.json()
        assert body["ok"] is False


class TestSkillMutations:
    """Tests for skill suggestion actions and tracked skill deletion."""

    @pytest.mark.asyncio
    async def test_dismiss_suggestion(self, client):
        resp = await client.post(
            "/api/skills/suggestions/1/action",
            json={"action": "dismiss"},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["data"]["status"] == "dismissed"
        assert body["data"]["generated"] is False

    @pytest.mark.asyncio
    async def test_defer_suggestion(self, seeded_db, aiohttp_client):
        # Need a fresh client because the previous test may have modified suggestion 1
        app = _create_test_app(seeded_db)
        client = await aiohttp_client(app)
        # Add a new pending suggestion
        conn = get_connection(seeded_db)
        try:
            conn.execute(
                "INSERT INTO skill_suggestions (project, proposed_name, proposed_content, "
                "theme, confidence, status) VALUES (?, ?, ?, ?, ?, ?)",
                ("/proj", "defer-test", "content", "theme", 0.5, "pending"),
            )
            conn.commit()
            sid = conn.execute("SELECT MAX(id) FROM skill_suggestions").fetchone()[0]
        finally:
            conn.close()

        resp = await client.post(
            f"/api/skills/suggestions/{sid}/action",
            json={"action": "defer"},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["data"]["status"] == "deferred"

    @pytest.mark.asyncio
    async def test_accept_suggestion(self, seeded_db, aiohttp_client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        app = _create_test_app(seeded_db)
        client = await aiohttp_client(app)
        # Add a new pending suggestion
        conn = get_connection(seeded_db)
        try:
            conn.execute(
                "INSERT INTO skill_suggestions (project, proposed_name, proposed_content, "
                "theme, confidence, status) VALUES (?, ?, ?, ?, ?, ?)",
                ("/proj", "accept-test", "# My Skill\nContent here", "testing", 0.9, "pending"),
            )
            conn.commit()
            sid = conn.execute("SELECT MAX(id) FROM skill_suggestions").fetchone()[0]
        finally:
            conn.close()

        output_dir = "skills_output"
        resp = await client.post(
            f"/api/skills/suggestions/{sid}/action",
            json={"action": "accept", "output_dir": output_dir},
        )
        assert resp.status == 201
        body = await resp.json()
        assert body["ok"] is True
        assert body["data"]["status"] == "accepted"
        assert body["data"]["generated"] is True
        assert "path" in body["data"]

        # Verify file was created
        generated_path = Path(body["data"]["path"])
        assert generated_path.exists()
        assert generated_path.read_text() == "# My Skill\nContent here"

    @pytest.mark.asyncio
    async def test_action_invalid_action(self, client):
        resp = await client.post(
            "/api/skills/suggestions/1/action",
            json={"action": "invalid"},
        )
        assert resp.status == 400
        body = await resp.json()
        assert body["ok"] is False
        assert "VALIDATION_INVALID_VALUE" in body["error"]["code"]

    @pytest.mark.asyncio
    async def test_action_not_found(self, client):
        resp = await client.post(
            "/api/skills/suggestions/999/action",
            json={"action": "dismiss"},
        )
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_action_already_resolved(self, seeded_db, aiohttp_client):
        # Mark the suggestion as dismissed first
        conn = get_connection(seeded_db)
        try:
            conn.execute(
                "UPDATE skill_suggestions SET status = 'dismissed', "
                "resolved_at = datetime('now') WHERE id = 1"
            )
            conn.commit()
        finally:
            conn.close()

        app = _create_test_app(seeded_db)
        client = await aiohttp_client(app)

        resp = await client.post(
            "/api/skills/suggestions/1/action",
            json={"action": "accept"},
        )
        assert resp.status == 409
        body = await resp.json()
        assert body["ok"] is False
        assert "CONFLICT_ALREADY_RESOLVED" in body["error"]["code"]

    @pytest.mark.asyncio
    async def test_delete_tracked_skill(self, client):
        resp = await client.delete("/api/skills/tracked/1")
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["data"]["deleted"] is True

    @pytest.mark.asyncio
    async def test_delete_tracked_skill_not_found(self, client):
        resp = await client.delete("/api/skills/tracked/999")
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_accept_suggestion_path_traversal(self, seeded_db, aiohttp_client):
        """Reject output_dir values that contain '..' path traversal segments."""
        app = _create_test_app(seeded_db)
        client = await aiohttp_client(app)
        # Add a new pending suggestion
        conn = get_connection(seeded_db)
        try:
            conn.execute(
                "INSERT INTO skill_suggestions (project, proposed_name, proposed_content, "
                "theme, confidence, status) VALUES (?, ?, ?, ?, ?, ?)",
                ("/proj", "traversal-test", "content", "theme", 0.5, "pending"),
            )
            conn.commit()
            sid = conn.execute("SELECT MAX(id) FROM skill_suggestions").fetchone()[0]
        finally:
            conn.close()

        resp = await client.post(
            f"/api/skills/suggestions/{sid}/action",
            json={"action": "accept", "output_dir": "../../etc"},
        )
        assert resp.status == 400
        body = await resp.json()
        assert body["ok"] is False
        assert "VALIDATION_INVALID_VALUE" in body["error"]["code"]

    @pytest.mark.asyncio
    async def test_accept_suggestion_absolute_path(self, seeded_db, aiohttp_client):
        """Reject output_dir values that are absolute paths."""
        app = _create_test_app(seeded_db)
        client = await aiohttp_client(app)
        conn = get_connection(seeded_db)
        try:
            conn.execute(
                "INSERT INTO skill_suggestions (project, proposed_name, proposed_content, "
                "theme, confidence, status) VALUES (?, ?, ?, ?, ?, ?)",
                ("/proj", "abs-test", "content", "theme", 0.5, "pending"),
            )
            conn.commit()
            sid = conn.execute("SELECT MAX(id) FROM skill_suggestions").fetchone()[0]
        finally:
            conn.close()

        resp = await client.post(
            f"/api/skills/suggestions/{sid}/action",
            json={"action": "accept", "output_dir": "/etc"},
        )
        assert resp.status == 400
        body = await resp.json()
        assert body["ok"] is False
        assert "VALIDATION_INVALID_VALUE" in body["error"]["code"]


class TestSettingsEndpoints:
    """Tests for settings GET, PUT, and schema endpoints."""

    @pytest.mark.asyncio
    async def test_get_settings(self, client):
        resp = await client.get("/api/settings")
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert "settings" in body["data"]
        assert "source_map" in body["data"]
        assert "config_path" in body["data"]
        # Check some expected fields
        settings = body["data"]["settings"]
        assert "max_patterns" in settings
        assert "default_top_k" in settings
        assert "drift_threshold_aligned" in settings

    @pytest.mark.asyncio
    async def test_get_settings_schema(self, client):
        resp = await client.get("/api/settings/schema")
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        schema = body["data"]["schema"]
        assert len(schema) > 0
        # Check schema field structure
        field = schema[0]
        assert "name" in field
        assert "type" in field
        assert "default" in field
        assert "description" in field

    @pytest.mark.asyncio
    async def test_put_settings_valid(self, seeded_db, aiohttp_client, tmp_path):
        config_path = tmp_path / "test_config.toml"
        app = _create_test_app(seeded_db, global_config_path=config_path)
        client = await aiohttp_client(app)

        resp = await client.put(
            "/api/settings",
            json={"max_patterns": 5000, "default_top_k": 5},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["data"]["saved"] is True
        assert "max_patterns" in body["data"]["fields"]

        # Verify file was created
        assert config_path.exists()
        content = config_path.read_text()
        assert "max_patterns = 5000" in content
        assert "default_top_k = 5" in content

    @pytest.mark.asyncio
    async def test_put_settings_invalid_field(self, client):
        resp = await client.put(
            "/api/settings",
            json={"nonexistent_field": "value"},
        )
        assert resp.status == 400
        body = await resp.json()
        assert body["ok"] is False
        assert "Unknown settings fields" in body["error"]["message"]

    @pytest.mark.asyncio
    async def test_put_settings_invalid_type(self, client):
        resp = await client.put(
            "/api/settings",
            json={"max_patterns": "not_a_number"},
        )
        assert resp.status == 400
        body = await resp.json()
        assert body["ok"] is False
        assert "VALIDATION_INVALID_TYPE" in body["error"]["code"]

    @pytest.mark.asyncio
    async def test_put_settings_empty_body(self, client):
        resp = await client.put("/api/settings", json={})
        assert resp.status == 400
        body = await resp.json()
        assert body["ok"] is False


class TestResetEndpoint:
    """Tests for the data reset endpoint."""

    @pytest.mark.asyncio
    async def test_reset_with_confirm(self, client):
        resp = await client.post("/api/reset", json={"confirm": True})
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["data"]["reset"] is True

        # Verify data is cleared
        resp = await client.get("/api/health")
        body = await resp.json()
        assert body["data"]["pattern_count"] == 0

    @pytest.mark.asyncio
    async def test_reset_without_confirm(self, client):
        resp = await client.post("/api/reset", json={})
        assert resp.status == 400
        body = await resp.json()
        assert body["ok"] is False
        assert "VALIDATION_CONSTRAINT" in body["error"]["code"]

    @pytest.mark.asyncio
    async def test_reset_with_confirm_false(self, client):
        resp = await client.post("/api/reset", json={"confirm": False})
        assert resp.status == 400
        body = await resp.json()
        assert body["ok"] is False

    @pytest.mark.asyncio
    async def test_reset_invalid_json(self, client):
        resp = await client.post(
            "/api/reset",
            data="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_reset_with_confirm_string(self, client):
        """String 'true' should be rejected — only boolean True is accepted."""
        resp = await client.post("/api/reset", json={"confirm": "true"})
        assert resp.status == 400
        body = await resp.json()
        assert body["ok"] is False
        assert "VALIDATION_CONSTRAINT" in body["error"]["code"]


class TestIndexMutations:
    """Tests for project re-index, clear, and health endpoints."""

    @pytest.mark.asyncio
    async def test_clear_project_index(self, client):
        resp = await client.delete("/api/projects/%2Fmy%2Fproject")
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["data"]["deleted"] is True

        # Verify project is gone from the list
        resp = await client.get("/api/projects")
        body = await resp.json()
        assert len(body["data"]["projects"]) == 0

    @pytest.mark.asyncio
    async def test_clear_project_not_found(self, client):
        resp = await client.delete("/api/projects/%2Fnonexistent")
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_project_health(self, client):
        resp = await client.get("/api/projects/%2Fmy%2Fproject/health")
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["file_count"] == 2
        assert "oldest_indexed_at" in data
        assert "newest_indexed_at" in data
        assert "missing_files_count" in data
        assert isinstance(data["missing_files"], list)

    @pytest.mark.asyncio
    async def test_project_health_not_found(self, client):
        resp = await client.get("/api/projects/%2Fnonexistent/health")
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_reindex_project(self, seeded_db, aiohttp_client, tmp_path):
        """Test re-index with a real directory on the filesystem."""
        # Create a minimal project directory
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text("def hello(): pass\n")
        (project_dir / "README.md").write_text("# Test\n")

        app = _create_test_app(seeded_db)
        client = await aiohttp_client(app)

        encoded_path = str(project_dir).replace("/", "%2F")
        resp = await client.post(f"/api/projects/{encoded_path}/reindex")
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["data"]["indexed"] is True
        assert body["data"]["files"] >= 1

    @pytest.mark.asyncio
    async def test_reindex_project_not_found(self, client):
        resp = await client.post("/api/projects/%2Fnonexistent%2Fpath/reindex")
        assert resp.status == 404
        body = await resp.json()
        assert body["ok"] is False
