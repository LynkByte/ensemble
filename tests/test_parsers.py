"""Tests for AI tool session parsers (OpenCode, Claude Code).

Parsers are Phase 3 — these are placeholder tests that verify the
modules exist and are importable.
"""

from __future__ import annotations


class TestParsersImportable:
    def test_opencode_parser_importable(self):
        from ensemble_mcp.parsers import opencode  # noqa: F401

    def test_claude_code_parser_importable(self):
        from ensemble_mcp.parsers import claude_code  # noqa: F401
