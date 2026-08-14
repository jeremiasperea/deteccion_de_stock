"""Tests for the detection-counting domain (Phase 1a).

Pure domain logic: no hardware, no I/O, no mocks. See
openspec/changes/refactor-clean-architecture/specs/detection-counting/spec.md
"""

from __future__ import annotations

from depot_vision.domain.counting import TARGET_CLASSES, CountingPolicy
from depot_vision.domain.detections import BoundingBox, Detection

SOME_BOX = BoundingBox(x1=0, y1=0, x2=10, y2=10)


def _detection(class_name: str, confidence: float) -> Detection:
    return Detection(class_name=class_name, confidence=confidence, bounding_box=SOME_BOX)


class TestKnownTargetClassIsLabeled:
    """Scenario: Known target class is labeled (PRESERVE 1)."""

    def test_known_target_class_carries_exact_label_and_emoji(self) -> None:
        policy = CountingPolicy()
        detections = [_detection("bottle", confidence=0.9)]

        snapshot = policy.apply(detections)

        bottle_class = TARGET_CLASSES["bottle"]
        assert bottle_class.label == "🍶 Botella"
        assert snapshot.count_for(bottle_class) == 1


class TestNonTargetClassIsExcluded:
    """Scenario: Non-target class is excluded."""

    def test_non_target_coco_class_does_not_appear_in_snapshot(self) -> None:
        policy = CountingPolicy()
        detections = [_detection("dog", confidence=0.9)]

        snapshot = policy.apply(detections)

        assert sum(snapshot.counts.values()) == 0


class TestBelowThresholdDetectionDiscarded:
    """Scenario: Below-threshold detection discarded (PRESERVE 2)."""

    def test_detection_below_active_threshold_does_not_contribute(self) -> None:
        policy = CountingPolicy(confidence_threshold=0.4)
        detections = [_detection("chair", confidence=0.1)]

        snapshot = policy.apply(detections)

        assert sum(snapshot.counts.values()) == 0


    def test_detection_at_exactly_the_threshold_is_kept(self) -> None:
        policy = CountingPolicy(confidence_threshold=0.4)
        detections = [_detection("chair", confidence=0.4)]

        snapshot = policy.apply(detections)

        assert snapshot.count_for(TARGET_CLASSES["chair"]) == 1


class TestDefaultThresholdAppliesWithoutConfiguration:
    """Scenario: Default threshold applies without configuration (PRESERVE 2)."""

    def test_default_confidence_threshold_is_zero_point_four(self) -> None:
        policy = CountingPolicy()

        assert policy.confidence_threshold == 0.4


class TestSnapshotReflectsFrameDetections:
    """Scenario: Snapshot reflects frame detections."""

    def test_snapshot_has_one_count_per_present_class_and_zero_for_absent(self) -> None:
        policy = CountingPolicy()
        detections = [
            _detection("bottle", confidence=0.9),
            _detection("bottle", confidence=0.8),
            _detection("laptop", confidence=0.95),
        ]

        snapshot = policy.apply(detections)

        assert snapshot.count_for(TARGET_CLASSES["bottle"]) == 2
        assert snapshot.count_for(TARGET_CLASSES["laptop"]) == 1
        assert snapshot.count_for(TARGET_CLASSES["person"]) == 0
        assert len(snapshot.counts) == len(TARGET_CLASSES)


class TestSnapshotProductionHasNoSideEffects:
    """Scenario: Snapshot production has no side effects."""

    def test_running_the_policy_twice_on_equal_inputs_yields_equal_snapshots(self) -> None:
        policy = CountingPolicy()
        detections = [_detection("cup", confidence=0.7)]

        first_snapshot = policy.apply(detections)
        second_snapshot = policy.apply(detections)

        assert first_snapshot == second_snapshot
        assert first_snapshot.count_for(TARGET_CLASSES["cup"]) == 1
