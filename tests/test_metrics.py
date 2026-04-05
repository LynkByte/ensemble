"""Tests for metrics tools (session tracking, step recording, reports)."""

from __future__ import annotations

import json
import sqlite3

import pytest

from ensemble_mcp.tools.metrics import (
    metrics_compare,
    metrics_end_session,
    metrics_record_step,
    metrics_session_report,
    metrics_start_session,
    metrics_trend,
)


class TestMetricsStartSession:
    @pytest.mark.asyncio
    async def test_starts_session(self, test_conn: sqlite3.Connection):
        env = await metrics_start_session(
            test_conn,
            task="fix bug in auth",
            classification="simple",
        )
        assert env["ok"] is True
        data = env["data"]
        assert data["session_id"].startswith("sess_")
        assert data["state"] == "running"

    @pytest.mark.asyncio
    async def test_session_persisted_in_db(self, test_conn: sqlite3.Connection):
        env = await metrics_start_session(
            test_conn,
            task="test task",
            classification="standard",
        )
        sid = env["data"]["session_id"]
        row = test_conn.execute(
            "SELECT id, state FROM sessions WHERE id = ?",
            (sid,),
        ).fetchone()
        assert row is not None
        assert row[1] == "running"

    @pytest.mark.asyncio
    async def test_with_optional_fields(self, test_conn: sqlite3.Connection):
        env = await metrics_start_session(
            test_conn,
            task="deploy",
            classification="complex",
            ai_tool="opencode",
            project="ensemble",
        )
        assert env["ok"] is True

    @pytest.mark.asyncio
    async def test_idempotency(self, test_conn: sqlite3.Connection):
        key = "metrics-start-1"
        env1 = await metrics_start_session(
            test_conn,
            task="a",
            classification="trivial",
            idempotency_key=key,
        )
        env2 = await metrics_start_session(
            test_conn,
            task="b",
            classification="complex",
            idempotency_key=key,
        )
        assert env1["data"]["session_id"] == env2["data"]["session_id"]


class TestMetricsRecordStep:
    @pytest.mark.asyncio
    async def _create_session(self, conn: sqlite3.Connection) -> str:
        env = await metrics_start_session(
            conn,
            task="test",
            classification="standard",
        )
        return env["data"]["session_id"]

    @pytest.mark.asyncio
    async def test_record_step(self, test_conn: sqlite3.Connection):
        sid = await self._create_session(test_conn)
        env = await metrics_record_step(
            test_conn,
            session_id=sid,
            agent="craft",
            input_tokens=1000,
            output_tokens=500,
            model="claude-sonnet-4",
        )
        assert env["ok"] is True
        data = env["data"]
        assert data["recorded"] is True
        assert isinstance(data["step_id"], int)
        assert isinstance(data["cost_usd"], float)

    @pytest.mark.asyncio
    async def test_record_step_missing_session(self, test_conn: sqlite3.Connection):
        env = await metrics_record_step(
            test_conn,
            session_id="nonexistent",
            agent="craft",
        )
        assert env["ok"] is False
        assert env["error"]["code"] == "NOT_FOUND_SESSION"

    @pytest.mark.asyncio
    async def test_record_step_updates_session_totals(
        self,
        test_conn: sqlite3.Connection,
    ):
        sid = await self._create_session(test_conn)
        await metrics_record_step(
            test_conn,
            session_id=sid,
            agent="craft",
            input_tokens=1000,
            output_tokens=500,
        )
        row = test_conn.execute(
            "SELECT total_input_tokens, total_output_tokens FROM sessions WHERE id = ?",
            (sid,),
        ).fetchone()
        assert row[0] == 1000
        assert row[1] == 500


class TestMetricsEndSession:
    @pytest.mark.asyncio
    async def test_end_session_completed(self, test_conn: sqlite3.Connection):
        env = await metrics_start_session(
            test_conn,
            task="task",
            classification="simple",
        )
        sid = env["data"]["session_id"]
        env2 = await metrics_end_session(
            test_conn,
            session_id=sid,
            status="completed",
        )
        assert env2["ok"] is True
        assert env2["data"]["state"] == "completed"
        assert env2["data"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_end_session_failed(self, test_conn: sqlite3.Connection):
        env = await metrics_start_session(
            test_conn,
            task="task",
            classification="simple",
        )
        sid = env["data"]["session_id"]
        env2 = await metrics_end_session(
            test_conn,
            session_id=sid,
            status="failed",
        )
        assert env2["ok"] is True
        assert env2["data"]["state"] == "failed"

    @pytest.mark.asyncio
    async def test_end_session_not_found(self, test_conn: sqlite3.Connection):
        env = await metrics_end_session(
            test_conn,
            session_id="nonexistent",
        )
        assert env["ok"] is False
        assert env["error"]["code"] == "NOT_FOUND_SESSION"


class TestMetricsSessionReport:
    @pytest.mark.asyncio
    async def test_report_with_steps(self, test_conn: sqlite3.Connection):
        env = await metrics_start_session(
            test_conn,
            task="test",
            classification="standard",
        )
        sid = env["data"]["session_id"]
        await metrics_record_step(
            test_conn,
            session_id=sid,
            agent="craft",
            input_tokens=1000,
            output_tokens=500,
        )
        await metrics_record_step(
            test_conn,
            session_id=sid,
            agent="lens",
            input_tokens=500,
            output_tokens=200,
        )

        env2 = await metrics_session_report(test_conn, session_id=sid)
        assert env2["ok"] is True
        report = env2["data"]["report"]
        assert report["session_id"] == sid
        assert len(report["steps"]) == 2

    @pytest.mark.asyncio
    async def test_report_not_found(self, test_conn: sqlite3.Connection):
        env = await metrics_session_report(test_conn, session_id="nonexistent")
        assert env["ok"] is False
        assert env["error"]["code"] == "NOT_FOUND_SESSION"


class TestMetricsTrend:
    @pytest.mark.asyncio
    async def test_trend_empty_db(self, test_conn: sqlite3.Connection):
        env = await metrics_trend(test_conn, days=30)
        assert env["ok"] is True
        assert env["data"]["daily_costs"] == []
        assert env["data"]["total_cost"] == 0
        assert env["data"]["total_sessions"] == 0

    @pytest.mark.asyncio
    async def test_trend_with_sessions(self, test_conn: sqlite3.Connection):
        await metrics_start_session(
            test_conn,
            task="a",
            classification="simple",
        )
        await metrics_start_session(
            test_conn,
            task="b",
            classification="standard",
        )
        env = await metrics_trend(test_conn, days=30)
        assert env["ok"] is True
        assert env["data"]["total_sessions"] >= 2


class TestMetricsCompare:
    @pytest.mark.asyncio
    async def test_compare_two_sessions(self, test_conn: sqlite3.Connection):
        env_a = await metrics_start_session(
            test_conn,
            task="task a",
            classification="simple",
        )
        env_b = await metrics_start_session(
            test_conn,
            task="task b",
            classification="complex",
        )
        sid_a = env_a["data"]["session_id"]
        sid_b = env_b["data"]["session_id"]

        env = await metrics_compare(
            test_conn,
            session_id_a=sid_a,
            session_id_b=sid_b,
        )
        assert env["ok"] is True
        assert "session_a" in env["data"]
        assert "session_b" in env["data"]
        assert "diff" in env["data"]

    @pytest.mark.asyncio
    async def test_compare_missing_session(self, test_conn: sqlite3.Connection):
        env_a = await metrics_start_session(
            test_conn,
            task="task a",
            classification="simple",
        )
        env = await metrics_compare(
            test_conn,
            session_id_a=env_a["data"]["session_id"],
            session_id_b="nonexistent",
        )
        assert env["ok"] is False
        assert env["error"]["code"] == "NOT_FOUND_SESSION"


# ── Phase 2: usage_raw, tiktoken, report_json, enhanced features ──


class TestRecordStepUsageRaw:
    """Test usage_raw provider payload parsing via metrics_record_step."""

    @pytest.mark.asyncio
    async def _create_session(self, conn: sqlite3.Connection) -> str:
        env = await metrics_start_session(conn, task="test", classification="standard")
        return env["data"]["session_id"]

    @pytest.mark.asyncio
    async def test_anthropic_usage_raw(self, test_conn: sqlite3.Connection) -> None:
        sid = await self._create_session(test_conn)
        env = await metrics_record_step(
            test_conn,
            session_id=sid,
            agent="craft",
            model="claude-sonnet-4",
            usage_raw={
                "input_tokens": 1500,
                "output_tokens": 800,
                "cache_read_input_tokens": 200,
                "cache_creation_input_tokens": 100,
            },
        )
        assert env["ok"] is True
        assert env["data"]["recorded"] is True
        assert env["data"]["source"] == "live_response_usage"
        assert env["data"]["confidence"] == "exact"
        assert env["data"]["cost_usd"] > 0

        # Verify DB values
        row = test_conn.execute(
            "SELECT input_tokens, output_tokens, cache_read_tokens, cache_write_tokens "
            "FROM steps WHERE session_id = ?",
            (sid,),
        ).fetchone()
        assert row[0] == 1500
        assert row[1] == 800
        assert row[2] == 200
        assert row[3] == 100

    @pytest.mark.asyncio
    async def test_openai_usage_raw(self, test_conn: sqlite3.Connection) -> None:
        sid = await self._create_session(test_conn)
        env = await metrics_record_step(
            test_conn,
            session_id=sid,
            agent="scope",
            model="gpt-4o",
            usage_raw={
                "prompt_tokens": 2000,
                "completion_tokens": 600,
                "prompt_tokens_details": {"cached_tokens": 500},
            },
            provider="openai",
        )
        assert env["ok"] is True
        row = test_conn.execute(
            "SELECT input_tokens, output_tokens, cache_read_tokens FROM steps WHERE session_id = ?",
            (sid,),
        ).fetchone()
        assert row[0] == 2000
        assert row[1] == 600
        assert row[2] == 500

    @pytest.mark.asyncio
    async def test_explicit_fields_override_usage_raw(self, test_conn: sqlite3.Connection) -> None:
        """Tier 1 (explicit) should take priority over Tier 2 (usage_raw)."""
        sid = await self._create_session(test_conn)
        env = await metrics_record_step(
            test_conn,
            session_id=sid,
            agent="craft",
            input_tokens=999,
            output_tokens=444,
            usage_raw={"input_tokens": 5000, "output_tokens": 3000},
        )
        assert env["ok"] is True
        row = test_conn.execute(
            "SELECT input_tokens, output_tokens FROM steps WHERE session_id = ?",
            (sid,),
        ).fetchone()
        assert row[0] == 999
        assert row[1] == 444


class TestRecordStepTiktokenEstimation:
    """Test tiktoken fallback estimation in metrics_record_step."""

    @pytest.mark.asyncio
    async def _create_session(self, conn: sqlite3.Connection) -> str:
        env = await metrics_start_session(conn, task="test", classification="standard")
        return env["data"]["session_id"]

    @pytest.mark.asyncio
    async def test_tiktoken_estimation_from_text(self, test_conn: sqlite3.Connection) -> None:
        sid = await self._create_session(test_conn)
        env = await metrics_record_step(
            test_conn,
            session_id=sid,
            agent="ensemble",
            input_text="This is a test input with several words to estimate tokens for.",
            output_text="And this is the response text.",
        )
        assert env["ok"] is True
        assert env["data"]["source"] == "estimator"
        assert env["data"]["confidence"] == "estimated"

        row = test_conn.execute(
            "SELECT input_tokens, output_tokens FROM steps WHERE session_id = ?",
            (sid,),
        ).fetchone()
        assert row[0] > 0  # tiktoken should produce non-zero
        assert row[1] > 0


class TestEndSessionReportJson:
    """Test that metrics_end_session populates report_json."""

    @pytest.mark.asyncio
    async def test_report_json_populated(self, test_conn: sqlite3.Connection) -> None:
        env = await metrics_start_session(test_conn, task="test report", classification="simple")
        sid = env["data"]["session_id"]
        await metrics_record_step(
            test_conn,
            session_id=sid,
            agent="craft",
            input_tokens=500,
            output_tokens=200,
        )
        await metrics_end_session(test_conn, session_id=sid, status="completed")

        row = test_conn.execute(
            "SELECT report_json FROM sessions WHERE id = ?",
            (sid,),
        ).fetchone()
        assert row[0] is not None
        report = json.loads(row[0])
        assert report["session_id"] == sid
        assert report["status"] == "completed"
        assert len(report["steps"]) == 1


class TestSessionReportFormatted:
    """Test that metrics_session_report returns a formatted_report."""

    @pytest.mark.asyncio
    async def test_formatted_report_present(self, test_conn: sqlite3.Connection) -> None:
        env = await metrics_start_session(test_conn, task="format test", classification="standard")
        sid = env["data"]["session_id"]
        await metrics_record_step(
            test_conn,
            session_id=sid,
            agent="scope",
            input_tokens=8000,
            output_tokens=2000,
        )
        env2 = await metrics_session_report(test_conn, session_id=sid)
        assert env2["ok"] is True
        assert "formatted_report" in env2["data"]
        formatted = env2["data"]["formatted_report"]
        assert "SESSION REPORT" in formatted
        assert "scope" in formatted
        assert "TOTAL" in formatted

    @pytest.mark.asyncio
    async def test_report_stores_report_json(self, test_conn: sqlite3.Connection) -> None:
        env = await metrics_start_session(
            test_conn, task="json store test", classification="simple"
        )
        sid = env["data"]["session_id"]
        await metrics_session_report(test_conn, session_id=sid)

        row = test_conn.execute(
            "SELECT report_json FROM sessions WHERE id = ?",
            (sid,),
        ).fetchone()
        assert row[0] is not None
        data = json.loads(row[0])
        assert data["session_id"] == sid

    @pytest.mark.asyncio
    async def test_report_includes_mcp_calls(self, test_conn: sqlite3.Connection) -> None:
        env = await metrics_start_session(test_conn, task="mcp call test", classification="simple")
        sid = env["data"]["session_id"]
        # Insert a fake MCP call
        test_conn.execute(
            "INSERT INTO mcp_calls (session_id, tool_name, input_bytes, output_bytes, duration_ms) "
            "VALUES (?, 'patterns_search', 100, 200, 5)",
            (sid,),
        )
        test_conn.commit()

        env2 = await metrics_session_report(test_conn, session_id=sid)
        report = env2["data"]["report"]
        assert len(report["mcp_calls"]) == 1
        assert report["mcp_calls"][0]["tool_name"] == "patterns_search"


class TestTrendDirection:
    """Test that metrics_trend returns trend direction."""

    @pytest.mark.asyncio
    async def test_trend_stable_empty(self, test_conn: sqlite3.Connection) -> None:
        env = await metrics_trend(test_conn, days=30)
        assert env["data"]["trend"] == "stable"

    @pytest.mark.asyncio
    async def test_trend_field_exists(self, test_conn: sqlite3.Connection) -> None:
        await metrics_start_session(test_conn, task="a", classification="simple")
        env = await metrics_trend(test_conn, days=30)
        assert "trend" in env["data"]


class TestCompareWithSteps:
    """Test that metrics_compare includes step breakdowns."""

    @pytest.mark.asyncio
    async def test_compare_includes_steps(self, test_conn: sqlite3.Connection) -> None:
        env_a = await metrics_start_session(test_conn, task="a", classification="simple")
        env_b = await metrics_start_session(test_conn, task="b", classification="standard")
        sid_a = env_a["data"]["session_id"]
        sid_b = env_b["data"]["session_id"]

        await metrics_record_step(
            test_conn,
            session_id=sid_a,
            agent="craft",
            input_tokens=1000,
            output_tokens=500,
        )
        await metrics_record_step(
            test_conn,
            session_id=sid_b,
            agent="scope",
            input_tokens=2000,
            output_tokens=800,
        )

        env = await metrics_compare(test_conn, session_id_a=sid_a, session_id_b=sid_b)
        assert env["ok"] is True
        assert "steps" in env["data"]["session_a"]
        assert "steps" in env["data"]["session_b"]
        assert len(env["data"]["session_a"]["steps"]) == 1
        assert len(env["data"]["session_b"]["steps"]) == 1
