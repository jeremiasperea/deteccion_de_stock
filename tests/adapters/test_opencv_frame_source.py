"""OpenCVFrameSource against fixture-driven fake captures (FT1); no real camera."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from depot_vision.adapters.opencv_frame_source import OpenCVFrameSource
from depot_vision.domain.config import AppConfig
from depot_vision.domain.errors import CameraUnavailable, FrameReadFailed
from depot_vision.ports import FrameSource

FIXTURE = Path(__file__).parent.parent / "fixtures" / "frame_64x48.jpg"


class FakeCapture:
    def __init__(self, *, opened: bool = True, frames: list[Any] | None = None) -> None:
        self._opened = opened
        self._frames = list(frames or [])
        self.props: dict[int, float] = {}
        self.released = 0
        self.release_error: Exception | None = None

    def set(self, prop: int, value: float) -> bool:
        self.props[prop] = value
        return True

    def isOpened(self) -> bool:  # noqa: N802 - mirrors cv2.VideoCapture
        return self._opened

    def read(self) -> tuple[bool, Any]:
        if not self._frames:
            return False, None
        frame = self._frames.pop(0)
        return (frame is not None), frame

    def release(self) -> None:
        self.released += 1
        if self.release_error:
            raise self.release_error
        self._opened = False


def _fixture_frame() -> np.ndarray:
    decoded = cv2.imdecode(np.fromfile(str(FIXTURE), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    return decoded


def _source(
    capture: FakeCapture, config: AppConfig | None = None
) -> tuple[OpenCVFrameSource, list[int]]:
    indexes: list[int] = []

    def factory(index: int) -> FakeCapture:
        indexes.append(index)
        return capture

    return OpenCVFrameSource(config or AppConfig(), capture_factory=factory), indexes


def test_conforms_to_frame_source_port() -> None:
    source, _ = _source(FakeCapture())
    assert isinstance(source, FrameSource)


def test_open_applies_camera_index_and_capture_size() -> None:
    capture = FakeCapture()
    source, indexes = _source(capture, AppConfig(camera_index=2, frame_width=320, frame_height=240))
    assert not source.is_open
    source.open()
    assert source.is_open
    assert indexes == [2]
    assert capture.props == {cv2.CAP_PROP_FRAME_WIDTH: 320, cv2.CAP_PROP_FRAME_HEIGHT: 240}


def test_open_raises_camera_unavailable_and_releases_when_not_opened() -> None:
    capture = FakeCapture(opened=False)
    source, _ = _source(capture)
    with pytest.raises(CameraUnavailable):
        source.open()
    assert not source.is_open
    assert capture.released == 1


def test_open_wraps_factory_errors() -> None:
    def boom(index: int) -> FakeCapture:
        raise RuntimeError("driver crashed")

    source = OpenCVFrameSource(AppConfig(), capture_factory=boom)
    with pytest.raises(CameraUnavailable):
        source.open()
    assert not source.is_open


def test_read_returns_domain_frame_with_pixels() -> None:
    pixels = _fixture_frame()
    source, _ = _source(FakeCapture(frames=[pixels]))
    source.open()
    frame = source.read()
    assert frame.pixels.shape == (48, 64, 3)
    assert np.array_equal(frame.pixels, pixels)


def test_read_raises_frame_read_failed_on_empty_frame() -> None:
    source, _ = _source(FakeCapture(frames=[]))
    source.open()
    with pytest.raises(FrameReadFailed):
        source.read()


def test_read_before_open_raises_frame_read_failed() -> None:
    source, _ = _source(FakeCapture())
    with pytest.raises(FrameReadFailed):
        source.read()


def test_close_is_idempotent_and_releases_once() -> None:
    capture = FakeCapture()
    source, _ = _source(capture)
    source.open()
    source.close()
    source.close()
    assert not source.is_open
    assert capture.released == 1


def test_close_without_open_is_noop() -> None:
    source, _ = _source(FakeCapture())
    source.close()
    assert not source.is_open


def test_close_swallows_release_errors_and_still_closes() -> None:
    capture = FakeCapture()
    capture.release_error = RuntimeError("release failed")
    source, _ = _source(capture)
    source.open()
    source.close()
    assert not source.is_open
