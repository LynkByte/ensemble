# Troubleshooting

Common issues and solutions for `ensemble-mcp`.

## Installation Problems

### `pip install` fails with dependency conflicts

**Symptoms:** Dependency resolver errors, version conflicts with `numpy`, `onnxruntime`, or `mcp`.

**Solutions:**
- Use a virtual environment: `python -m venv .venv && source .venv/bin/activate`
- Use `uvx` to run without installing: `uvx ensemble-mcp`
- Use `pipx` for isolated installation: `pipx install ensemble-mcp`
- Ensure Python 3.11+: `python --version`

### `ensemble-mcp: command not found`

**Solutions:**
- Check pip installed to your current Python: `pip show ensemble-mcp`
- Ensure your Python scripts directory is in `$PATH`
- Try running as a module: `python -m ensemble_mcp`

---

## ONNX Model Download Issues

### Model download fails or is slow

**Symptoms:** First run hangs or fails with network errors. The model is ~22 MB from Hugging Face.

**Model URLs:**
- `https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/onnx/model.onnx`
- `https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/tokenizer.json`

**Solutions:**
1. Check network connectivity to `huggingface.co`
2. Manually download and place files:
   ```bash
   mkdir -p ~/.cache/ensemble-mcp/models
   curl -L -o ~/.cache/ensemble-mcp/models/model.onnx \
     "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/onnx/model.onnx"
   curl -L -o ~/.cache/ensemble-mcp/models/tokenizer.json \
     "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/tokenizer.json"
   ```
3. If behind a proxy, set `HTTP_PROXY` / `HTTPS_PROXY` environment variables

### ONNX Runtime errors

**Symptoms:** `onnxruntime` import errors or inference failures.

**Solutions:**
- Ensure you have a compatible version: `pip install 'onnxruntime>=1.17'`
- On Apple Silicon: `pip install onnxruntime` (not `onnxruntime-gpu`)
- On Linux without AVX: use `onnxruntime` (CPU version), not GPU variant

---

## MCP Registration Failures

### `ensemble-mcp install` finds no tools

**Symptoms:** "Nothing to do — ensemble-mcp is already registered in all detected AI tools."

**Solutions:**
- Verify your AI tool is installed and has created its config directory (e.g., `~/.cursor/`, `~/.vscode/`)
- Force registration for a specific tool: `ensemble-mcp install --tools cursor`
- Use `--local` to create project-local registration even without global tool detection
- Check supported tools: `opencode`, `claude_code`, `copilot`, `cursor`, `windsurf`, `devin`

### Config file backup/permission errors

**Symptoms:** Permission denied when writing to AI tool config files.

**Solutions:**
- Check file permissions: `ls -la ~/.cursor/mcp.json`
- Ensure the user owns the config directory
- Use `--dry-run` to see the plan without writing

### Unknown tool name error

**Symptoms:** `Unknown tool(s): <name>`

**Solutions:**
- Use the exact tool names: `opencode`, `claude_code`, `copilot`, `cursor`, `windsurf`, `devin`
- Note: Claude Code uses `claude_code` (with underscore), not `claude-code`

---

## SQLite Lock Errors

### Database is locked

**Symptoms:** `sqlite3.OperationalError: database is locked`

**Cause:** Multiple processes writing to the same database simultaneously. The database uses WAL (Write-Ahead Logging) mode for better concurrency, but heavy concurrent writes can still cause contention.

**Solutions:**
1. Ensure only one MCP server instance is running per database
2. The dashboard opens separate connections — this is normal and handled correctly
3. If the database is corrupted, reset it:
   ```bash
   rm ~/.cache/ensemble-mcp/data.db
   # The database is recreated automatically on next start
   ```

### Database file not found

**Solutions:**
- The database is created automatically on first run
- Check the configured path: `ENSEMBLE_MCP_DB_PATH` env var or config file
- Default location: `~/.cache/ensemble-mcp/data.db`

---

## Dashboard Issues

### Dashboard won't start

**Symptoms:** Port already in use error.

```
Error: Port 8787 is already in use.
Try: ensemble-mcp web --port 8788
```

**Solutions:**
- Use a different port: `ensemble-mcp web --port 9000`
- Find what's using the port: `lsof -i :8787` (macOS/Linux)
- Kill the existing process or stop the other dashboard instance

### Dashboard shows no data

**Solutions:**
- The MCP server may not have been used yet — tools must be called to generate data
- Check the database path: the dashboard uses the same `~/.cache/ensemble-mcp/data.db`
- Run a health check: visit `http://127.0.0.1:8787/api/health`

### Browser doesn't open

**Solutions:**
- The dashboard runs headless in some environments (SSH, containers)
- Manually navigate to `http://127.0.0.1:8787`
- Use `--no-open` and open manually to avoid the startup delay

---

## Tool Errors

### `VALIDATION_*` errors

These indicate bad input — never retry automatically.

| Error Code | Meaning | Fix |
|------------|---------|-----|
| `VALIDATION_MISSING_FIELD` | Required parameter not provided | Check tool documentation for required params |
| `VALIDATION_INVALID_VALUE` | Parameter value is invalid | Check type, range, or allowed values |
| `VALIDATION_INVALID_TYPE` | Wrong parameter type | Check expected types in tool reference |
| `VALIDATION_CONSTRAINT` | Business rule violation | e.g., `reset` requires `confirm=true` |

### `NOT_FOUND_*` errors

Resource not found — never retry.

| Error Code | Fix |
|------------|-----|
| `NOT_FOUND_SESSION` | Check session_id exists |
| `NOT_FOUND_PATTERN` | Pattern may have been pruned or deleted |
| `NOT_FOUND_PROJECT` | Run `project_index` first, or check path |
| `NOT_FOUND_SKILL_SUGGESTION` | Suggestion ID doesn't exist |

### `CONFLICT_*` errors

Concurrency conflicts — retry after refreshing state.

| Error Code | Meaning | Fix |
|------------|---------|-----|
| `CONFLICT_VERSION_MISMATCH` | Optimistic lock failure | Re-load the session, get current version |
| `CONFLICT_ALREADY_RESOLVED` | Skill suggestion already accepted/dismissed | No action needed |

### `IO_*` errors

Transient I/O errors — retry with backoff.

| Error Code | Fix |
|------------|-----|
| `IO_DATABASE` | Check SQLite file permissions and disk space |
| `IO_FILESYSTEM` | Check directory permissions |
| `IO_MODEL_DOWNLOAD` | Check network connectivity |

---

## Resetting Everything

### Reset database (keep model)

```bash
# Via MCP tool (from AI agent)
# Call the `reset` tool with confirm=true

# Via dashboard
# POST /api/reset with {"confirm": true}

# Via filesystem
rm ~/.cache/ensemble-mcp/data.db
```

### Full clean reset

```bash
# Remove all cached data and config
ensemble-mcp uninstall --clean-data --remove-agents --yes

# Or manually
rm -rf ~/.cache/ensemble-mcp
rm -rf ~/.config/ensemble-mcp
```

### Re-download model

```bash
rm -rf ~/.cache/ensemble-mcp/models
# Model is re-downloaded on next server start
```

---

## Debugging

### Check server health

```bash
# Via dashboard API
curl http://127.0.0.1:8787/api/health
```

### Inspect database

```bash
sqlite3 ~/.cache/ensemble-mcp/data.db ".tables"
sqlite3 ~/.cache/ensemble-mcp/data.db "SELECT COUNT(*) FROM patterns"
```

### Logging

The server uses Python's `logging` module, hardcoded to INFO level. There is no `ENSEMBLE_MCP_LOG_LEVEL` environment variable — the `Settings` dataclass does not have a `log_level` field, so it would be silently ignored.

Supported `ENSEMBLE_MCP_*` environment variables map directly to `Settings` fields:

```bash
# Override storage paths
ENSEMBLE_MCP_CACHE_DIR=~/.my-cache/ensemble-mcp ensemble-mcp
ENSEMBLE_MCP_DB_PATH=/tmp/ensemble-debug.db ensemble-mcp

# Tune pattern matching
ENSEMBLE_MCP_MAX_PATTERNS=2000 ensemble-mcp
ENSEMBLE_MCP_DEFAULT_TOP_K=10 ensemble-mcp
ENSEMBLE_MCP_DEFAULT_MIN_SCORE=0.5 ensemble-mcp

# Adjust drift thresholds
ENSEMBLE_MCP_DRIFT_THRESHOLD_ALIGNED=0.15 ensemble-mcp
ENSEMBLE_MCP_DRIFT_THRESHOLD_MINOR=0.4 ensemble-mcp
```

### Check config sources

```bash
# Via dashboard API — shows where each setting came from
curl http://127.0.0.1:8787/api/settings | python -m json.tool
```

## Next Steps

- [Configuration](./configuration.md) — adjust settings that may fix issues
- [CLI Reference](./cli-reference.md) — command-line options for debugging
- [Tool Reference](./tool-reference.md) — understand tool error responses
