"""Entry point: python -m ensemble_mcp.

Provides four subcommands:
  - ``serve`` (default): Start the MCP server on stdio.
  - ``install``: Detect AI tools and register ensemble-mcp in their configs.
  - ``uninstall``: Remove ensemble-mcp registration from AI tool configs.
  - ``dashboard``: Display a terminal-based metrics dashboard.
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
        help="Also remove agent files from the project's .agents/ directory.",
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

    args = parser.parse_args()

    # Default to serve when no subcommand is given
    if args.command is None or args.command == "serve":
        _run_serve()
    elif args.command == "install":
        _run_install(args)
    elif args.command == "uninstall":
        _run_uninstall(args)
    elif args.command == "dashboard":
        _run_dashboard(args)
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


def _run_dashboard(args: argparse.Namespace) -> None:
    """Render and display the metrics dashboard."""
    from ensemble_mcp.cli.dashboard import run_dashboard

    run_dashboard(
        db_path=args.db_path,
        days=args.days,
        limit=args.limit,
        trend_days=args.trend_days,
    )


if __name__ == "__main__":
    main()
