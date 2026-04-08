"""Agent and skill file discovery and copying.

Looks for bundled agent files in the package's ``data/agents/`` directory
and prepares a copy plan to tool-specific agent directories (e.g.
``.opencode/agents/`` for OpenCode, ``.claude/agents/`` for Claude Code).

Also discovers bundled skill files in ``data/skills/`` and copies them
to tool-specific skill directories, using the correct format per tool
(flat ``.md`` files or ``<name>/SKILL.md`` directory layout).

Bundled agents include the 7-agent orchestration pipeline:
team-ensemble, team-scope, team-craft, team-forge,
team-trace, team-lens, and team-signal.

Bundled skills include the ensemble-mcp workflow skill that teaches
AI agents when and how to invoke ensemble-mcp tools.
"""

from __future__ import annotations

from pathlib import Path

from . import InstallScope, SkillFormat, ToolDefinition

# Relative to this file: src/ensemble_mcp/installer/agents.py
# Bundled agents would live at: src/ensemble_mcp/data/agents/
# Bundled skills would live at: src/ensemble_mcp/data/skills/
_PACKAGE_DIR = Path(__file__).resolve().parent.parent
_BUNDLED_AGENTS_DIR = _PACKAGE_DIR / "data" / "agents"
_BUNDLED_SKILLS_DIR = _PACKAGE_DIR / "data" / "skills"


def _resolve_agents_dir(
    tool: ToolDefinition,
    project_path: Path,
    scope: InstallScope,
) -> Path | None:
    """Resolve the destination directory for agent files.

    Returns ``None`` if the tool has no agent directory configured for
    the given scope, meaning agent copying should be skipped.
    """
    if scope == InstallScope.GLOBAL:
        return tool.global_agents_dir
    # LOCAL scope
    if tool.local_agents_dir is not None:
        return project_path / tool.local_agents_dir
    return None


def _resolve_skills_dir(
    tool: ToolDefinition,
    project_path: Path,
    scope: InstallScope,
) -> Path | None:
    """Resolve the destination directory for skill files.

    Returns ``None`` if the tool has no skill directory configured for
    the given scope, meaning skill copying should be skipped.
    """
    if scope == InstallScope.GLOBAL:
        return tool.global_skills_dir
    # LOCAL scope
    if tool.local_skills_dir is not None:
        return project_path / tool.local_skills_dir
    return None


def discover_agents(
    project_path: Path,
    tools: list[ToolDefinition] | None = None,
    scope: InstallScope = InstallScope.GLOBAL,
) -> list[tuple[Path, Path]]:
    """Discover bundled agent files and build a copy plan.

    Args:
        project_path: Absolute path to the project root.
        tools: Tool definitions to determine destination directories.
            When ``None``, returns an empty list (no tool-agnostic fallback).
        scope: Whether to use global or local agent directories.

    Returns:
        List of ``(source, destination)`` tuples. Empty if no bundled
        agents are available or all already exist at the destination.
        Destinations are de-duplicated across tools.
    """
    if not _BUNDLED_AGENTS_DIR.is_dir():
        return []

    if not tools:
        return []

    # Collect unique destination roots across tools
    dest_roots: list[Path] = []
    seen: set[Path] = set()
    for tool in tools:
        dest_root = _resolve_agents_dir(tool, project_path, scope)
        if dest_root is not None and dest_root not in seen:
            dest_roots.append(dest_root)
            seen.add(dest_root)

    if not dest_roots:
        return []

    pairs: list[tuple[Path, Path]] = []
    # Track destinations we've already added to avoid duplicates
    added_destinations: set[Path] = set()

    for dest_root in dest_roots:
        for source in sorted(_BUNDLED_AGENTS_DIR.rglob("*")):
            if not source.is_file():
                continue

            # Preserve directory structure relative to the agents dir
            relative = source.relative_to(_BUNDLED_AGENTS_DIR)
            destination = dest_root / relative

            # Skip if already exists at destination or already in plan
            if destination.exists() or destination in added_destinations:
                continue

            pairs.append((source, destination))
            added_destinations.add(destination)

    return pairs


def discover_skills(
    project_path: Path,
    tools: list[ToolDefinition] | None = None,
    scope: InstallScope = InstallScope.LOCAL,
) -> list[tuple[Path, Path]]:
    """Discover bundled skill files and build a copy plan.

    Args:
        project_path: Absolute path to the project root.
        tools: Tool definitions to determine destination directories and
            skill file format. When ``None``, returns an empty list.
        scope: Whether to use global or local skill directories.

    Returns:
        List of ``(source, destination)`` tuples. Empty if no bundled
        skills are available or all already exist at the destination.
        Destinations are de-duplicated across tools.

    For tools with ``skill_format == SkillFormat.DIRECTORY`` (e.g. OpenCode),
    a source file ``foo-bar.md`` is placed as ``<skills_dir>/foo-bar/SKILL.md``.
    For ``SkillFormat.FLAT``, it is placed as ``<skills_dir>/foo-bar.md``.
    """
    if not _BUNDLED_SKILLS_DIR.is_dir():
        return []

    if not tools:
        return []

    # Collect unique (dest_root, skill_format) pairs across tools
    dest_configs: list[tuple[Path, SkillFormat]] = []
    seen: set[Path] = set()
    for tool in tools:
        dest_root = _resolve_skills_dir(tool, project_path, scope)
        if dest_root is not None and dest_root not in seen:
            dest_configs.append((dest_root, tool.skill_format))
            seen.add(dest_root)

    if not dest_configs:
        return []

    pairs: list[tuple[Path, Path]] = []
    added_destinations: set[Path] = set()

    for dest_root, skill_format in dest_configs:
        for source in sorted(_BUNDLED_SKILLS_DIR.rglob("*")):
            if not source.is_file():
                continue

            relative = source.relative_to(_BUNDLED_SKILLS_DIR)

            if skill_format == SkillFormat.DIRECTORY:
                # e.g. ensemble-mcp-workflow.md → ensemble-mcp-workflow/SKILL.md
                skill_name = relative.stem  # strip .md
                destination = dest_root / skill_name / "SKILL.md"
            else:
                # Flat: preserve original filename
                destination = dest_root / relative

            # Skip if already exists at destination or already in plan
            if destination.exists() or destination in added_destinations:
                continue

            pairs.append((source, destination))
            added_destinations.add(destination)

    return pairs
