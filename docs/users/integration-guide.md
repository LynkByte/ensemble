# Integration Guide

How to integrate `ensemble-mcp` into AI agent pipelines. This guide covers the recommended tool invocation patterns for each phase of a development pipeline.

## Overview

`ensemble-mcp` provides 19 tools that augment AI agent pipelines with memory, drift detection, model routing, and codebase intelligence. All processing is local — no external API calls.

```mermaid
flowchart TB
    subgraph Pre["Pre-Pipeline Setup"]
        direction LR
        A1[project_index] --> A2[project_snapshot]
        A2 --> A3[skills_discover]
        A3 --> A4[patterns_search]
        A4 --> A5[session_search]
        A5 --> A6[model_recommend]
    end

    subgraph Mid["Mid-Pipeline Execution"]
        direction LR
        B1[session_save\ncheckpoints] --> B2[drift_check]
        B2 --> B3[project_query\nfile lookup]
        B3 --> B4[project_dependencies\nimport graph]
        B4 --> B5[context_compress\ntoken savings]
    end

    subgraph Post["Post-Pipeline Completion"]
        direction LR
        C1[session_save\nfinal status] --> C2[patterns_store]
        C2 --> C3[skills_suggest]
        C3 --> C4[patterns_prune]
    end

    Pre --> Mid --> Post

    style Pre fill:#2563eb,color:#fff
    style Mid fill:#059669,color:#fff
    style Post fill:#7c3aed,color:#fff
```

---

## Pre-Pipeline Phase

Before starting the main implementation work, set up context and gather intelligence.

### 1. Index the Project

Build or refresh the codebase index so `project_query` and `project_dependencies` work:

```json
{
  "tool": "project_index",
  "arguments": {
    "project_path": "/path/to/project"
  }
}
```

The index is incremental — only changed files are re-processed. Use `force: true` for a full rebuild.

### 2. Get Project Snapshot

Generate a compact baseline summary of the project:

```json
{
  "tool": "project_snapshot",
  "arguments": {
    "project_path": "/path/to/project"
  }
}
```

Returns language, framework, conventions, directory structure, test setup, build tools, and key files. Cached for 24 hours with mtime-based invalidation.

### 3. Discover Skills

Find relevant skill files that provide domain-specific instructions:

```json
{
  "tool": "skills_discover",
  "arguments": {
    "project_path": "/path/to/project",
    "query": "testing patterns for REST APIs"
  }
}
```

### 4. Search for Past Patterns

Find similar past solutions before starting new work:

```json
{
  "tool": "patterns_search",
  "arguments": {
    "query": "add user authentication with JWT",
    "top_k": 5,
    "project": "/path/to/project",
    "detail_level": "index"
  }
}
```

Use `detail_level: "index"` for a compact scan (~10x fewer tokens), then fetch full details for relevant matches with `detail_level: "full"` (the default). You can also filter by `category` (e.g., `"gotcha"`, `"problem-solution"`).

### 5. Search Past Sessions

Find relevant previous pipeline sessions:

```json
{
  "tool": "session_search",
  "arguments": {
    "query": "authentication implementation",
    "project": "/path/to/project",
    "status": "completed"
  }
}
```

### 6. Choose Model Tier

Get a model recommendation for the current agent and task:

```json
{
  "tool": "model_recommend",
  "arguments": {
    "agent": "craft",
    "task_classification": "standard",
    "task_description": "Add JWT authentication to the API"
  }
}
```

---

## Mid-Pipeline Phase

During implementation, use checkpoints, drift detection, and code intelligence.

### Session Checkpoints

Save progress regularly so work can be resumed if interrupted:

```json
{
  "tool": "session_save",
  "arguments": {
    "session_id": "session-abc-123",
    "state": {
      "current_step": "implementing auth middleware"
    },
    "original_request": "Add JWT authentication to the API",
    "completed_steps": ["created user model", "added login endpoint"],
    "remaining_steps": ["add middleware", "write tests"],
    "files_changed": ["src/auth/middleware.py", "src/models/user.py"],
    "task_classification": "standard",
    "status": "running",
    "project": "/path/to/project"
  }
}
```

The `version` field enables optimistic locking — pass the current version to detect concurrent modifications:

```json
{
  "tool": "session_save",
  "arguments": {
    "session_id": "session-abc-123",
    "state": { ... },
    "version": 2
  }
}
```

### Drift Detection

After making changes, check if the implementation drifted from the original task:

```json
{
  "tool": "drift_check",
  "arguments": {
    "task_description": "Add JWT authentication to the API",
    "changed_files": [
      "src/auth/middleware.py",
      "src/models/user.py",
      "migrations/001_add_users.sql",
      "src/config/database.py"
    ],
    "diff_summary": "Added user model, login endpoint, JWT middleware, and database config changes"
  }
}
```

Act on the verdict:
- **`aligned`** (score < 0.3) — continue normally
- **`minor_drift`** (score < 0.6) — review the flagged files
- **`significant_drift`** (score ≥ 0.6) — stop and reassess scope

### File Lookup

Query the index to find relevant files:

```json
{
  "tool": "project_query",
  "arguments": {
    "project_path": "/path/to/project",
    "query": "authentication middleware",
    "file_types": ["python"]
  }
}
```

### Dependency Analysis

Check what a file imports and what imports it:

```json
{
  "tool": "project_dependencies",
  "arguments": {
    "project_path": "/path/to/project",
    "file_path": "src/auth/middleware.py"
  }
}
```

### Context Compression

Reduce token usage when passing large context to LLMs:

```json
{
  "tool": "context_compress",
  "arguments": {
    "text": "Long verbose text that needs to be compressed..."
  }
}
```

### Context Preparation

Order prompt sections for optimal LLM cache hit rates:

```json
{
  "tool": "context_prepare",
  "arguments": {
    "sections": [
      {
        "name": "system-prompt",
        "content": "You are a senior engineer...",
        "priority": "static"
      },
      {
        "name": "project-conventions",
        "content": "This project uses FastAPI...",
        "priority": "project"
      },
      {
        "name": "current-task",
        "content": "Add JWT authentication...",
        "priority": "task"
      }
    ],
    "compress_sections": true
  }
}
```

---

## Post-Pipeline Phase

After completing the task, store lessons learned and maintain the pattern database.

### Final Session Save

Mark the session as completed with final state:

```json
{
  "tool": "session_save",
  "arguments": {
    "session_id": "session-abc-123",
    "state": {
      "result": "success",
      "summary": "Added JWT authentication with middleware and tests"
    },
    "status": "completed",
    "completed_steps": ["created user model", "added login endpoint", "added middleware", "wrote tests"],
    "remaining_steps": [],
    "files_changed": [
      "src/auth/middleware.py",
      "src/models/user.py",
      "tests/test_auth.py"
    ]
  }
}
```

### Store Pattern

Record the successful approach for future reference:

```json
{
  "tool": "patterns_store",
  "arguments": {
    "name": "jwt-auth-fastapi",
    "context": "Adding JWT authentication to a FastAPI application",
    "approach": "Created User model, login endpoint with token generation, and middleware for route protection",
    "outcome": "Successfully added auth with 95% test coverage",
    "project": "/path/to/project",
    "category": "how-it-works"
  }
}
```

### Suggest Skills

Detect recurring patterns that could become reusable skills:

```json
{
  "tool": "skills_suggest",
  "arguments": {
    "project_path": "/path/to/project",
    "min_cluster_size": 3
  }
}
```

### Prune Old Patterns

Clean up stale, unused patterns:

```json
{
  "tool": "patterns_prune",
  "arguments": {
    "max_age_days": 90
  }
}
```

---

## Pipeline Resumption

When a pipeline is interrupted and needs to resume:

1. **Load the checkpoint:**
   ```json
   {
     "tool": "session_load",
     "arguments": {
       "session_id": "session-abc-123"
     }
   }
   ```

2. **Read the resume context** from the loaded session's `state.resume.context_for_resume` field, alongside `state.resume.remaining_steps`, `state.resume.decisions`, etc.

3. **Continue from the last completed step** without re-deriving context

---

## Idempotency in Pipelines

For pipeline steps that might be retried (e.g., after a crash), use idempotency keys:

```json
{
  "tool": "patterns_store",
  "arguments": {
    "name": "jwt-auth-fastapi",
    "context": "...",
    "approach": "...",
    "outcome": "...",
    "idempotency_key": "pipeline-abc-123-store-pattern"
  }
}
```

Replayed calls with the same key return the original result without re-executing.

---

## Multi-Agent Pipeline Example

In a multi-agent orchestration (e.g., the 7-agent ensemble pipeline):

| Phase | Agent | Tools Used |
|-------|-------|-----------|
| Planning | Ensemble (orchestrator) | `model_recommend`, `session_search`, `patterns_search` |
| Exploration | Scope (planner) | `project_index`, `project_snapshot`, `project_query`, `skills_discover` |
| Implementation | Craft (code writer) | `project_dependencies`, `context_compress`, `session_save` |
| Verification | Forge (test runner) | `drift_check`, `session_save` |
| Review | Lens (code review) | `context_prepare`, `drift_check` |
| Debugging | Trace (bug hunter) | `project_query`, `patterns_search` |
| Completion | Signal (git ops) | `session_save` (final), `patterns_store` |

## Next Steps

- [Tool Reference](./tool-reference.md) — detailed parameter docs for every tool
- [Architecture Overview](./architecture-overview.md) — how the system is built
- [Configuration](./configuration.md) — tune thresholds for your workflow

---

## Realistic End-to-End Example

To see how these pipeline phases work in practice, here's a condensed multi-session scenario showing how ensemble-mcp tools fire behind the scenes while a developer builds a Laravel todo application.

### Session 1: Project Scaffolding

The developer creates a new Laravel project and asks the AI to set up authentication, a todos table, and an auto-categorizer.

| Tool Called | Purpose |
|---|---|
| `project_index` | Indexes the fresh Laravel scaffold so the agent knows every file |
| `project_snapshot` | Generates a compact baseline summary (language, framework, structure) |
| `patterns_search` | Searches for past patterns matching "laravel project setup" — empty on first project |
| `session_save` | Checkpoints progress after scaffolding is complete |

After completion, `patterns_store` saves the approach: *"Breeze for auth, service class for business logic"*.

### Session 2: Adding a Feature (CRUD + Soft Deletes)

Next day, the developer asks for full CRUD with Blade views.

| Tool Called | Purpose |
|---|---|
| `session_load` | Restores context from Session 1 |
| `patterns_search` | Finds the Session 1 pattern — agent learns the developer prefers service classes |
| `drift_check` | When the developer adds "also add soft deletes", drift score is 0.25 (aligned). If they'd asked for "also add a blog system", drift would be 0.72 (significant drift) and the agent would suggest finishing CRUD first |
| `patterns_store` | Saves the CRUD approach for future reference |

### Session 3: Refactoring and Skills

After several projects, the developer has accumulated 20+ patterns.

| Tool Called | Purpose |
|---|---|
| `skills_discover` | Finds existing skill files relevant to the current task |
| `skills_suggest` | Detects a cluster of 6 patterns around "Laravel service class architecture" and proposes a reusable skill |
| `skills_generate` | Writes the accepted suggestion as a reusable skill file to `.ai/skills/` |

The developer accepts the suggestion, and a skill file is written to `.ai/skills/`. From this point forward, every new Laravel project automatically loads this skill.

### Session 4: Different Project Reuses Patterns

The developer starts a completely different Laravel project (e.g., an e-commerce app).

| Tool Called | Purpose |
|---|---|
| `patterns_search` | Finds prior approaches from the todo app — service class architecture, duplicate detection, dashboard aggregation |

The agent applies the developer's preferred patterns from day one, without re-explaining anything. **This is the compounding effect** — each project makes the next one faster.

---

## What the Developer Sees vs. What ensemble-mcp Provides

| What the developer sees | What ensemble-mcp provides behind the scenes |
|---|---|
| "It remembered my project structure" | `project_snapshot` cached baseline summary |
| "It avoided the same mistake" | `patterns_search` found a prior gotcha pattern |
| "It knew our coding style" | `skills_discover` loaded project convention skills |
| "It caught my scope creep" | `drift_check` flagged unrelated changes |
| "It picked up where it left off" | `session_load` restored checkpoint state |
| "It used a cheaper model for simple tasks" | `model_recommend` selected the right tier |
| "It got smarter over time" | Patterns → Skills → Institutional AI memory |

---

## The Flywheel Effect

ensemble-mcp creates a compounding improvement cycle:

```
Patterns → Skills → Institutional AI Memory
```

1. **Patterns accumulate**: Each successful task generates stored patterns (`patterns_store`) capturing what worked, what didn't, and why
2. **Skills emerge**: Recurring patterns are detected via clustering (`skills_suggest`) and crystallized into reusable skill files (`skills_generate`)
3. **Memory compounds**: Skills make future tasks faster and more accurate. New patterns build on existing skills. The AI gets better at your specific project, team, and codebase over time

This is **institutional AI memory** — knowledge that persists across sessions, projects, and even team members. Unlike chat history that disappears, patterns and skills are durable and searchable.
