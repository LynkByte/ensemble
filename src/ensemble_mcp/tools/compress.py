"""Compress tools: context_compress, context_prepare.

Thin MCP tool wrappers around the compression engine. Validates input,
calls the engine, and returns the result in the standard envelope format.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from ..compress.engine import compress
from ..config.defaults import COMPRESS_MAX_INPUT_LENGTH, COMPRESS_MIN_INPUT_LENGTH
from ..contracts.envelope import tool_handler
from ..contracts.errors import validation_error
from ..state.idempotency import check_idempotency, store_idempotency

# Priority ordering for context_prepare: static content first (most cacheable),
# then project context, then task-specific content last (least cacheable).
_PRIORITY_ORDER: dict[str, int] = {"static": 0, "project": 1, "task": 2}

# Whitespace normalization patterns
_MULTI_NEWLINE: re.Pattern[str] = re.compile(r"\n{3,}")
_TRAILING_SPACE: re.Pattern[str] = re.compile(r"[ \t]+$", re.MULTILINE)


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


def _normalize_whitespace(text: str) -> str:
    """Collapse multiple newlines and strip trailing whitespace per line."""
    result = _TRAILING_SPACE.sub("", text)
    result = _MULTI_NEWLINE.sub("\n\n", result)
    return result.strip()


@tool_handler(source="local", confidence="exact")
async def context_prepare(
    conn: sqlite3.Connection,
    *,
    sections: list[dict[str, str]],
    compress_sections: bool = False,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Prepare and order prompt sections for optimal LLM cache hit rates.

    Sorts sections by priority (static → project → task) to maximize the
    stable prefix that LLM providers can cache across calls. Within each
    priority tier, sections are sorted by name for determinism.

    Optionally compresses each section through the compression engine to
    reduce token usage.

    Args:
        conn: SQLite connection.
        sections: List of dicts with ``name``, ``content``, and ``priority``
            (one of ``"static"``, ``"project"``, ``"task"``).
        compress_sections: If True, run each section through the compression
            engine before assembling.
        idempotency_key: Optional idempotency key for deduplication.

    Returns:
        Dict with ``prepared_text``, ``section_count``, ``prefix_stable_bytes``,
        and per-section metadata.
    """
    cached = check_idempotency(conn, idempotency_key)
    if cached is not None:
        return cached

    # ── Validate input ────────────────────────────────────────────
    if not sections:
        raise validation_error("Sections list must not be empty", field="sections")

    valid_priorities = set(_PRIORITY_ORDER.keys())
    section_meta: list[dict[str, Any]] = []

    for i, section in enumerate(sections):
        if not isinstance(section, dict):
            raise validation_error(
                f"Section at index {i} must be a dict",
                field="sections",
                index=i,
            )
        for required_key in ("name", "content", "priority"):
            if required_key not in section:
                raise validation_error(
                    f"Section at index {i} missing required key '{required_key}'",
                    field=f"sections[{i}].{required_key}",
                )
        if section["priority"] not in valid_priorities:
            raise validation_error(
                f"Section at index {i} has invalid priority '{section['priority']}'; "
                f"must be one of: {', '.join(sorted(valid_priorities))}",
                field=f"sections[{i}].priority",
            )

    # ── Sort: priority order (static→project→task), then name ─────
    sorted_sections = sorted(
        sections,
        key=lambda s: (_PRIORITY_ORDER[s["priority"]], s["name"]),
    )

    # ── Process each section ──────────────────────────────────────
    prepared_parts: list[str] = []
    prefix_stable_bytes = 0
    saw_task = False

    for section in sorted_sections:
        name = section["name"]
        content = section["content"]
        priority = section["priority"]
        original_bytes = len(content.encode("utf-8"))

        # Normalize whitespace
        prepared = _normalize_whitespace(content)

        # Optionally compress
        if compress_sections and prepared:
            cr = compress(prepared)
            prepared = cr.compressed_text

        prepared_bytes = len(prepared.encode("utf-8"))

        section_meta.append(
            {
                "name": name,
                "priority": priority,
                "original_bytes": original_bytes,
                "prepared_bytes": prepared_bytes,
            }
        )

        prepared_parts.append(prepared)

        # Accumulate prefix_stable_bytes for static + project sections
        if priority in ("static", "project") and not saw_task:
            # Include the section content plus a separator newline
            prefix_stable_bytes += prepared_bytes + 2  # +2 for "\n\n" separator
        elif priority == "task":
            saw_task = True

    # ── Assemble final text ───────────────────────────────────────
    prepared_text = "\n\n".join(prepared_parts)

    # Adjust: remove trailing separator padding from prefix_stable_bytes
    if prefix_stable_bytes > 0:
        prefix_stable_bytes -= 2  # last section doesn't need trailing separator

    result: dict[str, Any] = {
        "prepared_text": prepared_text,
        "section_count": len(sorted_sections),
        "prefix_stable_bytes": max(prefix_stable_bytes, 0),
        "sections": section_meta,
    }

    store_idempotency(conn, idempotency_key, result)
    return result
