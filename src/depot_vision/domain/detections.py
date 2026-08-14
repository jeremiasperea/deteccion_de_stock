"""Raw detector output value objects.

Stdlib-only. See domain/counting.py for the policy that turns these into a
CountSnapshot.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned pixel bounding box, top-left/bottom-right corners."""

    x1: int
    y1: int
    x2: int
    y2: int


@dataclass(frozen=True)
class Detection:
    """One raw detector output for a single frame.

    ``class_name`` is the detector's raw class label (for example the COCO
    class name), not the Spanish display label — label lookup happens in
    ``domain.counting``.
    """

    class_name: str
    confidence: float
    bounding_box: BoundingBox
