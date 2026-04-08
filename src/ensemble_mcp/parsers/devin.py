"""Devin CLI session parser — **stub**.

Devin CLI (by Cognition Labs) is a cloud-first AI agent.  The local CLI
is a thin client that proxies all work to Devin's cloud servers.  Session
data and token usage live entirely on the server side.

Known data locations
--------------------
- ``~/.config/cognition/config.json``
    Minimal local configuration with only ``shell.setup_complete`` (bool)
    and ``theme_mode`` (string).  No session data, no token counts.

- ``devin list``
    Lists sessions from the **server** (not local files).  Returns
    "No previous sessions found in this directory" when no server-side
    sessions match the current project path.

- ``~/.devin/`` (if present)
    May contain MCP configuration (``mcp.json``) and skill files, but
    no session conversation data.

Why parsing is not feasible
---------------------------
Devin is architecturally cloud-only.  The CLI authenticates via
``devin auth`` and sends prompts to Cognition's API.  All conversation
history, token usage, and billing data live on Devin's servers.  The local
filesystem contains only authentication state, tool configuration, and UI
preferences — zero session content or token metrics.

Future support
--------------
If Cognition adds a local export command (e.g. ``devin export --format
jsonl``) or starts logging token usage to ``~/.config/cognition/``, this
stub can be upgraded to a full parser following the pattern in
:mod:`ensemble_mcp.parsers.opencode`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..config.defaults import DEVIN_CONFIG_DIR

__all__ = [
    "TOOL_NAME",
    "UNSUPPORTED_REASON",
    "detect",
    "parse_latest_session",
]

logger = logging.getLogger(__name__)

TOOL_NAME = "devin"

UNSUPPORTED_REASON = (
    "Devin CLI is a cloud-first agent — session data and token usage "
    "live entirely on Cognition's servers. The local ~/.config/cognition/ "
    "directory contains only shell setup and theme preferences."
)

DATA_PATHS: dict[str, Path] = {
    "config_dir": DEVIN_CONFIG_DIR,
}


def detect(
    *,
    config_dir: Path | None = None,
) -> bool:
    """Check whether Devin CLI is installed.

    Returns *True* if the Cognition config directory exists — **not**
    that session data is available for parsing (it never is locally).
    """
    cd = config_dir or DEVIN_CONFIG_DIR
    return cd.is_dir()


def parse_latest_session(
    *,
    config_dir: Path | None = None,  # noqa: ARG001
    project_path: str | None = None,  # noqa: ARG001
) -> None:
    """Attempt to parse the latest Devin session — always returns *None*.

    Devin session data is cloud-only.  This stub exists so that the
    parser dispatcher can report a clear, actionable message rather than
    a generic "unknown tool" warning.
    """
    logger.warning(
        "Devin parser: %s",
        UNSUPPORTED_REASON,
    )
    return None
