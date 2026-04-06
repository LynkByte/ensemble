"""Tests for state lifecycle (session/step state machines)."""

from __future__ import annotations

import pytest

from ensemble_mcp.contracts.errors import ErrorCode, ToolError
from ensemble_mcp.state.lifecycle import (
    TERMINAL_SESSION_STATES,
    TERMINAL_STEP_STATES,
    SessionState,
    StepState,
    transition_session,
    transition_step,
)

# ── SessionState ──────────────────────────────────────────────────


class TestSessionState:
    def test_all_states_exist(self):
        assert SessionState.PENDING.value == "pending"
        assert SessionState.RUNNING.value == "running"
        assert SessionState.COMPLETED.value == "completed"
        assert SessionState.FAILED.value == "failed"
        assert SessionState.KILLED.value == "killed"

    def test_terminal_states(self):
        assert SessionState.COMPLETED in TERMINAL_SESSION_STATES
        assert SessionState.FAILED in TERMINAL_SESSION_STATES
        assert SessionState.KILLED in TERMINAL_SESSION_STATES
        assert SessionState.PENDING not in TERMINAL_SESSION_STATES
        assert SessionState.RUNNING not in TERMINAL_SESSION_STATES


# ── StepState ─────────────────────────────────────────────────────


class TestStepState:
    def test_all_states_exist(self):
        assert StepState.PENDING.value == "pending"
        assert StepState.RUNNING.value == "running"
        assert StepState.COMPLETED.value == "completed"
        assert StepState.FAILED.value == "failed"
        assert StepState.SKIPPED.value == "skipped"

    def test_terminal_states(self):
        assert StepState.COMPLETED in TERMINAL_STEP_STATES
        assert StepState.FAILED in TERMINAL_STEP_STATES
        assert StepState.SKIPPED in TERMINAL_STEP_STATES


# ── transition_session ────────────────────────────────────────────


class TestTransitionSession:
    def test_pending_to_running(self):
        result = transition_session(SessionState.PENDING, SessionState.RUNNING)
        assert result == SessionState.RUNNING

    def test_running_to_completed(self):
        result = transition_session(SessionState.RUNNING, SessionState.COMPLETED)
        assert result == SessionState.COMPLETED

    def test_running_to_failed(self):
        result = transition_session(SessionState.RUNNING, SessionState.FAILED)
        assert result == SessionState.FAILED

    def test_running_to_killed(self):
        result = transition_session(SessionState.RUNNING, SessionState.KILLED)
        assert result == SessionState.KILLED

    def test_string_inputs(self):
        result = transition_session("pending", "running")
        assert result == SessionState.RUNNING

    def test_invalid_transition_raises_conflict(self):
        with pytest.raises(ToolError) as exc_info:
            transition_session(SessionState.PENDING, SessionState.COMPLETED)
        assert exc_info.value.code == ErrorCode.CONFLICT_INVALID_STATE_TRANSITION

    def test_terminal_state_cannot_transition(self):
        for terminal in TERMINAL_SESSION_STATES:
            with pytest.raises(ToolError) as exc_info:
                transition_session(terminal, SessionState.RUNNING)
            assert exc_info.value.code == ErrorCode.CONFLICT_INVALID_STATE_TRANSITION

    def test_backwards_transition_rejected(self):
        with pytest.raises(ToolError):
            transition_session(SessionState.RUNNING, SessionState.PENDING)


# ── transition_step ───────────────────────────────────────────────


class TestTransitionStep:
    def test_pending_to_running(self):
        result = transition_step(StepState.PENDING, StepState.RUNNING)
        assert result == StepState.RUNNING

    def test_pending_to_skipped(self):
        result = transition_step(StepState.PENDING, StepState.SKIPPED)
        assert result == StepState.SKIPPED

    def test_running_to_completed(self):
        result = transition_step(StepState.RUNNING, StepState.COMPLETED)
        assert result == StepState.COMPLETED

    def test_running_to_failed(self):
        result = transition_step(StepState.RUNNING, StepState.FAILED)
        assert result == StepState.FAILED

    def test_running_to_skipped(self):
        result = transition_step(StepState.RUNNING, StepState.SKIPPED)
        assert result == StepState.SKIPPED

    def test_string_inputs(self):
        result = transition_step("pending", "running")
        assert result == StepState.RUNNING

    def test_invalid_transition_raises_conflict(self):
        with pytest.raises(ToolError) as exc_info:
            transition_step(StepState.PENDING, StepState.COMPLETED)
        assert exc_info.value.code == ErrorCode.CONFLICT_INVALID_STATE_TRANSITION

    def test_terminal_step_cannot_transition(self):
        for terminal in TERMINAL_STEP_STATES:
            with pytest.raises(ToolError):
                transition_step(terminal, StepState.RUNNING)
