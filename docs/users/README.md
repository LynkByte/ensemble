# ensemble-mcp User Documentation

**ensemble-mcp** is a Python MCP server (v0.1.0b4) providing vector memory, drift detection, model routing, skills discovery, session management, codebase indexing, context compression, and a local web dashboard for AI-assisted development pipelines.

All processing is **100% local** — ONNX Runtime embeddings (~5ms), numpy cosine similarity, SQLite storage. Zero LLM or cloud API calls.

---

## For Users

Get started with installing and configuring ensemble-mcp for your AI coding tool.

| Guide | Description |
|-------|-------------|
| [Getting Started](./getting-started.md) | 5-minute quick start — install, register, verify |
| [Installation](./installation.md) | Detailed install: pip, source, Docker, system requirements |
| [CLI Reference](./cli-reference.md) | All commands: `serve`, `web`, `install`, `uninstall`, `add-agents`, `add-skills` |
| [Configuration](./configuration.md) | Config files, layering, all settings with defaults |
| [MCP Client Setup](./mcp-clients.md) | Per-tool registration: OpenCode, Claude Code, Copilot, Cursor, Windsurf, Devin CLI |
| [Web Dashboard](./web-dashboard.md) | Dashboard usage, features, and JSON API endpoints |
| [Troubleshooting](./troubleshooting.md) | Common issues, error codes, and fixes |

## For Developers

Integrate ensemble-mcp into AI agent pipelines or contribute to the project.

| Guide | Description |
|-------|-------------|
| [Tool Reference](./tool-reference.md) | All 19 MCP tools: parameters, types, response schemas, examples |
| [Integration Guide](./integration-guide.md) | Pipeline patterns: pre/mid/post pipeline tool usage |
| [Architecture Overview](./architecture-overview.md) | System design, subpackages, data flow, extension points |

---

## Quick Links

- **Install:** `pip install ensemble-mcp`
- **Register:** `ensemble-mcp install`
- **Dashboard:** `ensemble-mcp web`
- **GitHub:** [LynkByte/ensemble](https://github.com/LynkByte/ensemble)
- **Issues:** [GitHub Issues](https://github.com/LynkByte/ensemble/issues)
- **Changelog:** [CHANGELOG.md](https://github.com/LynkByte/ensemble/blob/main/CHANGELOG.md)

## 19 MCP Tools at a Glance

| Category | Tools | Purpose |
|----------|-------|---------|
| **Patterns** | `patterns_search`, `patterns_store`, `patterns_prune` | Semantic memory of past solutions |
| **Drift** | `drift_check` | Detect scope drift during implementation |
| **Routing** | `model_recommend` | Choose model tier per agent and task |
| **Skills** | `skills_discover`, `skills_suggest`, `skills_generate` | Find, suggest, and create reusable skills |
| **Session** | `session_save`, `session_load`, `session_search` | Pipeline checkpoints with resume support |
| **Indexer** | `project_index`, `project_query`, `project_dependencies`, `project_snapshot` | Codebase intelligence |
| **Compress** | `context_compress`, `context_prepare` | Token-efficient context optimization |
| **Utility** | `health`, `reset` | Server status and data management |
