"""Eval-specific test fixtures.

Provides database connections, mock models, and snapshot data loaders
for benchmark tests.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from ensemble_mcp.memory.embeddings import EmbeddingModel
from ensemble_mcp.memory.store import VectorStore
from ensemble_mcp.state.idempotency import ensure_idempotency_table
from ensemble_mcp.state.locks import get_connection

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


class EvalMockEmbeddingModel(EmbeddingModel):
    """Deterministic embedding model for eval benchmarks."""

    def __init__(self) -> None:
        super().__init__(model_dir=Path("/dev/null"))
        self._session = MagicMock()
        self._tokenizer = MagicMock()

    def embed(self, text: str) -> np.ndarray:
        rng = np.random.RandomState(hash(text) % (2**31))
        vec = rng.randn(384).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        return [self.embed(t) for t in texts]

    def _load(self) -> None:
        pass

    def _ensure_model(self) -> None:
        pass


@pytest.fixture()
def snapshot_data() -> dict[str, list[dict]]:
    """Load all snapshot JSON files from evals/snapshots/."""
    data: dict[str, list[dict]] = {}
    for path in SNAPSHOTS_DIR.glob("*.json"):
        data[path.stem] = json.loads(path.read_text())
    return data


@pytest.fixture()
def eval_model() -> EvalMockEmbeddingModel:
    """Return a deterministic mock embedding model for evals."""
    return EvalMockEmbeddingModel()


@pytest.fixture()
def eval_conn(tmp_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Yield a clean SQLite connection with all tables for eval benchmarks."""
    db_path = tmp_path / "eval_data.db"
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
            UNIQUE(session_id)
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
        CREATE INDEX IF NOT EXISTS idx_drift_history_project
            ON drift_history(project);
        CREATE INDEX IF NOT EXISTS idx_drift_history_created
            ON drift_history(created_at);
    """)
    ensure_idempotency_table(conn)
    conn.commit()

    yield conn
    conn.close()


@pytest.fixture()
def eval_store(
    tmp_path: Path,
    eval_model: EvalMockEmbeddingModel,
) -> Generator[VectorStore, None, None]:
    """Yield a VectorStore backed by a temp DB and mock embeddings for evals."""
    db_path = tmp_path / "eval_store.db"
    store = VectorStore(db_path=db_path, model=eval_model)
    yield store
    store.close()
