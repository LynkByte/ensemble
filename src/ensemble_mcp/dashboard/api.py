"""JSON API endpoints for the ensemble-mcp dashboard.

Provides both read-only (GET) and mutation (POST/PUT/DELETE) endpoints.
All responses use the standard ``{ok, data, error, meta}`` envelope.
Each handler opens its own SQLite connection so the MCP server is
never blocked.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import logging
import re
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from aiohttp import web

from ..config.defaults import (
    DB_PATH,
    GLOBAL_CONFIG_PATH,
    SERVER_NAME,
    SERVER_VERSION,
    VALID_PATTERN_CATEGORIES,
)
from ..config.settings import Settings, _load_toml, load_settings
from ..security.redaction import redact
from ..state.locks import get_connection

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────


def _get_conn(request: web.Request) -> sqlite3.Connection:
    """Open a read-only WAL connection to the dashboard DB."""
    db_path: Path = request.app["db_path"]
    conn = get_connection(db_path)
    conn.execute("PRAGMA query_only = ON")
    return conn


def _get_write_conn(request: web.Request) -> sqlite3.Connection:
    """Open a writable WAL connection to the dashboard DB."""
    db_path: Path = request.app["db_path"]
    return get_connection(db_path)


def _envelope(data: dict[str, Any], *, duration_ms: int = 0) -> dict[str, Any]:
    """Wrap data in the standard response envelope."""
    return {
        "ok": True,
        "data": data,
        "error": None,
        "meta": {
            "duration_ms": duration_ms,
            "source": "dashboard",
            "confidence": "exact",
        },
    }


def _error_envelope(message: str, *, code: str = "NOT_FOUND", status: int = 404) -> web.Response:
    """Return a JSON error response."""
    body = {
        "ok": False,
        "data": None,
        "error": {"code": code, "message": message, "retryable": False, "details": {}},
        "meta": {"duration_ms": 0, "source": "dashboard", "confidence": "exact"},
    }
    return web.json_response(body, status=status)


def _json_ok(data: dict[str, Any], *, duration_ms: int = 0) -> web.Response:
    """Return a successful JSON response."""
    return web.json_response(_envelope(data, duration_ms=duration_ms))


def _json_mutated(data: dict[str, Any], *, duration_ms: int = 0, status: int = 200) -> web.Response:
    """Return a mutation success response with optional status code."""
    return web.json_response(_envelope(data, duration_ms=duration_ms), status=status)


# Keep in sync with _find_missing_files() which inlines these as
# startswith() literals for CodeQL path-injection sanitiser recognition.
_ALLOWED_ROOTS = ("/home", "/opt", "/workspace", "/var/www", "/srv")


def _is_path_under_allowed_root(resolved: Path) -> bool:
    """Check if a resolved path is under an allowed root directory.

    Guards against path-traversal attacks by ensuring the resolved path
    is under a known safe root directory.
    """
    path_str = str(resolved)
    for root in _ALLOWED_ROOTS:
        root_resolved = str(Path(root).resolve())
        if path_str == root_resolved or path_str.startswith(root_resolved + "/"):
            return True
    return False


async def _parse_json_body(request: web.Request) -> dict[str, Any]:
    """Parse and return JSON body from a request.

    Raises:
        web.HTTPBadRequest: If the body is missing or invalid JSON.
    """
    try:
        body = await request.json()
    except Exception as exc:
        raise web.HTTPBadRequest(
            text=json.dumps(
                {
                    "ok": False,
                    "data": None,
                    "error": {
                        "code": "VALIDATION_INVALID_VALUE",
                        "message": "Request body must be valid JSON",
                        "retryable": False,
                        "details": {},
                    },
                    "meta": {"duration_ms": 0, "source": "dashboard", "confidence": "exact"},
                }
            ),
            content_type="application/json",
        ) from exc
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(
            text=json.dumps(
                {
                    "ok": False,
                    "data": None,
                    "error": {
                        "code": "VALIDATION_INVALID_TYPE",
                        "message": "Request body must be a JSON object",
                        "retryable": False,
                        "details": {},
                    },
                    "meta": {"duration_ms": 0, "source": "dashboard", "confidence": "exact"},
                }
            ),
            content_type="application/json",
        )
    return body


def _parse_int(value: str | None, default: int) -> int:
    """Parse a query param as int, falling back to default."""
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _settings_field_schema() -> list[dict[str, Any]]:
    """Return field names, types, defaults, and descriptions for the Settings form."""
    descriptions: dict[str, str] = {
        "cache_dir": "Directory for cache data (DB and models)",
        "db_path": "Path to the SQLite database file",
        "model_dir": "Directory for ONNX embedding model files",
        "max_patterns": "Maximum number of stored patterns",
        "default_top_k": "Default number of results for pattern search",
        "default_min_score": "Minimum similarity score for pattern matches",
        "default_prune_max_age_days": "Default max age (days) for pruning stale patterns",
        "drift_threshold_aligned": "Score threshold below which drift is 'aligned'",
        "drift_threshold_minor": "Score threshold below which drift is 'minor'",
        "cluster_similarity_threshold": "Cosine similarity threshold for skill clustering",
        "default_min_cluster_size": "Minimum cluster size for skill suggestions",
        "default_stale_threshold_days": "Days before a skill is considered stale",
        "idempotency_key_ttl_hours": "Hours before idempotency keys expire",
    }
    fields: list[dict[str, Any]] = []
    for f in dataclasses.fields(Settings):
        if f.name == "source_map":
            continue
        ftype = f.type
        # Resolve type strings to display-friendly names
        if ftype == "Path" or ftype is Path:
            type_name = "path"
        elif ftype == "int" or ftype is int:
            type_name = "integer"
        elif ftype == "float" or ftype is float:
            type_name = "float"
        else:
            type_name = "string"
        default_val = f.default if f.default is not dataclasses.MISSING else None
        fields.append(
            {
                "name": f.name,
                "type": type_name,
                "default": str(default_val) if default_val is not None else None,
                "description": descriptions.get(f.name, ""),
            }
        )
    return fields


def _write_toml(path: Path, data: dict[str, Any]) -> None:
    """Write a flat dict as a TOML file (simple scalar values only)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["# ensemble-mcp configuration", "# Auto-generated by dashboard", ""]
    for key, value in sorted(data.items()):
        if isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key} = {value}")
        elif isinstance(value, str):
            # Escape backslashes and quotes for TOML
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
        else:
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
    lines.append("")  # trailing newline
    path.write_text("\n".join(lines), encoding="utf-8")


# ── Route registration ────────────────────────────────────────────


def register_api_routes(app: web.Application) -> None:
    """Add all /api/* routes to the application."""
    # Read endpoints
    app.router.add_get("/api/summary", handle_summary)
    app.router.add_get("/api/patterns", handle_patterns)
    app.router.add_get("/api/patterns/{id}", handle_pattern_detail)
    app.router.add_get("/api/skills", handle_skills)
    app.router.add_get("/api/skills/stale", handle_skills_stale)
    app.router.add_get("/api/projects", handle_projects)
    app.router.add_get("/api/projects/{path:.+}/health", handle_project_health)
    app.router.add_get("/api/projects/{path:.+}", handle_project_detail)
    app.router.add_get("/api/drift", handle_drift)
    app.router.add_get("/api/sessions", handle_sessions)
    app.router.add_get("/api/sessions/{id}", handle_session_detail)
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/settings", handle_settings_get)
    app.router.add_get("/api/settings/schema", handle_settings_schema)

    # Mutation endpoints
    app.router.add_delete("/api/patterns/{id}", handle_pattern_delete)
    app.router.add_put("/api/patterns/{id}", handle_pattern_edit)
    app.router.add_post("/api/patterns/prune", handle_pattern_prune)
    app.router.add_post("/api/skills/suggestions/{id}/action", handle_skill_action)
    app.router.add_delete("/api/skills/tracked/{id}", handle_skill_delete)
    app.router.add_put("/api/settings", handle_settings_update)
    app.router.add_post("/api/reset", handle_reset)
    app.router.add_post("/api/projects/{path:.+}/reindex", handle_project_reindex)
    app.router.add_delete("/api/projects/{path:.+}", handle_project_delete)

    # Reports endpoints (filesystem-backed, read-only)
    app.router.add_get("/api/reports/markdown", handle_reports_markdown)
    app.router.add_get("/api/reports/history", handle_reports_history)
    app.router.add_get("/api/reports/summary", handle_reports_summary)
    app.router.add_get("/api/reports/full", handle_reports_full)


# ── Endpoint handlers ─────────────────────────────────────────────


async def handle_summary(request: web.Request) -> web.Response:
    """Aggregate counts and recent activity."""
    start = time.monotonic()
    project = request.query.get("project")
    conn = _get_conn(request)
    try:
        # Pattern count
        if project:
            pattern_count = conn.execute(
                "SELECT COUNT(*) FROM patterns WHERE project = ? OR project IS NULL", (project,)
            ).fetchone()[0]
        else:
            pattern_count = conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]

        # Skill suggestion counts
        if project:
            pending_skills = conn.execute(
                "SELECT COUNT(*) FROM skill_suggestions WHERE status = 'pending' AND project = ?",
                (project,),
            ).fetchone()[0]
            active_skills = conn.execute(
                "SELECT COUNT(*) FROM skill_usage_tracking WHERE project = ?", (project,)
            ).fetchone()[0]
        else:
            pending_skills = conn.execute(
                "SELECT COUNT(*) FROM skill_suggestions WHERE status = 'pending'"
            ).fetchone()[0]
            active_skills = conn.execute("SELECT COUNT(*) FROM skill_usage_tracking").fetchone()[0]

        # Project count
        project_count = conn.execute(
            "SELECT COUNT(DISTINCT project_path) FROM project_files"
        ).fetchone()[0]

        # Drift check count (last 30 days)
        if project:
            drift_count = conn.execute(
                "SELECT COUNT(*) FROM drift_history "
                "WHERE created_at >= datetime('now', '-30 days') AND project = ?",
                (project,),
            ).fetchone()[0]
        else:
            drift_count = conn.execute(
                "SELECT COUNT(*) FROM drift_history WHERE created_at >= datetime('now', '-30 days')"
            ).fetchone()[0]

        # Session count
        session_count = conn.execute("SELECT COUNT(*) FROM session_checkpoints").fetchone()[0]

        # Recent activity (last 20 MCP calls)
        recent_rows = conn.execute(
            "SELECT tool_name, called_at, duration_ms FROM mcp_calls "
            "ORDER BY called_at DESC LIMIT 20"
        ).fetchall()
        recent_activity = [
            {
                "tool_name": r["tool_name"],
                "called_at": r["called_at"],
                "duration_ms": r["duration_ms"],
            }
            for r in recent_rows
        ]

        # Session counts by status (single query instead of two)
        sessions_running = 0
        sessions_completed = 0
        for row in conn.execute(
            "SELECT status, COUNT(*) as cnt FROM session_checkpoints "
            "WHERE status IN ('running', 'completed') GROUP BY status"
        ).fetchall():
            if row["status"] == "running":
                sessions_running = row["cnt"]
            elif row["status"] == "completed":
                sessions_completed = row["cnt"]

        # MCP call counts — uses called_at column (TEXT, datetime format)
        calls_today = conn.execute(
            "SELECT COUNT(*) FROM mcp_calls WHERE called_at >= datetime('now', '-24 hours')"
        ).fetchone()[0]

        # Calls by hour (last 24h): single GROUP BY query, fill 24-slot array
        # Index 0 = 23h ago (oldest), index 23 = current hour (newest)
        calls_by_hour: list[int] = [0] * 24
        now_hour = int(conn.execute("SELECT strftime('%H', 'now')").fetchone()[0])
        for row in conn.execute(
            "SELECT strftime('%H', called_at) as hour, COUNT(*) as cnt "
            "FROM mcp_calls WHERE called_at >= datetime('now', '-24 hours') "
            "GROUP BY hour"
        ).fetchall():
            hour_idx = int(row["hour"])
            hours_ago = (now_hour - hour_idx + 24) % 24
            calls_by_hour[23 - hours_ago] = row["cnt"]

        # Calls per day for last 7 days: single GROUP BY query, fill 7-slot array
        calls_7d: list[int] = [0] * 7
        today_rows = conn.execute(
            "SELECT strftime('%Y-%m-%d', called_at) as day, COUNT(*) as cnt "
            "FROM mcp_calls WHERE called_at >= datetime('now', '-7 days') "
            "GROUP BY day"
        ).fetchall()
        # Build a lookup of date string → count
        day_counts: dict[str, int] = {r["day"]: r["cnt"] for r in today_rows}
        for i in range(6, -1, -1):
            day_str = conn.execute(
                "SELECT strftime('%Y-%m-%d', datetime('now', ? || ' days'))",
                (f"-{i}",),
            ).fetchone()[0]
            calls_7d[6 - i] = day_counts.get(day_str, 0)

        # Pattern growth over last 30 days: single GROUP BY query, fill 30-slot array
        pattern_growth_30d: list[int] = [0] * 30
        growth_rows = conn.execute(
            "SELECT strftime('%Y-%m-%d', created_at) as day, COUNT(*) as cnt "
            "FROM patterns WHERE created_at >= datetime('now', '-30 days') "
            "GROUP BY day"
        ).fetchall()
        growth_counts: dict[str, int] = {r["day"]: r["cnt"] for r in growth_rows}
        for i in range(29, -1, -1):
            day_str = conn.execute(
                "SELECT strftime('%Y-%m-%d', datetime('now', ? || ' days'))",
                (f"-{i}",),
            ).fetchone()[0]
            pattern_growth_30d[29 - i] = growth_counts.get(day_str, 0)

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {
                "pattern_count": pattern_count,
                "pending_skills": pending_skills,
                "active_skills": active_skills,
                "project_count": project_count,
                "drift_checks_30d": drift_count,
                "session_count": session_count,
                "recent_activity": recent_activity,
                "sessions_running": sessions_running,
                "sessions_completed": sessions_completed,
                "calls_today": calls_today,
                "calls_7d": calls_7d,
                "calls_by_hour": calls_by_hour,
                "pattern_growth_30d": pattern_growth_30d,
            },
            duration_ms=elapsed,
        )
    finally:
        conn.close()


async def handle_patterns(request: web.Request) -> web.Response:
    """Paginated pattern list with optional category filter."""
    start = time.monotonic()
    project = request.query.get("project")
    category = request.query.get("category")
    if category and category not in VALID_PATTERN_CATEGORIES:
        return _error_envelope(
            f"Invalid category. Must be one of: {', '.join(VALID_PATTERN_CATEGORIES)}",
            code="VALIDATION_INVALID_VALUE",
            status=400,
        )
    limit = _parse_int(request.query.get("limit"), 50)
    offset = _parse_int(request.query.get("offset"), 0)
    conn = _get_conn(request)
    try:
        # Build dynamic WHERE clause for project + category filters
        conditions: list[str] = []
        params: list[str | int] = []
        if project:
            conditions.append("(project = ? OR project IS NULL)")
            params.append(project)
        if category:
            conditions.append("category = ?")
            params.append(category)

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        # Safe: where clause built from hardcoded allowlist, all values parameterized
        from_clause = f"FROM patterns{where} "  # noqa: S608
        select_q = (
            "SELECT id, name, context, approach, outcome, project, category, "
            "created_at, last_matched_at, match_count "
            + from_clause
            + "ORDER BY created_at DESC LIMIT ? OFFSET ?"
        )
        count_q = "SELECT COUNT(*) " + from_clause

        rows = conn.execute(select_q, (*params, limit, offset)).fetchall()
        total = conn.execute(count_q, params).fetchone()[0]

        patterns = [
            {
                "id": r["id"],
                "name": r["name"],
                "context": r["context"],
                "approach": r["approach"],
                "outcome": r["outcome"],
                "project": r["project"],
                "category": r["category"],
                "created_at": r["created_at"],
                "last_matched_at": r["last_matched_at"],
                "match_count": r["match_count"],
            }
            for r in rows
        ]

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {"patterns": patterns, "total": total, "limit": limit, "offset": offset},
            duration_ms=elapsed,
        )
    finally:
        conn.close()


async def handle_pattern_detail(request: web.Request) -> web.Response:
    """Single pattern detail."""
    start = time.monotonic()
    pattern_id = _parse_int(request.match_info.get("id"), -1)
    conn = _get_conn(request)
    try:
        row = conn.execute(
            "SELECT id, name, context, approach, outcome, project, category, "
            "created_at, last_matched_at, match_count "
            "FROM patterns WHERE id = ?",
            (pattern_id,),
        ).fetchone()

        if not row:
            return _error_envelope(f"Pattern {pattern_id} not found")

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {
                "id": row["id"],
                "name": row["name"],
                "context": row["context"],
                "approach": row["approach"],
                "outcome": row["outcome"],
                "project": row["project"],
                "category": row["category"],
                "created_at": row["created_at"],
                "last_matched_at": row["last_matched_at"],
                "match_count": row["match_count"],
            },
            duration_ms=elapsed,
        )
    finally:
        conn.close()


async def handle_skills(request: web.Request) -> web.Response:
    """Skill suggestions and tracked skills."""
    start = time.monotonic()
    project = request.query.get("project")
    status = request.query.get("status")
    conn = _get_conn(request)
    try:
        # Suggestions
        suggestion_sql = (
            "SELECT id, project, proposed_name, theme, confidence, status, "
            "created_at, resolved_at, generated_path FROM skill_suggestions"
        )
        suggestion_params: list[str] = []
        conditions: list[str] = []

        if project:
            conditions.append("project = ?")
            suggestion_params.append(project)
        if status:
            conditions.append("status = ?")
            suggestion_params.append(status)

        if conditions:
            suggestion_sql += " WHERE " + " AND ".join(conditions)
        suggestion_sql += " ORDER BY created_at DESC"

        suggestion_rows = conn.execute(suggestion_sql, suggestion_params).fetchall()
        suggestions = [
            {
                "id": r["id"],
                "project": r["project"],
                "proposed_name": r["proposed_name"],
                "theme": r["theme"],
                "confidence": r["confidence"],
                "status": r["status"],
                "created_at": r["created_at"],
                "resolved_at": r["resolved_at"],
                "generated_path": r["generated_path"],
            }
            for r in suggestion_rows
        ]

        # Tracked skills
        if project:
            tracked_rows = conn.execute(
                "SELECT id, skill_path, project, first_seen_at, last_matched_at, match_count "
                "FROM skill_usage_tracking WHERE project = ? "
                "ORDER BY last_matched_at DESC",
                (project,),
            ).fetchall()
        else:
            tracked_rows = conn.execute(
                "SELECT id, skill_path, project, first_seen_at, last_matched_at, match_count "
                "FROM skill_usage_tracking ORDER BY last_matched_at DESC"
            ).fetchall()

        tracked = [
            {
                "id": r["id"],
                "skill_path": r["skill_path"],
                "project": r["project"],
                "first_seen_at": r["first_seen_at"],
                "last_matched_at": r["last_matched_at"],
                "match_count": r["match_count"],
            }
            for r in tracked_rows
        ]

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {"suggestions": suggestions, "tracked": tracked},
            duration_ms=elapsed,
        )
    finally:
        conn.close()


async def handle_skills_stale(request: web.Request) -> web.Response:
    """Skills not matched within threshold."""
    start = time.monotonic()
    threshold_days = _parse_int(request.query.get("threshold_days"), 60)
    conn = _get_conn(request)
    try:
        rows = conn.execute(
            "SELECT skill_path, project, last_matched_at, match_count "
            "FROM skill_usage_tracking "
            "WHERE last_matched_at IS NULL "
            "   OR last_matched_at < datetime('now', '-' || ? || ' days') "
            "ORDER BY last_matched_at ASC",
            (str(threshold_days),),
        ).fetchall()

        stale = [
            {
                "skill_path": r["skill_path"],
                "project": r["project"],
                "last_matched_at": r["last_matched_at"],
                "match_count": r["match_count"],
            }
            for r in rows
        ]

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {"stale_skills": stale, "threshold_days": threshold_days},
            duration_ms=elapsed,
        )
    finally:
        conn.close()


async def handle_projects(request: web.Request) -> web.Response:
    """Indexed projects with file counts and language summaries."""
    start = time.monotonic()
    conn = _get_conn(request)
    try:
        rows = conn.execute(
            "SELECT project_path, "
            "  COUNT(*) as file_count, "
            "  COUNT(DISTINCT language) as language_count, "
            "  MAX(indexed_at) as last_indexed "
            "FROM project_files "
            "GROUP BY project_path "
            "ORDER BY last_indexed DESC"
        ).fetchall()

        projects = [
            {
                "project_path": r["project_path"],
                "file_count": r["file_count"],
                "language_count": r["language_count"],
                "last_indexed": r["last_indexed"],
            }
            for r in rows
        ]

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok({"projects": projects}, duration_ms=elapsed)
    finally:
        conn.close()


async def handle_project_detail(request: web.Request) -> web.Response:
    """Single project detail: language breakdown, role distribution, export counts."""
    start = time.monotonic()
    project_path = unquote(request.match_info["path"])
    conn = _get_conn(request)
    try:
        # Check project exists
        exists = conn.execute(
            "SELECT COUNT(*) FROM project_files WHERE project_path = ?",
            (project_path,),
        ).fetchone()[0]
        if not exists:
            return _error_envelope(f"Project '{project_path}' not found")

        # Language breakdown
        lang_rows = conn.execute(
            "SELECT language, COUNT(*) as count "
            "FROM project_files WHERE project_path = ? "
            "GROUP BY language ORDER BY count DESC",
            (project_path,),
        ).fetchall()
        languages = [
            {"language": r["language"] or "unknown", "count": r["count"]} for r in lang_rows
        ]

        # Role breakdown
        role_rows = conn.execute(
            "SELECT role, COUNT(*) as count "
            "FROM project_files WHERE project_path = ? "
            "GROUP BY role ORDER BY count DESC",
            (project_path,),
        ).fetchall()
        roles = [{"role": r["role"] or "unknown", "count": r["count"]} for r in role_rows]

        # Export counts
        export_rows = conn.execute(
            "SELECT fe.kind, COUNT(*) as count "
            "FROM file_exports fe "
            "JOIN project_files pf ON fe.file_id = pf.id "
            "WHERE pf.project_path = ? "
            "GROUP BY fe.kind ORDER BY count DESC",
            (project_path,),
        ).fetchall()
        exports = [{"kind": r["kind"], "count": r["count"]} for r in export_rows]

        # Total file count
        total_files = conn.execute(
            "SELECT COUNT(*) FROM project_files WHERE project_path = ?",
            (project_path,),
        ).fetchone()[0]

        # Total export count
        total_exports = conn.execute(
            "SELECT COUNT(*) FROM file_exports fe "
            "JOIN project_files pf ON fe.file_id = pf.id "
            "WHERE pf.project_path = ?",
            (project_path,),
        ).fetchone()[0]

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {
                "project_path": project_path,
                "total_files": total_files,
                "total_exports": total_exports,
                "languages": languages,
                "roles": roles,
                "exports_by_kind": exports,
            },
            duration_ms=elapsed,
        )
    finally:
        conn.close()


async def handle_drift(request: web.Request) -> web.Response:
    """Drift check history with scores."""
    start = time.monotonic()
    project = request.query.get("project")
    from_date = request.query.get("from")
    to_date = request.query.get("to")
    limit = _parse_int(request.query.get("limit"), 100)
    conn = _get_conn(request)
    try:
        sql = (
            "SELECT id, task_description, changed_files, score, similarity, "
            "verdict, flags, project, created_at FROM drift_history"
        )
        params: list[str | int] = []
        conditions: list[str] = []

        if project:
            conditions.append("project = ?")
            params.append(project)
        if from_date:
            conditions.append("created_at >= ?")
            params.append(from_date)
        if to_date:
            conditions.append("created_at <= ?")
            params.append(to_date)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()

        drift_checks = [
            {
                "id": r["id"],
                "task_description": r["task_description"],
                "changed_files": json.loads(r["changed_files"]),
                "score": r["score"],
                "similarity": r["similarity"],
                "verdict": r["verdict"],
                "flags": json.loads(r["flags"]),
                "project": r["project"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {"drift_checks": drift_checks, "count": len(drift_checks)}, duration_ms=elapsed
        )
    finally:
        conn.close()


async def handle_sessions(request: web.Request) -> web.Response:
    """Paginated session list."""
    start = time.monotonic()
    limit = _parse_int(request.query.get("limit"), 50)
    offset = _parse_int(request.query.get("offset"), 0)
    conn = _get_conn(request)
    try:
        rows = conn.execute(
            "SELECT session_id, state_json, version, created_at, "
            "original_request, task_classification, status, project "
            "FROM session_checkpoints "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()

        total = conn.execute("SELECT COUNT(*) FROM session_checkpoints").fetchone()[0]

        sessions = []
        for r in rows:
            state = json.loads(r["state_json"])
            # Prefer dedicated status column, fall back to state_json extraction
            status = r["status"] or state.get("status", state.get("state", "unknown"))
            entry: dict[str, Any] = {
                "session_id": r["session_id"],
                "status": status,
                "version": r["version"],
                "created_at": r["created_at"],
            }
            if r["original_request"] is not None:
                entry["original_request"] = r["original_request"]
            if r["task_classification"] is not None:
                entry["task_classification"] = r["task_classification"]
            if r["project"] is not None:
                entry["project"] = r["project"]
            sessions.append(entry)

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {"sessions": sessions, "total": total, "limit": limit, "offset": offset},
            duration_ms=elapsed,
        )
    finally:
        conn.close()


async def handle_session_detail(request: web.Request) -> web.Response:
    """Single session detail with full parsed state."""
    start = time.monotonic()
    session_id = request.match_info["id"]
    conn = _get_conn(request)
    try:
        row = conn.execute(
            "SELECT session_id, state_json, version, created_at, "
            "original_request, task_classification, status, project "
            "FROM session_checkpoints WHERE session_id = ?",
            (session_id,),
        ).fetchone()

        if not row:
            return _error_envelope(f"Session '{session_id}' not found")

        state = json.loads(row["state_json"])
        result: dict[str, Any] = {
            "session_id": row["session_id"],
            "state": state,
            "version": row["version"],
            "created_at": row["created_at"],
        }
        if row["original_request"] is not None:
            result["original_request"] = row["original_request"]
        if row["task_classification"] is not None:
            result["task_classification"] = row["task_classification"]
        if row["status"] is not None:
            result["status"] = row["status"]
        if row["project"] is not None:
            result["project"] = row["project"]

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(result, duration_ms=elapsed)
    finally:
        conn.close()


async def handle_health(request: web.Request) -> web.Response:
    """Server health, version, DB size, counts."""
    start = time.monotonic()
    db_path: Path = request.app.get("db_path", DB_PATH)
    conn = _get_conn(request)
    try:
        pattern_count = conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]
        session_count = conn.execute("SELECT COUNT(*) FROM session_checkpoints").fetchone()[0]
        project_count = conn.execute(
            "SELECT COUNT(DISTINCT project_path) FROM project_files"
        ).fetchone()[0]

        db_size = db_path.stat().st_size if db_path.exists() else 0

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {
                "status": "ok",
                "version": SERVER_VERSION,
                "server_name": SERVER_NAME,
                "db_size_bytes": db_size,
                "pattern_count": pattern_count,
                "session_count": session_count,
                "project_count": project_count,
            },
            duration_ms=elapsed,
        )
    finally:
        conn.close()


# ── Mutation endpoint handlers ────────────────────────────────────


async def handle_pattern_delete(request: web.Request) -> web.Response:
    """Delete a single pattern by ID."""
    start = time.monotonic()
    pattern_id = _parse_int(request.match_info.get("id"), -1)
    conn = _get_write_conn(request)
    try:
        # Check existence first
        row = conn.execute("SELECT id FROM patterns WHERE id = ?", (pattern_id,)).fetchone()
        if not row:
            return _error_envelope(f"Pattern {pattern_id} not found")

        conn.execute("DELETE FROM patterns WHERE id = ?", (pattern_id,))
        conn.commit()

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_mutated({"deleted": True, "id": pattern_id}, duration_ms=elapsed)
    finally:
        conn.close()


async def handle_pattern_edit(request: web.Request) -> web.Response:
    """Edit pattern fields (name, context, approach, outcome, category)."""
    start = time.monotonic()
    pattern_id = _parse_int(request.match_info.get("id"), -1)
    body = await _parse_json_body(request)

    # Only allow editing specific fields
    allowed_fields = {"name", "context", "approach", "outcome", "category"}
    updates = {k: v for k, v in body.items() if k in allowed_fields}

    if not updates:
        return _error_envelope(
            "No valid fields to update. Allowed: name, context, approach, outcome, category",
            code="VALIDATION_INVALID_VALUE",
            status=400,
        )

    # Validate that all values are strings
    for key, value in updates.items():
        if not isinstance(value, str) or not value.strip():
            return _error_envelope(
                f"Field '{key}' must be a non-empty string",
                code="VALIDATION_INVALID_TYPE",
                status=400,
            )

    # Validate category against allowed values
    if "category" in updates and updates["category"] not in VALID_PATTERN_CATEGORIES:
        return _error_envelope(
            f"Invalid category. Must be one of: {', '.join(VALID_PATTERN_CATEGORIES)}",
            code="VALIDATION_INVALID_VALUE",
            status=400,
        )

    conn = _get_write_conn(request)
    try:
        # Build SET clause from static field list (avoids taint on column names)
        set_parts: list[str] = []
        values: list[Any] = []
        for field in ("name", "context", "approach", "outcome", "category"):
            if field in updates:
                set_parts.append(f"{field} = ?")
                values.append(updates[field])
        values.append(pattern_id)
        cursor = conn.execute(
            f"UPDATE patterns SET {', '.join(set_parts)} WHERE id = ?",  # noqa: S608
            values,
        )
        if cursor.rowcount == 0:
            return _error_envelope(f"Pattern {pattern_id} not found")
        conn.commit()

        # Return updated pattern
        updated = conn.execute(
            "SELECT id, name, context, approach, outcome, project, category, "
            "created_at, last_matched_at, match_count "
            "FROM patterns WHERE id = ?",
            (pattern_id,),
        ).fetchone()

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_mutated(
            {
                "updated": True,
                "pattern": {
                    "id": updated["id"],
                    "name": updated["name"],
                    "context": updated["context"],
                    "approach": updated["approach"],
                    "outcome": updated["outcome"],
                    "project": updated["project"],
                    "category": updated["category"],
                    "created_at": updated["created_at"],
                    "last_matched_at": updated["last_matched_at"],
                    "match_count": updated["match_count"],
                },
            },
            duration_ms=elapsed,
        )
    finally:
        conn.close()


async def handle_pattern_prune(request: web.Request) -> web.Response:
    """Prune stale patterns (zero matches, older than max_age_days)."""
    start = time.monotonic()
    body = await _parse_json_body(request)

    max_age_days = body.get("max_age_days", 90)

    if not isinstance(max_age_days, int) or isinstance(max_age_days, bool) or max_age_days < 1:
        return _error_envelope(
            "max_age_days must be a positive integer",
            code="VALIDATION_INVALID_VALUE",
            status=400,
        )

    conn = _get_write_conn(request)
    try:
        # Replicate VectorStore.prune_patterns() logic: delete old patterns with zero matches
        cursor = conn.execute(
            "DELETE FROM patterns WHERE "
            "created_at < datetime('now', ? || ' days') AND match_count = 0",
            (f"-{max_age_days}",),
        )
        pruned = cursor.rowcount
        remaining = int(conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0])
        conn.commit()

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_mutated(
            {
                "pruned": pruned,
                "remaining": remaining,
                "max_age_days": max_age_days,
            },
            duration_ms=elapsed,
        )
    finally:
        conn.close()


async def handle_skill_action(request: web.Request) -> web.Response:
    """Accept, dismiss, or defer a skill suggestion."""
    start = time.monotonic()
    suggestion_id = _parse_int(request.match_info.get("id"), -1)
    body = await _parse_json_body(request)

    action = body.get("action", "")
    if action not in ("accept", "dismiss", "defer"):
        return _error_envelope(
            f"Invalid action '{action}'. Must be accept, dismiss, or defer",
            code="VALIDATION_INVALID_VALUE",
            status=400,
        )

    conn = _get_write_conn(request)
    try:
        row = conn.execute(
            "SELECT id, proposed_name, proposed_content, status, project "
            "FROM skill_suggestions WHERE id = ?",
            (suggestion_id,),
        ).fetchone()

        if not row:
            return _error_envelope(f"Skill suggestion {suggestion_id} not found")

        current_status = row["status"]
        if current_status in ("accepted", "dismissed"):
            return _error_envelope(
                f"Suggestion {suggestion_id} is already {current_status}",
                code="CONFLICT_ALREADY_RESOLVED",
                status=409,
            )

        if action == "dismiss":
            conn.execute(
                "UPDATE skill_suggestions SET status = 'dismissed', "
                "resolved_at = datetime('now') WHERE id = ?",
                (suggestion_id,),
            )
            conn.commit()
            elapsed = int((time.monotonic() - start) * 1000)
            return _json_mutated(
                {"suggestion_id": suggestion_id, "status": "dismissed", "generated": False},
                duration_ms=elapsed,
            )

        if action == "defer":
            conn.execute(
                "UPDATE skill_suggestions SET status = 'deferred' WHERE id = ?",
                (suggestion_id,),
            )
            conn.commit()
            elapsed = int((time.monotonic() - start) * 1000)
            return _json_mutated(
                {"suggestion_id": suggestion_id, "status": "deferred", "generated": False},
                duration_ms=elapsed,
            )

        # action == "accept"
        proposed_name = row["proposed_name"]
        proposed_content = row["proposed_content"]
        project = row["project"]

        output_dir = body.get("output_dir", ".ai/skills")
        # Validate output_dir: reject absolute paths and path traversal
        if Path(output_dir).is_absolute() or ".." in Path(output_dir).parts:
            return _error_envelope(
                "output_dir must be a relative path without '..' segments",
                code="VALIDATION_INVALID_VALUE",
                status=400,
            )
        cwd = Path.cwd().resolve()
        output_path = (cwd / output_dir).resolve()
        if not (str(output_path) + "/").startswith(str(cwd) + "/"):
            return _error_envelope(
                "output_dir resolves outside the working directory",
                code="VALIDATION_INVALID_VALUE",
                status=400,
            )
        output_path.mkdir(parents=True, exist_ok=True)

        safe_name = proposed_name.replace("/", "_").replace("\\", "_")
        file_name = f"{safe_name}.md"
        file_path = (output_path / file_name).resolve()
        if not (str(file_path) + "/").startswith(str(cwd) + "/"):
            return _error_envelope(
                "Generated file path resolves outside the working directory",
                code="VALIDATION_INVALID_VALUE",
                status=400,
            )
        file_path.write_text(proposed_content, encoding="utf-8")

        conn.execute(
            "UPDATE skill_suggestions SET status = 'accepted', "
            "resolved_at = datetime('now'), generated_path = ? WHERE id = ?",
            (str(file_path), suggestion_id),
        )
        conn.execute(
            "INSERT OR IGNORE INTO skill_usage_tracking (skill_path, project) VALUES (?, ?)",
            (str(file_path), project),
        )
        conn.commit()

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_mutated(
            {
                "suggestion_id": suggestion_id,
                "status": "accepted",
                "generated": True,
                "path": str(file_path),
            },
            duration_ms=elapsed,
            status=201,
        )
    finally:
        conn.close()


async def handle_skill_delete(request: web.Request) -> web.Response:
    """Remove a tracked skill from skill_usage_tracking."""
    start = time.monotonic()
    skill_id = _parse_int(request.match_info.get("id"), -1)
    conn = _get_write_conn(request)
    try:
        row = conn.execute(
            "SELECT id FROM skill_usage_tracking WHERE id = ?", (skill_id,)
        ).fetchone()
        if not row:
            return _error_envelope(f"Tracked skill {skill_id} not found")

        conn.execute("DELETE FROM skill_usage_tracking WHERE id = ?", (skill_id,))
        conn.commit()

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_mutated({"deleted": True, "id": skill_id}, duration_ms=elapsed)
    finally:
        conn.close()


async def handle_settings_get(request: web.Request) -> web.Response:
    """Read current config by loading Settings and serializing."""
    start = time.monotonic()
    settings = load_settings()

    # Serialize settings to a dict
    settings_dict: dict[str, Any] = {}
    for f in dataclasses.fields(settings):
        if f.name == "source_map":
            continue
        value = getattr(settings, f.name)
        settings_dict[f.name] = str(value) if isinstance(value, Path) else value

    # Read raw TOML if global config exists, redacting any secrets
    raw_toml: str | None = None
    config_path = request.app.get("global_config_path", GLOBAL_CONFIG_PATH)
    if Path(config_path).is_file():
        raw_toml = redact(Path(config_path).read_text(encoding="utf-8"))

    elapsed = int((time.monotonic() - start) * 1000)
    return _json_ok(
        {
            "settings": settings_dict,
            "source_map": settings.source_map,
            "raw_toml": raw_toml,
            "config_path": str(config_path),
        },
        duration_ms=elapsed,
    )


async def handle_settings_update(request: web.Request) -> web.Response:
    """Write config to ~/.config/ensemble-mcp/config.toml."""
    start = time.monotonic()
    body = await _parse_json_body(request)

    # Validate field names against Settings dataclass
    valid_fields = {f.name for f in dataclasses.fields(Settings) if f.name != "source_map"}
    invalid_fields = set(body.keys()) - valid_fields
    if invalid_fields:
        return _error_envelope(
            f"Unknown settings fields: {', '.join(sorted(invalid_fields))}",
            code="VALIDATION_INVALID_VALUE",
            status=400,
        )

    if not body:
        return _error_envelope(
            "No settings provided",
            code="VALIDATION_MISSING_FIELD",
            status=400,
        )

    # Type validation
    settings = Settings()
    for key, value in body.items():
        current = getattr(settings, key)
        if isinstance(current, int) and not isinstance(value, int):
            return _error_envelope(
                f"Field '{key}' must be an integer",
                code="VALIDATION_INVALID_TYPE",
                status=400,
            )
        if isinstance(current, int) and isinstance(value, bool):
            return _error_envelope(
                f"Field '{key}' must be an integer",
                code="VALIDATION_INVALID_TYPE",
                status=400,
            )
        if isinstance(current, float) and not isinstance(value, (int, float)):
            return _error_envelope(
                f"Field '{key}' must be a number",
                code="VALIDATION_INVALID_TYPE",
                status=400,
            )
        if isinstance(current, Path) and not isinstance(value, str):
            return _error_envelope(
                f"Field '{key}' must be a string path",
                code="VALIDATION_INVALID_TYPE",
                status=400,
            )

    # Load existing global config and merge
    config_path = request.app.get("global_config_path", GLOBAL_CONFIG_PATH)
    try:
        existing = _load_toml(Path(config_path))
        existing.update(body)
        _write_toml(Path(config_path), existing)
    except Exception as exc:
        return _error_envelope(
            f"Failed to write settings: {exc}",
            code="IO_WRITE_ERROR",
            status=500,
        )

    elapsed = int((time.monotonic() - start) * 1000)
    return _json_mutated(
        {"saved": True, "config_path": str(config_path), "fields": list(body.keys())},
        duration_ms=elapsed,
    )


async def handle_settings_schema(request: web.Request) -> web.Response:
    """Return field names, types, defaults for generating the settings form."""
    _ = request
    start = time.monotonic()
    schema = _settings_field_schema()
    elapsed = int((time.monotonic() - start) * 1000)
    return _json_ok({"schema": schema}, duration_ms=elapsed)


async def handle_reset(request: web.Request) -> web.Response:
    """Reset all data. Requires {"confirm": true} in body."""
    start = time.monotonic()
    body = await _parse_json_body(request)

    if body.get("confirm") is not True:
        return _error_envelope(
            "Reset requires confirm=true in request body",
            code="VALIDATION_CONSTRAINT",
            status=400,
        )

    conn = _get_write_conn(request)
    try:
        tables = [
            "patterns",
            "mcp_calls",
            "file_exports",
            "file_imports",
            "project_files",
            "skill_suggestion_patterns",
            "skill_suggestions",
            "skill_usage_tracking",
            "drift_history",
            "session_checkpoints",
            "idempotency_keys",
        ]
        with conn:
            for table in tables:
                with contextlib.suppress(sqlite3.OperationalError):
                    conn.execute(f"DELETE FROM {table}")  # noqa: S608

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_mutated({"reset": True}, duration_ms=elapsed)
    finally:
        conn.close()


def _sync_reindex_project(project: Path, db_path: str | Path) -> int:
    """Synchronous file scan and DB indexing for a project.

    Clears the existing index and re-scans the filesystem. Designed to
    run in a thread pool via ``asyncio.to_thread`` to avoid blocking the
    event loop.

    Creates its own SQLite connection (required because ``sqlite3``
    connections must not cross thread boundaries).
    """
    from datetime import UTC, datetime

    from ..config.defaults import INDEXER_IGNORED_DIRS, INDEXER_IGNORED_EXTENSIONS
    from ..tools.indexer import (
        _detect_language,
        _detect_role,
        _extract_exports,
        _extract_imports,
        _is_ignored,
        _load_gitignore_patterns,
    )

    conn = get_connection(Path(db_path))
    try:
        project_str = str(project)

        # Clear existing index (force re-index)
        conn.execute(
            "DELETE FROM file_exports WHERE file_id IN "
            "(SELECT id FROM project_files WHERE project_path = ?)",
            (project_str,),
        )
        conn.execute(
            "DELETE FROM file_imports WHERE file_id IN "
            "(SELECT id FROM project_files WHERE project_path = ?)",
            (project_str,),
        )
        conn.execute(
            "DELETE FROM project_files WHERE project_path = ?",
            (project_str,),
        )

        gitignore_patterns = _load_gitignore_patterns(project)

        indexed_count = 0
        for fp in project.rglob("*"):
            if not fp.is_file():
                continue

            rel = str(fp.relative_to(project))

            if _is_ignored(rel, INDEXER_IGNORED_DIRS, gitignore_patterns):
                continue

            if fp.suffix.lower() in INDEXER_IGNORED_EXTENSIONS:
                continue

            stat = fp.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
            size = stat.st_size

            language = _detect_language(fp)
            role = _detect_role(rel)

            content = ""
            if language and size < 500_000:
                with contextlib.suppress(OSError):
                    content = fp.read_text(encoding="utf-8", errors="replace")

            cursor = conn.execute(
                "INSERT INTO project_files "
                "(project_path, file_path, language, role, size_bytes, modified_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (project_str, rel, language, role, size, mtime),
            )
            file_id = cursor.lastrowid or 0

            exports = _extract_exports(content, language)
            for exp in exports:
                conn.execute(
                    "INSERT OR IGNORE INTO file_exports "
                    "(file_id, name, kind, line_number, signature, docstring) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        file_id,
                        exp["name"],
                        exp["kind"],
                        exp.get("line_number"),
                        exp.get("signature"),
                        exp.get("docstring"),
                    ),
                )

            imports = _extract_imports(content, language)
            for imp in imports:
                conn.execute(
                    "INSERT INTO file_imports (file_id, import_path, raw_import) VALUES (?, ?, ?)",
                    (file_id, imp["import_path"], imp["raw"]),
                )

            indexed_count += 1

        conn.commit()
        return indexed_count
    finally:
        conn.close()


async def handle_project_reindex(request: web.Request) -> web.Response:
    """Force re-index a project by scanning the filesystem."""
    start = time.monotonic()
    project_path = unquote(request.match_info["path"])
    project = Path(project_path).resolve()

    if not _is_path_under_allowed_root(project):
        return _error_envelope(
            "Project path is not under an allowed root directory",
            code="VALIDATION_INVALID_VALUE",
            status=400,
        )

    if not project.is_dir():
        return _error_envelope(
            f"Project directory not found: {project_path}",
            code="NOT_FOUND_PROJECT",
        )

    db_path = request.app["db_path"]
    indexed_count = await asyncio.to_thread(_sync_reindex_project, project, db_path)

    elapsed = int((time.monotonic() - start) * 1000)
    return _json_mutated(
        {"indexed": True, "files": indexed_count, "project_path": str(project)},
        duration_ms=elapsed,
    )


async def handle_project_delete(request: web.Request) -> web.Response:
    """Clear index for a project (delete all indexed data)."""
    start = time.monotonic()
    project_path = unquote(request.match_info["path"])
    conn = _get_write_conn(request)
    try:
        # Check project exists in index
        exists = conn.execute(
            "SELECT COUNT(*) FROM project_files WHERE project_path = ?",
            (project_path,),
        ).fetchone()[0]
        if not exists:
            return _error_envelope(f"Project '{project_path}' not found in index")

        # Delete in dependency order
        conn.execute(
            "DELETE FROM file_exports WHERE file_id IN "
            "(SELECT id FROM project_files WHERE project_path = ?)",
            (project_path,),
        )
        conn.execute(
            "DELETE FROM file_imports WHERE file_id IN "
            "(SELECT id FROM project_files WHERE project_path = ?)",
            (project_path,),
        )
        conn.execute(
            "DELETE FROM project_files WHERE project_path = ?",
            (project_path,),
        )
        conn.commit()

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_mutated(
            {"deleted": True, "project_path": project_path},
            duration_ms=elapsed,
        )
    finally:
        conn.close()


def _find_missing_files(
    project_path: str,
    rows: list[Any],
) -> tuple[list[str], bool]:
    """Check for indexed files that are missing on disk.

    Uses ``os.path.realpath`` + inline ``startswith`` guards so CodeQL
    can trace that filesystem operations only run on validated paths.

    Returns ``(missing_files, path_restricted)``.
    """
    import os.path

    resolved = os.path.realpath(project_path)

    # Inline allowed-root guard — must match _ALLOWED_ROOTS at module level.
    # Uses tuple-form startswith so CodeQL traces the sanitiser in-scope.
    if not resolved.startswith(("/home/", "/opt/", "/workspace/", "/var/www/", "/srv/")):
        return [], True

    missing: list[str] = []
    safe_prefix = resolved + "/"
    for r in rows:
        candidate = os.path.realpath(os.path.join(resolved, r["file_path"]))
        if not candidate.startswith(safe_prefix):
            continue  # file_path escapes project directory
        if not os.path.exists(candidate):
            missing.append(r["file_path"])
    return missing, False


async def handle_project_health(request: web.Request) -> web.Response:
    """Return index staleness info: file count, oldest indexed_at, files missing on disk."""
    start = time.monotonic()
    project_path = unquote(request.match_info["path"])
    conn = _get_conn(request)
    try:
        # Check project exists
        file_count = conn.execute(
            "SELECT COUNT(*) FROM project_files WHERE project_path = ?",
            (project_path,),
        ).fetchone()[0]
        if not file_count:
            return _error_envelope(f"Project '{project_path}' not found in index")

        # Oldest indexed_at
        oldest_row = conn.execute(
            "SELECT MIN(indexed_at) FROM project_files WHERE project_path = ?",
            (project_path,),
        ).fetchone()
        oldest_indexed_at = oldest_row[0] if oldest_row else None

        # Newest indexed_at
        newest_row = conn.execute(
            "SELECT MAX(indexed_at) FROM project_files WHERE project_path = ?",
            (project_path,),
        ).fetchone()
        newest_indexed_at = newest_row[0] if newest_row else None

        # Check for files not found on disk
        rows = conn.execute(
            "SELECT file_path FROM project_files WHERE project_path = ?",
            (project_path,),
        ).fetchall()

        missing_files, path_restricted = _find_missing_files(project_path, rows)

        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {
                "project_path": project_path,
                "file_count": file_count,
                "oldest_indexed_at": oldest_indexed_at,
                "newest_indexed_at": newest_indexed_at,
                "missing_files_count": len(missing_files),
                "missing_files": missing_files[:50],  # limit to avoid huge responses
                "path_restricted": path_restricted,
            },
            duration_ms=elapsed,
        )
    finally:
        conn.close()


# ── Reports endpoint handlers ─────────────────────────────────────


def _parse_bug_report_markdown(text: str) -> dict[str, Any]:
    """Extract structured data from a Bug Hunter markdown report.

    Parses metadata, health breakdown, bugs, code smells, architecture,
    project structure, refactor plan, test results, CI quality gate, and
    security audit sections.  Each section is parsed independently so a
    failure in one section does not prevent others from being extracted.

    Args:
        text: Raw markdown content of the bug report.

    Returns:
        Dictionary with parsed fields.  Missing sections yield empty
        lists or ``None`` values.
    """
    result: dict[str, Any] = {
        "project": None,
        "date": None,
        "analyzer": None,
        "branch": None,
        "commit": None,
        "health_score": None,
        "health_rating": None,
        "health_breakdown": [],
        "bugs": [],
        "smells": [],
        "architecture": None,
        "structure": None,
        "refactor_plan": [],
        "tests": None,
        "ci": None,
        "security": [],
    }

    # ── Metadata ──────────────────────────────────────────────────
    try:
        m = re.search(r"\*\*Project:\*\*\s*(.+)", text)
        if not m:
            m = re.search(r"\*\*Codebase:\*\*\s*(.+)", text)
        if m:
            result["project"] = m.group(1).strip()
        m = re.search(r"\*\*Date:\*\*\s*(.+)", text)
        if m:
            result["date"] = m.group(1).strip()
        m = re.search(r"\*\*Analyzer:\*\*\s*(.+)", text)
        if m:
            result["analyzer"] = m.group(1).strip()
        m = re.search(r"\*\*Branch:\*\*\s*(.+)", text)
        if m:
            result["branch"] = m.group(1).strip()
        m = re.search(r"\*\*Commit:\*\*\s*(.+)", text)
        if m:
            result["commit"] = m.group(1).strip()
    except Exception:  # noqa: S110
        pass

    # ── Overall Health Score ──────────────────────────────────────
    try:
        # Old format: ## Overall Health Score: 84/100 (Good)
        m = re.search(
            r"##\s+Overall Health Score:\s*(\d+)/(\d+)\s*\((\w+)\)",
            text,
        )
        if m:
            result["health_score"] = int(m.group(1))
            result["health_rating"] = m.group(3)

        # New format: ## Code Health table with **Total** row
        if not m:
            total_m = re.search(
                r"\|\s*\*\*Total\*\*\s*\|\s*\*\*(\d+)/(\d+)\*\*\s*\|\s*\*\*Rating:\s*(\w+)\*\*",
                text,
            )
            if not total_m:
                # Separate columns: | **Total** | **78** | **100** | **Rating: Moderate** |
                total_m = re.search(
                    r"\|\s*\*\*Total\*\*\s*\|\s*\*\*(\d+)\*\*\s*\|\s*\*\*(\d+)\*\*\s*\|\s*\*\*Rating:\s*(\w+)\*\*",
                    text,
                )
            if total_m:
                result["health_score"] = int(total_m.group(1))
                result["health_rating"] = total_m.group(3)

        # Parse health table — try both section headers
        health_section = re.search(
            r"##\s+(?:Overall Health Score|Code Health).*?\n(.*?)(?=\n---|\n## (?!#))",
            text,
            re.DOTALL,
        )
        if health_section:
            # New format: | Dimension | 17/20 | Notes |
            rows = re.findall(
                r"\|\s*([^|]+?)\s*\|\s*(\d+)/(\d+)\s*\|\s*([^|]*?)\s*\|",
                health_section.group(1),
            )
            breakdown = []
            for dim, score, mx, note in rows:
                dim = dim.strip().replace("**", "")
                if dim and dim != "Dimension" and "---" not in dim and dim != "Total":
                    breakdown.append(
                        {"pillar": dim, "score": int(score), "max": int(mx), "note": note.strip()}
                    )
            # Fallback: old format | dim | score_int | max_int |
            if not breakdown:
                # Separate columns with notes: | Category | 16 | 20 | Notes |
                # Only match if there's actual content in the 4th column
                rows_sep = re.findall(
                    r"\|\s*\*?\*?([^|\n*]+?)\*?\*?\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|\n]+?)\s*\|",
                    health_section.group(1),
                )
                for dim, score, mx, note in rows_sep:
                    dim = dim.strip().replace("**", "")
                    if dim and dim not in ("Category", "Dimension", "Total") and "---" not in dim:
                        breakdown.append(
                            {"pillar": dim, "score": int(score), "max": int(mx), "note": note.strip()}
                        )
            if not breakdown:
                rows_old = re.findall(
                    r"\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|",
                    health_section.group(1),
                )
                for dim, score, mx in rows_old:
                    dim = dim.strip()
                    if dim and dim != "Dimension" and "---" not in dim:
                        breakdown.append(
                            {"pillar": dim, "score": int(score), "max": int(mx), "note": ""}
                        )
            if breakdown:
                result["health_breakdown"] = breakdown
    except Exception:  # noqa: S110
        pass

    # ── Bugs ──────────────────────────────────────────────────────
    try:
        bugs_section = re.search(
            r"##\s+Bugs(?:\s+Found)?.*?\n(.*?)(?=\n## (?!#))",
            text,
            re.DOTALL,
        )
        if bugs_section:
            bug_blocks = re.split(r"###\s+(?:BUG-|B)(\d+):\s*", bugs_section.group(1))
            # bug_blocks: ['', '1', 'content', '2', 'content', ...]
            bugs = []
            i = 1
            while i < len(bug_blocks) - 1:
                bug_num = bug_blocks[i]
                content = bug_blocks[i + 1]
                bug_id = f"BH-{int(bug_num):04d}"

                # Title is the first line of content
                title_line = content.split("\n", 1)[0].strip()

                sev_match = re.search(
                    r"\*\*Severity:\*\*\s*(\w+)(?:\s*\(CVSS\s*([\d.]+)\))?", content
                )
                severity = sev_match.group(1).capitalize() if sev_match else "Unknown"
                cvss = float(sev_match.group(2)) if sev_match and sev_match.group(2) else 0.0

                cat_match = re.search(r"\*\*Category:\*\*\s*(.+)", content)
                category = cat_match.group(1).strip() if cat_match else ""

                loc_match = re.search(r"\*\*Location:\*\*\s*(.+)", content)
                location = loc_match.group(1).strip() if loc_match else ""

                # Description can be multi-line — capture until next bullet
                desc_match = re.search(
                    r"\*\*(?:Description|Detail):\*\*\s*(.*?)(?=\n-\s+\*\*|\Z)",
                    content,
                    re.DOTALL,
                )
                description = desc_match.group(1).strip() if desc_match else ""

                imp_match = re.search(r"\*\*Impact:\*\*\s*(\d+)(?:/(\d+))?", content)
                impact = int(imp_match.group(1)) if imp_match else None

                exp_match = re.search(r"\*\*Exploitability:\*\*\s*(\d+)(?:/(\d+))?", content)
                exploitability = int(exp_match.group(1)) if exp_match else None

                scope_match = re.search(r"\*\*Scope:\*\*\s*(\d+)(?:/(\d+))?", content)
                scope = int(scope_match.group(1)) if scope_match else None

                conf_match = re.search(r"\*\*Confidence:\*\*\s*(\d+)(?:/(\d+))?", content)
                confidence = int(conf_match.group(1)) if conf_match else None

                fix_match = re.search(r"\*\*Fix:\*\*\s*(.+)", content)
                fix = fix_match.group(1).strip() if fix_match else ""

                bugs.append(
                    {
                        "id": bug_id,
                        "title": title_line,
                        "severity": severity,
                        "cvss": cvss,
                        "category": category,
                        "location": location,
                        "description": description,
                        "impact": impact,
                        "exploitability": exploitability,
                        "scope": scope,
                        "confidence": confidence,
                        "fix": fix,
                    }
                )
                i += 2
            result["bugs"] = bugs
    except Exception:  # noqa: S110
        pass

    # ── Code Smells ───────────────────────────────────────────────
    try:
        smells_section = re.search(
            r"##\s+Code Smells.*?\n(.*?)(?=\n---|\n## (?!#))",
            text,
            re.DOTALL,
        )
        if smells_section:
            smell_blocks = re.split(r"###\s+(?:SMELL-|S)\d+:\s*", smells_section.group(1))
            smells = []
            for block in smell_blocks[1:]:
                lines = block.strip().split("\n", 1)
                type_desc = lines[0].strip()
                # Type may contain " — description"
                if " — " in type_desc:
                    smell_type, _ = type_desc.split(" — ", 1)
                else:
                    smell_type = type_desc

                loc_match = re.search(r"\*\*Location:\*\*\s*(.+)", block)
                location = loc_match.group(1).strip() if loc_match else ""

                fix_match = re.search(r"\*\*Fix:\*\*\s*(.+)", block)
                fix = fix_match.group(1).strip() if fix_match else ""

                smells.append(
                    {
                        "type": smell_type.strip(),
                        "count": 1,
                        "location": location,
                        "fix": fix,
                    }
                )
            result["smells"] = smells
            if not smells:
                # Table format: | # | Type | Location | Description | Status |
                table_rows = re.findall(
                    r"\|\s*(?:CS-\d+|SMELL-\d+|S\d+)\s*\|\s*\*?\*?([^|\n*]+?)\*?\*?\s*\|\s*([^|\n]+?)\s*\|\s*([^|\n]*?)\s*\|\s*(\w+)\s*\|",
                    smells_section.group(1),
                )
                for smell_type, location, desc, status in table_rows:
                    loc = location.strip().strip("`")
                    smells.append({
                        "type": smell_type.strip(),
                        "count": 1,
                        "location": loc,
                        "fix": desc.strip(),
                    })
                result["smells"] = smells
    except Exception:  # noqa: S110
        pass

    # ── Architecture ──────────────────────────────────────────────
    try:
        arch_section = re.search(
            r"##\s+Architecture\s*\n(.*?)(?=\n---|\n## (?!#))",
            text,
            re.DOTALL,
        )
        if arch_section:
            content = arch_section.group(1)
            detected_match = re.search(r"###\s+Detected:\s*(.+)", content)
            if not detected_match:
                detected_match = re.search(r"###\s+Detected Pattern\s*\n\*\*(.+?)\*\*", content)
            detected = detected_match.group(1).strip() if detected_match else None

            # Architecture Issues / Observations — numbered or bullet list
            issues_section = re.search(
                r"###\s+(?:Architecture Issues|(?:New )?Observations)\s*\n(.*?)(?=\n###|\Z)",
                content,
                re.DOTALL,
            )
            violations = []
            if issues_section:
                # Numbered list: 1. **text**
                violations = re.findall(
                    r"\d+\.\s+\*\*(.+?)(?:\n|$)",
                    issues_section.group(1),
                )
                violations = [v.strip().rstrip("*") for v in violations]
                # Fallback: bullet list: - text
                if not violations:
                    violations = re.findall(
                        r"-\s+(.+)",
                        issues_section.group(1),
                    )
                    violations = [v.strip() for v in violations]

            # Recommended Improvements / Recommendations — bullet or numbered list
            improvements_section = re.search(
                r"###\s+(?:Recommended Improvements|Recommendations)\s*\n(.*?)(?=\n###|\Z)",
                content,
                re.DOTALL,
            )
            recommendations = []
            if improvements_section:
                recommendations = re.findall(
                    r"(?:-|\d+\.)\s+(.+)",
                    improvements_section.group(1),
                )
                recommendations = [r.strip() for r in recommendations]

            result["architecture"] = {
                "detected": detected,
                "score": None,
                "violations": violations,
                "recommendations": recommendations,
            }
    except Exception:  # noqa: S110
        pass

    # ── Project Structure ─────────────────────────────────────────
    try:
        struct_section = re.search(
            r"##\s+Project Structure\s*\n(.*?)(?=\n---|\n## (?!#))",
            text,
            re.DOTALL,
        )
        if struct_section:
            content = struct_section.group(1)

            issues_part = re.search(
                r"###\s+Issues\s*\n(.*?)(?=\n###|\Z)",
                content,
                re.DOTALL,
            )
            issues = []
            if issues_part:
                issues = [m.strip() for m in re.findall(r"-\s+(.+)", issues_part.group(1))]

            suggestions_part = re.search(
                r"###\s+Suggestions\s*\n(.*?)(?=\n###|\Z)",
                content,
                re.DOTALL,
            )
            suggestions = []
            if suggestions_part:
                suggestions = [
                    m.strip() for m in re.findall(r"-\s+(.+)", suggestions_part.group(1))
                ]

            result["structure"] = {
                "issues": issues,
                "suggestions": suggestions,
            }
    except Exception:  # noqa: S110
        pass

    # ── Refactor Plan ─────────────────────────────────────────────
    try:
        refactor_section = re.search(
            r"##\s+Refactor Plan.*?\n(.*?)(?=\n---|\n## (?!#))",
            text,
            re.DOTALL,
        )
        if refactor_section:
            content = refactor_section.group(1)
            # Old format: table rows | step | title | complexity | impact |
            rows = re.findall(
                r"\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(\w+)\s*\|\s*(.+?)\s*\|",
                content,
            )
            plan = []
            if rows:
                for priority, item, complexity, impact in rows:
                    # Item: **bold title** — description
                    item_match = re.match(r"\*\*(.+?)\*\*\s*[—–-]\s*(.*)", item.strip())
                    if item_match:
                        title = item_match.group(1).strip()
                        desc = item_match.group(2).strip()
                    else:
                        title = item.strip()
                        desc = ""
                    plan.append(
                        {
                            "step": int(priority),
                            "title": title,
                            "effort": complexity.strip(),
                            "impact": impact.strip(),
                            "desc": desc,
                        }
                    )
            else:
                # New format: ### Priority N: Title (Complexity, Impact)
                priority_blocks = re.split(
                    r"###\s+Priority\s+(\d+)\s*[:\u2014\u2013-]\s*",
                    content,
                )
                # priority_blocks: ['', '1', 'content', '2', 'content', ...]
                i = 1
                while i < len(priority_blocks) - 1:
                    step_num = priority_blocks[i]
                    block = priority_blocks[i + 1]
                    # First line has title and optional (complexity, impact)
                    first_line, _, rest = block.partition("\n")
                    first_line = first_line.strip()

                    # Extract effort/impact from parenthetical
                    paren_match = re.search(r"\(([^)]+)\)", first_line)
                    step_effort: str = ""
                    step_impact: str = ""
                    if paren_match:
                        paren_text = paren_match.group(1)
                        # e.g. "Low complexity, High impact" or "Medium complexity"
                        effort_m = re.search(r"(\w+)\s+complexity", paren_text, re.IGNORECASE)
                        impact_m = re.search(r"(\w+)\s+impact", paren_text, re.IGNORECASE)
                        step_effort = effort_m.group(1) if effort_m else ""
                        step_impact = str(impact_m.group(1)) if impact_m else ""
                        title = first_line[: paren_match.start()].strip().rstrip(" (")
                    else:
                        title = first_line

                    # Collect numbered list items as description
                    desc_items = re.findall(r"\d+\.\s+(.+)", rest) if rest else []
                    desc = "; ".join(d.strip() for d in desc_items)

                    plan.append(
                        {
                            "step": int(step_num),
                            "title": title,
                            "effort": step_effort,
                            "impact": step_impact,
                            "desc": desc,
                        }
                    )
                    i += 2
            result["refactor_plan"] = plan
    except Exception:  # noqa: S110
        pass

    # ── Test Results ──────────────────────────────────────────────
    try:
        # Old format: 611 passed, 0 failed (16.31s)
        test_match = re.search(
            r"(\d+)\s+passed,\s*(\d+)\s+failed(?:,\s*(\d+)\s+skipped)?"
            r".*?\(([\d.]+)s\)",
            text,
        )
        if test_match:
            result["tests"] = {
                "passed": int(test_match.group(1)),
                "failed": int(test_match.group(2)),
                "skipped": int(test_match.group(3)) if test_match.group(3) else 0,
                "duration_sec": float(test_match.group(4)),
            }
        else:
            # New format: **611 passed**, 0 failed + separate duration line
            test_match2 = re.search(
                r"\*\*(\d+)\s+passed\*\*,?\s*(\d+)\s+failed",
                text,
            )
            if test_match2:
                dur_match = re.search(
                    r"(?:Test execution time|execution time):\s*([\d.]+)s",
                    text,
                )
                result["tests"] = {
                    "passed": int(test_match2.group(1)),
                    "failed": int(test_match2.group(2)),
                    "skipped": 0,
                    "duration_sec": float(dur_match.group(1)) if dur_match else 0.0,
                }
        if not result.get("tests"):
            # Table format: | **Passed** | 848 |
            passed_m = re.search(r"\|\s*\*\*Passed\*\*\s*\|\s*(\d+)\s*\|", text)
            failed_m = re.search(r"\|\s*\*\*Failed\*\*\s*\|\s*(\d+)\s*\|", text)
            if passed_m and failed_m:
                skipped_m = re.search(r"\|\s*\*\*Skipped\*\*\s*\|\s*(\d+)\s*\|", text)
                dur_m = re.search(r"\|\s*\*\*Duration\*\*\s*\|\s*([\d.]+)s?\s*\|", text)
                result["tests"] = {
                    "passed": int(passed_m.group(1)),
                    "failed": int(failed_m.group(1)),
                    "skipped": int(skipped_m.group(1)) if skipped_m else 0,
                    "duration_sec": float(dur_m.group(1)) if dur_m else 0.0,
                }
    except Exception:  # noqa: S110
        pass

    # ── CI/CD Quality Gate ────────────────────────────────────────
    try:
        ci_section = re.search(
            r"##\s+CI/CD Quality Gate\s*\n(.*?)(?=\n---|\n## (?!#))",
            text,
            re.DOTALL,
        )
        if ci_section:
            content = ci_section.group(1)

            # Overall status
            status_match = re.search(r"(?:\*\*)?CI Status:?\s*(?:\*\*)?\s*(\w+)", content)
            ci_status = status_match.group(1).strip() if status_match else "UNKNOWN"

            # Parse table rows
            rows = re.findall(
                r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
                content,
            )
            checks = []
            for gate, _threshold, value, status in rows:
                gate = gate.strip()
                if gate and gate != "Gate" and "---" not in gate:
                    ok = "PASS" in status
                    checks.append(
                        {
                            "name": gate,
                            "ok": ok,
                            "value": value.strip(),
                        }
                    )

            result["ci"] = {
                "status": ci_status,
                "checks": checks,
                "verdict_note": f"CI Status: {ci_status}",
            }
        else:
            # New format: ## CI Status: **PASS** with bullet points
            ci_status_match = re.search(
                r"##\s+CI Status:\s*\*\*(\w+)\*\*",
                text,
            )
            if ci_status_match:
                ci_status = ci_status_match.group(1).strip()
                # Find the bullet points after the CI Status heading
                ci_body = re.search(
                    r"##\s+CI Status:\s*\*\*\w+\*\*\s*\n(.*?)(?=\n---|\n## (?!#)|\Z)",
                    text,
                    re.DOTALL,
                )
                ci_passed = ci_status.upper() == "PASS"
                checks = []
                if ci_body:
                    bullets = re.findall(r"-\s+(.+)", ci_body.group(1))
                    for bullet in bullets:
                        checks.append(
                            {
                                "name": bullet.strip(),
                                "ok": ci_passed,
                                "value": "",
                            }
                        )

                result["ci"] = {
                    "status": ci_status,
                    "checks": checks,
                    "verdict_note": f"CI Status: {ci_status}",
                }
    except Exception:  # noqa: S110
        pass

    # ── Security Audit ────────────────────────────────────────────
    try:
        sec_section = re.search(
            r"##\s+Security Audit.*?\n(.*?)(?=\n---|\n## (?!#))",
            text,
            re.DOTALL,
        )
        if sec_section:
            rows = re.findall(
                r"\|\s*([^|]+?)\s*\|\s*\*\*(\w+)\*\*(?:\s*\(([^)]*)\))?\s*\|\s*([^|]*?)\s*\|",
                sec_section.group(1),
            )
            # Fallback: try simpler table pattern
            if not rows:
                rows = re.findall(
                    r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
                    sec_section.group(1),
                )
                security = []
                for check, status, notes in rows:
                    check = check.strip()
                    if check and check != "Check" and "---" not in check:
                        security.append(
                            {
                                "check": check,
                                "status": re.sub(r"\*+", "", status).strip(),
                                "notes": notes.strip(),
                            }
                        )
            else:
                security = []
                for check, status, caveat, notes in rows:
                    check = check.strip()
                    if check and check != "Check" and "---" not in check:
                        full_status = status
                        if caveat:
                            full_status = f"{status} ({caveat})"
                        security.append(
                            {
                                "check": check,
                                "status": full_status,
                                "notes": notes.strip(),
                            }
                        )
            result["security"] = security
    except Exception:  # noqa: S110
        pass

    return result


def _sync_read_text(path: Path, *, max_size: int | None = None) -> tuple[str, int, str]:
    """Read a text file from disk (blocking) and return content with metadata.

    Designed to run via ``asyncio.to_thread`` to avoid blocking the
    event loop. Performs ``stat()`` and ``read_text()`` atomically
    within the same thread to avoid TOCTOU races.

    Args:
        path: File to read.
        max_size: Optional maximum file size in bytes. If the file exceeds
            this limit a ``ValueError`` is raised *before* reading.

    Returns:
        A tuple of ``(content, file_size, modified_at_iso)``.

    Raises:
        ValueError: If the file exceeds *max_size* bytes.
    """
    stat = path.stat()
    file_size = stat.st_size
    modified_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()

    if max_size is not None and file_size > max_size:
        raise ValueError(
            f"File size ({file_size} bytes) exceeds maximum allowed ({max_size} bytes)"
        )

    content = path.read_text(encoding="utf-8")
    return content, file_size, modified_at


async def handle_reports_markdown(request: web.Request) -> web.Response:
    """Read ``bug-hunter-report.md`` from the reports directory.

    Returns the raw markdown string, file size, and modification time
    inside the standard response envelope.
    """
    start = time.monotonic()
    reports_dir: Path | None = request.app.get("reports_dir")

    if reports_dir is None or not reports_dir.is_dir():
        return _error_envelope(
            "Reports directory not found or not configured",
            code="NOT_FOUND_REPORTS_DIR",
        )

    report_path = reports_dir / "bug-hunter-report.md"
    if not report_path.is_file():
        return _error_envelope(
            "Report file not found: bug-hunter-report.md",
            code="NOT_FOUND_REPORT_FILE",
        )

    try:
        markdown, file_size, modified_at = await asyncio.to_thread(_sync_read_text, report_path)
    except OSError as exc:
        return _error_envelope(
            f"Failed to read report file: {exc}",
            code="IO_READ_ERROR",
            status=500,
        )

    elapsed = int((time.monotonic() - start) * 1000)
    return _json_ok(
        {
            "markdown": markdown,
            "file_size": file_size,
            "modified_at": modified_at,
        },
        duration_ms=elapsed,
    )


async def handle_reports_history(request: web.Request) -> web.Response:
    """Read and parse ``history.json`` from the reports directory.

    Returns the parsed JSON array of scan objects and a count.
    """
    start = time.monotonic()
    reports_dir: Path | None = request.app.get("reports_dir")

    if reports_dir is None or not reports_dir.is_dir():
        return _error_envelope(
            "Reports directory not found or not configured",
            code="NOT_FOUND_REPORTS_DIR",
        )

    history_path = reports_dir / "history.json"
    if not history_path.is_file():
        return _error_envelope(
            "History file not found: history.json",
            code="NOT_FOUND_REPORT_FILE",
        )

    try:
        raw, _, _ = await asyncio.to_thread(_sync_read_text, history_path, max_size=50_000_000)
        history = json.loads(raw)
    except json.JSONDecodeError as exc:
        return _error_envelope(
            f"Failed to read or parse history file: {exc}",
            code="IO_READ_ERROR",
            status=500,
        )
    except ValueError as exc:
        return _error_envelope(
            f"History file too large: {exc}",
            code="VALIDATION_CONSTRAINT",
            status=413,
        )
    except OSError as exc:
        return _error_envelope(
            f"Failed to read or parse history file: {exc}",
            code="IO_READ_ERROR",
            status=500,
        )

    if not isinstance(history, list):
        return _error_envelope(
            "history.json must contain a JSON array",
            code="VALIDATION_INVALID_TYPE",
            status=500,
        )

    elapsed = int((time.monotonic() - start) * 1000)
    return _json_ok(
        {"history": history, "count": len(history)},
        duration_ms=elapsed,
    )


async def handle_reports_summary(request: web.Request) -> web.Response:
    """Compute a summary from ``history.json`` for the overview card.

    Returns whether reports are available, the latest scan entry,
    a trend direction (improving/declining/stable), and the current
    health score.
    """
    start = time.monotonic()
    reports_dir: Path | None = request.app.get("reports_dir")

    if reports_dir is None or not reports_dir.is_dir():
        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {
                "available": False,
                "latest": None,
                "trend": "unknown",
                "health_score": None,
            },
            duration_ms=elapsed,
        )

    history_path = reports_dir / "history.json"
    if not history_path.is_file():
        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {
                "available": False,
                "latest": None,
                "trend": "unknown",
                "health_score": None,
            },
            duration_ms=elapsed,
        )

    try:
        raw, _, _ = await asyncio.to_thread(_sync_read_text, history_path)
        history = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {
                "available": False,
                "latest": None,
                "trend": "unknown",
                "health_score": None,
            },
            duration_ms=elapsed,
        )

    if not isinstance(history, list) or len(history) == 0:
        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {
                "available": False,
                "latest": None,
                "trend": "unknown",
                "health_score": None,
            },
            duration_ms=elapsed,
        )

    latest = history[-1]
    health_score = latest.get("health")

    # Determine trend from the last two entries
    trend = "stable"
    if len(history) >= 2:
        prev = history[-2]
        prev_health = prev.get("health", 0)
        curr_health = latest.get("health", 0)
        if curr_health > prev_health:
            trend = "improving"
        elif curr_health < prev_health:
            trend = "declining"

    elapsed = int((time.monotonic() - start) * 1000)
    return _json_ok(
        {
            "available": True,
            "latest": latest,
            "trend": trend,
            "health_score": health_score,
        },
        duration_ms=elapsed,
    )


async def handle_reports_full(request: web.Request) -> web.Response:
    """Return a full structured bug report combining markdown and history data.

    Reads ``bug-hunter-report.md`` and ``history.json`` from the reports
    directory and returns a structured response matching the BUG_REPORT
    shape expected by the React frontend.

    When the reports directory is not configured, returns
    ``{"available": false, "message": "Reports directory not configured"}``.
    """
    start = time.monotonic()
    reports_dir: Path | None = request.app.get("reports_dir")

    if reports_dir is None or not reports_dir.is_dir():
        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {"available": False, "message": "Reports directory not configured"},
            duration_ms=elapsed,
        )

    # Read markdown report
    report_path = reports_dir / "bug-hunter-report.md"
    markdown: str | None = None
    markdown_modified_at: str | None = None
    if report_path.is_file():
        try:
            markdown, _, markdown_modified_at = await asyncio.to_thread(
                _sync_read_text, report_path
            )
        except OSError:
            markdown = None

    # Read history
    history_path = reports_dir / "history.json"
    history: list[dict[str, Any]] = []
    if history_path.is_file():
        try:
            raw, _, _ = await asyncio.to_thread(_sync_read_text, history_path, max_size=50_000_000)
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                history = parsed
        except (OSError, json.JSONDecodeError, ValueError):
            history = []

    # Compute summary fields from history
    latest = history[-1] if history else {}
    health_score = latest.get("health")
    total_bugs = latest.get("bugs", 0)
    code_smells = latest.get("smells", 0)

    # Determine trend
    trend_direction = "stable"
    previous_score: int | None = None
    current_score = health_score
    change = 0
    if len(history) >= 2:
        previous_score = history[-2].get("health", 0)
        if current_score is not None and previous_score is not None:
            change = current_score - previous_score
            if current_score > previous_score:
                trend_direction = "improving"
            elif current_score < previous_score:
                trend_direction = "declining"

    # Determine rating from health score
    if health_score is not None:
        if health_score >= 90:
            rating = "Excellent"
        elif health_score >= 80:
            rating = "Good"
        elif health_score >= 60:
            rating = "Moderate"
        else:
            rating = "Poor"
    else:
        rating = "Unknown"

    result: dict[str, Any] = {
        "available": True,
        "generated_at": markdown_modified_at,
        "summary": {
            "total_bugs": total_bugs,
            "code_smells": code_smells,
            "health_score": health_score,
            "rating": rating,
        },
        "trend": {
            "previous_score": previous_score,
            "current_score": current_score,
            "change": change,
            "direction": trend_direction,
            "history": history,
        },
        "markdown": markdown,
    }

    # Merge structured data parsed from the markdown report
    if markdown is not None:
        try:
            parsed = _parse_bug_report_markdown(markdown)
            result["bugs"] = parsed["bugs"]
            result["smells"] = parsed["smells"]
            result["health_breakdown"] = parsed["health_breakdown"]
            result["architecture"] = parsed["architecture"]
            result["structure"] = parsed["structure"]
            result["refactor_plan"] = parsed["refactor_plan"]
            result["tests"] = parsed["tests"]
            result["ci"] = parsed["ci"]
            result["security"] = parsed["security"]
            result["project"] = parsed["project"]
            result["date"] = parsed["date"]
            result["analyzer"] = parsed["analyzer"]
            result["branch"] = parsed["branch"]
            result["commit"] = parsed["commit"]

            # Use parsed health score if more accurate than history-derived
            if parsed["health_score"] is not None:
                result["summary"]["health_score"] = parsed["health_score"]
                if parsed["health_rating"]:
                    result["summary"]["rating"] = parsed["health_rating"]
            if parsed["ci"] and parsed["ci"].get("status"):
                result["summary"]["ci_status"] = parsed["ci"]["status"]
            result["summary"]["total_bugs"] = len(parsed["bugs"])
            result["summary"]["code_smells"] = len(parsed["smells"])
        except Exception:
            logger.debug("Failed to parse bug report markdown", exc_info=True)

    elapsed = int((time.monotonic() - start) * 1000)
    return _json_ok(result, duration_ms=elapsed)
