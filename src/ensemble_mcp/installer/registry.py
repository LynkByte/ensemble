"""Config file read/write for each supported AI tool.

Handles TOML (OpenCode) and JSON (Claude Code, Copilot, Cursor, Windsurf,
Devin CLI) config formats. Creates backups before modification and ensures
parent directories exist.
"""

from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path
from typing import Any

from . import MCP_SERVER_NAME, ConfigFormat, ToolDefinition

# ── Public API ────────────────────────────────────────────────────


def read_config(path: Path) -> dict[str, Any]:
    """Read and parse a config file (TOML or JSON) based on extension.

    Returns an empty dict if the file does not exist.
    """
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}

    suffix = path.suffix.lower()
    if suffix == ".toml":
        return tomllib.loads(text)
    if suffix == ".json":
        return json.loads(text)  # type: ignore[no-any-return]

    msg = f"Unsupported config format: {suffix}"
    raise ValueError(msg)


def write_config(path: Path, data: dict[str, Any], fmt: ConfigFormat) -> None:
    """Serialize *data* and write to *path*, creating parent dirs if needed.

    For TOML files we generate a minimal TOML representation (since
    ``tomllib`` is read-only). For JSON files we use standard ``json.dump``
    with 2-space indentation.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == ConfigFormat.TOML:
        path.write_text(_serialize_toml(data), encoding="utf-8")
    elif fmt == ConfigFormat.JSON:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    else:
        msg = f"Unsupported format: {fmt}"
        raise ValueError(msg)


def create_backup(path: Path) -> Path | None:
    """Create a ``.bak`` copy of *path* if it exists.

    Returns the backup path, or ``None`` if no file to back up.
    """
    if not path.exists():
        return None
    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    return backup


def is_registered(config: dict[str, Any], definition: ToolDefinition) -> bool:
    """Check whether ensemble-mcp is already registered in *config*."""
    section = _traverse(config, definition.mcp_section_path)
    if section is None or not isinstance(section, dict):
        return False
    return MCP_SERVER_NAME in section


def register_mcp(
    config: dict[str, Any],
    definition: ToolDefinition,
) -> dict[str, Any]:
    """Add the ensemble MCP server entry to *config*.

    Returns the updated config dict. Does **not** write to disk — call
    :func:`write_config` separately.

    If the MCP section does not exist, it is created. If ensemble is already
    registered, the entry is overwritten with the latest server_entry values.
    """
    # Walk into the config creating intermediate dicts as needed
    node = config
    for key in definition.mcp_section_path:
        if key not in node or not isinstance(node[key], dict):
            node[key] = {}
        node = node[key]

    node[MCP_SERVER_NAME] = dict(definition.server_entry)
    return config


# ── TOML serialization ────────────────────────────────────────────
# tomllib is read-only; we generate minimal TOML output ourselves.
# This handles the subset of TOML we need: top-level keys, nested
# tables, strings, lists, ints, bools. NOT a general-purpose writer.


def _serialize_toml(data: dict[str, Any], prefix: str = "") -> str:
    """Produce a minimal TOML string from a nested dict."""
    lines: list[str] = []
    tables: list[tuple[str, dict[str, Any]]] = []

    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            tables.append((full_key, value))
        else:
            lines.append(f"{key} = {_toml_value(value)}")

    if lines:
        if prefix:
            lines.insert(0, f"\n[{prefix}]")
        output = "\n".join(lines) + "\n"
    else:
        output = ""

    for table_key, table_data in tables:
        output += _serialize_toml(table_data, prefix=table_key)

    return output


def _toml_value(value: object) -> str:
    """Format a single TOML value."""
    if isinstance(value, str):
        # Escape backslashes and quotes
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, list):
        items = ", ".join(_toml_value(v) for v in value)
        return f"[{items}]"
    msg = f"Unsupported TOML value type: {type(value)}"
    raise TypeError(msg)


# ── Helpers ───────────────────────────────────────────────────────


def _traverse(data: dict[str, Any], keys: list[str]) -> Any:
    """Walk a nested dict by key path, returning ``None`` if any key is missing."""
    node: Any = data
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node
