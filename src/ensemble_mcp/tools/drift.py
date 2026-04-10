"""Drift tool: drift_check.

Cosine similarity between task description embedding and change
embedding to detect scope drift. Returns a 0-1 score with flags and verdict.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..config.defaults import (
    DRIFT_THRESHOLD_ALIGNED,
    DRIFT_THRESHOLD_MINOR,
    SUSPICIOUS_FILE_PATTERNS,
    SUSPICIOUS_FILE_SIMILARITY_THRESHOLD,
)
from ..contracts.envelope import tool_handler
from ..memory.embeddings import EmbeddingModel
from ..memory.similarity import cosine_similarity
from ..state.idempotency import check_idempotency, store_idempotency


@tool_handler(source="local", confidence="exact")
async def drift_check(
    model: EmbeddingModel,
    conn: sqlite3.Connection,
    *,
    task_description: str,
    changed_files: list[str],
    diff_summary: str,
    project: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Check if code changes drift from the original task.

    Returns a 0-1 score (0 = no drift, 1 = complete drift) plus
    specific flags and a verdict.
    """
    cached = check_idempotency(conn, idempotency_key)
    if cached is not None:
        return cached

    # Embed task and diff
    task_emb = model.embed(task_description)
    diff_emb = model.embed(diff_summary)

    # Core similarity
    similarity = cosine_similarity(task_emb, diff_emb)
    drift_score = 1.0 - similarity  # Higher = more drift

    flags: list[str] = []

    # Check for suspicious file patterns not mentioned in the task
    for filepath in changed_files:
        for pattern in SUSPICIOUS_FILE_PATTERNS:
            if pattern in filepath.lower():
                file_emb = model.embed(filepath)
                file_sim = cosine_similarity(task_emb, file_emb)
                if file_sim < SUSPICIOUS_FILE_SIMILARITY_THRESHOLD:
                    flags.append(f"Unexpected file change: {filepath}")
                break  # one flag per file

    # Determine verdict
    if drift_score < DRIFT_THRESHOLD_ALIGNED:
        verdict = "aligned"
    elif drift_score < DRIFT_THRESHOLD_MINOR:
        verdict = "minor_drift"
    else:
        verdict = "significant_drift"

    result = {
        "score": round(drift_score, 3),
        "similarity": round(similarity, 3),
        "flags": flags,
        "verdict": verdict,
    }

    # Persist drift result for dashboard history
    _persist_drift_history(
        conn,
        task_description=task_description,
        changed_files=changed_files,
        score=round(drift_score, 3),
        similarity=round(similarity, 3),
        verdict=verdict,
        flags=flags,
        project=project,
    )

    store_idempotency(conn, idempotency_key, result)
    return result


def _persist_drift_history(
    conn: sqlite3.Connection,
    *,
    task_description: str,
    changed_files: list[str],
    score: float,
    similarity: float,
    verdict: str,
    flags: list[str],
    project: str | None,
) -> None:
    """Write a drift check result to the drift_history table."""
    conn.execute(
        "INSERT INTO drift_history "
        "(task_description, changed_files, score, similarity, verdict, flags, project) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            task_description,
            json.dumps(changed_files),
            score,
            similarity,
            verdict,
            json.dumps(flags),
            project,
        ),
    )
    conn.commit()
