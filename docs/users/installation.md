# Installation Guide

Detailed installation instructions for `ensemble-mcp`, covering multiple install methods, system requirements, and upgrade procedures.

## System Requirements

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| Python | 3.11+ | 3.12 and 3.13 also supported |
| OS | Linux, macOS, Windows | Any platform with Python support |
| Disk Space | ~50 MB | ~22 MB for ONNX model + DB + package |
| RAM | ~100 MB | ONNX Runtime embedding model |

### Runtime Dependencies

These are installed automatically via pip:

| Package | Version | Purpose |
|---------|---------|---------|
| `mcp` | ≥1.0 | MCP protocol implementation |
| `onnxruntime` | ≥1.17 | Local embedding model inference |
| `numpy` | ≥2.4.4 | Vector operations and cosine similarity |
| `tokenizers` | ≥0.15 | Tokenizer for the embedding model |
| `rich` | ≥15.0.0 | Terminal output formatting |
| `aiohttp` | ≥3.9 | Web dashboard HTTP server |

## Install from PyPI

The recommended installation method:

```bash
pip install ensemble-mcp
```

### Using uvx (No Install)

With [uv](https://docs.astral.sh/uv/), you can run without installing:

```bash
uvx ensemble-mcp
```

### Using pipx (Isolated Install)

For a globally available, isolated installation:

```bash
pipx install ensemble-mcp
```

### Command Detection During Registration

When you run `ensemble-mcp install`, the installer automatically detects how `ensemble-mcp` is available and registers the appropriate command in each AI tool's config:

| Priority | Detection | Registered Command |
|----------|-----------|-------------------|
| 1st | `ensemble-mcp` on PATH (pip/pipx) | `ensemble-mcp` |
| 2nd | `uvx` on PATH | `uvx ensemble-mcp` |
| 3rd | Neither found | `/path/to/python -m ensemble_mcp` (full `sys.executable` path) |

The installer prefers a direct `ensemble-mcp` binary first because it's the most specific and reliable — it confirms the package is actually installed locally. The `uvx` fallback can auto-fetch from PyPI but may fail on private networks or if the package hasn't been published yet. The final fallback uses the current Python interpreter's absolute path (e.g. `/home/user/.venv/bin/python`), not the bare `python` command, to ensure the correct environment is used.

## Install from Source

Clone the repository and install in editable mode:

```bash
git clone https://github.com/LynkByte/ensemble.git
cd ensemble

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows

pip install -e .
```

### With Development Dependencies

To also install testing and linting tools:

```bash
pip install -e ".[dev]"
```

This adds: `pytest`, `pytest-asyncio`, `pytest-aiohttp`, `pytest-cov`, `ruff`, `mypy`, and `build`.

## Docker

Build and run the server in a container:

```bash
# Build the image
docker build -t ensemble-mcp .

# Run the server (stdio mode)
docker run -i ensemble-mcp

# Run with a persistent data volume
docker run -i -v ensemble-data:/root/.cache/ensemble-mcp ensemble-mcp
```

> **Note:** When running in Docker, the MCP server communicates over stdio. Your AI tool must be configured to launch the container instead of a local command.

## Verifying Installation

After installing, verify the CLI is available:

```bash
# Check the command exists
ensemble-mcp --help

# Run the server (Ctrl+C to stop)
ensemble-mcp

# Check server health via the web dashboard
ensemble-mcp web
```

The first run will automatically:

1. Create `~/.cache/ensemble-mcp/` directory
2. Download the ONNX embedding model (~22 MB) to `~/.cache/ensemble-mcp/models/`
3. Create the SQLite database at `~/.cache/ensemble-mcp/data.db`
4. Initialize all 14 tables (13 data tables + 1 schema version tracker) and indexes

The model download is a one-time operation. Subsequent starts are fast (~50ms).

> **Note:** If you get `ModuleNotFoundError: No module named 'ensemble_mcp'` after install, ensure your virtual environment is activated and try `pip install -e .` again.

## Upgrading

### From PyPI

```bash
pip install --upgrade ensemble-mcp
```

### From Source

```bash
cd ensemble
git pull
pip install -e .
```

### Database Migrations

Schema migrations are applied automatically on startup. The server uses `ensure_schema()` to create or update tables as needed. Your existing data is preserved across upgrades.

## Data Locations

| Path | Contents |
|------|----------|
| `~/.cache/ensemble-mcp/data.db` | SQLite database (WAL mode) — patterns, sessions, indexes |
| `~/.cache/ensemble-mcp/data.db-wal` | SQLite WAL journal file (appears alongside `data.db`) |
| `~/.cache/ensemble-mcp/data.db-shm` | SQLite shared memory file (appears alongside `data.db`) |
| `~/.cache/ensemble-mcp/models/` | ONNX MiniLM-L6-v2 model files (~22 MB) |
| `~/.config/ensemble-mcp/config.toml` | Global configuration file (optional) |
| `.ensemble-mcp.toml` | Per-project configuration (optional, in project root) |

## Uninstalling

Remove ensemble-mcp registration from all AI tools:

```bash
ensemble-mcp uninstall
```

To also remove agent/skill files and cached data:

```bash
ensemble-mcp uninstall --remove-agents --clean-data
```

Then remove the package:

```bash
pip uninstall ensemble-mcp
```

Or if installed via uvx:

```bash
uvx uninstall ensemble-mcp
```

## Platform Notes

- **Linux/macOS**: Fully supported. File-based advisory locks use `fcntl`.
- **Windows**: Partial support. The `fcntl` module in `state/locks.py` is Unix-only — advisory locking will not work on Windows. The core server functions work, but concurrent access safety is not guaranteed.

## Next Steps

- [CLI Reference](./cli-reference.md) — all commands and options
- [Configuration](./configuration.md) — customize behavior
- [MCP Client Setup](./mcp-clients.md) — register with your AI tool
