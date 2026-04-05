"""Tests for config modules (pricing, settings)."""

from __future__ import annotations

from pathlib import Path

from ensemble_mcp.config.pricing import (
    FALLBACK_MODEL,
    MODEL_PRICING,
    PRICING_VERSION,
    ModelPricing,
    calculate_cost,
    get_pricing,
)
from ensemble_mcp.config.settings import Settings, load_settings


# ── Pricing ───────────────────────────────────────────────────────


class TestPricing:
    def test_pricing_version_is_string(self):
        assert isinstance(PRICING_VERSION, str)

    def test_all_models_have_pricing(self):
        expected_models = {
            "claude-opus-4",
            "claude-sonnet-4",
            "claude-haiku-3.5",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-5-mini",
            "o1",
        }
        assert expected_models == set(MODEL_PRICING.keys())

    def test_model_pricing_fields(self):
        for _name, pricing in MODEL_PRICING.items():
            assert isinstance(pricing, ModelPricing)
            assert pricing.input >= 0
            assert pricing.cached_input >= 0
            assert pricing.output >= 0

    def test_get_pricing_known_model(self):
        pricing, is_fallback = get_pricing("claude-sonnet-4")
        assert is_fallback is False
        assert pricing.input == 3.0
        assert pricing.output == 15.0

    def test_get_pricing_unknown_model_falls_back(self):
        pricing, is_fallback = get_pricing("nonexistent-model")
        assert is_fallback is True
        assert pricing == MODEL_PRICING[FALLBACK_MODEL]

    def test_calculate_cost_basic(self):
        cost, unknown = calculate_cost(
            input_tokens=1_000_000,
            output_tokens=500_000,
            model="claude-sonnet-4",
        )
        assert unknown is False
        # 1M input * $3/M + 500K output * $15/M = $3 + $7.50 = $10.50
        assert abs(cost - 10.5) < 0.01

    def test_calculate_cost_with_cache(self):
        cost, unknown = calculate_cost(
            input_tokens=1_000_000,
            output_tokens=0,
            cached_tokens=500_000,
            model="claude-sonnet-4",
        )
        assert unknown is False
        # billable_input = 1M - 500K = 500K
        # 500K input * $3/M = $1.50
        # 500K cached * $0.30/M = $0.15
        # total = $1.65
        assert abs(cost - 1.65) < 0.01

    def test_calculate_cost_unknown_model(self):
        cost, unknown = calculate_cost(
            input_tokens=0,
            output_tokens=0,
            model="mystery-model",
        )
        assert unknown is True
        assert cost == 0.0

    def test_calculate_cost_zero_tokens(self):
        cost, _ = calculate_cost(
            input_tokens=0,
            output_tokens=0,
            model="claude-sonnet-4",
        )
        assert cost == 0.0


# ── Settings ──────────────────────────────────────────────────────


class TestSettings:
    def test_default_settings(self):
        s = Settings()
        assert s.max_patterns == 10_000
        assert s.default_top_k == 3
        assert isinstance(s.db_path, Path)

    def test_load_settings_defaults(self):
        s = load_settings()
        assert s.max_patterns == 10_000
        assert s.source_map["max_patterns"] == "default"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("ENSEMBLE_MCP_MAX_PATTERNS", "5000")
        s = load_settings()
        assert s.max_patterns == 5000
        assert s.source_map["max_patterns"] == "env"

    def test_env_override_float(self, monkeypatch):
        monkeypatch.setenv("ENSEMBLE_MCP_DRIFT_THRESHOLD_ALIGNED", "0.5")
        s = load_settings()
        assert s.drift_threshold_aligned == 0.5

    def test_env_override_path(self, monkeypatch):
        monkeypatch.setenv("ENSEMBLE_MCP_DB_PATH", "/tmp/custom.db")
        s = load_settings()
        assert s.db_path == Path("/tmp/custom.db")

    def test_invalid_env_skipped(self, monkeypatch):
        monkeypatch.setenv("ENSEMBLE_MCP_MAX_PATTERNS", "not_a_number")
        s = load_settings()
        assert s.max_patterns == 10_000  # unchanged from default

    def test_source_map_populated(self):
        s = load_settings()
        assert len(s.source_map) > 0
        for key in ("max_patterns", "default_top_k", "db_path"):
            assert key in s.source_map
