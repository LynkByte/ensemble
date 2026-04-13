"""Technical content detection for compression preservation.

Identifies spans of text that must be preserved untouched during
compression: code blocks, URLs, file paths, shell commands, headings,
tables, inline code, version numbers, and other technical content.

Uses the same compiled-regex-scan approach as ``security/redaction.py``,
but for identifying preservation regions rather than secrets.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class Span(NamedTuple):
    """A region of text to preserve during compression."""

    start: int
    end: int
    kind: str


# ── Compiled patterns for technical content ──────────────────────
# Order matters: longer/greedy patterns first to avoid partial matches.

_PRESERVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Fenced code blocks (```...```) — must be DOTALL for multiline
    (
        "fenced_code",
        re.compile(r"```[^\n]*\n.*?```", re.DOTALL),
    ),
    # Indented code blocks (4+ spaces or tab at line start, consecutive lines)
    (
        "indented_code",
        re.compile(r"(?:^(?:    |\t).+\n?)+", re.MULTILINE),
    ),
    # Markdown headings (# ... to ###### ...)
    (
        "heading",
        re.compile(r"^#{1,6}\s+.+$", re.MULTILINE),
    ),
    # Markdown table rows (lines starting and containing |)
    (
        "table_row",
        re.compile(r"^\|.+\|$", re.MULTILINE),
    ),
    # Markdown table separator rows (|---|---|)
    (
        "table_separator",
        re.compile(r"^\|[\s\-:|]+\|$", re.MULTILINE),
    ),
    # Inline code (`...`) — non-greedy, single line
    (
        "inline_code",
        re.compile(r"`[^`\n]+`"),
    ),
    # URLs (http/https/ftp)
    (
        "url",
        re.compile(r"https?://[^\s)>\]\"']+|ftp://[^\s)>\]\"']+"),
    ),
    # File paths (Unix-style with extension or directory separator)
    (
        "file_path",
        re.compile(r"(?<!\w)(?:/[\w.\-]+)+(?:\.\w+)?(?!\w)"),
    ),
    # File paths (relative, with extension — must start with ./ ../ or a letter)
    (
        "relative_path",
        re.compile(r"(?<!\w)(?:\.{1,2}/)?(?:[a-zA-Z][\w.\-]*/)+[\w.\-]+\.\w+(?!\w)"),
    ),
    # Shell commands (lines starting with $ or >)
    (
        "shell_command",
        re.compile(r"^[>$]\s+.+$", re.MULTILINE),
    ),
    # Version numbers (e.g., v1.2.3, 2.0.0-beta.1)
    (
        "version",
        re.compile(r"\bv?\d+\.\d+(?:\.\d+)?(?:-[\w.]+)?\b"),
    ),
    # ISO dates (2024-01-15, 2024-01-15T10:30:00Z)
    (
        "date",
        re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:?\d{2})?)?\b"),
    ),
]


def find_preserve_spans(text: str) -> list[Span]:
    """Identify all regions of *text* that should be preserved during compression.

    Returns a sorted, non-overlapping list of ``Span`` tuples. When
    patterns overlap, earlier/longer matches take priority.
    """
    raw_spans: list[Span] = []

    for kind, pattern in _PRESERVE_PATTERNS:
        for match in pattern.finditer(text):
            raw_spans.append(Span(start=match.start(), end=match.end(), kind=kind))

    if not raw_spans:
        return []

    # Sort by start position, then by length (longest first) for overlap resolution
    raw_spans.sort(key=lambda s: (s.start, -(s.end - s.start)))

    # Merge overlapping spans, keeping the first (longest) match
    merged: list[Span] = [raw_spans[0]]
    for span in raw_spans[1:]:
        prev = merged[-1]
        if span.start < prev.end:
            # Overlapping — extend if the new span goes further
            if span.end > prev.end:
                merged[-1] = Span(start=prev.start, end=span.end, kind=prev.kind)
        else:
            merged.append(span)

    return merged
