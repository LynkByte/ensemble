"""Benchmark for context_compress tool.

Measures compression ratio, latency, and preservation accuracy
across a corpus of diverse text samples.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from ensemble_mcp.compress.engine import compress

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


if __name__ == "__main__":
    results = run_compress_benchmark()
    print(format_compress_results(results))
