"""Tests for the FPS meter domain metric (PRESERVE 7).

Pure domain logic: FpsMeter never reads a clock itself — timestamps are
always supplied by the caller. This reproduces app.py:142-144's exact
formula, including its division-by-zero clamp.
"""

from __future__ import annotations

from depot_vision.domain.metrics import FpsMeter


class TestFpsMeterComputesFromSuppliedTimestamps:
    def test_half_second_gap_yields_two_fps(self) -> None:
        meter = FpsMeter()

        fps = meter.update(now=10.5, previous=10.0)

        assert fps == 2.0
        assert meter.fps == 2.0

    def test_tenth_second_gap_yields_ten_fps(self) -> None:
        meter = FpsMeter()

        fps = meter.update(now=1.1, previous=1.0)

        assert abs(fps - 10.0) < 1e-9


class TestFpsMeterPreservesMonolithZeroDivisionClamp:
    """app.py:143 clamps ``now - prev_time`` to at least ``1e-9`` so two
    frames sharing an identical timestamp never raise ZeroDivisionError."""

    def test_identical_timestamps_do_not_raise_and_yield_the_clamped_rate(self) -> None:
        meter = FpsMeter()

        fps = meter.update(now=5.0, previous=5.0)

        assert fps == 1.0 / 1e-9
