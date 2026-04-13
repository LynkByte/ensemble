"""Benchmark for model_recommend tool.

Tests all known agent/classification combinations and unknown combos
to verify routing correctness and measure latency.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from pathlib import Path

from ensemble_mcp.tools.routing import _ROUTING_RULES, model_recommend
from evals.helpers import make_eval_db, percentile, run_async

# ── Known combos from routing rules ──────────────────────────────

_KNOWN_AGENTS = sorted({agent for agent, _ in _ROUTING_RULES})
_KNOWN_CLASSIFICATIONS = ["trivial", "simple", "standard", "complex"]

# Unknown combos to test fallback behavior
_UNKNOWN_COMBOS: list[dict[str, str]] = [
    {"agent": "unknown_agent", "task_classification": "simple"},
    {"agent": "craft", "task_classification": "extreme"},
    {"agent": "custom_bot", "task_classification": "mega"},
]


@dataclass(slots=True)
class RoutingBenchResult:
    """Result of the routing benchmark."""

    num_queries: int
    latencies_ms: list[float]
    correct_count: int
    total_count: int

    @property
    def accuracy_pct(self) -> float:
        return (self.correct_count / self.total_count * 100) if self.total_count else 0.0

    @property
    def p50_ms(self) -> float:
        return percentile(self.latencies_ms, 50)

    @property
    def p95_ms(self) -> float:
        return percentile(self.latencies_ms, 95)

    @property
    def p99_ms(self) -> float:
        return percentile(self.latencies_ms, 99)


def run_routing_benchmark(tmp_dir: Path | None = None) -> RoutingBenchResult:
    """Run the model_recommend benchmark.

    Tests all known agent/classification combinations and verifies
    the returned tier matches the routing rules. Also tests unknown
    combos for fallback behavior (should return 'mid').
    """
    import tempfile

    if tmp_dir is None:
        tmp_dir = Path(tempfile.mkdtemp())

    conn = make_eval_db(tmp_dir)
    latencies: list[float] = []
    correct = 0
    total = 0

    # Test all known combos
    for agent in _KNOWN_AGENTS:
        for classification in _KNOWN_CLASSIFICATIONS:
            start = time.perf_counter()
            env = run_async(
                model_recommend(
                    conn,
                    agent=agent,
                    task_classification=classification,
                )
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(round(elapsed_ms, 2))

            total += 1
            expected_tier = _ROUTING_RULES.get((agent, classification), "mid")
            if env["ok"] and env["data"]["tier"] == expected_tier:
                correct += 1

    # Test unknown combos (should fall back to "mid")
    for combo in _UNKNOWN_COMBOS:
        start = time.perf_counter()
        env = run_async(
            model_recommend(
                conn,
                agent=combo["agent"],
                task_classification=combo["task_classification"],
            )
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(round(elapsed_ms, 2))

        total += 1
        if env["ok"] and env["data"]["tier"] == "mid":
            correct += 1

    conn.close()

    return RoutingBenchResult(
        num_queries=len(latencies),
        latencies_ms=latencies,
        correct_count=correct,
        total_count=total,
    )


def format_routing_results(result: RoutingBenchResult) -> str:
    """Format routing benchmark results as markdown."""
    lines: list[str] = [
        "## Model Routing Benchmark",
        "",
        f"- **Total queries**: {result.num_queries}",
        f"- **Correct**: {result.correct_count}/{result.total_count} ({result.accuracy_pct:.0f}%)",
        "",
        "### Latency",
        "",
        f"- **p50**: {result.p50_ms:.2f}ms",
        f"- **p95**: {result.p95_ms:.2f}ms",
        f"- **p99**: {result.p99_ms:.2f}ms",
        f"- **Mean**: {statistics.mean(result.latencies_ms) if result.latencies_ms else 0.0:.2f}ms",
    ]

    return "\n".join(lines)


# ── Pytest-discoverable wrappers ─────────────────────────────────


def test_routing_benchmark_runs() -> None:
    """Pytest wrapper: runs routing benchmark and validates all combos are correct."""
    result = run_routing_benchmark()
    assert result.num_queries > 0
    assert result.correct_count == result.total_count, (
        f"Routing mismatch: {result.correct_count}/{result.total_count}"
    )
    assert result.p50_ms < 100, f"p50 latency too high: {result.p50_ms}ms"


def test_routing_format_output() -> None:
    """Pytest wrapper: ensures format function produces valid markdown."""
    result = run_routing_benchmark()
    markdown = format_routing_results(result)
    assert "## Model Routing Benchmark" in markdown
    assert "### Latency" in markdown


if __name__ == "__main__":
    result = run_routing_benchmark()
    print(format_routing_results(result))
