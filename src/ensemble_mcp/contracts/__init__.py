"""Contract layer: standardized tool response/error envelope."""

from .envelope import (
    Meta,
    ToolResponse,
    error_envelope,
    success_envelope,
    tool_handler,
)
from .errors import (
    ErrorCode,
    ToolError,
    conflict_error,
    internal_error,
    io_error,
    not_found_error,
    timeout_error,
    validation_error,
)

__all__ = [
    "ErrorCode",
    "Meta",
    "ToolError",
    "ToolResponse",
    "conflict_error",
    "error_envelope",
    "internal_error",
    "io_error",
    "not_found_error",
    "success_envelope",
    "timeout_error",
    "tool_handler",
    "validation_error",
]
