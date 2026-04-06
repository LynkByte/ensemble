"""Routing tool: model_recommend.

Recommend model tier (best/mid/cheapest) for an agent based on
task classification and agent role.
"""

from __future__ import annotations

import sqlite3

from ..contracts.envelope import tool_handler
from ..state.idempotency import check_idempotency, store_idempotency

# ── Routing rules ─────────────────────────────────────────────────
# Key: (agent, classification) -> tier

_ROUTING_RULES: dict[tuple[str, str], str] = {
    # Signal (git operations) — always cheapest
    ("signal", "trivial"): "cheapest",
    ("signal", "simple"): "cheapest",
    ("signal", "standard"): "cheapest",
    ("signal", "complex"): "cheapest",
    # Proof (format/build/test) — cheapest to mid
    ("proof", "trivial"): "cheapest",
    ("proof", "simple"): "cheapest",
    ("proof", "standard"): "mid",
    ("proof", "complex"): "mid",
    # Lens (code review, read-only) — cheapest to mid
    ("lens", "trivial"): "cheapest",
    ("lens", "simple"): "cheapest",
    ("lens", "standard"): "mid",
    ("lens", "complex"): "mid",
    # Craft (code writer) — mid to best
    ("craft", "trivial"): "mid",
    ("craft", "simple"): "mid",
    ("craft", "standard"): "best",
    ("craft", "complex"): "best",
    # Scope (planner) — mid to best
    ("scope", "trivial"): "mid",
    ("scope", "simple"): "mid",
    ("scope", "standard"): "best",
    ("scope", "complex"): "best",
    # Ensemble (orchestrator) — mid to best
    ("ensemble", "trivial"): "mid",
    ("ensemble", "simple"): "mid",
    ("ensemble", "standard"): "best",
    ("ensemble", "complex"): "best",
    # Trace (bug hunter) — best for all (precision matters)
    ("trace", "trivial"): "mid",
    ("trace", "simple"): "best",
    ("trace", "standard"): "best",
    ("trace", "complex"): "best",
}

_DEFAULT_TIER = "mid"

_TIER_REASONS: dict[str, dict[str, str]] = {
    "best": {
        "trivial": "Agent role requires high precision even for trivial tasks",
        "simple": "Simple task with an agent that benefits from top-tier reasoning",
        "standard": "Standard multi-file task — best model for accuracy",
        "complex": "Complex task requiring strongest reasoning capability",
    },
    "mid": {
        "trivial": "Trivial task — mid-tier sufficient for this agent role",
        "simple": "Simple task — balanced cost/quality with mid-tier model",
        "standard": "Standard task — mid-tier model suitable for this agent",
        "complex": "Complex task, but agent role works well with mid-tier model",
    },
    "cheapest": {
        "trivial": "Trivial task — cheapest model sufficient",
        "simple": "Simple task with routine agent role — cheapest saves cost",
        "standard": "Routine agent operations on standard task — cheapest adequate",
        "complex": "Complex task, but agent does mechanical work — cheapest is fine",
    },
}


def _get_reason(tier: str, classification: str) -> str:
    """Generate a human-readable reason for the recommendation."""
    tier_reasons = _TIER_REASONS.get(tier, _TIER_REASONS["mid"])
    return tier_reasons.get(classification, f"Default recommendation: {tier}")


@tool_handler(source="local", confidence="exact")
async def model_recommend(
    conn: sqlite3.Connection,
    *,
    agent: str,
    task_classification: str,
    task_description: str | None = None,  # noqa: ARG001  — reserved for future routing logic
    idempotency_key: str | None = None,
) -> dict:
    """Recommend a model tier for the given agent and task classification.

    Returns ``{tier, reason}`` where tier is one of: best, mid, cheapest.
    """
    cached = check_idempotency(conn, idempotency_key)
    if cached is not None:
        return cached

    agent_lower = agent.lower()
    classification_lower = task_classification.lower()

    tier = _ROUTING_RULES.get(
        (agent_lower, classification_lower),
        _DEFAULT_TIER,
    )
    reason = _get_reason(tier, classification_lower)

    result = {
        "tier": tier,
        "reason": reason,
        "agent": agent_lower,
        "classification": classification_lower,
    }
    store_idempotency(conn, idempotency_key, result)
    return result
