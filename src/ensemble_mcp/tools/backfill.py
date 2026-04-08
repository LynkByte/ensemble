"""Post-session token backfill engine.

Reads real token usage from AI tool session files (OpenCode SQLite DB or
Claude Code JSONL) and retroactively updates ensemble-mcp step records
that were originally recorded with zero or estimated tokens.

Supports both OpenCode and Claude Code via the shared parser dispatcher.
The matching algorithm pairs ensemble-mcp steps to parsed messages by
timestamp proximity and model name.

Usage:
    result = backfill_session(conn, session_id="sess_abc123")
    result = backfill_session(conn, force=True)          # overwrite existing
    result = backfill_session(conn, ai_tool_override="opencode")
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..config.defaults import (
    CONFIDENCE_EXACT,
    CONFIDENCE_PARTIAL,
    SOURCE_BACKFILL,
    SOURCE_ESTIMATOR,
)
from ..config.pricing import PRICING_VERSION, calculate_cost
from ..contracts.errors import ErrorCode, ToolError
from ..parsers import ParsedSession, ParsedStep, parse_latest_session

logger = logging.getLogger(__name__)

# Maximum seconds between an ensemble-mcp step and a parsed message
# for them to be considered a potential match.
MATCH_TOLERANCE_SECONDS = 120


@dataclass(slots=True)
class BackfillResult:
    """Summary of a backfill operation."""

    session_id: str
    steps_updated: int = 0
    steps_skipped: int = 0  # already backfilled
    steps_unmatched_db: int = 0  # DB steps with no parser match
    steps_unmatched_parser: int = 0  # parser steps with no DB match
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    source: str = SOURCE_BACKFILL
    confidence: str = CONFIDENCE_EXACT
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "steps_updated": self.steps_updated,
            "steps_skipped": self.steps_skipped,
            "steps_unmatched_db": self.steps_unmatched_db,
            "steps_unmatched_parser": self.steps_unmatched_parser,
            "before": self.before,
            "after": self.after,
            "source": self.source,
            "confidence": self.confidence,
            "errors": self.errors,
        }


# ── Timestamp helpers ─────────────────────────────────────────────


def _parse_iso_timestamp(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string to a datetime object."""
    if not ts:
        return None
    try:
        # Handle various ISO formats: with/without timezone, with/without T
        ts = ts.replace("Z", "+00:00")
        if "T" not in ts and " " in ts:
            ts = ts.replace(" ", "T", 1)
        # Ensure timezone-aware for comparison
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        return None


def _timestamp_distance_seconds(
    ts_a: str | None,
    ts_b: str | None,
) -> float | None:
    """Return the absolute distance in seconds between two ISO timestamps."""
    dt_a = _parse_iso_timestamp(ts_a)
    dt_b = _parse_iso_timestamp(ts_b)
    if dt_a is None or dt_b is None:
        return None
    return abs((dt_a - dt_b).total_seconds())


# ── Matching ──────────────────────────────────────────────────────


@dataclass(slots=True)
class StepMatch:
    """A matched pair of DB step and parsed step."""

    db_step_id: int
    db_step_model: str | None
    parsed_step: ParsedStep
    distance_seconds: float | None


def match_steps(
    db_steps: list[dict[str, Any]],
    parsed_steps: list[ParsedStep],
    tolerance_seconds: float = MATCH_TOLERANCE_SECONDS,
) -> tuple[list[StepMatch], list[int], list[int]]:
    """Match DB steps to parsed steps by timestamp proximity + model name.

    Uses greedy nearest-timestamp matching.  Each parsed step can only
    be claimed by one DB step.

    Parameters
    ----------
    db_steps:
        Rows from the ``steps`` table, each a dict with at minimum
        ``id``, ``model``, ``started_at``, ``source``.
    parsed_steps:
        ``ParsedStep`` objects from the parser.
    tolerance_seconds:
        Maximum timestamp distance for a match.

    Returns
    -------
    (matches, unmatched_db_ids, unmatched_parser_indices)
    """
    claimed_parser: set[int] = set()
    matches: list[StepMatch] = []
    unmatched_db: list[int] = []

    for db_step in db_steps:
        best_idx: int | None = None
        best_dist: float | None = None

        for i, ps in enumerate(parsed_steps):
            if i in claimed_parser:
                continue

            # Compute timestamp distance
            dist = _timestamp_distance_seconds(db_step["started_at"], ps.timestamp)

            # Model name matching: prefer exact match, accept if either is None
            model_match = (
                db_step.get("model") is None
                or ps.model is None
                or _normalize_model(db_step["model"]) == _normalize_model(ps.model)
            )

            if not model_match and dist is not None and dist < 10:  # noqa: SIM102
                # Still allow if timestamp is very close (< 10s) — model
                # names may differ between provider and ensemble-mcp.
                model_match = True

            if not model_match:
                continue

            if (
                dist is not None
                and dist <= tolerance_seconds
                and (best_dist is None or dist < best_dist)
            ):
                best_dist = dist
                best_idx = i

        if best_idx is not None:
            claimed_parser.add(best_idx)
            matches.append(
                StepMatch(
                    db_step_id=db_step["id"],
                    db_step_model=db_step.get("model"),
                    parsed_step=parsed_steps[best_idx],
                    distance_seconds=best_dist,
                )
            )
        else:
            unmatched_db.append(db_step["id"])

    unmatched_parser = [i for i in range(len(parsed_steps)) if i not in claimed_parser]
    return matches, unmatched_db, unmatched_parser


def _normalize_model(model: str) -> str:
    """Normalize model names for comparison.

    Strips common prefixes/suffixes and version indicators so that
    e.g. ``"claude-opus-4-20250514"`` matches ``"claude-opus-4"``.
    """
    m = model.lower().strip()
    # Remove common provider prefixes
    for prefix in ("anthropic/", "openai/", "github-copilot/"):
        if m.startswith(prefix):
            m = m[len(prefix) :]
    # Remove date suffixes like -20250514
    parts = m.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) >= 8:
        m = parts[0]
    return m


# ── Step UPDATE ───────────────────────────────────────────────────


def _update_step(
    conn: sqlite3.Connection,
    step_id: int,
    ps: ParsedStep,
    model: str | None,
) -> float:
    """Update a single step with parsed token data.  Returns cost_usd."""
    cached_tok = ps.cache_read_tokens  # for billing purposes

    cost_usd, _ = calculate_cost(
        input_tokens=ps.input_tokens,
        output_tokens=ps.output_tokens,
        cached_tokens=cached_tok,
        cache_write_tokens=ps.cache_write_tokens,
        web_search_requests=ps.web_search_requests,
        model=model or ps.model or "claude-sonnet-4",
    )

    conn.execute(
        "UPDATE steps SET "
        "input_tokens = ?, "
        "output_tokens = ?, "
        "cache_read_tokens = ?, "
        "cache_write_tokens = ?, "
        "web_search_requests = ?, "
        "reasoning_tokens = ?, "
        "cached_tokens = ?, "
        "cost_usd = ?, "
        "pricing_version = ?, "
        "source = ?, "
        "accuracy = ? "
        "WHERE id = ?",
        (
            ps.input_tokens,
            ps.output_tokens,
            ps.cache_read_tokens,
            ps.cache_write_tokens,
            ps.web_search_requests,
            ps.reasoning_tokens,
            cached_tok,
            cost_usd,
            PRICING_VERSION,
            SOURCE_BACKFILL,
            CONFIDENCE_EXACT,
            step_id,
        ),
    )
    return cost_usd


def _recompute_session_totals(
    conn: sqlite3.Connection,
    session_id: str,
) -> dict[str, Any]:
    """Recompute session totals from step data and return the new values."""
    row = conn.execute(
        "SELECT "
        "COALESCE(SUM(input_tokens), 0), "
        "COALESCE(SUM(output_tokens), 0), "
        "COALESCE(SUM(cached_tokens), 0), "
        "COALESCE(SUM(cost_usd), 0.0) "
        "FROM steps WHERE session_id = ?",
        (session_id,),
    ).fetchone()

    totals = {
        "total_input_tokens": row[0],
        "total_output_tokens": row[1],
        "total_cached_tokens": row[2],
        "total_cost_usd": round(row[3], 6),
    }

    conn.execute(
        "UPDATE sessions SET "
        "total_input_tokens = ?, "
        "total_output_tokens = ?, "
        "total_cached_tokens = ?, "
        "total_cost_usd = ? "
        "WHERE id = ?",
        (
            totals["total_input_tokens"],
            totals["total_output_tokens"],
            totals["total_cached_tokens"],
            totals["total_cost_usd"],
            session_id,
        ),
    )
    return totals


# ── Main entry point ──────────────────────────────────────────────


def _get_session_snapshot(
    conn: sqlite3.Connection,
    session_id: str,
) -> dict[str, Any]:
    """Read current session totals for before/after comparison."""
    row = conn.execute(
        "SELECT total_input_tokens, total_output_tokens, "
        "total_cached_tokens, total_cost_usd "
        "FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return {}
    return {
        "total_input_tokens": row[0],
        "total_output_tokens": row[1],
        "total_cached_tokens": row[2],
        "total_cost_usd": row[3],
    }


def backfill_session(
    conn: sqlite3.Connection,
    session_id: str | None = None,
    *,
    force: bool = False,
    ai_tool_override: str | None = None,
    opencode_db_path: Any | None = None,
    claude_projects_dir: Any | None = None,
) -> BackfillResult:
    """Backfill a session's step records with real token data from AI tool session files.

    Parameters
    ----------
    conn:
        ensemble-mcp SQLite connection.
    session_id:
        The session to backfill.  If *None*, uses the most recent session.
    force:
        If True, overwrite steps that were already backfilled or have
        real token data.
    ai_tool_override:
        Force a specific parser (e.g. ``"opencode"``, ``"claude-code"``).
    opencode_db_path:
        Override the default OpenCode DB path (for testing).
    claude_projects_dir:
        Override the default Claude Code projects dir (for testing).

    Returns
    -------
    BackfillResult
        Summary including steps updated, before/after totals, and errors.
    """
    # ── Resolve session ──────────────────────────────────────────
    if session_id is None:
        row = conn.execute("SELECT id FROM sessions ORDER BY started_at DESC LIMIT 1").fetchone()
        if not row:
            raise ToolError(
                code=ErrorCode.NOT_FOUND_SESSION,
                message="No sessions found to backfill",
            )
        session_id = row[0]

    session = conn.execute(
        "SELECT id, ai_tool, project, started_at, ended_at FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if not session:
        raise ToolError(
            code=ErrorCode.NOT_FOUND_SESSION,
            message=f"No session with id {session_id}",
            details={"session_id": session_id},
        )

    result = BackfillResult(session_id=session_id)

    ai_tool = ai_tool_override or session[1]  # session.ai_tool
    project_path = session[2]  # session.project

    if not ai_tool:
        raise ToolError(
            code=ErrorCode.VALIDATION_MISSING_FIELD,
            message=(
                "Session has no ai_tool set and no override provided. "
                "Pass ai_tool_override='opencode' or 'claude-code'."
            ),
            details={"session_id": session_id},
        )

    # ── Parse AI tool session ────────────────────────────────────
    try:
        parsed: ParsedSession | None = parse_latest_session(
            ai_tool=ai_tool,
            project_path=project_path,
            opencode_db_path=opencode_db_path,
            claude_projects_dir=claude_projects_dir,
        )
    except Exception as exc:
        raise ToolError(
            code=ErrorCode.IO_FILESYSTEM,
            message=f"Parser failed for ai_tool={ai_tool!r}: {exc}",
            details={"ai_tool": ai_tool, "error": str(exc)},
        ) from exc

    if not parsed or not parsed.steps:
        raise ToolError(
            code=ErrorCode.NOT_FOUND_SESSION,
            message=(
                f"No parsed session data found for ai_tool={ai_tool!r}. "
                "The AI tool may not have any recent session files."
            ),
            details={"ai_tool": ai_tool, "project": project_path},
        )

    # ── Load DB steps ────────────────────────────────────────────
    step_rows = conn.execute(
        "SELECT id, model, started_at, source, accuracy "
        "FROM steps WHERE session_id = ? ORDER BY started_at ASC",
        (session_id,),
    ).fetchall()

    if not step_rows:
        raise ToolError(
            code=ErrorCode.NOT_FOUND_STEP,
            message=f"No steps found for session {session_id}",
            details={"session_id": session_id},
        )

    # Snapshot before
    result.before = _get_session_snapshot(conn, session_id)

    # Separate steps into backfillable and skip
    db_steps_for_matching: list[dict[str, Any]] = []
    skipped_ids: set[int] = set()

    for row in step_rows:
        step_dict = {
            "id": row[0],
            "model": row[1],
            "started_at": row[2],
            "source": row[3],
            "accuracy": row[4],
        }

        # Skip steps that already have real data (unless forced)
        if (
            not force
            and step_dict["source"] not in (SOURCE_ESTIMATOR, "estimator")
            and step_dict["source"]
            in (
                SOURCE_BACKFILL,
                "backfill",
                "session_parser",
                "live_response_usage",
                "local",
            )
        ):
            skipped_ids.add(step_dict["id"])
            result.steps_skipped += 1
            continue

        db_steps_for_matching.append(step_dict)

    if not db_steps_for_matching:
        # All steps already backfilled
        result.after = _get_session_snapshot(conn, session_id)
        return result

    # ── Match and update ─────────────────────────────────────────
    matches, unmatched_db, unmatched_parser = match_steps(
        db_steps_for_matching,
        parsed.steps,
    )

    result.steps_unmatched_db = len(unmatched_db)
    result.steps_unmatched_parser = len(unmatched_parser)

    for m in matches:
        try:
            _update_step(conn, m.db_step_id, m.parsed_step, m.db_step_model)
            result.steps_updated += 1
        except Exception as exc:
            result.errors.append(f"Failed to update step {m.db_step_id}: {exc}")
            logger.warning("Failed to update step %d: %s", m.db_step_id, exc)

    # ── Recompute session totals ─────────────────────────────────
    if result.steps_updated > 0:
        result.after = _recompute_session_totals(conn, session_id)
        conn.commit()
    else:
        result.after = _get_session_snapshot(conn, session_id)

    # Set confidence based on outcome
    if result.errors or result.steps_unmatched_db > 0:
        result.confidence = CONFIDENCE_PARTIAL

    return result
