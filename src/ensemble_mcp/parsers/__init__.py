"""AI tool session file parsers.

Provides parsers for extracting exact token usage data from AI tool
session files.  Two parsers are implemented:

- **OpenCode**: reads the monolithic SQLite database at
  ``~/.local/share/opencode/opencode.db``.
- **Claude Code**: reads JSONL session files under
  ``~/.claude/projects/<project-slug>/*.jsonl``.

Common return types (:class:`ParsedStep`, :class:`ParsedSession`) and an
auto-detection dispatcher (:func:`detect_ai_tool`, :func:`parse_latest_session`)
are defined here so callers can work against a single interface regardless of
which AI tool produced the session data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config.defaults import (
    CLAUDE_PROJECTS_DIR,
    CONFIDENCE_EXACT,
    OPENCODE_DB_PATH,
    SOURCE_PARSER,
)

__all__ = [
    "ParsedStep",
    "ParsedSession",
    "detect_ai_tool",
    "parse_latest_session",
]

logger = logging.getLogger(__name__)

# ── Common types ─────────────────────────────────────────────────


@dataclass(slots=True)
class ParsedStep:
    """One assistant message/turn with token usage data."""

    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    web_search_requests: int = 0
    timestamp: str | None = None  # ISO-8601
    agent: str | None = None  # OpenCode: mode/agent field
    finish_reason: str | None = None


@dataclass(slots=True)
class ParsedSession:
    """Aggregated token usage from a parsed session."""

    session_id: str = ""
    ai_tool: str = ""  # "opencode" | "claude-code"
    project: str | None = None
    steps: list[ParsedStep] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    source: str = SOURCE_PARSER
    confidence: str = CONFIDENCE_EXACT
    started_at: str | None = None  # ISO-8601
    ended_at: str | None = None  # ISO-8601
    errors: list[str] = field(default_factory=list)

    def compute_totals(self) -> None:
        """Recompute totals from individual steps."""
        self.total_input_tokens = sum(s.input_tokens for s in self.steps)
        self.total_output_tokens = sum(s.output_tokens for s in self.steps)
        self.total_cache_read_tokens = sum(s.cache_read_tokens for s in self.steps)
        self.total_cache_write_tokens = sum(s.cache_write_tokens for s in self.steps)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for envelope consumption."""
        return {
            "session_id": self.session_id,
            "ai_tool": self.ai_tool,
            "project": self.project,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "total_cache_write_tokens": self.total_cache_write_tokens,
            "source": self.source,
            "confidence": self.confidence,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "step_count": len(self.steps),
            "error_count": len(self.errors),
        }


# ── Auto-detection ───────────────────────────────────────────────


def detect_ai_tool(
    *,
    opencode_db_path: Path | None = None,
    claude_projects_dir: Path | None = None,
) -> str | None:
    """Auto-detect which AI tool has session data available.

    Checks for the OpenCode SQLite database and the Claude Code projects
    directory.  Returns ``"opencode"``, ``"claude-code"``, or ``None``.

    If both are present, returns ``"opencode"`` (preferred because it's
    a single DB with richer metadata).  Callers can override by
    specifying the tool explicitly.
    """
    oc_path = opencode_db_path or OPENCODE_DB_PATH
    cc_path = claude_projects_dir or CLAUDE_PROJECTS_DIR

    has_opencode = oc_path.is_file()
    has_claude = cc_path.is_dir()

    if has_opencode:
        return "opencode"
    if has_claude:
        return "claude-code"
    return None


# ── Dispatcher ───────────────────────────────────────────────────


def parse_latest_session(
    *,
    ai_tool: str | None = None,
    project_path: str | None = None,
    opencode_db_path: Path | None = None,
    claude_projects_dir: Path | None = None,
) -> ParsedSession | None:
    """Parse the most recent session for the detected (or specified) AI tool.

    Parameters
    ----------
    ai_tool:
        ``"opencode"`` or ``"claude-code"``.  If *None*, auto-detected
        via :func:`detect_ai_tool`.
    project_path:
        Optional project directory to scope the search.
    opencode_db_path:
        Override the default OpenCode database path (for testing).
    claude_projects_dir:
        Override the default Claude Code projects directory (for testing).

    Returns
    -------
    ParsedSession | None
        Parsed session data, or *None* if no session was found or the
        detected tool has no data.
    """
    tool = ai_tool or detect_ai_tool(
        opencode_db_path=opencode_db_path,
        claude_projects_dir=claude_projects_dir,
    )
    if tool is None:
        logger.debug("No AI tool session data detected")
        return None

    if tool == "opencode":
        from .opencode import parse_latest_session as _oc_parse

        return _oc_parse(
            db_path=opencode_db_path,
            project_path=project_path,
        )

    if tool in ("claude-code", "claude_code", "claude"):
        from .claude_code import parse_latest_session as _cc_parse

        return _cc_parse(
            projects_dir=claude_projects_dir,
            project_path=project_path,
        )

    logger.warning("Unknown AI tool %r — cannot parse session", tool)
    return None
