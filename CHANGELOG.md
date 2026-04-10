# Changelog

All notable changes to **ensemble-mcp** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `skill_file_cache` SQLite table for mtime-based caching of skill file content and pre-computed embeddings

### Changed
- `skills_discover` now uses cached embeddings from SQLite instead of re-reading files and recomputing on every call
- `_scan_skill_files` refactored to use incremental mtime-based refresh (same pattern as `project_index`)

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

[0.1.0a3]: https://github.com/LynkByte/ensemble/releases/tag/v0.1.0a3
[0.1.0]: https://github.com/LynkByte/ensemble/releases/tag/v0.1.0
