# Contributing

Guide for contributors to the **ensemble-mcp** project.

## Prerequisites

- Python 3.11+
- pip (recent version with `[extras]` support)
- Git

## Development Setup

```bash
# Clone the repository
git clone <repo-url> ensemble
cd ensemble

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"
```

This installs the package in editable mode plus development tools:

| Tool | Version | Purpose |
|---|---|---|
| pytest | >= 8.0 | Test runner |
| pytest-asyncio | >= 0.24 | Async test support |
| ruff | >= 0.4 | Linting and formatting |
| mypy | >= 1.10 | Static type checking |

## Running Tests

```bash
# Run the full test suite
python -m pytest tests/

# Run with verbose output
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_patterns.py -v

# Run a specific test
python -m pytest tests/test_patterns.py::test_store_and_search -v

# Run tests matching a pattern
python -m pytest tests/ -k "drift"

# Run tests excluding slow ones (model downloads)
python -m pytest tests/ -m "not slow"
```

### Test Architecture

Tests use a shared fixture system defined in `tests/conftest.py`:

- **`MockEmbeddingModel`** — Deterministic mock that generates consistent embeddings from text hashes instead of running ONNX inference. This makes tests fast (~0ms vs ~5ms per embed) and reproducible.
- **`tmp_db`** — Creates a temporary SQLite database in `/tmp` for each test session.
- **`test_conn`** — Returns a connection to the temporary database with WAL mode and all tables created.
- **`test_store`** — Returns a `VectorStore` wired to the mock embedding model and temporary database.

Tests are async by default (`asyncio_mode = "auto"` in pyproject.toml).

### Test Coverage

The project has 224 tests across 15 test files:

| Test File | Tests | Coverage |
|---|---|---|
| `test_contracts.py` | 30 | Envelope, ToolError, tool_handler decorator |
| `test_lifecycle.py` | 16 | Session/step state machine transitions |
| `test_idempotency.py` | 8 | Key storage, expiry, replay |
| `test_redaction.py` | 15 | All 9 secret patterns + edge cases |
| `test_trust.py` | 14 | Validators, confirmation enforcement |
| `test_similarity.py` | 13 | Cosine similarity, search, pairwise matrix |
| `test_embeddings.py` | 6 | Model loading, embed, normalize |
| `test_patterns.py` | 11 | Store, search, prune tools |
| `test_drift.py` | 5 | Drift check, verdicts, flags |
| `test_routing.py` | 9 | All agent/classification combinations |
| `test_metrics.py` | 16 | Session lifecycle, steps, reports, trends |
| `test_session.py` | 9 | Save, load, optimistic versioning |
| `test_indexer.py` | 18 | Index, query, dependencies, language parsers |
| `test_skills.py` | 10 | Discover, suggest, generate, clustering |
| `test_config.py` | 16 | Settings loading, TOML, env overrides |
| `test_parsers.py` | 2 | Phase 3 stub smoke tests |

## Linting and Formatting

```bash
# Lint (check for errors)
ruff check src/ tests/

# Lint with auto-fix
ruff check --fix src/ tests/

# Format code
ruff format src/ tests/

# Check formatting without changing files
ruff format --check src/ tests/

# Type checking
mypy src/
```

### Ruff Configuration

The project uses ruff with these rule sets (configured in `pyproject.toml`):

| Rule Set | ID | Purpose |
|---|---|---|
| pycodestyle errors | E | Basic style errors |
| pycodestyle warnings | W | Style warnings |
| pyflakes | F | Logical errors |
| isort | I | Import sorting |
| pyupgrade | UP | Python version upgrades |
| flake8-bugbear | B | Common bug patterns |
| flake8-simplify | SIM | Code simplification |
| flake8-annotations | ANN | Type annotation enforcement |
| flake8-bandit | S | Security issues |
| flake8-unused-arguments | ARG | Unused arguments |

Annotations (ANN), security (S), and unused arguments (ARG) rules are **relaxed in tests** via per-file ignores.

Target: Python 3.11, line length 100.

### Mypy Configuration

Strict mode is enabled:

```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_unused_ignores = true
warn_return_any = true
disallow_untyped_defs = true
```

External libraries `onnxruntime`, `tokenizers`, and `mcp` have `ignore_missing_imports = true`.

## Code Conventions

### Response Envelope

Every tool must return a dict via `success_envelope()` or raise `ToolError` (caught by `@tool_handler`). Never return raw dicts without the envelope wrapper.

```python
from ..contracts.envelope import tool_handler
from ..contracts.errors import ErrorCode, ToolError

@tool_handler(source="sqlite", confidence="exact")
async def my_tool(conn, *, param: str, idempotency_key: str | None = None) -> dict:
    # Check idempotency
    cached = check_idempotency(conn, idempotency_key)
    if cached is not None:
        return cached

    # Validate
    if not param:
        raise ToolError(
            code=ErrorCode.VALIDATION_MISSING_FIELD,
            message="'param' is required",
            details={"field": "param"},
        )

    # Do work
    result = {"done": True}

    # Store idempotency
    store_idempotency(conn, idempotency_key, result)
    return result
```

### Error Handling

- Use the appropriate `ErrorCode` from the taxonomy
- Use convenience constructors: `validation_error()`, `not_found_error()`, `conflict_error()`, etc.
- Never catch and swallow exceptions silently in tool code — let `@tool_handler` catch unexpected errors as `INTERNAL_ERROR`

### Idempotency

All mutating tools should:

1. Accept `idempotency_key: str | None = None` as a keyword argument
2. Check for cached results at the top of the function
3. Store results before returning

### Security

- Always call `redact()` on user-supplied text before persisting to SQLite
- Destructive operations require `require_confirmation(confirm, "operation_name")`

### Naming

- Tool functions: `snake_case`, matching the MCP tool name exactly (e.g., `patterns_search`)
- Tool files: one file per tool category (e.g., `tools/patterns.py`)
- Test files: `test_<module>.py` (e.g., `tests/test_patterns.py`)

### Async

All tool functions are `async def` even if they don't await anything. This is required by the `@tool_handler` decorator and the MCP dispatch system.

## Adding a New Tool

1. **Choose the tool category** — add to an existing file in `tools/` or create a new one.

2. **Write the tool function:**

```python
@tool_handler(source="sqlite", confidence="exact")
async def my_new_tool(
    conn: sqlite3.Connection,
    *,
    required_param: str,
    optional_param: int = 10,
    idempotency_key: str | None = None,
) -> dict:
    cached = check_idempotency(conn, idempotency_key)
    if cached is not None:
        return cached

    # ... implementation ...

    result = {"key": "value"}
    store_idempotency(conn, idempotency_key, result)
    return result
```

3. **Register in `server.py`:**

   a. Add a `Tool()` definition to `TOOL_DEFINITIONS` with the JSON schema:

   ```python
   Tool(
       name="my_new_tool",
       description="What this tool does.",
       inputSchema={
           "type": "object",
           "properties": {
               "required_param": {"type": "string", "description": "..."},
               "optional_param": {"type": "integer", "default": 10},
               "idempotency_key": {"type": "string"},
           },
           "required": ["required_param"],
       },
   ),
   ```

   b. Add a `case` to the `_dispatch_tool()` match statement:

   ```python
   case "my_new_tool":
       return await my_module.my_new_tool(conn, **arguments)
   ```

4. **Write tests** in `tests/test_<category>.py`. Use the shared fixtures from `conftest.py`.

5. **Run the quality checks:**

```bash
python -m pytest tests/ -v
ruff check src/ tests/
ruff format src/ tests/
```

6. **Document the tool** in `docs/docs/API-REFERENCE.md` following the existing format.

## Project Structure

```
ensemble/
├── AGENTS.md              # Agent instructions for AI assistants
├── Dockerfile             # Container build
├── README.md              # Project overview
├── pyproject.toml         # Package config, deps, tool settings
├── docs/docs/
│   ├── DESIGN-SPEC.md         # Executive design spec
│   ├── DESIGN-SPEC-PHASE-01.md # Phase 1 implementation spec
│   ├── SETUP.md               # Installation and setup guide
│   ├── ARCHITECTURE.md        # Technical architecture
│   ├── API-REFERENCE.md       # MCP tool API reference
│   └── CONTRIBUTING.md        # This file
├── src/ensemble_mcp/     # Source code
└── tests/                # Test suite
```

## Common Development Tasks

### Reset the database

Delete the SQLite database to start fresh:

```bash
rm -f ~/.cache/ensemble-mcp/data.db*
```

Or use the `reset` tool with `confirm=true` via an MCP client.

### Run a quick integration test

```bash
# Start the server and send a health check via the MCP protocol
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | ensemble-mcp
```

### Check what the server exposes

All 23 tools are defined in `src/ensemble_mcp/server.py` in the `TOOL_DEFINITIONS` list. The tool names, descriptions, and JSON schemas are all there.

## Docker (CI / Isolation Only)

Docker is **not required** for end users or development. It exists as an optional convenience for CI pipelines or running the server in an isolated container.

```bash
# Build the image
docker build -t ensemble-mcp .

# Run (mount the cache directory to persist data across runs)
docker run --rm -v ~/.cache/ensemble-mcp:/root/.cache/ensemble-mcp ensemble-mcp
```

End users should install with `pip install -e .` and configure their MCP client to launch `ensemble-mcp` directly. See the [Setup Guide](SETUP.md) for details.

## Known Limitations

- **Windows**: `state/locks.py` uses `fcntl` (Unix-only). Advisory locking will not work on Windows.
- **No ANN index**: Vector search is brute-force. Sufficient for <10K patterns but won't scale beyond that.
- **Single-process**: The SQLite WAL mode handles concurrent reads, but the server is designed for single-process use.
- **Phase 3/4 stubs**: Parsers (`parsers/`) and installer (`installer/`) are placeholder files for future phases.
