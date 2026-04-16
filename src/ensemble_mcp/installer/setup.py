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
    SkillFormat,
    ToolDefinition,
    UninstallPlan,
    UninstallResult,
    detect_server_command,
)
from .agents import (
    _resolve_agents_dir,
    _resolve_skills_dir,
    discover_agents,
    discover_skills,
)
from .registry import (
    create_backup,
    deregister_mcp,
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

    # Collect tool definitions from detected tools for agent/skill discovery.
    # Use ALL detected tools (both to-register and already-registered) so
    # agent/skill files are copied for every installed tool.
    all_tool_defs = [t.definition for t in detected]

    # Discover agent files for copying (global scope by default for agents)
    plan.agents_to_copy = discover_agents(project_path, all_tool_defs, scope)

    # Discover skill files for copying (local scope by default for skills)
    skills_scope = InstallScope.LOCAL if scope == InstallScope.GLOBAL else scope
    plan.skills_to_copy = discover_skills(project_path, all_tool_defs, skills_scope)

    return plan


# ── Display ───────────────────────────────────────────────────────


def display_plan(plan: InstallPlan) -> str:
    """Format the install plan as a human-readable string for confirmation."""
    lines: list[str] = []

    lines.append("")
    lines.append("╔══════════════════════════════════════════════════════════╗")
    lines.append("║  ENSEMBLE-MCP INSTALL PLAN                              ║")
    lines.append("╠══════════════════════════════════════════════════════════╣")

    cmd_parts = detect_server_command()
    cmd_display = " ".join(cmd_parts)
    lines.append(f"║  Using command: {cmd_display}".ljust(59) + "║")
    lines.append("║                                                          ║")

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

    if plan.skills_to_copy:
        lines.append("║  Will copy skill files:                                  ║")
        for _src, dst in plan.skills_to_copy:
            lines.append(f"║    ✓ {dst.name}")
            lines.append(f"║      → {dst}")
        lines.append("║                                                          ║")

    if plan.skipped:
        lines.append("║  Skipped:                                                ║")
        for name, reason in plan.skipped:
            lines.append(f"║    ─ {name}: {reason}")
        lines.append("║                                                          ║")

    if not plan.tools_to_register and not plan.agents_to_copy and not plan.skills_to_copy:
        lines.append("║                                                          ║")
        lines.append("║  Nothing to do — ensemble-mcp is already registered      ║")
        lines.append("║  in all detected AI tools.                               ║")
        lines.append("║                                                          ║")

    lines.append("╚══════════════════════════════════════════════════════════╝")
    lines.append("")

    return "\n".join(lines)


# ── Execution ─────────────────────────────────────────────────────


def execute_plan(plan: InstallPlan) -> InstallResult:
    """Execute the install plan: register MCP in configs, copy agents and skills.

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

    # Copy skill files
    for src, dst in plan.skills_to_copy:
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
    if not plan.tools_to_register and not plan.agents_to_copy and not plan.skills_to_copy:
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


# ══════════════════════════════════════════════════════════════════
# ADD-AGENTS / ADD-SKILLS  (standalone agent/skill copy commands)
# ══════════════════════════════════════════════════════════════════


def _resolve_tool_defs(tool_filter: set[str] | None) -> list[ToolDefinition]:
    """Resolve tool definitions by name — no detection/installation required.

    Unlike ``detect_ai_tools``, this returns definitions purely by name
    lookup.  When *tool_filter* is ``None``, **all** known definitions
    are returned.
    """
    if tool_filter is None:
        return list(TOOL_DEFINITIONS)
    return [td for td in TOOL_DEFINITIONS if td.name in tool_filter]


def display_copy_plan(
    label: str,
    pairs: list[tuple[Path, Path]],
) -> str:
    """Format a list of ``(source, destination)`` copy pairs for display."""
    lines: list[str] = []

    lines.append("")
    header = f"ENSEMBLE-MCP {label.upper()} PLAN"
    lines.append("╔══════════════════════════════════════════════════════════╗")
    lines.append(f"║  {header:<55}║")
    lines.append("╠══════════════════════════════════════════════════════════╣")

    if pairs:
        lines.append("║                                                          ║")
        lines.append(f"║  Will copy {label} files:".ljust(59) + "║")
        for _src, dst in pairs:
            lines.append(f"║    ✓ {dst.name}")
            lines.append(f"║      → {dst}")
        lines.append("║                                                          ║")
    else:
        lines.append("║                                                          ║")
        lines.append(f"║  Nothing to do — all {label} files already exist.".ljust(59) + "║")
        lines.append("║                                                          ║")

    lines.append("╚══════════════════════════════════════════════════════════╝")
    lines.append("")

    return "\n".join(lines)


def add_agents(
    project_path: Path | None = None,
    scope: InstallScope = InstallScope.GLOBAL,
    tool_filter: set[str] | None = None,
    dry_run: bool = False,
    auto_confirm: bool = False,
) -> InstallResult:
    """Copy bundled agent files to tool-specific directories.

    Unlike ``install``, this does **not** register MCP in any config.
    It also does **not** require the AI tool to be installed — it uses
    the known ``ToolDefinition`` paths directly.

    Args:
        project_path: Project root directory.  Defaults to cwd.
        scope: ``GLOBAL`` copies to global agent dirs (e.g.
            ``~/.config/opencode/agents/``); ``LOCAL`` copies to
            project-local dirs (e.g. ``.opencode/agents/``).
        tool_filter: Restrict to specific tool names.
        dry_run: Show the plan without making changes.
        auto_confirm: Skip the confirmation prompt.

    Returns:
        ``InstallResult`` with the ``copied`` field populated.
    """
    if project_path is None:
        project_path = Path.cwd()
    project_path = project_path.resolve()

    tool_defs = _resolve_tool_defs(tool_filter)
    pairs = discover_agents(project_path, tool_defs, scope)

    plan_text = display_copy_plan("agent", pairs)
    sys.stdout.write(plan_text)

    if dry_run:
        sys.stdout.write("Dry run — no changes made.\n")
        return InstallResult()

    if not pairs:
        return InstallResult()

    if not auto_confirm:
        try:
            answer = input("Proceed? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.stdout.write("\nAborted.\n")
            return InstallResult()
        if answer not in ("y", "yes"):
            sys.stdout.write("Aborted.\n")
            return InstallResult()

    result = InstallResult()
    for src, dst in pairs:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copy2(src, dst)
            result.copied.append(dst)
        except Exception as exc:
            result.skipped.append((dst.name, f"copy error: {exc}"))

    result_text = display_result(result)
    sys.stdout.write(result_text)
    return result


def add_skills(
    project_path: Path | None = None,
    scope: InstallScope = InstallScope.LOCAL,
    tool_filter: set[str] | None = None,
    dry_run: bool = False,
    auto_confirm: bool = False,
) -> InstallResult:
    """Copy bundled skill files to tool-specific directories.

    Unlike ``install``, this does **not** register MCP in any config.
    It also does **not** require the AI tool to be installed — it uses
    the known ``ToolDefinition`` paths directly.

    Args:
        project_path: Project root directory.  Defaults to cwd.
        scope: ``LOCAL`` copies to project-local skill dirs (e.g.
            ``.opencode/skills/``); ``GLOBAL`` copies to global dirs.
        tool_filter: Restrict to specific tool names.
        dry_run: Show the plan without making changes.
        auto_confirm: Skip the confirmation prompt.

    Returns:
        ``InstallResult`` with the ``copied`` field populated.
    """
    if project_path is None:
        project_path = Path.cwd()
    project_path = project_path.resolve()

    tool_defs = _resolve_tool_defs(tool_filter)
    pairs = discover_skills(project_path, tool_defs, scope)

    plan_text = display_copy_plan("skill", pairs)
    sys.stdout.write(plan_text)

    if dry_run:
        sys.stdout.write("Dry run — no changes made.\n")
        return InstallResult()

    if not pairs:
        return InstallResult()

    if not auto_confirm:
        try:
            answer = input("Proceed? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.stdout.write("\nAborted.\n")
            return InstallResult()
        if answer not in ("y", "yes"):
            sys.stdout.write("Aborted.\n")
            return InstallResult()

    result = InstallResult()
    for src, dst in pairs:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copy2(src, dst)
            result.copied.append(dst)
        except Exception as exc:
            result.skipped.append((dst.name, f"copy error: {exc}"))

    result_text = display_result(result)
    sys.stdout.write(result_text)
    return result


# ══════════════════════════════════════════════════════════════════
# UNINSTALL
# ══════════════════════════════════════════════════════════════════

# Default agent filenames that the installer copies
_AGENT_FILES = [
    "team-ensemble.md",
    "team-scope.md",
    "team-craft.md",
    "team-forge.md",
    "team-lens.md",
    "team-signal.md",
    "team-trace.md",
]

# Default skill filenames that the installer copies
_SKILL_FILES = [
    "ensemble-mcp-workflow.md",
]

_CACHE_DIR = Path.home() / ".cache" / "ensemble-mcp"
_CONFIG_DIR = Path.home() / ".config" / "ensemble-mcp"


# ── Uninstall planning ───────────────────────────────────────────


def plan_uninstall(
    project_path: Path,
    scope: InstallScope = InstallScope.GLOBAL,
    tool_filter: set[str] | None = None,
    remove_agents: bool = False,
    clean_data: bool = False,
) -> UninstallPlan:
    """Build an uninstall plan: what tools to deregister, what to remove.

    Does NOT modify any files.
    """
    plan = UninstallPlan()
    plan.clean_data = clean_data
    detected = detect_ai_tools(project_path, scope, tool_filter)

    for tool in detected:
        if tool.already_registered:
            plan.tools_to_deregister.append(tool)
        else:
            plan.skipped.append((tool.definition.display_name, "not registered"))

    # Check for tools in the filter that were not detected at all
    if tool_filter:
        detected_names = {t.definition.name for t in detected}
        for name in tool_filter:
            if name not in detected_names and name in TOOL_NAMES:
                for td in TOOL_DEFINITIONS:
                    if td.name == name:
                        plan.skipped.append((td.display_name, "not installed"))
                        break

    # Discover agent and skill files for removal
    if remove_agents:
        # Build the set of all tool definitions we detected
        all_tool_defs = [t.definition for t in detected]

        # Also include definitions from the filter that weren't detected
        # (the user may have manually placed files for a tool that's since
        # been uninstalled)
        if not all_tool_defs:
            all_tool_defs = list(TOOL_DEFINITIONS)

        seen_agent_paths: set[Path] = set()
        seen_skill_paths: set[Path] = set()

        for td in all_tool_defs:
            # Agent files
            agents_dir = _resolve_agents_dir(td, project_path, scope)
            if agents_dir is not None:
                for filename in _AGENT_FILES:
                    agent_path = agents_dir / filename
                    if agent_path.exists() and agent_path not in seen_agent_paths:
                        plan.agents_to_remove.append(agent_path)
                        seen_agent_paths.add(agent_path)

            # Skill files
            skills_scope = InstallScope.LOCAL if scope == InstallScope.GLOBAL else scope
            skills_dir = _resolve_skills_dir(td, project_path, skills_scope)
            if skills_dir is not None:
                for filename in _SKILL_FILES:
                    if td.skill_format == SkillFormat.DIRECTORY:
                        # e.g. ensemble-mcp-workflow.md → ensemble-mcp-workflow/SKILL.md
                        skill_name = Path(filename).stem
                        skill_path = skills_dir / skill_name / "SKILL.md"
                    else:
                        skill_path = skills_dir / filename
                    if skill_path.exists() and skill_path not in seen_skill_paths:
                        plan.skills_to_remove.append(skill_path)
                        seen_skill_paths.add(skill_path)

        # Also check legacy paths (.agents/ and .ai/skills/) for backwards compat
        legacy_agents_dir = project_path / ".agents"
        for filename in _AGENT_FILES:
            agent_path = legacy_agents_dir / filename
            if agent_path.exists() and agent_path not in seen_agent_paths:
                plan.agents_to_remove.append(agent_path)
                seen_agent_paths.add(agent_path)

        legacy_skills_dir = project_path / ".ai" / "skills"
        for filename in _SKILL_FILES:
            skill_path = legacy_skills_dir / filename
            if skill_path.exists() and skill_path not in seen_skill_paths:
                plan.skills_to_remove.append(skill_path)
                seen_skill_paths.add(skill_path)

    return plan


# ── Uninstall display ────────────────────────────────────────────


def display_uninstall_plan(plan: UninstallPlan) -> str:
    """Format the uninstall plan as a human-readable string."""
    lines: list[str] = []

    lines.append("")
    lines.append("╔══════════════════════════════════════════════════════════╗")
    lines.append("║  ENSEMBLE-MCP UNINSTALL PLAN                            ║")
    lines.append("╠══════════════════════════════════════════════════════════╣")

    if plan.tools_to_deregister:
        lines.append("║                                                          ║")
        lines.append("║  Will remove MCP server from:                            ║")
        for tool in plan.tools_to_deregister:
            name = tool.definition.display_name
            scope_label = f"({tool.scope.value})"
            lines.append(f"║    ✗ {name} {scope_label}")
            lines.append(f"║      → {tool.config_path}")
        lines.append("║                                                          ║")

    if plan.agents_to_remove:
        lines.append("║  Will remove agent files:                                ║")
        for path in plan.agents_to_remove:
            lines.append(f"║    ✗ {path.name}")
            lines.append(f"║      → {path}")
        lines.append("║                                                          ║")

    if plan.skills_to_remove:
        lines.append("║  Will remove skill files:                                ║")
        for path in plan.skills_to_remove:
            lines.append(f"║    ✗ {path.name}")
            lines.append(f"║      → {path}")
        lines.append("║                                                          ║")

    if plan.clean_data:
        lines.append("║  Will remove cached data:                                ║")
        if _CACHE_DIR.exists():
            lines.append(f"║    ✗ {_CACHE_DIR}")
        if _CONFIG_DIR.exists():
            lines.append(f"║    ✗ {_CONFIG_DIR}")
        lines.append("║                                                          ║")

    if plan.skipped:
        lines.append("║  Skipped:                                                ║")
        for name, reason in plan.skipped:
            lines.append(f"║    ─ {name}: {reason}")
        lines.append("║                                                          ║")

    nothing_to_do = (
        not plan.tools_to_deregister
        and not plan.agents_to_remove
        and not plan.skills_to_remove
        and not plan.clean_data
    )
    if nothing_to_do:
        lines.append("║                                                          ║")
        lines.append("║  Nothing to do — ensemble-mcp is not registered          ║")
        lines.append("║  in any detected AI tools.                               ║")
        lines.append("║                                                          ║")

    lines.append("╚══════════════════════════════════════════════════════════╝")
    lines.append("")

    return "\n".join(lines)


# ── Uninstall execution ──────────────────────────────────────────


def execute_uninstall_plan(plan: UninstallPlan) -> UninstallResult:
    """Execute the uninstall plan: deregister MCP, remove agents/skills, clean data.

    Creates backups of each config file before modification.
    """
    import shutil

    result = UninstallResult()
    result.skipped = list(plan.skipped)

    # Deregister MCP from tool configs
    for tool in plan.tools_to_deregister:
        try:
            _deregister_tool(tool, result)
        except Exception as exc:
            result.skipped.append((tool.definition.display_name, f"error: {exc}"))

    # Remove agent files
    for path in plan.agents_to_remove:
        try:
            path.unlink()
            result.removed.append(path)
        except Exception as exc:
            result.skipped.append((path.name, f"remove error: {exc}"))

    # Remove skill files
    for path in plan.skills_to_remove:
        try:
            path.unlink()
            result.removed.append(path)
        except Exception as exc:
            result.skipped.append((path.name, f"remove error: {exc}"))

    # Clean cached data directories
    if plan.clean_data:
        for data_dir in (_CACHE_DIR, _CONFIG_DIR):
            if data_dir.exists():
                try:
                    shutil.rmtree(data_dir)
                    result.removed.append(data_dir)
                except Exception as exc:
                    result.skipped.append((str(data_dir), f"clean error: {exc}"))
        result.data_cleaned = True

    return result


def _deregister_tool(tool: DetectedTool, result: UninstallResult) -> None:
    """Remove ensemble-mcp from a single tool's config file."""
    # Backup existing config
    backup = create_backup(tool.config_path)
    if backup is not None:
        result.backups.append(backup)

    # Read, modify, write
    config = read_config(tool.config_path)
    deregister_mcp(config, tool.definition)
    write_config(tool.config_path, config, tool.definition.config_format)

    result.deregistered.append(tool.definition.display_name)


# ── Uninstall result display ─────────────────────────────────────


def display_uninstall_result(result: UninstallResult) -> str:
    """Format the uninstall result as a human-readable summary."""
    lines: list[str] = []

    lines.append("")
    if result.deregistered:
        lines.append("Removed ensemble-mcp from:")
        for name in result.deregistered:
            lines.append(f"  ✗ {name}")

    if result.removed:
        lines.append("Removed files/directories:")
        for path in result.removed:
            lines.append(f"  ✗ {path}")

    if result.backups:
        lines.append("Backups created:")
        for path in result.backups:
            lines.append(f"  ↩ {path}")

    if result.skipped:
        lines.append("Skipped:")
        for name, reason in result.skipped:
            lines.append(f"  ─ {name}: {reason}")

    if not result.deregistered and not result.removed:
        lines.append("No changes were made.")

    lines.append("")
    return "\n".join(lines)


# ── Uninstall entry point ────────────────────────────────────────


def uninstall(
    project_path: Path | None = None,
    scope: InstallScope = InstallScope.GLOBAL,
    tool_filter: set[str] | None = None,
    remove_agents: bool = False,
    clean_data: bool = False,
    dry_run: bool = False,
    auto_confirm: bool = False,
) -> UninstallResult:
    """Run the full uninstall flow: detect → plan → confirm → execute.

    Args:
        project_path: Project root directory. Defaults to cwd.
        scope: Global or project-local config deregistration.
        tool_filter: Restrict to specific tool names (e.g. {"opencode", "cursor"}).
        remove_agents: Also remove agent/skill files from tool-specific directories.
        clean_data: Also remove ~/.cache/ensemble-mcp/ and ~/.config/ensemble-mcp/.
        dry_run: If True, display the plan but do not execute.
        auto_confirm: If True, skip interactive confirmation.

    Returns:
        UninstallResult with what was done.
    """
    if project_path is None:
        project_path = Path.cwd()

    project_path = project_path.resolve()

    plan = plan_uninstall(project_path, scope, tool_filter, remove_agents, clean_data)

    # Display the plan
    plan_text = display_uninstall_plan(plan)
    sys.stdout.write(plan_text)

    if dry_run:
        sys.stdout.write("Dry run — no changes made.\n")
        return UninstallResult(skipped=plan.skipped)

    # Nothing to do?
    nothing_to_do = (
        not plan.tools_to_deregister
        and not plan.agents_to_remove
        and not plan.skills_to_remove
        and not plan.clean_data
    )
    if nothing_to_do:
        return UninstallResult(skipped=plan.skipped)

    # Confirm
    if not auto_confirm:
        try:
            answer = input("Proceed with uninstall? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.stdout.write("\nAborted.\n")
            return UninstallResult(skipped=plan.skipped)

        if answer not in ("y", "yes"):
            sys.stdout.write("Aborted.\n")
            return UninstallResult(skipped=plan.skipped)

    # Execute
    result = execute_uninstall_plan(plan)

    # Show result
    result_text = display_uninstall_result(result)
    sys.stdout.write(result_text)

    return result
