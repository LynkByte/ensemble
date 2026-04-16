# Bug Hunter Report — ensemble-mcp

**Date:** 2026-04-15 21:15:00  
**Scanner:** Bug Hunter (claude-opus-4.6)  
**Project:** ensemble-mcp — Python MCP server (16 tools, 11 subpackages)  
**Scan #3** (previous scans: #1 at 12:00, #2 at 18:30)

---

## Summary

| Metric | Value |
|--------|-------|
| **Total Bugs** | 8 |
| **Code Smells** | 7 |
| **Health Score** | **84 / 100** (Moderate — approaching Good) |
| **Critical** | 0 |
| **High** | 0 |
| **Medium** | 4 |
| **Low / Info** | 4 |
| **Tests** | 549 passed, 0 failed |
| **Coverage** | 85.62% (threshold: 80%) |
| **Ruff Lint** | All checks passed |

---

## Trends

| Metric | Scan #1 | Scan #2 | Scan #3 (now) | Change |
|--------|---------|---------|---------------|--------|
| Health Score | 68 | 82 | **84** | +2 |
| Bugs | 14 | 11 | **8** | -3 |
| Code Smells | 12 | 9 | **7** | -2 |
| Critical | 0 | 0 | **0** | -- |
| High | 6 | 0 | **0** | -- |
| Tests Passed | 487 | 543 | **549** | +6 |
| Test Errors | 54 | 0 | **0** | -- |

**Trend: Improving** — Steady improvement across all metrics over 3 scans. Health up +16 from first scan. All 6 High-severity bugs from scan #1 remain fixed. Bug count halved from 14 to 8.

---

## Bugs

### Medium Severity (4)

#### M1 — Dashboard `reset` Missing `project_snapshots` Table
- **Score:** 5.5 / 10 (Medium)
- **Impact:** 3 (data inconsistency) | **Exploitability:** 1 | **Scope:** 1 | **Confidence:** 0.5
- **Location:** `src/ensemble_mcp/dashboard/api.py:1176-1188`
- **Description:** The dashboard's `handle_reset()` deletes 11 tables but omits `project_snapshots`. Meanwhile, the MCP server's `_reset()` in `server.py:557-569` correctly includes all 12 tables. After a dashboard reset, stale project snapshots persist, causing the indexer to serve outdated data.
- **Fix:** Add `"project_snapshots"` to the table list at `api.py:1176`.

#### M2 — `session_save` Overwrites `created_at` on UPDATE
- **Score:** 4.5 / 10 (Medium)
- **Impact:** 2 (incorrect audit trail) | **Exploitability:** 1 | **Scope:** 1 | **Confidence:** 0.5
- **Location:** `src/ensemble_mcp/tools/session.py:136-137`
- **Description:** The UPDATE query sets `created_at = datetime('now')` every time a session checkpoint is updated. This destroys the original creation timestamp. The column should either be left untouched on update or a separate `updated_at` column should be used.
- **Fix:** Remove `created_at = datetime('now'),` from the UPDATE clause, or add a dedicated `updated_at` column to the schema.

#### M3 — `_get_store()` Has TOCTOU Race (Theoretical)
- **Score:** 4.0 / 10 (Medium)
- **Impact:** 2 (duplicate store) | **Exploitability:** 1 | **Scope:** 0.5 | **Confidence:** 0.5
- **Location:** `src/ensemble_mcp/server.py:40-50`
- **Description:** The lazy `_get_store()` function checks `if _store is None` then assigns it. In theory, two concurrent coroutines could both see `None` and create two VectorStore instances. Practically mitigated by asyncio's single-threaded event loop (no true preemption at `if` check), but the pattern is fragile — if `load_settings()` or `VectorStore()` ever yields control, the race becomes real.
- **Fix:** Use a lock or initialize eagerly in `serve()` before the event loop starts.

#### M4 — `advisory_lock` Is a No-Op on Windows
- **Score:** 4.0 / 10 (Medium)
- **Impact:** 2 (concurrent corruption) | **Exploitability:** 1 | **Scope:** 0.5 | **Confidence:** 0.5
- **Location:** `src/ensemble_mcp/state/locks.py:48-50`
- **Description:** On Windows, `advisory_lock()` silently yields without acquiring any lock. If two processes run concurrently on Windows, they can corrupt data protected by this lock. The no-op is documented but not warned at runtime.
- **Fix:** Use `msvcrt.locking()` on Windows, or log a warning when the no-op path is taken so users are aware.

### Low / Info (4)

#### L1 — `tools/__init__.py` Docstring Says 17 Tools, Server Has 19
- **Score:** 2.0 / 10 (Low)
- **Location:** `src/ensemble_mcp/tools/__init__.py:1`
- **Description:** The docstring says "17 tools total" and lists categories summing to 17. The server actually registers 19 tools (`project_snapshot` and `context_prepare` are not listed).
- **Fix:** Update the docstring to list all 19 tools with correct categories.

#### L2 — `server.py` Has 0% Test Coverage
- **Score:** 3.0 / 10 (Low)
- **Impact:** 1 | **Exploitability:** 0 | **Scope:** 1.5 | **Confidence:** 0.5
- **Location:** `src/ensemble_mcp/server.py` (115 statements, 0% covered)
- **Description:** The main MCP server entry point — tool registration, dispatch, and the `serve()` function — is completely untested. All tool logic is tested via unit tests against the underlying modules, but the glue code in `server.py` (argument parsing, dispatch routing, error wrapping) has zero coverage.
- **Fix:** Add integration tests that call `_dispatch_tool()` directly or test `call_tool()` with a mock MCP transport.

#### L3 — `compress/tokens.py` 57% Coverage — Download Path Untested
- **Score:** 1.5 / 10 (Info)
- **Location:** `src/ensemble_mcp/compress/tokens.py:47-67`
- **Description:** The tokenizer download and lazy-load fallback path is untested. If the ONNX tokenizer file is missing, the fallback to a regex-based counter is exercised but not verified.
- **Fix:** Add a test that patches the tokenizer path to a missing file and verifies the fallback works.

#### L4 — Dashboard DB Connections Created Per-Request Without Pooling
- **Score:** 2.0 / 10 (Info)
- **Location:** `src/ensemble_mcp/dashboard/api.py:35-46`
- **Description:** `_get_conn()` and `_get_write_conn()` create a new `sqlite3.Connection` for every HTTP request. While each handler closes connections in `try/finally`, this has overhead and risks leaks if any handler ever misses the `finally` block. A connection pool or per-app connection would be more robust.
- **Fix:** Consider an `aiohttp` cleanup context that manages a connection pool on `app` startup/shutdown.

---

## Code Smells

| # | Type | Location | Description | Fix |
|---|------|----------|-------------|-----|
| S1 | **Duplicate Logic** | `server.py:557-569` vs `api.py:1176-1188` | Reset table list is duplicated in two places and already diverged (M1). | Extract a shared `RESET_TABLES` constant in `config/defaults.py`. |
| S2 | **God File** | `tools/indexer.py` (1,176 lines) | Contains 4 tool implementations + file scanning + dependency analysis + snapshot logic. Too many responsibilities. | Split into `indexer/scan.py`, `indexer/query.py`, `indexer/deps.py`, `indexer/snapshot.py`. |
| S3 | **God File** | `dashboard/api.py` (1,424 lines) | Single file with 30+ HTTP handlers. Hard to navigate. | Split into route modules: `api/patterns.py`, `api/sessions.py`, `api/skills.py`, etc. |
| S4 | **Magic Numbers** | `tools/indexer.py` various | Hardcoded limits (500 files, 100KB file size, etc.) scattered through the code instead of centralized constants. | Move to `config/defaults.py`. |
| S5 | **SQL String Building** | `dashboard/api.py:1192` | `f"DELETE FROM {table}"` — while safe because `table` comes from a hardcoded list, this pattern triggers linting concerns and is fragile if the list source ever changes. | Use parameterized approach or at minimum assert table names against an allowlist. |
| S6 | **Import in Function Body** | `server.py:591` | `from .cli.banner import print_banner` is imported inside `serve()`. Minor, but inconsistent with the rest of the file's top-level imports. | Move to top-level imports. |
| S7 | **Stale Documentation** | `tools/__init__.py:1` | Docstring tool count (17) doesn't match reality (19). Documentation drift. | Update to 19 and add the two missing tools to the category list. |

---

## Code Health Score: 84 / 100

### Breakdown

| Category | Score | Max | Notes |
|----------|-------|-----|-------|
| **Readability** | 17 | 20 | Clean code style, consistent naming, good docstrings. Deducted for 2 god files and scattered magic numbers. |
| **Maintainability** | 16 | 20 | Strong patterns (envelope, error taxonomy, tool_handler decorator). Deducted for duplicated reset logic and stale docs. |
| **Test Coverage** | 16 | 20 | 85.62% overall is solid. Deducted for `server.py` at 0%, `dashboard/server.py` at 52%, `tokens.py` at 57%. |
| **Modularity** | 17 | 20 | 11 well-defined subpackages with clear responsibilities. Deducted for `indexer.py` (1,176 lines) and `api.py` (1,424 lines) being monolithic. |
| **Dependency Health** | 18 | 20 | Minimal external deps (mcp, numpy, onnxruntime, aiohttp). All local, zero LLM calls. Deducted for lack of connection pooling in dashboard. |

**Rating: Moderate** (84 — 1 point shy of "Good")

### Per-Subpackage Health

| Subpackage | Score | Key Issue |
|------------|-------|-----------|
| `config/` | 90 | Settings TOML loading at 70% coverage |
| `contracts/` | 95 | 100% coverage, clean abstractions |
| `memory/` | 85 | Embeddings download path untested (70%) |
| `security/` | 95 | 100% coverage, clean and focused |
| `state/` | 88 | Advisory lock Windows no-op, lifecycle is solid |
| `tools/` | 82 | Indexer is a god file; session overwrites created_at |
| `compress/` | 80 | Tokenizer fallback at 57% coverage |
| `dashboard/` | 75 | God file, per-request connections, server.py at 52% |
| `installer/` | 82 | Uninstall flow at 76% coverage |
| `cli/` | 95 | Small, focused, 100% coverage |
| `server.py` | 60 | 0% test coverage, TOCTOU race, stale table list |

---

## Project Structure

### Current Layout
```
src/ensemble_mcp/
  __init__.py
  __main__.py          (CLI entry point, 390 lines)
  server.py            (MCP server, 635 lines)
  cli/                 (banner, 39 lines)
  compress/            (engine + preservers + tokens, 457 lines)
  config/              (defaults + settings, 317 lines)
  contracts/           (envelope + errors, 303 lines)
  dashboard/           (api + server, 1,546 lines)
  data/                (bundled agent/skill files)
  installer/           (setup + agents + registry, 1,547 lines)
  memory/              (store + schema + embeddings + similarity, 711 lines)
  security/            (trust + redaction, 180 lines)
  state/               (lifecycle + idempotency + locks, 264 lines)
  tools/               (7 modules, 2,631 lines)
```

### Issues
1. `tools/indexer.py` at 1,176 lines is the largest single file — handles indexing, querying, dependencies, and snapshots
2. `dashboard/api.py` at 1,424 lines is a monolithic route file
3. No separation between tool definitions (schemas) and tool implementations

### Suggestions
1. Split `tools/indexer.py` into `tools/indexer/` package with `scan.py`, `query.py`, `deps.py`, `snapshot.py`
2. Split `dashboard/api.py` into `dashboard/routes/` package grouped by domain
3. Extract tool definitions (`TOOL_DEFINITIONS` list) from `server.py` into `tools/definitions.py`

---

## Architecture

### Detected: Layered Architecture with Service Pattern

```
CLI (__main__.py)
  -> Server (server.py)
       -> Tool Handlers (tools/*.py)
            -> State Management (state/*.py)
            -> Vector Store (memory/*.py)
            -> Security (security/*.py)
            -> Compression (compress/*.py)
       -> Dashboard (dashboard/*.py)  -- separate HTTP interface
       -> Installer (installer/*.py)  -- CLI-only flow
```

### Strengths
- Clear separation of concerns across 11 subpackages
- Consistent response envelope contract across all tools
- Error taxonomy with retry semantics is well-designed
- All intelligence is local (no external API dependencies)
- Idempotency pattern consistently applied to mutations

### Weaknesses
- Dashboard bypasses the tool layer and directly accesses SQLite — creates a parallel data access path that can diverge (M1 proves this)
- No formal "service layer" between tools and storage — tools directly call `store.conn.execute()`
- Tool definitions (JSON schemas) are co-located with dispatch in `server.py` (635 lines of mixed concerns)

### Recommended Improvements
1. Have the dashboard call tool functions instead of raw SQL — eliminates duplication
2. Extract a thin service/repository layer between tools and SQLite
3. Move tool definitions to a separate module

---

## Refactor Plan (Top 5 Priorities)

### Priority 1 — Fix Dashboard Reset Table Mismatch (M1)
- **Risk:** Low
- **Effort:** 5 minutes
- **Steps:**
  1. Add `"project_snapshots"` to the table list in `api.py:1176`
  2. Extract `RESET_TABLES` constant to `config/defaults.py`
  3. Import in both `server.py` and `api.py`
  4. Add a test asserting both paths reset the same tables

### Priority 2 — Fix `session_save` `created_at` Overwrite (M2)
- **Risk:** Low (schema change if adding `updated_at`)
- **Effort:** 15 minutes
- **Steps:**
  1. Remove `created_at = datetime('now'),` from UPDATE in `session.py:137`
  2. Optionally add `updated_at` column via migration in `schema.py`
  3. Add test verifying `created_at` doesn't change on update

### Priority 3 — Add `server.py` Integration Tests (L2)
- **Risk:** None (additive)
- **Effort:** 2 hours
- **Steps:**
  1. Create `tests/test_server_integration.py`
  2. Test `_dispatch_tool()` with valid/invalid tool names
  3. Test argument validation for each tool
  4. Test error wrapping for unknown tools
  5. Test `_get_store()` initialization

### Priority 4 — Split `tools/indexer.py` (S2)
- **Risk:** Medium (import paths change)
- **Effort:** 1 hour
- **Steps:**
  1. Create `tools/indexer/` package
  2. Move scanning logic to `scan.py`
  3. Move query logic to `query.py`
  4. Move dependency analysis to `deps.py`
  5. Move snapshot logic to `snapshot.py`
  6. Re-export from `__init__.py` for backward compatibility
  7. Update `server.py` imports

### Priority 5 — Split `dashboard/api.py` (S3)
- **Risk:** Medium (route registration changes)
- **Effort:** 2 hours
- **Steps:**
  1. Create `dashboard/routes/` package
  2. Group handlers by domain: `patterns.py`, `sessions.py`, `skills.py`, `indexer.py`, `system.py`
  3. Update `server.py` route registration to import from submodules
  4. Keep shared helpers in `dashboard/helpers.py`

---

## Test Results

| Metric | Value |
|--------|-------|
| **Total Tests** | 549 |
| **Passed** | 549 |
| **Failed** | 0 |
| **Errors** | 0 |
| **Duration** | 14.43s |
| **Coverage** | 85.62% (threshold: 80%) |
| **Ruff Lint** | All checks passed |

### Coverage Gaps (files below 80%)

| File | Coverage | Gap |
|------|----------|-----|
| `server.py` | **0%** | MCP server entry point completely untested |
| `dashboard/server.py` | **52%** | HTTP server startup untested |
| `compress/tokens.py` | **57%** | Tokenizer download/fallback untested |
| `state/locks.py` | **68%** | `fcntl` advisory lock path untested |
| `config/settings.py` | **70%** | TOML loading, env overrides untested |
| `memory/embeddings.py` | **70%** | ONNX model download/load untested |
| `__main__.py` | **75%** | Some CLI subcommands untested |
| `installer/setup.py` | **76%** | Uninstall flow, prompts untested |

---

## CI/CD Quality Gate

| Gate | Threshold | Actual | Result |
|------|-----------|--------|--------|
| Health Score >= 70 | 70 | **84** | PASS |
| Health Drop <= 10 | <=10 | **+2** (from 82) | PASS |
| No Critical Bugs | 0 | **0** | PASS |
| Health >= 80 | 80 | **84** | PASS |
| No Critical Issues | 0 | **0** | PASS |

### CI Status: PASS

---

## Output Summary

| Item | Value |
|------|-------|
| **Bugs Found** | 8 (0 Critical, 0 High, 4 Medium, 4 Low) |
| **Code Smells** | 7 |
| **Code Health Score** | 84 / 100 (Moderate) |
| **Trend** | Improving (+16 from scan #1, +2 from scan #2) |
| **CI Status** | PASS |
| **Report** | Generated at `reports/bug-hunter-report.md` |
| **History** | Updated at `reports/history.json` (3 entries) |

---

*Generated by Bug Hunter — read-only analysis, no source code modified.*
