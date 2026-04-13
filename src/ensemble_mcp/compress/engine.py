"""Core compression engine.

Implements the Extract-Preserve-Compress-Rejoin pattern:
1. Extract and mark all "preserve" spans (technical content)
2. Compress prose segments between preserved spans
3. Rejoin all pieces into the final compressed text
4. Count tokens before and after for savings metrics

All compression is rule-based — zero LLM/API calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .preservers import find_preserve_spans
from .tokens import count_tokens

# ── Compression rules for prose segments ─────────────────────────

# Articles to drop (word-boundary aware to avoid corrupting words)
_ARTICLES: re.Pattern[str] = re.compile(
    r"\b(?:a|an|the)\b\s*",
    re.IGNORECASE,
)

# Filler words to drop
_FILLERS: re.Pattern[str] = re.compile(
    r"\b(?:just|really|basically|actually|simply|very|quite|perhaps|maybe|essentially"
    r"|certainly|definitely|obviously|clearly|generally|typically|usually|often"
    r"|somewhat|rather|fairly|pretty\s+much)\b\s*",
    re.IGNORECASE,
)

# Hedging phrases to drop
_HEDGING: re.Pattern[str] = re.compile(
    r"\b(?:I\s+think|it\s+seems|might\s+be|could\s+potentially|it\s+appears\s+that"
    r"|in\s+my\s+opinion|as\s+far\s+as\s+I\s+can\s+tell|from\s+what\s+I\s+can\s+see"
    r"|it\s+looks\s+like)\b\s*",
    re.IGNORECASE,
)

# Pleasantries to drop (typically at start of responses).
# Use [^.!\n] to avoid matching across line boundaries.
_PLEASANTRIES: re.Pattern[str] = re.compile(
    r"(?:^|\n)\s*(?:Sure!|Sure,|Of course!|Of course,|Absolutely!|Absolutely,"
    r"|I'd be happy to\b[^.!\n]*[.!]?\s*"
    r"|Let me\b[^.!\n]*[.!]?\s*"
    r"|Great question[.!]?\s*"
    r"|Good question[.!]?\s*"
    r"|That's a great question[.!]?\s*"
    r"|Happy to help[.!]?\s*"
    r"|No problem[.!]?\s*"
    r"|Here's what\b[^:\n]*:\s*)",
    re.IGNORECASE,
)

# Phrase simplifications (order matters — longer phrases first)
_PHRASE_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bin\s+order\s+to\b", re.IGNORECASE), "to"),
    (re.compile(r"\bas\s+well\s+as\b", re.IGNORECASE), "and"),
    (re.compile(r"\bdue\s+to\s+the\s+fact\s+that\b", re.IGNORECASE), "because"),
    (re.compile(r"\bat\s+this\s+point\s+in\s+time\b", re.IGNORECASE), "now"),
    (re.compile(r"\bin\s+the\s+event\s+that\b", re.IGNORECASE), "if"),
    (re.compile(r"\bfor\s+the\s+purpose\s+of\b", re.IGNORECASE), "to"),
    (re.compile(r"\bwith\s+regard\s+to\b", re.IGNORECASE), "about"),
    (re.compile(r"\bwith\s+respect\s+to\b", re.IGNORECASE), "about"),
    (re.compile(r"\bin\s+addition\s+to\b", re.IGNORECASE), "besides"),
    (re.compile(r"\bon\s+the\s+other\s+hand\b", re.IGNORECASE), "however"),
    (re.compile(r"\bas\s+a\s+result\s+of\b", re.IGNORECASE), "because of"),
    (re.compile(r"\btake\s+into\s+consideration\b", re.IGNORECASE), "consider"),
    (re.compile(r"\bmake\s+use\s+of\b", re.IGNORECASE), "use"),
    (re.compile(r"\bin\s+the\s+process\s+of\b", re.IGNORECASE), "while"),
    (re.compile(r"\bit\s+is\s+important\s+to\s+note\s+that\b", re.IGNORECASE), "notably"),
    (re.compile(r"\bplease\s+note\s+that\b", re.IGNORECASE), "note:"),
    (re.compile(r"\bkeep\s+in\s+mind\s+that\b", re.IGNORECASE), "note:"),
]

# Whitespace normalization
_MULTI_SPACE: re.Pattern[str] = re.compile(r"[ \t]+")
_MULTI_NEWLINE: re.Pattern[str] = re.compile(r"\n{3,}")
_TRAILING_SPACE: re.Pattern[str] = re.compile(r"[ \t]+$", re.MULTILINE)


@dataclass(slots=True, frozen=True)
class CompressResult:
    """Result of compressing a text string."""

    compressed_text: str
    original_tokens: int
    compressed_tokens: int
    savings_pct: float
    preserved_count: int


def _compress_prose(text: str) -> str:
    """Apply compression rules to a prose (non-technical) text segment.

    Drops articles, fillers, hedging, pleasantries, and simplifies
    verbose phrases. Normalizes whitespace.
    """
    result = text

    # Drop pleasantries first (often at segment boundaries)
    result = _PLEASANTRIES.sub("", result)

    # Simplify verbose phrases (before dropping articles)
    for pattern, replacement in _PHRASE_REPLACEMENTS:
        result = pattern.sub(replacement, result)

    # Drop hedging phrases
    result = _HEDGING.sub("", result)

    # Drop filler words
    result = _FILLERS.sub("", result)

    # Drop articles
    result = _ARTICLES.sub("", result)

    # Normalize whitespace
    result = _MULTI_SPACE.sub(" ", result)
    result = _TRAILING_SPACE.sub("", result)
    result = _MULTI_NEWLINE.sub("\n\n", result)

    return result.strip()


def compress(text: str) -> CompressResult:
    """Compress verbose natural language text while preserving technical content.

    Algorithm:
    1. Find all "preserve" spans (code blocks, URLs, paths, headings, etc.)
    2. For each prose segment between preserved spans, apply compression rules
    3. Rejoin preserved spans with compressed prose
    4. Count tokens before and after

    Returns a ``CompressResult`` with the compressed text and metrics.
    Pure code input is returned unchanged with ``savings_pct = 0``.
    """
    if not text or not text.strip():
        return CompressResult(
            compressed_text=text,
            original_tokens=0,
            compressed_tokens=0,
            savings_pct=0.0,
            preserved_count=0,
        )

    original_tokens = count_tokens(text)
    spans = find_preserve_spans(text)

    # If the entire text is technical content, return unchanged.
    # Check that preserved spans cover every character (no prose gaps).
    if (
        spans
        and spans[0].start == 0
        and spans[-1].end == len(text)
        and all(spans[i + 1].start <= spans[i].end for i in range(len(spans) - 1))
    ):
        return CompressResult(
            compressed_text=text,
            original_tokens=original_tokens,
            compressed_tokens=original_tokens,
            savings_pct=0.0,
            preserved_count=len(spans),
        )

    # Build output by interleaving compressed prose with preserved spans
    parts: list[str] = []
    pos = 0

    for span in spans:
        # Compress prose before this preserved span
        if pos < span.start:
            prose = text[pos : span.start]
            compressed_prose = _compress_prose(prose)
            if compressed_prose:
                parts.append(compressed_prose)

        # Add preserved span verbatim
        parts.append(text[span.start : span.end])
        pos = span.end

    # Compress any trailing prose after the last preserved span
    if pos < len(text):
        prose = text[pos:]
        compressed_prose = _compress_prose(prose)
        if compressed_prose:
            parts.append(compressed_prose)

    # Rejoin with appropriate spacing
    compressed_text = _rejoin_parts(parts)

    compressed_tokens = count_tokens(compressed_text)

    # Calculate savings
    if original_tokens > 0:
        savings_pct = round((1.0 - compressed_tokens / original_tokens) * 100, 1)
    else:
        savings_pct = 0.0

    return CompressResult(
        compressed_text=compressed_text,
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        savings_pct=max(savings_pct, 0.0),  # Clamp: compression should not increase tokens
        preserved_count=len(spans),
    )


def _rejoin_parts(parts: list[str]) -> str:
    """Rejoin compressed prose and preserved spans with appropriate spacing.

    Ensures newlines are preserved between block-level elements (headings,
    code blocks, tables) and spaces between inline elements.
    """
    if not parts:
        return ""

    result: list[str] = [parts[0]]
    for part in parts[1:]:
        prev = result[-1]

        # Block-level elements get newline separation
        if _is_block_element(part) or _is_block_element(prev):
            if not prev.endswith("\n"):
                result.append("\n")
        elif not prev.endswith((" ", "\n")):
            # Inline elements get space separation
            result.append(" ")

        result.append(part)

    return "".join(result)


def _is_block_element(text: str) -> bool:
    """Check if text starts or ends with a block-level element."""
    stripped = text.strip()
    return (
        stripped.startswith(("```", "#", "|", ">", "$"))
        or stripped.endswith("```")
        or "\n" in stripped
    )
