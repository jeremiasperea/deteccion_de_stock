"""UltralyticsDetector with an injected fake model: no weights, no network (FT8)."""

from __future__ import annotations

import json
import logging
from pathlib import Path, PurePath
from typing import Any

import pytest

from depot_vision.adapters.ultralytics_detector import UltralyticsDetector
from depot_vision.domain.config import WEIGHTS_DIR, AppConfig
from depot_vision.domain.detections import BoundingBox, Detection
from depot_vision.domain.errors import InferenceFailed
from depot_vision.domain.frames import Frame
from depot_vision.ports import ObjectDetector

LOGGER = "depot_vision.adapters.ultralytics_detector"
DATA = json.loads((Path(__file__).parent.parent / "fixtures" / "detections.json").read_text())


class FakeBox:
    def __init__(self, entry: dict[str, Any]) -> None:
        self.cls = [entry["class_id"]]
        self.conf = [entry["confidence"]]
        self.xyxy = [entry["xyxy"]]


class FakeResult:
    def __init__(self, boxes: list[FakeBox]) -> None:
        self.boxes = boxes


class FakeModel:
    def __init__(self) -> None:
        self.names = {int(k): v for k, v in DATA["names"].items()}
        self.calls: list[tuple[Any, dict[str, Any]]] = []
        self.error: Exception | None = None

    def __call__(self, frame: Any, /, **kwargs: Any) -> list[FakeResult]:
        self.calls.append((frame, kwargs))
        if self.error:
            raise self.error
        return [FakeResult([FakeBox(e) for e in DATA["detections"]])]


def _detector(
    model: FakeModel, config: AppConfig | None = None
) -> tuple[UltralyticsDetector, list[str]]:
    paths: list[str] = []

    def factory(path: str) -> FakeModel:
        paths.append(path)
        return model

    return UltralyticsDetector(config or AppConfig(), model_factory=factory), paths


def test_conforms_to_object_detector_port() -> None:
    detector, _ = _detector(FakeModel())
    assert isinstance(detector, ObjectDetector)


def test_load_resolves_weights_package_relative_without_override_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    detector, paths = _detector(FakeModel())
    with caplog.at_level(logging.INFO, logger=LOGGER):
        detector.load()
    assert paths == [str(WEIGHTS_DIR / "yolov8n.pt")]
    assert not [r for r in caplog.records if "override" in r.getMessage().lower()]


def test_load_logs_absolute_override(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    weights = tmp_path / "custom.pt"
    detector, paths = _detector(FakeModel(), AppConfig(model_weights=str(weights)))
    with caplog.at_level(logging.INFO, logger=LOGGER):
        detector.load()
    assert paths == [str(PurePath(weights))]
    assert any("override" in r.getMessage().lower() for r in caplog.records)
    assert any(str(weights) in r.getMessage() for r in caplog.records)


def test_load_wraps_model_errors_as_inference_failed() -> None:
    def boom(path: str) -> FakeModel:
        raise FileNotFoundError(path)

    detector = UltralyticsDetector(AppConfig(), model_factory=boom)
    with pytest.raises(InferenceFailed):
        detector.load()


def test_detect_before_load_raises_inference_failed() -> None:
    detector, _ = _detector(FakeModel())
    with pytest.raises(InferenceFailed):
        detector.detect(Frame(pixels=object()))


def test_detect_converts_results_to_domain_detections_with_verbose_false() -> None:
    model = FakeModel()
    detector, _ = _detector(model)
    detector.load()
    pixels = object()
    detections = detector.detect(Frame(pixels=pixels))
    assert model.calls == [(pixels, {"verbose": False})]
    assert list(detections) == [
        Detection("person", 0.91, BoundingBox(4, 6, 40, 44)),
        Detection("bottle", 0.55, BoundingBox(10, 12, 30, 30)),
    ]


def test_detect_wraps_inference_errors() -> None:
    model = FakeModel()
    detector, _ = _detector(model)
    detector.load()
    model.error = RuntimeError("cuda oom")
    with pytest.raises(InferenceFailed):
        detector.detect(Frame(pixels=object()))


def test_detect_wraps_unknown_class_id() -> None:
    model = FakeModel()
    model.names = {}
    detector, _ = _detector(model)
    detector.load()
    with pytest.raises(InferenceFailed):
        detector.detect(Frame(pixels=object()))
