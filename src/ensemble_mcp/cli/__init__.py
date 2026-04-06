"""CLI subpackage for terminal-based dashboard, banner, and display commands.

Provides the ``ensemble-mcp dashboard`` command that renders an ASCII
metrics dashboard directly from the SQLite database, and the startup
banner shown when the MCP server starts.
"""

from __future__ import annotations

from .banner import print_banner
from .dashboard import render_dashboard, run_dashboard

__all__ = ["print_banner", "render_dashboard", "run_dashboard"]
