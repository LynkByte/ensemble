"""MCP server setup and tool registration.

Registers all 16 tools with the MCP protocol and runs the stdio server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, cast

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .config.defaults import SERVER_NAME, SERVER_VERSION
from .memory.store import VectorStore
from .security.trust import require_confirmation
from .tools import (
    compress,
    drift,
    indexer,
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
    # ── Compress ──
    Tool(
        name="context_compress",
        description=(
            "Compress verbose natural language text into terse, token-efficient form "
            "while preserving all technical content (code, URLs, paths, headings). "
            "Rule-based, zero LLM calls."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to compress",
                },
                "idempotency_key": {"type": "string", "description": "Optional idempotency key"},
            },
            "required": ["text"],
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
            return cast(dict[str, Any], await patterns.patterns_search(store, **arguments))
        case "patterns_store":
            return cast(dict[str, Any], await patterns.patterns_store(store, **arguments))
        case "patterns_prune":
            return cast(dict[str, Any], await patterns.patterns_prune(store, **arguments))

        # Drift
        case "drift_check":
            return cast(dict[str, Any], await drift.drift_check(model, conn, **arguments))

        # Routing
        case "model_recommend":
            return cast(dict[str, Any], await routing.model_recommend(conn, **arguments))

        # Skills
        case "skills_discover":
            return cast(dict[str, Any], await skills.skills_discover(model, conn, **arguments))
        case "skills_suggest":
            return cast(dict[str, Any], await skills.skills_suggest(model, conn, **arguments))
        case "skills_generate":
            return cast(dict[str, Any], await skills.skills_generate(conn, **arguments))

        # Session
        case "session_save":
            return cast(dict[str, Any], await session.session_save(conn, **arguments))
        case "session_load":
            return cast(dict[str, Any], await session.session_load(conn, **arguments))

        # Indexer
        case "project_index":
            return cast(dict[str, Any], await indexer.project_index(conn, **arguments))
        case "project_query":
            return cast(dict[str, Any], await indexer.project_query(conn, **arguments))
        case "project_dependencies":
            return cast(dict[str, Any], await indexer.project_dependencies(conn, **arguments))

        # Utility
        case "health":
            return _health(store)
        case "reset":
            return await _reset(store, **arguments)

        # Compress
        case "context_compress":
            return cast(dict[str, Any], await compress.context_compress(conn, **arguments))

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

    # Show startup banner on stderr (stdout is reserved for MCP protocol)
    from .cli.banner import print_banner

    print_banner()

    app = Server(SERVER_NAME)

    @app.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def list_tools() -> list[Tool]:
        return TOOL_DEFINITIONS

    @app.call_tool()  # type: ignore[untyped-decorator]
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
