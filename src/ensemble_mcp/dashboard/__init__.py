"""Web dashboard for ensemble-mcp.

Local-only browser interface for visualizing patterns, skills,
projects, drift history, and sessions.
"""

from .server import start_dashboard

__all__ = ["start_dashboard"]
