"""Tests for the context_compress MCP tool wrapper."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ensemble_mcp.tools.compress import context_compress


class TestContextCompress:
    @pytest.mark.asyncio
    async def test_basic_compression(self, test_conn: sqlite3.Connection):
        env = await context_compress(
            test_conn,
            text=(
                "Sure! I'd be happy to help. I think this is basically a really good "
                "approach that actually works very well. Perhaps you should consider it."
            ),
        )
        assert env["ok"] is True
        data = env["data"]
        assert "compressed_text" in data
        assert "original_tokens" in data
        assert "compressed_tokens" in data
        assert "savings_pct" in data
        assert "preserved_count" in data
        assert isinstance(data["compressed_text"], str)
        assert isinstance(data["original_tokens"], int)
        assert isinstance(data["compressed_tokens"], int)
        assert isinstance(data["savings_pct"], float)
        assert isinstance(data["preserved_count"], int)

    @pytest.mark.asyncio
    async def test_envelope_structure(self, test_conn: sqlite3.Connection):
        env = await context_compress(
            test_conn,
            text="I think this is basically a really good test of the system right here.",
        )
        assert env["ok"] is True
        assert env["meta"]["source"] == "local"
        assert env["meta"]["confidence"] == "exact"
        assert isinstance(env["meta"]["duration_ms"], int)

    @pytest.mark.asyncio
    async def test_preserves_code(self, test_conn: sqlite3.Connection):
        env = await context_compress(
            test_conn,
            text=(
                "I think you should do this:\n\n"
                "```python\ndef hello():\n    print('world')\n```\n\n"
                "It's basically simple."
            ),
        )
        assert env["ok"] is True
        assert "```python" in env["data"]["compressed_text"]
        assert "def hello():" in env["data"]["compressed_text"]

    @pytest.mark.asyncio
    async def test_empty_text_error(self, test_conn: sqlite3.Connection):
        env = await context_compress(test_conn, text="")
        assert env["ok"] is False
        assert env["error"]["code"] == "VALIDATION_INVALID_VALUE"

    @pytest.mark.asyncio
    async def test_whitespace_only_error(self, test_conn: sqlite3.Connection):
        env = await context_compress(test_conn, text="   ")
        assert env["ok"] is False
        assert env["error"]["code"] == "VALIDATION_INVALID_VALUE"

    @pytest.mark.asyncio
    async def test_too_short_error(self, test_conn: sqlite3.Connection):
        env = await context_compress(test_conn, text="Hi")
        assert env["ok"] is False
        assert env["error"]["code"] == "VALIDATION_INVALID_VALUE"
        assert env["error"]["retryable"] is False

    @pytest.mark.asyncio
    async def test_too_long_error(self, test_conn: sqlite3.Connection):
        # Generate text exceeding max length
        long_text = "word " * 25_000  # ~125,000 chars
        env = await context_compress(test_conn, text=long_text)
        assert env["ok"] is False
        assert env["error"]["code"] == "VALIDATION_INVALID_VALUE"

    @pytest.mark.asyncio
    async def test_idempotency(self, test_conn: sqlite3.Connection):
        key = "compress-idem-1"
        env1 = await context_compress(
            test_conn,
            text="I think this is basically a really good test of the system.",
            idempotency_key=key,
        )
        env2 = await context_compress(
            test_conn,
            text="Completely different text that should not be processed.",
            idempotency_key=key,
        )
        # Second call should return cached result from first call
        assert env1["data"] == env2["data"]

    @pytest.mark.asyncio
    async def test_compression_reduces_tokens(self, test_conn: sqlite3.Connection):
        verbose = (
            "Sure! I'd be happy to help you with this. I think this is basically "
            "a really good approach that actually works very well in practice. "
            "Perhaps you should definitely consider using it. In order to get started, "
            "you just need to follow these steps. Due to the fact that it's simple, "
            "it should be easy to understand."
        )
        env = await context_compress(test_conn, text=verbose)
        assert env["ok"] is True
        data = env["data"]
        assert data["compressed_tokens"] <= data["original_tokens"]
        assert data["savings_pct"] >= 0

    @pytest.mark.asyncio
    async def test_with_sample_fixtures(self, test_conn: sqlite3.Connection):
        """Run compression on all fixture samples and verify basic invariants."""
        fixture_path = Path(__file__).parent / "fixtures" / "compress_samples.json"
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")

        samples = json.loads(fixture_path.read_text())
        for sample in samples:
            env = await context_compress(test_conn, text=sample["input"])
            assert env["ok"] is True, f"Failed for sample: {sample['name']}"
            data = env["data"]

            # Verify preserved content is still present
            for preserved in sample.get("expect_preserved", []):
                assert preserved in data["compressed_text"], (
                    f"Sample '{sample['name']}': expected '{preserved}' to be preserved"
                )
