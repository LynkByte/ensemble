"""File watcher daemon for automatic session backfill.

Monitors AI tool session files for changes and automatically triggers
backfill when new data is detected.  Two watch strategies are used:

- **Claude Code** (``~/.claude/projects/**/*.jsonl``): Filesystem event
  monitoring via ``watchdog``.  JSONL appends generate clean events.
- **OpenCode** (``~/.local/share/opencode/opencode.db``): Modification
  time polling.  SQLite WAL mode makes inotify unreliable because writes
  go to the WAL journal first, not the main DB file.

The watcher debounces rapid changes (AI tools write in bursts during a
session) and triggers backfill only after a configurable quiet period.

Usage::

    engine = WatcherEngine(db_path=DB_PATH, debounce_seconds=5)
    engine.run()  # blocks until SIGINT/SIGTERM

Requires the ``watchdog`` optional dependency::

    pip install ensemble-mcp[watch]
"""

from __future__ import annotations

import logging
import signal
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .config.defaults import (
    CLAUDE_PROJECTS_DIR,
    DB_PATH,
    DEFAULT_WATCH_DEBOUNCE_SECONDS,
    DEFAULT_WATCH_POLL_INTERVAL_SECONDS,
    OPENCODE_DB_PATH,
)
from .parsers import detect_ai_tool

logger = logging.getLogger(__name__)


def _check_watchdog() -> None:
    """Raise ImportError with a helpful message if watchdog is missing."""
    try:
        import watchdog  # noqa: F401
    except ImportError:
        raise ImportError(  # noqa: B904
            "The 'watchdog' package is required for the file watcher daemon.\n"
            "Install it with:  pip install ensemble-mcp[watch]"
        )


class _Debouncer:
    """Thread-safe debounce timer.

    Resets a countdown each time ``trigger()`` is called.  When the timer
    expires without another trigger, ``callback`` fires once.
    """

    def __init__(self, delay: float, callback: Any) -> None:
        self._delay = delay
        self._callback = callback
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def trigger(self) -> None:
        """Reset the debounce timer.  Called on each filesystem event."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        """Execute the callback after the debounce period."""
        with self._lock:
            self._timer = None
        try:
            self._callback()
        except Exception:
            logger.exception("Debounced callback failed")

    def cancel(self) -> None:
        """Cancel any pending timer."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None


class _ClaudeCodeHandler:
    """Watchdog event handler for Claude Code JSONL files.

    Fires the debouncer on any .jsonl file modification/creation under
    the Claude projects directory.
    """

    def __init__(self, debouncer: _Debouncer) -> None:
        self._debouncer = debouncer

    def dispatch(self, event: Any) -> None:
        """Handle watchdog events — filter for .jsonl changes."""
        # Only care about file events (not directory events)
        if getattr(event, "is_directory", False):
            return

        src = getattr(event, "src_path", "") or ""
        event_type = getattr(event, "event_type", "")

        # Only trigger on .jsonl file writes
        if src.endswith(".jsonl") and event_type in ("modified", "created"):
            logger.debug("Claude Code change detected: %s (%s)", src, event_type)
            self._debouncer.trigger()


class _OpenCodePoller(threading.Thread):
    """Poll the OpenCode SQLite database for modification time changes.

    SQLite WAL mode means inotify often misses writes (they go to the
    WAL file first).  Polling the main DB's mtime is more reliable.
    """

    def __init__(
        self,
        db_path: Path,
        debouncer: _Debouncer,
        interval: float,
    ) -> None:
        super().__init__(daemon=True, name="opencode-poller")
        self._db_path = db_path
        self._debouncer = debouncer
        self._interval = interval
        self._stop_event = threading.Event()
        self._last_mtime: float = 0.0

    def run(self) -> None:
        """Poll loop — check mtime every ``interval`` seconds."""
        # Also watch the WAL file as a secondary signal
        wal_path = self._db_path.parent / (self._db_path.name + "-wal")

        # Initialize with current mtime
        self._last_mtime = self._get_mtime(self._db_path, wal_path)

        while not self._stop_event.is_set():
            self._stop_event.wait(self._interval)
            if self._stop_event.is_set():
                break

            current = self._get_mtime(self._db_path, wal_path)
            if current > self._last_mtime:
                logger.debug(
                    "OpenCode DB change detected (mtime: %.1f → %.1f)",
                    self._last_mtime,
                    current,
                )
                self._last_mtime = current
                self._debouncer.trigger()

    def stop(self) -> None:
        """Signal the polling thread to exit."""
        self._stop_event.set()

    @staticmethod
    def _get_mtime(db_path: Path, wal_path: Path) -> float:
        """Return the latest mtime across the main DB and WAL file."""
        mtime = 0.0
        if db_path.exists():
            mtime = db_path.stat().st_mtime
        if wal_path.exists():
            mtime = max(mtime, wal_path.stat().st_mtime)
        return mtime


class WatcherEngine:
    """Orchestrates file watching and automatic backfill.

    Parameters
    ----------
    db_path:
        Path to the ensemble-mcp database.
    debounce_seconds:
        Quiet period after the last filesystem event before backfill
        triggers.  Prevents repeated backfills during burst writes.
    poll_interval:
        How often to check the OpenCode DB modification time (seconds).
    ai_tool:
        Override auto-detection — ``"opencode"``, ``"claude-code"``,
        or ``None`` for auto.
    opencode_db_path:
        Override the default OpenCode DB path.
    claude_projects_dir:
        Override the default Claude Code projects directory.
    """

    def __init__(
        self,
        *,
        db_path: Path | None = None,
        debounce_seconds: float = DEFAULT_WATCH_DEBOUNCE_SECONDS,
        poll_interval: float = DEFAULT_WATCH_POLL_INTERVAL_SECONDS,
        ai_tool: str | None = None,
        opencode_db_path: Path | None = None,
        claude_projects_dir: Path | None = None,
    ) -> None:
        self._db_path = db_path or DB_PATH
        self._debounce_seconds = debounce_seconds
        self._poll_interval = poll_interval
        self._ai_tool = ai_tool
        self._opencode_db_path = opencode_db_path or OPENCODE_DB_PATH
        self._claude_projects_dir = claude_projects_dir or CLAUDE_PROJECTS_DIR
        self._running = False
        self._stop_event = threading.Event()
        self._observer: Any = None  # watchdog Observer
        self._poller: _OpenCodePoller | None = None
        self._backfill_count = 0
        self._last_backfill: float = 0.0

    @property
    def backfill_count(self) -> int:
        """Number of backfill operations completed since start."""
        return self._backfill_count

    def _do_backfill(self) -> None:
        """Execute a backfill pass for the most recent session."""
        from .state.locks import get_connection
        from .tools.backfill import backfill_session

        logger.info("Watcher: triggering backfill...")
        conn: sqlite3.Connection | None = None
        try:
            conn = get_connection(self._db_path)
            result = backfill_session(
                conn,
                ai_tool_override=self._ai_tool,
            )
            self._backfill_count += 1
            self._last_backfill = time.time()
            logger.info(
                "Watcher: backfill complete — session=%s, updated=%d, "
                "skipped=%d, unmatched_db=%d, unmatched_parser=%d",
                result.session_id,
                result.steps_updated,
                result.steps_skipped,
                result.steps_unmatched_db,
                result.steps_unmatched_parser,
            )
        except Exception:
            logger.exception("Watcher: backfill failed")
        finally:
            if conn is not None:
                conn.close()

    def _resolve_tools(self) -> tuple[bool, bool]:
        """Determine which tools to watch.

        Returns (watch_opencode, watch_claude_code).
        """
        if self._ai_tool == "opencode":
            return (True, False)
        if self._ai_tool in ("claude-code", "claude_code", "claude"):
            return (False, True)
        if self._ai_tool is not None:
            # Stub parser tool specified — can't watch
            logger.warning(
                "Tool %r has no parsable session data; the watcher has nothing to watch.",
                self._ai_tool,
            )
            return (False, False)

        # Auto-detect
        detected = detect_ai_tool()
        watch_oc = self._opencode_db_path.is_file()
        watch_cc = self._claude_projects_dir.is_dir()

        if detected:
            logger.info("Auto-detected AI tool: %s", detected)
        if not watch_oc and not watch_cc:
            logger.warning(
                "No watchable AI tool session data found. "
                "Expected OpenCode DB at %s or Claude Code projects at %s",
                self._opencode_db_path,
                self._claude_projects_dir,
            )

        return (watch_oc, watch_cc)

    def run(self) -> None:
        """Start watching and block until SIGINT/SIGTERM.

        Raises
        ------
        RuntimeError
            If no watchable AI tool session data is found.
        ImportError
            If ``watchdog`` is not installed (only checked when Claude
            Code watching is needed).
        """
        watch_oc, watch_cc = self._resolve_tools()
        if not watch_oc and not watch_cc:
            raise RuntimeError(
                "No watchable AI tool session data found. "
                "Ensure OpenCode or Claude Code has session data, "
                "or specify --ai-tool explicitly."
            )

        debouncer = _Debouncer(self._debounce_seconds, self._do_backfill)
        self._running = True

        # Set up signal handlers for graceful shutdown (main thread only)
        original_sigint = None
        original_sigterm = None
        is_main_thread = threading.current_thread() is threading.main_thread()

        if is_main_thread:

            def _shutdown(signum: int, frame: Any) -> None:  # noqa: ARG001
                logger.info("Received signal %d, shutting down...", signum)
                self.stop()

            original_sigint = signal.getsignal(signal.SIGINT)
            original_sigterm = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGINT, _shutdown)
            signal.signal(signal.SIGTERM, _shutdown)

        try:
            # Start Claude Code filesystem watcher
            if watch_cc:
                _check_watchdog()
                from watchdog.events import FileSystemEventHandler
                from watchdog.observers import Observer

                handler = _ClaudeCodeHandler(debouncer)
                # Create a proper FileSystemEventHandler subclass wrapping our handler
                _wrapped = type(
                    "_WrappedHandler",
                    (FileSystemEventHandler,),
                    {"on_any_event": lambda self, event: handler.dispatch(event)},  # noqa: ARG005
                )()

                self._observer = Observer()
                self._observer.schedule(
                    _wrapped,
                    str(self._claude_projects_dir),
                    recursive=True,
                )
                self._observer.start()
                logger.info(
                    "Watching Claude Code projects: %s",
                    self._claude_projects_dir,
                )

            # Start OpenCode mtime poller
            if watch_oc:
                self._poller = _OpenCodePoller(
                    db_path=self._opencode_db_path,
                    debouncer=debouncer,
                    interval=self._poll_interval,
                )
                self._poller.start()
                logger.info(
                    "Polling OpenCode DB: %s (every %ds)",
                    self._opencode_db_path,
                    int(self._poll_interval),
                )

            logger.info(
                "Watcher started (debounce=%ds). Press Ctrl+C to stop.",
                int(self._debounce_seconds),
            )

            # Block until stop is requested
            self._stop_event.wait()

        finally:
            self._cleanup(debouncer)
            # Restore original signal handlers
            if is_main_thread:
                signal.signal(signal.SIGINT, original_sigint)
                signal.signal(signal.SIGTERM, original_sigterm)

    def stop(self) -> None:
        """Signal the watcher to shut down gracefully."""
        self._running = False
        self._stop_event.set()

    def _cleanup(self, debouncer: _Debouncer) -> None:
        """Stop all watchers and cancel pending timers."""
        debouncer.cancel()

        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

        if self._poller is not None:
            self._poller.stop()
            self._poller.join(timeout=5)
            self._poller = None

        self._running = False
        logger.info("Watcher stopped. Backfills performed: %d", self._backfill_count)
