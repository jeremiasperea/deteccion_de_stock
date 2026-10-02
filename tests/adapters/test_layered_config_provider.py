"""Layered config provider: CLI > env > INI > defaults (D-A).

Everything is injected (argv, env, cwd, home), so no test touches the real
environment, working directory or home directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from depot_vision.adapters.layered_config_provider import LayeredConfigProvider
from depot_vision.domain.config import AppConfig
from depot_vision.domain.errors import InvalidConfiguration
from depot_vision.ports import ConfigProvider


@pytest.fixture
def cwd(tmp_path: Path) -> Path:
    path = tmp_path / "cwd"
    path.mkdir()
    return path


@pytest.fixture
def home(tmp_path: Path) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    return path


def _ini(path: Path, **values: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"{key} = {value}" for key, value in values.items())
    path.write_text(f"[depot_vision]\n{body}\n", encoding="utf-8")
    return path


def _provider(
    cwd: Path,
    home: Path,
    argv: tuple[str, ...] = (),
    env: dict[str, str] | None = None,
) -> LayeredConfigProvider:
    return LayeredConfigProvider(argv=argv, env=env or {}, cwd=cwd, home=home)


def test_conforms_to_config_provider_port(cwd: Path, home: Path) -> None:
    assert isinstance(_provider(cwd, home), ConfigProvider)


def test_no_layers_yields_defaults_and_missing_file_is_not_an_error(cwd: Path, home: Path) -> None:
    assert _provider(cwd, home).load() == AppConfig()


class TestPrecedence:
    def test_env_overrides_ini(self, cwd: Path, home: Path) -> None:
        _ini(cwd / "depot_vision.ini", camera_index="1", target_fps="10")

        config = _provider(cwd, home, env={"DEPOT_VISION_CAMERA_INDEX": "2"}).load()

        assert config.camera_index == 2
        assert config.target_fps == 10

    def test_cli_overrides_env_and_ini(self, cwd: Path, home: Path) -> None:
        _ini(cwd / "depot_vision.ini", camera_index="1")

        config = _provider(
            cwd,
            home,
            argv=("--camera-index", "3"),
            env={"DEPOT_VISION_CAMERA_INDEX": "2"},
        ).load()

        assert config.camera_index == 3

    def test_cli_equals_form_is_supported(self, cwd: Path, home: Path) -> None:
        config = _provider(cwd, home, argv=("--confidence-threshold=0.9",)).load()

        assert config.confidence_threshold == 0.9

    def test_unrelated_env_and_unknown_cli_flags_are_ignored(self, cwd: Path, home: Path) -> None:
        config = _provider(
            cwd, home, argv=("--unknown", "x"), env={"PATH": "/bin", "DEPOT_VISION_NOPE": "1"}
        ).load()

        assert config == AppConfig()


class TestFileSearchOrder:
    def test_env_pointed_file_wins_over_cwd_and_home(self, cwd: Path, home: Path) -> None:
        explicit = _ini(cwd.parent / "explicit.ini", camera_index="7")
        _ini(cwd / "depot_vision.ini", camera_index="5")
        _ini(home / ".config" / "depot_vision" / "config.ini", camera_index="6")

        config = _provider(cwd, home, env={"DEPOT_VISION_CONFIG": str(explicit)}).load()

        assert config.camera_index == 7

    def test_cwd_file_wins_over_home_file(self, cwd: Path, home: Path) -> None:
        _ini(cwd / "depot_vision.ini", camera_index="5")
        _ini(home / ".config" / "depot_vision" / "config.ini", camera_index="6")

        assert _provider(cwd, home).load().camera_index == 5

    def test_home_file_is_used_last(self, cwd: Path, home: Path) -> None:
        _ini(home / ".config" / "depot_vision" / "config.ini", camera_index="6")

        assert _provider(cwd, home).load().camera_index == 6

    def test_first_hit_wins_files_are_not_merged(self, cwd: Path, home: Path) -> None:
        _ini(cwd / "depot_vision.ini", camera_index="5")
        _ini(home / ".config" / "depot_vision" / "config.ini", target_fps="9")

        config = _provider(cwd, home).load()

        assert config.camera_index == 5
        assert config.target_fps == AppConfig().target_fps

    def test_env_pointing_at_missing_file_falls_through_to_next(
        self, cwd: Path, home: Path
    ) -> None:
        _ini(cwd / "depot_vision.ini", camera_index="5")

        config = _provider(cwd, home, env={"DEPOT_VISION_CONFIG": str(cwd / "nope.ini")}).load()

        assert config.camera_index == 5


class TestErrors:
    def test_coercion_failures_surface_as_invalid_configuration(
        self, cwd: Path, home: Path
    ) -> None:
        with pytest.raises(InvalidConfiguration, match="camera_index"):
            _provider(cwd, home, env={"DEPOT_VISION_CAMERA_INDEX": "abc"}).load()

    def test_malformed_ini_raises_invalid_configuration(self, cwd: Path, home: Path) -> None:
        (cwd / "depot_vision.ini").write_text("not an ini\n", encoding="utf-8")

        with pytest.raises(InvalidConfiguration):
            _provider(cwd, home).load()

    def test_cli_flag_without_value_raises_invalid_configuration(
        self, cwd: Path, home: Path
    ) -> None:
        with pytest.raises(InvalidConfiguration):
            _provider(cwd, home, argv=("--camera-index",)).load()
