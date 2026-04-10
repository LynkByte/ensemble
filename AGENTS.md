# AGENTS.md

## Overview

Python MCP server (`ensemble-mcp`) providing vector memory, drift detection, model routing, skills discovery, session management, codebase indexing, and a local web dashboard. **Fully implemented** — 15 MCP tools across 10 subpackages, CLI with serve/install/uninstall/add-agents/add-skills/web commands.

## Commands

```bash
pip install -e .                  # editable install
ensemble-mcp                      # run server (or: python -m ensemble_mcp)
ensemble-mcp install              # auto-detect AI tools and register MCP
ensemble-mcp uninstall            # remove MCP registration from AI tool configs
ensemble-mcp add-agents           # copy agent files (no MCP registration)
ensemble-mcp add-skills           # copy skill files (no MCP registration)
ensemble-mcp web                  # launch web dashboard at localhost:8787
ensemble-mcp web --port 9000      # custom port
ensemble-mcp web --no-open        # start without auto-opening browser
python -m pytest tests/           # run tests
ruff check src/ tests/            # lint
ruff format src/ tests/           # format
mypy src/                         # typecheck
python -m build                   # build sdist + wheel
docker build -t ensemble-mcp .    # build container
```

> ruff and mypy are fully configured in `pyproject.toml` (strict mode, Python 3.11 target).

## Architecture

`src` layout — package lives at `src/ensemble_mcp/`, mapped via `[tool.hatch.build.targets.wheel]`.

Entry point: `__main__.py` → `server.serve()` (stdio MCP server).

| Subpackage | Role |
|------------|------|
| `config/` | Layered settings, defaults |
| `contracts/` | Response envelope and error taxonomy |
| `memory/` | ONNX embeddings, SQLite vector store, cosine similarity |
| `security/` | Secret redaction, trust boundary enforcement |
| `state/` | Session/step lifecycle, idempotency, locks |
| `tools/` | 15 MCP tool implementations + call-recording utility (7 categories below) |
| `installer/` | Auto-detect AI tools, register MCP server |
| `dashboard/` | Web dashboard: aiohttp server, JSON API, Alpine.js SPA |
| `cli/` | Startup banner |
| `data/` | Bundled agent and skill files |

### Tool categories (15 tools)

- **Patterns**: `patterns_search`, `patterns_store`, `patterns_prune`
- **Drift**: `drift_check`
- **Routing**: `model_recommend`
- **Skills**: `skills_discover`, `skills_suggest`, `skills_generate`
- **Session**: `session_save`, `session_load`
- **Indexer**: `project_index`, `project_query`, `project_dependencies`
- **Utility**: `health`, `reset`

### Local-only — zero LLM/API calls

All intelligence is local: ONNX Runtime embeddings (~5ms), numpy cosine similarity, SQLite storage.

| Path | Contents |
|------|----------|
| `~/.cache/ensemble-mcp/data.db` | SQLite database (WAL mode) |
| `~/.cache/ensemble-mcp/models/` | ONNX MiniLM-L6-v2 model (~22MB, 384 dimensions) |

## Conventions

- **Response envelope**: all tools return `{ok, data, error, meta: {duration_ms, source, confidence}}`
- **Error taxonomy** (`contracts/errors.py`): `VALIDATION_*` (never retry), `NOT_FOUND_*` (never retry), `CONFLICT_*` (retry after refresh), `TIMEOUT_*` (retry with backoff), `IO_*` (retry with backoff), `INTERNAL_*` (retryable only if marked)
- **Config layering order**: package defaults → `~/.config/ensemble-mcp/config.toml` → `.ensemble-mcp.toml` → CLI/env
- **Idempotency keys**: mutating tool calls accept `idempotency_key`; replayed keys return the previously committed result
- **Lifecycle state machines**: session `pending → running → completed | failed | killed`; step `pending → running → completed | failed | skipped`. Invalid transitions are rejected with `CONFLICT_INVALID_STATE_TRANSITION`
- **Embedding model**: MiniLM-L6-v2 via ONNX Runtime, 384-dim vectors, brute-force cosine similarity (sufficient for <10K vectors)
