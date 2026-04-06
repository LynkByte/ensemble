"""CLI subpackage for terminal-based dashboard and display commands.

Provides the ``ensemble-mcp dashboard`` command that renders an ASCII
metrics dashboard directly from the SQLite database.
"""

from __future__ import annotations

from .dashboard import render_dashboard, run_dashboard

__all__ = ["render_dashboard", "run_dashboard"]
