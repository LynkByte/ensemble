"""Tests for memory/similarity module."""

from __future__ import annotations

import numpy as np

from ensemble_mcp.memory.similarity import (
    cosine_similarity,
    pairwise_similarity_matrix,
    search_similar,
)


class TestCosineSimilarity:
    def test_identical_vectors(self):
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        score = cosine_similarity(a, a)
        assert abs(score - 1.0) < 1e-5

    def test_orthogonal_vectors(self):
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        score = cosine_similarity(a, b)
        assert abs(score) < 1e-5

    def test_opposite_vectors(self):
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([-1.0, 0.0, 0.0], dtype=np.float32)
        score = cosine_similarity(a, b)
        assert abs(score + 1.0) < 1e-5

    def test_zero_vector_returns_zero(self):
        a = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        b = np.zeros(3, dtype=np.float32)
        score = cosine_similarity(a, b)
        assert score == 0.0

    def test_both_zero_vectors(self):
        a = np.zeros(3, dtype=np.float32)
        b = np.zeros(3, dtype=np.float32)
        score = cosine_similarity(a, b)
        assert score == 0.0


class TestSearchSimilar:
    def test_empty_stored_returns_empty(self):
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        results = search_similar(query, [], top_k=3)
        assert results == []

    def test_finds_most_similar(self):
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        stored = [
            (1, np.array([0.9, 0.1, 0.0], dtype=np.float32)),  # most similar
            (2, np.array([0.0, 1.0, 0.0], dtype=np.float32)),  # orthogonal
            (3, np.array([0.8, 0.2, 0.0], dtype=np.float32)),  # second most
        ]
        results = search_similar(query, stored, top_k=2, min_score=0.0)
        assert len(results) <= 2
        assert results[0][0] in (1, 3)  # either of the similar ones

    def test_respects_min_score(self):
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        stored = [
            (1, np.array([0.0, 1.0, 0.0], dtype=np.float32)),  # orthogonal = ~0.0
        ]
        results = search_similar(query, stored, top_k=3, min_score=0.5)
        assert results == []

    def test_respects_top_k(self):
        query = np.ones(3, dtype=np.float32)
        stored = [
            (i, np.ones(3, dtype=np.float32) + np.random.rand(3).astype(np.float32) * 0.01)
            for i in range(10)
        ]
        results = search_similar(query, stored, top_k=3, min_score=0.0)
        assert len(results) <= 3

    def test_sorted_by_score_descending(self):
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        stored = [
            (1, np.array([0.5, 0.5, 0.0], dtype=np.float32)),
            (2, np.array([0.9, 0.1, 0.0], dtype=np.float32)),
            (3, np.array([0.3, 0.7, 0.0], dtype=np.float32)),
        ]
        results = search_similar(query, stored, top_k=3, min_score=0.0)
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)


class TestPairwiseSimilarityMatrix:
    def test_empty_list(self):
        result = pairwise_similarity_matrix([])
        assert result.size == 0

    def test_single_vector(self):
        vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        result = pairwise_similarity_matrix([vec])
        assert result.shape == (1, 1)
        assert abs(result[0, 0] - 1.0) < 1e-5

    def test_identity_diagonal(self):
        vecs = [
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
            np.array([0.0, 1.0, 0.0], dtype=np.float32),
        ]
        result = pairwise_similarity_matrix(vecs)
        assert result.shape == (2, 2)
        assert abs(result[0, 0] - 1.0) < 1e-5
        assert abs(result[1, 1] - 1.0) < 1e-5
        assert abs(result[0, 1]) < 1e-5  # orthogonal

    def test_symmetric(self):
        vecs = [
            np.random.rand(10).astype(np.float32),
            np.random.rand(10).astype(np.float32),
            np.random.rand(10).astype(np.float32),
        ]
        result = pairwise_similarity_matrix(vecs)
        np.testing.assert_allclose(result, result.T, atol=1e-5)
