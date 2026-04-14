"""HTTP server for the ensemble-mcp web dashboard.

Uses aiohttp to serve the SPA and JSON API endpoints.
Binds to 127.0.0.1 only — local access, no auth required.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
import webbrowser
from pathlib import Path

from aiohttp import web

from ..config.defaults import DASHBOARD_DEFAULT_PORT, DASHBOARD_HOST, DB_PATH, SERVER_VERSION
from ..state.locks import get_connection
from .api import register_api_routes

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def _ensure_db_ready(db_path: Path) -> None:
    """Ensure the database directory and tables exist.

    Called once at startup so the dashboard can serve even if the MCP
    server has never run. All statements are ``CREATE TABLE IF NOT
    EXISTS`` — safe and idempotent.
    """
    conn = get_connection(db_path)  # handles mkdir + WAL
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, context TEXT NOT NULL,
                approach TEXT NOT NULL, outcome TEXT NOT NULL,
                project TEXT, embedding BLOB NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                last_matched_at TEXT, match_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS mcp_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT NOT NULL,
                input_bytes INTEGER DEFAULT 0,
                output_bytes INTEGER DEFAULT 0,
                duration_ms INTEGER,
                called_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS project_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_path TEXT NOT NULL, file_path TEXT NOT NULL,
                language TEXT, role TEXT,
                size_bytes INTEGER DEFAULT 0,
                modified_at TEXT NOT NULL,
                indexed_at TEXT DEFAULT (datetime('now')),
                UNIQUE(project_path, file_path)
            );
            CREATE TABLE IF NOT EXISTS file_exports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL
                    REFERENCES project_files(id) ON DELETE CASCADE,
                name TEXT NOT NULL, kind TEXT NOT NULL,
                line_number INTEGER, signature TEXT, docstring TEXT,
                UNIQUE(file_id, name, kind)
            );
            CREATE TABLE IF NOT EXISTS file_imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL
                    REFERENCES project_files(id) ON DELETE CASCADE,
                import_path TEXT NOT NULL, raw_import TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS skill_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL, proposed_name TEXT NOT NULL,
                proposed_content TEXT NOT NULL, theme TEXT NOT NULL,
                confidence REAL DEFAULT 0.0, status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')),
                resolved_at TEXT, generated_path TEXT
            );
            CREATE TABLE IF NOT EXISTS skill_usage_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_path TEXT NOT NULL, project TEXT NOT NULL,
                first_seen_at TEXT DEFAULT (datetime('now')),
                last_matched_at TEXT, match_count INTEGER DEFAULT 0,
                UNIQUE(skill_path, project)
            );
            CREATE TABLE IF NOT EXISTS drift_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_description TEXT NOT NULL,
                changed_files TEXT NOT NULL,
                score REAL NOT NULL,
                similarity REAL NOT NULL,
                verdict TEXT NOT NULL,
                flags TEXT NOT NULL,
                project TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS session_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                embedding BLOB,
                original_request TEXT,
                task_classification TEXT,
                status TEXT DEFAULT 'in_progress',
                project TEXT,
                UNIQUE(session_id)
            );
        """)

        # Forward-only migrations: if session_checkpoints was created by
        # an older schema (memory/store.py <v7), it lacks the newer
        # columns.  ALTER TABLE ADD COLUMN is idempotent when wrapped in
        # contextlib.suppress — the OperationalError fires if the column
        # already exists.
        _alter_stmts = [
            "ALTER TABLE session_checkpoints ADD COLUMN embedding BLOB",
            "ALTER TABLE session_checkpoints ADD COLUMN original_request TEXT",
            "ALTER TABLE session_checkpoints ADD COLUMN task_classification TEXT",
            "ALTER TABLE session_checkpoints ADD COLUMN status TEXT DEFAULT 'in_progress'",
            "ALTER TABLE session_checkpoints ADD COLUMN project TEXT",
        ]
        for stmt in _alter_stmts:
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute(stmt)

        # Now safe to create indexes — columns are guaranteed to exist.
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_session_checkpoints_status
                ON session_checkpoints(status);
            CREATE INDEX IF NOT EXISTS idx_session_checkpoints_project
                ON session_checkpoints(project);
        """)
        conn.commit()
    finally:
        conn.close()


def _create_app(db_path: Path = DB_PATH) -> web.Application:
    """Build the aiohttp application with all routes."""
    # Ensure DB directory and tables exist before serving requests
    _ensure_db_ready(db_path)

    app = web.Application()

    # Store db_path in app state for handlers to access
    app["db_path"] = db_path

    # Register JSON API routes
    register_api_routes(app)

    # Serve the SPA for the root path
    app.router.add_get("/", _index_handler)

    # Serve static files (app.js, style.css)
    app.router.add_static("/static", STATIC_DIR, name="static")

    return app


async def _index_handler(request: web.Request) -> web.FileResponse:
    """Serve the dashboard SPA."""
    _ = request  # unused but required by aiohttp handler signature
    return web.FileResponse(STATIC_DIR / "index.html")


def start_dashboard(  # pragma: no cover — blocking server + browser open
    port: int = DASHBOARD_DEFAULT_PORT,
    open_browser: bool = True,
    db_path: Path = DB_PATH,
) -> None:
    """Start the dashboard HTTP server.

    Args:
        port: Port to bind on (default 8787).
        open_browser: Whether to auto-open the browser.
        db_path: Path to the SQLite database.
    """
    app = _create_app(db_path=db_path)
    url = f"http://{DASHBOARD_HOST}:{port}"

    logger.info("Starting ensemble-mcp dashboard v%s", SERVER_VERSION)
    logger.info("Dashboard: %s", url)

    # Print to stderr so it's visible even without logging configured
    import sys

    print(f"\n  ensemble-mcp dashboard v{SERVER_VERSION}", file=sys.stderr)  # noqa: T201
    print(f"  URL: {url}", file=sys.stderr)  # noqa: T201
    print(f"  Database: {db_path}", file=sys.stderr)  # noqa: T201
    print("  Press Ctrl+C to stop\n", file=sys.stderr)  # noqa: T201

    if open_browser:
        # Open browser after a short delay to let the server start
        import asyncio

        async def _open_browser() -> None:
            await asyncio.sleep(0.5)
            webbrowser.open(url)

        async def _on_startup(app: web.Application) -> None:
            _ = app
            asyncio.create_task(_open_browser())

        app.on_startup.append(_on_startup)

    try:
        web.run_app(
            app,
            host=DASHBOARD_HOST,
            port=port,
            print=lambda _: None,  # suppress aiohttp's default print
        )
    except OSError as e:
        if "Address already in use" in str(e) or e.errno == 98:  # noqa: PLR2004
            print(  # noqa: T201
                f"\n  Error: Port {port} is already in use.\n"
                f"  Try: ensemble-mcp web --port {port + 1}\n",
                file=sys.stderr,
            )
            raise SystemExit(1) from e
        raise
