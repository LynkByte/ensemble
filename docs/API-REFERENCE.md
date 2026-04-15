# API Reference

Complete reference for all 19 MCP tools provided by **ensemble-mcp** across 8 categories: Patterns (3), Drift (1), Routing (1), Skills (3), Session (3), Indexer (4), Compress (2), and Utility (2).

## Response Envelope

Every tool returns this structure:

```json
{
  "ok": true | false,
  "data": { ... } | null,
  "error": { "code": "...", "message": "...", "retryable": bool, "details": {} } | null,
  "meta": { "duration_ms": int, "source": "string", "confidence": "string" }
}
```

**Meta fields:**
- `duration_ms` — execution time in milliseconds
- `source` — data origin: `"local"`, `"sqlite"`
- `confidence` — accuracy indicator: `"exact"`, `"partial"`, `"estimated"`

---

## Patterns

Semantic memory for storing and retrieving successful pipeline patterns.

### `patterns_search`

Search stored patterns by semantic similarity using vector embeddings.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | yes | — | Semantic search query |
| `top_k` | integer | no | 3 | Maximum results to return |
| `project` | string | no | null | Scope search to a project |
| `idempotency_key` | string | no | null | Dedup key for the call |

**Response `data`:**

```json
{
  "matches": [
    {
      "id": 1,
      "name": "laravel-api-migration",
      "context": "Adding new API endpoint with database migration",
      "approach": "Create migration first, then model, then controller",
      "outcome": "Clean migration with rollback support",
      "score": 0.847
    }
  ]
}
```

**Possible errors:** None (returns empty matches on no results)

---

### `patterns_store`

Store a new pattern from a successful pipeline for future semantic search. Text fields are redacted for secrets before persistence.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | yes | — | Short pattern name |
| `context` | string | yes | — | When this pattern applies |
| `approach` | string | yes | — | What approach was used |
| `outcome` | string | yes | — | What happened (success/failure) |
| `project` | string | no | null | Project scope |
| `idempotency_key` | string | no | null | Dedup key |

**Response `data`:**

```json
{
  "id": 42,
  "stored": true
}
```

**Possible errors:** None (validation is done by MCP schema)

---

### `patterns_prune`

Remove old/unused patterns that have zero match count and are older than the configured threshold.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `max_age_days` | integer | no | 90 | Age threshold in days |
| `idempotency_key` | string | no | null | Dedup key |

**Response `data`:**

```json
{
  "pruned": 5,
  "remaining": 142
}
```

**Possible errors:** None

---

## Drift

Scope drift detection using embedding similarity.

### `drift_check`

Compare the task description against a diff summary to detect scope drift. Returns a 0-1 drift score with flags for suspicious file changes.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `task_description` | string | yes | — | Original task description |
| `changed_files` | array[string] | yes | — | List of changed file paths |
| `diff_summary` | string | yes | — | Summary of code changes |
| `idempotency_key` | string | no | null | Dedup key |

**Response `data`:**

```json
{
  "score": 0.234,
  "similarity": 0.766,
  "flags": [
    "Unexpected file change: database/migrations/2026_04_create_orders.php"
  ],
  "verdict": "aligned"
}
```

**Verdicts:**
- `aligned` — drift score < 0.3 (changes match the task)
- `minor_drift` — drift score 0.3-0.6 (some unrelated changes)
- `significant_drift` — drift score >= 0.6 (changes deviate significantly from task)

**Suspicious file detection:** Files matching patterns like `migration`, `schema`, `config`, `.env`, `package.json`, `composer.json` are flagged if their path has low similarity (< 0.3) to the task description.

**Possible errors:** None

---

## Routing

Model tier recommendation based on agent role and task classification.

### `model_recommend`

Recommend a model tier (`best`, `mid`, `cheapest`) for an agent based on the 7x4 routing matrix.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `agent` | string | yes | — | Agent name: `signal`, `proof`, `lens`, `craft`, `scope`, `ensemble`, `trace` |
| `task_classification` | string | yes | — | `trivial`, `simple`, `standard`, `complex` |
| `task_description` | string | no | null | Optional context (not currently used in routing logic) |
| `idempotency_key` | string | no | null | Dedup key |

**Response `data`:**

```json
{
  "tier": "best",
  "reason": "Standard multi-file task — best model for accuracy",
  "agent": "craft",
  "classification": "standard"
}
```

**Tier meanings:**
- `best` — Use the most capable model (e.g., claude-opus-4, o1)
- `mid` — Balanced cost/quality (e.g., claude-sonnet-4, gpt-4o)
- `cheapest` — Minimize cost (e.g., claude-haiku-3.5, gpt-4o-mini)

Unknown agent/classification pairs default to `mid`.

**Possible errors:** None

---

## Skills

Skill discovery, suggestion, and generation from stored patterns.

### `skills_discover`

Scan tool-native skill locations and return relevant skills. Optionally filter by semantic query.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_path` | string | yes | — | Path to the project root |
| `query` | string | no | null | Semantic search query to filter skills |
| `idempotency_key` | string | no | null | Dedup key |

**Scanned directories:**
- `.ai/skills/`
- `.claude/skills/`
- `.cursor/rules/`
- `.github/copilot-instructions/`
- `.opencode/skills/`

**Response `data`:**

```json
{
  "detected": [
    {
      "name": "api-testing",
      "source_tool": "opencode",
      "path": ".ai/skills/api-testing.md",
      "confidence": 0.847
    }
  ],
  "snippets": [
    {
      "content": "# API Testing\n\nWhen testing API endpoints...",
      "relevance": 0.847
    }
  ]
}
```

The `snippets` field is only present when a `query` is provided.

**Caching:** Skill file content and embeddings are cached in SQLite with mtime-based invalidation. The first call indexes skill files and computes embeddings; subsequent calls reuse cached data and only re-process files that have changed on disk. Deleted files are automatically cleaned up from the cache.

**Possible errors:**
- `NOT_FOUND_PROJECT` — project_path directory does not exist

---

### `skills_suggest`

Detect recurring patterns and suggest them as reusable skills. Uses single-linkage agglomerative clustering on pattern embeddings.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_path` | string | yes | — | Project path |
| `min_cluster_size` | integer | no | 3 | Minimum patterns to form a cluster |
| `stale_threshold_days` | integer | no | 60 | Days before a skill is considered stale |
| `idempotency_key` | string | no | null | Dedup key |

**Response `data`:**

```json
{
  "suggestions": [
    {
      "id": 1,
      "pattern_ids": [3, 7, 12],
      "theme": "Cluster of 3 similar patterns",
      "confidence": 0.823,
      "proposed_name": "api-endpoint-testing",
      "proposed_content": "# api-endpoint-testing\n\n> Auto-generated..."
    }
  ],
  "stale_skills": [
    {
      "path": ".ai/skills/old-pattern.md",
      "last_matched_at": "2026-01-15T10:00:00",
      "days_unused": 80
    }
  ]
}
```

**Possible errors:** None

---

### `skills_generate`

Accept, dismiss, or defer a skill suggestion.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `suggestion_id` | integer | yes | — | Suggestion ID from `skills_suggest` |
| `action` | string | no | `accept` | `accept`, `dismiss`, or `defer` |
| `output_dir` | string | no | `.ai/skills/` | Directory to write the skill file |
| `idempotency_key` | string | no | null | Dedup key |

**Response `data` (accept):**

```json
{
  "generated": true,
  "path": ".ai/skills/api-endpoint-testing.md",
  "content": "# api-endpoint-testing\n\n> Auto-generated...",
  "status": "accepted"
}
```

**Response `data` (dismiss/defer):**

```json
{
  "generated": false,
  "status": "dismissed"
}
```

**Possible errors:**
- `NOT_FOUND_SKILL_SUGGESTION` — suggestion_id does not exist
- `CONFLICT_ALREADY_RESOLVED` — suggestion already accepted or dismissed
- `VALIDATION_INVALID_VALUE` — action not one of accept/dismiss/defer

---

## Session

Pipeline checkpoint state with optimistic versioning.

### `session_save`

Save pipeline checkpoint state. Supports optimistic versioning to prevent concurrent overwrites. When `original_request` is provided, an embedding is generated for semantic search via `session_search`.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `session_id` | string | yes | — | Session identifier |
| `state` | object | yes | — | Arbitrary pipeline state to checkpoint |
| `version` | integer | no | null | Expected version for optimistic lock |
| `original_request` | string | no | null | The user's original request (enables semantic search) |
| `decisions` | array[string] | no | null | Key decisions made during the pipeline |
| `completed_steps` | array[string] | no | null | Steps completed so far |
| `remaining_steps` | array[string] | no | null | Steps remaining to complete |
| `files_changed` | array[string] | no | null | Files modified during the pipeline |
| `errors` | array[string] | no | null | Errors encountered during the pipeline |
| `context_for_resume` | string | no | null | Key context needed to resume without re-deriving |
| `task_classification` | string | no | null | `trivial`, `simple`, `standard`, `complex` |
| `status` | string | no | `running` | Pipeline status |
| `project` | string | no | null | Project path for scoped search |
| `idempotency_key` | string | no | null | Dedup key |

**Version behavior:**
- First save: version is set to 1
- Subsequent saves without `version`: auto-increments
- Subsequent saves with `version`: must match current version, otherwise `CONFLICT_VERSION_MISMATCH`

**Response `data`:**

```json
{
  "saved": true,
  "version": 3
}
```

**Possible errors:**
- `CONFLICT_VERSION_MISMATCH` — provided version does not match current version

---

### `session_load`

Load the latest checkpoint, or a specific session's checkpoint.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `session_id` | string | no | null | Specific session. Omit for the most recent checkpoint. |

**Response `data` (found):**

```json
{
  "found": true,
  "session_id": "sess_a1b2c3d4e5f6",
  "state": { "step": 3, "files_processed": ["a.py", "b.py"] },
  "version": 2,
  "original_request": "Add user authentication",
  "task_classification": "standard",
  "status": "running",
  "project": "/path/to/project"
}
```

Fields `original_request`, `task_classification`, `status`, and `project` are included only when non-null (backward compatible with older data).

**Response `data` (not found):**

```json
{
  "found": false
}
```

**Possible errors:** None (returns `found: false` instead of erroring)

---

### `session_search`

Search sessions by semantic similarity to a query string. Embeds the query and compares against stored session embeddings using cosine similarity.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | yes | — | Semantic search query |
| `top_k` | integer | no | 5 | Maximum results to return |
| `project` | string | no | null | Filter by project |
| `status` | string | no | null | Filter by status (e.g., `running`, `completed`) |
| `idempotency_key` | string | no | null | Dedup key |

**Response `data`:**

```json
{
  "matches": [
    {
      "session_id": "sess_a1b2c3d4e5f6",
      "score": 0.823,
      "version": 3,
      "created_at": "2026-04-15T10:00:00",
      "original_request": "Add user authentication",
      "task_classification": "standard",
      "status": "completed",
      "project": "/path/to/project"
    }
  ]
}
```

**Note:** Only sessions saved with an `original_request` (which generates an embedding) are searchable. Sessions without embeddings are excluded from search results.

**Possible errors:** None (returns empty matches on no results)

---

## Indexer

Lightweight file-level codebase index with incremental refresh.

### `project_index`

Build or refresh the codebase index. Scans the file tree, detects language, extracts exports/imports, and detects file roles. Uses mtime for incremental updates.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_path` | string | yes | — | Path to project root |
| `force` | boolean | no | false | Force full re-index (ignore mtime cache) |
| `idempotency_key` | string | no | null | Dedup key |

**Response `data`:**

```json
{
  "indexed": true,
  "files": 247,
  "cached": 1203,
  "total": 1450
}
```

**Supported languages:** Python, TypeScript, JavaScript, PHP, Go, Rust, Ruby, Java, Kotlin, Swift, C, C++, C#, Vue, Svelte, HTML, CSS, SCSS, LESS, JSON, YAML, TOML, XML, Markdown, SQL, Shell, Dockerfile, Terraform

**Possible errors:**
- `NOT_FOUND_PROJECT` — project_path directory does not exist

---

### `project_query`

Query the project index to find files by type, path pattern, or free-text search.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_path` | string | yes | — | Project path |
| `query` | string | no | null | Free-text search (matches file path and role) |
| `file_types` | array[string] | no | null | Filter by language (e.g., `["python", "typescript"]`) |
| `path_pattern` | string | no | null | Path substring filter |

**Response `data`:**

```json
{
  "files": [
    {
      "path": "src/ensemble_mcp/tools/patterns.py",
      "language": "python",
      "role": null,
      "size_bytes": 2560,
      "modified_at": "2026-04-05T08:30:00+00:00",
      "exports": [
        { "name": "patterns_search", "kind": "function" },
        { "name": "patterns_store", "kind": "function" }
      ]
    }
  ],
  "count": 1
}
```

**Possible errors:** None (returns empty files array)

---

### `project_dependencies`

Get the import/dependency graph for a specific file: what it imports, what imports it, and related files (sharing common imports).

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_path` | string | yes | — | Project path |
| `file_path` | string | yes | — | Relative file path within the project |

**Response `data`:**

```json
{
  "file": "src/ensemble_mcp/tools/patterns.py",
  "imports": [
    "..contracts.envelope",
    "..memory.store",
    "..state.idempotency"
  ],
  "imported_by": [
    "src/ensemble_mcp/server.py"
  ],
  "related": [
    "src/ensemble_mcp/tools/drift.py",
    "src/ensemble_mcp/tools/session.py"
  ]
}
```

**Possible errors:**
- `NOT_FOUND_FILE` — file not found in the index (run `project_index` first)

---

### `project_snapshot`

Generate or return a cached compact project baseline summary from the codebase index. Returns language, framework, conventions, directory structure, test setup, build tools, and key files. Results are cached with mtime-based invalidation.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_path` | string | yes | — | Path to project root |
| `force` | boolean | no | false | Force regeneration even if cached |
| `idempotency_key` | string | no | null | Dedup key |

**Response `data`:**

```json
{
  "snapshot": {
    "project_path": "/path/to/project",
    "language": "python",
    "framework": null,
    "conventions": [
      "snake_case file naming",
      "test files present (12 files)",
      "Python package structure (__init__.py)"
    ],
    "structure": {
      "src": "source",
      "tests": "tests",
      "docs": "documentation"
    },
    "test_setup": {
      "framework": "pytest",
      "pattern_dir": "tests"
    },
    "build_tools": ["pyproject.toml", "docker"],
    "key_files": [
      {
        "path": "src/ensemble_mcp/server.py",
        "role": "",
        "exports": ["serve", "_dispatch_tool", "_health"]
      }
    ]
  },
  "cached": false,
  "files_hash": "a1b2c3d4e5f6g7h8"
}
```

**Note:** Requires `project_index` to have been run first. The snapshot is cached for 24 hours (configurable) and invalidated when file modification times change.

**Possible errors:**
- `NOT_FOUND_PROJECT` — project not indexed (run `project_index` first)

---

## Context Compression & Prompt Caching

Rule-based text compression and prompt section ordering for reducing token usage and optimizing LLM cache hit rates.

### `context_compress`

Compress verbose natural language text into terse, token-efficient form while preserving all technical content.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `text` | string | yes | — | The text to compress |
| `idempotency_key` | string | no | null | Dedup key |

**Response `data`:**

```json
{
  "compressed_text": "Build REST API user mgmt. Need CRUD endpoints /api/users...",
  "original_tokens": 156,
  "compressed_tokens": 94,
  "savings_pct": 39.7,
  "preserved_count": 3
}
```

**Notes:**
- Rule-based compression, zero LLM calls
- Preserves: code blocks, inline code, URLs, file paths, headings, tables, version numbers, dates
- `preserved_count` indicates how many technical content blocks were detected and preserved verbatim
- Typical savings: ~30-40% token reduction on natural language text

**Possible errors:**
- `VALIDATION_MISSING_FIELD` — text is empty
- `VALIDATION_CONSTRAINT` — text too long or too short

---

### `context_prepare`

Prepare and order prompt sections for optimal LLM cache hit rates. Sorts sections by priority (static → project → task) to maximize the stable prefix that LLM providers can cache across calls. Optionally compresses each section through the compression engine.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `sections` | array[object] | yes | — | Sections to prepare, each with `name`, `content`, and `priority` |
| `compress_sections` | boolean | no | false | Optionally compress each section via the compression engine |
| `idempotency_key` | string | no | null | Dedup key |

Each section object requires:

| Field | Type | Description |
|---|---|---|
| `name` | string | Section name |
| `content` | string | Section content |
| `priority` | string | Cache priority tier: `"static"`, `"project"`, or `"task"` |

**Priority tiers:**
- `static` — System prompt, rules, instructions (most cacheable, placed first)
- `project` — Project conventions, structure, context (medium cacheability)
- `task` — Current request, diff, task-specific content (least cacheable, placed last)

**Response `data`:**

```json
{
  "prepared_text": "...(ordered and optionally compressed sections)...",
  "section_count": 3,
  "prefix_stable_bytes": 2048,
  "sections": [
    {
      "name": "system-prompt",
      "priority": "static",
      "original_bytes": 1200,
      "prepared_bytes": 1100
    },
    {
      "name": "project-conventions",
      "priority": "project",
      "original_bytes": 800,
      "prepared_bytes": 750
    },
    {
      "name": "current-task",
      "priority": "task",
      "original_bytes": 500,
      "prepared_bytes": 480
    }
  ]
}
```

`prefix_stable_bytes` indicates the byte count of the stable prefix (static + project sections) that LLM providers can cache across calls.

**Possible errors:**
- `VALIDATION_MISSING_FIELD` — sections list is empty
- `VALIDATION_INVALID_VALUE` — section missing required keys or invalid priority

---

## Utility

### `health`

Server health check. Returns status, version, database size, and pattern count.

**Parameters:** None

**Response `data`:**

```json
{
  "status": "ok",
  "version": "0.1.0b4",
  "db_size_bytes": 524288,
  "pattern_count": 42,
  "server_name": "ensemble-mcp"
}
```

**Possible errors:** None

---

### `reset`

Reset all stored data. This is a **destructive operation** — it deletes all patterns, sessions, steps, checkpoints, and other data from all tables.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `confirm` | boolean | yes | — | Must be `true` to proceed |
| `idempotency_key` | string | no | null | Dedup key |

**Response `data`:**

```json
{
  "reset": true
}
```

**Possible errors:**
- `VALIDATION_CONSTRAINT` — `confirm` is not `true`

---

## Error Code Reference

### VALIDATION (never retry)

| Code | Meaning |
|---|---|
| `VALIDATION_MISSING_FIELD` | Required field is empty or too short |
| `VALIDATION_INVALID_VALUE` | Value is not in the allowed set |
| `VALIDATION_INVALID_TYPE` | Wrong type (e.g., string where int expected) |
| `VALIDATION_CONSTRAINT` | Value violates a constraint (e.g., too long, confirmation required) |

### NOT_FOUND (never retry)

| Code | Meaning |
|---|---|
| `NOT_FOUND_SESSION` | Session ID does not exist |
| `NOT_FOUND_PATTERN` | Pattern ID does not exist |
| `NOT_FOUND_STEP` | Step ID does not exist |
| `NOT_FOUND_SKILL_SUGGESTION` | Skill suggestion ID does not exist |
| `NOT_FOUND_FILE` | File not found in the codebase index |
| `NOT_FOUND_PROJECT` | Project directory does not exist |
| `NOT_FOUND_CHECKPOINT` | Session checkpoint not found |

### CONFLICT (retry after refresh)

| Code | Meaning |
|---|---|
| `CONFLICT_VERSION_MISMATCH` | Optimistic lock failure in session_save |
| `CONFLICT_INVALID_STATE_TRANSITION` | Invalid state machine transition |
| `CONFLICT_DUPLICATE` | Duplicate resource creation attempt |
| `CONFLICT_ALREADY_RESOLVED` | Skill suggestion already accepted/dismissed |

### TIMEOUT (retry with backoff)

| Code | Meaning |
|---|---|
| `TIMEOUT_EMBEDDING` | Embedding computation timed out |
| `TIMEOUT_INDEX` | Indexing operation timed out |
| `TIMEOUT_QUERY` | Query execution timed out |

### IO (retry with backoff)

| Code | Meaning |
|---|---|
| `IO_DATABASE` | SQLite read/write error |
| `IO_FILESYSTEM` | File system access error |
| `IO_MODEL_DOWNLOAD` | ONNX model download failure |

### INTERNAL (not retryable unless marked)

| Code | Meaning |
|---|---|
| `INTERNAL_ERROR` | Unexpected server error |
| `INTERNAL_SCHEMA_MIGRATION` | Database migration failure |
