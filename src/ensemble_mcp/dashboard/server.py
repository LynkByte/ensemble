"""HTTP server for the ensemble-mcp web dashboard.

Uses aiohttp to serve the SPA and JSON API endpoints.
Binds to 127.0.0.1 only — local access, no auth required.
"""

from __future__ import annotations

import logging
import webbrowser
from pathlib import Path

from aiohttp import web

from ..config.defaults import DASHBOARD_DEFAULT_PORT, DASHBOARD_HOST, DB_PATH, SERVER_VERSION
from .api import register_api_routes

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def _create_app(db_path: Path = DB_PATH) -> web.Application:
    """Build the aiohttp application with all routes."""
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


def start_dashboard(
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
