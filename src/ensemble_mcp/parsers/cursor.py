"""Cursor session parser — **stub**.

Cursor (by Anysphere) stores AI interaction data locally but does **not**
expose per-message token usage in its local files.

Known data locations
--------------------
- ``~/.cursor/ai-tracking/ai-code-tracking.db``
    SQLite database tracking AI-authored code attribution — tables include
    ``ai_code_hashes``, ``scored_commits``, ``conversation_summaries``,
    ``tracked_file_content``, and ``ai_deleted_files``.  Tracks which lines
    of code were AI-generated (for commit scoring), **not** API token
    consumption.

- ``~/.config/Cursor/User/globalStorage/state.vscdb``
    VS Code key-value store (``ItemTable``) containing Composer session
    headers (``composer.composerHeaders``), UI state, and auth tokens.
    Session headers include metadata (title, mode, lines added/removed)
    but no ``input_tokens`` / ``output_tokens`` fields.

- ``~/.config/Cursor/User/globalStorage/cursorDiskKV``
    Secondary KV table containing serialised Composer data
    (``composerData:<uuid>``).  Structures include conversation context
    (file selections, image selections, terminal selections) but **no**
    token usage counters.

Why parsing is not feasible
---------------------------
Cursor routes LLM requests through Anysphere's proxy servers.  Token usage
and billing are tracked server-side.  None of the local databases or KV
stores contain consumed ``input_tokens``, ``output_tokens``,
``cache_read_tokens``, or ``reasoning_tokens`` values.

Future support
--------------
If Cursor adds local token usage logging (e.g. in ``ai-code-tracking.db``
or a new JSONL file), this stub can be upgraded to a full parser by
implementing ``parse_session()`` and ``parse_latest_session()`` following
the same pattern as :mod:`ensemble_mcp.parsers.opencode`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..config.defaults import CURSOR_AI_TRACKING_DB, CURSOR_CONFIG_DIR

__all__ = [
    "TOOL_NAME",
    "UNSUPPORTED_REASON",
    "detect",
    "parse_latest_session",
]

logger = logging.getLogger(__name__)

TOOL_NAME = "cursor"

UNSUPPORTED_REASON = (
    "Cursor does not store per-message token usage locally. "
    "The ai-code-tracking.db tracks code attribution (AI vs human lines) "
    "and state.vscdb stores Composer session metadata, but neither contains "
    "input_tokens/output_tokens data. Token tracking is server-side."
)

DATA_PATHS: dict[str, Path] = {
    "ai_tracking_db": CURSOR_AI_TRACKING_DB,
    "config_dir": CURSOR_CONFIG_DIR,
}


def detect(
    *,
    ai_tracking_db: Path | None = None,
    config_dir: Path | None = None,
) -> bool:
    """Check whether Cursor is installed and has local data.

    Returns *True* if the Cursor AI tracking database or config directory
    exists — **not** that token data is available for parsing.
    """
    db_path = ai_tracking_db or CURSOR_AI_TRACKING_DB
    cfg_path = config_dir or CURSOR_CONFIG_DIR
    return db_path.is_file() or cfg_path.is_dir()


def parse_latest_session(
    *,
    ai_tracking_db: Path | None = None,  # noqa: ARG001
    project_path: str | None = None,  # noqa: ARG001
) -> None:
    """Attempt to parse the latest Cursor session — always returns *None*.

    Cursor does not store token usage locally.  This stub exists so that
    the parser dispatcher can report a clear, actionable message rather
    than a generic "unknown tool" warning.
    """
    logger.warning(
        "Cursor parser: %s",
        UNSUPPORTED_REASON,
    )
    return None
