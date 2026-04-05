"""Tests for ONNX Runtime embedding generation.

Uses the mock embedding model from conftest to avoid downloading ONNX models.
Only tests the MockEmbeddingModel contract and the EmbeddingModel API surface.
"""

from __future__ import annotations

import numpy as np


class TestMockEmbeddingModel:
    def test_embed_returns_384_dim(self, mock_embedding_model):
        vec = mock_embedding_model.embed("hello world")
        assert vec.shape == (384,)
        assert vec.dtype == np.float32

    def test_embed_is_normalized(self, mock_embedding_model):
        vec = mock_embedding_model.embed("test string")
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-5

    def test_embed_deterministic(self, mock_embedding_model):
        vec1 = mock_embedding_model.embed("same text")
        vec2 = mock_embedding_model.embed("same text")
        np.testing.assert_array_equal(vec1, vec2)

    def test_embed_different_texts_differ(self, mock_embedding_model):
        vec1 = mock_embedding_model.embed("text one")
        vec2 = mock_embedding_model.embed("text two")
        assert not np.array_equal(vec1, vec2)

    def test_embed_batch(self, mock_embedding_model):
        texts = ["hello", "world", "foo"]
        results = mock_embedding_model.embed_batch(texts)
        assert len(results) == 3
        for vec in results:
            assert vec.shape == (384,)

    def test_dimensions_static(self, mock_embedding_model):
        assert mock_embedding_model.dimensions() == 384
