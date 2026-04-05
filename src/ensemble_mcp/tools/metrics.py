"""Metrics tools: metrics_start_session, metrics_record_step,
metrics_end_session, metrics_session_report, metrics_trend, metrics_compare.

Token tracking with per-agent cost breakdown using hybrid source precedence:
1. Direct response usage (exact)
2. AI tool session parsers (exact/partial)
3. Tokenizer estimation via tiktoken (estimated)
"""

from __future__ import annotations

import sqlite3
import uuid

from ..config.defaults import CONFIDENCE_EXACT, CONFIDENCE_PARTIAL, SOURCE_LOCAL
from ..config.pricing import PRICING_VERSION, calculate_cost
from ..contracts.envelope import tool_handler
from ..contracts.errors import ErrorCode, ToolError
from ..state.idempotency import check_idempotency, store_idempotency
from ..state.lifecycle import SessionState, transition_session


@tool_handler(source="sqlite", confidence="exact")
async def metrics_start_session(
    conn: sqlite3.Connection,
    *,
    task: str,
    classification: str,
    ai_tool: str | None = None,
    project: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
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
    model: str | None = None,
    source: str | None = None,
    confidence: str | None = None,
    duration_ms: int | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Record per-agent token and cost usage.

    Uses the best available source: direct usage > parser > estimator.
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

    # Default values
    in_tok = input_tokens or 0
    out_tok = output_tokens or 0
    cache_read = cache_read_tokens or 0
    cache_write = cache_write_tokens or 0
    web_reqs = web_search_requests or 0
    cached_tok = cached_tokens or cache_read

    # Determine confidence
    effective_source = source or SOURCE_LOCAL
    effective_confidence = confidence or CONFIDENCE_EXACT
    if in_tok == 0 and out_tok == 0:
        effective_confidence = CONFIDENCE_PARTIAL

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

    result = {
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
) -> dict:
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
    conn.commit()

    result = {
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
) -> dict:
    """Generate a formatted session report."""
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

    step_data = []
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

    report = {
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
    }

    return {
        "report": report,
        "__confidence__": overall_confidence,
    }


@tool_handler(source="sqlite", confidence="exact")
async def metrics_trend(
    conn: sqlite3.Connection,
    *,
    days: int = 30,
) -> dict:
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

    daily: list[dict] = []
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

    return {
        "daily_costs": daily,
        "total_cost": round(total_cost, 4),
        "total_sessions": total_sessions,
        "avg_cost_per_session": avg_cost,
        "days": days,
    }


@tool_handler(source="sqlite", confidence="exact")
async def metrics_compare(
    conn: sqlite3.Connection,
    *,
    session_id_a: str,
    session_id_b: str,
) -> dict:
    """Compare two sessions side by side."""

    def _get_session(sid: str) -> dict:
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

    a = _get_session(session_id_a)
    b = _get_session(session_id_b)

    return {
        "session_a": a,
        "session_b": b,
        "diff": {
            "input_tokens": b["input_tokens"] - a["input_tokens"],
            "output_tokens": b["output_tokens"] - a["output_tokens"],
            "cost_usd": round(b["cost_usd"] - a["cost_usd"], 6),
        },
    }
