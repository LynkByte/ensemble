"""Benchmark for project_index, project_query, and project_dependencies tools.

Creates a synthetic temporary project, indexes it, then measures query
and dependency-graph latency and correctness.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from ensemble_mcp.tools.indexer import project_dependencies, project_index, project_query
from evals.helpers import make_eval_db, run_async

# ── Synthetic project structure ──────────────────────────────────

_SYNTHETIC_FILES: dict[str, str] = {
    "src/main.py": (
        '"""Main application entry point."""\n\n'
        "import os\nimport sys\n\n"
        "from src.utils import helper\nfrom src.models import User\n\n\n"
        "def main() -> None:\n"
        '    """Run the application."""\n'
        "    print('hello')\n\n\n"
        "class App:\n"
        '    """Application class."""\n\n'
        "    def run(self) -> None:\n"
        "        pass\n"
    ),
    "src/utils.py": (
        '"""Utility functions."""\n\n'
        "import json\n\n\n"
        "def helper(x: int) -> int:\n"
        '    """Double a number."""\n'
        "    return x * 2\n\n\n"
        "def format_output(data: dict) -> str:\n"
        '    """Format data as JSON string."""\n'
        "    return json.dumps(data)\n"
    ),
    "src/models.py": (
        '"""Data models."""\n\n'
        "from dataclasses import dataclass\n\n\n"
        "@dataclass\n"
        "class User:\n"
        '    """A user entity."""\n\n'
        "    name: str\n"
        "    email: str\n"
    ),
    "src/__init__.py": "",
    "tests/test_main.py": (
        "from src.main import main, App\nfrom src.utils import helper\n\n\n"
        "def test_main() -> None:\n"
        "    main()\n\n\n"
        "def test_app() -> None:\n"
        "    app = App()\n"
        "    app.run()\n\n\n"
        "def test_helper() -> None:\n"
        "    assert helper(2) == 4\n"
    ),
    "frontend/index.ts": (
        "export function greet(name: string): string {\n"
        "    return `Hello, ${name}`;\n"
        "}\n\n"
        "export class UserService {\n"
        "    getUser(id: number) { return { id }; }\n"
        "}\n"
    ),
    "docs/README.md": (
        "# Test Project\n\nA test project for benchmarks.\n\n"
        "## Features\n\n- Feature A\n- Feature B\n"
    ),
    "config.yaml": ("app:\n  name: test\n  port: 8080\n  debug: true\n"),
}


@dataclass(slots=True)
class IndexerBenchResult:
    """Result of the indexer benchmark."""

    files_indexed: int
    index_latency_ms: float
    query_latency_ms: float
    dep_latency_ms: float
    query_results_correct: bool
    dep_results_correct: bool
    python_file_count: int
    ts_file_count: int

    @property
    def total_latency_ms(self) -> float:
        return self.index_latency_ms + self.query_latency_ms + self.dep_latency_ms


def _create_synthetic_project(tmp_dir: Path) -> Path:
    """Create a temporary project directory with synthetic files."""
    project = tmp_dir / "bench_project"
    project.mkdir()

    for rel_path, content in _SYNTHETIC_FILES.items():
        fp = project / rel_path
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")

    return project


def run_indexer_benchmark(tmp_dir: Path | None = None) -> IndexerBenchResult:
    """Run the indexer benchmark: index, query, and dependencies.

    Creates a synthetic project, indexes it, then runs various queries
    and dependency lookups.
    """
    import tempfile

    if tmp_dir is None:
        tmp_dir = Path(tempfile.mkdtemp())

    conn = make_eval_db(tmp_dir)
    project = _create_synthetic_project(tmp_dir)
    project_str = str(project)

    # Index the project
    start = time.perf_counter()
    index_env = run_async(project_index(conn, project_path=project_str, force=True))
    index_latency_ms = (time.perf_counter() - start) * 1000

    files_indexed = index_env["data"]["files"] if index_env["ok"] else 0

    # Query: find Python files
    start = time.perf_counter()
    query_env = run_async(project_query(conn, project_path=project_str, file_types=["python"]))
    query_latency_ms = (time.perf_counter() - start) * 1000

    python_count = query_env["data"]["count"] if query_env["ok"] else 0

    # Query: find TypeScript files
    ts_env = run_async(project_query(conn, project_path=project_str, file_types=["typescript"]))
    ts_count = ts_env["data"]["count"] if ts_env["ok"] else 0

    # Query: search by path pattern
    path_env = run_async(project_query(conn, project_path=project_str, path_pattern="tests/"))
    path_query_correct = path_env["ok"] and path_env["data"]["count"] >= 1

    # Query: search by keyword
    keyword_env = run_async(project_query(conn, project_path=project_str, query="helper"))
    keyword_correct = keyword_env["ok"] and keyword_env["data"]["count"] >= 1

    query_results_correct = path_query_correct and keyword_correct

    # Dependencies: check main.py imports
    start = time.perf_counter()
    dep_env = run_async(
        project_dependencies(conn, project_path=project_str, file_path="src/main.py")
    )
    dep_latency_ms = (time.perf_counter() - start) * 1000

    dep_results_correct = False
    if dep_env["ok"]:
        imports = dep_env["data"]["imports"]
        # main.py imports os, sys, src.utils, src.models → expect all 4
        dep_results_correct = len(imports) >= 4

    conn.close()

    return IndexerBenchResult(
        files_indexed=files_indexed,
        index_latency_ms=round(index_latency_ms, 2),
        query_latency_ms=round(query_latency_ms, 2),
        dep_latency_ms=round(dep_latency_ms, 2),
        query_results_correct=query_results_correct,
        dep_results_correct=dep_results_correct,
        python_file_count=python_count,
        ts_file_count=ts_count,
    )


def format_indexer_results(result: IndexerBenchResult) -> str:
    """Format indexer benchmark results as markdown."""
    lines: list[str] = [
        "## Indexer Benchmark",
        "",
        f"- **Files indexed**: {result.files_indexed}",
        f"- **Python files found**: {result.python_file_count}",
        f"- **TypeScript files found**: {result.ts_file_count}",
        f"- **Query results correct**: {'✓' if result.query_results_correct else '✗'}",
        f"- **Dependency results correct**: {'✓' if result.dep_results_correct else '✗'}",
        "",
        "### Latency",
        "",
        f"- **Index**: {result.index_latency_ms:.2f}ms",
        f"- **Query**: {result.query_latency_ms:.2f}ms",
        f"- **Dependencies**: {result.dep_latency_ms:.2f}ms",
        f"- **Total**: {result.total_latency_ms:.2f}ms",
    ]

    return "\n".join(lines)


# ── Pytest-discoverable wrappers ─────────────────────────────────


def test_indexer_benchmark_runs() -> None:
    """Pytest wrapper: runs indexer benchmark and validates results."""
    result = run_indexer_benchmark()
    assert result.files_indexed > 0, "No files were indexed"
    assert result.python_file_count >= 4, (
        f"Expected ≥4 Python files, got {result.python_file_count}"
    )
    assert result.ts_file_count >= 1, f"Expected ≥1 TypeScript file, got {result.ts_file_count}"


def test_indexer_query_correctness() -> None:
    """Pytest wrapper: validates query results are correct."""
    result = run_indexer_benchmark()
    assert result.query_results_correct, "Query results were incorrect"


def test_indexer_dependency_correctness() -> None:
    """Pytest wrapper: validates dependency graph is correct."""
    result = run_indexer_benchmark()
    assert result.dep_results_correct, "Dependency results were incorrect"


def test_indexer_format_output() -> None:
    """Pytest wrapper: ensures format function produces valid markdown."""
    result = run_indexer_benchmark()
    markdown = format_indexer_results(result)
    assert "## Indexer Benchmark" in markdown
    assert "### Latency" in markdown


if __name__ == "__main__":
    result = run_indexer_benchmark()
    print(format_indexer_results(result))
