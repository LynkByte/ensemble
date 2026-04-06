"""Entry point: python -m ensemble_mcp.

Provides two subcommands:
  - ``serve`` (default): Start the MCP server on stdio.
  - ``install``: Detect AI tools and register ensemble-mcp in their configs.
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

    args = parser.parse_args()

    # Default to serve when no subcommand is given
    if args.command is None or args.command == "serve":
        _run_serve()
    elif args.command == "install":
        _run_install(args)
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


if __name__ == "__main__":
    main()
