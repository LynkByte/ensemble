"""CLI subpackage for the startup banner and display commands.

Provides the startup banner shown when the MCP server starts.
"""

from __future__ import annotations

from .banner import print_banner

__all__ = ["print_banner"]
