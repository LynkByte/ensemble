"""GitHub Copilot Chat session parser — **stub**.

GitHub Copilot (VS Code extension) stores chat session metadata locally
but does **not** expose per-message token usage in its local files.

Known data locations
--------------------
- ``~/.config/Code/User/globalStorage/state.vscdb``
    VS Code key-value store containing extension state.  Keys like
    ``github-<user>-usages`` hold OAuth scope info (not token counts).
    ``GitHub.copilot-chat`` contains experiment/feature flag configs.

- ``~/.config/Code/User/workspaceStorage/<hash>/state.vscdb``
    Per-workspace KV stores with ``chat.ChatSessionStore.index`` entries.
    Each session record has ``sessionId``, ``title``, ``timing``
    (start/end timestamps), and ``lastResponseState`` — but **no**
    ``input_tokens``, ``output_tokens``, or cost fields.

- ``~/.config/Code/User/globalStorage/github.copilot-chat/``
    Contains CLI helper binaries, agent definitions (``Plan.agent.md``,
    ``Ask.agent.md``), embedding caches, and session metadata JSON.
    The ``copilotcli.session.metadata.json`` maps session UUIDs to
    ``{writtenToDisc: true}`` flags — no token data.

- ``memento/interactive-session-view-copilot`` (per-workspace)
    Current session state including selected model (``identifier``,
    ``maxInputTokens``, ``maxOutputTokens``) — these are model *limits*,
    not actual consumed tokens.

Why parsing is not feasible
---------------------------
GitHub Copilot proxies all LLM requests through GitHub's API servers.
Token usage and billing are tracked entirely server-side and surfaced via
GitHub's usage dashboard (github.com/settings/billing).  No per-message
token counts are written to the local filesystem.

Future support
--------------
If GitHub adds local token logging (e.g. via VS Code's chat history API
or a new extension storage key), this stub can be upgraded to a full
parser following the pattern in :mod:`ensemble_mcp.parsers.opencode`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..config.defaults import COPILOT_CHAT_DIR, COPILOT_STATE_DB

__all__ = [
    "TOOL_NAME",
    "UNSUPPORTED_REASON",
    "detect",
    "parse_latest_session",
]

logger = logging.getLogger(__name__)

TOOL_NAME = "copilot"

UNSUPPORTED_REASON = (
    "GitHub Copilot does not store per-message token usage locally. "
    "The VS Code state.vscdb has session metadata (titles, timing) "
    "and model selection (maxInputTokens/maxOutputTokens limits), but "
    "actual consumed token counts are tracked server-side via GitHub's API."
)

DATA_PATHS: dict[str, Path] = {
    "chat_dir": COPILOT_CHAT_DIR,
    "state_db": COPILOT_STATE_DB,
}


def detect(
    *,
    chat_dir: Path | None = None,
    state_db: Path | None = None,
) -> bool:
    """Check whether GitHub Copilot Chat is installed and has local data.

    Returns *True* if the Copilot Chat extension directory or VS Code
    state database exists — **not** that token data is available.
    """
    cd = chat_dir or COPILOT_CHAT_DIR
    db = state_db or COPILOT_STATE_DB
    return cd.is_dir() or db.is_file()


def parse_latest_session(
    *,
    chat_dir: Path | None = None,  # noqa: ARG001
    project_path: str | None = None,  # noqa: ARG001
) -> None:
    """Attempt to parse the latest Copilot session — always returns *None*.

    GitHub Copilot does not store token usage locally.  This stub exists
    so that the parser dispatcher can report a clear, actionable message
    rather than a generic "unknown tool" warning.
    """
    logger.warning(
        "GitHub Copilot parser: %s",
        UNSUPPORTED_REASON,
    )
    return None
