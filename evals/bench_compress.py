"""Benchmark for context_compress tool.

Measures compression ratio, latency, and preservation accuracy
across a corpus of diverse text samples and real project documentation.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from ensemble_mcp.compress.engine import compress
from evals.corpus import load_doc_corpus

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


@dataclass(slots=True)
class CompressBenchResult:
    """Result of a single compression benchmark run."""

    sample_id: str
    category: str
    input_chars: int
    output_chars: int
    original_tokens: int
    compressed_tokens: int
    savings_pct: float
    preserved_count: int
    latency_ms: float


def run_compress_benchmark() -> list[CompressBenchResult]:
    """Run compression benchmark on all snapshot samples.

    Returns per-sample results with latency and compression metrics.
    """
    corpus_path = SNAPSHOTS_DIR / "compress_samples.json"
    if not corpus_path.exists():
        raise FileNotFoundError(f"Snapshot corpus not found: {corpus_path}")

    samples: list[dict[str, str]] = json.loads(corpus_path.read_text())
    results: list[CompressBenchResult] = []

    for sample in samples:
        text = sample["input"]

        # Measure latency
        start = time.perf_counter()
        cr = compress(text)
        elapsed_ms = (time.perf_counter() - start) * 1000

        results.append(
            CompressBenchResult(
                sample_id=sample["id"],
                category=sample.get("category", "unknown"),
                input_chars=len(text),
                output_chars=len(cr.compressed_text),
                original_tokens=cr.original_tokens,
                compressed_tokens=cr.compressed_tokens,
                savings_pct=cr.savings_pct,
                preserved_count=cr.preserved_count,
                latency_ms=round(elapsed_ms, 2),
            )
        )

    return results


def run_compress_real_docs_benchmark() -> list[CompressBenchResult]:
    """Run compression benchmark on real project documentation files.

    Uses ``docs/*.md`` from the project root. Skips files shorter than
    the compression engine's minimum input length (10 chars).
    """
    docs = load_doc_corpus()
    results: list[CompressBenchResult] = []

    for doc in docs:
        text = doc["content"]
        # Skip very short docs that don't meet compression minimum
        if len(text) < 10:
            continue

        start = time.perf_counter()
        cr = compress(text)
        elapsed_ms = (time.perf_counter() - start) * 1000

        results.append(
            CompressBenchResult(
                sample_id=doc["id"],
                category=doc["category"],
                input_chars=len(text),
                output_chars=len(cr.compressed_text),
                original_tokens=cr.original_tokens,
                compressed_tokens=cr.compressed_tokens,
                savings_pct=cr.savings_pct,
                preserved_count=cr.preserved_count,
                latency_ms=round(elapsed_ms, 2),
            )
        )

    return results


def format_compress_results(results: list[CompressBenchResult]) -> str:
    """Format benchmark results as a markdown table.

    Returns a markdown string with per-sample and aggregate metrics.
    """
    lines: list[str] = [
        "## Compression Benchmark",
        "",
        "| Sample | Category | Input Tokens | Output Tokens | Savings % | Preserved | Latency (ms) |",  # noqa: E501
        "|--------|----------|-------------|---------------|-----------|-----------|-------------|",
    ]

    total_original = 0
    total_compressed = 0
    total_latency = 0.0

    for r in results:
        lines.append(
            f"| {r.sample_id} | {r.category} | {r.original_tokens} | "
            f"{r.compressed_tokens} | {r.savings_pct:.1f}% | "
            f"{r.preserved_count} | {r.latency_ms:.2f} |"
        )
        total_original += r.original_tokens
        total_compressed += r.compressed_tokens
        total_latency += r.latency_ms

    # Aggregate
    avg_savings = (1.0 - total_compressed / total_original) * 100 if total_original > 0 else 0.0

    avg_latency = total_latency / len(results) if results else 0.0

    lines.extend(
        [
            "",
            "### Aggregate",
            "",
            f"- **Total samples**: {len(results)}",
            f"- **Total original tokens**: {total_original}",
            f"- **Total compressed tokens**: {total_compressed}",
            f"- **Overall savings**: {avg_savings:.1f}%",
            f"- **Avg latency**: {avg_latency:.2f}ms",
            f"- **Total latency**: {total_latency:.2f}ms",
        ]
    )

    return "\n".join(lines)


# ── Pytest-discoverable wrappers ─────────────────────────────────


def test_compress_benchmark_runs() -> None:
    """Pytest wrapper: runs compression benchmark and validates results."""
    results = run_compress_benchmark()
    assert len(results) > 0, "Expected at least one benchmark result"
    for r in results:
        assert r.savings_pct >= 0, f"Negative savings for {r.sample_id}"
        assert r.latency_ms >= 0, f"Negative latency for {r.sample_id}"
        # Allow a small tolerance: whitespace normalisation around preserved spans
        # can add 1-2 chars; the meaningful metric is savings_pct, not raw char count.
        assert r.output_chars <= r.input_chars + 5, (
            f"Output much larger than input for {r.sample_id}"
        )


def test_compress_format_output() -> None:
    """Pytest wrapper: ensures format function produces valid markdown."""
    results = run_compress_benchmark()
    markdown = format_compress_results(results)
    assert "## Compression Benchmark" in markdown
    assert "### Aggregate" in markdown


def test_compress_real_docs() -> None:
    """Pytest wrapper: runs compression on real project docs."""
    results = run_compress_real_docs_benchmark()
    assert len(results) > 0, "Expected at least one real doc result"
    for r in results:
        # Structural assertion: savings should be non-negative
        assert r.savings_pct >= 0, f"Negative savings for real doc {r.sample_id}"
        assert r.latency_ms >= 0, f"Negative latency for real doc {r.sample_id}"


if __name__ == "__main__":
    results = run_compress_benchmark()
    print(format_compress_results(results))
    print()
    print("--- Real Docs ---")
    real_results = run_compress_real_docs_benchmark()
    print(format_compress_results(real_results))
