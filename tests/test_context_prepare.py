"""Tests for the context_prepare MCP tool."""

from __future__ import annotations

import sqlite3

import pytest

from ensemble_mcp.tools.compress import context_prepare


class TestContextPrepare:
    """Tests for context_prepare tool — section ordering, normalization, validation."""

    @pytest.mark.asyncio
    async def test_basic_ordering_static_project_task(self, test_conn: sqlite3.Connection):
        """Sections are sorted: static → project → task."""
        sections = [
            {"name": "task-info", "content": "Fix the bug", "priority": "task"},
            {"name": "system-prompt", "content": "You are an AI", "priority": "static"},
            {"name": "project-context", "content": "Python project", "priority": "project"},
        ]
        env = await context_prepare(test_conn, sections=sections)
        assert env["ok"] is True
        data = env["data"]

        # Verify ordering in sections metadata
        priorities = [s["priority"] for s in data["sections"]]
        assert priorities == ["static", "project", "task"]

        # Verify the prepared text follows the same order
        text = data["prepared_text"]
        assert text.index("You are an AI") < text.index("Python project")
        assert text.index("Python project") < text.index("Fix the bug")

    @pytest.mark.asyncio
    async def test_deterministic_output(self, test_conn: sqlite3.Connection):
        """Same input (regardless of input order) produces identical output."""
        sections_a = [
            {"name": "b-section", "content": "Content B", "priority": "static"},
            {"name": "a-section", "content": "Content A", "priority": "static"},
        ]
        sections_b = [
            {"name": "a-section", "content": "Content A", "priority": "static"},
            {"name": "b-section", "content": "Content B", "priority": "static"},
        ]

        env_a = await context_prepare(test_conn, sections=sections_a)
        env_b = await context_prepare(test_conn, sections=sections_b)

        assert env_a["data"]["prepared_text"] == env_b["data"]["prepared_text"]
        assert env_a["data"]["sections"] == env_b["data"]["sections"]

    @pytest.mark.asyncio
    async def test_within_priority_sorted_by_name(self, test_conn: sqlite3.Connection):
        """Within the same priority tier, sections are sorted by name."""
        sections = [
            {"name": "z-config", "content": "Z content", "priority": "project"},
            {"name": "a-config", "content": "A content", "priority": "project"},
            {"name": "m-config", "content": "M content", "priority": "project"},
        ]
        env = await context_prepare(test_conn, sections=sections)
        assert env["ok"] is True
        names = [s["name"] for s in env["data"]["sections"]]
        assert names == ["a-config", "m-config", "z-config"]

    @pytest.mark.asyncio
    async def test_whitespace_normalization(self, test_conn: sqlite3.Connection):
        """Multiple newlines are collapsed, trailing spaces stripped."""
        sections = [
            {
                "name": "messy",
                "content": "Line one   \n\n\n\nLine two  \n\n\n\n\nLine three",
                "priority": "static",
            },
        ]
        env = await context_prepare(test_conn, sections=sections)
        assert env["ok"] is True
        text = env["data"]["prepared_text"]

        # No more than 2 consecutive newlines
        assert "\n\n\n" not in text
        # No trailing spaces
        for line in text.split("\n"):
            assert line == line.rstrip()

    @pytest.mark.asyncio
    async def test_empty_sections_error(self, test_conn: sqlite3.Connection):
        """Empty sections list produces a validation error."""
        env = await context_prepare(test_conn, sections=[])
        assert env["ok"] is False
        assert env["error"]["code"] == "VALIDATION_INVALID_VALUE"

    @pytest.mark.asyncio
    async def test_invalid_priority_error(self, test_conn: sqlite3.Connection):
        """Invalid priority value produces a validation error."""
        sections = [
            {"name": "bad", "content": "content", "priority": "critical"},
        ]
        env = await context_prepare(test_conn, sections=sections)
        assert env["ok"] is False
        assert env["error"]["code"] == "VALIDATION_INVALID_VALUE"

    @pytest.mark.asyncio
    async def test_missing_required_key_error(self, test_conn: sqlite3.Connection):
        """Section missing a required key produces a validation error."""
        sections = [
            {"name": "incomplete", "priority": "static"},  # missing "content"
        ]
        env = await context_prepare(test_conn, sections=sections)
        assert env["ok"] is False
        assert env["error"]["code"] == "VALIDATION_INVALID_VALUE"

    @pytest.mark.asyncio
    async def test_prefix_stable_bytes_calculation(self, test_conn: sqlite3.Connection):
        """prefix_stable_bytes counts only static + project sections."""
        sections = [
            {"name": "static-a", "content": "Static content here", "priority": "static"},
            {"name": "project-a", "content": "Project info", "priority": "project"},
            {"name": "task-a", "content": "Task specific data", "priority": "task"},
        ]
        env = await context_prepare(test_conn, sections=sections)
        assert env["ok"] is True
        data = env["data"]

        # prefix_stable_bytes should be > 0 (covers static + project sections)
        assert data["prefix_stable_bytes"] > 0

        # Should not include task section bytes
        task_bytes = len(b"Task specific data")
        total_bytes = len(data["prepared_text"].encode("utf-8"))
        assert data["prefix_stable_bytes"] < total_bytes
        assert data["prefix_stable_bytes"] <= total_bytes - task_bytes

    @pytest.mark.asyncio
    async def test_prefix_stable_bytes_all_static(self, test_conn: sqlite3.Connection):
        """When all sections are static, prefix_stable_bytes covers everything."""
        sections = [
            {"name": "a", "content": "First", "priority": "static"},
            {"name": "b", "content": "Second", "priority": "static"},
        ]
        env = await context_prepare(test_conn, sections=sections)
        assert env["ok"] is True
        data = env["data"]

        # All content is stable prefix
        total_bytes = len(data["prepared_text"].encode("utf-8"))
        assert data["prefix_stable_bytes"] == total_bytes

    @pytest.mark.asyncio
    async def test_section_count(self, test_conn: sqlite3.Connection):
        """section_count matches the number of input sections."""
        sections = [
            {"name": "a", "content": "A", "priority": "static"},
            {"name": "b", "content": "B", "priority": "project"},
            {"name": "c", "content": "C", "priority": "task"},
        ]
        env = await context_prepare(test_conn, sections=sections)
        assert env["ok"] is True
        assert env["data"]["section_count"] == 3

    @pytest.mark.asyncio
    async def test_section_metadata_bytes(self, test_conn: sqlite3.Connection):
        """Each section's original_bytes and prepared_bytes are tracked."""
        sections = [
            {
                "name": "test",
                "content": "Hello world   \n\n\n\nextra whitespace",
                "priority": "static",
            },
        ]
        env = await context_prepare(test_conn, sections=sections)
        assert env["ok"] is True
        meta = env["data"]["sections"][0]
        assert meta["original_bytes"] > 0
        assert meta["prepared_bytes"] > 0
        # After whitespace normalization, prepared should be <= original
        assert meta["prepared_bytes"] <= meta["original_bytes"]

    @pytest.mark.asyncio
    async def test_compress_sections_flag(self, test_conn: sqlite3.Connection):
        """When compress_sections=True, sections are compressed."""
        verbose = (
            "Sure! I'd be happy to help. I think this is basically a really good "
            "approach that actually works very well. Perhaps you should consider it. "
            "In order to get started, you need to follow these steps carefully."
        )
        sections = [
            {"name": "verbose", "content": verbose, "priority": "static"},
        ]

        env_normal = await context_prepare(test_conn, sections=sections)
        env_compressed = await context_prepare(test_conn, sections=sections, compress_sections=True)

        assert env_normal["ok"] is True
        assert env_compressed["ok"] is True

        # Compressed version should be shorter or equal
        normal_bytes = env_normal["data"]["sections"][0]["prepared_bytes"]
        compressed_bytes = env_compressed["data"]["sections"][0]["prepared_bytes"]
        assert compressed_bytes <= normal_bytes

    @pytest.mark.asyncio
    async def test_envelope_structure(self, test_conn: sqlite3.Connection):
        """Response follows the standard envelope format."""
        sections = [
            {"name": "test", "content": "Hello", "priority": "static"},
        ]
        env = await context_prepare(test_conn, sections=sections)
        assert env["ok"] is True
        assert env["meta"]["source"] == "local"
        assert env["meta"]["confidence"] == "exact"
        assert isinstance(env["meta"]["duration_ms"], int)

    @pytest.mark.asyncio
    async def test_empty_content_section(self, test_conn: sqlite3.Connection):
        """Sections with empty content are handled gracefully."""
        sections = [
            {"name": "empty", "content": "", "priority": "static"},
            {"name": "real", "content": "Actual content", "priority": "task"},
        ]
        env = await context_prepare(test_conn, sections=sections)
        assert env["ok"] is True
        assert env["data"]["section_count"] == 2
