"""Tests for routing tool (model_recommend)."""

from __future__ import annotations

import sqlite3

import pytest

from ensemble_mcp.tools.routing import model_recommend


class TestModelRecommend:
    @pytest.mark.asyncio
    async def test_signal_always_cheapest(self, test_conn: sqlite3.Connection):
        for classification in ("trivial", "simple", "standard", "complex"):
            env = await model_recommend(
                test_conn,
                agent="signal",
                task_classification=classification,
            )
            assert env["ok"] is True
            assert env["data"]["tier"] == "cheapest"

    @pytest.mark.asyncio
    async def test_craft_trivial_is_mid(self, test_conn: sqlite3.Connection):
        env = await model_recommend(
            test_conn,
            agent="craft",
            task_classification="trivial",
        )
        assert env["ok"] is True
        assert env["data"]["tier"] == "mid"

    @pytest.mark.asyncio
    async def test_craft_complex_is_best(self, test_conn: sqlite3.Connection):
        env = await model_recommend(
            test_conn,
            agent="craft",
            task_classification="complex",
        )
        assert env["ok"] is True
        assert env["data"]["tier"] == "best"

    @pytest.mark.asyncio
    async def test_trace_simple_is_best(self, test_conn: sqlite3.Connection):
        env = await model_recommend(
            test_conn,
            agent="trace",
            task_classification="simple",
        )
        assert env["ok"] is True
        assert env["data"]["tier"] == "best"

    @pytest.mark.asyncio
    async def test_unknown_agent_defaults_to_mid(self, test_conn: sqlite3.Connection):
        env = await model_recommend(
            test_conn,
            agent="unknown_agent",
            task_classification="standard",
        )
        assert env["ok"] is True
        assert env["data"]["tier"] == "mid"

    @pytest.mark.asyncio
    async def test_case_insensitive(self, test_conn: sqlite3.Connection):
        env = await model_recommend(
            test_conn,
            agent="SIGNAL",
            task_classification="COMPLEX",
        )
        assert env["ok"] is True
        assert env["data"]["tier"] == "cheapest"

    @pytest.mark.asyncio
    async def test_response_structure(self, test_conn: sqlite3.Connection):
        env = await model_recommend(
            test_conn,
            agent="ensemble",
            task_classification="standard",
        )
        assert env["ok"] is True
        data = env["data"]
        assert "tier" in data
        assert "reason" in data
        assert "agent" in data
        assert "classification" in data
        assert isinstance(data["reason"], str)
        assert len(data["reason"]) > 0

    @pytest.mark.asyncio
    async def test_idempotency(self, test_conn: sqlite3.Connection):
        key = "routing-idem-1"
        env1 = await model_recommend(
            test_conn,
            agent="craft",
            task_classification="complex",
            idempotency_key=key,
        )
        env2 = await model_recommend(
            test_conn,
            agent="signal",
            task_classification="trivial",
            idempotency_key=key,
        )
        assert env1["data"] == env2["data"]

    @pytest.mark.asyncio
    async def test_all_agents_covered(self, test_conn: sqlite3.Connection):
        agents = ["signal", "proof", "lens", "craft", "scope", "ensemble", "trace"]
        for agent in agents:
            env = await model_recommend(
                test_conn,
                agent=agent,
                task_classification="standard",
            )
            assert env["ok"] is True
            assert env["data"]["tier"] in ("best", "mid", "cheapest")
