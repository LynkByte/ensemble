# Architecture

Technical architecture of **ensemble-mcp** — the local MCP server powering the Ensemble 7-agent AI orchestration system.

## Design Principles

1. **Zero-LLM-Call Principle**: The server makes no LLM or external API calls. All intelligence is local: ONNX Runtime embeddings (~5ms), numpy cosine similarity, tiktoken counting, SQLite storage.

2. **Single-Binary Simplicity**: One Python package, one SQLite database, one ONNX model. No Redis, no Postgres, no message queues.

3. **Deterministic Responses**: Same inputs always produce the same outputs. Embedding-based similarity is the only source of non-trivial computation.

4. **Structured Error Contracts**: Every tool returns the same envelope shape. Every error has a code, retry guidance, and structured details.

## System Overview

```
MCP Client (OpenCode / Claude Code / etc.)
    |
    | stdio (JSON-RPC)
    v
ensemble-mcp server  (server.py)
    |
    +-- Tool Dispatch (match on tool name)
    |       |
    |       +-- patterns.py    (3 tools)
    |       +-- metrics.py     (6 tools)
    |       +-- drift.py       (1 tool)
    |       +-- routing.py     (1 tool)
    |       +-- skills.py      (3 tools)
    |       +-- session.py     (2 tools)
    |       +-- indexer.py     (3 tools)
    |       +-- health / reset (2 tools, inline)
    |
    +-- Shared Infrastructure
            |
            +-- memory/         (ONNX embeddings + SQLite vector store)
            +-- contracts/      (response envelope + error taxonomy)
            +-- state/          (lifecycle FSM + idempotency + locks)
            +-- security/       (redaction + trust boundaries)
            +-- config/         (layered settings + pricing tables)
```

## Package Layout

```
src/ensemble_mcp/
├── __init__.py           # Package version
├── __main__.py           # Entry point: python -m ensemble_mcp
├── server.py             # MCP server, tool definitions, dispatch
│
├── config/
│   ├── defaults.py       # All constants and default values
│   ├── pricing.py        # Model pricing table (7 models), calculate_cost()
│   └── settings.py       # Layered config loader (TOML + env vars)
│
├── contracts/
│   ├── errors.py         # ErrorCode enum (23 codes), ToolError, constructors
│   └── envelope.py       # ToolResponse, success/error envelope, @tool_handler
│
├── memory/
│   ├── embeddings.py     # ONNX MiniLM-L6-v2, lazy load, embed()
│   ├── similarity.py     # cosine_similarity(), search_similar(), pairwise_matrix()
│   └── store.py          # VectorStore: 12-table schema, pattern CRUD
│
├── state/
│   ├── lifecycle.py      # SessionState/StepState enums, transition functions
│   ├── idempotency.py    # SQLite-backed idempotency key store (24h TTL)
│   └── locks.py          # WAL mode, get_connection(), advisory_lock()
│
├── security/
│   ├── redaction.py      # 9 regex patterns, redact(), contains_secrets()
│   └── trust.py          # SourceClass, validators, require_confirmation()
│
├── tools/
│   ├── patterns.py       # patterns_search, patterns_store, patterns_prune
│   ├── metrics.py        # 6 metrics tools (start/record/end/report/trend/compare)
│   ├── drift.py          # drift_check
│   ├── routing.py        # model_recommend (7x4 agent-classification matrix)
│   ├── skills.py         # skills_discover, skills_suggest, skills_generate
│   ├── session.py        # session_save, session_load (optimistic versioning)
│   └── indexer.py        # project_index, project_query, project_dependencies
│
├── parsers/              # Phase 3 — session file parsers
│   ├── __init__.py       # ParsedStep/ParsedSession types, detect_ai_tool(), dispatcher
│   ├── opencode.py       # OpenCode SQLite parser (~/.local/share/opencode/opencode.db)
│   └── claude_code.py    # Claude Code JSONL parser (~/.claude/projects/) + subagents
│
└── installer/            # Phase 4 (not yet implemented)
    └── setup.py          # Auto-detect AI tools, register MCP server
```

## Request Lifecycle

Every MCP tool call follows this path:

```
1. MCP Client sends JSON-RPC call_tool(name, arguments)
        |
2. server.py call_tool() handler
        |
3. _dispatch_tool() matches tool name
        |
4. Tool function invoked (e.g. patterns_search)
        |
   4a. @tool_handler decorator starts timer
   4b. Idempotency check (return cached result if key exists)
   4c. Core logic executes
   4d. Idempotency store (save result for future replays)
   4e. @tool_handler wraps result in envelope
        |
5. Envelope returned as TextContent JSON
        |
6. MCP Client receives structured response
```

### Response Envelope

Every tool returns this exact shape:

```json
{
  "ok": true,
  "data": { "...tool-specific payload..." },
  "error": null,
  "meta": {
    "duration_ms": 12,
    "source": "sqlite",
    "confidence": "exact"
  }
}
```

On error:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "NOT_FOUND_SESSION",
    "message": "No session with id sess_abc123",
    "retryable": false,
    "details": { "session_id": "sess_abc123" }
  },
  "meta": {
    "duration_ms": 2,
    "source": "sqlite",
    "confidence": "exact"
  }
}
```

### The `@tool_handler` Decorator

Defined in `contracts/envelope.py`, this decorator:

1. Starts a monotonic timer
2. Calls the wrapped async function
3. On success: wraps the returned dict in `success_envelope()`
4. On `ToolError`: wraps in `error_envelope()` with the structured error
5. On unexpected `Exception`: wraps in `error_envelope()` with `INTERNAL_ERROR`
6. Records `duration_ms` in all cases

Tool functions can override envelope metadata by returning special keys `__confidence__` and `__source__` in their result dict (these are stripped before the envelope is built).

## Error Taxonomy

All errors use the `ErrorCode` enum from `contracts/errors.py`. Each code belongs to a category that determines retry behavior:

| Category | Retry Guidance | Codes |
|---|---|---|
| `VALIDATION_*` | Never retry | `MISSING_FIELD`, `INVALID_VALUE`, `INVALID_TYPE`, `CONSTRAINT` |
| `NOT_FOUND_*` | Never retry | `SESSION`, `PATTERN`, `STEP`, `SKILL_SUGGESTION`, `FILE`, `PROJECT`, `CHECKPOINT` |
| `CONFLICT_*` | Retry after refresh | `VERSION_MISMATCH`, `INVALID_STATE_TRANSITION`, `DUPLICATE`, `ALREADY_RESOLVED` |
| `TIMEOUT_*` | Retry with backoff | `EMBEDDING`, `INDEX`, `QUERY` |
| `IO_*` | Retry with backoff | `DATABASE`, `FILESYSTEM`, `MODEL_DOWNLOAD` |
| `INTERNAL_*` | Only if marked | `ERROR`, `SCHEMA_MIGRATION` |

The `is_retryable()` function returns the default retry guidance for any error code.

## Embedding Pipeline

The embedding system lives in `memory/`:

```
Text Input
    |
    v
EmbeddingModel.embed(text)          [memory/embeddings.py]
    |
    +-- Tokenize via HuggingFace tokenizer (tokenizer.json)
    +-- Pad/truncate to 128 tokens
    +-- Run ONNX Runtime inference (model.onnx)
    +-- Mean pooling over token embeddings
    +-- L2 normalize to unit vector
    |
    v
384-dimensional float32 numpy array
```

Key characteristics:

- **Model**: `all-MiniLM-L6-v2` via ONNX Runtime (~22 MB)
- **Dimensions**: 384
- **Inference time**: ~5ms per text
- **Lazy loading**: Model is loaded on first `embed()` call, not at import time
- **Storage**: Embeddings stored as `BLOB` in SQLite (`numpy.tobytes()`)
- **Retrieval**: `np.frombuffer(blob, dtype=np.float32)` to reconstruct

### Similarity Search

`memory/similarity.py` provides:

- `cosine_similarity(a, b)` — dot product of two unit vectors
- `search_similar(query, candidates, top_k, min_score)` — brute-force top-K
- `pairwise_matrix(vectors)` — NxN similarity matrix for clustering

Brute-force search is sufficient for the expected scale (<10K vectors). No ANN index is needed.

## SQLite Schema

All state lives in a single SQLite database (`~/.cache/ensemble-mcp/data.db`) with WAL mode enabled. The schema has 12 tables plus a version tracker:

### Core Tables

| Table | Purpose | Key Columns |
|---|---|---|
| `schema_version` | Forward-only migration tracking | `version`, `applied_at` |
| `patterns` | Stored patterns with embeddings | `name`, `context`, `approach`, `outcome`, `embedding` (BLOB), `match_count` |
| `sessions` | Pipeline session tracking | `id`, `task`, `classification`, `state`, `total_cost_usd` |
| `steps` | Per-agent step metrics | `session_id`, `agent`, `model`, `input_tokens`, `output_tokens`, `cost_usd` |
| `mcp_calls` | MCP call tracking | `tool_name`, `input_bytes`, `output_bytes`, `duration_ms` |

### Indexer Tables

| Table | Purpose | Key Columns |
|---|---|---|
| `project_files` | File-level codebase index | `project_path`, `file_path`, `language`, `role`, `size_bytes` |
| `file_exports` | Exported symbols per file | `file_id`, `name`, `kind`, `line_number` |
| `file_imports` | Import statements per file | `file_id`, `import_path`, `raw_import` |

### Skills Tables

| Table | Purpose | Key Columns |
|---|---|---|
| `skill_suggestions` | AI-generated skill proposals | `proposed_name`, `proposed_content`, `confidence`, `status` |
| `skill_suggestion_patterns` | Junction: suggestion <-> patterns | `suggestion_id`, `pattern_id` |
| `skill_usage_tracking` | Skill file usage metrics | `skill_path`, `project`, `match_count` |

### Infrastructure Tables

| Table | Purpose | Key Columns |
|---|---|---|
| `session_checkpoints` | Optimistic-versioned state snapshots | `session_id`, `state_json`, `version` |
| `idempotency_keys` | Dedup store for mutating calls | `key`, `result_json`, `expires_at` |

### WAL Mode and Concurrency

SQLite is configured with:

```sql
PRAGMA journal_mode=WAL;     -- Write-Ahead Logging for concurrent reads
PRAGMA busy_timeout=5000;    -- 5s retry on lock contention
PRAGMA foreign_keys=ON;      -- Enforce FK constraints
```

## State Machines

### Session Lifecycle

```
pending ──> running ──> completed
                   ├──> failed
                   └──> killed
```

- `pending -> running`: Automatic on `metrics_start_session`
- `running -> completed|failed|killed`: Via `metrics_end_session`
- Terminal states have no outgoing transitions

### Step Lifecycle

```
pending ──> running ──> completed
       |           ├──> failed
       |           └──> skipped
       └──> skipped
```

Invalid transitions raise `CONFLICT_INVALID_STATE_TRANSITION` (retryable after refresh).

## Idempotency

All mutating tool calls accept an optional `idempotency_key` parameter. The system:

1. **Before execution**: Checks `idempotency_keys` table for the key
2. **Cache hit**: Returns the previously stored result immediately
3. **Cache miss**: Executes the tool, stores the result under the key
4. **TTL**: Keys expire after 24 hours (configurable via `idempotency_key_ttl_hours`)
5. **Cleanup**: Expired keys are lazily deleted on each lookup

This prevents duplicate side effects when MCP clients retry failed network calls.

## Security

### Secret Redaction

`security/redaction.py` scans all text before persistence through 9 regex patterns:

| Pattern | Example Match |
|---|---|
| AWS Access Key | `AKIA1234567890ABCDEF` |
| AWS Secret Key | `aws_secret_access_key=...` |
| Generic API Key | `api_key=sk-...` |
| Bearer Token | `Bearer eyJ...` |
| Private Key | `-----BEGIN RSA PRIVATE KEY-----` |
| Password | `password=hunter2` |
| GitHub Token | `ghp_xxxxxxxxxxxx` |
| Hex Token | `token=0a1b2c3d...` |
| Env Secret | `SECRET_KEY=...` |

Matched content is replaced with `[REDACTED]`. Redaction is applied to pattern fields (`name`, `context`, `approach`, `outcome`) before SQLite insertion.

### Trust Boundaries

`security/trust.py` classifies data sources:

- **`local_state`** — SQLite/session state generated by ensemble-mcp (trusted)
- **`client_input`** — MCP tool arguments from AI clients (validated, redacted)
- **`filesystem_scan`** — project files, skill files (read-only, errors non-fatal)

Destructive operations (`reset`) require explicit `confirm=true`.

## Model Routing

`tools/routing.py` maps (agent, classification) pairs to model tiers using a 7x4 rule matrix:

| Agent | Trivial | Simple | Standard | Complex |
|---|---|---|---|---|
| signal | cheapest | cheapest | cheapest | cheapest |
| proof | cheapest | cheapest | mid | mid |
| lens | cheapest | cheapest | mid | mid |
| craft | mid | mid | best | best |
| scope | mid | mid | best | best |
| ensemble | mid | mid | best | best |
| trace | mid | best | best | best |

Tiers (`best`, `mid`, `cheapest`) are abstract — the consuming agent maps them to specific models. Unknown agent/classification pairs default to `mid`.

## Pricing Table

`config/pricing.py` stores per-model costs in USD per 1M tokens:

| Model | Input | Cached Input | Output |
|---|---|---|---|
| claude-opus-4 | $15.00 | $1.50 | $75.00 |
| claude-sonnet-4 | $3.00 | $0.30 | $15.00 |
| claude-haiku-3.5 | $0.80 | $0.08 | $4.00 |
| gpt-4o | $2.50 | $1.25 | $10.00 |
| gpt-4o-mini | $0.15 | $0.075 | $0.60 |
| gpt-5-mini | $0.20 | $0.10 | $0.80 |
| o1 | $15.00 | $7.50 | $60.00 |

Pricing carries a `PRICING_VERSION` (`2026-03`) for reproducible historical reports. Unknown models fall back to `claude-sonnet-4` pricing with an `unknown_model` flag.

## Codebase Indexer

`tools/indexer.py` builds a file-level codebase index:

- **Incremental**: Uses file mtime to skip unchanged files
- **Language detection**: 30+ extensions mapped to languages
- **Role detection**: 12 heuristic patterns (test, migration, config, model, controller, service, etc.)
- **Export extraction**: Language-aware parsers for Python, TypeScript/JavaScript, PHP, Go, Rust, Ruby
- **Import extraction**: Same 6 languages
- **Filtering**: Respects `.gitignore` patterns plus a built-in ignore list (node_modules, vendor, .git, etc.)

## Skill Intelligence

`tools/skills.py` provides three capabilities:

1. **Discovery**: Scans 5 known skill directories (`.ai/skills/`, `.claude/skills/`, `.cursor/rules/`, `.github/copilot-instructions/`, `.opencode/skills/`) for existing skill files
2. **Suggestion**: Clusters stored patterns by embedding similarity (threshold >= 0.75) using single-linkage agglomerative clustering. Clusters with >= 3 members become skill suggestions
3. **Generation**: Accepts/dismisses/defers suggestions. On accept, writes a Markdown skill file (zero-LLM generation from pattern content)

## Configuration Layering

`config/settings.py` loads settings in order:

```
Package defaults (Settings dataclass)
        |
        v
~/.config/ensemble-mcp/config.toml   (global user prefs)
        |
        v
.ensemble-mcp.toml                   (project-specific)
        |
        v
ENSEMBLE_MCP_* environment vars       (runtime overrides)
```

Merge rules:
- **Scalars**: Higher layers replace lower
- **Maps**: Shallow merge by key
- **Lists**: Higher layers replace entirely

Every setting tracks which layer it came from via `source_map` for debugging.

## Future Phases

| Phase | Scope | Status |
|---|---|---|
| 1.0 | Contract Foundation (config, errors, envelope, state, security) | Complete |
| 1 | MCP Core (21 tools, server, tests) | Complete |
| 2 | Performance optimization, benchmarks | Not started |
| 3 | Session file parsers (OpenCode, Claude Code) | Complete |
| 4 | Auto-installer for AI tools | Not started |
