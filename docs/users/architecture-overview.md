# Architecture Overview

Technical architecture of the `ensemble-mcp` server — a **harness infrastructure layer** for AI agent pipelines.

## What is an Agent Harness?

**Agent = Model + Harness.** A harness is every piece of code, configuration, and execution logic that wraps a model to make it useful. Without a harness, a model can only take in text and output text — it can't maintain state, execute code, or learn from past work.

ensemble-mcp is specifically the **intelligence infrastructure layer** of the harness — it provides memory, skills, drift detection, model routing, context management, and session persistence. The execution layer (filesystem, bash, sandbox) is provided by the host agent tool (Claude Code, Cursor, Codex, etc.).

> *For a deeper dive on harness concepts, see [The Anatomy of an Agent Harness](https://www.langchain.com/blog/the-anatomy-of-an-agent-harness) by LangChain.*

## Harness Component Mapping

The following diagram shows how ensemble-mcp's subpackages map to harness primitives:

```mermaid
flowchart TB
    subgraph Harness["Agent Harness Primitives"]
        direction TB
        MEM["Memory & Search\n(Continual Learning)"]
        CTX["Context Management\n(Context Rot Prevention)"]
        SKL["Skills\n(Progressive Disclosure)"]
        DFT["Drift Detection\n(Self-Verification)"]
        RTG["Model Routing\n(Orchestration)"]
        SES["Session Persistence\n(Long Horizon Execution)"]
        IDX["Codebase Awareness\n(Workspace Knowledge)"]
    end

    subgraph Impl["ensemble-mcp Implementation"]
        direction TB
        P["memory/\nONNX embeddings\n+ vector store"]
        C["compress/\nRule-based compression\n+ prompt caching"]
        S["tools/skills.py\nDiscover, suggest,\ngenerate skills"]
        D["tools/drift.py\nCosine similarity\nscope checking"]
        R["tools/routing.py\n7x4 agent-tier\nmatrix"]
        SS["tools/session.py\nCheckpoint save/load\noptimistic versioning"]
        I["tools/indexer.py\nFile index, exports,\nimports, snapshots"]
    end

    MEM --> P
    CTX --> C
    SKL --> S
    DFT --> D
    RTG --> R
    SES --> SS
    IDX --> I

    style Harness fill:#1e40af,color:#fff
    style Impl fill:#059669,color:#fff
```

## High-Level Design

`ensemble-mcp` is a Python MCP server that runs locally as a stdio process. It provides 19 tools across 8 categories, all backed by local ONNX embeddings and SQLite storage.

```mermaid
flowchart TB
    subgraph External["External"]
        AI[AI Coding Tool\nOpenCode / Cursor / Copilot / etc.]
        Browser[Web Browser]
    end

    subgraph Server["ensemble-mcp Process"]
        MCP[MCP Protocol Handler\nserver.py]
        Dispatch[Tool Dispatcher\n19 tools]
        CLI[CLI Entry Point\n__main__.py]
        Banner[Startup Banner\ncli/banner.py]
    end

    subgraph Dashboard["Dashboard Process"]
        HTTP[aiohttp Server\ndashboard/server.py]
        API[JSON API\ndashboard/api.py]
        SPA[Alpine.js SPA\ndashboard/static/]
    end

    subgraph Core["Core Engine"]
        Embed[Embedding Model\nmemory/embeddings.py]
        Store[Vector Store\nmemory/store.py]
        Sim[Cosine Similarity\nmemory/similarity.py]
        Schema[DB Schema\nmemory/schema.py]
    end

    subgraph Tools["Tool Implementations"]
        Patterns[patterns.py]
        Drift[drift.py]
        Routing[routing.py]
        Skills[skills.py]
        Session[session.py]
        Indexer[indexer.py]
        Compress[compress.py]
        Track[mcp_tracking.py]
    end

    subgraph Support["Support Layer"]
        Config[Config\nconfig/]
        Contracts[Contracts\ncontracts/]
        Security[Security\nsecurity/]
        State[State\nstate/]
        CompEngine[Compression Engine\ncompress/]
        Installer[Installer\ninstaller/]
    end

    subgraph Storage["Local Storage"]
        SQLite[(SQLite DB\nWAL mode)]
        ONNX[ONNX Model\nMiniLM-L6-v2]
    end

    AI <-->|stdio| MCP
    MCP --> Dispatch
    Dispatch --> Tools
    CLI --> MCP
    CLI --> Banner
    CLI --> HTTP
    Browser <-->|HTTP| HTTP
    HTTP --> API
    API --> SPA

    Tools --> Core
    Tools --> Support
    Core --> Storage
    API --> SQLite

    style External fill:#94a3b8,color:#fff
    style Server fill:#2563eb,color:#fff
    style Dashboard fill:#0891b2,color:#fff
    style Core fill:#059669,color:#fff
    style Tools fill:#7c3aed,color:#fff
    style Support fill:#d97706,color:#fff
    style Storage fill:#dc2626,color:#fff
```

## Package Layout

The project uses a `src` layout with the package at `src/ensemble_mcp/`:

```
src/ensemble_mcp/
├── __init__.py
├── __main__.py          # CLI entry point (argparse, 6 subcommands)
├── server.py            # MCP server setup, tool registration, dispatch
│
├── config/              # Configuration management
│   ├── defaults.py      # Constants, thresholds, paths
│   └── settings.py      # Layered config loader (TOML + env vars)
│
├── contracts/           # Response envelope and error taxonomy
│   ├── envelope.py      # {ok, data, error, meta} wrapper + @tool_handler
│   └── errors.py        # ErrorCode enum, ToolError, retry guidance
│
├── memory/              # Embedding and vector storage
│   ├── embeddings.py    # ONNX Runtime model loading and inference
│   ├── similarity.py    # Cosine similarity, top-K search
│   ├── store.py         # VectorStore class (SQLite + embeddings)
│   └── schema.py        # DDL: CREATE TABLE statements
│
├── security/            # Input/output safety
│   ├── redaction.py     # Secret/PII redaction
│   └── trust.py         # Confirmation requirement enforcement
│
├── state/               # Session and lifecycle management
│   ├── idempotency.py   # Idempotency key check/store
│   ├── lifecycle.py     # SessionState/StepState enums, transitions
│   └── locks.py         # SQLite connection management (WAL, threading)
│
├── tools/               # MCP tool implementations (19 tools)
│   ├── patterns.py      # patterns_search, patterns_store, patterns_prune
│   ├── drift.py         # drift_check
│   ├── routing.py       # model_recommend
│   ├── skills.py        # skills_discover, skills_suggest, skills_generate
│   ├── session.py       # session_save, session_load, session_search
│   ├── indexer.py       # project_index, project_query, project_dependencies, project_snapshot
│   ├── compress.py      # context_compress, context_prepare
│   └── mcp_tracking.py  # Record MCP call history
│
├── compress/            # Context compression engine
│   ├── __init__.py      # Package init, re-exports compress + CompressResult
│   ├── engine.py        # Rule-based text compression pipeline
│   ├── preservers.py    # Regex patterns for preserving technical content
│   └── tokens.py        # Token counting via HuggingFace tokenizer
│
├── installer/           # Auto-installer for AI tools
│   ├── __init__.py      # ToolDefinition, InstallPlan, result types
│   ├── setup.py         # detect → plan → confirm → execute flow
│   ├── registry.py      # Config file read/write (JSON, TOML)
│   └── agents.py        # Agent/skill file discovery and copying
│
├── dashboard/           # Web dashboard
│   ├── __init__.py      # start_dashboard() export
│   ├── server.py        # aiohttp app creation, static file serving
│   ├── api.py           # 25+ JSON API endpoints
│   └── static/          # SPA frontend
│       ├── index.html
│       ├── app.js
│       └── style.css
│
├── cli/                 # Terminal UI
│   └── banner.py        # Startup banner (Rich)
│
└── data/                # Bundled files
    ├── agents/          # 7 agent markdown files
    └── skills/          # Workflow skill file
```

## Subpackage Responsibilities

Each subpackage implements one or more harness primitives:

### `memory/` — Memory & Search (Continual Learning)

**ONNX embeddings and vector storage.** The foundation of the harness's memory system. Loads the MiniLM-L6-v2 model via ONNX Runtime (~5ms per embedding, 384 dimensions). `VectorStore` manages the SQLite database with schema migrations. Cosine similarity is computed via numpy — brute-force is sufficient for <10K vectors. Enables agents to durably store knowledge from one session and inject it into future sessions.

### `compress/` — Context Rot Prevention (Compaction)

**Rule-based text compression engine.** Addresses context rot — the degradation of model performance as the context window fills up. Removes filler words, articles, hedging phrases, and pleasantries from prose sections while preserving all technical content (code blocks, URLs, file paths, headings, tables). Zero LLM calls. The `context_prepare` tool orders prompt sections for optimal LLM cache hit rates.

### `tools/` — Harness Tool Implementations (19 tools)

**19 MCP tool implementations mapping to harness primitives.** Each tool is an async function decorated with `@tool_handler`:

| Harness Primitive | Tools | File |
|---|---|---|
| Memory & Search | `patterns_search`, `patterns_store`, `patterns_prune` | `patterns.py` |
| Drift Detection | `drift_check` | `drift.py` |
| Model Routing | `model_recommend` | `routing.py` |
| Skills (Progressive Disclosure) | `skills_discover`, `skills_suggest`, `skills_generate` | `skills.py` |
| Session Persistence | `session_save`, `session_load`, `session_search` | `session.py` |
| Codebase Awareness | `project_index`, `project_query`, `project_dependencies`, `project_snapshot` | `indexer.py` |
| Context Management | `context_compress`, `context_prepare` | `compress.py` |

The `mcp_tracking.py` module records every MCP call for observability (tool name, arguments, result, duration).

### `config/` — Harness Configuration

**Layered settings resolution.** Loads defaults from `defaults.py`, merges global config (`~/.config/ensemble-mcp/config.toml`), project config (`.ensemble-mcp.toml`), and environment variables (`ENSEMBLE_MCP_*`). Scalar values override; maps merge shallowly; lists replace.

### `contracts/` — Response Standardization

**Response standardization and error taxonomy.** Every tool returns `{ok, data, error, meta}` via the `@tool_handler` decorator, which handles timing, error wrapping, and the envelope format. Error codes follow a prefix-based taxonomy (`VALIDATION_*`, `NOT_FOUND_*`, `CONFLICT_*`, `TIMEOUT_*`, `IO_*`, `INTERNAL_*`) with built-in retry guidance.

### `security/` — Trust Boundaries

**Input safety.** `redaction.py` strips secrets and PII before storage or embedding. `trust.py` enforces confirmation requirements for destructive operations (e.g., `reset` requires `confirm=true`).

#### Secret Redaction Patterns

All text fields are scanned through 9 regex patterns before persistence. Matched content is replaced with `[REDACTED]`:

| Pattern | Regex | Example Match |
|---|---|---|
| AWS Access Key | `AKIA[0-9A-Z]{16}` | `AKIA1234567890ABCDEF` |
| AWS Secret Key | `[0-9a-zA-Z/+=]{40}` | `aws_secret_access_key=...` |
| Generic API Key | key/api_key/apikey patterns | `api_key=sk-...` |
| Bearer Token | `Bearer [a-zA-Z0-9\-._~+/]+=*` | `Bearer eyJ...` |
| Private Key | BEGIN ... PRIVATE KEY blocks | `-----BEGIN RSA PRIVATE KEY-----` |
| Password | password/passwd/pwd patterns | `password=hunter2` |
| GitHub Token | `gh[ps]_[a-zA-Z0-9]{36}` | `ghp_xxxxxxxxxxxx` |
| Hex Token | 32+ character hex strings | `token=0a1b2c3d...` |
| Env Secret | KEY=value patterns in env-like formats | `SECRET_KEY=...` |

Redaction is applied to pattern fields (`name`, `context`, `approach`, `outcome`) before SQLite insertion.

#### Trust Boundaries

Data sources are classified into three trust zones:

| Trust Zone | Classification | Behavior |
|---|---|---|
| `local_state` | **Trusted** | Internal database and cached computations — generated by ensemble-mcp itself |
| `client_input` | **Validated and redacted** | All text from MCP tool parameters goes through validation and secret redaction before processing |
| `filesystem_scan` | **Read-only, errors non-fatal** | File indexing and skill scanning never write to user files. I/O errors are caught and skipped gracefully |

Destructive operations (`reset`) require explicit `confirm=true` to proceed.

### `state/` — Lifecycle & Idempotency

**Session lifecycle and idempotency.** Defines state machines for sessions (`pending → running → completed | failed | killed`) and steps (`pending → running → completed | failed | skipped`). Supports the long horizon execution harness primitive by enabling durable state across context windows. Idempotency keys prevent duplicate execution of mutating tools.

### `installer/` — Harness Setup

**Auto-detection and registration of AI tools.** Defines `ToolDefinition` for 6 supported tools (OpenCode, Claude Code, Copilot, Cursor, Windsurf, Devin CLI) with their config paths. Makes it easy to plug ensemble-mcp into any existing agent harness.

### `dashboard/` — Observability

**Local web dashboard.** An aiohttp server serving an Alpine.js SPA. Provides visibility into harness state — patterns, skills, drift history, sessions, and codebase index. The API layer (25+ endpoints) opens its own SQLite connections to avoid blocking the MCP server.

### `cli/` — Terminal UI

**Terminal UI.** Currently contains only the startup banner, which uses Rich to display server version, config paths, and database location on stderr.

### `data/` — Bundled Harness Files

**Bundled agent and skill files.** The 7-agent orchestration pipeline (`team-ensemble`, `team-scope`, `team-craft`, `team-forge`, `team-trace`, `team-lens`, `team-signal`) and the `ensemble-mcp-workflow` skill file. These are the system prompts and AGENTS.md files that constitute the orchestration layer of the harness.

## Data Flow

### Tool Call Flow

1. AI tool sends MCP request over stdin
2. `server.py` deserializes the request and routes to `_dispatch_tool()`
3. `_dispatch_tool()` matches the tool name and calls the handler
4. Handler function executes (embedding, DB queries, etc.)
5. `@tool_handler` wraps the result in `{ok, data, error, meta}`
6. `mcp_tracking.py` records the call in `mcp_calls` table
7. Response is serialized to JSON and written to stdout

### The `@tool_handler` Decorator

Every tool function is wrapped with the `@tool_handler` decorator (defined in `contracts/envelope.py`), which standardizes behavior across all 19 tools:

1. **Starts a monotonic timer** — begins measuring execution time
2. **Calls the tool function** — invokes the wrapped async function
3. **Wraps the result** — on success, packages the returned dict into the `{ok, data, error, meta}` response envelope
4. **Catches and classifies errors** — if the tool raises a `ToolError`, it wraps it in an error envelope with the structured error code and retry guidance. Unexpected exceptions become `INTERNAL_ERROR`
5. **Records duration** — `meta.duration_ms` is set in all cases (success or error)
6. **Supports metadata overrides** — tool functions can return special keys `__confidence__` and `__source__` in their result dict to customize the `meta.confidence` and `meta.source` fields. These keys are stripped before the envelope is built

### Embedding Pipeline

The embedding system processes text into searchable vectors through a 5-step pipeline:

1. **Tokenize** — input text is tokenized using the HuggingFace tokenizer (`tokenizer.json`)
2. **Pad or truncate** — token sequence is padded or truncated to exactly 128 tokens
3. **ONNX inference** — the token IDs are passed through the MiniLM-L6-v2 model via ONNX Runtime
4. **Mean pooling** — token-level embeddings are averaged (mean pooled) into a single vector
5. **L2 normalize** — the resulting 384-dimensional vector is normalized to unit length

The output is a 384-dimensional float32 numpy array. Vectors are stored as raw bytes (`BLOB`) in SQLite and reconstructed with `np.frombuffer()`. Search uses brute-force cosine similarity (dot product of unit vectors) via numpy.

Key characteristics:
- **Model**: `all-MiniLM-L6-v2` via ONNX Runtime (~22 MB)
- **Inference time**: ~5ms per text
- **Lazy loading**: model is loaded on first `embed()` call, not at import time
- **128-token truncation**: longer inputs are truncated before embedding

## Storage Layer

### SQLite Database

Location: `~/.cache/ensemble-mcp/data.db` (WAL mode for concurrent reads)

#### WAL Mode and PRAGMA Configuration

The SQLite database is configured with three PRAGMAs on every connection:

```sql
PRAGMA journal_mode=WAL;     -- Write-Ahead Logging for concurrent reads
PRAGMA busy_timeout=5000;    -- 5-second retry on lock contention
PRAGMA foreign_keys=ON;      -- Enforce referential integrity
```

- **WAL mode** enables concurrent reads while a write is in progress — the MCP server and dashboard can both read the database simultaneously without blocking each other
- **5-second busy timeout** prevents immediate failures under contention — if the database is locked, SQLite retries for up to 5 seconds before returning an error
- **Foreign keys** enforce referential integrity between related tables (e.g., skill suggestions and their linked patterns)

**Core tables:**
- `patterns` — stored patterns with embeddings and match counts
- `session_checkpoints` — pipeline checkpoints with state JSON and embeddings
- `drift_history` — drift check results with scores and verdicts
- `project_files` — indexed files with language, role, size, mtime
- `file_exports` — extracted exports (functions, classes, etc.)
- `file_imports` — extracted imports per file
- `skill_suggestions` — proposed skill suggestions from clustering
- `skill_suggestion_patterns` — junction table linking suggestions to patterns
- `skill_usage_tracking` — usage metrics for discovered skills
- `skill_file_cache` — cached skill file content and embeddings
- `mcp_calls` — MCP call history for dashboard
- `idempotency_keys` — idempotency key deduplication (24h TTL)
- `project_snapshots` — cached project baseline summaries

### ONNX Model

Location: `~/.cache/ensemble-mcp/models/`

Files:
- `model.onnx` — MiniLM-L6-v2 ONNX model (~22 MB)
- `tokenizer.json` — HuggingFace tokenizer config

Model: `sentence-transformers/all-MiniLM-L6-v2` — 384-dimensional embeddings, downloaded from Hugging Face on first use.

## Extension Points

### Adding a New Tool

1. Create or add to a file in `src/ensemble_mcp/tools/`
2. Implement an async function decorated with `@tool_handler`
3. Add a `Tool` definition in `server.py`'s `TOOL_DEFINITIONS` list
4. Add a case to `_dispatch_tool()` in `server.py`

### Adding a New AI Tool (Installer)

1. Add a `ToolDefinition` to `TOOL_DEFINITIONS` in `src/ensemble_mcp/installer/__init__.py`
2. Define: config format, config path, MCP section path, detection paths, server entry format
3. The installer automatically handles detection, registration, and backup

### Adding Configuration Options

1. Add a constant to `src/ensemble_mcp/config/defaults.py`
2. Add a field to the `Settings` dataclass in `src/ensemble_mcp/config/settings.py`
3. The field is automatically available via TOML config and `ENSEMBLE_MCP_*` env vars

## Design Principles

- **Local-only harness intelligence:** Zero LLM/API calls — all intelligence runs locally (ONNX embeddings, numpy similarity, rule-based compression). The harness infrastructure layer adds zero latency or cost from external services.
- **Single-file storage:** One SQLite database per user, WAL mode for concurrency
- **Incremental indexing:** mtime-based invalidation avoids re-processing unchanged files
- **Standard envelope:** Every tool returns `{ok, data, error, meta}` with typed error codes
- **Idempotent mutations:** Optional idempotency keys prevent duplicate execution
- **Non-destructive installs:** Config backups are created before any modification
- **Harness-agnostic:** Works with any MCP-compatible agent harness — not tied to a specific execution environment

## Known Limitations

- **Brute-force cosine similarity**: The vector search uses brute-force comparison against all stored vectors. This is sufficient for <10K vectors (the expected scale), but would need an ANN (Approximate Nearest Neighbor) index for significantly larger datasets
- **Single-process design**: The server is designed for single-instance use. It is not designed for multi-instance concurrent access to the same database
- **128-token truncation**: Input text is truncated to 128 tokens before embedding. Very long text inputs may lose context from the truncated portion, which can affect similarity search accuracy

## Next Steps

- [Tool Reference](./tool-reference.md) — complete tool documentation
- [Integration Guide](./integration-guide.md) — using tools in pipelines
- [Configuration](./configuration.md) — all configurable options
