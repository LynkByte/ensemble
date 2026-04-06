"""Tests for contracts: envelope, errors, and ToolError."""

from __future__ import annotations

import pytest

from ensemble_mcp.contracts.envelope import (
    Meta,
    ToolResponse,
    error_envelope,
    success_envelope,
    tool_handler,
)
from ensemble_mcp.contracts.errors import (
    ErrorCode,
    ToolError,
    conflict_error,
    internal_error,
    io_error,
    is_retryable,
    not_found_error,
    timeout_error,
    validation_error,
)

# ── ErrorCode enum ────────────────────────────────────────────────


class TestErrorCode:
    def test_all_codes_are_string_enums(self):
        for code in ErrorCode:
            assert isinstance(code, str)
            assert isinstance(code.value, str)

    def test_validation_codes_exist(self):
        codes = {c.value for c in ErrorCode}
        assert "VALIDATION_MISSING_FIELD" in codes
        assert "VALIDATION_INVALID_VALUE" in codes
        assert "VALIDATION_INVALID_TYPE" in codes
        assert "VALIDATION_CONSTRAINT" in codes

    def test_not_found_codes_exist(self):
        codes = {c.value for c in ErrorCode}
        assert "NOT_FOUND_SESSION" in codes
        assert "NOT_FOUND_PATTERN" in codes
        assert "NOT_FOUND_STEP" in codes

    def test_conflict_codes_exist(self):
        codes = {c.value for c in ErrorCode}
        assert "CONFLICT_VERSION_MISMATCH" in codes
        assert "CONFLICT_INVALID_STATE_TRANSITION" in codes

    def test_timeout_codes_exist(self):
        codes = {c.value for c in ErrorCode}
        assert "TIMEOUT_EMBEDDING" in codes
        assert "TIMEOUT_INDEX" in codes

    def test_io_codes_exist(self):
        codes = {c.value for c in ErrorCode}
        assert "IO_DATABASE" in codes
        assert "IO_FILESYSTEM" in codes

    def test_internal_codes_exist(self):
        codes = {c.value for c in ErrorCode}
        assert "INTERNAL_ERROR" in codes


# ── is_retryable ──────────────────────────────────────────────────


class TestIsRetryable:
    def test_validation_never_retryable(self):
        assert is_retryable(ErrorCode.VALIDATION_MISSING_FIELD) is False
        assert is_retryable(ErrorCode.VALIDATION_INVALID_VALUE) is False

    def test_not_found_never_retryable(self):
        assert is_retryable(ErrorCode.NOT_FOUND_SESSION) is False
        assert is_retryable(ErrorCode.NOT_FOUND_PATTERN) is False

    def test_conflict_retryable(self):
        assert is_retryable(ErrorCode.CONFLICT_VERSION_MISMATCH) is True
        assert is_retryable(ErrorCode.CONFLICT_INVALID_STATE_TRANSITION) is True

    def test_timeout_retryable(self):
        assert is_retryable(ErrorCode.TIMEOUT_EMBEDDING) is True
        assert is_retryable(ErrorCode.TIMEOUT_INDEX) is True

    def test_io_retryable(self):
        assert is_retryable(ErrorCode.IO_DATABASE) is True
        assert is_retryable(ErrorCode.IO_FILESYSTEM) is True

    def test_internal_not_retryable_by_default(self):
        assert is_retryable(ErrorCode.INTERNAL_ERROR) is False


# ── ToolError ─────────────────────────────────────────────────────


class TestToolError:
    def test_is_exception(self):
        err = ToolError(code=ErrorCode.VALIDATION_MISSING_FIELD, message="oops")
        assert isinstance(err, Exception)

    def test_retryable_auto_set(self):
        err = ToolError(code=ErrorCode.IO_DATABASE, message="db error")
        assert err.retryable is True

        err2 = ToolError(code=ErrorCode.VALIDATION_CONSTRAINT, message="bad input")
        assert err2.retryable is False

    def test_to_dict(self):
        err = ToolError(
            code=ErrorCode.NOT_FOUND_SESSION,
            message="session gone",
            details={"session_id": "abc"},
        )
        d = err.to_dict()
        assert d["code"] == "NOT_FOUND_SESSION"
        assert d["message"] == "session gone"
        assert d["retryable"] is False
        assert d["details"]["session_id"] == "abc"

    def test_message_in_str(self):
        err = ToolError(code=ErrorCode.INTERNAL_ERROR, message="boom")
        assert str(err) == "boom"


# ── Convenience constructors ──────────────────────────────────────


class TestConvenienceConstructors:
    def test_validation_error(self):
        err = validation_error("bad input", field="name")
        assert err.code == ErrorCode.VALIDATION_INVALID_VALUE
        assert err.retryable is False
        assert err.details["field"] == "name"

    def test_not_found_error(self):
        err = not_found_error("not found", code=ErrorCode.NOT_FOUND_PATTERN)
        assert err.code == ErrorCode.NOT_FOUND_PATTERN

    def test_conflict_error(self):
        err = conflict_error("version mismatch")
        assert err.code == ErrorCode.CONFLICT_VERSION_MISMATCH
        assert err.retryable is True

    def test_timeout_error(self):
        err = timeout_error("embedding timed out")
        assert err.code == ErrorCode.TIMEOUT_EMBEDDING
        assert err.retryable is True

    def test_io_error(self):
        err = io_error("db failure")
        assert err.code == ErrorCode.IO_DATABASE
        assert err.retryable is True

    def test_internal_error(self):
        err = internal_error("unexpected")
        assert err.code == ErrorCode.INTERNAL_ERROR
        assert err.retryable is False


# ── Envelope ──────────────────────────────────────────────────────


class TestEnvelope:
    def test_meta_defaults(self):
        m = Meta()
        assert m.duration_ms == 0
        assert m.source == "local"
        assert m.confidence == "exact"

    def test_tool_response_to_dict(self):
        tr = ToolResponse(ok=True, data={"x": 1})
        d = tr.to_dict()
        assert d["ok"] is True
        assert d["data"]["x"] == 1
        assert d["error"] is None
        assert "meta" in d

    def test_success_envelope(self):
        env = success_envelope({"items": [1, 2]}, source="sqlite", confidence="partial")
        assert env["ok"] is True
        assert env["data"]["items"] == [1, 2]
        assert env["error"] is None
        assert env["meta"]["source"] == "sqlite"
        assert env["meta"]["confidence"] == "partial"

    def test_error_envelope(self):
        err = ToolError(code=ErrorCode.IO_DATABASE, message="oops")
        env = error_envelope(err, duration_ms=42)
        assert env["ok"] is False
        assert env["data"] is None
        assert env["error"]["code"] == "IO_DATABASE"
        assert env["meta"]["duration_ms"] == 42


# ── @tool_handler decorator ──────────────────────────────────────


class TestToolHandler:
    @pytest.mark.asyncio
    async def test_success_wrapping(self):
        @tool_handler(source="sqlite")
        async def my_tool():
            return {"result": 42}

        env = await my_tool()
        assert env["ok"] is True
        assert env["data"]["result"] == 42
        assert env["meta"]["source"] == "sqlite"
        assert env["meta"]["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_tool_error_wrapping(self):
        @tool_handler(source="local")
        async def failing_tool():
            raise ToolError(
                code=ErrorCode.VALIDATION_INVALID_VALUE,
                message="bad value",
            )

        env = await failing_tool()
        assert env["ok"] is False
        assert env["error"]["code"] == "VALIDATION_INVALID_VALUE"

    @pytest.mark.asyncio
    async def test_unexpected_exception_wrapping(self):
        @tool_handler(source="local")
        async def crashing_tool():
            raise RuntimeError("oops")

        env = await crashing_tool()
        assert env["ok"] is False
        assert env["error"]["code"] == "INTERNAL_ERROR"
        assert "oops" in env["error"]["message"]

    @pytest.mark.asyncio
    async def test_confidence_override(self):
        @tool_handler(source="sqlite", confidence="exact")
        async def tool_with_override():
            return {"value": 1, "__confidence__": "partial", "__source__": "parser"}

        env = await tool_with_override()
        assert env["ok"] is True
        assert env["meta"]["confidence"] == "partial"
        assert env["meta"]["source"] == "parser"
        # Override keys should not leak into data
        assert "__confidence__" not in env["data"]
        assert "__source__" not in env["data"]
