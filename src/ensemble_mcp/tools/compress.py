"""Compress tool: context_compress.

Thin MCP tool wrapper around the compression engine. Validates input,
calls the engine, and returns the result in the standard envelope format.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from ..compress.engine import compress
from ..config.defaults import COMPRESS_MAX_INPUT_LENGTH, COMPRESS_MIN_INPUT_LENGTH
from ..contracts.envelope import tool_handler
from ..contracts.errors import validation_error
from ..state.idempotency import check_idempotency, store_idempotency


@tool_handler(source="local", confidence="exact")
async def context_compress(
    conn: sqlite3.Connection,
    *,
    text: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Compress verbose natural language text into terse, token-efficient form.

    Preserves all technical content (code blocks, URLs, file paths,
    headings, tables) while removing filler words, articles, hedging
    phrases, and pleasantries from prose sections. Rule-based, zero
    LLM calls.
    """
    cached = check_idempotency(conn, idempotency_key)
    if cached is not None:
        return cached

    # Validate input
    if not text or not text.strip():
        raise validation_error("Text must not be empty", field="text")

    if len(text) < COMPRESS_MIN_INPUT_LENGTH:
        raise validation_error(
            f"Text must be at least {COMPRESS_MIN_INPUT_LENGTH} characters",
            field="text",
            length=len(text),
            min_length=COMPRESS_MIN_INPUT_LENGTH,
        )

    if len(text) > COMPRESS_MAX_INPUT_LENGTH:
        raise validation_error(
            f"Text exceeds maximum length of {COMPRESS_MAX_INPUT_LENGTH} characters",
            field="text",
            length=len(text),
            max_length=COMPRESS_MAX_INPUT_LENGTH,
        )

    # Run compression
    cr = compress(text)

    result: dict[str, Any] = {
        "compressed_text": cr.compressed_text,
        "original_tokens": cr.original_tokens,
        "compressed_tokens": cr.compressed_tokens,
        "savings_pct": cr.savings_pct,
        "preserved_count": cr.preserved_count,
    }

    store_idempotency(conn, idempotency_key, result)
    return result
