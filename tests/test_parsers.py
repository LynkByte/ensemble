"""Comprehensive tests for AI tool session parsers (OpenCode, Claude Code).

Tests cover:
- OpenCode SQLite parser: find DB, parse session, list sessions,
  missing DB, schema mismatch, partial tokens, epoch timestamps.
- Claude Code JSONL parser: find files, parse JSONL, streaming dedup,
  synthetic skip, subagent parsing, project slug matching, malformed lines.
- Auto-detection: detect OpenCode, detect Claude Code, detect neither.
- Metrics integration: parser hook fires/skipped/degrades.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

# ── OpenCode synthetic fixture helpers ───────────────────────────


def _create_opencode_db(db_path: Path) -> None:
    """Create a minimal OpenCode-schema SQLite database with sample data.

    Mirrors the real OpenCode schema (project, session, message tables)
    with known token values for assertion.
    """
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE project (
            id TEXT PRIMARY KEY,
            worktree TEXT NOT NULL,
            name TEXT,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            vcs TEXT,
            icon_url TEXT,
            icon_color TEXT,
            time_initialized INTEGER,
            sandboxes TEXT NOT NULL DEFAULT '[]',
            commands TEXT
        );

        CREATE TABLE session (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES project(id),
            parent_id TEXT,
            slug TEXT NOT NULL,
            directory TEXT NOT NULL,
            title TEXT NOT NULL,
            version TEXT NOT NULL,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            share_url TEXT,
            summary_additions INTEGER,
            summary_deletions INTEGER,
            summary_files INTEGER,
            summary_diffs TEXT,
            revert TEXT,
            permission TEXT,
            time_compacting INTEGER,
            time_archived INTEGER,
            workspace_id TEXT
        );
        CREATE INDEX session_project_idx ON session(project_id);

        CREATE TABLE message (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            data TEXT NOT NULL
        );
        CREATE INDEX message_session_time_created_id_idx
            ON message(session_id, time_created, id);
    """)

    # Insert project
    conn.execute(
        "INSERT INTO project (id, worktree, name, time_created, time_updated, sandboxes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("proj_001", "/home/user/myproject", "myproject", 1700000000000, 1700000100000, "[]"),
    )

    # Insert session
    conn.execute(
        "INSERT INTO session "
        "(id, project_id, slug, directory, title, version, time_created, time_updated) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "sess_abc123",
            "proj_001",
            "test-session",
            "/home/user/myproject",
            "Fix login bug",
            "1.0",
            1700000010000,
            1700000090000,
        ),
    )

    # Insert second session (older)
    conn.execute(
        "INSERT INTO session "
        "(id, project_id, slug, directory, title, version, time_created, time_updated) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "sess_older",
            "proj_001",
            "old-session",
            "/home/user/myproject",
            "Old task",
            "1.0",
            1700000000000,
            1700000005000,
        ),
    )

    # Insert messages for sess_abc123
    messages = [
        # User message (should be skipped)
        {
            "id": "msg_001",
            "session_id": "sess_abc123",
            "time_created": 1700000010000,
            "data": json.dumps({"role": "user", "content": "Fix the login bug"}),
        },
        # Assistant message with full tokens
        {
            "id": "msg_002",
            "session_id": "sess_abc123",
            "time_created": 1700000020000,
            "data": json.dumps(
                {
                    "role": "assistant",
                    "mode": "build",
                    "agent": "build",
                    "modelID": "claude-opus-4.6",
                    "providerID": "github-copilot",
                    "tokens": {
                        "input": 5000,
                        "output": 1500,
                        "reasoning": 200,
                        "total": 58700,
                        "cache": {"read": 52000, "write": 0},
                    },
                    "time": {"created": 1700000020000, "completed": 1700000025000},
                    "finish": "stop",
                }
            ),
        },
        # Another assistant message with tokens
        {
            "id": "msg_003",
            "session_id": "sess_abc123",
            "time_created": 1700000030000,
            "data": json.dumps(
                {
                    "role": "assistant",
                    "mode": "plan",
                    "agent": "plan",
                    "modelID": "claude-sonnet-4.6",
                    "providerID": "github-copilot",
                    "tokens": {
                        "input": 3000,
                        "output": 800,
                        "reasoning": 0,
                        "cache": {"read": 2500, "write": 100},
                    },
                    "time": {"created": 1700000030000, "completed": 1700000035000},
                    "finish": "tool-calls",
                }
            ),
        },
        # Assistant message with zero tokens (should be skipped)
        {
            "id": "msg_004",
            "session_id": "sess_abc123",
            "time_created": 1700000040000,
            "data": json.dumps(
                {
                    "role": "assistant",
                    "mode": "build",
                    "tokens": {"input": 0, "output": 0, "cache": {"read": 0, "write": 0}},
                    "time": {"created": 1700000040000},
                    "finish": "stop",
                }
            ),
        },
        # Assistant message with missing tokens object (should be skipped)
        {
            "id": "msg_005",
            "session_id": "sess_abc123",
            "time_created": 1700000050000,
            "data": json.dumps(
                {
                    "role": "assistant",
                    "mode": "build",
                    "modelID": "claude-opus-4.6",
                    "time": {"created": 1700000050000},
                    "finish": "stop",
                }
            ),
        },
    ]

    for msg in messages:
        conn.execute(
            "INSERT INTO message (id, session_id, time_created, time_updated, data) "
            "VALUES (?, ?, ?, ?, ?)",
            (msg["id"], msg["session_id"], msg["time_created"], msg["time_created"], msg["data"]),
        )

    conn.commit()
    conn.close()


def _create_opencode_db_bad_schema(db_path: Path) -> None:
    """Create an OpenCode database with a mismatched schema (no message table)."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dummy (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()


# ── Claude Code synthetic JSONL helpers ──────────────────────────

# Known values for assertion
CLAUDE_ASSISTANT_1: dict[str, Any] = {
    "parentUuid": "uuid-user-1",
    "isSidechain": False,
    "type": "assistant",
    "uuid": "uuid-asst-1",
    "timestamp": "2026-03-30T10:00:00Z",
    "sessionId": "sess-cc-001",
    "message": {
        "model": "claude-sonnet-4-6",
        "id": "msg_final_1",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Here is the fix."}],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 4000,
            "output_tokens": 1200,
            "cache_creation_input_tokens": 500,
            "cache_read_input_tokens": 30000,
            "server_tool_use": {"web_search_requests": 1, "web_fetch_requests": 0},
        },
    },
}

# Streaming duplicate: same message.id as CLAUDE_ASSISTANT_1 but earlier
# (partial output_tokens — should be overwritten by CLAUDE_ASSISTANT_1)
CLAUDE_STREAMING_PARTIAL: dict[str, Any] = {
    "parentUuid": "uuid-user-1",
    "isSidechain": False,
    "type": "assistant",
    "uuid": "uuid-asst-1-partial",
    "timestamp": "2026-03-30T09:59:58Z",
    "sessionId": "sess-cc-001",
    "message": {
        "model": "claude-sonnet-4-6",
        "id": "msg_final_1",  # Same message.id!
        "type": "message",
        "role": "assistant",
        "content": [{"type": "thinking", "thinking": "..."}],
        "stop_reason": None,
        "usage": {
            "input_tokens": 4000,
            "output_tokens": 0,  # Partial — no output yet
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    },
}

CLAUDE_ASSISTANT_2: dict[str, Any] = {
    "type": "assistant",
    "uuid": "uuid-asst-2",
    "timestamp": "2026-03-30T10:01:00Z",
    "sessionId": "sess-cc-001",
    "message": {
        "model": "claude-opus-4",
        "id": "msg_final_2",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Done."}],
        "stop_reason": "stop",
        "usage": {
            "input_tokens": 2000,
            "output_tokens": 500,
            "cache_creation_input_tokens": 200,
            "cache_read_input_tokens": 15000,
        },
    },
}

CLAUDE_USER: dict[str, Any] = {
    "type": "user",
    "uuid": "uuid-user-1",
    "timestamp": "2026-03-30T09:59:00Z",
    "message": {"role": "user", "content": "Fix the login bug"},
}

CLAUDE_SYSTEM: dict[str, Any] = {
    "type": "system",
    "subtype": "local_command",
    "content": "Running tests...",
    "uuid": "uuid-sys-1",
    "timestamp": "2026-03-30T10:00:30Z",
}

CLAUDE_SYNTHETIC_ERROR: dict[str, Any] = {
    "type": "assistant",
    "uuid": "uuid-error-1",
    "timestamp": "2026-03-30T09:58:00Z",
    "message": {
        "model": "<synthetic>",
        "id": "msg_error",
        "content": [],
        "stop_reason": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    },
    "error": "authentication_failed",
    "isApiErrorMessage": True,
}

CLAUDE_NO_USAGE: dict[str, Any] = {
    "type": "assistant",
    "uuid": "uuid-no-usage",
    "timestamp": "2026-03-30T10:02:00Z",
    "message": {
        "model": "claude-sonnet-4-6",
        "id": "msg_no_usage",
        "content": [{"type": "text", "text": "..."}],
        "stop_reason": "end_turn",
        # No "usage" key at all
    },
}

# Subagent message
CLAUDE_SUBAGENT: dict[str, Any] = {
    "type": "assistant",
    "uuid": "uuid-sub-1",
    "timestamp": "2026-03-30T10:03:00Z",
    "message": {
        "model": "claude-sonnet-4-6",
        "id": "msg_sub_1",
        "content": [{"type": "text", "text": "Subagent result"}],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 300,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 5000,
        },
    },
}


def _write_claude_session(
    session_dir: Path,
    filename: str,
    lines: list[dict[str, Any]],
) -> Path:
    """Write a JSONL session file with the given lines."""
    session_dir.mkdir(parents=True, exist_ok=True)
    filepath = session_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    return filepath


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture()
def opencode_db(tmp_path: Path) -> Path:
    """Create a synthetic OpenCode database and return its path."""
    db_path = tmp_path / "opencode.db"
    _create_opencode_db(db_path)
    return db_path


@pytest.fixture()
def opencode_db_bad_schema(tmp_path: Path) -> Path:
    """Create an OpenCode DB with wrong schema."""
    db_path = tmp_path / "bad_opencode.db"
    _create_opencode_db_bad_schema(db_path)
    return db_path


@pytest.fixture()
def claude_projects_dir(tmp_path: Path) -> Path:
    """Create a synthetic Claude Code projects directory structure."""
    projects = tmp_path / "projects"

    # Project directory: slug of /home/user/myproject
    proj_slug = "-home-user-myproject"
    proj_dir = projects / proj_slug
    proj_dir.mkdir(parents=True)

    # Main session JSONL (with streaming dedup, synthetic error, etc.)
    _write_claude_session(
        proj_dir,
        "sess-cc-001.jsonl",
        [
            {"type": "file-history-snapshot", "messageId": "snap1", "snapshot": {}},
            CLAUDE_USER,
            CLAUDE_STREAMING_PARTIAL,  # Partial streaming (should be deduped)
            CLAUDE_ASSISTANT_1,  # Final version (keeps this one)
            CLAUDE_SYSTEM,
            CLAUDE_SYNTHETIC_ERROR,  # Synthetic error (should be skipped)
            CLAUDE_ASSISTANT_2,
            CLAUDE_NO_USAGE,  # No usage field (should be skipped)
        ],
    )

    # Subagent directory
    sub_dir = proj_dir / "sess-cc-001" / "subagents"
    _write_claude_session(
        sub_dir,
        "agent-a1234.jsonl",
        [CLAUDE_SUBAGENT],
    )

    # Second project (empty, for negative testing)
    empty_proj = projects / "-home-user-empty"
    empty_proj.mkdir(parents=True)

    # Older session in the main project
    _write_claude_session(
        proj_dir,
        "sess-cc-old.jsonl",
        [CLAUDE_USER],  # No assistant messages
    )

    return projects


@pytest.fixture()
def claude_malformed_session(tmp_path: Path) -> Path:
    """Create a JSONL file with malformed lines."""
    projects = tmp_path / "malformed_projects"
    proj_dir = projects / "-home-user-bad"
    proj_dir.mkdir(parents=True)

    filepath = proj_dir / "sess-bad.jsonl"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("this is not json\n")
        f.write(json.dumps(CLAUDE_ASSISTANT_2) + "\n")
        f.write("{invalid json too\n")
    return projects


# ── Test: OpenCode parser ────────────────────────────────────────


class TestOpenCodeFindDB:
    def test_find_existing_db(self, opencode_db: Path) -> None:
        from ensemble_mcp.parsers.opencode import find_opencode_db

        result = find_opencode_db(opencode_db)
        assert result == opencode_db

    def test_find_missing_db(self, tmp_path: Path) -> None:
        from ensemble_mcp.parsers.opencode import find_opencode_db

        result = find_opencode_db(tmp_path / "nonexistent.db")
        assert result is None

    def test_find_default_path_when_missing(self) -> None:
        """Default path is unlikely to be a test file — just verify None or Path."""
        from ensemble_mcp.parsers.opencode import find_opencode_db

        # This tests the default path logic (may or may not exist)
        result = find_opencode_db()
        assert result is None or isinstance(result, Path)


class TestOpenCodeListSessions:
    def test_list_sessions(self, opencode_db: Path) -> None:
        from ensemble_mcp.parsers.opencode import list_sessions

        sessions = list_sessions(opencode_db)
        assert len(sessions) == 2
        # Most recent first
        assert sessions[0]["session_id"] == "sess_abc123"
        assert sessions[0]["title"] == "Fix login bug"
        assert sessions[0]["project"] == "/home/user/myproject"
        assert sessions[0]["message_count"] == 5

    def test_list_sessions_by_project(self, opencode_db: Path) -> None:
        from ensemble_mcp.parsers.opencode import list_sessions

        sessions = list_sessions(opencode_db, project_path="/home/user/myproject")
        assert len(sessions) == 2

        # Non-existent project
        sessions = list_sessions(opencode_db, project_path="/nowhere")
        assert len(sessions) == 0

    def test_list_sessions_limit(self, opencode_db: Path) -> None:
        from ensemble_mcp.parsers.opencode import list_sessions

        sessions = list_sessions(opencode_db, limit=1)
        assert len(sessions) == 1

    def test_list_sessions_bad_schema(self, opencode_db_bad_schema: Path) -> None:
        from ensemble_mcp.parsers.opencode import list_sessions

        sessions = list_sessions(opencode_db_bad_schema)
        assert sessions == []


class TestOpenCodeParseSession:
    def test_parse_session_full(self, opencode_db: Path) -> None:
        from ensemble_mcp.parsers.opencode import parse_session

        result = parse_session(opencode_db, "sess_abc123")
        assert result is not None
        assert result.session_id == "sess_abc123"
        assert result.ai_tool == "opencode"
        assert result.project == "/home/user/myproject"
        assert result.source == "session_parser"

        # Should have 2 valid assistant steps (zero-token and missing-tokens skipped)
        assert len(result.steps) == 2

        # Verify totals: 5000+3000=8000 input, 1500+800=2300 output
        assert result.total_input_tokens == 8000
        assert result.total_output_tokens == 2300
        assert result.total_cache_read_tokens == 52000 + 2500  # 54500
        assert result.total_cache_write_tokens == 0 + 100  # 100

        # Check individual steps
        step0 = result.steps[0]
        assert step0.model == "claude-opus-4.6"
        assert step0.input_tokens == 5000
        assert step0.output_tokens == 1500
        assert step0.cache_read_tokens == 52000
        assert step0.reasoning_tokens == 200
        assert step0.agent == "build"
        assert step0.finish_reason == "stop"

        step1 = result.steps[1]
        assert step1.model == "claude-sonnet-4.6"
        assert step1.input_tokens == 3000
        assert step1.agent == "plan"

    def test_parse_session_timestamps(self, opencode_db: Path) -> None:
        from ensemble_mcp.parsers.opencode import parse_session

        result = parse_session(opencode_db, "sess_abc123")
        assert result is not None
        # Verify epoch ms → ISO-8601 conversion
        assert result.started_at is not None
        assert "T" in result.started_at  # ISO-8601 format
        assert result.ended_at is not None

        # First step should have a timestamp
        assert result.steps[0].timestamp is not None
        assert "T" in result.steps[0].timestamp

    def test_parse_session_not_found(self, opencode_db: Path) -> None:
        from ensemble_mcp.parsers.opencode import parse_session

        result = parse_session(opencode_db, "nonexistent")
        assert result is None

    def test_parse_session_confidence(self, opencode_db: Path) -> None:
        from ensemble_mcp.parsers.opencode import parse_session

        result = parse_session(opencode_db, "sess_abc123")
        assert result is not None
        # Has steps and no errors → exact confidence
        assert result.confidence == "exact"

    def test_parse_session_empty(self, opencode_db: Path) -> None:
        """Session with no messages → partial confidence."""
        from ensemble_mcp.parsers.opencode import parse_session

        result = parse_session(opencode_db, "sess_older")
        assert result is not None
        assert len(result.steps) == 0
        assert result.confidence == "partial"


class TestOpenCodeParseLatest:
    def test_parse_latest(self, opencode_db: Path) -> None:
        from ensemble_mcp.parsers.opencode import parse_latest_session

        result = parse_latest_session(db_path=opencode_db)
        assert result is not None
        assert result.session_id == "sess_abc123"  # Most recent

    def test_parse_latest_by_project(self, opencode_db: Path) -> None:
        from ensemble_mcp.parsers.opencode import parse_latest_session

        result = parse_latest_session(db_path=opencode_db, project_path="/home/user/myproject")
        assert result is not None

    def test_parse_latest_missing_db(self, tmp_path: Path) -> None:
        from ensemble_mcp.parsers.opencode import parse_latest_session

        result = parse_latest_session(db_path=tmp_path / "nope.db")
        assert result is None


# ── Test: Claude Code parser ─────────────────────────────────────


class TestClaudeCodeSlugHelpers:
    def test_path_to_slug(self) -> None:
        from ensemble_mcp.parsers.claude_code import _path_to_slug

        assert _path_to_slug("/home/user/project") == "-home-user-project"

    def test_slug_to_path(self) -> None:
        from ensemble_mcp.parsers.claude_code import _slug_to_path

        assert _slug_to_path("-home-user-project") == "/home/user/project"


class TestClaudeCodeFindDir:
    def test_find_existing_dir(self, claude_projects_dir: Path) -> None:
        from ensemble_mcp.parsers.claude_code import find_claude_projects_dir

        result = find_claude_projects_dir(claude_projects_dir)
        assert result == claude_projects_dir

    def test_find_missing_dir(self, tmp_path: Path) -> None:
        from ensemble_mcp.parsers.claude_code import find_claude_projects_dir

        result = find_claude_projects_dir(tmp_path / "nonexistent")
        assert result is None


class TestClaudeCodeFindSessionFiles:
    def test_find_all_sessions(self, claude_projects_dir: Path) -> None:
        from ensemble_mcp.parsers.claude_code import find_session_files

        files = find_session_files(claude_projects_dir)
        # Should find 2 JSONL files in the main project (not subagent files)
        assert len(files) == 2
        assert all(f.suffix == ".jsonl" for f in files)

    def test_find_sessions_by_project(self, claude_projects_dir: Path) -> None:
        from ensemble_mcp.parsers.claude_code import find_session_files

        files = find_session_files(claude_projects_dir, project_path="/home/user/myproject")
        assert len(files) == 2

    def test_find_sessions_unknown_project(self, claude_projects_dir: Path) -> None:
        from ensemble_mcp.parsers.claude_code import find_session_files

        files = find_session_files(claude_projects_dir, project_path="/home/user/nonexistent")
        assert len(files) == 0


class TestClaudeCodeDeduplication:
    def test_deduplicate_streaming(self) -> None:
        from ensemble_mcp.parsers.claude_code import _deduplicate_messages

        # Partial then final — should keep final
        lines = [CLAUDE_STREAMING_PARTIAL, CLAUDE_ASSISTANT_1]
        deduped = _deduplicate_messages(lines)
        assert len(deduped) == 1
        # The final version should be kept (output_tokens=1200, not 0)
        assert deduped[0]["message"]["usage"]["output_tokens"] == 1200

    def test_deduplicate_no_message_id(self) -> None:
        from ensemble_mcp.parsers.claude_code import _deduplicate_messages

        # Lines without message.id are kept as-is
        no_id = {"type": "assistant", "message": {"content": "test"}}
        deduped = _deduplicate_messages([no_id, CLAUDE_ASSISTANT_2])
        assert len(deduped) == 2

    def test_deduplicate_preserves_unique(self) -> None:
        from ensemble_mcp.parsers.claude_code import _deduplicate_messages

        # Two different message.ids — both kept
        deduped = _deduplicate_messages([CLAUDE_ASSISTANT_1, CLAUDE_ASSISTANT_2])
        assert len(deduped) == 2


class TestClaudeCodeParseAssistant:
    def test_parse_valid_assistant(self) -> None:
        from ensemble_mcp.parsers.claude_code import _parse_assistant_message

        step = _parse_assistant_message(CLAUDE_ASSISTANT_1)
        assert step is not None
        assert step.model == "claude-sonnet-4-6"
        assert step.input_tokens == 4000
        assert step.output_tokens == 1200
        assert step.cache_write_tokens == 500
        assert step.cache_read_tokens == 30000
        assert step.web_search_requests == 1
        assert step.finish_reason == "end_turn"

    def test_skip_synthetic_error(self) -> None:
        from ensemble_mcp.parsers.claude_code import _parse_assistant_message

        step = _parse_assistant_message(CLAUDE_SYNTHETIC_ERROR)
        assert step is None

    def test_skip_no_usage(self) -> None:
        from ensemble_mcp.parsers.claude_code import _parse_assistant_message

        step = _parse_assistant_message(CLAUDE_NO_USAGE)
        assert step is None

    def test_skip_zero_tokens(self) -> None:
        from ensemble_mcp.parsers.claude_code import _parse_assistant_message

        # The streaming partial has input_tokens=4000 — this IS valid data,
        # so the parser correctly returns a step.  Only messages with
        # BOTH input=0 AND output=0 are skipped.
        step = _parse_assistant_message(CLAUDE_STREAMING_PARTIAL)
        assert step is not None
        assert step.input_tokens == 4000
        assert step.output_tokens == 0

    def test_skip_non_assistant(self) -> None:
        from ensemble_mcp.parsers.claude_code import _parse_assistant_message

        step = _parse_assistant_message(CLAUDE_USER)
        assert step is None  # No "message" key with model/usage


class TestClaudeCodeParseSessionFile:
    def test_parse_session_file(self, claude_projects_dir: Path) -> None:
        from ensemble_mcp.parsers.claude_code import parse_session_file

        session_file = claude_projects_dir / "-home-user-myproject" / "sess-cc-001.jsonl"
        result = parse_session_file(session_file, include_subagents=False)

        assert result is not None
        assert result.session_id == "sess-cc-001"
        assert result.ai_tool == "claude-code"
        assert result.source == "session_parser"

        # After dedup: CLAUDE_ASSISTANT_1 (deduped) + CLAUDE_ASSISTANT_2 = 2 steps
        # CLAUDE_STREAMING_PARTIAL deduped away, SYNTHETIC_ERROR skipped, NO_USAGE skipped
        assert len(result.steps) == 2

        # Totals: 4000+2000=6000 input, 1200+500=1700 output
        assert result.total_input_tokens == 6000
        assert result.total_output_tokens == 1700
        assert result.total_cache_read_tokens == 30000 + 15000  # 45000
        assert result.total_cache_write_tokens == 500 + 200  # 700

    def test_parse_session_with_subagents(self, claude_projects_dir: Path) -> None:
        from ensemble_mcp.parsers.claude_code import parse_session_file

        session_file = claude_projects_dir / "-home-user-myproject" / "sess-cc-001.jsonl"
        result = parse_session_file(session_file, include_subagents=True)

        assert result is not None
        # 2 main + 1 subagent = 3 steps
        assert len(result.steps) == 3

        # Totals: 4000+2000+1000=7000 input, 1200+500+300=2000 output
        assert result.total_input_tokens == 7000
        assert result.total_output_tokens == 2000

    def test_parse_nonexistent_file(self, tmp_path: Path) -> None:
        from ensemble_mcp.parsers.claude_code import parse_session_file

        result = parse_session_file(tmp_path / "nope.jsonl")
        assert result is None

    def test_parse_session_project_from_slug(self, claude_projects_dir: Path) -> None:
        from ensemble_mcp.parsers.claude_code import parse_session_file

        session_file = claude_projects_dir / "-home-user-myproject" / "sess-cc-001.jsonl"
        result = parse_session_file(session_file)
        assert result is not None
        assert result.project == "/home/user/myproject"

    def test_parse_session_timestamps(self, claude_projects_dir: Path) -> None:
        from ensemble_mcp.parsers.claude_code import parse_session_file

        session_file = claude_projects_dir / "-home-user-myproject" / "sess-cc-001.jsonl"
        result = parse_session_file(session_file)
        assert result is not None
        assert result.started_at is not None
        assert result.ended_at is not None


class TestClaudeCodeMalformedLines:
    def test_malformed_jsonl(self, claude_malformed_session: Path) -> None:
        from ensemble_mcp.parsers.claude_code import parse_session_file

        session_file = claude_malformed_session / "-home-user-bad" / "sess-bad.jsonl"
        result = parse_session_file(session_file)
        assert result is not None
        # Should have 1 valid step (CLAUDE_ASSISTANT_2) and 2 errors
        assert len(result.steps) == 1
        assert len(result.errors) == 2
        assert result.confidence == "partial"  # Errors degrade confidence


class TestClaudeCodeParseLatest:
    def test_parse_latest(self, claude_projects_dir: Path) -> None:
        from ensemble_mcp.parsers.claude_code import parse_latest_session

        result = parse_latest_session(projects_dir=claude_projects_dir)
        assert result is not None
        assert result.ai_tool == "claude-code"

    def test_parse_latest_by_project(self, claude_projects_dir: Path) -> None:
        from ensemble_mcp.parsers.claude_code import parse_latest_session

        result = parse_latest_session(
            projects_dir=claude_projects_dir, project_path="/home/user/myproject"
        )
        assert result is not None

    def test_parse_latest_missing_dir(self, tmp_path: Path) -> None:
        from ensemble_mcp.parsers.claude_code import parse_latest_session

        result = parse_latest_session(projects_dir=tmp_path / "nope")
        assert result is None

    def test_parse_latest_empty_project(self, claude_projects_dir: Path) -> None:
        from ensemble_mcp.parsers.claude_code import parse_latest_session

        result = parse_latest_session(
            projects_dir=claude_projects_dir, project_path="/home/user/empty"
        )
        assert result is None  # No JSONL files


# ── Test: Auto-detection ─────────────────────────────────────────


class TestAutoDetection:
    def test_detect_opencode(self, opencode_db: Path) -> None:
        from ensemble_mcp.parsers import detect_ai_tool

        result = detect_ai_tool(
            opencode_db_path=opencode_db,
            claude_projects_dir=Path("/nonexistent"),
        )
        assert result == "opencode"

    def test_detect_claude_code(self, claude_projects_dir: Path) -> None:
        from ensemble_mcp.parsers import detect_ai_tool

        result = detect_ai_tool(
            opencode_db_path=Path("/nonexistent.db"),
            claude_projects_dir=claude_projects_dir,
        )
        assert result == "claude-code"

    def test_detect_opencode_preferred(self, opencode_db: Path, claude_projects_dir: Path) -> None:
        """When both are available, OpenCode is preferred."""
        from ensemble_mcp.parsers import detect_ai_tool

        result = detect_ai_tool(
            opencode_db_path=opencode_db,
            claude_projects_dir=claude_projects_dir,
        )
        assert result == "opencode"

    def test_detect_neither(self, tmp_path: Path) -> None:
        from ensemble_mcp.parsers import detect_ai_tool

        result = detect_ai_tool(
            opencode_db_path=tmp_path / "nope.db",
            claude_projects_dir=tmp_path / "nope",
            cursor_ai_tracking_db=tmp_path / "nope2.db",
            copilot_chat_dir=tmp_path / "nope3",
            windsurf_cascade_dir=tmp_path / "nope4",
            devin_config_dir=tmp_path / "nope5",
        )
        assert result is None


class TestDispatcher:
    def test_dispatch_opencode(self, opencode_db: Path) -> None:
        from ensemble_mcp.parsers import parse_latest_session

        result = parse_latest_session(ai_tool="opencode", opencode_db_path=opencode_db)
        assert result is not None
        assert result.ai_tool == "opencode"

    def test_dispatch_claude_code(self, claude_projects_dir: Path) -> None:
        from ensemble_mcp.parsers import parse_latest_session

        result = parse_latest_session(
            ai_tool="claude-code", claude_projects_dir=claude_projects_dir
        )
        assert result is not None
        assert result.ai_tool == "claude-code"

    def test_dispatch_unknown_tool(self) -> None:
        from ensemble_mcp.parsers import parse_latest_session

        result = parse_latest_session(ai_tool="unknown-tool")
        assert result is None

    def test_dispatch_auto_detect(self, opencode_db: Path) -> None:
        from ensemble_mcp.parsers import parse_latest_session

        result = parse_latest_session(
            opencode_db_path=opencode_db,
            claude_projects_dir=Path("/nonexistent"),
        )
        assert result is not None
        assert result.ai_tool == "opencode"


# ── Test: ParsedSession helpers ──────────────────────────────────


class TestParsedSession:
    def test_compute_totals(self) -> None:
        from ensemble_mcp.parsers import ParsedSession, ParsedStep

        session = ParsedSession(
            steps=[
                ParsedStep(input_tokens=100, output_tokens=50, cache_read_tokens=10),
                ParsedStep(input_tokens=200, output_tokens=75, cache_write_tokens=5),
            ]
        )
        session.compute_totals()
        assert session.total_input_tokens == 300
        assert session.total_output_tokens == 125
        assert session.total_cache_read_tokens == 10
        assert session.total_cache_write_tokens == 5

    def test_to_dict(self) -> None:
        from ensemble_mcp.parsers import ParsedSession

        session = ParsedSession(
            session_id="test",
            ai_tool="opencode",
            total_input_tokens=100,
        )
        d = session.to_dict()
        assert d["session_id"] == "test"
        assert d["ai_tool"] == "opencode"
        assert d["total_input_tokens"] == 100
        assert d["step_count"] == 0
        assert d["error_count"] == 0


# ── Test: Metrics integration hook ───────────────────────────────


class TestMetricsParserHook:
    """Test that the parser fallback in metrics_record_step works."""

    @pytest.fixture()
    def metrics_conn(self, test_conn: sqlite3.Connection) -> sqlite3.Connection:
        """Create a session with ai_tool set."""
        test_conn.execute(
            "INSERT INTO sessions (id, task, classification, ai_tool, project, state) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("sess_hook_test", "Test task", "simple", "opencode", "/test", "running"),
        )
        test_conn.commit()
        return test_conn

    @pytest.mark.asyncio()
    async def test_parser_skipped_when_tokens_present(
        self, metrics_conn: sqlite3.Connection
    ) -> None:
        """When explicit tokens are provided, parser is NOT called."""
        from ensemble_mcp.tools.metrics import metrics_record_step

        env = await metrics_record_step(
            metrics_conn,
            session_id="sess_hook_test",
            agent="craft",
            input_tokens=5000,
            output_tokens=1000,
            model="claude-sonnet-4",
        )
        assert env["ok"] is True
        data = env["data"]
        assert data["recorded"] is True
        # Source should be "local" (direct fields), not "session_parser"
        assert data["source"] != "session_parser"

    @pytest.mark.asyncio()
    async def test_parser_skipped_when_source_explicit(
        self, metrics_conn: sqlite3.Connection
    ) -> None:
        """When source is explicitly set, parser fallback is suppressed."""
        from ensemble_mcp.tools.metrics import metrics_record_step

        env = await metrics_record_step(
            metrics_conn,
            session_id="sess_hook_test",
            agent="craft",
            source="estimator",
            model="claude-sonnet-4",
        )
        assert env["ok"] is True
        data = env["data"]
        assert data["recorded"] is True
        # Parser should not override an explicit source
        assert data["source"] == "estimator"

    @pytest.mark.asyncio()
    async def test_parser_failure_is_non_fatal(
        self, metrics_conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the parser raises, metrics_record_step still succeeds."""

        # Patch the parser dispatch to raise
        def _bad_parser(**kwargs: Any) -> None:
            raise RuntimeError("Parser exploded")

        # The parser is imported lazily inside metrics_record_step,
        # so we patch at the parsers module level
        import ensemble_mcp.parsers as parsers_mod

        monkeypatch.setattr(parsers_mod, "parse_latest_session", _bad_parser)

        from ensemble_mcp.tools.metrics import metrics_record_step

        env = await metrics_record_step(
            metrics_conn,
            session_id="sess_hook_test",
            agent="craft",
            model="claude-sonnet-4",
        )
        # Should still succeed, just with zero/estimated tokens
        assert env["ok"] is True
        assert env["data"]["recorded"] is True
