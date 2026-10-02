"""``FrameSource`` adapter over ``cv2.VideoCapture`` (FT1).

The capture is obtained through an injected factory so tests never touch a
real camera. Frames are exposed to the domain as opaque BGR ``ndarray``s.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol

import cv2

from depot_vision.domain.config import AppConfig
from depot_vision.domain.errors import CameraUnavailable, FrameReadFailed
from depot_vision.domain.frames import Frame

logger = logging.getLogger(__name__)


class Capture(Protocol):
    """The subset of ``cv2.VideoCapture`` this adapter uses."""

    def set(self, prop: int, value: float) -> bool: ...

    def isOpened(self) -> bool: ...  # noqa: N802 - mirrors cv2.VideoCapture

    def read(self) -> tuple[bool, Any]: ...

    def release(self) -> None: ...


CaptureFactory = Callable[[int], Capture]


class OpenCVFrameSource:
    def __init__(
        self, config: AppConfig, capture_factory: CaptureFactory = cv2.VideoCapture
    ) -> None:
        self._config = config
        self._factory = capture_factory
        self._capture: Capture | None = None

    @property
    def is_open(self) -> bool:
        return self._capture is not None

    def open(self) -> None:
        if self._capture is not None:
            return
        try:
            capture = self._factory(self._config.camera_index)
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._config.frame_width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._config.frame_height)
            opened = capture.isOpened()
        except Exception as exc:
            raise CameraUnavailable(
                f"could not open camera {self._config.camera_index}: {exc}"
            ) from exc
        if not opened:
            _release_quietly(capture)
            raise CameraUnavailable(f"camera {self._config.camera_index} is not available")
        self._capture = capture

    def read(self) -> Frame:
        capture = self._capture
        if capture is None:
            raise FrameReadFailed("frame source is not open")
        try:
            ok, pixels = capture.read()
        except Exception as exc:
            raise FrameReadFailed(f"capture read raised: {exc}") from exc
        if not ok or pixels is None:
            raise FrameReadFailed("capture returned no frame")
        return Frame(pixels=pixels)

    def close(self) -> None:
        capture, self._capture = self._capture, None
        if capture is not None:
            _release_quietly(capture)


def _release_quietly(capture: Capture) -> None:
    try:
        capture.release()
    except Exception:
        logger.warning("capture release failed", exc_info=True)
