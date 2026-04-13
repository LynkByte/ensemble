"""Benchmark for drift_check tool.

Runs drift detection on pairs with known ground-truth labels
and measures latency and classification accuracy.
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
from ensemble_mcp.state.idempotency import ensure_idempotency_table
from ensemble_mcp.state.locks import get_connection
from ensemble_mcp.tools.drift import drift_check


class _BenchEmbeddingModel(EmbeddingModel):
    """Deterministic embedding model for drift benchmarks."""

    def __init__(self) -> None:
        super().__init__(model_dir=Path("/dev/null"))
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


# ── Test pairs with ground-truth expectations ────────────────────

_DRIFT_PAIRS: list[dict[str, object]] = [
    {
        "task": "Add user authentication with JWT tokens",
        "changed_files": ["src/auth.py", "tests/test_auth.py"],
        "diff": "Added JWT authentication module with login, logout, and token refresh endpoints",
        "expected_verdict": "aligned",
        "description": "Closely aligned task and changes",
    },
    {
        "task": "Fix the login button CSS on the homepage",
        "changed_files": ["src/styles.css", "src/components/LoginButton.vue"],
        "diff": "Fixed login button styling and hover states on homepage",
        "expected_verdict": "aligned",
        "description": "Narrowly scoped CSS fix",
    },
    {
        "task": "Update API rate limiting",
        "changed_files": [
            "src/middleware/rate_limit.py",
            "migrations/003_add_rate_limit_table.sql",
            "src/config.py",
            "src/database/schema.py",
        ],
        "diff": "Updated rate limiting middleware, added database migration for rate limit tracking",  # noqa: E501
        "expected_verdict": "minor_drift",
        "description": "Related but includes config and migration changes",
    },
    {
        "task": "Fix typo in README",
        "changed_files": [
            "README.md",
            "src/auth.py",
            "src/database.py",
            "migrations/005_restructure.sql",
            "package.json",
        ],
        "diff": "Fixed README typo, also restructured database schema and updated auth module",
        "expected_verdict": "significant_drift",
        "description": "Major scope creep from a typo fix",
    },
    {
        "task": "Add pagination to the users list endpoint",
        "changed_files": ["src/api/users.py", "tests/test_users.py"],
        "diff": "Added offset/limit pagination to GET /users endpoint with tests",
        "expected_verdict": "aligned",
        "description": "Tightly scoped feature addition",
    },
    {
        "task": "Refactor logging module",
        "changed_files": [
            "src/logging.py",
            "src/auth.py",
            "src/api/users.py",
            "src/api/orders.py",
            "src/database.py",
            "src/cache.py",
        ],
        "diff": "Replaced all print statements with structured logging across the entire codebase",
        "expected_verdict": "minor_drift",
        "description": "Cross-cutting refactor touching many files",
    },
    {
        "task": "Add dark mode to settings page",
        "changed_files": [
            "src/api/payments.py",
            "src/billing/stripe.py",
            "migrations/010_billing.sql",
        ],
        "diff": "Implemented Stripe billing integration with recurring subscriptions",
        "expected_verdict": "significant_drift",
        "description": "Completely unrelated changes (billing vs dark mode)",
    },
    {
        "task": "Optimize database query performance",
        "changed_files": [
            "src/database/queries.py",
            "src/database/indexes.py",
            "tests/test_queries.py",
        ],
        "diff": "Added composite indexes and query optimization for slow endpoints",
        "expected_verdict": "aligned",
        "description": "Focused performance optimization",
    },
]


@dataclass(slots=True)
class DriftBenchResult:
    """Result of the drift benchmark."""

    num_pairs: int
    latencies_ms: list[float]
    correct_verdicts: int
    total_verdicts: int
    per_pair: list[dict[str, object]]

    @property
    def accuracy_pct(self) -> float:
        return (self.correct_verdicts / self.total_verdicts * 100) if self.total_verdicts else 0.0

    @property
    def p50_ms(self) -> float:
        return _percentile(self.latencies_ms, 50)

    @property
    def p95_ms(self) -> float:
        return _percentile(self.latencies_ms, 95)

    @property
    def p99_ms(self) -> float:
        return _percentile(self.latencies_ms, 99)


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


def run_drift_benchmark(tmp_dir: Path | None = None) -> DriftBenchResult:
    """Run the drift_check benchmark on all test pairs.

    Uses a mock embedding model, so accuracy reflects hash-based
    similarity rather than true semantic similarity.
    """
    import tempfile

    if tmp_dir is None:
        tmp_dir = Path(tempfile.mkdtemp())

    db_path = tmp_dir / "bench_drift.db"
    conn = get_connection(db_path)

    # Create required tables
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS drift_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_description TEXT NOT NULL,
            changed_files TEXT NOT NULL,
            score REAL NOT NULL,
            similarity REAL NOT NULL,
            verdict TEXT NOT NULL,
            flags TEXT NOT NULL,
            project TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    ensure_idempotency_table(conn)
    conn.commit()

    model = _BenchEmbeddingModel()
    latencies: list[float] = []
    correct = 0
    per_pair: list[dict[str, object]] = []

    for pair in _DRIFT_PAIRS:
        start = time.perf_counter()
        env = asyncio.run(
            drift_check(
                model,
                conn,
                task_description=str(pair["task"]),
                changed_files=list(pair["changed_files"]),  # type: ignore[arg-type]
                diff_summary=str(pair["diff"]),
            )
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(round(elapsed_ms, 2))

        actual_verdict = env["data"]["verdict"]
        expected_verdict = pair["expected_verdict"]
        is_correct = actual_verdict == expected_verdict

        if is_correct:
            correct += 1

        per_pair.append(
            {
                "description": pair["description"],
                "expected": expected_verdict,
                "actual": actual_verdict,
                "correct": is_correct,
                "score": env["data"]["score"],
                "latency_ms": round(elapsed_ms, 2),
            }
        )

    conn.close()

    return DriftBenchResult(
        num_pairs=len(_DRIFT_PAIRS),
        latencies_ms=latencies,
        correct_verdicts=correct,
        total_verdicts=len(_DRIFT_PAIRS),
        per_pair=per_pair,
    )


def format_drift_results(result: DriftBenchResult) -> str:
    """Format drift benchmark results as markdown."""
    lines: list[str] = [
        "## Drift Detection Benchmark",
        "",
        f"- **Test pairs**: {result.num_pairs}",
        f"- **Accuracy**: {result.correct_verdicts}/{result.total_verdicts}"
        f" ({result.accuracy_pct:.0f}%)",
        "",
        "### Latency",
        "",
        f"- **p50**: {result.p50_ms:.2f}ms",
        f"- **p95**: {result.p95_ms:.2f}ms",
        f"- **p99**: {result.p99_ms:.2f}ms",
        f"- **Mean**: {statistics.mean(result.latencies_ms):.2f}ms",
        "",
        "### Per-Pair Results",
        "",
        "| Description | Expected | Actual | Score | Correct | Latency (ms) |",
        "|-------------|----------|--------|-------|---------|-------------|",
    ]

    for p in result.per_pair:
        mark = "✓" if p["correct"] else "✗"
        lines.append(
            f"| {p['description']} | {p['expected']} | {p['actual']} | "
            f"{p['score']:.3f} | {mark} | {p['latency_ms']:.2f} |"
        )

    lines.append("")
    lines.append(
        "**Note**: Mock embedding model uses hash-based vectors, so accuracy "
        "reflects hash similarity, not true semantic understanding."
    )

    return "\n".join(lines)


if __name__ == "__main__":
    result = run_drift_benchmark()
    print(format_drift_results(result))
