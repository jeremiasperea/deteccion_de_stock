"""Tests for AppConfig.from_mapping (D-A; runtime-configuration spec).

Pure domain logic: the mapping is the only input, no environment or
filesystem access is needed.
"""

from __future__ import annotations

import dataclasses
from pathlib import PurePath, PurePosixPath, PureWindowsPath

import pytest

from depot_vision.domain.config import WEIGHTS_DIR, AppConfig
from depot_vision.domain.errors import InvalidConfiguration


class TestDefaults:
    def test_empty_mapping_yields_documented_defaults(self) -> None:
        config = AppConfig.from_mapping({})

        assert config.confidence_threshold == 0.4
        assert config.model_weights == "yolov8n.pt"
        assert config.export_dir == "~"
        assert config.camera_index == 0
        assert config.frame_width == 640
        assert config.frame_height == 480
        assert config.target_fps == 30
        assert config.queue_soft_capacity == 1024
        assert config.queue_hard_ceiling == 8192
        assert config.stop_timeout_s == 5.0
        assert config.log_retention == 200

    def test_direct_construction_matches_defaults(self) -> None:
        assert AppConfig() == AppConfig.from_mapping({})

    def test_config_is_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            AppConfig().camera_index = 1  # type: ignore[misc]


class TestCoercion:
    def test_explicit_values_override_defaults(self) -> None:
        config = AppConfig.from_mapping(
            {
                "confidence_threshold": "0.75",
                "model_weights": "custom.pt",
                "export_dir": "/data/exports",
                "camera_index": "2",
                "frame_width": "1280",
                "frame_height": "720",
                "target_fps": "15",
                "queue_soft_capacity": "10",
                "queue_hard_ceiling": "20",
                "stop_timeout_s": "2.5",
                "log_retention": "50",
            }
        )

        assert config.confidence_threshold == 0.75
        assert config.model_weights == "custom.pt"
        assert config.export_dir == "/data/exports"
        assert config.camera_index == 2
        assert config.frame_width == 1280
        assert config.frame_height == 720
        assert config.target_fps == 15
        assert config.queue_soft_capacity == 10
        assert config.queue_hard_ceiling == 20
        assert config.stop_timeout_s == 2.5
        assert config.log_retention == 50

    def test_surrounding_whitespace_is_stripped(self) -> None:
        assert AppConfig.from_mapping({"camera_index": " 3 "}).camera_index == 3

    def test_unknown_keys_are_ignored(self) -> None:
        assert AppConfig.from_mapping({"unrelated": "x"}) == AppConfig()


class TestValidation:
    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("confidence_threshold", "abc"),
            ("confidence_threshold", "-0.1"),
            ("confidence_threshold", "1.5"),
            ("confidence_threshold", "nan"),
            ("camera_index", "x"),
            ("camera_index", "-1"),
            ("camera_index", "1.5"),
            ("frame_width", "0"),
            ("frame_height", "-480"),
            ("target_fps", "0"),
            ("stop_timeout_s", "0"),
            ("stop_timeout_s", "inf"),
            ("log_retention", "0"),
            ("queue_soft_capacity", "0"),
            ("model_weights", ""),
            ("export_dir", "  "),
        ],
    )
    def test_bad_value_raises_invalid_configuration(self, key: str, value: str) -> None:
        with pytest.raises(InvalidConfiguration, match=key):
            AppConfig.from_mapping({key: value})

    def test_hard_ceiling_below_soft_capacity_raises(self) -> None:
        with pytest.raises(InvalidConfiguration, match="queue_hard_ceiling"):
            AppConfig.from_mapping({"queue_soft_capacity": "100", "queue_hard_ceiling": "50"})

    def test_direct_construction_is_validated_too(self) -> None:
        with pytest.raises(InvalidConfiguration):
            AppConfig(frame_width=0)


class TestModelWeightsTraversalGuard:
    @pytest.mark.parametrize(
        "value",
        ["../evil.pt", "weights/../../evil.pt", "..\\evil.pt", "a/..", ".."],
    )
    def test_parent_traversal_raises(self, value: str) -> None:
        with pytest.raises(InvalidConfiguration, match="model_weights"):
            AppConfig.from_mapping({"model_weights": value})

    def test_plain_and_nested_relative_names_are_accepted(self) -> None:
        assert AppConfig.from_mapping({"model_weights": "sub/yolo.pt"}).model_weights == (
            "sub/yolo.pt"
        )

    def test_dotted_filename_is_not_traversal(self) -> None:
        assert AppConfig.from_mapping({"model_weights": "yolo..v2.pt"}).model_weights == (
            "yolo..v2.pt"
        )


class TestModelWeightsResolution:
    def test_weights_dir_is_package_relative(self) -> None:
        assert WEIGHTS_DIR.parts[-2:] == ("depot_vision", "weights")

    def test_relative_name_resolves_under_package_weights_dir(self) -> None:
        location = AppConfig().resolve_model_weights()

        assert location.path == WEIGHTS_DIR / "yolov8n.pt"
        assert location.is_override is False

    def test_nested_relative_name_resolves_under_weights_dir(self) -> None:
        location = AppConfig(model_weights="sub/yolo.pt").resolve_model_weights()

        assert location.path == WEIGHTS_DIR / "sub" / "yolo.pt"

    def test_resolution_ignores_cwd_and_honors_injected_weights_dir(self) -> None:
        base = PurePosixPath("/opt/pkg/depot_vision/weights")

        location = AppConfig().resolve_model_weights(weights_dir=base)

        assert location.path == base / "yolov8n.pt"

    def test_absolute_posix_path_is_accepted_and_flagged_as_override(self) -> None:
        location = AppConfig(model_weights="/models/custom.pt").resolve_model_weights()

        assert location.path == PurePath("/models/custom.pt")
        assert location.is_override is True

    def test_absolute_windows_path_is_accepted_and_flagged_as_override(self) -> None:
        location = AppConfig(model_weights="C:\\models\\custom.pt").resolve_model_weights()

        assert location.path == PureWindowsPath("C:\\models\\custom.pt")
        assert location.is_override is True

    def test_absolute_path_may_contain_dotdot_since_it_is_an_explicit_override(self) -> None:
        config = AppConfig.from_mapping({"model_weights": "/models/../other/custom.pt"})

        assert config.resolve_model_weights().is_override is True

    def test_relative_traversal_is_still_rejected(self) -> None:
        with pytest.raises(InvalidConfiguration, match="model_weights"):
            AppConfig.from_mapping({"model_weights": "../evil.pt"})


class TestExportDirResolution:
    def test_default_expands_to_injected_home(self) -> None:
        home = PurePosixPath("/home/operator")

        assert AppConfig().resolve_export_dir(home) == home

    def test_tilde_prefix_expands_under_home(self) -> None:
        home = PurePosixPath("/home/operator")

        assert AppConfig(export_dir="~/exports").resolve_export_dir(home) == home / "exports"

    def test_absolute_dir_is_returned_unchanged(self) -> None:
        home = PurePosixPath("/home/operator")

        assert AppConfig(export_dir="/data/out").resolve_export_dir(home) == PurePath("/data/out")

    def test_relative_dir_without_tilde_is_not_rewritten(self) -> None:
        home = PurePosixPath("/home/operator")

        assert AppConfig(export_dir="out").resolve_export_dir(home) == PurePath("out")
