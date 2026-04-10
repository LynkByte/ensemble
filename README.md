# ensemble-mcp

A Python MCP (Model Context Protocol) server that provides **vector memory**, **drift detection**, **model routing**, **skills discovery**, **session management**, and **codebase indexing** for AI-assisted development pipelines.

All intelligence is local — zero LLM/API calls. Uses ONNX Runtime embeddings (~5ms), numpy cosine similarity, and SQLite storage.

---

## Features

| Feature | What It Does |
|---------|-------------|
| **Pattern Memory** | Semantic vector search over stored pipeline patterns (MiniLM-L6-v2, 384-dim) |
| **Drift Detection** | Cosine similarity between task description and code changes |
| **Model Routing** | Recommend model tier (best/mid/cheapest) per agent and task complexity |
| **Skills Discovery** | Scan `.ai/skills/`, `.claude/skills/`, `.cursor/rules/` etc. with semantic search |
| **Skill Intelligence** | Auto-detect recurring patterns and suggest converting them to reusable skills |
| **Session Management** | Pipeline checkpoint save/load with optimistic versioning |
| **Codebase Indexing** | File-level index with exports, imports, roles — incremental via mtime |
| **Auto-Installer** | Detect AI tools and register the MCP server in their configs |
| **Web Dashboard** | Local browser UI at `localhost:8787` for visualizing patterns, skills, projects, drift, and sessions |

## Quick Start

### Install from source

```bash
git clone https://github.com/LynkByte/ensemble.git
cd ensemble
pip install -e ".[dev]"
```

### Install via uvx (after PyPI publish)

```bash
uvx ensemble-mcp
```

### Run the server

```bash
# Start the MCP server (stdio protocol)
ensemble-mcp

# Or explicitly
ensemble-mcp serve
```

### Other CLI commands

```bash
# Auto-detect AI tools and register the MCP server
ensemble-mcp install

# Remove MCP server registration from AI tool configs
ensemble-mcp uninstall

# Copy agent files to a project (no MCP registration needed)
ensemble-mcp add-agents --tools opencode

# Copy skill files to a project (no MCP registration needed)
ensemble-mcp add-skills --tools opencode
```

### Web Dashboard

A local-only browser dashboard for visualizing patterns, skills, projects, drift history, and sessions.

```bash
# Start the dashboard (opens browser to http://localhost:8787)
ensemble-mcp web

# Custom port
ensemble-mcp web --port 9000

# Start without auto-opening the browser
ensemble-mcp web --no-open
```

The dashboard reads directly from the same SQLite database the MCP server writes to (WAL mode, no contention). It binds to `127.0.0.1` only — never exposed to the network, no authentication needed.

#### Dashboard Pages

| Page | What It Shows |
|------|--------------|
| **Overview** | Summary cards (patterns, skills, projects, drift checks), drift score trend chart, recent activity |
| **Patterns** | All stored patterns with match counts, project filtering, search |
| **Skills** | Pending skill suggestions with confidence scores, stale skill detection |
| **Projects** | Indexed projects with language breakdown pie charts, file role bar charts, export counts |
| **Drift** | Drift check history with scores, verdicts, flagged files, project filtering |
| **Sessions** | Session list with lifecycle status, click-through to step-by-step detail |

#### API Endpoints

All endpoints return the standard `ok/data/error/meta` envelope:

| Endpoint | Description |
|----------|-------------|
| `GET /api/summary` | Aggregate counts and recent activity |
| `GET /api/patterns` | Paginated pattern list (filter by `project`) |
| `GET /api/patterns/:id` | Single pattern detail with embedding metadata |
| `GET /api/skills` | Skill suggestions (filter by `project`, `status`) |
| `GET /api/skills/stale` | Skills not matched within threshold days |
| `GET /api/projects` | Indexed projects with file/export counts |
| `GET /api/projects/:path` | Project detail with language and role breakdown |
| `GET /api/drift` | Drift history (filter by `project`, `from`, `to`) |
| `GET /api/sessions` | Paginated session list (filter by `project`, `status`) |
| `GET /api/sessions/:id` | Session detail with steps |
| `GET /api/health` | Server health, version, DB size |

## MCP Client Configuration

### OpenCode

Add to `~/.config/opencode/config.json` or project `config.json`:

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

Or for a local development install:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "ensemble": {
      "type": "local",
      "command": ["/path/to/venv/bin/ensemble-mcp"]
    }
  }
}
```

### Claude Code

Add to `~/.claude/claude_desktop_config.json`:

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

### GitHub Copilot (VS Code)

Add to `.vscode/mcp.json`:

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

### Cursor

Add to `~/.cursor/mcp.json`:

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

### Windsurf

Add to `~/.windsurf/mcp.json`:

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

### Auto-Install

Instead of manual configuration, run the installer to auto-detect installed AI tools and register the server:

```bash
# Detect tools and register (interactive)
ensemble-mcp install

# Register specific tools only
ensemble-mcp install --tools opencode,cursor

# Preview without making changes
ensemble-mcp install --dry-run

# Non-interactive
ensemble-mcp install --yes
```

## 15 MCP Tools

### Patterns (semantic memory)

| Tool | Description |
|------|-------------|
| `patterns_search` | Semantic search over stored patterns |
| `patterns_store` | Store a new pattern with embedding |
| `patterns_prune` | Remove old/unused patterns |

### Drift Detection

| Tool | Description |
|------|-------------|
| `drift_check` | Cosine similarity between task and changes (0-1 score) |

### Model Routing

| Tool | Description |
|------|-------------|
| `model_recommend` | Recommend model tier for agent + task complexity |

### Skills

| Tool | Description |
|------|-------------|
| `skills_discover` | Scan skill directories with optional semantic search |
| `skills_suggest` | Detect recurring patterns, propose as reusable skills |
| `skills_generate` | Accept, dismiss, or defer a skill suggestion |

### Session

| Tool | Description |
|------|-------------|
| `session_save` | Save pipeline checkpoint with optimistic versioning |
| `session_load` | Load latest or specific checkpoint |

### Codebase Indexer

| Tool | Description |
|------|-------------|
| `project_index` | Build/refresh file-level codebase index |
| `project_query` | Query index by language, path, or text |
| `project_dependencies` | Get import/dependency graph for a file |

### Utility

| Tool | Description |
|------|-------------|
| `health` | Server health check |
| `reset` | Reset all data (destructive, requires confirmation) |

## Response Envelope

Every tool returns a standardized envelope:

```json
{
  "ok": true,
  "data": { "matches": [...] },
  "error": null,
  "meta": {
    "duration_ms": 12,
    "source": "sqlite",
    "confidence": "exact"
  }
}
```

Confidence indicators: `exact` (direct data), `partial` (mixed sources), `estimated` (heuristic).

## Architecture

```
ensemble-mcp/
  src/ensemble_mcp/
    server.py             # MCP server + tool registration
    config/               # Settings, defaults
    contracts/            # Response envelope, error taxonomy
    memory/               # ONNX embeddings, SQLite vector store, cosine similarity
    security/             # Secret redaction, trust boundaries
    state/                # Session/step lifecycle, idempotency, locks
    tools/                # 15 MCP tool implementations + call-recording utility
    installer/            # AI tool detection + MCP registration
    dashboard/            # Web dashboard (aiohttp server, JSON API, SPA frontend)
    cli/                  # Startup banner
    data/                 # Bundled agent and skill files
```

### Technology Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.11+ |
| Distribution | `uvx` (zero-hassle cross-platform) |
| MCP Framework | `mcp` (official Python SDK) |
| Embeddings | ONNX Runtime + MiniLM-L6-v2 (~22MB, 384-dim) |
| Vector Storage | SQLite + numpy cosine similarity |
| Tokenizer | HuggingFace `tokenizers` (for MiniLM input) |
| Package Size | ~90MB (including ONNX + model) |

### Local Storage

| Path | Contents |
|------|----------|
| `~/.cache/ensemble-mcp/data.db` | SQLite database (WAL mode) |
| `~/.cache/ensemble-mcp/models/` | ONNX MiniLM-L6-v2 model (~22MB) |
| `~/.config/ensemble-mcp/config.toml` | Global user configuration |

## Configuration

Layered config with deterministic merge order:

1. Package defaults (built-in)
2. Global config (`~/.config/ensemble-mcp/config.toml`)
3. Project config (`.ensemble-mcp.toml`)
4. Environment variables (`ENSEMBLE_MCP_*`)

```toml
# ~/.config/ensemble-mcp/config.toml
drift_threshold_aligned = 0.25
default_top_k = 5
cluster_similarity_threshold = 0.8
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests (619 tests, ~10s)
python -m pytest tests/ -v

# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/

# Type check
mypy src/

# Build package
python -m build
```

### Docker

```bash
docker build -t ensemble-mcp .
docker run --rm -v ~/.cache/ensemble-mcp:/home/app/.cache/ensemble-mcp ensemble-mcp
```

## Supported AI Tools

| AI Tool | Config Format | Auto-Install |
|---------|--------------|--------------|
| OpenCode | JSON | Yes |
| Claude Code | JSON | Yes |
| GitHub Copilot (VS Code) | JSON | Yes |
| Cursor | JSON | Yes |
| Windsurf | JSON | Yes |
| Devin CLI | JSON | Yes |

## License

[MIT](LICENSE)
