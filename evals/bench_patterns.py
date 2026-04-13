"""Benchmark for patterns_search tool.

Pre-loads patterns into a VectorStore, then measures search latency
(p50/p95/p99) and recall accuracy across a set of queries.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from ensemble_mcp.memory.embeddings import EmbeddingModel
from ensemble_mcp.memory.store import VectorStore
from ensemble_mcp.tools.patterns import patterns_search, patterns_store

# ── Mock model for benchmarks ────────────────────────────────────


class _BenchEmbeddingModel(EmbeddingModel):
    """Deterministic embedding model for pattern benchmarks."""

    def __init__(self) -> None:
        self._model_dir = Path("/dev/null")
        self._session = MagicMock()
        self._tokenizer = MagicMock()

    def embed(self, text: str) -> np.ndarray:
        rng = np.random.RandomState(hash(text) % (2**31))
        vec = rng.randn(384).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        return [self.embed(t) for t in texts]

    def _load(self) -> None:
        pass

    def _ensure_model(self) -> None:
        pass


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
    """Aggregate result of the patterns_search benchmark."""

    num_patterns: int
    num_queries: int
    latencies_ms: list[float]
    recall_hits: int
    recall_total: int

    @property
    def p50_ms(self) -> float:
        return _percentile(self.latencies_ms, 50)

    @property
    def p95_ms(self) -> float:
        return _percentile(self.latencies_ms, 95)

    @property
    def p99_ms(self) -> float:
        return _percentile(self.latencies_ms, 99)

    @property
    def recall_pct(self) -> float:
        return (self.recall_hits / self.recall_total * 100) if self.recall_total else 0.0


def _percentile(data: list[float], p: int) -> float:
    """Compute the p-th percentile of a list of floats."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[-1]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


def run_patterns_benchmark(tmp_dir: Path | None = None) -> PatternBenchResult:
    """Run the patterns_search benchmark.

    Creates a temporary VectorStore, seeds it with patterns, then
    measures search latency and recall accuracy.
    """
    import tempfile

    if tmp_dir is None:
        tmp_dir = Path(tempfile.mkdtemp())

    db_path = tmp_dir / "bench_patterns.db"
    model = _BenchEmbeddingModel()
    store = VectorStore(db_path=db_path, model=model)

    # Seed patterns
    for pat in _SEED_PATTERNS:
        asyncio.run(patterns_store(store, **pat))

    # Run searches and measure
    latencies: list[float] = []
    hits = 0

    for sq in _SEARCH_QUERIES:
        start = time.perf_counter()
        env = asyncio.run(patterns_search(store, query=sq["query"], top_k=5))
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(round(elapsed_ms, 2))

        # Check recall: did the expected pattern appear in results?
        if env["ok"] and env["data"]["matches"]:
            match_names = [m["name"] for m in env["data"]["matches"]]
            if sq["expected_match"] in match_names:
                hits += 1

    store.close()

    return PatternBenchResult(
        num_patterns=len(_SEED_PATTERNS),
        num_queries=len(_SEARCH_QUERIES),
        latencies_ms=latencies,
        recall_hits=hits,
        recall_total=len(_SEARCH_QUERIES),
    )


def format_patterns_results(result: PatternBenchResult) -> str:
    """Format patterns benchmark results as markdown."""
    lines: list[str] = [
        "## Patterns Search Benchmark",
        "",
        f"- **Patterns seeded**: {result.num_patterns}",
        f"- **Queries run**: {result.num_queries}",
        f"- **Recall**: {result.recall_hits}/{result.recall_total} ({result.recall_pct:.0f}%)",
        "",
        "### Latency",
        "",
        f"- **p50**: {result.p50_ms:.2f}ms",
        f"- **p95**: {result.p95_ms:.2f}ms",
        f"- **p99**: {result.p99_ms:.2f}ms",
        f"- **Mean**: {statistics.mean(result.latencies_ms):.2f}ms",
    ]

    return "\n".join(lines)


if __name__ == "__main__":
    result = run_patterns_benchmark()
    print(format_patterns_results(result))
