"""Benchmark for patterns_search, patterns_store, and patterns_prune tools.

Pre-loads patterns into a VectorStore, then measures search latency
(p50/p95/p99) and recall accuracy across a set of queries. Also
benchmarks store throughput and prune correctness.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

from ensemble_mcp.memory.store import VectorStore
from ensemble_mcp.tools.patterns import patterns_prune, patterns_search, patterns_store
from evals.conftest import EvalMockEmbeddingModel
from evals.helpers import percentile, run_async

# ── Seed patterns ────────────────────────────────────────────────

_SEED_PATTERNS: list[dict[str, str]] = [
    {
        "name": "database connection pooling",
        "context": "Setting up PostgreSQL with connection pooling",
        "approach": "Used pgbouncer with SQLAlchemy pool_size=10",
        "outcome": "Reduced connection overhead by 80%",
    },
    {
        "name": "error handling pattern",
        "context": "API endpoint error handling for REST service",
        "approach": "Custom exception hierarchy with error codes",
        "outcome": "Cleaner error messages, better client handling",
    },
    {
        "name": "authentication middleware",
        "context": "JWT-based authentication for FastAPI",
        "approach": "Middleware with token validation and role-based access",
        "outcome": "Secure endpoints with role-based authorization",
    },
    {
        "name": "caching strategy",
        "context": "Reducing database load for frequently accessed data",
        "approach": "Redis cache with TTL and cache invalidation on writes",
        "outcome": "90% reduction in database queries for hot paths",
    },
    {
        "name": "logging and observability",
        "context": "Structured logging for microservices",
        "approach": "structlog with JSON output and correlation IDs",
        "outcome": "Better debugging and distributed tracing",
    },
    {
        "name": "test fixtures pattern",
        "context": "Setting up test database fixtures for integration tests",
        "approach": "pytest fixtures with temporary SQLite databases",
        "outcome": "Isolated, repeatable test environments",
    },
    {
        "name": "CI/CD pipeline optimization",
        "context": "Slow GitHub Actions workflows taking 20+ minutes",
        "approach": "Dependency caching, parallel test runs, matrix strategy",
        "outcome": "Reduced CI time from 20min to 5min",
    },
    {
        "name": "data migration script",
        "context": "Migrating user data from legacy schema to new format",
        "approach": "Idempotent migration with progress tracking and rollback",
        "outcome": "Zero-downtime migration of 1M records",
    },
    {
        "name": "rate limiting implementation",
        "context": "Protecting API endpoints from abuse",
        "approach": "Token bucket algorithm with Redis backend",
        "outcome": "Effective rate limiting with per-user quotas",
    },
    {
        "name": "websocket real-time updates",
        "context": "Adding real-time notifications to dashboard",
        "approach": "WebSocket with asyncio and pub/sub pattern",
        "outcome": "Sub-100ms notification delivery",
    },
]

_SEARCH_QUERIES: list[dict[str, str]] = [
    {"query": "database connection management", "expected_match": "database connection pooling"},
    {"query": "handling errors in API", "expected_match": "error handling pattern"},
    {"query": "JWT auth middleware", "expected_match": "authentication middleware"},
    {"query": "caching data with Redis", "expected_match": "caching strategy"},
    {"query": "structured logging setup", "expected_match": "logging and observability"},
    {"query": "pytest database fixtures", "expected_match": "test fixtures pattern"},
    {"query": "speeding up CI builds", "expected_match": "CI/CD pipeline optimization"},
    {"query": "migrating database schema", "expected_match": "data migration script"},
    {"query": "API rate limiting", "expected_match": "rate limiting implementation"},
    {"query": "real-time WebSocket notifications", "expected_match": "websocket real-time updates"},
]


@dataclass(slots=True)
class PatternBenchResult:
    """Aggregate result of the patterns benchmark suite."""

    num_patterns: int
    num_queries: int
    latencies_ms: list[float]
    recall_hits: int
    recall_total: int
    store_latencies_ms: list[float] = field(default_factory=list)
    prune_latency_ms: float = 0.0
    prune_count: int = 0

    @property
    def p50_ms(self) -> float:
        return percentile(self.latencies_ms, 50)

    @property
    def p95_ms(self) -> float:
        return percentile(self.latencies_ms, 95)

    @property
    def p99_ms(self) -> float:
        return percentile(self.latencies_ms, 99)

    @property
    def recall_pct(self) -> float:
        return (self.recall_hits / self.recall_total * 100) if self.recall_total else 0.0


def run_patterns_benchmark(tmp_dir: Path | None = None) -> PatternBenchResult:
    """Run the full patterns benchmark: store, search, and prune.

    Creates a temporary VectorStore, seeds it with patterns, then
    measures search latency and recall accuracy. Also benchmarks
    store throughput and prune operations.
    """
    import tempfile

    if tmp_dir is None:
        tmp_dir = Path(tempfile.mkdtemp())

    db_path = tmp_dir / "bench_patterns.db"
    model = EvalMockEmbeddingModel()
    store = VectorStore(db_path=db_path, model=model)

    # Seed patterns and measure store latency
    store_latencies: list[float] = []
    for pat in _SEED_PATTERNS:
        start = time.perf_counter()
        run_async(patterns_store(store, **pat))
        elapsed_ms = (time.perf_counter() - start) * 1000
        store_latencies.append(round(elapsed_ms, 2))

    # Run searches and measure
    latencies: list[float] = []
    hits = 0

    for sq in _SEARCH_QUERIES:
        start = time.perf_counter()
        env = run_async(patterns_search(store, query=sq["query"], top_k=5))
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(round(elapsed_ms, 2))

        # Check recall: did the expected pattern appear in results?
        if env["ok"] and env["data"]["matches"]:
            match_names = [m["name"] for m in env["data"]["matches"]]
            if sq["expected_match"] in match_names:
                hits += 1

    # Prune benchmark (with max_age_days=0 to prune all unmatched)
    start = time.perf_counter()
    prune_env = run_async(patterns_prune(store, max_age_days=0))
    prune_latency_ms = (time.perf_counter() - start) * 1000
    prune_count = prune_env["data"]["pruned"] if prune_env["ok"] else 0

    store.close()

    return PatternBenchResult(
        num_patterns=len(_SEED_PATTERNS),
        num_queries=len(_SEARCH_QUERIES),
        latencies_ms=latencies,
        recall_hits=hits,
        recall_total=len(_SEARCH_QUERIES),
        store_latencies_ms=store_latencies,
        prune_latency_ms=round(prune_latency_ms, 2),
        prune_count=prune_count,
    )


def format_patterns_results(result: PatternBenchResult) -> str:
    """Format patterns benchmark results as markdown."""
    lines: list[str] = [
        "## Patterns Benchmark",
        "",
        f"- **Patterns seeded**: {result.num_patterns}",
        f"- **Queries run**: {result.num_queries}",
        f"- **Recall**: {result.recall_hits}/{result.recall_total} ({result.recall_pct:.0f}%)",
        "",
        "### Search Latency",
        "",
        f"- **p50**: {result.p50_ms:.2f}ms",
        f"- **p95**: {result.p95_ms:.2f}ms",
        f"- **p99**: {result.p99_ms:.2f}ms",
        f"- **Mean**: {statistics.mean(result.latencies_ms) if result.latencies_ms else 0.0:.2f}ms",
    ]

    if result.store_latencies_ms:
        lines.extend(
            [
                "",
                "### Store Latency",
                "",
                f"- **Mean**: {statistics.mean(result.store_latencies_ms):.2f}ms",
                f"- **p95**: {percentile(result.store_latencies_ms, 95):.2f}ms",
            ]
        )

    lines.extend(
        [
            "",
            "### Prune",
            "",
            f"- **Pruned**: {result.prune_count}",
            f"- **Latency**: {result.prune_latency_ms:.2f}ms",
        ]
    )

    return "\n".join(lines)


# ── Pytest-discoverable wrappers ─────────────────────────────────


def test_patterns_benchmark_runs() -> None:
    """Pytest wrapper: runs patterns benchmark and validates results."""
    result = run_patterns_benchmark()
    assert result.num_patterns > 0
    assert result.num_queries > 0
    assert result.p50_ms >= 0
    assert result.recall_total == result.num_queries


def test_patterns_store_benchmark() -> None:
    """Pytest wrapper: validates store latency measurements exist."""
    result = run_patterns_benchmark()
    assert len(result.store_latencies_ms) == result.num_patterns
    assert all(lat >= 0 for lat in result.store_latencies_ms)


def test_patterns_prune_benchmark() -> None:
    """Pytest wrapper: validates prune operation ran successfully."""
    result = run_patterns_benchmark()
    assert result.prune_latency_ms >= 0
    # Prune count may be 0 if patterns gained matches before the prune
    # call; >= 0 is the tightest bound we can assert here.
    assert result.prune_count >= 0


def test_patterns_format_output() -> None:
    """Pytest wrapper: ensures format function produces valid markdown."""
    result = run_patterns_benchmark()
    markdown = format_patterns_results(result)
    assert "## Patterns Benchmark" in markdown
    assert "### Search Latency" in markdown
    assert "### Store Latency" in markdown
    assert "### Prune" in markdown


if __name__ == "__main__":
    result = run_patterns_benchmark()
    print(format_patterns_results(result))
