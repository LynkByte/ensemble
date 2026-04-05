"""Memory layer: embeddings, vector store, and similarity search."""

from .embeddings import EmbeddingModel
from .similarity import cosine_similarity, pairwise_similarity_matrix, search_similar
from .store import VectorStore

__all__ = [
    "EmbeddingModel",
    "VectorStore",
    "cosine_similarity",
    "pairwise_similarity_matrix",
    "search_similar",
]
