"""``FrameAnnotator`` adapter that draws with OpenCV primitives.

Drawing is reproduced verbatim from the monolith's ``detection_worker`` so the
rendered frames stay pixel-identical (PRESERVE 3). Frames are opaque BGR
``ndarray``s drawn into in place; the returned ``Frame`` is the valid handle.
The caller passes already-selected detections (``CountingPolicy.select``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import cv2

from depot_vision.domain.counting import TARGET_CLASSES
from depot_vision.domain.detections import Detection
from depot_vision.domain.frames import Frame, Overlay

BGR = tuple[int, int, int]

#: Fixed per-class BGR box colors, verbatim from app.py (PRESERVE 3).
CLASS_COLORS: Mapping[str, BGR] = {
    "person": (255, 100, 50),
    "bottle": (50, 200, 255),
    "cup": (100, 255, 150),
    "backpack": (200, 50, 255),
    "suitcase": (255, 200, 50),
    "chair": (50, 255, 200),
    "laptop": (255, 50, 200),
    "cell phone": (150, 255, 50),
    "book": (50, 150, 255),
    "clock": (255, 150, 50),
}

_FALLBACK_COLOR: BGR = (200, 200, 200)
_TAG_TEXT_COLOR: BGR = (10, 10, 10)
_FPS_COLOR: BGR = (0, 255, 120)


class Cv2Annotator:
    def annotate(self, frame: Frame, detections: Sequence[Detection], overlay: Overlay) -> Frame:
        """Draw boxes and tags, then the FPS overlay (monolith order; no frame counter)."""
        pixels = frame.pixels
        for detection in detections:
            _draw_detection(pixels, detection)
        cv2.putText(
            pixels,
            f"FPS: {overlay.fps:.1f}",
            (8, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            _FPS_COLOR,
            2,
        )
        return Frame(pixels=pixels)


def _draw_detection(pixels: Any, detection: Detection) -> None:
    target_class = TARGET_CLASSES.get(detection.class_name)
    if target_class is None:
        return
    box = detection.bounding_box
    color = CLASS_COLORS.get(detection.class_name, _FALLBACK_COLOR)
    cv2.rectangle(pixels, (box.x1, box.y1), (box.x2, box.y2), color, 2)
    tag = f"{target_class.label.split()[-1]} {detection.confidence:.0%}"
    cv2.rectangle(pixels, (box.x1, box.y1 - 22), (box.x1 + len(tag) * 9, box.y1), color, -1)
    cv2.putText(
        pixels,
        tag,
        (box.x1 + 3, box.y1 - 5),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        _TAG_TEXT_COLOR,
        1,
    )
