"""Session tools: session_save, session_load, session_search.

Pipeline checkpoint state with optimistic versioning and semantic search.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from ..config.defaults import SESSION_DEFAULT_TOP_K, SESSION_MIN_SCORE
from ..contracts.envelope import tool_handler
from ..contracts.errors import ErrorCode, ToolError
from ..memory.similarity import search_similar
from ..memory.store import VectorStore
from ..security.redaction import redact
from ..state.idempotency import check_idempotency, store_idempotency


@tool_handler(source="sqlite", confidence="exact")
async def session_save(
    store: VectorStore,
    *,
    session_id: str,
    state: dict[str, Any],
    version: int | None = None,
    original_request: str | None = None,
    decisions: list[str] | None = None,
    completed_steps: list[str] | None = None,
    remaining_steps: list[str] | None = None,
    files_changed: list[str] | None = None,
    errors: list[str] | None = None,
    context_for_resume: str | None = None,
    task_classification: str | None = None,
    status: str | None = None,
    project: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Save pipeline checkpoint state with optimistic versioning.

    If ``version`` is provided, it must match the current version in the
    database — otherwise a ``CONFLICT_VERSION_MISMATCH`` is raised.

    When ``original_request`` is provided, an embedding is generated for
    semantic search via ``session_search``. Resume-related fields are
    merged into ``state`` under a ``resume`` key and also stored in
    dedicated columns for SQL-level filtering.
    """
    conn = store.conn

    cached = check_idempotency(conn, idempotency_key)
    if cached is not None:
        return cached

    # Build resume sub-dict from optional structured fields
    resume: dict[str, Any] = {}
    if original_request is not None:
        resume["original_request"] = original_request
    if decisions is not None:
        resume["decisions"] = decisions
    if completed_steps is not None:
        resume["completed_steps"] = completed_steps
    if remaining_steps is not None:
        resume["remaining_steps"] = remaining_steps
    if files_changed is not None:
        resume["files_changed"] = files_changed
    if errors is not None:
        resume["errors"] = errors
    if context_for_resume is not None:
        resume["context_for_resume"] = context_for_resume
    if task_classification is not None:
        resume["task_classification"] = task_classification
    if status is not None:
        resume["status"] = status
    if project is not None:
        resume["project"] = project

    # Merge resume fields into state dict (preserving existing keys)
    if resume:
        state = {**state, "resume": resume}

    state_json = json.dumps(state)

    # Redact original_request before storage AND embedding (matches
    # pattern store convention — see memory/store.py)
    if original_request is not None:
        original_request = redact(original_request)

    # Generate embedding from original_request if provided
    emb_blob: bytes | None = None
    if original_request is not None:
        embedding = store.model.embed(original_request)
        emb_blob = embedding.tobytes()

    # Default status: "in_progress" when caller omits status.
    # Applied to both INSERT and UPDATE so behaviour is consistent —
    # passing status=None always means "in_progress", not "keep old".
    effective_status = status or "in_progress"

    # Check for existing checkpoint
    existing = conn.execute(
        "SELECT version FROM session_checkpoints WHERE session_id = ?",
        (session_id,),
    ).fetchone()

    if existing is not None:
        current_version = existing[0]
        if version is not None and version != current_version:
            raise ToolError(
                code=ErrorCode.CONFLICT_VERSION_MISMATCH,
                message=(
                    f"Version mismatch for session {session_id}: "
                    f"expected {version}, current is {current_version}"
                ),
                details={
                    "session_id": session_id,
                    "expected_version": version,
                    "current_version": current_version,
                },
            )
        new_version = current_version + 1
        conn.execute(
            "UPDATE session_checkpoints SET state_json = ?, version = ?, "
            "created_at = datetime('now'), "
            "original_request = COALESCE(?, original_request), "
            "task_classification = COALESCE(?, task_classification), "
            "status = ?, "
            "project = COALESCE(?, project), "
            "embedding = COALESCE(?, embedding) "
            "WHERE session_id = ?",
            (
                state_json,
                new_version,
                original_request,
                task_classification,
                effective_status,
                project,
                emb_blob,
                session_id,
            ),
        )
    else:
        new_version = 1
        conn.execute(
            "INSERT INTO session_checkpoints "
            "(session_id, state_json, version, original_request, "
            "task_classification, status, project, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                state_json,
                new_version,
                original_request,
                task_classification,
                effective_status,
                project,
                emb_blob,
            ),
        )

    conn.commit()
    result = {"saved": True, "version": new_version}
    store_idempotency(conn, idempotency_key, result)
    return result


@tool_handler(source="sqlite", confidence="exact")
async def session_load(
    store: VectorStore,
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Load latest checkpoint, or a specific session's checkpoint.

    If ``session_id`` is ``None``, returns the most recent checkpoint.
    Returns new columns (``original_request``, ``task_classification``,
    ``status``, ``project``) when present, omitting them for old data.
    """
    conn = store.conn

    if session_id:
        row = conn.execute(
            "SELECT session_id, state_json, version, "
            "original_request, task_classification, status, project "
            "FROM session_checkpoints WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT session_id, state_json, version, "
            "original_request, task_classification, status, project "
            "FROM session_checkpoints "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

    if not row:
        return {"found": False}

    data: dict[str, Any] = {
        "found": True,
        "session_id": row[0],
        "state": json.loads(row[1]),
        "version": row[2],
    }

    # Include new columns only when non-NULL (backward compat)
    if row[3] is not None:
        data["original_request"] = row[3]
    if row[4] is not None:
        data["task_classification"] = row[4]
    if row[5] is not None:
        data["status"] = row[5]
    if row[6] is not None:
        data["project"] = row[6]

    return data


@tool_handler(source="sqlite", confidence="approximate")
async def session_search(
    store: VectorStore,
    *,
    query: str,
    top_k: int = SESSION_DEFAULT_TOP_K,
    project: str | None = None,
    status: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Search sessions by semantic similarity to a query string.

    Embeds the query and compares against stored session embeddings
    using cosine similarity. Optionally filters by ``project`` and/or
    ``status`` columns.

    Returns matched sessions with similarity scores, following the
    same pattern as ``patterns_search``.
    """
    conn = store.conn

    cached = check_idempotency(conn, idempotency_key)
    if cached is not None:
        return cached

    query_embedding = store.model.embed(query)

    # Build filtered query for sessions with embeddings
    sql = "SELECT id, embedding FROM session_checkpoints WHERE embedding IS NOT NULL"
    params: list[Any] = []

    if project is not None:
        sql += " AND (project = ? OR project IS NULL)"
        params.append(project)
    if status is not None:
        sql += " AND status = ?"
        params.append(status)

    rows = conn.execute(sql, params).fetchall()

    stored = [(row[0], np.frombuffer(row[1], dtype=np.float32)) for row in rows]
    matches = search_similar(query_embedding, stored, top_k, SESSION_MIN_SCORE)

    # Batch-fetch all matched sessions in a single query (avoids N+1)
    results: list[dict[str, Any]] = []
    if matches:
        matched_ids = [id_ for id_, _ in matches]
        score_by_id = {id_: score for id_, score in matches}
        placeholders = ", ".join("?" for _ in matched_ids)
        cols = (
            "id, session_id, original_request, task_classification, "
            "status, project, version, created_at"
        )
        sql = f"SELECT {cols} FROM session_checkpoints WHERE id IN ({placeholders})"  # noqa: S608
        detail_rows = conn.execute(sql, matched_ids).fetchall()

        detail_by_id = {r[0]: r for r in detail_rows}

        # Preserve the similarity-ranked order from search_similar
        for id_ in matched_ids:
            row = detail_by_id.get(id_)
            if row is None:
                continue
            entry: dict[str, Any] = {
                "session_id": row[1],
                "score": round(score_by_id[id_], 3),
                "version": row[6],
                "created_at": row[7],
            }
            if row[2] is not None:
                entry["original_request"] = row[2]
            if row[3] is not None:
                entry["task_classification"] = row[3]
            if row[4] is not None:
                entry["status"] = row[4]
            if row[5] is not None:
                entry["project"] = row[5]
            results.append(entry)

    result = {"matches": results}
    store_idempotency(conn, idempotency_key, result)
    return result
