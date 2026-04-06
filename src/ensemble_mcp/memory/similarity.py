"""Cosine similarity search.

Brute-force cosine similarity over numpy arrays. Sufficient for <10K vectors
with <1ms search time.
"""

from __future__ import annotations

from typing import cast

import numpy as np


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors.

    Returns a float in [-1, 1]. Returns 0.0 if either vector is zero.
    """
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def search_similar(
    query_embedding: np.ndarray,
    stored_embeddings: list[tuple[int, np.ndarray]],
    top_k: int = 3,
    min_score: float = 0.3,
) -> list[tuple[int, float]]:
    """Find top-K most similar embeddings above *min_score*.

    Args:
        query_embedding: The query vector (384-dim).
        stored_embeddings: List of ``(id, embedding)`` pairs.
        top_k: Maximum number of results.
        min_score: Minimum cosine similarity threshold.

    Returns:
        List of ``(id, score)`` tuples sorted by descending score.
    """
    if not stored_embeddings:
        return []

    scores: list[tuple[int, float]] = []
    for id_, emb in stored_embeddings:
        score = cosine_similarity(query_embedding, emb)
        if score >= min_score:
            scores.append((id_, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_k]


def pairwise_similarity_matrix(
    embeddings: list[np.ndarray],
) -> np.ndarray:
    """Compute a pairwise cosine similarity matrix.

    Args:
        embeddings: List of N vectors.

    Returns:
        An NxN numpy array of cosine similarities.
    """
    if not embeddings:
        return np.array([])

    matrix = np.stack(embeddings)  # (N, D)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.clip(norms, a_min=1e-9, a_max=None)
    normalized = matrix / norms
    return cast(np.ndarray, normalized @ normalized.T)
