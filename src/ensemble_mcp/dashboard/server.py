"""HTTP server for the ensemble-mcp web dashboard.

Uses aiohttp to serve the SPA and JSON API endpoints.
Binds to 127.0.0.1 only — local access, no auth required.
"""

from __future__ import annotations

import logging
import mimetypes
import webbrowser
from pathlib import Path

from aiohttp import web

from ..config.defaults import DASHBOARD_DEFAULT_PORT, DASHBOARD_HOST, DB_PATH, SERVER_VERSION
from ..memory.schema import ensure_schema
from ..state.locks import get_connection
from .api import register_api_routes

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

# Ensure .jsx files are served with a JavaScript MIME type
mimetypes.add_type("application/javascript", ".jsx")


def _ensure_db_ready(db_path: Path) -> None:
    """Ensure the database directory and tables exist.

    Called once at startup so the dashboard can serve even if the MCP
    server has never run.  Delegates to the shared ``ensure_schema()``
    function — the single source of truth for DDL.
    """
    conn = get_connection(db_path)  # handles mkdir + WAL
    try:
        ensure_schema(conn)
    finally:
        conn.close()


def _create_app(db_path: Path = DB_PATH, reports_dir: Path | None = None) -> web.Application:
    """Build the aiohttp application with all routes."""
    # Ensure DB directory and tables exist before serving requests
    _ensure_db_ready(db_path)

    app = web.Application()

    # Store db_path in app state for handlers to access
    app["db_path"] = db_path

    # Store reports_dir in app state for report handlers
    app["reports_dir"] = reports_dir

    # Register JSON API routes
    register_api_routes(app)

    # Serve the SPA for the root path
    app.router.add_get("/", _index_handler)

    # Serve dashboard sub-directory (CSS, JS, JSX files for the React UI)
    app.router.add_static("/dashboard", STATIC_DIR / "dashboard", name="dashboard")

    # Serve remaining static files (legacy /static path kept for compatibility)
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
    reports_dir: Path | None = None,
) -> None:
    """Start the dashboard HTTP server.

    Args:
        port: Port to bind on (default 8787).
        open_browser: Whether to auto-open the browser.
        db_path: Path to the SQLite database.
        reports_dir: Directory containing Bug Hunter report files.
    """
    app = _create_app(db_path=db_path, reports_dir=reports_dir)
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
