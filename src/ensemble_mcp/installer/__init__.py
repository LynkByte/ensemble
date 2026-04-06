"""Auto-installer for AI tool detection and MCP registration.

Detects installed AI tools (OpenCode, Claude Code, GitHub Copilot, Cursor,
Windsurf, Devin CLI), registers ensemble-mcp in their configs, and copies
agent files into the project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class ConfigFormat(StrEnum):
    """Supported config file formats."""

    TOML = "toml"
    JSON = "json"


class InstallScope(StrEnum):
    """Whether to modify global or project-local config files."""

    GLOBAL = "global"
    LOCAL = "local"


# ── Tool definitions ──────────────────────────────────────────────


@dataclass(slots=True)
class ToolDefinition:
    """Static definition of a supported AI tool and its config layout."""

    name: str
    display_name: str
    config_format: ConfigFormat
    global_config_path: Path
    local_config_filename: str
    mcp_section_path: list[str]
    """Dotted key path to the MCP servers section (e.g. ["mcp"] for OpenCode,
    ["mcpServers"] for Claude Code)."""
    detection_paths: list[Path]
    """Directories or files whose existence signals the tool is installed."""
    server_entry: dict[str, object]
    """The MCP server registration payload (value under the server key)."""


# ── Server name used as the key in MCP configs ───────────────────
MCP_SERVER_NAME = "ensemble"

_UVXENTRY: dict[str, object] = {
    "command": "uvx",
    "args": ["ensemble-mcp"],
}

_UVXENTRY_TYPED: dict[str, object] = {
    "type": "stdio",
    "command": "uvx",
    "args": ["ensemble-mcp"],
}

# ── Supported tool definitions ────────────────────────────────────

TOOL_DEFINITIONS: list[ToolDefinition] = [
    ToolDefinition(
        name="opencode",
        display_name="OpenCode",
        config_format=ConfigFormat.TOML,
        global_config_path=Path.home() / ".config" / "opencode" / "config.toml",
        local_config_filename=".opencode.toml",
        mcp_section_path=["mcp"],
        detection_paths=[Path.home() / ".config" / "opencode"],
        server_entry=_UVXENTRY_TYPED,
    ),
    ToolDefinition(
        name="claude_code",
        display_name="Claude Code",
        config_format=ConfigFormat.JSON,
        global_config_path=Path.home() / ".claude" / "claude_desktop_config.json",
        local_config_filename=".claude.json",
        mcp_section_path=["mcpServers"],
        detection_paths=[Path.home() / ".claude"],
        server_entry=_UVXENTRY,
    ),
    ToolDefinition(
        name="copilot",
        display_name="GitHub Copilot",
        config_format=ConfigFormat.JSON,
        global_config_path=Path.home() / ".vscode" / "mcp.json",
        local_config_filename=".vscode/mcp.json",
        mcp_section_path=["servers"],
        detection_paths=[Path.home() / ".vscode"],
        server_entry=_UVXENTRY,
    ),
    ToolDefinition(
        name="cursor",
        display_name="Cursor",
        config_format=ConfigFormat.JSON,
        global_config_path=Path.home() / ".cursor" / "mcp.json",
        local_config_filename=".cursor/mcp.json",
        mcp_section_path=["mcpServers"],
        detection_paths=[Path.home() / ".cursor"],
        server_entry=_UVXENTRY,
    ),
    ToolDefinition(
        name="windsurf",
        display_name="Windsurf",
        config_format=ConfigFormat.JSON,
        global_config_path=Path.home() / ".windsurf" / "mcp.json",
        local_config_filename=".windsurf/mcp.json",
        mcp_section_path=["mcpServers"],
        detection_paths=[Path.home() / ".windsurf"],
        server_entry=_UVXENTRY,
    ),
    ToolDefinition(
        name="devin",
        display_name="Devin CLI",
        config_format=ConfigFormat.JSON,
        global_config_path=Path.home() / ".devin" / "mcp.json",
        local_config_filename=".devin/mcp.json",
        mcp_section_path=["mcpServers"],
        detection_paths=[Path.home() / ".devin"],
        server_entry=_UVXENTRY,
    ),
]

TOOL_NAMES: set[str] = {t.name for t in TOOL_DEFINITIONS}


def get_tool_definition(name: str) -> ToolDefinition | None:
    """Look up a tool definition by its short name."""
    for td in TOOL_DEFINITIONS:
        if td.name == name:
            return td
    return None


# ── Result types ──────────────────────────────────────────────────


@dataclass(slots=True)
class DetectedTool:
    """An AI tool detected on the system, with its resolved config path."""

    definition: ToolDefinition
    config_path: Path
    scope: InstallScope
    already_registered: bool = False


@dataclass(slots=True)
class InstallPlan:
    """Everything the installer intends to do, before execution."""

    tools_to_register: list[DetectedTool] = field(default_factory=list)
    agents_to_copy: list[tuple[Path, Path]] = field(default_factory=list)
    skills_to_copy: list[tuple[Path, Path]] = field(default_factory=list)
    """Skill files to copy to .ai/skills/ in the project."""
    skipped: list[tuple[str, str]] = field(default_factory=list)
    """(tool_display_name, reason) for tools that were skipped."""


@dataclass(slots=True)
class InstallResult:
    """Summary of what the installer actually did."""

    registered: list[str] = field(default_factory=list)
    """Display names of tools where MCP was registered."""
    copied: list[Path] = field(default_factory=list)
    """Agent files that were copied."""
    skipped: list[tuple[str, str]] = field(default_factory=list)
    """(tool_display_name, reason) for tools that were skipped."""
    backups: list[Path] = field(default_factory=list)
    """Backup files created before modification."""


# ── Uninstall types ───────────────────────────────────────────────


@dataclass(slots=True)
class UninstallPlan:
    """Everything the uninstaller intends to do, before execution."""

    tools_to_deregister: list[DetectedTool] = field(default_factory=list)
    """Tools where ensemble-mcp is currently registered and will be removed."""
    agents_to_remove: list[Path] = field(default_factory=list)
    """Agent files to delete from the project."""
    skills_to_remove: list[Path] = field(default_factory=list)
    """Skill files to delete from the project."""
    clean_data: bool = False
    """Whether to remove ~/.cache/ensemble-mcp/ and ~/.config/ensemble-mcp/."""
    skipped: list[tuple[str, str]] = field(default_factory=list)
    """(tool_display_name, reason) for tools that were skipped."""


@dataclass(slots=True)
class UninstallResult:
    """Summary of what the uninstaller actually did."""

    deregistered: list[str] = field(default_factory=list)
    """Display names of tools where MCP was removed."""
    removed: list[Path] = field(default_factory=list)
    """Agent/skill files that were deleted."""
    data_cleaned: bool = False
    """Whether cached data directories were removed."""
    skipped: list[tuple[str, str]] = field(default_factory=list)
    """(tool_display_name, reason) for tools that were skipped."""
    backups: list[Path] = field(default_factory=list)
    """Backup files created before modification."""
