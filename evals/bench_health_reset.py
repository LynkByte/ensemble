"""Benchmark for health and reset utility tools.

Tests the health endpoint returns correct shape and the reset
endpoint properly clears data with confirmation handling.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from ensemble_mcp.memory.store import VectorStore
from ensemble_mcp.server import _health, _reset
from evals.conftest import EvalMockEmbeddingModel
from evals.helpers import run_async


@dataclass(slots=True)
class UtilityBenchResult:
    """Result of the health/reset benchmark."""

    health_latency_ms: float
    reset_latency_ms: float
    health_ok: bool
    reset_ok: bool
    reset_no_confirm_ok: bool
    health_has_version: bool
    health_has_db_size: bool
    health_has_pattern_count: bool


def run_health_reset_benchmark(tmp_dir: Path | None = None) -> UtilityBenchResult:
    """Run the health and reset benchmark.

    Tests health returns correct shape, reset with confirm=True clears data,
    and reset with confirm=False returns an error.
    """
    import tempfile

    if tmp_dir is None:
        tmp_dir = Path(tempfile.mkdtemp())

    db_path = tmp_dir / "bench_utility.db"
    model = EvalMockEmbeddingModel()
    store = VectorStore(db_path=db_path, model=model)

    # Seed a pattern so we have data to reset
    store.store_pattern(
        name="test pattern",
        context="test context",
        approach="test approach",
        outcome="test outcome",
    )

    # Test health
    start = time.perf_counter()
    health_env = _health(store)
    health_ms = (time.perf_counter() - start) * 1000

    health_ok = health_env.get("ok", False)
    health_data = health_env.get("data", {})
    health_has_version = "version" in health_data
    health_has_db_size = "db_size_bytes" in health_data
    health_has_pattern_count = "pattern_count" in health_data

    # Test reset with confirm=False (should fail)
    reset_no_confirm_env = run_async(_reset(store, confirm=False))
    reset_no_confirm_ok = not reset_no_confirm_env.get("ok", True)

    # Test reset with confirm=True
    start = time.perf_counter()
    reset_env = run_async(_reset(store, confirm=True))
    reset_ms = (time.perf_counter() - start) * 1000

    reset_ok = reset_env.get("ok", False)

    # Verify data was actually cleared
    count_after = store.get_pattern_count()
    reset_ok = reset_ok and count_after == 0

    store.close()

    return UtilityBenchResult(
        health_latency_ms=round(health_ms, 2),
        reset_latency_ms=round(reset_ms, 2),
        health_ok=health_ok,
        reset_ok=reset_ok,
        reset_no_confirm_ok=reset_no_confirm_ok,
        health_has_version=health_has_version,
        health_has_db_size=health_has_db_size,
        health_has_pattern_count=health_has_pattern_count,
    )


def format_health_reset_results(result: UtilityBenchResult) -> str:
    """Format health/reset benchmark results as markdown."""
    lines: list[str] = [
        "## Health & Reset Benchmark",
        "",
        f"- **Health OK**: {'✓' if result.health_ok else '✗'}",
        f"- **Health has version**: {'✓' if result.health_has_version else '✗'}",
        f"- **Health has db_size**: {'✓' if result.health_has_db_size else '✗'}",
        f"- **Health has pattern_count**: {'✓' if result.health_has_pattern_count else '✗'}",
        f"- **Reset OK (confirm=True)**: {'✓' if result.reset_ok else '✗'}",
        f"- **Reset rejected (confirm=False)**: {'✓' if result.reset_no_confirm_ok else '✗'}",
        "",
        "### Latency",
        "",
        f"- **Health**: {result.health_latency_ms:.2f}ms",
        f"- **Reset**: {result.reset_latency_ms:.2f}ms",
    ]

    return "\n".join(lines)


# ── Pytest-discoverable wrappers ─────────────────────────────────


def test_health_benchmark() -> None:
    """Pytest wrapper: validates health returns correct shape."""
    result = run_health_reset_benchmark()
    assert result.health_ok, "Health check failed"
    assert result.health_has_version, "Health missing version"
    assert result.health_has_db_size, "Health missing db_size_bytes"
    assert result.health_has_pattern_count, "Health missing pattern_count"


def test_reset_with_confirm() -> None:
    """Pytest wrapper: validates reset clears data when confirmed."""
    result = run_health_reset_benchmark()
    assert result.reset_ok, "Reset with confirm=True failed"


def test_reset_without_confirm() -> None:
    """Pytest wrapper: validates reset is rejected without confirmation."""
    result = run_health_reset_benchmark()
    assert result.reset_no_confirm_ok, "Reset without confirm should be rejected"


def test_health_reset_format_output() -> None:
    """Pytest wrapper: ensures format function produces valid markdown."""
    result = run_health_reset_benchmark()
    markdown = format_health_reset_results(result)
    assert "## Health & Reset Benchmark" in markdown
    assert "### Latency" in markdown


if __name__ == "__main__":
    result = run_health_reset_benchmark()
    print(format_health_reset_results(result))
