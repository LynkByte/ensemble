"""Tests for the backfill engine and metrics_backfill MCP tool.

Covers:
- Step matching algorithm (timestamp + model)
- Step UPDATE logic
- Session total recomputation
- Force mode (overwrite already-backfilled steps)
- Edge cases: no match, partial match, already backfilled
- Schema migration (v1 → v2: reasoning_tokens column)
- MCP tool integration (metrics_backfill via metrics.py)
"""

from __future__ import annotations

import sqlite3
from typing import Any
from unittest.mock import patch

import pytest

from ensemble_mcp.config.defaults import (
    CONFIDENCE_EXACT,
    CONFIDENCE_PARTIAL,
    SOURCE_BACKFILL,
)
from ensemble_mcp.parsers import ParsedSession, ParsedStep
from ensemble_mcp.tools.backfill import (
    _normalize_model,
    _recompute_session_totals,
    _timestamp_distance_seconds,
    _update_step,
    backfill_session,
    match_steps,
)

# ── Fixtures ──────────────────────────────────────────────────────


def _insert_session(
    conn: sqlite3.Connection,
    session_id: str = "sess_test123",
    ai_tool: str = "opencode",
    project: str | None = "/home/user/project",
    state: str = "running",
) -> str:
    """Insert a test session and return the ID."""
    conn.execute(
        "INSERT INTO sessions (id, task, classification, ai_tool, project, state) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, "Test task", "standard", ai_tool, project, state),
    )
    conn.commit()
    return session_id


def _insert_step(
    conn: sqlite3.Connection,
    session_id: str = "sess_test123",
    agent: str = "scope",
    model: str | None = "claude-sonnet-4",
    input_tokens: int = 0,
    output_tokens: int = 50,
    source: str = "estimator",
    accuracy: str = "estimated",
    started_at: str | None = None,
) -> int:
    """Insert a test step and return its ID."""
    conn.execute(
        "INSERT INTO steps "
        "(session_id, agent, model, model_canonical_name, "
        "input_tokens, output_tokens, source, accuracy, started_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')))",
        (
            session_id,
            agent,
            model,
            model,
            input_tokens,
            output_tokens,
            source,
            accuracy,
            started_at,
        ),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _make_parsed_step(
    model: str = "claude-sonnet-4",
    input_tokens: int = 5000,
    output_tokens: int = 1200,
    cache_read_tokens: int = 3000,
    cache_write_tokens: int = 0,
    reasoning_tokens: int = 0,
    web_search_requests: int = 0,
    timestamp: str | None = None,
) -> ParsedStep:
    return ParsedStep(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        reasoning_tokens=reasoning_tokens,
        web_search_requests=web_search_requests,
        timestamp=timestamp or "2026-04-08T10:00:00+00:00",
    )


def _make_parsed_session(
    steps: list[ParsedStep] | None = None,
    ai_tool: str = "opencode",
) -> ParsedSession:
    s = ParsedSession(
        session_id="oc_sess_1",
        ai_tool=ai_tool,
        project="/home/user/project",
        steps=steps or [_make_parsed_step()],
    )
    s.compute_totals()
    return s


# ── Timestamp helper tests ────────────────────────────────────────


class TestTimestampDistance:
    def test_same_timestamp(self) -> None:
        ts = "2026-04-08T10:00:00+00:00"
        assert _timestamp_distance_seconds(ts, ts) == 0.0

    def test_30_second_gap(self) -> None:
        ts_a = "2026-04-08T10:00:00+00:00"
        ts_b = "2026-04-08T10:00:30+00:00"
        dist = _timestamp_distance_seconds(ts_a, ts_b)
        assert dist is not None
        assert abs(dist - 30.0) < 0.01

    def test_none_returns_none(self) -> None:
        assert _timestamp_distance_seconds(None, "2026-04-08T10:00:00+00:00") is None
        assert _timestamp_distance_seconds("2026-04-08T10:00:00+00:00", None) is None

    def test_invalid_returns_none(self) -> None:
        assert _timestamp_distance_seconds("not-a-date", "2026-04-08T10:00:00+00:00") is None

    def test_sqlite_datetime_format(self) -> None:
        """SQLite uses 'YYYY-MM-DD HH:MM:SS' without T separator."""
        ts_a = "2026-04-08 10:00:00"
        ts_b = "2026-04-08T10:00:30+00:00"
        dist = _timestamp_distance_seconds(ts_a, ts_b)
        assert dist is not None
        assert abs(dist - 30.0) < 0.01


# ── Model normalization tests ────────────────────────────────────


class TestNormalizeModel:
    def test_identity(self) -> None:
        assert _normalize_model("claude-sonnet-4") == "claude-sonnet-4"

    def test_strips_provider_prefix(self) -> None:
        assert _normalize_model("anthropic/claude-sonnet-4") == "claude-sonnet-4"
        assert _normalize_model("openai/gpt-4o") == "gpt-4o"
        assert _normalize_model("github-copilot/claude-opus-4") == "claude-opus-4"

    def test_strips_date_suffix(self) -> None:
        assert _normalize_model("claude-opus-4-20250514") == "claude-opus-4"

    def test_case_insensitive(self) -> None:
        assert _normalize_model("Claude-Sonnet-4") == "claude-sonnet-4"


# ── Matching algorithm tests ──────────────────────────────────────


class TestMatchSteps:
    def test_exact_match_single(self) -> None:
        db_steps = [
            {
                "id": 1,
                "model": "claude-sonnet-4",
                "started_at": "2026-04-08 10:00:00",
                "source": "estimator",
            },
        ]
        parsed = [_make_parsed_step(timestamp="2026-04-08T10:00:05+00:00")]

        matches, unmatched_db, unmatched_parser = match_steps(db_steps, parsed)
        assert len(matches) == 1
        assert matches[0].db_step_id == 1
        assert matches[0].distance_seconds is not None
        assert matches[0].distance_seconds < 10
        assert len(unmatched_db) == 0
        assert len(unmatched_parser) == 0

    def test_multiple_steps_matched_in_order(self) -> None:
        db_steps = [
            {
                "id": 1,
                "model": "claude-sonnet-4",
                "started_at": "2026-04-08 10:00:00",
                "source": "estimator",
            },
            {
                "id": 2,
                "model": "claude-sonnet-4",
                "started_at": "2026-04-08 10:02:00",
                "source": "estimator",
            },
        ]
        parsed = [
            _make_parsed_step(timestamp="2026-04-08T10:00:03+00:00"),
            _make_parsed_step(timestamp="2026-04-08T10:02:05+00:00", input_tokens=8000),
        ]

        matches, unmatched_db, unmatched_parser = match_steps(db_steps, parsed)
        assert len(matches) == 2
        assert matches[0].db_step_id == 1
        assert matches[1].db_step_id == 2

    def test_unmatched_db_step(self) -> None:
        db_steps = [
            {
                "id": 1,
                "model": "claude-sonnet-4",
                "started_at": "2026-04-08 10:00:00",
                "source": "estimator",
            },
        ]
        parsed: list[ParsedStep] = []  # no parsed steps

        matches, unmatched_db, unmatched_parser = match_steps(db_steps, parsed)
        assert len(matches) == 0
        assert unmatched_db == [1]

    def test_unmatched_parser_step(self) -> None:
        db_steps: list[dict[str, Any]] = []  # no DB steps
        parsed = [_make_parsed_step()]

        matches, unmatched_db, unmatched_parser = match_steps(db_steps, parsed)
        assert len(matches) == 0
        assert unmatched_parser == [0]

    def test_model_mismatch_rejected(self) -> None:
        """Steps with different models beyond 10s apart should not match."""
        db_steps = [
            {
                "id": 1,
                "model": "gpt-4o",
                "started_at": "2026-04-08 10:00:00",
                "source": "estimator",
            },
        ]
        parsed = [_make_parsed_step(model="claude-opus-4", timestamp="2026-04-08T10:01:00+00:00")]

        matches, unmatched_db, unmatched_parser = match_steps(db_steps, parsed)
        assert len(matches) == 0
        assert unmatched_db == [1]
        assert unmatched_parser == [0]

    def test_model_none_always_matches(self) -> None:
        """None model in either side should not prevent matching."""
        db_steps = [
            {"id": 1, "model": None, "started_at": "2026-04-08 10:00:00", "source": "estimator"},
        ]
        parsed = [_make_parsed_step(timestamp="2026-04-08T10:00:05+00:00")]

        matches, _, _ = match_steps(db_steps, parsed)
        assert len(matches) == 1

    def test_tolerance_exceeded(self) -> None:
        """Steps farther apart than tolerance should not match."""
        db_steps = [
            {
                "id": 1,
                "model": "claude-sonnet-4",
                "started_at": "2026-04-08 10:00:00",
                "source": "estimator",
            },
        ]
        # 5 minutes away — beyond default 120s tolerance
        parsed = [_make_parsed_step(timestamp="2026-04-08T10:05:00+00:00")]

        matches, unmatched_db, _ = match_steps(db_steps, parsed)
        assert len(matches) == 0
        assert unmatched_db == [1]


# ── Step UPDATE tests ─────────────────────────────────────────────


class TestUpdateStep:
    def test_updates_token_fields(self, test_conn: sqlite3.Connection) -> None:
        sid = _insert_session(test_conn)
        step_id = _insert_step(test_conn, session_id=sid, input_tokens=0, output_tokens=50)

        ps = _make_parsed_step(
            input_tokens=5000,
            output_tokens=1200,
            cache_read_tokens=3000,
            reasoning_tokens=500,
        )
        _update_step(test_conn, step_id, ps, "claude-sonnet-4")
        test_conn.commit()

        row = test_conn.execute(
            "SELECT input_tokens, output_tokens, cache_read_tokens, "
            "reasoning_tokens, source, accuracy FROM steps WHERE id = ?",
            (step_id,),
        ).fetchone()

        assert row[0] == 5000  # input_tokens
        assert row[1] == 1200  # output_tokens
        assert row[2] == 3000  # cache_read_tokens
        assert row[3] == 500  # reasoning_tokens
        assert row[4] == SOURCE_BACKFILL
        assert row[5] == CONFIDENCE_EXACT

    def test_cost_recalculated(self, test_conn: sqlite3.Connection) -> None:
        sid = _insert_session(test_conn)
        step_id = _insert_step(test_conn, session_id=sid)

        ps = _make_parsed_step(input_tokens=1000, output_tokens=500)
        cost = _update_step(test_conn, step_id, ps, "claude-sonnet-4")

        assert cost > 0  # should be non-zero with real token counts


class TestRecomputeSessionTotals:
    def test_sums_all_steps(self, test_conn: sqlite3.Connection) -> None:
        sid = _insert_session(test_conn)
        _insert_step(test_conn, session_id=sid, input_tokens=100, output_tokens=50)
        _insert_step(test_conn, session_id=sid, input_tokens=200, output_tokens=75)

        totals = _recompute_session_totals(test_conn, sid)
        test_conn.commit()

        assert totals["total_input_tokens"] == 300
        assert totals["total_output_tokens"] == 125

        # Verify the DB was updated
        row = test_conn.execute(
            "SELECT total_input_tokens, total_output_tokens FROM sessions WHERE id = ?",
            (sid,),
        ).fetchone()
        assert row[0] == 300
        assert row[1] == 125


# ── Full backfill_session tests ───────────────────────────────────


class TestBackfillSession:
    @patch("ensemble_mcp.tools.backfill.parse_latest_session")
    def test_basic_backfill(
        self,
        mock_parse: Any,
        test_conn: sqlite3.Connection,
    ) -> None:
        """Single step, single parsed message — straightforward backfill."""
        sid = _insert_session(test_conn, ai_tool="opencode")
        _insert_step(
            test_conn,
            session_id=sid,
            input_tokens=0,
            output_tokens=50,
            source="estimator",
            started_at="2026-04-08 10:00:00",
        )

        mock_parse.return_value = _make_parsed_session(
            steps=[
                _make_parsed_step(
                    input_tokens=5000,
                    output_tokens=1200,
                    timestamp="2026-04-08T10:00:05+00:00",
                )
            ]
        )

        result = backfill_session(test_conn, session_id=sid)

        assert result.steps_updated == 1
        assert result.steps_skipped == 0
        assert result.after["total_input_tokens"] == 5000
        assert result.after["total_output_tokens"] == 1200
        assert result.before["total_input_tokens"] == 0

    @patch("ensemble_mcp.tools.backfill.parse_latest_session")
    def test_skips_already_backfilled(
        self,
        mock_parse: Any,
        test_conn: sqlite3.Connection,
    ) -> None:
        """Steps with source='backfill' should be skipped unless forced."""
        sid = _insert_session(test_conn, ai_tool="opencode")
        _insert_step(
            test_conn,
            session_id=sid,
            input_tokens=5000,
            output_tokens=1200,
            source="backfill",
            accuracy="exact",
            started_at="2026-04-08 10:00:00",
        )

        mock_parse.return_value = _make_parsed_session()

        result = backfill_session(test_conn, session_id=sid)

        assert result.steps_updated == 0
        assert result.steps_skipped == 1

    @patch("ensemble_mcp.tools.backfill.parse_latest_session")
    def test_force_overwrites_backfilled(
        self,
        mock_parse: Any,
        test_conn: sqlite3.Connection,
    ) -> None:
        """With force=True, even backfilled steps should be updated."""
        sid = _insert_session(test_conn, ai_tool="opencode")
        _insert_step(
            test_conn,
            session_id=sid,
            input_tokens=5000,
            output_tokens=1200,
            source="backfill",
            accuracy="exact",
            started_at="2026-04-08 10:00:00",
        )

        mock_parse.return_value = _make_parsed_session(
            steps=[
                _make_parsed_step(
                    input_tokens=6000,
                    output_tokens=1500,
                    timestamp="2026-04-08T10:00:05+00:00",
                )
            ]
        )

        result = backfill_session(test_conn, session_id=sid, force=True)

        assert result.steps_updated == 1
        assert result.after["total_input_tokens"] == 6000

    @patch("ensemble_mcp.tools.backfill.parse_latest_session")
    def test_no_ai_tool_raises(
        self,
        mock_parse: Any,
        test_conn: sqlite3.Connection,
    ) -> None:
        """Session with no ai_tool and no override should raise."""
        sid = _insert_session(test_conn, ai_tool=None)
        _insert_step(test_conn, session_id=sid)

        from ensemble_mcp.contracts.errors import ToolError

        with pytest.raises(ToolError, match="no ai_tool"):
            backfill_session(test_conn, session_id=sid)

    @patch("ensemble_mcp.tools.backfill.parse_latest_session")
    def test_ai_tool_override(
        self,
        mock_parse: Any,
        test_conn: sqlite3.Connection,
    ) -> None:
        """ai_tool_override should be passed to the parser."""
        sid = _insert_session(test_conn, ai_tool=None)
        _insert_step(
            test_conn,
            session_id=sid,
            started_at="2026-04-08 10:00:00",
        )

        mock_parse.return_value = _make_parsed_session(
            steps=[_make_parsed_step(timestamp="2026-04-08T10:00:05+00:00")]
        )

        result = backfill_session(test_conn, session_id=sid, ai_tool_override="opencode")

        assert result.steps_updated == 1
        mock_parse.assert_called_once()
        call_kwargs = mock_parse.call_args[1]
        assert call_kwargs["ai_tool"] == "opencode"

    @patch("ensemble_mcp.tools.backfill.parse_latest_session")
    def test_no_parsed_session_raises(
        self,
        mock_parse: Any,
        test_conn: sqlite3.Connection,
    ) -> None:
        """When the parser returns None, should raise NOT_FOUND."""
        sid = _insert_session(test_conn, ai_tool="opencode")
        _insert_step(test_conn, session_id=sid)

        mock_parse.return_value = None

        from ensemble_mcp.contracts.errors import ToolError

        with pytest.raises(ToolError, match="No parsed session"):
            backfill_session(test_conn, session_id=sid)

    @patch("ensemble_mcp.tools.backfill.parse_latest_session")
    def test_defaults_to_latest_session(
        self,
        mock_parse: Any,
        test_conn: sqlite3.Connection,
    ) -> None:
        """When no session_id is given, should use the most recent."""
        # Insert with explicit started_at to guarantee ordering
        test_conn.execute(
            "INSERT INTO sessions (id, task, classification, ai_tool, project, state, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "sess_old",
                "Old task",
                "standard",
                "opencode",
                "/project",
                "running",
                "2026-04-08 09:00:00",
            ),
        )
        _insert_step(test_conn, session_id="sess_old", started_at="2026-04-08 09:00:00")

        test_conn.execute(
            "INSERT INTO sessions (id, task, classification, ai_tool, project, state, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "sess_new",
                "New task",
                "standard",
                "opencode",
                "/project",
                "running",
                "2026-04-08 10:00:00",
            ),
        )
        _insert_step(test_conn, session_id="sess_new", started_at="2026-04-08 10:00:00")
        test_conn.commit()

        mock_parse.return_value = _make_parsed_session(
            steps=[_make_parsed_step(timestamp="2026-04-08T10:00:05+00:00")]
        )

        result = backfill_session(test_conn, session_id=None)

        # Should pick sess_new (most recent by started_at)
        assert result.session_id == "sess_new"

    @patch("ensemble_mcp.tools.backfill.parse_latest_session")
    def test_partial_match_confidence(
        self,
        mock_parse: Any,
        test_conn: sqlite3.Connection,
    ) -> None:
        """When some DB steps don't match, confidence should be partial."""
        sid = _insert_session(test_conn, ai_tool="opencode")
        _insert_step(test_conn, session_id=sid, started_at="2026-04-08 10:00:00")
        _insert_step(test_conn, session_id=sid, started_at="2026-04-08 11:00:00")

        # Only one parsed step — so second DB step will be unmatched
        mock_parse.return_value = _make_parsed_session(
            steps=[_make_parsed_step(timestamp="2026-04-08T10:00:05+00:00")]
        )

        result = backfill_session(test_conn, session_id=sid)

        assert result.steps_updated == 1
        assert result.steps_unmatched_db == 1
        assert result.confidence == CONFIDENCE_PARTIAL

    @patch("ensemble_mcp.tools.backfill.parse_latest_session")
    def test_reasoning_tokens_stored(
        self,
        mock_parse: Any,
        test_conn: sqlite3.Connection,
    ) -> None:
        """Reasoning tokens from the parser should be stored in the new column."""
        sid = _insert_session(test_conn, ai_tool="opencode")
        step_id = _insert_step(
            test_conn,
            session_id=sid,
            started_at="2026-04-08 10:00:00",
        )

        mock_parse.return_value = _make_parsed_session(
            steps=[
                _make_parsed_step(
                    reasoning_tokens=1500,
                    timestamp="2026-04-08T10:00:05+00:00",
                )
            ]
        )

        backfill_session(test_conn, session_id=sid)

        row = test_conn.execute(
            "SELECT reasoning_tokens FROM steps WHERE id = ?",
            (step_id,),
        ).fetchone()
        assert row[0] == 1500

    @patch("ensemble_mcp.tools.backfill.parse_latest_session")
    def test_claude_code_backfill(
        self,
        mock_parse: Any,
        test_conn: sqlite3.Connection,
    ) -> None:
        """Backfill should work with Claude Code sessions too."""
        sid = _insert_session(test_conn, ai_tool="claude-code")
        _insert_step(
            test_conn,
            session_id=sid,
            model="claude-sonnet-4",
            started_at="2026-04-08 10:00:00",
        )

        mock_parse.return_value = _make_parsed_session(
            ai_tool="claude-code",
            steps=[
                _make_parsed_step(
                    model="claude-sonnet-4",
                    input_tokens=3000,
                    output_tokens=800,
                    web_search_requests=2,
                    timestamp="2026-04-08T10:00:05+00:00",
                )
            ],
        )

        result = backfill_session(test_conn, session_id=sid)

        assert result.steps_updated == 1
        assert result.after["total_input_tokens"] == 3000

        # Verify web_search_requests stored
        row = test_conn.execute(
            "SELECT web_search_requests FROM steps WHERE session_id = ?",
            (sid,),
        ).fetchone()
        assert row[0] == 2


# ── Schema migration tests ────────────────────────────────────────


class TestSchemaMigration:
    def test_reasoning_tokens_column_exists(
        self,
        test_conn: sqlite3.Connection,
    ) -> None:
        """The reasoning_tokens column should exist in the steps table."""
        cols = {row[1] for row in test_conn.execute("PRAGMA table_info(steps)").fetchall()}
        assert "reasoning_tokens" in cols

    def test_v1_to_v2_migration(self, tmp_path: Any) -> None:
        """Simulate a v1 database that gets upgraded to v2."""
        from ensemble_mcp.state.locks import get_connection

        db_path = tmp_path / "v1_test.db"
        conn = get_connection(db_path)

        # Create v1 schema (without reasoning_tokens)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT DEFAULT (datetime('now'))
            );
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
            INSERT INTO schema_version (version) VALUES (1);
        """)
        conn.commit()

        # Verify no reasoning_tokens column
        cols_before = {row[1] for row in conn.execute("PRAGMA table_info(steps)").fetchall()}
        assert "reasoning_tokens" not in cols_before

        conn.close()

        # Now open with VectorStore which should run migration
        from ensemble_mcp.memory.store import VectorStore

        store = VectorStore(db_path=db_path, model=None)  # type: ignore[arg-type]

        # Verify column was added
        cols_after = {row[1] for row in store.conn.execute("PRAGMA table_info(steps)").fetchall()}
        assert "reasoning_tokens" in cols_after

        # Verify schema version is now 2
        version = store.conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        assert version == 2

        store.close()
