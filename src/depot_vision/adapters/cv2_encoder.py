"""``FrameEncoder`` adapter producing JPEG bytes with OpenCV (quality 75)."""

from __future__ import annotations

import cv2

from depot_vision.domain.errors import EncodingFailed
from depot_vision.domain.frames import EncodedImage, Frame

JPEG_QUALITY = 75


class Cv2Encoder:
    def encode(self, frame: Frame) -> EncodedImage:
        try:
            ok, buffer = cv2.imencode(
                ".jpg", frame.pixels, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )
        except cv2.error as exc:
            raise EncodingFailed(f"JPEG encoding failed: {exc}") from exc
        if not ok:
            raise EncodingFailed("JPEG encoding failed")
        return EncodedImage(data=bytes(buffer), media_type="image/jpeg")
