"""Shared utilities for eval benchmarks.

Provides common helpers for percentile computation, async execution,
and database setup used across all benchmark modules.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

from ensemble_mcp.state.idempotency import ensure_idempotency_table
from ensemble_mcp.state.locks import get_connection


def percentile(data: list[float], p: int) -> float:
    """Compute the p-th percentile of a list of floats.

    Uses linear interpolation between the two nearest data points.
    Returns 0.0 for empty lists.

    Args:
        data: List of numeric values to compute percentile for.
        p: Percentile to compute (0-100).
    """
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[-1]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


def run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously.

    Wrapper around ``asyncio.run()`` for use in standalone benchmark scripts.
    """
    return asyncio.run(coro)


def make_eval_db(tmp_dir: Path) -> sqlite3.Connection:
    """Create a clean SQLite database with all required tables for eval benchmarks.

    Args:
        tmp_dir: Directory to place the database file in.

    Returns:
        An open SQLite connection with all tables created.
    """
    db_path = tmp_dir / "eval_data.db"
    conn = get_connection(db_path)

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        );

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
            project_path TEXT NOT NULL,
            file_path TEXT NOT NULL,
            language TEXT,
            role TEXT,
            size_bytes INTEGER DEFAULT 0,
            modified_at TEXT NOT NULL,
            indexed_at TEXT DEFAULT (datetime('now')),
            UNIQUE(project_path, file_path)
        );

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

        CREATE TABLE IF NOT EXISTS file_imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL
                REFERENCES project_files(id) ON DELETE CASCADE,
            import_path TEXT NOT NULL,
            raw_import TEXT NOT NULL
        );

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

        CREATE TABLE IF NOT EXISTS skill_suggestion_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suggestion_id INTEGER NOT NULL
                REFERENCES skill_suggestions(id) ON DELETE CASCADE,
            pattern_id INTEGER NOT NULL
                REFERENCES patterns(id) ON DELETE CASCADE,
            UNIQUE(suggestion_id, pattern_id)
        );

        CREATE TABLE IF NOT EXISTS skill_usage_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_path TEXT NOT NULL,
            project TEXT NOT NULL,
            first_seen_at TEXT DEFAULT (datetime('now')),
            last_matched_at TEXT,
            match_count INTEGER DEFAULT 0,
            UNIQUE(skill_path, project)
        );

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
        CREATE INDEX IF NOT EXISTS idx_session_checkpoints_status
            ON session_checkpoints(status);
        CREATE INDEX IF NOT EXISTS idx_session_checkpoints_project
            ON session_checkpoints(project);

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
    """)
    ensure_idempotency_table(conn)
    conn.commit()

    return conn
