"""CountingPolicy.select: the single filter rule shared with apply()."""

from __future__ import annotations

from depot_vision.domain.counting import TARGET_CLASSES, CountingPolicy
from depot_vision.domain.detections import BoundingBox, Detection

BOX = BoundingBox(0, 0, 1, 1)


def _det(name: str, conf: float) -> Detection:
    return Detection(class_name=name, confidence=conf, bounding_box=BOX)


def test_select_keeps_target_classes_above_threshold_in_order() -> None:
    a, b = _det("person", 0.9), _det("cup", 0.5)
    result = CountingPolicy().select([a, _det("giraffe", 0.99), b])
    assert result == (a, b)
    assert isinstance(result, tuple)


def test_select_discards_detection_exactly_at_threshold() -> None:
    assert CountingPolicy(confidence_threshold=0.4).select([_det("person", 0.4)]) == ()


def test_apply_counts_exactly_the_selected_detections() -> None:
    policy = CountingPolicy()
    dets = [_det("person", 0.9), _det("person", 0.3), _det("book", 0.8), _det("dog", 0.9)]
    snapshot = policy.apply(dets)
    selected = policy.select(dets)
    for raw, target in TARGET_CLASSES.items():
        assert snapshot.count_for(target) == sum(d.class_name == raw for d in selected)
