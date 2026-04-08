"""Tests for stub parsers (Cursor, GitHub Copilot, Windsurf, Devin CLI).

Covers:
- Module constants and docstrings
- ``detect()`` — returns True when local files exist, False otherwise
- ``parse_latest_session()`` — always returns None with a logged warning
- Dispatcher integration — stub tools route correctly through ``__init__``
- Aliases — ``"github-copilot"`` / ``"codeium"`` dispatch correctly
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from ensemble_mcp.parsers import detect_ai_tool, parse_latest_session
from ensemble_mcp.parsers.copilot import (
    TOOL_NAME as COPILOT_TOOL,
)
from ensemble_mcp.parsers.copilot import (
    UNSUPPORTED_REASON as COPILOT_REASON,
)
from ensemble_mcp.parsers.copilot import (
    detect as copilot_detect,
)
from ensemble_mcp.parsers.copilot import (
    parse_latest_session as copilot_parse,
)
from ensemble_mcp.parsers.cursor import (
    TOOL_NAME as CURSOR_TOOL,
)
from ensemble_mcp.parsers.cursor import (
    UNSUPPORTED_REASON as CURSOR_REASON,
)
from ensemble_mcp.parsers.cursor import (
    detect as cursor_detect,
)
from ensemble_mcp.parsers.cursor import (
    parse_latest_session as cursor_parse,
)
from ensemble_mcp.parsers.devin import (
    TOOL_NAME as DEVIN_TOOL,
)
from ensemble_mcp.parsers.devin import (
    UNSUPPORTED_REASON as DEVIN_REASON,
)
from ensemble_mcp.parsers.devin import (
    detect as devin_detect,
)
from ensemble_mcp.parsers.devin import (
    parse_latest_session as devin_parse,
)
from ensemble_mcp.parsers.windsurf import (
    TOOL_NAME as WINDSURF_TOOL,
)
from ensemble_mcp.parsers.windsurf import (
    UNSUPPORTED_REASON as WINDSURF_REASON,
)
from ensemble_mcp.parsers.windsurf import (
    detect as windsurf_detect,
)
from ensemble_mcp.parsers.windsurf import (
    parse_latest_session as windsurf_parse,
)

# ── Constants ────────────────────────────────────────────────────


class TestConstants:
    """Each stub parser must have TOOL_NAME, UNSUPPORTED_REASON, DATA_PATHS."""

    def test_cursor_tool_name(self) -> None:
        assert CURSOR_TOOL == "cursor"

    def test_copilot_tool_name(self) -> None:
        assert COPILOT_TOOL == "copilot"

    def test_windsurf_tool_name(self) -> None:
        assert WINDSURF_TOOL == "windsurf"

    def test_devin_tool_name(self) -> None:
        assert DEVIN_TOOL == "devin"

    def test_unsupported_reasons_are_non_empty(self) -> None:
        for reason in (CURSOR_REASON, COPILOT_REASON, WINDSURF_REASON, DEVIN_REASON):
            assert len(reason) > 30, f"Reason too short: {reason!r}"


# ── detect() ─────────────────────────────────────────────────────


class TestDetect:
    """detect() should return True when local marker files/dirs exist."""

    # -- Cursor --

    def test_cursor_detect_with_db(self, tmp_path: Path) -> None:
        db = tmp_path / "ai-code-tracking.db"
        db.write_bytes(b"fake")
        assert cursor_detect(ai_tracking_db=db) is True

    def test_cursor_detect_with_config_dir(self, tmp_path: Path) -> None:
        cfg = tmp_path / "Cursor"
        cfg.mkdir()
        assert cursor_detect(config_dir=cfg) is True

    def test_cursor_detect_nothing(self, tmp_path: Path) -> None:
        assert (
            cursor_detect(
                ai_tracking_db=tmp_path / "nope.db",
                config_dir=tmp_path / "NoDir",
            )
            is False
        )

    # -- Copilot --

    def test_copilot_detect_with_chat_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "github.copilot-chat"
        d.mkdir()
        assert copilot_detect(chat_dir=d) is True

    def test_copilot_detect_with_state_db(self, tmp_path: Path) -> None:
        db = tmp_path / "state.vscdb"
        db.write_bytes(b"fake")
        assert copilot_detect(state_db=db) is True

    def test_copilot_detect_nothing(self, tmp_path: Path) -> None:
        assert (
            copilot_detect(
                chat_dir=tmp_path / "nodir",
                state_db=tmp_path / "nope.vscdb",
            )
            is False
        )

    # -- Windsurf --

    def test_windsurf_detect_with_cascade_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "cascade"
        d.mkdir()
        assert windsurf_detect(cascade_dir=d) is True

    def test_windsurf_detect_with_config_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "Windsurf"
        d.mkdir()
        assert windsurf_detect(config_dir=d) is True

    def test_windsurf_detect_nothing(self, tmp_path: Path) -> None:
        assert (
            windsurf_detect(
                cascade_dir=tmp_path / "nodir",
                config_dir=tmp_path / "nodir2",
            )
            is False
        )

    # -- Devin --

    def test_devin_detect_with_config_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "cognition"
        d.mkdir()
        assert devin_detect(config_dir=d) is True

    def test_devin_detect_nothing(self, tmp_path: Path) -> None:
        assert devin_detect(config_dir=tmp_path / "nodir") is False


# ── parse_latest_session() ───────────────────────────────────────


class TestParse:
    """All stub parsers must return None and log a warning."""

    def test_cursor_parse_returns_none(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = cursor_parse()
        assert result is None
        assert "Cursor parser" in caplog.text

    def test_copilot_parse_returns_none(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = copilot_parse()
        assert result is None
        assert "GitHub Copilot parser" in caplog.text

    def test_windsurf_parse_returns_none(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = windsurf_parse()
        assert result is None
        assert "Windsurf parser" in caplog.text

    def test_devin_parse_returns_none(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = devin_parse()
        assert result is None
        assert "Devin parser" in caplog.text


# ── Dispatcher integration ───────────────────────────────────────


class TestDispatcher:
    """Verify that stub tools route correctly through the __init__ dispatcher."""

    def test_detect_cursor(self, tmp_path: Path) -> None:
        db = tmp_path / "tracking.db"
        db.write_bytes(b"fake")
        result = detect_ai_tool(
            opencode_db_path=tmp_path / "nope.db",
            claude_projects_dir=tmp_path / "nodir",
            cursor_ai_tracking_db=db,
        )
        assert result == "cursor"

    def test_detect_copilot(self, tmp_path: Path) -> None:
        d = tmp_path / "copilot"
        d.mkdir()
        result = detect_ai_tool(
            opencode_db_path=tmp_path / "nope.db",
            claude_projects_dir=tmp_path / "nodir",
            cursor_ai_tracking_db=tmp_path / "nope2.db",
            copilot_chat_dir=d,
        )
        assert result == "copilot"

    def test_detect_windsurf(self, tmp_path: Path) -> None:
        d = tmp_path / "cascade"
        d.mkdir()
        result = detect_ai_tool(
            opencode_db_path=tmp_path / "nope.db",
            claude_projects_dir=tmp_path / "nodir",
            cursor_ai_tracking_db=tmp_path / "nope2.db",
            copilot_chat_dir=tmp_path / "nodir2",
            windsurf_cascade_dir=d,
        )
        assert result == "windsurf"

    def test_detect_devin(self, tmp_path: Path) -> None:
        d = tmp_path / "cognition"
        d.mkdir()
        result = detect_ai_tool(
            opencode_db_path=tmp_path / "nope.db",
            claude_projects_dir=tmp_path / "nodir",
            cursor_ai_tracking_db=tmp_path / "nope2.db",
            copilot_chat_dir=tmp_path / "nodir2",
            windsurf_cascade_dir=tmp_path / "nodir3",
            devin_config_dir=d,
        )
        assert result == "devin"

    def test_active_parser_preferred_over_stub(self, tmp_path: Path) -> None:
        """When both active (OpenCode) and stub (Cursor) files exist, prefer active."""
        oc_db = tmp_path / "opencode.db"
        oc_db.write_bytes(b"fake")
        cu_db = tmp_path / "tracking.db"
        cu_db.write_bytes(b"fake")
        result = detect_ai_tool(
            opencode_db_path=oc_db,
            claude_projects_dir=tmp_path / "nodir",
            cursor_ai_tracking_db=cu_db,
        )
        assert result == "opencode"

    def test_detect_nothing(self, tmp_path: Path) -> None:
        result = detect_ai_tool(
            opencode_db_path=tmp_path / "nope.db",
            claude_projects_dir=tmp_path / "nodir",
            cursor_ai_tracking_db=tmp_path / "nope2.db",
            copilot_chat_dir=tmp_path / "nodir2",
            windsurf_cascade_dir=tmp_path / "nodir3",
            devin_config_dir=tmp_path / "nodir4",
        )
        assert result is None

    def test_dispatcher_routes_cursor(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = parse_latest_session(ai_tool="cursor")
        assert result is None
        assert "Cursor parser" in caplog.text

    def test_dispatcher_routes_copilot(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = parse_latest_session(ai_tool="copilot")
        assert result is None
        assert "GitHub Copilot parser" in caplog.text

    def test_dispatcher_routes_github_copilot_alias(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = parse_latest_session(ai_tool="github-copilot")
        assert result is None
        assert "GitHub Copilot parser" in caplog.text

    def test_dispatcher_routes_github_copilot_underscore_alias(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            result = parse_latest_session(ai_tool="github_copilot")
        assert result is None
        assert "GitHub Copilot parser" in caplog.text

    def test_dispatcher_routes_windsurf(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = parse_latest_session(ai_tool="windsurf")
        assert result is None
        assert "Windsurf parser" in caplog.text

    def test_dispatcher_routes_codeium_alias(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = parse_latest_session(ai_tool="codeium")
        assert result is None
        assert "Windsurf parser" in caplog.text

    def test_dispatcher_routes_devin(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = parse_latest_session(ai_tool="devin")
        assert result is None
        assert "Devin parser" in caplog.text

    def test_unknown_tool_returns_none(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = parse_latest_session(ai_tool="nonexistent-tool")
        assert result is None
        assert "Unknown AI tool" in caplog.text
