#!/usr/bin/env python3
"""Standalone benchmark runner for ensemble-mcp.

Usage:
    python evals/runner.py

Runs all benchmarks and formats results as markdown tables to stdout.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

# Ensure the src directory is on the path when run standalone
_project_root = Path(__file__).parent.parent
_src_dir = _project_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


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
        print(f"## Patterns Search Benchmark\n\n**FAILED**: {exc}")
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

    print("---")
    print("*All benchmarks complete.*")


if __name__ == "__main__":
    main()
