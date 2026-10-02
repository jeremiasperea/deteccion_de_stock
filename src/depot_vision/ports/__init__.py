"""Ports: the nine Protocols the application layer depends on (D-B).

Only ``depot_vision.domain`` and the standard library may be imported here.
``PixelBuffer`` is opaque (see ``domain.frames``): only adapters interpret it.
Every protocol is ``runtime_checkable`` so tests can assert member presence;
signature conformance is checked statically by mypy.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from depot_vision.domain.config import AppConfig
from depot_vision.domain.counting import CountSnapshot
from depot_vision.domain.detections import Detection
from depot_vision.domain.events import AppEvent
from depot_vision.domain.frames import EncodedImage, Frame, Overlay

__all__ = [
    "Clock",
    "ConfigProvider",
    "CountExporter",
    "CountRepository",
    "EventBus",
    "FrameAnnotator",
    "FrameEncoder",
    "FrameSource",
    "ObjectDetector",
]


@runtime_checkable
class FrameSource(Protocol):
    def open(self) -> None:
        """Raises ``CameraUnavailable``."""
        ...

    def read(self) -> Frame:
        """Raises ``FrameReadFailed``."""
        ...

    def close(self) -> None:
        """Idempotent."""
        ...

    @property
    def is_open(self) -> bool: ...


@runtime_checkable
class ObjectDetector(Protocol):
    def load(self) -> None:
        """Raises ``InferenceFailed``."""
        ...

    def detect(self, frame: Frame) -> Sequence[Detection]:
        """Raises ``InferenceFailed``."""
        ...


@runtime_checkable
class FrameAnnotator(Protocol):
    def annotate(self, frame: Frame, detections: Sequence[Detection], overlay: Overlay) -> Frame:
        """Transfers ownership: the returned frame is the only valid handle afterwards."""
        ...


@runtime_checkable
class FrameEncoder(Protocol):
    def encode(self, frame: Frame) -> EncodedImage: ...


@runtime_checkable
class CountRepository(Protocol):
    def append(self, snapshot: CountSnapshot) -> None: ...

    def snapshot(self) -> tuple[CountSnapshot, ...]: ...

    def clear(self) -> None:
        """Raises ``InvalidTransition`` if a worker is live."""
        ...


@runtime_checkable
class CountExporter(Protocol):
    def export(self, history: Sequence[CountSnapshot], destination_dir: Path) -> Path: ...


@runtime_checkable
class EventBus(Protocol):
    def publish(self, event: AppEvent) -> None:
        """Never blocks, never raises."""
        ...

    def drain(self) -> Sequence[AppEvent]: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Wall clock, for CSV timestamps."""
        ...

    def monotonic(self) -> float:
        """For FPS and backoff."""
        ...

    def sleep(self, seconds: float) -> None: ...


@runtime_checkable
class ConfigProvider(Protocol):
    def load(self) -> AppConfig: ...
