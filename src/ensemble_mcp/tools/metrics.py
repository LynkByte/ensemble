"""Metrics tools: metrics_start_session, metrics_record_step,
metrics_end_session, metrics_session_report, metrics_trend, metrics_compare.

Token tracking with per-agent cost breakdown using hybrid source precedence:
1. Direct response usage (exact)
2. ``usage_raw`` provider payload parsing (exact)
3. AI tool session parsers (exact/partial) — OpenCode + Claude Code
4. Tokenizer estimation via tiktoken (estimated)
"""

from __future__ import annotations

import json as _json
import sqlite3
import uuid
from typing import Any

from ..config.defaults import CONFIDENCE_EXACT, CONFIDENCE_PARTIAL, SOURCE_PARSER
from ..config.pricing import PRICING_VERSION, calculate_cost
from ..contracts.envelope import tool_handler
from ..contracts.errors import ErrorCode, ToolError
from ..state.idempotency import check_idempotency, store_idempotency
from ..state.lifecycle import SessionState, transition_session
from .token_utils import resolve_token_fields


@tool_handler(source="sqlite", confidence="exact")
async def metrics_start_session(
    conn: sqlite3.Connection,
    *,
    task: str,
    classification: str,
    ai_tool: str | None = None,
    project: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Start tracking a pipeline session."""
    cached = check_idempotency(conn, idempotency_key)
    if cached is not None:
        return cached

    session_id = f"sess_{uuid.uuid4().hex[:12]}"

    conn.execute(
        "INSERT INTO sessions (id, task, classification, ai_tool, project, state) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, task, classification, ai_tool, project, SessionState.RUNNING.value),
    )
    conn.commit()

    result = {"session_id": session_id, "state": SessionState.RUNNING.value}
    store_idempotency(conn, idempotency_key, result)
    return result


@tool_handler(source="sqlite")
async def metrics_record_step(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    agent: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
    web_search_requests: int | None = None,
    cached_tokens: int | None = None,
    usage_raw: dict[str, Any] | None = None,
    provider: str | None = None,
    model: str | None = None,
    source: str | None = None,
    confidence: str | None = None,
    input_text: str | None = None,
    output_text: str | None = None,
    duration_ms: int | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Record per-agent token and cost usage.

    Uses the best available source (3-tier precedence):
    1. Direct token fields (exact) — ``input_tokens``, ``output_tokens``, etc.
    2. ``usage_raw`` provider payload (exact) — Anthropic/OpenAI format auto-detected.
    3. ``tiktoken`` estimation (estimated) — from ``input_text`` / ``output_text``.
    """
    cached_result = check_idempotency(conn, idempotency_key)
    if cached_result is not None:
        return cached_result

    # Verify session exists
    session = conn.execute(
        "SELECT id, state FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if not session:
        raise ToolError(
            code=ErrorCode.NOT_FOUND_SESSION,
            message=f"No session with id {session_id}",
            details={"session_id": session_id},
        )

    # Resolve tokens via 3-tier precedence
    resolved = resolve_token_fields(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        web_search_requests=web_search_requests,
        cached_tokens=cached_tokens,
        usage_raw=usage_raw,
        provider=provider,
        input_text=input_text,
        output_text=output_text,
        source=source,
        confidence=confidence,
    )

    # ── Phase 3: Session parser fallback ─────────────────────────
    # If tokens are still zero and the parent session has an ai_tool,
    # attempt to extract usage from the AI tool's local session files.
    if (
        resolved["input_tokens"] == 0
        and resolved["output_tokens"] == 0
        and source is None  # don't override an explicit source label
    ):
        # Look up ai_tool from the parent session
        session_ai_tool = conn.execute(
            "SELECT ai_tool FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        ai_tool_name = session_ai_tool[0] if session_ai_tool else None

        if ai_tool_name:
            try:
                from ..parsers import parse_latest_session as _parser_dispatch

                parsed = _parser_dispatch(ai_tool=ai_tool_name)
                if parsed and parsed.total_input_tokens > 0:
                    resolved["input_tokens"] = parsed.total_input_tokens
                    resolved["output_tokens"] = parsed.total_output_tokens
                    resolved["cache_read_tokens"] = parsed.total_cache_read_tokens
                    resolved["cache_write_tokens"] = parsed.total_cache_write_tokens
                    resolved["cached_tokens"] = parsed.total_cache_read_tokens
                    resolved["source"] = SOURCE_PARSER
                    resolved["confidence"] = parsed.confidence
            except Exception:
                # Parser failures are non-fatal — fall through to
                # whatever resolve_token_fields already produced.
                import logging as _logging

                _logging.getLogger(__name__).debug(
                    "Session parser fallback failed for ai_tool=%s",
                    ai_tool_name,
                    exc_info=True,
                )

    in_tok: int = resolved["input_tokens"]
    out_tok: int = resolved["output_tokens"]
    cache_read: int = resolved["cache_read_tokens"]
    cache_write: int = resolved["cache_write_tokens"]
    web_reqs: int = resolved["web_search_requests"]
    cached_tok: int = resolved["cached_tokens"]
    effective_source: str = resolved["source"]
    effective_confidence: str = resolved["confidence"]

    # Calculate cost
    cost_usd, unknown_model = calculate_cost(
        input_tokens=in_tok,
        output_tokens=out_tok,
        cached_tokens=cached_tok,
        cache_write_tokens=cache_write,
        web_search_requests=web_reqs,
        model=model or "claude-sonnet-4",
    )

    conn.execute(
        "INSERT INTO steps "
        "(session_id, agent, model, model_canonical_name, "
        "input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
        "web_search_requests, cached_tokens, cost_usd, pricing_version, "
        "source, duration_ms, unknown_model_cost, accuracy) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            agent,
            model,
            model,
            in_tok,
            out_tok,
            cache_read,
            cache_write,
            web_reqs,
            cached_tok,
            cost_usd,
            PRICING_VERSION,
            effective_source,
            duration_ms,
            int(unknown_model),
            effective_confidence,
        ),
    )

    # Update session totals
    conn.execute(
        "UPDATE sessions SET "
        "total_input_tokens = total_input_tokens + ?, "
        "total_output_tokens = total_output_tokens + ?, "
        "total_cached_tokens = total_cached_tokens + ?, "
        "total_cost_usd = total_cost_usd + ? "
        "WHERE id = ?",
        (in_tok, out_tok, cached_tok, cost_usd, session_id),
    )
    conn.commit()

    result: dict[str, Any] = {
        "recorded": True,
        "step_id": conn.execute("SELECT last_insert_rowid()").fetchone()[0],
        "cost_usd": cost_usd,
        "confidence": effective_confidence,
        "source": effective_source,
        "__confidence__": effective_confidence,
        "__source__": "sqlite",
    }
    store_idempotency(conn, idempotency_key, result)
    return result


@tool_handler(source="sqlite", confidence="exact")
async def metrics_end_session(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    status: str = "completed",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Finalize a session, compute totals."""
    cached = check_idempotency(conn, idempotency_key)
    if cached is not None:
        return cached

    session = conn.execute(
        "SELECT id, state, total_cost_usd FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if not session:
        raise ToolError(
            code=ErrorCode.NOT_FOUND_SESSION,
            message=f"No session with id {session_id}",
            details={"session_id": session_id},
        )

    # Map status to state
    state_map = {
        "completed": SessionState.COMPLETED,
        "success": SessionState.COMPLETED,
        "failed": SessionState.FAILED,
        "partial": SessionState.FAILED,
        "killed": SessionState.KILLED,
    }
    target_state = state_map.get(status, SessionState.COMPLETED)
    new_state = transition_session(session[1], target_state)

    conn.execute(
        "UPDATE sessions SET state = ?, status = ?, ended_at = datetime('now') WHERE id = ?",
        (new_state.value, status, session_id),
    )

    # Auto-generate and store report_json
    step_rows = conn.execute(
        "SELECT agent, model, input_tokens, output_tokens, cached_tokens, "
        "cost_usd, accuracy FROM steps WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    step_summary = [
        {
            "agent": r[0],
            "model": r[1],
            "input_tokens": r[2],
            "output_tokens": r[3],
            "cached_tokens": r[4],
            "cost_usd": r[5],
            "accuracy": r[6],
        }
        for r in step_rows
    ]
    report_data = {
        "session_id": session_id,
        "status": status,
        "state": new_state.value,
        "total_cost_usd": session[2],
        "steps": step_summary,
    }
    conn.execute(
        "UPDATE sessions SET report_json = ? WHERE id = ?",
        (_json.dumps(report_data, default=str), session_id),
    )
    conn.commit()

    result: dict[str, Any] = {
        "session_id": session_id,
        "total_cost": session[2],
        "state": new_state.value,
        "status": status,
    }
    store_idempotency(conn, idempotency_key, result)
    return result


@tool_handler(source="sqlite", confidence="exact")
async def metrics_session_report(
    conn: sqlite3.Connection,
    *,
    session_id: str,
) -> dict[str, Any]:
    """Generate a formatted session report with ASCII table and structured data."""
    from .report_formatter import format_session_report

    session = conn.execute(
        "SELECT id, task, classification, ai_tool, state, status, "
        "total_input_tokens, total_output_tokens, total_cached_tokens, "
        "total_cost_usd, started_at, ended_at "
        "FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()

    if not session:
        raise ToolError(
            code=ErrorCode.NOT_FOUND_SESSION,
            message=f"No session with id {session_id}",
            details={"session_id": session_id},
        )

    # Get step breakdown
    steps = conn.execute(
        "SELECT agent, model, input_tokens, output_tokens, cached_tokens, "
        "cost_usd, accuracy, duration_ms FROM steps WHERE session_id = ? "
        "ORDER BY started_at",
        (session_id,),
    ).fetchall()

    step_data: list[dict[str, Any]] = []
    overall_confidence = CONFIDENCE_EXACT
    for s in steps:
        step_data.append(
            {
                "agent": s[0],
                "model": s[1],
                "input_tokens": s[2],
                "output_tokens": s[3],
                "cached_tokens": s[4],
                "cost_usd": s[5],
                "accuracy": s[6],
                "duration_ms": s[7],
            }
        )
        if s[6] == "estimated":
            overall_confidence = CONFIDENCE_PARTIAL

    # Get MCP call summary
    mcp_calls_rows = conn.execute(
        "SELECT tool_name, input_bytes, output_bytes, duration_ms "
        "FROM mcp_calls WHERE session_id = ? ORDER BY called_at",
        (session_id,),
    ).fetchall()
    mcp_calls: list[dict[str, Any]] = [
        {
            "tool_name": r[0],
            "input_bytes": r[1],
            "output_bytes": r[2],
            "duration_ms": r[3],
        }
        for r in mcp_calls_rows
    ]

    # Get cumulative project stats
    project = conn.execute(
        "SELECT project FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    cumulative_sessions = None
    cumulative_cost = None
    if project and project[0]:
        cum = conn.execute(
            "SELECT COUNT(*), SUM(total_cost_usd) FROM sessions WHERE project = ?",
            (project[0],),
        ).fetchone()
        if cum:
            cumulative_sessions = cum[0]
            cumulative_cost = cum[1] or 0.0

    # Build structured report
    report: dict[str, Any] = {
        "session_id": session[0],
        "task": session[1],
        "classification": session[2],
        "ai_tool": session[3],
        "state": session[4],
        "status": session[5],
        "total_input_tokens": session[6],
        "total_output_tokens": session[7],
        "total_cached_tokens": session[8],
        "total_cost_usd": session[9],
        "started_at": session[10],
        "ended_at": session[11],
        "steps": step_data,
        "mcp_calls": mcp_calls,
        "overall_confidence": overall_confidence,
    }

    # Generate ASCII report
    formatted = format_session_report(
        session_id=session[0],
        task=session[1],
        classification=session[2],
        status=session[5],
        state=session[4],
        ai_tool=session[3],
        total_input_tokens=session[6],
        total_output_tokens=session[7],
        total_cached_tokens=session[8],
        total_cost_usd=session[9],
        started_at=session[10],
        ended_at=session[11],
        steps=step_data,
        mcp_calls=mcp_calls if mcp_calls else None,
        overall_confidence=overall_confidence,
        cumulative_sessions=cumulative_sessions,
        cumulative_cost=cumulative_cost,
    )

    # Store report_json on session
    conn.execute(
        "UPDATE sessions SET report_json = ? WHERE id = ?",
        (_json.dumps(report, default=str), session_id),
    )
    conn.commit()

    return {
        "report": report,
        "formatted_report": formatted,
        "__confidence__": overall_confidence,
    }


@tool_handler(source="sqlite", confidence="exact")
async def metrics_trend(
    conn: sqlite3.Connection,
    *,
    days: int = 30,
) -> dict[str, Any]:
    """Cost/token trends over the last N days."""
    rows = conn.execute(
        "SELECT date(started_at) as day, "
        "SUM(total_input_tokens) as input_tok, "
        "SUM(total_output_tokens) as output_tok, "
        "SUM(total_cost_usd) as cost, "
        "COUNT(*) as sessions "
        "FROM sessions "
        "WHERE started_at >= datetime('now', ? || ' days') "
        "GROUP BY date(started_at) ORDER BY day",
        (f"-{days}",),
    ).fetchall()

    daily: list[dict[str, Any]] = []
    for r in rows:
        daily.append(
            {
                "date": r[0],
                "input_tokens": r[1] or 0,
                "output_tokens": r[2] or 0,
                "cost_usd": round(r[3] or 0, 4),
                "sessions": r[4],
            }
        )

    total_cost = sum(d["cost_usd"] for d in daily)
    total_sessions = sum(d["sessions"] for d in daily)
    avg_cost = round(total_cost / max(total_sessions, 1), 4)

    # Compute trend direction: compare first half vs second half of the period
    trend = "stable"
    if len(daily) >= 2:
        mid = len(daily) // 2
        first_half_cost = sum(d["cost_usd"] for d in daily[:mid])
        second_half_cost = sum(d["cost_usd"] for d in daily[mid:])
        if first_half_cost > 0:
            change_pct = (second_half_cost - first_half_cost) / first_half_cost * 100
            if change_pct > 10:
                trend = f"increasing (+{change_pct:.0f}%)"
            elif change_pct < -10:
                trend = f"decreasing ({change_pct:.0f}%)"

    return {
        "daily_costs": daily,
        "total_cost": round(total_cost, 4),
        "total_sessions": total_sessions,
        "avg_cost_per_session": avg_cost,
        "trend": trend,
        "days": days,
    }


@tool_handler(source="sqlite", confidence="exact")
async def metrics_compare(
    conn: sqlite3.Connection,
    *,
    session_id_a: str,
    session_id_b: str,
) -> dict[str, Any]:
    """Compare two sessions side by side."""

    def _get_session(sid: str) -> dict[str, Any]:
        row = conn.execute(
            "SELECT id, task, classification, total_input_tokens, "
            "total_output_tokens, total_cached_tokens, total_cost_usd "
            "FROM sessions WHERE id = ?",
            (sid,),
        ).fetchone()
        if not row:
            raise ToolError(
                code=ErrorCode.NOT_FOUND_SESSION,
                message=f"No session with id {sid}",
                details={"session_id": sid},
            )
        return {
            "session_id": row[0],
            "task": row[1],
            "classification": row[2],
            "input_tokens": row[3],
            "output_tokens": row[4],
            "cached_tokens": row[5],
            "cost_usd": row[6],
        }

    def _get_step_breakdown(sid: str) -> list[dict[str, Any]]:
        step_rows = conn.execute(
            "SELECT agent, model, input_tokens, output_tokens, "
            "cached_tokens, cost_usd, accuracy "
            "FROM steps WHERE session_id = ? ORDER BY started_at",
            (sid,),
        ).fetchall()
        return [
            {
                "agent": r[0],
                "model": r[1],
                "input_tokens": r[2],
                "output_tokens": r[3],
                "cached_tokens": r[4],
                "cost_usd": r[5],
                "accuracy": r[6],
            }
            for r in step_rows
        ]

    a = _get_session(session_id_a)
    b = _get_session(session_id_b)
    steps_a = _get_step_breakdown(session_id_a)
    steps_b = _get_step_breakdown(session_id_b)

    # Determine overall confidence from step accuracies
    all_accuracies = [s["accuracy"] for s in steps_a + steps_b if s.get("accuracy")]
    overall_confidence = CONFIDENCE_EXACT
    if "estimated" in all_accuracies:
        overall_confidence = CONFIDENCE_PARTIAL

    return {
        "session_a": {**a, "steps": steps_a},
        "session_b": {**b, "steps": steps_b},
        "diff": {
            "input_tokens": b["input_tokens"] - a["input_tokens"],
            "output_tokens": b["output_tokens"] - a["output_tokens"],
            "cost_usd": round(b["cost_usd"] - a["cost_usd"], 6),
        },
        "__confidence__": overall_confidence,
    }
