"""Tests for memory/schema.py — shared DDL and migrations."""

from __future__ import annotations

from pathlib import Path

from ensemble_mcp.memory.schema import SCHEMA_VERSION, ensure_schema
from ensemble_mcp.state.locks import get_connection


class TestEnsureSchema:
    def test_creates_all_tables(self, tmp_path: Path):
        """ensure_schema() should create every expected table."""
        db_path = tmp_path / "test_schema.db"
        conn = get_connection(db_path)
        try:
            ensure_schema(conn)

            # Query sqlite_master for table names
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            table_names = {row[0] for row in rows}

            expected_tables = {
                "schema_version",
                "patterns",
                "mcp_calls",
                "project_files",
                "file_exports",
                "file_imports",
                "skill_suggestions",
                "skill_suggestion_patterns",
                "skill_usage_tracking",
                "skill_file_cache",
                "drift_history",
                "session_checkpoints",
                "project_snapshots",
                "idempotency_keys",
            }
            assert expected_tables.issubset(table_names)
        finally:
            conn.close()

    def test_idempotent_call(self, tmp_path: Path):
        """Calling ensure_schema() twice on the same DB is safe."""
        db_path = tmp_path / "test_idempotent.db"
        conn = get_connection(db_path)
        try:
            ensure_schema(conn)
            ensure_schema(conn)  # Should not raise

            # Verify schema_version is set correctly
            version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
            assert version == SCHEMA_VERSION
        finally:
            conn.close()

    def test_schema_version_is_set(self, tmp_path: Path):
        """ensure_schema() should set the schema version."""
        db_path = tmp_path / "test_version.db"
        conn = get_connection(db_path)
        try:
            ensure_schema(conn)
            version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
            assert version == SCHEMA_VERSION
            assert isinstance(SCHEMA_VERSION, int)
            assert SCHEMA_VERSION >= 8
        finally:
            conn.close()

    def test_migrations_run_on_old_schema(self, tmp_path: Path):
        """Forward-only migrations should add columns to old tables."""
        db_path = tmp_path / "test_migrations.db"
        conn = get_connection(db_path)
        try:
            # Create a minimal old schema (pre-v5 — no signature/docstring)
            conn.executescript("""
                CREATE TABLE schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT DEFAULT (datetime('now'))
                );
                INSERT INTO schema_version (version) VALUES (1);

                CREATE TABLE file_exports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    line_number INTEGER,
                    UNIQUE(file_id, name, kind)
                );

                CREATE TABLE session_checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(session_id)
                );
            """)
            conn.commit()

            # Now run ensure_schema — it should add missing columns
            ensure_schema(conn)

            # Verify signature column was added to file_exports
            cursor = conn.execute("PRAGMA table_info(file_exports)")
            columns = {row[1] for row in cursor.fetchall()}
            assert "signature" in columns
            assert "docstring" in columns

            # Verify session_checkpoints got new columns
            cursor = conn.execute("PRAGMA table_info(session_checkpoints)")
            columns = {row[1] for row in cursor.fetchall()}
            assert "embedding" in columns
            assert "original_request" in columns
            assert "status" in columns
            assert "project" in columns
        finally:
            conn.close()
