"""ONNX Runtime embedding generation.

Loads MiniLM-L6-v2 (~22MB) via ONNX Runtime for local CPU inference.
~5ms per embedding, 384 dimensions. Model cached at
~/.cache/ensemble-mcp/models/.
"""

from __future__ import annotations

import logging
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from ..config.defaults import (
    EMBEDDING_DIMENSIONS,
    MODEL_DIR,
    MODEL_URL,
    TOKENIZER_URL,
)

if TYPE_CHECKING:
    import onnxruntime as ort
    from tokenizers import Tokenizer

logger = logging.getLogger(__name__)


class EmbeddingModel:
    """Local ONNX-based sentence embedding model.

    Lazy-loads the ONNX Runtime session and HuggingFace tokenizer on
    first use.  Downloads model files from HuggingFace Hub if not
    already cached.
    """

    def __init__(self, model_dir: Path = MODEL_DIR) -> None:
        self._model_dir = model_dir
        self._session: ort.InferenceSession | None = None
        self._tokenizer: Tokenizer | None = None

    # ── Model management ──────────────────────────────────────────

    @property
    def model_path(self) -> Path:
        return self._model_dir / "model.onnx"

    @property
    def tokenizer_path(self) -> Path:
        return self._model_dir / "tokenizer.json"

    def _ensure_model(self) -> None:
        """Download model files if not cached."""
        self._model_dir.mkdir(parents=True, exist_ok=True)

        if not self.model_path.exists():
            logger.info("Downloading ONNX model to %s ...", self.model_path)
            urllib.request.urlretrieve(MODEL_URL, self.model_path)  # noqa: S310
            logger.info("Model download complete.")

        if not self.tokenizer_path.exists():
            logger.info("Downloading tokenizer to %s ...", self.tokenizer_path)
            urllib.request.urlretrieve(TOKENIZER_URL, self.tokenizer_path)  # noqa: S310
            logger.info("Tokenizer download complete.")

    def _load(self) -> None:
        """Lazy-load ONNX session and tokenizer."""
        if self._session is not None:
            return

        self._ensure_model()

        import onnxruntime as ort_mod
        from tokenizers import Tokenizer as TokClass

        self._session = ort_mod.InferenceSession(
            str(self.model_path),
            providers=["CPUExecutionProvider"],
        )
        self._tokenizer = TokClass.from_file(str(self.tokenizer_path))

    # ── Embedding generation ──────────────────────────────────────

    def embed(self, text: str) -> np.ndarray:
        """Generate a 384-dimensional embedding for *text*.

        Returns a normalized float32 vector of shape ``(384,)``.
        """
        self._load()
        assert self._session is not None
        assert self._tokenizer is not None

        # Tokenize
        encoded = self._tokenizer.encode(text)
        input_ids = np.array([encoded.ids], dtype=np.int64)
        attention_mask = np.array([encoded.attention_mask], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids)

        # Run ONNX inference
        outputs = self._session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )

        # Mean pooling over token embeddings
        token_embeddings = outputs[0]  # (1, seq_len, 384)
        mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
        summed = np.sum(token_embeddings * mask_expanded, axis=1)
        counted = np.clip(np.sum(mask_expanded, axis=1), a_min=1e-9, a_max=None)
        embedding = summed / counted

        # L2 normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding.flatten().astype(np.float32)  # (384,)

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Embed multiple texts. Returns a list of 384-dim vectors.

        Simple sequential loop for now — batch ONNX if needed later.
        """
        return [self.embed(t) for t in texts]

    @staticmethod
    def dimensions() -> int:
        """Return the embedding dimensionality."""
        return EMBEDDING_DIMENSIONS
