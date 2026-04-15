"""Shared test fixtures for ensemble-mcp.

Provides:
- tmp_db: temporary SQLite database with WAL mode and all tables
- mock_embedding_model: EmbeddingModel that returns deterministic vectors
- test_store: VectorStore using tmp_db + mock model (no ONNX download)
- test_conn: raw SQLite connection with all tables
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from ensemble_mcp.memory.embeddings import EmbeddingModel
from ensemble_mcp.memory.schema import ensure_schema
from ensemble_mcp.memory.store import VectorStore
from ensemble_mcp.state.locks import get_connection

# ── Mock Embedding Model ──────────────────────────────────────────


class MockEmbeddingModel(EmbeddingModel):
    """Deterministic embedding model for testing (no ONNX download).

    Produces normalized 384-dim vectors derived from a hash of the input
    text so that identical texts always produce identical embeddings and
    similar texts produce somewhat similar embeddings.
    """

    def __init__(self) -> None:
        # Skip parent __init__ which sets model_dir
        self._model_dir = Path("/dev/null")
        self._session = MagicMock()
        self._tokenizer = MagicMock()

    def embed(self, text: str) -> np.ndarray:
        """Return a deterministic 384-dim vector from text hash."""
        rng = np.random.RandomState(hash(text) % (2**31))
        vec = rng.randn(384).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        return [self.embed(t) for t in texts]

    def _load(self) -> None:
        pass  # No-op: skip ONNX loading

    def _ensure_model(self) -> None:
        pass  # No-op: skip model download


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture()
def mock_embedding_model() -> MockEmbeddingModel:
    """Return a deterministic mock embedding model."""
    return MockEmbeddingModel()


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Generator[Path, None, None]:
    """Yield a temporary database file path."""
    yield tmp_path / "test_data.db"


@pytest.fixture()
def test_conn(tmp_db: Path) -> Generator[sqlite3.Connection, None, None]:
    """Yield a SQLite connection with all tables created.

    Delegates to ``ensure_schema()`` — the single source of truth for DDL.
    """
    conn = get_connection(tmp_db)
    ensure_schema(conn)

    yield conn
    conn.close()


@pytest.fixture()
def test_store(
    tmp_db: Path,
    mock_embedding_model: MockEmbeddingModel,
) -> Generator[VectorStore, None, None]:
    """Yield a VectorStore backed by a temp DB and mock embeddings."""
    store = VectorStore(db_path=tmp_db, model=mock_embedding_model)
    yield store
    store.close()
