"""Session lifecycle state machine (FT2).

Pure domain logic: the ``SessionState`` enum and its legal-transition table
only — no threads, no I/O. The worker orchestration that actually drives
these transitions lives in the application layer's ``SessionController``
(Phase 4a); this module is the shared vocabulary it moves through. See
openspec/changes/refactor-clean-architecture/specs/capture-session/spec.md
("Explicit Session States") and design.md's sequence diagrams.
"""

from __future__ import annotations

from enum import Enum, auto

from depot_vision.domain.errors import InvalidTransition


class SessionState(Enum):
    """The seven observable session lifecycle states (FT2)."""

    IDLE = auto()
    STARTING = auto()
    RUNNING = auto()
    PAUSED = auto()
    DEGRADED = auto()
    STOPPING = auto()
    ERROR = auto()


#: Legal-transition table: current state -> the states it may move to next.
_LEGAL_TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    SessionState.IDLE: frozenset({SessionState.STARTING}),
    SessionState.STARTING: frozenset({SessionState.RUNNING, SessionState.ERROR}),
    SessionState.RUNNING: frozenset(
        {SessionState.PAUSED, SessionState.DEGRADED, SessionState.STOPPING}
    ),
    SessionState.PAUSED: frozenset({SessionState.RUNNING, SessionState.STOPPING}),
    SessionState.DEGRADED: frozenset(
        {SessionState.RUNNING, SessionState.STOPPING, SessionState.ERROR}
    ),
    SessionState.STOPPING: frozenset({SessionState.IDLE, SessionState.ERROR}),
    SessionState.ERROR: frozenset({SessionState.STOPPING}),
}


def is_legal_transition(current: SessionState, target: SessionState) -> bool:
    """Return whether moving from ``current`` to ``target`` is allowed."""
    return target in _LEGAL_TRANSITIONS[current]


def transition(current: SessionState, target: SessionState) -> SessionState:
    """Move from ``current`` to ``target``, or raise ``InvalidTransition``."""
    if not is_legal_transition(current, target):
        raise InvalidTransition(f"{current.name} -> {target.name} is not a legal transition")
    return target
