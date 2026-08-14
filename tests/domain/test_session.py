"""Tests for the session-state legal-transition table (FT2).

Pure domain logic: no threads, no I/O, no mocks. See
openspec/changes/refactor-clean-architecture/specs/capture-session/spec.md
("Explicit Session States") and design.md's sequence diagrams (start
sequence, DEGRADED recovery, ordered shutdown).
"""

from __future__ import annotations

import pytest

from depot_vision.domain.errors import InvalidTransition
from depot_vision.domain.session import SessionState, transition


class TestStartSequenceIsLegal:
    """Scenario: Start transitions to RUNNING."""

    def test_idle_to_starting_to_running_is_legal(self) -> None:
        state = transition(SessionState.IDLE, SessionState.STARTING)
        assert state is SessionState.STARTING

        state = transition(state, SessionState.RUNNING)
        assert state is SessionState.RUNNING


class TestDegradedRecoveryIsBidirectional:
    """Scenario: Failure transitions to DEGRADED / Recovery clears DEGRADED."""

    def test_running_to_degraded_and_back_to_running_are_both_legal(self) -> None:
        degraded = transition(SessionState.RUNNING, SessionState.DEGRADED)
        assert degraded is SessionState.DEGRADED

        recovered = transition(degraded, SessionState.RUNNING)
        assert recovered is SessionState.RUNNING


class TestOrderedShutdownStates:
    """Scenario: Stop closes camera — ordered shutdown reaches IDLE or ERROR."""

    def test_running_to_stopping_to_idle_is_legal(self) -> None:
        stopping = transition(SessionState.RUNNING, SessionState.STOPPING)
        assert stopping is SessionState.STOPPING

        idle = transition(stopping, SessionState.IDLE)
        assert idle is SessionState.IDLE

    def test_stopping_to_error_on_join_timeout_is_legal(self) -> None:
        errored = transition(SessionState.STOPPING, SessionState.ERROR)
        assert errored is SessionState.ERROR


class TestIllegalTransitionsAreRejected:
    def test_idle_to_running_directly_is_illegal(self) -> None:
        with pytest.raises(InvalidTransition):
            transition(SessionState.IDLE, SessionState.RUNNING)

    def test_idle_to_idle_is_illegal(self) -> None:
        with pytest.raises(InvalidTransition):
            transition(SessionState.IDLE, SessionState.IDLE)
