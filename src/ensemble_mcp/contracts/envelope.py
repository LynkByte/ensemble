"""Standard tool response/error envelope.

All MCP tools return a normalized envelope:
  {ok, data, error, meta: {duration_ms, source, confidence}}

Usage:
    # Success
    return success_envelope({"matches": results}, source="sqlite")

    # Error (via ToolError exception caught by the wrapper)
    raise ToolError(code=ErrorCode.NOT_FOUND_SESSION, message="...")

    # Automatic timing via the @tool_handler decorator
    @tool_handler(source="sqlite")
    async def patterns_search(...) -> dict: ...
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .errors import ToolError


@dataclass(slots=True)
class Meta:
    """Metadata attached to every tool response."""

    duration_ms: int = 0
    source: str = "local"
    confidence: str = "exact"


@dataclass(slots=True)
class ToolResponse:
    """Standardized response envelope returned by all MCP tools."""

    ok: bool
    data: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    meta: Meta = field(default_factory=Meta)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for MCP transport."""
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "meta": {
                "duration_ms": self.meta.duration_ms,
                "source": self.meta.source,
                "confidence": self.meta.confidence,
            },
        }


def success_envelope(
    data: dict[str, Any],
    *,
    source: str = "local",
    confidence: str = "exact",
    duration_ms: int = 0,
) -> dict[str, Any]:
    """Build a success envelope dict."""
    return ToolResponse(
        ok=True,
        data=data,
        error=None,
        meta=Meta(duration_ms=duration_ms, source=source, confidence=confidence),
    ).to_dict()


def error_envelope(
    error: ToolError,
    *,
    source: str = "local",
    confidence: str = "exact",
    duration_ms: int = 0,
) -> dict[str, Any]:
    """Build an error envelope dict from a ToolError."""
    return ToolResponse(
        ok=False,
        data=None,
        error=error.to_dict(),
        meta=Meta(duration_ms=duration_ms, source=source, confidence=confidence),
    ).to_dict()


def tool_handler(
    *,
    source: str = "local",
    confidence: str = "exact",
) -> Callable:  # type: ignore[type-arg]
    """Decorator that wraps a tool function with timing and error handling.

    The wrapped function should return a ``dict`` (the *data* payload).
    The decorator produces the full envelope automatically.

    If the function raises :class:`ToolError`, it is caught and converted
    to an error envelope.  Unexpected exceptions become INTERNAL_ERROR.
    """

    def decorator(fn):  # noqa: ANN001, ANN202
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            start = time.monotonic()
            try:
                result = await fn(*args, **kwargs)
                elapsed = int((time.monotonic() - start) * 1000)

                # Allow the tool to override confidence/source via
                # special keys in the returned dict.
                effective_confidence = result.pop("__confidence__", confidence)
                effective_source = result.pop("__source__", source)

                return success_envelope(
                    result,
                    source=effective_source,
                    confidence=effective_confidence,
                    duration_ms=elapsed,
                )
            except ToolError as exc:
                elapsed = int((time.monotonic() - start) * 1000)
                return error_envelope(
                    exc,
                    source=source,
                    confidence=confidence,
                    duration_ms=elapsed,
                )
            except Exception as exc:
                elapsed = int((time.monotonic() - start) * 1000)
                from .errors import internal_error

                err = internal_error(str(exc))
                return error_envelope(
                    err,
                    source=source,
                    confidence=confidence,
                    duration_ms=elapsed,
                )

        return wrapper

    return decorator
