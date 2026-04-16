# CLI Reference

Complete reference for all `ensemble-mcp` CLI commands, flags, and options.

## Entry Point

```
ensemble-mcp [command] [options]
```

The CLI is registered as `ensemble-mcp` via the `pyproject.toml` entry point (`ensemble_mcp.__main__:main`).

Running `ensemble-mcp` with no command defaults to `serve`.

---

## Commands

### `serve` (default)

Start the MCP server on stdio. This is the default when no subcommand is given.

```bash
ensemble-mcp
ensemble-mcp serve
```

The server:
- Prints a startup banner to **stderr** (stdout is reserved for MCP protocol)
- Downloads the ONNX model on first run (~22 MB)
- Creates/opens the SQLite database at the configured path
- Listens for MCP tool calls on stdin/stdout

---

### `web`

Start the local web dashboard.

```bash
ensemble-mcp web [options]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--port` | int | `8787` | Port to bind on |
| `--no-open` | flag | `false` | Don't auto-open browser |
| `--reports-dir` | path | auto | Directory containing Bug Hunter report files |

**Examples:**

```bash
# Start dashboard on default port
ensemble-mcp web

# Custom port, no auto-open
ensemble-mcp web --port 9000 --no-open

# Specify reports directory
ensemble-mcp web --reports-dir ./reports
```

The dashboard binds to `127.0.0.1` only (local access, no authentication required). If the port is already in use, an error message suggests the next port.

**Reports directory auto-detection:** When `--reports-dir` is not specified, the dashboard looks for a `reports/` directory in (1) the current working directory, then (2) the git repository root.

---

### `install`

Auto-detect AI tools and register `ensemble-mcp` in their MCP configs.

```bash
ensemble-mcp install [options]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--local` | flag | `false` | Register in project-local configs instead of global |
| `--project-path` | path | cwd | Project root directory |
| `--tools` | string | all | Comma-separated list of tools (e.g. `--tools opencode,cursor`) |
| `--dry-run` | flag | `false` | Show plan without making changes |
| `--yes`, `-y` | flag | `false` | Skip confirmation prompt |

**Supported tool names:** `opencode`, `claude_code`, `copilot`, `cursor`, `windsurf`, `devin`

**Examples:**

```bash
# Auto-detect and register globally
ensemble-mcp install

# Register only in Cursor and OpenCode
ensemble-mcp install --tools cursor,opencode

# Project-local registration
ensemble-mcp install --local

# Preview without changes
ensemble-mcp install --dry-run

# Non-interactive (CI/CD)
ensemble-mcp install --yes
```

The installer:
1. Detects installed AI tools by checking for config directories
2. Displays a plan showing what will be registered
3. Creates backups of existing config files (`.bak`)
4. Registers the MCP server entry
5. Copies bundled agent files to tool-specific directories
6. Copies bundled skill files to project-local directories

---

### `uninstall`

Remove `ensemble-mcp` registration from AI tool configs.

```bash
ensemble-mcp uninstall [options]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--local` | flag | `false` | Remove from project-local configs |
| `--project-path` | path | cwd | Project root directory |
| `--tools` | string | all | Comma-separated list of tools |
| `--remove-agents` | flag | `false` | Also remove agent/skill files |
| `--clean-data` | flag | `false` | Remove `~/.cache/ensemble-mcp/` and `~/.config/ensemble-mcp/` |
| `--dry-run` | flag | `false` | Show plan without making changes |
| `--yes`, `-y` | flag | `false` | Skip confirmation prompt |

**Examples:**

```bash
# Remove from all detected tools
ensemble-mcp uninstall

# Full cleanup: deregister, remove agents, delete data
ensemble-mcp uninstall --remove-agents --clean-data --yes

# Preview uninstall plan
ensemble-mcp uninstall --dry-run
```

---

### `add-agents`

Copy bundled agent files to tool-specific directories without MCP registration.

```bash
ensemble-mcp add-agents [options]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--local` | flag | `false` | Copy to project-local agent dirs |
| `--project-path` | path | cwd | Project root directory |
| `--tools` | string | all | Comma-separated list of tools |
| `--dry-run` | flag | `false` | Show plan without making changes |
| `--yes`, `-y` | flag | `false` | Skip confirmation prompt |

Bundled agents include the 7-agent orchestration pipeline: `team-ensemble`, `team-scope`, `team-craft`, `team-forge`, `team-trace`, `team-lens`, `team-signal`.

**Examples:**

```bash
# Copy agents globally for all detected tools
ensemble-mcp add-agents

# Copy agents locally for OpenCode only
ensemble-mcp add-agents --local --tools opencode
```

---

### `add-skills`

Copy bundled skill files to tool-specific directories without MCP registration.

```bash
ensemble-mcp add-skills [options]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--local` | flag | default | Copy to project-local skill dirs (default) |
| `--global` | flag | `false` | Copy to global skill dirs instead |
| `--project-path` | path | cwd | Project root directory |
| `--tools` | string | all | Comma-separated list of tools |
| `--dry-run` | flag | `false` | Show plan without making changes |
| `--yes`, `-y` | flag | `false` | Skip confirmation prompt |

> **Note:** `add-skills` defaults to **local** scope (unlike `add-agents` which defaults to global). Use `--global` to override.

Bundled skills include the `ensemble-mcp-workflow` skill that teaches AI agents when and how to invoke ensemble-mcp tools.

**Examples:**

```bash
# Copy skills locally (default)
ensemble-mcp add-skills

# Copy skills globally
ensemble-mcp add-skills --global

# Preview what would be copied
ensemble-mcp add-skills --dry-run
```

---

## Environment Variables

All settings fields can be overridden via environment variables with the `ENSEMBLE_MCP_` prefix:

| Variable | Type | Description |
|----------|------|-------------|
| `ENSEMBLE_MCP_DB_PATH` | path | Override database file location |
| `ENSEMBLE_MCP_CACHE_DIR` | path | Override cache directory |
| `ENSEMBLE_MCP_MODEL_DIR` | path | Override model directory |
| `ENSEMBLE_MCP_MAX_PATTERNS` | int | Maximum stored patterns |
| `ENSEMBLE_MCP_DEFAULT_TOP_K` | int | Default search result count |
| `ENSEMBLE_MCP_DEFAULT_MIN_SCORE` | float | Minimum similarity threshold |
| `ENSEMBLE_MCP_DRIFT_THRESHOLD_ALIGNED` | float | Drift score below which changes are "aligned" |
| `ENSEMBLE_MCP_DRIFT_THRESHOLD_MINOR` | float | Drift score below which changes are "minor" |
| `ENSEMBLE_MCP_IDEMPOTENCY_KEY_TTL_HOURS` | int | Hours before idempotency keys expire |

See [Configuration](./configuration.md) for the full list of settings.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (invalid args, port in use, unknown tool names, etc.) |

## Next Steps

- [Configuration](./configuration.md) — config file format and all options
- [MCP Client Setup](./mcp-clients.md) — per-tool registration details
