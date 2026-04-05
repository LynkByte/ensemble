"""Tests for security/trust module (validators, confirmation)."""

from __future__ import annotations

import pytest

from ensemble_mcp.contracts.errors import ErrorCode, ToolError
from ensemble_mcp.security.trust import (
    SourceClass,
    require_confirmation,
    validate_positive_int,
    validate_string,
)


class TestSourceClass:
    def test_values(self):
        assert SourceClass.LOCAL_STATE.value == "local_state"
        assert SourceClass.CLIENT_INPUT.value == "client_input"
        assert SourceClass.FILESYSTEM_SCAN.value == "filesystem_scan"


class TestRequireConfirmation:
    def test_passes_when_true(self):
        require_confirmation(True, "reset")  # Should not raise

    def test_raises_when_false(self):
        with pytest.raises(ToolError) as exc_info:
            require_confirmation(False, "reset")
        assert exc_info.value.code == ErrorCode.VALIDATION_CONSTRAINT
        assert "confirm=true" in exc_info.value.message

    def test_raises_when_not_boolean_true(self):
        with pytest.raises(ToolError):
            require_confirmation(1, "reset")  # type: ignore[arg-type]


class TestValidateString:
    def test_valid_string(self):
        result = validate_string("hello", "field")
        assert result == "hello"

    def test_non_string_raises(self):
        with pytest.raises(ToolError) as exc_info:
            validate_string(123, "field")
        assert exc_info.value.code == ErrorCode.VALIDATION_INVALID_TYPE

    def test_empty_string_raises(self):
        with pytest.raises(ToolError) as exc_info:
            validate_string("", "field")
        assert exc_info.value.code == ErrorCode.VALIDATION_MISSING_FIELD

    def test_too_long_raises(self):
        with pytest.raises(ToolError) as exc_info:
            validate_string("x" * 200, "field", max_length=100)
        assert exc_info.value.code == ErrorCode.VALIDATION_CONSTRAINT

    def test_custom_min_length(self):
        with pytest.raises(ToolError):
            validate_string("hi", "field", min_length=5)


class TestValidatePositiveInt:
    def test_valid_int(self):
        result = validate_positive_int(5, "count")
        assert result == 5

    def test_non_int_raises(self):
        with pytest.raises(ToolError) as exc_info:
            validate_positive_int("5", "count")
        assert exc_info.value.code == ErrorCode.VALIDATION_INVALID_TYPE

    def test_bool_raises(self):
        # bool is subclass of int, should be explicitly rejected
        with pytest.raises(ToolError) as exc_info:
            validate_positive_int(True, "count")
        assert exc_info.value.code == ErrorCode.VALIDATION_INVALID_TYPE

    def test_below_min_raises(self):
        with pytest.raises(ToolError) as exc_info:
            validate_positive_int(0, "count")
        assert exc_info.value.code == ErrorCode.VALIDATION_CONSTRAINT

    def test_above_max_raises(self):
        with pytest.raises(ToolError) as exc_info:
            validate_positive_int(5, "count", max_value=3)
        assert exc_info.value.code == ErrorCode.VALIDATION_CONSTRAINT

    def test_custom_range(self):
        result = validate_positive_int(50, "count", min_value=10, max_value=100)
        assert result == 50
