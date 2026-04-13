#!/usr/bin/env python3
"""Generic CLI for ad-hoc evaluation of individual MCP tools.

Usage:
    python evals/cli.py list
    python evals/cli.py run context_compress --text "Some verbose text..."
    python evals/cli.py run context_compress --file docs/README.md
    python evals/cli.py run model_recommend --agent craft --task-classification standard
    python evals/cli.py run patterns_search --query "database"
    python evals/cli.py run drift_check --task-description "Fix login" \\
        --changed-files '["auth.py"]' --diff-summary "Changed auth"
    python evals/cli.py run session_save --session-id test --state '{"step": "plan"}'
    python evals/cli.py run session_load --session-id test
    python evals/cli.py run project_index --project-path /path/to/project
    python evals/cli.py run health
    python evals/cli.py run reset --confirm
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

# Ensure src/ and project root are importable when run standalone
_project_root = Path(__file__).parent.parent
_src_dir = _project_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ensemble_mcp.memory.store import VectorStore
from ensemble_mcp.server import _health, _reset
from ensemble_mcp.tools.compress import context_compress
from ensemble_mcp.tools.drift import drift_check
from ensemble_mcp.tools.indexer import project_dependencies, project_index, project_query
from ensemble_mcp.tools.patterns import patterns_prune, patterns_search, patterns_store
from ensemble_mcp.tools.routing import model_recommend
from ensemble_mcp.tools.session import session_load, session_save
from ensemble_mcp.tools.skills import skills_discover, skills_generate, skills_suggest
from evals.conftest import EvalMockEmbeddingModel
from evals.helpers import make_eval_db

# ── Tool registry ────────────────────────────────────────────────

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "patterns_search": "Search stored patterns by semantic similarity",
    "patterns_store": "Store a new pattern for future search",
    "patterns_prune": "Remove old/unused patterns",
    "drift_check": "Check if code changes drift from the original task",
    "model_recommend": "Recommend a model tier for an agent and task",
    "session_save": "Save pipeline checkpoint state",
    "session_load": "Load pipeline checkpoint state",
    "skills_discover": "Discover skill files in a project",
    "skills_suggest": "Suggest reusable skills from pattern clusters",
    "skills_generate": "Accept/dismiss/defer a skill suggestion",
    "project_index": "Build or refresh the codebase index",
    "project_query": "Query the project index",
    "project_dependencies": "Get import/dependency graph for a file",
    "context_compress": "Compress verbose text into terse form",
    "health": "Server health check",
    "reset": "Reset all stored data",
}


def _get_store(db_path: Path | None = None) -> VectorStore:
    """Create a VectorStore with mock model for CLI use."""
    if db_path is None:
        db_path = Path(tempfile.mkdtemp()) / "cli_eval.db"
    model = EvalMockEmbeddingModel()
    return VectorStore(db_path=db_path, model=model)


def _get_conn(db_path: Path | None = None) -> Any:
    """Create a database connection for CLI use.

    Args:
        db_path: Optional path to an existing or desired database file.
            When provided, the database is created at that location.
            When ``None``, a temporary directory is used.
    """
    if db_path is None:
        db_dir = Path(tempfile.mkdtemp())
    else:
        db_dir = db_path.parent
        db_dir.mkdir(parents=True, exist_ok=True)
    return make_eval_db(db_dir)


def _get_model() -> EvalMockEmbeddingModel:
    """Create a mock embedding model for CLI use."""
    return EvalMockEmbeddingModel()


# ── Tool handlers ────────────────────────────────────────────────


def _handle_patterns_search(args: argparse.Namespace) -> dict[str, Any]:
    store = _get_store(args.db_path)
    result = asyncio.run(patterns_search(store, query=args.query, top_k=args.top_k or 3))
    store.close()
    return result


def _handle_patterns_store(args: argparse.Namespace) -> dict[str, Any]:
    store = _get_store(args.db_path)
    result = asyncio.run(
        patterns_store(
            store,
            name=args.name,
            context=args.context,
            approach=args.approach,
            outcome=args.outcome,
        )
    )
    store.close()
    return result


def _handle_patterns_prune(args: argparse.Namespace) -> dict[str, Any]:
    store = _get_store(args.db_path)
    result = asyncio.run(patterns_prune(store, max_age_days=args.max_age_days or 90))
    store.close()
    return result


def _handle_drift_check(args: argparse.Namespace) -> dict[str, Any]:
    conn = _get_conn(args.db_path)
    model = _get_model()
    changed_files = json.loads(args.changed_files) if args.changed_files else []
    result = asyncio.run(
        drift_check(
            model,
            conn,
            task_description=args.task_description,
            changed_files=changed_files,
            diff_summary=args.diff_summary,
        )
    )
    conn.close()
    return result


def _handle_model_recommend(args: argparse.Namespace) -> dict[str, Any]:
    conn = _get_conn(args.db_path)
    result = asyncio.run(
        model_recommend(
            conn,
            agent=args.agent,
            task_classification=args.task_classification,
            task_description=args.task_description,
        )
    )
    conn.close()
    return result


def _handle_session_save(args: argparse.Namespace) -> dict[str, Any]:
    conn = _get_conn(args.db_path)
    state = json.loads(args.state) if args.state else {}
    version = args.version
    result = asyncio.run(
        session_save(
            conn,
            session_id=args.session_id,
            state=state,
            version=version,
        )
    )
    conn.close()
    return result


def _handle_session_load(args: argparse.Namespace) -> dict[str, Any]:
    conn = _get_conn(args.db_path)
    result = asyncio.run(session_load(conn, session_id=args.session_id))
    conn.close()
    return result


def _handle_skills_discover(args: argparse.Namespace) -> dict[str, Any]:
    conn = _get_conn(args.db_path)
    model = _get_model()
    result = asyncio.run(
        skills_discover(model, conn, project_path=args.project_path, query=args.query)
    )
    conn.close()
    return result


def _handle_skills_suggest(args: argparse.Namespace) -> dict[str, Any]:
    conn = _get_conn(args.db_path)
    model = _get_model()
    result = asyncio.run(
        skills_suggest(
            model,
            conn,
            project_path=args.project_path,
            min_cluster_size=args.min_cluster_size or 3,
        )
    )
    conn.close()
    return result


def _handle_skills_generate(args: argparse.Namespace) -> dict[str, Any]:
    conn = _get_conn(args.db_path)
    result = asyncio.run(
        skills_generate(
            conn,
            suggestion_id=args.suggestion_id,
            action=args.action or "accept",
        )
    )
    conn.close()
    return result


def _handle_project_index(args: argparse.Namespace) -> dict[str, Any]:
    conn = _get_conn(args.db_path)
    result = asyncio.run(
        project_index(
            conn,
            project_path=args.project_path,
            force=args.force or False,
        )
    )
    conn.close()
    return result


def _handle_project_query(args: argparse.Namespace) -> dict[str, Any]:
    conn = _get_conn(args.db_path)
    file_types = json.loads(args.file_types) if args.file_types else None
    result = asyncio.run(
        project_query(
            conn,
            project_path=args.project_path,
            query=args.query,
            file_types=file_types,
            path_pattern=args.path_pattern,
        )
    )
    conn.close()
    return result


def _handle_project_dependencies(args: argparse.Namespace) -> dict[str, Any]:
    conn = _get_conn(args.db_path)
    result = asyncio.run(
        project_dependencies(
            conn,
            project_path=args.project_path,
            file_path=args.file_path,
        )
    )
    conn.close()
    return result


def _handle_context_compress(args: argparse.Namespace) -> dict[str, Any]:
    conn = _get_conn(args.db_path)
    text = args.text
    if args.file:
        try:
            text = Path(args.file).read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"ok": False, "error": f"File not found: {args.file}"}
        except OSError as exc:
            return {"ok": False, "error": f"Cannot read file {args.file}: {exc}"}
    if not text:
        return {"ok": False, "error": "No text provided. Use --text or --file."}
    result = asyncio.run(context_compress(conn, text=text))
    conn.close()
    return result


def _handle_health(args: argparse.Namespace) -> dict[str, Any]:
    store = _get_store(args.db_path)
    result = _health(store)
    store.close()
    return result


def _handle_reset(args: argparse.Namespace) -> dict[str, Any]:
    store = _get_store(args.db_path)
    result = asyncio.run(_reset(store, confirm=args.confirm or False))
    store.close()
    return result


# ── Handler registry ─────────────────────────────────────────────

_HANDLERS: dict[str, Any] = {
    "patterns_search": _handle_patterns_search,
    "patterns_store": _handle_patterns_store,
    "patterns_prune": _handle_patterns_prune,
    "drift_check": _handle_drift_check,
    "model_recommend": _handle_model_recommend,
    "session_save": _handle_session_save,
    "session_load": _handle_session_load,
    "skills_discover": _handle_skills_discover,
    "skills_suggest": _handle_skills_suggest,
    "skills_generate": _handle_skills_generate,
    "project_index": _handle_project_index,
    "project_query": _handle_project_query,
    "project_dependencies": _handle_project_dependencies,
    "context_compress": _handle_context_compress,
    "health": _handle_health,
    "reset": _handle_reset,
}


# ── Output formatters ────────────────────────────────────────────


def _format_json(result: dict[str, Any]) -> str:
    """Format result as indented JSON."""
    return json.dumps(result, indent=2, default=str)


def _format_markdown(result: dict[str, Any]) -> str:
    """Format result as markdown."""
    lines = ["## Tool Result", ""]
    ok = result.get("ok", False)
    lines.append(f"**Status**: {'✓ OK' if ok else '✗ Error'}")
    lines.append("")

    if ok and result.get("data"):
        lines.append("### Data")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(result["data"], indent=2, default=str))
        lines.append("```")
    elif result.get("error"):
        lines.append("### Error")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(result["error"], indent=2, default=str))
        lines.append("```")

    if result.get("meta"):
        lines.append("")
        lines.append("### Meta")
        lines.append("")
        meta = result["meta"]
        lines.append(f"- **Duration**: {meta.get('duration_ms', 0)}ms")
        lines.append(f"- **Source**: {meta.get('source', 'unknown')}")

    return "\n".join(lines)


def _format_table(result: dict[str, Any]) -> str:
    """Format result as a compact table."""
    lines: list[str] = []
    ok = result.get("ok", False)
    lines.append(f"Status: {'OK' if ok else 'ERROR'}")

    data = result.get("data", {})
    if data:
        lines.append("")
        lines.append("| Key | Value |")
        lines.append("|-----|-------|")
        for key, value in data.items():
            val_str = str(value)
            if len(val_str) > 80:
                val_str = val_str[:77] + "..."
            lines.append(f"| {key} | {val_str} |")

    return "\n".join(lines)


_FORMATTERS = {
    "json": _format_json,
    "markdown": _format_markdown,
    "table": _format_table,
}


# ── CLI setup ────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the eval CLI."""
    parser = argparse.ArgumentParser(
        description="Eval CLI for ad-hoc MCP tool evaluation",
        prog="python evals/cli.py",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # list subcommand
    subparsers.add_parser("list", help="List all available tools")

    # run subcommand
    run_parser = subparsers.add_parser("run", help="Run a specific tool")
    run_parser.add_argument("tool", choices=list(_HANDLERS.keys()), help="Tool name")
    run_parser.add_argument(
        "--format",
        choices=["json", "markdown", "table"],
        default="json",
        help="Output format (default: json)",
    )
    run_parser.add_argument("--db-path", type=Path, default=None, help="Custom DB path")
    run_parser.add_argument("--file", type=str, default=None, help="Read input from file")

    # Common tool arguments
    run_parser.add_argument("--text", type=str, default=None, help="Text input")
    run_parser.add_argument("--query", type=str, default=None, help="Search query")
    run_parser.add_argument("--top-k", type=int, default=None, help="Top-K results")
    run_parser.add_argument("--name", type=str, default=None, help="Pattern name")
    run_parser.add_argument("--context", type=str, default=None, help="Pattern context")
    run_parser.add_argument("--approach", type=str, default=None, help="Pattern approach")
    run_parser.add_argument("--outcome", type=str, default=None, help="Pattern outcome")
    run_parser.add_argument("--max-age-days", type=int, default=None, help="Max age for prune")
    run_parser.add_argument("--task-description", type=str, default=None, help="Task description")
    run_parser.add_argument(
        "--changed-files", type=str, default=None, help="JSON array of changed files"
    )
    run_parser.add_argument("--diff-summary", type=str, default=None, help="Diff summary")
    run_parser.add_argument("--agent", type=str, default=None, help="Agent name")
    run_parser.add_argument(
        "--task-classification", type=str, default=None, help="Task classification"
    )
    run_parser.add_argument("--session-id", type=str, default=None, help="Session ID")
    run_parser.add_argument("--state", type=str, default=None, help="JSON state object")
    run_parser.add_argument("--version", type=int, default=None, help="Version for save")
    run_parser.add_argument("--project-path", type=str, default=None, help="Project path")
    run_parser.add_argument("--file-path", type=str, default=None, help="File path for deps")
    run_parser.add_argument("--file-types", type=str, default=None, help="JSON array of file types")
    run_parser.add_argument("--path-pattern", type=str, default=None, help="Path pattern filter")
    run_parser.add_argument("--force", action="store_true", help="Force reindex")
    run_parser.add_argument("--confirm", action="store_true", help="Confirm destructive action")
    run_parser.add_argument("--min-cluster-size", type=int, default=None, help="Min cluster size")
    run_parser.add_argument("--suggestion-id", type=int, default=None, help="Suggestion ID")
    run_parser.add_argument(
        "--action",
        type=str,
        default=None,
        choices=["accept", "dismiss", "defer"],
        help="Action for skill suggestion",
    )

    return parser


def main() -> None:
    """Entry point for the eval CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "list":
        print("Available tools:")
        print()
        for tool_name, description in _TOOL_DESCRIPTIONS.items():
            print(f"  {tool_name:<25} {description}")
        return

    if args.command == "run":
        handler = _HANDLERS.get(args.tool)
        if not handler:
            print(f"Unknown tool: {args.tool}", file=sys.stderr)
            sys.exit(1)

        try:
            result = handler(args)
        except Exception as exc:
            print(f"Error running {args.tool}: {exc}", file=sys.stderr)
            sys.exit(1)

        formatter = _FORMATTERS[args.format]
        print(formatter(result))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
