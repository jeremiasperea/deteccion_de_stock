"""Bounded two-lane ``EventBus`` (D-C, FT3, D2).

One ``threading.Lock`` guards a ``deque`` (durable lane: STATE and LOG events)
and a single-slot frame reference (frame lane). Publishing a frame overwrites
the slot, so only pixels are ever discarded. Durable events are always kept:
reaching ``soft_capacity`` appends one ``QueueSaturated`` diagnostic and
reaching ``hard_ceiling`` appends one ``SessionFault(QueueOverflow)`` for the
consumer to act on. Each notice is re-armed once the lane falls below half of
the soft capacity. ``publish`` never blocks and never raises.
"""

from __future__ import annotations

import threading
from collections import deque

from depot_vision.domain.errors import QueueOverflow
from depot_vision.domain.events import (
    AppEvent,
    EventClass,
    QueueSaturated,
    SessionFault,
)


class BoundedEventBus:
    def __init__(self, *, soft_capacity: int, hard_ceiling: int) -> None:
        self._soft = soft_capacity
        self._hard = hard_ceiling
        self._lock = threading.Lock()
        self._durable: deque[AppEvent] = deque()
        self._latest_frame: AppEvent | None = None
        self._saturation_armed = True
        self._overflow_armed = True

    def publish(self, event: AppEvent) -> None:
        with self._lock:
            if event.event_class is EventClass.FRAME:
                self._latest_frame = event  # coalesce: the newest pixels win
                return
            self._durable.append(event)
            depth = len(self._durable)
            if depth >= self._soft and self._saturation_armed:
                self._saturation_armed = False
                self._durable.append(QueueSaturated(depth=depth))
            if depth >= self._hard and self._overflow_armed:
                self._overflow_armed = False
                fault = QueueOverflow(f"event queue reached its hard ceiling of {self._hard}")
                self._durable.append(SessionFault(error=fault))

    def drain(self) -> tuple[AppEvent, ...]:
        """Durable events in FIFO order, then the coalesced frame; clears both lanes."""
        with self._lock:
            drained = list(self._durable)
            if self._latest_frame is not None:
                drained.append(self._latest_frame)
            self._durable.clear()
            self._latest_frame = None
            # ``drain`` empties the lane, the only way depth falls, so it is
            # always below half of the soft capacity here: re-arm both notices.
            self._saturation_armed = True
            self._overflow_armed = True
            return tuple(drained)
