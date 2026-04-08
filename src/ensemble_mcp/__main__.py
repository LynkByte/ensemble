"""Entry point: python -m ensemble_mcp.

Provides eight subcommands:
  - ``serve`` (default): Start the MCP server on stdio.
  - ``install``: Detect AI tools and register ensemble-mcp in their configs.
  - ``uninstall``: Remove ensemble-mcp registration from AI tool configs.
  - ``add-agents``: Copy bundled agent files to tool-specific directories.
  - ``add-skills``: Copy bundled skill files to tool-specific directories.
  - ``dashboard``: Display a terminal-based metrics dashboard.
  - ``backfill``: Backfill session steps with real token data from AI tool files.
  - ``watch``: Watch AI tool session files and auto-trigger backfill on changes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate command."""
    parser = argparse.ArgumentParser(
        prog="ensemble-mcp",
        description="MCP server for vector memory, token tracking, drift detection, and more.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # ── serve (default) ───────────────────────────────────────────
    subparsers.add_parser(
        "serve",
        help="Start the MCP server (default when no command is given).",
    )

    # ── install ───────────────────────────────────────────────────
    install_parser = subparsers.add_parser(
        "install",
        help="Detect AI tools and register ensemble-mcp in their configs.",
    )
    install_parser.add_argument(
        "--local",
        action="store_true",
        default=False,
        help="Register in project-local configs instead of global user configs.",
    )
    install_parser.add_argument(
        "--project-path",
        type=Path,
        default=None,
        help="Project root directory (defaults to current working directory).",
    )
    install_parser.add_argument(
        "--tools",
        type=str,
        default=None,
        help=(
            "Comma-separated list of tools to register "
            "(e.g. --tools opencode,cursor). "
            "Defaults to all detected tools."
        ),
    )
    install_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show the install plan without making any changes.",
    )
    install_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        default=False,
        help="Skip confirmation prompt.",
    )

    # ── uninstall ─────────────────────────────────────────────────
    uninstall_parser = subparsers.add_parser(
        "uninstall",
        help="Remove ensemble-mcp registration from AI tool configs.",
    )
    uninstall_parser.add_argument(
        "--local",
        action="store_true",
        default=False,
        help="Remove from project-local configs instead of global user configs.",
    )
    uninstall_parser.add_argument(
        "--project-path",
        type=Path,
        default=None,
        help="Project root directory (defaults to current working directory).",
    )
    uninstall_parser.add_argument(
        "--tools",
        type=str,
        default=None,
        help=(
            "Comma-separated list of tools to deregister "
            "(e.g. --tools opencode,cursor). "
            "Defaults to all detected tools."
        ),
    )
    uninstall_parser.add_argument(
        "--remove-agents",
        action="store_true",
        default=False,
        help="Also remove agent/skill files from tool-specific directories.",
    )
    uninstall_parser.add_argument(
        "--clean-data",
        action="store_true",
        default=False,
        help=(
            "Also remove cached data (~/.cache/ensemble-mcp/) "
            "and global config (~/.config/ensemble-mcp/)."
        ),
    )
    uninstall_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show the uninstall plan without making any changes.",
    )
    uninstall_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        default=False,
        help="Skip confirmation prompt.",
    )

    # ── add-agents ────────────────────────────────────────────────
    add_agents_parser = subparsers.add_parser(
        "add-agents",
        help="Copy bundled agent files to tool-specific directories.",
    )
    add_agents_parser.add_argument(
        "--local",
        action="store_true",
        default=False,
        help="Copy to project-local agent dirs instead of global dirs.",
    )
    add_agents_parser.add_argument(
        "--project-path",
        type=Path,
        default=None,
        help="Project root directory (defaults to current working directory).",
    )
    add_agents_parser.add_argument(
        "--tools",
        type=str,
        default=None,
        help=(
            "Comma-separated list of tools to copy agents for "
            "(e.g. --tools opencode). "
            "Defaults to all known tools."
        ),
    )
    add_agents_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show the plan without making any changes.",
    )
    add_agents_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        default=False,
        help="Skip confirmation prompt.",
    )

    # ── add-skills ────────────────────────────────────────────────
    add_skills_parser = subparsers.add_parser(
        "add-skills",
        help="Copy bundled skill files to tool-specific directories.",
    )
    add_skills_parser.add_argument(
        "--local",
        action="store_true",
        default=False,
        help="Copy to project-local skill dirs (this is the default).",
    )
    add_skills_parser.add_argument(
        "--global",
        dest="use_global",
        action="store_true",
        default=False,
        help="Copy to global skill dirs instead of project-local.",
    )
    add_skills_parser.add_argument(
        "--project-path",
        type=Path,
        default=None,
        help="Project root directory (defaults to current working directory).",
    )
    add_skills_parser.add_argument(
        "--tools",
        type=str,
        default=None,
        help=(
            "Comma-separated list of tools to copy skills for "
            "(e.g. --tools opencode). "
            "Defaults to all known tools."
        ),
    )
    add_skills_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show the plan without making any changes.",
    )
    add_skills_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        default=False,
        help="Skip confirmation prompt.",
    )

    # ── dashboard ─────────────────────────────────────────────────
    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Display a terminal-based metrics dashboard.",
    )
    dashboard_parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Time range in days for the agent cost breakdown (default: 1 = today).",
    )
    dashboard_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of recent sessions to display (default: 10).",
    )
    dashboard_parser.add_argument(
        "--trend-days",
        type=int,
        default=7,
        help="Number of days for the daily trend chart (default: 7).",
    )
    dashboard_parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Override the database file path.",
    )

    # ── backfill ──────────────────────────────────────────────────
    backfill_parser = subparsers.add_parser(
        "backfill",
        help="Backfill session steps with real token data from AI tool files.",
    )
    backfill_parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Session ID to backfill (defaults to the most recent session).",
    )
    backfill_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite steps that already have real token data.",
    )
    backfill_parser.add_argument(
        "--ai-tool",
        type=str,
        default=None,
        help="Override AI tool detection: 'opencode' or 'claude-code'.",
    )
    backfill_parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Override the database file path.",
    )

    # ── watch ─────────────────────────────────────────────────────
    watch_parser = subparsers.add_parser(
        "watch",
        help="Watch AI tool session files and auto-trigger backfill on changes.",
    )
    watch_parser.add_argument(
        "--debounce",
        type=float,
        default=None,
        help="Seconds to wait after last change before backfill (default: 5).",
    )
    watch_parser.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="Seconds between OpenCode DB mtime checks (default: 10).",
    )
    watch_parser.add_argument(
        "--ai-tool",
        type=str,
        default=None,
        help="Watch specific tool only: 'opencode' or 'claude-code'.",
    )
    watch_parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Override the ensemble-mcp database file path.",
    )

    args = parser.parse_args()

    # Default to serve when no subcommand is given
    if args.command is None or args.command == "serve":
        _run_serve()
    elif args.command == "install":
        _run_install(args)
    elif args.command == "uninstall":
        _run_uninstall(args)
    elif args.command == "add-agents":
        _run_add_agents(args)
    elif args.command == "add-skills":
        _run_add_skills(args)
    elif args.command == "dashboard":
        _run_dashboard(args)
    elif args.command == "backfill":
        _run_backfill(args)
    elif args.command == "watch":
        _run_watch(args)
    else:
        parser.print_help()
        sys.exit(1)


def _run_serve() -> None:
    """Start the MCP server."""
    from ensemble_mcp.server import serve

    serve()


def _run_install(args: argparse.Namespace) -> None:
    """Run the auto-installer."""
    from ensemble_mcp.installer import TOOL_NAMES, InstallScope
    from ensemble_mcp.installer.setup import install

    scope = InstallScope.LOCAL if args.local else InstallScope.GLOBAL

    tool_filter: set[str] | None = None
    if args.tools:
        tool_filter = {t.strip() for t in args.tools.split(",")}
        unknown = tool_filter - TOOL_NAMES
        if unknown:
            sys.stderr.write(
                f"Unknown tool(s): {', '.join(sorted(unknown))}\n"
                f"Available: {', '.join(sorted(TOOL_NAMES))}\n"
            )
            sys.exit(1)

    result = install(
        project_path=args.project_path,
        scope=scope,
        tool_filter=tool_filter,
        dry_run=args.dry_run,
        auto_confirm=args.yes,
    )

    # Exit with error if nothing was registered and there were tools to register
    if not result.registered and not args.dry_run:
        sys.exit(0)


def _run_uninstall(args: argparse.Namespace) -> None:
    """Run the auto-uninstaller."""
    from ensemble_mcp.installer import TOOL_NAMES, InstallScope
    from ensemble_mcp.installer.setup import uninstall

    scope = InstallScope.LOCAL if args.local else InstallScope.GLOBAL

    tool_filter: set[str] | None = None
    if args.tools:
        tool_filter = {t.strip() for t in args.tools.split(",")}
        unknown = tool_filter - TOOL_NAMES
        if unknown:
            sys.stderr.write(
                f"Unknown tool(s): {', '.join(sorted(unknown))}\n"
                f"Available: {', '.join(sorted(TOOL_NAMES))}\n"
            )
            sys.exit(1)

    uninstall(
        project_path=args.project_path,
        scope=scope,
        tool_filter=tool_filter,
        remove_agents=args.remove_agents,
        clean_data=args.clean_data,
        dry_run=args.dry_run,
        auto_confirm=args.yes,
    )


def _run_add_agents(args: argparse.Namespace) -> None:
    """Copy bundled agent files to tool-specific directories."""
    from ensemble_mcp.installer import TOOL_NAMES, InstallScope
    from ensemble_mcp.installer.setup import add_agents

    scope = InstallScope.LOCAL if args.local else InstallScope.GLOBAL

    tool_filter: set[str] | None = None
    if args.tools:
        tool_filter = {t.strip() for t in args.tools.split(",")}
        unknown = tool_filter - TOOL_NAMES
        if unknown:
            sys.stderr.write(
                f"Unknown tool(s): {', '.join(sorted(unknown))}\n"
                f"Available: {', '.join(sorted(TOOL_NAMES))}\n"
            )
            sys.exit(1)

    add_agents(
        project_path=args.project_path,
        scope=scope,
        tool_filter=tool_filter,
        dry_run=args.dry_run,
        auto_confirm=args.yes,
    )


def _run_add_skills(args: argparse.Namespace) -> None:
    """Copy bundled skill files to tool-specific directories."""
    from ensemble_mcp.installer import TOOL_NAMES, InstallScope
    from ensemble_mcp.installer.setup import add_skills

    # add-skills defaults to LOCAL; --global overrides to GLOBAL
    scope = InstallScope.GLOBAL if args.use_global else InstallScope.LOCAL

    tool_filter: set[str] | None = None
    if args.tools:
        tool_filter = {t.strip() for t in args.tools.split(",")}
        unknown = tool_filter - TOOL_NAMES
        if unknown:
            sys.stderr.write(
                f"Unknown tool(s): {', '.join(sorted(unknown))}\n"
                f"Available: {', '.join(sorted(TOOL_NAMES))}\n"
            )
            sys.exit(1)

    add_skills(
        project_path=args.project_path,
        scope=scope,
        tool_filter=tool_filter,
        dry_run=args.dry_run,
        auto_confirm=args.yes,
    )


def _run_dashboard(args: argparse.Namespace) -> None:
    """Render and display the metrics dashboard."""
    from ensemble_mcp.cli.dashboard import run_dashboard

    run_dashboard(
        db_path=args.db_path,
        days=args.days,
        limit=args.limit,
        trend_days=args.trend_days,
    )


def _run_backfill(args: argparse.Namespace) -> None:
    """Backfill session steps with real token data from AI tool session files."""
    from ensemble_mcp.config.defaults import DB_PATH
    from ensemble_mcp.state.locks import get_connection
    from ensemble_mcp.tools.backfill import backfill_session

    db_path = args.db_path or DB_PATH
    if not db_path.exists():
        sys.stderr.write(f"Database not found: {db_path}\n")
        sys.exit(1)

    conn = get_connection(db_path)
    try:
        result = backfill_session(
            conn,
            session_id=args.session_id,
            force=args.force,
            ai_tool_override=args.ai_tool,
        )

        # Print summary
        print(f"Backfill complete for session {result.session_id}")
        print(f"  Steps updated:           {result.steps_updated}")
        print(f"  Steps skipped (existing): {result.steps_skipped}")
        print(f"  Steps unmatched (DB):     {result.steps_unmatched_db}")
        print(f"  Steps unmatched (parser): {result.steps_unmatched_parser}")
        print(f"  Confidence:              {result.confidence}")

        if result.before and result.after:
            print()
            print("  Before:")
            print(f"    input_tokens:  {result.before.get('total_input_tokens', 0):>10,}")
            print(f"    output_tokens: {result.before.get('total_output_tokens', 0):>10,}")
            print(f"    cost_usd:      ${result.before.get('total_cost_usd', 0):>10.6f}")
            print()
            print("  After:")
            print(f"    input_tokens:  {result.after.get('total_input_tokens', 0):>10,}")
            print(f"    output_tokens: {result.after.get('total_output_tokens', 0):>10,}")
            print(f"    cost_usd:      ${result.after.get('total_cost_usd', 0):>10.6f}")

        if result.errors:
            print()
            print("  Errors:")
            for err in result.errors:
                print(f"    - {err}")

    except Exception as exc:
        sys.stderr.write(f"Backfill failed: {exc}\n")
        sys.exit(1)
    finally:
        conn.close()


def _run_watch(args: argparse.Namespace) -> None:
    """Start the file watcher daemon for automatic backfill."""
    import logging as _logging

    try:
        from ensemble_mcp.watcher import WatcherEngine
    except ImportError:
        sys.stderr.write(
            "The 'watchdog' package is required for the watch command.\n"
            "Install it with:  pip install ensemble-mcp[watch]\n"
        )
        sys.exit(1)

    # Configure logging for the watcher (stderr so it doesn't conflict with stdout)
    _logging.basicConfig(
        level=_logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    kwargs: dict[str, object] = {}
    if args.debounce is not None:
        kwargs["debounce_seconds"] = args.debounce
    if args.poll_interval is not None:
        kwargs["poll_interval"] = args.poll_interval
    if args.ai_tool is not None:
        kwargs["ai_tool"] = args.ai_tool
    if args.db_path is not None:
        kwargs["db_path"] = args.db_path

    try:
        engine = WatcherEngine(**kwargs)  # type: ignore[arg-type]
        engine.run()
    except RuntimeError as exc:
        sys.stderr.write(f"Watch failed: {exc}\n")
        sys.exit(1)
    except ImportError as exc:
        sys.stderr.write(f"{exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
