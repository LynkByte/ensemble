"""Tests for config modules (settings, defaults)."""

from __future__ import annotations

from pathlib import Path

from ensemble_mcp.config.defaults import SERVER_VERSION
from ensemble_mcp.config.settings import Settings, load_settings

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


# ── Version ───────────────────────────────────────────────────────


class TestVersion:
    def test_server_version_is_non_empty_string(self):
        """SERVER_VERSION should be a non-empty string from importlib.metadata."""
        assert isinstance(SERVER_VERSION, str)
        assert len(SERVER_VERSION) > 0

    def test_server_version_is_semver_like(self):
        """SERVER_VERSION should look like a version string, not a dev fallback."""
        import re

        assert re.match(r"^\d+\.\d+\.\d+", SERVER_VERSION), (
            f"Unexpected version format: {SERVER_VERSION}"
        )
        assert SERVER_VERSION != "0.0.0-dev", "Should not be the dev fallback"
