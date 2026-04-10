"""Entry point: python -m ensemble_mcp.

Provides six subcommands:
  - ``serve`` (default): Start the MCP server on stdio.
  - ``web``: Start the local web dashboard.
  - ``install``: Detect AI tools and register ensemble-mcp in their configs.
  - ``uninstall``: Remove ensemble-mcp registration from AI tool configs.
  - ``add-agents``: Copy bundled agent files to tool-specific directories.
  - ``add-skills``: Copy bundled skill files to tool-specific directories.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate command."""
    parser = argparse.ArgumentParser(
        prog="ensemble-mcp",
        description="MCP server for vector memory, drift detection, model routing, and more.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # ── serve (default) ───────────────────────────────────────────
    subparsers.add_parser(
        "serve",
        help="Start the MCP server (default when no command is given).",
    )

    # ── web ───────────────────────────────────────────────────────
    web_parser = subparsers.add_parser(
        "web",
        help="Start the local web dashboard.",
    )
    web_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind on (default: 8787).",
    )
    web_parser.add_argument(
        "--no-open",
        action="store_true",
        default=False,
        help="Don't auto-open browser.",
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

    args = parser.parse_args()

    # Default to serve when no subcommand is given
    if args.command is None or args.command == "serve":
        _run_serve()
    elif args.command == "web":
        _run_web(args)
    elif args.command == "install":
        _run_install(args)
    elif args.command == "uninstall":
        _run_uninstall(args)
    elif args.command == "add-agents":
        _run_add_agents(args)
    elif args.command == "add-skills":
        _run_add_skills(args)
    else:
        parser.print_help()
        sys.exit(1)


def _run_serve() -> None:
    """Start the MCP server."""
    from ensemble_mcp.server import serve

    serve()


def _run_web(args: argparse.Namespace) -> None:
    """Start the web dashboard."""
    from ensemble_mcp.config.defaults import DASHBOARD_DEFAULT_PORT
    from ensemble_mcp.dashboard import start_dashboard

    port = args.port if args.port is not None else DASHBOARD_DEFAULT_PORT
    open_browser = not args.no_open
    start_dashboard(port=port, open_browser=open_browser)


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


if __name__ == "__main__":
    main()
