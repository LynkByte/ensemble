"""Shared database schema: DDL and forward-only migrations.

Single source of truth for all ``CREATE TABLE`` statements, indexes,
and migration logic.  Consumers call ``ensure_schema(conn)`` instead
of embedding DDL inline.

Pattern follows ``state/idempotency.py::ensure_idempotency_table``.
"""

from __future__ import annotations

import contextlib
import sqlite3

from ..state.idempotency import ensure_idempotency_table

# Current schema version — bump when adding new migrations.
SCHEMA_VERSION = 9


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if they do not exist, then run migrations.

    Safe to call multiple times — all statements are idempotent
    (``CREATE TABLE IF NOT EXISTS``, ``CREATE INDEX IF NOT EXISTS``).
    Forward-only migrations are gated on ``schema_version`` so each
    ALTER TABLE runs at most once per database.
    """
    conn.executescript("""
        -- Schema versioning
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        );

        -- Patterns
        CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            context TEXT NOT NULL,
            approach TEXT NOT NULL,
            outcome TEXT NOT NULL,
            project TEXT,
            category TEXT DEFAULT 'general',
            embedding BLOB NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            last_matched_at TEXT,
            match_count INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_patterns_project
            ON patterns(project);
        CREATE INDEX IF NOT EXISTS idx_patterns_created
            ON patterns(created_at);

        -- MCP Calls
        CREATE TABLE IF NOT EXISTS mcp_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT NOT NULL,
            input_bytes INTEGER DEFAULT 0,
            output_bytes INTEGER DEFAULT 0,
            duration_ms INTEGER,
            called_at TEXT DEFAULT (datetime('now'))
        );

        -- Project Files (Codebase Index)
        CREATE TABLE IF NOT EXISTS project_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_path TEXT NOT NULL,
            file_path TEXT NOT NULL,
            language TEXT,
            role TEXT,
            size_bytes INTEGER DEFAULT 0,
            modified_at TEXT NOT NULL,
            indexed_at TEXT DEFAULT (datetime('now')),
            UNIQUE(project_path, file_path)
        );
        CREATE INDEX IF NOT EXISTS idx_project_files_project
            ON project_files(project_path);
        CREATE INDEX IF NOT EXISTS idx_project_files_lang
            ON project_files(project_path, language);
        CREATE INDEX IF NOT EXISTS idx_project_files_role
            ON project_files(project_path, role);

        -- File Exports
        CREATE TABLE IF NOT EXISTS file_exports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL
                REFERENCES project_files(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            line_number INTEGER,
            signature TEXT,
            docstring TEXT,
            UNIQUE(file_id, name, kind)
        );
        CREATE INDEX IF NOT EXISTS idx_file_exports_file
            ON file_exports(file_id);
        CREATE INDEX IF NOT EXISTS idx_file_exports_name
            ON file_exports(name);

        -- File Imports
        CREATE TABLE IF NOT EXISTS file_imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL
                REFERENCES project_files(id) ON DELETE CASCADE,
            import_path TEXT NOT NULL,
            raw_import TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_file_imports_file
            ON file_imports(file_id);
        CREATE INDEX IF NOT EXISTS idx_file_imports_path
            ON file_imports(import_path);

        -- Skill Suggestions
        CREATE TABLE IF NOT EXISTS skill_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            proposed_name TEXT NOT NULL,
            proposed_content TEXT NOT NULL,
            theme TEXT NOT NULL,
            confidence REAL DEFAULT 0.0,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            resolved_at TEXT,
            generated_path TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_skill_suggestions_project
            ON skill_suggestions(project);
        CREATE INDEX IF NOT EXISTS idx_skill_suggestions_status
            ON skill_suggestions(status);

        -- Skill Suggestion <-> Pattern junction
        CREATE TABLE IF NOT EXISTS skill_suggestion_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suggestion_id INTEGER NOT NULL
                REFERENCES skill_suggestions(id) ON DELETE CASCADE,
            pattern_id INTEGER NOT NULL
                REFERENCES patterns(id) ON DELETE CASCADE,
            UNIQUE(suggestion_id, pattern_id)
        );
        CREATE INDEX IF NOT EXISTS idx_ssp_suggestion
            ON skill_suggestion_patterns(suggestion_id);
        CREATE INDEX IF NOT EXISTS idx_ssp_pattern
            ON skill_suggestion_patterns(pattern_id);

        -- Skill Usage Tracking
        CREATE TABLE IF NOT EXISTS skill_usage_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_path TEXT NOT NULL,
            project TEXT NOT NULL,
            first_seen_at TEXT DEFAULT (datetime('now')),
            last_matched_at TEXT,
            match_count INTEGER DEFAULT 0,
            UNIQUE(skill_path, project)
        );
        CREATE INDEX IF NOT EXISTS idx_skill_usage_project
            ON skill_usage_tracking(project);
        CREATE INDEX IF NOT EXISTS idx_skill_usage_last_matched
            ON skill_usage_tracking(last_matched_at);

        -- Skill File Cache (mtime-based, mirrors project_index pattern)
        CREATE TABLE IF NOT EXISTS skill_file_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_path TEXT NOT NULL,
            file_path TEXT NOT NULL,
            name TEXT NOT NULL,
            source_tool TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding BLOB NOT NULL,
            modified_at TEXT NOT NULL,
            cached_at TEXT DEFAULT (datetime('now')),
            UNIQUE(project_path, file_path)
        );
        CREATE INDEX IF NOT EXISTS idx_skill_cache_project
            ON skill_file_cache(project_path);

        -- Drift History
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
        CREATE INDEX IF NOT EXISTS idx_drift_history_project
            ON drift_history(project);
        CREATE INDEX IF NOT EXISTS idx_drift_history_created
            ON drift_history(created_at);

        -- Session Checkpoints
        CREATE TABLE IF NOT EXISTS session_checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            state_json TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(session_id)
        );

        -- Project Snapshots (cached project baseline summaries)
        CREATE TABLE IF NOT EXISTS project_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_path TEXT NOT NULL UNIQUE,
            snapshot_json TEXT NOT NULL,
            files_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT DEFAULT (datetime('now', '+24 hours'))
        );
        CREATE INDEX IF NOT EXISTS idx_project_snapshots_path
            ON project_snapshots(project_path);
        CREATE INDEX IF NOT EXISTS idx_project_snapshots_expires
            ON project_snapshots(expires_at);
    """)

    # Idempotency table in its own module
    ensure_idempotency_table(conn)

    # ── Forward-only migrations ────────────────────────────────
    existing = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    if existing is None:
        existing = 0

    if existing < 5:
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE file_exports ADD COLUMN signature TEXT")
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE file_exports ADD COLUMN docstring TEXT")

    if existing < 7:
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE session_checkpoints ADD COLUMN embedding BLOB")
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE session_checkpoints ADD COLUMN original_request TEXT")
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE session_checkpoints ADD COLUMN task_classification TEXT")
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE session_checkpoints ADD COLUMN status TEXT DEFAULT 'running'")
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE session_checkpoints ADD COLUMN project TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_checkpoints_status "
            "ON session_checkpoints(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_checkpoints_project "
            "ON session_checkpoints(project)"
        )

    # v8: project_snapshots table (created in executescript above for new DBs;
    # existing DBs get it via CREATE TABLE IF NOT EXISTS in the script).
    if existing < 8:
        # No additional ALTER TABLE needed — the table is created idempotently
        # by CREATE TABLE IF NOT EXISTS in the executescript block above.
        pass

    # v9: Add category column to patterns table for structured pattern
    # categories and filtering.
    if existing < 9:
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE patterns ADD COLUMN category TEXT DEFAULT 'general'")
    # Create the index idempotently — safe whether column came from CREATE TABLE
    # (new DB) or from the ALTER TABLE migration above (old DB).
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_patterns_category ON patterns(category)")

    if existing < SCHEMA_VERSION:
        conn.execute(
            "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
    conn.commit()
