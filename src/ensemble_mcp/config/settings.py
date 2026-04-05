"""Configuration management.

Layered config with deterministic merge order:
1. Package defaults (defaults.py)
2. Global user config (~/.config/ensemble-mcp/config.toml)
3. Project config (.ensemble-mcp.toml)
4. Runtime overrides (CLI/env)

Scalar values override; maps merge shallowly by key; lists replace.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .defaults import (
    CACHE_DIR,
    CLUSTER_SIMILARITY_THRESHOLD,
    DB_PATH,
    DEFAULT_MIN_CLUSTER_SIZE,
    DEFAULT_MIN_SCORE,
    DEFAULT_PRUNE_MAX_AGE_DAYS,
    DEFAULT_STALE_THRESHOLD_DAYS,
    DEFAULT_TOP_K,
    DRIFT_THRESHOLD_ALIGNED,
    DRIFT_THRESHOLD_MINOR,
    GLOBAL_CONFIG_PATH,
    IDEMPOTENCY_KEY_TTL_HOURS,
    MAX_PATTERNS,
    MODEL_DIR,
    PROJECT_CONFIG_FILENAME,
)


@dataclass(slots=True)
class Settings:
    """Resolved configuration for the ensemble-mcp server."""

    # Paths
    cache_dir: Path = CACHE_DIR
    db_path: Path = DB_PATH
    model_dir: Path = MODEL_DIR

    # Patterns
    max_patterns: int = MAX_PATTERNS
    default_top_k: int = DEFAULT_TOP_K
    default_min_score: float = DEFAULT_MIN_SCORE
    default_prune_max_age_days: int = DEFAULT_PRUNE_MAX_AGE_DAYS

    # Drift
    drift_threshold_aligned: float = DRIFT_THRESHOLD_ALIGNED
    drift_threshold_minor: float = DRIFT_THRESHOLD_MINOR

    # Skills
    cluster_similarity_threshold: float = CLUSTER_SIMILARITY_THRESHOLD
    default_min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE
    default_stale_threshold_days: int = DEFAULT_STALE_THRESHOLD_DAYS

    # Idempotency
    idempotency_key_ttl_hours: int = IDEMPOTENCY_KEY_TTL_HOURS

    # Debug: which source each value came from
    source_map: dict[str, str] = field(default_factory=dict)


def _load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file, returning empty dict on any failure."""
    if not path.is_file():
        return {}
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:  # pragma: no cover
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _apply_overrides(
    settings: Settings,
    data: dict[str, Any],
    source_label: str,
) -> None:
    """Apply a flat or nested dict of overrides to *settings*.

    Scalars override, maps merge shallowly, lists replace.
    """
    field_names = {f.name for f in settings.__dataclass_fields__.values()}  # type: ignore[attr-defined]

    for key, value in data.items():
        if key in field_names and key != "source_map":
            current = getattr(settings, key)
            if isinstance(current, dict) and isinstance(value, dict):
                # Shallow merge for maps
                current.update(value)
            else:
                # Scalar or list: replace
                if isinstance(current, Path) and isinstance(value, str):
                    value = Path(value)
                setattr(settings, key, value)
            settings.source_map[key] = source_label


def _apply_env_overrides(settings: Settings) -> None:
    """Apply ENSEMBLE_MCP_* environment variables."""
    prefix = "ENSEMBLE_MCP_"
    field_names = {f.name for f in settings.__dataclass_fields__.values()}  # type: ignore[attr-defined]

    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        field_name = key[len(prefix) :].lower()
        if field_name not in field_names or field_name == "source_map":
            continue

        current = getattr(settings, field_name)
        try:
            if isinstance(current, bool):
                converted: Any = value.lower() in ("1", "true", "yes")
            elif isinstance(current, int):
                converted = int(value)
            elif isinstance(current, float):
                converted = float(value)
            elif isinstance(current, Path):
                converted = Path(value)
            else:
                converted = value
            setattr(settings, field_name, converted)
            settings.source_map[field_name] = "env"
        except (ValueError, TypeError):
            continue  # skip invalid env values silently


def load_settings(project_dir: Path | None = None) -> Settings:
    """Build settings by layering all config sources.

    Precedence (low → high):
    1. Package defaults (the ``Settings`` dataclass defaults)
    2. Global user config (``~/.config/ensemble-mcp/config.toml``)
    3. Project config (``.ensemble-mcp.toml`` in *project_dir*)
    4. Environment variables (``ENSEMBLE_MCP_*``)
    """
    settings = Settings()

    # Mark all defaults
    for f in settings.__dataclass_fields__:  # type: ignore[attr-defined]
        if f != "source_map":
            settings.source_map[f] = "default"

    # Layer 2: global user config
    global_data = _load_toml(GLOBAL_CONFIG_PATH)
    if global_data:
        _apply_overrides(settings, global_data, "global_config")

    # Layer 3: project config
    if project_dir is not None:
        project_config = project_dir / PROJECT_CONFIG_FILENAME
        project_data = _load_toml(project_config)
        if project_data:
            _apply_overrides(settings, project_data, "project_config")

    # Layer 4: environment variables
    _apply_env_overrides(settings)

    return settings
