# Changelog

All notable changes to **ensemble-mcp** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0a7] - 2026-04-13

### Added
- **Context Compression Tool** — new `context_compress` MCP tool (#16) that compresses verbose natural language text into terse, token-efficient form while preserving all technical content (code blocks, URLs, paths, headings, tables). Rule-based, zero LLM calls, ~10-23% token savings on verbose prose
  - New `compress/` subpackage with engine, preservers, and token counter
  - Atomic tokenizer download with integrity protection
  - Thread-safe initialization
- **Eval/Benchmark Framework** — comprehensive `evals/` directory with benchmarks for all 16 MCP tools
  - `bench_compress.py` — compression ratio, latency, preservation accuracy (synthetic + real docs)
  - `bench_patterns.py` — pattern search/store/prune latency and recall
  - `bench_drift.py` — drift detection accuracy and latency
  - `bench_routing.py` — model routing correctness (31 rule matrix, 100% accuracy)
  - `bench_session.py` — session save/load roundtrip, version conflicts
  - `bench_indexer.py` — project indexing, querying, dependency analysis
  - `bench_skills.py` — skill discovery, suggestion, generation
  - `bench_health_reset.py` — health check and data reset
  - `evals/runner.py` — standalone runner with markdown table output
  - `evals/cli.py` — generic CLI: `python evals/cli.py run <tool> [--key value]`
  - `evals/corpus.py` — real project data loader (docs/ and src/ as test corpus)
  - `evals/helpers.py` — shared utilities (percentile, async runner, DB setup)
  - Run with `python evals/runner.py`, `python -m pytest evals/ -v`, or `python evals/cli.py run <tool>`

### Fixed
- **Tokenizer padding/truncation bug** — `count_tokens()` was always returning 128 due to MiniLM tokenizer padding and truncation settings, causing compression to report 0% savings. Fixed by disabling padding and truncation in the token counter.

### Test Suite
- 464 unit tests + 27 eval benchmarks passing

## [0.1.0a6] - 2026-04-10

### Added
- **Web Dashboard v1** — local-only browser interface at `localhost:8787` for visualizing patterns, skills, projects, drift history, and sessions
  - `ensemble-mcp web` CLI command with `--port` and `--no-open` flags
  - 11 JSON API endpoints returning standard `{ok, data, error, meta}` envelope
  - Single-page app using Alpine.js, Chart.js (CDN), and Tailwind CSS (CDN)
  - 5 dashboard pages: Overview, Patterns, Skills, Projects, Drift, Sessions
  - Drift history chart with trend visualization
  - Read-only SQLite connection (WAL mode) — does not block MCP server writes
- `drift_history` SQLite table for persisting drift check results over time
- `drift_check` tool now accepts optional `project` parameter for history tracking
- `pytest-aiohttp` added to dev dependencies for dashboard API testing
- SQLite schema version bumped from 5 to 6

### Test Suite
- 416 tests passing (24 new: 18 dashboard API + 6 drift history)

## [0.1.0a5] - 2026-04-10

### Added
- `skill_file_cache` SQLite table for mtime-based caching of skill file content and pre-computed embeddings

### Changed
- `skills_discover` now uses cached embeddings from SQLite instead of re-reading files and recomputing on every call
- `_scan_skill_files` refactored to use incremental mtime-based refresh (same pattern as `project_index`)
- Removed metrics/cost/token tracking subsystem — stripped out the metrics backfill tool, file watcher daemon, and stub parsers
- Synced all documentation with current codebase state
- Rewrote FUTURE-PLANS to focus on actual data sources

## [0.1.0a3] - 2026-04-07

### Fixed
- **OpenCode config format**: Installer now generates correct JSON config (`config.json` with `$schema`) instead of TOML (`config.toml`), using `{"type": "local", "command": ["uvx", "ensemble-mcp"]}` entry format under the `mcp` section
- **Tool-specific agent/skill directories**: Agent and skill files are now placed in the correct tool-specific locations instead of generic `.agents/` and `.ai/skills/` paths

### Added
- `SkillFormat` enum (`FLAT` / `DIRECTORY`) to support OpenCode's `<name>/SKILL.md` directory layout vs flat `.md` files for other tools
- Per-tool `global_agents_dir`, `local_agents_dir`, `global_skills_dir`, `local_skills_dir`, `skill_format` fields on `ToolDefinition`
- `ensemble-mcp add-agents` CLI command — copy bundled agent files without MCP registration (defaults to global scope)
- `ensemble-mcp add-skills` CLI command — copy bundled skill files without MCP registration (defaults to local scope)
- Both commands support `--tools`, `--local`/`--global`, `--dry-run`, `--yes` flags
- Both commands work without requiring the AI tool to be installed
- Uninstall now scans tool-specific directories plus legacy paths (`.agents/`, `.ai/skills/`) for backwards compatibility

### Changed
- `discover_agents()` and `discover_skills()` now accept a tool list and scope parameter with deduplication across tools
- Updated all documentation (README, SETUP, UNINSTALL, EXAMPLE-SCENARIO, DESIGN-SPEC) to reflect correct OpenCode format and tool-specific paths

### Tool-specific paths

| Tool | Agent Dir (local) | Skill Dir (local) | Skill Format |
|------|-------------------|-------------------|--------------|
| OpenCode | `.opencode/agents/` | `.opencode/skills/` | directory (`<name>/SKILL.md`) |
| Claude Code | — | `.claude/skills/` | flat |
| Cursor | — | `.cursor/rules/` | flat |
| Devin | — | `.devin/` | flat |

### Test Suite
- 529 tests passing (up from 505)

## [0.1.0] - 2026-04-06

Initial release with all 15 MCP tools across 3 implementation phases.

### Added

#### Phase 1.0 + 1: Contract Foundation & MCP Core
- Response envelope (`{ok, data, error, meta}`) and `@tool_handler` decorator with auto-timing
- Error taxonomy: 16 error codes across 6 categories (VALIDATION, NOT_FOUND, CONFLICT, TIMEOUT, IO, INTERNAL) with retry guidance
- Session/step lifecycle state machines with valid transition enforcement
- Idempotency key support for all mutating tools (24h TTL, SQLite-backed)
- SQLite database with WAL mode, 12 tables, 20+ indexes, schema versioning
- Secret redaction (8 regex patterns: AWS keys, Bearer tokens, API keys, GitHub tokens, etc.)
- Trust boundary enforcement and input validation helpers
- File-based advisory locks (Unix)
- ONNX MiniLM-L6-v2 embeddings (384-dim, lazy-download, ~5ms/embed)
- Cosine similarity search with brute-force + pairwise matrix
- SQLite-backed vector store with pattern CRUD
- **Pattern tools**: `patterns_search`, `patterns_store`, `patterns_prune`
- **Drift tool**: `drift_check` with 0-1 score, suspicious file flagging, verdict classification
- **Routing tool**: `model_recommend` with 7x4 agent/classification matrix
- **Skills tools**: `skills_discover` (multi-tool skill scanning), `skills_suggest` (pattern clustering), `skills_generate` (accept/dismiss/defer)
- **Session tools**: `session_save` (optimistic versioning), `session_load`
- **Indexer tools**: `project_index` (incremental mtime-based), `project_query`, `project_dependencies`
- **Utility tools**: `health`, `reset`
- Layered configuration: defaults > global TOML > project TOML > env vars
- MCP server with stdio transport and 15 tool definitions

#### Phase 4: Auto-Installer
- Detection of 6 AI tools: OpenCode, Claude Code, GitHub Copilot, Cursor, Windsurf, Devin CLI
- Config registration with backup creation (TOML for OpenCode, JSON for others)
- `ensemble-mcp install` CLI command with `--local`, `--tools`, `--dry-run`, `--yes` flags
- Interactive confirmation flow with plan preview

#### Phase 6: Package & Publish
- Full PyPI metadata: license, classifiers, keywords, URLs, typed marker
- MIT license
- `py.typed` marker for mypy consumers
- Comprehensive README.md with install instructions, config examples, tool reference
- Multi-stage Dockerfile with non-root user, OCI labels
- `.dockerignore` for lean container builds
- This changelog

### Test Suite
- 451 tests across 23 test files
- Mock embedding model (deterministic hash-based 384-dim vectors, no ONNX download)
- Shared fixtures: `tmp_db`, `test_conn`, `test_store`, `MockEmbeddingModel`
- Full lint (ruff) and format compliance

[0.1.0a6]: https://github.com/LynkByte/ensemble/releases/tag/v0.1.0a6
[0.1.0a5]: https://github.com/LynkByte/ensemble/releases/tag/v0.1.0a5
[0.1.0a3]: https://github.com/LynkByte/ensemble/releases/tag/v0.1.0a3
[0.1.0]: https://github.com/LynkByte/ensemble/releases/tag/v0.1.0
