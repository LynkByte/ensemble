"""Real project data loader for eval benchmarks.

Loads documentation and source files from the ensemble-mcp project
for use as test corpus in benchmark tests.
"""

from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent


def load_doc_corpus() -> list[dict[str, str]]:
    """Load markdown docs from ``docs/`` as benchmark corpus.

    Returns a list of dicts with keys: ``id``, ``path``, ``content``,
    ``category``. Category is derived from the file name (e.g. ``references``
    for files in the ``docs/references/`` subdirectory).
    """
    docs_dir = _PROJECT_ROOT / "docs"
    if not docs_dir.is_dir():
        return []

    corpus: list[dict[str, str]] = []
    for md_file in sorted(docs_dir.rglob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        rel_path = md_file.relative_to(_PROJECT_ROOT)
        # Determine category from parent dir
        category = md_file.parent.name if md_file.parent != docs_dir else "docs"

        corpus.append(
            {
                "id": md_file.stem.lower().replace(" ", "-"),
                "path": str(rel_path),
                "content": content,
                "category": category,
            }
        )

    return corpus


def load_src_corpus() -> list[dict[str, str]]:
    """Load Python source files from ``src/ensemble_mcp/`` as benchmark corpus.

    Skips ``__pycache__`` directories. Returns a list of dicts with keys:
    ``id``, ``path``, ``content``, ``language``.
    """
    src_dir = _PROJECT_ROOT / "src" / "ensemble_mcp"
    if not src_dir.is_dir():
        return []

    corpus: list[dict[str, str]] = []
    for py_file in sorted(src_dir.rglob("*.py")):
        # Skip __pycache__
        if any(p.name == "__pycache__" for p in py_file.parents):
            continue

        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        rel_path = py_file.relative_to(_PROJECT_ROOT)
        corpus.append(
            {
                "id": str(rel_path).replace("/", ".").replace(".py", ""),
                "path": str(rel_path),
                "content": content,
                "language": "python",
            }
        )

    return corpus


def load_mixed_corpus(max_files: int = 20) -> list[dict[str, str]]:
    """Load a representative mix of docs and source files.

    Combines both corpora, capping at ``max_files`` total. Takes roughly
    half from each category for balanced representation.

    Args:
        max_files: Maximum number of files to return.
    """
    docs = load_doc_corpus()
    src = load_src_corpus()

    half = max_files // 2
    selected_docs = docs[:half]
    selected_src = src[: max_files - len(selected_docs)]

    return selected_docs + selected_src
