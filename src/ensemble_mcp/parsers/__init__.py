"""AI tool session file parsers.

Provides parsers for extracting exact token usage data from AI tool
session files.  Six parser modules exist:

**Active parsers** (extract real token data):

- **OpenCode**: reads the monolithic SQLite database at
  ``~/.local/share/opencode/opencode.db``.
- **Claude Code**: reads JSONL session files under
  ``~/.claude/projects/<project-slug>/*.jsonl``.

**Stub parsers** (detect tool presence, explain why parsing is not feasible):

- **Cursor**: local DB tracks code attribution, not token usage.
- **GitHub Copilot**: session metadata only; token tracking is server-side.
- **Windsurf**: cascade files are encrypted Protocol Buffers.
- **Devin CLI**: cloud-only architecture; no local session data.

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
    COPILOT_CHAT_DIR,
    CURSOR_AI_TRACKING_DB,
    DEVIN_CONFIG_DIR,
    OPENCODE_DB_PATH,
    SOURCE_PARSER,
    WINDSURF_CASCADE_DIR,
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
    cursor_ai_tracking_db: Path | None = None,
    copilot_chat_dir: Path | None = None,
    windsurf_cascade_dir: Path | None = None,
    devin_config_dir: Path | None = None,
) -> str | None:
    """Auto-detect which AI tool has session data available.

    Checks for session data from all six supported tools.  Returns the
    tool identifier string or ``None`` if nothing is detected.

    **Active parsers** (can extract token data):
      ``"opencode"``, ``"claude-code"``

    **Stub parsers** (detected but token data not accessible):
      ``"cursor"``, ``"copilot"``, ``"windsurf"``, ``"devin"``

    If multiple tools are present, returns the first *active* parser
    found (OpenCode preferred, then Claude Code).  If only stub-parsable
    tools are present, returns the first detected stub tool.
    """
    oc_path = opencode_db_path or OPENCODE_DB_PATH
    cc_path = claude_projects_dir or CLAUDE_PROJECTS_DIR

    # Active parsers — prefer these (they yield real token data)
    if oc_path.is_file():
        return "opencode"
    if cc_path.is_dir():
        return "claude-code"

    # Stub parsers — detected but cannot extract tokens
    cu_path = cursor_ai_tracking_db or CURSOR_AI_TRACKING_DB
    if cu_path.is_file():
        return "cursor"

    cp_path = copilot_chat_dir or COPILOT_CHAT_DIR
    if cp_path.is_dir():
        return "copilot"

    ws_path = windsurf_cascade_dir or WINDSURF_CASCADE_DIR
    if ws_path.is_dir():
        return "windsurf"

    dv_path = devin_config_dir or DEVIN_CONFIG_DIR
    if dv_path.is_dir():
        return "devin"

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
        Tool identifier — ``"opencode"``, ``"claude-code"``, ``"cursor"``,
        ``"copilot"``, ``"windsurf"``, or ``"devin"``.  If *None*,
        auto-detected via :func:`detect_ai_tool`.
    project_path:
        Optional project directory to scope the search.
    opencode_db_path:
        Override the default OpenCode database path (for testing).
    claude_projects_dir:
        Override the default Claude Code projects directory (for testing).

    Returns
    -------
    ParsedSession | None
        Parsed session data, or *None* if no session was found, the
        detected tool has no data, or the tool's session data is not
        parsable (stub parser).
    """
    tool = ai_tool or detect_ai_tool(
        opencode_db_path=opencode_db_path,
        claude_projects_dir=claude_projects_dir,
    )
    if tool is None:
        logger.debug("No AI tool session data detected")
        return None

    # ── Active parsers ────────────────────────────────────────────
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

    # ── Stub parsers (detected but not parsable) ──────────────────
    if tool == "cursor":
        from .cursor import parse_latest_session as _cu_parse

        _cu_parse(project_path=project_path)
        return None

    if tool in ("copilot", "github-copilot", "github_copilot"):
        from .copilot import parse_latest_session as _cp_parse

        _cp_parse(project_path=project_path)
        return None

    if tool in ("windsurf", "codeium"):
        from .windsurf import parse_latest_session as _ws_parse

        _ws_parse(project_path=project_path)
        return None

    if tool == "devin":
        from .devin import parse_latest_session as _dv_parse

        _dv_parse(project_path=project_path)
        return None

    logger.warning("Unknown AI tool %r — cannot parse session", tool)
    return None
