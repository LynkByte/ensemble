"""ONNX Runtime embedding generation.

Loads MiniLM-L6-v2 (~22MB) via ONNX Runtime for local CPU inference.
~5ms per embedding, 384 dimensions. Model cached at
~/.cache/ensemble-mcp/models/.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, cast

import numpy as np
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from ..config.defaults import (
    EMBEDDING_DIMENSIONS,
    MODEL_DIR,
    MODEL_URL,
    TOKENIZER_URL,
)
from ..contracts.errors import ErrorCode, ToolError

if TYPE_CHECKING:
    import onnxruntime as ort
    from tokenizers import Tokenizer

logger = logging.getLogger(__name__)

# All user-facing output goes to stderr — stdout is reserved for MCP.
_stderr = Console(stderr=True, highlight=False)


def _download_with_progress(url: str, dest: Path, label: str) -> None:
    """Download *url* to *dest* with a rich progress bar on stderr.

    Falls back to a plain ``urlretrieve`` when the server does not
    provide a ``Content-Length`` header (e.g. chunked transfer).

    Raises ``ToolError(IO_MODEL_DOWNLOAD)`` on any network failure.
    """
    try:
        response = urllib.request.urlopen(url)  # noqa: S310
    except (urllib.error.URLError, OSError) as exc:
        raise ToolError(
            code=ErrorCode.IO_MODEL_DOWNLOAD,
            message=f"Failed to connect to {url}: {exc}",
            details={"url": url, "dest": str(dest)},
        ) from exc

    total = int(response.headers.get("Content-Length", 0))

    try:
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=_stderr,
            transient=True,
        ) as progress:
            task_id = progress.add_task(label, total=total or None)

            with dest.open("wb") as fp:
                while True:
                    chunk = response.read(64 * 1024)  # 64 KB chunks
                    if not chunk:
                        break
                    fp.write(chunk)
                    progress.advance(task_id, len(chunk))

    except (urllib.error.URLError, OSError) as exc:
        # Clean up partial file on failure
        dest.unlink(missing_ok=True)
        raise ToolError(
            code=ErrorCode.IO_MODEL_DOWNLOAD,
            message=f"Download interrupted for {label}: {exc}",
            details={"url": url, "dest": str(dest)},
        ) from exc
    finally:
        response.close()

    _stderr.print(f"  [green]{label} complete.[/green]")


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
            _download_with_progress(MODEL_URL, self.model_path, "ONNX model")

        if not self.tokenizer_path.exists():
            _download_with_progress(TOKENIZER_URL, self.tokenizer_path, "Tokenizer")

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

        return cast(np.ndarray, embedding.flatten().astype(np.float32))  # (384,)

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Embed multiple texts. Returns a list of 384-dim vectors.

        Simple sequential loop for now — batch ONNX if needed later.
        """
        return [self.embed(t) for t in texts]

    @staticmethod
    def dimensions() -> int:
        """Return the embedding dimensionality."""
        return EMBEDDING_DIMENSIONS
