"""Tests for the installer module.

Covers tool detection, config reading/writing, MCP registration,
idempotency (running install twice), backup creation, CLI argument
parsing, and the full install flow orchestration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ensemble_mcp.installer import (
    MCP_SERVER_NAME,
    TOOL_DEFINITIONS,
    TOOL_NAMES,
    ConfigFormat,
    DetectedTool,
    InstallPlan,
    InstallScope,
    ToolDefinition,
    get_tool_definition,
)
from ensemble_mcp.installer.agents import discover_agents
from ensemble_mcp.installer.registry import (
    _serialize_toml,
    _toml_value,
    create_backup,
    is_registered,
    read_config,
    register_mcp,
    write_config,
)
from ensemble_mcp.installer.setup import (
    InstallResult,
    detect_ai_tools,
    display_plan,
    display_result,
    execute_plan,
    plan_install,
)

# ── Helpers ───────────────────────────────────────────────────────


def _opencode_def(tmp_path: Path) -> ToolDefinition:
    """Return an OpenCode ToolDefinition with paths rooted in tmp_path."""
    return ToolDefinition(
        name="opencode",
        display_name="OpenCode",
        config_format=ConfigFormat.TOML,
        global_config_path=tmp_path / "global" / "opencode" / "config.toml",
        local_config_filename=".opencode.toml",
        mcp_section_path=["mcp"],
        detection_paths=[tmp_path / "global" / "opencode"],
        server_entry={"type": "stdio", "command": "uvx", "args": ["ensemble-mcp"]},
    )


def _claude_def(tmp_path: Path) -> ToolDefinition:
    """Return a Claude Code ToolDefinition with paths rooted in tmp_path."""
    return ToolDefinition(
        name="claude_code",
        display_name="Claude Code",
        config_format=ConfigFormat.JSON,
        global_config_path=tmp_path / "global" / ".claude" / "claude_desktop_config.json",
        local_config_filename=".claude.json",
        mcp_section_path=["mcpServers"],
        detection_paths=[tmp_path / "global" / ".claude"],
        server_entry={"command": "uvx", "args": ["ensemble-mcp"]},
    )


def _cursor_def(tmp_path: Path) -> ToolDefinition:
    """Return a Cursor ToolDefinition with paths rooted in tmp_path."""
    return ToolDefinition(
        name="cursor",
        display_name="Cursor",
        config_format=ConfigFormat.JSON,
        global_config_path=tmp_path / "global" / ".cursor" / "mcp.json",
        local_config_filename=".cursor/mcp.json",
        mcp_section_path=["mcpServers"],
        detection_paths=[tmp_path / "global" / ".cursor"],
        server_entry={"command": "uvx", "args": ["ensemble-mcp"]},
    )


# ── Tool Definitions ─────────────────────────────────────────────


class TestToolDefinitions:
    def test_all_six_tools_defined(self):
        assert len(TOOL_DEFINITIONS) == 6

    def test_tool_names_set(self):
        expected = {"opencode", "claude_code", "copilot", "cursor", "windsurf", "devin"}
        assert expected == TOOL_NAMES

    def test_get_tool_definition_found(self):
        td = get_tool_definition("opencode")
        assert td is not None
        assert td.display_name == "OpenCode"

    def test_get_tool_definition_not_found(self):
        assert get_tool_definition("nonexistent") is None

    def test_opencode_is_toml_format(self):
        td = get_tool_definition("opencode")
        assert td is not None
        assert td.config_format == ConfigFormat.TOML

    def test_json_tools_have_json_format(self):
        for name in ("claude_code", "copilot", "cursor", "windsurf", "devin"):
            td = get_tool_definition(name)
            assert td is not None
            assert td.config_format == ConfigFormat.JSON

    def test_mcp_section_paths(self):
        opencode = get_tool_definition("opencode")
        assert opencode is not None
        assert opencode.mcp_section_path == ["mcp"]

        claude = get_tool_definition("claude_code")
        assert claude is not None
        assert claude.mcp_section_path == ["mcpServers"]

        copilot = get_tool_definition("copilot")
        assert copilot is not None
        assert copilot.mcp_section_path == ["servers"]


# ── Config Reading ───────────────────────────────────────────────


class TestReadConfig:
    def test_read_nonexistent_returns_empty(self, tmp_path: Path):
        result = read_config(tmp_path / "nope.json")
        assert result == {}

    def test_read_empty_file_returns_empty(self, tmp_path: Path):
        f = tmp_path / "empty.json"
        f.write_text("")
        result = read_config(f)
        assert result == {}

    def test_read_json(self, tmp_path: Path):
        f = tmp_path / "config.json"
        data = {"mcpServers": {"other": {"command": "foo"}}}
        f.write_text(json.dumps(data))
        result = read_config(f)
        assert result == data

    def test_read_toml(self, tmp_path: Path):
        f = tmp_path / "config.toml"
        f.write_text('[mcp.other]\ncommand = "foo"\n')
        result = read_config(f)
        assert result["mcp"]["other"]["command"] == "foo"

    def test_read_unsupported_format_raises(self, tmp_path: Path):
        f = tmp_path / "config.yaml"
        f.write_text("key: value")
        with pytest.raises(ValueError, match="Unsupported config format"):
            read_config(f)


# ── Config Writing ───────────────────────────────────────────────


class TestWriteConfig:
    def test_write_json(self, tmp_path: Path):
        f = tmp_path / "out.json"
        data: dict[str, Any] = {"servers": {"test": {"command": "echo"}}}
        write_config(f, data, ConfigFormat.JSON)
        result = json.loads(f.read_text())
        assert result["servers"]["test"]["command"] == "echo"

    def test_write_toml(self, tmp_path: Path):
        f = tmp_path / "out.toml"
        data: dict[str, Any] = {"mcp": {"ensemble": {"type": "stdio", "command": "uvx"}}}
        write_config(f, data, ConfigFormat.TOML)
        text = f.read_text()
        assert "ensemble" in text
        assert "uvx" in text

    def test_write_creates_parent_dirs(self, tmp_path: Path):
        f = tmp_path / "deep" / "nested" / "config.json"
        write_config(f, {"key": "value"}, ConfigFormat.JSON)
        assert f.exists()

    def test_write_json_roundtrip(self, tmp_path: Path):
        f = tmp_path / "roundtrip.json"
        original: dict[str, Any] = {
            "mcpServers": {
                "existing": {"command": "other"},
                "ensemble": {"command": "uvx", "args": ["ensemble-mcp"]},
            }
        }
        write_config(f, original, ConfigFormat.JSON)
        result = read_config(f)
        assert result == original


# ── TOML Serialization ───────────────────────────────────────────


class TestTomlSerialization:
    def test_string_value(self):
        assert _toml_value("hello") == '"hello"'

    def test_bool_value(self):
        assert _toml_value(True) == "true"
        assert _toml_value(False) == "false"

    def test_int_value(self):
        assert _toml_value(42) == "42"

    def test_list_value(self):
        assert _toml_value(["a", "b"]) == '["a", "b"]'

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError, match="Unsupported TOML"):
            _toml_value(object())

    def test_serialize_flat_dict(self):
        result = _serialize_toml({"key": "value", "num": 42})
        assert 'key = "value"' in result
        assert "num = 42" in result

    def test_serialize_nested_dict(self):
        result = _serialize_toml(
            {
                "mcp": {
                    "ensemble": {
                        "type": "stdio",
                        "command": "uvx",
                    }
                }
            }
        )
        assert "[mcp.ensemble]" in result
        assert 'type = "stdio"' in result
        assert 'command = "uvx"' in result

    def test_string_with_quotes_escaped(self):
        assert _toml_value('say "hello"') == '"say \\"hello\\""'


# ── Backup ───────────────────────────────────────────────────────


class TestBackup:
    def test_backup_existing_file(self, tmp_path: Path):
        f = tmp_path / "config.json"
        f.write_text('{"old": true}')
        backup = create_backup(f)
        assert backup is not None
        assert backup.exists()
        assert backup.suffix == ".bak"
        assert backup.read_text() == '{"old": true}'

    def test_backup_nonexistent_returns_none(self, tmp_path: Path):
        result = create_backup(tmp_path / "nope.json")
        assert result is None


# ── Registration Check ───────────────────────────────────────────


class TestIsRegistered:
    def test_not_registered_empty_config(self, tmp_path: Path):
        defn = _claude_def(tmp_path)
        assert is_registered({}, defn) is False

    def test_not_registered_section_exists_but_no_ensemble(self, tmp_path: Path):
        defn = _claude_def(tmp_path)
        config: dict[str, Any] = {"mcpServers": {"other-tool": {}}}
        assert is_registered(config, defn) is False

    def test_registered(self, tmp_path: Path):
        defn = _claude_def(tmp_path)
        config: dict[str, Any] = {"mcpServers": {"ensemble": {"command": "uvx"}}}
        assert is_registered(config, defn) is True

    def test_opencode_registered(self, tmp_path: Path):
        defn = _opencode_def(tmp_path)
        config: dict[str, Any] = {"mcp": {"ensemble": {"type": "stdio"}}}
        assert is_registered(config, defn) is True


# ── MCP Registration ─────────────────────────────────────────────


class TestRegisterMcp:
    def test_register_into_empty_config(self, tmp_path: Path):
        defn = _claude_def(tmp_path)
        config: dict[str, Any] = {}
        register_mcp(config, defn)
        assert config["mcpServers"][MCP_SERVER_NAME] == {
            "command": "uvx",
            "args": ["ensemble-mcp"],
        }

    def test_register_preserves_existing_servers(self, tmp_path: Path):
        defn = _claude_def(tmp_path)
        config: dict[str, Any] = {"mcpServers": {"other": {"command": "other-tool"}}}
        register_mcp(config, defn)
        assert "other" in config["mcpServers"]
        assert MCP_SERVER_NAME in config["mcpServers"]

    def test_register_overwrites_existing_entry(self, tmp_path: Path):
        defn = _claude_def(tmp_path)
        config: dict[str, Any] = {"mcpServers": {MCP_SERVER_NAME: {"command": "old-value"}}}
        register_mcp(config, defn)
        assert config["mcpServers"][MCP_SERVER_NAME]["command"] == "uvx"

    def test_register_opencode_toml(self, tmp_path: Path):
        defn = _opencode_def(tmp_path)
        config: dict[str, Any] = {}
        register_mcp(config, defn)
        assert config["mcp"][MCP_SERVER_NAME] == {
            "type": "stdio",
            "command": "uvx",
            "args": ["ensemble-mcp"],
        }

    def test_register_creates_intermediate_sections(self, tmp_path: Path):
        defn = _claude_def(tmp_path)
        config: dict[str, Any] = {"unrelated": "data"}
        register_mcp(config, defn)
        assert "mcpServers" in config
        assert MCP_SERVER_NAME in config["mcpServers"]
        assert config["unrelated"] == "data"


# ── Detection ─────────────────────────────────────────────────────


class TestDetection:
    def test_detect_no_tools_installed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        # Monkey-patch TOOL_DEFINITIONS to use tmp_path-based paths
        monkeypatch.setattr(
            "ensemble_mcp.installer.setup.TOOL_DEFINITIONS",
            [_opencode_def(tmp_path), _claude_def(tmp_path)],
        )
        detected = detect_ai_tools(tmp_path, InstallScope.GLOBAL)
        assert detected == []

    def test_detect_opencode_installed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        defn = _opencode_def(tmp_path)
        # Create the detection directory
        defn.detection_paths[0].mkdir(parents=True)
        monkeypatch.setattr(
            "ensemble_mcp.installer.setup.TOOL_DEFINITIONS",
            [defn],
        )
        detected = detect_ai_tools(tmp_path, InstallScope.GLOBAL)
        assert len(detected) == 1
        assert detected[0].definition.name == "opencode"
        assert detected[0].already_registered is False

    def test_detect_already_registered(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        defn = _claude_def(tmp_path)
        # Create detection dir and pre-existing config
        defn.detection_paths[0].mkdir(parents=True)
        defn.global_config_path.parent.mkdir(parents=True, exist_ok=True)
        defn.global_config_path.write_text(
            json.dumps({"mcpServers": {"ensemble": {"command": "uvx"}}})
        )
        monkeypatch.setattr(
            "ensemble_mcp.installer.setup.TOOL_DEFINITIONS",
            [defn],
        )
        detected = detect_ai_tools(tmp_path, InstallScope.GLOBAL)
        assert len(detected) == 1
        assert detected[0].already_registered is True

    def test_detect_with_tool_filter(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        oc_def = _opencode_def(tmp_path)
        cl_def = _claude_def(tmp_path)
        oc_def.detection_paths[0].mkdir(parents=True)
        cl_def.detection_paths[0].mkdir(parents=True)
        monkeypatch.setattr(
            "ensemble_mcp.installer.setup.TOOL_DEFINITIONS",
            [oc_def, cl_def],
        )
        detected = detect_ai_tools(tmp_path, InstallScope.GLOBAL, tool_filter={"opencode"})
        assert len(detected) == 1
        assert detected[0].definition.name == "opencode"

    def test_detect_local_scope_always_detects(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        defn = _opencode_def(tmp_path)
        # Don't create detection paths — local scope doesn't require them
        monkeypatch.setattr(
            "ensemble_mcp.installer.setup.TOOL_DEFINITIONS",
            [defn],
        )
        detected = detect_ai_tools(tmp_path, InstallScope.LOCAL)
        assert len(detected) == 1
        assert detected[0].scope == InstallScope.LOCAL
        # Config path should be project-local
        assert detected[0].config_path == tmp_path / ".opencode.toml"


# ── Plan ──────────────────────────────────────────────────────────


class TestPlan:
    def test_plan_with_new_tools(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        defn = _cursor_def(tmp_path)
        defn.detection_paths[0].mkdir(parents=True)
        monkeypatch.setattr(
            "ensemble_mcp.installer.setup.TOOL_DEFINITIONS",
            [defn],
        )
        plan = plan_install(tmp_path, InstallScope.GLOBAL)
        assert len(plan.tools_to_register) == 1
        assert plan.tools_to_register[0].definition.name == "cursor"
        assert len(plan.skipped) == 0

    def test_plan_skips_already_registered(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        defn = _cursor_def(tmp_path)
        defn.detection_paths[0].mkdir(parents=True)
        defn.global_config_path.parent.mkdir(parents=True, exist_ok=True)
        defn.global_config_path.write_text(
            json.dumps({"mcpServers": {"ensemble": {"command": "uvx", "args": ["ensemble-mcp"]}}})
        )
        monkeypatch.setattr(
            "ensemble_mcp.installer.setup.TOOL_DEFINITIONS",
            [defn],
        )
        plan = plan_install(tmp_path, InstallScope.GLOBAL)
        assert len(plan.tools_to_register) == 0
        assert len(plan.skipped) == 1
        assert plan.skipped[0] == ("Cursor", "already registered")

    def test_plan_reports_not_installed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        defn = _cursor_def(tmp_path)
        # Don't create detection paths
        monkeypatch.setattr(
            "ensemble_mcp.installer.setup.TOOL_DEFINITIONS",
            [defn],
        )
        monkeypatch.setattr(
            "ensemble_mcp.installer.setup.TOOL_NAMES",
            {"cursor"},
        )
        plan = plan_install(tmp_path, InstallScope.GLOBAL, tool_filter={"cursor"})
        assert len(plan.tools_to_register) == 0
        assert any(reason == "not installed" for _, reason in plan.skipped)


# ── Display ──────────────────────────────────────────────────────


class TestDisplay:
    def test_display_plan_with_tools(self, tmp_path: Path):
        defn = _cursor_def(tmp_path)
        plan = InstallPlan(
            tools_to_register=[
                DetectedTool(
                    definition=defn,
                    config_path=defn.global_config_path,
                    scope=InstallScope.GLOBAL,
                    already_registered=False,
                )
            ],
        )
        text = display_plan(plan)
        assert "INSTALL PLAN" in text
        assert "Cursor" in text
        assert "Will register" in text

    def test_display_plan_nothing_to_do(self):
        plan = InstallPlan(
            skipped=[("Cursor", "already registered")],
        )
        text = display_plan(plan)
        assert "Nothing to do" in text
        assert "Cursor" in text

    def test_display_result_registered(self):
        result = InstallResult(
            registered=["Cursor", "OpenCode"],
            backups=[Path("/tmp/config.json.bak")],
        )
        text = display_result(result)
        assert "Cursor" in text
        assert "OpenCode" in text
        assert "Backups" in text

    def test_display_result_no_changes(self):
        result = InstallResult()
        text = display_result(result)
        assert "No changes" in text


# ── Execute ──────────────────────────────────────────────────────


class TestExecute:
    def test_execute_registers_json_tool(self, tmp_path: Path):
        defn = _claude_def(tmp_path)
        defn.global_config_path.parent.mkdir(parents=True, exist_ok=True)
        # Start with empty config
        defn.global_config_path.write_text("{}")

        plan = InstallPlan(
            tools_to_register=[
                DetectedTool(
                    definition=defn,
                    config_path=defn.global_config_path,
                    scope=InstallScope.GLOBAL,
                )
            ],
        )
        result = execute_plan(plan)
        assert "Claude Code" in result.registered
        assert len(result.backups) == 1

        # Verify the config was written correctly
        config = json.loads(defn.global_config_path.read_text())
        assert config["mcpServers"]["ensemble"]["command"] == "uvx"

    def test_execute_registers_toml_tool(self, tmp_path: Path):
        defn = _opencode_def(tmp_path)
        defn.global_config_path.parent.mkdir(parents=True, exist_ok=True)
        defn.global_config_path.write_text("")

        plan = InstallPlan(
            tools_to_register=[
                DetectedTool(
                    definition=defn,
                    config_path=defn.global_config_path,
                    scope=InstallScope.GLOBAL,
                )
            ],
        )
        result = execute_plan(plan)
        assert "OpenCode" in result.registered

        # Verify TOML content
        text = defn.global_config_path.read_text()
        assert "ensemble" in text
        assert "uvx" in text

    def test_execute_creates_new_config(self, tmp_path: Path):
        defn = _cursor_def(tmp_path)
        # Don't create the config file — it should be created by execute
        plan = InstallPlan(
            tools_to_register=[
                DetectedTool(
                    definition=defn,
                    config_path=defn.global_config_path,
                    scope=InstallScope.GLOBAL,
                )
            ],
        )
        result = execute_plan(plan)
        assert "Cursor" in result.registered
        assert defn.global_config_path.exists()
        # No backup since file didn't exist
        assert len(result.backups) == 0

    def test_execute_preserves_existing_config(self, tmp_path: Path):
        defn = _claude_def(tmp_path)
        defn.global_config_path.parent.mkdir(parents=True, exist_ok=True)
        # Existing config with another server
        defn.global_config_path.write_text(
            json.dumps(
                {
                    "mcpServers": {"other-server": {"command": "other"}},
                    "someOtherKey": "preserved",
                }
            )
        )

        plan = InstallPlan(
            tools_to_register=[
                DetectedTool(
                    definition=defn,
                    config_path=defn.global_config_path,
                    scope=InstallScope.GLOBAL,
                )
            ],
        )
        execute_plan(plan)
        config = json.loads(defn.global_config_path.read_text())

        # Both servers present
        assert "other-server" in config["mcpServers"]
        assert "ensemble" in config["mcpServers"]
        # Other keys preserved
        assert config["someOtherKey"] == "preserved"

    def test_execute_idempotent(self, tmp_path: Path):
        """Running execute twice produces the same result."""
        defn = _claude_def(tmp_path)
        defn.global_config_path.parent.mkdir(parents=True, exist_ok=True)
        defn.global_config_path.write_text("{}")

        plan = InstallPlan(
            tools_to_register=[
                DetectedTool(
                    definition=defn,
                    config_path=defn.global_config_path,
                    scope=InstallScope.GLOBAL,
                )
            ],
        )

        # First run
        execute_plan(plan)
        first_config = json.loads(defn.global_config_path.read_text())

        # Second run (re-registration overwrites with same values)
        execute_plan(plan)
        second_config = json.loads(defn.global_config_path.read_text())

        assert first_config == second_config

    def test_execute_multiple_tools(self, tmp_path: Path):
        oc_def = _opencode_def(tmp_path)
        cl_def = _claude_def(tmp_path)

        # Create parent dirs
        oc_def.global_config_path.parent.mkdir(parents=True, exist_ok=True)
        cl_def.global_config_path.parent.mkdir(parents=True, exist_ok=True)

        plan = InstallPlan(
            tools_to_register=[
                DetectedTool(
                    definition=oc_def,
                    config_path=oc_def.global_config_path,
                    scope=InstallScope.GLOBAL,
                ),
                DetectedTool(
                    definition=cl_def,
                    config_path=cl_def.global_config_path,
                    scope=InstallScope.GLOBAL,
                ),
            ],
        )
        result = execute_plan(plan)
        assert len(result.registered) == 2
        assert "OpenCode" in result.registered
        assert "Claude Code" in result.registered


# ── Agent Discovery ──────────────────────────────────────────────


class TestAgentDiscovery:
    def test_no_bundled_agents_dir(self, tmp_path: Path):
        """When no data/agents/ directory exists, return empty list."""
        result = discover_agents(tmp_path)
        # The bundled agents dir doesn't exist in the package yet
        # so this should return an empty list (or whatever is there)
        assert isinstance(result, list)

    def test_discover_bundled_agents(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """When bundled agents exist, return copy pairs."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        (bundled / "team-captain.md").write_text("# Captain")
        (bundled / "team-engineer.md").write_text("# Engineer")

        monkeypatch.setattr(
            "ensemble_mcp.installer.agents._BUNDLED_AGENTS_DIR",
            bundled,
        )
        project = tmp_path / "project"
        project.mkdir()

        pairs = discover_agents(project)
        assert len(pairs) == 2
        sources = {p[0].name for p in pairs}
        assert sources == {"team-captain.md", "team-engineer.md"}
        # Destinations should be under project/.agents/
        for _, dst in pairs:
            assert str(dst).startswith(str(project / ".agents"))

    def test_discover_skips_existing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Already-copied agents are not included in the copy plan."""
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        (bundled / "team-captain.md").write_text("# Captain")

        monkeypatch.setattr(
            "ensemble_mcp.installer.agents._BUNDLED_AGENTS_DIR",
            bundled,
        )
        project = tmp_path / "project"
        (project / ".agents").mkdir(parents=True)
        (project / ".agents" / "team-captain.md").write_text("# Already there")

        pairs = discover_agents(project)
        assert len(pairs) == 0


# ── Full Flow (Orchestrator) ─────────────────────────────────────


class TestFullFlow:
    def test_full_install_flow(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """End-to-end: detect → plan → execute for two tools."""
        oc_def = _opencode_def(tmp_path)
        cl_def = _claude_def(tmp_path)

        # Create detection dirs
        oc_def.detection_paths[0].mkdir(parents=True)
        cl_def.detection_paths[0].mkdir(parents=True)

        monkeypatch.setattr(
            "ensemble_mcp.installer.setup.TOOL_DEFINITIONS",
            [oc_def, cl_def],
        )

        # Plan
        plan = plan_install(tmp_path, InstallScope.GLOBAL)
        assert len(plan.tools_to_register) == 2

        # Execute
        result = execute_plan(plan)
        assert len(result.registered) == 2

        # Verify configs written
        assert oc_def.global_config_path.exists()
        assert cl_def.global_config_path.exists()

        cl_config = json.loads(cl_def.global_config_path.read_text())
        assert cl_config["mcpServers"]["ensemble"]["command"] == "uvx"

    def test_local_scope_install(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Local scope writes project-local configs."""
        defn = _claude_def(tmp_path)
        monkeypatch.setattr(
            "ensemble_mcp.installer.setup.TOOL_DEFINITIONS",
            [defn],
        )

        project = tmp_path / "my-project"
        project.mkdir()

        plan = plan_install(project, InstallScope.LOCAL)
        assert len(plan.tools_to_register) == 1
        assert plan.tools_to_register[0].config_path == project / ".claude.json"

        result = execute_plan(plan)
        assert len(result.registered) == 1

        local_config = json.loads((project / ".claude.json").read_text())
        assert local_config["mcpServers"]["ensemble"]["command"] == "uvx"

    def test_second_install_skips_registered(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Running install a second time correctly skips already-registered tools."""
        defn = _cursor_def(tmp_path)
        defn.detection_paths[0].mkdir(parents=True)
        monkeypatch.setattr(
            "ensemble_mcp.installer.setup.TOOL_DEFINITIONS",
            [defn],
        )

        # First install
        plan1 = plan_install(tmp_path, InstallScope.GLOBAL)
        assert len(plan1.tools_to_register) == 1
        execute_plan(plan1)

        # Second install — should be detected as already registered
        plan2 = plan_install(tmp_path, InstallScope.GLOBAL)
        assert len(plan2.tools_to_register) == 0
        assert len(plan2.skipped) == 1
        assert plan2.skipped[0] == ("Cursor", "already registered")


# ── CLI Entry Point ──────────────────────────────────────────────


class TestCli:
    def test_main_help(self):
        """Ensure argparse is configured without errors."""
        import sys

        from ensemble_mcp.__main__ import main

        sys.argv = ["ensemble-mcp", "--help"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_install_help(self):
        import sys

        from ensemble_mcp.__main__ import main

        sys.argv = ["ensemble-mcp", "install", "--help"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_unknown_tool_name_exits(self, monkeypatch: pytest.MonkeyPatch):
        """--tools with an unknown name should exit with error."""
        import sys

        from ensemble_mcp.__main__ import main

        monkeypatch.setattr(
            sys,
            "argv",
            ["ensemble-mcp", "install", "--tools", "badtool", "--yes"],
        )
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
