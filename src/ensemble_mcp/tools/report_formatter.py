"""ASCII session report formatter.

Generates the box-drawing report format described in Section 6.3 of the
design spec.  The report includes:

- Session header (task, classification, status)
- Per-agent token/cost breakdown table
- MCP tool call summary table
- Savings analysis
- Cumulative project stats
- Accuracy indicator (● exact / ◐ partial / ○ estimated)
"""

from __future__ import annotations

from typing import Any

from ..config.defaults import (
    CONFIDENCE_ESTIMATED,
    CONFIDENCE_EXACT,
    CONFIDENCE_PARTIAL,
)

# ── Accuracy indicators ──────────────────────────────────────────

ACCURACY_SYMBOLS: dict[str, str] = {
    CONFIDENCE_EXACT: "●",
    CONFIDENCE_PARTIAL: "◐",
    CONFIDENCE_ESTIMATED: "○",
}


def _accuracy_symbol(confidence: str) -> str:
    return ACCURACY_SYMBOLS.get(confidence, "?")


def _fmt_tokens(n: int) -> str:
    """Format a token count with thousands separator."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    return f"{n:,}"


def _fmt_cost(c: float) -> str:
    """Format a USD cost."""
    return f"${c:.3f}"


# ── Table builders ───────────────────────────────────────────────


def _build_agent_table(steps: list[dict[str, Any]]) -> list[str]:
    """Build the per-agent breakdown table.

    Returns a list of lines (without leading/trailing box borders).
    """
    if not steps:
        return ["  (no steps recorded)"]

    # Column widths
    w_agent = max(len(s.get("agent", "")) for s in steps)
    w_agent = max(w_agent, len("Agent"), len("TOTAL"))

    # Header
    header = (
        f"  │ {'Agent':<{w_agent}} │ {'In Tkns':>9} │ {'Out Tkns':>9} │ "
        f"{'Cached':>8} │ {'Cost':>8} │"
    )
    sep = f"  ├─{'─' * w_agent}─┼─{'─' * 9}─┼─{'─' * 9}─┼─{'─' * 8}─┼─{'─' * 8}─┤"
    top = f"  ┌─{'─' * w_agent}─┬─{'─' * 9}─┬─{'─' * 9}─┬─{'─' * 8}─┬─{'─' * 8}─┐"
    bottom = f"  └─{'─' * w_agent}─┴─{'─' * 9}─┴─{'─' * 9}─┴─{'─' * 8}─┴─{'─' * 8}─┘"

    lines = [top, header, sep]

    total_in = 0
    total_out = 0
    total_cached = 0
    total_cost = 0.0

    for s in steps:
        agent = s.get("agent", "?")
        in_t = s.get("input_tokens", 0) or 0
        out_t = s.get("output_tokens", 0) or 0
        cached = s.get("cached_tokens", 0) or 0
        cost = s.get("cost_usd", 0.0) or 0.0

        total_in += in_t
        total_out += out_t
        total_cached += cached
        total_cost += cost

        lines.append(
            f"  │ {agent:<{w_agent}} │ {_fmt_tokens(in_t):>9} │ "
            f"{_fmt_tokens(out_t):>9} │ {_fmt_tokens(cached):>8} │ "
            f"{_fmt_cost(cost):>8} │"
        )

    lines.append(sep)
    lines.append(
        f"  │ {'TOTAL':<{w_agent}} │ {_fmt_tokens(total_in):>9} │ "
        f"{_fmt_tokens(total_out):>9} │ {_fmt_tokens(total_cached):>8} │ "
        f"{_fmt_cost(total_cost):>8} │"
    )
    lines.append(bottom)

    return lines


def _build_mcp_calls_table(mcp_calls: list[dict[str, Any]]) -> list[str]:
    """Build the MCP tool calls summary table."""
    if not mcp_calls:
        return []

    # Aggregate by tool name
    by_tool: dict[str, dict[str, int]] = {}
    for call in mcp_calls:
        name = call.get("tool_name", "?")
        if name not in by_tool:
            by_tool[name] = {"calls": 0, "total_bytes": 0}
        by_tool[name]["calls"] += 1
        by_tool[name]["total_bytes"] += (call.get("input_bytes", 0) or 0) + (
            call.get("output_bytes", 0) or 0
        )

    w_tool = max(len(t) for t in by_tool)
    w_tool = max(w_tool, len("Tool"), len("TOTAL"))

    top = f"  ┌─{'─' * w_tool}─┬─{'─' * 7}─┬─{'─' * 9}─┐"
    header = f"  │ {'Tool':<{w_tool}} │ {'Calls':>7} │ {'Bytes':>9} │"
    sep = f"  ├─{'─' * w_tool}─┼─{'─' * 7}─┼─{'─' * 9}─┤"
    bottom = f"  └─{'─' * w_tool}─┴─{'─' * 7}─┴─{'─' * 9}─┘"

    lines = ["", "  MCP TOOL CALLS", top, header, sep]

    total_calls = 0
    total_bytes = 0
    for name, agg in sorted(by_tool.items()):
        total_calls += agg["calls"]
        total_bytes += agg["total_bytes"]
        lines.append(
            f"  │ {name:<{w_tool}} │ {agg['calls']:>7} │ {_fmt_tokens(agg['total_bytes']):>9} │"
        )

    lines.append(sep)
    lines.append(f"  │ {'TOTAL':<{w_tool}} │ {total_calls:>7} │ {_fmt_tokens(total_bytes):>9} │")
    lines.append(bottom)

    return lines


# ── Main formatter ───────────────────────────────────────────────


def format_session_report(
    *,
    session_id: str,  # noqa: ARG001
    task: str,
    classification: str,
    status: str | None,
    state: str | None,
    ai_tool: str | None,  # noqa: ARG001
    total_input_tokens: int,  # noqa: ARG001
    total_output_tokens: int,  # noqa: ARG001
    total_cached_tokens: int,
    total_cost_usd: float,  # noqa: ARG001
    started_at: str | None,  # noqa: ARG001
    ended_at: str | None,  # noqa: ARG001
    steps: list[dict[str, Any]],
    mcp_calls: list[dict[str, Any]] | None = None,
    overall_confidence: str = CONFIDENCE_EXACT,
    cumulative_sessions: int | None = None,
    cumulative_cost: float | None = None,
) -> str:
    """Render a full ASCII session report.

    Returns a multi-line string matching the format in Section 6.3 of
    the design spec.
    """
    display_status = (status or state or "unknown").upper()
    display_class = (classification or "unknown").upper()
    acc_sym = _accuracy_symbol(overall_confidence)
    acc_label = overall_confidence

    # ── Header box ────────────────────────────────────────────────
    width = 62
    hline = "═" * width

    lines: list[str] = [
        f"╔{hline}╗",
        f"║{'SESSION REPORT':^{width}}║",
        f"║  Task: {task:<{width - 9}}║",
        f"║  Classification: {display_class}  │  Status: "
        f"{display_status:<{width - 32 - len(display_class)}}║",
        f"╠{hline}╣",
    ]

    # ── Agent breakdown ───────────────────────────────────────────
    lines.append(f"║{'':^{width}}║")
    agent_header = f"  AGENT BREAKDOWN{' ' * 20}{acc_sym} {acc_label}"
    lines.append(f"║{agent_header:<{width}}║")

    agent_table = _build_agent_table(steps)
    for tl in agent_table:
        # Pad to box width
        lines.append(f"║{tl:<{width}}║")

    # ── MCP calls ─────────────────────────────────────────────────
    if mcp_calls:
        mcp_table = _build_mcp_calls_table(mcp_calls)
        for tl in mcp_table:
            lines.append(f"║{tl:<{width}}║")

    # ── Savings analysis ──────────────────────────────────────────
    if total_cached_tokens > 0:
        lines.append(f"║{'':^{width}}║")
        lines.append(f"║  {'SAVINGS ANALYSIS':<{width - 2}}║")
        cached_saving = total_cached_tokens * 15.0 / 1_000_000  # rough Opus rate
        lines.append(
            f"║  • Cached tokens saved: {_fmt_cost(cached_saving)} "
            f"({_fmt_tokens(total_cached_tokens)} tokens at cache rate)"
            f"{' ' * max(0, width - 60)}║"
        )

    # ── Cumulative ────────────────────────────────────────────────
    if cumulative_sessions is not None and cumulative_cost is not None:
        avg_cost = cumulative_cost / max(cumulative_sessions, 1)
        lines.append(f"║{'':^{width}}║")
        cum_line = (
            f"  CUMULATIVE: {cumulative_sessions} sessions  │  "
            f"Total: {_fmt_cost(cumulative_cost)}  │  Avg: {_fmt_cost(avg_cost)}/run"
        )
        lines.append(f"║{cum_line:<{width}}║")

    # ── Footer ────────────────────────────────────────────────────
    lines.append(f"║{'':^{width}}║")
    acc_line = f"  Accuracy: {acc_sym} {acc_label}"
    lines.append(f"║{acc_line:<{width}}║")
    lines.append(f"╚{hline}╝")

    return "\n".join(lines)
