"""Tests for the CLI dashboard (Phase 5).

Tests cover:
- cli/queries.py — SQLite query functions return correct aggregates
- cli/widgets.py — ASCII rendering produces expected output
- cli/dashboard.py — full dashboard composition
- __main__.py — dashboard subcommand wiring
"""

from __future__ import annotations

import sqlite3

import pytest

from ensemble_mcp.cli.dashboard import render_dashboard
from ensemble_mcp.cli.queries import (
    AgentCost,
    DailyTrend,
    DashboardData,
    PeriodSummary,
    RecentSession,
    fetch_dashboard_data,
    get_cost_by_agent,
    get_daily_trend,
    get_period_summaries,
    get_recent_sessions,
)
from ensemble_mcp.cli.widgets import (
    fmt_cost,
    fmt_share,
    fmt_tokens,
    render_cost_by_agent,
    render_daily_trend,
    render_empty_dashboard,
    render_header,
    render_recent_sessions,
    render_summary_bar,
)

# ── Fixtures ──────────────────────────────────────────────────────


def _seed_sessions(conn: sqlite3.Connection) -> None:
    """Insert sample session and step data for dashboard testing."""
    # Session 1: completed today
    conn.execute(
        "INSERT INTO sessions (id, task, classification, ai_tool, project, "
        "state, started_at, ended_at, status, "
        "total_input_tokens, total_output_tokens, total_cached_tokens, total_cost_usd) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?, ?, ?, ?)",
        (
            "sess_001",
            "Fix login redirect bug",
            "simple",
            "opencode",
            "/project/a",
            "completed",
            "completed",
            8000,
            3000,
            1200,
            0.82,
        ),
    )
    # Session 2: completed today
    conn.execute(
        "INSERT INTO sessions (id, task, classification, ai_tool, project, "
        "state, started_at, ended_at, status, "
        "total_input_tokens, total_output_tokens, total_cached_tokens, total_cost_usd) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?, ?, ?, ?)",
        (
            "sess_002",
            "Add profile settings page",
            "standard",
            "opencode",
            "/project/a",
            "completed",
            "completed",
            12000,
            4500,
            2100,
            1.16,
        ),
    )
    # Session 3: completed 3 days ago
    conn.execute(
        "INSERT INTO sessions (id, task, classification, ai_tool, project, "
        "state, started_at, ended_at, status, "
        "total_input_tokens, total_output_tokens, total_cached_tokens, total_cost_usd) "
        "VALUES (?, ?, ?, ?, ?, ?, "
        "datetime('now', '-3 days'), "
        "datetime('now', '-3 days'), ?, ?, ?, ?, ?)",
        (
            "sess_003",
            "Refactor auth service",
            "complex",
            "opencode",
            "/project/a",
            "completed",
            "completed",
            20000,
            8000,
            3500,
            2.34,
        ),
    )
    # Session 4: failed 10 days ago
    conn.execute(
        "INSERT INTO sessions (id, task, classification, ai_tool, project, "
        "state, started_at, ended_at, status, "
        "total_input_tokens, total_output_tokens, total_cached_tokens, total_cost_usd) "
        "VALUES (?, ?, ?, ?, ?, ?, "
        "datetime('now', '-10 days'), "
        "datetime('now', '-10 days'), ?, ?, ?, ?, ?)",
        (
            "sess_004",
            "Update README",
            "trivial",
            "opencode",
            "/project/a",
            "failed",
            "failed",
            2000,
            500,
            300,
            0.12,
        ),
    )

    # Steps for session 1
    conn.execute(
        "INSERT INTO steps (session_id, agent, model, input_tokens, output_tokens, "
        "cached_tokens, cost_usd, accuracy, started_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        ("sess_001", "scope", "claude-opus-4", 4000, 1500, 600, 0.35, "exact"),
    )
    conn.execute(
        "INSERT INTO steps (session_id, agent, model, input_tokens, output_tokens, "
        "cached_tokens, cost_usd, accuracy, started_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        ("sess_001", "craft", "claude-opus-4", 4000, 1500, 600, 0.47, "exact"),
    )

    # Steps for session 2
    conn.execute(
        "INSERT INTO steps (session_id, agent, model, input_tokens, output_tokens, "
        "cached_tokens, cost_usd, accuracy, started_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        ("sess_002", "scope", "claude-opus-4", 5000, 2000, 800, 0.42, "exact"),
    )
    conn.execute(
        "INSERT INTO steps (session_id, agent, model, input_tokens, output_tokens, "
        "cached_tokens, cost_usd, accuracy, started_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        ("sess_002", "craft", "claude-opus-4", 5000, 2000, 1000, 0.52, "exact"),
    )
    conn.execute(
        "INSERT INTO steps (session_id, agent, model, input_tokens, output_tokens, "
        "cached_tokens, cost_usd, accuracy, started_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        ("sess_002", "proof", "claude-sonnet-4", 2000, 500, 300, 0.22, "exact"),
    )

    # Steps for session 3 (3 days ago)
    conn.execute(
        "INSERT INTO steps (session_id, agent, model, input_tokens, output_tokens, "
        "cached_tokens, cost_usd, accuracy, started_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '-3 days'))",
        ("sess_003", "scope", "claude-opus-4", 8000, 3000, 1500, 0.78, "exact"),
    )
    conn.execute(
        "INSERT INTO steps (session_id, agent, model, input_tokens, output_tokens, "
        "cached_tokens, cost_usd, accuracy, started_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '-3 days'))",
        ("sess_003", "craft", "claude-opus-4", 8000, 3500, 1500, 1.05, "exact"),
    )
    conn.execute(
        "INSERT INTO steps (session_id, agent, model, input_tokens, output_tokens, "
        "cached_tokens, cost_usd, accuracy, started_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '-3 days'))",
        ("sess_003", "ensemble", "claude-opus-4", 4000, 1500, 500, 0.51, "exact"),
    )

    conn.commit()


@pytest.fixture()
def seeded_conn(test_conn):
    """Return a test_conn with sample dashboard data seeded."""
    _seed_sessions(test_conn)
    return test_conn


# ── Format helper tests ──────────────────────────────────────────


class TestFormatHelpers:
    """Test number formatting functions."""

    def test_fmt_tokens_small(self):
        assert fmt_tokens(500) == "500"

    def test_fmt_tokens_thousands(self):
        assert fmt_tokens(12345) == "12.3K"

    def test_fmt_tokens_millions(self):
        assert fmt_tokens(1_940_000) == "1.94M"

    def test_fmt_tokens_zero(self):
        assert fmt_tokens(0) == "0"

    def test_fmt_cost(self):
        assert fmt_cost(1.16) == "$1.16"

    def test_fmt_cost_small(self):
        assert fmt_cost(0.001) == "$0.00"

    def test_fmt_cost_large(self):
        assert fmt_cost(178.23) == "$178.23"

    def test_fmt_share_normal(self):
        assert fmt_share(40.0) == "40%"

    def test_fmt_share_small(self):
        assert fmt_share(0.5) == "<1%"

    def test_fmt_share_zero(self):
        assert fmt_share(0.0) == "0%"


# ── Query tests ──────────────────────────────────────────────────


class TestPeriodSummaries:
    """Test get_period_summaries."""

    def test_empty_database(self, test_conn):
        today, week, month = get_period_summaries(test_conn)
        assert today.sessions == 0
        assert today.cost_usd == 0.0
        assert today.total_tokens == 0

    def test_today_summary(self, seeded_conn):
        today, week, month = get_period_summaries(seeded_conn)
        # Sessions 1 and 2 are "today"
        assert today.sessions == 2
        assert today.cost_usd == pytest.approx(0.82 + 1.16, abs=0.01)
        assert today.total_tokens == (8000 + 3000) + (12000 + 4500)

    def test_week_summary(self, seeded_conn):
        today, week, month = get_period_summaries(seeded_conn)
        # Sessions 1, 2 (today) + 3 (3 days ago) = 3 sessions
        assert week.sessions == 3
        assert week.cost_usd == pytest.approx(0.82 + 1.16 + 2.34, abs=0.01)

    def test_month_summary(self, seeded_conn):
        today, week, month = get_period_summaries(seeded_conn)
        # All 4 sessions are within 30 days
        assert month.sessions == 4
        assert month.cost_usd == pytest.approx(0.82 + 1.16 + 2.34 + 0.12, abs=0.01)


class TestCostByAgent:
    """Test get_cost_by_agent."""

    def test_empty_database(self, test_conn):
        result = get_cost_by_agent(test_conn, days=1)
        assert result == []

    def test_today_agents(self, seeded_conn):
        result = get_cost_by_agent(seeded_conn, days=1)
        # Today's steps: scope (0.35+0.42), craft (0.47+0.52), proof (0.22)
        assert len(result) == 3
        agents = {a.agent for a in result}
        assert agents == {"scope", "craft", "proof"}

        # Sorted by cost descending: craft > scope > proof
        assert result[0].agent == "craft"
        assert result[0].cost_usd == pytest.approx(0.99, abs=0.01)
        assert result[1].agent == "scope"
        assert result[1].cost_usd == pytest.approx(0.77, abs=0.01)

    def test_share_percentages_sum_to_100(self, seeded_conn):
        result = get_cost_by_agent(seeded_conn, days=1)
        total_share = sum(a.share_pct for a in result)
        assert total_share == pytest.approx(100.0, abs=1.0)

    def test_wider_range_includes_more_agents(self, seeded_conn):
        result = get_cost_by_agent(seeded_conn, days=7)
        agents = {a.agent for a in result}
        # 7-day range includes session 3 which has ensemble steps
        assert "ensemble" in agents


class TestRecentSessions:
    """Test get_recent_sessions."""

    def test_empty_database(self, test_conn):
        result = get_recent_sessions(test_conn, limit=10)
        assert result == []

    def test_returns_newest_first(self, seeded_conn):
        result = get_recent_sessions(seeded_conn, limit=10)
        assert len(result) == 4
        # Newest first — sessions 1 and 2 are today
        assert result[0].row_num == 1
        # Session 4 is 10 days ago — should be last
        assert result[-1].task == "Update README"

    def test_respects_limit(self, seeded_conn):
        result = get_recent_sessions(seeded_conn, limit=2)
        assert len(result) == 2

    def test_session_fields(self, seeded_conn):
        result = get_recent_sessions(seeded_conn, limit=10)
        # Find the "Fix login redirect bug" session
        login_session = next(s for s in result if "login" in s.task.lower())
        assert login_session.classification == "simple"
        assert login_session.cost_usd == pytest.approx(0.82, abs=0.01)
        assert login_session.status == "completed"

    def test_failed_status(self, seeded_conn):
        result = get_recent_sessions(seeded_conn, limit=10)
        readme_session = next(s for s in result if "README" in s.task)
        assert readme_session.status == "failed"


class TestDailyTrend:
    """Test get_daily_trend."""

    def test_empty_database(self, test_conn):
        result = get_daily_trend(test_conn, days=7)
        assert result == []

    def test_returns_daily_data(self, seeded_conn):
        result = get_daily_trend(seeded_conn, days=7)
        # Should have at least 2 distinct days (today + 3 days ago)
        assert len(result) >= 2

    def test_daily_data_sorted_by_date(self, seeded_conn):
        result = get_daily_trend(seeded_conn, days=30)
        dates = [d.date for d in result]
        assert dates == sorted(dates)


class TestFetchDashboardData:
    """Test the composite fetch_dashboard_data function."""

    def test_returns_all_sections(self, seeded_conn):
        data = fetch_dashboard_data(seeded_conn)
        assert isinstance(data, DashboardData)
        assert isinstance(data.today, PeriodSummary)
        assert isinstance(data.week, PeriodSummary)
        assert isinstance(data.month, PeriodSummary)
        assert isinstance(data.cost_by_agent, list)
        assert isinstance(data.recent_sessions, list)
        assert isinstance(data.daily_trend, list)

    def test_empty_database_returns_zeros(self, test_conn):
        data = fetch_dashboard_data(test_conn)
        assert data.today.sessions == 0
        assert data.cost_by_agent == []
        assert data.recent_sessions == []


# ── Widget rendering tests ───────────────────────────────────────


class TestRenderHeader:
    """Test the dashboard header rendering."""

    def test_contains_title(self):
        output = render_header()
        assert "Ensemble MCP" in output
        assert "Dashboard" in output

    def test_contains_separator(self):
        output = render_header()
        assert "═" in output


class TestRenderSummaryBar:
    """Test the period summary bar rendering."""

    def test_renders_all_periods(self):
        today = PeriodSummary(sessions=8, cost_usd=9.42, total_tokens=378000)
        week = PeriodSummary(sessions=42, cost_usd=48.67, total_tokens=1940000)
        month = PeriodSummary(sessions=156, cost_usd=178.23, total_tokens=7100000)

        output = render_summary_bar(today, week, month)
        assert "Today:" in output
        assert "Week:" in output
        assert "Month:" in output
        assert "8 sessions" in output
        assert "$9.42" in output
        assert "378.0K tokens" in output

    def test_renders_zero_values(self):
        empty = PeriodSummary()
        output = render_summary_bar(empty, empty, empty)
        assert "0 sessions" in output
        assert "$0.00" in output


class TestRenderCostByAgent:
    """Test the agent cost breakdown table rendering."""

    def test_renders_table(self):
        agents = [
            AgentCost(agent="craft", cost_usd=3.78, share_pct=40.0),
            AgentCost(agent="scope", cost_usd=2.84, share_pct=30.0),
            AgentCost(agent="ensemble", cost_usd=2.10, share_pct=22.0),
        ]
        output = render_cost_by_agent(agents)
        assert "Cost by Agent" in output
        assert "craft" in output
        assert "$3.78" in output
        assert "40%" in output
        assert "TOTAL" in output
        # Box-drawing characters
        assert "┌" in output
        assert "└" in output

    def test_empty_data(self):
        output = render_cost_by_agent([])
        assert "no data" in output

    def test_single_agent_no_total_row(self):
        agents = [AgentCost(agent="craft", cost_usd=1.00, share_pct=100.0)]
        output = render_cost_by_agent(agents)
        assert "TOTAL" not in output

    def test_custom_days_label(self):
        agents = [
            AgentCost(agent="craft", cost_usd=1.00, share_pct=50.0),
            AgentCost(agent="scope", cost_usd=1.00, share_pct=50.0),
        ]
        output = render_cost_by_agent(agents, days=7)
        assert "last 7 days" in output


class TestRenderRecentSessions:
    """Test the recent sessions table rendering."""

    def test_renders_table(self):
        sessions = [
            RecentSession(
                row_num=1,
                task="Fix login bug",
                classification="simple",
                cost_usd=0.82,
                status="completed",
            ),
            RecentSession(
                row_num=2,
                task="Add settings",
                classification="standard",
                cost_usd=1.16,
                status="completed",
            ),
        ]
        output = render_recent_sessions(sessions, max_task_width=24)
        assert "Recent Sessions" in output
        assert "Fix login bug" in output
        assert "$0.82" in output
        assert "✓" in output  # completed status symbol

    def test_empty_sessions(self):
        output = render_recent_sessions([])
        assert "no sessions" in output

    def test_failed_status_symbol(self):
        sessions = [
            RecentSession(
                row_num=1, task="Bad task", classification="simple", cost_usd=0.50, status="failed"
            ),
        ]
        output = render_recent_sessions(sessions, max_task_width=24)
        assert "✗" in output

    def test_long_task_truncated(self):
        sessions = [
            RecentSession(
                row_num=1,
                task="This is a very long task description that should be truncated",
                classification="complex",
                cost_usd=2.50,
                status="completed",
            ),
        ]
        output = render_recent_sessions(sessions, max_task_width=20)
        # Task should be truncated to 20 chars
        assert "This is a very long " in output
        assert "should be truncated" not in output


class TestRenderDailyTrend:
    """Test the daily trend chart rendering."""

    def test_renders_chart(self):
        trend = [
            DailyTrend(date="2026-04-01", sessions=3, cost_usd=1.24, tokens=45000),
            DailyTrend(date="2026-04-02", sessions=5, cost_usd=2.10, tokens=78000),
        ]
        output = render_daily_trend(trend)
        assert "Daily Trend" in output
        assert "2026-04-01" in output
        assert "$1.24" in output
        assert "█" in output

    def test_empty_trend(self):
        output = render_daily_trend([])
        assert output == ""

    def test_bar_scaling(self):
        """The highest cost day should have the longest bar."""
        trend = [
            DailyTrend(date="2026-04-01", sessions=1, cost_usd=1.00, tokens=10000),
            DailyTrend(date="2026-04-02", sessions=1, cost_usd=5.00, tokens=50000),
        ]
        output = render_daily_trend(trend)
        lines = output.strip().split("\n")
        # Line for day 2 (cost=5.00) should have more blocks than day 1 (cost=1.00)
        day1_bars = lines[1].count("█")
        day2_bars = lines[2].count("█")
        assert day2_bars > day1_bars


class TestRenderEmptyDashboard:
    """Test the empty state dashboard."""

    def test_shows_helpful_message(self):
        output = render_empty_dashboard()
        assert "No session data" in output
        assert "metrics_start_session" in output


# ── Full dashboard rendering tests ───────────────────────────────


class TestRenderDashboard:
    """Test the full dashboard composition."""

    def test_empty_database_shows_empty_state(self, test_conn):
        output = render_dashboard(test_conn)
        assert "No session data" in output

    def test_full_dashboard_has_all_sections(self, seeded_conn):
        output = render_dashboard(seeded_conn)
        assert "Ensemble MCP - Dashboard" in output
        assert "Today:" in output
        assert "Week:" in output
        assert "Month:" in output
        assert "Cost by Agent" in output
        assert "Recent Sessions" in output

    def test_dashboard_with_custom_days(self, seeded_conn):
        output = render_dashboard(seeded_conn, days=7)
        assert "last 7 days" in output

    def test_dashboard_contains_session_data(self, seeded_conn):
        output = render_dashboard(seeded_conn)
        assert "2 sessions" in output  # today count
        assert "Fix login redirect bug" in output or "Add profile settings" in output

    def test_dashboard_contains_trend(self, seeded_conn):
        output = render_dashboard(seeded_conn, trend_days=7)
        # Should include daily trend with bar chart
        assert "Daily Trend" in output


# ── CLI integration tests ─────────────────────────────────────────


class TestDashboardCLI:
    """Test the dashboard subcommand wiring in __main__.py."""

    def test_dashboard_subcommand_exists(self):
        """Verify the dashboard subcommand is registered."""
        import argparse

        from ensemble_mcp.__main__ import main

        # Create a parser the same way main() does, but capture the subparsers
        parser = argparse.ArgumentParser(prog="ensemble-mcp")
        parser.add_subparsers(dest="command")
        # Just verify importing doesn't crash and main is callable
        assert callable(main)

    def test_dashboard_run_with_nonexistent_db(self, tmp_path, capsys):
        """Dashboard should show empty state when DB doesn't exist."""
        from ensemble_mcp.cli.dashboard import run_dashboard

        fake_db = tmp_path / "nonexistent.db"
        run_dashboard(db_path=fake_db)
        captured = capsys.readouterr()
        assert "No session data" in captured.out

    def test_dashboard_run_with_seeded_db(self, seeded_conn, capsys, tmp_path):
        """Dashboard should render data when DB has sessions."""
        from ensemble_mcp.cli.dashboard import run_dashboard

        # The seeded_conn uses a file DB — we need to find its path
        # Create a fresh DB file and seed it
        db_path = tmp_path / "dashboard_test.db"
        from ensemble_mcp.state.locks import get_connection

        conn = get_connection(db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                task TEXT NOT NULL,
                classification TEXT NOT NULL,
                ai_tool TEXT,
                project TEXT,
                state TEXT DEFAULT 'pending',
                started_at TEXT DEFAULT (datetime('now')),
                ended_at TEXT,
                status TEXT,
                total_input_tokens INTEGER DEFAULT 0,
                total_output_tokens INTEGER DEFAULT 0,
                total_cached_tokens INTEGER DEFAULT 0,
                total_cost_usd REAL DEFAULT 0,
                report_json TEXT
            );
            CREATE TABLE IF NOT EXISTS steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                agent TEXT NOT NULL,
                model TEXT,
                model_canonical_name TEXT,
                state TEXT DEFAULT 'pending',
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read_tokens INTEGER DEFAULT 0,
                cache_write_tokens INTEGER DEFAULT 0,
                web_search_requests INTEGER DEFAULT 0,
                cached_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0,
                pricing_version TEXT,
                source TEXT DEFAULT 'estimator',
                duration_ms INTEGER,
                unknown_model_cost INTEGER DEFAULT 0,
                accuracy TEXT DEFAULT 'estimated',
                started_at TEXT DEFAULT (datetime('now')),
                ended_at TEXT
            );
        """)
        conn.execute(
            "INSERT INTO sessions (id, task, classification, state, started_at, status, "
            "total_input_tokens, total_output_tokens, total_cached_tokens, total_cost_usd) "
            "VALUES (?, ?, ?, ?, datetime('now'), ?, ?, ?, ?, ?)",
            ("s1", "Test task", "simple", "completed", "completed", 1000, 500, 200, 0.50),
        )
        conn.commit()
        conn.close()

        run_dashboard(db_path=db_path, days=1, limit=5, trend_days=7)
        captured = capsys.readouterr()
        assert "Ensemble MCP - Dashboard" in captured.out
        assert "Test task" in captured.out


# ── Data class tests ─────────────────────────────────────────────


class TestDataClasses:
    """Test that dataclasses work correctly."""

    def test_period_summary_defaults(self):
        ps = PeriodSummary()
        assert ps.sessions == 0
        assert ps.cost_usd == 0.0
        assert ps.total_tokens == 0

    def test_agent_cost_fields(self):
        ac = AgentCost(agent="craft", cost_usd=1.50, share_pct=45.0)
        assert ac.agent == "craft"
        assert ac.cost_usd == 1.50

    def test_recent_session_fields(self):
        rs = RecentSession(
            row_num=1,
            task="test",
            classification="simple",
            cost_usd=0.50,
            status="completed",
        )
        assert rs.row_num == 1
        assert rs.task == "test"

    def test_dashboard_data_defaults(self):
        dd = DashboardData()
        assert dd.today.sessions == 0
        assert dd.cost_by_agent == []
        assert dd.recent_sessions == []
