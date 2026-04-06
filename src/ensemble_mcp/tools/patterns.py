"""Pattern tools: patterns_search, patterns_store, patterns_prune.

Semantic search over stored patterns using vector embeddings.
"""

from __future__ import annotations

from typing import Any

from ..contracts.envelope import tool_handler
from ..memory.store import VectorStore
from ..state.idempotency import check_idempotency, store_idempotency


@tool_handler(source="sqlite", confidence="exact")
async def patterns_search(
    store: VectorStore,
    *,
    query: str,
    top_k: int = 3,
    project: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Search stored patterns by semantic similarity.

    Returns top-K matches above the minimum score threshold.
    """
    cached = check_idempotency(store.conn, idempotency_key)
    if cached is not None:
        return cached

    matches = store.search_patterns(query, top_k=top_k, project=project)

    result = {"matches": matches}
    store_idempotency(store.conn, idempotency_key, result)
    return result


@tool_handler(source="sqlite", confidence="exact")
async def patterns_store(
    store: VectorStore,
    *,
    name: str,
    context: str,
    approach: str,
    outcome: str,
    project: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Store a new pattern with embedding for future semantic search."""
    cached = check_idempotency(store.conn, idempotency_key)
    if cached is not None:
        return cached

    pattern_id = store.store_pattern(
        name=name,
        context=context,
        approach=approach,
        outcome=outcome,
        project=project,
    )

    result = {"id": pattern_id, "stored": True}
    store_idempotency(store.conn, idempotency_key, result)
    return result


@tool_handler(source="sqlite", confidence="exact")
async def patterns_prune(
    store: VectorStore,
    *,
    max_age_days: int = 90,
    min_score: float = 0.3,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Remove old/unused patterns (zero match_count, older than max_age_days)."""
    cached = check_idempotency(store.conn, idempotency_key)
    if cached is not None:
        return cached

    pruned, remaining = store.prune_patterns(
        max_age_days=max_age_days,
        min_score=min_score,
    )

    result = {"pruned": pruned, "remaining": remaining}
    store_idempotency(store.conn, idempotency_key, result)
    return result
