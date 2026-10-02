"""Conformance of in-memory fakes to the nine ports (D-B).

Two independent checks: ``isinstance`` against the ``runtime_checkable``
protocols (member presence, at runtime) and plain typed assignments that
mypy verifies statically (signatures).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import pytest

from depot_vision.domain.config import AppConfig
from depot_vision.domain.counting import CountSnapshot
from depot_vision.domain.detections import Detection
from depot_vision.domain.events import AppEvent
from depot_vision.domain.frames import EncodedImage, Frame, Overlay
from depot_vision.ports import (
    Clock,
    ConfigProvider,
    CountExporter,
    CountRepository,
    EventBus,
    FrameAnnotator,
    FrameEncoder,
    FrameSource,
    ObjectDetector,
)


class FakeFrameSource:
    def __init__(self) -> None:
        self._open = False

    def open(self) -> None:
        self._open = True

    def read(self) -> Frame:
        return Frame(pixels=b"px")

    def close(self) -> None:
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open


class FakeObjectDetector:
    def load(self) -> None:
        return None

    def detect(self, frame: Frame) -> Sequence[Detection]:
        return ()


class FakeFrameAnnotator:
    def annotate(self, frame: Frame, detections: Sequence[Detection], overlay: Overlay) -> Frame:
        return frame


class FakeFrameEncoder:
    def encode(self, frame: Frame) -> EncodedImage:
        return EncodedImage(data=b"jpg", media_type="image/jpeg")


class FakeCountRepository:
    def __init__(self) -> None:
        self._items: list[CountSnapshot] = []

    def append(self, snapshot: CountSnapshot) -> None:
        self._items.append(snapshot)

    def snapshot(self) -> tuple[CountSnapshot, ...]:
        return tuple(self._items)

    def clear(self) -> None:
        self._items.clear()


class FakeCountExporter:
    def export(self, history: Sequence[CountSnapshot], destination_dir: Path) -> Path:
        return destination_dir / "export.csv"


class FakeEventBus:
    def __init__(self) -> None:
        self._events: list[AppEvent] = []

    def publish(self, event: AppEvent) -> None:
        self._events.append(event)

    def drain(self) -> Sequence[AppEvent]:
        drained, self._events = self._events, []
        return drained


class FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return 0.0

    def sleep(self, seconds: float) -> None:
        return None


class FakeConfigProvider:
    def load(self) -> AppConfig:
        return AppConfig()


# Static conformance: mypy rejects any signature drift against the ports.
_STATIC_FRAME_SOURCE: FrameSource = FakeFrameSource()
_STATIC_DETECTOR: ObjectDetector = FakeObjectDetector()
_STATIC_ANNOTATOR: FrameAnnotator = FakeFrameAnnotator()
_STATIC_ENCODER: FrameEncoder = FakeFrameEncoder()
_STATIC_REPOSITORY: CountRepository = FakeCountRepository()
_STATIC_EXPORTER: CountExporter = FakeCountExporter()
_STATIC_BUS: EventBus = FakeEventBus()
_STATIC_CLOCK: Clock = FakeClock()
_STATIC_PROVIDER: ConfigProvider = FakeConfigProvider()


@pytest.mark.parametrize(
    ("port", "fake"),
    [
        (FrameSource, FakeFrameSource),
        (ObjectDetector, FakeObjectDetector),
        (FrameAnnotator, FakeFrameAnnotator),
        (FrameEncoder, FakeFrameEncoder),
        (CountRepository, FakeCountRepository),
        (CountExporter, FakeCountExporter),
        (EventBus, FakeEventBus),
        (Clock, FakeClock),
        (ConfigProvider, FakeConfigProvider),
    ],
)
def test_fake_conforms_to_port(port: type, fake: type) -> None:
    assert isinstance(fake(), port)


def test_incomplete_object_does_not_conform() -> None:
    class Partial:
        def now(self) -> datetime:
            return datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert not isinstance(Partial(), Clock)


def test_fakes_behave_through_the_ports() -> None:
    bus: EventBus = FakeEventBus()
    repo: CountRepository = FakeCountRepository()
    snapshot = CountSnapshot(counts={})

    repo.append(snapshot)
    assert repo.snapshot() == (snapshot,)
    repo.clear()
    assert repo.snapshot() == ()
    assert bus.drain() == []
