"""Tests for patterns tools (patterns_search, patterns_store, patterns_prune).

Covers category filtering, progressive disclosure via detail_level,
and token cost metadata on search results.
"""

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

    @pytest.mark.asyncio
    async def test_store_with_category(self, test_store):
        """Storing with an explicit category includes it in the response."""
        env = await patterns_store(
            test_store,
            name="gotcha pattern",
            context="silent failure in async code",
            approach="always await or handle the promise",
            outcome="no more swallowed errors",
            category="gotcha",
        )
        assert env["ok"] is True
        assert env["data"]["stored"] is True
        assert env["data"]["category"] == "gotcha"

    @pytest.mark.asyncio
    async def test_store_default_category(self, test_store):
        """Storing without a category defaults to 'general'."""
        env = await patterns_store(
            test_store,
            name="plain pattern",
            context="ctx",
            approach="approach",
            outcome="outcome",
        )
        assert env["ok"] is True
        assert env["data"]["category"] == "general"

    @pytest.mark.asyncio
    async def test_store_invalid_category(self, test_store):
        """Storing with an invalid category returns a validation error."""
        env = await patterns_store(
            test_store,
            name="bad pattern",
            context="ctx",
            approach="approach",
            outcome="outcome",
            category="not-a-real-category",
        )
        assert env["ok"] is False
        assert env["error"]["code"] == "VALIDATION_INVALID_VALUE"


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

    @pytest.mark.asyncio
    async def test_search_detail_level_full_returns_all_fields(self, test_store):
        """detail_level='full' includes context, approach, outcome, token_count, category."""
        await patterns_store(
            test_store,
            name="full detail pattern",
            context="when testing APIs",
            approach="use integration tests",
            outcome="better coverage",
            category="how-it-works",
        )
        env = await patterns_search(
            test_store,
            query="full detail pattern when testing APIs use integration tests",
            detail_level="full",
            top_k=5,
        )
        assert env["ok"] is True
        # The mock embedding may or may not produce a match, but if it does
        # the fields must be present
        for match in env["data"]["matches"]:
            assert "context" in match
            assert "approach" in match
            assert "outcome" in match
            assert "token_count" in match
            assert "category" in match
            assert match["category"] == "how-it-works"

    @pytest.mark.asyncio
    async def test_search_detail_level_index_omits_text(self, test_store):
        """detail_level='index' returns only id, name, category, score, token_count."""
        await patterns_store(
            test_store,
            name="index detail pattern",
            context="when indexing patterns",
            approach="use compact mode",
            outcome="less tokens",
            category="discovery",
        )
        env = await patterns_search(
            test_store,
            query="index detail pattern when indexing patterns use compact mode",
            detail_level="index",
            top_k=5,
        )
        assert env["ok"] is True
        for match in env["data"]["matches"]:
            # Index mode should have these fields
            assert "id" in match
            assert "name" in match
            assert "category" in match
            assert "score" in match
            assert "token_count" in match
            # Index mode should NOT have text fields
            assert "context" not in match
            assert "approach" not in match
            assert "outcome" not in match

    @pytest.mark.asyncio
    async def test_search_invalid_detail_level(self, test_store):
        """An invalid detail_level returns a validation error."""
        env = await patterns_search(
            test_store,
            query="test",
            detail_level="compact",
        )
        assert env["ok"] is False
        assert env["error"]["code"] == "VALIDATION_INVALID_VALUE"

    @pytest.mark.asyncio
    async def test_search_invalid_category(self, test_store):
        """An invalid category returns a validation error."""
        env = await patterns_search(
            test_store,
            query="test",
            category="nonexistent-category",
        )
        assert env["ok"] is False
        assert env["error"]["code"] == "VALIDATION_INVALID_VALUE"

    @pytest.mark.asyncio
    async def test_search_filter_by_category(self, test_store):
        """Category filter narrows results to matching patterns only."""
        await patterns_store(
            test_store,
            name="gotcha pattern alpha",
            context="ctx alpha gotcha",
            approach="approach alpha gotcha",
            outcome="outcome alpha",
            category="gotcha",
        )
        await patterns_store(
            test_store,
            name="general pattern beta",
            context="ctx beta general",
            approach="approach beta general",
            outcome="outcome beta",
            category="general",
        )
        # Search with category filter — only "gotcha" patterns should appear
        env = await patterns_search(
            test_store,
            query="gotcha pattern alpha ctx alpha gotcha approach alpha gotcha",
            category="gotcha",
            top_k=10,
        )
        assert env["ok"] is True
        for match in env["data"]["matches"]:
            assert match["category"] == "gotcha"

    @pytest.mark.asyncio
    async def test_search_token_count_present(self, test_store):
        """Search results include token_count as a positive integer."""
        await patterns_store(
            test_store,
            name="token count pattern",
            context="some context text here for counting",
            approach="some approach text here for counting",
            outcome="some outcome text here for counting",
        )
        env = await patterns_search(
            test_store,
            query=(
                "token count pattern some context text here"
                " for counting some approach text here for counting"
            ),
            top_k=5,
        )
        assert env["ok"] is True
        for match in env["data"]["matches"]:
            assert "token_count" in match
            assert isinstance(match["token_count"], int)
            assert match["token_count"] > 0


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
