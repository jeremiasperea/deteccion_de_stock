"""Tests for the retry/backoff domain policy (FT1).

Pure domain logic: no hardware, no I/O, no mocks, no sleeping. See
openspec/changes/refactor-clean-architecture/specs/capture-session/spec.md
("Retry With Bounded Backoff") and design.md D-E for the exact schedule
tables this pins.
"""

from __future__ import annotations

from depot_vision.domain.retry import RetryPolicy

# D-E: camera open / frame read — base 0.25s, cap 4.0s, 8 attempts, degrade after 2.
CAMERA_RETRY_POLICY = RetryPolicy(base_delay=0.25, max_delay=4.0, max_attempts=8, degrade_after=2)

# D-E: inference — base 0.25s, cap 1.0s, 3 attempts, degrade after 2.
INFERENCE_RETRY_POLICY = RetryPolicy(
    base_delay=0.25, max_delay=1.0, max_attempts=3, degrade_after=2
)


class TestCameraScheduleMatchesDesignTable:
    """D-E camera row: base 0.25s, cap 4.0s, 8 attempts (~19.75s total)."""

    def test_delay_doubles_then_caps_at_four_seconds(self) -> None:
        assert CAMERA_RETRY_POLICY.delay_for(1) == 0.25
        assert CAMERA_RETRY_POLICY.delay_for(2) == 0.5
        assert CAMERA_RETRY_POLICY.delay_for(3) == 1.0
        assert CAMERA_RETRY_POLICY.delay_for(4) == 2.0
        assert CAMERA_RETRY_POLICY.delay_for(5) == 4.0
        assert CAMERA_RETRY_POLICY.delay_for(8) == 4.0

    def test_total_schedule_across_eight_attempts_is_nineteen_point_seven_five(self) -> None:
        total = sum(CAMERA_RETRY_POLICY.delay_for(n) for n in range(1, 9))
        assert total == 19.75

    def test_is_exhausted_only_after_eight_attempts(self) -> None:
        assert CAMERA_RETRY_POLICY.is_exhausted(7) is False
        assert CAMERA_RETRY_POLICY.is_exhausted(8) is True


class TestInferenceScheduleMatchesDesignTable:
    """D-E inference row: base 0.25s, cap 1.0s, 3 attempts."""

    def test_delay_doubles_then_caps_at_one_second(self) -> None:
        assert INFERENCE_RETRY_POLICY.delay_for(1) == 0.25
        assert INFERENCE_RETRY_POLICY.delay_for(2) == 0.5
        assert INFERENCE_RETRY_POLICY.delay_for(3) == 1.0

    def test_is_exhausted_only_after_three_attempts(self) -> None:
        assert INFERENCE_RETRY_POLICY.is_exhausted(2) is False
        assert INFERENCE_RETRY_POLICY.is_exhausted(3) is True
