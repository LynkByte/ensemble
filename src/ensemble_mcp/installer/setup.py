"""Auto-detect AI tools, plan installation, and execute MCP registration.

Orchestrates the full install flow: detect → plan → confirm → execute.

Supports: OpenCode, Claude Code, GitHub Copilot, Cursor, Windsurf, Devin CLI.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import (
    TOOL_DEFINITIONS,
    TOOL_NAMES,
    DetectedTool,
    InstallPlan,
    InstallResult,
    InstallScope,
    ToolDefinition,
)
from .agents import discover_agents
from .registry import (
    create_backup,
    is_registered,
    read_config,
    register_mcp,
    write_config,
)

# ── Detection ─────────────────────────────────────────────────────


def detect_ai_tools(
    project_path: Path,
    scope: InstallScope = InstallScope.GLOBAL,
    tool_filter: set[str] | None = None,
) -> list[DetectedTool]:
    """Detect which AI tools are installed on the system.

    Args:
        project_path: Absolute path to the project root.
        scope: Whether to target global or project-local config files.
        tool_filter: If set, only detect tools whose name is in this set.

    Returns:
        List of detected tools with their resolved config paths.
    """
    detected: list[DetectedTool] = []

    for definition in TOOL_DEFINITIONS:
        if tool_filter and definition.name not in tool_filter:
            continue

        config_path = _resolve_config_path(definition, project_path, scope)

        # Check if the tool is installed by looking for detection paths
        # OR if a local config already exists at the project level
        is_installed = _is_tool_installed(definition, project_path, scope)
        if not is_installed:
            continue

        # Read existing config to check if already registered
        existing_config = read_config(config_path)
        already = is_registered(existing_config, definition)

        detected.append(
            DetectedTool(
                definition=definition,
                config_path=config_path,
                scope=scope,
                already_registered=already,
            )
        )

    return detected


def _resolve_config_path(
    definition: ToolDefinition,
    project_path: Path,
    scope: InstallScope,
) -> Path:
    """Determine the config file path based on scope."""
    if scope == InstallScope.LOCAL:
        return project_path / definition.local_config_filename
    return definition.global_config_path


def _is_tool_installed(
    definition: ToolDefinition,
    project_path: Path,
    scope: InstallScope,
) -> bool:
    """Check if the tool is installed (global) or has a local config."""
    # In local scope, we always allow registration — the user explicitly
    # chose to register in the project regardless of global install state
    if scope == InstallScope.LOCAL:
        return True

    # In global scope, check for detection paths (config dirs, etc.)
    for detection_path in definition.detection_paths:
        if detection_path.exists():
            return True

    # Also check if a local config already exists (user may have the tool
    # configured at the project level even without a global install)
    local_config = project_path / definition.local_config_filename
    return local_config.exists()


# ── Planning ──────────────────────────────────────────────────────


def plan_install(
    project_path: Path,
    scope: InstallScope = InstallScope.GLOBAL,
    tool_filter: set[str] | None = None,
) -> InstallPlan:
    """Build an install plan: what tools to register, what to skip.

    Does NOT modify any files.
    """
    plan = InstallPlan()
    detected = detect_ai_tools(project_path, scope, tool_filter)

    for tool in detected:
        if tool.already_registered:
            plan.skipped.append((tool.definition.display_name, "already registered"))
        else:
            plan.tools_to_register.append(tool)

    # Check for tools in the filter that were not detected at all
    if tool_filter:
        detected_names = {t.definition.name for t in detected}
        for name in tool_filter:
            if name not in detected_names and name in TOOL_NAMES:
                # Find display name
                for td in TOOL_DEFINITIONS:
                    if td.name == name:
                        plan.skipped.append((td.display_name, "not installed"))
                        break

    # Discover agent files for copying
    plan.agents_to_copy = discover_agents(project_path)

    return plan


# ── Display ───────────────────────────────────────────────────────


def display_plan(plan: InstallPlan) -> str:
    """Format the install plan as a human-readable string for confirmation."""
    lines: list[str] = []

    lines.append("")
    lines.append("╔══════════════════════════════════════════════════════════╗")
    lines.append("║  ENSEMBLE-MCP INSTALL PLAN                              ║")
    lines.append("╠══════════════════════════════════════════════════════════╣")

    if plan.tools_to_register:
        lines.append("║                                                          ║")
        lines.append("║  Will register MCP server in:                            ║")
        for tool in plan.tools_to_register:
            name = tool.definition.display_name
            path = str(tool.config_path)
            scope_label = f"({tool.scope.value})"
            lines.append(f"║    ✓ {name} {scope_label}")
            lines.append(f"║      → {path}")
        lines.append("║                                                          ║")

    if plan.agents_to_copy:
        lines.append("║  Will copy agent files:                                  ║")
        for _src, dst in plan.agents_to_copy:
            lines.append(f"║    ✓ {dst.name}")
            lines.append(f"║      → {dst}")
        lines.append("║                                                          ║")

    if plan.skipped:
        lines.append("║  Skipped:                                                ║")
        for name, reason in plan.skipped:
            lines.append(f"║    ─ {name}: {reason}")
        lines.append("║                                                          ║")

    if not plan.tools_to_register and not plan.agents_to_copy:
        lines.append("║                                                          ║")
        lines.append("║  Nothing to do — ensemble-mcp is already registered      ║")
        lines.append("║  in all detected AI tools.                               ║")
        lines.append("║                                                          ║")

    lines.append("╚══════════════════════════════════════════════════════════╝")
    lines.append("")

    return "\n".join(lines)


# ── Execution ─────────────────────────────────────────────────────


def execute_plan(plan: InstallPlan) -> InstallResult:
    """Execute the install plan: register MCP in configs, copy agents.

    Creates backups of each config file before modification.
    """
    result = InstallResult()
    result.skipped = list(plan.skipped)

    # Register MCP in tool configs
    for tool in plan.tools_to_register:
        try:
            _register_tool(tool, result)
        except Exception as exc:
            result.skipped.append((tool.definition.display_name, f"error: {exc}"))

    # Copy agent files
    for src, dst in plan.agents_to_copy:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copy2(src, dst)
            result.copied.append(dst)
        except Exception as exc:
            result.skipped.append((dst.name, f"copy error: {exc}"))

    return result


def _register_tool(tool: DetectedTool, result: InstallResult) -> None:
    """Register ensemble-mcp in a single tool's config file."""
    # Backup existing config
    backup = create_backup(tool.config_path)
    if backup is not None:
        result.backups.append(backup)

    # Read, modify, write
    config = read_config(tool.config_path)
    register_mcp(config, tool.definition)
    write_config(tool.config_path, config, tool.definition.config_format)

    result.registered.append(tool.definition.display_name)


# ── Display result ────────────────────────────────────────────────


def display_result(result: InstallResult) -> str:
    """Format the install result as a human-readable summary."""
    lines: list[str] = []

    lines.append("")
    if result.registered:
        lines.append("Registered ensemble-mcp in:")
        for name in result.registered:
            lines.append(f"  ✓ {name}")

    if result.copied:
        lines.append("Copied agent files:")
        for path in result.copied:
            lines.append(f"  ✓ {path}")

    if result.backups:
        lines.append("Backups created:")
        for path in result.backups:
            lines.append(f"  ↩ {path}")

    if result.skipped:
        lines.append("Skipped:")
        for name, reason in result.skipped:
            lines.append(f"  ─ {name}: {reason}")

    if not result.registered and not result.copied:
        lines.append("No changes were made.")

    lines.append("")
    return "\n".join(lines)


# ── Top-level entry point ────────────────────────────────────────


def install(
    project_path: Path | None = None,
    scope: InstallScope = InstallScope.GLOBAL,
    tool_filter: set[str] | None = None,
    dry_run: bool = False,
    auto_confirm: bool = False,
) -> InstallResult:
    """Run the full install flow: detect → plan → confirm → execute.

    Args:
        project_path: Project root directory. Defaults to cwd.
        scope: Global or project-local config registration.
        tool_filter: Restrict to specific tool names (e.g. {"opencode", "cursor"}).
        dry_run: If True, display the plan but do not execute.
        auto_confirm: If True, skip interactive confirmation.

    Returns:
        InstallResult with what was done.
    """
    if project_path is None:
        project_path = Path.cwd()

    project_path = project_path.resolve()

    plan = plan_install(project_path, scope, tool_filter)

    # Display the plan
    plan_text = display_plan(plan)
    sys.stdout.write(plan_text)

    if dry_run:
        sys.stdout.write("Dry run — no changes made.\n")
        return InstallResult(skipped=plan.skipped)

    # Nothing to do?
    if not plan.tools_to_register and not plan.agents_to_copy:
        return InstallResult(skipped=plan.skipped)

    # Confirm
    if not auto_confirm:
        try:
            answer = input("Proceed? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.stdout.write("\nAborted.\n")
            return InstallResult(skipped=plan.skipped)

        if answer not in ("y", "yes"):
            sys.stdout.write("Aborted.\n")
            return InstallResult(skipped=plan.skipped)

    # Execute
    result = execute_plan(plan)

    # Show result
    result_text = display_result(result)
    sys.stdout.write(result_text)

    return result
