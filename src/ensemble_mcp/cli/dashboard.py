"""Main dashboard composer and entry point.

Composes query results and widget renderers into a single dashboard
output string.  ``run_dashboard()`` is the CLI entry point that opens
the database, renders, and prints to stdout.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from ..config.defaults import DB_PATH
from ..state.locks import get_connection
from .queries import fetch_dashboard_data
from .widgets import (
    render_cost_by_agent,
    render_daily_trend,
    render_empty_dashboard,
    render_header,
    render_recent_sessions,
    render_summary_bar,
)


def render_dashboard(
    conn: sqlite3.Connection,
    *,
    days: int = 1,
    limit: int = 10,
    trend_days: int = 7,
) -> str:
    """Render the full ASCII dashboard from database data.

    Parameters
    ----------
    conn:
        Open SQLite connection to the ensemble-mcp database.
    days:
        Time range (in days) for the agent cost breakdown.
    limit:
        Maximum number of recent sessions to display.
    trend_days:
        Number of days to show in the daily trend chart.

    Returns
    -------
    str
        Multi-line ASCII dashboard ready for printing.
    """
    data = fetch_dashboard_data(
        conn,
        agent_days=days,
        recent_limit=limit,
        trend_days=trend_days,
    )

    # If there's absolutely no data, show a helpful empty state
    if data.today.sessions == 0 and data.week.sessions == 0 and data.month.sessions == 0:
        return render_empty_dashboard()

    sections: list[str] = [
        render_header(),
        "",
        render_summary_bar(data.today, data.week, data.month),
        "",
        render_cost_by_agent(data.cost_by_agent, days=days),
        "",
        render_recent_sessions(data.recent_sessions),
    ]

    # Daily trend is optional — only show if there's multi-day data
    if data.daily_trend:
        sections.append("")
        sections.append(render_daily_trend(data.daily_trend))

    return "\n".join(sections)


def run_dashboard(
    *,
    db_path: Path | None = None,
    days: int = 1,
    limit: int = 10,
    trend_days: int = 7,
) -> None:
    """Open the database, render the dashboard, and print to stdout.

    This is the main entry point called from ``__main__.py``.

    Parameters
    ----------
    db_path:
        Path to the SQLite database.  Defaults to ``~/.cache/ensemble-mcp/data.db``.
    days:
        Time range for agent cost breakdown.
    limit:
        Maximum recent sessions to display.
    trend_days:
        Days to show in the daily trend chart.
    """
    effective_path = db_path or DB_PATH

    if not effective_path.exists():
        print(render_empty_dashboard())  # noqa: T201
        return

    try:
        conn = get_connection(effective_path)
    except Exception as exc:
        sys.stderr.write(f"Error opening database at {effective_path}: {exc}\n")
        sys.exit(1)

    try:
        output = render_dashboard(
            conn,
            days=days,
            limit=limit,
            trend_days=trend_days,
        )
        print(output)  # noqa: T201
    finally:
        conn.close()
