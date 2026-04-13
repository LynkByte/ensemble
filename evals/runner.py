#!/usr/bin/env python3
"""Standalone benchmark runner for ensemble-mcp.

Usage:
    python evals/runner.py

Runs all 16-tool benchmarks and formats results as markdown tables to stdout.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

# Ensure both src/ and project root are on the path when run standalone.
# src/ is needed for `ensemble_mcp` imports; project root for `evals` package imports.
_project_root = Path(__file__).parent.parent
_src_dir = _project_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def main() -> None:
    """Run all benchmarks and print results."""
    print("# ensemble-mcp Benchmark Report")
    print()
    print(f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    tmp_dir = Path(tempfile.mkdtemp())

    # ── Compression benchmark ────────────────────────────────────
    print("Running compression benchmark...")
    try:
        from evals.bench_compress import format_compress_results, run_compress_benchmark

        compress_results = run_compress_benchmark()
        print(format_compress_results(compress_results))
    except Exception as exc:
        print(f"## Compression Benchmark\n\n**FAILED**: {exc}")
    print()

    # ── Patterns benchmark ───────────────────────────────────────
    print("Running patterns benchmark...")
    try:
        from evals.bench_patterns import format_patterns_results, run_patterns_benchmark

        patterns_result = run_patterns_benchmark(tmp_dir)
        print(format_patterns_results(patterns_result))
    except Exception as exc:
        print(f"## Patterns Benchmark\n\n**FAILED**: {exc}")
    print()

    # ── Drift benchmark ──────────────────────────────────────────
    print("Running drift benchmark...")
    try:
        from evals.bench_drift import format_drift_results, run_drift_benchmark

        drift_result = run_drift_benchmark(tmp_dir)
        print(format_drift_results(drift_result))
    except Exception as exc:
        print(f"## Drift Detection Benchmark\n\n**FAILED**: {exc}")
    print()

    # ── Routing benchmark ────────────────────────────────────────
    print("Running routing benchmark...")
    try:
        from evals.bench_routing import format_routing_results, run_routing_benchmark

        routing_result = run_routing_benchmark(tmp_dir)
        print(format_routing_results(routing_result))
    except Exception as exc:
        print(f"## Model Routing Benchmark\n\n**FAILED**: {exc}")
    print()

    # ── Session benchmark ────────────────────────────────────────
    print("Running session benchmark...")
    try:
        from evals.bench_session import format_session_results, run_session_benchmark

        session_result = run_session_benchmark(tmp_dir)
        print(format_session_results(session_result))
    except Exception as exc:
        print(f"## Session Benchmark\n\n**FAILED**: {exc}")
    print()

    # ── Indexer benchmark ────────────────────────────────────────
    print("Running indexer benchmark...")
    try:
        from evals.bench_indexer import format_indexer_results, run_indexer_benchmark

        indexer_result = run_indexer_benchmark(tmp_dir)
        print(format_indexer_results(indexer_result))
    except Exception as exc:
        print(f"## Indexer Benchmark\n\n**FAILED**: {exc}")
    print()

    # ── Skills benchmark ─────────────────────────────────────────
    print("Running skills benchmark...")
    try:
        from evals.bench_skills import format_skills_results, run_skills_benchmark

        skills_result = run_skills_benchmark(tmp_dir)
        print(format_skills_results(skills_result))
    except Exception as exc:
        print(f"## Skills Benchmark\n\n**FAILED**: {exc}")
    print()

    # ── Health & Reset benchmark ─────────────────────────────────
    print("Running health & reset benchmark...")
    try:
        from evals.bench_health_reset import (
            format_health_reset_results,
            run_health_reset_benchmark,
        )

        utility_result = run_health_reset_benchmark(tmp_dir)
        print(format_health_reset_results(utility_result))
    except Exception as exc:
        print(f"## Health & Reset Benchmark\n\n**FAILED**: {exc}")
    print()

    # ── Real docs compression ────────────────────────────────────
    print("Running real-docs compression benchmark...")
    try:
        from evals.bench_compress import (
            format_compress_results,
            run_compress_real_docs_benchmark,
        )

        real_docs_results = run_compress_real_docs_benchmark()
        print("## Real Docs Compression")
        print()
        print(format_compress_results(real_docs_results))
    except Exception as exc:
        print(f"## Real Docs Compression\n\n**FAILED**: {exc}")
    print()

    print("---")
    print("*All benchmarks complete.*")


if __name__ == "__main__":
    main()
