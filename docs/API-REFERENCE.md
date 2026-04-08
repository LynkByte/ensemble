# API Reference

Complete reference for all 24 MCP tools provided by **ensemble-mcp** (22 core tools + `health` + `reset`).

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
- `source` — data origin: `"local"`, `"sqlite"`, `"session_parser"`, `"estimator"`, `"hybrid"`
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
| `min_score` | number | no | 0.3 | Minimum score threshold |
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

## Metrics

Token tracking with per-agent cost breakdown using the pricing table.

### `metrics_start_session`

Start tracking a pipeline session. Creates a session in `running` state.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `task` | string | yes | — | Task description |
| `classification` | string | yes | — | `trivial`, `simple`, `standard`, or `complex` |
| `ai_tool` | string | no | null | Tool name: `opencode`, `claude-code`, `copilot`, etc. |
| `project` | string | no | null | Project path |
| `idempotency_key` | string | no | null | Dedup key |

**Response `data`:**

```json
{
  "session_id": "sess_a1b2c3d4e5f6",
  "state": "running"
}
```

**Possible errors:** None

---

### `metrics_record_step`

Record per-agent token and cost usage for a pipeline step. Cost is calculated automatically from the pricing table.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `session_id` | string | yes | — | Session to record against |
| `agent` | string | yes | — | Agent name (`ensemble`, `scope`, `craft`, etc.) |
| `input_tokens` | integer | no | 0 | Input token count |
| `output_tokens` | integer | no | 0 | Output token count |
| `cache_read_tokens` | integer | no | 0 | Tokens read from cache |
| `cache_write_tokens` | integer | no | 0 | Tokens written to cache |
| `web_search_requests` | integer | no | 0 | Web search request count |
| `cached_tokens` | integer | no | 0 | Total cached tokens (legacy) |
| `model` | string | no | `claude-sonnet-4` | Model used for pricing |
| `source` | string | no | `local` | Data source label |
| `confidence` | string | no | `exact` | Accuracy: `exact`, `partial`, `estimated` |
| `duration_ms` | integer | no | null | Step execution time |
| `idempotency_key` | string | no | null | Dedup key |

**Response `data`:**

```json
{
  "recorded": true,
  "step_id": 7,
  "cost_usd": 0.001245,
  "confidence": "exact",
  "source": "local"
}
```

**Possible errors:**
- `NOT_FOUND_SESSION` — session_id does not exist

---

### `metrics_end_session`

Finalize a session, transition it to a terminal state, and record the end time.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `session_id` | string | yes | — | Session to finalize |
| `status` | string | no | `completed` | Final status: `completed`, `success`, `failed`, `partial`, `killed` |
| `idempotency_key` | string | no | null | Dedup key |

**Response `data`:**

```json
{
  "session_id": "sess_a1b2c3d4e5f6",
  "total_cost": 0.0523,
  "state": "completed",
  "status": "completed"
}
```

**Possible errors:**
- `NOT_FOUND_SESSION` — session_id does not exist
- `CONFLICT_INVALID_STATE_TRANSITION` — session already in terminal state

---

### `metrics_session_report`

Generate a formatted session report with per-agent breakdown.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `session_id` | string | yes | — | Session to report on |

**Response `data`:**

```json
{
  "report": {
    "session_id": "sess_a1b2c3d4e5f6",
    "task": "Add user authentication",
    "classification": "standard",
    "ai_tool": "opencode",
    "state": "completed",
    "status": "completed",
    "total_input_tokens": 15000,
    "total_output_tokens": 3200,
    "total_cached_tokens": 8000,
    "total_cost_usd": 0.0523,
    "started_at": "2026-04-05T10:00:00",
    "ended_at": "2026-04-05T10:05:30",
    "steps": [
      {
        "agent": "scope",
        "model": "claude-sonnet-4",
        "input_tokens": 5000,
        "output_tokens": 1200,
        "cached_tokens": 3000,
        "cost_usd": 0.018,
        "accuracy": "exact",
        "duration_ms": 4500
      }
    ]
  }
}
```

**Possible errors:**
- `NOT_FOUND_SESSION` — session_id does not exist

---

### `metrics_trend`

Cost and token trends aggregated by day over the last N days.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `days` | integer | no | 30 | Number of days to look back |

**Response `data`:**

```json
{
  "daily_costs": [
    {
      "date": "2026-04-04",
      "input_tokens": 50000,
      "output_tokens": 12000,
      "cost_usd": 0.1523,
      "sessions": 3
    }
  ],
  "total_cost": 1.2345,
  "total_sessions": 42,
  "avg_cost_per_session": 0.0294,
  "days": 30
}
```

**Possible errors:** None (returns empty array on no data)

---

### `metrics_compare`

Compare two sessions side by side with a diff of key metrics.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `session_id_a` | string | yes | — | First session |
| `session_id_b` | string | yes | — | Second session |

**Response `data`:**

```json
{
  "session_a": {
    "session_id": "sess_aaa",
    "task": "Feature A",
    "classification": "standard",
    "input_tokens": 10000,
    "output_tokens": 3000,
    "cached_tokens": 5000,
    "cost_usd": 0.04
  },
  "session_b": {
    "session_id": "sess_bbb",
    "task": "Feature B",
    "classification": "complex",
    "input_tokens": 25000,
    "output_tokens": 8000,
    "cached_tokens": 10000,
    "cost_usd": 0.12
  },
  "diff": {
    "input_tokens": 15000,
    "output_tokens": 5000,
    "cost_usd": 0.08
  }
}
```

**Possible errors:**
- `NOT_FOUND_SESSION` — either session_id does not exist

---

### `metrics_backfill`

Backfill step records with real token data from AI tool session files. Reads actual usage from OpenCode's SQLite database or Claude Code's JSONL session files and retroactively updates steps that were recorded with zero or estimated tokens.

Supports both OpenCode and Claude Code via the shared parser dispatcher. Steps are matched to parsed messages by timestamp proximity and model name.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `session_id` | string | No | Session to backfill. Defaults to the most recent session. |
| `force` | boolean | No | Overwrite steps that already have real token data. Default: `false`. |
| `ai_tool` | string | No | Override AI tool detection: `"opencode"` or `"claude-code"`. |
| `idempotency_key` | string | No | Deduplication key. |

**Response data:**

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | The session that was backfilled. |
| `steps_updated` | integer | Number of steps updated with real data. |
| `steps_skipped` | integer | Steps skipped (already had real data). |
| `steps_unmatched_db` | integer | DB steps with no parser match. |
| `steps_unmatched_parser` | integer | Parser steps with no DB match. |
| `before` | object | Session totals before backfill. |
| `after` | object | Session totals after backfill. |
| `source` | string | Always `"backfill"`. |
| `confidence` | string | `"exact"` if all steps matched, `"partial"` if some unmatched. |

**Possible errors:** `NOT_FOUND_SESSION`, `NOT_FOUND_STEP`, `VALIDATION_MISSING_FIELD`, `IO_FILESYSTEM`

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

**Possible errors:** None

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

Save pipeline checkpoint state. Supports optimistic versioning to prevent concurrent overwrites.

**Parameters:**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `session_id` | string | yes | — | Session identifier |
| `state` | object | yes | — | Arbitrary pipeline state to checkpoint |
| `version` | integer | no | null | Expected version for optimistic lock |
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
  "version": 2
}
```

**Response `data` (not found):**

```json
{
  "found": false
}
```

**Possible errors:** None (returns `found: false` instead of erroring)

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
    "src/ensemble_mcp/tools/metrics.py"
  ]
}
```

**Possible errors:**
- `NOT_FOUND_FILE` — file not found in the index (run `project_index` first)

---

## Utility

### `health`

Server health check. Returns status, version, database size, and pattern count.

**Parameters:** None

**Response `data`:**

```json
{
  "status": "ok",
  "version": "0.1.0",
  "db_size_bytes": 524288,
  "pattern_count": 42,
  "server_name": "ensemble-mcp"
}
```

**Possible errors:** None

---

### `reset`

Reset all stored data. This is a **destructive operation** — it deletes all patterns, sessions, steps, checkpoints, and other data from all 12 tables.

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
