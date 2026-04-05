"""MCP server setup and tool registration.

Registers all 21 tools with the MCP protocol and runs the stdio server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .config.defaults import SERVER_NAME, SERVER_VERSION
from .memory.store import VectorStore
from .security.trust import require_confirmation
from .tools import (
    drift,
    indexer,
    metrics,
    patterns,
    routing,
    session,
    skills,
)
from .tools.mcp_tracking import record_mcp_call

logger = logging.getLogger(__name__)

# ── Global state (initialized on serve) ──────────────────────────
_store: VectorStore | None = None


def _get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


# ── Tool definitions ─────────────────────────────────────────────

TOOL_DEFINITIONS: list[Tool] = [
    # ── Patterns ──
    Tool(
        name="patterns_search",
        description="Search stored patterns by semantic similarity. Returns top-K matches.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Semantic search query"},
                "top_k": {"type": "integer", "default": 3, "description": "Max results"},
                "project": {"type": "string", "description": "Optional project scope"},
                "idempotency_key": {"type": "string", "description": "Optional idempotency key"},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="patterns_store",
        description="Store a new pattern from a successful pipeline for future semantic search.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short pattern name"},
                "context": {"type": "string", "description": "When this pattern applies"},
                "approach": {"type": "string", "description": "What approach was used"},
                "outcome": {"type": "string", "description": "What happened (success/failure)"},
                "project": {"type": "string", "description": "Optional project scope"},
                "idempotency_key": {"type": "string", "description": "Optional idempotency key"},
            },
            "required": ["name", "context", "approach", "outcome"],
        },
    ),
    Tool(
        name="patterns_prune",
        description="Remove old/unused patterns (zero match_count, older than max_age_days).",
        inputSchema={
            "type": "object",
            "properties": {
                "max_age_days": {"type": "integer", "default": 90},
                "min_score": {"type": "number", "default": 0.3},
                "idempotency_key": {"type": "string"},
            },
        },
    ),
    # ── Metrics ──
    Tool(
        name="metrics_start_session",
        description="Start tracking a pipeline session. Returns a session_id.",
        inputSchema={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Task description"},
                "classification": {
                    "type": "string",
                    "description": "trivial/simple/standard/complex",
                },
                "ai_tool": {"type": "string", "description": "opencode/claude-code/copilot/etc"},
                "project": {"type": "string", "description": "Project path"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["task", "classification"],
        },
    ),
    Tool(
        name="metrics_record_step",
        description=(
            "Record per-agent token/cost usage for a pipeline step. "
            "Supports 3-tier source precedence: "
            "direct fields > usage_raw payload > tiktoken estimation."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "agent": {"type": "string", "description": "Agent name (ensemble/scope/craft/etc)"},
                "input_tokens": {"type": "integer"},
                "output_tokens": {"type": "integer"},
                "cache_read_tokens": {"type": "integer"},
                "cache_write_tokens": {"type": "integer"},
                "web_search_requests": {"type": "integer"},
                "cached_tokens": {"type": "integer"},
                "usage_raw": {
                    "type": "object",
                    "description": (
                        "Raw provider/runtime usage payload (Anthropic or OpenAI format). "
                        "Auto-detected. Overridden by explicit token fields."
                    ),
                },
                "provider": {
                    "type": "string",
                    "description": (
                        "Provider hint: 'anthropic' or 'openai'. Auto-detected if omitted."
                    ),
                },
                "model": {"type": "string"},
                "source": {
                    "type": "string",
                    "description": (
                        "Source label: live_response_usage/session_parser/estimator/hybrid"
                    ),
                },
                "confidence": {
                    "type": "string",
                    "description": "Confidence: exact/partial/estimated",
                },
                "input_text": {
                    "type": "string",
                    "description": (
                        "Input text for tiktoken estimation fallback (when no token counts)."
                    ),
                },
                "output_text": {
                    "type": "string",
                    "description": (
                        "Output text for tiktoken estimation fallback (when no token counts)."
                    ),
                },
                "duration_ms": {"type": "integer"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["session_id", "agent"],
        },
    ),
    Tool(
        name="metrics_end_session",
        description="Finalize a session, compute totals.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "status": {"type": "string", "default": "completed"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="metrics_session_report",
        description="Generate a formatted session report with per-agent breakdown.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="metrics_trend",
        description="Cost/token trends over the last N days.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 30},
            },
        },
    ),
    Tool(
        name="metrics_compare",
        description="Compare two sessions side by side.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id_a": {"type": "string"},
                "session_id_b": {"type": "string"},
            },
            "required": ["session_id_a", "session_id_b"],
        },
    ),
    # ── Drift ──
    Tool(
        name="drift_check",
        description="Check if code changes drift from the original task. Returns 0-1 drift score.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_description": {"type": "string"},
                "changed_files": {"type": "array", "items": {"type": "string"}},
                "diff_summary": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["task_description", "changed_files", "diff_summary"],
        },
    ),
    # ── Routing ──
    Tool(
        name="model_recommend",
        description="Recommend a model tier (best/mid/cheapest) for an agent and task.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "Agent name"},
                "task_classification": {
                    "type": "string",
                    "description": "trivial/simple/standard/complex",
                },
                "task_description": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["agent", "task_classification"],
        },
    ),
    # ── Skills ──
    Tool(
        name="skills_discover",
        description=(
            "Scan tool-native skill locations and return relevant skills via semantic search."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "query": {"type": "string", "description": "Optional semantic search query"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["project_path"],
        },
    ),
    Tool(
        name="skills_suggest",
        description="Detect recurring patterns and suggest them as reusable skills.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "min_cluster_size": {"type": "integer", "default": 3},
                "stale_threshold_days": {"type": "integer", "default": 60},
                "idempotency_key": {"type": "string"},
            },
            "required": ["project_path"],
        },
    ),
    Tool(
        name="skills_generate",
        description="Accept, dismiss, or defer a skill suggestion.",
        inputSchema={
            "type": "object",
            "properties": {
                "suggestion_id": {"type": "integer"},
                "action": {"type": "string", "enum": ["accept", "dismiss", "defer"]},
                "output_dir": {"type": "string", "default": ".ai/skills/"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["suggestion_id"],
        },
    ),
    # ── Session ──
    Tool(
        name="session_save",
        description="Save pipeline checkpoint state with optimistic versioning.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "state": {"type": "object", "description": "Pipeline state to checkpoint"},
                "version": {
                    "type": "integer",
                    "description": "Expected version for optimistic lock",
                },
                "idempotency_key": {"type": "string"},
            },
            "required": ["session_id", "state"],
        },
    ),
    Tool(
        name="session_load",
        description="Load latest or specific pipeline checkpoint.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Load specific session. Omit for latest.",
                },
            },
        },
    ),
    # ── Indexer ──
    Tool(
        name="project_index",
        description="Build or refresh the codebase index for faster Scope exploration.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "force": {"type": "boolean", "default": False},
                "idempotency_key": {"type": "string"},
            },
            "required": ["project_path"],
        },
    ),
    Tool(
        name="project_query",
        description="Query the project index — find files by type, path, or semantic query.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "query": {"type": "string"},
                "file_types": {"type": "array", "items": {"type": "string"}},
                "path_pattern": {"type": "string"},
            },
            "required": ["project_path"],
        },
    ),
    Tool(
        name="project_dependencies",
        description="Get import/dependency graph for a specific file.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "file_path": {"type": "string"},
            },
            "required": ["project_path", "file_path"],
        },
    ),
    # ── Utility ──
    Tool(
        name="health",
        description="Server health check — status, version, DB size, pattern count.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="reset",
        description="Reset all stored data (destructive). Requires confirm=true.",
        inputSchema={
            "type": "object",
            "properties": {
                "confirm": {"type": "boolean", "description": "Must be true to proceed"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["confirm"],
        },
    ),
]


# ── Tool dispatch ─────────────────────────────────────────────────


async def _dispatch_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Route a tool call to the appropriate handler."""
    store = _get_store()
    conn = store.conn
    model = store.model

    match name:
        # Patterns
        case "patterns_search":
            return await patterns.patterns_search(store, **arguments)
        case "patterns_store":
            return await patterns.patterns_store(store, **arguments)
        case "patterns_prune":
            return await patterns.patterns_prune(store, **arguments)

        # Metrics
        case "metrics_start_session":
            return await metrics.metrics_start_session(conn, **arguments)
        case "metrics_record_step":
            return await metrics.metrics_record_step(conn, **arguments)
        case "metrics_end_session":
            return await metrics.metrics_end_session(conn, **arguments)
        case "metrics_session_report":
            return await metrics.metrics_session_report(conn, **arguments)
        case "metrics_trend":
            return await metrics.metrics_trend(conn, **arguments)
        case "metrics_compare":
            return await metrics.metrics_compare(conn, **arguments)

        # Drift
        case "drift_check":
            return await drift.drift_check(model, conn, **arguments)

        # Routing
        case "model_recommend":
            return await routing.model_recommend(conn, **arguments)

        # Skills
        case "skills_discover":
            return await skills.skills_discover(model, conn, **arguments)
        case "skills_suggest":
            return await skills.skills_suggest(model, conn, **arguments)
        case "skills_generate":
            return await skills.skills_generate(conn, **arguments)

        # Session
        case "session_save":
            return await session.session_save(conn, **arguments)
        case "session_load":
            return await session.session_load(conn, **arguments)

        # Indexer
        case "project_index":
            return await indexer.project_index(conn, **arguments)
        case "project_query":
            return await indexer.project_query(conn, **arguments)
        case "project_dependencies":
            return await indexer.project_dependencies(conn, **arguments)

        # Utility
        case "health":
            return _health(store)
        case "reset":
            return await _reset(store, **arguments)

        case _:
            return {
                "ok": False,
                "data": None,
                "error": {
                    "code": "VALIDATION_INVALID_VALUE",
                    "message": f"Unknown tool: {name}",
                    "retryable": False,
                    "details": {"tool": name},
                },
                "meta": {"duration_ms": 0, "source": "local", "confidence": "exact"},
            }


def _health(store: VectorStore) -> dict[str, Any]:
    """Return server health information."""
    from .contracts.envelope import success_envelope

    return success_envelope(
        {
            "status": "ok",
            "version": SERVER_VERSION,
            "db_size_bytes": store.get_db_size_bytes(),
            "pattern_count": store.get_pattern_count(),
            "server_name": SERVER_NAME,
        }
    )


async def _reset(store: VectorStore, *, confirm: bool = False, **_: Any) -> dict[str, Any]:
    """Reset all data."""
    from .contracts.envelope import error_envelope, success_envelope
    from .state.idempotency import check_idempotency, store_idempotency

    idempotency_key = _.get("idempotency_key")
    cached = check_idempotency(store.conn, idempotency_key)
    if cached is not None:
        return success_envelope(cached)

    try:
        require_confirmation(confirm, "reset")
    except Exception as e:
        return error_envelope(e)  # type: ignore[arg-type]

    # Drop all data
    tables = [
        "patterns",
        "steps",
        "mcp_calls",
        "sessions",
        "file_exports",
        "file_imports",
        "project_files",
        "skill_suggestion_patterns",
        "skill_suggestions",
        "skill_usage_tracking",
        "session_checkpoints",
        "idempotency_keys",
    ]
    for table in tables:
        store.conn.execute(f"DELETE FROM {table}")  # noqa: S608
    store.conn.commit()

    result = {"reset": True}
    store_idempotency(store.conn, idempotency_key, result)
    return success_envelope(result)


# ── Server entry point ────────────────────────────────────────────


def serve() -> None:
    """Initialize and run the MCP server via stdio transport."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    app = Server(SERVER_NAME)

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOL_DEFINITIONS

    @app.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        args = arguments or {}
        start = time.monotonic()
        result = await _dispatch_tool(name, args)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        # Record the MCP call in the tracking table
        try:
            store = _get_store()
            record_mcp_call(
                store.conn,
                tool_name=name,
                arguments=args,
                result=result,
                duration_ms=elapsed_ms,
            )
        except Exception:
            # Never let tracking failures break tool calls
            logger.debug("Failed to record MCP call for %s", name, exc_info=True)

        return [TextContent(type="text", text=json.dumps(result, default=str))]

    async def run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )

    asyncio.run(run())
