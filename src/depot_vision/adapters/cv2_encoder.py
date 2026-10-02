"""``FrameEncoder`` adapter producing JPEG bytes with OpenCV (quality 75)."""

from __future__ import annotations

import cv2

from depot_vision.domain.frames import EncodedImage, Frame

JPEG_QUALITY = 75


class Cv2Encoder:
    def encode(self, frame: Frame) -> EncodedImage:
        ok, buffer = cv2.imencode(".jpg", frame.pixels, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            raise ValueError("JPEG encoding failed")
        return EncodedImage(data=bytes(buffer), media_type="image/jpeg")
