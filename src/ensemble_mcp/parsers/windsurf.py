"""Windsurf (Codeium) session parser — **stub**.

Windsurf stores cascade (conversation) session data locally as encrypted
Protocol Buffer files that cannot be parsed without Codeium's decryption
key.

Known data locations
--------------------
- ``~/.codeium/windsurf/cascade/<uuid>.pb``
    Binary Protocol Buffer files (0.4–2.1 MB each), one per cascade
    session.  Shannon entropy analysis shows **7.98 out of 8.0 bits** —
    effectively random data, confirming the files are encrypted.
    All 256 byte values appear with near-uniform frequency.

- ``~/.codeium/windsurf/implicit/<uuid>.pb``
    Additional encrypted protobuf files (implicit context/state).

- ``~/.codeium/windsurf/code_tracker/``
    Code tracking files containing markdown plan descriptions — no token
    data.

- ``~/.config/Windsurf/User/globalStorage/state.vscdb``
    VS Code key-value store.  ``chat.ChatSessionStore.index`` is present
    but typically has ``{"version": 1, "entries": {}}``.  Auth keys like
    ``windsurf_auth-<email>-usages`` hold OAuth session info, not token
    counts.

- ``~/.config/Windsurf/User/workspaceStorage/<hash>/state.vscdb``
    Per-workspace stores with ``windsurf.cascadeViewContainerId.state``
    (UI layout data) — no token usage.

Why parsing is not feasible
---------------------------
Windsurf encrypts its cascade session data.  The ``.pb`` files in
``~/.codeium/windsurf/cascade/`` are Protocol Buffer messages processed
through an encryption layer (not just standard protobuf serialization).
Without Codeium's encryption key or schema definitions, the content
cannot be decoded.  No readable model names, token counts, or timestamps
are present in the raw bytes.

Future support
--------------
If Codeium adds an unencrypted export format, publishes their protobuf
schema, or exposes token data via a local API, this stub can be upgraded
to a full parser following the pattern in
:mod:`ensemble_mcp.parsers.claude_code`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..config.defaults import WINDSURF_CASCADE_DIR, WINDSURF_CONFIG_DIR

__all__ = [
    "TOOL_NAME",
    "UNSUPPORTED_REASON",
    "detect",
    "parse_latest_session",
]

logger = logging.getLogger(__name__)

TOOL_NAME = "windsurf"

UNSUPPORTED_REASON = (
    "Windsurf encrypts cascade session data in ~/.codeium/windsurf/cascade/*.pb "
    "(Protocol Buffer files with Shannon entropy 7.98/8.0 = encrypted). "
    "Token usage cannot be extracted without Codeium's decryption key."
)

DATA_PATHS: dict[str, Path] = {
    "cascade_dir": WINDSURF_CASCADE_DIR,
    "config_dir": WINDSURF_CONFIG_DIR,
}


def detect(
    *,
    cascade_dir: Path | None = None,
    config_dir: Path | None = None,
) -> bool:
    """Check whether Windsurf is installed and has cascade data.

    Returns *True* if the Windsurf cascade directory or config directory
    exists — **not** that token data is available for parsing.
    """
    cd = cascade_dir or WINDSURF_CASCADE_DIR
    cfg = config_dir or WINDSURF_CONFIG_DIR
    return cd.is_dir() or cfg.is_dir()


def parse_latest_session(
    *,
    cascade_dir: Path | None = None,  # noqa: ARG001
    project_path: str | None = None,  # noqa: ARG001
) -> None:
    """Attempt to parse the latest Windsurf session — always returns *None*.

    Windsurf cascade files are encrypted and cannot be parsed.  This stub
    exists so that the parser dispatcher can report a clear, actionable
    message rather than a generic "unknown tool" warning.
    """
    logger.warning(
        "Windsurf parser: %s",
        UNSUPPORTED_REASON,
    )
    return None
