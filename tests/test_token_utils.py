"""Tests for token_utils: usage_raw parsing, tiktoken estimation, and resolve_token_fields."""

from __future__ import annotations

from ensemble_mcp.tools.token_utils import (
    estimate_tokens,
    parse_usage_raw,
    resolve_token_fields,
)


class TestEstimateTokens:
    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 0

    def test_simple_text(self) -> None:
        count = estimate_tokens("Hello world")
        assert count > 0
        assert isinstance(count, int)

    def test_longer_text(self) -> None:
        short = estimate_tokens("Hello")
        long = estimate_tokens("Hello world, this is a much longer sentence with many more tokens")
        assert long > short

    def test_code_snippet(self) -> None:
        code = (
            "def fibonacci(n):\n"
            "    if n <= 1:\n"
            "        return n\n"
            "    return fibonacci(n-1) + fibonacci(n-2)"
        )
        count = estimate_tokens(code)
        assert count > 10  # Code should produce meaningful tokens


class TestParseUsageRawAnthropic:
    def test_full_anthropic_payload(self) -> None:
        raw = {
            "input_tokens": 1500,
            "output_tokens": 800,
            "cache_read_input_tokens": 200,
            "cache_creation_input_tokens": 100,
        }
        result = parse_usage_raw(raw, provider="anthropic")
        assert result["input_tokens"] == 1500
        assert result["output_tokens"] == 800
        assert result["cache_read_tokens"] == 200
        assert result["cache_write_tokens"] == 100

    def test_minimal_anthropic_payload(self) -> None:
        raw = {"input_tokens": 500, "output_tokens": 200}
        result = parse_usage_raw(raw, provider="anthropic")
        assert result["input_tokens"] == 500
        assert result["output_tokens"] == 200
        assert result["cache_read_tokens"] == 0
        assert result["cache_write_tokens"] == 0

    def test_auto_detect_anthropic(self) -> None:
        """Auto-detect Anthropic from cache_read_input_tokens field."""
        raw = {
            "input_tokens": 1000,
            "output_tokens": 400,
            "cache_read_input_tokens": 50,
        }
        result = parse_usage_raw(raw)  # no provider hint
        assert result["input_tokens"] == 1000
        assert result["cache_read_tokens"] == 50


class TestParseUsageRawOpenAI:
    def test_full_openai_payload(self) -> None:
        raw = {
            "prompt_tokens": 2000,
            "completion_tokens": 600,
            "total_tokens": 2600,
            "prompt_tokens_details": {"cached_tokens": 500},
        }
        result = parse_usage_raw(raw, provider="openai")
        assert result["input_tokens"] == 2000
        assert result["output_tokens"] == 600
        assert result["cache_read_tokens"] == 500
        assert result["cache_write_tokens"] == 0

    def test_minimal_openai_payload(self) -> None:
        raw = {"prompt_tokens": 1000, "completion_tokens": 300}
        result = parse_usage_raw(raw, provider="openai")
        assert result["input_tokens"] == 1000
        assert result["output_tokens"] == 300
        assert result["cache_read_tokens"] == 0

    def test_auto_detect_openai(self) -> None:
        """Auto-detect OpenAI from prompt_tokens field."""
        raw = {"prompt_tokens": 800, "completion_tokens": 200}
        result = parse_usage_raw(raw)
        assert result["input_tokens"] == 800
        assert result["output_tokens"] == 200


class TestParseUsageRawGeneric:
    def test_generic_with_mixed_fields(self) -> None:
        """Generic parser handles both Anthropic and OpenAI field names."""
        raw = {"input_tokens": 500, "output_tokens": 200}
        result = parse_usage_raw(raw, provider="generic")
        assert result["input_tokens"] == 500
        assert result["output_tokens"] == 200

    def test_unknown_provider(self) -> None:
        raw = {"input_tokens": 100, "output_tokens": 50}
        result = parse_usage_raw(raw, provider="unknown_provider")
        # Falls through to generic
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50

    def test_empty_payload(self) -> None:
        result = parse_usage_raw({})
        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 0


class TestResolveTokenFields:
    def test_tier1_explicit_fields(self) -> None:
        """Direct fields take highest priority."""
        result = resolve_token_fields(
            input_tokens=1000,
            output_tokens=500,
        )
        assert result["input_tokens"] == 1000
        assert result["output_tokens"] == 500
        assert result["confidence"] == "exact"
        assert result["source"] == "local"

    def test_tier1_overrides_usage_raw(self) -> None:
        """Explicit fields should not be overridden by usage_raw."""
        result = resolve_token_fields(
            input_tokens=1000,
            output_tokens=500,
            usage_raw={"input_tokens": 9999, "output_tokens": 8888},
        )
        assert result["input_tokens"] == 1000
        assert result["output_tokens"] == 500

    def test_tier2_usage_raw_fallback(self) -> None:
        """usage_raw is used when explicit fields are None/0."""
        result = resolve_token_fields(
            usage_raw={
                "input_tokens": 1500,
                "output_tokens": 800,
                "cache_read_input_tokens": 200,
            },
        )
        assert result["input_tokens"] == 1500
        assert result["output_tokens"] == 800
        assert result["cache_read_tokens"] == 200
        assert result["source"] == "live_response_usage"
        assert result["confidence"] == "exact"

    def test_tier3_tiktoken_fallback(self) -> None:
        """tiktoken estimation is used when no token counts are available."""
        result = resolve_token_fields(
            input_text="Hello world, this is a test input.",
            output_text="This is the response.",
        )
        assert result["input_tokens"] > 0
        assert result["output_tokens"] > 0
        assert result["source"] == "estimator"
        assert result["confidence"] == "estimated"

    def test_all_zero_no_text_partial_confidence(self) -> None:
        """When nothing is available, confidence degrades to partial."""
        result = resolve_token_fields()
        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 0
        assert result["confidence"] == "partial"

    def test_cached_tokens_from_cache_read(self) -> None:
        """cached_tokens defaults to cache_read_tokens if not explicitly set."""
        result = resolve_token_fields(
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=300,
        )
        assert result["cached_tokens"] == 300

    def test_explicit_cached_tokens_overrides(self) -> None:
        """Explicit cached_tokens overrides cache_read_tokens."""
        result = resolve_token_fields(
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=300,
            cached_tokens=150,
        )
        assert result["cached_tokens"] == 150

    def test_web_search_requests(self) -> None:
        result = resolve_token_fields(
            input_tokens=100,
            output_tokens=50,
            web_search_requests=3,
        )
        assert result["web_search_requests"] == 3

    def test_caller_source_override(self) -> None:
        """Caller-supplied source/confidence should be respected."""
        result = resolve_token_fields(
            input_tokens=100,
            output_tokens=50,
            source="session_parser",
            confidence="partial",
        )
        assert result["source"] == "session_parser"
        assert result["confidence"] == "partial"

    def test_usage_raw_with_web_search(self) -> None:
        """Web search requests should be extracted from usage_raw."""
        result = resolve_token_fields(
            usage_raw={
                "input_tokens": 500,
                "output_tokens": 200,
                "web_search_requests": 2,
            },
        )
        assert result["web_search_requests"] == 2
