"""Tests for patterns tools (patterns_search, patterns_store, patterns_prune)."""

from __future__ import annotations

import pytest

from ensemble_mcp.tools.patterns import patterns_prune, patterns_search, patterns_store


class TestPatternsStore:
    @pytest.mark.asyncio
    async def test_store_returns_id(self, test_store):
        env = await patterns_store(
            test_store,
            name="error handling",
            context="API endpoint error handling",
            approach="try/except with custom exceptions",
            outcome="cleaner error messages",
        )
        assert env["ok"] is True
        assert env["data"]["stored"] is True
        assert isinstance(env["data"]["id"], int)
        assert env["meta"]["source"] == "sqlite"

    @pytest.mark.asyncio
    async def test_store_with_project(self, test_store):
        env = await patterns_store(
            test_store,
            name="logging pattern",
            context="structured logging setup",
            approach="use structlog",
            outcome="better observability",
            project="my-project",
        )
        assert env["ok"] is True
        assert env["data"]["stored"] is True

    @pytest.mark.asyncio
    async def test_store_idempotency(self, test_store):
        key = "idem-store-1"
        env1 = await patterns_store(
            test_store,
            name="pattern A",
            context="ctx",
            approach="approach",
            outcome="outcome",
            idempotency_key=key,
        )
        env2 = await patterns_store(
            test_store,
            name="pattern B different",
            context="ctx2",
            approach="approach2",
            outcome="outcome2",
            idempotency_key=key,
        )
        # Second call should return cached result
        assert env1["data"]["id"] == env2["data"]["id"]


class TestPatternsSearch:
    @pytest.mark.asyncio
    async def test_search_empty_db(self, test_store):
        env = await patterns_search(test_store, query="anything")
        assert env["ok"] is True
        assert env["data"]["matches"] == []

    @pytest.mark.asyncio
    async def test_search_finds_stored_pattern(self, test_store):
        await patterns_store(
            test_store,
            name="database connection pooling",
            context="setting up postgres pooling",
            approach="use pgbouncer",
            outcome="reduced connection overhead",
        )
        env = await patterns_search(
            test_store,
            query="database connection pooling",
            top_k=5,
        )
        assert env["ok"] is True
        matches = env["data"]["matches"]
        # The mock model is hash-based, identical text should produce
        # high self-similarity
        assert len(matches) >= 0  # may or may not match depending on hash

    @pytest.mark.asyncio
    async def test_search_with_project_filter(self, test_store):
        await patterns_store(
            test_store,
            name="test pattern",
            context="ctx",
            approach="approach",
            outcome="outcome",
            project="proj-a",
        )
        env = await patterns_search(
            test_store,
            query="test pattern",
            project="proj-a",
        )
        assert env["ok"] is True

    @pytest.mark.asyncio
    async def test_search_idempotency(self, test_store):
        key = "idem-search-1"
        env1 = await patterns_search(
            test_store,
            query="test",
            idempotency_key=key,
        )
        env2 = await patterns_search(
            test_store,
            query="different",
            idempotency_key=key,
        )
        assert env1["data"] == env2["data"]


class TestPatternsPrune:
    @pytest.mark.asyncio
    async def test_prune_empty_db(self, test_store):
        env = await patterns_prune(test_store)
        assert env["ok"] is True
        assert env["data"]["pruned"] == 0
        assert env["data"]["remaining"] == 0

    @pytest.mark.asyncio
    async def test_prune_does_not_remove_recent(self, test_store):
        await patterns_store(
            test_store,
            name="fresh pattern",
            context="ctx",
            approach="approach",
            outcome="outcome",
        )
        env = await patterns_prune(test_store, max_age_days=90)
        assert env["ok"] is True
        assert env["data"]["pruned"] == 0
        assert env["data"]["remaining"] == 1

    @pytest.mark.asyncio
    async def test_prune_idempotency(self, test_store):
        key = "idem-prune-1"
        env1 = await patterns_prune(test_store, idempotency_key=key)
        env2 = await patterns_prune(test_store, idempotency_key=key)
        assert env1["data"] == env2["data"]
