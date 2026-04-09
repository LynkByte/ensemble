# Setup Guide

Installation, configuration, and integration instructions for **ensemble-mcp**.

## System Requirements

| Requirement | Minimum |
|---|---|
| Python | 3.11+ |
| OS | Linux, macOS (Windows partial — see [Platform Notes](#platform-notes)) |
| Disk | ~50 MB (22 MB ONNX model + SQLite DB) |
| RAM | ~100 MB at runtime |

## Installation

### From Source (Recommended for Development)

```bash
git clone <repo-url> ensemble
cd ensemble

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install with dev dependencies
pip install -e ".[dev]"
```

### Production Install

```bash
pip install -e .
```

This installs the `ensemble-mcp` CLI command and all runtime dependencies:

| Package | Purpose |
|---|---|
| `mcp>=1.0` | MCP protocol server |
| `onnxruntime>=1.17` | ONNX model inference for embeddings |
| `numpy>=1.26` | Vector math (cosine similarity) |
| `tokenizers>=0.15` | HuggingFace tokenizer for MiniLM |
| `rich>=13.0` | Terminal formatting and startup banner |

## Running the Server

```bash
# Direct
ensemble-mcp

# Or via module
python -m ensemble_mcp
```

The server communicates over **stdio** using the MCP protocol. It is not an HTTP server — it is launched by an MCP client (OpenCode, Claude Code, etc.) as a subprocess.

## First Run

On first startup, ensemble-mcp will:

1. Create `~/.cache/ensemble-mcp/` directory
2. Download the ONNX MiniLM-L6-v2 model (~22 MB) to `~/.cache/ensemble-mcp/models/`
3. Create the SQLite database at `~/.cache/ensemble-mcp/data.db` with WAL mode enabled
4. Initialize all 12 tables and indexes

The model download is a one-time operation. Subsequent starts are fast (~50ms).

## Verifying the Installation

After installing, verify with:

```bash
# Check the CLI entry point exists
ensemble-mcp --help 2>/dev/null || echo "Server runs via stdio — no --help flag"

# Run the test suite
python -m pytest tests/ -v

# Quick lint check
ruff check src/ tests/
```

You can also verify the server starts correctly by checking that it responds to the `health` tool. See the [MCP Client Configuration](#mcp-client-configuration) section below for how to connect a client.

## Configuration

ensemble-mcp uses layered configuration with deterministic merge order:

```
1. Package defaults (built-in)
2. Global config   (~/.config/ensemble-mcp/config.toml)
3. Project config  (.ensemble-mcp.toml in project root)
4. Environment vars (ENSEMBLE_MCP_*)
```

Higher layers override lower layers. Scalar values replace; maps merge shallowly; lists replace.

### Global Config

Create `~/.config/ensemble-mcp/config.toml`:

```toml
# Override default thresholds
drift_threshold_aligned = 0.25
drift_threshold_minor = 0.5
default_top_k = 5
idempotency_key_ttl_hours = 48
```

### Project Config

Create `.ensemble-mcp.toml` in your project root:

```toml
# Project-specific overrides
default_prune_max_age_days = 60
cluster_similarity_threshold = 0.8
```

### Environment Variables

All settings can be overridden via `ENSEMBLE_MCP_` prefixed environment variables:

```bash
export ENSEMBLE_MCP_DB_PATH="/custom/path/data.db"
export ENSEMBLE_MCP_DEFAULT_TOP_K=10
export ENSEMBLE_MCP_DRIFT_THRESHOLD_ALIGNED=0.25
```

### Available Settings

| Setting | Type | Default | Description |
|---|---|---|---|
| `cache_dir` | Path | `~/.cache/ensemble-mcp` | Root cache directory |
| `db_path` | Path | `~/.cache/ensemble-mcp/data.db` | SQLite database path |
| `model_dir` | Path | `~/.cache/ensemble-mcp/models` | ONNX model directory |
| `max_patterns` | int | 10,000 | Maximum stored patterns |
| `default_top_k` | int | 3 | Default search results count |
| `default_min_score` | float | 0.3 | Minimum similarity score |
| `default_prune_max_age_days` | int | 90 | Pattern prune age threshold |
| `drift_threshold_aligned` | float | 0.3 | Drift score below this = "aligned" |
| `drift_threshold_minor` | float | 0.6 | Drift score below this = "minor_drift" |
| `cluster_similarity_threshold` | float | 0.75 | Skill clustering threshold |
| `default_min_cluster_size` | int | 3 | Min patterns for a skill suggestion |
| `default_stale_threshold_days` | int | 60 | Days before a skill is "stale" |
| `idempotency_key_ttl_hours` | int | 24 | Idempotency key expiration |

## MCP Client Configuration

### OpenCode

Add to your OpenCode MCP config (`~/.config/opencode/config.json` or project `config.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "ensemble": {
      "type": "local",
      "command": ["ensemble-mcp"]
    }
  }
}
```

Or if using a virtual environment:

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

Add to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "ensemble": {
      "command": "ensemble-mcp",
      "args": []
    }
  }
}
```

## Adding Agents and Skills Separately

If ensemble-mcp is already registered but you need to add agent or skill files to a project (e.g. cloning a repo that doesn't have them yet), use the dedicated commands:

```bash
# Copy bundled agent files to tool-specific directories
ensemble-mcp add-agents --tools opencode

# Copy bundled skill files to tool-specific directories
ensemble-mcp add-skills --tools opencode
```

These commands do **not** touch MCP config files — they only copy agent/skill files. They also do not require the AI tool to be installed, so you can pre-seed files before setting up the tool.

| Flag | Description |
|------|-------------|
| `--tools` | Comma-separated tool names (default: all known tools) |
| `--local` | Copy to project-local directories (default for skills) |
| `--global` | Copy to global directories (default for agents) |
| `--dry-run` | Show the plan without making changes |
| `--yes` | Skip confirmation prompt |

## Data Locations

| Path | Contents |
|---|---|
| `~/.cache/ensemble-mcp/data.db` | SQLite database (WAL mode) |
| `~/.cache/ensemble-mcp/data.db-wal` | WAL journal file |
| `~/.cache/ensemble-mcp/data.db-shm` | Shared memory file |
| `~/.cache/ensemble-mcp/models/` | ONNX MiniLM-L6-v2 model (~22 MB) |
| `~/.config/ensemble-mcp/config.toml` | Global user configuration |

## Platform Notes

- **Linux/macOS**: Fully supported. File-based advisory locks use `fcntl`.
- **Windows**: Partial support. The `fcntl` module in `state/locks.py` is Unix-only. The core server functions work, but `advisory_lock()` will fail. This is a known limitation for Phase 1.

## Troubleshooting

### Model download fails

If the ONNX model fails to download on first run (firewall, proxy, etc.), manually download:

```bash
mkdir -p ~/.cache/ensemble-mcp/models
curl -L -o ~/.cache/ensemble-mcp/models/model.onnx \
  "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/onnx/model.onnx"
curl -L -o ~/.cache/ensemble-mcp/models/tokenizer.json \
  "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/tokenizer.json"
```

### Database locked errors

The SQLite database uses WAL mode with a 5-second busy timeout. If you see `database is locked` errors:

1. Ensure only one server process is running
2. Check for stale lock files
3. Increase the busy timeout if needed

### Import errors after install

If you get `ModuleNotFoundError` for ensemble_mcp:

```bash
# Ensure you installed in the correct environment
which python
pip show ensemble-mcp

# Reinstall if needed
pip install -e .
```
