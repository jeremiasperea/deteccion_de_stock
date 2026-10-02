"""Application events published on the EventBus (D-C, supports D2/FT3).

Each event declares an ``EventClass`` so the bus can route it: ``FRAME``
events are coalescible pixels (newest wins), while ``STATE`` and ``LOG``
events are durable evidence that must never be discarded.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from depot_vision.domain.errors import DepotVisionError
from depot_vision.domain.frames import EncodedImage
from depot_vision.domain.session import SessionState


class EventClass(Enum):
    """Kind of an event, which decides its bus lane."""

    FRAME = auto()
    STATE = auto()
    LOG = auto()


@dataclass(frozen=True)
class AppEvent:
    """Base type for every event; subclasses pin their ``event_class``."""

    @property
    def event_class(self) -> EventClass:
        raise NotImplementedError

    @property
    def is_droppable(self) -> bool:
        """Only frame pixels may be coalesced or discarded."""
        return self.event_class is EventClass.FRAME


@dataclass(frozen=True)
class FrameRendered(AppEvent):
    image: EncodedImage

    @property
    def event_class(self) -> EventClass:
        return EventClass.FRAME


@dataclass(frozen=True)
class SessionStateChanged(AppEvent):
    state: SessionState

    @property
    def event_class(self) -> EventClass:
        return EventClass.STATE


@dataclass(frozen=True)
class LogEmitted(AppEvent):
    message: str

    @property
    def event_class(self) -> EventClass:
        return EventClass.LOG


@dataclass(frozen=True)
class DetectionLogged(AppEvent):
    message: str

    @property
    def event_class(self) -> EventClass:
        return EventClass.LOG


@dataclass(frozen=True)
class SessionFault(AppEvent):
    error: DepotVisionError

    @property
    def event_class(self) -> EventClass:
        return EventClass.LOG


@dataclass(frozen=True)
class QueueSaturated(AppEvent):
    """Diagnostic: the durable lane reached its soft capacity."""

    depth: int

    @property
    def event_class(self) -> EventClass:
        return EventClass.LOG
