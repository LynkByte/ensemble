"""Error taxonomy and helpers.

Standard error classes:
- VALIDATION_*  -- bad input (never retry)
- NOT_FOUND_*   -- missing resource (never retry)
- CONFLICT_*    -- stale version / optimistic lock failure (retry after refresh)
- TIMEOUT_*     -- local operation timeout (retry with backoff)
- IO_*          -- filesystem/db transient errors (retry with backoff)
- INTERNAL_*    -- unexpected server error (retryable only if marked)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Canonical error codes returned by all MCP tools."""

    # VALIDATION — bad input (never retry)
    VALIDATION_MISSING_FIELD = "VALIDATION_MISSING_FIELD"
    VALIDATION_INVALID_VALUE = "VALIDATION_INVALID_VALUE"
    VALIDATION_INVALID_TYPE = "VALIDATION_INVALID_TYPE"
    VALIDATION_CONSTRAINT = "VALIDATION_CONSTRAINT"

    # NOT_FOUND — missing resource (never retry)
    NOT_FOUND_SESSION = "NOT_FOUND_SESSION"
    NOT_FOUND_PATTERN = "NOT_FOUND_PATTERN"
    NOT_FOUND_STEP = "NOT_FOUND_STEP"
    NOT_FOUND_SKILL_SUGGESTION = "NOT_FOUND_SKILL_SUGGESTION"
    NOT_FOUND_FILE = "NOT_FOUND_FILE"
    NOT_FOUND_PROJECT = "NOT_FOUND_PROJECT"
    NOT_FOUND_CHECKPOINT = "NOT_FOUND_CHECKPOINT"

    # CONFLICT — stale version or optimistic lock failure (retry after refresh)
    CONFLICT_VERSION_MISMATCH = "CONFLICT_VERSION_MISMATCH"
    CONFLICT_INVALID_STATE_TRANSITION = "CONFLICT_INVALID_STATE_TRANSITION"
    CONFLICT_DUPLICATE = "CONFLICT_DUPLICATE"
    CONFLICT_ALREADY_RESOLVED = "CONFLICT_ALREADY_RESOLVED"

    # TIMEOUT — local operation timeout (retry with backoff)
    TIMEOUT_EMBEDDING = "TIMEOUT_EMBEDDING"
    TIMEOUT_INDEX = "TIMEOUT_INDEX"
    TIMEOUT_QUERY = "TIMEOUT_QUERY"

    # IO — filesystem/db transient errors (retry with backoff)
    IO_DATABASE = "IO_DATABASE"
    IO_FILESYSTEM = "IO_FILESYSTEM"
    IO_MODEL_DOWNLOAD = "IO_MODEL_DOWNLOAD"

    # INTERNAL — unexpected server error (retryable only if marked)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INTERNAL_SCHEMA_MIGRATION = "INTERNAL_SCHEMA_MIGRATION"


# ── Retry policy per category ─────────────────────────────────────
_NEVER_RETRY: frozenset[str] = frozenset({"VALIDATION", "NOT_FOUND"})
_RETRY_AFTER_REFRESH: frozenset[str] = frozenset({"CONFLICT"})
_RETRY_WITH_BACKOFF: frozenset[str] = frozenset({"TIMEOUT", "IO"})
# INTERNAL is retryable only if explicitly marked


def _category(code: ErrorCode) -> str:
    """Extract the error category prefix (e.g. 'VALIDATION')."""
    return code.value.split("_", 1)[0]


def is_retryable(code: ErrorCode) -> bool:
    """Return default retry guidance for an error code."""
    cat = _category(code)
    if cat in _NEVER_RETRY:
        return False
    return cat in _RETRY_AFTER_REFRESH | _RETRY_WITH_BACKOFF


@dataclass
class ToolError(Exception):
    """Structured error returned inside the MCP envelope."""

    code: ErrorCode
    message: str
    retryable: bool = field(init=False)
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.retryable = is_retryable(self.code)
        Exception.__init__(self, self.message)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the JSON envelope."""
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


# ── Convenience constructors ──────────────────────────────────────


def validation_error(
    message: str,
    *,
    code: ErrorCode = ErrorCode.VALIDATION_INVALID_VALUE,
    **details: Any,
) -> ToolError:
    return ToolError(code=code, message=message, details=details)


def not_found_error(
    message: str,
    *,
    code: ErrorCode = ErrorCode.NOT_FOUND_SESSION,
    **details: Any,
) -> ToolError:
    return ToolError(code=code, message=message, details=details)


def conflict_error(
    message: str,
    *,
    code: ErrorCode = ErrorCode.CONFLICT_VERSION_MISMATCH,
    **details: Any,
) -> ToolError:
    return ToolError(code=code, message=message, details=details)


def timeout_error(
    message: str,
    *,
    code: ErrorCode = ErrorCode.TIMEOUT_EMBEDDING,
    **details: Any,
) -> ToolError:
    return ToolError(code=code, message=message, details=details)


def io_error(
    message: str,
    *,
    code: ErrorCode = ErrorCode.IO_DATABASE,
    **details: Any,
) -> ToolError:
    return ToolError(code=code, message=message, details=details)


def internal_error(
    message: str,
    *,
    code: ErrorCode = ErrorCode.INTERNAL_ERROR,
    **details: Any,
) -> ToolError:
    return ToolError(code=code, message=message, details=details)
