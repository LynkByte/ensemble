"""Tests for the file watcher daemon (ensemble_mcp.watcher).

Covers:
- Debouncer: trigger, cancel, debounce collapse
- ClaudeCodeHandler: dispatches on .jsonl changes, ignores non-jsonl
- OpenCodePoller: detects mtime changes, stops cleanly
- WatcherEngine: resolve_tools auto-detection, stub tool rejection
- WatcherEngine: run/stop lifecycle with real filesystem events
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ensemble_mcp.watcher import (
    WatcherEngine,
    _ClaudeCodeHandler,
    _Debouncer,
    _OpenCodePoller,
)

_has_watchdog = True
try:
    import watchdog  # noqa: F401
except ImportError:
    _has_watchdog = False

requires_watchdog = pytest.mark.skipif(
    not _has_watchdog,
    reason="watchdog not installed (optional dependency)",
)

# ── Debouncer ────────────────────────────────────────────────────


class TestDebouncer:
    def test_trigger_fires_callback_after_delay(self) -> None:
        callback = MagicMock()
        debouncer = _Debouncer(delay=0.1, callback=callback)
        debouncer.trigger()
        time.sleep(0.3)
        callback.assert_called_once()

    def test_rapid_triggers_collapse(self) -> None:
        """Multiple rapid triggers should fire callback only once."""
        callback = MagicMock()
        debouncer = _Debouncer(delay=0.2, callback=callback)
        for _ in range(5):
            debouncer.trigger()
            time.sleep(0.05)
        time.sleep(0.5)
        callback.assert_called_once()

    def test_cancel_prevents_callback(self) -> None:
        callback = MagicMock()
        debouncer = _Debouncer(delay=0.2, callback=callback)
        debouncer.trigger()
        debouncer.cancel()
        time.sleep(0.4)
        callback.assert_not_called()

    def test_cancel_without_trigger_is_safe(self) -> None:
        callback = MagicMock()
        debouncer = _Debouncer(delay=0.1, callback=callback)
        debouncer.cancel()  # should not raise

    def test_callback_exception_is_caught(self) -> None:
        callback = MagicMock(side_effect=RuntimeError("boom"))
        debouncer = _Debouncer(delay=0.05, callback=callback)
        debouncer.trigger()
        time.sleep(0.2)
        callback.assert_called_once()
        # Should not propagate — just logged


# ── ClaudeCodeHandler ────────────────────────────────────────────


class TestClaudeCodeHandler:
    def test_jsonl_modified_triggers_debouncer(self) -> None:
        debouncer = MagicMock()
        handler = _ClaudeCodeHandler(debouncer)
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/home/user/.claude/projects/foo/session.jsonl"
        event.event_type = "modified"
        handler.dispatch(event)
        debouncer.trigger.assert_called_once()

    def test_jsonl_created_triggers_debouncer(self) -> None:
        debouncer = MagicMock()
        handler = _ClaudeCodeHandler(debouncer)
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/test.jsonl"
        event.event_type = "created"
        handler.dispatch(event)
        debouncer.trigger.assert_called_once()

    def test_non_jsonl_ignored(self) -> None:
        debouncer = MagicMock()
        handler = _ClaudeCodeHandler(debouncer)
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/test.json"
        event.event_type = "modified"
        handler.dispatch(event)
        debouncer.trigger.assert_not_called()

    def test_directory_event_ignored(self) -> None:
        debouncer = MagicMock()
        handler = _ClaudeCodeHandler(debouncer)
        event = MagicMock()
        event.is_directory = True
        event.src_path = "/tmp/test.jsonl"
        event.event_type = "modified"
        handler.dispatch(event)
        debouncer.trigger.assert_not_called()

    def test_deleted_event_ignored(self) -> None:
        debouncer = MagicMock()
        handler = _ClaudeCodeHandler(debouncer)
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/test.jsonl"
        event.event_type = "deleted"
        handler.dispatch(event)
        debouncer.trigger.assert_not_called()


# ── OpenCodePoller ───────────────────────────────────────────────


class TestOpenCodePoller:
    def test_detects_mtime_change(self, tmp_path: Path) -> None:
        db = tmp_path / "opencode.db"
        db.write_bytes(b"initial")

        triggered = threading.Event()
        debouncer = MagicMock()
        debouncer.trigger.side_effect = lambda: triggered.set()

        poller = _OpenCodePoller(db_path=db, debouncer=debouncer, interval=0.1)
        poller.start()

        try:
            # Wait for initial mtime to be captured
            time.sleep(0.3)

            # Modify the file
            db.write_bytes(b"modified content")

            # Wait for detection
            assert triggered.wait(timeout=2.0), "Poller did not detect mtime change"
            debouncer.trigger.assert_called()
        finally:
            poller.stop()
            poller.join(timeout=2)

    def test_stops_cleanly(self, tmp_path: Path) -> None:
        db = tmp_path / "opencode.db"
        db.write_bytes(b"data")

        debouncer = MagicMock()
        poller = _OpenCodePoller(db_path=db, debouncer=debouncer, interval=0.1)
        poller.start()
        time.sleep(0.2)
        poller.stop()
        poller.join(timeout=2)
        assert not poller.is_alive()

    def test_handles_missing_db(self, tmp_path: Path) -> None:
        """Poller should not crash if the DB doesn't exist initially."""
        db = tmp_path / "nonexistent.db"

        debouncer = MagicMock()
        poller = _OpenCodePoller(db_path=db, debouncer=debouncer, interval=0.1)
        poller.start()
        time.sleep(0.3)
        poller.stop()
        poller.join(timeout=2)
        # Should not have triggered — no file to change
        debouncer.trigger.assert_not_called()

    def test_detects_wal_change(self, tmp_path: Path) -> None:
        """Poller should detect changes to the WAL file too."""
        db = tmp_path / "opencode.db"
        db.write_bytes(b"data")
        wal = tmp_path / "opencode.db-wal"

        triggered = threading.Event()
        debouncer = MagicMock()
        debouncer.trigger.side_effect = lambda: triggered.set()

        poller = _OpenCodePoller(db_path=db, debouncer=debouncer, interval=0.1)
        poller.start()

        try:
            time.sleep(0.3)
            # Write to WAL file
            wal.write_bytes(b"wal data")
            assert triggered.wait(timeout=2.0), "Poller did not detect WAL change"
        finally:
            poller.stop()
            poller.join(timeout=2)


# ── WatcherEngine ────────────────────────────────────────────────


class TestWatcherEngineResolve:
    """Test tool resolution logic without starting the actual watcher."""

    def test_explicit_opencode(self, tmp_path: Path) -> None:
        engine = WatcherEngine(ai_tool="opencode", db_path=tmp_path / "data.db")
        watch_oc, watch_cc = engine._resolve_tools()
        assert watch_oc is True
        assert watch_cc is False

    def test_explicit_claude_code(self, tmp_path: Path) -> None:
        engine = WatcherEngine(ai_tool="claude-code", db_path=tmp_path / "data.db")
        watch_oc, watch_cc = engine._resolve_tools()
        assert watch_oc is False
        assert watch_cc is True

    def test_stub_tool_rejected(self, tmp_path: Path) -> None:
        engine = WatcherEngine(ai_tool="cursor", db_path=tmp_path / "data.db")
        watch_oc, watch_cc = engine._resolve_tools()
        assert watch_oc is False
        assert watch_cc is False

    def test_auto_detect_opencode(self, tmp_path: Path) -> None:
        oc_db = tmp_path / "opencode.db"
        oc_db.write_bytes(b"fake")
        engine = WatcherEngine(
            db_path=tmp_path / "data.db",
            opencode_db_path=oc_db,
            claude_projects_dir=tmp_path / "nodir",
        )
        watch_oc, watch_cc = engine._resolve_tools()
        assert watch_oc is True

    def test_auto_detect_claude(self, tmp_path: Path) -> None:
        cc_dir = tmp_path / "projects"
        cc_dir.mkdir()
        engine = WatcherEngine(
            db_path=tmp_path / "data.db",
            opencode_db_path=tmp_path / "nope.db",
            claude_projects_dir=cc_dir,
        )
        watch_oc, watch_cc = engine._resolve_tools()
        assert watch_cc is True


class TestWatcherEngineLifecycle:
    """Test run/stop lifecycle with real but short-lived watchers."""

    def test_run_raises_when_no_tools(self, tmp_path: Path) -> None:
        engine = WatcherEngine(
            db_path=tmp_path / "data.db",
            opencode_db_path=tmp_path / "nope.db",
            claude_projects_dir=tmp_path / "nodir",
        )
        with pytest.raises(RuntimeError, match="No watchable AI tool"):
            engine.run()

    def test_run_and_stop_opencode(self, tmp_path: Path) -> None:
        """Engine should start and stop cleanly with OpenCode polling."""
        oc_db = tmp_path / "opencode.db"
        oc_db.write_bytes(b"fake")
        db_path = tmp_path / "ensemble.db"

        engine = WatcherEngine(
            db_path=db_path,
            opencode_db_path=oc_db,
            claude_projects_dir=tmp_path / "nodir",
            debounce_seconds=0.1,
            poll_interval=0.1,
        )

        # Run in a thread so we can stop it
        thread = threading.Thread(target=engine.run, daemon=True)
        thread.start()
        time.sleep(0.3)
        engine.stop()
        thread.join(timeout=3)
        assert not thread.is_alive()

    @requires_watchdog
    def test_run_and_stop_claude_code(self, tmp_path: Path) -> None:
        """Engine should start and stop cleanly with Claude Code watching."""
        cc_dir = tmp_path / "projects"
        cc_dir.mkdir()
        db_path = tmp_path / "ensemble.db"

        engine = WatcherEngine(
            db_path=db_path,
            opencode_db_path=tmp_path / "nope.db",
            claude_projects_dir=cc_dir,
            debounce_seconds=0.1,
        )

        thread = threading.Thread(target=engine.run, daemon=True)
        thread.start()
        time.sleep(0.3)
        engine.stop()
        thread.join(timeout=3)
        assert not thread.is_alive()

    def test_backfill_count_starts_zero(self, tmp_path: Path) -> None:
        engine = WatcherEngine(
            db_path=tmp_path / "data.db",
            opencode_db_path=tmp_path / "nope.db",
        )
        assert engine.backfill_count == 0
