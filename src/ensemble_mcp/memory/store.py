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

from ..config.defaults import DB_PATH, DEFAULT_PATTERN_CATEGORY, VALID_PATTERN_CATEGORIES
from ..contracts.errors import validation_error
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
        category: str | None = None,
    ) -> int:
        """Embed and store a new pattern. Returns the pattern ID.

        Text fields are redacted before storage. The ``category``
        defaults to ``DEFAULT_PATTERN_CATEGORY`` when not provided
        and is validated against ``VALID_PATTERN_CATEGORIES``.
        """
        if category is None:
            category = DEFAULT_PATTERN_CATEGORY
        if category not in VALID_PATTERN_CATEGORIES:
            raise validation_error(
                f"Invalid category '{category}'. "
                f"Must be one of: {', '.join(VALID_PATTERN_CATEGORIES)}",
                category=category,
            )

        name = redact(name)
        context = redact(context)
        approach = redact(approach)
        outcome = redact(outcome)

        # Front-load high-signal text for the 128-token window
        text = f"{name} {context} {approach}"
        embedding = self.model.embed(text)
        emb_blob = embedding.tobytes()

        cursor = self.conn.execute(
            "INSERT INTO patterns (name, context, approach, outcome, project, category, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, context, approach, outcome, project, category, emb_blob),
        )
        self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def search_patterns(
        self,
        query: str,
        top_k: int = 3,
        project: str | None = None,
        min_score: float = 0.3,
        category: str | None = None,
        detail_level: str = "full",
    ) -> list[dict[str, Any]]:
        """Semantic search over stored patterns.

        Args:
            query: Text to search for semantically.
            top_k: Maximum number of results.
            project: Scope results to a project (includes NULL-project patterns).
            min_score: Minimum cosine similarity threshold.
            category: Filter results to a specific pattern category.
            detail_level: ``"full"`` returns all fields; ``"index"`` returns
                compact metadata only (id, name, category, score, token_count).

        Note: This method has write side effects — it increments
        ``match_count`` and updates ``last_matched_at`` on matching
        patterns.  This tracking is used by ``prune_patterns`` to
        identify unused patterns.
        """
        query_embedding = self.model.embed(query)

        # Build WHERE clause dynamically for project + category filters
        conditions: list[str] = []
        params: list[str] = []
        if project:
            conditions.append("(project = ? OR project IS NULL)")
            params.append(project)
        if category:
            conditions.append("category = ?")
            params.append(category)

        sql = "SELECT id, embedding FROM patterns"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        rows = self.conn.execute(sql, params).fetchall()

        stored = [(row[0], np.frombuffer(row[1], dtype=np.float32)) for row in rows]
        matches = search_similar(query_embedding, stored, top_k, min_score)

        results: list[dict[str, Any]] = []
        for id_, score in matches:
            row = self.conn.execute(
                "SELECT name, context, approach, outcome, category FROM patterns WHERE id = ?",
                (id_,),
            ).fetchone()
            if row:
                self.conn.execute(
                    "UPDATE patterns SET last_matched_at = datetime('now'), "
                    "match_count = match_count + 1 WHERE id = ?",
                    (id_,),
                )
                pat_category = row[4] or DEFAULT_PATTERN_CATEGORY
                token_count = (
                    len(row[1]) + len(row[2]) + len(row[3])
                ) // 4  # ~4 chars/token approximation

                if detail_level == "index":
                    results.append(
                        {
                            "id": id_,
                            "name": row[0],
                            "category": pat_category,
                            "score": round(score, 3),
                            "token_count": token_count,
                        }
                    )
                else:
                    results.append(
                        {
                            "id": id_,
                            "name": row[0],
                            "context": row[1],
                            "approach": row[2],
                            "outcome": row[3],
                            "category": pat_category,
                            "score": round(score, 3),
                            "token_count": token_count,
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
