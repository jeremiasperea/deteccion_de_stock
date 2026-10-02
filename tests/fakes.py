"""Shared in-memory test doubles."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from depot_vision.domain.counting import CountSnapshot
from depot_vision.domain.events import AppEvent, SessionStateChanged
from depot_vision.domain.frames import Frame
from depot_vision.domain.session import SessionState


class FakeClock:
    """Deterministic ``Clock``: ``sleep`` advances time instantly and is recorded."""

    def __init__(self) -> None:
        self._monotonic = 0.0
        self._start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self._start + timedelta(seconds=self._monotonic)

    def monotonic(self) -> float:
        return self._monotonic

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self._monotonic += seconds


class CallLog:
    """Shared ordered record of collaborator calls, for ordering assertions."""

    def __init__(self) -> None:
        self.entries: list[str] = []

    def add(self, entry: str) -> None:
        self.entries.append(entry)


class RecordingBus:
    """``EventBus`` double that keeps every published event."""

    def __init__(self, log: CallLog | None = None) -> None:
        self.events: list[AppEvent] = []
        self._log = log

    def publish(self, event: AppEvent) -> None:
        self.events.append(event)
        if self._log is not None:
            self._log.add(f"publish:{type(event).__name__}")

    def drain(self) -> Sequence[AppEvent]:
        drained, self.events = self.events, []
        return drained

    def states(self) -> list[SessionState]:
        return [e.state for e in self.events if isinstance(e, SessionStateChanged)]


class FakeFrameSource:
    def __init__(self, log: CallLog | None = None) -> None:
        self.closed = 0
        self._log = log

    def open(self) -> None:
        pass

    def read(self) -> Frame:
        raise NotImplementedError

    def close(self) -> None:
        self.closed += 1
        if self._log is not None:
            self._log.add("close")

    @property
    def is_open(self) -> bool:
        return self.closed == 0


class FakeWorker:
    """Deterministic ``WorkerHandle``: ``exits_on_join`` decides join success."""

    def __init__(self, log: CallLog | None = None, *, exits_on_join: bool = True) -> None:
        self.exits_on_join = exits_on_join
        self.alive = False
        self.started = 0
        self.stop_requested = 0
        self.paused = False
        self.join_timeouts: list[float] = []
        self._log = log

    def _note(self, entry: str) -> None:
        if self._log is not None:
            self._log.add(entry)

    def start(self) -> None:
        self.started += 1
        self.alive = True
        self._note("spawn")

    def request_stop(self) -> None:
        self.stop_requested += 1
        self._note("signal")

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def join(self, timeout: float) -> bool:
        self.join_timeouts.append(timeout)
        self._note("join")
        if self.exits_on_join:
            self.alive = False
        return not self.alive

    def is_alive(self) -> bool:
        return self.alive


class FakeRepository:
    """``CountRepository`` double recording ``clear`` calls."""

    def __init__(self, log: CallLog | None = None) -> None:
        self.cleared = 0
        self._log = log

    def append(self, snapshot: CountSnapshot) -> None:
        pass

    def snapshot(self) -> tuple[CountSnapshot, ...]:
        return ()

    def clear(self) -> None:
        self.cleared += 1
        if self._log is not None:
            self._log.add("clear")
