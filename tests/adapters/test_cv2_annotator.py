"""Cv2Annotator against a recorded fixture frame and per-class golden pixels.

Goldens (``annotated_goldens.npz`` boxes/FPS alone, ``annotated_goldens_with_fps.npz``
box then FPS in the monolith's draw order) were produced by the monolith's original
drawing code (app.py ``detection_worker``) on ``frame_64x48.jpg``, not by the
adapter, so they pin PRESERVE 3 independently of the implementation.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from depot_vision.adapters.cv2_annotator import CLASS_COLORS, Cv2Annotator
from depot_vision.domain.counting import TARGET_CLASSES
from depot_vision.domain.detections import BoundingBox, Detection
from depot_vision.domain.frames import Frame, Overlay
from depot_vision.ports import FrameAnnotator

FIXTURES = Path(__file__).parent.parent / "fixtures"
BOX = BoundingBox(x1=8, y1=26, x2=50, y2=44)
CONFIDENCE = 0.87
OVERLAY = Overlay(fps=12.34, frame_count=7)


def _fixture_frame() -> Frame:
    data = np.fromfile(str(FIXTURES / "frame_64x48.jpg"), dtype=np.uint8)
    pixels = cv2.imdecode(data, cv2.IMREAD_COLOR)
    assert pixels is not None
    return Frame(pixels=pixels)


def test_conforms_to_frame_annotator_port() -> None:
    assert isinstance(Cv2Annotator(), FrameAnnotator)


def test_palette_covers_exactly_the_target_classes() -> None:
    assert set(CLASS_COLORS) == set(TARGET_CLASSES)
    assert CLASS_COLORS["person"] == (255, 100, 50)
    assert CLASS_COLORS["clock"] == (255, 150, 50)


@pytest.mark.parametrize("raw_name", list(TARGET_CLASSES))
def test_annotate_matches_golden_per_class(raw_name: str) -> None:
    goldens = np.load(FIXTURES / "annotated_goldens_with_fps.npz")
    detection = Detection(class_name=raw_name, confidence=CONFIDENCE, bounding_box=BOX)
    out = Cv2Annotator().annotate(_fixture_frame(), [detection], Overlay(fps=12.34, frame_count=7))
    assert np.array_equal(out.pixels, goldens[raw_name])


def test_annotate_skips_non_target_boxes_but_still_draws_fps() -> None:
    goldens = np.load(FIXTURES / "annotated_goldens.npz")
    detection = Detection(class_name="giraffe", confidence=0.9, bounding_box=BOX)
    out = Cv2Annotator().annotate(_fixture_frame(), [detection], Overlay(fps=12.34, frame_count=7))
    assert np.array_equal(out.pixels, goldens["fps_overlay"])


def test_annotate_draws_fps_overlay_matching_golden() -> None:
    goldens = np.load(FIXTURES / "annotated_goldens.npz")
    out = Cv2Annotator().annotate(_fixture_frame(), [], OVERLAY)
    assert np.array_equal(out.pixels, goldens["fps_overlay"])
