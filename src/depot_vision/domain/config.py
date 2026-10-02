"""Runtime configuration: a pure, frozen ``AppConfig`` core (D-A).

Adapters gather string layers (CLI > env > INI > defaults) into one
``Mapping[str, str]``; ``AppConfig.from_mapping`` does all coercion and
validation here in the domain and raises ``InvalidConfiguration``. No
environment or filesystem access happens in this module: ``resolve_*``
only compute paths (pure ``PurePath`` operations) from injected inputs.
A ``ModelWeightsLocation`` flags absolute overrides so the adapter that
consumes it can log them; the domain itself never logs.
See openspec/changes/refactor-clean-architecture/specs/runtime-configuration/spec.md
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePath, PurePosixPath, PureWindowsPath
from typing import TypeVar

from depot_vision.domain.counting import DEFAULT_CONFIDENCE_THRESHOLD
from depot_vision.domain.errors import InvalidConfiguration

_T = TypeVar("_T", str, int, float)

#: Where relative ``model_weights`` names resolve: ``depot_vision/weights/``,
#: derived from this module's location, never from the working directory.
WEIGHTS_DIR: PurePath = PurePath(__file__).parent.parent / "weights"


@dataclass(frozen=True)
class ModelWeightsLocation:
    """Resolved weights path; ``is_override`` is True for an absolute configured path."""

    path: PurePath
    is_override: bool


def _check_positive_int(name: str, value: int) -> None:
    if value < 1:
        raise InvalidConfiguration(f"{name} must be >= 1, got {value}")


def _check_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise InvalidConfiguration(f"{name} must not be empty")


def _has_parent_traversal(path: str) -> bool:
    return ".." in re.split(r"[\\/]", path)


def _is_absolute(path: str) -> bool:
    return PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute()


@dataclass(frozen=True)
class AppConfig:
    """Resolved runtime configuration with the D-A key-table defaults."""

    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    model_weights: str = "yolov8n.pt"
    export_dir: str = "~"
    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    target_fps: int = 30
    queue_soft_capacity: int = 1024
    queue_hard_ceiling: int = 8192
    stop_timeout_s: float = 5.0
    log_retention: int = 200

    def __post_init__(self) -> None:
        if not (
            math.isfinite(self.confidence_threshold) and 0.0 <= self.confidence_threshold <= 1.0
        ):
            raise InvalidConfiguration(
                f"confidence_threshold must be within [0, 1], got {self.confidence_threshold}"
            )
        _check_non_empty("model_weights", self.model_weights)
        # An absolute path is an explicit operator override, so only relative
        # names (which resolve under the package weights dir) are traversal-guarded.
        if not _is_absolute(self.model_weights) and _has_parent_traversal(self.model_weights):
            raise InvalidConfiguration(
                f"model_weights must not contain '..' path segments, got {self.model_weights!r}"
            )
        _check_non_empty("export_dir", self.export_dir)
        if self.camera_index < 0:
            raise InvalidConfiguration(f"camera_index must be >= 0, got {self.camera_index}")
        _check_positive_int("frame_width", self.frame_width)
        _check_positive_int("frame_height", self.frame_height)
        _check_positive_int("target_fps", self.target_fps)
        _check_positive_int("queue_soft_capacity", self.queue_soft_capacity)
        _check_positive_int("queue_hard_ceiling", self.queue_hard_ceiling)
        if self.queue_hard_ceiling < self.queue_soft_capacity:
            raise InvalidConfiguration(
                "queue_hard_ceiling must be >= queue_soft_capacity, got "
                f"{self.queue_hard_ceiling} < {self.queue_soft_capacity}"
            )
        if not (math.isfinite(self.stop_timeout_s) and self.stop_timeout_s > 0):
            raise InvalidConfiguration(
                f"stop_timeout_s must be a finite number > 0, got {self.stop_timeout_s}"
            )
        _check_positive_int("log_retention", self.log_retention)

    def resolve_model_weights(self, weights_dir: PurePath = WEIGHTS_DIR) -> ModelWeightsLocation:
        """Relative names resolve under ``weights_dir``; absolute paths are overrides."""
        if _is_absolute(self.model_weights):
            # Keep the flavour of the configured path (POSIX vs Windows).
            override: PurePath = (
                PurePosixPath(self.model_weights)
                if PurePosixPath(self.model_weights).is_absolute()
                else PureWindowsPath(self.model_weights)
            )
            return ModelWeightsLocation(path=override, is_override=True)
        return ModelWeightsLocation(path=weights_dir / self.model_weights, is_override=False)

    def resolve_export_dir(self, home: PurePath) -> PurePath:
        """Expand a leading ``~`` against the injected ``home``; otherwise unchanged."""
        parts = re.split(r"[\\/]", self.export_dir)
        if parts[0] == "~":
            return home.joinpath(*[part for part in parts[1:] if part])
        return PurePath(self.export_dir)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> AppConfig:
        """Coerce string values over the defaults; unknown keys are ignored."""
        defaults = cls()
        return cls(
            confidence_threshold=_coerce(
                values, "confidence_threshold", float, defaults.confidence_threshold
            ),
            model_weights=_coerce(values, "model_weights", str, defaults.model_weights),
            export_dir=_coerce(values, "export_dir", str, defaults.export_dir),
            camera_index=_coerce(values, "camera_index", int, defaults.camera_index),
            frame_width=_coerce(values, "frame_width", int, defaults.frame_width),
            frame_height=_coerce(values, "frame_height", int, defaults.frame_height),
            target_fps=_coerce(values, "target_fps", int, defaults.target_fps),
            queue_soft_capacity=_coerce(
                values, "queue_soft_capacity", int, defaults.queue_soft_capacity
            ),
            queue_hard_ceiling=_coerce(
                values, "queue_hard_ceiling", int, defaults.queue_hard_ceiling
            ),
            stop_timeout_s=_coerce(values, "stop_timeout_s", float, defaults.stop_timeout_s),
            log_retention=_coerce(values, "log_retention", int, defaults.log_retention),
        )


def _coerce(values: Mapping[str, str], key: str, kind: type[_T], default: _T) -> _T:
    raw = values.get(key)
    if raw is None:
        return default
    try:
        return kind(raw.strip())
    except ValueError as exc:
        raise InvalidConfiguration(f"{key} must be a valid {kind.__name__}, got {raw!r}") from exc
