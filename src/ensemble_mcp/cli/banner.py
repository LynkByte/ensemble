"""Startup banner displayed when the MCP server starts.

Writes an informative banner to *stderr* so it never interferes with
the MCP protocol on stdout.
"""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

from ..config.defaults import (
    DB_PATH,
    GLOBAL_CONFIG_PATH,
    MODEL_DIR,
    SERVER_NAME,
    SERVER_VERSION,
)

# All user-facing output goes to stderr — stdout is reserved for MCP.
_stderr = Console(stderr=True, highlight=False)


def print_banner() -> None:
    """Print the server startup banner to stderr."""
    title = Text()
    title.append(f"{SERVER_NAME}", style="bold cyan")
    title.append(f" v{SERVER_VERSION}", style="dim")
    _stderr.print(title)

    _stderr.print(f"  Config:   {GLOBAL_CONFIG_PATH}", style="dim")
    _stderr.print(f"  Database: {DB_PATH}", style="dim")
    _stderr.print(f"  Models:   {MODEL_DIR}", style="dim")
    _stderr.print()

    ready = Text()
    ready.append("Server started", style="bold green")
    ready.append(" — listening on stdio", style="dim")
    _stderr.print(ready)
