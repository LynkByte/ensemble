"""Eval-specific test fixtures.

Provides database connections, mock models, snapshot data loaders,
real-project corpus data, and synthetic project directories
for benchmark tests across all 16 MCP tools.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from ensemble_mcp.memory.embeddings import EmbeddingModel
from ensemble_mcp.memory.store import VectorStore
from evals.corpus import load_doc_corpus, load_src_corpus
from evals.helpers import make_eval_db

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


class EvalMockEmbeddingModel(EmbeddingModel):
    """Deterministic embedding model for eval benchmarks."""

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


@pytest.fixture()
def snapshot_data() -> dict[str, list[dict]]:
    """Load all snapshot JSON files from evals/snapshots/."""
    data: dict[str, list[dict]] = {}
    for path in SNAPSHOTS_DIR.glob("*.json"):
        data[path.stem] = json.loads(path.read_text())
    return data


@pytest.fixture()
def eval_model() -> EvalMockEmbeddingModel:
    """Return a deterministic mock embedding model for evals."""
    return EvalMockEmbeddingModel()


@pytest.fixture()
def eval_conn(tmp_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Yield a clean SQLite connection with all tables for eval benchmarks.

    Delegates table creation to :func:`evals.helpers.make_eval_db` so
    the DDL is defined in a single place.
    """
    conn = make_eval_db(tmp_path)

    yield conn
    conn.close()


@pytest.fixture()
def eval_store(
    tmp_path: Path,
    eval_model: EvalMockEmbeddingModel,
) -> Generator[VectorStore, None, None]:
    """Yield a VectorStore backed by a temp DB and mock embeddings for evals."""
    db_path = tmp_path / "eval_store.db"
    store = VectorStore(db_path=db_path, model=eval_model)
    yield store
    store.close()


@pytest.fixture()
def corpus_docs() -> list[dict[str, str]]:
    """Load real docs/*.md files as benchmark corpus."""
    return load_doc_corpus()


@pytest.fixture()
def corpus_src() -> list[dict[str, str]]:
    """Load real src/ensemble_mcp/**/*.py files as benchmark corpus."""
    return load_src_corpus()


@pytest.fixture()
def eval_project_dir(tmp_path: Path) -> Path:
    """Create a synthetic project directory for indexer/skills benchmarks.

    Contains a mix of Python, TypeScript, Markdown files and a
    ``.ai/skills/`` directory with mock skill files.
    """
    project = tmp_path / "test_project"
    project.mkdir()

    # Python files
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text(
        '"""Main application entry point."""\n\n'
        "import os\nimport sys\n\n"
        "from src.utils import helper\n\n\n"
        "def main() -> None:\n"
        '    """Run the application."""\n'
        "    print('hello')\n\n\n"
        "class App:\n"
        '    """Application class."""\n\n'
        "    def run(self) -> None:\n"
        "        pass\n",
        encoding="utf-8",
    )
    (project / "src" / "utils.py").write_text(
        '"""Utility functions."""\n\n'
        "import json\n\n\n"
        "def helper(x: int) -> int:\n"
        '    """Double a number."""\n'
        "    return x * 2\n\n\n"
        "def format_output(data: dict) -> str:\n"
        '    """Format data as JSON string."""\n'
        "    return json.dumps(data)\n",
        encoding="utf-8",
    )
    (project / "src" / "__init__.py").write_text("", encoding="utf-8")

    # Tests
    (project / "tests").mkdir()
    (project / "tests" / "test_main.py").write_text(
        "from src.main import main, App\n\n\n"
        "def test_main() -> None:\n"
        "    main()\n\n\n"
        "def test_app() -> None:\n"
        "    app = App()\n"
        "    app.run()\n",
        encoding="utf-8",
    )

    # TypeScript files
    (project / "frontend").mkdir()
    (project / "frontend" / "index.ts").write_text(
        "export function greet(name: string): string {\n"
        "    return `Hello, ${name}`;\n"
        "}\n\n"
        "export class UserService {\n"
        "    getUser(id: number) { return { id }; }\n"
        "}\n",
        encoding="utf-8",
    )

    # Markdown docs
    (project / "docs").mkdir()
    (project / "docs" / "README.md").write_text(
        "# Test Project\n\nA test project for benchmarks.\n\n"
        "## Features\n\n- Feature A\n- Feature B\n",
        encoding="utf-8",
    )

    # Config file
    (project / "config.yaml").write_text(
        "app:\n  name: test\n  port: 8080\n  debug: true\n",
        encoding="utf-8",
    )

    # Skill files for skills_discover
    skills_dir = project / ".ai" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "testing.md").write_text(
        "# Testing Patterns\n\n"
        "## When to Apply\n\n"
        "- Writing unit tests\n"
        "- Integration testing\n\n"
        "## Approach\n\n"
        "Use pytest fixtures with dependency injection.\n",
        encoding="utf-8",
    )
    (skills_dir / "refactoring.md").write_text(
        "# Refactoring Guide\n\n"
        "## When to Apply\n\n"
        "- Code smells detected\n"
        "- Performance issues\n\n"
        "## Approach\n\n"
        "Extract method, rename variables, simplify conditionals.\n",
        encoding="utf-8",
    )

    return project
