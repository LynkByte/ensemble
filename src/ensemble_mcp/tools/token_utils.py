"""Token utility helpers for the hybrid source-precedence approach.

Provides:
- ``parse_usage_raw``: extract token fields from raw provider payloads
  (Anthropic, OpenAI, and generic formats).
- ``estimate_tokens``: tiktoken-based fallback estimation from text.
- ``resolve_token_fields``: orchestrate the 3-tier source precedence:
  1. Direct fields (exact) — passed explicitly by caller
  2. ``usage_raw`` parsing (exact) — extract from provider payload
  3. ``tiktoken`` estimation (estimated) — count tokens in text

Each function is pure (no DB access) so it is easy to test in isolation.
"""

from __future__ import annotations

from typing import Any

from ..config.defaults import (
    CONFIDENCE_ESTIMATED,
    CONFIDENCE_EXACT,
    CONFIDENCE_PARTIAL,
    SOURCE_ESTIMATOR,
    SOURCE_LOCAL,
)

# ── tiktoken lazy singleton ──────────────────────────────────────

_encoder: Any = None


def _get_encoder() -> Any:
    """Return a cached ``cl100k_base`` tiktoken encoder (GPT-4/Claude compatible)."""
    global _encoder  # noqa: PLW0603
    if _encoder is None:
        import tiktoken

        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def estimate_tokens(text: str) -> int:
    """Estimate token count for *text* using tiktoken (~85-95% accurate).

    Uses the ``cl100k_base`` encoding which is compatible with GPT-4,
    GPT-4o, and reasonably close for Claude models.
    """
    if not text:
        return 0
    return len(_get_encoder().encode(text))


# ── Provider payload parsers ─────────────────────────────────────

# Maps from known provider field names to our canonical field names.
# Anthropic usage shape: {"input_tokens": ..., "output_tokens": ...,
#   "cache_read_input_tokens": ..., "cache_creation_input_tokens": ...}
# OpenAI usage shape:    {"prompt_tokens": ..., "completion_tokens": ...,
#   "prompt_tokens_details": {"cached_tokens": ...}, "total_tokens": ...}


def _parse_anthropic_usage(raw: dict[str, Any]) -> dict[str, int]:
    """Extract token counts from an Anthropic-shaped usage payload."""
    return {
        "input_tokens": int(raw.get("input_tokens", 0)),
        "output_tokens": int(raw.get("output_tokens", 0)),
        "cache_read_tokens": int(raw.get("cache_read_input_tokens", 0)),
        "cache_write_tokens": int(raw.get("cache_creation_input_tokens", 0)),
    }


def _parse_openai_usage(raw: dict[str, Any]) -> dict[str, int]:
    """Extract token counts from an OpenAI-shaped usage payload."""
    result: dict[str, int] = {
        "input_tokens": int(raw.get("prompt_tokens", 0)),
        "output_tokens": int(raw.get("completion_tokens", 0)),
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }
    # OpenAI nests cache info under prompt_tokens_details
    details = raw.get("prompt_tokens_details") or {}
    if isinstance(details, dict):
        result["cache_read_tokens"] = int(details.get("cached_tokens", 0))
    return result


def _parse_generic_usage(raw: dict[str, Any]) -> dict[str, int]:
    """Best-effort extraction from an unrecognised payload shape.

    Tries both Anthropic and OpenAI field names, preferring whichever
    yields non-zero values.
    """
    return {
        "input_tokens": int(raw.get("input_tokens", 0) or raw.get("prompt_tokens", 0)),
        "output_tokens": int(raw.get("output_tokens", 0) or raw.get("completion_tokens", 0)),
        "cache_read_tokens": int(
            raw.get("cache_read_input_tokens", 0) or raw.get("cache_read_tokens", 0)
        ),
        "cache_write_tokens": int(
            raw.get("cache_creation_input_tokens", 0) or raw.get("cache_write_tokens", 0)
        ),
    }


def _detect_provider(raw: dict[str, Any], provider_hint: str | None) -> str:
    """Auto-detect the payload provider when no hint is given."""
    if provider_hint:
        return provider_hint.lower()
    # Anthropic payloads use "input_tokens"; OpenAI uses "prompt_tokens"
    if "cache_read_input_tokens" in raw or "cache_creation_input_tokens" in raw:
        return "anthropic"
    if "prompt_tokens" in raw or "completion_tokens" in raw:
        return "openai"
    # Default to generic
    return "generic"


def parse_usage_raw(
    raw: dict[str, Any],
    provider: str | None = None,
) -> dict[str, int]:
    """Parse a raw provider usage payload into canonical token fields.

    Supports Anthropic, OpenAI, and generic (best-effort) formats.

    Returns a dict with keys: ``input_tokens``, ``output_tokens``,
    ``cache_read_tokens``, ``cache_write_tokens``.
    """
    detected = _detect_provider(raw, provider)
    if detected == "anthropic":
        return _parse_anthropic_usage(raw)
    if detected == "openai":
        return _parse_openai_usage(raw)
    return _parse_generic_usage(raw)


# ── Resolve: 3-tier source precedence ────────────────────────────


def resolve_token_fields(
    *,
    # Tier 1: explicit token fields (highest priority)
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
    web_search_requests: int | None = None,
    cached_tokens: int | None = None,
    # Tier 2: raw provider payload
    usage_raw: dict[str, Any] | None = None,
    provider: str | None = None,
    # Tier 3: text for tiktoken estimation
    input_text: str | None = None,
    output_text: str | None = None,
    # Caller-supplied overrides
    source: str | None = None,
    confidence: str | None = None,
) -> dict[str, Any]:
    """Resolve token counts using the best available source.

    Precedence (high → low):
    1. Direct token fields passed by the caller.
    2. Parsed ``usage_raw`` provider payload.
    3. tiktoken estimation from ``input_text`` / ``output_text``.

    Returns a dict containing the resolved ``input_tokens``,
    ``output_tokens``, ``cache_read_tokens``, ``cache_write_tokens``,
    ``web_search_requests``, ``cached_tokens``, ``source``, and
    ``confidence``.
    """
    # Start from explicit fields (may be None)
    in_tok = input_tokens
    out_tok = output_tokens
    cache_read = cache_read_tokens
    cache_write = cache_write_tokens
    web_reqs = web_search_requests or 0

    resolved_source = source or SOURCE_LOCAL
    resolved_confidence = confidence or CONFIDENCE_EXACT

    has_explicit = (in_tok is not None and in_tok > 0) or (out_tok is not None and out_tok > 0)

    # Tier 2: fill from usage_raw if explicit fields are missing
    if not has_explicit and usage_raw is not None:
        parsed = parse_usage_raw(usage_raw, provider)
        in_tok = in_tok if (in_tok is not None and in_tok > 0) else parsed["input_tokens"]
        out_tok = out_tok if (out_tok is not None and out_tok > 0) else parsed["output_tokens"]
        cache_read = (
            cache_read
            if (cache_read is not None and cache_read > 0)
            else parsed["cache_read_tokens"]
        )
        cache_write = (
            cache_write
            if (cache_write is not None and cache_write > 0)
            else parsed["cache_write_tokens"]
        )
        resolved_source = source or "live_response_usage"
        resolved_confidence = confidence or CONFIDENCE_EXACT
        # Check if web_search_requests is in the raw payload
        if web_reqs == 0 and isinstance(usage_raw, dict):
            web_reqs = int(usage_raw.get("web_search_requests", 0))

    # Tier 3: tiktoken fallback if still missing
    in_tok = in_tok or 0
    out_tok = out_tok or 0
    if in_tok == 0 and out_tok == 0 and (input_text or output_text):
        in_tok = estimate_tokens(input_text) if input_text else 0
        out_tok = estimate_tokens(output_text) if output_text else 0
        resolved_source = source or SOURCE_ESTIMATOR
        resolved_confidence = confidence or CONFIDENCE_ESTIMATED

    # Resolve cached_tokens: prefer explicit, then cache_read fallback
    cache_read = cache_read or 0
    cache_write = cache_write or 0
    has_explicit_cached = cached_tokens is not None and cached_tokens > 0
    resolved_cached = cached_tokens if has_explicit_cached else cache_read

    # Determine final confidence: if mixing sources, degrade to partial
    if resolved_confidence == CONFIDENCE_EXACT and (in_tok == 0 and out_tok == 0):
        resolved_confidence = CONFIDENCE_PARTIAL

    return {
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "web_search_requests": web_reqs,
        "cached_tokens": resolved_cached,
        "source": resolved_source,
        "confidence": resolved_confidence,
    }
