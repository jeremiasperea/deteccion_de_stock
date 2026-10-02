"""Tests for the frame value types (D-B): opaque pixels, no numpy."""

from __future__ import annotations

import dataclasses

import pytest

from depot_vision.domain.frames import EncodedImage, Frame, Overlay


class TestFrameTypes:
    def test_frame_carries_an_opaque_pixel_buffer(self) -> None:
        buffer = object()
        assert Frame(pixels=buffer).pixels is buffer

    def test_encoded_image_holds_data_and_media_type(self) -> None:
        image = EncodedImage(data=b"\xff\xd8", media_type="image/jpeg")
        assert (image.data, image.media_type) == (b"\xff\xd8", "image/jpeg")

    def test_overlay_holds_fps_and_frame_counter(self) -> None:
        overlay = Overlay(fps=29.5, frame_count=7)
        assert (overlay.fps, overlay.frame_count) == (29.5, 7)

    def test_value_types_are_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            Overlay(fps=1.0, frame_count=1).fps = 2.0  # type: ignore[misc]
