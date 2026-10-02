"""``ConfigProvider`` that layers CLI > environment > INI > defaults (D-A).

This adapter only *gathers* string layers; all coercion and validation is
delegated to ``AppConfig.from_mapping``. Argv, environment, working
directory and home are injected so tests never touch the real ones.
"""

from __future__ import annotations

import argparse
import configparser
import dataclasses
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NoReturn

from depot_vision.domain.config import AppConfig
from depot_vision.domain.errors import InvalidConfiguration

ENV_PREFIX = "DEPOT_VISION_"
CONFIG_ENV_VAR = "DEPOT_VISION_CONFIG"
INI_SECTION = "depot_vision"
_KEYS: tuple[str, ...] = tuple(field.name for field in dataclasses.fields(AppConfig))


class _ArgumentError(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise InvalidConfiguration(f"invalid command-line arguments: {message}")


class LayeredConfigProvider:
    def __init__(
        self,
        *,
        argv: Sequence[str] | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        home: Path | None = None,
    ) -> None:
        self._argv = tuple(argv) if argv is not None else ()
        self._env = env if env is not None else os.environ
        self._cwd = cwd if cwd is not None else Path.cwd()
        self._home = home if home is not None else Path.home()

    def load(self) -> AppConfig:
        merged: dict[str, str] = {}
        merged.update(self._ini_layer())
        merged.update(self._env_layer())
        merged.update(self._cli_layer())
        return AppConfig.from_mapping(merged)

    def _search_paths(self) -> list[Path]:
        paths: list[Path] = []
        explicit = self._env.get(CONFIG_ENV_VAR)
        if explicit:
            paths.append(Path(explicit))
        paths.append(self._cwd / "depot_vision.ini")
        paths.append(self._home / ".config" / "depot_vision" / "config.ini")
        return paths

    def _ini_layer(self) -> dict[str, str]:
        for path in self._search_paths():
            if not path.is_file():
                continue
            parser = configparser.ConfigParser(interpolation=None)
            try:
                parser.read_string(path.read_text(encoding="utf-8"), source=str(path))
            except (configparser.Error, OSError, UnicodeDecodeError) as exc:
                raise InvalidConfiguration(f"cannot read config file {path}: {exc}") from exc
            if not parser.has_section(INI_SECTION):
                return {}
            return {key: value for key, value in parser.items(INI_SECTION) if key in _KEYS}
        return {}

    def _env_layer(self) -> dict[str, str]:
        layer: dict[str, str] = {}
        for key in _KEYS:
            value = self._env.get(ENV_PREFIX + key.upper())
            if value is not None:
                layer[key] = value
        return layer

    def _cli_layer(self) -> dict[str, str]:
        parser = _ArgumentError(add_help=False, allow_abbrev=False)
        for key in _KEYS:
            parser.add_argument(f"--{key.replace('_', '-')}", dest=key)
        namespace, _unknown = parser.parse_known_args(self._argv)
        return {key: value for key, value in vars(namespace).items() if value is not None}
