# Uninstalling ensemble-mcp

This guide covers three scenarios: stopping the server, disabling it (keeping it installed), and fully removing it from your system.

---

## 1. Stopping the Server

ensemble-mcp is **not a daemon or HTTP server**. It is a stdio subprocess spawned by your AI tool (OpenCode, Claude Code, Cursor, etc.) when it connects to MCP servers. The server lives only as long as the parent process keeps the stdio pipe open.

| Situation | How to Stop |
|-----------|-------------|
| AI tool spawned it (normal usage) | Close the AI tool -- the server process exits automatically |
| You ran `ensemble-mcp serve` manually | Press `Ctrl+C` in the terminal |
| Process is stuck or orphaned | `pkill -f ensemble-mcp` |
| Need to find the PID first | `pgrep -f ensemble-mcp` |

To verify no ensemble-mcp processes are running:

```bash
pgrep -fa ensemble-mcp
```

If nothing is returned, the server is not running.

---

## 2. Disabling (Keep Installed, Stop Using)

To stop your AI tool from spawning ensemble-mcp without uninstalling it, remove the `ensemble` entry from the tool's MCP configuration file.

### Using the CLI (recommended)

```bash
ensemble-mcp uninstall
```

This auto-detects which AI tools have ensemble-mcp registered and removes the config entries. It supports the same flags as `install`:

```bash
ensemble-mcp uninstall --tools opencode      # only remove from OpenCode
ensemble-mcp uninstall --local               # remove from project-local configs
ensemble-mcp uninstall --dry-run             # preview what would be removed
ensemble-mcp uninstall --yes                 # skip confirmation prompt
```

### Manual removal per tool

If you prefer to edit configs manually, remove the `ensemble` entry from the relevant file:

#### OpenCode

**Global:** `~/.config/opencode/opencode.json`
**Local:** `opencode.json` (in project root)

Remove the `"ensemble"` key from `"mcpServers"`:

```json
{
  "mcpServers": {
    "ensemble": { ... }  // DELETE this entry
  }
}
```

#### Claude Code

**Global:** `~/.claude/claude_desktop_config.json`
**Local:** `.claude.json` (in project root)

Remove the `"ensemble"` key from `"mcpServers"`:

```json
{
  "mcpServers": {
    "ensemble": { ... }  // DELETE this entry
  }
}
```

#### GitHub Copilot

**Global:** `~/.vscode/mcp.json`
**Local:** `.vscode/mcp.json` (in project root)

Remove the `"ensemble"` key from `"servers"`:

```json
{
  "servers": {
    "ensemble": { ... }  // DELETE this entry
  }
}
```

#### Cursor

**Global:** `~/.cursor/mcp.json`
**Local:** `.cursor/mcp.json` (in project root)

Remove the `"ensemble"` key from `"mcpServers"`:

```json
{
  "mcpServers": {
    "ensemble": { ... }  // DELETE this entry
  }
}
```

#### Windsurf

**Global:** `~/.windsurf/mcp.json`
**Local:** `.windsurf/mcp.json` (in project root)

Remove the `"ensemble"` key from `"mcpServers"`:

```json
{
  "mcpServers": {
    "ensemble": { ... }  // DELETE this entry
  }
}
```

#### Devin CLI

**Global:** `~/.devin/mcp.json`
**Local:** `.devin/mcp.json` (in project root)

Remove the `"ensemble"` key from `"mcpServers"`:

```json
{
  "mcpServers": {
    "ensemble": { ... }  // DELETE this entry
  }
}
```

After removing the config entry, restart the AI tool for the change to take effect.

---

## 3. Full Uninstall (Remove Everything)

To completely remove ensemble-mcp from your system:

### Step 1: Remove MCP config entries

```bash
# Automatic (removes from all detected AI tools)
ensemble-mcp uninstall --yes

# Or manual: edit each tool's config file as described above
```

### Step 2: Remove agent files from the project

The installer copies agent definition files into a tool-specific directory. The location depends on which AI tool you use:

| AI Tool | Agent Directory |
|---------|----------------|
| OpenCode | `.opencode/agents/` (local) or `~/.config/opencode/agents/` (global) |
| Other tools | `.agents/` (legacy) |

Remove the agent files:

```bash
# OpenCode (local)
rm -f .opencode/agents/team-captain.md
rm -f .opencode/agents/team-architect.md
rm -f .opencode/agents/team-engineer.md
rm -f .opencode/agents/team-forge.md
rm -f .opencode/agents/team-inspector.md
rm -f .opencode/agents/team-shipper.md
rm -f .opencode/agents/team-hunter.md

# Legacy path (also check this for older installations)
rm -f .agents/team-captain.md
rm -f .agents/team-architect.md
rm -f .agents/team-engineer.md
rm -f .agents/team-forge.md
rm -f .agents/team-inspector.md
rm -f .agents/team-shipper.md
rm -f .agents/team-hunter.md
```

### Step 3: Remove skill files (optional)

The installer copies skill files into a tool-specific directory:

| AI Tool | Skill Location |
|---------|---------------|
| OpenCode | `.opencode/skills/ensemble-mcp-workflow/SKILL.md` |
| Claude Code | `.claude/skills/ensemble-mcp-workflow.md` |
| Cursor | `.cursor/rules/ensemble-mcp-workflow.md` |
| Devin | `.devin/ensemble-mcp-workflow.md` |
| Legacy | `.ai/skills/ensemble-mcp-workflow.md` |

```bash
# OpenCode
rm -rf .opencode/skills/ensemble-mcp-workflow/

# Claude Code
rm -f .claude/skills/ensemble-mcp-workflow.md

# Cursor
rm -f .cursor/rules/ensemble-mcp-workflow.md

# Devin
rm -f .devin/ensemble-mcp-workflow.md

# Legacy path (also check this for older installations)
rm -f .ai/skills/ensemble-mcp-workflow.md
```

### Step 4: Remove cached data

ensemble-mcp stores its SQLite database and the ONNX embedding model in `~/.cache/ensemble-mcp/`:

```bash
# Remove database (stored patterns, metrics, sessions)
rm -rf ~/.cache/ensemble-mcp/
```

This deletes:
- `data.db` -- SQLite database (patterns, metrics, sessions, codebase index)
- `models/` -- ONNX MiniLM-L6-v2 model (~22MB)

### Step 5: Remove global config (optional)

If you created a global config file:

```bash
rm -rf ~/.config/ensemble-mcp/
```

### Step 6: Uninstall the Python package

```bash
pip uninstall ensemble-mcp
```

Or if installed via uvx:

```bash
uvx uninstall ensemble-mcp
```

### One-liner (nuclear option)

Remove everything in one command:

```bash
ensemble-mcp uninstall --yes --remove-agents --clean-data && pip uninstall -y ensemble-mcp
```

---

## Verifying Removal

After uninstalling, verify ensemble-mcp is fully removed:

```bash
# 1. No running processes
pgrep -fa ensemble-mcp

# 2. Package is gone
pip show ensemble-mcp 2>/dev/null && echo "Still installed" || echo "Not installed"

# 3. No cached data
ls ~/.cache/ensemble-mcp/ 2>/dev/null && echo "Cache still exists" || echo "Cache clean"

# 4. No global config
ls ~/.config/ensemble-mcp/ 2>/dev/null && echo "Config still exists" || echo "Config clean"
```

---

## Restoring from Backup

The installer creates `.bak` backup files before modifying any config. If you need to restore a config to its pre-ensemble state:

```bash
# Example for OpenCode
cp ~/.config/opencode/opencode.json.bak ~/.config/opencode/opencode.json

# Example for Claude Code
cp ~/.claude/claude_desktop_config.json.bak ~/.claude/claude_desktop_config.json
```

Backup files are created at the same location as the config with a `.bak` extension.
