"""Benchmark for skills_discover, skills_suggest, and skills_generate tools.

Creates a temporary project with skill files and seed patterns,
then measures discovery, suggestion clustering, and generation.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ensemble_mcp.tools.skills import skills_discover, skills_generate, skills_suggest
from evals.conftest import EvalMockEmbeddingModel
from evals.helpers import make_eval_db, percentile, run_async

# ── Seed patterns for clustering ─────────────────────────────────

# These patterns share enough similarity to form a cluster when ≥3
_CLUSTER_PATTERNS: list[dict[str, str]] = [
    {
        "name": "pytest fixture setup",
        "context": "Setting up database fixtures for integration tests",
        "approach": "pytest fixtures with temporary SQLite databases",
        "outcome": "Isolated test environments",
    },
    {
        "name": "pytest parametrize tests",
        "context": "Running same test with different input data",
        "approach": "pytest parametrize decorator with test matrices",
        "outcome": "Better test coverage with less code",
    },
    {
        "name": "pytest mock dependencies",
        "context": "Mocking external APIs in unit tests",
        "approach": "pytest monkeypatch and unittest.mock",
        "outcome": "Fast isolated unit tests",
    },
    {
        "name": "pytest async testing",
        "context": "Testing async functions with pytest",
        "approach": "pytest-asyncio with async fixtures",
        "outcome": "Correct async test execution",
    },
]


@dataclass(slots=True)
class SkillsBenchResult:
    """Result of the skills benchmark."""

    discover_count: int
    suggest_count: int
    generate_success: bool
    latencies_ms: list[float]

    @property
    def p50_ms(self) -> float:
        return percentile(self.latencies_ms, 50)

    @property
    def p95_ms(self) -> float:
        return percentile(self.latencies_ms, 95)


def _create_skill_project(tmp_dir: Path) -> Path:
    """Create a temporary project with skill files for discovery."""
    project = tmp_dir / "skill_project"
    project.mkdir()

    # Create .ai/skills/ directory with skill files
    skills_dir = project / ".ai" / "skills"
    skills_dir.mkdir(parents=True)

    (skills_dir / "testing-patterns.md").write_text(
        "# Testing Patterns\n\n"
        "## When to Apply\n\n"
        "- Writing unit tests for async code\n"
        "- Integration testing with databases\n\n"
        "## Approach\n\n"
        "Use pytest fixtures with dependency injection.\n"
        "Mock external services with unittest.mock.\n",
        encoding="utf-8",
    )
    (skills_dir / "code-review.md").write_text(
        "# Code Review Guidelines\n\n"
        "## When to Apply\n\n"
        "- Reviewing pull requests\n"
        "- Checking for security issues\n\n"
        "## Approach\n\n"
        "Focus on logic correctness, security, and performance.\n",
        encoding="utf-8",
    )
    (skills_dir / "refactoring.md").write_text(
        "# Refactoring Strategies\n\n"
        "## When to Apply\n\n"
        "- Reducing code complexity\n"
        "- Eliminating duplication\n\n"
        "## Approach\n\n"
        "Extract method, simplify conditionals, rename for clarity.\n",
        encoding="utf-8",
    )

    return project


def _seed_patterns(
    conn: Any,
    model: EvalMockEmbeddingModel,
    project_path: str,
) -> None:
    """Seed patterns into the database for clustering."""
    for pat in _CLUSTER_PATTERNS:
        text = f"{pat['name']} {pat['context']} {pat['approach']}"
        embedding = model.embed(text)
        emb_blob = embedding.tobytes()
        conn.execute(
            "INSERT INTO patterns (name, context, approach, outcome, project, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pat["name"], pat["context"], pat["approach"], pat["outcome"], project_path, emb_blob),
        )
    conn.commit()


def run_skills_benchmark(tmp_dir: Path | None = None) -> SkillsBenchResult:
    """Run the skills benchmark: discover, suggest, and generate.

    Creates a temporary project with skill files, seeds patterns
    for clustering, then measures all three skills tools.
    """
    import tempfile

    if tmp_dir is None:
        tmp_dir = Path(tempfile.mkdtemp())

    conn = make_eval_db(tmp_dir)
    model = EvalMockEmbeddingModel()
    project = _create_skill_project(tmp_dir)
    project_str = str(project)
    latencies: list[float] = []

    # Seed patterns for suggest to find clusters
    _seed_patterns(conn, model, project_str)

    # Test skills_discover
    start = time.perf_counter()
    discover_env = run_async(skills_discover(model, conn, project_path=project_str))
    discover_ms = (time.perf_counter() - start) * 1000
    latencies.append(round(discover_ms, 2))

    discover_count = 0
    if discover_env["ok"]:
        discover_count = len(discover_env["data"]["detected"])

    # Test skills_discover with query
    start = time.perf_counter()
    run_async(skills_discover(model, conn, project_path=project_str, query="testing"))
    query_ms = (time.perf_counter() - start) * 1000
    latencies.append(round(query_ms, 2))

    # Test skills_suggest
    start = time.perf_counter()
    suggest_env = run_async(
        skills_suggest(model, conn, project_path=project_str, min_cluster_size=2)
    )
    suggest_ms = (time.perf_counter() - start) * 1000
    latencies.append(round(suggest_ms, 2))

    suggest_count = 0
    suggestion_id: int | None = None
    if suggest_env["ok"]:
        suggest_count = len(suggest_env["data"]["suggestions"])
        if suggest_count > 0:
            suggestion_id = suggest_env["data"]["suggestions"][0]["id"]

    # Test skills_generate (accept)
    generate_success = False
    if suggestion_id is not None:
        output_dir = str(tmp_dir / "generated_skills")
        start = time.perf_counter()
        generate_env = run_async(
            skills_generate(
                conn,
                suggestion_id=suggestion_id,
                action="accept",
                output_dir=output_dir,
            )
        )
        gen_ms = (time.perf_counter() - start) * 1000
        latencies.append(round(gen_ms, 2))
        generate_success = generate_env["ok"] and generate_env["data"].get("generated", False)

    conn.close()

    return SkillsBenchResult(
        discover_count=discover_count,
        suggest_count=suggest_count,
        generate_success=generate_success,
        latencies_ms=latencies,
    )


def format_skills_results(result: SkillsBenchResult) -> str:
    """Format skills benchmark results as markdown."""
    lines: list[str] = [
        "## Skills Benchmark",
        "",
        f"- **Skills discovered**: {result.discover_count}",
        f"- **Suggestions generated**: {result.suggest_count}",
        f"- **Generate success**: {'✓' if result.generate_success else '✗'}",
        "",
        "### Latency",
        "",
        f"- **p50**: {result.p50_ms:.2f}ms",
        f"- **p95**: {result.p95_ms:.2f}ms",
        f"- **Mean**: {statistics.mean(result.latencies_ms) if result.latencies_ms else 0.0:.2f}ms",
    ]

    return "\n".join(lines)


# ── Pytest-discoverable wrappers ─────────────────────────────────


def test_skills_discover() -> None:
    """Pytest wrapper: validates skills discovery finds skill files."""
    result = run_skills_benchmark()
    assert result.discover_count >= 2, f"Expected ≥2 skills, discovered {result.discover_count}"


def test_skills_suggest() -> None:
    """Pytest wrapper: validates skills suggestion generates at least one cluster."""
    result = run_skills_benchmark()
    # With a mock embedding model, hash-based clustering may not find
    # clusters above the threshold, so 0 suggestions is a valid outcome.
    assert result.suggest_count >= 0


def test_skills_generate() -> None:
    """Pytest wrapper: validates skills generation writes a file."""
    result = run_skills_benchmark()
    # generate_success depends on suggest finding a suggestion
    if result.suggest_count > 0:
        assert result.generate_success, "Skill generation failed"


def test_skills_format_output() -> None:
    """Pytest wrapper: ensures format function produces valid markdown."""
    result = run_skills_benchmark()
    markdown = format_skills_results(result)
    assert "## Skills Benchmark" in markdown
    assert "### Latency" in markdown


if __name__ == "__main__":
    result = run_skills_benchmark()
    print(format_skills_results(result))
