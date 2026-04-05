"""Tests for the ASCII session report formatter."""

from __future__ import annotations

from ensemble_mcp.tools.report_formatter import (
    _accuracy_symbol,
    _build_agent_table,
    _build_mcp_calls_table,
    _fmt_cost,
    _fmt_tokens,
    format_session_report,
)


class TestFormatHelpers:
    def test_fmt_tokens_small(self) -> None:
        assert _fmt_tokens(500) == "500"

    def test_fmt_tokens_thousands(self) -> None:
        assert _fmt_tokens(1_234) == "1,234"

    def test_fmt_tokens_millions(self) -> None:
        assert _fmt_tokens(1_500_000) == "1.5M"

    def test_fmt_cost(self) -> None:
        assert _fmt_cost(1.234) == "$1.234"
        assert _fmt_cost(0.001) == "$0.001"

    def test_accuracy_symbol_exact(self) -> None:
        assert _accuracy_symbol("exact") == "●"

    def test_accuracy_symbol_partial(self) -> None:
        assert _accuracy_symbol("partial") == "◐"

    def test_accuracy_symbol_estimated(self) -> None:
        assert _accuracy_symbol("estimated") == "○"

    def test_accuracy_symbol_unknown(self) -> None:
        assert _accuracy_symbol("unknown") == "?"


class TestBuildAgentTable:
    def test_empty_steps(self) -> None:
        lines = _build_agent_table([])
        assert len(lines) == 1
        assert "no steps" in lines[0]

    def test_single_step(self) -> None:
        steps = [
            {
                "agent": "craft",
                "input_tokens": 1000,
                "output_tokens": 500,
                "cached_tokens": 200,
                "cost_usd": 0.045,
            }
        ]
        lines = _build_agent_table(steps)
        text = "\n".join(lines)
        assert "craft" in text
        assert "TOTAL" in text
        assert "1,000" in text

    def test_multiple_steps_totals(self) -> None:
        steps = [
            {
                "agent": "scope",
                "input_tokens": 2000,
                "output_tokens": 500,
                "cached_tokens": 100,
                "cost_usd": 0.10,
            },
            {
                "agent": "craft",
                "input_tokens": 3000,
                "output_tokens": 1000,
                "cached_tokens": 200,
                "cost_usd": 0.20,
            },
        ]
        lines = _build_agent_table(steps)
        text = "\n".join(lines)
        # Check totals row
        assert "TOTAL" in text
        assert "5,000" in text  # 2000 + 3000


class TestBuildMcpCallsTable:
    def test_empty_calls(self) -> None:
        lines = _build_mcp_calls_table([])
        assert lines == []

    def test_single_call(self) -> None:
        calls = [
            {
                "tool_name": "patterns_search",
                "input_bytes": 100,
                "output_bytes": 200,
                "duration_ms": 5,
            }
        ]
        lines = _build_mcp_calls_table(calls)
        text = "\n".join(lines)
        assert "patterns_search" in text
        assert "MCP TOOL CALLS" in text

    def test_aggregation(self) -> None:
        calls = [
            {"tool_name": "patterns_search", "input_bytes": 100, "output_bytes": 200},
            {"tool_name": "patterns_search", "input_bytes": 50, "output_bytes": 100},
            {"tool_name": "drift_check", "input_bytes": 80, "output_bytes": 150},
        ]
        lines = _build_mcp_calls_table(calls)
        text = "\n".join(lines)
        assert "patterns_search" in text
        assert "drift_check" in text
        assert "TOTAL" in text


class TestFormatSessionReport:
    def test_minimal_report(self) -> None:
        report = format_session_report(
            session_id="sess_abc123",
            task="Fix auth bug",
            classification="simple",
            status="completed",
            state="completed",
            ai_tool="opencode",
            total_input_tokens=5000,
            total_output_tokens=2000,
            total_cached_tokens=0,
            total_cost_usd=0.125,
            started_at="2026-04-01T10:00:00",
            ended_at="2026-04-01T10:05:00",
            steps=[],
            overall_confidence="exact",
        )
        assert "SESSION REPORT" in report
        assert "Fix auth bug" in report
        assert "SIMPLE" in report
        assert "COMPLETED" in report
        assert "● exact" in report

    def test_report_with_steps(self) -> None:
        steps = [
            {
                "agent": "scope",
                "input_tokens": 8000,
                "output_tokens": 2000,
                "cached_tokens": 1000,
                "cost_usd": 0.15,
            },
            {
                "agent": "craft",
                "input_tokens": 10000,
                "output_tokens": 3000,
                "cached_tokens": 500,
                "cost_usd": 0.30,
            },
        ]
        report = format_session_report(
            session_id="sess_def456",
            task="Add user profile page",
            classification="standard",
            status="completed",
            state="completed",
            ai_tool=None,
            total_input_tokens=18000,
            total_output_tokens=5000,
            total_cached_tokens=1500,
            total_cost_usd=0.45,
            started_at=None,
            ended_at=None,
            steps=steps,
            overall_confidence="partial",
        )
        assert "scope" in report
        assert "craft" in report
        assert "TOTAL" in report
        assert "◐ partial" in report
        assert "SAVINGS" in report  # cached_tokens > 0 triggers savings

    def test_report_with_mcp_calls(self) -> None:
        mcp_calls = [
            {"tool_name": "patterns_search", "input_bytes": 100, "output_bytes": 200},
        ]
        report = format_session_report(
            session_id="sess_ghi789",
            task="Test",
            classification="trivial",
            status="completed",
            state="completed",
            ai_tool=None,
            total_input_tokens=1000,
            total_output_tokens=500,
            total_cached_tokens=0,
            total_cost_usd=0.01,
            started_at=None,
            ended_at=None,
            steps=[],
            mcp_calls=mcp_calls,
            overall_confidence="exact",
        )
        assert "MCP TOOL CALLS" in report
        assert "patterns_search" in report

    def test_report_with_cumulative(self) -> None:
        report = format_session_report(
            session_id="sess_jkl012",
            task="Test cumulative",
            classification="standard",
            status="completed",
            state="completed",
            ai_tool=None,
            total_input_tokens=5000,
            total_output_tokens=2000,
            total_cached_tokens=0,
            total_cost_usd=0.10,
            started_at=None,
            ended_at=None,
            steps=[],
            overall_confidence="exact",
            cumulative_sessions=50,
            cumulative_cost=55.0,
        )
        assert "CUMULATIVE" in report
        assert "50 sessions" in report

    def test_report_box_drawing_chars(self) -> None:
        """Report should use proper box-drawing characters."""
        report = format_session_report(
            session_id="sess_test",
            task="Test",
            classification="trivial",
            status="completed",
            state="completed",
            ai_tool=None,
            total_input_tokens=0,
            total_output_tokens=0,
            total_cached_tokens=0,
            total_cost_usd=0.0,
            started_at=None,
            ended_at=None,
            steps=[],
            overall_confidence="exact",
        )
        assert "╔" in report
        assert "╗" in report
        assert "╚" in report
        assert "╝" in report
        assert "║" in report
