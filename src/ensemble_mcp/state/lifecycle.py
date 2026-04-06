"""Session/step state machine and transitions.

Session lifecycle: pending -> running -> completed | failed | killed
Step lifecycle:    pending -> running -> completed | failed | skipped

Invalid transitions are rejected with CONFLICT_INVALID_STATE_TRANSITION.
"""

from __future__ import annotations

from enum import StrEnum

from ..contracts.errors import ErrorCode, ToolError


class SessionState(StrEnum):
    """Valid session states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


class StepState(StrEnum):
    """Valid step states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── Valid transition maps ─────────────────────────────────────────

_SESSION_TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    SessionState.PENDING: frozenset({SessionState.RUNNING}),
    SessionState.RUNNING: frozenset(
        {
            SessionState.COMPLETED,
            SessionState.FAILED,
            SessionState.KILLED,
        }
    ),
    # Terminal states — no outgoing transitions
    SessionState.COMPLETED: frozenset(),
    SessionState.FAILED: frozenset(),
    SessionState.KILLED: frozenset(),
}

_STEP_TRANSITIONS: dict[StepState, frozenset[StepState]] = {
    StepState.PENDING: frozenset({StepState.RUNNING, StepState.SKIPPED}),
    StepState.RUNNING: frozenset(
        {
            StepState.COMPLETED,
            StepState.FAILED,
            StepState.SKIPPED,
        }
    ),
    # Terminal states
    StepState.COMPLETED: frozenset(),
    StepState.FAILED: frozenset(),
    StepState.SKIPPED: frozenset(),
}

TERMINAL_SESSION_STATES: frozenset[SessionState] = frozenset(
    {
        SessionState.COMPLETED,
        SessionState.FAILED,
        SessionState.KILLED,
    }
)

TERMINAL_STEP_STATES: frozenset[StepState] = frozenset(
    {
        StepState.COMPLETED,
        StepState.FAILED,
        StepState.SKIPPED,
    }
)


def transition_session(
    current: SessionState | str,
    target: SessionState | str,
) -> SessionState:
    """Validate and perform a session state transition.

    Returns the new state on success.
    Raises ``ToolError`` with CONFLICT_INVALID_STATE_TRANSITION on failure.
    """
    if isinstance(current, str):
        current = SessionState(current)
    if isinstance(target, str):
        target = SessionState(target)

    allowed = _SESSION_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise ToolError(
            code=ErrorCode.CONFLICT_INVALID_STATE_TRANSITION,
            message=f"Cannot transition session from '{current.value}' to '{target.value}'",
            details={"current": current.value, "target": target.value},
        )
    return target


def transition_step(
    current: StepState | str,
    target: StepState | str,
) -> StepState:
    """Validate and perform a step state transition.

    Returns the new state on success.
    Raises ``ToolError`` with CONFLICT_INVALID_STATE_TRANSITION on failure.
    """
    if isinstance(current, str):
        current = StepState(current)
    if isinstance(target, str):
        target = StepState(target)

    allowed = _STEP_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise ToolError(
            code=ErrorCode.CONFLICT_INVALID_STATE_TRANSITION,
            message=f"Cannot transition step from '{current.value}' to '{target.value}'",
            details={"current": current.value, "target": target.value},
        )
    return target
