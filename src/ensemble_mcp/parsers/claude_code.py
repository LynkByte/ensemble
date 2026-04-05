"""Parse Claude Code session data.

Claude Code stores session data as JSONL files under
``~/.claude/projects/<project-slug>/*.jsonl``.  Each line is a JSON
object with a ``type`` field (``user``, ``assistant``, ``system``,
``file-history-snapshot``).

Token usage lives on **assistant** lines in ``message.usage``::

    {
      "type": "assistant",
      "uuid": "...",
      "message": {
        "model": "claude-sonnet-4-6",
        "usage": {
          "input_tokens": 3,
          "output_tokens": 141,
          "cache_creation_input_tokens": 1740,
          "cache_read_input_tokens": 22715,
          "server_tool_use": { "web_search_requests": 0 }
        },
        "stop_reason": "tool_use"
      }
    }

**Streaming deduplication**: Claude Code may emit multiple JSONL lines
for the same ``message.id`` as content streams in.  The *last* line
for a given ``message.id`` contains the final/accurate token counts.

**Subagent sessions** are stored under
``<session-uuid>/subagents/agent-*.jsonl`` and are parsed recursively.

Project directory slugs encode the filesystem path:
``/home/user/project`` becomes ``-home-user-project``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..config.defaults import (
    CLAUDE_PROJECTS_DIR,
    CONFIDENCE_EXACT,
    CONFIDENCE_PARTIAL,
    SOURCE_PARSER,
)
from . import ParsedSession, ParsedStep

__all__ = [
    "find_claude_projects_dir",
    "find_session_files",
    "parse_session_file",
    "parse_latest_session",
]

logger = logging.getLogger(__name__)


# ── Slug helpers ─────────────────────────────────────────────────


def _path_to_slug(path: str) -> str:
    """Convert an absolute filesystem path to a Claude Code project slug.

    ``/home/user/project`` → ``-home-user-project``
    """
    return path.replace("/", "-")


def _slug_to_path(slug: str) -> str:
    """Convert a Claude Code project slug back to a filesystem path.

    ``-home-user-project`` → ``/home/user/project``

    This is a best-effort inverse — the first ``-`` maps to ``/``.
    """
    if slug.startswith("-"):
        return slug.replace("-", "/", 1).replace("-", "/")
    return slug.replace("-", "/")


# ── Message parsing ──────────────────────────────────────────────


def _parse_assistant_message(line: dict[str, Any]) -> ParsedStep | None:
    """Extract a :class:`ParsedStep` from a Claude Code assistant line.

    Returns *None* if the line has no usable usage data.
    """
    msg = line.get("message")
    if not isinstance(msg, dict):
        return None

    model = msg.get("model")

    # Skip synthetic error messages
    if model == "<synthetic>":
        return None

    usage = msg.get("usage")
    if not isinstance(usage, dict):
        return None

    input_tok = int(usage.get("input_tokens", 0) or 0)
    output_tok = int(usage.get("output_tokens", 0) or 0)
    cache_read = int(usage.get("cache_read_input_tokens", 0) or 0)
    cache_write = int(usage.get("cache_creation_input_tokens", 0) or 0)

    # Web search requests from server_tool_use
    web_reqs = 0
    server_tool_use = usage.get("server_tool_use")
    if isinstance(server_tool_use, dict):
        web_reqs = int(server_tool_use.get("web_search_requests", 0) or 0)

    # Skip lines with no token data at all
    if input_tok == 0 and output_tok == 0:
        return None

    timestamp = line.get("timestamp")  # already ISO-8601

    return ParsedStep(
        model=model,
        input_tokens=input_tok,
        output_tokens=output_tok,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        web_search_requests=web_reqs,
        timestamp=timestamp,
        finish_reason=msg.get("stop_reason"),
    )


def _deduplicate_messages(
    assistant_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deduplicate streaming lines by ``message.id``.

    Claude Code may emit multiple lines with the same ``message.id``
    as content streams.  The *last* occurrence has the final token
    counts, so we keep only that one.

    Lines without a ``message.id`` are kept as-is.
    """
    # Preserve insertion order; last write wins
    seen: dict[str, int] = {}  # message_id -> index in result
    result: list[dict[str, Any]] = []

    for line in assistant_lines:
        msg = line.get("message")
        if not isinstance(msg, dict):
            result.append(line)
            continue

        msg_id = msg.get("id")
        if msg_id is None:
            result.append(line)
            continue

        if msg_id in seen:
            # Replace the earlier occurrence with this newer one
            result[seen[msg_id]] = line
        else:
            seen[msg_id] = len(result)
            result.append(line)

    return result


# ── JSONL file parsing ───────────────────────────────────────────


def _parse_jsonl_file(jsonl_path: Path) -> tuple[list[ParsedStep], list[str]]:
    """Parse a single JSONL file and return steps + errors.

    Streams line-by-line to handle large files without loading the
    full content into memory.
    """
    steps: list[ParsedStep] = []
    errors: list[str] = []

    # Collect all assistant lines first for deduplication
    assistant_lines: list[dict[str, Any]] = []

    try:
        with open(jsonl_path, encoding="utf-8") as f:
            for line_num, raw_line in enumerate(f, 1):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    line_data = json.loads(raw_line)
                except json.JSONDecodeError:
                    errors.append(f"Malformed JSON at line {line_num} in {jsonl_path.name}")
                    continue

                if not isinstance(line_data, dict):
                    continue

                if line_data.get("type") == "assistant":
                    assistant_lines.append(line_data)

    except OSError as exc:
        errors.append(f"Cannot read {jsonl_path.name}: {exc}")
        return steps, errors

    # Deduplicate streaming updates (keep last per message.id)
    deduped = _deduplicate_messages(assistant_lines)

    for line_data in deduped:
        step = _parse_assistant_message(line_data)
        if step is not None:
            steps.append(step)

    return steps, errors


# ── Public API ───────────────────────────────────────────────────


def find_claude_projects_dir(custom_path: Path | None = None) -> Path | None:
    """Locate the Claude Code projects directory.

    Returns
    -------
    Path | None
        The directory path, or *None* if it does not exist.
    """
    path = custom_path or CLAUDE_PROJECTS_DIR
    return path if path.is_dir() else None


def find_session_files(
    projects_dir: Path,
    *,
    project_path: str | None = None,
) -> list[Path]:
    """Find JSONL session files, optionally filtered by project path.

    Parameters
    ----------
    projects_dir:
        The Claude Code projects root (``~/.claude/projects/``).
    project_path:
        If provided, only return sessions for this project directory.
        Compared against the directory slug.

    Returns
    -------
    list[Path]
        Session JSONL file paths, sorted by modification time (newest first).
    """
    if project_path:
        slug = _path_to_slug(project_path)
        project_dir = projects_dir / slug
        if not project_dir.is_dir():
            return []
        pattern_dirs = [project_dir]
    else:
        # Scan all project directories
        try:
            pattern_dirs = [d for d in projects_dir.iterdir() if d.is_dir()]
        except OSError:
            return []

    jsonl_files: list[Path] = []
    for pdir in pattern_dirs:
        try:
            for f in pdir.iterdir():
                if f.is_file() and f.suffix == ".jsonl":
                    jsonl_files.append(f)
        except OSError:
            continue

    # Sort by mtime, newest first
    jsonl_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return jsonl_files


def _find_subagent_files(session_jsonl: Path) -> list[Path]:
    """Find subagent JSONL files associated with a session.

    Subagent sessions live in ``<session-uuid>/subagents/*.jsonl``
    where ``<session-uuid>`` is a directory alongside the session
    JSONL file.
    """
    # Session file: <uuid>.jsonl -> companion dir: <uuid>/subagents/
    stem = session_jsonl.stem
    companion_dir = session_jsonl.parent / stem / "subagents"
    if not companion_dir.is_dir():
        return []

    subagent_files: list[Path] = []
    try:
        for f in companion_dir.iterdir():
            if f.is_file() and f.suffix == ".jsonl":
                subagent_files.append(f)
    except OSError:
        pass

    return subagent_files


def parse_session_file(
    jsonl_path: Path,
    *,
    include_subagents: bool = True,
) -> ParsedSession | None:
    """Parse a Claude Code session JSONL file.

    Parameters
    ----------
    jsonl_path:
        Path to the ``.jsonl`` session file.
    include_subagents:
        If *True* (default), also parse subagent JSONL files under
        ``<session-uuid>/subagents/`` and merge their steps.

    Returns
    -------
    ParsedSession | None
        Parsed session, or *None* if the file cannot be read.
    """
    if not jsonl_path.is_file():
        return None

    # Derive session_id from filename (the UUID stem)
    session_id = jsonl_path.stem

    # Determine project path from parent directory slug
    parent_slug = jsonl_path.parent.name
    project = _slug_to_path(parent_slug)

    steps, errors = _parse_jsonl_file(jsonl_path)

    # Parse subagent sessions if requested
    if include_subagents:
        subagent_files = _find_subagent_files(jsonl_path)
        for sub_path in subagent_files:
            sub_steps, sub_errors = _parse_jsonl_file(sub_path)
            steps.extend(sub_steps)
            errors.extend(sub_errors)

    result = ParsedSession(
        session_id=session_id,
        ai_tool="claude-code",
        project=project,
        steps=steps,
        source=SOURCE_PARSER,
        confidence=CONFIDENCE_EXACT,
        errors=errors,
    )

    # Set timestamps from first and last steps
    if steps:
        timestamps = [s.timestamp for s in steps if s.timestamp]
        if timestamps:
            result.started_at = min(timestamps)
            result.ended_at = max(timestamps)

    # Degrade confidence on parse errors
    if errors and steps or not steps:
        result.confidence = CONFIDENCE_PARTIAL

    result.compute_totals()
    return result


def parse_latest_session(
    *,
    projects_dir: Path | None = None,
    project_path: str | None = None,
) -> ParsedSession | None:
    """Find and parse the most recent Claude Code session.

    Parameters
    ----------
    projects_dir:
        Override the default projects directory (for testing).
    project_path:
        If provided, restrict to sessions for this project.

    Returns
    -------
    ParsedSession | None
        Parsed session, or *None* if no sessions found.
    """
    resolved_dir = find_claude_projects_dir(projects_dir)
    if resolved_dir is None:
        logger.debug("Claude Code projects directory not found")
        return None

    files = find_session_files(resolved_dir, project_path=project_path)
    if not files:
        logger.debug("No Claude Code session files found")
        return None

    # Parse the most recent file
    return parse_session_file(files[0])
