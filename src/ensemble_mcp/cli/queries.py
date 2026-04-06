"""Direct SQLite queries for the CLI dashboard.

Reads from the ``sessions`` and ``steps`` tables to produce aggregate
data for the dashboard display.  These bypass the MCP tool layer for
efficiency — the dashboard reads the same DB directly.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

# ── Data containers ──────────────────────────────────────────────


@dataclass(slots=True)
class PeriodSummary:
    """Aggregate stats for a time period."""

    sessions: int = 0
    cost_usd: float = 0.0
    total_tokens: int = 0


@dataclass(slots=True)
class AgentCost:
    """Cost breakdown for a single agent."""

    agent: str = ""
    cost_usd: float = 0.0
    share_pct: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(slots=True)
class RecentSession:
    """Summary of a recent session for the dashboard table."""

    row_num: int = 0
    task: str = ""
    classification: str = ""
    cost_usd: float = 0.0
    status: str = ""
    started_at: str = ""


@dataclass(slots=True)
class DailyTrend:
    """Daily aggregate for trend display."""

    date: str = ""
    sessions: int = 0
    cost_usd: float = 0.0
    tokens: int = 0


@dataclass(slots=True)
class DashboardData:
    """All data needed to render the dashboard."""

    today: PeriodSummary = field(default_factory=PeriodSummary)
    week: PeriodSummary = field(default_factory=PeriodSummary)
    month: PeriodSummary = field(default_factory=PeriodSummary)
    cost_by_agent: list[AgentCost] = field(default_factory=list)
    recent_sessions: list[RecentSession] = field(default_factory=list)
    daily_trend: list[DailyTrend] = field(default_factory=list)


# ── Queries ──────────────────────────────────────────────────────


def _period_summary(conn: sqlite3.Connection, days: int) -> PeriodSummary:
    """Aggregate sessions within the last N days."""
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(total_cost_usd), 0), "
        "COALESCE(SUM(total_input_tokens + total_output_tokens), 0) "
        "FROM sessions "
        "WHERE started_at >= datetime('now', ? || ' days')",
        (f"-{days}",),
    ).fetchone()
    if not row:
        return PeriodSummary()
    return PeriodSummary(
        sessions=row[0] or 0,
        cost_usd=round(row[1] or 0.0, 4),
        total_tokens=row[2] or 0,
    )


def get_period_summaries(
    conn: sqlite3.Connection,
) -> tuple[PeriodSummary, PeriodSummary, PeriodSummary]:
    """Return summary stats for today (1 day), this week (7 days), and this month (30 days)."""
    today = _period_summary(conn, 1)
    week = _period_summary(conn, 7)
    month = _period_summary(conn, 30)
    return today, week, month


def get_cost_by_agent(
    conn: sqlite3.Connection,
    days: int = 1,
) -> list[AgentCost]:
    """Return per-agent cost breakdown sorted by cost descending.

    Aggregates from the ``steps`` table, joining through ``sessions``
    to filter by time range.
    """
    rows = conn.execute(
        "SELECT s.agent, "
        "COALESCE(SUM(s.cost_usd), 0), "
        "COALESCE(SUM(s.input_tokens), 0), "
        "COALESCE(SUM(s.output_tokens), 0) "
        "FROM steps s "
        "JOIN sessions sess ON s.session_id = sess.id "
        "WHERE sess.started_at >= datetime('now', ? || ' days') "
        "GROUP BY s.agent "
        "ORDER BY SUM(s.cost_usd) DESC",
        (f"-{days}",),
    ).fetchall()

    total_cost = sum(r[1] for r in rows) if rows else 0.0
    result: list[AgentCost] = []
    for r in rows:
        cost = round(r[1] or 0.0, 4)
        share = round((cost / total_cost * 100) if total_cost > 0 else 0.0, 1)
        result.append(
            AgentCost(
                agent=r[0] or "?",
                cost_usd=cost,
                share_pct=share,
                input_tokens=r[2] or 0,
                output_tokens=r[3] or 0,
            )
        )
    return result


def get_recent_sessions(
    conn: sqlite3.Connection,
    limit: int = 10,
) -> list[RecentSession]:
    """Return the most recent sessions, newest first."""
    rows = conn.execute(
        "SELECT id, task, classification, total_cost_usd, "
        "COALESCE(status, state, 'unknown'), started_at "
        "FROM sessions "
        "ORDER BY started_at DESC "
        "LIMIT ?",
        (limit,),
    ).fetchall()

    result: list[RecentSession] = []
    for i, r in enumerate(rows, 1):
        result.append(
            RecentSession(
                row_num=i,
                task=r[1] or "",
                classification=r[2] or "",
                cost_usd=round(r[3] or 0.0, 4),
                status=r[4] or "unknown",
                started_at=r[5] or "",
            )
        )
    return result


def get_daily_trend(
    conn: sqlite3.Connection,
    days: int = 7,
) -> list[DailyTrend]:
    """Return daily aggregate stats for the last N days."""
    rows = conn.execute(
        "SELECT date(started_at) as day, "
        "COUNT(*), "
        "COALESCE(SUM(total_cost_usd), 0), "
        "COALESCE(SUM(total_input_tokens + total_output_tokens), 0) "
        "FROM sessions "
        "WHERE started_at >= datetime('now', ? || ' days') "
        "GROUP BY date(started_at) "
        "ORDER BY day",
        (f"-{days}",),
    ).fetchall()

    return [
        DailyTrend(
            date=r[0] or "",
            sessions=r[1] or 0,
            cost_usd=round(r[2] or 0.0, 4),
            tokens=r[3] or 0,
        )
        for r in rows
    ]


def fetch_dashboard_data(
    conn: sqlite3.Connection,
    *,
    agent_days: int = 1,
    recent_limit: int = 10,
    trend_days: int = 7,
) -> DashboardData:
    """Fetch all data needed for the dashboard in a single call."""
    today, week, month = get_period_summaries(conn)
    return DashboardData(
        today=today,
        week=week,
        month=month,
        cost_by_agent=get_cost_by_agent(conn, days=agent_days),
        recent_sessions=get_recent_sessions(conn, limit=recent_limit),
        daily_trend=get_daily_trend(conn, days=trend_days),
    )
