"""SQLite-backed vector store.

Stores embeddings as BLOBs in SQLite. Uses WAL mode for concurrent access
and schema_version table for forward-only migrations.

This is the central data layer — all tables live in a single SQLite DB
at ``~/.cache/ensemble-mcp/data.db``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from ..config.defaults import DB_PATH
from ..memory.embeddings import EmbeddingModel
from ..memory.similarity import search_similar
from ..security.redaction import redact
from ..state.idempotency import ensure_idempotency_table
from ..state.locks import get_connection

logger = logging.getLogger(__name__)

# Current schema version — bump when adding new migrations.
SCHEMA_VERSION = 2


class VectorStore:
    """SQLite-backed storage for patterns, sessions, and all server state.

    Manages:
    - Pattern embeddings (384-dim float32 BLOBs)
    - Sessions and steps
    - MCP call tracking
    - Codebase file index
    - Skill suggestions and usage tracking
    - Idempotency keys
    - Session checkpoints
    """

    def __init__(
        self,
        db_path: Path = DB_PATH,
        model: EmbeddingModel | None = None,
    ) -> None:
        self.db_path = db_path
        self.conn = get_connection(db_path)
        self.model = model or EmbeddingModel()
        self._create_tables()

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()

    # ── Schema ────────────────────────────────────────────────────

    def _create_tables(self) -> None:
        """Create all tables if they do not exist and run migrations."""
        self.conn.executescript("""
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
                embedding BLOB NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                last_matched_at TEXT,
                match_count INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_patterns_project
                ON patterns(project);
            CREATE INDEX IF NOT EXISTS idx_patterns_created
                ON patterns(created_at);

            -- Sessions
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                task TEXT NOT NULL,
                classification TEXT NOT NULL,
                ai_tool TEXT,
                project TEXT,
                state TEXT DEFAULT 'pending',
                started_at TEXT DEFAULT (datetime('now')),
                ended_at TEXT,
                status TEXT,
                total_input_tokens INTEGER DEFAULT 0,
                total_output_tokens INTEGER DEFAULT 0,
                total_cached_tokens INTEGER DEFAULT 0,
                total_cost_usd REAL DEFAULT 0,
                report_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_project
                ON sessions(project);
            CREATE INDEX IF NOT EXISTS idx_sessions_started
                ON sessions(started_at);

            -- Steps
            CREATE TABLE IF NOT EXISTS steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                agent TEXT NOT NULL,
                model TEXT,
                model_canonical_name TEXT,
                state TEXT DEFAULT 'pending',
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read_tokens INTEGER DEFAULT 0,
                cache_write_tokens INTEGER DEFAULT 0,
                web_search_requests INTEGER DEFAULT 0,
                cached_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0,
                pricing_version TEXT,
                source TEXT DEFAULT 'estimator',
                duration_ms INTEGER,
                unknown_model_cost INTEGER DEFAULT 0,
                accuracy TEXT DEFAULT 'estimated',
                reasoning_tokens INTEGER DEFAULT 0,
                started_at TEXT DEFAULT (datetime('now')),
                ended_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_steps_session
                ON steps(session_id);

            -- MCP Calls
            CREATE TABLE IF NOT EXISTS mcp_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT REFERENCES sessions(id),
                tool_name TEXT NOT NULL,
                input_bytes INTEGER DEFAULT 0,
                output_bytes INTEGER DEFAULT 0,
                duration_ms INTEGER,
                called_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_mcp_calls_session
                ON mcp_calls(session_id);

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

            -- Session Checkpoints
            CREATE TABLE IF NOT EXISTS session_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(session_id)
            );
        """)

        # Idempotency table in its own module
        ensure_idempotency_table(self.conn)

        # ── Forward-only migrations ────────────────────────────────
        existing = self.conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        if existing is None:
            existing = 0

        # v2: add reasoning_tokens column to steps table
        if existing < 2:
            # Check whether the column already exists (fresh DBs have it
            # from the CREATE TABLE above; only upgraded DBs need ALTER).
            cols = {row[1] for row in self.conn.execute("PRAGMA table_info(steps)").fetchall()}
            if "reasoning_tokens" not in cols:
                self.conn.execute("ALTER TABLE steps ADD COLUMN reasoning_tokens INTEGER DEFAULT 0")

        if existing < SCHEMA_VERSION:
            self.conn.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
        self.conn.commit()

    # ── Pattern operations ────────────────────────────────────────

    def store_pattern(
        self,
        name: str,
        context: str,
        approach: str,
        outcome: str,
        project: str | None = None,
    ) -> int:
        """Embed and store a new pattern. Returns the pattern ID.

        Text fields are redacted before storage.
        """
        name = redact(name)
        context = redact(context)
        approach = redact(approach)
        outcome = redact(outcome)

        # Front-load high-signal text for the 128-token window
        text = f"{name} {context} {approach}"
        embedding = self.model.embed(text)
        emb_blob = embedding.tobytes()

        cursor = self.conn.execute(
            "INSERT INTO patterns (name, context, approach, outcome, project, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, context, approach, outcome, project, emb_blob),
        )
        self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def search_patterns(
        self,
        query: str,
        top_k: int = 3,
        project: str | None = None,
        min_score: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Semantic search over stored patterns.

        Updates ``match_count`` and ``last_matched_at`` for returned results.
        """
        query_embedding = self.model.embed(query)

        if project:
            rows = self.conn.execute(
                "SELECT id, embedding FROM patterns WHERE project = ? OR project IS NULL",
                (project,),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT id, embedding FROM patterns").fetchall()

        stored = [(row[0], np.frombuffer(row[1], dtype=np.float32)) for row in rows]
        matches = search_similar(query_embedding, stored, top_k, min_score)

        results: list[dict[str, Any]] = []
        for id_, score in matches:
            row = self.conn.execute(
                "SELECT name, context, approach, outcome FROM patterns WHERE id = ?",
                (id_,),
            ).fetchone()
            if row:
                self.conn.execute(
                    "UPDATE patterns SET last_matched_at = datetime('now'), "
                    "match_count = match_count + 1 WHERE id = ?",
                    (id_,),
                )
                results.append(
                    {
                        "id": id_,
                        "name": row[0],
                        "context": row[1],
                        "approach": row[2],
                        "outcome": row[3],
                        "score": round(score, 3),
                    }
                )
        self.conn.commit()
        return results

    def prune_patterns(
        self,
        max_age_days: int = 90,
        min_score: float = 0.3,  # noqa: ARG002
    ) -> tuple[int, int]:
        """Remove old patterns with zero matches.

        Returns ``(pruned_count, remaining_count)``.
        """
        cursor = self.conn.execute(
            "DELETE FROM patterns WHERE "
            "created_at < datetime('now', ? || ' days') AND match_count = 0",
            (f"-{max_age_days}",),
        )
        pruned = cursor.rowcount
        remaining = int(self.conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0])
        self.conn.commit()
        return pruned, remaining

    def get_pattern_count(self) -> int:
        """Return the total number of stored patterns."""
        return int(self.conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0])

    def get_db_size_bytes(self) -> int:
        """Return the database file size in bytes."""
        if self.db_path.exists():
            return self.db_path.stat().st_size
        return 0
