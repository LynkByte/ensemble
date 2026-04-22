# MCP Client Integration

How to register `ensemble-mcp` with each supported AI coding tool. The easiest method is the auto-installer (`ensemble-mcp install`), but manual registration is also documented below.

## Auto-Detection with `ensemble-mcp install`

The installer detects AI tools by checking for known config directories:

| Tool | Detection Path |
|------|---------------|
| OpenCode | `~/.config/opencode/` |
| Claude Code | `~/.claude/` |
| GitHub Copilot | `~/.vscode/` |
| Cursor | `~/.cursor/` |
| Windsurf | `~/.windsurf/` |
| Devin CLI | `~/.devin/` |

```bash
# Auto-detect and register all found tools
ensemble-mcp install

# Register only specific tools
ensemble-mcp install --tools cursor,copilot

# Project-local registration (writes to project dir instead of global config)
ensemble-mcp install --local

# Preview without making changes
ensemble-mcp install --dry-run
```

The installer creates backups of existing config files (`.bak` extension) before modification.

---

## OpenCode

### Global Registration

Config file: `~/.config/opencode/config.json`

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "ensemble": {
      "type": "local",
      "command": ["uvx", "ensemble-mcp"]
    }
  }
}
```

### Project-Local Registration

Config file: `config.json` in project root

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "ensemble": {
      "type": "local",
      "command": ["uvx", "ensemble-mcp"]
    }
  }
}
```

### Agent & Skill Directories

| Scope | Agents | Skills |
|-------|--------|--------|
| Global | `~/.config/opencode/agents/` | `~/.config/opencode/skills/` |
| Local | `.opencode/agents/` | `.opencode/skills/` |

Skills use **directory** format: each skill is placed as `<skill-name>/SKILL.md`.

---

## Claude Code (Claude Desktop)

### Global Registration

Config file: `~/.claude.json`

```json
{
  "mcpServers": {
    "ensemble": {
      "command": "uvx",
      "args": ["ensemble-mcp"]
    }
  }
}
```

### Project-Local Registration

Config file: `.mcp.json` in project root

```json
{
  "mcpServers": {
    "ensemble": {
      "command": "uvx",
      "args": ["ensemble-mcp"]
    }
  }
}
```

### Skill Directories

| Scope | Skills |
|-------|--------|
| Local | `.claude/skills/` |

---

## GitHub Copilot (VS Code)

### Global Registration

Config file: `~/.vscode/mcp.json`

```json
{
  "servers": {
    "ensemble": {
      "command": "uvx",
      "args": ["ensemble-mcp"]
    }
  }
}
```

### Project-Local Registration

Config file: `.vscode/mcp.json` in project root

```json
{
  "servers": {
    "ensemble": {
      "command": "uvx",
      "args": ["ensemble-mcp"]
    }
  }
}
```

---

## Cursor

### Global Registration

Config file: `~/.cursor/mcp.json`

```json
{
  "mcpServers": {
    "ensemble": {
      "command": "uvx",
      "args": ["ensemble-mcp"]
    }
  }
}
```

### Project-Local Registration

Config file: `.cursor/mcp.json` in project root

```json
{
  "mcpServers": {
    "ensemble": {
      "command": "uvx",
      "args": ["ensemble-mcp"]
    }
  }
}
```

### Skill Directories

| Scope | Skills |
|-------|--------|
| Local | `.cursor/rules/` |

---

## Windsurf

### Global Registration

Config file: `~/.windsurf/mcp.json`

```json
{
  "mcpServers": {
    "ensemble": {
      "command": "uvx",
      "args": ["ensemble-mcp"]
    }
  }
}
```

### Project-Local Registration

Config file: `.windsurf/mcp.json` in project root

```json
{
  "mcpServers": {
    "ensemble": {
      "command": "uvx",
      "args": ["ensemble-mcp"]
    }
  }
}
```

---

## Devin CLI

### Global Registration

Config file: `~/.devin/mcp.json`

```json
{
  "mcpServers": {
    "ensemble": {
      "command": "uvx",
      "args": ["ensemble-mcp"]
    }
  }
}
```

### Project-Local Registration

Config file: `.devin/mcp.json` in project root

```json
{
  "mcpServers": {
    "ensemble": {
      "command": "uvx",
      "args": ["ensemble-mcp"]
    }
  }
}
```

### Skill Directories

| Scope | Skills |
|-------|--------|
| Local | `.devin/` |

---

## Manual Registration (Generic stdio)

For any MCP-compatible tool not listed above, register the server with stdio transport:

```json
{
  "ensemble": {
    "command": "uvx",
    "args": ["ensemble-mcp"]
  }
}
```

Or if installed via pip:

```json
{
  "ensemble": {
    "command": "ensemble-mcp"
  }
}
```

The server communicates exclusively over **stdio** — it reads MCP requests from stdin and writes responses to stdout. All diagnostic output (startup banner, logs) goes to stderr.

---

## Agent and Skill Files

The installer can also copy bundled agent and skill files:

### Agents (7-agent pipeline)

Bundled agent files: `team-ensemble.md`, `team-scope.md`, `team-craft.md`, `team-forge.md`, `team-trace.md`, `team-lens.md`, `team-signal.md`.

These are automatically copied during `ensemble-mcp install`. To copy separately:

```bash
ensemble-mcp add-agents          # global scope
ensemble-mcp add-agents --local  # project-local scope
```

### Skills (workflow skill)

Bundled skill file: `ensemble-mcp-workflow.md` — teaches AI agents when and how to invoke ensemble-mcp tools.

```bash
ensemble-mcp add-skills          # project-local scope (default)
ensemble-mcp add-skills --global # global scope
```

## Stopping the Server

The MCP server is **not a daemon** — it starts when your AI tool launches it and stops when the AI tool closes. You can also stop it manually:

| Situation | How to Stop |
|-----------|-------------|
| AI tool spawned it (normal usage) | Close the AI tool — the server exits automatically |
| Running manually in a terminal | Press `Ctrl+C` |
| Process is stuck or orphaned | `pkill -f ensemble-mcp` |

To verify no ensemble-mcp processes are running:

```bash
pgrep -fa ensemble-mcp
```

---

## Removing Registration

### Using the CLI

```bash
ensemble-mcp uninstall
```

See [CLI Reference](./cli-reference.md) for flags like `--tools`, `--local`, `--dry-run`.

### Manual Removal Per Tool

If you prefer to edit config files manually, remove the `ensemble` entry from the relevant file:

| Tool | Config File | Key to Remove |
|------|-------------|---------------|
| OpenCode | `~/.config/opencode/config.json` | `"ensemble"` from `"mcp"` |
| Claude Code | `~/.claude.json` | `"ensemble"` from `"mcpServers"` |
| GitHub Copilot | `~/.vscode/mcp.json` | `"ensemble"` from `"servers"` |
| Cursor | `~/.cursor/mcp.json` | `"ensemble"` from `"mcpServers"` |
| Windsurf | `~/.windsurf/mcp.json` | `"ensemble"` from `"mcpServers"` |
| Devin CLI | `~/.devin/mcp.json` | `"ensemble"` from `"mcpServers"` |

After removing the config entry, restart the AI tool for the change to take effect.

### Verification

After removal, verify by checking that your AI tool no longer lists ensemble-mcp as a connected server. You can also confirm the config file no longer contains the `ensemble` entry.

---

## Restoring from Backup

The installer creates `.bak` backup files before modifying any config. If something goes wrong, restore from the backup:

```bash
# Example: restore OpenCode config
cp ~/.config/opencode/config.json.bak ~/.config/opencode/config.json

# Example: restore Claude Code config
cp ~/.claude.json.bak ~/.claude.json
```

Backup files are created at the same location as the config with a `.bak` extension.

---

## Next Steps

- [CLI Reference](./cli-reference.md) — all install/uninstall flags
- [Tool Reference](./tool-reference.md) — tools available after registration
- [Troubleshooting](./troubleshooting.md) — registration issues
