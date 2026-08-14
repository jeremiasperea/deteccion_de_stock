"""Detection counting domain: turns raw detections into a CountSnapshot.

Pure domain logic — no hardware, I/O, or mocks required to exercise it.
See openspec/changes/refactor-clean-architecture/specs/detection-counting/spec.md
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from depot_vision.domain.detections import Detection

#: Default confidence threshold when no configuration is supplied (PRESERVE 2).
DEFAULT_CONFIDENCE_THRESHOLD = 0.4


@dataclass(frozen=True)
class TargetClass:
    """One of the ten recognized target classes (PRESERVE 1).

    ``label`` is the exact Spanish display label plus emoji, reproduced
    verbatim from the pre-refactor monolith's ``TARGET_CLASSES`` dict.
    """

    raw_name: str
    label: str


# Reproduced verbatim from app.py:19-30 (PRESERVE 1) — same keys, same
# emoji, same wording, same order. Do not translate, re-word, or re-order.
_TARGET_CLASS_LABELS: dict[str, str] = {
    "person": "👤 Persona",
    "bottle": "🍶 Botella",
    "cup": "☕ Taza",
    "backpack": "🎒 Mochila",
    "suitcase": "🧳 Valija",
    "chair": "🪑 Silla",
    "laptop": "💻 Laptop",
    "cell phone": "📱 Celular",
    "book": "📚 Libro",
    "clock": "⏰ Reloj",
}

#: Raw detector class name -> TargetClass, for exactly the ten target classes.
TARGET_CLASSES: Mapping[str, TargetClass] = {
    raw_name: TargetClass(raw_name=raw_name, label=label)
    for raw_name, label in _TARGET_CLASS_LABELS.items()
}


@dataclass(frozen=True)
class CountSnapshot:
    """Per-class detection counts for one processed frame."""

    counts: Mapping[TargetClass, int]

    def count_for(self, target_class: TargetClass) -> int:
        return self.counts.get(target_class, 0)


@dataclass(frozen=True)
class CountingPolicy:
    """Filters raw detections by target class and confidence, then counts."""

    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD

    def apply(self, detections: Sequence[Detection]) -> CountSnapshot:
        counts: dict[TargetClass, int] = {tc: 0 for tc in TARGET_CLASSES.values()}
        for detection in detections:
            target_class = TARGET_CLASSES.get(detection.class_name)
            if target_class is None:
                continue
            # Strictly-greater comparison, matching the monolith's `conf > 0.4`
            # (app.py:130): a detection exactly at the threshold is discarded.
            # PRESERVE 2 pins observable behavior, not just the default value.
            if detection.confidence <= self.confidence_threshold:
                continue
            counts[target_class] += 1
        return CountSnapshot(counts=counts)
