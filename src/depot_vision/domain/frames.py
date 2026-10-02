"""Frame value types shared across ports (D-B).

``PixelBuffer`` is deliberately opaque (``Any``): only adapters may
interpret it, which keeps numpy/cv2 out of the domain while a real frame
flows through untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Opaque pixel container; the domain never inspects it.
PixelBuffer = Any


@dataclass(frozen=True)
class Frame:
    """One captured (or annotated) video frame."""

    pixels: PixelBuffer


@dataclass(frozen=True)
class EncodedImage:
    """An encoded image ready for presentation, e.g. JPEG bytes."""

    data: bytes
    media_type: str


@dataclass(frozen=True)
class Overlay:
    """Live metrics for a rendered frame. Only ``fps`` is drawn onto the pixels;
    ``frame_count`` is carried for the caller and is not drawn on the frame."""

    fps: float
    frame_count: int
