"""Reusable ASCII rendering components for CLI display.

Provides terminal width detection, number formatting, and table/chart
builders using Unicode box-drawing characters.  Consistent with the
style established in ``tools/report_formatter.py``.
"""

from __future__ import annotations

import shutil

from .queries import AgentCost, DailyTrend, PeriodSummary, RecentSession

# ── Terminal helpers ──────────────────────────────────────────────


def get_terminal_width() -> int:
    """Return the current terminal width, defaulting to 80."""
    try:
        return shutil.get_terminal_size((80, 24)).columns
    except Exception:
        return 80


# ── Number formatting ─────────────────────────────────────────────


def fmt_tokens(n: int) -> str:
    """Format a token count with appropriate suffix."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def fmt_cost(c: float) -> str:
    """Format a USD cost value."""
    return f"${c:.2f}"


def fmt_share(pct: float) -> str:
    """Format a percentage share."""
    if pct < 1.0 and pct > 0:
        return "<1%"
    return f"{pct:.0f}%"


def _status_symbol(status: str) -> str:
    """Map a session status to a display symbol."""
    status_lower = status.lower() if status else ""
    if status_lower in ("completed", "success"):
        return "✓"
    if status_lower in ("failed", "error"):
        return "✗"
    if status_lower in ("running", "pending"):
        return "…"
    if status_lower == "killed":
        return "☠"
    return status_lower[:6]


# ── Widget renderers ──────────────────────────────────────────────


def render_header() -> str:
    """Render the dashboard title and separator."""
    return "  Ensemble MCP - Dashboard\n  ═══════════════════════════"


def render_summary_bar(
    today: PeriodSummary,
    week: PeriodSummary,
    month: PeriodSummary,
) -> str:
    """Render the 3-line period summary.

    Example::

        Today: 8 sessions │ $9.42 │ 378K tokens
        Week:  42 sessions │ $48.67 │ 1.94M tokens
        Month: 156 sessions │ $178.23 │ 7.1M tokens
    """
    t_tok = fmt_tokens(today.total_tokens)
    w_tok = fmt_tokens(week.total_tokens)
    m_tok = fmt_tokens(month.total_tokens)
    t_cost = fmt_cost(today.cost_usd)
    w_cost = fmt_cost(week.cost_usd)
    m_cost = fmt_cost(month.cost_usd)
    lines = [
        f"  Today: {today.sessions} sessions │ {t_cost} │ {t_tok} tokens",
        f"  Week:  {week.sessions} sessions │ {w_cost} │ {w_tok} tokens",
        f"  Month: {month.sessions} sessions │ {m_cost} │ {m_tok} tokens",
    ]
    return "\n".join(lines)


def render_cost_by_agent(
    agents: list[AgentCost],
    days: int = 1,
) -> str:
    """Render the per-agent cost breakdown table.

    Example::

        Cost by Agent (last 1 day)
        ┌──────────┬──────────┬────────┬───────┐
        │ Agent    │ Cost     │ Share  │       │
        ...
    """
    if not agents:
        return "  Cost by Agent\n  (no data)"

    period_label = "today" if days == 1 else f"last {days} days"

    # Determine column widths
    w_agent = max(len(a.agent) for a in agents)
    w_agent = max(w_agent, len("Agent"), len("TOTAL"))

    w_cost = 9
    w_share = 6

    # Build table
    top = f"  ┌─{'─' * w_agent}─┬─{'─' * w_cost}─┬─{'─' * w_share}─┐"
    header = f"  │ {'Agent':<{w_agent}} │ {'Cost':>{w_cost}} │ {'Share':>{w_share}} │"
    sep = f"  ├─{'─' * w_agent}─┼─{'─' * w_cost}─┼─{'─' * w_share}─┤"
    bottom = f"  └─{'─' * w_agent}─┴─{'─' * w_cost}─┴─{'─' * w_share}─┘"

    lines = [f"  Cost by Agent ({period_label})", top, header, sep]

    total_cost = 0.0
    for a in agents:
        total_cost += a.cost_usd
        cost_str = fmt_cost(a.cost_usd)
        share_str = fmt_share(a.share_pct)
        lines.append(f"  │ {a.agent:<{w_agent}} │ {cost_str:>{w_cost}} │ {share_str:>{w_share}} │")

    if len(agents) > 1:
        lines.append(sep)
        lines.append(
            f"  │ {'TOTAL':<{w_agent}} │ {fmt_cost(total_cost):>{w_cost}} │ {'100%':>{w_share}} │"
        )

    lines.append(bottom)
    return "\n".join(lines)


def render_recent_sessions(
    sessions: list[RecentSession],
    max_task_width: int | None = None,
) -> str:
    """Render the recent sessions table.

    Example::

        Recent Sessions
        ┌────┬────────────────────────┬──────────┬────────┬────────┐
        │ #  │ Task                   │ Class    │ Cost   │ Status │
        ...
    """
    if not sessions:
        return "  Recent Sessions\n  (no sessions)"

    # Terminal-aware task width
    term_width = get_terminal_width()
    w_num = 3
    w_class = 8
    w_cost = 8
    w_status = 6
    # Fixed overhead: 2 indent + 5 borders (│ + spaces) + 4 separators
    fixed = 2 + (w_num + 2) + (w_class + 2) + (w_cost + 2) + (w_status + 2) + 5 + 4
    if max_task_width is not None:
        w_task = max_task_width
    else:
        w_task = max(term_width - fixed, 12)
        w_task = min(w_task, 40)  # cap at 40

    def _hline(l: str, m: str, r: str) -> str:  # noqa: E741
        """Build a horizontal table border."""
        return (
            f"  {l}─{'─' * w_num}─{m}─{'─' * w_task}─"
            f"{m}─{'─' * w_class}─{m}─{'─' * w_cost}─"
            f"{m}─{'─' * w_status}─{r}"
        )

    top = _hline("┌", "┬", "┐")
    header = (
        f"  │ {'#':>{w_num}} │ {'Task':<{w_task}} │ {'Class':<{w_class}} │ "
        f"{'Cost':>{w_cost}} │ {'Status':>{w_status}} │"
    )
    sep = _hline("├", "┼", "┤")
    bottom = _hline("└", "┴", "┘")

    lines = ["  Recent Sessions", top, header, sep]

    for s in sessions:
        task_display = s.task[:w_task] if len(s.task) > w_task else s.task
        status_sym = _status_symbol(s.status)
        lines.append(
            f"  │ {s.row_num:>{w_num}} │ {task_display:<{w_task}} │ "
            f"{s.classification:<{w_class}} │ {fmt_cost(s.cost_usd):>{w_cost}} │ "
            f"{status_sym:>{w_status}} │"
        )

    lines.append(bottom)
    return "\n".join(lines)


def render_daily_trend(trend: list[DailyTrend]) -> str:
    """Render a simple daily trend with horizontal ASCII bar chart.

    Example::

        Daily Trend (7 days)
        2026-04-01 │ $1.24 │ 3 sessions │ ████████
        2026-04-02 │ $2.10 │ 5 sessions │ █████████████
    """
    if not trend:
        return ""

    max_cost = max(d.cost_usd for d in trend) if trend else 1.0
    if max_cost == 0:
        max_cost = 1.0

    bar_max = 20  # max bar width in chars

    lines = [f"  Daily Trend ({len(trend)} days)"]
    for d in trend:
        bar_len = int((d.cost_usd / max_cost) * bar_max) if max_cost > 0 else 0
        bar = "█" * bar_len
        lines.append(f"  {d.date} │ {fmt_cost(d.cost_usd):>7} │ {d.sessions:>3} sessions │ {bar}")

    return "\n".join(lines)


def render_empty_dashboard() -> str:
    """Render a message when the database has no data."""
    return (
        "  Ensemble MCP - Dashboard\n"
        "  ═══════════════════════════\n"
        "\n"
        "  No session data found.\n"
        "\n"
        "  Start a pipeline to begin tracking metrics.\n"
        "  Sessions are recorded via the metrics_start_session MCP tool."
    )
