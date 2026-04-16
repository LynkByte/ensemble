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
| pytest-asyncio | >= 1.3.0 | Async test support |
| pytest-aiohttp | >= 1.0 | aiohttp test support |
| pytest-cov | >= 7.1.0 | Coverage reporting |
| ruff | >= 0.4 | Linting and formatting |
| mypy | >= 1.20.1 | Static type checking |
| build | >= 1.0 | Package building |

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

The project has test files covering all implemented features:

| Test File | Coverage |
|---|---|
| `test_contracts.py` | Envelope, ToolError, tool_handler decorator |
| `test_lifecycle.py` | Session/step state machine transitions |
| `test_idempotency.py` | Key storage, expiry, replay |
| `test_redaction.py` | All 9 secret patterns + edge cases |
| `test_trust.py` | Validators, confirmation enforcement |
| `test_similarity.py` | Cosine similarity, search, pairwise matrix |
| `test_embeddings.py` | Model loading, embed, normalize |
| `test_patterns.py` | Store, search, prune tools |
| `test_drift.py` | Drift check, verdicts, flags |
| `test_drift_history.py` | Drift history persistence and querying |
| `test_routing.py` | All agent/classification combinations |
| `test_session.py` | Save, load, search, optimistic versioning |
| `test_indexer.py` | Index, query, dependencies, language parsers |
| `test_project_snapshot.py` | Snapshot generation, caching, invalidation |
| `test_skills.py` | Discover, suggest, generate, clustering |
| `test_config.py` | Settings loading, TOML, env overrides |
| `test_schema.py` | Schema creation, migrations |
| `test_installer.py` | Tool detection, registration, config read/write, CLI |
| `test_mcp_tracking.py` | MCP call recording |
| `test_banner.py` | Server startup banner |
| `test_download_progress.py` | Model download with progress bar |
| `test_compress.py` | Context compression tool |
| `test_compress_engine.py` | Compression engine pipeline |
| `test_context_prepare.py` | Prompt section ordering and cache optimization |
| `test_dashboard_api.py` | Dashboard JSON API endpoints |
| `test___main__.py` | CLI entry point and subcommand dispatch |

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

External libraries `onnxruntime`, `tokenizers`, `mcp`, `rich`, and `aiohttp` have `ignore_missing_imports = true`.

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

6. **Document the tool** in `docs/API-REFERENCE.md` following the existing format.

## Project Structure

```
ensemble/
├── AGENTS.md              # Agent instructions for AI assistants
├── Dockerfile             # Container build
├── README.md              # Project overview
├── pyproject.toml         # Package config, deps, tool settings
├── docs/
│   ├── ARCHITECTURE.md        # Technical architecture
│   ├── API-REFERENCE.md       # MCP tool API reference
│   ├── BUSINESS-CASE.md       # Business case and value proposition
│   ├── CONTRIBUTING.md        # This file
│   ├── DASHBOARD-DESIGN.md    # Dashboard design system
│   ├── DESIGN-SPEC.md         # Executive design spec
│   ├── DESIGN-SPEC-PHASE-01.md # MCP server design spec
│   ├── EXAMPLE-SCENARIO.md    # End-to-end usage walkthrough
│   ├── FUTURE-PLANS.md        # Future roadmap
│   ├── RELEASING.md           # Release process guide
│   ├── SETUP.md               # Installation and setup guide
│   └── UNINSTALL.md           # Uninstallation guide
├── evals/                # Eval framework and benchmarks
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

All 19 tools are defined in `src/ensemble_mcp/server.py` in the `TOOL_DEFINITIONS` list. The tool names, descriptions, and JSON schemas are all there.

## Docker (CI / Isolation Only)

Docker is **not required** for end users or development. It exists as an optional convenience for CI pipelines or running the server in an isolated container.

```bash
# Build the image
docker build -t ensemble-mcp .

# Run (mount the cache directory to persist data across runs)
docker run --rm -v ~/.cache/ensemble-mcp:/home/app/.cache/ensemble-mcp ensemble-mcp
```

End users should install with `pip install -e .` and configure their MCP client to launch `ensemble-mcp` directly. See the [Setup Guide](SETUP.md) for details.

## CI/CD

The project uses GitHub Actions for continuous integration, security scanning, and automated publishing. Workflows live in `.github/workflows/`.

### Workflows

| Workflow | File | Trigger | What it does |
|---|---|---|---|
| CI | `ci.yml` | PR + push to `main` | Runs tests across Python 3.11/3.12/3.13 with coverage reporting (fail_under=80%) |
| Lint | `lint.yml` | PR + push to `main` | `ruff check`, `ruff format --check`, `mypy src/` (3 parallel jobs) |
| Security | `security.yml` | PR + push to `main` + weekly | CodeQL SAST analysis + `pip-audit` dependency vulnerability scanning |
| Release | `release.yml` | Manual (workflow_dispatch) | Validates, builds sdist+wheel, publishes to PyPI via OIDC, commits version, creates git tag + GitHub Release |
| Docker | `docker.yml` | GitHub release published | Multi-arch Docker build, pushed to `ghcr.io/lynkbyte/ensemble-mcp` |

Dependabot is configured (`.github/dependabot.yml`) to auto-create PRs for pip and GitHub Actions dependency updates weekly.

### Required Setup

Before the workflows function fully, the following one-time setup steps are required:

#### 1. PyPI Trusted Publishing (package releases)

The publish workflow uses [OIDC trusted publishing](https://docs.pypi.org/trusted-publishers/) — no API tokens are stored in GitHub.

1. Go to [pypi.org/manage/account/publishing](https://pypi.org/manage/account/publishing/)
2. Add a new pending publisher (or configure on an existing project):
   - **PyPI project name**: `ensemble-mcp`
   - **Owner**: `LynkByte`
   - **Repository**: `ensemble`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi`
3. In your GitHub repo, go to **Settings > Environments**
4. Create an environment named `pypi`
5. Optionally add required reviewers for deployment protection (recommended for production releases)

#### 2. GHCR (Docker image publishing)

Docker images are pushed to GitHub Container Registry (`ghcr.io`) using the built-in `GITHUB_TOKEN`. No additional secrets are needed, but ensure:

1. In your GitHub repo, go to **Settings > Actions > General**
2. Under "Workflow permissions", ensure **Read and write permissions** is selected
3. The first push will create the package at `ghcr.io/lynkbyte/ensemble-mcp` — you can then configure its visibility (public/private) under **Packages** in the organization/user settings

### Running Checks Locally

All CI checks can be run locally before pushing:

```bash
# Tests with coverage
pytest tests/ --cov=ensemble_mcp --cov-report=term-missing -m "not slow"

# Lint
ruff check src/ tests/

# Format check
ruff format --check src/ tests/

# Type check
mypy src/
```

## Known Limitations

- **Windows**: `state/locks.py` uses `fcntl` (Unix-only). Advisory locking will not work on Windows.
- **No ANN index**: Vector search is brute-force. Sufficient for <10K patterns but won't scale beyond that.
- **Single-process**: The SQLite WAL mode handles concurrent reads, but the server is designed for single-process use.
