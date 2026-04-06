"""Agent and skill file discovery and copying.

Looks for bundled agent files in the package's ``data/agents/`` directory
and prepares a copy plan to the project's ``.agents/`` directory (or
tool-native locations).

Also discovers bundled skill files in ``data/skills/`` and copies them
to the project's ``.ai/skills/`` directory.

Bundled agents include the 7-agent orchestration pipeline:
team-captain, team-architect, team-engineer, team-forge,
team-hunter, team-inspector, and team-shipper.

Bundled skills include the ensemble-mcp workflow skill that teaches
AI agents when and how to invoke ensemble-mcp tools.
"""

from __future__ import annotations

from pathlib import Path

# Relative to this file: src/ensemble_mcp/installer/agents.py
# Bundled agents would live at: src/ensemble_mcp/data/agents/
# Bundled skills would live at: src/ensemble_mcp/data/skills/
_PACKAGE_DIR = Path(__file__).resolve().parent.parent
_BUNDLED_AGENTS_DIR = _PACKAGE_DIR / "data" / "agents"
_BUNDLED_SKILLS_DIR = _PACKAGE_DIR / "data" / "skills"

# Default destinations inside the project
_DEFAULT_AGENTS_DIR = ".agents"
_DEFAULT_SKILLS_DIR = ".ai/skills"


def discover_agents(
    project_path: Path,
    agents_dir: str = _DEFAULT_AGENTS_DIR,
) -> list[tuple[Path, Path]]:
    """Discover bundled agent files and build a copy plan.

    Args:
        project_path: Absolute path to the project root.
        agents_dir: Relative directory within the project to copy agents to.

    Returns:
        List of ``(source, destination)`` tuples. Empty if no bundled
        agents are available or all already exist at the destination.
    """
    if not _BUNDLED_AGENTS_DIR.is_dir():
        return []

    pairs: list[tuple[Path, Path]] = []
    dest_root = project_path / agents_dir

    for source in sorted(_BUNDLED_AGENTS_DIR.rglob("*")):
        if not source.is_file():
            continue

        # Preserve directory structure relative to the agents dir
        relative = source.relative_to(_BUNDLED_AGENTS_DIR)
        destination = dest_root / relative

        # Skip if already exists at destination
        if destination.exists():
            continue

        pairs.append((source, destination))

    return pairs


def discover_skills(
    project_path: Path,
    skills_dir: str = _DEFAULT_SKILLS_DIR,
) -> list[tuple[Path, Path]]:
    """Discover bundled skill files and build a copy plan.

    Args:
        project_path: Absolute path to the project root.
        skills_dir: Relative directory within the project to copy skills to.

    Returns:
        List of ``(source, destination)`` tuples. Empty if no bundled
        skills are available or all already exist at the destination.
    """
    if not _BUNDLED_SKILLS_DIR.is_dir():
        return []

    pairs: list[tuple[Path, Path]] = []
    dest_root = project_path / skills_dir

    for source in sorted(_BUNDLED_SKILLS_DIR.rglob("*")):
        if not source.is_file():
            continue

        # Preserve directory structure relative to the skills dir
        relative = source.relative_to(_BUNDLED_SKILLS_DIR)
        destination = dest_root / relative

        # Skip if already exists at destination
        if destination.exists():
            continue

        pairs.append((source, destination))

    return pairs
