"""Tests for security/redaction module."""

from __future__ import annotations

from ensemble_mcp.security.redaction import (
    REDACTED_PLACEHOLDER,
    contains_secrets,
    redact,
)


class TestRedact:
    def test_aws_access_key(self):
        text = "my key is AKIAIOSFODNN7EXAMPLE"
        result = redact(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert REDACTED_PLACEHOLDER in result

    def test_bearer_token(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc"
        result = redact(text)
        assert "eyJhbGciOi" not in result
        assert REDACTED_PLACEHOLDER in result

    def test_api_key_in_assignment(self):
        text = 'api_key = "sk-abc123xyz456qwerty7890abcdef"'
        result = redact(text)
        assert "sk-abc123xyz456qwerty7890abcdef" not in result
        assert REDACTED_PLACEHOLDER in result

    def test_github_token(self):
        text = "token=ghp_1234567890abcdefghijklmnopqrstuvwxyz1234"
        result = redact(text)
        assert "ghp_1234567890" not in result
        assert REDACTED_PLACEHOLDER in result

    def test_password_in_connection_string(self):
        text = 'password="SuperSecret123!"'
        result = redact(text)
        assert "SuperSecret123!" not in result
        assert REDACTED_PLACEHOLDER in result

    def test_private_key_header(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIBogIBAAJ..."
        result = redact(text)
        assert "BEGIN RSA PRIVATE KEY" not in result
        assert REDACTED_PLACEHOLDER in result

    def test_env_secret(self):
        text = 'SECRET_KEY = "myverysecretvalue123"'
        result = redact(text)
        assert "myverysecretvalue123" not in result

    def test_clean_text_unchanged(self):
        text = "This is a normal function that adds two numbers"
        result = redact(text)
        assert result == text

    def test_multiple_secrets(self):
        text = "key AKIAIOSFODNN7EXAMPLE and Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.xyz"
        result = redact(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "eyJhbGci" not in result
        assert result.count(REDACTED_PLACEHOLDER) >= 2

    def test_original_string_not_modified(self):
        text = "AKIAIOSFODNN7EXAMPLE"
        _ = redact(text)
        assert "AKIAIOSFODNN7EXAMPLE" in text


class TestContainsSecrets:
    def test_returns_true_for_aws_key(self):
        assert contains_secrets("AKIAIOSFODNN7EXAMPLE") is True

    def test_returns_true_for_bearer_token(self):
        assert contains_secrets("Bearer eyJhbGciOiJIUzI1NiJ9.abc") is True

    def test_returns_false_for_clean_text(self):
        assert contains_secrets("just some normal code") is False

    def test_returns_false_for_empty_string(self):
        assert contains_secrets("") is False

    def test_returns_true_for_github_token(self):
        assert contains_secrets("ghp_1234567890abcdefghijklmnopqrstuvwxyz1234") is True
