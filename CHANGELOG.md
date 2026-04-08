# Changelog

All notable changes to **ensemble-mcp** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `metrics_backfill` MCP tool — backfill session steps with real token data from OpenCode or Claude Code session files
- `backfill` CLI command — `ensemble-mcp backfill [--session-id X] [--force] [--ai-tool opencode|claude-code]`
- `reasoning_tokens` column on the `steps` table (schema v2 migration)
- `SOURCE_BACKFILL = "backfill"` source label constant
- `watch` CLI command — file watcher daemon that monitors AI tool session files and auto-triggers backfill on changes (`ensemble-mcp watch [--debounce N] [--poll-interval N] [--ai-tool X]`)
- `watchdog>=4.0` optional dependency (`pip install ensemble-mcp[watch]`)
- Stub parsers for Cursor, GitHub Copilot, Windsurf, and Devin CLI — `detect()` functions identify installed tools; `parse_latest_session()` returns None with a logged warning explaining why token parsing is not feasible for each tool
- 7 new path constants in `config/defaults.py` for stub parser data locations
- Watcher engine (`watcher.py`) with debounced filesystem events (Claude Code via watchdog) and mtime polling (OpenCode SQLite WAL)

### Changed
- Skill workflow (`ensemble-mcp-workflow.md`) now promotes `metrics_backfill` from optional to standard post-pipeline step
- `parsers/__init__.py` expanded: `detect_ai_tool()` checks 6 tools (2 active + 4 stubs); `parse_latest_session()` dispatcher handles aliases (`github-copilot`, `github_copilot`, `codeium`)

### Test Suite
- 619 tests passing (up from 562)

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

Initial release with all 21 MCP tools across 6 implementation phases.

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
- Model pricing table (7 models: Claude Opus 4/Sonnet 4/Haiku 3.5, GPT-4o/4o-mini/5-mini, o1)
- MCP server with stdio transport and 23 tool definitions

#### Phase 2: Metrics & Token Tracking
- `metrics_start_session`, `metrics_record_step`, `metrics_end_session`
- `metrics_session_report` with ASCII table formatter
- `metrics_trend` with daily cost/token aggregation
- `metrics_compare` for side-by-side session comparison
- 3-tier token resolution: direct usage > `usage_raw` parsing (Anthropic/OpenAI) > tiktoken estimation
- MCP call tracking (`mcp_calls` table) with byte-level input/output recording
- Cost calculation with per-model pricing, cache read/write separation, pricing version tracking

#### Phase 3: Session File Parsers
- OpenCode SQLite parser (read-only mode, message-level token extraction)
- Claude Code JSONL parser (streaming deduplication by `message.id`, subagent recursion)
- Auto-detection dispatcher (detects which AI tool is running)
- Integration as fallback source in `metrics_record_step`

#### Phase 4: Auto-Installer
- Detection of 6 AI tools: OpenCode, Claude Code, GitHub Copilot, Cursor, Windsurf, Devin CLI
- Config registration with backup creation (TOML for OpenCode, JSON for others)
- `ensemble-mcp install` CLI command with `--local`, `--tools`, `--dry-run`, `--yes` flags
- Interactive confirmation flow with plan preview

#### Phase 5: CLI Dashboard
- `ensemble-mcp dashboard` CLI command
- Period summaries (today, week, month) with token and cost totals
- Per-agent cost breakdown table with share percentages
- Recent sessions table (configurable limit)
- Daily trend bar chart (configurable range)
- Terminal-width-aware rendering
- `--days`, `--limit`, `--trend-days`, `--db-path` options

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

[0.1.0a3]: https://github.com/LynkByte/ensemble/releases/tag/v0.1.0a3
[0.1.0]: https://github.com/LynkByte/ensemble/releases/tag/v0.1.0
