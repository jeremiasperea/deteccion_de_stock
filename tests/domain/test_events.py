"""Tests for the AppEvent hierarchy and EventClass (D-C, supports D2/FT3).

The event class tells the bus which lane an event travels in: pixels are
coalescible, everything else is durable evidence.
"""

from __future__ import annotations

import dataclasses

import pytest

from depot_vision.domain.errors import CameraUnavailable
from depot_vision.domain.events import (
    AppEvent,
    DetectionLogged,
    EventClass,
    FrameRendered,
    LogEmitted,
    QueueSaturated,
    SessionFault,
    SessionStateChanged,
    ShutdownTimedOut,
)
from depot_vision.domain.frames import EncodedImage
from depot_vision.domain.session import SessionState


def _one_of_each() -> list[AppEvent]:
    return [
        FrameRendered(image=EncodedImage(data=b"x", media_type="image/jpeg")),
        SessionStateChanged(state=SessionState.RUNNING),
        LogEmitted(message="hello"),
        DetectionLogged(message="2 x person"),
        SessionFault(error=CameraUnavailable("gone")),
        QueueSaturated(depth=1024),
        ShutdownTimedOut(timeout_s=5.0),
    ]


class TestEventClass:
    def test_has_frame_state_and_log_kinds(self) -> None:
        assert {c.name for c in EventClass} == {"FRAME", "STATE", "LOG"}

    def test_each_event_reports_its_class(self) -> None:
        classes = [event.event_class for event in _one_of_each()]

        assert classes == [
            EventClass.FRAME,
            EventClass.STATE,
            EventClass.LOG,
            EventClass.LOG,
            EventClass.LOG,
            EventClass.LOG,
            EventClass.LOG,
        ]

    def test_only_frame_events_are_droppable(self) -> None:
        droppable = [e for e in _one_of_each() if e.is_droppable]

        assert [type(e) for e in droppable] == [FrameRendered]


class TestHierarchy:
    def test_every_event_is_an_app_event(self) -> None:
        assert all(isinstance(e, AppEvent) for e in _one_of_each())

    def test_events_are_frozen(self) -> None:
        event = LogEmitted(message="x")
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.message = "y"  # type: ignore[misc]

    def test_payloads_are_carried(self) -> None:
        fault = SessionFault(error=CameraUnavailable("gone"))
        assert isinstance(fault.error, CameraUnavailable)
        assert SessionStateChanged(state=SessionState.DEGRADED).state is SessionState.DEGRADED
