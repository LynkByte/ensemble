# ensemble-mcp

A Python MCP (Model Context Protocol) server that provides **vector memory**, **token tracking**, **drift detection**, **model routing**, **skills discovery**, **session management**, and **codebase indexing** for AI-assisted development pipelines.

All intelligence is local -- zero LLM/API calls. Uses ONNX Runtime embeddings (~5ms), numpy cosine similarity, tiktoken counting, and SQLite storage.

---

## Features

| Feature | What It Does |
|---------|-------------|
| **Pattern Memory** | Semantic vector search over stored pipeline patterns (MiniLM-L6-v2, 384-dim) |
| **Token Tracking** | Per-agent cost breakdown with 3-tier source precedence (direct > parser > estimation) |
| **Drift Detection** | Cosine similarity between task description and code changes |
| **Model Routing** | Recommend model tier (best/mid/cheapest) per agent and task complexity |
| **Skills Discovery** | Scan `.ai/skills/`, `.claude/skills/`, `.cursor/rules/` etc. with semantic search |
| **Skill Intelligence** | Auto-detect recurring patterns and suggest converting them to reusable skills |
| **Session Management** | Pipeline checkpoint save/load with optimistic versioning |
| **Codebase Indexing** | File-level index with exports, imports, roles -- incremental via mtime |
| **CLI Dashboard** | Terminal-based metrics display with cost breakdowns and trends |
| **Auto-Installer** | Detect AI tools and register the MCP server in their configs |

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

# Copy agent files to a project (no MCP registration needed)
ensemble-mcp add-agents --tools opencode

# Copy skill files to a project (no MCP registration needed)
ensemble-mcp add-skills --tools opencode

# Show terminal metrics dashboard
ensemble-mcp dashboard
```

## MCP Client Configuration

### OpenCode

Add to `~/.config/opencode/opencode.json` or project `opencode.json`:

```json
{
  "mcpServers": {
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
  "mcpServers": {
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

## 21 MCP Tools

### Patterns (semantic memory)

| Tool | Description |
|------|-------------|
| `patterns_search` | Semantic search over stored patterns |
| `patterns_store` | Store a new pattern with embedding |
| `patterns_prune` | Remove old/unused patterns |

### Metrics (token tracking)

| Tool | Description |
|------|-------------|
| `metrics_start_session` | Start tracking a pipeline session |
| `metrics_record_step` | Record per-agent token/cost usage |
| `metrics_end_session` | Finalize session, compute totals |
| `metrics_session_report` | Generate formatted session report |
| `metrics_trend` | Cost/token trends over time |
| `metrics_compare` | Compare two sessions |

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

Confidence indicators: `exact` (provider data), `partial` (mixed sources), `estimated` (tiktoken only).

## Architecture

```
ensemble-mcp/
  src/ensemble_mcp/
    server.py             # MCP server + tool registration
    config/               # Settings, defaults, model pricing
    contracts/            # Response envelope, error taxonomy
    memory/               # ONNX embeddings, SQLite vector store, cosine similarity
    parsers/              # OpenCode + Claude Code session file parsers
    security/             # Secret redaction, trust boundaries
    state/                # Session/step lifecycle, idempotency, locks
    tools/                # 21 MCP tool implementations
    installer/            # AI tool detection + MCP registration
    cli/                  # Terminal dashboard
```

### Technology Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.11+ |
| Distribution | `uvx` (zero-hassle cross-platform) |
| MCP Framework | `mcp` (official Python SDK) |
| Embeddings | ONNX Runtime + MiniLM-L6-v2 (~22MB, 384-dim) |
| Vector Storage | SQLite + numpy cosine similarity |
| Token Counting | tiktoken (local BPE tokenizer) |
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

# Run tests (451 tests, ~6s)
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
| OpenCode | TOML | Yes |
| Claude Code | JSON | Yes |
| GitHub Copilot (VS Code) | JSON | Yes |
| Cursor | JSON | Yes |
| Windsurf | JSON | Yes |
| Devin CLI | JSON | Yes |

## License

[MIT](LICENSE)
