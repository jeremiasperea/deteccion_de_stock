"""Cv2Encoder against a recorded quality-75 JPEG of the fixture frame.

Raw JPEG bytes depend on the libjpeg build bundled with each OpenCV wheel, so
the golden is compared on decoded pixels (tolerance for IDCT rounding) plus
the size band that distinguishes quality 75 from the encoder default.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from depot_vision.adapters.cv2_encoder import Cv2Encoder
from depot_vision.domain.errors import EncodingFailed
from depot_vision.domain.frames import Frame
from depot_vision.ports import FrameEncoder

FIXTURES = Path(__file__).parent.parent / "fixtures"
TOLERANCE = 3


def _decode(data: bytes) -> np.ndarray:
    pixels = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert pixels is not None
    return pixels


def _source_frame() -> Frame:
    return Frame(pixels=_decode((FIXTURES / "frame_64x48.jpg").read_bytes()))


def test_conforms_to_frame_encoder_port() -> None:
    assert isinstance(Cv2Encoder(), FrameEncoder)


def test_encode_returns_jpeg_image() -> None:
    image = Cv2Encoder().encode(_source_frame())
    assert image.media_type == "image/jpeg"
    assert image.data[:2] == b"\xff\xd8"
    assert image.data[-2:] == b"\xff\xd9"


def test_encode_matches_golden_quality_75_jpeg() -> None:
    golden = (FIXTURES / "frame_64x48_q75.jpg").read_bytes()
    image = Cv2Encoder().encode(_source_frame())
    diff = np.abs(_decode(image.data).astype(int) - _decode(golden).astype(int))
    assert diff.max() <= TOLERANCE
    assert abs(len(image.data) - len(golden)) <= len(golden) * 0.05


def test_encode_uses_quality_75_not_default() -> None:
    frame = _source_frame()
    ok, q95 = cv2.imencode(".jpg", frame.pixels, [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert ok
    assert len(Cv2Encoder().encode(frame).data) < len(bytes(q95))


def test_encode_raises_typed_error_when_imencode_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cv2, "imencode", lambda *_a, **_k: (False, None))
    with pytest.raises(EncodingFailed):
        Cv2Encoder().encode(_source_frame())


def test_encode_wraps_cv2_exceptions_as_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise cv2.error("bad frame")

    monkeypatch.setattr(cv2, "imencode", boom)
    with pytest.raises(EncodingFailed):
        Cv2Encoder().encode(_source_frame())
