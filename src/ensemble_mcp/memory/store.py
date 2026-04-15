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
from ..memory.schema import ensure_schema
from ..memory.similarity import search_similar
from ..security.redaction import redact
from ..state.locks import get_connection

logger = logging.getLogger(__name__)


class VectorStore:
    """SQLite-backed storage for patterns and all server state.

    Manages:
    - Pattern embeddings (384-dim float32 BLOBs)
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
        """Create all tables if they do not exist and run migrations.

        Delegates to the shared ``ensure_schema()`` function in
        ``memory.schema`` — the single source of truth for DDL.
        """
        ensure_schema(self.conn)

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

        Note: This method has write side effects — it increments
        ``match_count`` and updates ``last_matched_at`` on matching
        patterns.  This tracking is used by ``prune_patterns`` to
        identify unused patterns.
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
