"""Tests for the domain's typed fault exceptions (FT6, replaces FIX 7/11).

Pure domain logic: no hardware, I/O, or mocks required to exercise it.
"""

from __future__ import annotations

import pytest

from depot_vision.domain.errors import (
    CameraUnavailable,
    ExportFailed,
    FrameReadFailed,
    InferenceFailed,
    InvalidConfiguration,
    InvalidTransition,
)

ALL_ERROR_TYPES = (
    CameraUnavailable,
    FrameReadFailed,
    InferenceFailed,
    ExportFailed,
    InvalidConfiguration,
    InvalidTransition,
)


class TestTypedFaultExceptionsExist:
    def test_all_six_error_types_are_exceptions(self) -> None:
        for error_type in ALL_ERROR_TYPES:
            assert issubclass(error_type, Exception)

    def test_all_six_error_types_are_pairwise_distinct(self) -> None:
        assert len(set(ALL_ERROR_TYPES)) == len(ALL_ERROR_TYPES)

    def test_camera_unavailable_is_not_frame_read_failed(self) -> None:
        with pytest.raises(CameraUnavailable):
            raise CameraUnavailable("camera index 0 could not be opened")

        with pytest.raises(FrameReadFailed):
            raise FrameReadFailed("read() returned no frame")

        # A CameraUnavailable must not also satisfy a FrameReadFailed catch —
        # they are distinct fault types, not aliases of one broad exception.
        with pytest.raises(CameraUnavailable):
            try:
                raise CameraUnavailable("still unavailable")
            except FrameReadFailed:
                pytest.fail("CameraUnavailable must not be caught as FrameReadFailed")

    def test_invalid_transition_carries_a_message(self) -> None:
        with pytest.raises(InvalidTransition, match="clear\\(\\) while worker is live"):
            raise InvalidTransition("clear() while worker is live")
