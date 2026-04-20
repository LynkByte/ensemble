# AI Tool Compatibility Guide

Which AI tools work with `ensemble-mcp`, what gets installed where, and which MCP tools each tool can use.

---

## Supported AI Tools

| AI Tool | MCP Server | Agents | Skills | Auto-Detect |
|---------|:---:|:---:|:---:|:---:|
| **OpenCode** | Yes | Yes | Yes | Yes |
| **Claude Code** | Yes | Yes | Yes | Yes |
| **GitHub Copilot** (VS Code) | Yes | No | No | Yes |
| **Cursor** | Yes | No | Yes | Yes |
| **Windsurf** | Yes | No | No | Yes |
| **Devin CLI** | Yes | No | Yes | Yes |
| **Any MCP-compatible tool** | Yes (manual) | Manual | Manual | No |

> **All 6 supported tools use JSON config.** The installer auto-detects them, creates backups, and registers in one command.

---

## What Gets Installed

### 1. MCP Server Registration

The core integration — registers `ensemble-mcp` as an MCP server so the AI tool can call all 19 tools.

| Tool | Global Config File | Local Config File | Config Key |
|------|---|---|---|
| OpenCode | `~/.config/opencode/config.json` | `config.json` | `mcp.ensemble` |
| Claude Code | `~/.claude.json` | `.claude.json` | `mcpServers.ensemble` |
| GitHub Copilot | `~/.vscode/mcp.json` | `.vscode/mcp.json` | `servers.ensemble` |
| Cursor | `~/.cursor/mcp.json` | `.cursor/mcp.json` | `mcpServers.ensemble` |
| Windsurf | `~/.windsurf/mcp.json` | `.windsurf/mcp.json` | `mcpServers.ensemble` |
| Devin CLI | `~/.devin/mcp.json` | `.devin/mcp.json` | `mcpServers.ensemble` |

### 2. Agent Files (7 agents)

The multi-agent pipeline agents. Only some tools have agent directories:

| Agent File | Purpose | OpenCode | Claude Code |
|---|---|:---:|:---:|
| `team-ensemble.md` | Captain / orchestrator | Yes | Yes |
| `team-scope.md` | Architect / planner | Yes | Yes |
| `team-craft.md` | Engineer / code writer | Yes | Yes |
| `team-forge.md` | Builder / test runner | Yes | Yes |
| `team-lens.md` | Inspector / code reviewer | Yes | Yes |
| `team-signal.md` | Shipper / git ops | Yes | Yes |
| `team-trace.md` | Hunter / bug detector | Yes | Yes |

**Agent file locations:**

| Tool | Global | Local |
|------|---|---|
| OpenCode | `~/.config/opencode/agents/` | `.opencode/agents/` |
| Claude Code | `~/.claude/agents/` | `.claude/agents/` |

> GitHub Copilot, Cursor, Windsurf, and Devin CLI don't have native agent directory support. You can still use ensemble-mcp tools directly — you just won't get the multi-agent pipeline.

### 3. Skill Files (1 bundled skill)

The `ensemble-mcp-workflow` skill teaches any AI agent when and how to call the 19 MCP tools.

| Tool | Local Skill Location | Skill Format |
|------|---|---|
| OpenCode | `.opencode/skills/ensemble-mcp-workflow/SKILL.md` | Directory (`<name>/SKILL.md`) |
| Claude Code | `.claude/skills/ensemble-mcp-workflow.md` | Flat (`.md` file) |
| Cursor | `.cursor/rules/ensemble-mcp-workflow.md` | Flat (`.md` file) |
| Devin CLI | `.devin/ensemble-mcp-workflow.md` | Flat (`.md` file) |

> GitHub Copilot and Windsurf don't have native skill directories.

---

## The 19 MCP Tools — What Each Tool Can Use

**Every AI tool that has the MCP server registered gets access to all 19 tools.** The MCP server is identical regardless of which tool connects. The difference is in how well each tool can *leverage* them.

### Full Tool List

| # | Tool | Category | What It Does |
|---|------|----------|---|
| 1 | `patterns_search` | Memory | Semantic search over stored patterns from past tasks |
| 2 | `patterns_store` | Memory | Save a new pattern (problem + approach + outcome) |
| 3 | `patterns_prune` | Memory | Clean up old/unused patterns |
| 4 | `drift_check` | Drift | Check if code changes drifted from the original task |
| 5 | `model_recommend` | Routing | Recommend model tier (best/mid/cheapest) for agent + task |
| 6 | `skills_discover` | Skills | Scan skill directories, find relevant skills by query |
| 7 | `skills_suggest` | Skills | Detect recurring patterns, propose as reusable skills |
| 8 | `skills_generate` | Skills | Accept/dismiss/defer a skill suggestion |
| 9 | `session_save` | Session | Save pipeline checkpoint (with optimistic versioning) |
| 10 | `session_load` | Session | Load latest or specific checkpoint |
| 11 | `session_search` | Session | Search past sessions by semantic similarity |
| 12 | `project_index` | Indexer | Build/refresh the codebase index |
| 13 | `project_query` | Indexer | Find files by type, path pattern, or semantic query |
| 14 | `project_dependencies` | Indexer | Get import/dependency graph for a file |
| 15 | `project_snapshot` | Indexer | Generate compact project baseline summary |
| 16 | `context_compress` | Compress | Compress verbose text to save tokens |
| 17 | `context_prepare` | Compress | Order prompt sections for optimal LLM cache hits |
| 18 | `health` | Utility | Server health check (status, version, DB size) |
| 19 | `reset` | Utility | Delete all stored data (destructive) |

### Which Tools Matter Most Per AI Tool

#### OpenCode — Full Pipeline Support

OpenCode gets the richest experience because it supports agents, skills, and MCP:

| Pipeline Phase | MCP Tools Used | Why |
|---|---|---|
| **Pre-pipeline** | `project_index`, `project_snapshot`, `patterns_search`, `skills_discover`, `model_recommend` | Build context, find past solutions, choose model tier |
| **Planning** | `project_query`, `project_dependencies`, `session_search` | Explore codebase, find related sessions |
| **Implementation** | `session_save`, `context_compress` | Checkpoint progress, reduce token usage |
| **Post-implementation** | `drift_check` | Verify changes match the task |
| **Testing & review** | `session_save` | Update checkpoint after tests pass |
| **Completion** | `patterns_store`, `session_save` | Save approach for future recall |
| **Maintenance** | `patterns_prune`, `skills_suggest`, `skills_generate` | Clean up, create reusable skills |

#### Claude Code — Full Pipeline Support

Same pipeline as OpenCode — supports agents, skills, and MCP:

| Pipeline Phase | MCP Tools Used |
|---|---|
| **Pre-pipeline** | `project_index`, `project_snapshot`, `patterns_search`, `skills_discover`, `model_recommend` |
| **Planning** | `project_query`, `project_dependencies`, `session_search` |
| **Implementation** | `session_save`, `context_compress` |
| **Post-implementation** | `drift_check` |
| **Completion** | `patterns_store`, `session_save` |
| **Maintenance** | `patterns_prune`, `skills_suggest`, `skills_generate` |

#### GitHub Copilot — MCP Tools Only

No agents or skills, but all 19 MCP tools are callable. Best used as a standalone assistant:

| Use Case | MCP Tools |
|---|---|
| **Explore a codebase** | `project_index`, `project_snapshot`, `project_query`, `project_dependencies` |
| **Remember past work** | `patterns_search`, `patterns_store`, `patterns_prune` |
| **Check drift** | `drift_check` |
| **Resume work** | `session_save`, `session_load`, `session_search` |
| **Compress context** | `context_compress`, `context_prepare` |
| **Server status** | `health` |

#### Cursor — MCP Tools + Skills

Has skill support (via `.cursor/rules/`) so the workflow skill teaches it when to call tools:

| Use Case | MCP Tools |
|---|---|
| **Explore a codebase** | `project_index`, `project_snapshot`, `project_query`, `project_dependencies` |
| **Remember past work** | `patterns_search`, `patterns_store` |
| **Check drift** | `drift_check` |
| **Resume work** | `session_save`, `session_load`, `session_search` |
| **Find/create skills** | `skills_discover`, `skills_suggest`, `skills_generate` |
| **Compress context** | `context_compress`, `context_prepare` |

#### Windsurf — MCP Tools Only

Same as Copilot — all 19 tools callable, no agents or skills:

| Use Case | MCP Tools |
|---|---|
| **Explore a codebase** | `project_index`, `project_snapshot`, `project_query`, `project_dependencies` |
| **Remember past work** | `patterns_search`, `patterns_store`, `patterns_prune` |
| **Check drift** | `drift_check` |
| **Resume work** | `session_save`, `session_load`, `session_search` |
| **Compress context** | `context_compress`, `context_prepare` |

#### Devin CLI — MCP Tools + Skills

Has skill support (via `.devin/`) for the workflow skill:

| Use Case | MCP Tools |
|---|---|
| **Explore a codebase** | `project_index`, `project_snapshot`, `project_query`, `project_dependencies` |
| **Remember past work** | `patterns_search`, `patterns_store` |
| **Check drift** | `drift_check` |
| **Resume work** | `session_save`, `session_load`, `session_search` |
| **Find/create skills** | `skills_discover`, `skills_suggest`, `skills_generate` |
| **Compress context** | `context_compress`, `context_prepare` |

---

## Capability Tiers at a Glance

| Tier | What You Get | AI Tools |
|------|---|---|
| **Full Pipeline** | 7 agents + workflow skill + 19 MCP tools | OpenCode, Claude Code |
| **Tools + Skills** | Workflow skill + 19 MCP tools (single-agent mode) | Cursor, Devin CLI |
| **Tools Only** | 19 MCP tools (manual invocation) | GitHub Copilot, Windsurf |
| **Manual Setup** | 19 MCP tools (register yourself) | Any MCP-compatible tool |

---

## Multi-Agent Pipeline (Full Pipeline tier only)

When using OpenCode or Claude Code with the full agent set, the 7 agents use MCP tools at specific pipeline phases:

| Agent | Role | MCP Tools It Uses |
|---|---|---|
| **team-ensemble** (Captain) | Orchestrates the pipeline | `patterns_search`, `model_recommend`, `session_search`, `session_save`, `drift_check`, `patterns_store`, `skills_discover`, `project_index`, `project_snapshot` |
| **team-scope** (Architect) | Plans and explores | `project_query`, `project_dependencies`, `project_snapshot`, `skills_discover` |
| **team-craft** (Engineer) | Writes code | `project_dependencies`, `context_compress`, `session_save` |
| **team-forge** (Builder) | Formats, builds, tests | `drift_check`, `session_save` |
| **team-lens** (Inspector) | Reviews code | `context_prepare`, `drift_check` |
| **team-signal** (Shipper) | Git commit/push | `session_save`, `patterns_store` |
| **team-trace** (Hunter) | Finds bugs | `project_query`, `patterns_search` |

---

## Quick Install Commands

```bash
# Auto-detect all tools and register everything
ensemble-mcp install

# Register only specific tools
ensemble-mcp install --tools cursor,opencode

# Project-local instead of global
ensemble-mcp install --local

# Preview what would happen (no changes)
ensemble-mcp install --dry-run

# Non-interactive (CI/CD)
ensemble-mcp install --yes

# Copy just agent files (no MCP registration)
ensemble-mcp add-agents

# Copy just skill files (no MCP registration)
ensemble-mcp add-skills

# Remove everything
ensemble-mcp uninstall --remove-agents --clean-data
```

---

## Manual Registration (Any MCP Tool)

For any MCP-compatible tool not listed above:

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

The server uses **stdio transport** — reads MCP requests from stdin, writes responses to stdout. All 19 tools become available immediately after registration.

---

## Next Steps

- [Installation](./installation.md) — system requirements and install methods
- [MCP Client Setup](./mcp-clients.md) — detailed per-tool config examples
- [Tool Reference](./tool-reference.md) — full parameter docs for all 19 tools
- [Integration Guide](./integration-guide.md) — pipeline patterns and invocation examples
- [CLI Reference](./cli-reference.md) — all install/uninstall flags
