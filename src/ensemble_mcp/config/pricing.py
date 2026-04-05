"""Model pricing tables.

Stores per-model input/output/cached token costs and web search request costs.
Includes pricing_version for reproducible historical reports.

All costs are in USD per 1 million tokens unless otherwise noted.
"""

from __future__ import annotations

from dataclasses import dataclass

# Bump this whenever the pricing table changes so historical reports
# remain reproducible.
PRICING_VERSION = "2026-03"


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Cost structure for a single model."""

    input: float  # USD per 1M input tokens
    cached_input: float  # USD per 1M cached input tokens
    output: float  # USD per 1M output tokens
    cache_write: float = 0.0  # USD per 1M cache write tokens (if applicable)
    web_search: float = 0.0  # USD per web search request (if applicable)


# ── Pricing Table ─────────────────────────────────────────────────
MODEL_PRICING: dict[str, ModelPricing] = {
    # Anthropic
    "claude-opus-4": ModelPricing(
        input=15.00,
        cached_input=1.50,
        output=75.00,
    ),
    "claude-sonnet-4": ModelPricing(
        input=3.00,
        cached_input=0.30,
        output=15.00,
    ),
    "claude-haiku-3.5": ModelPricing(
        input=0.80,
        cached_input=0.08,
        output=4.00,
    ),
    # OpenAI
    "gpt-4o": ModelPricing(
        input=2.50,
        cached_input=1.25,
        output=10.00,
    ),
    "gpt-4o-mini": ModelPricing(
        input=0.15,
        cached_input=0.075,
        output=0.60,
    ),
    "gpt-5-mini": ModelPricing(
        input=0.20,
        cached_input=0.10,
        output=0.80,
    ),
    "o1": ModelPricing(
        input=15.00,
        cached_input=7.50,
        output=60.00,
    ),
}

# Fallback when model is not in the pricing table.
FALLBACK_MODEL = "claude-sonnet-4"


def get_pricing(model: str) -> tuple[ModelPricing, bool]:
    """Return pricing for *model* and whether it was a fallback.

    Returns:
        (pricing, is_fallback) -- is_fallback is True when the model
        was not found and the fallback tier was used instead.
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is not None:
        return pricing, False
    return MODEL_PRICING[FALLBACK_MODEL], True


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
    web_search_requests: int = 0,
    model: str = FALLBACK_MODEL,
) -> tuple[float, bool]:
    """Calculate cost in USD for a given token usage.

    Returns:
        (cost_usd, unknown_model) -- unknown_model is True when the
        model was not in the pricing table and fallback was used.
    """
    pricing, is_fallback = get_pricing(model)

    billable_input = max(input_tokens - cached_tokens, 0)
    input_cost = billable_input * pricing.input / 1_000_000
    cached_cost = cached_tokens * pricing.cached_input / 1_000_000
    output_cost = output_tokens * pricing.output / 1_000_000
    cache_write_cost = cache_write_tokens * pricing.cache_write / 1_000_000
    web_cost = web_search_requests * pricing.web_search

    total = input_cost + cached_cost + output_cost + cache_write_cost + web_cost
    return round(total, 6), is_fallback
