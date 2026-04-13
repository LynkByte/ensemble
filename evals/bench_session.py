"""Benchmark for session_save and session_load tools.

Tests roundtrip save/load, version conflict handling, and
load-latest behavior with varied payloads.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ensemble_mcp.tools.session import session_load, session_save
from evals.helpers import make_eval_db, percentile, run_async

# ── Test payloads ────────────────────────────────────────────────

_SESSION_CASES: list[dict[str, Any]] = [
    {
        "session_id": "pipeline-001",
        "state": {"step": "planning", "files": ["main.py"], "progress": 0.1},
    },
    {
        "session_id": "pipeline-002",
        "state": {"step": "coding", "files": ["auth.py", "tests/test_auth.py"], "progress": 0.5},
    },
    {
        "session_id": "pipeline-003",
        "state": {
            "step": "review",
            "agent": "lens",
            "findings": [{"file": "api.py", "line": 42, "issue": "N+1 query"}],
        },
    },
    {
        "session_id": "pipeline-004",
        "state": {"step": "testing", "passed": 12, "failed": 0, "skipped": 1},
    },
    {
        "session_id": "pipeline-005",
        "state": {"step": "deploy", "environment": "staging", "commit": "abc123"},
    },
    {
        "session_id": "pipeline-006",
        "state": {"step": "complete", "summary": "All tasks done", "duration_min": 15},
    },
    {
        "session_id": "pipeline-007",
        "state": {"nested": {"deep": {"value": [1, 2, 3], "flag": True}}},
    },
    {
        "session_id": "pipeline-008",
        "state": {"empty_list": [], "empty_dict": {}, "null_value": None},
    },
    {
        "session_id": "pipeline-009",
        "state": {"unicode": "日本語テスト", "emoji": "🚀", "special": "line\nbreak"},
    },
    {
        "session_id": "pipeline-010",
        "state": {"large_list": list(range(100)), "step": "batch"},
    },
]


@dataclass(slots=True)
class SessionBenchResult:
    """Result of the session benchmark."""

    num_cases: int
    latencies_ms: list[float]
    roundtrip_pass_count: int
    total_count: int
    version_conflict_ok: bool
    load_latest_ok: bool

    @property
    def p50_ms(self) -> float:
        return percentile(self.latencies_ms, 50)

    @property
    def p95_ms(self) -> float:
        return percentile(self.latencies_ms, 95)


def run_session_benchmark(tmp_dir: Path | None = None) -> SessionBenchResult:
    """Run the session save/load benchmark.

    Tests roundtrip save→load→verify for each case, then version
    conflict detection and load-latest behavior.
    """
    import tempfile

    if tmp_dir is None:
        tmp_dir = Path(tempfile.mkdtemp())

    conn = make_eval_db(tmp_dir)
    latencies: list[float] = []
    roundtrip_pass = 0
    total = 0

    # Test roundtrip save → load → verify
    for case in _SESSION_CASES:
        # Save
        start = time.perf_counter()
        save_env = run_async(
            session_save(
                conn,
                session_id=case["session_id"],
                state=case["state"],
            )
        )
        save_ms = (time.perf_counter() - start) * 1000
        latencies.append(round(save_ms, 2))

        # Load
        start = time.perf_counter()
        load_env = run_async(session_load(conn, session_id=case["session_id"]))
        load_ms = (time.perf_counter() - start) * 1000
        latencies.append(round(load_ms, 2))

        total += 1
        if (
            save_env["ok"]
            and load_env["ok"]
            and load_env["data"]["found"]
            and load_env["data"]["state"] == case["state"]
            and load_env["data"]["version"] == 1
        ):
            roundtrip_pass += 1

    # Test version conflict: save with correct version, then with wrong version
    conflict_session = "conflict-test"
    run_async(session_save(conn, session_id=conflict_session, state={"v": 1}))
    # Update to v2
    run_async(session_save(conn, session_id=conflict_session, state={"v": 2}, version=1))
    # Try update with stale version 1 (should fail)
    conflict_env = run_async(
        session_save(conn, session_id=conflict_session, state={"v": 3}, version=1)
    )
    version_conflict_ok = not conflict_env["ok"]

    # Test load latest (no session_id → most recent)
    latest_env = run_async(session_load(conn, session_id=None))
    load_latest_ok = latest_env["ok"] and latest_env["data"]["found"]

    conn.close()

    return SessionBenchResult(
        num_cases=len(_SESSION_CASES),
        latencies_ms=latencies,
        roundtrip_pass_count=roundtrip_pass,
        total_count=total,
        version_conflict_ok=version_conflict_ok,
        load_latest_ok=load_latest_ok,
    )


def format_session_results(result: SessionBenchResult) -> str:
    """Format session benchmark results as markdown."""
    lines: list[str] = [
        "## Session Benchmark",
        "",
        f"- **Test cases**: {result.num_cases}",
        f"- **Roundtrip pass**: {result.roundtrip_pass_count}/{result.total_count}",
        f"- **Version conflict handled**: {'✓' if result.version_conflict_ok else '✗'}",
        f"- **Load latest works**: {'✓' if result.load_latest_ok else '✗'}",
        "",
        "### Latency (save + load combined)",
        "",
        f"- **p50**: {result.p50_ms:.2f}ms",
        f"- **p95**: {result.p95_ms:.2f}ms",
        f"- **Mean**: {statistics.mean(result.latencies_ms) if result.latencies_ms else 0.0:.2f}ms",
    ]

    return "\n".join(lines)


# ── Pytest-discoverable wrappers ─────────────────────────────────


def test_session_benchmark_runs() -> None:
    """Pytest wrapper: runs session benchmark and validates roundtrips."""
    result = run_session_benchmark()
    assert result.num_cases > 0
    assert result.roundtrip_pass_count == result.total_count, (
        f"Roundtrip failures: {result.roundtrip_pass_count}/{result.total_count}"
    )


def test_session_version_conflict() -> None:
    """Pytest wrapper: validates version conflict detection."""
    result = run_session_benchmark()
    assert result.version_conflict_ok, "Version conflict was not properly detected"


def test_session_load_latest() -> None:
    """Pytest wrapper: validates load-latest behavior."""
    result = run_session_benchmark()
    assert result.load_latest_ok, "Load latest session failed"


def test_session_format_output() -> None:
    """Pytest wrapper: ensures format function produces valid markdown."""
    result = run_session_benchmark()
    markdown = format_session_results(result)
    assert "## Session Benchmark" in markdown
    assert "### Latency" in markdown


if __name__ == "__main__":
    result = run_session_benchmark()
    print(format_session_results(result))
