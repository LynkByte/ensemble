"""Standalone token counter using HuggingFace tokenizers.

Loads only the tokenizer (no ONNX model) for lightweight token counting.
The tokenizer is lazy-loaded on first call and cached at module level.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING

from ..config.defaults import MODEL_DIR, TOKENIZER_URL

if TYPE_CHECKING:
    from tokenizers import Tokenizer

logger = logging.getLogger(__name__)

_tokenizer: Tokenizer | None = None
_tokenizer_lock = threading.Lock()


def _ensure_tokenizer() -> Tokenizer:
    """Lazy-load the HuggingFace tokenizer, downloading if needed.

    Returns the cached tokenizer instance. Uses a lock to ensure
    thread-safe initialization — only one thread will download or
    load the tokenizer; subsequent callers get the cached instance.
    """
    global _tokenizer  # noqa: PLW0603
    if _tokenizer is not None:
        return _tokenizer

    with _tokenizer_lock:
        # Double-check after acquiring lock (another thread may have finished)
        if _tokenizer is not None:
            return _tokenizer

        tokenizer_path = MODEL_DIR / "tokenizer.json"

        if not tokenizer_path.exists():
            # Download to a temp file then atomically rename on success.
            # Uses urlopen with timeout instead of urlretrieve (which
            # has no timeout support).
            import urllib.request

            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            tmp_path = tokenizer_path.with_suffix(".tmp")
            logger.info("Downloading tokenizer to %s", tokenizer_path)
            try:
                response = urllib.request.urlopen(TOKENIZER_URL, timeout=30)  # noqa: S310
                try:
                    with tmp_path.open("wb") as fp:
                        while True:
                            chunk = response.read(64 * 1024)  # 64 KB chunks
                            if not chunk:
                                break
                            fp.write(chunk)
                finally:
                    response.close()
                os.replace(tmp_path, tokenizer_path)
            except Exception:
                # Clean up partial download on any failure
                tmp_path.unlink(missing_ok=True)
                raise

        from tokenizers import Tokenizer as TokClass

        _tokenizer = TokClass.from_file(str(tokenizer_path))
        # Disable truncation and padding — we need accurate full-length
        # token counts, not the 128-token padded/truncated sequences
        # used for embedding inference.
        _tokenizer.no_truncation()
        _tokenizer.no_padding()
        return _tokenizer


def count_tokens(text: str) -> int:
    """Count the number of tokens in *text* using the MiniLM tokenizer.

    Returns 0 for empty strings. Uses the same tokenizer as the
    embedding model for consistency.
    """
    if not text:
        return 0

    tokenizer = _ensure_tokenizer()
    encoded = tokenizer.encode(text)
    return len(encoded.ids)
