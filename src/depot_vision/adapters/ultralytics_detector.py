"""``ObjectDetector`` adapter over Ultralytics YOLO (FT8).

The model is built through an injected factory so tests never download
weights or run inference. Weights resolve package-relative through
``AppConfig.resolve_model_weights``; absolute overrides are logged here
because the domain never logs.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, cast

from depot_vision.domain.config import AppConfig
from depot_vision.domain.detections import BoundingBox, Detection
from depot_vision.domain.errors import InferenceFailed
from depot_vision.domain.frames import Frame

logger = logging.getLogger(__name__)


class Model(Protocol):
    """The subset of a YOLO model this adapter uses."""

    @property
    def names(self) -> Mapping[int, str]: ...

    def __call__(self, frame: Any, /, **kwargs: Any) -> Any: ...


ModelFactory = Callable[[str], Model]


def _yolo_factory(path: str) -> Model:
    from ultralytics import YOLO  # heavy import, deferred until a model is really needed

    # cast, not a type: ignore: stays valid whether or not ultralytics is installed.
    return cast(Model, YOLO(path))


class UltralyticsDetector:
    def __init__(self, config: AppConfig, model_factory: ModelFactory = _yolo_factory) -> None:
        self._config = config
        self._factory = model_factory
        self._model: Model | None = None

    def load(self) -> None:
        location = self._config.resolve_model_weights()
        if location.is_override:
            logger.warning("Using model weights override: %s", location.path)
        try:
            self._model = self._factory(str(location.path))
        except Exception as exc:
            raise InferenceFailed(f"could not load model weights {location.path}: {exc}") from exc

    def detect(self, frame: Frame) -> Sequence[Detection]:
        model = self._model
        if model is None:
            raise InferenceFailed("detector is not loaded")
        try:
            result = model(frame.pixels, verbose=False)[0]
            return [
                Detection(
                    class_name=model.names[int(box.cls[0])],
                    confidence=float(box.conf[0]),
                    bounding_box=BoundingBox(*map(int, box.xyxy[0])),
                )
                for box in result.boxes
            ]
        except Exception as exc:
            raise InferenceFailed(f"inference failed: {exc}") from exc
