# Web Dashboard

`ensemble-mcp` includes a local web dashboard for browsing patterns, sessions, drift history, indexed projects, skills, and server settings.

## Starting the Dashboard

```bash
# Default: port 8787, auto-opens browser
ensemble-mcp web

# Custom port
ensemble-mcp web --port 9000

# Don't auto-open browser
ensemble-mcp web --no-open

# Specify reports directory
ensemble-mcp web --reports-dir ./reports
```

The dashboard binds to `127.0.0.1` only — it is accessible only from your local machine. No authentication is required.

## Dashboard URL

```
http://127.0.0.1:8787
```

The startup output shows the URL, database path, and version:

```
  ensemble-mcp dashboard v0.1.0b7
  URL: http://127.0.0.1:8787
  Database: ~/.cache/ensemble-mcp/data.db
  Press Ctrl+C to stop
```

## Architecture

The dashboard is built with:
- **Backend:** [aiohttp](https://docs.aiohttp.org/) HTTP server
- **Frontend:** [Alpine.js](https://alpinejs.dev/) single-page application
- **Static files:** `index.html`, `app.js`, `style.css`

The dashboard opens its own SQLite connections (separate from the MCP server) to avoid blocking. Read endpoints use `PRAGMA query_only = ON` for safety.

## Dashboard Pages

### Summary

The landing page shows aggregate statistics:
- Pattern count
- Pending skill suggestions
- Active (tracked) skills
- Indexed project count
- Drift checks in the last 30 days
- Session count
- Recent MCP call activity (last 20 calls with tool name, timestamp, duration)

### Patterns

Browse, search, edit, and delete stored patterns:
- Paginated list with name, context, approach, outcome, project, match count
- Edit pattern fields (name, context, approach, outcome)
- Delete individual patterns
- Prune stale patterns (zero matches, older than configurable age)

### Skills

View skill suggestions and tracked skill usage:
- Pending suggestions with accept/dismiss/defer actions
- Tracked skills with match counts and last-matched timestamps
- Stale skill detection (configurable threshold in days)

### Projects

Browse indexed projects:
- File counts, language breakdown, role distribution
- Export counts by kind (function, class, etc.)
- Project health: index staleness, missing files on disk
- Re-index a project from the dashboard
- Delete a project's index

### Drift

Drift check history:
- Task descriptions, changed files, scores, verdicts
- Filter by project, date range
- Score visualization (aligned / minor / significant)

### Sessions

Pipeline session checkpoints:
- Session list with status, version, timestamps
- Detailed view with full state JSON
- Original request, task classification, project

### Settings

View and edit server configuration:
- Current values with source labels (default, global_config, project_config, env)
- Edit form with field types, descriptions, and defaults
- Saves to `~/.config/ensemble-mcp/config.toml`

### Health

Server health information:
- Version, server name
- Database size
- Pattern, session, and project counts

## JSON API Endpoints

The dashboard exposes a REST API under `/api/`. All responses use the standard envelope format:

```json
{
  "ok": true,
  "data": { ... },
  "error": null,
  "meta": {
    "duration_ms": 5,
    "source": "dashboard",
    "confidence": "exact"
  }
}
```

### Read Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/summary` | Aggregate counts and recent activity |
| GET | `/api/patterns` | Paginated pattern list (`?limit=&offset=&project=`) |
| GET | `/api/patterns/{id}` | Single pattern detail |
| GET | `/api/skills` | Skill suggestions and tracked skills |
| GET | `/api/skills/stale` | Skills not matched within threshold |
| GET | `/api/projects` | Indexed projects with file counts |
| GET | `/api/projects/{path}` | Project detail (languages, roles, exports) |
| GET | `/api/projects/{path}/health` | Index staleness and missing files |
| GET | `/api/drift` | Drift check history (`?project=&from=&to=&limit=`) |
| GET | `/api/sessions` | Paginated session list |
| GET | `/api/sessions/{id}` | Session detail with full state |
| GET | `/api/health` | Server health and counts |
| GET | `/api/settings` | Current config with source map |
| GET | `/api/settings/schema` | Field names, types, defaults for the settings form |

### Mutation Endpoints

| Method | Path | Description |
|--------|------|-------------|
| DELETE | `/api/patterns/{id}` | Delete a pattern |
| PUT | `/api/patterns/{id}` | Edit pattern fields |
| POST | `/api/patterns/prune` | Prune stale patterns |
| POST | `/api/skills/suggestions/{id}/action` | Accept/dismiss/defer a suggestion |
| DELETE | `/api/skills/tracked/{id}` | Remove a tracked skill |
| PUT | `/api/settings` | Update global config |
| POST | `/api/reset` | Reset all data (`{"confirm": true}` required) |
| POST | `/api/projects/{path}/reindex` | Force re-index a project |
| DELETE | `/api/projects/{path}` | Delete a project's index |

### Report Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/reports/markdown` | Bug Hunter report in markdown |
| GET | `/api/reports/history` | Report history |
| GET | `/api/reports/summary` | Report summary |

## Port Conflicts

If port 8787 is already in use, the dashboard exits with a suggestion:

```
Error: Port 8787 is already in use.
Try: ensemble-mcp web --port 8788
```

## Database Independence

The dashboard creates its own SQLite connections, so it can run independently from the MCP server. It also calls `ensure_schema()` at startup, so the dashboard works even if the MCP server has never run.

## Next Steps

- [Tool Reference](./tool-reference.md) — tools that generate the data shown in the dashboard
- [Configuration](./configuration.md) — settings you can change in the dashboard
- [Troubleshooting](./troubleshooting.md) — dashboard issues
