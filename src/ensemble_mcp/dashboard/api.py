"""JSON API endpoints for the ensemble-mcp dashboard.

All endpoints are read-only (GET) and return the standard
``{ok, data, error, meta}`` envelope. Each handler opens its own
read-only SQLite connection so the MCP server is never blocked.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from aiohttp import web

from ..config.defaults import DB_PATH, SERVER_NAME, SERVER_VERSION
from ..state.locks import get_connection

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────


def _get_conn(request: web.Request) -> sqlite3.Connection:
    """Open a read-only WAL connection to the dashboard DB."""
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


def _parse_int(value: str | None, default: int) -> int:
    """Parse a query param as int, falling back to default."""
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


# ── Route registration ────────────────────────────────────────────


def register_api_routes(app: web.Application) -> None:
    """Add all /api/* routes to the application."""
    app.router.add_get("/api/summary", handle_summary)
    app.router.add_get("/api/patterns", handle_patterns)
    app.router.add_get("/api/patterns/{id}", handle_pattern_detail)
    app.router.add_get("/api/skills", handle_skills)
    app.router.add_get("/api/skills/stale", handle_skills_stale)
    app.router.add_get("/api/projects", handle_projects)
    app.router.add_get("/api/projects/{path:.+}", handle_project_detail)
    app.router.add_get("/api/drift", handle_drift)
    app.router.add_get("/api/sessions", handle_sessions)
    app.router.add_get("/api/sessions/{id}", handle_session_detail)
    app.router.add_get("/api/health", handle_health)


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
            },
            duration_ms=elapsed,
        )
    finally:
        conn.close()


async def handle_patterns(request: web.Request) -> web.Response:
    """Paginated pattern list."""
    start = time.monotonic()
    project = request.query.get("project")
    limit = _parse_int(request.query.get("limit"), 50)
    offset = _parse_int(request.query.get("offset"), 0)
    conn = _get_conn(request)
    try:
        if project:
            rows = conn.execute(
                "SELECT id, name, context, approach, outcome, project, "
                "created_at, last_matched_at, match_count "
                "FROM patterns WHERE project = ? OR project IS NULL "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (project, limit, offset),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) FROM patterns WHERE project = ? OR project IS NULL",
                (project,),
            ).fetchone()[0]
        else:
            rows = conn.execute(
                "SELECT id, name, context, approach, outcome, project, "
                "created_at, last_matched_at, match_count "
                "FROM patterns ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]

        patterns = [
            {
                "id": r["id"],
                "name": r["name"],
                "context": r["context"],
                "approach": r["approach"],
                "outcome": r["outcome"],
                "project": r["project"],
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
            "SELECT id, name, context, approach, outcome, project, "
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
                "SELECT skill_path, project, first_seen_at, last_matched_at, match_count "
                "FROM skill_usage_tracking WHERE project = ? "
                "ORDER BY last_matched_at DESC",
                (project,),
            ).fetchall()
        else:
            tracked_rows = conn.execute(
                "SELECT skill_path, project, first_seen_at, last_matched_at, match_count "
                "FROM skill_usage_tracking ORDER BY last_matched_at DESC"
            ).fetchall()

        tracked = [
            {
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
            "SELECT session_id, state_json, version, created_at "
            "FROM session_checkpoints "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()

        total = conn.execute("SELECT COUNT(*) FROM session_checkpoints").fetchone()[0]

        sessions = []
        for r in rows:
            state = json.loads(r["state_json"])
            # Best-effort status extraction from state_json
            status = state.get("status", state.get("state", "unknown"))
            sessions.append(
                {
                    "session_id": r["session_id"],
                    "status": status,
                    "version": r["version"],
                    "created_at": r["created_at"],
                }
            )

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
            "SELECT session_id, state_json, version, created_at "
            "FROM session_checkpoints WHERE session_id = ?",
            (session_id,),
        ).fetchone()

        if not row:
            return _error_envelope(f"Session '{session_id}' not found")

        state = json.loads(row["state_json"])
        elapsed = int((time.monotonic() - start) * 1000)
        return _json_ok(
            {
                "session_id": row["session_id"],
                "state": state,
                "version": row["version"],
                "created_at": row["created_at"],
            },
            duration_ms=elapsed,
        )
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
