---
name: ensemble-mcp-workflow
description: Workflow instructions for invoking ensemble-mcp tools during AI agent pipelines. Load this skill to enable automatic memory, cost tracking, drift detection, model routing, and skills discovery.
---

# Ensemble MCP Workflow

This skill tells you **when and how** to call ensemble-mcp tools during your work. These tools provide persistent memory, cost tracking, drift detection, smart model routing, codebase indexing, and skills discovery.

**Graceful degradation:** If any ensemble-mcp tool call fails or the tools are not available (no MCP server connected), skip that step silently and continue your work normally. Never let a missing tool block the pipeline.

---

## Tool Quick Reference

| Tool | When to Call | Required Parameters |
|------|-------------|-------------------|
| `metrics_start_session` | Start of every task | `task`, `classification` |
| `metrics_record_step` | After each agent completes work | `session_id`, `agent` |
| `metrics_end_session` | Task complete or failed | `session_id`, `status` |
| `metrics_session_report` | When user asks about session cost | `session_id` |
| `metrics_trend` | When user asks about cost over time | `days` (optional) |
| `metrics_compare` | When user asks to compare sessions | `session_id_a`, `session_id_b` |
| `patterns_search` | Before planning/implementing | `query` |
| `patterns_store` | After successful task completion | `name`, `context`, `approach`, `outcome` |
| `patterns_prune` | Periodic maintenance | *(none required)* |
| `drift_check` | After implementation, before commit | `task_description`, `changed_files`, `diff_summary` |
| `model_recommend` | Before invoking expensive agents | `agent`, `task_classification` |
| `skills_discover` | Before planning/implementing | `project_path` |
| `skills_suggest` | When user asks, or periodically | `project_path` |
| `skills_generate` | When user accepts a skill suggestion | `suggestion_id` |
| `project_index` | Start of task (first time per project) | `project_path` |
| `project_query` | During codebase exploration | `project_path` |
| `project_dependencies` | When understanding file relationships | `project_path`, `file_path` |
| `session_save` | After each major step (standard/complex) | `session_id`, `state` |
| `session_load` | When resuming interrupted work | `session_id` (optional) |
| `health` | When checking server status | *(none)* |
| `reset` | When user requests data wipe | `confirm: true` |

---

## Pipeline Integration

When working within the multi-agent pipeline (Captain orchestrating Architect, Engineer, Forge, Inspector, Shipper), call ensemble-mcp tools at these specific points:

### Pre-Pipeline (Captain, before Step 1)

```
1. metrics_start_session(task=<user's request summary>, classification=<trivial|simple|standard|complex>)
   → Save the returned session_id for all subsequent calls

2. patterns_search(query=<user's request as natural language>)
   → Pass any relevant findings to the Architect as "Prior approaches"

3. project_index(project_path=<project root>)
   → Only needed once per project, or when force=true for refresh

4. skills_discover(project_path=<project root>, query=<task-relevant keywords>)
   → Pass discovered skills to the Architect and Engineer
```

### After Step 1: PLAN+EXPLORE (Captain)

```
5. metrics_record_step(session_id=<id>, agent="scope")
   → Optional: include input_text/output_text for token estimation
```

### After Step 2: IMPLEMENT (Captain)

```
6. drift_check(
       task_description=<original user request>,
       changed_files=<list of files the Engineer modified>,
       diff_summary=<brief summary of what changed>
   )
   → If verdict is "significant_drift" (score >= 0.6): warn the user,
     list flagged files, and ask whether to proceed or revert
   → If "aligned" or "minor_drift": proceed normally

7. metrics_record_step(session_id=<id>, agent="craft")
```

### After Step 3: BUILD+TEST (Captain)

```
8. metrics_record_step(session_id=<id>, agent="forge")
```

### After Step 4: REVIEW (Captain)

```
9. metrics_record_step(session_id=<id>, agent="lens")
```

### Post-Pipeline (Captain, after final step)

```
10. patterns_store(
        name=<short descriptive name for the approach>,
        context=<what problem was being solved>,
        approach=<how it was solved>,
        outcome=<result: success/partial/failed + brief detail>
    )
    → Only store on successful or partially successful completions
    → Do NOT store on complete failures (nothing useful to remember)

11. metrics_end_session(session_id=<id>, status=<completed|failed|killed>)

12. session_save(session_id=<id>, state=<final pipeline state>)
    → Only for standard/complex tasks
```

### Session Persistence (Standard/Complex tasks)

```
- After PLAN+EXPLORE completes: session_save(session_id=<id>, state={step: 1, ...})
- After IMPLEMENT completes: session_save(session_id=<id>, state={step: 2, ...})
- On resume: session_load() or session_load(session_id=<known id>)
```

---

## Standalone Usage (Single-Agent Mode)

When working as a single agent (no pipeline, just one AI assistant), use a simplified flow:

### Start of Task

```
1. metrics_start_session(task=<what the user asked>, classification=<estimate>)
2. patterns_search(query=<task description>)
   → Use findings to inform your approach
3. project_index(project_path=<project root>)
   → If not already indexed
```

### During Work

```
4. project_query(project_path=<root>, query=<what you're looking for>)
   → Use instead of raw file searches when possible
5. project_dependencies(project_path=<root>, file_path=<file>)
   → Before making structural changes to understand import/export graph
6. skills_discover(project_path=<root>, query=<relevant domain>)
   → Find and load project-specific skills
```

### After Implementation

```
7. drift_check(task_description=<original request>, changed_files=[...], diff_summary="...")
   → Verify you stayed on task
```

### End of Task

```
8. patterns_store(name=..., context=..., approach=..., outcome=...)
   → On success, save for future recall
9. metrics_end_session(session_id=<id>, status="completed")
```

### On Demand (when user asks)

```
- "How much did that cost?" → metrics_session_report(session_id=<id>)
- "What's my spend this week?" → metrics_trend(days=7)
- "Compare those two sessions" → metrics_compare(session_id_a=..., session_id_b=...)
- "Any skill suggestions?" → skills_suggest(project_path=<root>)
```

---

## Agent Name Mapping

When calling `metrics_record_step` or `model_recommend`, use these agent names:

| Pipeline Agent | ensemble-mcp agent name |
|---------------|------------------------|
| Captain | `"ensemble"` |
| Architect | `"scope"` |
| Engineer | `"craft"` |
| Forge | `"forge"` |
| Inspector | `"lens"` |
| Shipper | `"signal"` |
| Hunter | `"trace"` |

---

## Classification Guide

When calling `metrics_start_session`, classify the task:

| Classification | When to use |
|---------------|------------|
| `"trivial"` | Typo, config change, rename, single-line fix |
| `"simple"` | Bug fix, small feature, isolated change |
| `"standard"` | Feature, refactor, multi-file change |
| `"complex"` | New system, major refactor, cross-cutting concern |

---

## Parameter Tips

### patterns_store — write good patterns

- **name**: Short, searchable (e.g., "laravel service class pattern", "react auth hook")
- **context**: The problem being solved (e.g., "Login endpoint 500 with special chars in password")
- **approach**: How it was solved (e.g., "Escape password before bcrypt, add input validation")
- **outcome**: Result (e.g., "Fixed, added 3 test cases for edge cases")
- **project** (optional): Set to project name for project-scoped patterns

### drift_check — provide enough context

- **task_description**: Use the user's original request, not your rephrasing
- **changed_files**: Full relative paths of all files modified
- **diff_summary**: 1-3 sentences summarizing what the changes do (not a git diff)

### metrics_record_step — token tracking

Priority order for token data (use the first available):
1. Direct fields: `input_tokens`, `output_tokens`, `cache_read_tokens`, etc.
2. Raw provider payload: `usage_raw` (Anthropic or OpenAI format, auto-detected)
3. Text estimation: `input_text`, `output_text` (tiktoken fallback)

If you have none of these, call the tool with just `session_id` and `agent` — it will record the step without token data.
